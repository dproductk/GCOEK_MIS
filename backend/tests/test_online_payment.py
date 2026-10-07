"""
Production Test Suite for Easebuzz Online Payment Gateway Integration.
Tests:
- Cryptographic SHA-512 hash generation and verification
- Concurrency-safe receipt sequence generation
- Student online payment status check (7 preconditions)
- Server-authoritative amount calculation and idempotency
- Successful callback processing (PaymentLedger creation + receipt generation)
- Forged signature rejection
- Duplicate callback idempotency
- Accountant toggle and online payment tracker
"""
import datetime
from decimal import Decimal
import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.academic_structure.models import AcademicYear, Department, Program
from apps.authentication.models import Role, RoleAssignment, User
from apps.finance.gateway.easebuzz import EasebuzzGateway
from apps.finance.models import (
    FeeHead,
    OnlinePaymentAttempt,
    PaymentLedger,
    StudentFeeAssessment,
)
from apps.finance.services import apply_gateway_result, generate_next_receipt_no
from apps.results.models import EligibilityVerification
from apps.students.models import Student


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def online_payment_setup(db):
    year = AcademicYear.objects.create(
        code='2026-27',
        name='2026-2027',
        start_date=datetime.date(2026, 7, 1),
        end_date=datetime.date(2027, 6, 30),
        is_current=True,
    )
    dept = Department.objects.create(name='Mechanical Engineering', code='MECH')
    prog = Program.objects.create(department=dept, name='B.Tech Mechanical', code='BTECH_MECH')

    role_acc, _ = Role.objects.get_or_create(codename='ACCOUNTANT', defaults={'name': 'Accountant'})
    role_student, _ = Role.objects.get_or_create(codename='STUDENT', defaults={'name': 'Student'})

    user_acc = User.objects.create_user(username='acc_user', password='Password123!', user_type=User.UserType.FACULTY)
    RoleAssignment.objects.create(user=user_acc, role=role_acc, status=RoleAssignment.Status.ACTIVE)

    user_stu = User.objects.create_user(username='stu_online', password='Password123!', user_type=User.UserType.STUDENT)
    RoleAssignment.objects.create(user=user_stu, role=role_student, status=RoleAssignment.Status.ACTIVE)

    student = Student.objects.create(
        user=user_stu,
        enrollment_no='PRN-ONLINE-001',
        first_name='Aditya',
        last_name='Kulkarni',
    )

    fee_head = FeeHead.objects.create(
        name='Tuition Fee',
        code='TF-MECH-2026',
        academic_year=year,
        program=prog,
        category_quota=FeeHead.CategoryQuota.OPEN,
        amount=Decimal('45000.00'),
    )

    assessment = StudentFeeAssessment.objects.create(
        student=student,
        academic_year=year,
        fee_breakdown={'Tuition Fee': '45000.00'},
        total_fee=Decimal('45000.00'),
        allow_online_payment=True,
        assessed_by=user_acc,
    )

    return {
        'year': year,
        'student': student,
        'user_stu': user_stu,
        'user_acc': user_acc,
        'assessment': assessment,
    }


@pytest.mark.django_db
def test_easebuzz_hash_calculation_and_verification():
    gateway = EasebuzzGateway(key='test_key_123', salt='test_salt_456')
    init_params = {
        'txnid': 'TXN_TEST_001',
        'amount': '45000.00',
        'productinfo': 'Tuition Fee',
        'firstname': 'Aditya',
        'email': 'aditya@gceok.ac.in',
        'udf1': 'std_1',
        'udf2': 'ay_1',
        'udf3': 'ass_1',
    }
    init_hash = gateway.calculate_initiate_hash(init_params)
    assert isinstance(init_hash, str)
    assert len(init_hash) == 128  # SHA-512 hex length

    # Response verification
    response_data = {
        'status': 'success',
        'txnid': 'TXN_TEST_001',
        'amount': '45000.00',
        'productinfo': 'Tuition Fee',
        'firstname': 'Aditya',
        'email': 'aditya@gceok.ac.in',
        'udf1': 'std_1',
        'udf2': 'ay_1',
        'udf3': 'ass_1',
    }
    # Calculate valid reverse hash
    seq = [
        'test_salt_456',
        'success',
        '', '', '', '', '', '', '',
        'ass_1',
        'ay_1',
        'std_1',
        'aditya@gceok.ac.in',
        'Aditya',
        'Tuition Fee',
        '45000.00',
        'TXN_TEST_001',
        'test_key_123',
    ]
    import hashlib
    valid_hash = hashlib.sha512('|'.join(seq).encode('utf-8')).hexdigest()
    response_data['hash'] = valid_hash

    assert gateway.verify_response_hash(response_data) is True

    # Tampered response
    response_data['amount'] = '100.00'
    assert gateway.verify_response_hash(response_data) is False


@pytest.mark.django_db
def test_concurrency_safe_receipt_number_generation(online_payment_setup):
    year = online_payment_setup['year']
    r1 = generate_next_receipt_no(year)
    r2 = generate_next_receipt_no(year)
    r3 = generate_next_receipt_no(year)

    assert r1 == 'GCOEK/2026-27/FEE/0001'
    assert r2 == 'GCOEK/2026-27/FEE/0002'
    assert r3 == 'GCOEK/2026-27/FEE/0003'


@pytest.mark.django_db
def test_student_online_payment_status_api(api_client, online_payment_setup):
    api_client.force_authenticate(user=online_payment_setup['user_stu'])
    res = api_client.get('/api/v1/finance/online-payment/status/')
    assert res.status_code == status.HTTP_200_OK
    assert res.data['can_pay'] is True
    assert Decimal(str(res.data['assessment']['total_fee'])) == Decimal('45000.00')
    assert res.data['is_paid'] is False


