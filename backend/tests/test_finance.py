"""
Automated tests for Finance, Fee Head Configuration, and Payment Ledger.
Tests:
- FeeHead creation and category breakdown
- PaymentLedger balance calculation, status transitions (PAID vs PARTIAL)
- Student self-access to their fee receipts via /api/v1/finance/ledger/my_payments/
- Scope security: Student cannot inspect or mutate accountant records or other student ledgers
- Analytics endpoint aggregation
"""
import datetime
from decimal import Decimal
import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.academic_structure.models import AcademicYear, Department, Program
from apps.authentication.models import Role, RoleAssignment, User
from apps.finance.models import FeeHead, PaymentLedger
from apps.students.models import Student


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def finance_setup(db):
    year = AcademicYear.objects.create(
        code='2026-27', name='2026-2027',
        start_date=datetime.date(2026, 7, 1), end_date=datetime.date(2027, 6, 30),
        is_current=True
    )
    dept = Department.objects.create(name='Computer Science and Engineering', code='CSE')
    prog = Program.objects.create(department=dept, name='B.Tech Computer Science', code='BTECH_CSE')

    role_acc, _ = Role.objects.get_or_create(codename='ACCOUNTANT', defaults={'name': 'Accountant'})
    role_student, _ = Role.objects.get_or_create(codename='STUDENT', defaults={'name': 'Student'})

    user_acc = User.objects.create_user(username='accountant_user', password='Password123!', user_type=User.UserType.FACULTY)
    RoleAssignment.objects.create(user=user_acc, role=role_acc, status=RoleAssignment.Status.ACTIVE)

    user_stu1 = User.objects.create_user(username='student1', password='Password123!', user_type=User.UserType.STUDENT)
    RoleAssignment.objects.create(user=user_stu1, role=role_student, status=RoleAssignment.Status.ACTIVE)
    stu1 = Student.objects.create(
        user=user_stu1,
        enrollment_no='PRN-FIN-001',
        first_name='Rahul',
        last_name='Shinde',
    )

    user_stu2 = User.objects.create_user(username='student2', password='Password123!', user_type=User.UserType.STUDENT)
    RoleAssignment.objects.create(user=user_stu2, role=role_student, status=RoleAssignment.Status.ACTIVE)
    stu2 = Student.objects.create(
        user=user_stu2,
        enrollment_no='PRN-FIN-002',
        first_name='Pooja',
        last_name='Patil',
    )

    fee_head = FeeHead.objects.create(
        name='Tuition Fee',
        code='TF-OPEN-2026',
        academic_year=year,
        program=prog,
        category_quota=FeeHead.CategoryQuota.OPEN,
        amount=Decimal('65000.00'),
    )

    ledger1 = PaymentLedger.objects.create(
        student=stu1,
        academic_year=year,
        receipt_no='GCOEK/2026/TEST/001',
        total_fee_due=Decimal('65000.00'),
        amount_paid=Decimal('65000.00'),
        payment_mode=PaymentLedger.PaymentMode.ONLINE,
        transaction_ref='TXN-TEST-12345',
        payment_date=datetime.date.today(),
        collected_by=user_acc,
    )

    ledger2 = PaymentLedger.objects.create(
        student=stu2,
        academic_year=year,
        receipt_no='GCOEK/2026/TEST/002',
        total_fee_due=Decimal('65000.00'),
        amount_paid=Decimal('35000.00'),
        payment_mode=PaymentLedger.PaymentMode.CHALLAN,
        payment_date=datetime.date.today(),
        collected_by=user_acc,
    )

    return {
        'year': year,
        'prog': prog,
        'user_acc': user_acc,
        'user_stu1': user_stu1,
        'user_stu2': user_stu2,
        'stu1': stu1,
        'stu2': stu2,
        'fee_head': fee_head,
        'ledger1': ledger1,
        'ledger2': ledger2,
    }


@pytest.mark.django_db
def test_payment_ledger_status_and_balance(finance_setup):
    ledger1 = finance_setup['ledger1']
    assert ledger1.balance_due == Decimal('0.00')
    assert ledger1.status == PaymentLedger.PaymentStatus.PAID

    ledger2 = finance_setup['ledger2']
    assert ledger2.balance_due == Decimal('30000.00')
    assert ledger2.status == PaymentLedger.PaymentStatus.PARTIAL


@pytest.mark.django_db
def test_student_my_payments_self_service(api_client, finance_setup):
    api_client.force_authenticate(user=finance_setup['user_stu1'])
    response = api_client.get('/api/v1/finance/ledger/my-payments/')
    assert response.status_code == status.HTTP_200_OK
    assert len(response.data) == 1
    assert response.data[0]['receipt_no'] == 'GCOEK/2026/TEST/001'
    assert Decimal(str(response.data[0]['amount_paid'])) == Decimal('65000.00')


