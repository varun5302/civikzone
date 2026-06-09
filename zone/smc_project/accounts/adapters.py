from django.contrib import messages
from django.shortcuts import redirect

from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.adapter import DefaultAccountAdapter

from .models import CustomUser


class CustomAccountAdapter(DefaultAccountAdapter):
    """Customize allauth account behavior to show username instead of email in login message."""

    def add_message(self, request, level, message_template, *args, **kwargs):
        """Suppress allauth's post-login success banner entirely."""
        template_name = str(message_template or '')
        text_message = str(kwargs.get('message') or '')

        if 'logged_in' in template_name or 'Successfully signed in as' in text_message:
            return

        return super().add_message(request, level, message_template, *args, **kwargs)
    
    def get_login_redirect_url(self, request):
        """Override to use username in success message"""
        path = super().get_login_redirect_url(request)
        return path


class GoogleSocialAccountAdapter(DefaultSocialAccountAdapter):
    """Link Google sign-ins to existing citizen accounts when the email already exists."""

    def pre_social_login(self, request, sociallogin):
        if sociallogin.is_existing:
            return

        email = (sociallogin.user.email or '').strip().lower()
        if not email:
            return

        existing_user = CustomUser.objects.filter(email__iexact=email).first()
        if not existing_user:
            return

        if not existing_user.is_active:
            messages.error(request, 'This account is disabled. Please contact support.')
            raise ImmediateHttpResponse(redirect('login'))

        if existing_user.role != 'user':
            messages.error(request, 'Google Sign-In is available for citizen accounts only.')
            raise ImmediateHttpResponse(redirect('login'))

        sociallogin.connect(request, existing_user)
    
    def post_social_login(self, request, sociallogin):
        """Use default social login flow without adding extra success messages."""
        super().post_social_login(request, sociallogin)
