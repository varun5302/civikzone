from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.core.paginator import Paginator
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.forms import AuthenticationForm
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.cache import never_cache
from functools import wraps
from .models import CustomUser, Officer, SuperAdmin
from complaints.models import Notification
from .forms import CustomUserCreationForm, CustomUserChangeForm, ProfilePictureForm, PasswordChangeForm, AdminForgotPasswordForm, AdminResetPasswordForm, OfficerProfileForm, OfficerForgotPasswordForm, OfficerResetPasswordForm, ProfileResetPasswordForm, CitizenPasswordResetForm
from django.core.mail import send_mail
from django.http import JsonResponse, HttpResponseForbidden
from django.core.cache import cache
from django.conf import settings
import os
import random
from datetime import timedelta
from django.contrib.auth.views import PasswordResetView, PasswordResetDoneView, PasswordResetConfirmView, PasswordResetCompleteView
from django.urls import reverse, reverse_lazy
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.utils import timezone
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.db.models import Q


SIGNUP_OTP_SESSION_KEY = 'signup_otp_payload'
SIGNUP_OTP_EXPIRY_MINUTES = 10
LOGIN_ATTEMPTS_KEY = 'admin_login_attempts'
MAX_LOGIN_ATTEMPTS = 5
LOGIN_ATTEMPT_TIMEOUT = 900  # 15 minutes
ADMIN_LOGIN_OTP_KEY = 'admin_login_otp'
ADMIN_LOGIN_OTP_EXPIRY_MINUTES = 5
ADMIN_LOGIN_USER_KEY = 'admin_login_user'
LOGIN_CONFIRMATION_KEY = 'login_confirmation'
LOGIN_CONFIRMATION_EXPIRY_MINUTES = 10
USER_LOGIN_CONFIRMATION_KEY = 'user_login_confirmation'
ADMIN_LOGIN_CONFIRM_CACHE_PREFIX = 'admin_login_confirm:'
PROFILE_PASSWORD_RESET_CACHE_PREFIX = 'profile_password_reset:'
FOOTER_CONTENT_DIR = os.path.join(settings.BASE_DIR, 'content')
TERMS_CONTENT_FILE = os.path.join(FOOTER_CONTENT_DIR, 'terms.txt')
SUPPORT_CONTENT_FILE = os.path.join(FOOTER_CONTENT_DIR, 'support.txt')
PRIVACY_CONTENT_FILE = os.path.join(FOOTER_CONTENT_DIR, 'privacy.txt')

DEFAULT_TERMS_TEXT = """By using this complaint portal, you agree to the following terms.

User Responsibilities
- Provide accurate complaint details
- Avoid abusive, false, or duplicate spam submissions
- Use the portal only for civic and lawful purposes

Portal Usage
- Complaint status updates depend on department workflow
- Municipality may request additional verification
- Accounts may be restricted for misuse

Limitation
Resolution timelines are best-effort and can vary by complaint category and field conditions."""

DEFAULT_SUPPORT_TEXT = """If you need help using the portal, contact support through the channels below.

Contact
- Email: support@civiczone.com
- Phone: +91-261-000-0000
- Office Hours: Mon-Sat, 10:00 AM to 6:00 PM

What to Include
- Your username/email
- Complaint ID (if available)
- Screenshots and a clear problem summary

We usually respond within 1-2 working days."""

DEFAULT_PRIVACY_TEXT = """We collect only the data needed to manage complaints and provide civic services.

Data We Collect
- Profile details: name, email, phone, address
- Complaint details: category, description, location, media
- System logs for security and troubleshooting

How We Use Data
- To process and track complaints
- To send status updates and notifications
- To improve service quality and reporting

Data Sharing
Your data is shared only with authorized municipal staff for complaint resolution.

Security
We apply role-based access, audit logs, and secure handling for user records."""


def _admin_login_confirm_cache_key(token):
    return f"{ADMIN_LOGIN_CONFIRM_CACHE_PREFIX}{token}"


def _profile_password_reset_cache_key(token):
    return f"{PROFILE_PASSWORD_RESET_CACHE_PREFIX}{token}"


def _generate_unique_token():
    """Generate a unique secure token"""
    import secrets
    return secrets.token_urlsafe(32)


def _log_password_reset_notification(user, message, reason='password_reset', notification_type='email', status='sent'):
    """Log password reset email in notifications table"""
    try:
        Notification.objects.create(
            username=user.username,
            email=user.email,
            complaint_id=None,
            message=message,
            notification_type=notification_type,
            status=status,
            reason=reason,
            sent_at=timezone.now(),
        )
    except Exception as e:
        # Logging should not block password reset flow
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to log password reset notification: {str(e)}")


def _send_login_confirmation_email(user, confirmation_link):
    """Send email confirmation link for login"""
    try:
        subject = f'Login Confirmation - {user.get_full_name() or user.username}'
        html_message = f"""
        <html>
            <body style="font-family: Arial, sans-serif; background: #f5f5f5; padding: 20px;">
                <div style="background: white; border-radius: 10px; padding: 30px; max-width: 600px; margin: 0 auto;">
                    <h2 style="color: #2c3e50; margin-bottom: 20px;">
                        <i style="color: #3498db;">✓</i> Login Confirmation
                    </h2>
                    
                    <p style="color: #555; font-size: 15px; line-height: 1.6; margin-bottom: 20px;">
                        Hello <strong>{user.get_full_name() or user.username}</strong>,
                    </p>
                    
                    <p style="color: #555; font-size: 15px; line-height: 1.6; margin-bottom: 25px;">
                        Someone just tried to log in to your <strong>{user.role.title()}</strong> account on Civic Zone Solution.
                    </p>
                    
                    <p style="color: #555; font-size: 15px; line-height: 1.6; margin-bottom: 25px; background: #f9f9f9; padding: 15px; border-left: 4px solid #3498db;">
                        If this was <strong>YOU</strong>, click the button below to confirm:
                    </p>
                    
                    <a href="{confirmation_link}" style="display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 15px 40px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 16px; margin: 25px 0;">
                        ✓ Yes, It's Me - Confirm Login
                    </a>
                    
                    <p style="color: #999; font-size: 13px; margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee;">
                        <strong>This link expires in 10 minutes.</strong><br>
                        If you don't recognize this login attempt, ignore this email. Your account is safe.
                    </p>
                    
                    <p style="color: #999; font-size: 12px; margin-top: 20px;">
                        <strong>Security Tip:</strong> Never share this email with anyone. Civic Zone will never ask for your password via email.
                    </p>
                </div>
            </body>
        </html>
        """
        
        plain_message = (
            f"Hello {user.get_full_name() or user.username},\n\n"
            f"Someone just tried to log in to your {user.role.title()} account.\n\n"
            f"If this was YOU, confirm your login here:\n"
            f"{confirmation_link}\n\n"
            f"This link expires in 10 minutes.\n"
            f"If this wasn't you, ignore this email and change your password.\n\n"
            f"Civic Zone Solution Team"
        )
        
        send_mail(
            subject,
            plain_message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            html_message=html_message,
            fail_silently=False
        )
    except Exception as e:
        print(f"Error sending login confirmation email: {e}")
        raise


def _send_admin_login_email(user, ip_address, user_agent):
    """Send login notification email to admin/officer"""
    try:
        from datetime import datetime
        login_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        subject = f'Login Alert - {user.get_full_name() or user.username} ({user.role.title()})'
        message = (
            f"Hello {user.get_full_name() or user.username},\n\n"
            f"Your account just logged in to the Civic Zone Admin Panel.\n\n"
            f"Login Details:\n"
            f"- Time: {login_time}\n"
            f"- IP Address: {ip_address}\n"
            f"- Username: {user.username}\n"
            f"- Role: {user.role.title()}\n\n"
            f"If this wasn't you, please change your password immediately and contact the administrator.\n\n"
            f"Regards,\nCivic Zone Solution Team"
        )
        
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=True
        )
    except Exception as e:
        print(f"Error sending login email: {e}")


def _send_admin_login_otp_email(user, otp):
    """Send OTP verification email for admin/officer"""
    try:
        subject = 'Civic Zone - Admin Login OTP Verification'
        message = (
            f"Hello {user.get_full_name() or user.username},\n\n"
            f"Your One-Time Password (OTP) for admin panel login verification is:\n\n"
            f"{otp}\n\n"
            f"This OTP will expire in 5 minutes.\n"
            f"Do NOT share this OTP with anyone.\n\n"
            f"If you did not attempt to log in, please ignore this email and change your password.\n\n"
            f"Regards,\nCivic Zone Solution Team"
        )
        
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False
        )
    except Exception as e:
        print(f"Error sending OTP email: {e}")
        raise


def _get_client_ip(request):
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def _get_user_agent(request):
    """Get user agent from request"""
    return request.META.get('HTTP_USER_AGENT', 'Unknown')


def admin_or_officer_required(view_func):
    """Decorator to restrict access to admin and officer roles only"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, "Please login first.")
            return redirect('admin_login')
        
        if not hasattr(request.user, 'role') or request.user.role not in ['administrator', 'officer']:
            messages.error(request, "Access denied. Admin/Officer login required.")
            return redirect('dashboard')
        
        if not request.user.is_active:
            messages.error(request, "Your account has been disabled. Contact administrator.")
            return redirect('admin_login')
        
        return view_func(request, *args, **kwargs)
    return wrapper


def admin_only_required(view_func):
    """Decorator to restrict access to administrator role only"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, "Please login first.")
            return redirect('admin_login')
        
        if not hasattr(request.user, 'role') or request.user.role != 'administrator':
            messages.error(request, "Access denied. Administrator login required.")
            return redirect('admin_panel')
        
        if not request.user.is_active:
            messages.error(request, "Your account has been disabled. Contact administrator.")
            return redirect('admin_login')
        
        return view_func(request, *args, **kwargs)
    return wrapper


