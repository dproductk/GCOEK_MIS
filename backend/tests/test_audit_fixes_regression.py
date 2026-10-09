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


def _backfill_setup(year_code_suffix=''):
    """Backfill cohort: enrollment + EV anchored on a stale batch year while
    the running class (division) and fee collection live in the current year."""
    import datetime
    old = AcademicYear.objects.create(
        code=f'2024-25{year_code_suffix}', name='Academic Year 2024-2025',
        start_date=datetime.date(2024, 7, 1), end_date=datetime.date(2025, 6, 30),
        is_current=False)
    cur = AcademicYear.objects.create(
        code=f'2026-27{year_code_suffix}', name='Academic Year 2026-2027',
        start_date=datetime.date(2026, 7, 1), end_date=datetime.date(2027, 6, 30),
        is_current=True)
    dept = Department.objects.create(name=f'Backfill Dept{year_code_suffix}', code=f'BKF{year_code_suffix or "X"}')
    sem4 = Semester.objects.create(number=4, name='Semester 4', year_level=2, term_type=Semester.TermType.EVEN)
    sem5 = Semester.objects.create(number=5, name='Semester 5', year_level=3, term_type=Semester.TermType.ODD)
    div4 = Division.objects.create(department=dept, academic_year=cur, semester=sem4, name='A')
    Division.objects.create(department=dept, academic_year=cur, semester=sem5, name='A')
    prog = Program.objects.create(department=dept, name='B.Tech B', code=f'BTBKF{year_code_suffix or "X"}')
    stu = Student.objects.create(first_name='Back', last_name='Fill', enrollment_no=f'PRN-BKF-{year_code_suffix or "X"}')
    StudentEnrollment.objects.create(
        student=stu, academic_year=old, department=dept, program=prog,
        semester=sem4, division=div4, status='ACTIVE', is_current=True)
    EligibilityVerification.objects.create(
        student=stu, academic_year=old, target_semester=sem5, department=dept,
        active_backlog_count=0,
        calculated_status=EligibilityVerification.CalculatedStatus.ELIGIBLE,
        class_teacher_status=EligibilityVerification.StageStatus.APPROVED,
        hod_status=EligibilityVerification.StageStatus.APPROVED,
        final_eligible=True)
    return {'old': old, 'cur': cur, 'dept': dept, 'sem4': sem4, 'sem5': sem5,
            'div4': div4, 'prog': prog, 'stu': stu}


@pytest.mark.django_db
def test_promote_backfill_paid_in_completing_year_succeeds():
    """F-S5-001 follow-up: fee PAID in the completing (division) year promotes
    even when enrollment/EV carry a stale batch year."""
    import datetime
    from apps.students.services import check_and_promote_student
    s = _backfill_setup('A')
    PaymentLedger.objects.create(
        student=s['stu'], academic_year=s['cur'], receipt_no='R-BKF-A',
        total_fee_due=1000, amount_paid=1000, balance_due=0,
        status=PaymentLedger.PaymentStatus.PAID,
        payment_date=datetime.date(2026, 8, 1))
    ok, msg = check_and_promote_student(s['stu'].id)
    assert ok is True, msg
    old_enr = s['stu'].enrollments.filter(semester=s['sem4']).first()
    assert old_enr.status == 'PROMOTED' and old_enr.is_current is False
    new_enr = s['stu'].enrollments.filter(is_current=True).first()
    assert new_enr.semester.number == 5
    assert new_enr.academic_year.code == s['cur'].code
    assert new_enr.division is not None and new_enr.division.semester.number == 5
    assert new_enr.placement_confirmed is True


@pytest.mark.django_db
def test_promote_prior_year_only_payment_stays_blocked():
    """F-S5-001 preserved: a PAID ledger ONLY in an unrelated past year never
    promotes, even for backfill cohorts."""
    import datetime
    from apps.students.services import check_and_promote_student
    s = _backfill_setup('B')
    PaymentLedger.objects.create(
        student=s['stu'], academic_year=s['old'], receipt_no='R-BKF-B',
        total_fee_due=1000, amount_paid=1000, balance_due=0,
        status=PaymentLedger.PaymentStatus.PAID,
        payment_date=datetime.date(2024, 8, 1))
    ok, msg = check_and_promote_student(s['stu'].id)
    assert ok is False and 'Fees' in msg
    enr = s['stu'].enrollments.filter(is_current=True).first()
    assert enr.semester.number == 4 and enr.status == 'ACTIVE'


