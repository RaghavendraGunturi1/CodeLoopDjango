from django import template
register = template.Library()

@register.filter
def dict_get(d, key):
    """Safely get a value from dict by key."""
    try:
        return d.get(int(key)) if d else []
    except Exception:
        return []

# codingapp/templatetags/dict_extras.py
from django import template
register = template.Library()

@register.filter
def get_item(d, key):
    try:
        return d.get(key, 0)
    except Exception:
        return 0
