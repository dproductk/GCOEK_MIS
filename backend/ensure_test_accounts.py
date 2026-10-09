import os
import sys
import django

# Setup Django environment
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gceok_core.settings')
django.setup()

from apps.authentication.models import User, Role, RoleAssignment
from apps.academic_structure.models import Department, Division

from django.conf import settings
if not settings.DEBUG:
    print('ERROR: This script is for development only. Set DEBUG=True to use it.')
    sys.exit(1)

def setup_users():
    password = 'Password123!'
    cse_dept = Department.objects.filter(code='CSE').first()
    cse_div_a = Division.objects.filter(department=cse_dept, name='A').first()

    roles = {r.codename: r for r in Role.objects.all()}

    accounts = [
        # (username, email, user_type, role_codename, dept, div)
        ('sysadmin', 'sysadmin@gceok.ac.in', User.UserType.SYSADMIN, 'SYSADMIN', None, None),
        ('admin', 'admin@gceok.ac.in', User.UserType.SYSADMIN, 'SYSADMIN', None, None),
        ('admin_head', 'admin_head@gceok.ac.in', User.UserType.FACULTY, 'ADMIN_HEAD', None, None),
        ('accountant', 'accountant@gceok.ac.in', User.UserType.FACULTY, 'ACCOUNTANT', None, None),
        ('hod_cse', 'hod_cse@gceok.ac.in', User.UserType.FACULTY, 'HOD', cse_dept, None),
        ('ct_cse_a', 'ct_cse_a@gceok.ac.in', User.UserType.FACULTY, 'CLASS_TEACHER', cse_dept, cse_div_a),
        ('faculty_cse1', 'faculty_cse1@gceok.ac.in', User.UserType.FACULTY, 'FACULTY', cse_dept, None),
        ('faculty_priya', 'priya@gceok.ac.in', User.UserType.FACULTY, 'FACULTY', cse_dept, None),
        ('student_rohit', 'rohit@gceok.ac.in', User.UserType.STUDENT, 'STUDENT', None, None),
        ('student', 'student@gceok.ac.in', User.UserType.STUDENT, 'STUDENT', None, None),
    ]

    for username, email, user_type, role_code, dept, div in accounts:
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                'email': email,
                'user_type': user_type,
                'is_active': True,
                'is_staff': (user_type == User.UserType.SYSADMIN),
                'is_superuser': (user_type == User.UserType.SYSADMIN),
                'must_change_password': False,
            }
        )
        user.set_password(password)
        user.must_change_password = False
        user.is_active = True
        user.save()

        # Assign Role
        role = roles.get(role_code)
        if role:
            assign, _ = RoleAssignment.objects.get_or_create(
                user=user,
                role=role,
                defaults={
                    'department_id': dept.id if dept else None,
                    'division_id': div.id if div else None,
                    'status': RoleAssignment.Status.ACTIVE,
                }
            )
            assign.department_id = dept.id if dept else None
            assign.division_id = div.id if div else None
            assign.status = RoleAssignment.Status.ACTIVE
            assign.save()

        print(f"Verified user: {username} | Role: {role_code} | Password: {password}")

if __name__ == '__main__':
    setup_users()
