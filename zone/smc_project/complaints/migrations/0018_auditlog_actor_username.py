from django.db import migrations, models


def backfill_actor_username(apps, schema_editor):
    AuditLog = apps.get_model('complaints', 'AuditLog')

    for log in AuditLog.objects.filter(actor__isnull=False, actor_username='').select_related('actor'):
        log.actor_username = getattr(log.actor, 'username', '') or ''
        log.save(update_fields=['actor_username'])


class Migration(migrations.Migration):

    dependencies = [
        ('complaints', '0017_notification_email_notification_reason_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='auditlog',
            name='actor_username',
            field=models.CharField(blank=True, default='', max_length=150),
        ),
        migrations.RunPython(backfill_actor_username, migrations.RunPython.noop),
    ]
