from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.signals import user_logged_in
from django.contrib import messages
from django.contrib.messages import get_messages

from .models import CustomUser


@receiver(post_save, sender=CustomUser)
def sync_role_profile_snapshots(sender, instance, **kwargs):
    """Keep role tables in sync with latest CustomUser profile details."""
    officer_profile = getattr(instance, 'officer_profile', None)
    if officer_profile:
        officer_profile.save()

    superadmin_profile = getattr(instance, 'superadmin_profile', None)
    if superadmin_profile:
        superadmin_profile.save()


@receiver(user_logged_in)
def fix_login_message_to_show_username(sender, request, user, **kwargs):
    """Suppress allauth login banner to avoid repeated success alerts."""
    # Get all messages from storage
    storage = get_messages(request)
    message_list = list(storage)
    
    # Clear all messages
    storage.used = True
    
    # Re-add messages, replacing the login message
    for msg in message_list:
        msg_text = str(msg)
        if "Successfully signed in as" in msg_text:
            # Drop allauth sign-in message entirely.
            continue
        else:
            # Keep other messages as is
            messages.add_message(request, msg.level, msg_text)

