# In codingplatform/urls.py

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('codingapp.urls')),
]

# ⭐ FIX: This block tells the development server to serve static and media files
if settings.DEBUG:
    # 1. Serving Static files (CSS, JS, Images from your static/ folder)
    # We use STATICFILES_DIRS[0] as per your configuration.
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
    
    # 2. Serving Media files (Your user-uploaded notes)
    # This is the critical line that makes /media/ URLs work.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)