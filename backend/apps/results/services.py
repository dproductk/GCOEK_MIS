"""
Results Engine, 9-Point Grade Evaluator, and Eligibility Workflow Service.
"""
from decimal import Decimal
from django.db import transaction
from django.utils import timezone

from apps.academic_structure.models import AcademicYear, Department, Semester
from apps.results.models import EligibilityVerification, SemesterResult, SubjectResult
from apps.students.models import Student, StudentEnrollment


YEAR_CHANGE_TARGETS = {3, 5, 7}
"""Semesters entered only through the yearly verification cycle."""


def _require_student_ready_for_review(student, reviewer=None):
    """
    Student-side prerequisites for any teacher/HOD eligibility review.

    1. The student must have filled all details and locked their profile
       (one-time self-service lock).
    2. EVERY semester from 1 up to the student's current semester must have
       a published result (lateral-entry DSY students start at 3, since Sem
       1-2 never exist for them). WITHHELD/PASS/ATKT/FAIL count as filled;
       only missing rows and NOT_YET_HELD block.

    Raises rest_framework ValidationError (400) with a human-readable
    reason so the teacher UI can show exactly what is blocking review.
    Reads profile_locked fresh (the EV's cached student row may be stale).

    Sysadmin / superuser bypass the gate (admin corrections must never
    deadlock on a student prerequisite); teachers and HODs never do.
    """
    from rest_framework.exceptions import ValidationError

    if reviewer is not None and (
        getattr(reviewer, 'is_superuser', False)
    ):
        return
    if reviewer is not None:
        try:
            from apps.authentication.permissions import user_has_role as _has_role
            if _has_role(reviewer, 'SYSADMIN'):
                return
        except Exception:
            pass

    locked = Student.objects.filter(id=student.id).values_list('profile_locked', flat=True).first()
    if not locked:
        raise ValidationError(
            'Student has not locked their profile yet. '
            'Review is blocked until the student fills all details and locks their profile.'
        )
    enrollment = StudentEnrollment.objects.filter(
        student_id=student.id, is_current=True
    ).select_related('semester').first()
    if enrollment is None or enrollment.semester_id is None:
        raise ValidationError(
            'Student has no active enrollment. Review is blocked.'
        )
    cur_num = enrollment.semester.number
    row = Student.objects.filter(id=student.id).values(
        'is_direct_second_year', 'admission_type').first() or {}
    is_dsy = bool(row.get('is_direct_second_year')) or str(
        row.get('admission_type') or '').upper() == 'DSE'
    start_num = 3 if is_dsy else 1
    need = set(range(start_num, cur_num + 1))
    have = set(
        SemesterResult.objects.filter(
            student_id=student.id,
            semester__number__in=list(need),
            is_published=True,
        ).exclude(
            result_status=SemesterResult.ResultStatus.NOT_YET_HELD
        ).values_list('semester__number', flat=True)
    )
    missing = sorted(need - have)
    if missing:
        missing_str = ', '.join(f'Sem {n}' for n in missing)
        raise ValidationError(
            f'Semester results missing for {missing_str}. '
            'Review is blocked until all results are filled.'
        )


def grade_for_marks(marks, max_marks=100):
    """
    9-Point Autonomous Grading scale.
    """
    if marks is None:
        return 'NYH', 0, False

    perc = (float(marks) / float(max_marks)) * 100.0

    if perc >= 90:
        return 'O', 10, False
    elif perc >= 80:
        return 'A+', 9, False
    elif perc >= 70:
        return 'A', 8, False
    elif perc >= 60:
        return 'B+', 7, False
    elif perc >= 50:
        return 'B', 6, False
    elif perc >= 45:
        return 'C', 5, False
    elif perc >= 40:
        return 'P', 4, False
    else:
        return 'F', 0, True