def _generate_numeric_otp():
    return f"{random.randint(0, 999999):06d}"


def _mask_email(email):
    if not email or '@' not in email:
        return email or ''
    local, domain = email.split('@', 1)
    if len(local) <= 2:
        masked_local = local[0] + '*'
    else:
        masked_local = local[:2] + '*' * (len(local) - 2)
    return f"{masked_local}@{domain}"


def _send_signup_email_otp(email, otp):
    subject = 'Civic Zone OTP Verification (Email)'
    message = (
        "Your Civic Zone email verification OTP is:\n\n"
        f"{otp}\n\n"
        f"This OTP will expire in {SIGNUP_OTP_EXPIRY_MINUTES} minutes.\n"
        "If you did not request this, please ignore this email."
    )
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False)


def _store_signup_otp_session(request, form_data, email_otp):
    request.session[SIGNUP_OTP_SESSION_KEY] = {
        'form_data': form_data,
        'email_otp': email_otp,
        'expires_at': (timezone.now() + timedelta(minutes=SIGNUP_OTP_EXPIRY_MINUTES)).isoformat(),
    }
    request.session.modified = True


def _clear_signup_otp_session(request):
    if SIGNUP_OTP_SESSION_KEY in request.session:
        del request.session[SIGNUP_OTP_SESSION_KEY]
        request.session.modified = True


def _get_signup_otp_payload(request):
    payload = request.session.get(SIGNUP_OTP_SESSION_KEY)
    if not payload:
        return None

    expires_at_raw = payload.get('expires_at')
    try:
        expires_at = timezone.datetime.fromisoformat(expires_at_raw)
        if timezone.is_naive(expires_at):
            expires_at = timezone.make_aware(expires_at, timezone.get_current_timezone())
    except Exception:
        _clear_signup_otp_session(request)
        return None

    if timezone.now() > expires_at:
        _clear_signup_otp_session(request)
        return None
    return payload


def _send_registration_email(request, user):
    """Send a registration confirmation email to newly created users."""
    if not user.email:
        return

    login_url = request.build_absolute_uri('/accounts/login/')
    subject = 'Welcome to Civic Zone Solution'
    message = (
        f"Hello {user.get_full_name() or user.username},\n\n"
        "Your account has been created successfully on Civic Zone Solution.\n"
        "You can now log in and submit or track your complaints online.\n\n"
        f"Login here: {login_url}\n\n"
        "If you did not create this account, please contact support immediately.\n\n"
        "Regards,\n"
        "Civic Zone Solution Team"
    )

    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=False,
    )


def _is_google_oauth_configured(request):
    """Return True when Google OAuth is configured via env vars or SocialApp."""
    if os.environ.get('GOOGLE_CLIENT_ID') and os.environ.get('GOOGLE_CLIENT_SECRET'):
        return True

    try:
        from allauth.socialaccount.models import SocialApp
        from django.contrib.sites.shortcuts import get_current_site

        current_site = get_current_site(request)
        return SocialApp.objects.filter(provider='google', sites=current_site).exists()
    except Exception:
        return False

def home(request):
    """Home/Landing page view"""
    if request.user.is_authenticated:
        # If user is logged in, redirect to appropriate dashboard
        if request.user.role == 'user':
            return redirect('dashboard')
        elif request.user.role in ['administrator', 'officer']:
            return redirect('admin_panel')
    
    # For non-authenticated users, show the home page
    return render(request, 'accounts/home.html')


def privacy_policy(request):
    """Public privacy policy page."""
    privacy_text = _read_content_file(PRIVACY_CONTENT_FILE, DEFAULT_PRIVACY_TEXT)

    if request.method == 'POST':
        if not _can_manage_footer_content(request.user):
            return HttpResponseForbidden('Only administrator can edit privacy content.')

        updated_privacy = (request.POST.get('privacy_content') or '').strip()
        if not updated_privacy:
            messages.error(request, 'Privacy content cannot be empty.')
        else:
            _write_content_file(PRIVACY_CONTENT_FILE, updated_privacy)
            messages.success(request, 'Privacy content updated successfully.')
        return redirect('privacy_policy')

    return render(
        request,
        'accounts/privacy_policy.html',
        {
            'privacy_text': privacy_text,
            'privacy_last_updated': _file_last_updated(PRIVACY_CONTENT_FILE),
            'can_edit_footer': _can_manage_footer_content(request.user),
        },
    )


def _can_manage_footer_content(user):
    """Allow footer content edits only for administrator accounts."""
    return user.is_authenticated and (user.is_superuser or getattr(user, 'role', None) == 'administrator')


def _read_content_file(path, default_text):
    os.makedirs(FOOTER_CONTENT_DIR, exist_ok=True)
    if not os.path.exists(path):
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(default_text.strip() + '\n')
    with open(path, 'r', encoding='utf-8') as handle:
        return handle.read().strip()


def _write_content_file(path, value):
    os.makedirs(FOOTER_CONTENT_DIR, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(value.strip() + '\n')


def _file_last_updated(path):
    if not os.path.exists(path):
        return timezone.now()
    return timezone.localtime(timezone.datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.get_current_timezone()))


def terms_and_conditions(request):
    """Public terms and conditions page."""
    terms_text = _read_content_file(TERMS_CONTENT_FILE, DEFAULT_TERMS_TEXT)

    if request.method == 'POST':
        if not _can_manage_footer_content(request.user):
            return HttpResponseForbidden('Only administrator can edit terms content.')

        updated_terms = (request.POST.get('terms_content') or '').strip()
        if not updated_terms:
            messages.error(request, 'Terms content cannot be empty.')
        else:
            _write_content_file(TERMS_CONTENT_FILE, updated_terms)
            messages.success(request, 'Terms content updated successfully.')
        return redirect('terms_and_conditions')

    return render(
        request,
        'accounts/terms_and_conditions.html',
        {
            'terms_text': terms_text,
            'terms_last_updated': _file_last_updated(TERMS_CONTENT_FILE),
            'can_edit_footer': _can_manage_footer_content(request.user),
        },
    )


def support_page(request):
    """Public support/contact page."""
    support_text = _read_content_file(SUPPORT_CONTENT_FILE, DEFAULT_SUPPORT_TEXT)

    if request.method == 'POST':
        if not _can_manage_footer_content(request.user):
            return HttpResponseForbidden('Only administrator can edit support content.')

        updated_support = (request.POST.get('support_content') or '').strip()
        if not updated_support:
            messages.error(request, 'Support content cannot be empty.')
        else:
            _write_content_file(SUPPORT_CONTENT_FILE, updated_support)
            messages.success(request, 'Support content updated successfully.')
        return redirect('support_page')

    return render(
        request,
        'accounts/support.html',
        {
            'support_text': support_text,
            'can_edit_footer': _can_manage_footer_content(request.user),
        },
    )

