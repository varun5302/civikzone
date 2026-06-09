from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from .models import CustomUser, SuperAdmin, Officer

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    # List display - what shows in the main list view
    list_display = (
        'username', 'email', 'get_full_name', 'role',
        'phone', 'is_active', 'profile_completion_percentage',
        'date_joined', 'last_login'
    )

    # List filters - sidebar filters
    list_filter = (
        'role', 'department', 'gender', 'is_staff',
        'is_active', 'is_superuser', 'date_joined', 'last_login'
    )

    # Search fields - searchable columns
    search_fields = (
        'username', 'email', 'first_name', 'last_name',
        'phone', 'aadhar_number', 'address', 'city', 'state'
    )

    # Ordering - default sort order
    ordering = ('-date_joined', 'username')

    # Read-only fields
    readonly_fields = (
        'date_joined', 'last_login', 'profile_completion_percentage',
        'last_profile_update', 'profile_picture_preview'
    )

    # Fieldsets for the detail view
    fieldsets = (
        ('Basic Information', {
            'fields': (
                'username', 'password', 'email', 'first_name', 'last_name',
                'date_of_birth', 'gender', 'phone'
            )
        }),
        ('Address Information', {
            'fields': ('address', 'city', 'state', 'pincode'),
            'classes': ('collapse',)
        }),
        ('Identification & Role', {
            'fields': ('aadhar_number', 'role', 'department'),
            'classes': ('collapse',)
        }),
        ('Profile & Media', {
            'fields': ('profile_picture', 'profile_picture_preview'),
            'classes': ('collapse',)
        }),
        ('Permissions', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
            'classes': ('collapse',)
        }),
        ('Important Dates', {
            'fields': ('date_joined', 'last_login', 'last_profile_update'),
            'classes': ('collapse',)
        }),
        ('Profile Analytics', {
            'fields': ('profile_completion_percentage',),
            'classes': ('collapse',)
        }),
    )

    # Fieldsets for adding new users
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'password1', 'password2'),
        }),
        ('Personal Information', {
            'classes': ('wide',),
            'fields': ('first_name', 'last_name', 'date_of_birth', 'gender', 'phone'),
        }),
        ('Address', {
            'classes': ('wide',),
            'fields': ('address', 'city', 'state', 'pincode'),
        }),
        ('Role Assignment', {
            'classes': ('wide',),
            'fields': ('role', 'department', 'aadhar_number'),
        }),
        ('Permissions', {
            'classes': ('wide',),
            'fields': ('is_active', 'is_staff', 'is_superuser'),
        }),
    )

    # Custom methods for list display
    def profile_picture_preview(self, obj):
        """Display profile picture preview in admin"""
        if obj.profile_picture:
            return format_html(
                '<img src="{}" style="width: 50px; height: 50px; border-radius: 50%; object-fit: cover;" />',
                obj.profile_picture.url
            )
        return "No picture"
    profile_picture_preview.short_description = "Profile Picture"

    # Custom display methods
    def get_full_name(self, obj):
        """Display full name in list view"""
        return obj.get_full_name() or "N/A"
    get_full_name.short_description = "Full Name"

    def profile_completion_percentage(self, obj):
        """Calculate and display profile completion percentage"""
        required_fields = [
            'username', 'email', 'first_name', 'last_name', 'phone',
            'address', 'city', 'state', 'pincode', 'aadhar_number'
        ]
        filled_fields = sum(1 for field in required_fields if getattr(obj, field))
        percentage = round((filled_fields / len(required_fields)) * 100)
        return f"{percentage}%"
    profile_completion_percentage.short_description = "Profile Completion"

    # Actions
    actions = ['activate_users', 'deactivate_users', 'reset_passwords']

    def get_queryset(self, request):
        """Show only citizen users in CustomUser admin list."""
        queryset = super().get_queryset(request)
        return queryset.filter(role='user')

    def activate_users(self, request, queryset):
        """Activate selected users"""
        updated = queryset.update(is_active=True)
        self.message_user(request, f'{updated} users have been activated.')
    activate_users.short_description = "Activate selected users"

    def deactivate_users(self, request, queryset):
        """Deactivate selected users"""
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} users have been deactivated.')
    deactivate_users.short_description = "Deactivate selected users"

    def reset_passwords(self, request, queryset):
        """Reset passwords for selected users (set to default)"""
        from django.contrib.auth.hashers import make_password
        default_password = 'changeme123'  # You should change this
        updated = 0
        for user in queryset:
            user.password = make_password(default_password)
            user.save()
            updated += 1
        self.message_user(request, f'Passwords reset for {updated} users. Default password: {default_password}')
    reset_passwords.short_description = "Reset passwords for selected users"

    # Custom CSS and JS for admin
    class Media:
        css = {
            'all': ('css/admin_custom.css',)
        }
        js = ('js/admin_custom.js',)


