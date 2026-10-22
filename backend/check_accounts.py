from apps.authentication.models import User, RoleAssignment
from apps.academic_structure.models import Department, Division
from apps.students.models import Student

print('=== SUPERUSERS ===')
for u in User.objects.filter(is_superuser=True):
    print(u.username, u.email)

print('=== HODs ===')
for ra in RoleAssignment.objects.filter(role__codename='HOD', status='ACTIVE').select_related('user'):
    dept = Department.objects.filter(id=ra.department_id).first()
    print(f'{ra.user.username} -> {dept.name if dept else ra.department_id}')

print('=== CLASS TEACHERS ===')
for ra in RoleAssignment.objects.filter(role__codename='CLASS_TEACHER', status='ACTIVE').select_related('user'):
    div = Division.objects.filter(id=ra.division_id).first()
    sem = div.semester.number if div and div.semester else "?"
    print(f'{ra.user.username} -> {div.name if div else ra.division_id} (Sem {sem})')

print('=== STUDENTS ===')
for s in Student.objects.select_related('user').all()[:5]:
    print(f'{s.enrollment_no} | {s.first_name} {s.last_name} | user={s.user.username if s.user else None}')
