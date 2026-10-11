"""
Views for Semester Results and Eligibility Verification Workflow.
"""
import logging

from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

logger = logging.getLogger(__name__)

from apps.authentication.permissions import (
    HasScopeAccess,
    get_user_scopes,
    user_has_role,
)
from apps.results.models import (
    EligibilityVerification,
    SemesterResult,
)
from apps.results.serializers import (
    EligibilityVerificationSerializer,
    SemesterResultSerializer,
)
from apps.results.services import (
    class_teacher_review_eligibility,
    hod_endorse_eligibility,
)
from apps.students.models import Student, StudentEnrollment


def staff_display_name(user):
    """Human-readable name for a staff User.

    Division/EV teacher FKs point at the login User; the actual name lives on
    the linked Faculty profile. Falls back to the username (User carries no
    name columns) so callers never render blank.
    """
    if not user:
        return ''
    profile = getattr(user, 'faculty_profile', None)
    if profile and getattr(profile, 'display_name', ''):
        return profile.display_name
    try:
        full = user.get_full_name()
    except Exception:
        full = ''
    return full or getattr(user, 'username', '')


def _admission_student_allowed(user, scopes, student):
    """Scope check for admission-form-data/pdf (PII-heavy). Mirrors class-roster."""
    if scopes.get('is_system_wide') or 'ADMIN_HEAD' in scopes.get('roles', []):
        return True
    if 'ACCOUNTANT' in scopes.get('roles', []):
        # Fee desk needs admission data college-wide (same as eligible-candidates).
        return True
    roles = scopes.get('roles', [])
    # Student own only
    if 'STUDENT' in roles and len([r for r in roles if r in ('HOD', 'CLASS_TEACHER', 'FACULTY', 'ACCOUNTANT', 'ADMIN_HEAD')]) == 0:
        return getattr(student, 'user_id', None) == getattr(user, 'id', None)
    if 'HOD' in roles:
        enr = student.enrollments.filter(is_current=True).first()
        if enr and str(enr.department_id) in {str(d) for d in scopes.get('department_ids', [])}:
            return True
        # Historical dept membership also counts (promoted-out still viewable).
        if student.enrollments.filter(department_id__in=scopes.get('department_ids', [])).exists():
            return True
        return False
    if 'CLASS_TEACHER' in roles:
        enr = student.enrollments.filter(is_current=True).select_related('division').first()
        div = getattr(enr, 'division', None) if enr else None
        if div is None:
            return False
        assigned = {str(x) for x in scopes.get('division_ids', [])}
        if div.class_teacher_id == getattr(user, 'id', None) or str(div.id) in assigned:
            return True
        return False
    # Plain FACULTY: no PII access (eligibility link removed from nav).
    return False


class SemesterResultViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Semester Marksheet and Results ViewSet.
    Protected by role scopes; students see only their own published results.
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SemesterResultSerializer

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated:
            return SemesterResult.objects.none()

        qs = SemesterResult.objects.select_related(
            'student', 'academic_year', 'semester'
        ).prefetch_related('subject_results')

        scopes = get_user_scopes(user)

        # Optional per-student filter (used by the verification modal).
        # Without this, staff endpoints ignored ?student_id= and returned
        # other students' marksheets mixed together (incl. duplicate
        # semester cards). Non-staff may only ever query themselves.
        student_param = self.request.query_params.get('student_id') or self.request.query_params.get('student')
        if 'STUDENT' in scopes['roles'] and not (scopes['is_system_wide'] or 'ADMIN_HEAD' in scopes['roles']):
            own = Student.objects.filter(user_id=user.id).values_list('id', flat=True)
            if student_param and str(student_param) not in {str(x) for x in own}:
                return SemesterResult.objects.none()
            qs = qs.filter(student__user_id=user.id, is_published=True)
        elif student_param:
            from django.db import models as _models
            if scopes['is_system_wide'] or 'ADMIN_HEAD' in scopes['roles']:
                qs = qs.filter(student_id=student_param)
            elif 'HOD' in scopes['roles']:
                # Dept-scoped: current OR historical enrollment in the HOD's
                # department (promoted-out students stay viewable).
                qs = qs.filter(
                    student_id=student_param,
                    student__enrollments__department_id__in=scopes['department_ids'],
                )
            elif 'CLASS_TEACHER' in scopes['roles']:
                # Division-scoped incl. enrollment history (promoted students).
                # Covers both explicit division assignments and direct
                # Division.class_teacher ownership.
                from apps.academic_structure.models import Division as _Division
                _ct_div_ids = {str(x) for x in (scopes.get('division_ids') or [])}
                _ct_div_ids |= {str(x) for x in _Division.objects.filter(class_teacher_id=user.id).values_list('id', flat=True)}
                qs = qs.filter(
                    student_id=student_param,
                    student__enrollments__division_id__in=list(_ct_div_ids) or [],
                )
            elif 'FACULTY' in scopes['roles']:
                # Faculty has no direct result access; use class roster via CT/HOD.
                return SemesterResult.objects.none()
            else:
                return SemesterResult.objects.none()
        elif not (scopes['is_system_wide'] or 'ADMIN_HEAD' in scopes['roles']):
            # No explicit student requested: keep role scoping so the list
            # endpoint never dumps the whole college by accident.
            if 'HOD' in scopes['roles']:
                dept_ids = scopes['department_ids']
                qs = qs.filter(student__enrollments__department_id__in=dept_ids, student__enrollments__is_current=True)
            elif 'CLASS_TEACHER' in scopes['roles']:
                div_ids = scopes['division_ids']
                qs = qs.filter(student__enrollments__division_id__in=div_ids, student__enrollments__is_current=True)
            elif 'STUDENT' in scopes['roles']:
                qs = qs.filter(student__user_id=user.id, is_published=True)
            else:
                # FACULTY and any other role: no college-wide dump.
                return SemesterResult.objects.none()

        semester_param = self.request.query_params.get('semester_number') or self.request.query_params.get('semester')
        if semester_param:
            try:
                qs = qs.filter(semester__number=int(semester_param))
            except (TypeError, ValueError):
                pass

        return qs.distinct().order_by('semester__number')

    @action(detail=False, methods=['get'], url_path='my-results')
    def my_results(self, request):
        """Current authenticated student's published marksheets."""
        results = SemesterResult.objects.filter(
            student__user_id=request.user.id,
            is_published=True,
        ).order_by('semester__number')
        serializer = self.get_serializer(results, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='graduation-pending')
    def graduation_pending(self, request):
        """Final-sem PASS students awaiting HOD graduation confirmation."""
        user = request.user
        scopes = get_user_scopes(user)
        qs = SemesterResult.objects.filter(
            semester__number=8, is_published=True,
            result_status=SemesterResult.ResultStatus.PASS,
        ).select_related('student', 'semester', 'academic_year').exclude(
            student__status='PASSED_OUT')
        if scopes['is_system_wide'] or 'ADMIN_HEAD' in scopes['roles']:
            filtered = qs
        elif 'HOD' in scopes['roles']:
            filtered = qs.filter(student__enrollments__department_id__in=scopes['department_ids'],
                                 student__enrollments__is_current=True)
        elif 'CLASS_TEACHER' in scopes['roles'] and scopes['division_ids']:
            filtered = qs.filter(student__enrollments__division_id__in=scopes['division_ids'],
                                 student__enrollments__is_current=True)
        else:
            filtered = SemesterResult.objects.none()
        qs = filtered.distinct().order_by('student__display_name')
        # Paginate: graduation queue grows with every Sem-8 batch (Rule 22).
        # Contract-safe: tests and frontend accept paginated or list shape.
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='confirm-graduation')
    def confirm_graduation(self, request, pk=None):
        """HOD confirms graduation after final results; student passes out."""
        from apps.audit.models import AuditLog
        from apps.audit.services import audit_log
        from apps.authentication.permissions import user_has_role
        sem_res = self.get_object()
        user = request.user
        scopes = get_user_scopes(user)
        student = sem_res.student
        enr = student.enrollments.filter(is_current=True).first()
        dept_ok = (
            scopes['is_system_wide'] or request.user.is_superuser
            or (user_has_role(user, 'HOD') and enr and str(enr.department_id) in {
                str(d) for d in scopes.get('department_ids', [])})
        )
        if not dept_ok:
            return Response({'detail': 'Only the HOD of this department can confirm graduation.'},
                            status=status.HTTP_403_FORBIDDEN)
        if sem_res.semester.number != 8 or not sem_res.is_published or sem_res.result_status != SemesterResult.ResultStatus.PASS:
            return Response({'detail': 'Graduation needs a published PASS result for Semester 8.'},
                            status=status.HTTP_400_BAD_REQUEST)
        from django.db import transaction
        with transaction.atomic():
            student.status = 'PASSED_OUT'
            student.save(update_fields=['status'])
            if enr:
                enr.status = 'COMPLETED'
                enr.save(update_fields=['status'])
            audit_log(
                request=request, actor=user, action=AuditLog.Action.STATUS_CHANGE,
                target_type='Student', target_id=str(student.id),
                target_display=student.display_name,
                reason=request.data.get('reason', 'HOD graduation confirmation') if request.data else 'HOD graduation confirmation',
                description=f"Confirmed graduation of {student.display_name} after Sem 8 PASS.",
            )
        return Response({'detail': f'{student.display_name} marked as graduated.'}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='submit-marks')
    def submit_marks(self, request):
        """
        Student enters or updates semester examination marks.
        Validates 9-point criteria and routes to Class Teacher eligibility verification.
        """
        user = request.user
        scopes = get_user_scopes(user)

        # Identify student
        student = None
        student_id = request.data.get('student_id')
        if student_id and (scopes['is_system_wide'] or 'ADMIN_HEAD' in scopes['roles'] or 'FACULTY' in scopes['roles']):
            student = Student.objects.filter(id=student_id).first()
            # F-S3-001: Scoped staff must only write marks for students in their department.
            if student and not scopes['is_system_wide'] and 'ADMIN_HEAD' not in scopes['roles']:
                enr = student.enrollments.filter(is_current=True).first()
                if enr:
                    user_dept_ids = {str(d) for d in scopes.get('department_ids', [])}
                    if str(enr.department_id) not in user_dept_ids:
                        return Response(
                            {'detail': 'You do not have permission to submit marks for a student outside your department.'},
                            status=status.HTTP_403_FORBIDDEN,
                        )
        elif hasattr(user, 'student_profile'):
            student = user.student_profile
        else:
            student = Student.objects.filter(user_id=user.id).first()

        if not student:
            return Response({'detail': 'Student profile not found.'}, status=status.HTTP_404_NOT_FOUND)

        semester_num = request.data.get('semester_number')
        if not semester_num:
            return Response({'detail': 'semester_number is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            semester_num_int = int(semester_num)
        except (TypeError, ValueError):
            return Response({'detail': 'semester_number must be an integer.'}, status=status.HTTP_400_BAD_REQUEST)

        # Server-side enforcement of the even-semester upload window:
        # a student self-submission for Sem 2/4/6 in an assigned division is
        # only allowed after HOD/Class Teacher opened verification (EV row
        # exists). The window belongs to the student's CURRENT class
        # (division sem + 1) — never submitted+1, so backlog fills for older
        # semesters ride the open class window instead of demanding a stale
        # first-year cycle. Staff bypass for corrections; existing results
        # allow edits; students without a division fall through (legacy,
        # preserves tests).
        if semester_num_int in (2, 4, 6) and student is not None:
            is_staff_actor = bool(
                scopes.get('is_system_wide')
                or request.user.is_superuser
                or any(r in scopes.get('roles', []) for r in ('ADMIN_HEAD', 'HOD', 'CLASS_TEACHER', 'FACULTY'))
            )
            if not is_staff_actor:
                is_self_submit = (
                    getattr(student, 'user_id', None) == request.user.id
                    or student_id is None
                )
                if is_self_submit:
                    already_has_result = SemesterResult.objects.filter(
                        student=student, semester__number=semester_num_int,
                    ).exists()
                    if not already_has_result:
                        enr = student.enrollments.filter(is_current=True).select_related('division', 'division__semester').first()
                        div = getattr(enr, 'division', None) if enr else None
                        div_sem_num = getattr(getattr(div, 'semester', None), 'number', None) if div else None
                        if div is not None and div_sem_num in (2, 4, 6):
                            from apps.academic_structure.models import Semester as _Sem
                            _target = _Sem.objects.filter(number=div_sem_num + 1).first()
                            _ev_exists = False
                            if _target is not None and enr is not None:
                                _ev_exists = EligibilityVerification.objects.filter(
                                    student=student,
                                    academic_year=enr.academic_year,
                                    target_semester=_target,
                                ).exists()
                            if not _ev_exists:
                                return Response(
                                    {'detail': 'Verification not started for this class. Ask your HOD or Class Teacher to start verification first.'},
                                    status=status.HTTP_403_FORBIDDEN,
                                )

        exam_session = (request.data.get('exam_session') or '').strip()
        if not exam_session:
            return Response({'detail': 'exam_session is required (e.g. Winter 2026).'}, status=status.HTTP_400_BAD_REQUEST)
        seat_no = request.data.get('seat_number', '')
        subjects = request.data.get('subjects', [])

        if not subjects:
            return Response({'detail': 'At least one subject score is required.'}, status=status.HTTP_400_BAD_REQUEST)

        from apps.results.services import submit_semester_marks
        try:
            sem_res, ev = submit_semester_marks(
                student=student,
                semester_number=int(semester_num),
                exam_session=exam_session,
                subjects_data=subjects,
                seat_number=seat_no,
                actor=user,
                request=request,
            )
            payload = {
                'semester_result': SemesterResultSerializer(sem_res).data,
                'eligibility': EligibilityVerificationSerializer(ev).data if ev else None,
                'message': (
                    'Marks submitted successfully. Routed to Class Teacher for verification.'
                    if ev else
                    'Marks submitted successfully. No verification needed for this semester.'
                ),
            }
            return Response(payload, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class EligibilityVerificationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Multi-tier eligibility review workflow (ARCH 17: guarded transitions only):
    - Class Teacher flags / approves with remarks (locked once confirmed)
    - HOD endorses / flags back to teacher with remarks
    - Accountant uses HOD-endorsed records for candidate fee desk
    Direct PUT/PATCH/DELETE are blocked; state changes go through the
    review-class-teacher / endorse-hod actions only.
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = EligibilityVerificationSerializer

    def update(self, request, *args, **kwargs):
        return Response({'detail': 'Direct edit blocked. Use the review workflow actions.'},
                        status=status.HTTP_405_METHOD_NOT_ALLOWED)

    def partial_update(self, request, *args, **kwargs):
        return Response({'detail': 'Direct edit blocked. Use the review workflow actions.'},
                        status=status.HTTP_405_METHOD_NOT_ALLOWED)

    def destroy(self, request, *args, **kwargs):
        return Response({'detail': 'Eligibility records cannot be deleted.'},
                        status=status.HTTP_405_METHOD_NOT_ALLOWED)

    def get_queryset(self):
        user = self.request.user
        scopes = get_user_scopes(user)

        qs = EligibilityVerification.objects.select_related(
            'student', 'department', 'academic_year', 'target_semester',
            'class_teacher', 'hod',
        ).prefetch_related(
            'student__semester_results__semester',
            'student__semester_results__subject_results',
        )

        # Per-student filter for the review modal's semester picker
        # (one student, many target semesters). Same scoping as the
        # semester-results endpoint: staff see scoped students, students
        # see only themselves. History enrollments count (promoted-out
        # students stay flaggable).
        student_param = self.request.query_params.get('student_id') or self.request.query_params.get('student')
        if student_param:
            if 'STUDENT' in scopes['roles'] and not (scopes['is_system_wide'] or 'ADMIN_HEAD' in scopes['roles']):
                own = Student.objects.filter(user_id=user.id).values_list('id', flat=True)
                if str(student_param) not in {str(x) for x in own}:
                    return EligibilityVerification.objects.none()
                qs = qs.filter(student_id=student_param)
            elif scopes['is_system_wide'] or 'ADMIN_HEAD' in scopes['roles']:
                qs = qs.filter(student_id=student_param)
            elif 'HOD' in scopes['roles']:
                qs = qs.filter(
                    student_id=student_param,
                    student__enrollments__department_id__in=scopes['department_ids'],
                )
            elif 'CLASS_TEACHER' in scopes['roles']:
                # Assigned-division only (matches class-roster strictness).
                # Dept-wide fallback removed: unassigned CTs get nothing here.
                from apps.academic_structure.models import Division as _Division
                _ct_div_ids = {str(x) for x in (scopes.get('division_ids') or [])}
                _ct_div_ids |= {str(x) for x in _Division.objects.filter(class_teacher_id=user.id).values_list('id', flat=True)}
                if not _ct_div_ids:
                    return EligibilityVerification.objects.none()
                qs = qs.filter(
                    student_id=student_param,
                    student__enrollments__division_id__in=list(_ct_div_ids),
                )
            else:
                return EligibilityVerification.objects.none()
            # Fix 13: honour department filter even with student_id.
            dept_param_early = self.request.query_params.get('department_id') or self.request.query_params.get('department')
            if dept_param_early:
                qs = qs.filter(department_id=dept_param_early)
            return qs.distinct().order_by('target_semester__number')

        dept_param = self.request.query_params.get('department_id') or self.request.query_params.get('department')
        if dept_param:
            qs = qs.filter(department_id=dept_param)

        final_eligible_param = self.request.query_params.get('final_eligible')
        if final_eligible_param is not None:
            is_fe = final_eligible_param.lower() in ('true', '1')
            qs = qs.filter(final_eligible=is_fe)

        if scopes['is_system_wide'] or 'ADMIN_HEAD' in scopes['roles'] or 'ACCOUNTANT' in scopes['roles']:
            filtered_qs = qs
        elif 'HOD' in scopes['roles']:
            # Fix 14: use live current enrollment dept, not snapshot,
            # so transferred students move to new HOD and old HOD loses access.
            filtered_qs = qs.filter(
                student__enrollments__department_id__in=scopes['department_ids'],
                student__enrollments__is_current=True,
            )
        elif 'CLASS_TEACHER' in scopes['roles']:
            # Assigned divisions only (matches classes()/roster). No dept fallback.
            from apps.academic_structure.models import Division as _Division
            _assigned = {str(x) for x in (scopes.get('division_ids') or [])}
            _assigned |= {str(x) for x in _Division.objects.filter(class_teacher_id=user.id).values_list('id', flat=True)}
            if not _assigned:
                filtered_qs = qs.none()
            else:
                filtered_qs = qs.filter(student__enrollments__division_id__in=list(_assigned), student__enrollments__is_current=True)
        elif 'STUDENT' in scopes['roles']:
            return qs.filter(student__user_id=user.id)
        else:
            return EligibilityVerification.objects.none()

        # Pre-sort queue so Class Teacher / HOD reviews pre-sorted list:
        # 1. Actionable status first (PENDING, FLAGGED, APPROVED, REJECTED)
        # 2. Backlogs count ascending: 0 (Eligible) -> <= 4 (ATKT/Provisional) -> > 4 (Not Eligible)
        # 3. Student display name
        from django.db.models import Case, When, Value, IntegerField
        if 'HOD' in scopes.get('roles', []):
            status_order = Case(
                When(hod_status='PENDING', then=Value(1)),
                When(hod_status='FLAGGED', then=Value(2)),
                When(hod_status='APPROVED', then=Value(3)),
                default=Value(4),
                output_field=IntegerField(),
            )
        else:
            status_order = Case(
                When(class_teacher_status='PENDING', then=Value(1)),
                When(class_teacher_status='FLAGGED', then=Value(2)),
                When(class_teacher_status='APPROVED', then=Value(3)),
                default=Value(4),
                output_field=IntegerField(),
            )

        return filtered_qs.annotate(_action_priority=status_order).order_by(
            '_action_priority',
            'active_backlog_count',
            'student__display_name',
        )

    @action(detail=False, methods=['get'], url_path='eligible-candidates')
    def eligible_candidates(self, request):
        """Returns only HOD-endorsed candidates (final_eligible=True) for fee processing."""
        qs = self.get_queryset().filter(final_eligible=True)
        # Paginate: fee roster scales with admissions (Rule 22).
        # Contract-safe: frontend accepts paginated or list shape.
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='classes')
    def classes(self, request):
        """Returns classes (divisions) in caller's scope with verification statistics."""
        from django.db import models
        from apps.academic_structure.models import AcademicContext, Division
        from apps.students.models import StudentEnrollment
        from apps.results.models import SemesterResult

        scopes = get_user_scopes(request.user)
        active_ctx = AcademicContext.objects.filter(is_active=True).select_related('academic_year').first()
        active_term = active_ctx.term if active_ctx else 'EVEN'

        div_qs = Division.objects.filter(is_active=True).select_related(
            'department', 'semester', 'class_teacher',
            'class_teacher__faculty_profile', 'academic_year')
        dept_param = request.query_params.get('department_id') or request.query_params.get('department')
        if dept_param:
            div_qs = div_qs.filter(department_id=dept_param)

        if scopes['is_system_wide'] or 'ADMIN_HEAD' in scopes['roles']:
            pass
        elif 'HOD' in scopes['roles']:
            div_qs = div_qs.filter(department_id__in=scopes['department_ids'])
        elif 'CLASS_TEACHER' in scopes['roles']:
            # Assigned divisions only: explicit division scope OR Division.class_teacher.
            # Dept-wide fallback removed — unassigned CTs see EmptyState, not the
            # whole department roster (least-privilege; matches documented scope).
            from django.db.models import Q as _Q
            assigned_ids = list(scopes.get('division_ids', []) or [])
            if assigned_ids:
                div_qs = div_qs.filter(_Q(id__in=assigned_ids) | _Q(class_teacher_id=request.user.id))
            else:
                div_qs = div_qs.filter(class_teacher_id=request.user.id)
        else:
            return Response([], status=status.HTTP_200_OK)

        divisions = list(div_qs.order_by('department__name', 'semester__number', 'name'))
        data = []

        # F-S4-002: Bulk pre-fetch all counts in constant (~4) queries instead of looping per division
        valid_divs = [d for d in divisions if d.semester is not None]
        valid_div_ids = [d.id for d in valid_divs]

        # 1. Bulk current enrollments
        div_to_students = {d.id: [] for d in valid_divs}
        all_student_ids = set()
        enr_qs = StudentEnrollment.objects.filter(
            division_id__in=valid_div_ids, is_current=True
        ).values('division_id', 'student_id')
        for e in enr_qs:
            div_to_students[e['division_id']].append(e['student_id'])
            all_student_ids.add(e['student_id'])

        # 2. Bulk promoted counts
        promoted_counts_qs = StudentEnrollment.objects.filter(
            division_id__in=valid_div_ids, status=StudentEnrollment.Status.PROMOTED
        ).values('division_id').annotate(count=models.Count('id'))
        div_to_promoted_count = {p['division_id']: p['count'] for p in promoted_counts_qs}

        # 3. Bulk published semester results
        sem_res_qs = SemesterResult.objects.filter(
            student_id__in=all_student_ids,
            is_published=True,
        ).exclude(result_status=SemesterResult.ResultStatus.NOT_YET_HELD).values('student_id', 'semester_id')
        published_results = {(r['student_id'], r['semester_id']) for r in sem_res_qs}

        # 4. Bulk eligibility verifications
        ev_qs = EligibilityVerification.objects.filter(
            student_id__in=all_student_ids,
        ).values(
            'student_id', 'target_semester__number',
            'class_teacher_status', 'hod_status', 'final_eligible'
        )
        student_target_to_evs = {}
        for ev in ev_qs:
            key = (ev['student_id'], ev['target_semester__number'])
            student_target_to_evs[key] = ev

        # 5. Bulk stuck-unpromoted: endorsed + paid for the completing year,
        # yet still seated below the target semester (auto-promotion misfired
        # or is pending HOD action). Same completing-year rule as
        # check_and_promote_student. +3 queries total, not per division.
        from apps.finance.models import PaymentLedger
        cur_qs = StudentEnrollment.objects.filter(
            student_id__in=all_student_ids, is_current=True
        ).values('student_id', 'semester__number', 'division_id')
        cur_by_student = {c['student_id']: c for c in cur_qs}
        final_qs = EligibilityVerification.objects.filter(
            student_id__in=all_student_ids, final_eligible=True,
        ).values('student_id', 'target_semester__number')
        paid_years = set(PaymentLedger.objects.filter(
            student_id__in=all_student_ids,
            status=PaymentLedger.PaymentStatus.PAID,
        ).values_list('student_id', 'academic_year_id'))
        div_ay = {d.id: d.academic_year_id for d in valid_divs}
        div_to_stuck = {d.id: 0 for d in valid_divs}
        for fev in final_qs:
            sid = fev['student_id']
            cur = cur_by_student.get(sid)
            if not cur or not cur['division_id']:
                continue
            if (fev['target_semester__number'] or 0) <= (cur['semester__number'] or 0):
                continue
            if (sid, div_ay.get(cur['division_id'])) not in paid_years:
                continue
            div_to_stuck[cur['division_id']] = div_to_stuck.get(cur['division_id'], 0) + 1

        for div in divisions:
            try:
                if div.semester is None:
                    logger.warning('classes: skipping division %s with no semester', div.id)
                    continue
                sem_num = div.semester.number
                is_year_change = sem_num in [2, 4, 6]
                target_sem_num = sem_num + 1 if is_year_change else sem_num

                enrollments = div_to_students.get(div.id, [])
                total_students = len(enrollments)
                promoted_count = div_to_promoted_count.get(div.id, 0)
                if total_students == 0 and promoted_count == 0:
                    continue

                results_filled_count = sum(
                    1 for sid in enrollments if (sid, div.semester_id) in published_results
                )

                matched_evs = [
                    student_target_to_evs[(sid, target_sem_num)]
                    for sid in enrollments
                    if (sid, target_sem_num) in student_target_to_evs
                ]
                ev_count = len(matched_evs)
                teacher_approved_count = sum(
                    1 for e in matched_evs
                    if e['class_teacher_status'] == EligibilityVerification.StageStatus.APPROVED
                )
                hod_approved_count = sum(
                    1 for e in matched_evs
                    if e['hod_status'] == EligibilityVerification.StageStatus.APPROVED
                )
                final_eligible_count = sum(
                    1 for e in matched_evs if e['final_eligible']
                )
                flagged_count = sum(
                    1 for e in matched_evs
                    if e['class_teacher_status'] == EligibilityVerification.StageStatus.FLAGGED
                    or e['hod_status'] == EligibilityVerification.StageStatus.FLAGGED
                )

                has_teacher = div.class_teacher_id is not None

                can_start = (
                    is_year_change and has_teacher and (
                        scopes['is_system_wide'] or
                        'ADMIN_HEAD' in scopes['roles'] or
                        ('HOD' in scopes['roles'] and div.department_id in scopes['department_ids']) or
                        ('CLASS_TEACHER' in scopes['roles'] and (
                            div.class_teacher_id == request.user.id or
                            str(div.id) in {str(x) for x in scopes.get('division_ids', [])}
                        ))
                    )
                )

                can_promote = (
                    is_year_change and (
                        scopes['is_system_wide'] or
                        'ADMIN_HEAD' in scopes['roles'] or
                        ('HOD' in scopes['roles'] and div.department_id in scopes['department_ids'])
                    )
                )

                year_level_label = {
                    1: 'First Year (FY)',
                    2: 'Second Year (SY)',
                    3: 'Third Year (TY)',
                    4: 'Final Year (B.Tech)',
                }.get(div.semester.year_level, f'Year {div.semester.year_level}')

                data.append({
                    'division_id': str(div.id),
                    'division_name': div.name,
                    'class_name': f"{year_level_label} - Div {div.name} (Sem {sem_num})",
                    'department_id': str(div.department_id),
                    'department_code': div.department.code if div.department else '—',
                    'department_name': div.department.name if div.department else '—',
                    'semester_number': sem_num,
                    'semester_name': div.semester.name,
                    'year_level': div.semester.year_level,
                    'year_level_label': year_level_label,
                    'class_teacher_name': staff_display_name(div.class_teacher) or 'Unassigned',
                    'has_class_teacher': has_teacher,
                    'is_year_change_class': is_year_change,
                    'target_semester_number': target_sem_num,
                    'total_students': total_students,
                    'active_students_count': total_students,
                    'promoted_count': promoted_count,
                    'stuck_unpromoted_count': div_to_stuck.get(div.id, 0),
                    'results_filled_count': results_filled_count,
                    'teacher_approved_count': teacher_approved_count,
                    'hod_approved_count': hod_approved_count,
                    'final_eligible_count': final_eligible_count,
                    'flagged_count': flagged_count,
                    'is_verification_started': ev_count > 0,
                    'can_start_verification': can_start,
                    'can_promote_class': can_promote,
                    'active_term': active_term,
                    'academic_year_code': div.academic_year.code if div.academic_year else '',
                })
            except Exception:
                # One bad division must never break the whole class list.
                logger.exception('classes: skipped corrupt division %s', getattr(div, 'id', '?'))

        return Response(data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='class-roster')
    def class_roster(self, request):
        """Returns student roster for a specific division with pipeline status."""
        import uuid as _uuid
        from apps.academic_structure.models import Division, Semester
        from apps.students.models import StudentEnrollment
        from apps.results.models import SemesterResult

        division_id = request.query_params.get('division_id')
        if not division_id:
            return Response({'detail': 'division_id query parameter is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            _uuid.UUID(str(division_id))
        except (ValueError, AttributeError, TypeError):
            return Response({'detail': 'Invalid division_id.'}, status=status.HTTP_400_BAD_REQUEST)

        div = Division.objects.filter(id=division_id).select_related(
            'department', 'semester', 'class_teacher',
            'class_teacher__faculty_profile', 'academic_year').first()
        if not div:
            return Response({'detail': 'Division not found.'}, status=status.HTTP_404_NOT_FOUND)

        scopes = get_user_scopes(request.user)
        if not (scopes['is_system_wide'] or 'ADMIN_HEAD' in scopes['roles']):
            if 'HOD' in scopes['roles']:
                if div.department_id not in scopes['department_ids']:
                    return Response({'detail': 'You do not have access to this department.'}, status=status.HTTP_403_FORBIDDEN)
            elif 'CLASS_TEACHER' in scopes['roles']:
                # Assigned teacher only (Division.class_teacher or explicit
                # division scope). Same-department but unassigned CTs are denied
                # — roster contains marks/SGPA, so dept fallback would leak PII.
                _assigned_div_ids = {str(x) for x in scopes.get('division_ids', [])}
                is_assigned = (div.class_teacher_id == request.user.id or str(div.id) in _assigned_div_ids)
                if not is_assigned:
                    return Response({'detail': 'You do not have access to this division.'}, status=status.HTTP_403_FORBIDDEN)
            else:
                return Response({'detail': 'Access denied.'}, status=status.HTTP_403_FORBIDDEN)

        if div.semester is None:
            return Response({'detail': 'This division has no semester assigned. Contact Admin Head.'}, status=status.HTTP_400_BAD_REQUEST)
        if div.department is None:
            return Response({'detail': 'This division has no department assigned. Contact Admin Head.'}, status=status.HTTP_400_BAD_REQUEST)

        sem_num = div.semester.number
        is_year_change = sem_num in [2, 4, 6]
        target_sem_num = sem_num + 1 if is_year_change else sem_num

        enrollments = list(StudentEnrollment.objects.filter(
            division=div, is_current=True
        ).select_related('student', 'semester').order_by('roll_number', 'student__display_name'))

        # Students promoted OUT of this class in this cycle: their PROMOTED
        # enrollment row still points at this division while their current
        # enrollment moved ahead. They no longer count toward this class, but
        # the HOD must still see them here with their new semester.
        promoted_rows = list(StudentEnrollment.objects.filter(
            division=div, status=StudentEnrollment.Status.PROMOTED,
        ).select_related('student', 'semester').order_by('student__display_name'))
        current_ids = {e.student_id for e in enrollments}
        current_map = {
            e.student_id: e
            for e in StudentEnrollment.objects.filter(
                student_id__in=[e.student_id for e in promoted_rows],
                is_current=True,
            ).select_related('semester', 'division')
        }
        promoted_rows = [
            e for e in promoted_rows
            if e.student_id not in current_ids
            and e.student_id in current_map
            and current_map[e.student_id].semester_id != div.semester_id
        ]

        student_ids = [e.student_id for e in enrollments] + [e.student_id for e in promoted_rows]

        results_map = {
            r.student_id: r
            for r in SemesterResult.objects.filter(
                student_id__in=student_ids,
                semester=div.semester,
                is_published=True,
            ).prefetch_related('subject_results')
        }

        target_sem = Semester.objects.filter(number=target_sem_num).first() or div.semester
        ev_map = {
            ev.student_id: ev
            for ev in EligibilityVerification.objects.filter(
                student_id__in=student_ids,
                target_semester=target_sem,
            ).select_related(
                'class_teacher', 'class_teacher__faculty_profile',
                'hod', 'hod__faculty_profile',
            )
        }

        # One-time profile lock per student (1 query, no N+1). Missing rows
        # (should not happen — enrollments always point at students) default
        # to unlocked so the teacher sees the blocking reason, never a 500.
        locked_map = dict(
            Student.objects.filter(id__in=student_ids).values_list('id', 'profile_locked')
        )
        # Strict gate mirror: filled-results coverage per student (1 query)
        # plus DSY start (lateral entry starts at Sem 3). Roster rows gate
        # review on EVERY semester 1..current being published.
        stu_info = {
            r['id']: r for r in Student.objects.filter(
                id__in=student_ids).values('id', 'is_direct_second_year', 'admission_type')
        }
        filled_map = {}
        for _sid, _num in SemesterResult.objects.filter(
            student_id__in=student_ids, is_published=True,
        ).exclude(
            result_status=SemesterResult.ResultStatus.NOT_YET_HELD
        ).values_list('student_id', 'semester__number'):
            filled_map.setdefault(_sid, set()).add(_num)

        can_teacher_review = (
            scopes['is_system_wide'] or
            request.user.is_superuser or
            ('CLASS_TEACHER' in scopes['roles'] and (
                div.class_teacher_id == request.user.id or
                str(div.id) in {str(x) for x in scopes.get('division_ids', [])}
            ))
        )
        can_hod_endorse = (
            scopes['is_system_wide'] or
            'ADMIN_HEAD' in scopes['roles'] or
            ('HOD' in scopes['roles'] and div.department_id in scopes['department_ids'])
        )

        def build_row(stu, roll_number, current_sem_num, moved_up=False):
            sr = results_map.get(stu.id)
            ev = ev_map.get(stu.id)

            has_result = sr is not None and sr.result_status != SemesterResult.ResultStatus.NOT_YET_HELD
            profile_locked = bool(locked_map.get(stu.id, False))
            # Strict mirror of services._require_student_ready_for_review:
            # EVERY semester start..current must be published (DSY from 3).
            _info = stu_info.get(stu.id, {})
            _dsy = bool(_info.get('is_direct_second_year')) or str(
                _info.get('admission_type') or '').upper() == 'DSE'
            _need = set(range(3 if _dsy else 1, (current_sem_num or 1) + 1))
            missing_result_semesters = sorted(_need - filled_map.get(stu.id, set()))
            # Mirror of services._require_student_ready_for_review so the UI
            # disables Review with the exact blocking reason (no silent fail).
            if not profile_locked:
                review_blocked_reason = 'PROFILE_UNLOCKED'
            elif missing_result_semesters:
                review_blocked_reason = 'RESULT_PENDING'
            else:
                review_blocked_reason = None

            if moved_up:
                stage = 'PROMOTED'
            elif not has_result:
                stage = 'RESULT_PENDING'
            elif ev and (ev.class_teacher_status == EligibilityVerification.StageStatus.FLAGGED or ev.hod_status == EligibilityVerification.StageStatus.FLAGGED):
                stage = 'FLAGGED'
            elif ev and (ev.class_teacher_status == EligibilityVerification.StageStatus.REJECTED or ev.hod_status == EligibilityVerification.StageStatus.REJECTED):
                stage = 'FAILED'
            elif ev and ev.final_eligible:
                stage = 'ELIGIBLE'
            elif ev and ev.class_teacher_status == EligibilityVerification.StageStatus.APPROVED:
                stage = 'HOD_PENDING'
            elif ev and ev.class_teacher_status == EligibilityVerification.StageStatus.PENDING:
                stage = 'TEACHER_PENDING'
            else:
                stage = 'RESULT_FILLED'

            return {
                'student_id': str(stu.id),
                'student_name': stu.display_name,
                'enrollment_no': stu.enrollment_no,
                'roll_number': roll_number,
                'current_semester': current_sem_num,
                'is_direct_second_year': _dsy,
                'target_semester': target_sem_num,
                'moved_up': moved_up,
                'result_filled': has_result,
                'semester_result': {
                    'sgpa': str(sr.sgpa) if sr and sr.sgpa is not None else '—',
                    'cgpa': str(sr.cgpa) if sr and sr.cgpa is not None else '—',
                    'backlog_count': sr.backlog_count if sr else 0,
                    'result_status': sr.result_status if sr else 'NOT_YET_HELD',
                    'result_status_display': sr.get_result_status_display() if sr else 'Pending',
                } if sr else None,
                'eligibility_id': str(ev.id) if ev else None,
                'calculated_status': ev.calculated_status if ev else None,
                'calculated_status_display': ev.get_calculated_status_display() if ev else None,
                'class_teacher_status': ev.class_teacher_status if ev else 'NOT_STARTED',
                'class_teacher_status_display': ev.get_class_teacher_status_display() if ev else 'Not Started',
                'class_teacher_remarks': ev.class_teacher_remarks if ev else '',
                'class_teacher_name': staff_display_name(ev.class_teacher) if ev and ev.class_teacher else '',
                'hod_status': ev.hod_status if ev else 'NOT_STARTED',
                'hod_status_display': ev.get_hod_status_display() if ev else 'Not Started',
                'hod_remarks': ev.hod_remarks if ev else '',
                'hod_name': staff_display_name(ev.hod) if ev and ev.hod else '',
                'final_eligible': ev.final_eligible if ev else False,
                'is_locked_for_teacher': ev.is_locked_for_teacher if ev else False,
                'pipeline_stage': stage,
                'profile_locked': profile_locked,
                'review_blocked_reason': review_blocked_reason,
                'missing_result_semesters': missing_result_semesters,
                'can_review_teacher': (not moved_up) and can_teacher_review and (
                    ev is not None and not ev.is_locked_for_teacher and review_blocked_reason is None),
                'can_endorse_hod': (not moved_up) and can_hod_endorse and (
                    ev is not None and (
                        ev.class_teacher_status in (EligibilityVerification.StageStatus.APPROVED, EligibilityVerification.StageStatus.REJECTED)
                        or ev.hod_status == EligibilityVerification.StageStatus.REJECTED
                    ) and review_blocked_reason is None
                ),
            }

        # Fail-soft per row: one corrupt enrollment/result/EV record must
        # never 500 the whole roster for the class teacher. Bad rows are
        # skipped, counted, and logged for admin follow-up.
        students_data = []
        skipped_rows = 0
        for enr in enrollments:
            try:
                if enr.student_id is None:
                    raise ValueError('enrollment missing student')
                students_data.append(build_row(
                    enr.student, enr.roll_number or '—',
                    enr.semester.number if enr.semester else sem_num,
                ))
            except Exception:
                skipped_rows += 1
                logger.exception('class-roster: skipped corrupt enrollment %s in division %s', getattr(enr, 'id', '?'), division_id)
        promoted_data = []
        for e in promoted_rows:
            try:
                cur = current_map.get(e.student_id)
                if cur is None or e.student_id is None:
                    raise ValueError('promoted row missing current enrollment')
                promoted_data.append(build_row(
                    e.student, e.roll_number or '—',
                    cur.semester.number if cur.semester else target_sem_num,
                    moved_up=True,
                ))
            except Exception:
                skipped_rows += 1
                logger.exception('class-roster: skipped corrupt promoted row %s in division %s', getattr(e, 'id', '?'), division_id)

        payload = {
            'division_id': str(div.id),
            'division_name': div.name,
            'class_name': f"{div.semester.name} - Div {div.name}",
            'department_code': div.department.code if div.department else '—',
            'department_name': div.department.name if div.department else '—',
            'semester_number': sem_num,
            'target_semester_number': target_sem_num,
            'total_students': len(students_data),
            'active_students_count': len(students_data),
            'promoted_count': len(promoted_data),
            'promoted_students': promoted_data,
            'can_teacher_review': can_teacher_review,
            'can_hod_endorse': can_hod_endorse,
            'students': students_data,
            'skipped_rows': skipped_rows,
        }
        if skipped_rows:
            payload['warning'] = f"{skipped_rows} record(s) skipped due to corrupt data. Contact Admin Head."
        return Response(payload, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='start-class-verification')
    def start_class_verification(self, request):
        """Initializes or opens verification for all students in a specific division."""
        import uuid as _uuid
        from django.db import transaction as _transaction
        from apps.academic_structure.models import Division, Semester
        from apps.audit.models import AuditLog
        from apps.audit.services import audit_log
        from apps.results.services import evaluate_student_eligibility
        from apps.students.models import StudentEnrollment

        division_id = request.data.get('division_id')
        if not division_id:
            return Response({'detail': 'division_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            _uuid.UUID(str(division_id))
        except (ValueError, AttributeError, TypeError):
            return Response({'detail': 'Invalid division_id.'}, status=status.HTTP_400_BAD_REQUEST)

        div = Division.objects.filter(id=division_id).select_related('department', 'semester', 'academic_year').first()
        if not div:
            return Response({'detail': 'Division not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Production guard: verification is meaningless without the teacher
        # who must review it. The class needs its teacher assigned first
        # (Classes & Divisions → Set teacher). No role bypasses this —
        # assigning a teacher takes seconds on the HOD page.
        if not div.class_teacher_id:
            return Response(
                {'detail': 'Assign a class teacher to this division before starting verification.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        scopes = get_user_scopes(request.user)
        allowed = scopes['is_system_wide'] or 'ADMIN_HEAD' in scopes['roles']
        if not allowed:
            if 'HOD' in scopes['roles'] and div.department_id in scopes['department_ids']:
                allowed = True
            elif 'CLASS_TEACHER' in scopes['roles'] and (
                div.class_teacher_id == request.user.id or str(div.id) in {str(x) for x in scopes.get('division_ids', [])}
            ):
                allowed = True

        if not allowed:
            return Response({'detail': 'Only HOD, Class Teacher, or Admin can start verification.'}, status=status.HTTP_403_FORBIDDEN)

        sem_num = div.semester.number
        # Only year-change classes (Sem 2/4/6 → targets 3/5/7) have a verification
        # cycle. Matches classes() target formula; Sem 8 uses graduation queue.
        if sem_num not in (2, 4, 6):
            return Response(
                {'detail': 'Verification can only be started for year-change classes (Sem 2, 4, 6).'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        target_sem_num = sem_num + 1
        # Semester.number is unique (academic_structure/models.py), so a plain
        # number lookup is authoritative — no academic-year scoping needed.
        target_sem = Semester.objects.filter(number=target_sem_num).first()
        if target_sem is None:
            return Response({'detail': 'Target semester not configured.'}, status=status.HTTP_400_BAD_REQUEST)

        enrollments = list(StudentEnrollment.objects.filter(
            division=div, is_current=True
        ).select_related('student', 'academic_year'))

        with _transaction.atomic():
            created = 0
            for enr in enrollments:
                exists = EligibilityVerification.objects.filter(
                    student=enr.student,
                    academic_year=enr.academic_year,
                    target_semester=target_sem,
                ).exists()
                if not exists:
                    evaluate_student_eligibility(enr.student, target_sem)
                    created += 1

            is_resync = (created == 0 and len(enrollments) > 0)
            audit_log(
                request=request, actor=request.user, action=AuditLog.Action.CREATE,
                target_type='EligibilityVerification', target_id=str(div.id),
                target_display=f'{"Re-synced" if is_resync else "Started"} verification for {div.department.code} Sem {sem_num} Div {div.name}',
                new_value={'division_id': str(div.id), 'created': created, 'total': len(enrollments)},
                reason='Class verification initiated',
                description=f"{'Re-synced' if is_resync else 'Initiated'} verification cycle for {div.department.code} Sem {sem_num} Div {div.name} ({created} new rows, {len(enrollments)} total).",
            )

        detail_msg = (
            f"Verification already up to date for {div.semester.name} Div {div.name} ({len(enrollments)} in queue)."
            if created == 0 else
            f"Verification cycle started for {div.semester.name} Div {div.name}. {created} verifications initialized."
        )
        return Response({
            'detail': detail_msg,
            'created': created,
            'total': len(enrollments),
            'division_id': str(div.id),
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='initialize')
    def initialize(self, request):
        """Create missing PENDING verification rows for the caller's scope.

        Fresh imports have results but no EligibilityVerification rows yet
        (rows are otherwise born on marks submission), so the verification
        queue stays empty. Class Teacher initializes their division, HOD
        their department, Sysadmin/Admin Head optionally one department.
        Idempotent: existing (student, year, target) rows are never remade.
        """
        from apps.academic_structure.models import Semester
        from apps.audit.models import AuditLog
        from apps.audit.services import audit_log
        from apps.results.services import evaluate_student_eligibility

        scopes = get_user_scopes(request.user)
        if scopes['is_system_wide'] or 'ADMIN_HEAD' in scopes['roles']:
            enroll_qs = StudentEnrollment.objects.filter(is_current=True)
            dept_param = (request.data or {}).get('department_id')
            if dept_param:
                enroll_qs = enroll_qs.filter(department_id=dept_param)
        elif 'HOD' in scopes['roles']:
            enroll_qs = StudentEnrollment.objects.filter(
                is_current=True, department_id__in=scopes['department_ids'])
        elif 'CLASS_TEACHER' in scopes['roles']:
            from apps.academic_structure.models import Division as _Division
            _assigned = {str(x) for x in (scopes.get('division_ids') or [])}
            _assigned |= {str(x) for x in _Division.objects.filter(class_teacher_id=request.user.id).values_list('id', flat=True)}
            if not _assigned:
                return Response(
                    {'detail': 'No class assigned to you yet.'},
                    status=status.HTTP_400_BAD_REQUEST)
            enroll_qs = StudentEnrollment.objects.filter(
                is_current=True, division_id__in=list(_assigned))
        else:
            return Response(
                {'detail': 'Only Class Teacher, HOD, or Admin can initialize verifications.'},
                status=status.HTTP_403_FORBIDDEN)

        enrollments = list(enroll_qs.filter(
            semester__number__in=[2, 4, 6]).select_related('student', 'semester', 'academic_year'))
        # Teacher gate (same rule as start-class-verification): students in a
        # division with no assigned class teacher are skipped — nobody could
        # review their rows. Division-less enrollments still initialize (the
        # HOD places them into a class next).
        teacher_div_ids = set()
        pending_div_ids = {str(e.division_id) for e in enrollments if e.division_id}
        if pending_div_ids:
            from apps.academic_structure.models import Division as _Division
            teacher_div_ids = {
                str(d) for d in _Division.objects.filter(
                    id__in=pending_div_ids).exclude(
                    class_teacher__isnull=True).values_list('id', flat=True)
            }
        created = 0
        skipped_no_teacher = 0
        for enr in enrollments:
            if enr.division_id and str(enr.division_id) not in teacher_div_ids:
                skipped_no_teacher += 1
                continue
            target = Semester.objects.filter(number=enr.semester.number + 1).first() or enr.semester
            exists = EligibilityVerification.objects.filter(
                student=enr.student, academic_year=enr.academic_year,
                target_semester=target).exists()
            if not exists:
                evaluate_student_eligibility(enr.student, target)
                created += 1

        audit_log(
            request=request, actor=request.user, action=AuditLog.Action.CREATE,
            target_type='EligibilityVerification', target_id='bulk-init',
            target_display=f'Initialized {created}/{len(enrollments)} verifications',
            new_value={'created': created, 'in_scope': len(enrollments), 'skipped_no_teacher': skipped_no_teacher},
            reason='Verification queue bootstrap for class/department',
            description=f"Initialized {created} pending eligibility verifications ({len(enrollments)} in scope, {skipped_no_teacher} skipped: no class teacher).",
        )
        detail_msg = f'{created} verification(s) ready for review.'
        if skipped_no_teacher:
            detail_msg += f' {skipped_no_teacher} skipped — assign a class teacher to their division first.'
        return Response(
            {'detail': detail_msg, 'created': created, 'total': len(enrollments),
             'skipped_no_teacher': skipped_no_teacher},
            status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='review-class-teacher')
    def review_class_teacher(self, request, pk=None):
        """Class teacher approves or flags candidate eligibility.

        Only the student's assigned division teacher (Division.class_teacher
        or a matching division-scoped CLASS_TEACHER assignment) may review;
        HOD uses the separate endorse step. Students without a division fall
        back to any same-department class teacher. Sysadmin may override.
        """
        # Fetch directly (not via filtered get_queryset) so list scoping
        # (assigned-only) never turns an allowed review into a 404.
        # The scope check below is authoritative.
        try:
            ev = EligibilityVerification.objects.select_related('student').get(id=pk)
        except EligibilityVerification.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        scopes = get_user_scopes(request.user)
        allowed = scopes['is_system_wide'] or request.user.is_superuser
        if not allowed and user_has_role(request.user, 'CLASS_TEACHER'):
            enr = ev.student.enrollments.filter(is_current=True).select_related('division').first()
            div_id = enr.division_id if enr and enr.division_id else None
            if div_id:
                from apps.academic_structure.models import Division
                div = Division.objects.filter(id=div_id).first()
                if div and div.class_teacher_id == request.user.id:
                    allowed = True
                elif str(div_id) in {str(d) for d in scopes.get('division_ids', [])}:
                    allowed = True
            elif enr and str(enr.department_id) in {str(d) for d in scopes.get('department_ids', [])}:
                allowed = True
        if not allowed:
            return Response(
                {'detail': 'Only the assigned class teacher of this student may review.'},
                status=status.HTTP_403_FORBIDDEN)

        decision = request.data.get('status', 'APPROVED')
        remarks = request.data.get('remarks', '')

        try:
            updated_ev = class_teacher_review_eligibility(
                eligibility_id=ev.id,
                reviewer_user=request.user,
                status_decision=decision,
                remarks=remarks,
                request=request,
            )
            # Keep per-semester correction flags in sync with the cycle
            # decision: a single FLAG reopens every published semester (the
            # remark may point at any of them), while APPROVE/REJECTED closes
            # all corrections. Bulk flag (below) narrows to ticked semesters.
            from apps.results.models import SemesterResult as _SemesterResult
            if decision == EligibilityVerification.StageStatus.FLAGGED:
                _SemesterResult.objects.filter(
                    student_id=ev.student_id, is_published=True,
                ).exclude(
                    result_status=_SemesterResult.ResultStatus.NOT_YET_HELD,
                ).update(
                    correction_requested=True,
                    correction_remarks=str(remarks or '')[:500],
                )
            elif decision in (
                EligibilityVerification.StageStatus.APPROVED,
                EligibilityVerification.StageStatus.REJECTED,
            ):
                _SemesterResult.objects.filter(
                    student_id=ev.student_id, correction_requested=True,
                ).update(correction_requested=False, correction_remarks='')
            return Response(EligibilityVerificationSerializer(updated_ev).data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], url_path='bulk-flag')
    def bulk_flag(self, request):
        """Flag corrections for one student across several semesters at once.

        Two input shapes (one required):
        - {student_id, semester_numbers: [3, 4, ...], remarks}: teacher ticks
          RESULT semesters 1..current in the review modal. Only those
          semesters reopen for the student; the current verification cycle
          is flagged alongside so re-review is queued. Each successful
          student resubmit clears its own semester only.
        - {student_id, target_semester_numbers: [2, 3, ...], remarks}:
          legacy direct verification-row flagging (kept for compatibility).

        The teacher ticks semesters in the review modal, writes ONE remarks
        note, and flags all chosen rows in a single atomic transaction:
        either every chosen row is flagged or none is (no partial flags).
        Only FLAGGED is allowed here - approvals stay single-row so each
        decision keeps its own audit trail. Only the flagged rows reopen
        for student correction; every other row keeps its state.
        Same scope + prerequisite gates as single review, per row.
        Teacher-only by design (mirrors review-class-teacher): HODs flag
        back one semester at a time via endorse-hod.
        """
        from django.db import transaction as _transaction
        from apps.academic_structure.models import Semester as _Semester

        student_id = request.data.get('student_id')
        raw_numbers = request.data.get('target_semester_numbers') or []
        remarks = str(request.data.get('remarks') or '').strip()
        if not student_id:
            return Response({'detail': 'student_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if not remarks:
            return Response(
                {'detail': 'Remarks are required — they become the permanent audit record.'},
                status=status.HTTP_400_BAD_REQUEST)
        if len(remarks) > 500:
            return Response(
                {'detail': 'Remarks must be 500 characters or fewer (audit record limit).'},
                status=status.HTTP_400_BAD_REQUEST)
        # New per-semester path: the teacher ticks RESULT semesters
        # 1..current; only those reopen for the student.
        if request.data.get('semester_numbers') is not None:
            return self._bulk_flag_by_semester(request)
        if not isinstance(raw_numbers, list) or not raw_numbers:
            return Response(
                {'detail': 'target_semester_numbers list is required (e.g. [2, 3]).'},
                status=status.HTTP_400_BAD_REQUEST)
        try:
            numbers = sorted({int(n) for n in raw_numbers})
        except (TypeError, ValueError):
            return Response(
                {'detail': 'target_semester_numbers must be integers 1-8.'},
                status=status.HTTP_400_BAD_REQUEST)
        if any(n < 1 or n > 8 for n in numbers):
            return Response(
                {'detail': 'target_semester_numbers must be integers 1-8.'},
                status=status.HTTP_400_BAD_REQUEST)
        if len(numbers) > 8:
            return Response({'detail': 'Too many semesters at once.'}, status=status.HTTP_400_BAD_REQUEST)

        student = Student.objects.filter(id=student_id).first()
        if student is None:
            return Response({'detail': 'Student not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Scope check once for the student (mirrors single review: assigned
        # division teacher, division scope, or same-department fallback).
        scopes = get_user_scopes(request.user)
        allowed = scopes['is_system_wide'] or request.user.is_superuser
        if not allowed and user_has_role(request.user, 'CLASS_TEACHER'):
            enr = student.enrollments.filter(is_current=True).select_related('division').first()
            div_id = enr.division_id if enr and enr.division_id else None
            if div_id:
                from apps.academic_structure.models import Division
                div = Division.objects.filter(id=div_id).first()
                if div and div.class_teacher_id == request.user.id:
                    allowed = True
                elif str(div_id) in {str(d) for d in scopes.get('division_ids', [])}:
                    allowed = True
            elif enr and str(enr.department_id) in {str(d) for d in scopes.get('department_ids', [])}:
                allowed = True
        if not allowed:
            return Response(
                {'detail': 'Only the assigned class teacher of this student may bulk-flag. '
                           'HODs flag semesters back one at a time via endorse-hod.'},
                status=status.HTTP_403_FORBIDDEN)

        # Resolve each chosen semester to its verification row: the latest
        # academic year wins when history rows exist for the same target.
        targets = []
        missing = []
        for num in numbers:
            sem = _Semester.objects.filter(number=num).first()
            if sem is None:
                missing.append(num)
                continue
            ev = EligibilityVerification.objects.filter(
                student=student, target_semester=sem
            ).select_related('academic_year').order_by(
                '-academic_year__start_date', '-created_at').first()
            if ev is None:
                missing.append(num)
            else:
                targets.append((num, ev))
        if missing:
            return Response(
                {'detail': f"No verification row for Sem {', '.join(str(n) for n in missing)}. Start verification first."},
                status=status.HTTP_400_BAD_REQUEST)

        try:
            with _transaction.atomic():
                flagged = []
                for num, ev in sorted(targets, key=lambda t: str(t[1].id)):
                    locked_ev = EligibilityVerification.objects.select_for_update().get(id=ev.id)
                    updated = class_teacher_review_eligibility(
                        eligibility_id=str(locked_ev.id),
                        reviewer_user=request.user,
                        status_decision=EligibilityVerification.StageStatus.FLAGGED,
                        remarks=remarks,
                        request=request,
                    )
                    flagged.append({
                        'eligibility_id': str(updated.id),
                        'target_semester_number': num,
                        'class_teacher_status': updated.class_teacher_status,
                    })
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {'detail': f"Flagged {len(flagged)} semester(s) for correction. Only those semesters reopen for the student.",
             'flagged': flagged},
            status=status.HTTP_200_OK,
        )

    def _bulk_flag_by_semester(self, request):
        """Per-semester flagging: teacher ticks RESULT semesters 1..current.

        Only the ticked semesters reopen for the student (each keeps its own
        correction flag, cleared independently on resubmit). The student's
        current verification cycle is flagged alongside so the roster shows
        FLAGGED and re-review is queued. All-or-nothing like the legacy path.
        """
        from django.db import transaction as _transaction
        from apps.academic_structure.models import Semester as _Semester
        from apps.results.services import evaluate_student_eligibility

        student_id = request.data.get('student_id')
        raw_numbers = request.data.get('semester_numbers') or []
        remarks = str(request.data.get('remarks') or '').strip()
        if not student_id:
            return Response({'detail': 'student_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if not remarks:
            return Response(
                {'detail': 'Remarks are required — they become the permanent audit record.'},
                status=status.HTTP_400_BAD_REQUEST)
        if len(remarks) > 500:
            return Response(
                {'detail': 'Remarks must be 500 characters or fewer (audit record limit).'},
                status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(raw_numbers, list) or not raw_numbers:
            return Response(
                {'detail': 'semester_numbers list is required (e.g. [3, 4]).'},
                status=status.HTTP_400_BAD_REQUEST)
        try:
            numbers = sorted({int(n) for n in raw_numbers})
        except (TypeError, ValueError):
            return Response(
                {'detail': 'semester_numbers must be integers 1-8.'},
                status=status.HTTP_400_BAD_REQUEST)
        if any(n < 1 or n > 8 for n in numbers):
            return Response(
                {'detail': 'semester_numbers must be integers 1-8.'},
                status=status.HTTP_400_BAD_REQUEST)
        if len(numbers) > 8:
            return Response({'detail': 'Too many semesters at once.'}, status=status.HTTP_400_BAD_REQUEST)

        student = Student.objects.filter(id=student_id).first()
        if student is None:
            return Response({'detail': 'Student not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Same teacher scope gate as the legacy path.
        scopes = get_user_scopes(request.user)
        allowed = scopes['is_system_wide'] or request.user.is_superuser
        if not allowed and user_has_role(request.user, 'CLASS_TEACHER'):
            enr = student.enrollments.filter(is_current=True).select_related('division').first()
            div_id = enr.division_id if enr and enr.division_id else None
            if div_id:
                from apps.academic_structure.models import Division
                div = Division.objects.filter(id=div_id).first()
                if div and div.class_teacher_id == request.user.id:
                    allowed = True
                elif str(div_id) in {str(d) for d in scopes.get('division_ids', [])}:
                    allowed = True
            elif enr and str(enr.department_id) in {str(d) for d in scopes.get('department_ids', [])}:
                allowed = True
        if not allowed:
            return Response(
                {'detail': 'Only the assigned class teacher of this student may bulk-flag. '
                           'HODs flag semesters back one at a time via endorse-hod.'},
                status=status.HTTP_403_FORBIDDEN)

        enr = student.enrollments.filter(is_current=True).select_related('semester').first()
        cur_num = enr.semester.number if enr and enr.semester else None
        if cur_num is None:
            return Response(
                {'detail': 'Student has no active enrollment. Review is blocked.'},
                status=status.HTTP_400_BAD_REQUEST)
        _row = Student.objects.filter(id=student.id).values(
            'is_direct_second_year', 'admission_type').first() or {}
        _dsy = bool(_row.get('is_direct_second_year')) or str(
            _row.get('admission_type') or '').upper() == 'DSE'
        _start = 3 if _dsy else 1
        out_of_range = [n for n in numbers if n < _start or n > cur_num]
        if out_of_range:
            return Response(
                {'detail': f"Semester {', '.join(str(n) for n in out_of_range)} is out of range — "
                           f"this student is in Sem {cur_num} (corrections open Sem {_start}..{cur_num})."},
                status=status.HTTP_400_BAD_REQUEST)

        # Every ticked semester must have a filled, published result to correct.
        rows = SemesterResult.objects.filter(
            student=student, semester__number__in=numbers, is_published=True,
        ).exclude(
            result_status=SemesterResult.ResultStatus.NOT_YET_HELD,
        ).select_related('semester', 'academic_year').order_by(
            '-academic_year__start_date', '-created_at')
        by_num = {}
        for r in rows:
            by_num.setdefault(r.semester.number, r)
        missing = [n for n in numbers if n not in by_num]
        if missing:
            return Response(
                {'detail': f"Sem {', '.join(str(n) for n in missing)} has no filled result to correct yet."},
                status=status.HTTP_400_BAD_REQUEST)

        # The student's current verification cycle rides along so the roster
        # shows FLAGGED and the teacher re-review is queued.
        target_num = cur_num + 1 if cur_num in (2, 4, 6) else cur_num
        target_sem = _Semester.objects.filter(number=target_num).first()
        if target_sem is None:
            return Response(
                {'detail': f'Semester {target_num} not found.'},
                status=status.HTTP_400_BAD_REQUEST)

        try:
            with _transaction.atomic():
                ev = EligibilityVerification.objects.filter(
                    student=student, target_semester=target_sem,
                ).select_related('academic_year').order_by(
                    '-academic_year__start_date', '-created_at').first()
                if ev is None:
                    ev = evaluate_student_eligibility(student, target_sem)
                locked_ev = EligibilityVerification.objects.select_for_update().get(id=ev.id)
                updated = class_teacher_review_eligibility(
                    eligibility_id=str(locked_ev.id),
                    reviewer_user=request.user,
                    status_decision=EligibilityVerification.StageStatus.FLAGGED,
                    remarks=remarks,
                    request=request,
                )
                flagged = []
                for num in numbers:
                    locked_row = SemesterResult.objects.select_for_update().get(id=by_num[num].id)
                    locked_row.correction_requested = True
                    locked_row.correction_remarks = remarks[:500]
                    locked_row.save(update_fields=['correction_requested', 'correction_remarks', 'updated_at'])
                    flagged.append({
                        'semester_number': num,
                        'class_teacher_status': updated.class_teacher_status,
                    })
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {'detail': f"Flagged {len(flagged)} semester(s) for correction. Only those semesters reopen for the student.",
             'flagged': flagged},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=['post'], url_path='endorse-hod')
    def endorse_hod(self, request, pk=None):
        """HOD approves or flags/rejects candidate eligibility."""
        try:
            ev = EligibilityVerification.objects.select_related('student').get(id=pk)
        except EligibilityVerification.DoesNotExist:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        scopes = get_user_scopes(request.user)
        if not (scopes['is_system_wide'] or 'ADMIN_HEAD' in scopes['roles']):
            if 'HOD' in scopes['roles']:
                allowed = {str(d) for d in scopes.get('department_ids', [])}
                # Fix 14: prefer live current enrollment dept so transfers move
                # to new HOD; snapshot is fallback only when no live enrollment.
                live_enr = ev.student.enrollments.filter(is_current=True).first()
                if live_enr and live_enr.department_id:
                    if str(live_enr.department_id) not in allowed:
                        return Response({'detail': 'HOD may only endorse eligibility for their own department.'}, status=status.HTTP_403_FORBIDDEN)
                elif str(ev.department_id) not in allowed:
                    return Response({'detail': 'HOD may only endorse eligibility for their own department.'}, status=status.HTTP_403_FORBIDDEN)
            else:
                return Response({'detail': 'Only the HOD or Admin can endorse departmental eligibility.'}, status=status.HTTP_403_FORBIDDEN)

        decision = request.data.get('status', 'APPROVED')
        remarks = request.data.get('remarks', '')

        try:
            updated_ev = hod_endorse_eligibility(
                eligibility_id=ev.id,
                hod_user=request.user,
                status_decision=decision,
                remarks=remarks,
                request=request,
            )
            # Any HOD decision closes outstanding per-semester corrections:
            # APPROVE/REJECTED finalise the cycle, and FLAGGED-back hands the
            # cycle to the teacher, who re-flags the exact semesters afresh.
            from apps.results.models import SemesterResult as _SemesterResult
            if decision in (
                EligibilityVerification.StageStatus.APPROVED,
                EligibilityVerification.StageStatus.FLAGGED,
                EligibilityVerification.StageStatus.REJECTED,
            ):
                _SemesterResult.objects.filter(
                    student_id=ev.student_id, correction_requested=True,
                ).update(correction_requested=False, correction_remarks='')
            data = EligibilityVerificationSerializer(updated_ev).data
            outcome = getattr(updated_ev, '_promotion_outcome', None)
            if outcome is not None:
                data['promotion'] = outcome
            return Response(data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'], url_path='admission-form-data')
    def admission_form_data(self, request):
        """Returns structured data for the student's admission verification form."""
        user = request.user
        scopes = get_user_scopes(user)
        student_id = request.query_params.get('student_id')
        eligibility_id = request.query_params.get('eligibility_id')

        student = None
        if student_id:
            student = Student.objects.filter(id=student_id).first()
            if not student:
                return Response({'detail': 'Student profile not found.'}, status=status.HTTP_404_NOT_FOUND)
            if not _admission_student_allowed(user, scopes, student):
                return Response({'detail': 'You do not have access to this student.'}, status=status.HTTP_403_FORBIDDEN)
        elif hasattr(user, 'student_profile'):
            student = user.student_profile
        else:
            student = Student.objects.filter(user_id=user.id).first()

        if not student:
            return Response({'detail': 'Student profile not found.'}, status=status.HTTP_404_NOT_FOUND)

        ev = None
        if eligibility_id:
            ev = EligibilityVerification.objects.filter(id=eligibility_id, student=student).first()

        from apps.results.pdf_service import get_student_admission_form_data
        data = get_student_admission_form_data(student, eligibility=ev)
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='admission-form-pdf')
    def admission_form_pdf(self, request):
        """Downloads the official generated A4 Admission Verification Form PDF."""
        from django.http import HttpResponse
        user = request.user
        scopes = get_user_scopes(user)
        student_id = request.query_params.get('student_id')
        eligibility_id = request.query_params.get('eligibility_id')

        student = None
        if student_id:
            student = Student.objects.filter(id=student_id).first()
            if not student:
                return Response({'detail': 'Student profile not found.'}, status=status.HTTP_404_NOT_FOUND)
            if not _admission_student_allowed(user, scopes, student):
                return Response({'detail': 'You do not have access to this student.'}, status=status.HTTP_403_FORBIDDEN)
        elif hasattr(user, 'student_profile'):
            student = user.student_profile
        else:
            student = Student.objects.filter(user_id=user.id).first()

        if not student:
            return Response({'detail': 'Student profile not found.'}, status=status.HTTP_404_NOT_FOUND)

        ev = None
        if eligibility_id:
            ev = EligibilityVerification.objects.filter(id=eligibility_id, student=student).first()

        from apps.results.pdf_service import get_student_admission_form_data, generate_admission_verification_pdf
        data = get_student_admission_form_data(student, eligibility=ev)
        # UI gate is not enough: students may download only when HOD-endorsed.
        # Staff (HOD/CT/Accountant/Admin) still need pre-approval access for review.
        _roles = scopes.get('roles', [])
        _is_staff = bool(scopes.get('is_system_wide') or any(r in _roles for r in ('ADMIN_HEAD', 'ACCOUNTANT', 'HOD', 'CLASS_TEACHER')))
        if not _is_staff and not data.get('can_download'):
            return Response({'detail': 'Official PDF unlocks once approved by HOD.'}, status=status.HTTP_403_FORBIDDEN)
        try:
            pdf_bytes = generate_admission_verification_pdf(data)
        except RuntimeError as exc:
            # Optional render dependency missing -> 503, never a 500 trace.
            return Response({'detail': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        # F-S6-005: Sanitize PRN to prevent header injection in Content-Disposition.
        import re as _re
        safe_prn = _re.sub(r'[^A-Za-z0-9_]', '_', str(data.get('prn_number') or 'STUDENT'))
        filename = f"Admission_Verification_Form_{safe_prn}.pdf"
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response['Access-Control-Expose-Headers'] = 'Content-Disposition'
        return response