def user_register(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            try:
                email_otp = _generate_numeric_otp()

                _send_signup_email_otp(form.cleaned_data['email'], email_otp)

                _store_signup_otp_session(
                    request,
                    {
                        'username': form.cleaned_data['username'],
                        'email': form.cleaned_data['email'],
                        'phone': form.cleaned_data['phone'],
                        'first_name': form.cleaned_data.get('first_name', ''),
                        'last_name': form.cleaned_data.get('last_name', ''),
                        'password1': form.cleaned_data['password1'],
                        'password2': form.cleaned_data['password2'],
                    },
                    email_otp,
                )

                messages.info(request, 'OTP sent to your email. Please verify to complete registration.')
                return redirect('verify_signup_otp')
            except ValidationError as exc:
                messages.error(request, str(exc))
            except Exception:
                messages.error(request, "Unable to send OTP right now due to server configuration issue.")
    else:
        form = CustomUserCreationForm()
    return render(request, 'accounts/register.html', {'form': form})


def verify_signup_otp(request):
    payload = _get_signup_otp_payload(request)
    if not payload:
        messages.error(request, 'OTP session expired or not found. Please register again.')
        return redirect('register')

    form_data = payload.get('form_data', {})
    email = form_data.get('email', '')

    if request.method == 'POST':
        entered_email_otp = (request.POST.get('email_otp') or '').strip()

        if entered_email_otp != payload.get('email_otp'):
            messages.error(request, 'Invalid email OTP.')
        else:
            register_form = CustomUserCreationForm(form_data)
            if register_form.is_valid():
                user = register_form.save(commit=False)
                user.role = 'user'
                user.save()

                _clear_signup_otp_session(request)

                try:
                    _send_registration_email(request, user)
                except Exception:
                    messages.warning(request, 'Account created, but welcome email could not be sent right now.')

                messages.success(request, 'Registration successful! Please log in.')
                return redirect('login')

            _clear_signup_otp_session(request)
            messages.error(request, 'Registration data became invalid. Please register again.')
            return redirect('register')

    context = {
        'masked_email': _mask_email(email),
        'otp_expiry_minutes': SIGNUP_OTP_EXPIRY_MINUTES,
    }
    return render(request, 'accounts/verify_signup_otp.html', context)


def resend_signup_otp(request):
    payload = _get_signup_otp_payload(request)
    if not payload:
        messages.error(request, 'OTP session expired. Please register again.')
        return redirect('register')

    form_data = payload.get('form_data', {})
    email = form_data.get('email')

    try:
        email_otp = _generate_numeric_otp()
        _send_signup_email_otp(email, email_otp)
        _store_signup_otp_session(request, form_data, email_otp)
        messages.success(request, 'New OTP sent to your email.')
    except ValidationError as exc:
        messages.error(request, str(exc))
    except Exception:
        messages.error(request, 'Unable to resend OTP right now. Please try again in a moment.')

    return redirect('verify_signup_otp')

def user_login(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(request, username=username, password=password)
            
            if user is not None:
                # Check if user is active
                if not user.is_active:
                    messages.error(request, "Your account has been disabled.")
                    return render(request, 'accounts/login.html', {'form': form, 'google_oauth_enabled': _is_google_oauth_configured(request)})
                
                if user.role == 'user':
                    # User login no longer requires email confirmation.
                    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                    messages.success(request, f"Welcome back, {user.get_full_name() or user.username}!")
                    return redirect('dashboard')
                else:
                    messages.error(request, "Access denied. User login only.")
            else:
                messages.error(request, "Invalid username or password.")
        else:
            messages.error(request, "Invalid form data.")
    else:
        form = AuthenticationForm()
    return render(request, 'accounts/login.html', {
        'form': form,
        'google_oauth_enabled': _is_google_oauth_configured(request),
    })


def google_login_start(request):
    """Start Google OAuth if configured; otherwise show a helpful message."""
    if _is_google_oauth_configured(request):
        return redirect('/accounts/google/login/?process=login')

    messages.error(
        request,
        'Google Sign-In is not configured. Add Google OAuth credentials in Admin > Social Applications or set GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET.'
    )
    return redirect('login')

@login_required
def user_logout(request):
    logout(request)
    return redirect('home')

@never_cache
@ensure_csrf_cookie
def admin_login(request):
    # Check if user is already logged in as admin/officer
    if request.user.is_authenticated:
        if hasattr(request.user, 'role') and request.user.role in ['administrator', 'officer']:
            return redirect('admin_panel')
    
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        
        # Security: Check login attempts
        login_attempts = request.session.get(LOGIN_ATTEMPTS_KEY, {})
        current_time = timezone.now().timestamp()
        
        # Clean up old attempts
        login_attempts = {k: v for k, v in login_attempts.items() 
                         if (current_time - v['timestamp']) < LOGIN_ATTEMPT_TIMEOUT}
        
        # Check if locked out
        if username in login_attempts:
            if login_attempts[username]['count'] >= MAX_LOGIN_ATTEMPTS:
                time_remaining = int(LOGIN_ATTEMPT_TIMEOUT - (current_time - login_attempts[username]['timestamp']))
                messages.error(request, f"Too many login attempts. Please try again in {time_remaining} seconds.")
                request.session[LOGIN_ATTEMPTS_KEY] = login_attempts
                return render(request, 'accounts/admin_login.html')
        
        # Validate input
        if not username or not password:
            messages.error(request, "Please enter both username and password.")
            return render(request, 'accounts/admin_login.html')
        
        # Authenticate user
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            # Security: Check user status
            if not user.is_active:
                messages.error(request, "Your account has been disabled. Please contact administrator.")
                return render(request, 'accounts/admin_login.html')
            
            # Check user role
            if not hasattr(user, 'role'):
                messages.error(request, "User role not configured. Contact administrator.")
                return render(request, 'accounts/admin_login.html')
            
            if user.role not in ['administrator', 'officer']:
                # Log failed access attempt
                if username not in login_attempts:
                    login_attempts[username] = {'count': 0, 'timestamp': current_time}
                login_attempts[username]['count'] += 1
                login_attempts[username]['timestamp'] = current_time
                request.session[LOGIN_ATTEMPTS_KEY] = login_attempts
                
                messages.error(request, "Access denied. Admin/Officer login only.")
                return render(request, 'accounts/admin_login.html')
            
            # ✅ SEND EMAIL CONFIRMATION
            try:
                # Generate unique confirmation token
                token = _generate_unique_token()
                
                # Build confirmation link
                confirmation_link = request.build_absolute_uri(
                    reverse('confirm_admin_login', kwargs={'token': token})
                )
                
                # Send confirmation email
                _send_login_confirmation_email(user, confirmation_link)
                
                # Store in session
                request.session[LOGIN_CONFIRMATION_KEY] = {
                    'token': token,
                    'user_id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'ip_address': _get_client_ip(request),
                    'user_agent': _get_user_agent(request),
                    'expires_at': (timezone.now() + timedelta(minutes=LOGIN_CONFIRMATION_EXPIRY_MINUTES)).isoformat(),
                }
                request.session.modified = True

                cache.set(
                    _admin_login_confirm_cache_key(token),
                    {
                        'user_id': user.id,
                        'ip_address': _get_client_ip(request),
                        'user_agent': _get_user_agent(request),
                        'confirmed': False,
                    },
                    timeout=LOGIN_CONFIRMATION_EXPIRY_MINUTES * 60,
                )
                
                # Clear login attempts on successful credential verification
                if username in login_attempts:
                    del login_attempts[username]
                request.session[LOGIN_ATTEMPTS_KEY] = login_attempts
                
                messages.success(request, f"Confirmation email sent to {_mask_email(user.email)}. Click the link to login.")
                return redirect('admin_login_confirmation_pending')
                
            except Exception as e:
                messages.error(request, f"Error sending confirmation email: {str(e)}")
                return render(request, 'accounts/admin_login.html')
        else:
            # Invalid credentials - track attempt
            if username not in login_attempts:
                login_attempts[username] = {'count': 0, 'timestamp': current_time}
            login_attempts[username]['count'] += 1
            login_attempts[username]['timestamp'] = current_time
            request.session[LOGIN_ATTEMPTS_KEY] = login_attempts
            
            remaining_attempts = MAX_LOGIN_ATTEMPTS - login_attempts[username]['count']
            messages.error(request, f"Invalid username or password. ({remaining_attempts} attempts remaining)")
    
    return render(request, 'accounts/admin_login.html')


@csrf_protect
def admin_login_verify_otp(request):
    """Verify OTP for admin/officer login"""
    # Check if OTP session exists
    otp_payload = request.session.get(ADMIN_LOGIN_OTP_KEY)
    user_info = request.session.get(ADMIN_LOGIN_USER_KEY)
    
    if not otp_payload or not user_info:
        messages.error(request, "OTP session expired. Please login again.")
        return redirect('admin_login')
    
    # Check OTP expiry
    try:
        expires_at = timezone.datetime.fromisoformat(otp_payload['expires_at'])
        if timezone.is_naive(expires_at):
            expires_at = timezone.make_aware(expires_at, timezone.get_current_timezone())
        
        if timezone.now() > expires_at:
            # Clear expired OTP
            if ADMIN_LOGIN_OTP_KEY in request.session:
                del request.session[ADMIN_LOGIN_OTP_KEY]
            if ADMIN_LOGIN_USER_KEY in request.session:
                del request.session[ADMIN_LOGIN_USER_KEY]
            request.session.modified = True
            
            messages.error(request, "OTP has expired. Please login again.")
            return redirect('admin_login')
    except Exception as e:
        messages.error(request, "Invalid OTP session.")
        return redirect('admin_login')
    
    if request.method == 'POST':
        otp_entered = request.POST.get('otp', '').strip()
        
        if not otp_entered:
            messages.error(request, "Please enter the OTP.")
            return render(request, 'accounts/admin_login_verify_otp.html', {'email': _mask_email(user_info['email'])})
        
        # Verify OTP
        if otp_entered == otp_payload['otp']:
            # OTP is correct - login user
            user = get_object_or_404(CustomUser, id=otp_payload['user_id'])
            
            # Check user is still active
            if not user.is_active:
                messages.error(request, "Your account has been disabled.")
                return redirect('admin_login')
            
            # Login user
            login(request, user)
            
            # Send login notification email
            _send_admin_login_email(
                user,
                user_info['ip_address'],
                user_info['user_agent']
            )
            
            # Clear OTP and user info from session
            if ADMIN_LOGIN_OTP_KEY in request.session:
                del request.session[ADMIN_LOGIN_OTP_KEY]
            if ADMIN_LOGIN_USER_KEY in request.session:
                del request.session[ADMIN_LOGIN_USER_KEY]
            request.session.modified = True
            
            messages.success(request, f"Welcome, {user.get_full_name() or user.username}! Login verified.")
            return redirect('admin_panel')
        else:
            messages.error(request, "Invalid OTP. Please try again.")
    
    context = {
        'email': _mask_email(user_info['email']),
        'username': user_info['username']
    }
    return render(request, 'accounts/admin_login_verify_otp.html', context)


@csrf_protect
def admin_resend_otp(request):
    """Resend OTP for admin/officer login"""
    otp_payload = request.session.get(ADMIN_LOGIN_OTP_KEY)
    user_info = request.session.get(ADMIN_LOGIN_USER_KEY)
    
    if not otp_payload or not user_info:
        messages.error(request, "OTP session expired. Please login again.")
        return redirect('admin_login')
    
    try:
        user = CustomUser.objects.get(id=otp_payload['user_id'])
        
        # Generate new OTP
        new_otp = _generate_numeric_otp()
        
        # Send new OTP email
        _send_admin_login_otp_email(user, new_otp)
        
        # Update session
        request.session[ADMIN_LOGIN_OTP_KEY] = {
            'otp': new_otp,
            'user_id': user.id,
            'username': user.username,
            'expires_at': (timezone.now() + timedelta(minutes=ADMIN_LOGIN_OTP_EXPIRY_MINUTES)).isoformat(),
        }
        request.session.modified = True
        
        messages.success(request, f"New OTP sent to {_mask_email(user.email)}")
        return redirect('admin_login_verify_otp')
    except Exception as e:
        messages.error(request, f"Error resending OTP: {str(e)}")
        return redirect('admin_login')


def admin_login_confirmation_pending(request):
    """Show pending confirmation page for admin login"""
    confirmation_data = request.session.get(LOGIN_CONFIRMATION_KEY)
    
    if not confirmation_data:
        messages.error(request, "No pending confirmation. Please login again.")
        return redirect('admin_login')
    
    context = {
        'email': _mask_email(confirmation_data['email']),
        'username': confirmation_data['username']
    }
    return render(request, 'accounts/admin_login_confirmation_pending.html', context)


def admin_login_status(request):
    """Return whether admin/officer is authenticated in this browser session."""
    if request.user.is_authenticated and getattr(request.user, 'role', None) in ['administrator', 'officer']:
        return JsonResponse({
            'authenticated': True,
            'redirect_url': reverse('admin_panel'),
        })

    confirmation_data = request.session.get(LOGIN_CONFIRMATION_KEY)
    if confirmation_data:
        token = confirmation_data.get('token')
        if token:
            cache_data = cache.get(_admin_login_confirm_cache_key(token))
            if cache_data and cache_data.get('confirmed'):
                try:
                    user = CustomUser.objects.get(id=confirmation_data['user_id'])
                    if user.is_active and getattr(user, 'role', None) in ['administrator', 'officer']:
                        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                        if LOGIN_CONFIRMATION_KEY in request.session:
                            del request.session[LOGIN_CONFIRMATION_KEY]
                        request.session.modified = True
                        cache.delete(_admin_login_confirm_cache_key(token))
                        return JsonResponse({
                            'authenticated': True,
                            'redirect_url': reverse('admin_panel'),
                        })
                except CustomUser.DoesNotExist:
                    pass

    return JsonResponse({'authenticated': False})


def confirm_admin_login(request, token):
    """Confirm admin login via email link"""
    confirmation_data = request.session.get(LOGIN_CONFIRMATION_KEY)
    cache_data = cache.get(_admin_login_confirm_cache_key(token))

    if not cache_data:
        messages.error(request, "Confirmation session expired. Please login again.")
        return redirect('admin_login')

    if confirmation_data and confirmation_data.get('token') != token:
        confirmation_data = None
    
    # Check expiry from session data when available.
    if confirmation_data:
        try:
            expires_at = timezone.datetime.fromisoformat(confirmation_data['expires_at'])
            if timezone.is_naive(expires_at):
                expires_at = timezone.make_aware(expires_at, timezone.get_current_timezone())
            
            if timezone.now() > expires_at:
                # Clear expired confirmation
                if LOGIN_CONFIRMATION_KEY in request.session:
                    del request.session[LOGIN_CONFIRMATION_KEY]
                request.session.modified = True
                
                messages.error(request, "Confirmation link has expired. Please login again.")
                return redirect('admin_login')
        except Exception:
            messages.error(request, "Invalid confirmation session.")
            return redirect('admin_login')
    
    try:
        # Get user and login
        user_id = confirmation_data['user_id'] if confirmation_data else cache_data.get('user_id')
        user = CustomUser.objects.get(id=user_id)
        
        if not user.is_active:
            messages.error(request, "Your account has been disabled.")
            return redirect('admin_login')
        
        # Mark confirmation complete for the original project tab.
        cache.set(
            _admin_login_confirm_cache_key(token),
            {
                **cache_data,
                'user_id': user.id,
                'confirmed': True,
            },
            timeout=LOGIN_CONFIRMATION_EXPIRY_MINUTES * 60,
        )

        # Send login notification email (optional - for audit trail)
        _send_admin_login_email(
            user,
            (confirmation_data or {}).get('ip_address', cache_data.get('ip_address', 'Unknown')),
            (confirmation_data or {}).get('user_agent', cache_data.get('user_agent', 'Unknown'))
        )
        
        messages.success(request, f"Welcome, {user.get_full_name() or user.username}! You have been successfully logged in.")
        return render(request, 'accounts/admin_login_confirmed_email.html')
        
    except CustomUser.DoesNotExist:
        messages.error(request, "User not found.")
        return redirect('admin_login')
    except Exception as e:
        messages.error(request, f"Error during login: {str(e)}")
        return redirect('admin_login')


def login_confirmation_pending(request):
    """Show pending confirmation page for user login"""
    confirmation_data = request.session.get(USER_LOGIN_CONFIRMATION_KEY)
    
    if not confirmation_data:
        messages.error(request, "No pending confirmation. Please login again.")
        return redirect('login')
    
    context = {
        'email': _mask_email(confirmation_data['email']),
        'username': confirmation_data['username']
    }
    return render(request, 'accounts/login_confirmation_pending.html', context)


def confirm_user_login(request, token):
    """Confirm user login via email link"""
    confirmation_data = request.session.get(USER_LOGIN_CONFIRMATION_KEY)
    
    if not confirmation_data:
        messages.error(request, "Confirmation session expired. Please login again.")
        return redirect('login')
    
    # Verify token
    if confirmation_data['token'] != token:
        messages.error(request, "Invalid confirmation link.")
        return redirect('login')
    
    # Check expiry
    try:
        expires_at = timezone.datetime.fromisoformat(confirmation_data['expires_at'])
        if timezone.is_naive(expires_at):
            expires_at = timezone.make_aware(expires_at, timezone.get_current_timezone())
        
        if timezone.now() > expires_at:
            # Clear expired confirmation
            if USER_LOGIN_CONFIRMATION_KEY in request.session:
                del request.session[USER_LOGIN_CONFIRMATION_KEY]
            request.session.modified = True
            
            messages.error(request, "Confirmation link has expired. Please login again.")
            return redirect('login')
    except Exception:
        messages.error(request, "Invalid confirmation session.")
        return redirect('login')
    
    try:
        # Get user and login
        user = CustomUser.objects.get(id=confirmation_data['user_id'])
        
        if not user.is_active:
            messages.error(request, "Your account has been disabled.")
            return redirect('login')
        
        # Login user
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        
        # Clear confirmation from session
        if USER_LOGIN_CONFIRMATION_KEY in request.session:
            del request.session[USER_LOGIN_CONFIRMATION_KEY]
        request.session.modified = True
        
        messages.success(request, f"Welcome back, {user.get_full_name() or user.username}! You have been successfully logged in.")
        return redirect('dashboard')
        
    except CustomUser.DoesNotExist:
        messages.error(request, "User not found.")
        return redirect('login')
    except Exception as e:
        messages.error(request, f"Error during login: {str(e)}")
        return redirect('login')

@csrf_protect
def admin_forgot_password(request):
    """Handle admin/officer forgot password - send reset link by email."""
    if request.method == 'POST':
        form = AdminForgotPasswordForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            user = CustomUser.objects.filter(
                Q(username__iexact=username) | Q(email__iexact=username),
                role__in=['administrator', 'officer']
            ).first()
            if user and user.email:
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                token = default_token_generator.make_token(user)
                _send_admin_password_reset_email(request, user, uid, token)

            messages.success(request, 'Password reset link has been sent to your registered email address.')
            return redirect('admin_login')
    else:
        form = AdminForgotPasswordForm()
    
    return render(request, 'accounts/admin_forgot_password.html', {'form': form})

@csrf_protect
def admin_reset_password(request):
    """Legacy route. Redirect to forgot-password to request a fresh reset link."""
    messages.info(request, 'Please request a new password reset link from forgot password page.')
    return redirect('admin_forgot_password')


@csrf_protect
def admin_reset_password_confirm(request, uidb64, token):
    """Handle admin/officer reset password confirmation by tokenized email link."""
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = CustomUser.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, CustomUser.DoesNotExist):
        user = None

    if user is None or not default_token_generator.check_token(user, token) or user.role not in ['administrator', 'officer']:
        messages.error(request, 'Invalid or expired password reset link.')
        return redirect('admin_forgot_password')

    if request.method == 'POST':
        form = AdminResetPasswordForm(request.POST)
        if form.is_valid():
            new_password = form.cleaned_data['new_password']
            user.set_password(new_password)
            user.save()
            messages.success(request, 'Password reset successfully. Please log in with your new password.')
            return redirect('admin_login')
    else:
        form = AdminResetPasswordForm()

    return render(request, 'accounts/admin_reset_password.html', {
        'form': form,
        'username': user.username
    })


@csrf_protect
def officer_forgot_password(request):
    """Handle zone officer forgot password - email input"""
    if request.method == 'POST':
        form = OfficerForgotPasswordForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            user = CustomUser.objects.filter(email=email, role='officer').first()
            
            # Generate token
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            
            # Send email
            _send_officer_password_reset_email(request, user, uid, token)
            
            messages.success(request, 'Password reset link has been sent to your email address.')
            return redirect('admin_login')  # Redirect to login page
    else:
        form = OfficerForgotPasswordForm()
    
    return render(request, 'accounts/officer_forgot_password.html', {'form': form})


@csrf_protect
def officer_reset_password_confirm(request, uidb64, token):
    """Handle zone officer password reset confirmation"""
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = CustomUser.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, CustomUser.DoesNotExist):
        user = None
    
    if user is not None and default_token_generator.check_token(user, token) and user.role == 'officer':
        if request.method == 'POST':
            form = OfficerResetPasswordForm(request.POST)
            if form.is_valid():
                new_password = form.cleaned_data['new_password']
                user.set_password(new_password)
                user.save()
                messages.success(request, 'Password reset successfully. Please log in with your new password.')
                return redirect('admin_login')
        else:
            form = OfficerResetPasswordForm()
        
        return render(request, 'accounts/officer_reset_password.html', {
            'form': form,
            'validlink': True
        })
    else:
        return render(request, 'accounts/officer_reset_password.html', {
            'form': None,
            'validlink': False
        })


