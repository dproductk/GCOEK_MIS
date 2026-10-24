"""
Authoritative Finance Services for GCOEK MIS.
Implements:
- Concurrency-safe institutional receipt generation (<ROMAN><YY><YY>-<nnnn>, e.g. IV2627-0001)
- Centralized payment result service (apply_gateway_result)
- Single source of truth for converting verified gateway results into permanent college records
- Fail-safe decoupling: Payment success remains permanent even if downstream promotion or email fails
"""
import logging
import re
from decimal import Decimal
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.audit.services import audit_log
from apps.finance.models import (
    FeeReceiptCounter,
    OnlinePaymentAttempt,
    PaymentLedger,
    StudentFeeAssessment,
)
from apps.finance.notifications import send_payment_confirmation_email_async
from apps.students.services import check_and_promote_student

logger = logging.getLogger(__name__)

# Roman numerals for year levels: 1st year -> I, 2nd -> II, 3rd -> III, 4th -> IV.
ROMAN_YEAR_LEVELS = {1: 'I', 2: 'II', 3: 'III', 4: 'IV'}


def _current_semester_number(student):
    """Semester number of the candidate's current enrollment (None if absent)."""
    from apps.students.models import StudentEnrollment

    if student is None or getattr(student, 'pk', None) is None:
        return None
    return StudentEnrollment.objects.filter(
        student=student, is_current=True,
    ).values_list('semester__number', flat=True).first()


