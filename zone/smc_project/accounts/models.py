from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
import re

class CustomUser(AbstractUser):
    BASE_PROFILE_REQUIRED_FIELDS = [
        'first_name', 'last_name', 'email', 'phone',
        'date_of_birth', 'gender',
        'address', 'landmark', 'city', 'state', 'pincode',
        'aadhar_number', 'pan_number',
        'alternate_phone', 'emergency_contact', 'emergency_contact_name',
    ]

    STAFF_PROFILE_REQUIRED_FIELDS = ['department', 'employee_id']

    ROLE_CHOICES = [
        ('user', 'User'),
        ('officer', 'Officer'),
        ('administrator', 'Administrator'),
    ]
    
    GENDER_CHOICES = [
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other'),
        ('prefer_not_to_say', 'Prefer not to say'),
    ]
    
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='user')
    phone = models.CharField(max_length=15, blank=True, null=True, verbose_name='Phone Number')
    address = models.TextField(blank=True, null=True, verbose_name='Full Address')
    
    # New profile fields
    profile_picture = models.ImageField(upload_to='profile_pics/', blank=True, null=True, verbose_name='Profile Picture')
    date_of_birth = models.DateField(blank=True, null=True, verbose_name='Date of Birth')
    gender = models.CharField(max_length=20, choices=GENDER_CHOICES, blank=True, null=True)
    aadhar_number = models.CharField(max_length=12, blank=True, null=True, unique=True, verbose_name='Aadhar Number')
    pan_number = models.CharField(max_length=10, blank=True, null=True, unique=True, verbose_name='PAN Number')
    
    # Additional contact info
    alternate_phone = models.CharField(max_length=15, blank=True, null=True, verbose_name='Alternate Phone')
    emergency_contact = models.CharField(max_length=15, blank=True, null=True, verbose_name='Emergency Contact')
    emergency_contact_name = models.CharField(max_length=100, blank=True, null=True, verbose_name='Emergency Contact Name')
    
    # Location info
    pincode = models.CharField(max_length=6, blank=True, null=True, verbose_name='Pincode')
    city = models.CharField(max_length=100, blank=True, null=True, default='Surat')
    state = models.CharField(max_length=100, blank=True, null=True, default='Gujarat')
    landmark = models.CharField(max_length=200, blank=True, null=True, verbose_name='Landmark')
    
    # For officers
    department = models.CharField(max_length=100, blank=True, null=True)
    employee_id = models.CharField(max_length=50, blank=True, null=True, unique=True, verbose_name='Employee ID')
    
    # Profile verification
    is_profile_complete = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(blank=True, null=True)   
    
    # AI features
    enable_gpt_codex = models.BooleanField(default=True, verbose_name='Enable GPT-5.2-Codex')
    verification_documents = models.FileField(upload_to='verification_docs/', blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_profile_update = models.DateTimeField(blank=True, null=True)
    
    def __str__(self):
        return self.username
    
    def get_full_address(self):
        """Get formatted full address"""
        address_parts = []
        if self.address:
            address_parts.append(self.address)
        if self.landmark:
            address_parts.append(f"Landmark: {self.landmark}")
        if self.city:
            address_parts.append(self.city)
        if self.state:
            address_parts.append(self.state)
        if self.pincode:
            address_parts.append(f"Pincode: {self.pincode}")
        return ", ".join(address_parts)
    
    def get_age(self):
        """Calculate age from date of birth"""
        if self.date_of_birth:
            from datetime import date
            today = date.today()
            return today.year - self.date_of_birth.year - (
                (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
            )
        return None
    
    def clean(self):
        """Custom validation"""
        # Validate Aadhar number (12 digits)
        if self.aadhar_number and not re.match(r'^\d{12}$', self.aadhar_number):
            raise ValidationError({
                'aadhar_number': _('Aadhar number must be 12 digits')
            })
        
        # Validate PAN number (10 alphanumeric characters)
        if self.pan_number and not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]{1}$', self.pan_number):
            raise ValidationError({
                'pan_number': _('PAN number must be 10 characters (5 letters, 4 digits, 1 letter)')
            })
        
        # Validate phone number
        if self.phone and not re.match(r'^\d{10}$', self.phone):
            raise ValidationError({
                'phone': _('Phone number must be 10 digits')
            })
        
        # Validate pincode
        if self.pincode and not re.match(r'^\d{6}$', self.pincode):
            raise ValidationError({
                'pincode': _('Pincode must be 6 digits')
            })
    
    def check_profile_completion(self):
        """Check if profile is complete"""
        stats = self.get_profile_completion_stats()
        self.is_profile_complete = stats['completion_percentage'] >= 100
        return self.is_profile_complete

    def get_assigned_zone(self):
        """Return assigned zone from role-specific profile tables."""
        if self.role == 'officer':
            officer = getattr(self, 'officer_profile', None)
            return officer.zone if officer else None
        if self.role == 'administrator':
            superadmin = getattr(self, 'superadmin_profile', None)
            return superadmin.zone if superadmin else None
        return None

    @property
    def zone(self):
        return self.get_assigned_zone()

    @staticmethod
    def _is_field_filled(value):
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        return True

    def get_profile_required_fields(self):
        required_fields = list(self.BASE_PROFILE_REQUIRED_FIELDS)
        if self.role in ['officer', 'administrator']:
            required_fields.extend(self.STAFF_PROFILE_REQUIRED_FIELDS)
        return required_fields

    def get_profile_completion_stats(self):
        required_fields = self.get_profile_required_fields()
        total_fields = len(required_fields)
        completed_fields = sum(
            1 for field in required_fields if self._is_field_filled(getattr(self, field, None))
        )
        completion_percentage = (completed_fields / total_fields) * 100 if total_fields else 0
        return {
            'completed_fields': completed_fields,
            'total_fields': total_fields,
            'completion_percentage': completion_percentage,
        }

    @property
    def profile_completion_percentage(self):
        return round(self.get_profile_completion_stats()['completion_percentage'])
    
    class Meta:
        verbose_name = _('User')
        verbose_name_plural = _('Users')
        ordering = ['-date_joined']


class ProfileSnapshotMixin(models.Model):
    """Store a snapshot of linked CustomUser profile data in role-specific tables."""

    first_name = models.CharField(max_length=150, blank=True, null=True)
    last_name = models.CharField(max_length=150, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=15, blank=True, null=True, verbose_name='Phone Number')
    address = models.TextField(blank=True, null=True, verbose_name='Full Address')
    profile_picture = models.ImageField(upload_to='profile_pics/', blank=True, null=True, verbose_name='Profile Picture')
    date_of_birth = models.DateField(blank=True, null=True, verbose_name='Date of Birth')
    gender = models.CharField(max_length=20, choices=CustomUser.GENDER_CHOICES, blank=True, null=True)
    aadhar_number = models.CharField(max_length=12, blank=True, null=True, verbose_name='Aadhar Number')
    pan_number = models.CharField(max_length=10, blank=True, null=True, verbose_name='PAN Number')
    alternate_phone = models.CharField(max_length=15, blank=True, null=True, verbose_name='Alternate Phone')
    emergency_contact = models.CharField(max_length=15, blank=True, null=True, verbose_name='Emergency Contact')
    emergency_contact_name = models.CharField(max_length=100, blank=True, null=True, verbose_name='Emergency Contact Name')
    pincode = models.CharField(max_length=6, blank=True, null=True, verbose_name='Pincode')
    city = models.CharField(max_length=100, blank=True, null=True, default='Surat')
    state = models.CharField(max_length=100, blank=True, null=True, default='Gujarat')
    landmark = models.CharField(max_length=200, blank=True, null=True, verbose_name='Landmark')

    PROFILE_SNAPSHOT_FIELDS = [
        'first_name', 'last_name', 'email', 'phone', 'address', 'profile_picture',
        'date_of_birth', 'gender', 'aadhar_number', 'pan_number', 'alternate_phone',
        'emergency_contact', 'emergency_contact_name', 'pincode', 'city', 'state', 'landmark'
    ]

    class Meta:
        abstract = True

    def sync_profile_from_user(self):
        """Copy profile data from linked CustomUser to this table."""
        if not getattr(self, 'user_id', None):
            return

        for field_name in self.PROFILE_SNAPSHOT_FIELDS:
            setattr(self, field_name, getattr(self.user, field_name, None))


class SuperAdmin(ProfileSnapshotMixin):
    """SuperAdmin model for administrative users with elevated privileges"""
    
    PERMISSION_LEVEL_CHOICES = [
        ('full', 'Full Access'),
        ('restricted', 'Restricted Access'),
    ]
    
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='superadmin_profile')
    permission_level = models.CharField(max_length=20, choices=PERMISSION_LEVEL_CHOICES, default='full')
    
    # Administrative info
    can_manage_officers = models.BooleanField(default=True)
    can_manage_users = models.BooleanField(default=True)
    can_manage_complaints = models.BooleanField(default=True)
    can_view_reports = models.BooleanField(default=True)
    can_manage_system_settings = models.BooleanField(default=True)
    can_modify_other_admins = models.BooleanField(default=False)
    
    # Super admin specific fields
    admin_code = models.CharField(max_length=50, unique=True, verbose_name='Admin Code')
    department = models.CharField(max_length=100, blank=True, null=True)
    zone = models.CharField(max_length=100, blank=True, null=True)
    
    # Activity tracking
    is_active = models.BooleanField(default=True)
    last_login = models.DateTimeField(blank=True, null=True)
    last_activity = models.DateTimeField(blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"SuperAdmin: {self.user.get_full_name() or self.user.username}"

    def save(self, *args, **kwargs):
        self.sync_profile_from_user()
        super().save(*args, **kwargs)
    
    class Meta:
        verbose_name = _('SuperAdmin')
        verbose_name_plural = _('SuperAdmins')
        ordering = ['-created_at']


class Officer(ProfileSnapshotMixin):
    """Officer model for municipal/administrative officers"""
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('on_leave', 'On Leave'),
        ('suspended', 'Suspended'),
    ]
    
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='officer_profile')
    
    # Officer details
    officer_id = models.CharField(max_length=50, unique=True, verbose_name='Officer ID')
    designation = models.CharField(max_length=100, verbose_name='Designation')
    department = models.CharField(max_length=100, verbose_name='Department')
    zone = models.CharField(max_length=100, verbose_name='Zone')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    
    # Contact and assignment
    office_phone = models.CharField(max_length=15, blank=True, null=True, verbose_name='Office Phone')
    office_address = models.TextField(blank=True, null=True, verbose_name='Office Address')
    assigned_areas = models.TextField(blank=True, null=True, help_text='Comma-separated list of assigned areas/zones')
    
    # Permissions specific to officers
    can_view_complaints = models.BooleanField(default=True)
    can_update_complaint_status = models.BooleanField(default=True)
    can_add_feedback = models.BooleanField(default=True)
    can_generate_reports = models.BooleanField(default=True)
    can_export_data = models.BooleanField(default=False)
    
    # Verification and approval
    is_verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(SuperAdmin, on_delete=models.SET_NULL, null=True, blank=True, related_name='verified_officers')
    verified_at = models.DateTimeField(blank=True, null=True)
    
    # Activity tracking
    complaints_handled = models.IntegerField(default=0, verbose_name='Total Complaints Handled')
    is_active = models.BooleanField(default=True)
    last_login = models.DateTimeField(blank=True, null=True)
    last_activity = models.DateTimeField(blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Officer: {self.user.get_full_name() or self.user.username} ({self.designation})"

    def save(self, *args, **kwargs):
        self.sync_profile_from_user()
        super().save(*args, **kwargs)
    
    class Meta:
        verbose_name = _('Officer')
        verbose_name_plural = _('Officers')
        ordering = ['-created_at']
        unique_together = [['officer_id', 'department']]
