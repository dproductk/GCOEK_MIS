"""
Views for Academic Structure domain.

Enforces:
- Read-only access for all authenticated roles.
- Write access (CRUD) restricted to Sysadmin / users with 'academic.manage' permission.
- Full audit trail on creation, modification, and deletion.
"""
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.academic_structure.models import (
    AcademicContext,
    AcademicYear,
    Department,
    Division,
    LabBatch,
    Program,
    Semester,
)
from apps.academic_structure.serializers import (
    AcademicContextSerializer,
    AcademicYearSerializer,
    DepartmentSerializer,
    DivisionSerializer,
    LabBatchSerializer,
    ProgramSerializer,
    SemesterSerializer,
)
from apps.audit.models import AuditLog
from apps.audit.services import audit_log
from apps.authentication.permissions import HasRolePermission


class AcademicStructurePermission(permissions.BasePermission):
    """
    Allows read access to any authenticated user.
    Restricts write operations to Sysadmin / 'academic.manage'.
    Exception: HOD may manage Divisions scoped to their own department
    (dept check enforced in DivisionViewSet.perform_create/update).
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated or not request.user.is_active:
            return False

        if request.method in permissions.SAFE_METHODS:
            return True

        if request.user.is_superuser:
            return True

        # Check for sysadmin or academic.manage via HasRolePermission helper
        from apps.authentication.permissions import user_has_permission, user_has_role
        if user_has_role(request.user, 'SYSADMIN'):
            return True

        if user_has_permission(request.user, 'academic.manage'):
            return True

        # HOD division/lab-batch management: allow write at permission level,
        # department scope enforced in DivisionViewSet / LabBatchViewSet.
        view_name = getattr(view, '__class__', None).__name__ if hasattr(view, '__class__') else ''
        if view_name in ('DivisionViewSet', 'LabBatchViewSet') and user_has_role(request.user, 'HOD'):
            return True

        return False


class DepartmentViewSet(viewsets.ModelViewSet):
    """
    CRUD API for Departments.
    """

    queryset = Department.objects.all().order_by('name')
    serializer_class = DepartmentSerializer
    permission_classes = [AcademicStructurePermission]

    def get_queryset(self):
        from django.db.models import Count, Q
        return Department.objects.annotate(
            _programs_count=Count('programs', filter=Q(programs__is_active=True), distinct=True),
            _divisions_count=Count('divisions', filter=Q(divisions__is_active=True), distinct=True),
        ).order_by('name')

    def perform_create(self, serializer):
        dept = serializer.save()
        audit_log(
            request=self.request,
            action=AuditLog.Action.CREATE,
            target_type='Department',
            target_id=str(dept.id),
            target_display=dept.name,
            description=f"Created department '{dept.name}' ({dept.code}).",
        )

    def perform_update(self, serializer):
        dept = serializer.save()
        audit_log(
            request=self.request,
            action=AuditLog.Action.UPDATE,
            target_type='Department',
            target_id=str(dept.id),
            target_display=dept.name,
            description=f"Updated department '{dept.name}' ({dept.code}).",
        )

    def perform_destroy(self, instance):
        name = instance.name
        code = instance.code
        dept_id = str(instance.id)
        instance.delete()
        audit_log(
            request=self.request,
            action=AuditLog.Action.DELETE,
            target_type='Department',
            target_id=dept_id,
            target_display=name,
            description=f"Deleted department '{name}' ({code}).",
        )


class ProgramViewSet(viewsets.ModelViewSet):
    """
    CRUD API for Degree Programs under departments.
    """

    queryset = Program.objects.select_related('department').all().order_by('department__name', 'name')
    serializer_class = ProgramSerializer
    permission_classes = [AcademicStructurePermission]

    def get_queryset(self):
        qs = super().get_queryset()
        dept_id = self.request.query_params.get('department_id')
        if dept_id:
            qs = qs.filter(department_id=dept_id)
        return qs

    def perform_create(self, serializer):
        prog = serializer.save()
        audit_log(
            request=self.request,
            action=AuditLog.Action.CREATE,
            target_type='Program',
            target_id=str(prog.id),
            target_display=prog.name,
            new_value={'name': prog.name, 'code': prog.code},
            description=f"Created program '{prog.name}' ({prog.code}).",
        )

    def perform_update(self, serializer):
        old = serializer.instance
        old_snapshot = {'name': old.name, 'code': old.code} if old else None
        prog = serializer.save()
        audit_log(
            request=self.request,
            action=AuditLog.Action.UPDATE,
            target_type='Program',
            target_id=str(prog.id),
            target_display=prog.name,
            old_value=old_snapshot,
            new_value={'name': prog.name, 'code': prog.code},
            description=f"Updated program '{prog.name}' ({prog.code}).",
        )

    def perform_destroy(self, instance):
        name, code, pid = instance.name, instance.code, str(instance.id)
        instance.delete()
        audit_log(
            request=self.request,
            action=AuditLog.Action.DELETE,
            target_type='Program',
            target_id=pid,
            target_display=name,
            description=f"Deleted program '{name}' ({code}).",
        )


class AcademicYearViewSet(viewsets.ModelViewSet):
    """
    CRUD API for Academic Years.
    """

    queryset = AcademicYear.objects.all().order_by('-start_date')
    serializer_class = AcademicYearSerializer
    permission_classes = [AcademicStructurePermission]

    def perform_create(self, serializer):
        year = serializer.save()
        audit_log(
            request=self.request,
            action=AuditLog.Action.CREATE,
            target_type='AcademicYear',
            target_id=str(year.id),
            target_display=year.code,
            new_value={'code': year.code, 'name': year.name},
            description=f"Created academic year '{year.code}'.",
        )

    def perform_update(self, serializer):
        old = serializer.instance
        old_snapshot = {'code': old.code, 'name': old.name} if old else None
        year = serializer.save()
        audit_log(
            request=self.request,
            action=AuditLog.Action.UPDATE,
            target_type='AcademicYear',
            target_id=str(year.id),
            target_display=year.code,
            old_value=old_snapshot,
            new_value={'code': year.code, 'name': year.name},
            description=f"Updated academic year '{year.code}'.",
        )

    def perform_destroy(self, instance):
        code, yid = instance.code, str(instance.id)
        instance.delete()
        audit_log(
            request=self.request,
            action=AuditLog.Action.DELETE,
            target_type='AcademicYear',
            target_id=yid,
            target_display=code,
            description=f"Deleted academic year '{code}'.",
        )

    @action(detail=True, methods=['post'], url_path='set_current')
    def set_current(self, request, pk=None):
        """Atomically set this academic year as current."""
        academic_year = self.get_object()
        academic_year.is_current = True
        academic_year.save()

        audit_log(
            request=request,
            action=AuditLog.Action.UPDATE,
            target_type='AcademicYear',
            target_id=str(academic_year.id),
            target_display=academic_year.code,
            description=f"Set Academic Year '{academic_year.code}' as current.",
        )
        return Response(AcademicYearSerializer(academic_year).data, status=status.HTTP_200_OK)


class AcademicContextViewSet(viewsets.ModelViewSet):
    """
    CRUD API for Academic Contexts (Odd/Even term operational context).
    """

    queryset = AcademicContext.objects.select_related('academic_year').all().order_by('-created_at')
    serializer_class = AcademicContextSerializer
    permission_classes = [AcademicStructurePermission]

    def perform_create(self, serializer):
        ctx = serializer.save()
        audit_log(
            request=self.request,
            action=AuditLog.Action.CREATE,
            target_type='AcademicContext',
            target_id=str(ctx.id),
            target_display=f'{ctx.academic_year.code if ctx.academic_year else "?"} {ctx.term}',
            new_value={'term': str(ctx.term)},
            description='Created academic term context.',
        )

    def perform_update(self, serializer):
        ctx = serializer.save()
        audit_log(
            request=self.request,
            action=AuditLog.Action.UPDATE,
            target_type='AcademicContext',
            target_id=str(ctx.id),
            target_display=str(ctx.id),
            description='Updated academic term context.',
        )

    def perform_destroy(self, instance):
        cid = str(instance.id)
        label = str(instance)
        instance.delete()
        audit_log(
            request=self.request,
            action=AuditLog.Action.DELETE,
            target_type='AcademicContext',
            target_id=cid,
            target_display=label,
            description='Deleted academic term context.',
        )

    @action(detail=False, methods=['get'], url_path='current')
    def get_current(self, request):
        """Retrieve the currently active college academic context."""
        context = AcademicContext.objects.filter(is_active=True).select_related('academic_year').first()
        if not context:
            return Response(
                {'detail': 'No active academic context found.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(AcademicContextSerializer(context).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='rollover')
    def rollover(self, request):
        """Sysadmin term/year rollover.

        Body: {academic_year_id?, term: ODD|EVEN}.
        Switches the active term (and current year when given). When the
        new term is EVEN within the same year, all current odd-semester
        enrollments auto-advance one semester (no verification, no fee
        gate; repeaters with repeat_count > 0 are skipped for HOD review).
        Year changes never auto-move anyone: those go through verification.
        Idempotent: re-running finds no odd current enrollments.
        """
        from django.db import transaction
        from apps.authentication.permissions import user_has_role
        from apps.students.models import StudentEnrollment
        from rest_framework.exceptions import PermissionDenied

        user = request.user
        if not (user.is_superuser or user_has_role(user, 'SYSADMIN')):
            raise PermissionDenied('Only Sysadmin can roll the academic term over.')

        term = str(request.data.get('term', '')).upper()
        if term not in ('ODD', 'EVEN'):
            return Response({'detail': 'term must be ODD or EVEN.'}, status=status.HTTP_400_BAD_REQUEST)
        year = None
        if request.data.get('academic_year_id'):
            year = AcademicYear.objects.filter(id=request.data.get('academic_year_id')).first()
            if not year:
                return Response({'detail': 'Academic year not found.'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            year = AcademicYear.objects.filter(is_current=True).first()
            if not year:
                return Response({'detail': 'No current academic year.'}, status=status.HTTP_400_BAD_REQUEST)

        prev_ctx = AcademicContext.objects.filter(is_active=True).first()
        same_year = prev_ctx is not None and prev_ctx.academic_year_id == year.id

        advanced, skipped_repeats = 0, 0
        with transaction.atomic():
            if not year.is_current:
                year.is_current = True
                year.save(update_fields=['is_current'])
            ctx = AcademicContext.objects.create(academic_year=year, term=term, is_active=True)
            # Auto-advance only on same-year odd->even flips.
            if same_year and term == 'EVEN':
                odds = list(StudentEnrollment.objects.select_for_update().filter(
                    is_current=True, semester__number__in=[1, 3, 5, 7]
                ).select_related('semester', 'student'))
                sem_cache = {s.number: s for s in Semester.objects.filter(number__in=[2, 4, 6, 8])}
                from django.db import IntegrityError as _IE
                for enr in odds:
                    if (enr.student.repeat_count or 0) > 0:
                        skipped_repeats += 1
                        continue
                    nxt = sem_cache.get(enr.semester.number + 1)
                    if not nxt:
                        continue
                    try:
                        # Per-row savepoint: an IntegrityError must not abort
                        # the outer rollover transaction (Postgres aborts the
                        # whole txn otherwise and every later row would fail).
                        with transaction.atomic():
                            clash = StudentEnrollment.objects.select_for_update().filter(
                                student=enr.student, academic_year=enr.academic_year,
                                semester=nxt).exclude(id=enr.id).first()
                            enr.is_current = False
                            enr.status = StudentEnrollment.Status.COMPLETED
                            enr.save(update_fields=['is_current', 'status'])
                            if clash:
                                clash.division = None
                                clash.lab_batch = None
                                clash.status = StudentEnrollment.Status.ACTIVE
                                clash.is_current = True
                                clash.placement_confirmed = False
                                clash.save()
                            else:
                                StudentEnrollment.objects.create(
                                    student=enr.student, academic_year=enr.academic_year,
                                    department=enr.department, program=enr.program,
                                    semester=nxt, division=None, lab_batch=None,
                                    scheme=enr.scheme, roll_number=enr.roll_number,
                                    status=StudentEnrollment.Status.ACTIVE, is_current=True,
                                    placement_confirmed=False,
                                )
                            advanced += 1
                    except _IE:
                        # Concurrent rollover created the target row — skip,
                        # don't abort the whole batch.
                        continue
            audit_log(
                request=request,
                action=AuditLog.Action.STATUS_CHANGE,
                target_type='AcademicContext',
                target_id=str(ctx.id),
                target_display=f'{year.code} {term}',
                reason='Sysadmin term rollover',
                description=(
                    f"Rolled term to {year.code} {term}. Auto-advanced {advanced} "
                    f"enrollment(s); {skipped_repeats} repeater(s) left for HOD review."
                ),
            )
        return Response(
            {'detail': f'Term is now {year.code} {term}. {advanced} auto-advanced, {skipped_repeats} repeaters held.',
             'advanced': advanced, 'skipped_repeats': skipped_repeats,
             'academic_year': str(year.id), 'term': term},
            status=status.HTTP_200_OK)


class SemesterViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only viewset for canonical Semesters 1 through 8.
    """

    queryset = Semester.objects.all().order_by('number')
    serializer_class = SemesterSerializer
    permission_classes = [permissions.IsAuthenticated]


