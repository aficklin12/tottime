from django.contrib.auth.backends import ModelBackend
from django.utils import timezone
from .models import TemporaryAccess

class TemporaryAccessBackend(ModelBackend):
    """Authenticates users with temporary access tokens"""

    def authenticate(self, request=None, token=None, **kwargs):
        if not token:
            return None

        try:
            temp_access = TemporaryAccess.objects.get(token=token, is_active=True)
            if temp_access.expires_at < timezone.now():
                return None
            temp_access.last_used = timezone.now()
            temp_access.save(update_fields=['last_used'])
            return temp_access.user
        except (TemporaryAccess.DoesNotExist, ValueError):
            return None