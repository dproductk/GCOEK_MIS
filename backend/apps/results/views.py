"""
Views for Semester Results and Eligibility Verification Workflow.
"""
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

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

        if scopes['is_system_wide'] or 'ADMIN_HEAD' in scopes['roles']:
            return qs

        if 'HOD' in scopes['roles']:
            dept_ids = scopes['department_ids']
            return qs.filter(student__enrollments__department_id__in=dept_ids, student__enrollments__is_current=True)

        if 'CLASS_TEACHER' in scopes['roles']:
            div_ids = scopes['division_ids']
            return qs.filter(student__enrollments__division_id__in=div_ids, student__enrollments__is_current=True)

        if 'FACULTY' in scopes['roles']:
            return qs

        if 'STUDENT' in scopes['roles']:
            return qs.filter(student__user_id=user.id, is_published=True)

        return SemesterResult.objects.none()

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
        serializer = self.get_serializer(filtered.distinct().order_by('student__display_name'), many=True)
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

        exam_session = request.data.get('exam_session', 'Winter 2026')
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
            'student', 'department', 'academic_year', 'target_semester'
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
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

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
        created = 0
        for enr in enrollments:
            target = Semester.objects.filter(number=enr.semester.number + 1).first() or enr.semester
            exists = EligibilityVerification.objects.filter(
                student=enr.student, academic_year=enr.academic_year,
                target_semester=target).exists()
            if not exists:
                evaluate_student_eligibility(enr.student, target)
                created += 1

        audit_log(
            request=request, actor=request.user, action=AuditLog.Action.CREATE,
            target_type='EligibilityVerification', target_id='',
            target_display=f'Initialized {created}/{len(enrollments)} verifications',
            reason='Verification queue bootstrap for class/department',
            description=f"Initialized {created} pending eligibility verifications ({len(enrollments)} in scope).",
        )
        return Response(
            {'detail': f'{created} verification(s) ready for review.', 'created': created, 'total': len(enrollments)},
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
            )
            return Response(EligibilityVerificationSerializer(updated_ev).data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='endorse-hod')
    def endorse_hod(self, request, pk=None):
        """HOD approves or flags/rejects candidate eligibility."""
        ev = self.get_object()
        scopes = get_user_scopes(request.user)
        if not (scopes['is_system_wide'] or 'ADMIN_HEAD' in scopes['roles'] or 'HOD' in scopes['roles']):
            return Response({'detail': 'Only the HOD or Admin can endorse departmental eligibility.'}, status=status.HTTP_403_FORBIDDEN)

        decision = request.data.get('status', 'APPROVED')
        remarks = request.data.get('remarks', '')

        try:
            updated_ev = hod_endorse_eligibility(
                eligibility_id=ev.id,
                hod_user=request.user,
                status_decision=decision,
                remarks=remarks,
            )
            return Response(EligibilityVerificationSerializer(updated_ev).data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
