from django.db import models
from django.conf import settings
from django.utils import timezone
from django.db.models import Count, Max


CANONICAL_ZONE_CHOICES = [
    ('West Zone (Rander)', 'West Zone (Rander)'),
    ('Central Zone', 'Central Zone'),
    ('North Zone (Katargam)', 'North Zone (Katargam)'),
    ('East Zone – A(Varachha)', 'East Zone – A(Varachha)'),
    ('East Zone – B(Sarthana)', 'East Zone – B(Sarthana)'),
    ('South Zone – A (Udhna)', 'South Zone – A (Udhna)'),
    ('South Zone – B (Kanakpur)', 'South Zone – B (Kanakpur)'),
    ('South West Zone (Athwa)', 'South West Zone (Athwa)'),
    ('South East Zone (Limbayat)', 'South East Zone (Limbayat)'),
]


def _normalize_zone_name(zone_value):
    if not zone_value:
        return ''
    return ' '.join(str(zone_value).strip().split())


def _canonical_zone_name(zone_value):
    normalized_value = _normalize_zone_name(zone_value)
    if not normalized_value:
        return ''

    for zone_name, _label in CANONICAL_ZONE_CHOICES:
        if _normalize_zone_name(zone_name).lower() == normalized_value.lower():
            return zone_name

    return normalized_value


def _sync_zone_department_stats(zones=None):
    from accounts.models import Officer

    if zones:
        target_zones = {_canonical_zone_name(zone) for zone in zones if zone}
        target_zones.discard('')
    else:
        target_zones = {zone for zone, _ in CANONICAL_ZONE_CHOICES}

    complaint_stats = {}
    complaint_qs = Complaint.objects.values('zone').annotate(
        total=Count('complaint_id'),
        last_submitted=Max('complaint_date'),
    )
    if zones:
        complaint_qs = complaint_qs.filter(zone__in=target_zones)

    for row in complaint_qs:
        canonical_zone = _canonical_zone_name(row.get('zone'))
        if not canonical_zone:
            continue

        row_total = int(row.get('total') or 0)
        row_last = row.get('last_submitted')
        existing = complaint_stats.get(canonical_zone)
        if not existing:
            complaint_stats[canonical_zone] = {
                'total': row_total,
                'last_submitted': row_last,
            }
            continue

        existing['total'] += row_total
        if row_last and (existing['last_submitted'] is None or row_last > existing['last_submitted']):
            existing['last_submitted'] = row_last

    officer_counts = {}
    officer_qs = Officer.objects.values('zone').annotate(total=Count('id'))
    if zones:
        officer_qs = officer_qs.filter(zone__in=target_zones)
    for row in officer_qs:
        canonical_zone = _canonical_zone_name(row.get('zone'))
        if not canonical_zone:
            continue
        officer_counts[canonical_zone] = officer_counts.get(canonical_zone, 0) + int(row.get('total') or 0)

    for zone_name in target_zones:
        zone_complaints = complaint_stats.get(zone_name, {}).get('total', 0)
        last_submitted = complaint_stats.get(zone_name, {}).get('last_submitted')
        zone_officers = officer_counts.get(zone_name, 0)

        zone_row, created = ZoneDepartment.objects.get_or_create(
            zone_name=zone_name,
            defaults={
                'zone_officers': zone_officers,
                'zone_complaints': zone_complaints,
                'last_complaint_submitted_at': last_submitted,
            }
        )

        if created:
            continue

        if (
            zone_row.zone_officers != zone_officers or
            zone_row.zone_complaints != zone_complaints or
            zone_row.last_complaint_submitted_at != last_submitted
        ):
            zone_row.zone_officers = zone_officers
            zone_row.zone_complaints = zone_complaints
            zone_row.last_complaint_submitted_at = last_submitted
            zone_row.save(update_fields=['zone_officers', 'zone_complaints', 'last_complaint_submitted_at'])

    if not zones:
        ZoneDepartment.objects.exclude(zone_name__in=[zone for zone, _ in CANONICAL_ZONE_CHOICES]).delete()

