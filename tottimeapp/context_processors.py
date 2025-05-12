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