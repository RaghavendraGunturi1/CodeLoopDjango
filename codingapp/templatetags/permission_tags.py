from django import template
register = template.Library()

@register.filter
def has_permission(user, perm_code):
    """Usage: {% if request.user|has_permission:'create_quiz' %}"""
    profile = getattr(user, "userprofile", None)
    if not profile:
        return False
    return perm_code in profile.get_all_permissions()
