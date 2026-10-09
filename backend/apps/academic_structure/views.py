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
        from rest_framework.exceptions import ValidationError

        # F-S4-001: Guard department deletion against cascading wipe of related records
        in_use = []
        checks = [
            ('programs', instance.programs.count(), 'degree program(s)'),
            ('divisions', instance.divisions.count(), 'division(s)'),
        ]
        try:
            from apps.faculty.models import Faculty
            n = Faculty.objects.filter(department=instance).count()
            checks.append(('faculty', n, 'faculty member(s)'))
        except Exception:
            pass
        try:
            from apps.students.models import StudentEnrollment
            n = StudentEnrollment.objects.filter(department=instance).count()
            checks.append(('enrollments', n, 'student enrollment(s)'))
        except Exception:
            pass
        try:
            from apps.curriculum.models import Scheme
            n = Scheme.objects.filter(department=instance).count()
            checks.append(('schemes', n, 'curriculum scheme(s)'))
        except Exception:
            pass

        for label, count, desc in checks:
            if count > 0:
                in_use.append(f"{count} {desc}")

        if in_use:
            raise ValidationError(
                f"Cannot delete department '{instance.name}' ({instance.code}) because it is in use by: "
                f"{', '.join(in_use)}. Deactivate it instead."
            )

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
        from rest_framework.exceptions import ValidationError

        # F-S4-001: Guard program deletion against cascading wipe of fee heads, enrollments, schemes
        in_use = []
        checks = []
        try:
            from apps.students.models import StudentEnrollment
            n = StudentEnrollment.objects.filter(program=instance).count()
            checks.append(('enrollments', n, 'student enrollment(s)'))
        except Exception:
            pass
        try:
            from apps.finance.models import FeeHead
            n = FeeHead.objects.filter(program=instance).count()
            checks.append(('fee_heads', n, 'fee head(s)'))
        except Exception:
            pass
        try:
            from apps.curriculum.models import Scheme
            n = Scheme.objects.filter(program=instance).count()
            checks.append(('schemes', n, 'curriculum scheme(s)'))
        except Exception:
            pass

        for label, count, desc in checks:
            if count > 0:
                in_use.append(f"{count} {desc}")

        if in_use:
            raise ValidationError(
                f"Cannot delete program '{instance.name}' ({instance.code}) because it is in use by: "
                f"{', '.join(in_use)}. Deactivate it instead."
            )

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
        from rest_framework.exceptions import ValidationError

        if instance.is_current:
            raise ValidationError(
                f"Cannot delete the current academic year '{instance.code}'. "
                'Set another year as current first.'
            )

        # Block deletion while operational/academic records still point here.
        # (PROTECT would raise a raw IntegrityError; this gives a clean 400.)
        in_use = []
        checks = [
            ('divisions', instance.divisions.count(), 'class division(s)'),
            ('contexts', instance.contexts.count(), 'academic term context(s)'),
        ]
        try:
            from apps.students.models import StudentEnrollment
            n = StudentEnrollment.objects.filter(academic_year=instance).count()
            checks.append(('enrollments', n, 'student enrollment(s)'))
        except Exception:
            pass
        try:
            from apps.admissions.models import ImportBatch, StudentAdmission
            n = ImportBatch.objects.filter(academic_year=instance).count()
            checks.append(('import batches', n, 'admission import batch(es)'))
            n = StudentAdmission.objects.filter(academic_year=instance).count()
            checks.append(('admissions', n, 'student admission(s)'))
        except Exception:
            pass
        try:
            from apps.finance.models import PaymentLedger
            n = PaymentLedger.objects.filter(academic_year=instance).count()
            checks.append(('fee records', n, 'fee ledger record(s)'))
        except Exception:
            pass
        try:
            from apps.results.models import EligibilityVerification, SemesterResult
            n = EligibilityVerification.objects.filter(academic_year=instance).count()
            checks.append(('eligibility records', n, 'eligibility verification(s)'))
            n = SemesterResult.objects.filter(academic_year=instance).count()
            checks.append(('results', n, 'semester result(s)'))
        except Exception:
            pass
        try:
            from apps.faculty.models import TeachingAssignment
            n = TeachingAssignment.objects.filter(academic_year=instance).count()
            checks.append(('teaching assignments', n, 'teaching assignment(s)'))
        except Exception:
            pass
        try:
            from apps.curriculum.models import Scheme
            n = Scheme.objects.filter(
                effective_from_year=instance
            ).count() + Scheme.objects.filter(
                effective_to_year=instance
            ).count()
            checks.append(('schemes', n, 'curriculum scheme reference(s)'))
        except Exception:
            pass

        for _key, count, label in checks:
            if count:
                in_use.append(f'{count} {label}')

        if in_use:
            raise ValidationError(
                f"Cannot delete academic year '{instance.code}': "
                + ', '.join(in_use) + ' still reference it. '
                'Deactivate it instead (is_active=false) to keep history intact.'
            )

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
        import uuid as _uuid
        try:
            _uuid.UUID(str(teacher_val))
        except (ValueError, AttributeError, TypeError):
            raise ValidationError({'class_teacher': 'Selected teacher is not a valid identifier.'})
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
        # Semester change blocked when actively seated students exist
        new_semester = serializer.validated_data.get('semester')
        if new_semester and new_semester != serializer.instance.semester:
            from rest_framework.exceptions import ValidationError
            from apps.students.models import StudentEnrollment
            if StudentEnrollment.objects.filter(division=serializer.instance, is_current=True).exists():
                raise ValidationError(
                    'Cannot change semester of a division with actively seated students. Use class promotion instead.'
                )

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

        Body: {student_ids: [...], semester_id?: optional correction,
               source_batch_id?: optional import batch for single-use create}.
        HOD own-dept only. Sets division (+semester), marks
        placement_confirmed, and applies the repeat rule: finalizing at a
        same/lower semester than the student's current one bumps
        repeat_count (detention with juniors).

        Single-use rule (production): when source_batch_id is supplied
        (division-create flow), only unplaced students belonging to that
        batch are moved; already-placed students and off-batch ids are
        reported in `skipped` instead of being silently re-seated. Without
        source_batch_id (Add/Move flows) the legacy move-any-unplaced
        behaviour is preserved. Retries against the same division are
        idempotent.
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
            # A semester correction must land the student IN this division:
            # the correction target and the division's semester must agree.
            if semester_obj.id != division.semester_id:
                return Response(
                    {'detail': (
                        f"Division '{division.name}' is a Semester {division.semester.number} class, "
                        f"but semester correction asked for Semester {semester_obj.number}. "
                        'Correct into a division of the target semester instead.'
                    )},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Optional single-use batch guard: resolve the batch's student set once.
        source_batch_id = request.data.get('source_batch_id') or None
        batch_member_ids = None
        batch_file_name = ''
        if source_batch_id:
            from apps.admissions.models import ImportBatch, ImportRow
            try:
                batch = ImportBatch.objects.filter(id=source_batch_id).first()
            except (ValueError, TypeError):
                batch = None
            if batch is None:
                return Response({'detail': 'Import batch not found.'}, status=status.HTTP_400_BAD_REQUEST)
            batch_file_name = batch.file_name
            batch_member_ids = set(
                str(sid) for sid in ImportRow.objects.filter(
                    batch=batch,
                    validation_status=ImportRow.ValidationStatus.IMPORTED,
                    student__isnull=False,
                ).values_list('student_id', flat=True)
            )

        moved, repeated, skipped = [], [], []
        with transaction.atomic():
            # Lock the division row so concurrent placements serialize.
            Division.objects.select_for_update().filter(id=division.id).first()
            for sid in student_ids:
                student = Student.objects.select_for_update().filter(id=sid).first()
                if not student:
                    skipped.append({'id': str(sid), 'reason': 'Student not found.'})
                    continue
                if batch_member_ids is not None and str(student.id) not in batch_member_ids:
                    skipped.append({'id': str(sid), 'reason': 'Not part of the selected import batch.'})
                    continue
                enr = StudentEnrollment.objects.select_for_update().filter(
                    student=student, is_current=True
                ).select_related('semester').first()
                if not enr:
                    skipped.append({'id': str(sid), 'reason': 'No active enrollment.'})
                    continue
                if enr.department_id != division.department_id:
                    skipped.append({'id': str(sid), 'reason': 'Different department.'})
                    continue
                # Idempotent retry: already seated here -> skip, don't double-count/repeat.
                if enr.division_id == division.id and enr.placement_confirmed:
                    skipped.append({'id': str(sid), 'reason': 'Already in this class.'})
                    continue
                # Strict single-use for the create flow: never steal an
                # already-placed student from another class via batch create.
                # (Use Add/Move without source_batch_id for intentional moves.)
                if batch_member_ids is not None and enr.placement_confirmed:
                    current_div = str(enr.division_id) if enr.division_id else 'unassigned'
                    skipped.append({'id': str(sid), 'reason': f'Already placed (Div {current_div}). Use Move to relocate.'})
                    continue
                prev_sem = enr.semester.number if enr.semester else 0
                new_sem = semester_obj.number if semester_obj else division.semester.number
                # Never seat across semesters: a Sem N student in a Sem M
                # division corrupts rosters, verification queues and result
                # rows. Skip with a reason instead of writing a bad row.
                resulting_sem_id = semester_obj.id if semester_obj else enr.semester_id
                if resulting_sem_id != division.semester_id:
                    skipped.append({'id': str(sid), 'reason': (
                        f"Student is in Semester {enr.semester.number if enr.semester else '?'} "
                        f"but Division '{division.name}' is Semester {division.semester.number}. "
                        'Seat into a same-semester division.'
                    )})
                    continue
                if semester_obj:
                    # A (student, year, sem) row may already exist from history:
                    # make it current instead of colliding.
                    clash = StudentEnrollment.objects.select_for_update().filter(
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

        batch_suffix = f" from batch '{batch_file_name}'" if batch_file_name else ''
        audit_log(
            request=request,
            action=AuditLog.Action.UPDATE,
            target_type='Division',
            target_id=str(division.id),
            target_display=str(division),
            description=(
                f"Bulk finalized {len(moved)} student(s) into {division}{batch_suffix} "
                f"({len(repeated)} repeat(s), {len(skipped)} skipped)."
            ),
        )
        return Response(
            {'detail': f'{len(moved)} student(s) placed in Division {division.name}.',
             'moved': moved, 'repeated': repeated, 'skipped': skipped},
            status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='promote-class')
    def promote_class(self, request, pk=None):
        """Promote a year-change class (Sem 2/4/6) into the next semester.

        Runs individual promotion for every ready student (HOD-approved
        eligibility + fully paid fees), supports repeater class creation for
        failed / fee-pending students, then settles the class itself:

        - FULL FLIP: 0 active students remaining in current semester -> this division
          flips to the next semester in place (or into existing clash).
        - PARTIAL: students not moved to repeater or promoted stay back in this division;
          promoted students move into the successor class (or existing class).
        """
        from django.db import transaction
        from apps.authentication.permissions import get_user_scopes, user_has_permission, user_has_role
        from apps.finance.models import PaymentLedger
        from apps.results.models import EligibilityVerification as _EV, SemesterResult as _SR
        from apps.students.models import Student, StudentEnrollment
        from apps.academic_structure.services import (
            flip_class_to_next_semester, seat_traced_students_to_division, sync_class_teacher
        )
        from apps.audit.models import AuditLog
        from apps.audit.services import audit_log
        from rest_framework.exceptions import PermissionDenied

        division = self.get_object()
        user = request.user
        if not (user.is_superuser or user_has_role(user, 'SYSADMIN') or user_has_permission(user, 'academic.manage')):
            if user_has_role(user, 'HOD'):
                scopes = get_user_scopes(user)
                allowed = {str(d) for d in scopes.get('department_ids', [])}
                if str(division.department_id) not in allowed:
                    raise PermissionDenied('HOD may only promote classes within their own department.')
            else:
                raise PermissionDenied('You do not have permission to promote classes.')

        sem_num = division.semester.number
        if sem_num not in (2, 4, 6):
            return Response(
                {'detail': 'Only year-change classes (Sem 2, 4, 6) can be promoted this way.'},
                status=status.HTTP_400_BAD_REQUEST)
        target_sem = Semester.objects.filter(number=sem_num + 1).first()
        if target_sem is None:
            return Response({'detail': 'Target semester not configured.'}, status=status.HTTP_400_BAD_REQUEST)

        dry_run = bool(request.data.get('dry_run')) if request.data else False

        def _decision(student):
            """Classify student for class promotion.

            Returns (group, reason) where group is one of:
            - 'ready_to_move': decided eligible + fees paid.
            - 'already_promoted': already in target_sem or higher.
            - 'fees_pending': HOD approved eligible, but fee not paid.
            - 'failed': marked not eligible (failed).
            - 'blocked': verification undecided (pending review, flagged, or no result).
            """
            current = student.enrollments.filter(is_current=True).first()
            if not current:
                return 'blocked', 'No active enrollment.'
            if current.semester_id is not None and target_sem.number <= current.semester.number:
                return 'already_promoted', f'Already in Sem {current.semester.number}.'

            ev = student.eligibility_records.filter(
                target_semester=target_sem).order_by('-final_eligible').first()

            if ev is not None and ev.final_eligible and ev.target_semester_id == target_sem.id:
                # F-S5-001: Scope fee check to the COMPLETING academic year only.
                # Accepting a prior-year PAID ledger would allow a student with
                # unpaid current-year fees to be promoted. Filter to the year
                # that the division belongs to (the year being completed).
                completing_year = division.academic_year
                paid = PaymentLedger.objects.filter(
                    student=student,
                    academic_year=completing_year,
                    status=PaymentLedger.PaymentStatus.PAID,
                ).first()
                if not paid:
                    paid = PaymentLedger.objects.filter(
                        student=student,
                        academic_year=completing_year,
                        total_fee_due__gt=0,
                        balance_due__lte=0,
                    ).first()
                if not paid:
                    return 'fees_pending', 'Fees not fully paid for the current academic year.'
                return 'ready_to_move', ''

            if ev is not None and ev.hod_status == _EV.StageStatus.REJECTED:
                return 'failed', 'Marked not eligible (failed). Fees do not matter.'

            has_result = _SR.objects.filter(
                student=student, semester=division.semester,
                is_published=True).exclude(
                result_status=_SR.ResultStatus.NOT_YET_HELD).exists()
            if not has_result:
                return 'blocked', 'Result not filled.'
            if ev is None:
                return 'blocked', 'Teacher review pending.'
            if (ev.class_teacher_status == _EV.StageStatus.FLAGGED
                    or ev.hod_status == _EV.StageStatus.FLAGGED):
                return 'blocked', 'Flagged — correction pending.'
            if ev.class_teacher_status == _EV.StageStatus.PENDING:
                return 'blocked', 'Teacher review pending.'
            if ev.class_teacher_status == _EV.StageStatus.REJECTED and ev.hod_status == _EV.StageStatus.PENDING:
                return 'blocked', 'Teacher marked fail — HOD decision pending.'
            if ev.class_teacher_status == _EV.StageStatus.APPROVED and ev.hod_status == _EV.StageStatus.PENDING:
                return 'blocked', 'HOD endorsement pending.'

            return 'blocked', 'Teacher review pending.'

        # Cohort students: currently seated active students + students promoted out in this cycle
        active_enrollments = list(StudentEnrollment.objects.filter(
            division=division, is_current=True).select_related('student', 'semester'))
        promoted_enrollments = list(StudentEnrollment.objects.filter(
            division=division, status=StudentEnrollment.Status.PROMOTED
        ).select_related('student', 'semester'))

        seen_student_ids = set()
        cohort_students = []
        for enr in active_enrollments + promoted_enrollments:
            if enr.student_id not in seen_student_ids:
                seen_student_ids.add(enr.student_id)
                cohort_students.append(enr.student)

        ready_to_move, already_promoted, fees_pending, failed, blocked = [], [], [], [], []
        for stu in cohort_students:
            group, reason = _decision(stu)
            entry = {'id': str(stu.id), 'name': stu.display_name, 'reason': reason, 'prn': stu.enrollment_no or stu.application_id}
            if group == 'ready_to_move':
                ready_to_move.append(entry)
            elif group == 'already_promoted':
                already_promoted.append(entry)
            elif group == 'fees_pending':
                fees_pending.append(entry)
            elif group == 'failed':
                failed.append(entry)
            else:
                blocked.append(entry)

        teacher_user = division.class_teacher
        profile = getattr(teacher_user, 'faculty_profile', None) if teacher_user else None
        t_name = profile.display_name if profile and getattr(profile, 'display_name', '') else (
            teacher_user.get_full_name() or teacher_user.username if teacher_user else ''
        )

        default_repeater = {
            'division_name': 'R',
            'semester_number': sem_num,
            'academic_year_id': str(division.academic_year_id) if division.academic_year_id else None,
            'academic_year_code': division.academic_year.code if division.academic_year else '',
            'class_teacher_id': str(division.class_teacher_id) if division.class_teacher_id else None,
            'class_teacher_name': t_name,
            'preselected_student_ids': [s['id'] for s in failed],
            'optional_student_ids': [s['id'] for s in fees_pending],
        }

        if dry_run:
            already_out = StudentEnrollment.objects.filter(
                semester=target_sem, is_current=True, division__isnull=True,
                department=division.department).count()
            return Response({
                'division_id': str(division.id),
                'from_semester': sem_num,
                'to_semester': target_sem.number,
                'ready_to_move_count': len(ready_to_move),
                'already_promoted_count': len(already_promoted),
                'fees_pending_count': len(fees_pending),
                'failed_count': len(failed),
                'blocked_count': len(blocked),
                'will_promote': len(ready_to_move),
                'will_stay': len(fees_pending) + len(failed),
                'blocked': len(blocked),
                'already_promoted_unseated': already_out,
                'full_flip': len(fees_pending) == 0 and len(failed) == 0 and len(blocked) == 0,
                'ready': len(blocked) == 0,
                'buckets': {
                    'ready_to_move': ready_to_move,
                    'already_promoted': already_promoted,
                    'fees_pending': fees_pending,
                    'failed': failed,
                    'blocked': blocked,
                },
                'default_repeater': default_repeater,
                'movers': ready_to_move,
                'stayers': fees_pending + failed,
                'blocked_students': blocked,
            }, status=status.HTTP_200_OK)

        if blocked:
            return Response(
                {'detail': (
                    f'Complete verification for {len(blocked)} student(s) first — '
                    'every student must be eligible or failed before the class can move.'),
                 'blocked_students': blocked},
                status=status.HTTP_400_BAD_REQUEST)

        repeater_student_ids = set(request.data.get('repeater_student_ids') or [])
        repeater_teacher_id = request.data.get('repeater_teacher_id')
        repeater_name = (request.data.get('repeater_division_name') or 'R').strip().upper()

        # Validate repeater student selections: only failed or fee-pending students in this class
        eligible_for_repeater = {s['id'] for s in failed} | {s['id'] for s in fees_pending}
        invalid_repeaters = repeater_student_ids - eligible_for_repeater
        if invalid_repeaters:
            return Response(
                {'detail': 'Only failed or fee-pending students from this class can be moved to the repeater class.'},
                status=status.HTTP_400_BAD_REQUEST)

        from apps.students.services import check_and_promote_student
        promoted = []
        promotion_errors = []
        moved_to_repeater = []
        with transaction.atomic():
            # Lock division row
            division = Division.objects.select_for_update().get(id=division.id)

            # 1. Promote ready students (F-S7-004: per-student savepoint to isolate failures)
            for s in ready_to_move:
                sid = s['id']
                sid_sp = transaction.savepoint()
                try:
                    ok, msg = check_and_promote_student(sid, actor=user, request=request)
                    if ok:
                        promoted.append(sid)
                        transaction.savepoint_commit(sid_sp)
                    else:
                        promotion_errors.append({'student_id': str(sid), 'error': msg or 'Promotion check returned false'})
                        transaction.savepoint_rollback(sid_sp)
                except Exception as exc:
                    transaction.savepoint_rollback(sid_sp)
                    promotion_errors.append({'student_id': str(sid), 'error': str(exc)})

            # 2. Repeater class creation and student move
            repeater_div = None
            if repeater_student_ids:
                rep_teacher = None
                if repeater_teacher_id:
                    from apps.authentication.models import User as _User
                    rep_teacher = _User.objects.filter(id=repeater_teacher_id).first()
                if not rep_teacher:
                    rep_teacher = division.class_teacher

                repeater_div, rep_created = Division.objects.get_or_create(
                    department=division.department,
                    academic_year=division.academic_year,
                    semester=division.semester,
                    name=repeater_name,
                    defaults={
                        'seat_capacity': division.seat_capacity,
                        'class_teacher': rep_teacher,
                    }
                )
                if rep_created and repeater_div.class_teacher:
                    try:
                        sync_class_teacher(repeater_div, repeater_div.class_teacher, user, request,
                                           reason='Repeater class created')
                    except Exception:
                        pass
                    audit_log(
                        request=self.request, action=AuditLog.Action.CREATE,
                        target_type='Division', target_id=str(repeater_div.id),
                        target_display=str(repeater_div),
                        description=f"Created repeater class {repeater_div} for {division} repeaters."
                    )

                for r_id in repeater_student_ids:
                    enr = StudentEnrollment.objects.select_for_update().filter(
                        student_id=r_id, division=division, is_current=True, semester__number=sem_num
                    ).first()
                    if enr:
                        enr.division = repeater_div
                        enr.save(update_fields=['division', 'updated_at'])
                        moved_to_repeater.append(str(r_id))
                        audit_log(
                            request=self.request, action=AuditLog.Action.UPDATE,
                            target_type='StudentEnrollment', target_id=str(enr.id),
                            target_display=f"{enr.student.display_name} -> {repeater_div.name}",
                            description=f"Moved student {enr.student.display_name} into repeater class {repeater_div}."
                        )

            # 3. Recalculate remaining active students in original division
            remaining = StudentEnrollment.objects.filter(
                division=division, is_current=True, semester__number=sem_num
            ).count()

            # 4. If 0 active students remain -> Flip to next semester!
            if remaining == 0:
                dest_div, flipped_in_place = flip_class_to_next_semester(
                    division, target_sem, actor=user, request=request
                )
                return Response({
                    'detail': f'Class promoted to Sem {target_sem.number} in place. {len(promoted)} student(s) moved up, {len(moved_to_repeater)} moved to repeater.',
                    'flipped': flipped_in_place,
                    'successor_division_id': str(dest_div.id),
                    'repeater_division_id': str(repeater_div.id) if repeater_div else None,
                    'promoted': promoted,
                    'promotion_errors': promotion_errors,
                    'moved_to_repeater': moved_to_repeater,
                    'staying': [s for s in fees_pending + failed if s['id'] not in repeater_student_ids],
                }, status=status.HTTP_200_OK)

            # 5. Partial split: some students remain in Sem 6 Div A
            successor, created = Division.objects.get_or_create(
                department=division.department, academic_year=division.academic_year,
                semester=target_sem, name=division.name,
                defaults={'seat_capacity': division.seat_capacity,
                          'class_teacher': division.class_teacher},
            )
            if created and successor.class_teacher_id:
                try:
                    sync_class_teacher(successor, successor.class_teacher, user,
                                       self.request, reason='Class teacher carried over on class split')
                except Exception:
                    pass
            seated_back = seat_traced_students_to_division(successor, original_div_id=division.id)
            audit_log(
                request=self.request, action=AuditLog.Action.UPDATE,
                target_type='Division', target_id=str(division.id),
                target_display=str(division),
                description=(
                    f"Partial class promotion {division.department.code} Sem {sem_num} Div {division.name}: "
                    f"{len(promoted)} moved to {successor} ({seated_back} seated), "
                    f"{remaining} staying back under verification ({len(moved_to_repeater)} in repeater). "
                    "Class teacher carried over to the new class."
                ),
            )
            return Response({
                'detail': (
                    f'{len(promoted)} student(s) moved to Sem {target_sem.number}. '
                    f'{remaining} staying back in Sem {sem_num} ({len(moved_to_repeater)} in repeater).'),
                'flipped': False,
                'successor_division_id': str(successor.id),
                'successor_created': created,
                'repeater_division_id': str(repeater_div.id) if repeater_div else None,
                'promoted': promoted,
                'promotion_errors': promotion_errors,
                'moved_to_repeater': moved_to_repeater,
                'staying': [s for s in fees_pending + failed if s['id'] not in repeater_student_ids],
            }, status=status.HTTP_200_OK)

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
        # Empty-only: actively seated students block deletion (move them
        # first); even with none seated, historical placement rows keep
        # the division as evidence and block deletion too.
        current_count = StudentEnrollment.objects.filter(division=instance, is_current=True).count()
        if current_count > 0:
            raise ValidationError(
                f"Division '{instance.name}' has {current_count} active student(s) assigned. "
                'Move them to another division first.'
            )
        history_count = StudentEnrollment.objects.filter(division=instance).count()
        if history_count > 0:
            raise ValidationError(
                f"Division '{instance.name}' has student history records and cannot be deleted. "
                'It is kept as evidence of past placements.'
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
