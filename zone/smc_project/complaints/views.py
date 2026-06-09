from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.mail import send_mail
from django.db.models import Q, Count, Avg, F
from django.db.models.functions import Trim
from django.conf import settings
from .models import Complaint, Feedback, ComplaintStatusTimeline, AuditLog, Notification, ZoneDepartment
from .forms import ComplaintForm
from accounts.views import admin_or_officer_required, admin_only_required
from accounts.models import CustomUser, Officer
from PIL import Image, ExifTags
from math import radians, cos, sin, asin, sqrt
from accounts.forms import AdminUserChangeForm
from twilio.rest import Client
import json
import os
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from django.http import JsonResponse
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_protect
from django.utils import timezone
from django.db import close_old_connections
import folium
from folium.plugins import HeatMap
from datetime import datetime, timedelta
from django.db.models import DurationField, ExpressionWrapper
import threading
import logging


TIMELINE_STAGE_SEQUENCE = ['Submitted', 'In Review', 'Assigned', 'Resolved']
logger = logging.getLogger(__name__)


def _normalize_zone_key(zone_value):
    """Normalize zone labels to avoid unicode/punctuation mismatch issues."""
    if not zone_value:
        return ''
    normalized = re.sub(r'[^a-z0-9]+', ' ', zone_value.lower())
    return ' '.join(normalized.split())


def _canonical_zone_name(zone_value):
    """Map zone text variants to canonical Complaint.ZONE_CHOICES value."""
    if not zone_value:
        return ''

    normalized_input = _normalize_zone_key(zone_value)
    for zone_name, _label in Complaint.ZONE_CHOICES:
        if _normalize_zone_key(zone_name) == normalized_input:
            return zone_name
    return zone_value


def _sync_officer_complaint_counts(zones=None):
    """Update Officer.complaints_handled using zone-level SQL aggregates."""
    if zones:
        target_zones = {_canonical_zone_name(zone) for zone in zones if zone}
        target_zones.discard('')
    else:
        target_zones = {zone for zone, _ in Complaint.ZONE_CHOICES}

    for zone_name in target_zones:
        complaint_count = Complaint.objects.filter(zone=zone_name).count()
        Officer.objects.filter(zone=zone_name).exclude(complaints_handled=complaint_count).update(
            complaints_handled=complaint_count
        )


def _sync_zone_department_stats(zones=None):
    """Sync ZoneDepartment table with officer and complaint counts per zone."""
    complaint_counts = {}
    complaint_last_submitted_at = {}
    for zone in Complaint.objects.values_list('zone', flat=True):
        canonical_zone = _canonical_zone_name(zone)
        complaint_counts[canonical_zone] = complaint_counts.get(canonical_zone, 0) + 1

    for complaint_zone, complaint_date in Complaint.objects.values_list('zone', 'complaint_date'):
        canonical_zone = _canonical_zone_name(complaint_zone)
        if not canonical_zone or not complaint_date:
            continue
        existing = complaint_last_submitted_at.get(canonical_zone)
        if existing is None or complaint_date > existing:
            complaint_last_submitted_at[canonical_zone] = complaint_date

    officer_counts = {}
    for zone in Officer.objects.values_list('zone', flat=True):
        canonical_zone = _canonical_zone_name(zone)
        officer_counts[canonical_zone] = officer_counts.get(canonical_zone, 0) + 1

    all_zones = {zone for zone, _ in Complaint.ZONE_CHOICES}
    all_zones.update(complaint_counts.keys())
    all_zones.update(officer_counts.keys())

    if zones:
        zone_filter = {_canonical_zone_name(zone) for zone in zones if zone}
        all_zones = {zone for zone in all_zones if zone in zone_filter}

    for zone_name in all_zones:
        if not zone_name:
            continue

        new_zone_officers = officer_counts.get(zone_name, 0)
        new_zone_complaints = complaint_counts.get(zone_name, 0)
        new_last_submitted = complaint_last_submitted_at.get(zone_name)

        zone_row, created = ZoneDepartment.objects.get_or_create(
            zone_name=zone_name,
            defaults={
                'zone_officers': new_zone_officers,
                'zone_complaints': new_zone_complaints,
                'last_complaint_submitted_at': new_last_submitted,
            }
        )

        if created:
            continue

        if (
            zone_row.zone_officers != new_zone_officers or
            zone_row.zone_complaints != new_zone_complaints or
            zone_row.last_complaint_submitted_at != new_last_submitted
        ):
            zone_row.zone_officers = new_zone_officers
            zone_row.zone_complaints = new_zone_complaints
            zone_row.last_complaint_submitted_at = new_last_submitted
            zone_row.save(update_fields=['zone_officers', 'zone_complaints', 'last_complaint_submitted_at'])


def _create_timeline_event(complaint, stage, changed_by=None, timestamp=None, notes=''):
    """Create one timeline event per stage for each complaint."""
    ComplaintStatusTimeline.objects.get_or_create(
        complaint=complaint,
        stage=stage,
        defaults={
            'timestamp': timestamp or timezone.now(),
            'changed_by': changed_by,
            'notes': notes,
        },
    )


def _ensure_submitted_timeline(complaint):
    _create_timeline_event(
        complaint=complaint,
        stage='Submitted',
        changed_by=complaint.user,
        timestamp=complaint.complaint_date,
        notes='Complaint submitted by citizen',
    )


def _create_audit_log(actor, action, entity_type, entity_id, complaint=None, target_user=None, change_data=None, metadata=None):
    """Persist immutable audit event for critical system changes."""
    try:
        actor_user = actor if getattr(actor, 'is_authenticated', False) else None
        AuditLog.objects.create(
            actor=actor_user,
            actor_username=getattr(actor_user, 'username', '') or '',
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            complaint=complaint,
            target_user=target_user,
            change_data=change_data or {},
            metadata=metadata or {},
        )
    except Exception:
        # Audit failures must not block user-facing transaction.
        pass


def _create_notification_log(username, complaint_id, message, notification_type='sms', status='sent', sent_at=None):
    """Persist notification delivery attempt with timestamp."""
    try:
        Notification.objects.create(
            username=username,
            complaint_id=complaint_id,
            message=message,
            notification_type=notification_type,
            status=status,
            sent_at=sent_at or timezone.now(),
        )
    except Exception:
        # Notification logging should not block complaint flow.
        pass


def _send_submit_sms_async(user, complaint_id, phone, sent_time):
    """Send complaint submission SMS in background so request returns quickly."""
    sms_body = "Your complaint has been submitted successfully. You'll be notified of any updates."

    def _worker():
        try:
            close_old_connections()
            account_sid = settings.TWILIO_ACCOUNT_SID
            auth_token = settings.TWILIO_AUTH_TOKEN
            from_number = settings.TWILIO_PHONE_NUMBER

            client = Client(account_sid, auth_token)
            client.messages.create(
                body=sms_body,
                from_=from_number,
                to=f"+91{phone}"
            )

            _create_notification_log(
                username=user.username,
                complaint_id=complaint_id,
                message=sms_body,
                notification_type='sms',
                status='sent',
                sent_at=sent_time,
            )
        except Exception as exc:
            logger.error(f"SMS sending failed: {str(exc)}")
            _create_notification_log(
                username=user.username,
                complaint_id=complaint_id,
                message="Complaint submitted notification SMS failed.",
                notification_type='sms',
                status='failed',
                sent_at=sent_time,
            )
        finally:
            close_old_connections()

    threading.Thread(target=_worker, daemon=True).start()


def _send_reference_invite_email(request, feedback_obj):
    """Send a system invitation email to the provided reference email."""
    if not feedback_obj.reference_email:
        return

    register_url = request.build_absolute_uri('/accounts/register/')
    login_url = request.build_absolute_uri('/accounts/login/')

    subject = 'Invitation to Use Civic Zone Solution'
    message = (
        f"Hello,\n\n"
        f"{feedback_obj.fullname} has shared Civic Zone Solution with you.\n"
        "This platform helps citizens submit and track civic complaints online.\n\n"
        f"Create your account: {register_url}\n"
        f"Already registered? Login here: {login_url}\n\n"
        "Thank you,\n"
        "Civic Zone Solution Team"
    )

    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [feedback_obj.reference_email],
        fail_silently=False,
    )


def _get_zone_boundaries():
    """Return approximate geographical boundaries for Surat zones (lat/lng ranges)"""
    return {
        'West Zone (Rander)': {
            'lat_min': 21.15, 'lat_max': 21.25,
            'lng_min': 72.75, 'lng_max': 72.85
        },
        'Central Zone': {
            'lat_min': 21.15, 'lat_max': 21.25,
            'lng_min': 72.80, 'lng_max': 72.90
        },
        'North Zone (Katargam)': {
            'lat_min': 21.20, 'lat_max': 21.30,
            'lng_min': 72.75, 'lng_max': 72.85
        },
        'East Zone – A(Varachha)': {
            'lat_min': 21.20, 'lat_max': 21.30,
            'lng_min': 72.85, 'lng_max': 72.95
        },
        'East Zone – B(Sarthana)': {
            'lat_min': 21.25, 'lat_max': 21.35,
            'lng_min': 72.85, 'lng_max': 72.95
        },
        'South Zone – A (Udhna)': {
            'lat_min': 21.10, 'lat_max': 21.20,
            'lng_min': 72.80, 'lng_max': 72.90
        },
        'South Zone – B (Kanakpur)': {
            'lat_min': 21.05, 'lat_max': 21.15,
            'lng_min': 72.80, 'lng_max': 72.90
        },
        'South West Zone (Athwa)': {
            'lat_min': 21.10, 'lat_max': 21.20,
            'lng_min': 72.70, 'lng_max': 72.80
        },
        'South East Zone (Limbayat)': {
            'lat_min': 21.10, 'lat_max': 21.20,
            'lng_min': 72.85, 'lng_max': 72.95
        }
    }