def _send_officer_password_reset_email(request, user, uid, token):
    """Send password reset email to zone officer"""
    reset_url = request.build_absolute_uri(
        reverse('officer_reset_password_confirm', kwargs={'uidb64': uid, 'token': token})
    )
    
    subject = 'Password Reset Request - Zone Officer'
    message = f"""
Hello {user.get_full_name() or user.username},

You have requested a password reset for your Zone Officer account.

Please click the link below to reset your password:
{reset_url}

This link will expire in 24 hours.

If you did not request this password reset, please ignore this email.

Best regards,
Civic Zone Team
"""
    
    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False
        )
        # Log notification
        _log_password_reset_notification(
            user, 
            message, 
            reason='officer_password_reset',
            status='sent'
        )
    except Exception as e:
        # Log failed notification
        _log_password_reset_notification(
            user,
            f"Password reset email failed: {str(e)}",
            reason='officer_password_reset',
            status='failed'
        )
        raise


def _send_admin_password_reset_email(request, user, uid, token):
    """Send password reset email to admin/officer user from admin forgot-password flow."""
    reset_url = request.build_absolute_uri(
        reverse('admin_reset_password_confirm', kwargs={'uidb64': uid, 'token': token})
    )

    subject = 'Password Reset Request - Admin/Officer'
    message = f"""
Hello {user.get_full_name() or user.username},

You have requested a password reset for your admin/officer account.

Please click the link below to reset your password:
{reset_url}

This link will expire in 24 hours.

If you did not request this password reset, please ignore this email.

Best regards,
Civic Zone Team
"""

    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False
        )
        # Log notification
        _log_password_reset_notification(
            user,
            message,
            reason='admin_password_reset',
            status='sent'
        )
    except Exception as e:
        # Log failed notification
        _log_password_reset_notification(
            user,
            f"Password reset email failed: {str(e)}",
            reason='admin_password_reset',
            status='failed'
        )
        raise


