from django.db.models import Q, Count, Sum
from tottimeapp.models import Conversation, CompanyAccountOwner
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from datetime import datetime


def unread_messages_count(request):
    if request.user.is_authenticated:
        unread_message_count = Conversation.objects.filter(
            Q(recipient=request.user)
        ).annotate(
            unread_count=Count('messages', filter=Q(messages__recipient=request.user, messages__is_read=False))
        ).aggregate(total_unread=Sum('unread_count'))['total_unread'] or 0
        unread_message_count = int(unread_message_count)
        print(f"Total unread messages: {unread_message_count}")  # Debugging
        return {'unread_message_count': unread_message_count}
    return {'unread_message_count': 0}

def is_app_context(request):
    user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
    is_app = 'cordova' in user_agent or 'tot-time-app' in user_agent or 'mobile' in user_agent
    return {'is_app': is_app}

def show_back_button(request):
    # List of view names where the back button should be hidden
    hide_view_names = [
        'index',
        'index_director',
        'index_teacher_parent',
        'index_teacher',
        'index_cook',
        'index_parent',
        'index_free_user',
    ]
    resolver_match = getattr(request, 'resolver_match', None)
    current_view_name = resolver_match.view_name if resolver_match else None
    return {'show_back_button': current_view_name not in hide_view_names}

def account_switcher_context(request):
    if request.user.is_authenticated and request.user.can_switch and request.user.company:
        available_account_owners = CompanyAccountOwner.objects.filter(
            company=request.user.company
        ).select_related('main_account_owner')
        return {'available_account_owners': available_account_owners}
    return {'available_account_owners': []}


def template_type(request):
    """
    Add template type context variables to all templates.
    """
    is_public = (
        request.GET.get('public') == 'true' or
        request.GET.get('popup') in ('1', 'true')
    )
    return {
        'is_public_view': is_public
    }

def template_base(request):
    """Determine which base template to use."""
    is_public = request.GET.get('public') == 'true'
    return {
        'base_template': 'tottimeapp/base_public.html' if is_public else 'tottimeapp/base.html',
        'default_base_template': 'tottimeapp/base_public.html' if is_public else 'tottimeapp/base.html',
    }

def temporary_access_context(request):
    """Add temporary access information to all templates"""
    context = {
        'is_temporary_access': request.session.get('is_temporary_access', False),
    }
    
    # If this is a temporary access session, add expiry information
    if context['is_temporary_access'] and request.session.get('temp_access_expires'):
        try:
            # Parse ISO format date string using Django helper
            expires_iso = request.session.get('temp_access_expires')
            expires_at = parse_datetime(expires_iso)
            if expires_at is None:
                raise ValueError("Could not parse date")

            # Ensure timezone-aware datetime
            if timezone.is_naive(expires_at):
                expires_at = timezone.make_aware(expires_at, timezone.get_default_timezone())
            
            expiry_date = expires_at.strftime('%B %d, %Y at %I:%M %p')
            
            context.update({
                'temp_access_expires': expires_at,
                'expiry_date': expiry_date,
                'is_expired': expires_at < timezone.now()
            })
        except (ValueError, TypeError):
            pass
            
    return context