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

# codingapp/context_processors.py
def current_user_permissions(request):
    """
    Adds `user_perms` (set of permission codes) and `is_admin_like` boolean
    to the template context so navbar and other templates can use them.
    """
    user_perms = set()
    is_admin_like = False

    user = getattr(request, "user", None)
    if user and user.is_authenticated:
        try:
            profile = getattr(user, "userprofile", None)
            if profile:
                user_perms = profile.permission_codes()
                # optionally expose a convenient boolean for admin-like roles
                is_admin_like = (profile.role and profile.role.name.lower() == "admin")
        except Exception:
            # fail safe => empty perms
            user_perms = set()

    return {
        "user_perms": user_perms,
        "is_admin_like": is_admin_like,
    }
