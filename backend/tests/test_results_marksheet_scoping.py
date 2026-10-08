"""
The verification modal fetches GET /results/semester-results/?student_id=<id>.
The list endpoint used to ignore that parameter and return other students'
marksheets mixed together (duplicate semester cards + cross-student data leak
during HOD endorsement). These tests lock the scoped filter in place.
"""
import datetime

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from apps.academic_structure.models import (
    AcademicYear, Department, Division, Program, Semester,
)
from apps.authentication.models import Role, RoleAssignment
from apps.results.models import SemesterResult
from apps.students.models import Student, StudentEnrollment

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def marksheet_setup(db):
    year = AcademicYear.objects.create(
        code='2026-27', name='2026-2027',
        start_date=datetime.date(2026, 7, 1), end_date=datetime.date(2027, 6, 30),
        is_current=True)
    dept = Department.objects.create(name='Electronics and Telecommunication', code='ETC')
    other_dept = Department.objects.create(name='Mechanical', code='MECH')
    prog = Program.objects.create(department=dept, name='B.Tech ETC', code='BTECH_ETC')
    prog2 = Program.objects.create(department=other_dept, name='B.Tech MECH', code='BTECH_MECH')
    sem6 = Semester.objects.create(number=6, name='Semester 6', year_level=3, term_type='EVEN')

    teacher = User.objects.create_user(username='ct_scope', password='Password123!', user_type=User.UserType.FACULTY)
    div = Division.objects.create(department=dept, academic_year=year, semester=sem6, name='A', class_teacher=teacher)
    ct_role, _ = Role.objects.get_or_create(codename='CLASS_TEACHER', defaults={'name': 'Class Teacher'})
    RoleAssignment.objects.create(user=teacher, role=ct_role, division_id=div.id, status='ACTIVE')

    hod = User.objects.create_user(username='hod_scope', password='Password123!', user_type=User.UserType.FACULTY)
    hod_role, _ = Role.objects.get_or_create(codename='HOD', defaults={'name': 'HOD'})
    RoleAssignment.objects.create(user=hod, role=hod_role, department_id=dept.id, status='ACTIVE')

    def _student(username, dept_o, prog_o, div_o, enr):
        u = User.objects.create_user(username=username, password='Password123!', user_type=User.UserType.STUDENT)
        s_role, _ = Role.objects.get_or_create(codename='STUDENT', defaults={'name': 'Student'})
        RoleAssignment.objects.create(user=u, role=s_role, status='ACTIVE')
        s = Student.objects.create(user=u, first_name='S', last_name=username,
                                   display_name=f'Student {username}',
                                   enrollment_no=enr, application_id=f'APP{enr}')
        StudentEnrollment.objects.create(
            student=s, academic_year=year, department=dept_o, program=prog_o,
            semester=sem6, division=div_o, status='ACTIVE', is_current=True)
        SemesterResult.objects.create(
            student=s, academic_year=year, semester=sem6, is_published=True,
            exam_session='Summer 2026', result_status=SemesterResult.ResultStatus.PASS,
            sgpa='7.50', total_credits_registered=3, total_credits_earned=3)
        return u, s

    stu_u, stu = _student('scope_a', dept, prog, div, 'EN60A01')
    other_div = Division.objects.create(department=other_dept, academic_year=year, semester=sem6, name='A')
    stu2_u, stu2 = _student('scope_b', other_dept, prog2, other_div, 'EN60B01')
    return {'teacher': teacher, 'hod': hod, 'div': div, 'stu': stu, 'stu_u': stu_u,
            'stu2': stu2, 'stu2_u': stu2_u}


@pytest.mark.django_db
def test_hod_sees_only_requested_student(api_client, marksheet_setup):
    api_client.force_authenticate(user=marksheet_setup['hod'])
    res = api_client.get(f"/api/v1/results/semester-results/?student_id={marksheet_setup['stu'].id}")
    assert res.status_code == status.HTTP_200_OK
    rows = res.json() if isinstance(res.json(), list) else res.json().get('results', [])
    assert len(rows) == 1
    assert rows[0]['student_id'] == str(marksheet_setup['stu'].id)


@pytest.mark.django_db
def test_hod_cannot_pull_cross_dept_student(api_client, marksheet_setup):
    api_client.force_authenticate(user=marksheet_setup['hod'])
    res = api_client.get(f"/api/v1/results/semester-results/?student_id={marksheet_setup['stu2'].id}")
    assert res.status_code == status.HTTP_200_OK
    rows = res.json() if isinstance(res.json(), list) else res.json().get('results', [])
    assert rows == []


@pytest.mark.django_db
def test_teacher_sees_own_division_student(api_client, marksheet_setup):
    api_client.force_authenticate(user=marksheet_setup['teacher'])
    res = api_client.get(f"/api/v1/results/semester-results/?student_id={marksheet_setup['stu'].id}")
    assert res.status_code == status.HTTP_200_OK
    rows = res.json() if isinstance(res.json(), list) else res.json().get('results', [])
    assert len(rows) == 1


@pytest.mark.django_db
def test_student_cannot_pull_other_student(api_client, marksheet_setup):
    api_client.force_authenticate(user=marksheet_setup['stu2_u'])
    res = api_client.get(f"/api/v1/results/semester-results/?student_id={marksheet_setup['stu'].id}")
    assert res.status_code == status.HTTP_200_OK
    rows = res.json() if isinstance(res.json(), list) else res.json().get('results', [])
    assert all(r['student_id'] != str(marksheet_setup['stu'].id) for r in rows)
