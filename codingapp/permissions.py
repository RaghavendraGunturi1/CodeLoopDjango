# codingapp/permissions.py
from django.core.exceptions import PermissionDenied

# Hierarchy definition
ROLE_HIERARCHY = {
    "admin": ["hod", "teacher", "student"],
    "hod": ["teacher", "student"],
    "teacher": ["student"],
    "student": [],
}

def can_assign(grantor_profile, target_profile, permission_obj):
    """
    True if grantor is allowed to assign the given permission to the target user.
    """
    # Must have valid roles
    if not grantor_profile or not grantor_profile.role or not target_profile.role:
        return False

    grantor_role = grantor_profile.role.name.lower()
    target_role = target_profile.role.name.lower()

    # Admin can assign anything
    if grantor_role == "admin":
        return True

    # Must be within hierarchy
    allowed_roles = ROLE_HIERARCHY.get(grantor_role, [])
    if target_role not in allowed_roles:
        return False

    # Grantor must personally have the permission
    return permission_obj.code in grantor_profile.get_all_permissions()

def permission_required(permission_code):
    """
    Decorator that checks if the logged-in user has a given permission.
    Use like: @permission_required("create_quiz")
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                raise PermissionDenied("You must be logged in.")
            profile = getattr(request.user, "userprofile", None)
            if not profile:
                raise PermissionDenied("Profile missing.")
            if permission_code not in profile.get_all_permissions():
                raise PermissionDenied(f"Missing permission: {permission_code}")
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