def _roman_year_level(current_semester):
    """
    Map the candidate's semester at payment time to the roman year level the
    fee is being paid FOR. Candidates usually pay at the tail of a year, just
    before promotion:
      - new admission (sem 1)            -> I
      - sem 2 (entering 2nd year, sem 3) -> II
      - sem 4 / sem 5                    -> III
      - sem 6 (entering sem 7) / sem 7   -> IV
      - sem 8                            -> IV (clamped)
    Missing enrollment data falls back to 'I' (new admission).
    """
    try:
        n = int(current_semester)
    except (TypeError, ValueError):
        return 'I'
    return ROMAN_YEAR_LEVELS[min(4, max(1, n // 2 + 1))]


def _compact_year_code(code):
    """
    Compact an academic year code for the receipt number.

    Both ``2026-27`` and ``2026-2027`` become ``2627`` (last two digits of
    each year). Unexpected formats fall back to the digits present.
    """
    parts = re.findall(r'\d+', str(code or ''))
    if len(parts) >= 2:
        return f'{parts[0][-2:]}{parts[1][-2:]}'
    return parts[0][-2:] if parts else str(code or '').strip()


def generate_next_receipt_no(academic_year, current_semester=None):
    """
    Concurrency-safe sequence generator for official institutional receipts.
    Format: <roman year level><YY><YY>-<sequence:04d>
            e.g. IV2627-0001 for a candidate entering the 4th year in 2026-27.
    Serializes allocation via SELECT FOR UPDATE on FeeReceiptCounter row.
    Auto-initializes to the maximum existing sequence from PaymentLedger if the
    counter is new, including receipts issued in the legacy
    <roman>-<academic_year.code>-<nnnn> format so numbering continues without
    restarting or colliding after the format change.
    """
    roman = _roman_year_level(current_semester)
    base = f'{roman}{_compact_year_code(academic_year.code)}-'
    legacy_base = f'{roman}-{academic_year.code}-'
    counter, created = FeeReceiptCounter.objects.select_for_update().get_or_create(
        academic_year=academic_year,
        prefix=roman,
        defaults={'last_sequence': 0},
    )

    if created or counter.last_sequence == 0:
        # Determine existing max in database for this year+prefix so sequence never collides.
        # Scan both the current compact format and the legacy hyphenated format.
        existing = PaymentLedger.objects.filter(
            Q(receipt_no__startswith=base) | Q(receipt_no__startswith=legacy_base)
        ).values_list('receipt_no', flat=True)
        max_n = 0
        pattern = re.compile(r'-(\d{4,})$')
        for r in existing:
            m = pattern.search(str(r))
            if m:
                try:
                    max_n = max(max_n, int(m.group(1)))
                except ValueError:
                    pass
        counter.last_sequence = max_n

    counter.last_sequence += 1
    counter.save(update_fields=['last_sequence', 'updated_at'])
    return f'{base}{counter.last_sequence:04d}'


def apply_gateway_result(
    transaction_id,
    gateway_status,
    easebuzz_txn_id='',
    raw_payload=None,
    payment_mode='ONLINE',
    actor=None,
    request=None,
):
    """
    Central, authoritative payment result processor.
    Safely applies a verified Easebuzz result into the college financial ledger.
    All callbacks, webhooks, and manual reconciliations pass through this service.

    Returns:
        tuple: (attempt: OnlinePaymentAttempt, success: bool, message: str)
    """
    raw_payload = raw_payload or {}
    ledger = None

    with transaction.atomic():
        try:
            attempt = OnlinePaymentAttempt.objects.select_for_update().get(
                transaction_id=transaction_id
            )
        except OnlinePaymentAttempt.DoesNotExist:
            logger.error("Payment attempt with txnid '%s' not found.", transaction_id)
            return None, False, f"Payment attempt '{transaction_id}' does not exist."

        # Idempotency check: Already processed successfully?
        if attempt.status == OnlinePaymentAttempt.Status.SUCCESS:
            logger.info("Payment attempt '%s' was already applied successfully. Idempotent return.", transaction_id)
            return attempt, True, "Payment already recorded and confirmed."

        norm_status = str(gateway_status or '').strip().lower()
        is_success = norm_status in ('success', 'successful')

        if not is_success:
            # Payment failed, cancelled, or pending
            if norm_status in ('usercancelled', 'user_cancelled', 'cancelled'):
                attempt.status = OnlinePaymentAttempt.Status.CANCELLED
            elif norm_status in ('pending', 'initiated', 'in_process'):
                attempt.status = OnlinePaymentAttempt.Status.PENDING
            elif norm_status in ('expired',):
                attempt.status = OnlinePaymentAttempt.Status.EXPIRED
            else:
                attempt.status = OnlinePaymentAttempt.Status.FAILED

            attempt.easebuzz_txn_id = easebuzz_txn_id or attempt.easebuzz_txn_id
            attempt.easebuzz_status = gateway_status
            attempt.failure_reason = raw_payload.get('error_desc') or raw_payload.get('error') or f"Status: {gateway_status}"
            attempt.raw_callback_payload = raw_payload
            attempt.completed_at = timezone.now()
            attempt.save(update_fields=['status', 'easebuzz_txn_id', 'easebuzz_status', 'failure_reason', 'raw_callback_payload', 'completed_at'])

            audit_log(
                request=request,
                actor=actor,
                action=AuditLog.Action.UPDATE,
                target_type='OnlinePaymentAttempt',
                target_id=str(attempt.id),
                target_display=f"Online Payment {attempt.transaction_id}",
                new_value={'status': attempt.status, 'easebuzz_status': gateway_status},
                reason='Online gateway payment state update',
                description=f"Online payment attempt {attempt.transaction_id} transitioned to {attempt.status} ({attempt.failure_reason}).",
            )
            return attempt, False, f"Payment was not successful (Status: {attempt.status})."

        # F-S5-003: SECURITY CHECK: Verify payload amount matches attempt.amount authoritatively
        # Run tamper check BEFORE existing_ledger duplicate check to avoid marking tampered payloads SUCCESS.
        payload_amt = raw_payload.get('amount')
        if payload_amt is not None:
            try:
                if Decimal(str(payload_amt)) != attempt.amount:
                    logger.critical(
                        "SECURITY ALERT: Amount tampering detected for txnid %s. Expected %s, received %s.",
                        transaction_id, attempt.amount, payload_amt
                    )
                    attempt.status = OnlinePaymentAttempt.Status.FAILED
                    attempt.failure_reason = f"Security: Amount tampering detected (Expected {attempt.amount}, received {payload_amt})"
                    attempt.raw_callback_payload = raw_payload
                    attempt.completed_at = timezone.now()
                    attempt.save(update_fields=['status', 'failure_reason', 'raw_callback_payload', 'completed_at'])
                    audit_log(
                        request=request,
                        actor=actor,
                        action=AuditLog.Action.UPDATE,
                        target_type='OnlinePaymentAttempt',
                        target_id=str(attempt.id),
                        target_display=f"Online Payment {attempt.transaction_id}",
                        old_value={'status': 'PENDING', 'expected_amount': str(attempt.amount)},
                        new_value={'status': 'FAILED', 'received_amount': str(payload_amt)},
                        reason='Amount tampering detected',
                        description=f"Amount mismatch on online transaction {transaction_id}: expected ₹{attempt.amount}, received ₹{payload_amt}.",
                    )
                    return attempt, False, "Security verification failed: amount mismatch."
            except Exception as e:
                logger.error("Error validating payload amount: %s", str(e))
                return attempt, False, "Amount validation error."

        # Verify whether student already has a PAID ledger for this academic year
        existing_ledger = PaymentLedger.objects.filter(
            student=attempt.student,
            academic_year=attempt.academic_year,
        ).first()

        if existing_ledger and (existing_ledger.status == PaymentLedger.PaymentStatus.PAID or existing_ledger.balance_due <= 0):
            logger.warning("Duplicate payment attempt blocked: Student %s already has paid ledger %s.", attempt.student.display_name, existing_ledger.receipt_no)
            attempt.status = OnlinePaymentAttempt.Status.SUCCESS
            attempt.completed_at = timezone.now()
            attempt.save(update_fields=['status', 'completed_at'])
            audit_log(
                request=request,
                actor=actor,
                action=AuditLog.Action.UPDATE,
                target_type='OnlinePaymentAttempt',
                target_id=str(attempt.id),
                target_display=f"Online Payment {attempt.transaction_id}",
                old_value={'status': 'PENDING'},
                new_value={
                    'status': attempt.status,
                    'blocked_as_duplicate': True,
                    'existing_receipt': existing_ledger.receipt_no,
                },
                reason='Duplicate online payment blocked — fee already settled',
                description=(
                    f"Blocked duplicate online attempt {attempt.transaction_id} for "
                    f"{attempt.student.display_name}: receipt {existing_ledger.receipt_no} already PAID."
                ),
            )
            return attempt, True, "Fee was already settled for this candidate."

        # SUCCESS PATH: Create official permanent PaymentLedger row with concurrency protection.
        # The insert runs in its own savepoint so a unique-violation rolls
        # back ONLY the insert — the outer transaction stays usable for the
        # conflicting-ledger lookup, attempt update, and audit below.
        # (Without this, Postgres aborts the whole txn and every later query
        # raises TransactionManagementError.)
        ledger = None
        try:
            with transaction.atomic():
                receipt_no = generate_next_receipt_no(
                    attempt.academic_year,
                    _current_semester_number(attempt.student),
                )
                try:
                    _ass = attempt.assessment
                    _snap = _ass.fee_breakdown if isinstance(getattr(_ass, 'fee_breakdown', None), dict) else {}
                except Exception:
                    _snap = {}
                ledger = PaymentLedger.objects.create(
                    receipt_no=receipt_no,
                    student=attempt.student,
                    academic_year=attempt.academic_year,
                    total_fee_due=attempt.amount,
                    amount_paid=attempt.amount,
                    balance_due=Decimal('0.00'),
                    payment_mode=PaymentLedger.PaymentMode.ONLINE,
                    transaction_ref=easebuzz_txn_id or attempt.transaction_id,
                    status=PaymentLedger.PaymentStatus.PAID,
                    # IST local date for the official receipt. Bare .date() on
                    # timezone.now() is UTC and stamps verified payments made
                    # 00:00–05:30 IST with the previous day's date.
                    payment_date=timezone.localtime(timezone.now()).date(),
                    collected_by=actor if (actor and actor.is_authenticated) else None,
                    remarks=f"Easebuzz Online Payment (Txn: {attempt.transaction_id}, EasepayID: {easebuzz_txn_id})",
                    fee_snapshot=dict(_snap or {}),
                    fee_types_snapshot=PaymentLedger.build_head_types_map(
                        attempt.academic_year, _snap),
                )
        except IntegrityError as exc:
            logger.warning(
                "IntegrityError creating PaymentLedger for %s (concurrent worker race): %s",
                attempt.student.display_name, exc
            )
            # Fetch the row the parallel transaction committed. A PARTIAL
            # offline row is NOT a successful online payment — never mark the
            # attempt SUCCESS for it; the desk must resolve it first.
            ledger = PaymentLedger.objects.filter(
                student=attempt.student,
                academic_year=attempt.academic_year,
            ).first()
            if not ledger:
                raise exc
            if not (ledger.status == PaymentLedger.PaymentStatus.PAID or ledger.balance_due <= 0):
                attempt.status = OnlinePaymentAttempt.Status.FAILED
                attempt.failure_reason = (
                    f"Fee already partially recorded under receipt {ledger.receipt_no}; "
                    "contact the accounts desk before retrying online."
                )
                attempt.raw_callback_payload = raw_payload
                attempt.completed_at = timezone.now()
                attempt.save(update_fields=['status', 'failure_reason', 'raw_callback_payload', 'completed_at'])
                audit_log(
                    request=request,
                    actor=actor,
                    action=AuditLog.Action.UPDATE,
                    target_type='OnlinePaymentAttempt',
                    target_id=str(attempt.id),
                    target_display=f"Online Payment {attempt.transaction_id}",
                    new_value={'status': attempt.status, 'existing_receipt': ledger.receipt_no},
                    reason='Online payment collides with partial offline ledger',
                    description=(
                        f"Online attempt {attempt.transaction_id} for "
                        f"{attempt.student.display_name} blocked: partial receipt "
                        f"{ledger.receipt_no} already exists."
                    ),
                )
                return attempt, False, attempt.failure_reason

        attempt.status = OnlinePaymentAttempt.Status.SUCCESS
        attempt.easebuzz_txn_id = easebuzz_txn_id or attempt.easebuzz_txn_id
        attempt.easebuzz_status = gateway_status
        attempt.payment_mode = payment_mode
        attempt.raw_callback_payload = raw_payload
        attempt.completed_at = timezone.now()
        attempt.save(update_fields=[
            'status', 'easebuzz_txn_id', 'easebuzz_status',
            'payment_mode', 'raw_callback_payload', 'completed_at'
        ])

        audit_log(
            request=request,
            actor=actor,
            action=AuditLog.Action.PAYMENT,
            target_type='PaymentLedger',
            target_id=str(ledger.id),
            target_display=f"Receipt {ledger.receipt_no}",
            new_value={
                'receipt_no': ledger.receipt_no,
                'amount_paid': str(ledger.amount_paid),
                'total_fee_due': str(ledger.total_fee_due),
                'payment_mode': ledger.payment_mode,
                'transaction_ref': ledger.transaction_ref,
                'gateway_txnid': attempt.transaction_id,
                'easebuzz_txn_id': attempt.easebuzz_txn_id,
            },
            reason='Online fee payment capture',
            description=f"Successfully verified online fee payment of {ledger.amount_paid} for {attempt.student.display_name} via Easebuzz.",
        )

    # -------------------------------------------------------------------------
    # CRITICAL FAILURE RULE (Prompt Section 19):
    # Payment success and promotion must NEVER create an unsafe rollback.
    # If promotion or email fails, payment remains safely committed and PAID.
    # -------------------------------------------------------------------------
    promotion_success = False
    promotion_msg = ''
    try:
        promotion_success, promotion_msg = check_and_promote_student(
            attempt.student_id,
            actor=actor,
            request=request,
        )
        if promotion_success:
            logger.info("Student %s automatically promoted: %s", attempt.student.display_name, promotion_msg)
        else:
            logger.warning("Promotion check for %s returned false: %s", attempt.student.display_name, promotion_msg)
    except Exception as exc:
        logger.exception("Unexpected exception in check_and_promote_student for student %s: %s", attempt.student_id, exc)

    # Async email notification
    try:
        send_payment_confirmation_email_async(attempt, ledger)
    except Exception as exc:
        logger.warning("Could not dispatch confirmation email for txn %s: %s", attempt.transaction_id, exc)

    return attempt, True, f"Fee payment verified successfully! Receipt {ledger.receipt_no} generated."
