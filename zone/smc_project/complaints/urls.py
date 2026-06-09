from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('analysis/', views.complaint_analysis, name='complaint_analysis'),
    path('submit/', views.submit_complaint, name='submit_complaint'),
    path('submit/check-duplicate/', views.check_duplicate_realtime, name='check_duplicate_realtime'),
    path('detail/<int:complaint_id>/', views.complaint_detail, name='complaint_detail'),
    path('edit/<int:complaint_id>/', views.edit_complaint, name='edit_complaint'),
    path('delete/<int:complaint_id>/', views.delete_complaint, name='delete_complaint'),
    path('admin/', views.admin_panel, name='admin_panel'),
    path('admin/heatmap/', views.complaint_heatmap, name='complaint_heatmap'),
    path('admin/update-status/', views.update_complaint_status, name='update_complaint_status'),
    path('admin/generate-pdf/', views.generate_pdf_report, name='generate_pdf_report'),

    # User Management URLs (Super Admin Only)
    path('admin/users/', views.user_management, name='user_management'),
    path('admin/users/my-zone/', views.officer_zone_users, name='officer_zone_users'),
    path('admin/users/<int:user_id>/', views.view_user_profile, name='view_user_profile'),
    path('admin/users/<int:user_id>/edit/', views.edit_user_profile, name='edit_user_profile'),
    path('admin/users/<int:user_id>/delete/', views.delete_user, name='delete_user'),
    
    # Report Generation URLs
    path('admin/reports/monthly/', views.monthly_report, name='monthly_report'),
    path('admin/reports/zone/', views.zone_report, name='zone_report'),
    path('admin/reports/officer-performance/', views.officer_performance_report, name='officer_performance_report'),
    
    # Feedback URL
    path('feedback/', views.feedback, name='feedback'),
]