import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gceok_core.settings')
django.setup()

from apps.authentication.models import User, RoleAssignment, Role
from apps.academic_structure.models import Department, Division, Semester, AcademicYear
from apps.students.models import Student

print("Setting up demo accounts...")

# 1. Admin/Sysadmin
admin_user = User.objects.filter(username='admin').first()
if not admin_user:
    admin_user = User.objects.filter(is_superuser=True).first()
if admin_user:
    admin_user.set_password('Admin@123')
    admin_user.must_change_password = False
    admin_user.save()
    print(f"Admin user set: {admin_user.username} / Admin@123")

# 2. HOD CSE
hod_cse = User.objects.filter(username='hod_cse').first()
if hod_cse:
    hod_cse.set_password('Hod@123')
    hod_cse.must_change_password = False
    hod_cse.save()
    print(f"HOD CSE set: hod_cse / Hod@123")

# 3. Class Teacher
ct_user = User.objects.filter(username='faculty_ee2').first()
if not ct_user:
    ct_user = User.objects.filter(role_assignments__role__codename='CLASS_TEACHER').first()
if ct_user:
    ct_user.set_password('Teacher@123')
    ct_user.must_change_password = False
    ct_user.save()
    print(f"Class Teacher set: {ct_user.username} / Teacher@123")

# 4. Student
student = Student.objects.select_related('user').first()
if student and student.user:
    student.user.set_password('Student@123')
    student.user.must_change_password = False
    student.user.save()
    print(f"Student user set: {student.user.username} (Enrollment: {student.enrollment_no}) / Student@123")
    print(f"Student Name: {student.first_name} {student.last_name}")
else:
    # Check student_mech01
    s_user = User.objects.filter(username='student_mech01').first()
    if s_user:
        s_user.set_password('Student@123')
        s_user.must_change_password = False
        s_user.save()
        print(f"Student mech01 set: student_mech01 / Student@123")

print("Demo accounts configured successfully!")
