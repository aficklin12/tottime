from django.utils.deprecation import MiddlewareMixin
from .models import TemporaryAccess
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

class TemporaryAccessMiddleware(MiddlewareMixin):
    """
    Middleware to handle temporary access tokens in query parameters.
    When a valid access_token is present, sets request.temp_main_user to the
    location that was shared (TemporaryAccess.user), regardless of who created it
    or what location they're currently viewing.
    """
    def process_request(self, request):
        # Check for access_token in query params (don't skip if user is authenticated)
        token = request.GET.get('access_token')
        if not token:
            return None
        
        try:
            temp_access = TemporaryAccess.objects.get(token=token, is_active=True)
            
            if temp_access.is_valid:
                # The temp_main_user is the location that was shared when the link was created
                # This is locked at creation time and never changes
                request.temp_main_user = temp_access.user
                request.is_public_access = True
                
                # Update last used
                temp_access.last_used = timezone.now()
                temp_access.save(update_fields=['last_used'])
                
                logger.info(f"Public access granted for location {temp_access.user.id} ({temp_access.user.company_name}) via token {token}")
            else:
                logger.warning(f"Expired access token used: {token}")
                
        except (TemporaryAccess.DoesNotExist, ValueError):
            logger.warning(f"Invalid access token: {token}")
        
        return None