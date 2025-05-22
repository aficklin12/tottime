from django.db.models import Q, Count, Sum
from tottimeapp.models import Conversation

def unread_messages_count(request):
    if request.user.is_authenticated:
        total_unread_count = Conversation.objects.filter(
            Q(recipient=request.user)
        ).annotate(
            unread_count=Count('messages', filter=Q(messages__recipient=request.user, messages__is_read=False))
        ).aggregate(total_unread=Sum('unread_count'))['total_unread'] or 0
        print(f"Total unread messages: {total_unread_count}")  # Debugging
        return {'total_unread_count': total_unread_count}
    return {'total_unread_count': 0}

def is_app_context(request):
    user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
    is_app = 'cordova' in user_agent or 'tot-time-app' in user_agent or 'mobile' in user_agent
    return {'is_app': is_app}

def show_back_button(request):
    # List of paths where the back button should be hidden
    hide_paths = [
        '/index.html',
        '/index_director.html',
        '/index_teacher_parent.html',
        '/index_teacher.html',
        '/index_cook.html',
        '/index_parent.html',
        '/index_free_user.html',
        '/',
    ]
    # Hide the back button if the current path matches any in the list
    return {'show_back_button': request.path not in hide_paths}