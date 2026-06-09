from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('complaints', '0008_complaintstatustimeline'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AuditLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(choices=[('complaint_created', 'Complaint Created'), ('complaint_updated', 'Complaint Updated'), ('complaint_deleted', 'Complaint Deleted'), ('status_changed', 'Status Changed'), ('user_updated', 'User Updated'), ('user_deleted', 'User Deleted')], max_length=50)),
                ('entity_type', models.CharField(max_length=30)),
                ('entity_id', models.CharField(max_length=64)),
                ('change_data', models.JSONField(blank=True, default=dict)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('actor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='audit_actions', to=settings.AUTH_USER_MODEL)),
                ('complaint', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='audit_logs', to='complaints.complaint')),
                ('target_user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='audit_targets', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Audit Log',
                'verbose_name_plural': 'Audit Logs',
                'db_table': 'audit_logs',
                'ordering': ['-created_at', '-id'],
            },
        ),
    ]
