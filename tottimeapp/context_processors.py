from django.db.models import Q, Count, Sum
from tottimeapp.models import Conversation, CompanyAccountOwner

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