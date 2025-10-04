from .models import Notice, NoticeReadStatus
from django.db.models import Q
from django.db.models import Q

def unread_notice_count(request):
    if request.user.is_authenticated:
        notices = Notice.objects.filter(
            Q(for_everyone=True) | Q(group__in=request.user.custom_groups.all())
        ).distinct()
        unread_count = NoticeReadStatus.objects.filter(
            user=request.user, is_read=False, notice__in=notices
        ).count()
        return {'unread_notice_count': unread_count}
    return {}
