from django.contrib import admin
from .models import Complaint, Feedback, AuditLog, Notification, ZoneDepartment
from django.urls import path
from django.shortcuts import redirect
from django.contrib import messages

@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = ('complaint_id', 'user', 'category', 'zone', 'location', 'address', 'status', 'complaint_date', 'updated_at', 'resolved_at')
    list_filter = ('status', 'category', 'complaint_date')
    search_fields = ('complaint_id', 'user__username', 'description')
    readonly_fields = ('complaint_id', 'complaint_date')
    ordering = ('-complaint_date',)

    fieldsets = (
        ('Complaint Details', {
            'fields': ('complaint_id', 'user', 'category', 'subcategory', 'zone', 'location', 'address', 'latitude', 'longitude', 'description', 'phone', 'proof_image', 'complaint_date', 'updated_at')
        }),
        ('Status and Resolution', {
            'fields': ('status', 'admin_remarks', 'resolved_at')
        }),
    )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('heatmap/', self.admin_site.admin_view(self.complaint_heatmap_view), name='complaint_heatmap'),
        ]
        return custom_urls + urls

    def complaint_heatmap_view(self, request):
        """Redirect to the main heatmap view"""
        return redirect('complaint_heatmap')


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = (
        'feedback_id',
        'fullname',
        'email',
        'mobile',
        'overall_rating',
        'response_time_satisfaction',
        'reference_email',
        'feedback',
        'submitted_at',
        'user_id_display',
    )
    list_filter = ('overall_rating', 'response_time_satisfaction', 'submitted_at')
    search_fields = ('feedback_id', 'user__username', 'fullname', 'email', 'mobile', 'reference_email', 'feedback')
    readonly_fields = ('feedback_id', 'submitted_at')
    ordering = ('-submitted_at',)

    fieldsets = (
        ('User Information', {
            'fields': ('feedback_id', 'user', 'fullname', 'email', 'mobile')
        }),
        ('Ratings', {
            'fields': ('overall_rating', 'response_time_satisfaction')
        }),
        ('Feedback Details', {
            'fields': ('feedback', 'reference_email', 'submitted_at')
        }),
    )

    def user_id_display(self, obj):
        return obj.user_id
    user_id_display.short_description = 'user_id'


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'created_at', 'action', 'actor_username_display', 'entity_type', 'entity_id', 'complaint', 'target_username_display')
    list_filter = ('action', 'entity_type', 'created_at')
    search_fields = ('entity_id', 'actor_username', 'actor__username', 'target_user__username', 'complaint__complaint_id')
    readonly_fields = (
        'actor', 'actor_username', 'action', 'entity_type', 'entity_id',
        'complaint', 'target_user', 'change_data', 'metadata', 'created_at'
    )
    ordering = ('-created_at', '-id')

    @staticmethod
    def _user_display_name(user_obj):
        if not user_obj:
            return ''
        full_name = user_obj.get_full_name()
        if full_name and full_name.strip():
            return full_name.strip()
        return user_obj.username

    def actor_username_display(self, obj):
        actor_name = self._user_display_name(obj.actor)
        return actor_name or obj.actor_username or '-'
    actor_username_display.short_description = 'actor'

    def target_username_display(self, obj):
        return self._user_display_name(obj.target_user) or '-'
    target_username_display.short_description = 'target user'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('notification_id', 'username', 'email', 'complaint_id', 'reason', 'notification_type', 'status', 'sent_at')
    list_filter = ('notification_type', 'status', 'reason', 'sent_at')
    search_fields = ('username', 'email', 'complaint_id', 'message', 'reason')
    readonly_fields = ('notification_id', 'sent_at')
    ordering = ('-sent_at', '-notification_id')


@admin.register(ZoneDepartment)
class ZoneDepartmentAdmin(admin.ModelAdmin):
    list_display = ('zone_name', 'zone_officers', 'zone_complaints', 'last_complaint_submitted_at')
    list_filter = ('zone_name',)
    search_fields = ('zone_name',)
    readonly_fields = ('last_complaint_submitted_at',)
    ordering = ('zone_name',)
