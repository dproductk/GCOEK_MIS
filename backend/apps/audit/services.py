"""
Audit logging service — utility to create audit log entries.

Usage:
    from apps.audit.services import audit_log
    audit_log(
        request=request,
        action=AuditLog.Action.CREATE,
        target_type='Student',
        target_id=str(student.id),
        target_display=student.full_name,
        new_value={'enrollment_no': student.enrollment_no},
        description='Created student record from government import.',
    )
"""
from apps.audit.models import AuditLog


def get_client_ip(request):
    """Extract client IP from request, handling proxy headers."""
    if request is None:
        return None
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def audit_log(
    request=None,
    actor=None,
    action='',
    target_type='',
    target_id='',
    target_display='',
    old_value=None,
    new_value=None,
    reason='',
    description='',
):
    """
    Create an audit log entry.

    Args:
        request: The HTTP request (used for actor, IP, user-agent).
        actor: Override actor user (defaults to request.user if available).
        action: AuditLog.Action value.
        target_type: Type/model name of the target entity.
        target_id: ID of the target entity.
        target_display: Human-readable label for the target.
        old_value: Previous state as dict (for updates).
        new_value: New state as dict (for creates/updates).
        reason: Reason for the action.
        description: Human-readable description.
    """
    if actor is None and request is not None:
        user = getattr(request, 'user', None)
        if user and user.is_authenticated:
            actor = user

    actor_username = ''
    actor_role = ''
    if actor is not None:
        actor_username = getattr(actor, 'username', str(actor))
        # If the request has a resolved role context, use it
        actor_role = getattr(request, '_audit_role', '') if request else ''

    return AuditLog.objects.create(
        actor=actor,
        actor_username=actor_username,
        actor_role=actor_role,
        action=action,
        description=description,
        target_type=target_type,
        target_id=str(target_id),
        target_display=target_display,
        old_value=old_value,
        new_value=new_value,
        reason=reason,
        ip_address=get_client_ip(request),
        user_agent=(
            request.META.get('HTTP_USER_AGENT', '') if request else ''
        ),
    )