def _validate_zone_match(zone_name, lat, lng):
    """Check if GPS coordinates fall within the selected zone boundaries"""
    if not zone_name or lat is None or lng is None:
        return False

    boundaries = _get_zone_boundaries().get(zone_name)
    if not boundaries:
        return False  # Unknown zone

    return (boundaries['lat_min'] <= lat <= boundaries['lat_max'] and
            boundaries['lng_min'] <= lng <= boundaries['lng_max'])


def _get_zone_center_coordinates(zone_name):
    """Return an approximate center point for a canonical Surat zone."""
    if not zone_name:
        return None

    zone_centers = {
        'West Zone (Rander)': (21.2218, 72.7872),
        'Central Zone': (21.1950, 72.8190),
        'North Zone (Katargam)': (21.2400, 72.8360),
        'East Zone – A(Varachha)': (21.2150, 72.8800),
        'East Zone – B(Sarthana)': (21.2370, 72.9070),
        'South Zone – A (Udhna)': (21.1540, 72.8420),
        'South Zone – B (Kanakpur)': (21.1700, 72.8650),
        'South West Zone (Athwa)': (21.1700, 72.7900),
        'South East Zone (Limbayat)': (21.1420, 72.8620),
    }

    canonical_zone = _canonical_zone_name(zone_name)
    return zone_centers.get(canonical_zone)


def _resolve_surat_local_address(address_text, selected_zone=None):
    """Accept well-known Surat areas/zones even when geocoding is incomplete."""
    if not address_text:
        return None

    normalized_text = _normalize_zone_key(address_text)
    if not normalized_text:
        return None

    local_area_aliases = {
        'central zone': 'Central Zone',
        'west zone': 'West Zone (Rander)',
        'rander': 'West Zone (Rander)',
        'north zone': 'North Zone (Katargam)',
        'katargam': 'North Zone (Katargam)',
        'east zone a': 'East Zone – A(Varachha)',
        'varachha': 'East Zone – A(Varachha)',
        'east zone b': 'East Zone – B(Sarthana)',
        'sarthana': 'East Zone – B(Sarthana)',
        'south zone a': 'South Zone – A (Udhna)',
        'udhna': 'South Zone – A (Udhna)',
        'south zone b': 'South Zone – B (Kanakpur)',
        'kanakpur': 'South Zone – B (Kanakpur)',
        'south west zone': 'South West Zone (Athwa)',
        'athwa': 'South West Zone (Athwa)',
        'south east zone': 'South East Zone (Limbayat)',
        'limbayat': 'South East Zone (Limbayat)',
    }

    for alias, canonical_zone in local_area_aliases.items():
        if alias in normalized_text:
            coords = _get_zone_center_coordinates(canonical_zone)
            if coords:
                return {
                    'location': address_text.strip(),
                    'address': address_text.strip(),
                    'lat': coords[0],
                    'lon': coords[1],
                    'zone': canonical_zone,
                }

    if 'surat' in normalized_text:
        coords = _get_zone_center_coordinates(selected_zone) if selected_zone else None
        return {
            'location': address_text.strip(),
            'address': address_text.strip(),
            'lat': coords[0] if coords else None,
            'lon': coords[1] if coords else None,
            'zone': _canonical_zone_name(selected_zone) if selected_zone else '',
        }

    return None


def _convert_to_decimal_degrees(value):
    """Convert GPS coordinates in EXIF format to decimal degrees."""
    try:
        degrees = float(value[0][0]) / float(value[0][1])
        minutes = float(value[1][0]) / float(value[1][1])
        seconds = float(value[2][0]) / float(value[2][1])
        return degrees + (minutes / 60.0) + (seconds / 3600.0)
    except Exception:
        return None


def _extract_image_gps(image_file):
    """Extract GPS latitude and longitude from image EXIF (if available)."""
    try:
        image = Image.open(image_file)
        exif_data = image._getexif()
        if not exif_data:
            return None

        gps_info = {}
        for tag_id, value in exif_data.items():
            tag = ExifTags.TAGS.get(tag_id, tag_id)
            if tag == 'GPSInfo':
                for key in value:
                    sub_tag = ExifTags.GPSTAGS.get(key, key)
                    gps_info[sub_tag] = value[key]

        if not gps_info:
            return None

        lat = gps_info.get('GPSLatitude')
        lat_ref = gps_info.get('GPSLatitudeRef')
        lon = gps_info.get('GPSLongitude')
        lon_ref = gps_info.get('GPSLongitudeRef')

        if not lat or not lon or not lat_ref or not lon_ref:
            return None

        lat_decimal = _convert_to_decimal_degrees(lat)
        lon_decimal = _convert_to_decimal_degrees(lon)

        if lat_decimal is None or lon_decimal is None:
            return None

        if lat_ref and lat_ref.upper() == 'S':
            lat_decimal = -lat_decimal
        if lon_ref and lon_ref.upper() == 'W':
            lon_decimal = -lon_decimal

        return (lat_decimal, lon_decimal)

    except Exception:
        return None


def _reverse_geocode_address(lat, lng):
    """Resolve human-readable location/address from coordinates using Nominatim."""
    if lat is None or lng is None:
        return None

    params = urlencode({
        'format': 'jsonv2',
        'lat': str(lat),
        'lon': str(lng),
        'addressdetails': 1,
        'accept-language': 'en',
        'zoom': 18,
    })
    url = f"https://nominatim.openstreetmap.org/reverse?{params}"

    req = Request(
        url,
        headers={
            'User-Agent': 'smc-project-complaints/1.0',
        },
    )

    try:
        with urlopen(req, timeout=6) as response:
            payload = json.loads(response.read().decode('utf-8'))
    except Exception:
        return None

    display_name = (payload.get('display_name') or '').strip()
    address = payload.get('address') or {}

    location_parts = [
        address.get('road') or address.get('pedestrian') or address.get('footway'),
        address.get('suburb') or address.get('neighbourhood'),
        address.get('city') or address.get('town') or address.get('village'),
    ]
    concise_location = ', '.join([part for part in location_parts if part])

    return {
        'location': concise_location or display_name,
        'address': display_name,
    }


def _is_surat_geocoded_result(payload):
    """Return True when Nominatim payload clearly points to Surat, Gujarat, India."""
    if not payload:
        return False

    address = payload.get('address') or {}
    display_name = (payload.get('display_name') or '').lower()

    city_like_parts = [
        address.get('city'),
        address.get('town'),
        address.get('municipality'),
        address.get('county'),
        address.get('state_district'),
    ]
    city_blob = ' '.join([str(part).lower() for part in city_like_parts if part])

    state_blob = (address.get('state') or '').lower()
    country_blob = (address.get('country') or '').lower()

    has_surat = 'surat' in city_blob or 'surat' in display_name
    has_gujarat = 'gujarat' in state_blob or 'gujarat' in display_name
    has_india = 'india' in country_blob or 'india' in display_name

    return has_surat and has_gujarat and has_india


def _geocode_address_details(address_text):
    """Geocode address via Nominatim and return first detailed payload."""
    if not address_text:
        return None

    params = urlencode({
        'format': 'jsonv2',
        'q': address_text,
        'addressdetails': 1,
        'accept-language': 'en',
        'limit': 1,
    })
    url = f"https://nominatim.openstreetmap.org/search?{params}"

    req = Request(
        url,
        headers={
            'User-Agent': 'smc-project-complaints/1.0',
        },
    )

    try:
        with urlopen(req, timeout=6) as response:
            payload = json.loads(response.read().decode('utf-8'))
    except Exception:
        return None

    if not isinstance(payload, list) or not payload:
        return None

    return payload[0]

@login_required
def dashboard(request):
    # Check if user has appropriate role
    if request.user.role != 'user':
        messages.error(request, "Access denied. User login only.")
        return redirect('login')
    
    # Get filter parameter
    filter_status = request.GET.get('filter', '')
    
    # Get items per page
    items_per_page = request.GET.get('items', '10')
    valid_items = ['5', '10', '20', '50']
    if items_per_page not in valid_items:
        items_per_page = '10'
    items_per_page = int(items_per_page)
    
    # Get complaints for current user
    complaints = Complaint.objects.filter(user=request.user)
    
    # Apply filter
    if filter_status == 'pending':
        complaints = complaints.filter(status='Pending')
    elif filter_status == 'progress':
        complaints = complaints.filter(status='In Progress')
    elif filter_status == 'resolved':
        complaints = complaints.filter(status='Resolved')
    
    # Pagination
    paginator = Paginator(complaints, items_per_page)
    page = request.GET.get('page', 1)
    
    try:
        complaints_page = paginator.page(page)
    except PageNotAnInteger:
        complaints_page = paginator.page(1)
    except EmptyPage:
        complaints_page = paginator.page(paginator.num_pages)
    
    # Get counts for notification
    total_complaints = complaints.count()
    resolved_count = complaints.filter(status='Resolved').count()
    
    # Calculate pagination info
    current_page = complaints_page.number
    start_item = (current_page - 1) * items_per_page + 1
    end_item = min(start_item + items_per_page - 1, total_complaints)
    
    # Generate page range for pagination display
    page_range = []
    total_pages = paginator.num_pages
    
    if total_pages <= 5:
        page_range = range(1, total_pages + 1)
    else:
        if current_page <= 3:
            page_range = range(1, 6)
        elif current_page >= total_pages - 2:
            page_range = range(total_pages - 4, total_pages + 1)
        else:
            page_range = range(current_page - 2, current_page + 3)
    
    context = {
        'user': request.user,
        'complaints': complaints_page,
        'filter': filter_status,
        'items_per_page': items_per_page,
        'current_page': current_page,
        'total_pages': total_pages,
        'total_rows': total_complaints,
        'start_item': start_item,
        'end_item': end_item,
        'resolved_count': resolved_count,
        'page_range': page_range,
    }
    
    return render(request, 'complaints/dashboard.html', context)