def calculate_semester_metrics(sem_result_id):
    """
    Compute SGPA, credit totals, backlog count, and result status for a semester.
    9-Point Validation (data-driven per student scheme, fallback 20/40/<=4):
    - Fail courses count determines Pass / ATKT / Fail status.
    - ATKT granted if active failed courses <= scheme.max_backlogs_for_atkt.
    """
    sem_res = SemesterResult.objects.get(id=sem_result_id)
    # Deduplicate by course_code (defense against race-created duplicates
    # until DB unique constraint lands): last row wins, extras ignored.
    seen = {}
    for s in sem_res.subject_results.all().order_by('created_at', 'id'):
        seen[s.course_code] = s
    subjects = list(seen.values())

    if not subjects:
        sem_res.result_status = SemesterResult.ResultStatus.NOT_YET_HELD
        sem_res.save(update_fields=['result_status'])
        return sem_res

    try:
        from apps.curriculum.services import get_thresholds
        _, _, max_backlogs = get_thresholds(sem_res.student)
    except Exception:
        import logging as _logging
        _logging.getLogger(__name__).warning(
            'calculate_semester_metrics: no scheme for student %s; using fallback max_backlogs=4',
            getattr(getattr(sem_res, 'student', None), 'id', '?'),
        )
        max_backlogs = 4

    total_credits = 0
    earned_credits = 0
    weighted_gp = Decimal('0.0')
    backlogs = 0

    for s in subjects:
        total_credits += s.credits
        if s.grade_letter == 'F' or s.is_backlog:
            backlogs += 1
        else:
            earned_credits += s.credits
            weighted_gp += Decimal(str(s.credits * s.grade_point))

    sgpa = round(weighted_gp / Decimal(str(total_credits)), 2) if total_credits > 0 else Decimal('0.0')

    if backlogs == 0:
        res_status = SemesterResult.ResultStatus.PASS
    elif backlogs <= max_backlogs:
        res_status = SemesterResult.ResultStatus.ATKT
    else:
        res_status = SemesterResult.ResultStatus.FAIL

    sem_res.sgpa = sgpa
    sem_res.total_credits_registered = total_credits
    sem_res.total_credits_earned = earned_credits
    sem_res.backlog_count = backlogs
    sem_res.result_status = res_status
    # CGPA: cumulative weighted SGPA across all published semesters.
    try:
        _all = SemesterResult.objects.filter(
            student_id=sem_res.student_id, is_published=True,
        ).exclude(result_status=SemesterResult.ResultStatus.NOT_YET_HELD)
        _tw = Decimal('0.0')
        _tc = 0
        for _r in _all:
            if _r.id == sem_res.id:
                _sg, _cr = sgpa, total_credits
            else:
                _sg, _cr = (_r.sgpa, _r.total_credits_registered)
            if _sg is None or not _cr:
                continue
            _tw += Decimal(str(_sg)) * Decimal(str(_cr))
            _tc += int(_cr)
        sem_res.cgpa = round(_tw / Decimal(str(_tc)), 2) if _tc > 0 else sgpa
    except Exception:
        sem_res.cgpa = sgpa
    sem_res.save()

    return sem_res


def evaluate_student_eligibility(student, target_semester, user_reviewer=None):
    """
    Compute promotion eligibility based on cumulative semester performance.
    Data-driven per student scheme (fallback: ATKT if backlogs <= 4).
    """
    enrollment = student.enrollments.filter(is_current=True).first()
    dept = enrollment.department if enrollment else Department.objects.first()
    year = enrollment.academic_year if enrollment else AcademicYear.objects.filter(is_current=True).first()

    try:
        from apps.curriculum.services import get_thresholds
        _, _, max_backlogs = get_thresholds(student)
    except Exception:
        max_backlogs = 4

    # Sum active backlogs across all published semester results
    prev_results = SemesterResult.objects.filter(student=student, is_published=True)
    total_backlogs = sum(r.backlog_count for r in prev_results)
    total_credits = sum(r.total_credits_earned for r in prev_results)

    if total_backlogs == 0:
        calc_status = EligibilityVerification.CalculatedStatus.ELIGIBLE
    elif total_backlogs <= max_backlogs:
        calc_status = EligibilityVerification.CalculatedStatus.PROVISIONAL
    else:
        calc_status = EligibilityVerification.CalculatedStatus.NOT_ELIGIBLE

    eligibility, created = EligibilityVerification.objects.get_or_create(
        student=student,
        academic_year=year,
        target_semester=target_semester,
        defaults={
            'department': dept,
            'active_backlog_count': total_backlogs,
            'total_credits_earned': total_credits,
            'calculated_status': calc_status,
            'class_teacher_status': EligibilityVerification.StageStatus.PENDING,
            'hod_status': EligibilityVerification.StageStatus.PENDING,
            'final_eligible': False,
        },
    )

    if not created:
        eligibility.active_backlog_count = total_backlogs
        eligibility.total_credits_earned = total_credits
        eligibility.calculated_status = calc_status
        eligibility.save()

    return eligibility


