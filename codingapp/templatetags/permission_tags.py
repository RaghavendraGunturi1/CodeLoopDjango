from django import template
register = template.Library()

from django import template

register = template.Library()

@register.filter
def has_permission(user_permission_map, user_id):
    """
    Safely returns the permission ID set for a given user ID.
    Usage: {{ user_permission_map|has_permission:user.id }}
    """
    try:
        return user_permission_map.get(user_id, set())
    except Exception:
        return set()

@register.filter
def in_set(value, collection):
    """
    Check if a value (e.g., perm.id) is in a collection (set/list).
    Usage: {% if perm.id|in_set:user_permission_map|has_permission:user.id %}
    """
    try:
        return value in collection
    except Exception:
        return False