class Complaint(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('In Progress', 'In Progress'),
        ('Resolved', 'Resolved'),
    ]

    CATEGORY_CHOICES = [
        ('1. Water Supply', '1. Water Supply'),
        ('2. Drainage & Stormwater', '2. Drainage & Stormwater'),
        ('3. Health & Hospitals/Dispensaries', '3. Health & Hospitals/Dispensaries'),
        ('4. Public Toilets', '4. Public Toilets'),
        ('5. Food & Hygiene', '5. Food & Hygiene'),
        ('6. Streetlights, Roads, and Footpaths', '6. Streetlights, Roads, and Footpaths'),
        ('7. Solid Waste Management', '7. Solid Waste Management'),
        ('8. Parks & Gardens', '8. Parks & Gardens'),
        ('9. Civic Centers & Administrative Services', '9. Civic Centers & Administrative Services'),
        ('10. Miscellaneous', '10. Miscellaneous'),
        ('Other', 'Other'),
    ]

    ZONE_CHOICES = CANONICAL_ZONE_CHOICES

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='complaints'
    )
    complaint_id = models.AutoField(primary_key=True)
    category = models.CharField(max_length=100, choices=CATEGORY_CHOICES)
    other_category = models.CharField(max_length=100, blank=True, null=True)
    subcategory = models.CharField(max_length=200)
    other_subcategory = models.CharField(max_length=200, blank=True, null=True)
    zone = models.CharField(max_length=100, choices=ZONE_CHOICES)
    location = models.TextField()
    address = models.TextField(blank=True, null=True, help_text="Full address details (optional)")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    description = models.TextField()
    phone = models.CharField(max_length=15)
    proof_image = models.ImageField(upload_to='complaints/', blank=True, null=True)
    complaint_date = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)  # Auto-updates on every save
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    admin_remarks = models.TextField(blank=True, null=True)
    resolved_at = models.DateTimeField(blank=True, null=True)  # Set when status becomes Resolved
    is_duplicate = models.BooleanField(default=False)
    original_complaint = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='duplicate_complaints'
    )
    similarity_score = models.FloatField(null=True, blank=True)

    def __str__(self):
        return f"Complaint #{self.complaint_id} - {self.get_category_display()}"

    class Meta:
        ordering = ['-complaint_date']
        db_table = 'complaints'
        verbose_name = 'Complaint'
        verbose_name_plural = 'Complaints'

    def save(self, *args, **kwargs):
        self.zone = _canonical_zone_name(self.zone)
        old_zone = None
        if self.pk:
            old_zone = Complaint.objects.filter(pk=self.pk).values_list('zone', flat=True).first()

        super().save(*args, **kwargs)

        zones_to_sync = [self.zone]
        if old_zone:
            zones_to_sync.append(old_zone)
        _sync_zone_department_stats(zones=zones_to_sync)

    def delete(self, *args, **kwargs):
        deleted_zone = self.zone
        super().delete(*args, **kwargs)
        if deleted_zone:
            _sync_zone_department_stats(zones=[deleted_zone])


class ZoneDepartment(models.Model):
    zone_name = models.CharField(max_length=100, unique=True)
    zone_officers = models.PositiveIntegerField(default=0)
    zone_complaints = models.PositiveIntegerField(default=0)
    last_complaint_submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'zone_departments'
        ordering = ['zone_name']
        verbose_name = 'Zone Department'
        verbose_name_plural = 'Zone Departments'

    def __str__(self):
        return f"{self.zone_name} (Officers: {self.zone_officers}, Complaints: {self.zone_complaints})"


