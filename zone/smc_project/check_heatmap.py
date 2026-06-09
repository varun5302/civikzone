#!/usr/bin/env python
"""
Test script to check complaint heatmap data
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smc_project.settings')
django.setup()

from complaints.models import Complaint

def check_heatmap_data():
    print("=== Complaint Heatmap Data Check ===")

    # Total complaints
    total = Complaint.objects.count()
    print(f"Total complaints: {total}")

    # Complaints with location data
    with_location = Complaint.objects.exclude(latitude__isnull=True).exclude(longitude__isnull=True).count()
    print(f"Complaints with location: {with_location}")

    # Sample complaints with location
    sample_complaints = Complaint.objects.exclude(latitude__isnull=True).exclude(longitude__isnull=True)[:5]

    print("\nSample complaints with location data:")
    for complaint in sample_complaints:
        print(f"ID: {complaint.complaint_id}, Lat: {complaint.latitude}, Lng: {complaint.longitude}, Location: {complaint.location[:50]}...")

    # Check if we have enough data for heatmap
    if with_location == 0:
        print("\n⚠️  WARNING: No complaints with location data found!")
        print("The heatmap will show an empty map.")
        print("\nTo add sample data, run:")
        print("python manage.py shell")
        print("Then execute the create_sample_complaints() function from this script.")
    else:
        print(f"\n✅ Found {with_location} complaints with location data - heatmap should work!")

if __name__ == "__main__":
    check_heatmap_data()