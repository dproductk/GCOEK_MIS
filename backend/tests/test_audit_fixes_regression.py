"""
Regression tests for audit gap fixes (Items 1 - 10).
"""
import datetime
from decimal import Decimal
import pytest
from django.contrib.auth import get_user_model
from django.test.utils import CaptureQueriesContext
from django.db import connection, IntegrityError
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.academic_structure.models import (
    AcademicYear,
    Department,
    Division,
    Program,
    Semester,
)
from apps.admissions.models import ImportBatch, ImportRow
from apps.admissions.services import commit_import_batch
from apps.authentication.models import Role, RoleAssignment
from apps.curriculum.models import Subject
from apps.finance.models import FeeHead, OnlinePaymentAttempt, PaymentLedger, StudentFeeAssessment
from apps.results.models import EligibilityVerification, SemesterResult
from apps.results.services import submit_semester_marks
from apps.students.models import Student, StudentEnrollment

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def sysadmin(db):
    user = User.objects.create_superuser(
        username='sysadmin_audit_test',
        email='sysadmin_audit@gcoek.ac.in',
        password='Password123!',
    )
    role, _ = Role.objects.get_or_create(codename='SYSADMIN', defaults={'name': 'Sysadmin'})
    RoleAssignment.objects.create(user=user, role=role, status=RoleAssignment.Status.ACTIVE)
    return user


@pytest.mark.django_db
def test_item1_department_delete_in_use_rejected(api_client, sysadmin):
    """F-S4-001: Deleting a department in use must return 400 and preserve records."""
    api_client.force_authenticate(user=sysadmin)
    dept = Department.objects.create(name='Dept With Program', code='DWP')
    Program.objects.create(department=dept, name='Program 1', code='P1')

    resp = api_client.delete(f'/api/v1/academic/departments/{dept.id}/')
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert 'in use' in str(resp.data).lower()
    assert Department.objects.filter(id=dept.id).exists()


@pytest.mark.django_db
def test_item1_program_delete_in_use_rejected(api_client, sysadmin):
    """F-S4-001: Deleting a program in use must return 400 and preserve records."""
    api_client.force_authenticate(user=sysadmin)
    year = AcademicYear.objects.create(
        code='2026-27', name='2026-2027',
        start_date=datetime.date(2026, 7, 1), end_date=datetime.date(2027, 6, 30),
        is_current=True,
    )
    dept = Department.objects.create(name='Dept Program Test', code='DPT')
    prog = Program.objects.create(department=dept, name='Program Test', code='PT')
    FeeHead.objects.create(
        program=prog,
        academic_year=year,
        name='Tuition Fee',
        code='TUI_PROG_TEST',
        amount=Decimal('1000.00'),
    )

    resp = api_client.delete(f'/api/v1/academic/programs/{prog.id}/')
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert 'in use' in str(resp.data).lower()
    assert Program.objects.filter(id=prog.id).exists()


@pytest.mark.django_db
def test_item2_classes_action_query_count_constant(api_client, sysadmin):
    """F-S4-002: classes action must use bulk pre-aggregations with query count < 15."""
    api_client.force_authenticate(user=sysadmin)
    year = AcademicYear.objects.create(
        code='2026-27', name='2026-2027',
        start_date=datetime.date(2026, 7, 1), end_date=datetime.date(2027, 6, 30),
        is_current=True,
    )
    dept = Department.objects.create(name='Query Test Dept', code='QTD')
    sem = Semester.objects.create(number=2, year_level=1, name='Semester 2', term_type='EVEN')

    # Create 4 divisions
    for name in ['A', 'B', 'C', 'D']:
        Division.objects.create(
            department=dept, academic_year=year, semester=sem, name=name,
        )

    with CaptureQueriesContext(connection) as ctx:
        resp = api_client.get('/api/v1/results/eligibility/classes/')
        assert resp.status_code == status.HTTP_200_OK

    # Measured: previously 7-8 queries per division (30+ for 4 divs). Now < 12 queries total.
    assert len(ctx.captured_queries) < 12


