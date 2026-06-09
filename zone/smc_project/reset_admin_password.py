#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smc_project.settings')
django.setup()

from accounts.models import CustomUser

# Reset password for administrator account
admin = CustomUser.objects.get(username='administrator')
admin.set_password('admin123')  # Set new password
admin.save()

print("\n" + "="*60)
print("✅ Admin Password Reset Successfully!")
print("="*60)
print(f"\nUsername: administrator")
print(f"New Password: admin123")
print("\nYou can now login at: /accounts/admin_login/")
print("="*60 + "\n")
