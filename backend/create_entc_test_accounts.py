import os, sys, django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gceok_core.settings')
django.setup()

from datetime import date
from apps.authentication.models import User, Role, RoleAssignment
from apps.academic_structure.models import Department, AcademicYear, Semester, Division
from apps.curriculum.models import Subject
from apps.faculty.models import Faculty, TeachingAssignment

PASSWORD = 'Password123!'
dept = Department.objects.get(code='ETC')
roles = {r.codename: r for r in Role.objects.all()}
year = AcademicYear.objects.get(code='2026-27', is_current=True)
sem3 = Semester.objects.get(number=3)
divA = Division.objects.get(department=dept, academic_year=year, semester=sem3, name='A')

accounts = [
    dict(username='hod_entc', email='hod.entc@gceok.ac.in', emp='HOD_ENTC01', fn='Rajesh', ln='Patil', desig='HOD', role='HOD'),
    dict(username='faculty_entc1', email='faculty.entc1@gceok.ac.in', emp='ENTC_F01', fn='Sneha', ln='Deshmukh', desig='ASSISTANT_PROFESSOR', role='FACULTY'),
    dict(username='faculty_entc2', email='faculty.entc2@gceok.ac.in', emp='ENTC_F02', fn='Amit', ln='Kulkarni', desig='ASSISTANT_PROFESSOR', role='FACULTY'),
    dict(username='faculty_entc3', email='faculty.entc3@gceok.ac.in', emp='ENTC_F03', fn='Pooja', ln='Shinde', desig='ASSISTANT_PROFESSOR', role='FACULTY'),
]
for a in accounts:
    user, _ = User.objects.get_or_create(
        username=a['username'],
        defaults={'email': a['email'], 'user_type': User.UserType.FACULTY,
                  'is_active': True, 'must_change_password': False})
    user.email = a['email']
    user.user_type = User.UserType.FACULTY
    user.is_active = True
    user.must_change_password = False
    user.set_password(PASSWORD)
    user.save()
    ra, _ = RoleAssignment.objects.get_or_create(
        user=user, role=roles[a['role']],
        defaults={'department_id': dept.id, 'status': RoleAssignment.Status.ACTIVE})
    ra.department_id = dept.id
    ra.status = RoleAssignment.Status.ACTIVE
    ra.save()
    if a['role'] != 'FACULTY':
        base, _ = RoleAssignment.objects.get_or_create(
            user=user, role=roles['FACULTY'],
            defaults={'department_id': dept.id, 'status': RoleAssignment.Status.ACTIVE})
        base.department_id = dept.id
        base.status = RoleAssignment.Status.ACTIVE
        base.save()
    fac, created = Faculty.objects.get_or_create(
        employee_code=a['emp'],
        defaults={'user': user, 'first_name': a['fn'], 'last_name': a['ln'],
                  'department': dept, 'designation': a['desig'],
                  'date_of_joining': date(2024, 7, 1),
                  'official_email': a['email'], 'is_active': True})
    fac.user = user
    fac.first_name = a['fn']
    fac.last_name = a['ln']
    fac.department = dept
    fac.designation = a['desig']
    fac.official_email = a['email']
    fac.is_active = True
    fac.save()
    print(f"OK user={a['username']} role={a['role']} emp={a['emp']}")

subs = [
    dict(code='ETC301', title='Digital Signal Processing'),
    dict(code='ETC302', title='VLSI Design'),
]
for s in subs:
    obj, created = Subject.objects.get_or_create(
        code=s['code'],
        defaults={'title': s['title'], 'course_category': 'PCC', 'lecture_hours': 3,
                  'ca_max_marks': 20, 'mse_max_marks': 20, 'ese_max_marks': 60,
                  'credits': 3, 'is_active': True})
    obj.title = s['title']
    obj.course_category = 'PCC'
    obj.lecture_hours = 3
    obj.ca_max_marks = 20
    obj.mse_max_marks = 20
    obj.ese_max_marks = 60
    obj.credits = 3
    obj.is_active = True
    obj.save()
    print(f"OK subject={obj.code} created={created}")

assign_map = [('faculty_entc1', 'ENTC_F01', 'ETC301', 'Digital Signal Processing'),
              ('faculty_entc2', 'ENTC_F02', 'ETC302', 'VLSI Design')]
for uname, emp, scode, sname in assign_map:
    fac = Faculty.objects.get(employee_code=emp)
    ta, created = TeachingAssignment.objects.get_or_create(
        faculty=fac, academic_year=year, department=dept, semester=sem3,
        division=divA, subject_code=scode, role='PRIMARY_FACULTY',
        defaults={'subject_name': sname, 'is_active': True})
    ta.subject_name = sname
    ta.is_active = True
    ta.save()
    print(f"OK assignment {uname} -> {scode} ({divA})")
print('DONE')