@pytest.mark.django_db
def test_student_cannot_access_full_ledger_list(api_client, finance_setup):
    """Students querying ledger should only receive their own records."""
    api_client.force_authenticate(user=finance_setup['user_stu1'])
    response = api_client.get('/api/v1/finance/ledger/')
    for record in response.data.get('results', response.data):
        assert record['enrollment_no'] == finance_setup['stu1'].enrollment_no


@pytest.mark.django_db
def test_duplicate_payment_blocked_for_same_student_year(api_client, finance_setup):
    """Marking fee twice for the same student+year must be rejected (400), not duplicated."""
    api_client.force_authenticate(user=finance_setup['user_acc'])
    payload = {
        'student': str(finance_setup['stu1'].id),
        'academic_year': str(finance_setup['year'].id),
        'receipt_no': 'GCOEK/2026/TEST/DUP',
        'total_fee_due': '65000.00',
        'amount_paid': '65000.00',
        'payment_mode': PaymentLedger.PaymentMode.ONLINE,
        'transaction_ref': 'TXN-DUP-1',
        'payment_date': datetime.date.today().isoformat(),
    }
    # stu1 already has a PAID ledger for this year in fixtures
    response = api_client.post('/api/v1/finance/ledger/', payload)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert PaymentLedger.objects.filter(student=finance_setup['stu1']).count() == 1


@pytest.mark.django_db
def test_accountant_can_view_analytics(api_client, finance_setup):
    api_client.force_authenticate(user=finance_setup['user_acc'])
    response = api_client.get('/api/v1/finance/ledger/analytics/')
    assert response.status_code == status.HTTP_200_OK
    assert 'total_collected' in response.data
    assert Decimal(str(response.data['total_collected'])) == Decimal('100000.00')
    assert Decimal(str(response.data['total_due'])) == Decimal('130000.00')
    assert response.data['total_receipts'] == 2


@pytest.mark.django_db
def test_fee_head_changes_are_audited(api_client, finance_setup):
    """Fee-head create/update/delete each write audit entries (sysadmin-visible)."""    """Fee-head create/update/delete each write audit entries (sysadmin-visible)."""
    from apps.audit.models import AuditLog
    admin = User.objects.create(username='audit_admin', email='aa@x.in',
                                user_type='SYSADMIN', is_superuser=True, is_staff=True)
    admin.set_password('TestPass12345!'); admin.save()
    api_client.force_authenticate(user=admin)
    before = AuditLog.objects.filter(target_type='FeeHead').count()
    created = api_client.post('/api/v1/finance/fee-heads/', {
        'name': 'Tuition Audit', 'code': 'TUA',
        'academic_year': str(finance_setup['year'].id),
        'program': str(finance_setup['prog'].id),
        'category_quota': 'OPEN', 'amount': '10000'}, format='json')
    assert created.status_code in (200, 201), created.data
    head_id = created.data['id']
    api_client.patch(f'/api/v1/finance/fee-heads/{head_id}/', {'amount': '12000'}, format='json')
    api_client.delete(f'/api/v1/finance/fee-heads/{head_id}/')
    actions = list(AuditLog.objects.filter(target_type='FeeHead').order_by('timestamp').values_list('action', flat=True)[before:])
    assert actions == ['CREATE', 'UPDATE', 'DELETE'], actions


