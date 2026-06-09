# Generated manually on 2026-04-04

from django.db import migrations, models


PROFILE_FIELDS = [
    'first_name', 'last_name', 'email', 'phone', 'address', 'profile_picture',
    'date_of_birth', 'gender', 'aadhar_number', 'pan_number', 'alternate_phone',
    'emergency_contact', 'emergency_contact_name', 'pincode', 'city', 'state', 'landmark'
]


def backfill_profile_snapshots(apps, schema_editor):
    CustomUser = apps.get_model('accounts', 'CustomUser')
    Officer = apps.get_model('accounts', 'Officer')
    SuperAdmin = apps.get_model('accounts', 'SuperAdmin')

    users_map = {
        user.id: user
        for user in CustomUser.objects.all()
    }

    for officer in Officer.objects.all():
        user = users_map.get(officer.user_id)
        if not user:
            continue

        for field in PROFILE_FIELDS:
            setattr(officer, field, getattr(user, field, None))
        officer.save(update_fields=PROFILE_FIELDS)

    for superadmin in SuperAdmin.objects.all():
        user = users_map.get(superadmin.user_id)
        if not user:
            continue

        for field in PROFILE_FIELDS:
            setattr(superadmin, field, getattr(user, field, None))
        superadmin.save(update_fields=PROFILE_FIELDS)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0011_alter_customuser_email_superadmin_officer'),
    ]

    operations = [
        migrations.AddField(
            model_name='officer',
            name='aadhar_number',
            field=models.CharField(blank=True, max_length=12, null=True, verbose_name='Aadhar Number'),
        ),
        migrations.AddField(
            model_name='officer',
            name='address',
            field=models.TextField(blank=True, null=True, verbose_name='Full Address'),
        ),
        migrations.AddField(
            model_name='officer',
            name='alternate_phone',
            field=models.CharField(blank=True, max_length=15, null=True, verbose_name='Alternate Phone'),
        ),
        migrations.AddField(
            model_name='officer',
            name='city',
            field=models.CharField(blank=True, default='Surat', max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='officer',
            name='date_of_birth',
            field=models.DateField(blank=True, null=True, verbose_name='Date of Birth'),
        ),
        migrations.AddField(
            model_name='officer',
            name='email',
            field=models.EmailField(blank=True, max_length=254, null=True),
        ),
        migrations.AddField(
            model_name='officer',
            name='emergency_contact',
            field=models.CharField(blank=True, max_length=15, null=True, verbose_name='Emergency Contact'),
        ),
        migrations.AddField(
            model_name='officer',
            name='emergency_contact_name',
            field=models.CharField(blank=True, max_length=100, null=True, verbose_name='Emergency Contact Name'),
        ),
        migrations.AddField(
            model_name='officer',
            name='first_name',
            field=models.CharField(blank=True, max_length=150, null=True),
        ),
        migrations.AddField(
            model_name='officer',
            name='gender',
            field=models.CharField(blank=True, choices=[('male', 'Male'), ('female', 'Female'), ('other', 'Other'), ('prefer_not_to_say', 'Prefer not to say')], max_length=20, null=True),
        ),
        migrations.AddField(
            model_name='officer',
            name='landmark',
            field=models.CharField(blank=True, max_length=200, null=True, verbose_name='Landmark'),
        ),
        migrations.AddField(
            model_name='officer',
            name='last_name',
            field=models.CharField(blank=True, max_length=150, null=True),
        ),
        migrations.AddField(
            model_name='officer',
            name='pan_number',
            field=models.CharField(blank=True, max_length=10, null=True, verbose_name='PAN Number'),
        ),
        migrations.AddField(
            model_name='officer',
            name='phone',
            field=models.CharField(blank=True, max_length=15, null=True, verbose_name='Phone Number'),
        ),
        migrations.AddField(
            model_name='officer',
            name='pincode',
            field=models.CharField(blank=True, max_length=6, null=True, verbose_name='Pincode'),
        ),
        migrations.AddField(
            model_name='officer',
            name='profile_picture',
            field=models.ImageField(blank=True, null=True, upload_to='profile_pics/', verbose_name='Profile Picture'),
        ),
        migrations.AddField(
            model_name='officer',
            name='state',
            field=models.CharField(blank=True, default='Gujarat', max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='superadmin',
            name='aadhar_number',
            field=models.CharField(blank=True, max_length=12, null=True, verbose_name='Aadhar Number'),
        ),
        migrations.AddField(
            model_name='superadmin',
            name='address',
            field=models.TextField(blank=True, null=True, verbose_name='Full Address'),
        ),
        migrations.AddField(
            model_name='superadmin',
            name='alternate_phone',
            field=models.CharField(blank=True, max_length=15, null=True, verbose_name='Alternate Phone'),
        ),
        migrations.AddField(
            model_name='superadmin',
            name='city',
            field=models.CharField(blank=True, default='Surat', max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='superadmin',
            name='date_of_birth',
            field=models.DateField(blank=True, null=True, verbose_name='Date of Birth'),
        ),
        migrations.AddField(
            model_name='superadmin',
            name='email',
            field=models.EmailField(blank=True, max_length=254, null=True),
        ),
        migrations.AddField(
            model_name='superadmin',
            name='emergency_contact',
            field=models.CharField(blank=True, max_length=15, null=True, verbose_name='Emergency Contact'),
        ),
        migrations.AddField(
            model_name='superadmin',
            name='emergency_contact_name',
            field=models.CharField(blank=True, max_length=100, null=True, verbose_name='Emergency Contact Name'),
        ),
        migrations.AddField(
            model_name='superadmin',
            name='first_name',
            field=models.CharField(blank=True, max_length=150, null=True),
        ),
        migrations.AddField(
            model_name='superadmin',
            name='gender',
            field=models.CharField(blank=True, choices=[('male', 'Male'), ('female', 'Female'), ('other', 'Other'), ('prefer_not_to_say', 'Prefer not to say')], max_length=20, null=True),
        ),
        migrations.AddField(
            model_name='superadmin',
            name='landmark',
            field=models.CharField(blank=True, max_length=200, null=True, verbose_name='Landmark'),
        ),
        migrations.AddField(
            model_name='superadmin',
            name='last_name',
            field=models.CharField(blank=True, max_length=150, null=True),
        ),
        migrations.AddField(
            model_name='superadmin',
            name='pan_number',
            field=models.CharField(blank=True, max_length=10, null=True, verbose_name='PAN Number'),
        ),
        migrations.AddField(
            model_name='superadmin',
            name='phone',
            field=models.CharField(blank=True, max_length=15, null=True, verbose_name='Phone Number'),
        ),
        migrations.AddField(
            model_name='superadmin',
            name='pincode',
            field=models.CharField(blank=True, max_length=6, null=True, verbose_name='Pincode'),
        ),
        migrations.AddField(
            model_name='superadmin',
            name='profile_picture',
            field=models.ImageField(blank=True, null=True, upload_to='profile_pics/', verbose_name='Profile Picture'),
        ),
        migrations.AddField(
            model_name='superadmin',
            name='state',
            field=models.CharField(blank=True, default='Gujarat', max_length=100, null=True),
        ),
        migrations.RunPython(backfill_profile_snapshots, migrations.RunPython.noop),
    ]
