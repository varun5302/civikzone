from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0015_remove_customuser_zone'),
    ]

    operations = [
        migrations.CreateModel(
            name='FooterContentSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('terms_content', models.TextField(blank=True, default='')),
                ('support_content', models.TextField(blank=True, default='')),
                ('terms_last_updated', models.DateTimeField(default=django.utils.timezone.now)),
                ('support_last_updated', models.DateTimeField(default=django.utils.timezone.now)),
            ],
            options={
                'verbose_name': 'Footer Content Settings',
                'verbose_name_plural': 'Footer Content Settings',
            },
        ),
    ]
