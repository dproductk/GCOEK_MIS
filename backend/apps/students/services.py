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

        # Terminal fail can never be promoted, even with fees fully paid.
        if latest_eligibility.hod_status == EligibilityVerification.StageStatus.REJECTED:
            return False, 'Marked not eligible (failed). Fees do not matter.'

        target_sem = latest_eligibility.target_semester
        if target_sem.number <= current_enrollment.semester.number:
            return True, f'Student already active in Semester {current_enrollment.semester.number}.'

        # 2 & 3. Fees Set and Fees Paid Check
        # F-S5-001: Year-scoped — the fee must be PAID for the year being
        # COMPLETED (the student's current division year), not merely any
        # year. Stale prior-year payments must not trigger promotion.
        # Completing-year-first resolution: backfill cohorts carry a stale
        # enrollment/EV year from their import file while fees are assessed
        # and collected in the running year. Normal cohorts are unaffected
        # (division, EV and enrollment years coincide there).
        completing_ay = (
            (current_enrollment.division.academic_year if current_enrollment.division else None)
            or latest_eligibility.academic_year
            or current_enrollment.academic_year
        )
        fee_year = completing_ay
        paid_ledger = PaymentLedger.objects.filter(
            student=student,
            academic_year=fee_year,
            status=PaymentLedger.PaymentStatus.PAID,
        ).first()

        if not paid_ledger:
            paid_ledger = PaymentLedger.objects.filter(
                student=student,
                academic_year=fee_year,
                total_fee_due__gt=0,
                balance_due__lte=0,
            ).first()

        if not paid_ledger:
            return False, 'Fees have not been fully paid.'

        # Target academic year = the year being completed (running class year),
        # so the new enrollment lives in the current cycle, not a stale batch year.
        target_ay = completing_ay

        # Determine target division (preserve same division name if available)
        # Prefer a division in the SAME target semester, in the same academic
        # year as the student's current class (a promoted class keeps its year
        # identity; late fee payers auto-join the successor class this way).
        # Repeater student (Div R): auto-place into origin division or first standard division in target_sem.
        # Never fall back to a different-semester division: a silently wrong
        # division corrupts rosters and verification queues. When no matching
        # class exists yet, leave unassigned for HOD placement.
        target_div = None
        if current_enrollment.division:
            target_div_name = current_enrollment.division.name
            if target_div_name == 'R':
                prior_enr = student.enrollments.filter(
                    semester=current_enrollment.semester
                ).exclude(division__name='R').exclude(division__isnull=True).order_by('-created_at').first()
                if prior_enr and prior_enr.division:
                    target_div_name = prior_enr.division.name
                else:
                    target_div_name = 'A'

            same_name = Division.objects.filter(
                department=current_enrollment.department,
                semester=target_sem,
                name=target_div_name,
            )
            target_div = same_name.filter(
                academic_year=current_enrollment.division.academic_year
            ).first() or same_name.order_by('-academic_year__start_date').first()

            if not target_div and current_enrollment.division.name == 'R':
                target_div = Division.objects.filter(
                    department=current_enrollment.department,
                    semester=target_sem,
                ).exclude(name='R').order_by('name').first()

        # Archive old enrollment while preserving history
        old_div = current_enrollment.division
        old_sem_num = current_enrollment.semester.number
        current_enrollment.is_current = False
        current_enrollment.status = StudentEnrollment.Status.PROMOTED
        current_enrollment.save(update_fields=['is_current', 'status'])

        # Create new current enrollment for target semester
        # Scheme preserved: student stays in entry scheme (CONTEXT Sec 9).
        # Seated-by-promotion into an HOD-created class counts as HOD
        # placement (prerequisites were HOD endorsement + full payment), so
        # it lands confirmed and never re-asks on the pending-imports queue.
        # Unassigned (no class exists yet) stays unconfirmed for HOD pickup.
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
            placement_confirmed=target_div is not None,
        )

        # Trigger empty-class flip for regular class (Div R repeaters never flip)
        if old_div and old_div.name != 'R' and old_div.semester.number in (2, 4, 6):
            remaining = StudentEnrollment.objects.filter(
                division=old_div, is_current=True, semester__number=old_sem_num
            ).count()
            if remaining == 0:
                from apps.academic_structure.services import flip_class_to_next_semester
                dest_div, _ = flip_class_to_next_semester(
                    old_div, target_sem, actor=actor, request=request
                )
                if dest_div and new_enrollment.division is None:
                    new_enrollment.division = dest_div
                    new_enrollment.placement_confirmed = True
                    new_enrollment.save(update_fields=['division', 'placement_confirmed', 'updated_at'])

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