def class_teacher_review_eligibility(eligibility_id, reviewer_user, status_decision, remarks='', request=None):
    """
    Class Teacher verifies, flags, or fails student eligibility.
    FAIL (REJECTED) is terminal at teacher level: the student is not
    eligible this cycle and fees can never promote them. Only the HOD
    can reopen a failed case by flagging it back.
    Enforces locking rule: Once decided, it is locked unless flagged back by HOD.
    Audited per SECURITY.md Sec 12/16 (who verified/flagged, old/new state).
    """
    from rest_framework.exceptions import ValidationError

    allowed = {
        EligibilityVerification.StageStatus.APPROVED,
        EligibilityVerification.StageStatus.FLAGGED,
        EligibilityVerification.StageStatus.REJECTED,
    }
    if status_decision not in allowed:
        raise ValidationError(f'Invalid decision {status_decision!r}. Use APPROVED, FLAGGED or REJECTED (fail).')

    with transaction.atomic():
        ev = EligibilityVerification.objects.select_for_update().get(id=eligibility_id)

        # Student prerequisites: locked profile + filled results. Checked
        # first so the teacher sees exactly what is blocking review.
        _require_student_ready_for_review(ev.student, reviewer_user)

        # HOD-closed (failed) cases are untouchable by the teacher.
        if ev.hod_status == EligibilityVerification.StageStatus.REJECTED:
            raise ValidationError(
                'The HOD has closed this case as failed. It cannot be edited.'
            )

        # Enforce lock: If already decided and HOD has not flagged it back, block edit.
        if ev.is_locked_for_teacher:
            raise ValidationError(
                'This eligibility verification is locked because it was already decided by the Class Teacher. '
                'It can only be edited if returned/flagged by the HOD.'
            )

        old_snapshot = {
            'class_teacher_status': ev.class_teacher_status,
            'hod_status': ev.hod_status,
            'final_eligible': ev.final_eligible,
        }
        ev.class_teacher = reviewer_user
        ev.class_teacher_status = status_decision
        ev.class_teacher_remarks = remarks
        ev.class_teacher_reviewed_at = timezone.now()

        # If teacher approves, it moves to HOD review queue
        if status_decision == EligibilityVerification.StageStatus.APPROVED:
            ev.hod_status = EligibilityVerification.StageStatus.PENDING
            ev.final_eligible = False
        elif status_decision in (
            EligibilityVerification.StageStatus.FLAGGED,
            EligibilityVerification.StageStatus.REJECTED,
        ):
            ev.final_eligible = False

        ev.save()
        from apps.audit.models import AuditLog as _AuditLog
        from apps.audit.services import audit_log as _audit_log
        _audit_log(
            request=request,
            actor=reviewer_user,
            action=_AuditLog.Action.VERIFY,
            target_type='EligibilityVerification',
            target_id=str(ev.id),
            target_display=f'{ev.student.display_name} -> Sem {ev.target_semester.number if ev.target_semester else "?"}',
            old_value=old_snapshot,
            new_value={
                'class_teacher_status': ev.class_teacher_status,
                'hod_status': ev.hod_status,
                'final_eligible': ev.final_eligible,
            },
            reason=str(remarks or 'Class-teacher eligibility review')[:500],
            description=(
                f"Class teacher set {ev.student.display_name} to {status_decision} "
                f"(target Sem {ev.target_semester.number if ev.target_semester else '?'})."
            ),
        )
        return ev