class ComplaintStatusTimeline(models.Model):
    STAGE_CHOICES = [
        ('Submitted', 'Submitted'),
        ('In Review', 'In Review'),
        ('Assigned', 'Assigned'),
        ('Resolved', 'Resolved'),
    ]

    complaint = models.ForeignKey(
        Complaint,
        on_delete=models.CASCADE,
        related_name='timeline_events'
    )
    stage = models.CharField(max_length=20, choices=STAGE_CHOICES)
    timestamp = models.DateTimeField(default=timezone.now)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='complaint_timeline_events'
    )
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = 'complaint_status_timeline'
        ordering = ['timestamp', 'id']
        unique_together = ('complaint', 'stage')
        verbose_name = 'Complaint Timeline Event'
        verbose_name_plural = 'Complaint Timeline Events'

    def __str__(self):
        return f"#{self.complaint_id} - {self.stage}"


class Feedback(models.Model):
    RATING_CHOICES = [
        (1, '1 Star - Very Poor'),
        (2, '2 Stars - Poor'),
        (3, '3 Stars - Average'),
        (4, '4 Stars - Good'),
        (5, '5 Stars - Excellent'),
    ]
    
    RESPONSE_TIME_CHOICES = [
        ('very_poor', 'Very Poor'),
        ('poor', 'Poor'),
        ('average', 'Average'),
        ('good', 'Good'),
        ('excellent', 'Excellent'),
    ]
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='feedbacks'
    )
    feedback_id = models.AutoField(primary_key=True)
    fullname = models.CharField(max_length=200)
    email = models.EmailField()
    mobile = models.CharField(max_length=15)
    overall_rating = models.IntegerField(choices=RATING_CHOICES)
    response_time_satisfaction = models.CharField(max_length=20, choices=RESPONSE_TIME_CHOICES)
    reference_email = models.EmailField(blank=True, null=True)
    feedback = models.TextField()
    submitted_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Feedback #{self.feedback_id} - {self.fullname} ({self.overall_rating} stars)"
    
    class Meta:
        ordering = ['-submitted_at']
        db_table = 'feedback'
        verbose_name = 'Feedback'
        verbose_name_plural = 'Feedbacks'


class Notification(models.Model):
    TYPE_CHOICES = [
        ('sms', 'SMS'),
        ('email', 'Email'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
    ]

    notification_id = models.AutoField(primary_key=True)
    username = models.CharField(max_length=150, db_index=True, default='unknown')
    email = models.EmailField(blank=True, null=True, verbose_name='Recipient Email')
    complaint_id = models.IntegerField(null=True, blank=True, db_index=True)
    message = models.TextField()
    notification_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default='email')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='sent')
    sent_at = models.DateTimeField(default=timezone.now, db_index=True)
    reason = models.CharField(max_length=100, blank=True, null=True, verbose_name='Notification Reason', help_text='e.g., password_reset, complaint_update, etc.')

    class Meta:
        db_table = 'notifications'
        ordering = ['-sent_at', '-notification_id']
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'

    def __str__(self):
        return f"{self.notification_type.upper()} to {self.username}"


class AuditLog(models.Model):
    ACTION_CHOICES = [
        ('complaint_created', 'Complaint Created'),
        ('complaint_updated', 'Complaint Updated'),
        ('complaint_deleted', 'Complaint Deleted'),
        ('status_changed', 'Status Changed'),
        ('user_updated', 'User Updated'),
        ('user_deleted', 'User Deleted'),
    ]

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='audit_actions',
    )
    actor_username = models.CharField(max_length=150, blank=True, default='')
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    entity_type = models.CharField(max_length=30)
    entity_id = models.CharField(max_length=64)
    complaint = models.ForeignKey(
        Complaint,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='audit_logs',
    )
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='audit_targets',
    )
    change_data = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'audit_logs'
        ordering = ['-created_at', '-id']
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError('AuditLog entries are immutable and cannot be modified.')
        if not self.actor_username and self.actor_id:
            self.actor_username = getattr(self.actor, 'username', '') or ''
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError('AuditLog entries are immutable and cannot be deleted.')

    def __str__(self):
        return f"{self.action} | {self.entity_type}:{self.entity_id}"
