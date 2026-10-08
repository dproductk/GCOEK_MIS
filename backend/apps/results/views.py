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
                # Read-only directory view (existing behavior).
                qs = qs.filter(student_id=student_param)
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
            elif 'FACULTY' not in scopes['roles']:
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
            filtered_qs = qs.filter(department_id__in=scopes['department_ids'])
        elif 'CLASS_TEACHER' in scopes['roles']:
            if scopes['division_ids']:
                filtered_qs = qs.filter(student__enrollments__division_id__in=scopes['division_ids'], student__enrollments__is_current=True)
            elif scopes['department_ids']:
                filtered_qs = qs.filter(department_id__in=scopes['department_ids'])
            else:
                filtered_qs = qs
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

        for div in divisions:
            try:
                if div.semester is None:
                    logger.warning('classes: skipping division %s with no semester', div.id)
                    continue
                sem_num = div.semester.number
                is_year_change = sem_num in [2, 4, 6]
                target_sem_num = sem_num + 1 if is_year_change else sem_num

                enrollments = list(StudentEnrollment.objects.filter(division=div, is_current=True).values_list('student_id', flat=True))
                total_students = len(enrollments)
                promoted_count = StudentEnrollment.objects.filter(
                    division=div, status=StudentEnrollment.Status.PROMOTED
                ).count()
                if total_students == 0 and promoted_count == 0:
                    continue

                results_filled_count = SemesterResult.objects.filter(
                    student_id__in=enrollments,
                    semester=div.semester,
                    is_published=True,
                ).exclude(result_status=SemesterResult.ResultStatus.NOT_YET_HELD).count()

                ev_qs = EligibilityVerification.objects.filter(
                    student_id__in=enrollments,
                    target_semester__number=target_sem_num,
                )
                ev_count = ev_qs.count()
                teacher_approved_count = ev_qs.filter(class_teacher_status=EligibilityVerification.StageStatus.APPROVED).count()
                hod_approved_count = ev_qs.filter(hod_status=EligibilityVerification.StageStatus.APPROVED).count()
                final_eligible_count = ev_qs.filter(final_eligible=True).count()
                flagged_count = ev_qs.filter(
                    models.Q(class_teacher_status=EligibilityVerification.StageStatus.FLAGGED) |
                    models.Q(hod_status=EligibilityVerification.StageStatus.FLAGGED)
                ).count()

                # Verification requires a teacher to review it: a class with
                # no assigned class teacher can never start verification.
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
                'can_review_teacher': (not moved_up) and can_teacher_review and (ev is not None and not ev.is_locked_for_teacher),
                'can_endorse_hod': (not moved_up) and can_hod_endorse and (
                    ev is not None and (
                        ev.class_teacher_status in (EligibilityVerification.StageStatus.APPROVED, EligibilityVerification.StageStatus.REJECTED)
                        or ev.hod_status == EligibilityVerification.StageStatus.REJECTED
                    )
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
            if scopes['division_ids']:
                enroll_qs = StudentEnrollment.objects.filter(
                    is_current=True, division_id__in=scopes['division_ids'])
            elif scopes['department_ids']:
                enroll_qs = StudentEnrollment.objects.filter(
                    is_current=True, department_id__in=scopes['department_ids'])
            else:
                return Response(
                    {'detail': 'No class assigned to you yet.'},
                    status=status.HTTP_400_BAD_REQUEST)
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
        ev = self.get_object()
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
            return Response(EligibilityVerificationSerializer(updated_ev).data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='endorse-hod')
    def endorse_hod(self, request, pk=None):
        """HOD approves or flags/rejects candidate eligibility."""
        ev = self.get_object()
        scopes = get_user_scopes(request.user)
        if not (scopes['is_system_wide'] or 'ADMIN_HEAD' in scopes['roles']):
            if 'HOD' in scopes['roles']:
                allowed = {str(d) for d in scopes.get('department_ids', [])}
                if str(ev.department_id) not in allowed:
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
            return Response(EligibilityVerificationSerializer(updated_ev).data, status=status.HTTP_200_OK)
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
        if student_id and (scopes['is_system_wide'] or any(r in scopes['roles'] for r in ('ADMIN_HEAD', 'ACCOUNTANT', 'HOD', 'CLASS_TEACHER', 'FACULTY'))):
            student = Student.objects.filter(id=student_id).first()
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
        if student_id and (scopes['is_system_wide'] or any(r in scopes['roles'] for r in ('ADMIN_HEAD', 'ACCOUNTANT', 'HOD', 'CLASS_TEACHER', 'FACULTY'))):
            student = Student.objects.filter(id=student_id).first()
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
        try:
            pdf_bytes = generate_admission_verification_pdf(data)
        except RuntimeError as exc:
            # Optional render dependency missing -> 503, never a 500 trace.
            return Response({'detail': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        safe_prn = str(data.get('prn_number') or 'STUDENT').replace('/', '_')
        filename = f"Admission_Verification_Form_{safe_prn}.pdf"
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response['Access-Control-Expose-Headers'] = 'Content-Disposition'
        return response