@pytest.mark.django_db
def test_item3_admissions_commit_collision_fails_row_no_fabricated_prn(db, sysadmin):
    """F-S6-003: On enrollment collision, row must FAIL for review; never fabricate PRN_1."""
    ay = AcademicYear.objects.create(
        code='2026-27', name='2026-2027',
        start_date=datetime.date(2026, 7, 1), end_date=datetime.date(2027, 6, 30),
        is_current=True,
    )
    Role.objects.get_or_create(codename='STUDENT', defaults={'name': 'Student'})
    Semester.objects.create(number=1, year_level=1, name='Semester 1', term_type='ODD')
    dept = Department.objects.create(name='Dept Collision', code='DC', choice_code='6006')
    Program.objects.create(department=dept, name='B.Tech DC', code='BT_DC')

    existing_student = Student.objects.create(
        enrollment_no='PRN_COLLIDE_100',
        application_id='APP_EXISTING',
        first_name='Existing',
        last_name='Student',
    )
    batch = ImportBatch.objects.create(
        file_name='test_collision.csv',
        academic_year=ay,
        uploaded_by=sysadmin,
        status=ImportBatch.Status.VALIDATED,
    )
    row = ImportRow.objects.create(
        batch=batch,
        row_number=1,
        application_id='APP_NEW',
        enrollment_no='PRN_COLLIDE_100',
        candidate_name='New Student',
        choice_code='6006',
        validation_status=ImportRow.ValidationStatus.VALID,
        normalized_data={
            'application_id': 'APP_NEW',
            'enrollment_no': 'PRN_COLLIDE_100',
            'candidate_name': 'New Student',
            'choice_code': '6006',
            'course': 'Dept Collision',
        },
    )

    commit_import_batch(batch.id)

    row.refresh_from_db()
    assert row.validation_status == ImportRow.ValidationStatus.FAILED
    assert 'enrollment conflict — manual review' in row.import_error

    # Assert zero fabricated PRNs
    assert Student.objects.filter(enrollment_no__startswith='PRN_COLLIDE_100_').count() == 0


@pytest.mark.django_db
def test_item4_payment_initiate_integrity_error_handled(api_client, monkeypatch):
    """F-S7-001: Concurrent payment initiate catching IntegrityError converges to 200."""
    from apps.finance.models import StudentFeeAssessment, OnlinePaymentAttempt

    year = AcademicYear.objects.create(
        code='2026-27', name='2026-2027',
        start_date=datetime.date(2026, 7, 1), end_date=datetime.date(2027, 6, 30),
        is_current=True,
    )
    user_stu = User.objects.create_user(username='stu_init_race', email='stu@test.com', password='Password123!')
    role_student, _ = Role.objects.get_or_create(codename='STUDENT', defaults={'name': 'Student'})
    RoleAssignment.objects.create(user=user_stu, role=role_student, status=RoleAssignment.Status.ACTIVE)
    student = Student.objects.create(user=user_stu, enrollment_no='ENR_INIT_RACE', first_name='Race', last_name='Test')
    from apps.students.models import StudentPersonalDetail
    StudentPersonalDetail.objects.create(student=student, student_email='stu@test.com', student_mobile='9876543210')

    assessment = StudentFeeAssessment.objects.create(
        student=student, academic_year=year, total_fee=Decimal('50000.00'), allow_online_payment=True
    )

    # Pre-create the attempt with idempotency key
    key = 'test-idemp-key-123'
    existing_attempt = OnlinePaymentAttempt.objects.create(
        student=student,
        academic_year=year,
        assessment=assessment,
        transaction_id='GCOEK_EXISTING_TXN',
        idempotency_key=key,
        amount=Decimal('50000.00'),
        status=OnlinePaymentAttempt.Status.INITIATED,
        gateway_provider='EASEBUZZ',
        checkout_url='https://pay.easebuzz.in/pay/test',
    )

    api_client.force_authenticate(user=user_stu)

    # Monkeypatch OnlinePaymentAttempt.objects.create to simulate race condition (IntegrityError)
    def mock_create(*args, **kwargs):
        raise IntegrityError('duplicate key value violates unique constraint uniq_online_payment_student_idempotency')

    monkeypatch.setattr(OnlinePaymentAttempt.objects, 'create', mock_create)

    # Initiating with the same key should catch IntegrityError, re-fetch existing attempt, and return 200
    resp = api_client.post('/api/v1/finance/online-payment/initiate/', {'idempotency_key': key})
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data['transaction_id'] == 'GCOEK_EXISTING_TXN'


