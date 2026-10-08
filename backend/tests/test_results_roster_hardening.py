"""
Regression tests: faculty result-verification pages must never 500 on messy data.

Covers class-roster + classes for a class teacher when records contain:
- SemesterResult with null sgpa/cgpa and NOT_YET_HELD status
- EligibilityVerification with NULL class_teacher/hod (no Faculty profile)
- Student with no result and no EV row at all
- Promoted-out enrollment row alongside current rows
- Unassigned division access still 403 for class teachers
"""
import datetime

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status

from apps.academic_structure.models import (
    AcademicYear, Department, Division, Program, Semester,
)
from apps.authentication.models import Role, RoleAssignment
from apps.results.models import EligibilityVerification, SemesterResult
from apps.students.models import Student, StudentEnrollment

User = get_user_model()


@pytest.fixture
def api_client():
    from rest_framework.test import APIClient
    return APIClient()


def _make_setup():
    year = AcademicYear.objects.create(
        code='2026-27', name='2026-2027',
        start_date=datetime.date(2026, 7, 1), end_date=datetime.date(2027, 6, 30),
        is_current=True)
    dept = Department.objects.create(name='Electronics and Telecommunication', code='ETC')
    prog = Program.objects.create(department=dept, name='B.Tech ETC', code='BTECH_ETC')
    sem6 = Semester.objects.create(number=6, name='Semester 6', year_level=3, term_type='EVEN')
    sem7 = Semester.objects.create(number=7, name='Semester 7', year_level=4, term_type='ODD')

    teacher = User.objects.create_user(username='ct_harden', password='Password123!', user_type=User.UserType.FACULTY)
    ct_role, _ = Role.objects.get_or_create(codename='CLASS_TEACHER', defaults={'name': 'Class Teacher'})
    div = Division.objects.create(department=dept, academic_year=year, semester=sem6, name='A', class_teacher=teacher)
    RoleAssignment.objects.create(user=teacher, role=ct_role, division_id=div.id, status='ACTIVE')
    fac_role, _ = Role.objects.get_or_create(codename='FACULTY', defaults={'name': 'Faculty'})
    RoleAssignment.objects.create(user=teacher, role=fac_role, status='ACTIVE')

    def _student(tag, **kw):
        kw.setdefault('display_name', f'Student {tag}')
        kw.setdefault('enrollment_no', f'EN56{tag}')
        kw.setdefault('application_id', f'APP56{tag}')
        s = Student.objects.create(first_name='S', last_name=tag, **kw)
        StudentEnrollment.objects.create(
            student=s, academic_year=year, department=dept, program=prog,
            semester=sem6, division=div, status='ACTIVE', is_current=True)
        return s

    # 1. Normal: published PASS result + teacher-approved EV (no staff FKs set).
    s_ok = _student('OK01')
    SemesterResult.objects.create(
        student=s_ok, academic_year=year, semester=sem6, is_published=True,
        result_status=SemesterResult.ResultStatus.PASS, sgpa='8.10', cgpa='7.90',
        total_credits_registered=20, total_credits_earned=20)
    EligibilityVerification.objects.create(
        student=s_ok, academic_year=year, target_semester=sem7, department=dept,
        active_backlog_count=0,
        calculated_status=EligibilityVerification.CalculatedStatus.ELIGIBLE,
        class_teacher_status=EligibilityVerification.StageStatus.APPROVED,
        hod_status=EligibilityVerification.StageStatus.PENDING, final_eligible=False)

    # 2. Messy: NOT_YET_HELD result with null sgpa/cgpa, no EV row at all.
    s_bare = _student('BARE02')
    SemesterResult.objects.create(
        student=s_bare, academic_year=year, semester=sem6, is_published=True,
        result_status=SemesterResult.ResultStatus.NOT_YET_HELD,
        sgpa=None, cgpa=None, total_credits_registered=0, total_credits_earned=0)

    # 3. Flagged EV with NULL teacher/hod FKs (exercises staff_display_name fallback).
    s_flag = _student('FLAG03')
    SemesterResult.objects.create(
        student=s_flag, academic_year=year, semester=sem6, is_published=True,
        result_status=SemesterResult.ResultStatus.ATKT, sgpa='5.40',
        total_credits_registered=20, total_credits_earned=14)
    EligibilityVerification.objects.create(
        student=s_flag, academic_year=year, target_semester=sem7, department=dept,
        active_backlog_count=2,
        calculated_status=EligibilityVerification.CalculatedStatus.PROVISIONAL,
        class_teacher_status=EligibilityVerification.StageStatus.FLAGGED,
        class_teacher_remarks='Marks mismatch in one subject.',
        hod_status=EligibilityVerification.StageStatus.PENDING, final_eligible=False,
        class_teacher=None, hod=None)

    # 4. No result, no EV at all.
    _student('NONE04')

    # 5. Promoted-out row (old PROMOTED enrollment + current ahead, no division).
    s_move = Student.objects.create(
        first_name='S', last_name='MOVE05', display_name='Student MOVE05',
        enrollment_no='EN56MOVE05', application_id='APP56MOVE05')
    old = StudentEnrollment.objects.create(
        student=s_move, academic_year=year, department=dept, program=prog,
        semester=sem6, division=div, status='ACTIVE', is_current=True)
    old.is_current = False
    old.status = StudentEnrollment.Status.PROMOTED
    old.save(update_fields=['is_current', 'status'])
    StudentEnrollment.objects.create(
        student=s_move, academic_year=year, department=dept, program=prog,
        semester=sem7, division=None, status='ACTIVE', is_current=True)

    return teacher, div, dept