@login_required
def user_profile(request):
    """Display and update user profile"""
    user = request.user
    
    if request.method == 'POST':
        form = CustomUserChangeForm(request.POST, request.FILES, instance=user)
        
        if form.is_valid():
            # Save the form
            updated_user = form.save(commit=False)
            
            # Update last_profile_update timestamp
            from django.utils import timezone
            updated_user.last_profile_update = timezone.now()
            
            # Check profile completion
            updated_user.check_profile_completion()
            
            updated_user.save()
            user = updated_user
            
            messages.success(request, 'Profile updated successfully!')
            return redirect('user_profile')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = CustomUserChangeForm(instance=user)
    
    completion_stats = user.get_profile_completion_stats()
    
    context = {
        'user': user,
        'form': form,
        'completion_percentage': completion_stats['completion_percentage'],
        'completed_fields': completion_stats['completed_fields'],
        'total_fields': completion_stats['total_fields'],
        'age': user.get_age(),
    }
    
    return render(request, 'accounts/user_profile.html', context)

@login_required
def update_profile_picture(request):
    """Update only profile picture"""
    if request.method == 'POST':
        form = ProfilePictureForm(request.POST, request.FILES, instance=request.user)
        
        if form.is_valid():
            # Delete old profile picture if exists
            old_picture = request.user.profile_picture
            if old_picture:
                if os.path.isfile(old_picture.path):
                    os.remove(old_picture.path)
            
            form.save()
            messages.success(request, 'Profile picture updated successfully!')
        else:
            messages.error(request, 'Error updating profile picture.')

    if request.user.role in ['officer', 'administrator']:
        return redirect('officer_profile')
    return redirect('user_profile')


@login_required
def delete_profile_picture(request):
    """Delete current user's profile picture."""
    if request.method == 'POST':
        picture = request.user.profile_picture
        if picture:
            if os.path.isfile(picture.path):
                os.remove(picture.path)
            request.user.profile_picture = None
            request.user.save(update_fields=['profile_picture'])
            messages.success(request, 'Profile picture removed successfully.')
        else:
            messages.info(request, 'No profile picture found to remove.')

    if request.user.role in ['officer', 'administrator']:
        return redirect('officer_profile')
    return redirect('user_profile')

@login_required
def request_change_password(request):
    """Send email with change password link"""
    user = request.user
    
    # Generate URLs
    reset_token = _generate_unique_token()
    cache.set(
        _profile_password_reset_cache_key(reset_token),
        {'user_id': user.pk},
        timeout=60 * 60
    )
    change_password_url = request.build_absolute_uri(
        reverse('profile_change_password_confirm', kwargs={'token': reset_token})
    )
    if user.role in ['officer', 'administrator']:
        login_url = request.build_absolute_uri(reverse('admin_login'))
    else:
        login_url = request.build_absolute_uri(reverse('login'))
    
    # Send email
    subject = 'Change Your Password - Civic Zone Solution'
    message = (
        f"Hello {user.get_full_name() or user.username},\n\n"
        "You have requested to change your password.\n\n"
        f"Click the link below to change your password:\n{change_password_url}\n\n"
        "This link will open the password reset page directly.\n\n"
        f"If you need to login first, use this link:\n{login_url}\n\n"
        "If you did not request this change, please ignore this email.\n\n"
        "Regards,\n"
        "Civic Zone Solution Team"
    )
    
    try:
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False)
        # Log notification
        _log_password_reset_notification(
            user,
            message,
            reason='profile_change_password',
            status='sent'
        )
        messages.success(request, 'Password change link has been sent to your email. Please check your inbox.')
    except Exception as e:
        # Log failed notification
        _log_password_reset_notification(
            user,
            f"Password change link email failed: {str(e)}",
            reason='profile_change_password',
            status='failed'
        )
        print(f"Email sending failed: {str(e)}")  # Debug logging
        messages.error(request, f'Unable to send email right now. Error: {str(e)}')
    
    # Redirect back to profile
    if user.role in ['officer', 'administrator']:
        return redirect('officer_profile')
    return redirect('user_profile')


def profile_change_password_confirm(request, token):
    """Public password reset page opened from profile email link."""
    cache_key = _profile_password_reset_cache_key(token)
    payload = cache.get(cache_key)
    if not payload:
        return render(request, 'accounts/profile_change_password_confirm.html', {
            'form': None,
            'validlink': False,
            'back_url': reverse('login'),
        })

    try:
        user = CustomUser.objects.get(pk=payload['user_id'])
    except CustomUser.DoesNotExist:
        cache.delete(cache_key)
        return render(request, 'accounts/profile_change_password_confirm.html', {
            'form': None,
            'validlink': False,
            'back_url': reverse('login'),
        })

    if request.method == 'POST':
        form = ProfileResetPasswordForm(request.POST)
        if form.is_valid():
            user.set_password(form.cleaned_data['new_password'])
            user.save()
            cache.delete(cache_key)
            messages.success(request, 'Password changed successfully. Please log in with your new password.')
            if user.role in ['officer', 'administrator']:
                return redirect('admin_login')
            return redirect('login')
    else:
        form = ProfileResetPasswordForm()

    return render(request, 'accounts/profile_change_password_confirm.html', {
        'form': form,
        'validlink': True,
        'username': user.get_full_name() or user.username,
        'back_url': reverse('admin_login') if user.role in ['officer', 'administrator'] else reverse('login'),
    })

@login_required
def change_password(request):
    """Change user password"""
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        
        if form.is_valid():
            # Change password
            new_password = form.cleaned_data['new_password']
            request.user.set_password(new_password)
            request.user.save()
            
            # Update session to prevent logout
            update_session_auth_hash(request, request.user)

            if request.user.role == 'officer' and request.user.email:
                change_password_url = request.build_absolute_uri(reverse('change_password'))
                officer_login_url = request.build_absolute_uri(reverse('admin_login'))
                subject = 'Password Changed Successfully - Civic Zone Solution'
                message = (
                    f"Hello {request.user.get_full_name() or request.user.username},\n\n"
                    "Your password has been changed successfully.\n\n"
                    f"Password change page link:\n{change_password_url}\n\n"
                    f"Admin/Officer login page link:\n{officer_login_url}\n\n"
                    "If you did not make this change, please contact the administrator immediately.\n\n"
                    "Regards,\n"
                    "Civic Zone Solution Team"
                )

                try:
                    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [request.user.email], fail_silently=False)
                    # Log notification
                    _log_password_reset_notification(
                        request.user,
                        message,
                        reason='password_changed',
                        status='sent'
                    )
                except Exception as e:
                    # Log failed notification
                    _log_password_reset_notification(
                        request.user,
                        f"Password change confirmation email failed: {str(e)}",
                        reason='password_changed',
                        status='failed'
                    )
                    print(f"Password change email failed: {str(e)}")
            
            messages.success(request, 'Password changed successfully!')
            if request.user.role in ['officer', 'administrator']:
                return redirect('officer_profile')
            return redirect('user_profile')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = PasswordChangeForm(request.user)
    
    return render(request, 'accounts/change_password.html', {'form': form})

@login_required
def officer_profile(request):
    """Display and update officer profile"""
    # Check if user is officer or administrator
    if request.user.role not in ['officer', 'administrator']:
        messages.error(request, "Access denied. Officer login only.")
        return redirect('dashboard')
    
    user = request.user
    
    if request.method == 'POST':
        form = OfficerProfileForm(request.POST, request.FILES, instance=user)
        
        if form.is_valid():
            # Save the form
            updated_user = form.save(commit=False)
            
            # Update last_profile_update timestamp
            from django.utils import timezone
            updated_user.last_profile_update = timezone.now()

            # Check profile completion
            updated_user.check_profile_completion()
            
            updated_user.save()
            user = updated_user
            
            messages.success(request, 'Profile updated successfully!')
            return redirect('officer_profile')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = OfficerProfileForm(instance=user)
    
    completion_stats = user.get_profile_completion_stats()
    
    context = {
        'user': user,
        'form': form,
        'completion_percentage': completion_stats['completion_percentage'],
        'completed_fields': completion_stats['completed_fields'],
        'total_fields': completion_stats['total_fields'],
        'age': user.get_age(),
    }
    
    return render(request, 'accounts/officer_profile.html', context)

@login_required
def delete_account(request):
    """Delete user account"""
    if request.method == 'POST':
        # Verify password
        password = request.POST.get('password')
        if request.user.check_password(password):
            # Delete user
            user = request.user
            user.delete()
            
            messages.success(request, 'Your account has been deleted successfully.')
            return redirect('login')
        else:
            messages.error(request, 'Incorrect password. Account not deleted.')
    
    return render(request, 'accounts/confirm_delete_account.html')