class DivisionViewSet(viewsets.ModelViewSet):
    """
    CRUD API for Class Divisions with Class Teacher assignments.
    """

    queryset = (
        Division.objects.select_related('department', 'academic_year', 'semester', 'class_teacher')
        .all()
        .order_by('department__name', 'semester__number', 'name')
    )
    serializer_class = DivisionSerializer
    permission_classes = [AcademicStructurePermission]

    def get_queryset(self):
        from django.db.models import Count, Q
        qs = (
            super().get_queryset().annotate(
                _annotated_enrolled_count=Count(
                    'enrolled_students',
                    filter=Q(enrolled_students__is_current=True),
                )
            )
        )
        user = self.request.user
        if user and user.is_authenticated:
            from apps.authentication.permissions import get_user_scopes
            scopes = get_user_scopes(user)
            if 'HOD' in scopes.get('roles', []) and not (scopes.get('is_system_wide') or 'ADMIN_HEAD' in scopes.get('roles', [])):
                dept_ids = scopes.get('department_ids', [])
                qs = qs.filter(department_id__in=dept_ids)

        dept_id = self.request.query_params.get('department_id')
        year_id = self.request.query_params.get('academic_year_id')
        sem_id = self.request.query_params.get('semester_id')
        if dept_id:
            qs = qs.filter(department_id=dept_id)
        if year_id:
            qs = qs.filter(academic_year_id=year_id)
        if sem_id:
            qs = qs.filter(semester_id=sem_id)
        return qs

    def _resolve_teacher_input(self, request):
        """Accept a Faculty id for class_teacher and translate to its User.

        The HOD UI lists Faculty records (Faculty UUIDs) but
        Division.class_teacher points at the login User, so translate here
        and fail with a clear message when the faculty has no login.
        """
        data = request.data
        teacher_val = data.get('class_teacher') if hasattr(data, 'get') else None
        if not teacher_val:
            return
        from apps.authentication.models import User
        from apps.faculty.models import Faculty
        from rest_framework.exceptions import ValidationError
        if User.objects.filter(id=teacher_val).exists():
            return
        faculty = Faculty.objects.filter(id=teacher_val).first()
        if faculty is None:
            raise ValidationError({'class_teacher': 'Selected teacher not found.'})
        if not faculty.user_id:
            raise ValidationError(
                {'class_teacher': f"{faculty.display_name} has no login account yet. Create one first."}
            )
        mutable = data.copy() if hasattr(data, 'copy') else dict(data)
        mutable['class_teacher'] = str(faculty.user_id)
        request._full_data = mutable

    def create(self, request, *args, **kwargs):
        self._resolve_teacher_input(request)
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        self._resolve_teacher_input(request)
        return super().update(request, *args, **kwargs)

    def perform_create(self, serializer):
        from apps.authentication.permissions import get_user_scopes, user_has_permission, user_has_role
        from rest_framework.exceptions import PermissionDenied

        # HOD without academic.manage may only create divisions in own department
        user = self.request.user
        if not (user.is_superuser or user_has_role(user, 'SYSADMIN') or user_has_permission(user, 'academic.manage')):
            if user_has_role(user, 'HOD'):
                scopes = get_user_scopes(user)
                dept_id = str(serializer.validated_data.get('department').id) if serializer.validated_data.get('department') else None
                allowed = {str(d) for d in scopes.get('department_ids', [])}
                if not dept_id or dept_id not in allowed:
                    raise PermissionDenied('HOD may only create divisions for their own department.')
            else:
                raise PermissionDenied('You do not have permission to create divisions.')
        div = serializer.save()
        audit_log(
            request=self.request,
            action=AuditLog.Action.CREATE,
            target_type='Division',
            target_id=str(div.id),
            target_display=str(div),
            description=f"Created division '{div.name}' for {div.department.code} Sem {div.semester.number}.",
        )
        if div.class_teacher_id:
            from apps.academic_structure.services import sync_class_teacher
            sync_class_teacher(div, div.class_teacher, user, self.request,
                               reason='Class teacher set at division creation')

    def perform_update(self, serializer):
        from apps.authentication.permissions import get_user_scopes, user_has_permission, user_has_role
        from rest_framework.exceptions import PermissionDenied

        user = self.request.user
        if not (user.is_superuser or user_has_role(user, 'SYSADMIN') or user_has_permission(user, 'academic.manage')):
            if user_has_role(user, 'HOD'):
                scopes = get_user_scopes(user)
                div_dept_id = str(serializer.instance.department_id)
                allowed = {str(d) for d in scopes.get('department_ids', [])}
                if div_dept_id not in allowed:
                    raise PermissionDenied('HOD may only update divisions for their own department.')
            else:
                raise PermissionDenied('You do not have permission to update divisions.')
        # Class-teacher changes go through the single-owner sync service so
        # Division.class_teacher and the RoleAssignment never drift apart.
        _sentinel = object()
        new_teacher = serializer.validated_data.pop('class_teacher', _sentinel)
        div = serializer.save()
        audit_log(
            request=self.request,
            action=AuditLog.Action.UPDATE,
            target_type='Division',
            target_id=str(div.id),
            target_display=str(div),
            description=f"Updated division '{div.name}' for {div.department.code} Sem {div.semester.number}.",
        )
        if new_teacher is not _sentinel:
            new_id = new_teacher.id if new_teacher else None
            if new_id != div.class_teacher_id:
                from apps.academic_structure.services import sync_class_teacher
                sync_class_teacher(div, new_teacher, user, self.request,
                                   reason='HOD class-teacher assignment')
    @action(detail=True, methods=['get'], url_path='subjects')
    def division_subjects(self, request, pk=None):
        """Scheme subject slots for this division (drives the HOD teacher UI).

        Resolves the applicable published scheme for the division's
        department program + academic year and returns its subjects for the
        division's semester with their assessment splits.
        """
        from apps.curriculum.services import resolve_applicable_scheme
        from apps.curriculum.models import SchemeSubject
        from apps.curriculum.serializers import SchemeSubjectSerializer
        division = self.get_object()
        program = division.department.programs.filter(is_active=True).order_by('code').first()
        scheme = resolve_applicable_scheme(program, division.academic_year) if program else None
        if not scheme:
            return Response({'scheme': None, 'subjects': []}, status=status.HTTP_200_OK)
        subjects = SchemeSubject.objects.filter(
            scheme=scheme, semester_number=division.semester.number
        ).select_related('subject').prefetch_related('assessment_components').order_by('display_order', 'course_code')
        return Response({
            'scheme': {'id': str(scheme.id), 'code': scheme.code, 'version': scheme.version},
            'subjects': SchemeSubjectSerializer(subjects, many=True).data,
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='assign-students')
    def assign_students(self, request, pk=None):
        """Bulk-finalize a batch of students into this division.

        Body: {student_ids: [...], semester_id?: optional correction}.
        HOD own-dept only. Sets division (+semester), marks
        placement_confirmed, and applies the repeat rule: finalizing at a
        same/lower semester than the student's current one bumps
        repeat_count (detention with juniors).
        """
        from django.db import transaction
        from apps.authentication.permissions import get_user_scopes, user_has_permission, user_has_role
        from apps.students.models import Student, StudentEnrollment
        from rest_framework.exceptions import PermissionDenied

        division = self.get_object()
        user = request.user
        if not (user.is_superuser or user_has_role(user, 'SYSADMIN') or user_has_permission(user, 'academic.manage')):
            if user_has_role(user, 'HOD'):
                scopes = get_user_scopes(user)
                allowed = {str(d) for d in scopes.get('department_ids', [])}
                if str(division.department_id) not in allowed:
                    raise PermissionDenied('HOD may only assign students within their own department.')
            else:
                raise PermissionDenied('You do not have permission to assign students.')

        student_ids = request.data.get('student_ids') or []
        if not isinstance(student_ids, list) or not student_ids:
            return Response({'detail': 'student_ids list is required.'}, status=status.HTTP_400_BAD_REQUEST)

        semester_obj = None
        if request.data.get('semester_id'):
            try:
                semester_obj = Semester.objects.get(id=request.data.get('semester_id'))
            except (Semester.DoesNotExist, ValueError):
                return Response({'detail': 'Semester not found.'}, status=status.HTTP_400_BAD_REQUEST)

        moved, repeated, skipped = [], [], []
        with transaction.atomic():
            for sid in student_ids:
                student = Student.objects.filter(id=sid).first()
                if not student:
                    skipped.append({'id': str(sid), 'reason': 'Student not found.'})
                    continue
                enr = student.enrollments.filter(is_current=True).select_related('semester').first()
                if not enr:
                    skipped.append({'id': str(sid), 'reason': 'No active enrollment.'})
                    continue
                if enr.department_id != division.department_id:
                    skipped.append({'id': str(sid), 'reason': 'Different department.'})
                    continue
                prev_sem = enr.semester.number if enr.semester else 0
                new_sem = semester_obj.number if semester_obj else division.semester.number
                if semester_obj:
                    # A (student, year, sem) row may already exist from history:
                    # make it current instead of colliding.
                    clash = StudentEnrollment.objects.filter(
                        student=student, academic_year=enr.academic_year,
                        semester=semester_obj).exclude(id=enr.id).first()
                    if clash:
                        clash.division = division
                        clash.placement_confirmed = True
                        clash.is_current = True
                        clash.save()
                        enr.is_current = False
                        enr.save(update_fields=['is_current'])
                        enr = clash
                    else:
                        enr.semester = semester_obj
                enr.division = division
                enr.placement_confirmed = True
                enr.save()
                if new_sem <= prev_sem:
                    student.repeat_count = (student.repeat_count or 0) + 1
                    student.save(update_fields=['repeat_count'])
                    repeated.append(str(student.id))
                moved.append(str(student.id))

        audit_log(
            request=request,
            action=AuditLog.Action.UPDATE,
            target_type='Division',
            target_id=str(division.id),
            target_display=str(division),
            description=(
                f"Bulk finalized {len(moved)} student(s) into {division} "
                f"({len(repeated)} repeat(s), {len(skipped)} skipped)."
            ),
        )
        return Response(
            {'detail': f'{len(moved)} student(s) placed in Division {division.name}.',
             'moved': moved, 'repeated': repeated, 'skipped': skipped},
            status=status.HTTP_200_OK)

    def perform_destroy(self, instance):
        from apps.authentication.permissions import get_user_scopes, user_has_permission, user_has_role
        from rest_framework.exceptions import PermissionDenied, ValidationError
        from apps.students.models import StudentEnrollment
        user = self.request.user
        if not (user.is_superuser or user_has_role(user, 'SYSADMIN') or user_has_permission(user, 'academic.manage')):
            if user_has_role(user, 'HOD'):
                scopes = get_user_scopes(user)
                div_dept_id = str(instance.department_id)
                allowed = {str(d) for d in scopes.get('department_ids', [])}
                if div_dept_id not in allowed:
                    raise PermissionDenied('HOD may only delete divisions for their own department.')
            else:
                raise PermissionDenied('You do not have permission to delete divisions.')
        # Empty-only: any enrollment reference (current or historical
        # placement) blocks deletion — move students first.
        student_count = StudentEnrollment.objects.filter(division=instance).count()
        if student_count > 0:
            raise ValidationError(
                f"Division '{instance.name}' has {student_count} student(s) assigned. "
                'Move them to another division first.'
            )
        name = instance.name
        div_id = str(instance.id)
        dept_code = instance.department.code
        sub_batches = instance.lab_batches.count()
        instance.delete()
        audit_log(
            request=self.request,
            action=AuditLog.Action.DELETE,
            target_type='Division',
            target_id=div_id,
            target_display=name,
            description=f"Deleted empty division '{name}' in department {dept_code} ({sub_batches} empty lab batch(es) removed).",
        )


class LabBatchViewSet(viewsets.ModelViewSet):
    """
    CRUD API for Lab Batches (sub-groups like A1, A2 within a Division).
    HOD may manage batches for divisions in their own department.
    """

    queryset = (
        LabBatch.objects.select_related('division', 'division__department')
        .all()
        .order_by('division__department__name', 'division__name', 'name')
    )
    serializer_class = LabBatchSerializer
    permission_classes = [AcademicStructurePermission]

    def get_queryset(self):
        qs = super().get_queryset()
        div_id = self.request.query_params.get('division_id')
        if div_id:
            qs = qs.filter(division_id=div_id)
        return qs

    def _check_hod_scope(self, division):
        from apps.authentication.permissions import get_user_scopes, user_has_permission, user_has_role
        from rest_framework.exceptions import PermissionDenied

        user = self.request.user
        if user.is_superuser or user_has_role(user, 'SYSADMIN') or user_has_permission(user, 'academic.manage'):
            return
        if user_has_role(user, 'HOD'):
            scopes = get_user_scopes(user)
            allowed = {str(d) for d in scopes.get('department_ids', [])}
            if str(division.department_id) not in allowed:
                raise PermissionDenied('HOD may only manage batches for their own department.')
            return
        raise PermissionDenied('You do not have permission to manage lab batches.')

    def perform_create(self, serializer):
        division = serializer.validated_data.get('division')
        self._check_hod_scope(division)
        batch = serializer.save()
        audit_log(
            request=self.request,
            action=AuditLog.Action.CREATE,
            target_type='LabBatch',
            target_id=str(batch.id),
            target_display=str(batch),
            description=f"Created lab batch '{batch.name}' for {batch.division}.",
        )

    def perform_update(self, serializer):
        division = serializer.validated_data.get('division', serializer.instance.division)
        self._check_hod_scope(division)
        batch = serializer.save()
        audit_log(
            request=self.request,
            action=AuditLog.Action.UPDATE,
            target_type='LabBatch',
            target_id=str(batch.id),
            target_display=str(batch),
            description=f"Updated lab batch '{batch.name}' for {batch.division}.",
        )

    def perform_destroy(self, instance):
        self._check_hod_scope(instance.division)
        label, bid = str(instance), str(instance.id)
        instance.delete()
        audit_log(
            request=self.request,
            action=AuditLog.Action.DELETE,
            target_type='LabBatch',
            target_id=bid,
            target_display=label,
            description=f"Deleted lab batch '{label}'.",
        )
