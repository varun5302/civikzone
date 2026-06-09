from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('login/', views.user_login, name='login'),
    path('register/', views.user_register, name='register'),
     path('register/verify-otp/', views.verify_signup_otp, name='verify_signup_otp'),
     path('register/resend-otp/', views.resend_signup_otp, name='resend_signup_otp'),
    path('login/confirmation-pending/', views.login_confirmation_pending, name='login_confirmation_pending'),
    path('confirm-login/<str:token>/', views.confirm_user_login, name='confirm_user_login'),
    path('forgot-password/', views.forgot_password, name='forgot_password'),
    path('admin/login/', views.admin_login, name='admin_login'),
    path('admin/login/verify-otp/', views.admin_login_verify_otp, name='admin_login_verify_otp'),
    path('admin/login/resend-otp/', views.admin_resend_otp, name='admin_resend_otp'),
    path('admin/login/confirmation-pending/', views.admin_login_confirmation_pending, name='admin_login_confirmation_pending'),
     path('admin/login/status/', views.admin_login_status, name='admin_login_status'),
    path('admin/confirm-login/<str:token>/', views.confirm_admin_login, name='confirm_admin_login'),
    path('admin/forgot-password/', views.admin_forgot_password, name='admin_forgot_password'),
    path('admin/reset-password/', views.admin_reset_password, name='admin_reset_password'),
     path('admin/reset-password/<uidb64>/<token>/', views.admin_reset_password_confirm, name='admin_reset_password_confirm'),
    path('officer/forgot-password/', views.officer_forgot_password, name='officer_forgot_password'),
    path('officer/reset-password/<uidb64>/<token>/', views.officer_reset_password_confirm, name='officer_reset_password_confirm'),
    path('logout/', views.user_logout, name='logout'),
    path('google/start/', views.google_login_start, name='google_login_start'),

    # Profile URLs
    path('profile/', views.user_profile, name='user_profile'),
    path('officer/profile/', views.officer_profile, name='officer_profile'),
    path('profile/picture/', views.update_profile_picture, name='update_profile_picture'),
     path('profile/picture/delete/', views.delete_profile_picture, name='delete_profile_picture'),
    path('profile/change-password/', views.change_password, name='change_password'),
    path('profile/request-change-password/', views.request_change_password, name='request_change_password'),
     path('profile/change-password/<str:token>/', views.profile_change_password_confirm, name='profile_change_password_confirm'),
    path('profile/delete-account/', views.delete_account, name='delete_account'),

    # Password reset for Citizens (email-based)
    path('password-reset/',
         views.CitizenPasswordResetView.as_view(),
         name='password_reset'),
    path('password-reset/done/',
         views.CitizenPasswordResetDoneView.as_view(),
         name='password_reset_done'),
    path('password-reset-confirm/<uidb64>/<token>/',
         views.CitizenPasswordResetConfirmView.as_view(),
         name='password_reset_confirm'),
    path('password-reset-complete/',
         views.CitizenPasswordResetCompleteView.as_view(),
         name='password_reset_complete'),
    
    # Chatbot
    path('chatbot/', views.chatbot_response, name='chatbot_response'),
     path('chat-history/', views.chat_history_page, name='chat_history_page'),
]