def forgot_password(request):
    """Handle forgot password requests by redirecting to Django's password reset"""
    messages.info(request, 'Please use the password reset form below to reset your password.')
    return redirect('password_reset')


@login_required
def chat_history_page(request):
    """Open full chatbot history in a dedicated page."""
    return render(request, 'chatbot/chat_history.html')


from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt, csrf_protect
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from complaints.models import Complaint


def _build_chatbot_user_context(user, is_logged_in):
    """Build a compact context block for AI-assisted chatbot responses."""
    if not is_logged_in:
        return "User is not logged in."

    complaints_qs = Complaint.objects.filter(user=user)
    total = complaints_qs.count()
    pending = complaints_qs.filter(status='Pending').count()
    in_progress = complaints_qs.filter(status='In Progress').count()
    resolved = complaints_qs.filter(status='Resolved').count()

    latest = complaints_qs.order_by('-complaint_date').first()
    latest_summary = "No complaints submitted yet."
    if latest:
        latest_summary = (
            f"Latest complaint: #{latest.complaint_id}, {latest.category}, "
            f"status={latest.status}, zone={latest.zone}."
        )

    return (
        f"User is logged in as {user.get_full_name() or user.username}. "
        f"Complaints summary: total={total}, pending={pending}, "
        f"in_progress={in_progress}, resolved={resolved}. "
        f"{latest_summary}"
    )


def _get_ai_chatbot_fallback(message, user, is_logged_in):
    """Return AI-generated chatbot response when deterministic rules do not match."""
    ai_enabled = bool(getattr(settings, 'CHATBOT_AI_ENABLED', False))
    if not ai_enabled:
        return None

    api_key = (getattr(settings, 'CHATBOT_AI_API_KEY', '') or '').strip()
    if not api_key:
        return None

    base_url = (getattr(settings, 'CHATBOT_AI_BASE_URL', 'https://api.openai.com/v1') or '').rstrip('/')
    model = getattr(settings, 'CHATBOT_AI_MODEL', 'gpt-4o-mini')
    timeout = int(getattr(settings, 'CHATBOT_AI_TIMEOUT_SECONDS', 12))

    user_context = _build_chatbot_user_context(user, is_logged_in)
    system_prompt = (
        "You are SMC Assistant for CivicZoneSolution. "
        "Reply in clear, practical, short bullet-style guidance. "
        "Use Gujarati-friendly simple English where helpful. "
        "Never invent private data. "
        "If asked unrelated or impossible platform actions, politely redirect to supported actions. "
        "Keep response under 10 lines."
    )

    payload = {
        'model': model,
        'temperature': 0.3,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'system', 'content': f'Context: {user_context}'},
            {'role': 'user', 'content': message},
        ],
        'max_tokens': 260,
    }

    req = Request(
        url=f"{base_url}/chat/completions",
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}',
        },
        method='POST',
    )

    try:
        with urlopen(req, timeout=timeout) as response:
            body = response.read().decode('utf-8')
        parsed = json.loads(body)
        ai_text = parsed.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
        return ai_text or None
    except (HTTPError, URLError, TimeoutError, ValueError, KeyError, IndexError, TypeError):
        return None

