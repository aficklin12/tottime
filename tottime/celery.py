from __future__ import absolute_import, unicode_literals
import os
from celery import Celery

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tottime.settings')

app = Celery('tottime')

# Configure Celery to use Django settings
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks in installed apps
app.autodiscover_tasks()

# Define a simple debug task for testing
@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
