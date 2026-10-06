"""
Audit app — append-only audit logging for all security-sensitive operations.

Per SECURITY.md:
- Every security-sensitive action is logged
- Audit logs are append-only (never updated or deleted)
- Captures: actor, role, action, target, IP, user-agent, changes, timestamp
"""
from django.apps import AppConfig


class AuditConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.audit'
    verbose_name = 'Audit Logging'
