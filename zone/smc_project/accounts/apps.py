from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = 'accounts'

    def ready(self):
        # Register model signal handlers.
        import accounts.signals  # noqa: F401
