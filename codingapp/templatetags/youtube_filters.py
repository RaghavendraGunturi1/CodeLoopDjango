from django import template
import re
from urllib.parse import urlparse, parse_qs

register = template.Library()

@register.filter
def youtube_id(url):
    """
    Extracts a YouTube video ID from common URL formats or raw IDs.
    """
    if not url:
        return ''
    if re.fullmatch(r'[\w-]{11}', url):
        return url
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    if 'v' in query:
        return query['v'][0]
    match = re.search(r'youtu\.be/([\w-]{11})', url)
    if match:
        return match.group(1)
    match = re.search(r'embed/([\w-]{11})', url)
    if match:
        return match.group(1)
    match = re.search(r'(?:v=|v/|embed/|youtu\.be/)([\w-]{11})', url)
    if match:
        return match.group(1)
    return ''
