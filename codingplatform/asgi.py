# In codingplatform/asgi.py
import os
from django.core.asgi import get_asgi_application
# --- Add these imports ---
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
# -------------------------
import codingapp.routing  # Import your new routing file

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'codingplatform.settings')

# This router now correctly uses the imported classes
application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(
            codingapp.routing.websocket_urlpatterns
        )
    ),
})