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


def seat_traced_students_to_division(target_div, original_div_id=None):
    """
    Seats active students in target_div.semester who are unassigned (division=None)
    and traced back to original_div_id (or target_div itself) into target_div.
    Only runs inside HOD promotion, so seated students land confirmed —
    the promotion already decided their placement.
    """
    from apps.students.models import StudentEnrollment
    moved = 0
    cands = StudentEnrollment.objects.filter(
        semester=target_div.semester,
        is_current=True,
        division__isnull=True,
        department=target_div.department,
    ).select_related('student')
    for cand in cands:
        # Check if student was previously enrolled in original_div_id or target_div
        filter_div_ids = [target_div.id]
        if original_div_id:
            filter_div_ids.append(original_div_id)
        traced = StudentEnrollment.objects.filter(
            student=cand.student,
            is_current=False,
            division_id__in=filter_div_ids,
        ).exists()
        if traced:
            cand.division = target_div
            cand.placement_confirmed = True
            cand.save(update_fields=['division', 'placement_confirmed', 'updated_at'])
            moved += 1
    return moved


def flip_class_to_next_semester(division, target_sem, actor=None, request=None):
    """
    Promote an empty year-change division (Sem 2/4/6) to target_sem.
    Strict rule: Only flips if 0 active students remain in current semester.
    Repeater divisions (name == 'R') never flip.

    Returns (destination_division, flipped_in_place).
    """
    from apps.academic_structure.models import Division
    from apps.faculty.models import TeachingAssignment
    from apps.students.models import StudentEnrollment

    # Repeater classes never flip
    if division.name == 'R':
        return division, False

    sem_num = division.semester.number
    if sem_num not in (2, 4, 6):
        return division, False

    if target_sem is None or target_sem.number != sem_num + 1:
        return division, False

    # Check remaining active students in current semester
    remaining = StudentEnrollment.objects.filter(
        division=division, is_current=True, semester__number=sem_num
    ).count()
    if remaining > 0:
        return division, False

    # Check if target division with same name already exists in target_sem
    clash = Division.objects.filter(
        department=division.department,
        academic_year=division.academic_year,
        semester=target_sem,
        name=division.name,
    ).exclude(id=division.id).first()

    original_div_id = division.id

    if clash is not None:
        seated_back = seat_traced_students_to_division(clash, original_div_id=original_div_id)
        audit_log(
            request=request,
            actor=actor,
            action=AuditLog.Action.UPDATE,
            target_type='Division',
            target_id=str(division.id),
            target_display=str(division),
            description=(
                f"Division {division.department.code} Sem {sem_num} Div {division.name} had 0 active students: "
                f"reseated {seated_back} student(s) into existing {clash}."
            ),
        )
        return clash, False

    # Flip in place
    old_label = str(division)
    division.semester = target_sem
    division.save(update_fields=['semester', 'updated_at'])

    seated_back = seat_traced_students_to_division(division, original_div_id=original_div_id)

    # Clear subject-teacher slots for old semester subjects
    cleared = 0
    try:
        cleared = TeachingAssignment.objects.filter(
            division=division, is_active=True
        ).update(is_active=False)
    except Exception:
        cleared = 0

    audit_log(
        request=request,
        actor=actor,
        action=AuditLog.Action.UPDATE,
        target_type='Division',
        target_id=str(division.id),
        target_display=str(division),
        description=(
            f"Promoted entire class {old_label} to Sem {target_sem.number} in place: "
            f"{seated_back} students seated, {cleared} subject-teacher slot(s) cleared. "
            "Class teacher carried over."
        ),
    )
    return division, True

