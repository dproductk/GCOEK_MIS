"""
Student Academic Lifecycle Services.
Implements CONTEXT.md Sec 7:
Promotion workflow:
Eligibility approved -> fees set -> fees paid -> student automatically moves to next year/semester.
Preserves historical enrollment records (marks previous as PROMOTED with is_current=False).
"""
from django.db import transaction
from django.utils import timezone

from apps.academic_structure.models import AcademicYear, Division, Semester
from apps.audit.models import AuditLog
from apps.audit.services import audit_log
from apps.finance.models import PaymentLedger
from apps.results.models import EligibilityVerification
from apps.students.models import Student, StudentEnrollment


def check_and_promote_student(student_id, actor=None, request=None):
    """
    Checks if student fulfills the three promotion prerequisites per CONTEXT.md Sec 7:
    1. Eligibility approved by HOD (final_eligible == True)
    2. Fees set & fees paid (PaymentLedger status == PAID or balance_due <= 0)

    If fulfilled, automatically promotes the student to target semester,
    updating the previous enrollment to PROMOTED and creating a new current enrollment.
    """
    with transaction.atomic():
        try:
            student = Student.objects.select_for_update().get(id=student_id)
        except Student.DoesNotExist:
            return False, 'Student not found.'

        current_enrollment = student.enrollments.filter(is_current=True).first()
        if not current_enrollment:
            return False, 'No active enrollment found for student.'

        # 1. Eligibility Check: must be HOD approved (final_eligible = True)
        latest_eligibility = student.eligibility_records.filter(
            final_eligible=True
        ).order_by('-target_semester__number').first()

        if not latest_eligibility:
            return False, 'No HOD-approved eligibility found.'

        target_sem = latest_eligibility.target_semester
        if target_sem.number <= current_enrollment.semester.number:
            return False, f'Target semester ({target_sem.number}) is not ahead of current semester ({current_enrollment.semester.number}).'

        # 2 & 3. Fees Set and Fees Paid Check
        # Check if there is a payment ledger where fees are set and fully paid
        paid_ledger = PaymentLedger.objects.filter(
            student=student,
            status=PaymentLedger.PaymentStatus.PAID,
        ).first()

        if not paid_ledger:
            paid_ledger = PaymentLedger.objects.filter(
                student=student,
                total_fee_due__gt=0,
                balance_due__lte=0,
            ).first()

        if not paid_ledger:
            return False, 'Fees have not been fully paid.'

        # Determine target academic year
        target_ay = latest_eligibility.academic_year or current_enrollment.academic_year

        # Determine target division (preserve same division name if available)
        target_div = None
        if current_enrollment.division:
            target_div = Division.objects.filter(
                department=current_enrollment.department,
                name=current_enrollment.division.name,
            ).first()

        # Archive old enrollment while preserving history
        old_sem_num = current_enrollment.semester.number
        current_enrollment.is_current = False
        current_enrollment.status = StudentEnrollment.Status.PROMOTED
        current_enrollment.save(update_fields=['is_current', 'status'])

        # Create new current enrollment for target semester
        # Scheme preserved: student stays in entry scheme (CONTEXT Sec 9).
        new_enrollment = StudentEnrollment.objects.create(
            student=student,
            academic_year=target_ay,
            department=current_enrollment.department,
            program=current_enrollment.program,
            semester=target_sem,
            division=target_div,
            scheme=current_enrollment.scheme,
            roll_number=current_enrollment.roll_number,
            status=StudentEnrollment.Status.ACTIVE,
            is_current=True,
        )

        if actor:
            audit_log(
                request=request,
                actor=actor,
                action=AuditLog.Action.UPDATE,
                target_type='StudentEnrollment',
                target_id=str(new_enrollment.id),
                target_display=f'{student.display_name} -> Sem {target_sem.number}',
                reason='Automatic promotion after HOD eligibility endorsement and fee payment',
                description=f'Student {student.display_name} automatically promoted from Sem {old_sem_num} to Sem {target_sem.number}.',
            )

        return True, f'Successfully promoted to Semester {target_sem.number}.'
