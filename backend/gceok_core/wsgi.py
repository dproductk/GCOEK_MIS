"""
WSGI config for GCOEK MIS project.
"""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gceok_core.settings')
application = get_wsgi_application()
