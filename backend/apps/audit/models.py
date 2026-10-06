"""
Audit log model — append-only audit trail.

Per SECURITY.md: all security-sensitive actions must be logged with
actor, role, action, target, IP, user-agent, changes, and timestamp.
Audit records are NEVER updated or deleted.
"""
from django.conf import settings
from django.db import models

from apps.common.models import UUIDPrimaryKeyModel


class AuditLog(UUIDPrimaryKeyModel):
    """
    Append-only audit log entry.

    Captures who did what, to which entity, when, and from where.
    This table must never have UPDATE or DELETE operations.
    """

    class Action(models.TextChoices):
        CREATE = 'CREATE', 'Create'
        READ = 'READ', 'Read'
        UPDATE = 'UPDATE', 'Update'
        DELETE = 'DELETE', 'Delete'
        LOGIN = 'LOGIN', 'Login'
        LOGOUT = 'LOGOUT', 'Logout'
        LOGIN_FAILED = 'LOGIN_FAILED', 'Login Failed'
        PASSWORD_CHANGE = 'PASSWORD_CHANGE', 'Password Change'
        ROLE_ASSIGN = 'ROLE_ASSIGN', 'Role Assignment'
        ROLE_REVOKE = 'ROLE_REVOKE', 'Role Revocation'
        SENSITIVE_REVEAL = 'SENSITIVE_REVEAL', 'Sensitive Data Reveal'
        IMPORT = 'IMPORT', 'Data Import'
        EXPORT = 'EXPORT', 'Data Export'
        VERIFY = 'VERIFY', 'Verification'
        PAYMENT = 'PAYMENT', 'Payment'
        STATUS_CHANGE = 'STATUS_CHANGE', 'Status Change'

    # Who performed the action
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
        help_text='User who performed the action. Null for system actions.',
    )
    actor_username = models.CharField(
        max_length=150,
        blank=True,
        default='',
        help_text='Username snapshot at time of action (preserved even if user deleted).',
    )
    actor_role = models.CharField(
        max_length=50,
        blank=True,
        default='',
        help_text='Role the actor was operating under at time of action.',
    )

    # What action was performed
    action = models.CharField(
        max_length=30,
        choices=Action.choices,
        db_index=True,
        help_text='Type of action performed.',
    )
    description = models.TextField(
        blank=True,
        default='',
        help_text='Human-readable description of the action.',
    )

    # Which entity was affected
    target_type = models.CharField(
        max_length=100,
        db_index=True,
        help_text='Type of the target entity (e.g., Student, User, Payment).',
    )
    target_id = models.CharField(
        max_length=255,
        blank=True,
        default='',
        db_index=True,
        help_text='ID of the target entity.',
    )
    target_display = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text='Human-readable label for the target (e.g., student name).',
    )

    # What changed
    old_value = models.JSONField(
        null=True,
        blank=True,
        help_text='Previous state (JSON). Null for create/login actions.',
    )
    new_value = models.JSONField(
        null=True,
        blank=True,
        help_text='New state (JSON). Null for delete/logout actions.',
    )
    reason = models.TextField(
        blank=True,
        default='',
        help_text='Reason for the action, if applicable.',
    )

    # Where the action originated
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text='IP address of the request.',
    )
    user_agent = models.TextField(
        blank=True,
        default='',
        help_text='Browser/client user-agent string.',
    )

    # When
    timestamp = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text='Exact time the action was recorded.',
    )

    class Meta:
        db_table = 'audit_logs'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['actor', 'timestamp']),
            models.Index(fields=['target_type', 'target_id']),
            models.Index(fields=['action', 'timestamp']),
        ]
        # Prevent Django admin from offering delete
        default_permissions = ('add', 'view')

    def __str__(self):
        return (
            f'[{self.timestamp}] {self.actor_username} '
            f'{self.action} {self.target_type}:{self.target_id}'
        )

    def save(self, *args, **kwargs):
        """Override save to prevent updates to existing records."""
        if self.pk and AuditLog.objects.filter(pk=self.pk).exists():
            raise ValueError('Audit log records cannot be modified.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Override delete to prevent deletion of audit records."""
        raise ValueError('Audit log records cannot be deleted.')