@csrf_exempt
def chatbot_response(request):
    """Simple and Clear SMC Chatbot"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            user_message = data.get('message', '').strip()
            
            # Get user info
            user_name = None
            is_logged_in = False
            if request.user.is_authenticated:
                user_name = request.user.get_full_name() or request.user.username
                is_logged_in = True
            
            # Get response
            response_data = get_chatbot_response(user_message, user_name, is_logged_in, request.user)
            
            return JsonResponse(response_data)
        except Exception as e:
            return JsonResponse({
                'response': 'Sorry, something went wrong. Please try again.',
                'suggestions': ['Help', 'Contact']
            })
    
    return JsonResponse({'response': 'Invalid request'}, status=400)


def get_chatbot_response(message, user_name, is_logged_in, user):
    """Advanced, user-friendly chatbot answers for common SMC queries."""

    raw_msg = (message or '').strip()
    msg = raw_msg.lower()
    clean_msg = ' '.join(''.join(ch if ch.isalnum() or ch.isspace() else ' ' for ch in msg).split())

    language_to_english = {
        'ફરિયાદ': 'complaint',
        'ફરિયાદો': 'complaints',
        'કમ્પ્લેઇન્ટ': 'complaint',
        'શિકાયત': 'complaint',
        'शिकायत': 'complaint',
        'કેટેગરી': 'category',
        'कैटेगरी': 'category',
        'સ્થિતિ': 'status',
        'स्टेटस': 'status',
        'स्थिति': 'status',
        'ટ્રેક': 'track',
        'ट्रैक': 'track',
        'મારી': 'my',
        'मेरी': 'my',
        'બતાવો': 'show',
        'दिखाओ': 'show',
        'કેવી રીતે': 'how to',
        'कैसे': 'how to',
        'ઝોન': 'zone',
        'ज़ोन': 'zone',
        'ડાયગ્રામ': 'diagram',
        'डायग्राम': 'diagram',
        'વિશ્લેષણ': 'analysis',
        'विश्लेषण': 'analysis',
        'મદદ': 'help',
        'सहायता': 'help',
        'મદદ કરો': 'help',
        'પાસવર્ડ': 'password',
        'पासवर्ड': 'password',
        'ચાર્જ': 'charge',
        'चार्ज': 'charge',
        'ફી': 'fee',
        'फीस': 'fee',
        'પૈસા': 'money',
        'पैसा': 'money',
        'સંપર્ક': 'contact',
        'संपर्क': 'contact',
        'ફોન': 'phone',
        'फोन': 'phone',
        'ઇમેઇલ': 'email',
        'ईमेल': 'email',
        'ઓફિસર': 'officer',
        'ऑफिसर': 'officer',
        'અધિકારી': 'officer',
        'अधिकारी': 'officer',
        'રજીસ્ટર': 'register',
        'रजिस्टर': 'register',
        'લોગિન': 'login',
        'लॉगिन': 'login',
        'નમસ્તે': 'hello',
        'नमस्ते': 'hello',
        'કેમ છો': 'hello',
        'ठीक है': 'ok',
        'બરાબર': 'ok',
    }

    translated_msg = f" {clean_msg} "
    for local_text, english_text in language_to_english.items():
        translated_msg = translated_msg.replace(f" {local_text} ", f" {english_text} ")
    translated_msg = ' '.join(translated_msg.split())

    language_aliases = {
        'submit complaint': [
            'ફરિયાદ નોંધાવો', 'ફરિયાદ કરવી', 'ફરિયાદ કરું', 'ફરિયાદ કેવી રીતે કરવી', 'complaint કેવી રીતે કરવી',
            'शिकायत दर्ज', 'शिकायत करना', 'शिकायत कैसे करें', 'कंप्लेंट दर्ज', 'कंप्लेंट करना',
            'fariyad nodhavo', 'fariyad karvi', 'complaint kem rite karvi', 'shikayat kaise kare',
            'fariyad kai rite karu', 'fariyad kai rite karvi', 'fariyad kevi rite karu', 'fariyad kevrite karu', 'fariyad kem rite karu',
            'fariyad kem rite karvi', 'complaint kevi rite karvi', 'complaint kai rite karvi'
        ],
        'my complaints': [
            'મારી ફરિયાદ', 'મારી ફરિયાદો', 'મારી કોમ્પ્લેઇન્ટ', 'મારો ઇશ્યુ',
            'मेरी शिकायत', 'मेरी शिकायतें', 'मेरी कंप्लेंट', 'मेरा इश्यू',
            'mari fariyad', 'mari fariyado', 'mari complaint', 'meri shikayat', 'show mari fariyad', 'fariyad batavo'
        ],
        'latest complaint': [
            'latest complaint', 'last complaint', 'recent complaint', 'my latest complaint',
            'mari latest complaint', 'mari last complaint', 'mari recent complaint',
            'latest fariyad', 'mari latest fariyad', 'meri latest shikayat',
            'latest complaint status', 'last complaint status', 'recent complaint status',
            'mari latest complaint kai che', 'mari latest complaint ka iche', 'mari latest complaint shu che'
        ],
        'track status': [
            'સ્થિતિ', 'સ્ટેટસ', 'ફરિયાદની સ્થિતિ', 'status ચેક', 'ટ્રેક',
            'स्थिति', 'स्टेटस', 'शिकायत की स्थिति', 'स्टेटस चेक', 'ट्रैक',
            'status batavo', 'fariyad status', 'mari fariyad no status', 'shikayat status'
        ],
        'analysis diagram': [
            'વિશ્લેષણ', 'ડાયગ્રામ', 'ચાર્ટ', 'રિપોર્ટ',
            'विश्लेषण', 'डायग्राम', 'चार्ट', 'रिपोर्ट'
        ],
        'resolution time': [
            'કેટલા દિવસ', 'કેટલો સમય', 'ક્યારે સોલ્વ',
            'कितने दिन', 'कितना समय', 'कब solve', 'कब resolve'
        ],
        'charges fee': [
            'ચાર્જ', 'ફી', 'પૈસા', 'ચુકવણી',
            'चार्ज', 'फीस', 'पैसा', 'भुगतान', 'पेमेंट'
        ],
        'contact support': [
            'સંપર્ક', 'હેલ્પલાઇન', 'ફોન નંબર', 'ઈમેઇલ',
            'संपर्क', 'हेल्पलाइन', 'फोन नंबर', 'ईमेल', 'सपोर्ट'
        ],
        'help': [
            'મદદ', 'ગાઇડ', 'સમજાવો',
            'मदद', 'सहायता', 'गाइड', 'समझाओ',
            'madad', 'guide karo', 'samjavo'
        ],
        'login register': [
            'લોગિન', 'પ્રવેશ', 'રજીસ્ટર', 'નવું એકાઉન્ટ',
            'लॉगिन', 'प्रवेश', 'रजिस्टर', 'नया अकाउंट'
        ],
        'password': [
            'પાસવર્ડ', 'પાસવર્ડ ભૂલી ગયો', 'પાસવર્ડ રીસેટ',
            'पासवर्ड', 'पासवर्ड भूल गया', 'पासवर्ड रीसेट', 'पासवर्ड बदलना'
        ],
        'profile account': [
            'પ્રોફાઇલ', 'એકાઉન્ટ', 'મારી વિગતો',
            'प्रोफाइल', 'अकाउंट', 'मेरी डिटेल्स'
        ],
        'zones': [
            'ઝોન', 'કયો ઝોન', 'ઝોન લિસ્ટ',
            'ज़ोन', 'कौन सा ज़ोन', 'ज़ोन लिस्ट'
        ],
        'categories': [
            'કેટેગરી', 'ફરિયાદ પ્રકાર',
            'कैटेगरी', 'शिकायत प्रकार'
        ],
        'officer contact': [
            'અધિકારી', 'ઓફિસર', 'ઝોન ઓફિસર',
            'अधिकारी', 'ऑफिसर', 'ज़ोन ऑफिसर'
        ]
    }

    expanded_msg = f"{clean_msg} {translated_msg}".strip()
    for canonical_phrase, localized_keywords in language_aliases.items():
        if any(keyword in msg for keyword in localized_keywords):
            expanded_msg += f" {canonical_phrase}"

    normalized_expanded_msg = f" {expanded_msg} "
    expanded_tokens = set(expanded_msg.split())

    response = ""
    suggestions = []

    def has_any(*keywords):
        for keyword in keywords:
            k = (keyword or '').strip().lower()
            if not k:
                continue

            # Phrase-level exact matching to avoid accidental partial hits.
            if ' ' in k:
                if f" {k} " in normalized_expanded_msg:
                    return True
                continue

            # For very short keywords, require token exact match.
            if len(k) <= 2:
                if k in expanded_tokens:
                    return True
                continue

            if k in expanded_msg:
                return True

        return False

    greeting_name = user_name if is_logged_in and user_name else "there"

    if not clean_msg:
        response = "Please type your question. I can help with complaints, tracking, profile, and contact details."
        suggestions = ['Submit Complaint', 'My Complaints', 'Track Status', 'Help']

    elif has_any('ok', 'okay', 'okey', 'yes', 'yup', 'sure', 'haan', 'ha', 'hmm'):
        response = (
            "Great 👍\n"
            "What would you like to do next?"
        )
        suggestions = ['Submit Complaint', 'My Complaints', 'Track Status', 'Complaint Analysis']

    elif has_any('hello', 'hi', 'hey', 'namaste', 'namaskar', 'kem cho', 'good morning', 'good evening'):
        response = f"Hello {greeting_name}! 👋\nHow can I help you today?"
        suggestions = ['Submit Complaint', 'My Complaints', 'Track Status', 'Contact SMC']

    elif has_any('resolution time', 'how long', 'how many days', 'days to solve', 'time to resolve', 'time to solve'):
        if is_logged_in:
            resolved_complaints = Complaint.objects.filter(user=user, status='Resolved', resolved_at__isnull=False).order_by('-resolved_at')
            if resolved_complaints.exists():
                total_days = 0
                lines = ["📊 Resolution time for your recently resolved complaints:"]
                for idx, comp in enumerate(resolved_complaints[:5], 1):
                    days = max((comp.resolved_at.date() - comp.complaint_date.date()).days, 0)
                    total_days += days
                    lines.append(f"{idx}. {comp.category} — {days} day(s)")

                avg_days = total_days / min(resolved_complaints.count(), 5)
                lines.append(f"\nAverage (latest): {avg_days:.1f} day(s)")
                response = "\n".join(lines)
            else:
                response = "You don't have any resolved complaints yet, so I can't calculate resolution time right now."
            suggestions = ['My Complaints', 'Complaint Analysis', 'Dashboard']
        else:
            response = "Please login first to check your complaint resolution time."
            suggestions = ['Login', 'Register']

    elif has_any('analysis', 'analytics', 'chart', 'diagram', 'graph', 'report'):
        if is_logged_in:
            complaints = Complaint.objects.filter(user=user)
            total = complaints.count()
            pending = complaints.filter(status='Pending').count()
            progress = complaints.filter(status='In Progress').count()
            resolved = complaints.filter(status='Resolved').count()
            resolved_rate = round((resolved * 100 / total), 2) if total else 0
            response = (
                "📈 Complaint Analysis Summary:\n"
                f"• Total: {total}\n"
                f"• Pending: {pending}\n"
                f"• In Progress: {progress}\n"
                f"• Resolved: {resolved}\n"
                f"• Resolved Rate: {resolved_rate}%\n\n"
                "Open the Complaint Analysis page from Dashboard > Quick Actions to view the diagram."
            )
            suggestions = ['Complaint Analysis', 'My Complaints', 'Dashboard']
        else:
            response = "Please login to view your complaint analysis."
            suggestions = ['Login', 'Register']

    elif (
        has_any('latest complaint', 'recent complaint', 'last complaint')
        or (
            ('latest' in expanded_msg or 'recent' in expanded_msg or 'last' in expanded_msg)
            and 'complaint' in expanded_msg
        )
    ):
        if is_logged_in:
            latest = Complaint.objects.filter(user=user).order_by('-complaint_date').first()
            if latest:
                date_text = timezone.localtime(latest.complaint_date).strftime('%d %b %Y %I:%M %p')
                status_emoji = {'Pending': '⏳', 'In Progress': '🔄', 'Resolved': '✅'}.get(latest.status, '📝')
                response = (
                    f"{status_emoji} Your latest complaint details:\n"
                    f"• ID: #{latest.complaint_id}\n"
                    f"• Category: {latest.category}\n"
                    f"• Status: {latest.status}\n"
                    f"• Submitted: {date_text}"
                )
            else:
                response = "You have not submitted any complaints yet."
            suggestions = ['My Complaints', 'Track Status', 'Complaint Analysis', 'Submit Complaint']
        else:
            response = "Please login to check your latest complaint status."
            suggestions = ['Login', 'Register']

    elif has_any('my complaint', 'show complaint', 'view complaint', 'my issue', 'my status'):
        if is_logged_in:
            complaints = Complaint.objects.filter(user=user).order_by('-complaint_date')
            total = complaints.count()
            pending = complaints.filter(status='Pending').count()
            progress = complaints.filter(status='In Progress').count()
            resolved = complaints.filter(status='Resolved').count()

            if total > 0:
                response_lines = [
                    f"📌 {user_name}, here is your complaint summary:",
                    f"Total: {total} | Pending: {pending} | In Progress: {progress} | Resolved: {resolved}",
                    "",
                    "Recent complaints:"
                ]
                for i, comp in enumerate(complaints[:3], 1):
                    emoji = {'Pending': '⏳', 'In Progress': '🔄', 'Resolved': '✅'}.get(comp.status, '📝')
                    response_lines.append(f"{i}. {emoji} {comp.category} ({comp.status})")
                response = "\n".join(response_lines)
            else:
                response = "You have not submitted any complaints yet. Would you like to create one now?"
            suggestions = ['Submit Complaint', 'Track Status', 'Complaint Analysis', 'Dashboard']
        else:
            response = "Please login to view your complaint details."
            suggestions = ['Login', 'Register']

    elif has_any('chat with officer', 'connect officer', 'talk to officer', 'contact officer', 'speak to officer', 'zone officer'):
        if is_logged_in:
            from .models import CustomUser
            complaint_zones = Complaint.objects.filter(user=user).values_list('zone', flat=True).distinct()
            if complaint_zones:
                officers = CustomUser.objects.filter(role='officer', zone__in=complaint_zones).distinct()
                if officers.exists():
                    lines = ["👔 Officers available for your complaint zones:"]
                    for i, officer in enumerate(officers[:5], 1):
                        name = f"{officer.first_name} {officer.last_name}".strip() or officer.username
                        details = f"{i}. {name} — {officer.zone}"
                        if officer.phone:
                            details += f" | 📞 {officer.phone}"
                        if officer.email:
                            details += f" | 📧 {officer.email}"
                        lines.append(details)
                    response = "\n".join(lines)
                else:
                    response = "No officer is currently mapped to your complaint zones. Please contact support."
            else:
                response = "Submit at least one complaint first, then I can suggest your zone officer details."
            suggestions = ['My Complaints', 'Submit Complaint', 'Contact SMC']
        else:
            response = "Please login to get officer contact details."
            suggestions = ['Login', 'Register']

    elif has_any('charge', 'charges', 'fee', 'fees', 'cost', 'price', 'payment', 'paid') and has_any('submit', 'complaint', 'file', 'report'):
        response = (
            "No, there is no charge for submitting a complaint. ✅\n"
            "Complaint registration on this portal is free for citizens."
        )
        suggestions = ['Submit Complaint', 'Track Status', 'Contact SMC']

    elif has_any('submit', 'file complaint', 'new complaint', 'report issue', 'complain'):
        if is_logged_in:
            response = (
                "To submit a complaint:\n"
                "1. Open Dashboard\n"
                "2. Click Submit Complaint\n"
                "3. Select category, subcategory, and zone\n"
                "4. Add location details and (optional) photo\n"
                "5. Submit"
            )
            suggestions = ['Submit Complaint', 'My Complaints', 'Track Status']
        else:
            response = "Please login first, then you can submit a complaint."
            suggestions = ['Login', 'Register']

    elif ('what' in clean_msg and 'zone' in clean_msg) or has_any('which zone', 'how many zone', 'zones list'):
        response = (
            "Surat is divided into 9 complaint zones:\n"
            "1. West Zone (Rander)\n"
            "2. Central Zone\n"
            "3. North Zone (Katargam)\n"
            "4. East Zone – A (Varachha)\n"
            "5. East Zone – B (Sarthana)\n"
            "6. South Zone – A (Udhna)\n"
            "7. South Zone – B (Kanakpur)\n"
            "8. South West Zone (Athwa)\n"
            "9. South East Zone (Limbayat)"
        )
        suggestions = ['Submit Complaint', 'My Complaints', 'Help']

    elif has_any('category', 'categories', 'type of complaint', 'complaint type'):
        response = (
            "Main complaint categories are:\n"
            "• Water Supply\n"
            "• Drainage & Stormwater\n"
            "• Health & Hospitals\n"
            "• Public Toilets\n"
            "• Food & Hygiene\n"
            "• Streetlights & Roads\n"
            "• Solid Waste\n"
            "• Parks & Gardens\n"
            "• Civic Centers\n"
            "• Miscellaneous"
        )
        suggestions = ['Submit Complaint', 'Track Status', 'Help']

    elif has_any('track', 'check status', 'status of complaint', 'where is my complaint'):
        if is_logged_in:
            response = "Go to Dashboard → My Complaints. You can see Pending, In Progress, and Resolved status there."
            suggestions = ['My Complaints', 'Complaint Analysis', 'Dashboard']
        else:
            response = "Please login to track your complaint status."
            suggestions = ['Login', 'Register']

    elif has_any('photo', 'image', 'picture', 'upload', 'attach', 'proof'):
        response = (
            "You can attach complaint proof images (like JPG/PNG).\n"
            "Adding clear photos helps officers resolve issues faster."
        )
        suggestions = ['Submit Complaint', 'Help']

    elif has_any('edit', 'update complaint', 'modify', 'delete complaint', 'remove complaint'):
        response = (
            "You can edit or delete only Pending complaints.\n"
            "In Progress and Resolved complaints cannot be modified."
        )
        suggestions = ['My Complaints', 'Track Status', 'Dashboard']

    elif has_any('profile', 'account', 'my details', 'update profile'):
        if is_logged_in:
            response = "Go to My Account → My Profile to view or update your details."
            suggestions = ['My Profile', 'Change Password', 'Dashboard']
        else:
            response = "Please login to manage your profile."
            suggestions = ['Login', 'Register']

    elif has_any('password', 'forgot password', 'reset password', 'change password'):
        if any(token in expanded_msg for token in ['forgot', 'reset', 'bhuli', 'bhool', 'forget', 'lost password']):
            response = "Click 'Forgot Password' on the login page and follow the reset link sent to your email."
            suggestions = ['Login', 'Help']
        elif is_logged_in:
            response = "Go to My Account → Change Password to update your password securely."
            suggestions = ['Change Password', 'My Profile']
        else:
            response = "Use 'Forgot Password' from the login page."
            suggestions = ['Login', 'Register']

    elif has_any('register', 'signup', 'create account', 'new account'):
        response = "To create an account, open Register, fill your details, and submit the form."
        suggestions = ['Register', 'Login', 'Help']

    elif has_any('login', 'log in', 'sign in', 'signin'):
        response = "Open Login page and enter your username and password to continue."
        suggestions = ['Login', 'Forgot Password', 'Register']

    elif has_any('contact', 'helpline', 'phone', 'call', 'email', 'office', 'support'):
        response = "📞 Helpline: 1800-XXX-XXXX\n📧 Email: complaints@smc.gov.in\n📍 Address: Muglisara, Surat - 395003"
        suggestions = ['Submit Complaint', 'Track Status', 'Help']

    elif has_any('help', 'assist', 'guide', 'what can you do'):
        response = (
            "I can help you with:\n"
            "• Submit complaint steps\n"
            "• Complaint status and summary\n"
            "• Complaint analysis\n"
            "• Officer/contact details\n"
            "• Account and password guidance"
        )
        suggestions = ['Submit Complaint', 'My Complaints', 'Complaint Analysis', 'Contact SMC']

    elif has_any('thank', 'thanks'):
        response = "You're welcome! 😊"
        suggestions = ['My Complaints', 'Submit Complaint', 'Help']

    elif has_any('bye', 'goodbye', 'see you'):
        response = f"Goodbye {greeting_name}! Have a great day."
        suggestions = []

    else:
        ai_response = _get_ai_chatbot_fallback(raw_msg, user, is_logged_in)
        if ai_response:
            response = ai_response
            suggestions = ['Submit Complaint', 'My Complaints', 'Track Status', 'Help']
        else:
            response = (
                "I did not fully understand that question, but I can still help.\n"
                "Try asking in simple words, for example:\n"
                "• How to submit complaint?\n"
                "• Show my complaints\n"
                "• Track complaint status\n"
                "• Complaint analysis\n"
                "• Contact SMC"
            )
            suggestions = ['Help', 'Submit Complaint', 'My Complaints', 'Contact SMC']

    return {
        'response': response,
        'suggestions': suggestions
    }


# Custom Password Reset Views for Citizens Only
class CitizenPasswordResetView(PasswordResetView):
    """Password reset view restricted to Citizen users only"""
    template_name = 'registration/password_reset_form.html'
    form_class = CitizenPasswordResetForm
    subject_template_name = 'registration/password_reset_subject.txt'
    email_template_name = 'registration/password_reset_email.html'
    success_url = reverse_lazy('password_reset_done')

    def form_valid(self, form):
        email = form.cleaned_data['email']
        matching_users = CustomUser.objects.filter(email__iexact=email, is_active=True)
        citizen_users = matching_users.filter(role='user')
        officer_users = matching_users.filter(role='officer')
        admin_users = matching_users.filter(role='administrator')

        if not matching_users.exists():
            # No matching users found - send helpful email with URLs
            self.send_helpful_email(email)
            messages.info(self.request, 'If this email address is registered with us, you will receive password reset instructions. Please also check your spam folder.')
            return redirect(self.success_url)

        # Send role-specific reset links for officer and admin accounts.
        for user in officer_users:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            _send_officer_password_reset_email(self.request, user, uid, token)

        for user in admin_users:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            _send_admin_password_reset_email(self.request, user, uid, token)

        if not citizen_users.exists():
            messages.info(self.request, 'Password reset instructions have been sent to your email address. Please check your inbox/spam folder.')
            return redirect(self.success_url)

        # Call parent form_valid to send reset emails
        try:
            response = super().form_valid(form)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Password reset email sending failed for {email}: {str(e)}")
            messages.error(self.request, 'We could not send reset email right now. Please try again after some time.')
            return redirect('password_reset')
        
        # Log password reset emails for each matching user
        reset_subject = 'Password Reset Request - Civic Zone Solution'
        reset_message = f"Password reset link has been sent to {email}"
        for user in citizen_users:
            try:
                _log_password_reset_notification(
                    user,
                    reset_message,
                    reason='user_password_reset',
                    status='sent'
                )
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to log password reset notification for user {user.username}: {str(e)}")
        
        return response

    def send_helpful_email(self, email):
        """Send an email with helpful URLs when email is not found"""
        login_url = self.request.build_absolute_uri(reverse('login'))
        password_reset_url = self.request.build_absolute_uri(reverse('password_reset'))

        subject = 'Civic Zone Solution - Password Reset Information'
        message = (
            f"Hello,\n\n"
            f"We received a password reset request for the email address: {email}\n\n"
            f"If you have an account with Civic Zone Solution, you can reset your password here:\n"
            f"{password_reset_url}\n\n"
            f"If you need to login to your account, use this link:\n"
            f"{login_url}\n\n"
            f"If you did not request this password reset, please ignore this email.\n\n"
            f"If you're having trouble accessing your account, please contact our support team.\n\n"
            f"Regards,\n"
            f"Civic Zone Solution Team"
        )

        try:
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False)
            # Try to log notification for tracking (email might not be registered)
            try:
                Notification.objects.create(
                    username='unknown',
                    email=email,
                    complaint_id=None,
                    message=f"Helpful password reset email sent to {email}",
                    notification_type='email',
                    status='sent',
                    reason='user_password_reset_info',
                    sent_at=timezone.now(),
                )
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to log helpful email notification: {str(e)}")
        except Exception as e:
            print(f"Helpful email sending failed: {str(e)}")  # Debug logging

    def get_users(self, email):
        """Override to only return Citizen users"""
        active_users = CustomUser.objects.filter(
            email__iexact=email,
            is_active=True,
            role='user'  # Only Citizen users
        )
        return active_users


class CitizenPasswordResetDoneView(PasswordResetDoneView):
    """Password reset done view"""
    template_name = 'registration/password_reset_done.html'


class CitizenPasswordResetConfirmView(PasswordResetConfirmView):
    """Password reset confirm view"""
    template_name = 'registration/password_reset_confirm.html'
    success_url = reverse_lazy('password_reset_complete')

    def get_user(self, uidb64):
        """Override to ensure only Citizen users can reset password"""
        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = CustomUser.objects.get(pk=uid)
            if user.role != 'user':
                raise ValidationError('Invalid user type')
            return user
        except (TypeError, ValueError, OverflowError, CustomUser.DoesNotExist, ValidationError):
            return None

    def form_valid(self, form):
        """Log notification when password is successfully reset"""
        response = super().form_valid(form)
        
        # Log password reset confirmation
        user = form.save()
        try:
            _log_password_reset_notification(
                user,
                "Your password has been successfully reset.",
                reason='user_password_reset_completed',
                status='sent'
            )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to log password reset completion for user {user.username}: {str(e)}")
        
        return response


class CitizenPasswordResetCompleteView(PasswordResetCompleteView):
    """Password reset complete view"""
    template_name = 'registration/password_reset_complete.html'


def forgot_password(request):
    """Redirect to citizen password reset"""
    return redirect('password_reset')
