from django.db.models import Q
from codingapp.models import Notice, NoticeReadStatus, UserProfile


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


def user_permissions_context(request):
    """
    Inject the logged-in user's permissions and role info into every template.
    Ensures Manage dropdown, Control Panel, etc. appear properly.
    """
    if not request.user.is_authenticated:
        return {}

    try:
        profile = getattr(request.user, "userprofile", None)
        if not profile:
            return {}

        user_perms = set(profile.permission_codes())
        role_name = profile.role.name.lower() if profile.role else None
        is_admin_like = role_name in ["admin", "hod"]
        is_teacher_like = role_name == "teacher"
        is_student = role_name == "student"

        return {
            "user_perms": user_perms,
            "role_name": role_name,
            "is_admin_like": is_admin_like,
            "is_teacher_like": is_teacher_like,
            "is_student": is_student,
        }

    except Exception as e:
        print(f"[ContextProcessor Error] user_permissions_context: {e}")
        return {}
