from django.utils.deprecation import MiddlewareMixin
from django.contrib.auth import authenticate, login
from .models import TemporaryAccess

class TemporaryAccessMiddleware(MiddlewareMixin):
    """Automatically authenticates users with temporary access tokens"""

    def process_request(self, request):
        # Skip if user is already authenticated
        if request.user.is_authenticated:
            return None

        token = None
        # query param
        token_param = request.GET.get('access_token')
        if token_param:
            token = token_param

        # path form /public/<token>/
        path_parts = request.path.strip('/').split('/')
        if len(path_parts) >= 2 and path_parts[-2] == 'public':
            token = path_parts[-1]

        if not token:
            return None

        user = authenticate(request=request, token=token)
        if user:
            login(request, user)
            request.session['is_temporary_access'] = True
            request.session['access_token'] = str(token)
            try:
                temp_access = TemporaryAccess.objects.get(token=token)
                request.session['temp_access_expires'] = temp_access.expires_at.isoformat()
            except TemporaryAccess.DoesNotExist:
                pass

        return None