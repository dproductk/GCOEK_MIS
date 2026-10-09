"""One-time backfill (audited, idempotent): promotion-seated confirmations + EE merge.

(a) Any current enrollment that is seated + unconfirmed + has a PROMOTED
    non-current sibling was seated by promotion (every HOD touch sets the
    flag) -> set placement_confirmed=True.
(b) Move the 2024-25 DSY pair into the running 2026-27 Sem-7 Div A, keeping
    them unconfirmed for HOD confirmation (merge, not auto-confirm).
(c) Delete the emptied 2024-25 Sem-7 Div A via the API (standard guards+audit).

Usage: python backfill_ee_promotion_merge.py
"""
import os
import sys

import django

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gceok_core.settings')
django.setup()

from django.conf import settings as _settings
if not _settings.DEBUG:
    print('ERROR: This script is for development only. Set DEBUG=True to use it.')
    sys.exit(1)

from apps.academic_structure.models import Division
from apps.audit.models import AuditLog
from apps.audit.services import audit_log
from apps.authentication.models import Role, User
from apps.students.models import StudentEnrollment
from rest_framework.test import APIClient


def hod_for(dept_code):
    role = Role.objects.filter(codename='HOD').first()
    if role is None:
        return User.objects.filter(is_superuser=True).first()
    ra = (
        role.assignments.filter(status='ACTIVE', department_id__isnull=False)
        .select_related('user')
        .first()
    )
    # Prefer an HOD actually scoped to this department.
    if ra is not None:
        from apps.academic_structure.models import Department
        dept = Department.objects.filter(code=dept_code).first()
        scoped = role.assignments.filter(
            status='ACTIVE', user=ra.user, department_id=getattr(dept, 'id', None)
        ).first() if dept else None
        if scoped is not None or (dept and str(ra.department_id) == str(dept.id)):
            return ra.user
        dept_scoped = role.assignments.filter(
            status='ACTIVE', department_id=getattr(dept, 'id', None)
        ).select_related('user').first() if dept else None
        if dept_scoped is not None:
            return dept_scoped.user
        return ra.user
    return User.objects.filter(is_superuser=True).first()


# (a) Promotion-seated -> confirmed.
fixed = 0
qs = StudentEnrollment.objects.filter(
    is_current=True, placement_confirmed=False, division__isnull=False
).select_related('student', 'division', 'division__department', 'semester')
for e in qs:
    if not StudentEnrollment.objects.filter(
        student=e.student, is_current=False,
        status=StudentEnrollment.Status.PROMOTED,
    ).exists():
        continue
    actor = hod_for(e.division.department.code)
    e.placement_confirmed = True
    e.save(update_fields=['placement_confirmed', 'updated_at'])
    audit_log(
        request=None, actor=actor, action=AuditLog.Action.UPDATE,
        target_type='StudentEnrollment', target_id=str(e.id),
        target_display=f'{e.student.display_name} confirmed in {e.division}',
        reason='Promotion-seating confirmation backfill',
        description=(
            f'Marked {e.student.display_name} placement-confirmed in {e.division}: '
            'seated by HOD promotion (PROMOTED history, never re-asked).'
        ),
    )
    fixed += 1
    print(f'CONFIRMED {e.student.display_name} in {e.division}')
print(f'(a) confirmed: {fixed}')

# (b) Merge the 2024-25 DSY pair into the running 2026-27 Sem-7 Div A.
hod_ee = User.objects.get(username='hod_ee')
target = Division.objects.get(
    department__code='EE', academic_year__code='2026-27',
    semester__number=7, name='A')
moved = 0
for nm in ['KHATANGALE PRAGATI SHAHAJI', 'MALI PRAMOD ABASO']:
    from apps.students.models import Student
    s = Student.objects.filter(display_name=nm).first()
    if s is None:
        print(f'MISSING {nm}')
        continue
    e = s.enrollments.filter(is_current=True).first()
    if e is None or e.division_id == target.id:
        print(f'SKIP {nm}')
        continue
    old = str(e.division)
    e.division = target
    e.save(update_fields=['division', 'updated_at'])
    audit_log(
        request=None, actor=hod_ee, action=AuditLog.Action.UPDATE,
        target_type='StudentEnrollment', target_id=str(e.id),
        target_display=f'{s.display_name} -> Div {target.name} (Sem 7)',
        reason='Merge auto-created past-year landing into running class',
        description=(
            f'Moved {s.display_name} from {old} into running {target} '
            '(still unconfirmed for HOD confirmation).'
        ),
    )
    moved += 1
    print(f'MOVED {nm} {old} -> {target}')
print(f'(b) moved: {moved}')

# (c) Delete the emptied past-year division through the API (guards + audit).
c = APIClient()
c.force_authenticate(user=hod_ee)
old_div = Division.objects.filter(
    department__code='EE', academic_year__code='2024-25',
    semester__number=7, name='A').first()
if old_div is None:
    print('(c) already gone')
else:
    r = c.delete(f'/api/v1/academic/divisions/{old_div.id}/')
    print(f'(c) delete {old_div.id}: {r.status_code}', dict(r.data) if r.status_code != 204 else 'deleted')
print('DONE')
