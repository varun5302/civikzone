#!/usr/bin/env python
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smc_project.settings')
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
django.setup()

from django.core.mail import send_mail
from django.conf import settings

print("🔧 Testing Email Functionality")
print("=" * 50)
print(f"Email Backend: {settings.EMAIL_BACKEND}")
print(f"Default From Email: {settings.DEFAULT_FROM_EMAIL}")
print()

print("📧 Testing Password Change Email...")
try:
    subject = 'Change Your Password - Civic Zone Solution'
    message = (
        "Hello Test User,\n\n"
        "You have requested to change your password.\n\n"
        "Click the link below to change your password:\n"
        "http://127.0.0.1:8000/accounts/profile/change-password/\n\n"
        "This link will take you to the password change page where you can set a new password.\n\n"
        "If you need to login first, use this link:\n"
        "http://127.0.0.1:8000/accounts/login/\n\n"
        "If you did not request this change, please ignore this email.\n\n"
        "Regards,\n"
        "Civic Zone Solution Team"
    )

    result = send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        ['test@example.com'],
        fail_silently=False,
    )
    print("✅ Email sent successfully!")
    print("📋 Email content should appear above this message.")
    print()
    print("💡 Note: Since you're using console backend, emails are printed to console instead of being sent.")
    print("   In production, configure real SMTP settings in settings.py")

except Exception as e:
    print(f"❌ Email failed: {str(e)}")
    print()
    print("🔧 Troubleshooting:")
    print("1. Check if EMAIL_BACKEND is set correctly in settings.py")
    print("2. For production, add real SMTP credentials")
    print("3. Make sure Django server is running")



    