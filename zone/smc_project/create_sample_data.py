#!/usr/bin/env python
"""
Script to create sample complaints with location data for heatmap testing
"""
import os
import sys
import django
from decimal import Decimal

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smc_project.settings')
django.setup()

from complaints.models import Complaint
from accounts.models import CustomUser
from django.utils import timezone

def create_sample_complaints():
    print("=== Creating Sample Complaints for Heatmap Testing ===")

    # Sample locations around Surat, Gujarat (approximate coordinates)
    sample_locations = [
        # Central Surat
        {"lat": 21.1702, "lng": 72.8311, "location": "Varachha Road, Surat", "zone": "East Zone – A(Varachha)"},
        {"lat": 21.1959, "lng": 72.8203, "location": "Ring Road, Surat", "zone": "Central Zone"},
        {"lat": 21.1850, "lng": 72.8080, "location": "Athwa Lines, Surat", "zone": "South West Zone (Athwa)"},
        {"lat": 21.2000, "lng": 72.8400, "location": "Adajan, Surat", "zone": "East Zone – B(Sarthana)"},
        {"lat": 21.1600, "lng": 72.7800, "location": "Vesu, Surat", "zone": "South Zone – A (Udhna)"},
        {"lat": 21.1800, "lng": 72.8500, "location": "Piplod, Surat", "zone": "East Zone – A(Varachha)"},
        {"lat": 21.1900, "lng": 72.8000, "location": "Nanpura, Surat", "zone": "Central Zone"},
        {"lat": 21.1750, "lng": 72.8250, "location": "Ghod Dod Road, Surat", "zone": "Central Zone"},
        {"lat": 21.1650, "lng": 72.8350, "location": "City Light, Surat", "zone": "East Zone – A(Varachha)"},
        {"lat": 21.1950, "lng": 72.8150, "location": "Majura Gate, Surat", "zone": "Central Zone"},
        # North Zone
        {"lat": 21.2200, "lng": 72.8200, "location": "Katargam, Surat", "zone": "North Zone (Katargam)"},
        {"lat": 21.2100, "lng": 72.8300, "location": "Dindoli, Surat", "zone": "North Zone (Katargam)"},
        # South Zone
        {"lat": 21.1400, "lng": 72.7800, "location": "Udhna, Surat", "zone": "South Zone – A (Udhna)"},
        {"lat": 21.1300, "lng": 72.7900, "location": "Sachin, Surat", "zone": "South Zone – B (Kanakpur)"},
        # West Zone
        {"lat": 21.1800, "lng": 72.7700, "location": "Rander, Surat", "zone": "West Zone (Rander)"},
    ]

    # Get or create a test user
    try:
        test_user = CustomUser.objects.filter(role='user').first()
        if not test_user:
            test_user = CustomUser.objects.create_user(
                username='testuser',
                email='test@example.com',
                password='testpass123',
                first_name='Test',
                last_name='User',
                role='user'
            )
            print("Created test user: testuser")
    except Exception as e:
        print(f"Error creating/getting user: {e}")
        return

    # Create sample complaints
    categories = ['1. Water Supply', '2. Drainage & Stormwater', '6. Streetlights, Roads, and Footpaths', '7. Solid Waste Management']
    statuses = ['Pending', 'In Progress', 'Resolved']

    created_count = 0
    for i, location_data in enumerate(sample_locations):
        try:
            complaint = Complaint.objects.create(
                user=test_user,
                category=categories[i % len(categories)],
                subcategory='Test Subcategory',
                zone=location_data['zone'],
                location=location_data['location'],
                latitude=Decimal(str(location_data['lat'])),
                longitude=Decimal(str(location_data['lng'])),
                description=f'Sample complaint #{i+1} at {location_data["location"]} for heatmap testing',
                phone='9876543210',
                status=statuses[i % len(statuses)],
                complaint_date=timezone.now()
            )
            created_count += 1
            print(f"Created complaint #{complaint.complaint_id} at {location_data['location']}")
        except Exception as e:
            print(f"Error creating complaint {i+1}: {e}")

    print(f"\n✅ Successfully created {created_count} sample complaints with location data!")
    print("You can now view the heatmap at: /admin/heatmap/")

if __name__ == "__main__":
    create_sample_complaints()