@pytest.mark.django_db
def test_roster_survives_messy_data(api_client):
    teacher, div, _ = _make_setup()
    api_client.force_authenticate(user=teacher)

    res = api_client.get(f'/api/v1/results/eligibility/class-roster/?division_id={div.id}')
    assert res.status_code == status.HTTP_200_OK, res.data
    roster = res.json()
    assert roster['total_students'] == 4
    assert roster['skipped_rows'] == 0
    by_id = {s['student_id']: s for s in roster['students']}

    ok = next(s for s in roster['students'] if s['enrollment_no'] == 'EN56OK01')
    assert ok['result_filled'] is True
    assert ok['semester_result']['sgpa'] == '8.10'
    assert ok['pipeline_stage'] == 'HOD_PENDING'

    bare = next(s for s in roster['students'] if s['enrollment_no'] == 'EN56BARE02')
    assert bare['result_filled'] is False
    assert bare['pipeline_stage'] == 'RESULT_PENDING'

    flag = next(s for s in roster['students'] if s['enrollment_no'] == 'EN56FLAG03')
    assert flag['pipeline_stage'] == 'FLAGGED'
    assert flag['class_teacher_name'] == ''
    assert 'Marks mismatch' in (flag['class_teacher_remarks'] or '')

    assert len(roster['promoted_students']) == 1
    assert roster['promoted_students'][0]['current_semester'] == 7


@pytest.mark.django_db
def test_classes_survives_messy_data(api_client):
    teacher, div, _ = _make_setup()
    api_client.force_authenticate(user=teacher)
    res = api_client.get('/api/v1/results/eligibility/classes/')
    assert res.status_code == status.HTTP_200_OK
    card = next((c for c in res.json() if c['division_id'] == str(div.id)), None)
    assert card is not None
    assert card['total_students'] == 4
    assert card['results_filled_count'] == 2


@pytest.mark.django_db
def test_unassigned_division_stays_forbidden(api_client):
    teacher, _, _ = _make_setup()
    other_dept = Department.objects.create(name='Other', code='OTH')
    year = AcademicYear.objects.filter(is_current=True).first()
    sem = Semester.objects.filter(number=6).first()
    other = Division.objects.create(department=other_dept, academic_year=year, semester=sem, name='Z')
    api_client.force_authenticate(user=teacher)
    res = api_client.get(f'/api/v1/results/eligibility/class-roster/?division_id={other.id}')
    assert res.status_code == status.HTTP_403_FORBIDDEN