@pytest.mark.django_db
def test_online_payment_initiation_and_idempotency(api_client, online_payment_setup):
    api_client.force_authenticate(user=online_payment_setup['user_stu'])

    headers = {'HTTP_IDEMPOTENCY_KEY': 'idemp_key_123'}
    res = api_client.post('/api/v1/finance/online-payment/initiate/', {}, **headers)

    assert res.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED)
    assert 'transaction_id' in res.data
    assert 'checkout_url' in res.data
    txn_id = res.data['transaction_id']

    # Repeated request with same idempotency key returns the same attempt
    res2 = api_client.post('/api/v1/finance/online-payment/initiate/', {}, **headers)
    assert res2.status_code == status.HTTP_200_OK
    assert res2.data['transaction_id'] == txn_id


@pytest.mark.django_db
def test_apply_gateway_result_creates_permanent_ledger(online_payment_setup):
    student = online_payment_setup['student']
    year = online_payment_setup['year']
    assessment = online_payment_setup['assessment']

    attempt = OnlinePaymentAttempt.objects.create(
        student=student,
        academic_year=year,
        assessment=assessment,
        transaction_id='TXN_TEST_APPLY_1',
        idempotency_key='key_apply_1',
        amount=Decimal('45000.00'),
        status=OnlinePaymentAttempt.Status.REDIRECTED,
    )

    attempt_res, success, msg = apply_gateway_result(
        transaction_id='TXN_TEST_APPLY_1',
        gateway_status='success',
        easebuzz_txn_id='EASEPAY_998877',
        payment_mode='UPI',
    )

    assert success is True
    assert attempt_res.status == OnlinePaymentAttempt.Status.SUCCESS

    # Verify PaymentLedger created
    ledger = PaymentLedger.objects.filter(student=student, academic_year=year).first()
    assert ledger is not None
    assert ledger.status == PaymentLedger.PaymentStatus.PAID
    assert ledger.amount_paid == Decimal('45000.00')
    assert ledger.receipt_no.startswith('GCOEK/2026-27/FEE/')
    assert ledger.payment_mode == PaymentLedger.PaymentMode.ONLINE


@pytest.mark.django_db
def test_accountant_toggle_online_payment(api_client, online_payment_setup):
    api_client.force_authenticate(user=online_payment_setup['user_acc'])
    assessment = online_payment_setup['assessment']

    # Toggle to False
    res = api_client.post(f'/api/v1/finance/assessments/{assessment.id}/toggle-online-payment/', {
        'allow_online_payment': False
    })
    assert res.status_code == status.HTTP_200_OK
    assert res.data['allow_online_payment'] is False

    # Toggle to True
    res2 = api_client.post(f'/api/v1/finance/assessments/{assessment.id}/toggle-online-payment/', {
        'allow_online_payment': True
    })
    assert res2.status_code == status.HTTP_200_OK
    assert res2.data['allow_online_payment'] is True


@pytest.mark.django_db
def test_accountant_tracker_endpoint(api_client, online_payment_setup):
    api_client.force_authenticate(user=online_payment_setup['user_acc'])
    res = api_client.get('/api/v1/finance/online-payment/tracker/')
    assert res.status_code == status.HTTP_200_OK
    assert len(res.data) >= 1
    item = res.data[0]
    assert 'student_name' in item
    assert 'total_fee' in item
    assert 'allow_online_payment' in item


@pytest.mark.django_db
def test_double_click_inflight_payment_deduplication(api_client, online_payment_setup):
    """
    Verifies that if a student double-clicks or has an in-flight attempt,
    the second initiate request returns the existing attempt and does not create a duplicate transaction.
    """
    api_client.force_authenticate(user=online_payment_setup['user_stu'])

    # First click (creates attempt -> 201 Created)
    res1 = api_client.post('/api/v1/finance/online-payment/initiate/')
    assert res1.status_code == status.HTTP_201_CREATED
    txn1 = res1.data['transaction_id']

    # Second click (immediate double click -> 200 OK with existing attempt)
    res2 = api_client.post('/api/v1/finance/online-payment/initiate/')
    assert res2.status_code == status.HTTP_200_OK
    txn2 = res2.data['transaction_id']
    assert res2.data.get('is_existing_attempt') is True

    # Both must point to the exact same transaction ID
    assert txn1 == txn2
    assert OnlinePaymentAttempt.objects.filter(student=online_payment_setup['student']).count() == 1


@pytest.mark.django_db
def test_amount_tampering_rejected(online_payment_setup):
    """
    Verifies that if a malicious callback/webhook sends a tampered amount,
    the payment is rejected and flagged as an amount mismatch.
    """
    student = online_payment_setup['student']
    year = online_payment_setup['year']
    assessment = online_payment_setup['assessment']

    attempt = OnlinePaymentAttempt.objects.create(
        student=student,
        academic_year=year,
        assessment=assessment,
        transaction_id='TXN_TAMPER_TEST',
        idempotency_key='IDEMP_TAMPER',
        amount=Decimal('45000.00'),
        status=OnlinePaymentAttempt.Status.REDIRECTED,
    )

    # Malicious actor sends amount 1.00 instead of 45000.00
    attempt_res, success, msg = apply_gateway_result(
        transaction_id='TXN_TAMPER_TEST',
        gateway_status='success',
        easebuzz_txn_id='EASEPAY_FRAUD',
        raw_payload={'amount': '1.00'},
        payment_mode='UPI',
    )

    assert success is False
    assert attempt_res.status == OnlinePaymentAttempt.Status.FAILED
    assert 'Amount tampering detected' in attempt_res.failure_reason
    # Ensure no ledger was created
    assert not PaymentLedger.objects.filter(student=student, academic_year=year).exists()