@admin.register(SuperAdmin)
class SuperAdminAdmin(admin.ModelAdmin):
    """Admin interface for SuperAdmin users"""
    
    list_display = (
        'username_display', 'email_display', 'get_full_name', 'admin_code', 'permission_level', 'department', 
        'zone', 'is_active', 'last_activity', 'created_at'
    )
    list_display_links = ('username_display',)
    
    list_filter = (
        'permission_level', 'department', 'zone', 'is_active', 'created_at'
    )
    
    search_fields = (
        'user__username', 'user__email', 'user__first_name', 
        'user__last_name', 'admin_code', 'department'
    )
    
    ordering = ('-created_at',)
    
    readonly_fields = (
        'username_display', 'created_at', 'updated_at', 'last_activity', 'user_link',
        'first_name', 'last_name', 'email', 'phone', 'profile_picture_preview',
        'date_of_birth', 'gender', 'aadhar_number', 'pan_number', 'alternate_phone',
        'emergency_contact', 'emergency_contact_name', 'address', 'landmark',
        'city', 'state', 'pincode'
    )
    
    fieldsets = (
        ('User Information', {
            'fields': ('user', 'username_display', 'user_link')
        }),
        ('Admin Details', {
            'fields': ('admin_code', 'permission_level', 'department', 'zone')
        }),
        ('Profile Data (User Structure)', {
            'fields': (
                'profile_picture_preview', 'first_name', 'last_name', 'email', 'phone',
                'date_of_birth', 'gender', 'aadhar_number', 'pan_number', 'alternate_phone',
                'emergency_contact', 'emergency_contact_name', 'address', 'landmark',
                'city', 'state', 'pincode'
            ),
            'classes': ('collapse',)
        }),
        ('Permissions', {
            'fields': (
                'can_manage_officers', 'can_manage_users', 'can_manage_complaints',
                'can_view_reports', 'can_manage_system_settings', 'can_modify_other_admins'
            )
        }),
        ('Activity', {
            'fields': ('is_active', 'last_login', 'last_activity')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_full_name(self, obj):
        """Display full name from linked user"""
        return obj.user.get_full_name() or obj.user.username
    get_full_name.short_description = "Full Name"

    def username_display(self, obj):
        return obj.user.username
    username_display.short_description = "Username"

    def email_display(self, obj):
        return obj.email or obj.user.email or "N/A"
    email_display.short_description = "Email"

    def profile_picture_preview(self, obj):
        if obj.profile_picture:
            return format_html(
                '<img src="{}" style="width: 50px; height: 50px; border-radius: 50%; object-fit: cover;" />',
                obj.profile_picture.url
            )
        return "No picture"
    profile_picture_preview.short_description = "Profile Picture"
    
    def user_link(self, obj):
        """Display link to user"""
        from django.urls import reverse
        url = reverse('admin:accounts_customuser_change', args=[obj.user.id])
        return format_html('<a href="{}">{}</a>', url, obj.user.username)
    user_link.short_description = "User"


@admin.register(Officer)
class OfficerAdmin(admin.ModelAdmin):
    """Admin interface for Officer users"""
    
    list_display = (
        'username_display', 'email_display', 'get_full_name', 'officer_id', 'designation', 'department', 
        'zone', 'status', 'is_verified', 'complaints_handled', 'is_active'
    )
    list_display_links = ('username_display',)
    
    list_filter = (
        'status', 'department', 'zone', 'is_verified', 'is_active', 
        'can_update_complaint_status', 'created_at'
    )
    
    search_fields = (
        'user__username', 'user__email', 'user__first_name',
        'user__last_name', 'officer_id', 'designation', 'department', 'zone'
    )
    
    ordering = ('-created_at',)
    
    readonly_fields = (
        'username_display', 'created_at', 'updated_at', 'last_activity', 'user_link', 'verified_info',
        'first_name', 'last_name', 'email', 'phone', 'profile_picture_preview',
        'date_of_birth', 'gender', 'aadhar_number', 'pan_number', 'alternate_phone',
        'emergency_contact', 'emergency_contact_name', 'address', 'landmark',
        'city', 'state', 'pincode'
    )
    
    fieldsets = (
        ('User Information', {
            'fields': ('user', 'username_display', 'user_link')
        }),
        ('Officer Details', {
            'fields': ('officer_id', 'designation', 'department', 'zone', 'status')
        }),
        ('Profile Data (User Structure)', {
            'fields': (
                'profile_picture_preview', 'first_name', 'last_name', 'email', 'phone',
                'date_of_birth', 'gender', 'aadhar_number', 'pan_number', 'alternate_phone',
                'emergency_contact', 'emergency_contact_name', 'address', 'landmark',
                'city', 'state', 'pincode'
            ),
            'classes': ('collapse',)
        }),
        ('Contact Information', {
            'fields': ('office_phone', 'office_address', 'assigned_areas')
        }),
        ('Permissions', {
            'fields': (
                'can_view_complaints', 'can_update_complaint_status',
                'can_add_feedback', 'can_generate_reports', 'can_export_data'
            )
        }),
        ('Verification', {
            'fields': ('is_verified', 'verified_by', 'verified_info', 'verified_at'),
            'classes': ('collapse',)
        }),
        ('Activity', {
            'fields': ('is_active', 'complaints_handled', 'last_login', 'last_activity')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['mark_as_active', 'mark_as_inactive', 'verify_officers', 'suspend_officers']
    
    def get_full_name(self, obj):
        """Display full name from linked user"""
        return obj.user.get_full_name() or obj.user.username
    get_full_name.short_description = "Full Name"

    def username_display(self, obj):
        return obj.user.username
    username_display.short_description = "Username"

    def email_display(self, obj):
        return obj.email or obj.user.email or "N/A"
    email_display.short_description = "Email"

    def profile_picture_preview(self, obj):
        if obj.profile_picture:
            return format_html(
                '<img src="{}" style="width: 50px; height: 50px; border-radius: 50%; object-fit: cover;" />',
                obj.profile_picture.url
            )
        return "No picture"
    profile_picture_preview.short_description = "Profile Picture"
    
    def user_link(self, obj):
        """Display link to user"""
        from django.urls import reverse
        url = reverse('admin:accounts_customuser_change', args=[obj.user.id])
        return format_html('<a href="{}">{}</a>', url, obj.user.username)
    user_link.short_description = "User"
    
    def verified_info(self, obj):
        """Display verification information"""
        if obj.is_verified:
            verified_by_name = obj.verified_by.user.get_full_name() if obj.verified_by else "System"
            return format_html(
                '<span style="color: green;">✓ Verified by {} on {}</span>',
                verified_by_name,
                obj.verified_at.strftime('%Y-%m-%d %H:%M') if obj.verified_at else 'N/A'
            )
        else:
            return format_html('<span style="color: red;">✗ Not Verified</span>')
    verified_info.short_description = "Verification Status"
    
    def mark_as_active(self, request, queryset):
        """Mark selected officers as active"""
        updated = queryset.update(is_active=True, status='active')
        self.message_user(request, f'{updated} officers have been marked as active.')
    mark_as_active.short_description = "Mark selected officers as active"
    
    def mark_as_inactive(self, request, queryset):
        """Mark selected officers as inactive"""
        updated = queryset.update(is_active=False, status='inactive')
        self.message_user(request, f'{updated} officers have been marked as inactive.')
    mark_as_inactive.short_description = "Mark selected officers as inactive"
    
    def verify_officers(self, request, queryset):
        """Verify selected officers"""
        from django.utils import timezone
        # Get the superadmin profile for the current user
        try:
            superadmin = request.user.superadmin_profile
            updated = queryset.update(
                is_verified=True, 
                verified_by=superadmin, 
                verified_at=timezone.now()
            )
            self.message_user(request, f'{updated} officers have been verified.')
        except:
            self.message_user(request, 'Only SuperAdmins can verify officers.', level='error')
    verify_officers.short_description = "Verify selected officers"
    
    def suspend_officers(self, request, queryset):
        """Suspend selected officers"""
        updated = queryset.update(is_active=False, status='suspended')
        self.message_user(request, f'{updated} officers have been suspended.')
    suspend_officers.short_description = "Suspend selected officers"
