from django.core.management.base import BaseCommand
from django.utils import timezone
from accounts.models import CustomUser, Officer, SuperAdmin
import uuid


class Command(BaseCommand):
    help = 'Migrate existing officer and administrator users to new Officer and SuperAdmin tables'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting migration of users to new tables...'))
        
        # Migrate Officers
        officers_migrated = self._migrate_officers()
        
        # Migrate SuperAdmins (Administrators)
        admins_migrated = self._migrate_superadmins()
        
        self.stdout.write(
            self.style.SUCCESS(
                f'\n✓ Migration completed!\n'
                f'  - Officers migrated: {officers_migrated}\n'
                f'  - SuperAdmins migrated: {admins_migrated}'
            )
        )
    
    def _migrate_officers(self):
        """Migrate users with role='officer' to Officer table"""
        officers = CustomUser.objects.filter(role='officer')
        migrated_count = 0
        synced_count = 0
        
        self.stdout.write(f'\nMigrating {officers.count()} officers...')
        
        for user in officers:
            # Check if officer profile already exists
            existing_officer = Officer.objects.filter(user=user).first()
            if existing_officer:
                existing_officer.save()
                self.stdout.write(self.style.WARNING(f'  ↺ Officer profile synced for {user.username}'))
                synced_count += 1
                continue
            
            try:
                # Generate unique officer_id
                officer_id = f"OFF-{user.id}-{uuid.uuid4().hex[:6].upper()}"
                
                # Create Officer record
                officer = Officer.objects.create(
                    user=user,
                    officer_id=officer_id,
                    designation=user.employee_id or f"Officer",
                    department=user.department or "General",
                    zone=user.zone or "N/A",
                    office_phone=user.phone or "",
                    office_address=user.address or "",
                    status='active' if user.is_active else 'inactive',
                    is_active=user.is_active,
                    is_verified=user.is_verified,
                    verified_at=user.verified_at,
                    can_view_complaints=True,
                    can_update_complaint_status=True,
                    can_add_feedback=True,
                    can_generate_reports=True,
                )
                
                self.stdout.write(self.style.SUCCESS(f'  ✓ Migrated officer: {user.username} (ID: {officer_id})'))
                migrated_count += 1
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  ✗ Error migrating {user.username}: {str(e)}'))

        self.stdout.write(self.style.SUCCESS(f'  - Officer profiles synced: {synced_count}'))
        
        return migrated_count
    
    def _migrate_superadmins(self):
        """Migrate users with role='administrator' to SuperAdmin table"""
        admins = CustomUser.objects.filter(role='administrator')
        migrated_count = 0
        synced_count = 0
        
        self.stdout.write(f'\nMigrating {admins.count()} superadmins...')
        
        for user in admins:
            # Check if superadmin profile already exists
            existing_superadmin = SuperAdmin.objects.filter(user=user).first()
            if existing_superadmin:
                existing_superadmin.save()
                self.stdout.write(self.style.WARNING(f'  ↺ SuperAdmin profile synced for {user.username}'))
                synced_count += 1
                continue
            
            try:
                # Generate unique admin_code
                admin_code = f"ADM-{user.id}-{uuid.uuid4().hex[:6].upper()}"
                
                # Create SuperAdmin record
                superadmin = SuperAdmin.objects.create(
                    user=user,
                    admin_code=admin_code,
                    permission_level='full',
                    department=user.department or "Admin",
                    zone=user.zone or "All",
                    can_manage_officers=True,
                    can_manage_users=True,
                    can_manage_complaints=True,
                    can_view_reports=True,
                    can_manage_system_settings=True,
                    can_modify_other_admins=False,
                    is_active=user.is_active,
                    last_login=user.last_login,
                )
                
                self.stdout.write(self.style.SUCCESS(f'  ✓ Migrated superadmin: {user.username} (Code: {admin_code})'))
                migrated_count += 1
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  ✗ Error migrating {user.username}: {str(e)}'))

        self.stdout.write(self.style.SUCCESS(f'  - SuperAdmin profiles synced: {synced_count}'))
        
        return migrated_count
