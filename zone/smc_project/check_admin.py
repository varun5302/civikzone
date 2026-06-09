#!/usr/bin/env python
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smc_project.settings')
django.setup()

from accounts.models import CustomUser

# Find all administrators
admins = CustomUser.objects.filter(role='administrator')
print(f"\n{'='*60}")
print(f"Total Administrators: {admins.count()}")
print(f"{'='*60}\n")

if admins.count() > 0:
    for admin in admins:
        print(f"Username: {admin.username}")
        print(f"Email: {admin.email}")
        print(f"Full Name: {admin.get_full_name()}")
        print(f"Is Active: {admin.is_active}")
        print("-" * 60)
else:
    print("❌ No administrator found in the system.")
    print("\nYou need to create a superuser. Run:")
    print("   python manage.py createsuperuser")
    print("\n" + "="*60)
