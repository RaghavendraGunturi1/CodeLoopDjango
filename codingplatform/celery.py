# codingplatform/celery.py
import os
from celery import Celery

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'codingplatform.settings')

# Create a Celery instance and name it after the project.
app = Celery('codingplatform')

# Load task settings from Django settings.py (all Celery config MUST be prefixed with 'CELERY_')
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks in all installed apps (like codingapp/tasks.py)
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    """Debug task for initial setup validation."""
    print(f'Request: {self.request!r}')