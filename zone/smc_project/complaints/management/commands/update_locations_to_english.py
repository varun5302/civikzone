from django.core.management.base import BaseCommand
from complaints.models import Complaint
import requests
import time


class Command(BaseCommand):
    help = 'Update all complaint locations from Gujarati to English using coordinates'

    def handle(self, *args, **kwargs):
        # Get all complaints with coordinates
        complaints = Complaint.objects.filter(
            latitude__isnull=False,
            longitude__isnull=False
        )
        
        total = complaints.count()
        self.stdout.write(f"Found {total} complaints with coordinates")
        
        updated = 0
        failed = 0
        skipped = 0
        
        for i, complaint in enumerate(complaints, 1):
            try:
                lat = float(complaint.latitude)
                lng = float(complaint.longitude)
                
                self.stdout.write(f"[{i}/{total}] Processing complaint #{complaint.complaint_id}...", ending='')
                
                # Call Nominatim API with English language
                url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lng}&accept-language=en"
                
                response = requests.get(url, headers={
                    'User-Agent': 'SMC-Complaint-System/1.0'
                })
                
                if response.status_code == 200:
                    data = response.json()
                    new_location = data.get('display_name', '')
                    
                    if new_location:
                        old_location = complaint.location
                        complaint.location = new_location
                        complaint.save(update_fields=['location'])
                        
                        self.stdout.write(self.style.SUCCESS(' ✓ Updated'))
                        self.stdout.write(f"  Old: {old_location[:80]}...")
                        self.stdout.write(f"  New: {new_location[:80]}...")
                        updated += 1
                    else:
                        self.stdout.write(self.style.WARNING(' ⚠ No address returned'))
                        skipped += 1
                else:
                    self.stdout.write(self.style.ERROR(f' ✗ API error {response.status_code}'))
                    failed += 1
                
                # Respect Nominatim usage policy: max 1 request per second
                time.sleep(1)
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f' ✗ Error: {str(e)}'))
                failed += 1
        
        # Show summary
        self.stdout.write("\n" + "="*50)
        self.stdout.write(self.style.SUCCESS(f"✓ Successfully updated: {updated}"))
        if skipped > 0:
            self.stdout.write(self.style.WARNING(f"⚠ Skipped: {skipped}"))
        if failed > 0:
            self.stdout.write(self.style.ERROR(f"✗ Failed: {failed}"))
        self.stdout.write("="*50)
