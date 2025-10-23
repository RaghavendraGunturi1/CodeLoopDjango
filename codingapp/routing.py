# In codingapp/routing.py
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # This regex matches the URL the browser will connect to
    re_path(r'ws/submission/(?P<submission_id>\d+)/$', consumers.SubmissionConsumer.as_asgi()),
]