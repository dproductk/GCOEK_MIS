"""
Asynchronous, provider-independent email and notification service for Finance.
Guarantees:
- Dispatched asynchronously without blocking HTTP requests.
- Failure of email dispatch NEVER affects or rolls back financial records.
"""
import logging
from concurrent.futures import ThreadPoolExecutor
from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)

# Reusable daemon thread pool for non-blocking email dispatch
_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix='gceok_email_worker')


def _format_payment_email_body(attempt, ledger):
    student = attempt.student
    ay = attempt.academic_year.code
    amount = f"₹{attempt.amount:,.2f}"
    receipt_no = ledger.receipt_no
    txn_id = attempt.easebuzz_txn_id or attempt.transaction_id
    date_str = str(ledger.payment_date)

    return f"""Dear {student.display_name},

Greetings from Government College of Engineering, Kolhapur.

Your online admission fee payment has been successfully verified and officially recorded.

============================================================
FEE PAYMENT & OFFICIAL RECEIPT DETAILS
============================================================
Student Name      : {student.display_name}
Enrollment / PRN  : {student.enrollment_no or 'Pending / Onboarding'}
Academic Term     : {ay}
Amount Paid       : {amount}
Official Receipt  : {receipt_no}
Gateway Reference : {txn_id}
Payment Date      : {date_str}
Payment Mode      : Online Gateway (Easebuzz)
Status            : FULLY PAID
============================================================

Your official institutional fee receipt is available for download and printing in your GCOEK Student Portal under 'Payment History'.

If eligible, your semester progression / academic promotion has been processed automatically.

This is an automated institutional transaction receipt.

Government College of Engineering, Kolhapur (Autonomous)
Vidyanagar, Kolhapur, Maharashtra 416004
Accounts & Finance Section
"""


def _send_email_task(recipient_email, subject, message):
    """Worker task executed in background thread."""
    if not getattr(settings, 'EMAIL_ENABLED', True):
        logger.info("Email notifications disabled. Skipping email to %s", recipient_email)
        return

    from_addr = getattr(settings, 'EMAIL_FROM_ADDRESS', 'accounts@gceok.ac.in')
    provider = getattr(settings, 'EMAIL_PROVIDER', 'console').lower()

    try:
        if provider == 'console':
            logger.info("--- [CONSOLE EMAIL DISPATCH] ---\nTo: %s\nSubject: %s\n\n%s\n---------------------------------", recipient_email, subject, message)
            return

        send_mail(
            subject=subject,
            message=message,
            from_email=from_addr,
            recipient_list=[recipient_email],
            fail_silently=False,
        )
        logger.info("Payment confirmation email successfully sent to %s", recipient_email)
    except Exception as exc:
        logger.warning("Failed to send payment confirmation email to %s: %s", recipient_email, exc)


def send_payment_confirmation_email_async(attempt, ledger):
    """
    Non-blocking async dispatcher for payment confirmation emails.
    """
    student = attempt.student
    personal = getattr(student, 'personal_details', None)
    email = getattr(personal, 'student_email', None) or (student.user.email if student.user else None)

    if not email:
        logger.info("No email found for student %s. Skipping confirmation email.", student.display_name)
        return

    subject = f"Official Fee Receipt: {ledger.receipt_no} — GCOE Kolhapur"
    body = _format_payment_email_body(attempt, ledger)

    try:
        _executor.submit(_send_email_task, email, subject, body)
    except Exception as exc:
        logger.error("Could not schedule email background task: %s", exc)
