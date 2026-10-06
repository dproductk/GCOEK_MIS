"""Application services for Academic Structure workflows.

Single-owner rule (ARCH 7): Division.class_teacher and the matching
CLASS_TEACHER RoleAssignment are two projections of ONE fact — "who mentors
this division". All writes go through sync_class_teacher() so they can never
drift apart again.
"""
from django.db import transaction

from apps.audit.models import AuditLog
from apps.audit.services import audit_log


def sync_class_teacher(division, user, actor, request=None, reason=''):
    """Set the division's class teacher on BOTH projections atomically.

    1. Revoke other ACTIVE CLASS_TEACHER assignments scoped to the division
       (history preserved, never deleted).
    2. Create (or reuse) the ACTIVE assignment for (user, division), unless
       user is None (unassign: only revoke + clear the FK).
    3. Point Division.class_teacher at the user (or clear it).
    Audits once with old/new values. Idempotent for the same user.
    Returns (assignment_or_None, previous_username_or_None).
    """
    from apps.authentication.models import Role, RoleAssignment

    with transaction.atomic():
        division = type(division).objects.select_for_update().get(id=division.id)
        old_username = (
            division.class_teacher.username if division.class_teacher else None
        )
        role = Role.objects.filter(codename='CLASS_TEACHER').first()
        if role is None:
            raise ValueError('CLASS_TEACHER role is not configured.')

        previous = RoleAssignment.objects.select_for_update().filter(
            role=role, division_id=division.id,
            status=RoleAssignment.Status.ACTIVE,
        )
        if user is not None:
            previous = previous.exclude(user=user)
        revoked = previous.count()
        for prev in previous:
            prev.status = RoleAssignment.Status.REVOKED
            from django.utils import timezone
            prev.revoked_at = timezone.now()
            prev.revoked_by = actor if actor and actor.is_authenticated else None
            prev.save(update_fields=['status', 'revoked_at', 'revoked_by', 'updated_at'])

        assignment = None
        if user is not None:
            assignment, _ = RoleAssignment.objects.get_or_create(
                user=user, role=role, department_id=division.department_id,
                division_id=division.id,
                defaults={
                    'status': RoleAssignment.Status.ACTIVE,
                    'assigned_by': actor if actor and actor.is_authenticated else None,
                    'reason': reason or 'Class-teacher assignment',
                },
            )
            if assignment.status != RoleAssignment.Status.ACTIVE:
                assignment.status = RoleAssignment.Status.ACTIVE
                assignment.revoked_at = None
                assignment.revoked_by = None
                assignment.save(update_fields=['status', 'assigned_by', 'revoked_at', 'revoked_by', 'updated_at'])

        division.class_teacher = user
        division.save(update_fields=['class_teacher'])

        audit_log(
            request=request, actor=actor, action=AuditLog.Action.UPDATE,
            target_type='Division', target_id=str(division.id),
            target_display=str(division),
            old_value={'class_teacher': old_username},
            new_value={'class_teacher': user.username if user else None},
            reason=reason or 'Class-teacher assignment',
            description=(
                f"Class teacher of {division} changed "
                f"{old_username or '—'} -> {(user.username if user else '—')} "
                f"({revoked} prior holder(s) revoked)."
            ),
        )
        return assignment, old_username
