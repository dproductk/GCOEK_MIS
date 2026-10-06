"""
ASGI config for GCOEK MIS project.
"""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gceok_core.settings')
application = get_asgi_application()