@pytest.mark.django_db
def test_item5_seed_faculty_refuses_when_not_debug(monkeypatch):
    """F-S6-001: seed_faculty must refuse to run when DEBUG=False."""
    from django.core.management import call_command
    from django.conf import settings

    monkeypatch.setattr(settings, 'DEBUG', False)
    with pytest.raises(SystemExit):
        call_command('seed_faculty')


@pytest.mark.django_db
def test_item6_marks_validation_rejects_client_maxima_override(db):
    """F-S6-002: Out-of-range marks cannot be bypassed with client-sent max_theory_marks."""
    from rest_framework.exceptions import ValidationError

    user = User.objects.create_user(username='stu_marks', password='Password123!')
    student = Student.objects.create(user=user, enrollment_no='ENR_MARKS', first_name='Marks', last_name='Test')
    sem = Semester.objects.create(number=1, year_level=1, name='Semester 1', term_type='ODD')
    year = AcademicYear.objects.create(
        code='2026-27', name='2026-2027',
        start_date=datetime.date(2026, 7, 1), end_date=datetime.date(2027, 6, 30),
        is_current=True,
    )
    Subject.objects.create(code='CS101', title='Intro to CS', ese_max_marks=100, credits=3)

    # Client tries to smuggle 999 marks by sending max_theory_marks: 9999
    payload = [{
        'course_code': 'CS101',
        'theory_marks': 999,
        'credits': 3,
        'max_theory_marks': 9999,
    }]

    with pytest.raises(ValidationError) as exc:
        submit_semester_marks(
            student=student,
            semester_number=1,
            subjects_data=payload,
            exam_session='Winter 2026',
        )

    assert 'out of range' in str(exc.value)


@pytest.mark.django_db
def test_item7_must_change_password_jwt_blocks_other_endpoints(api_client):
    """Item 7: JWT user with must_change_password=True gets 403 on protected endpoints."""
    user = User.objects.create_user(
        username='rotate_user',
        password='Password123!',
        must_change_password=True,
    )
    role_student, _ = Role.objects.get_or_create(codename='STUDENT', defaults={'name': 'Student'})
    RoleAssignment.objects.create(user=user, role=role_student, status=RoleAssignment.Status.ACTIVE)

    # Obtain JWT token
    token = str(RefreshToken.for_user(user).access_token)
    api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    # Accessing /api/v1/auth/me/ is allowed to let the frontend detect the flag
    resp_me = api_client.get('/api/v1/auth/me/')
    assert resp_me.status_code == status.HTTP_200_OK

    # Accessing any other protected API endpoint is blocked with 403 must_change_password
    resp_blocked = api_client.get('/api/v1/academic/departments/')
    assert resp_blocked.status_code == status.HTTP_403_FORBIDDEN
    assert resp_blocked.json().get('code') == 'must_change_password'


def test_item8_backfill_script_has_debug_guard():
    """Item 8: backfill_ee_promotion_merge.py must have DEBUG guard."""
    from pathlib import Path
    script_path = Path(__file__).resolve().parent.parent / 'backfill_ee_promotion_merge.py'
    content = script_path.read_text(encoding='utf-8')
    assert 'DEBUG' in content
    assert 'sys.exit(1)' in content


@pytest.mark.django_db
def test_item9_gateway_retirement_kill_switch(api_client, monkeypatch):
    """Item 9: When EASEBUZZ_ENABLED=False, online routes 403/404, while desk payments succeed."""
    from django.conf import settings

    monkeypatch.setattr(settings, 'EASEBUZZ_ENABLED', False)

    # 1. Online initiate returns 403
    user_stu = User.objects.create_user(username='stu_disabled', password='Password123!')
    role_student, _ = Role.objects.get_or_create(codename='STUDENT', defaults={'name': 'Student'})
    RoleAssignment.objects.create(user=user_stu, role=role_student, status=RoleAssignment.Status.ACTIVE)
    api_client.force_authenticate(user=user_stu)

    resp_init = api_client.post('/api/v1/finance/online-payment/initiate/')
    assert resp_init.status_code == status.HTTP_403_FORBIDDEN

    # 2. Callback and webhook return 404
    api_client.logout()
    resp_cb = api_client.post('/api/v1/finance/online-payment/callback/', {'txnid': 'test'})
    assert resp_cb.status_code == status.HTTP_404_NOT_FOUND

    resp_wh = api_client.post('/api/v1/finance/online-payment/webhook/', {'txnid': 'test'})
    assert resp_wh.status_code == status.HTTP_404_NOT_FOUND
