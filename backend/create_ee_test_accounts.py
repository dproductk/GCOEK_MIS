"""Dev-only setup: Electrical (EE) HOD + 3 teachers and 2 subjects per semester.

Mirrors create_entc_test_accounts.py. Idempotent — safe to re-run.

Usage:
    python create_ee_test_accounts.py

Creates:
- hod_ee (HOD + base FACULTY, dept-scoped to EE)
- faculty_ee1/2/3 (FACULTY, dept-scoped to EE), all password: Password123!
- 16 EE subjects (EE101..EE802, 2 per sem 1-8) linked into published
  all-programs Scheme G v1 with assessment components, so HOD subject-teacher
  assignment and eligibility workflows resolve for every semester.
"""
import os
import sys

import django

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gceok_core.settings')
django.setup()

from datetime import date

from apps.academic_structure.models import Department
from apps.authentication.models import Role, RoleAssignment, User
from apps.curriculum.models import Scheme, SchemeSubject, Subject
from apps.curriculum.services import ensure_assessment_components
from apps.faculty.models import Faculty

PASSWORD = 'Password123!'
dept = Department.objects.get(code='EE')
roles = {r.codename: r for r in Role.objects.all()}

accounts = [
    dict(username='hod_ee', email='hod.ee@gceok.ac.in', emp='HOD_EE01',
         fn='Vikram', ln='Jadhav', desig='HOD', role='HOD'),
    dict(username='faculty_ee1', email='faculty.ee1@gceok.ac.in', emp='EE_F01',
         fn='Rahul', ln='Pawar', desig='ASSISTANT_PROFESSOR', role='FACULTY'),
    dict(username='faculty_ee2', email='faculty.ee2@gceok.ac.in', emp='EE_F02',
         fn='Kavita', ln='Mane', desig='ASSISTANT_PROFESSOR', role='FACULTY'),
    dict(username='faculty_ee3', email='faculty.ee3@gceok.ac.in', emp='EE_F03',
         fn='Sachin', ln='Thorat', desig='ASSISTANT_PROFESSOR', role='FACULTY'),
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
    fac, _ = Faculty.objects.get_or_create(
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

# 2 Electrical subjects per semester (PCC theory: CA 20 + MSE 20 + ESE 60).
ee_subjects = [
    (1, 'EE101', 'Electrical Circuit Analysis I'),
    (1, 'EE102', 'Electromagnetic Fields'),
    (2, 'EE201', 'Electrical Circuit Analysis II'),
    (2, 'EE202', 'Digital Electronics'),
    (3, 'EE301', 'Electrical Machines I'),
    (3, 'EE302', 'Power Systems I'),
    (4, 'EE401', 'Electrical Machines II'),
    (4, 'EE402', 'Control Systems'),
    (5, 'EE501', 'Power Electronics'),
    (5, 'EE502', 'Microprocessors and Microcontrollers'),
    (6, 'EE601', 'Switchgear and Protection'),
    (6, 'EE602', 'Electric Drives'),
    (7, 'EE701', 'High Voltage Engineering'),
    (7, 'EE702', 'Smart Grid Technology'),
    (8, 'EE801', 'Power System Operation and Control'),
    (8, 'EE802', 'Electric Vehicles and Energy Storage'),
]
scheme = Scheme.objects.get(code='G', version=1)
order = {}
for sem, code, title in ee_subjects:
    obj, created = Subject.objects.get_or_create(
        code=code,
        defaults={'title': title, 'course_category': 'PCC', 'lecture_hours': 3,
                  'ca_max_marks': 20, 'mse_max_marks': 20, 'ese_max_marks': 60,
                  'credits': 3, 'is_active': True})
    obj.title = title
    obj.course_category = 'PCC'
    obj.lecture_hours = 3
    obj.ca_max_marks = 20
    obj.mse_max_marks = 20
    obj.ese_max_marks = 60
    obj.credits = 3
    obj.is_active = True
    obj.save()
    order[sem] = order.get(sem, 0) + 1
    ss, ss_created = SchemeSubject.objects.get_or_create(
        scheme=scheme, semester_number=sem, course_code=code,
        defaults={'subject': obj, 'credits': 3, 'total_marks': 100,
                  'display_order': order[sem]})
    ss.subject = obj
    ss.credits = 3
    ss.total_marks = 100
    ss.display_order = order[sem]
    ss.save()
    n = ensure_assessment_components(ss)
    print(f"OK subject={code} sem={sem} created={created} "
          f"scheme_link_created={ss_created} components={n}")

print('DONE')