@login_required
def complaint_analysis(request):
    if request.user.role != 'user':
        messages.error(request, "Access denied. User login only.")
        return redirect('login')

    user_complaints = Complaint.objects.filter(user=request.user)

    pending_count = user_complaints.filter(status='Pending').count()
    in_progress_count = user_complaints.filter(status='In Progress').count()
    resolved_count = user_complaints.filter(status='Resolved').count()
    total_complaints = user_complaints.count()

    status_labels = ['Pending', 'In Progress', 'Resolved']
    status_counts = [pending_count, in_progress_count, resolved_count]

    resolved_percentage = 0
    pending_percentage = 0
    in_progress_percentage = 0
    resolved_percentage_end = 100
    pending_percentage_end = 0
    in_progress_percentage_end = 0

    if total_complaints > 0:
        pending_percentage = round((pending_count / total_complaints) * 100, 2)
        in_progress_percentage = round((in_progress_count / total_complaints) * 100, 2)
        resolved_percentage = round((resolved_count / total_complaints) * 100, 2)
        pending_percentage_end = pending_percentage
        in_progress_percentage_end = round(pending_percentage + in_progress_percentage, 2)

    context = {
        'total_complaints': total_complaints,
        'pending_count': pending_count,
        'in_progress_count': in_progress_count,
        'resolved_count': resolved_count,
        'resolved_percentage': resolved_percentage,
        'pending_percentage_end': pending_percentage_end,
        'in_progress_percentage_end': in_progress_percentage_end,
        'status_labels_json': json.dumps(status_labels),
        'status_counts_json': json.dumps(status_counts),
    }

    return render(request, 'complaints/analysis.html', context)

@login_required
def submit_complaint(request):
    if not request.user.is_authenticated or request.user.role != 'user':
        messages.error(request, "Access denied. User login only.")
        return redirect('login')

    if request.method == 'POST':
        form = ComplaintForm(request.POST, request.FILES)
        force_submit = request.POST.get('force_submit', '0') == '1'

        if form.is_valid():
            final_category = form.cleaned_data['category']
            if final_category == 'Other':
                final_category = form.cleaned_data.get('other_category', '').strip()

            final_subcategory = form.cleaned_data['subcategory']
            if final_subcategory == 'Other':
                final_subcategory = form.cleaned_data.get('other_subcategory', '').strip()

            if not force_submit:
                from .services.duplicate_detection import detect_duplicates

                dup_result = detect_duplicates({
                    'category': final_category,
                    'subcategory': final_subcategory,
                    'zone': form.cleaned_data.get('zone', ''),
                    'location': form.cleaned_data.get('location', ''),
                    'description': form.cleaned_data.get('description', ''),
                })

                if dup_result['is_exact'] or dup_result['is_similar']:
                    context = {
                        'form': form,
                        'complaints_count': Complaint.objects.filter(user=request.user).count(),
                        'subcategories_by_category': get_subcategories_by_category(),
                        'duplicate_warning': dup_result,
                    }
                    return render(request, 'complaints/submit_complaint.html', context)

            # Handle image geotag requirements - IMAGE IS OPTIONAL, GPS IS OPTIONAL
            proof_image = form.cleaned_data.get('proof_image')
            form_lat = form.cleaned_data.get('latitude')
            form_lng = form.cleaned_data.get('longitude')

            lat_value = None
            lng_value = None

            if proof_image:
                # Try to extract GPS from image if available
                parsed_image_coords = _extract_image_gps(proof_image)
                if parsed_image_coords:
                    image_lat, image_lng = parsed_image_coords
                    lat_value = image_lat
                    lng_value = image_lng

                    # Validate that image GPS location matches selected zone (optional)
                    selected_zone = form.cleaned_data.get('zone')
                    if not _validate_zone_match(selected_zone, image_lat, image_lng):
                        # Just warn, don't reject
                        messages.warning(request, f'Image GPS location ({image_lat:.6f}, {image_lng:.6f}) does not match the selected zone "{selected_zone}". Using image location anyway.')

            if form_lat is not None and form_lng is not None:
                lat_value = float(form_lat)
                lng_value = float(form_lng)

            # Validate typed address, but only geocode when coordinates were not already supplied.
            address_value = (form.cleaned_data.get('address') or '').strip()
            selected_zone = _canonical_zone_name(form.cleaned_data.get('zone', ''))
            if address_value and (lat_value is None or lng_value is None):
                geocoded_address = _geocode_address_details(address_value)
                if geocoded_address and _is_surat_geocoded_result(geocoded_address):
                    # Prefer geocoded coordinates from the typed address.
                    try:
                        geocoded_lat = float(geocoded_address.get('lat'))
                        geocoded_lng = float(geocoded_address.get('lon'))
                        lat_value = geocoded_lat
                        lng_value = geocoded_lng
                    except (TypeError, ValueError):
                        form.add_error('address', 'Unable to read coordinates for the provided Surat address.')
                        context = {
                            'form': form,
                            'complaints_count': Complaint.objects.filter(user=request.user).count(),
                            'subcategories_by_category': get_subcategories_by_category(),
                        }
                        return render(request, 'complaints/submit_complaint.html', context)
                else:
                    local_address = _resolve_surat_local_address(address_value, selected_zone)
                    if local_address:
                        if not lat_value or not lng_value:
                            lat_value = local_address.get('lat')
                            lng_value = local_address.get('lon')
                    else:
                        form.add_error('address', 'Please enter a valid Surat area, zone, or full address.')
                        context = {
                            'form': form,
                            'complaints_count': Complaint.objects.filter(user=request.user).count(),
                            'subcategories_by_category': get_subcategories_by_category(),
                        }
                        return render(request, 'complaints/submit_complaint.html', context)

            if not lat_value or not lng_value:
                form.add_error(None, 'Unable to determine location. Please provide a detailed address or upload an image with GPS data.')
                context = {
                    'form': form,
                    'complaints_count': Complaint.objects.filter(user=request.user).count(),
                    'subcategories_by_category': get_subcategories_by_category(),
                }
                return render(request, 'complaints/submit_complaint.html', context)

            complaint = form.save(commit=False)
            complaint.user = request.user
            complaint.status = 'Pending'
            complaint.complaint_date = timezone.now()
            complaint.category = final_category
            complaint.subcategory = final_subcategory

            # Set coordinates
            complaint.latitude = lat_value
            complaint.longitude = lng_value

            location_value = (form.cleaned_data.get('location') or '').strip()
            address_value = (form.cleaned_data.get('address') or '').strip()

            # Keep the submitted text fields as-is to avoid a blocking reverse-geocode call.
            # The map fields already carry the authoritative coordinates.
            complaint.location = location_value or address_value or complaint.location
            complaint.address = address_value or complaint.address

            if force_submit:
                from .services.duplicate_detection import detect_duplicates

                dup_result = detect_duplicates({
                    'category': final_category,
                    'subcategory': final_subcategory,
                    'zone': complaint.zone,
                    'location': form.cleaned_data.get('location', ''),
                    'description': form.cleaned_data.get('description', ''),
                })

                if dup_result['matches']:
                    best_match = dup_result['matches'][0]
                    complaint.is_duplicate = True
                    complaint.original_complaint = best_match['complaint']
                    complaint.similarity_score = best_match['similarity_score']

            complaint.save()
            _sync_officer_complaint_counts(zones=[complaint.zone])
            _ensure_submitted_timeline(complaint)
            _create_audit_log(
                actor=request.user,
                action='complaint_created',
                entity_type='complaint',
                entity_id=complaint.complaint_id,
                complaint=complaint,
                target_user=request.user,
                change_data={
                    'status': complaint.status,
                    'zone': complaint.zone,
                    'category': complaint.category,
                    'subcategory': complaint.subcategory,
                },
            )

            to_number = form.cleaned_data['phone']
            sent_time = complaint.complaint_date or timezone.now()
            _send_submit_sms_async(
                user=request.user,
                complaint_id=complaint.complaint_id,
                phone=to_number,
                sent_time=sent_time,
            )
            messages.success(request, f"Complaint submitted successfully! SMS will be sent to {to_number} shortly.")

            return redirect('dashboard')
    else:
        form = ComplaintForm()

    complaints = Complaint.objects.filter(user=request.user)

    context = {
        'form': form,
        'complaints_count': complaints.count(),
        'subcategories_by_category': get_subcategories_by_category(),
    }

    return render(request, 'complaints/submit_complaint.html', context)


@login_required
def check_duplicate_realtime(request):
    if request.user.role != 'user':
        return JsonResponse({'error': 'Access denied'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'Invalid JSON payload'}, status=400)

    category = (payload.get('category') or '').strip()
    other_category = (payload.get('other_category') or '').strip()
    if category == 'Other':
        category = other_category

    subcategory = (payload.get('subcategory') or '').strip()
    other_subcategory = (payload.get('other_subcategory') or '').strip()
    if subcategory == 'Other':
        subcategory = other_subcategory

    from .services.duplicate_detection import detect_duplicates

    result = detect_duplicates({
        'category': category,
        'subcategory': subcategory,
        'zone': (payload.get('zone') or '').strip(),
        'location': (payload.get('location') or '').strip(),
        'description': (payload.get('description') or '').strip(),
    })

    serialized_matches = []
    for item in result['matches']:
        complaint = item['complaint']
        serialized_matches.append({
            'complaint_id': complaint.complaint_id,
            'category': complaint.category,
            'description': complaint.description,
            'status': complaint.status,
            'date': complaint.complaint_date.strftime('%d %b %Y %H:%M'),
            'similarity_score': item['similarity_score'],
            'match_type': item['match_type'],
        })

    return JsonResponse({
        'is_exact': result['is_exact'],
        'is_similar': result['is_similar'],
        'best_score': result['best_score'],
        'matches': serialized_matches,
    })


