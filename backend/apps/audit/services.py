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
import logging

from apps.audit.models import AuditLog

logger = logging.getLogger(__name__)

# Tokenized key parts that must never be written to the audit trail
# (SECURITY.md Sec 12). Matching is on whole underscore/dash/space/camelCase
# tokens — NOT substrings — so `pincode` does not match `pin` and `cardboard`
# does not match `card`, while `access_key` and `account_number` still do.
_SENSITIVE_PARTS = frozenset({
    'password', 'passwd', 'secret', 'token', 'refresh', 'access',
    'salt', 'hash', 'aadhaar', 'aadhar', 'uidai',
    'account', 'bank', 'card', 'cvv', 'pin', 'key',
})

import re as _re


def _is_sensitive_key(key):
    """True if any token of the key is a sensitive part."""
    text = str(key).lower()
    # Split snake/kebab/space/camelCase into tokens.
    text = _re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', str(key))
    tokens = _re.split(r'[^a-z0-9]+', text.lower())
    return any(tok in _SENSITIVE_PARTS for tok in tokens if tok)


def _redact(obj):
    """Recursively redact sensitive keys; coerce to JSON-safe primitives."""
    if isinstance(obj, dict):
        clean = {}
        for key, value in obj.items():
            if _is_sensitive_key(key):
                clean[str(key)] = '***REDACTED***'
            else:
                clean[str(key)] = _redact(value)
        return clean
    if isinstance(obj, (list, tuple)):
        return [_redact(v) for v in obj]
    # Coerce Decimal/UUID/datetime and friends to plain strings.
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    return str(obj)


def get_client_ip(request):
    """Extract client IP from request, handling proxy headers.

    NOTE: X-Forwarded-For is spoofable unless a trusted reverse proxy
    strips it. Deployments must configure the proxy to overwrite it and,
    in production, restrict direct app access to the proxy only.
    """
    if request is None:
        return None
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        candidate = x_forwarded_for.split(',')[0].strip()
        return candidate[:45] if candidate else None
    remote = request.META.get('REMOTE_ADDR')
    return str(remote)[:45] if remote else None


def _resolve_actor_role(actor, request):
    """Best-effort role snapshot for the audit row (max 50 chars)."""
    explicit = getattr(request, '_audit_role', '') if request else ''
    if explicit:
        return str(explicit)[:50]
    try:
        if actor is not None and getattr(actor, 'is_authenticated', False):
            from apps.authentication.permissions import get_user_scopes
            # get_user_scopes needs a user object, not the request.
            scopes = get_user_scopes(actor)
            roles = scopes.get('roles', []) if isinstance(scopes, dict) else []
            if roles:
                return ','.join(sorted({str(r) for r in roles}))[:50]
    except Exception:
        pass
    return ''


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
        if user and getattr(user, 'is_authenticated', False):
            actor = user

    actor_username = ''
    if actor is not None:
        actor_username = str(getattr(actor, 'username', str(actor)) or '')[:150]
    actor_role = _resolve_actor_role(actor, request)

    clean_old = _redact(old_value) if old_value is not None else None
    clean_new = _redact(new_value) if new_value is not None else None

    user_agent = ''
    if request is not None:
        try:
            user_agent = str(request.META.get('HTTP_USER_AGENT', '') or '')[:2000]
        except Exception:
            user_agent = ''

    try:
        return AuditLog.objects.create(
            actor=actor if getattr(actor, 'pk', None) else None,
            actor_username=actor_username,
            actor_role=actor_role,
            action=action,
            description=str(description or ''),
            target_type=str(target_type or 'Unknown')[:100],
            target_id=str(target_id or ''),
            target_display=str(target_display or '')[:255],
            old_value=clean_old,
            new_value=clean_new,
            reason=str(reason or ''),
            ip_address=get_client_ip(request),
            user_agent=user_agent,
        )
    except Exception:
        # Never swallow silently in production: emit to secured app logs
        # (SECURITY.md Sec 13) and re-raise so the caller fails closed
        # instead of committing business state without its audit trail.
        logger.exception(
            'Failed to write audit log action=%s target=%s:%s',
            action, target_type, target_id,
        )
        raise