def hod_endorse_eligibility(eligibility_id, hod_user, status_decision, remarks='', request=None):
    """
    HOD final approval of eligibility.
    - If APPROVED and class teacher APPROVED: final_eligible = True (eligible for admission).
    - If FLAGGED: returns candidate to Class Teacher (unlocks the record for teacher re-evaluation).
    - If REJECTED (fail): terminal. The student is not eligible this cycle and
      fee payment can never promote them. Only a HOD flag can reopen it.
    Audited per SECURITY.md Sec 12/16.
    """
    with transaction.atomic():
        ev = EligibilityVerification.objects.select_for_update().get(id=eligibility_id)
        # Student prerequisites apply to HOD endorsement too (defense in
        # depth: teacher approval already required them, but direct API calls
        # must not bypass the gate).
        _require_student_ready_for_review(ev.student, hod_user)
        allowed = {
            EligibilityVerification.StageStatus.APPROVED,
            EligibilityVerification.StageStatus.FLAGGED,
            EligibilityVerification.StageStatus.REJECTED,
        }
        from rest_framework.exceptions import ValidationError as _ValidationError
        if status_decision not in allowed:
            raise _ValidationError(
                f'Invalid decision {status_decision!r}. Use APPROVED, FLAGGED or REJECTED (fail).')
        # Fix 16: HOD APPROVE requires teacher APPROVE first. Prevents
        # stuck half-approved (HOD approved + teacher pending/flagged).
        if status_decision == EligibilityVerification.StageStatus.APPROVED:
            if ev.class_teacher_status != EligibilityVerification.StageStatus.APPROVED:
                raise _ValidationError(
                    'Class Teacher must APPROVE first. HOD cannot approve while teacher is pending, flagged or failed.')
        if (status_decision == EligibilityVerification.StageStatus.APPROVED
                and ev.class_teacher_status == EligibilityVerification.StageStatus.REJECTED):
            raise _ValidationError(
                'The Class Teacher marked this student as failed. Flag it back to reopen instead of approving.')
        if (ev.hod_status == EligibilityVerification.StageStatus.REJECTED
                and status_decision != EligibilityVerification.StageStatus.FLAGGED):
            raise _ValidationError(
                'This case is closed as failed. Only flagging can reopen it.')
        old_snapshot = {
            'hod_status': ev.hod_status,
            'final_eligible': ev.final_eligible,
            'class_teacher_status': ev.class_teacher_status,
        }
        ev.hod = hod_user
        ev.hod_status = status_decision
        ev.hod_remarks = remarks
        ev.hod_reviewed_at = timezone.now()

        if (
            ev.class_teacher_status == EligibilityVerification.StageStatus.APPROVED
            and status_decision == EligibilityVerification.StageStatus.APPROVED
        ):
            ev.final_eligible = True
            # Promotion is best-effort and must NEVER fail endorsement: capture
            # the outcome on the instance so the view can surface a deferral
            # instead of failing silently (stuck-but-paid trap).
            ev._promotion_outcome = {'attempted': True, 'promoted': False, 'message': ''}
            try:
                from apps.students.services import check_and_promote_student
                ok, msg = check_and_promote_student(ev.student_id, actor=hod_user, request=request)
                ev._promotion_outcome.update(promoted=bool(ok), message=msg or '')
            except Exception:
                import logging as _logging
                _logging.getLogger(__name__).exception(
                    'Auto-promotion failed after HOD endorsement for EV %s; endorsement stands.', ev.id)
                ev._promotion_outcome.update(
                    promoted=False,
                    message='Auto-promotion deferred by an unexpected error; endorsement stands. Use Promote Class.')
        else:
            ev.final_eligible = False
            ev._promotion_outcome = {'attempted': False, 'promoted': False, 'message': ''}

        ev.save()
        from apps.audit.models import AuditLog as _AuditLog
        from apps.audit.services import audit_log as _audit_log
        _audit_log(
            request=request,
            actor=hod_user,
            action=_AuditLog.Action.VERIFY,
            target_type='EligibilityVerification',
            target_id=str(ev.id),
            target_display=f'{ev.student.display_name} -> Sem {ev.target_semester.number if ev.target_semester else "?"}',
            old_value=old_snapshot,
            new_value={
                'hod_status': ev.hod_status,
                'final_eligible': ev.final_eligible,
                'class_teacher_status': ev.class_teacher_status,
            },
            reason=str(remarks or 'HOD eligibility endorsement')[:500],
            description=(
                f"HOD set {ev.student.display_name} to {status_decision} "
                f"(final_eligible={ev.final_eligible})."
            ),
        )
        return ev