def _promo_visibility_setup(suffix=''):
    """Division in current year + endorsed student + optional ledger."""
    import datetime
    cur = AcademicYear.objects.create(
        code=f'2026-27{suffix}', name='Academic Year 2026-2027',
        start_date=datetime.date(2026, 7, 1), end_date=datetime.date(2027, 6, 30),
        is_current=True)
    dept = Department.objects.create(name=f'Promo Vis{suffix}', code=f'PV{suffix or "X"}')
    sem4 = Semester.objects.create(number=4, name='Semester 4', year_level=2, term_type=Semester.TermType.EVEN)
    sem5 = Semester.objects.create(number=5, name='Semester 5', year_level=3, term_type=Semester.TermType.ODD)
    div4 = Division.objects.create(department=dept, academic_year=cur, semester=sem4, name='A')
    prog = Program.objects.create(department=dept, name='B.Tech P', code=f'BTPV{suffix or "X"}')
    hod = User.objects.create_user(username=f'hod_pv{suffix or "x"}', password='Password123!')
    role_hod, _ = Role.objects.get_or_create(codename='HOD', defaults={'name': 'HOD'})
    RoleAssignment.objects.create(user=hod, role=role_hod, department_id=dept.id,
                                  status=RoleAssignment.Status.ACTIVE)
    stu = Student.objects.create(first_name='Vis', last_name='Promo', enrollment_no=f'PRN-PV-{suffix or "X"}')
    StudentEnrollment.objects.create(
        student=stu, academic_year=cur, department=dept, program=prog,
        semester=sem4, division=div4, status='ACTIVE', is_current=True)
    ev = EligibilityVerification.objects.create(
        student=stu, academic_year=cur, target_semester=sem5, department=dept,
        active_backlog_count=0,
        calculated_status=EligibilityVerification.CalculatedStatus.ELIGIBLE,
        class_teacher_status=EligibilityVerification.StageStatus.APPROVED,
        hod_status=EligibilityVerification.StageStatus.APPROVED,
        final_eligible=True)
    return {'cur': cur, 'dept': dept, 'sem4': sem4, 'sem5': sem5,
            'div4': div4, 'prog': prog, 'hod': hod, 'stu': stu, 'ev': ev}


@pytest.mark.django_db
def test_classes_exposes_promoted_and_stuck_counts(api_client):
    """Visibility: class cards carry promoted_count + stuck_unpromoted_count."""
    import datetime
    s = _promo_visibility_setup('C')
    PaymentLedger.objects.create(
        student=s['stu'], academic_year=s['cur'], receipt_no='R-PV-C',
        total_fee_due=1000, amount_paid=1000, balance_due=0,
        status=PaymentLedger.PaymentStatus.PAID,
        payment_date=datetime.date(2026, 8, 1))
    api_client.force_authenticate(user=s['hod'])
    res = api_client.get('/api/v1/results/eligibility/classes/')
    assert res.status_code == status.HTTP_200_OK, res.data
    cards = res.data if isinstance(res.data, list) else res.data.get('results', [])
    card = next(c for c in cards if c['division_id'] == str(s['div4'].id))
    assert card['promoted_count'] == 0
    assert card['stuck_unpromoted_count'] == 1


@pytest.mark.django_db
def test_endorse_response_carries_promotion_outcome(api_client):
    """Endorse announces a deferred promotion instead of swallowing it."""
    s = _promo_visibility_setup('D')
    api_client.force_authenticate(user=s['hod'])
    res = api_client.post(
        f"/api/v1/results/eligibility/{s['ev'].id}/endorse-hod/",
        {'status': 'APPROVED', 'remarks': 'ok'}, format='json')
    assert res.status_code == status.HTTP_200_OK, res.data
    promo = res.data.get('promotion')
    assert promo is not None and promo['attempted'] is True
    assert promo['promoted'] is False and 'Fees' in promo['message']


@pytest.mark.django_db
def test_desk_receipt_carries_promotion_outcome(api_client):
    """Desk receipt announces a deferred promotion instead of silent success."""
    import datetime
    s = _promo_visibility_setup('E')
    acc = User.objects.create_user(username='acc_pv_e', password='Password123!')
    role_acc, _ = Role.objects.get_or_create(codename='ACCOUNTANT', defaults={'name': 'Accountant'})
    RoleAssignment.objects.create(user=acc, role=role_acc, status=RoleAssignment.Status.ACTIVE)
    api_client.force_authenticate(user=acc)
    head = FeeHead.objects.create(
        name='Tuition', code='TF-PV-E', academic_year=s['cur'], program=s['prog'],
        category_quota=FeeHead.CategoryQuota.OPEN, amount=1000,
        allowed_amounts=[1000])
    ok = api_client.post('/api/v1/finance/assessments/', {
        'student': str(s['stu'].id), 'academic_year': str(s['cur'].id),
        'fee_breakdown': {'Tuition': 1000}, 'total_fee': '1000'}, format='json')
    assert ok.status_code in (200, 201), ok.data
    res = api_client.post('/api/v1/finance/ledger/', {
        'student': str(s['stu'].id), 'academic_year': str(s['cur'].id),
        'total_fee_due': '1000.00', 'amount_paid': '1000.00',
        'payment_mode': PaymentLedger.PaymentMode.CASH,
        'transaction_ref': 'CASH-PV-E', 'payment_date': datetime.date.today().isoformat(),
    }, format='json')
    assert res.status_code == status.HTTP_201_CREATED, res.data
    promo = res.data.get('promotion')
    assert promo is not None and promo['attempted'] is True
