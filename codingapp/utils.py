# codingapp/utils.py
def get_user_accessible_groups(user):
    """Return groups visible to this user."""
    from codingapp.models import Group
    profile = getattr(user, "userprofile", None)
    if not profile:
        return Group.objects.none()

    role = profile.role.name.lower() if profile.role else ""
    if role == "admin":
        return Group.objects.all()
    elif role == "hod":
        return Group.objects.filter(department=profile.department)
    elif role == "teacher":
        return Group.objects.filter(teachers=user)
    elif role == "student":
        return Group.objects.filter(students=user)
    return Group.objects.none()

from django.shortcuts import render

def check_object_group_access(request, obj):
    """
    Returns True if the user can access this object's groups, False otherwise.
    Supported: objects having a `groups` ManyToMany or `group` ForeignKey.
    """
    accessible_groups = get_user_accessible_groups(request.user)

    # Case 1: Many-to-many 'groups'
    if hasattr(obj, "groups"):
        return obj.groups.filter(id__in=accessible_groups.values_list("id", flat=True)).exists()

    # Case 2: Single foreign key 'group'
    elif hasattr(obj, "group"):
        return accessible_groups.filter(id=obj.group.id).exists()

    # Case 3: No group relation → restrict to admins
    return getattr(request.user.userprofile.role, "name", "").lower() == "admin"


def deny_access_if_not_allowed(request, obj):
    """Return None if allowed, else render 403 page."""
    if not check_object_group_access(request, obj):
        return render(request, "codingapp/permission_denied.html", status=403)
    return None

# =========================================
# 🧠 ROLE-BASED ACCESS HELPERS (Universal)
# =========================================
def has_role(user, roles):
    """Return True if the user has one of the allowed roles."""
    try:
        profile = getattr(user, "userprofile", None)
        if not profile or not profile.role:
            return False

        # Normalize both user role and allowed roles for safe comparison
        user_role = profile.role.name.strip().lower()
        roles = [r.strip().lower() for r in roles]
        return user_role in roles
    except Exception:
        return False


def is_admin(user):
    return has_role(user, ["admin"])


def is_hod(user):
    return has_role(user, ["hod", "admin"])  # HODs and admins


def is_teacher(user):
    return has_role(user, ["teacher", "hod", "admin"])  # Teachers + HOD + Admin


def is_student(user):
    return has_role(user, ["student"])