def get_subcategories_by_category():
    """Return subcategories grouped by category"""
    return {
        '1. Water Supply': [
            'No water supply',
            'Leaking pipes',
            'Low water pressure',
            'Contaminated water',
            'Issues with water meters',
            'Repair of standposts or handpumps',
            'Illegal water connections',
        ],
        '2. Drainage & Stormwater': [
            'Overflowing or choked drainage',
            'Broken or open manholes',
            'Leakage in main drainage pipelines',
            'Overflowing soak pits or septic tanks',
            'Stormwater logging on public roads or open plots',
        ],
        '3. Health & Hospitals/Dispensaries': [
            'Mosquito breeding or water logging',
            'Nuisance or other mosquito-borne disease concerns',
            'Mismanagement in hospitals and dispensaries',
            'Improper disposal of biomedical waste',
            'Issues related to SMIMER College & Hospital',
            'Complaints regarding hospital staff',
        ],
        '4. Public Toilets': [
            'Unclean public toilets',
            'Lack of water or electricity supply',
            'Open defecation in public places',
            'Need for repairs in public toilets',
        ],
        '5. Food & Hygiene': [
            'Food adulteration or food poisoning',
            'Unregistered food vendors',
            'Illegal slaughterhouses',
            'Unhygienic conditions in food establishments',
            'Quality issues with food',
        ],
        '6. Streetlights, Roads, and Footpaths': [
            'Non-functional streetlights',
            'Collapsed poles or lights burning during the day',
            'High mast or LED streetlights not working',
            'Damaged roads, footpaths, or road dividers',
            'Missing markings on bumps or zebra crossings',
            'Potholes or other road maintenance issues',
        ],
        '7. Solid Waste Management': [
            'Irregular garbage collection',
            'Overflowing dustbins',
            'Littering in public places',
            'Illegal dumping of waste',
            'Burning of waste',
            'Dead animal removal',
            'Stray animals causing nuisance',
        ],
        '8. Parks & Gardens': [
            'Poor maintenance of public parks and gardens',
            'Damaged equipment or facilities',
            'Unclean surroundings',
            'Issues related to Sarthana Nature Park',
        ],
        '9. Civic Centers & Administrative Services': [
            'Issues related to services at City Civic Centers',
            'Complaints about staff behavior or inefficiency',
            'Problems with documentation or service delivery',
        ],
        '10. Miscellaneous': [
            'Complaints related to the SMC website',
            'Feedback on budget allocations',
            'Issues pertaining to specific zones',
        ],
    }

@login_required
def edit_complaint(request, complaint_id):
    if request.user.role != 'user':
        messages.error(request, "Access denied. User login only.")
        return redirect('login')
    
    complaint = get_object_or_404(Complaint, complaint_id=complaint_id, user=request.user)
    
    if complaint.status != 'Pending':
        messages.error(request, "Only pending complaints can be edited.")
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = ComplaintForm(request.POST, request.FILES, instance=complaint)
        
        if form.is_valid():
            old_values = {
                'category': complaint.category,
                'subcategory': complaint.subcategory,
                'zone': complaint.zone,
                'location': complaint.location,
                'description': complaint.description,
                'phone': complaint.phone,
            }
            # Store old image path before any changes
            old_image_path = None
            if complaint.proof_image:
                try:
                    old_image_path = complaint.proof_image.path
                except:
                    old_image_path = None
            
            # Check if new image was uploaded
            new_image = 'proof_image' in request.FILES
            
            # Handle category logic before saving
            category = form.cleaned_data.get('category')
            if category == 'Other':
                complaint.category = form.cleaned_data.get('other_category', '')
            else:
                complaint.category = category
            
            # Update other fields from form
            complaint.zone = form.cleaned_data.get('zone')
            complaint.subcategory = form.cleaned_data.get('subcategory')
            complaint.location = form.cleaned_data.get('location')
            complaint.latitude = form.cleaned_data.get('latitude')
            complaint.longitude = form.cleaned_data.get('longitude')
            complaint.phone = form.cleaned_data.get('phone')
            complaint.description = form.cleaned_data.get('description')
            
            # Handle image update
            if new_image:
                # Delete old image first if it exists
                if old_image_path and os.path.isfile(old_image_path):
                    try:
                        os.remove(old_image_path)
                        print(f"✓ Old image deleted: {old_image_path}")
                    except Exception as e:
                        print(f"✗ Error deleting old image: {e}")
                
                # Set new image
                complaint.proof_image = request.FILES['proof_image']
                print(f"✓ New image uploaded: {request.FILES['proof_image'].name}")
            
            old_zone = old_values['zone']

            # Save the complaint
            complaint.save()
            _sync_officer_complaint_counts(zones=[old_zone, complaint.zone])
            new_values = {
                'category': complaint.category,
                'subcategory': complaint.subcategory,
                'zone': complaint.zone,
                'location': complaint.location,
                'description': complaint.description,
                'phone': complaint.phone,
            }
            changed_fields = {}
            for key, old_val in old_values.items():
                new_val = new_values.get(key)
                if old_val != new_val:
                    changed_fields[key] = {'old': old_val, 'new': new_val}

            if changed_fields:
                _create_audit_log(
                    actor=request.user,
                    action='complaint_updated',
                    entity_type='complaint',
                    entity_id=complaint.complaint_id,
                    complaint=complaint,
                    target_user=request.user,
                    change_data=changed_fields,
                )
            
            # Show success message with alert
            if new_image:
                messages.success(request, "✅ Complaint and image updated successfully!")
            else:
                messages.success(request, "✅ Complaint updated successfully!")
            
            print(f"DEBUG: ==================")
            return redirect('dashboard')
    else:
        # Prepare initial data for the form
        initial_data = {}
        
        # Check if category is in standard choices
        if complaint.category in dict(Complaint.CATEGORY_CHOICES):
            initial_data['category'] = complaint.category
        else:
            initial_data['category'] = 'Other'
            initial_data['other_category'] = complaint.category
        
        # Check if subcategory is standard
        standard_subcats = []
        for cat_subcats in get_subcategories_by_category().values():
            standard_subcats.extend(cat_subcats)
        
        if complaint.subcategory in standard_subcats:
            initial_data['subcategory'] = complaint.subcategory
        else:
            initial_data['subcategory'] = 'Other'
            initial_data['other_subcategory'] = complaint.subcategory
        
        form = ComplaintForm(instance=complaint, initial=initial_data)
    
    context = {
        'form': form,
        'complaint': complaint,
        'subcategories_by_category': get_subcategories_by_category(),
    }
    
    return render(request, 'complaints/edit_complaint.html', context)

@login_required
def delete_complaint(request, complaint_id):
    if request.user.role != 'user':
        messages.error(request, "Access denied. User login only.")
        return redirect('login')
    
    complaint = get_object_or_404(Complaint, complaint_id=complaint_id, user=request.user)
    
    if complaint.status != 'Pending':
        messages.error(request, "Only pending complaints can be deleted.")
        return redirect('dashboard')
    
    if request.method == 'POST':
        complaint_snapshot = {
            'status': complaint.status,
            'category': complaint.category,
            'subcategory': complaint.subcategory,
            'zone': complaint.zone,
            'location': complaint.location,
            'description': complaint.description,
        }
        _create_audit_log(
            actor=request.user,
            action='complaint_deleted',
            entity_type='complaint',
            entity_id=complaint.complaint_id,
            complaint=complaint,
            target_user=request.user,
            change_data=complaint_snapshot,
        )

        # Delete the image file if exists
        if complaint.proof_image:
            if os.path.isfile(complaint.proof_image.path):
                os.remove(complaint.proof_image.path)
        
        deleted_zone = complaint.zone
        complaint.delete()
        _sync_officer_complaint_counts(zones=[deleted_zone])
        messages.success(request, "Complaint deleted successfully.")
        return redirect('dashboard')
    
    return render(request, 'complaints/confirm_delete.html', {'complaint': complaint})

