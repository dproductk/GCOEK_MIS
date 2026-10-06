"""
Authentication app — User, Role, Permission, RoleAssignment.

Per ARCHITECTURE.md and SECURITY.md:
- User model provides identity and account lifecycle
- user_type is for classification only, NOT authorization
- Authorization is: User → RoleAssignment → Role → Permission → Scope
"""
from django.apps import AppConfig


class AuthenticationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.authentication'
    verbose_name = 'Authentication & Access Control'