def submit_semester_marks(student, semester_number, exam_session, subjects_data, seat_number='', actor=None, request=None):
    """
    Process student marks submission / correction.
    - Enforces locking: Student cannot edit if results have already been confirmed by Class Teacher,
      unless flagged by the Class Teacher (or HOD).
    - Enforces scheme passing rules (data-driven, fallback Theory >= 20, Total >= 40).
    - Updates SemesterResult & SubjectResults, computes SGPA, and triggers Eligibility evaluation.
    - Every changed subject is audited with old/new marks (ARCH 24 evidence;
      full versioned supersession is a documented follow-up, see ADR-013).
    """
    from rest_framework.exceptions import ValidationError
    from apps.audit.models import AuditLog
    from apps.audit.services import audit_log

    with transaction.atomic():
        enrollment = student.enrollments.filter(is_current=True).first()
        academic_year = enrollment.academic_year if enrollment else AcademicYear.objects.filter(is_current=True).first()
        semester = Semester.objects.filter(number=semester_number).first()
        if not semester:
            raise ValidationError(f'Semester {semester_number} not found.')

        if not (exam_session or '').strip():
            raise ValidationError('exam_session is required (e.g. Winter 2026).')

        target_sem = Semester.objects.filter(number=semester_number + 1).first() or semester
        # Backlog catch-up (submitted older than the student's current
        # semester) rides the current class window instead: demanding or
        # birthing the stale first-year cycle (submitted+1) would block
        # seniors on long-closed verifications and pollute teacher queues.
        cur_sem_num = enrollment.semester.number if enrollment and enrollment.semester else None
        is_backlog_submit = cur_sem_num is not None and semester_number < cur_sem_num
        if is_backlog_submit:
            target_sem = Semester.objects.filter(number=cur_sem_num + 1).first() or target_sem

        # F-S7-002: Check existing eligibility lock with select_for_update to prevent
        # race conditions between student marks submission and teacher approval.
        existing_ev = EligibilityVerification.objects.select_for_update().filter(
            student=student,
            academic_year=academic_year,
            target_semester=target_sem,
        ).first()

        # Per-semester correction scoping (flag contract: only ticked
        # semesters reopen for the student). While ANY published result
        # carries a correction flag, resubmitting a published-but-unflagged
        # semester is rejected. First fills (no published row yet) always
        # pass, and staff actors bypass so admin corrections never deadlock.
        _published_row = SemesterResult.objects.filter(
            student=student,
            semester=semester,
            is_published=True,
        ).exclude(
            result_status=SemesterResult.ResultStatus.NOT_YET_HELD
        ).order_by('-academic_year__start_date', '-created_at').first()
        if _published_row is not None and not _published_row.correction_requested:
            _is_staff_actor = (
                actor is not None
                and getattr(student, 'user_id', None) != getattr(actor, 'id', None)
            )
            if not _is_staff_actor and SemesterResult.objects.filter(
                student=student,
                correction_requested=True,
                is_published=True,
            ).exclude(
                result_status=SemesterResult.ResultStatus.NOT_YET_HELD
            ).exists():
                raise ValidationError(
                    f'Semester {semester_number} was not flagged for correction by your '
                    f'class teacher. Only the flagged semesters can be resubmitted right now.'
                )

        if existing_ev and existing_ev.is_locked_for_student:
            raise ValidationError(
                'Your semester marks have already been confirmed by your Class Teacher and locked. '
                'Modifications are not allowed unless flagged by your teacher.'
            )

        # Create or update SemesterResult
        sem_res, _ = SemesterResult.objects.get_or_create(
            student=student,
            academic_year=academic_year,
            semester=semester,
            defaults={
                'exam_session': exam_session,
                'seat_number': seat_number or '',
                'is_published': True,
                'published_at': timezone.now(),
            }
        )
        if exam_session:
            sem_res.exam_session = exam_session
        if seat_number:
            sem_res.seat_number = seat_number
        sem_res.is_published = True
        sem_res.published_at = timezone.now()
        sem_res.save()

        # Deduplicate payload by course_code (last row wins) so a repeated
        # code in one request can never double-count SGPA.
        _deduped = {}
        for _s in (subjects_data or []):
            _code = ((_s.get('course_code') or _s.get('code') or '').strip())
            if _code:
                _deduped[_code] = _s
        subjects_data = list(_deduped.values())

        # Process each subject score with scheme passing criteria
        # Fix 25: log scheme fallback so silent 20/40 never hides missing scheme.
        try:
            from apps.curriculum.services import get_thresholds
            min_theory, min_total, _ = get_thresholds(student)
        except Exception:
            import logging as _logging2
            _logging2.getLogger(__name__).warning(
                'submit_semester_marks: no scheme for student %s; using fallback Theory>=20 Total>=40',
                getattr(student, 'id', '?'),
            )
            min_theory, min_total = 20.0, 40.0
        for s in subjects_data:
            code = (s.get('course_code') or s.get('code') or '').strip()
            if not code:
                raise ValidationError('Every subject needs a course_code.')
            name = s.get('course_name') or s.get('name') or code
            if s.get('credits') in (None, ''):
                raise ValidationError(f'Subject {code} needs credits from the scheme.')
            credits_val = int(s.get('credits'))

            th = float(s.get('theory_marks') or s.get('theory_ese_marks') or 0.0)
            m1 = float(s.get('mid1_marks') or 0.0)
            m2 = float(s.get('mid2_marks') or 0.0)
            ise = m1 + m2 if (m1 or m2) else float(s.get('theory_ise_marks') or 0.0)
            prac = float(s.get('practical_marks') or 0.0)
            # Server is authoritative on totals: recompute from components
            # whenever any component is present; a client-sent total is only
            # a fallback for component-less payloads (never trusted over parts).
            if th or ise or prac:
                tot = th + ise + prac
            else:
                tot = float(s.get('total_marks') or 0.0)

            # F-S6-002: Marks range validation against scheme maxima.
            # Maxima resolve server-side from the Subject record; client-supplied
            # maxima are discarded to prevent bypassing validation. Codes with no
            # Subject record keep generic defaults BUT are warning-logged with
            # student context: hard rejection here broke legitimate flows
            # (scheme setup often lags marks entry), so unknown codes stay
            # observable rather than blocking (W0 over W1 per contract).
            import logging as _logging
            from apps.curriculum.models import Subject
            subj = Subject.objects.filter(code=code).first()
            if subj is None:
                _logging.getLogger(__name__).warning(
                    'submit_marks: no Subject record for code %s (student %s); '
                    'validating against generic defaults 100/50/100. Register it.',
                    code, getattr(student, 'id', '?'),
                )
            if subj is not None:
                _max_theory = float(subj.ese_max_marks or 100)
                _ise_calc = float((subj.ca_max_marks or 0) + (subj.mse_max_marks or 0))
                _max_ise = _ise_calc if _ise_calc > 0 else 50.0
                _max_prac = float(subj.practical_total) if subj.practical_total else 0.0
                if subj.exam_total:
                    _max_total = float(subj.exam_total)
                else:
                    _max_total = _max_theory + _max_ise + (_max_prac if (prac > 0 or _max_prac > 0) else 0.0)
            else:
                _max_theory, _max_ise, _max_prac = 100.0, 50.0, 100.0
                # Unknown code: practical counts only when submitted.
                # Theory-only payloads grade against 150, not 250.
                _max_total = _max_theory + _max_ise + (_max_prac if prac > 0 else 0.0)

            if th < 0 or th > _max_theory:
                raise ValidationError(
                    f'Subject {code}: theory_ese_marks {th} is out of range [0, {_max_theory}].'
                )
            if ise < 0 or ise > _max_ise:
                raise ValidationError(
                    f'Subject {code}: theory_ise_marks {ise} is out of range [0, {_max_ise}].'
                )
            if prac < 0 or prac > _max_prac:
                raise ValidationError(
                    f'Subject {code}: practical_marks {prac} is out of range [0, {_max_prac}].'
                )
            if tot < 0 or tot > _max_total:
                raise ValidationError(
                    f'Subject {code}: total_marks {tot} is out of range [0, {_max_total}].'
                )

            # Scheme passing rule (fallback: Theory >= 20 AND Total >= 40)
            is_pass = (th >= min_theory and tot >= min_total)
            if is_pass:
                grade_letter, grade_point, is_backlog = grade_for_marks(tot, _max_total)
            else:
                grade_letter, grade_point, is_backlog = 'F', 0, True


            old_row = SubjectResult.objects.filter(
                semester_result=sem_res, course_code=code).first()
            old_marks = None
            if old_row is not None:
                old_marks = {
                    'theory_ese_marks': str(old_row.theory_ese_marks),
                    'theory_ise_marks': str(old_row.theory_ise_marks),
                    'practical_marks': str(old_row.practical_marks),
                    'total_marks': str(old_row.total_marks),
                    'grade_letter': old_row.grade_letter,
                }

            row, _ = SubjectResult.objects.update_or_create(
                semester_result=sem_res,
                course_code=code,
                defaults={
                    'course_name': name,
                    'credits': credits_val,
                    'theory_ese_marks': Decimal(str(round(th, 1))),
                    'theory_ise_marks': Decimal(str(round(ise, 1))),
                    'mid1_marks': Decimal(str(round(m1, 1))),
                    'mid2_marks': Decimal(str(round(m2, 1))),
                    'practical_marks': Decimal(str(round(prac, 1))),
                    'total_marks': Decimal(str(round(tot, 1))),
                    'grade_letter': grade_letter,
                    'grade_point': grade_point,
                    'is_backlog': is_backlog,
                }
            )
            new_marks = {
                'theory_ese_marks': str(round(th, 1)),
                'theory_ise_marks': str(round(ise, 1)),
                'practical_marks': str(round(prac, 1)),
                'total_marks': str(round(tot, 1)),
                'grade_letter': grade_letter,
            }
            if old_marks is not None and old_marks != new_marks:
                audit_log(
                    request=request, actor=actor,
                    action=AuditLog.Action.UPDATE,
                    target_type='SubjectResult',
                    target_id=str(row.id),
                    target_display=f'{student.display_name} Sem {semester_number} {code}',
                    old_value=old_marks, new_value=new_marks,
                    reason='Marks correction',
                    description=f"Marks changed for {code} (Sem {semester_number}).",
                )

        # Recalculate metrics
        calculate_semester_metrics(sem_res.id)
        sem_res.refresh_from_db()

        # Eligibility rows exist only for year-change targets (3, 5, 7).
        # Other semesters record results without spawning verification.
        # A backlog entry never births a cycle on its own — it only refreshes
        # the open class window (if any), so stale first-year rows are never
        # created for seniors catching up on old semesters.
        ev = None
        if target_sem.number in YEAR_CHANGE_TARGETS and not (is_backlog_submit and existing_ev is None):
            ev = evaluate_student_eligibility(student, target_sem)

            # If student corrected previously flagged result, reset teacher status to PENDING
            # Fix 19: HOD-flagged also reopens teacher queue on student resubmit
            # (HOD->teacher->student flow: student edit means teacher must re-check).
            if existing_ev and existing_ev.class_teacher_status == EligibilityVerification.StageStatus.FLAGGED:
                ev.class_teacher_status = EligibilityVerification.StageStatus.PENDING
                ev.final_eligible = False
                ev.save(update_fields=['class_teacher_status', 'final_eligible'])
            elif existing_ev and existing_ev.hod_status == EligibilityVerification.StageStatus.FLAGGED:
                ev.class_teacher_status = EligibilityVerification.StageStatus.PENDING
                ev.final_eligible = False
                ev.save(update_fields=['class_teacher_status', 'final_eligible'])

        # A successful resubmit resolves this semester's own correction flag
        # only — other flagged semesters stay open, so correcting one never
        # locks the rest.
        if sem_res.correction_requested:
            SemesterResult.objects.filter(pk=sem_res.pk).update(
                correction_requested=False, correction_remarks='')

        return sem_res, ev