@admin_or_officer_required
def admin_panel(request):
    # Debug info
    print(f"User Role: {request.user.role}")
    print(f"User Zone: {request.user.zone}")
    
    # Get filter parameters
    search_query = request.GET.get('search', '')
    zone_filter = request.GET.get('zone', '')
    status_filter = request.GET.get('status', '')
    items_per_page = request.GET.get('items', '10')
    
    # Validate items per page
    valid_items = ['5', '10', '20', '50']
    if items_per_page not in valid_items:
        items_per_page = '10'
    items_per_page = int(items_per_page)
    
    # Start with base queryset - IMPORTANT: યોગ્ય ક્વેરી સેટ
    if request.user.role == 'administrator':
        # Administrator sees all complaints
        complaints = Complaint.objects.all().select_related('user')
        print(f"Admin: Total complaints = {complaints.count()}")
    else:  # Officer
        if request.user.zone:
            # Officer sees only complaints in their zone
            complaints = Complaint.objects.filter(zone=request.user.zone).select_related('user')
            print(f"Officer: Zone = {request.user.zone}, Complaints = {complaints.count()}")
        else:
            messages.warning(request, "Your zone is not assigned. Please contact administrator.")
            complaints = Complaint.objects.none()
    
    # Apply search filter
    if search_query:
        complaints = complaints.filter(
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query) |
            Q(user__email__icontains=search_query) |
            Q(category__icontains=search_query) |
            Q(subcategory__icontains=search_query) |
            Q(location__icontains=search_query) |
            Q(address__icontains=search_query) |
            Q(description__icontains=search_query)
        )
    
    # Apply zone filter (if user is administrator)
    if zone_filter and request.user.role == 'administrator':
        complaints = complaints.filter(zone=zone_filter)
    
    # Keep a copy before status filter so cards show consistent scoped totals
    cards_queryset = complaints

    # Apply status filter for table rows only
    if status_filter and status_filter != 'all':
        complaints = complaints.filter(status=status_filter)
    
    # Get counts for status overview
    total_complaints_count = Complaint.objects.count()
    print(f"Total complaints in database: {total_complaints_count}")
    
    # Normalize status values before counting (handles accidental casing/spacing drift).
    normalized_cards_queryset = cards_queryset.annotate(status_normalized=Trim('status'))
    pending_count = normalized_cards_queryset.filter(status_normalized__iexact='Pending').count()
    in_progress_count = normalized_cards_queryset.filter(status_normalized__iexact='In Progress').count()
    resolved_count = normalized_cards_queryset.filter(status_normalized__iexact='Resolved').count()
    total_complaints = complaints.count()
    show_all_count = cards_queryset.count()
    
    # Get unique zones for filter
    zones = Complaint.objects.exclude(
        zone__isnull=True
    ).exclude(
        zone=''
    ).values_list(
        'zone', flat=True
    ).distinct().order_by('zone')
    
    # Predefined zones
    predefined_zones = [
        "West Zone (Rander)",
        "Central Zone", 
        "North Zone (Katargam)",
        "East Zone – A(Varachha)",
        "East Zone – B(Sarthana)",
        "South Zone – A (Udhna)",
        "South Zone – B (Kanakpur)",
        "South West Zone (Athwa)",
        "South East Zone (Limbayat)"
    ]
    
    # Use predefined zones if no zones in database
    if not zones:
        zones = predefined_zones
    
    # Pagination
    paginator = Paginator(complaints, items_per_page)
    page = request.GET.get('page', 1)
    
    try:
        complaints_page = paginator.page(page)
    except PageNotAnInteger:
        complaints_page = paginator.page(1)
    except EmptyPage:
        complaints_page = paginator.page(paginator.num_pages)
    
    # Calculate pagination info
    current_page = complaints_page.number
    total_pages = paginator.num_pages
    start_item = (current_page - 1) * items_per_page + 1
    end_item = min(start_item + items_per_page - 1, total_complaints)
    
    # Generate page range for pagination
    page_range = []
    if total_pages <= 5:
        page_range = range(1, total_pages + 1)
    else:
        if current_page <= 3:
            page_range = range(1, 6)
        elif current_page >= total_pages - 2:
            page_range = range(total_pages - 4, total_pages + 1)
        else:
            page_range = range(current_page - 2, current_page + 3)
    
    context = {
        'user': request.user,
        'complaints': complaints_page,
        'search_query': search_query,
        'zone_filter': zone_filter,
        'status_filter': status_filter,
        'items_per_page': items_per_page,
        'current_page': current_page,
        'total_pages': total_pages,
        'total_rows': total_complaints,
        'start_item': start_item,
        'end_item': end_item,
        'zones': zones,
        'pending_count': pending_count,
        'in_progress_count': in_progress_count,
        'resolved_count': resolved_count,
        'total_complaints': total_complaints,
        'show_all_count': show_all_count,
        'page_range': page_range,
        'debug_info': {  # Debug info for template
            'user_role': request.user.role,
            'user_zone': request.user.zone,
            'total_in_db': total_complaints_count,
            'filtered_count': total_complaints,
        }
    }
    
    return render(request, 'complaints/admin_panel.html', context)

@login_required
def complaint_heatmap(request):
    # Role check
    if request.user.role not in ['administrator', 'officer']:
        messages.error(request, "Access denied. Admin login only.")
        return redirect('dashboard')
    
    # Use all-area complaints for both roles so counts are city-wide.
    all_complaints = Complaint.objects.all()
    complaints = all_complaints.exclude(latitude__isnull=True).exclude(longitude__isnull=True)

    configured_zones = list(ZoneDepartment.objects.values_list('zone_name', flat=True).order_by('zone_name'))
    if not configured_zones:
        configured_zones = [label for _, label in Complaint.ZONE_CHOICES]

    # Approximate zone centers to show configured zones even when no complaint point exists.
    zone_center_coords = {
        'West Zone (Rander)': (21.2218, 72.7872),
        'Central Zone': (21.1950, 72.8190),
        'North Zone (Katargam)': (21.2400, 72.8360),
        'East Zone – A(Varachha)': (21.2150, 72.8800),
        'East Zone – B(Sarthana)': (21.2370, 72.9070),
        'South Zone – A (Udhna)': (21.1540, 72.8420),
        'South Zone – B (Kanakpur)': (21.1700, 72.8650),
        'South West Zone (Athwa)': (21.1700, 72.7900),
        'South East Zone (Limbayat)': (21.1420, 72.8620),
    }
    
    # Prepare data for heatmap.
    heat_data = []
    complaint_points = []
    for complaint in complaints:
        lat = float(complaint.latitude)
        lng = float(complaint.longitude)
        heat_data.append([lat, lng])
        complaint_points.append((complaint, lat, lng))
    
    # Create base map centered on Surat (approximate coordinates)
    m = folium.Map(location=[21.1702, 72.8311], zoom_start=12, tiles=None)

    folium.TileLayer(
        tiles='CartoDB positron',
        name='Street Map',
        control=False,
    ).add_to(m)
    
    # Add heatmap layer
    if heat_data:
        HeatMap(heat_data).add_to(m)

    # Determine highest complaint zone for summary card.
    zone_summary = list(
        complaints.exclude(zone__isnull=True).exclude(zone='').values('zone').annotate(
            zone_count=Count('complaint_id'),
        ).order_by('-zone_count', 'zone')
    )

    top_zone_name = ''
    top_zone_count = 0
    top_zones = []
    mapped_zones = [row['zone'] for row in zone_summary if row.get('zone')]
    configured_zone_count = len(configured_zones)
    missing_zones = sorted(set(configured_zones) - set(mapped_zones))

    if zone_summary:
        top_zone_count = zone_summary[0]['zone_count']
        top_zones = [
            row['zone']
            for row in zone_summary
            if row.get('zone') and row['zone_count'] == top_zone_count
        ]
        top_zone_name = ', '.join(top_zones)

    top_zones_set = set(top_zones)

    # Plot complaint points exactly as they exist in DB.
    # Top-zone complaints become red dots; others remain white.
    for complaint, lat, lng in complaint_points:
        zone_name = (complaint.zone or '').strip()
        zone_label = zone_name or 'Unknown Area'
        is_top_zone_point = zone_name in top_zones_set

        folium.CircleMarker(
            location=[lat, lng],
            radius=6 if is_top_zone_point else 4,
            color='#a50000' if is_top_zone_point else '#1f2937',
            weight=2 if is_top_zone_point else 1,
            fill=True,
            fill_color='#ff2d2d' if is_top_zone_point else '#ffffff',
            fill_opacity=0.95 if is_top_zone_point else 0.9,
            tooltip=(
                f"Top complaint zone: {zone_label} ({top_zone_count})"
                if is_top_zone_point
                else f"Area: {zone_label}"
            ),
        ).add_to(m)

    # Add fallback markers for zones that have no complaint points with coordinates.
    fallback_markers_added = 0
    for zone in missing_zones:
        coords = zone_center_coords.get(zone)
        if not coords:
            continue

        folium.CircleMarker(
            location=[coords[0], coords[1]],
            radius=7,
            color='#f59e0b',
            weight=2,
            fill=True,
            fill_color='#fde68a',
            fill_opacity=0.85,
            tooltip=f"Zone: {zone} (No mapped complaints yet)",
        ).add_to(m)
        fallback_markers_added += 1

    mapped_zone_count = len(mapped_zones) + fallback_markers_added
    
    # Save map to HTML string
    map_html = m._repr_html_()
    
    context = {
        'user': request.user,
        'map_html': map_html,
        'total_complaints': all_complaints.count(),
        'mapped_complaints': len(heat_data),
        'top_zone_name': top_zone_name,
        'top_zone_count': top_zone_count,
        'mapped_zone_count': mapped_zone_count,
        'configured_zone_count': configured_zone_count,
        'missing_zones': ', '.join(missing_zones),
    }
    
    return render(request, 'complaints/heatmap.html', context)