@pytest.mark.django_db
def test_recorded_ledger_fully_immutable(api_client, finance_setup):
    """Recorded rows are permanent at any status: update/destroy always blocked."""
    from apps.finance.models import PaymentLedger
    api_client.force_authenticate(user=finance_setup['user_acc'])
    for ledger in (finance_setup['ledger1'], finance_setup['ledger2']):
        res = api_client.patch(f'/api/v1/finance/ledger/{ledger.id}/',
                               {'remarks': 'tamper'}, format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        res = api_client.delete(f'/api/v1/finance/ledger/{ledger.id}/')
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert PaymentLedger.objects.filter(id=ledger.id).exists()


@pytest.mark.django_db
def test_assessment_api_validates_and_freezes_on_payment(api_client, finance_setup):
    """Set Fee via API: preset validation, total==sum, frozen once PAID."""
    from apps.finance.models import FeeHead, PaymentLedger, StudentFeeAssessment
    head = finance_setup['fee_head']
    head.allowed_amounts = [65000]
    head.save(update_fields=['allowed_amounts'])
    api_client.force_authenticate(user=finance_setup['user_acc'])
    stu2 = finance_setup['stu2']
    year = finance_setup['year']
    # Wrong preset rejected.
    bad = api_client.post('/api/v1/finance/assessments/', {
        'student': str(stu2.id), 'academic_year': str(year.id),
        'fee_breakdown': {'Tuition Fee': 60000}, 'total_fee': '60000'}, format='json')
    assert bad.status_code == status.HTTP_400_BAD_REQUEST
    # Total mismatch rejected.
    bad2 = api_client.post('/api/v1/finance/assessments/', {
        'student': str(stu2.id), 'academic_year': str(year.id),
        'fee_breakdown': {'Tuition Fee': 65000}, 'total_fee': '60000'}, format='json')
    assert bad2.status_code == status.HTTP_400_BAD_REQUEST
    # Correct assessment accepted + readable back.
    ok = api_client.post('/api/v1/finance/assessments/', {
        'student': str(stu2.id), 'academic_year': str(year.id),
        'fee_breakdown': {'Tuition Fee': 65000}, 'total_fee': '65000'}, format='json')
    assert ok.status_code in (200, 201), ok.data
    got = api_client.get(f"/api/v1/finance/assessments/?student={stu2.id}&academic_year={year.id}")
    rows = got.data['results'] if isinstance(got.data, dict) else got.data
    assert len(rows) == 1 and str(rows[0]['total_fee']) == '65000.00'
    # Duplicate assessment blocked.
    dup = api_client.post('/api/v1/finance/assessments/', {
        'student': str(stu2.id), 'academic_year': str(year.id),
        'fee_breakdown': {'Tuition Fee': 65000}, 'total_fee': '65000'}, format='json')
    assert dup.status_code == status.HTTP_400_BAD_REQUEST
    # Complete the fixture's PARTIAL payment -> PAID -> assessment frozen.
    # (Recorded rows are immutable via API, so settle it at ORM level.)
    from apps.finance.models import PaymentLedger as _PL
    from decimal import Decimal as _Decimal
    part = _PL.objects.get(student=stu2, academic_year=year)
    assert part.status != _PL.PaymentStatus.PAID
    part.amount_paid = _Decimal('65000')
    part.save()
    assert part.status == _PL.PaymentStatus.PAID
    frozen = api_client.patch(f"/api/v1/finance/assessments/{ok.data['id']}/",
                              {'total_fee': '65000', 'fee_breakdown': {'Tuition Fee': 65000}},
                              format='json')
    assert frozen.status_code == status.HTTP_400_BAD_REQUEST
    assert StudentFeeAssessment.objects.filter(student=stu2).count() == 1


@pytest.mark.django_db
def test_untouched_zero_head_breaks_whole_save(api_client, finance_setup):
    """Production regression: a second head whose presets exclude 0 (e.g. ID
    card fee [50, 100]) rejects the entire assessment when the desk leaves it
    at the form's old blind-0 default. The UI now defaults to the first
    preset; the API must keep rejecting off-preset values with a clear
    head-naming message."""
    from apps.finance.models import FeeHead
    year = finance_setup['year']
    FeeHead.objects.create(
        name='ID card fee', code='ID-2026', academic_year=year,
        program=finance_setup['prog'],
        category_quota=FeeHead.CategoryQuota.OPEN, amount=50,
        allowed_amounts=[50, 100],
    )
    api_client.force_authenticate(user=finance_setup['user_acc'])
    stu1 = finance_setup['stu1']
    bad = api_client.post('/api/v1/finance/assessments/', {
        'student': str(stu1.id), 'academic_year': str(year.id),
        'fee_breakdown': {'Tuition Fee': 65000, 'ID card fee': 0},
        'total_fee': '65000'}, format='json')
    assert bad.status_code == status.HTTP_400_BAD_REQUEST
    assert 'ID card fee' in str(bad.data)
    ok = api_client.post('/api/v1/finance/assessments/', {
        'student': str(stu1.id), 'academic_year': str(year.id),
        'fee_breakdown': {'Tuition Fee': 65000, 'ID card fee': 50},
        'total_fee': '65050'}, format='json')
    assert ok.status_code in (200, 201), ok.data


@pytest.mark.django_db
def test_manual_marking_happy_path_receipt_backend_generated(api_client, finance_setup):
    """Manual desk happy path: Set Fee -> Mark Fee succeeds once, receipt is backend-generated."""
    import datetime
    from apps.authentication.models import Role, RoleAssignment, User
    from apps.finance.models import PaymentLedger
    from apps.students.models import Student

    head = finance_setup['fee_head']
    head.allowed_amounts = [65000]
    head.save(update_fields=['allowed_amounts'])
    year = finance_setup['year']
    api_client.force_authenticate(user=finance_setup['user_acc'])

    # Fresh student with no ledger yet.
    role_student, _ = Role.objects.get_or_create(codename='STUDENT', defaults={'name': 'Student'})
    u = User.objects.create_user(username='manual_happy', password='Password123!', user_type=User.UserType.STUDENT)
    RoleAssignment.objects.create(user=u, role=role_student, status=RoleAssignment.Status.ACTIVE)
    stu = Student.objects.create(user=u, enrollment_no='PRN-FIN-HAPPY', first_name='Amit', last_name='Patil')

    # 1. Mark without Set Fee -> blocked.
    no_set = api_client.post('/api/v1/finance/ledger/', {
        'student': str(stu.id), 'academic_year': str(year.id),
        'total_fee_due': '65000.00', 'amount_paid': '65000.00',
        'payment_mode': PaymentLedger.PaymentMode.CASH,
        'transaction_ref': 'CASH-1', 'payment_date': datetime.date.today().isoformat(),
    }, format='json')
    assert no_set.status_code == status.HTTP_400_BAD_REQUEST

    # 2. Set Fee.
    ok = api_client.post('/api/v1/finance/assessments/', {
        'student': str(stu.id), 'academic_year': str(year.id),
        'fee_breakdown': {'Tuition Fee': 65000}, 'total_fee': '65000'}, format='json')
    assert ok.status_code in (200, 201), ok.data

    # 3. Half payment rejected (university rule: full payment only).
    half = api_client.post('/api/v1/finance/ledger/', {
        'student': str(stu.id), 'academic_year': str(year.id),
        'total_fee_due': '65000.00', 'amount_paid': '35000.00',
        'payment_mode': PaymentLedger.PaymentMode.CASH,
        'transaction_ref': 'CASH-HALF', 'payment_date': datetime.date.today().isoformat(),
    }, format='json')
    assert half.status_code == status.HTTP_400_BAD_REQUEST

    # 4. Full payment succeeds even when client sends a fake receipt_no;
    # backend must ignore it and generate GCOEK/<year>/FEE/<nnnn>.
    good = api_client.post('/api/v1/finance/ledger/', {
        'student': str(stu.id), 'academic_year': str(year.id),
        'receipt_no': 'MY-BILL-123',
        'total_fee_due': '65000.00', 'amount_paid': '65000.00',
        'payment_mode': PaymentLedger.PaymentMode.CASH,
        'transaction_ref': 'CASH-2', 'payment_date': datetime.date.today().isoformat(),
    }, format='json')
    assert good.status_code in (200, 201), good.data
    assert good.data['receipt_no'] != 'MY-BILL-123'
    assert good.data['receipt_no'].startswith('GCOEK/')
    assert good.data['status'] == PaymentLedger.PaymentStatus.PAID

    # 5. Second marking blocked (duplicate).
    dup = api_client.post('/api/v1/finance/ledger/', {
        'student': str(stu.id), 'academic_year': str(year.id),
        'total_fee_due': '65000.00', 'amount_paid': '65000.00',
        'payment_mode': PaymentLedger.PaymentMode.CASH,
        'transaction_ref': 'CASH-3', 'payment_date': datetime.date.today().isoformat(),
    }, format='json')
    assert dup.status_code == status.HTTP_400_BAD_REQUEST
    assert PaymentLedger.objects.filter(student=stu, academic_year=year).count() == 1


@pytest.mark.django_db
def test_receipt_carries_fee_breakdown(api_client, finance_setup):
    """Detailed bill: my-payments receipt must include the pay-head breakup."""
    from apps.finance.models import StudentFeeAssessment
    stu1 = finance_setup['stu1']
    year = finance_setup['year']
    StudentFeeAssessment.objects.create(
        student=stu1, academic_year=year,
        fee_breakdown={'Tuition Fee': '60000.00', 'Development Fee': '5000.00'},
        total_fee=Decimal('65000.00'),
    )
    api_client.force_authenticate(user=finance_setup['user_stu1'])
    response = api_client.get('/api/v1/finance/ledger/my-payments/')
    assert response.status_code == status.HTTP_200_OK
    row = response.data[0]
    assert row['fee_breakdown'] == {'Tuition Fee': '60000.00', 'Development Fee': '5000.00'}


@pytest.mark.django_db
def test_receipt_without_assessment_yields_empty_breakdown(api_client, finance_setup):
    """Old receipts with no assessment still serialize (empty breakup)."""
    api_client.force_authenticate(user=finance_setup['user_stu1'])
    response = api_client.get('/api/v1/finance/ledger/my-payments/')
    assert response.status_code == status.HTTP_200_OK
    assert response.data[0]['fee_breakdown'] == {}
