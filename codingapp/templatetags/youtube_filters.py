from django import template
import re

register = template.Library()

@register.filter
def youtube_id(url):
    """
    Extracts the YouTube video ID from various common YouTube URL formats.
    """
    # Match patterns like ?v=ID, /embed/ID, /v/ID, etc.
    match = re.search(r'(?:v=|v/|embed/|youtu\.be/)([\w-]{11})', url)
    if match:
        return match.group(1)
    return ''