@admin_only_required
def user_management(request):
    """Super admin user management view"""

    # Get filter parameters
    search_query = request.GET.get('search', '')
    role_filter = request.GET.get('role', '')
    zone_filter = request.GET.get('zone', '')
    items_per_page = request.GET.get('items', '10')

    # Validate items per page
    valid_items = ['5', '10', '20', '50']
    if items_per_page not in valid_items:
        items_per_page = '10'
    items_per_page = int(items_per_page)

    # Get all users
    users = CustomUser.objects.all()

    # Apply filters
    if search_query:
        users = users.filter(
            Q(username__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query)
        )

    if role_filter:
        users = users.filter(role=role_filter)

    if zone_filter:
        users = users.filter(
            Q(officer_profile__zone=zone_filter) |
            Q(superadmin_profile__zone=zone_filter)
        )

    # Get statistics
    total_users = CustomUser.objects.count()
    admin_count = CustomUser.objects.filter(role='administrator').count()
    officer_count = CustomUser.objects.filter(role='officer').count()
    citizen_count = CustomUser.objects.filter(role='user').count()

    # Get zones for filter
    zone_values = set(
        CustomUser.objects.filter(officer_profile__zone__isnull=False)
        .exclude(officer_profile__zone='')
        .values_list('officer_profile__zone', flat=True)
    )
    zone_values.update(
        CustomUser.objects.filter(superadmin_profile__zone__isnull=False)
        .exclude(superadmin_profile__zone='')
        .values_list('superadmin_profile__zone', flat=True)
    )
    zones = sorted(zone_values)

    # Pagination
    paginator = Paginator(users, items_per_page)
    page = request.GET.get('page', 1)

    try:
        users_page = paginator.page(page)
    except PageNotAnInteger:
        users_page = paginator.page(1)
    except EmptyPage:
        users_page = paginator.page(paginator.num_pages)

    # Pagination info
    current_page = users_page.number
    total_pages = paginator.num_pages
    total_rows = users.count()
    start_item = (current_page - 1) * items_per_page + 1
    end_item = min(start_item + items_per_page - 1, total_rows)

    # Generate page range for pagination
    page_range = []
    if total_pages <= 5:
        page_range = range(1, total_pages + 1)
    else:
        if current_page <= 3:
            page_range = range(1, 6)
        elif current_page >= total_pages - 2:
            page_range = range(total_pages - 4, total_pages + 1)
        else:
            page_range = range(current_page - 2, current_page + 3)

    context = {
        'users': users_page,
        'search_query': search_query,
        'role_filter': role_filter,
        'zone_filter': zone_filter,
        'items_per_page': items_per_page,
        'current_page': current_page,
        'total_pages': total_pages,
        'total_rows': total_rows,
        'start_item': start_item,
        'end_item': end_item,
        'zones': zones,
        'total_users': total_users,
        'admin_count': admin_count,
        'officer_count': officer_count,
        'citizen_count': citizen_count,
        'page_range': page_range,
        'is_officer_view': False,
        'can_manage_users': True,
        'clear_url_name': 'user_management',
    }

    return render(request, 'complaints/user_management.html', context)

@admin_or_officer_required
def officer_zone_users(request):
    """Officer view to list only users from officer's assigned zone."""

    if request.user.role != 'officer':
        return redirect('user_management')

    # Get filter parameters
    search_query = request.GET.get('search', '')
    role_filter = request.GET.get('role', '')
    items_per_page = request.GET.get('items', '10')

    # Validate items per page
    valid_items = ['5', '10', '20', '50']
    if items_per_page not in valid_items:
        items_per_page = '10'
    items_per_page = int(items_per_page)

    # Officers can only view users from their own zone
    officer_zone = request.user.zone
    if officer_zone:
        users = CustomUser.objects.filter(complaints__zone=officer_zone).distinct()
    else:
        messages.warning(request, "Your zone is not assigned. Please contact administrator.")
        users = CustomUser.objects.none()

    # Apply filters
    if search_query:
        users = users.filter(
            Q(username__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query)
        )

    if role_filter:
        users = users.filter(role=role_filter)

    # Zone-scoped statistics
    zone_users = CustomUser.objects.filter(complaints__zone=officer_zone).distinct() if officer_zone else CustomUser.objects.none()
    total_users = zone_users.count()
    admin_count = zone_users.filter(role='administrator').count()
    officer_count = zone_users.filter(role='officer').count()
    citizen_count = zone_users.filter(role='user').count()

    # Pagination
    paginator = Paginator(users, items_per_page)
    page = request.GET.get('page', 1)

    try:
        users_page = paginator.page(page)
    except PageNotAnInteger:
        users_page = paginator.page(1)
    except EmptyPage:
        users_page = paginator.page(paginator.num_pages)

    # Pagination info
    current_page = users_page.number
    total_pages = paginator.num_pages
    total_rows = users.count()
    start_item = (current_page - 1) * items_per_page + 1
    end_item = min(start_item + items_per_page - 1, total_rows)

    # Generate page range for pagination
    page_range = []
    if total_pages <= 5:
        page_range = range(1, total_pages + 1)
    else:
        if current_page <= 3:
            page_range = range(1, 6)
        elif current_page >= total_pages - 2:
            page_range = range(total_pages - 4, total_pages + 1)
        else:
            page_range = range(current_page - 2, current_page + 3)

    context = {
        'users': users_page,
        'search_query': search_query,
        'role_filter': role_filter,
        'zone_filter': '',
        'items_per_page': items_per_page,
        'current_page': current_page,
        'total_pages': total_pages,
        'total_rows': total_rows,
        'start_item': start_item,
        'end_item': end_item,
        'zones': [],
        'total_users': total_users,
        'admin_count': admin_count,
        'officer_count': officer_count,
        'citizen_count': citizen_count,
        'page_range': page_range,
        'is_officer_view': True,
        'can_manage_users': False,
        'clear_url_name': 'officer_zone_users',
    }

    return render(request, 'complaints/user_management.html', context)

@admin_only_required
def view_user_profile(request, user_id):
    """View user profile details for admin"""

    user = get_object_or_404(CustomUser, id=user_id)

    # Get user's complaints statistics
    total_complaints = Complaint.objects.filter(user=user).count()
    pending_complaints = Complaint.objects.filter(user=user, status='Pending').count()
    in_progress_complaints = Complaint.objects.filter(user=user, status='In Progress').count()
    resolved_complaints = Complaint.objects.filter(user=user, status='Resolved').count()

    # Get recent complaints
    recent_complaints = Complaint.objects.filter(user=user).order_by('-complaint_date')[:5]

    context = {
        'profile_user': user,
        'total_complaints': total_complaints,
        'pending_complaints': pending_complaints,
        'in_progress_complaints': in_progress_complaints,
        'resolved_complaints': resolved_complaints,
        'recent_complaints': recent_complaints,
    }

    return render(request, 'complaints/user_profile_detail.html', context)

@admin_only_required
def edit_user_profile(request, user_id):
    """Edit user profile for admin"""

    user = get_object_or_404(CustomUser, id=user_id)

    if request.method == 'POST':
        original_values = {
            field_name: getattr(user, field_name)
            for field_name in [
                'first_name', 'last_name', 'email', 'phone', 'role',
                'zone', 'department', 'employee_id', 'city', 'state'
            ]
        }
        form = AdminUserChangeForm(request.POST, request.FILES, instance=user)
        if form.is_valid():
            updated_user = form.save(commit=False)

            from django.utils import timezone
            updated_user.last_profile_update = timezone.now()

            updated_user.check_profile_completion()
            updated_user.save()

            changed_fields = {}
            for field_name, old_val in original_values.items():
                new_val = getattr(updated_user, field_name)
                if old_val != new_val:
                    changed_fields[field_name] = {'old': old_val, 'new': new_val}

            if changed_fields:
                _create_audit_log(
                    actor=request.user,
                    action='user_updated',
                    entity_type='user',
                    entity_id=updated_user.id,
                    target_user=updated_user,
                    change_data=changed_fields,
                )

            messages.success(request, f'Profile for {user.username} has been updated successfully.')
            return redirect('view_user_profile', user_id=user.id)
    else:
        form = AdminUserChangeForm(instance=user)

    context = {
        'form': form,
        'profile_user': user,
    }

    return render(request, 'complaints/edit_user_profile.html', context)

@admin_only_required
def delete_user(request, user_id):
    """Delete user account for admin"""

    user = get_object_or_404(CustomUser, id=user_id)

    if request.method == 'POST':
        user_snapshot = {
            'username': user.username,
            'email': user.email,
            'role': user.role,
            'zone': user.zone,
        }
        _create_audit_log(
            actor=request.user,
            action='user_deleted',
            entity_type='user',
            entity_id=user.id,
            target_user=user,
            change_data=user_snapshot,
        )

        username = user.username
        user.delete()
        messages.success(request, f'User {username} has been deleted successfully.')
        return redirect('user_management')

    context = {
        'user_to_delete': user,
    }

    return render(request, 'complaints/delete_user_confirm.html', context)

@login_required
@csrf_protect
def update_complaint_status(request):
    if request.method == 'POST' and request.user.role in ['administrator', 'officer']:
        complaint_id = request.POST.get('complaint_id')
        status = (request.POST.get('status') or '').strip()
        allowed_statuses = {choice[0] for choice in Complaint.STATUS_CHOICES}

        if status not in allowed_statuses:
            return JsonResponse({'success': False, 'error': 'Invalid status value'})
        
        try:
            complaint = Complaint.objects.get(complaint_id=complaint_id)
            
            # Check if officer can update this complaint
            if request.user.role == 'officer' and complaint.zone != request.user.zone:
                return JsonResponse({'success': False, 'error': 'You can only update complaints in your zone'})
            
            # Update status
            old_status = complaint.status
            complaint.status = status
            status_changed_at = timezone.now()
            
            # Set resolved_at when status becomes Resolved
            if status == 'Resolved' and old_status != 'Resolved':
                complaint.resolved_at = status_changed_at
            elif status != 'Resolved':
                # Clear resolved_at if status is changed from Resolved to something else
                complaint.resolved_at = None
            
            complaint.save()
            _sync_officer_complaint_counts(zones=[complaint.zone])
            _ensure_submitted_timeline(complaint)

            if old_status != status:
                _create_audit_log(
                    actor=request.user,
                    action='status_changed',
                    entity_type='complaint',
                    entity_id=complaint.complaint_id,
                    complaint=complaint,
                    target_user=complaint.user,
                    change_data={
                        'status': {'old': old_status, 'new': status},
                        'resolved_at': str(complaint.resolved_at) if complaint.resolved_at else None,
                    },
                )

            if old_status != status:
                if old_status == 'Pending' and status in ['In Progress', 'Resolved']:
                    _create_timeline_event(
                        complaint=complaint,
                        stage='In Review',
                        changed_by=request.user,
                        timestamp=status_changed_at,
                        notes='Complaint moved to review stage',
                    )

                if status in ['In Progress', 'Resolved']:
                    _create_timeline_event(
                        complaint=complaint,
                        stage='Assigned',
                        changed_by=request.user,
                        timestamp=status_changed_at,
                        notes='Complaint assigned for action',
                    )

                if status == 'Resolved':
                    _create_timeline_event(
                        complaint=complaint,
                        stage='Resolved',
                        changed_by=request.user,
                        timestamp=complaint.resolved_at or status_changed_at,
                        notes='Complaint marked as resolved',
                    )
            
            # Send SMS notification if Twilio is configured
            try:
                account_sid = settings.TWILIO_ACCOUNT_SID
                auth_token = settings.TWILIO_AUTH_TOKEN
                from_number = settings.TWILIO_PHONE_NUMBER
                
                if account_sid and auth_token and from_number:
                    # Build message body
                    body = ""
                    if status == "Pending":
                        body = f"Your complaint (ID: #{complaint_id}) is now Pending."
                    elif status == "In Progress":
                        body = f"Your complaint (ID: #{complaint_id}) is now In Progress. The officer has started reviewing your issue."
                    elif status == "Resolved":
                        body = f"Your complaint (ID: #{complaint_id}) has been Resolved. Thank you for your patience."
                    
                    # Send SMS
                    client = Client(account_sid, auth_token)
                    if status == "Pending":
                        sent_time = complaint.complaint_date or timezone.now()
                    else:
                        sent_time = timezone.now()
                    message = client.messages.create(
                        body=body,
                        from_=from_number,
                        to=f"+91{complaint.phone}"  # Assuming Indian numbers
                    )
                    _create_notification_log(
                        username=complaint.user.username,
                        complaint_id=complaint.complaint_id,
                        message=body,
                        notification_type='sms',
                        status='sent',
                        sent_at=complaint.complaint_date or sent_time,
                    )
                else:
                    _create_notification_log(
                        username=complaint.user.username,
                        complaint_id=complaint.complaint_id,
                        message=f"Status update SMS not sent for complaint #{complaint_id} due to missing Twilio config.",
                        notification_type='sms',
                        status='failed',
                        sent_at=complaint.complaint_date or timezone.now(),
                    )
            except Exception as e:
                # Log error but continue
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Twilio SMS failed: {str(e)}")
                _create_notification_log(
                    username=complaint.user.username,
                    complaint_id=complaint.complaint_id,
                    message=f"Status update SMS failed for complaint #{complaint_id}: {str(e)}",
                    notification_type='sms',
                    status='failed',
                    sent_at=complaint.complaint_date or timezone.now(),
                )
            
            return JsonResponse({'success': True, 'message': 'Status updated successfully'})
        except Complaint.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Complaint not found'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request'})

@login_required
@csrf_protect
def generate_pdf_report(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'})

    if request.user.role not in ['administrator', 'officer']:
        return JsonResponse({'success': False, 'error': 'Access denied'})

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import mm
        from reportlab.lib.utils import simpleSplit
    except Exception:
        return JsonResponse({
            'success': False,
            'error': 'PDF library not installed. Please install reportlab.'
        })

    if request.user.role == 'administrator':
        complaints_qs = Complaint.objects.all().select_related('user').order_by('-complaint_date')
    else:
        complaints_qs = Complaint.objects.filter(zone=request.user.zone).select_related('user').order_by('-complaint_date')

    response = HttpResponse(content_type='application/pdf')
    timestamp = timezone.localtime().strftime('%Y%m%d_%H%M%S')
    response['Content-Disposition'] = f'attachment; filename="complaints_report_{timestamp}.pdf"'

    pdf = canvas.Canvas(response, pagesize=A4)
    width, height = A4

    y = height - 20 * mm
    pdf.setFont('Helvetica-Bold', 14)
    pdf.drawString(15 * mm, y, 'CivicZone Complaint Report')
    y -= 8 * mm

    pdf.setFont('Helvetica', 9)
    generated_at = timezone.localtime().strftime('%d %b %Y %H:%M')
    pdf.drawString(15 * mm, y, f'Generated: {generated_at}')
    y -= 5 * mm
    pdf.drawString(15 * mm, y, f'Generated by: {request.user.get_full_name() or request.user.username} ({request.user.role})')
    y -= 10 * mm

    col_id_x = 15 * mm
    col_category_x = 28 * mm
    col_zone_x = 78 * mm
    col_status_x = 118 * mm
    col_date_x = 145 * mm

    col_id_width = 12 * mm
    col_category_width = 48 * mm
    col_zone_width = 38 * mm
    col_status_width = 25 * mm
    col_date_width = 50 * mm

    row_line_height = 4 * mm

    def draw_table_header(current_y):
        pdf.setFont('Helvetica-Bold', 9)
        pdf.drawString(col_id_x, current_y, 'ID')
        pdf.drawString(col_category_x, current_y, 'Category')
        pdf.drawString(col_zone_x, current_y, 'Zone')
        pdf.drawString(col_status_x, current_y, 'Status')
        pdf.drawString(col_date_x, current_y, 'Date')
        current_y -= 4 * mm
        pdf.line(15 * mm, current_y, 195 * mm, current_y)
        current_y -= 5 * mm
        pdf.setFont('Helvetica', 8)
        return current_y

    def wrap_text(value, width):
        text = (value or '-').strip() or '-'
        lines = simpleSplit(text, 'Helvetica', 8, width)
        return lines if lines else ['-']

    y = draw_table_header(y)

    pdf.setFont('Helvetica', 8)
    total = 0
    for complaint in complaints_qs:
        category_lines = wrap_text(complaint.category, col_category_width)
        zone_lines = wrap_text(complaint.zone, col_zone_width)
        status_lines = wrap_text(complaint.status, col_status_width)
        date_text = timezone.localtime(complaint.complaint_date).strftime('%d-%m-%Y %H:%M')
        date_lines = wrap_text(date_text, col_date_width)

        row_lines = max(len(category_lines), len(zone_lines), len(status_lines), len(date_lines), 1)
        row_height = row_lines * row_line_height

        if y - row_height < 20 * mm:
            pdf.showPage()
            y = height - 20 * mm
            y = draw_table_header(y)

        pdf.drawString(col_id_x, y, str(complaint.complaint_id))

        for idx, line in enumerate(category_lines):
            pdf.drawString(col_category_x, y - (idx * row_line_height), line)

        for idx, line in enumerate(zone_lines):
            pdf.drawString(col_zone_x, y - (idx * row_line_height), line)

        for idx, line in enumerate(status_lines):
            pdf.drawString(col_status_x, y - (idx * row_line_height), line)

        for idx, line in enumerate(date_lines):
            pdf.drawString(col_date_x, y - (idx * row_line_height), line)

        y -= row_height + (1 * mm)
        total += 1

    y -= 3 * mm
    pdf.setFont('Helvetica-Bold', 9)
    pdf.drawString(15 * mm, y, f'Total complaints in report: {total}')

    pdf.save()
    return response

@login_required
def feedback(request):
    """Feedback page for users to provide feedback"""
    if request.method == 'POST':
        # Get user data from profile (not from form since they're readonly)
        fullname = request.user.get_full_name() if request.user.get_full_name() else request.user.username
        email = request.user.email if request.user.email else ''
        mobile = request.user.phone if request.user.phone else 'Not provided'
        
        overall_rating = request.POST.get('overall_rating', '0')
        response_time_satisfaction = request.POST.get('response_time_satisfaction', '')
        reference_email = request.POST.get('reference_email', '').strip()
        feedback_text = request.POST.get('feedback', '')
        
        if feedback_text.strip() and fullname and overall_rating != '0' and response_time_satisfaction:
            # Save feedback to database
            try:
                feedback_obj = Feedback.objects.create(
                    user=request.user,
                    fullname=fullname,
                    email=email,
                    mobile=mobile,
                    overall_rating=int(overall_rating),
                    response_time_satisfaction=response_time_satisfaction,
                    reference_email=reference_email if reference_email else None,
                    feedback=feedback_text
                )

                try:
                    _send_reference_invite_email(request, feedback_obj)
                except Exception:
                    messages.warning(
                        request,
                        "Feedback submitted, but reference email could not be sent right now."
                    )

                messages.success(request, "Thank you for your feedback! We appreciate your input.")
                return redirect('feedback')
            except Exception as e:
                messages.error(request, f"Error submitting feedback: {str(e)}")
        else:
            messages.error(request, "Please fill all required fields and provide a rating.")
    
    context = {
        'user': request.user,
    }
    return render(request, 'complaints/feedback.html', context)

@login_required
def complaint_detail(request, complaint_id):
    """View detailed information of a specific complaint"""
    complaint = get_object_or_404(Complaint, complaint_id=complaint_id, user=request.user)
    _ensure_submitted_timeline(complaint)

    event_map = {
        event.stage: event
        for event in complaint.timeline_events.select_related('changed_by').all()
    }
    timeline_items = []
    for stage in TIMELINE_STAGE_SEQUENCE:
        event = event_map.get(stage)
        timeline_items.append({
            'stage': stage,
            'event': event,
            'is_completed': event is not None,
        })
    
    context = {
        'complaint': complaint,
        'user': request.user,
        'timeline_items': timeline_items,
    }
    
    return render(request, 'complaints/complaint_detail.html', context)


# ============== REPORT GENERATION VIEWS ==============

@login_required
def monthly_report(request):
    """Generate monthly complaints report"""
    # Check if user is admin
    if request.user.role != 'administrator':
        messages.error(request, "Access denied. Admin login only.")
        return redirect('admin_panel')
    
    # Get current month data
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # Determine which complaints to show based on user role
    if request.user.role == 'administrator':
        complaints = Complaint.objects.filter(complaint_date__gte=month_start)
    else:  # Officer
        complaints = Complaint.objects.filter(
            complaint_date__gte=month_start,
            zone=request.user.zone
        )
    
    # Status breakdown
    status_breakdown = complaints.values('status').annotate(count=Count('complaint_id')).order_by('status')
    
    # Category breakdown
    category_breakdown = complaints.values('category').annotate(count=Count('complaint_id')).order_by('-count')[:10]
    
    # Zone breakdown (for administrators)
    if request.user.role == 'administrator':
        zone_breakdown = complaints.values('zone').annotate(count=Count('complaint_id')).order_by('-count')
    else:
        zone_breakdown = None
    
    # Calculate statistics
    total_complaints = complaints.count()
    resolved = complaints.filter(status='Resolved').count()
    pending = complaints.filter(status='Pending').count()
    in_progress = complaints.filter(status='In Progress').count()
    
    context = {
        'user': request.user,
        'month': month_start.strftime('%B %Y'),
        'month_short': month_start.strftime('%b %Y'),
        'total_complaints': total_complaints,
        'resolved': resolved,
        'pending': pending,
        'in_progress': in_progress,
        'status_breakdown': status_breakdown,
        'category_breakdown': category_breakdown,
        'zone_breakdown': zone_breakdown,
        'is_admin': request.user.role == 'administrator',
    }
    
    return render(request, 'complaints/reports/monthly_report.html', context)


@login_required
def zone_report(request):
    """Generate zone-specific complaints report"""
    # Check if user is admin
    if request.user.role != 'administrator':
        messages.error(request, "Access denied. Admin login only.")
        return redirect('admin_panel')
    
    # Get selected zone
    selected_zone = request.GET.get('zone', '')
    
    # Get all available zones
    zones = list(Complaint.objects.exclude(
        zone__isnull=True
    ).exclude(
        zone=''
    ).values_list('zone', flat=True).distinct().order_by('zone'))
    
    # Predefined zones list
    predefined_zones = [
        "West Zone (Rander)",
        "Central Zone",
        "North Zone (Katargam)",
        "East Zone – A(Varachha)",
        "East Zone – B(Sarthana)",
        "South Zone – A (Udhna)",
        "South Zone – B (Kanakpur)",
        "South West Zone (Athwa)",
        "South East Zone (Limbayat)"
    ]
    
    # Add predefined zones that don't exist in database yet
    for zone in predefined_zones:
        if zone not in zones:
            zones.append(zone)
    
    # Add "All Zones" option
    zones.insert(0, "All Zones")
    
    if not zones:
        zones = predefined_zones
    
    # If no zone selected, default to first zone or officer's zone
    if not selected_zone:
        if request.user.role == 'officer' and request.user.zone:
            selected_zone = request.user.zone
        elif zones:
            selected_zone = zones[0]
    
    # Get complaints for selected zone
    if selected_zone == "All Zones":
        complaints = Complaint.objects.all()
    elif selected_zone:
        complaints = Complaint.objects.filter(zone=selected_zone)
    else:
        complaints = Complaint.objects.none()
    
    # Status breakdown
    status_breakdown = complaints.values('status').annotate(count=Count('complaint_id')).order_by('status')
    
    # Category breakdown
    category_breakdown = complaints.values('category').annotate(count=Count('complaint_id')).order_by('-count')[:10]
    
    # Calculate statistics
    total_complaints = complaints.count()
    resolved = complaints.filter(status='Resolved').count()
    pending = complaints.filter(status='Pending').count()
    in_progress = complaints.filter(status='In Progress').count()
    
    # Get officers assigned to this zone (if admin)
    if request.user.role == 'administrator' and selected_zone != "All Zones":
        officers = CustomUser.objects.filter(role='officer', officer_profile__zone=selected_zone)
    else:
        officers = None
    
    context = {
        'user': request.user,
        'zones': zones,
        'selected_zone': selected_zone,
        'total_complaints': total_complaints,
        'resolved': resolved,
        'pending': pending,
        'in_progress': in_progress,
        'status_breakdown': status_breakdown,
        'category_breakdown': category_breakdown,
        'officers': officers,
        'is_admin': request.user.role == 'administrator',
    }
    
    return render(request, 'complaints/reports/zone_report.html', context)


@login_required
def officer_performance_report(request):
    """Generate officer performance report"""
    # Check if user is admin
    if request.user.role != 'administrator':
        messages.error(request, "Access denied. Admin login only.")
        return redirect('admin_panel')
    
    # Get selected zone
    selected_zone = request.GET.get('zone', '')
    
    # Get all available zones
    zones = list(Complaint.objects.exclude(
        zone__isnull=True
    ).exclude(
        zone=''
    ).values_list('zone', flat=True).distinct().order_by('zone'))
    
    # Predefined zones list
    predefined_zones = [
        "West Zone (Rander)",
        "Central Zone",
        "North Zone (Katargam)",
        "East Zone – A(Varachha)",
        "East Zone – B(Sarthana)",
        "South Zone – A (Udhna)",
        "South Zone – B (Kanakpur)",
        "South West Zone (Athwa)",
        "South East Zone (Limbayat)"
    ]
    
    # Add predefined zones that don't exist in database yet
    for zone in predefined_zones:
        if zone not in zones:
            zones.append(zone)
    
    # Add "All Zones" option
    zones.insert(0, "All Zones")
    
    if not zones:
        zones = predefined_zones
    
    # If no zone selected, default to first zone or officer's zone
    if not selected_zone:
        if request.user.role == 'officer' and request.user.zone:
            selected_zone = request.user.zone
        elif zones:
            selected_zone = zones[0]
    
    # Get officers for selected zone
    officers_data = []
    if selected_zone == "All Zones":
        # Get all officers
        officers = CustomUser.objects.filter(role='officer').order_by('first_name')
        
        for officer in officers:
            officer_zone = officer.zone
            if officer_zone:
                # Get complaints for this officer's zone
                complaints_count = Complaint.objects.filter(
                    zone=officer_zone
                ).count()
                
                # Get resolved complaints
                resolved_complaints = Complaint.objects.filter(
                    zone=officer_zone,
                    status='Resolved'
                )
                resolved_count = resolved_complaints.count()
                
                # Calculate average resolution time
                resolved_with_dates = resolved_complaints.filter(resolved_at__isnull=False)
                avg_resolution_time = None
                if resolved_with_dates.exists():
                    total_time = timedelta(0)
                    for complaint in resolved_with_dates:
                        if complaint.resolved_at:
                            time_diff = complaint.resolved_at - complaint.complaint_date
                            total_time += time_diff
                    avg_resolution_time = total_time / resolved_with_dates.count()
                
                # Count pending
                pending_count = Complaint.objects.filter(
                    zone=officer_zone,
                    status='Pending'
                ).count()
                
                # Count in progress
                in_progress_count = Complaint.objects.filter(
                    zone=officer_zone,
                    status='In Progress'
                ).count()
                
                # Calculate resolution rate
                resolution_rate = 0
                if complaints_count > 0:
                    resolution_rate = (resolved_count / complaints_count) * 100
                
                officers_data.append({
                    'officer': officer,
                    'zone': officer_zone,
                    'complaints_count': complaints_count,
                    'resolved_count': resolved_count,
                    'pending_count': pending_count,
                    'in_progress_count': in_progress_count,
                    'resolution_rate': round(resolution_rate, 2),
                    'avg_resolution_time': avg_resolution_time,
                })
    elif selected_zone:
        officers = CustomUser.objects.filter(role='officer', officer_profile__zone=selected_zone).order_by('first_name')
        
        for officer in officers:
            # Get complaints for this zone
            complaints_count = Complaint.objects.filter(
                zone=selected_zone
            ).count()
            
            # Get resolved complaints
            resolved_complaints = Complaint.objects.filter(
                zone=selected_zone,
                status='Resolved'
            )
            resolved_count = resolved_complaints.count()
            
            # Calculate average resolution time
            resolved_with_dates = resolved_complaints.filter(resolved_at__isnull=False)
            avg_resolution_time = None
            if resolved_with_dates.exists():
                total_time = timedelta(0)
                for complaint in resolved_with_dates:
                    if complaint.resolved_at:
                        time_diff = complaint.resolved_at - complaint.complaint_date
                        total_time += time_diff
                avg_resolution_time = total_time / resolved_with_dates.count()
            
            # Count pending
            pending_count = Complaint.objects.filter(
                zone=selected_zone,
                status='Pending'
            ).count()
            
            # Count in progress
            in_progress_count = Complaint.objects.filter(
                zone=selected_zone,
                status='In Progress'
            ).count()
            
            # Calculate resolution rate
            resolution_rate = 0
            if complaints_count > 0:
                resolution_rate = (resolved_count / complaints_count) * 100
            
            officers_data.append({
                'officer': officer,
                'complaints_count': complaints_count,
                'resolved_count': resolved_count,
                'pending_count': pending_count,
                'in_progress_count': in_progress_count,
                'resolution_rate': round(resolution_rate, 2),
                'avg_resolution_time': avg_resolution_time,
            })
    
    context = {
        'user': request.user,
        'zones': zones,
        'selected_zone': selected_zone,
        'officers_data': officers_data,
        'is_admin': request.user.role == 'administrator',
    }
    
    return render(request, 'complaints/reports/officer_performance_report.html', context)
