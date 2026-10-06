"""
Views for Faculty domain.

Enforces:
- Scope-aware directory querysets.
- Self-profile access via /me/.
- Sensitive bank account unmasking with mandatory audit logging.
- IDOR prevention via scope checks.
"""
from django.db import models, transaction
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.audit.models import AuditLog
from apps.audit.services import audit_log
from apps.common.encryption import decrypt_value
from django.utils import timezone
from apps.authentication.permissions import (
    HasScopeAccess,
    get_user_scopes,
    user_has_permission,
)
from apps.academic_structure.models import Department
from apps.authentication.models import PasswordHistory, Role, RoleAssignment, User
from apps.faculty.models import (
    Faculty,
    FacultyBankAccount,
    TeachingAssignment,
)
from apps.faculty.serializers import (
    FacultyCreateSerializer,
    FacultyListSerializer,
    FacultyProfileSerializer,
    TeachingAssignmentSerializer,
    TeachingAssignmentWriteSerializer,
)


class FacultyViewSet(viewsets.ModelViewSet):
    """
    Faculty ViewSet supporting institute directory, profile composition,
    self-service /me/ endpoint, audited sensitive data reveal,
    and sysadmin-only faculty onboarding via POST /.
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = FacultyProfileSerializer

    def get_serializer_class(self):
        if self.action == 'list':
            return FacultyListSerializer
        if self.action == 'create':
            return FacultyCreateSerializer
        return FacultyProfileSerializer

    def create(self, request, *args, **kwargs):
        """Sysadmin-only faculty onboarding: User + Faculty + RoleAssignment."""
        scopes = get_user_scopes(request.user)
        allowed = (
            scopes['is_system_wide']
            or request.user.is_superuser
            or user_has_permission(request.user, 'faculty.create')
        )
        if not allowed:
            return Response(
                {'detail': 'Only Sysadmin can add faculty members.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = FacultyCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        department = Department.objects.filter(id=data['department_id']).first()
        if not department:
            return Response(
                {'department_id': 'Department not found.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            user = User(
                username=data['username'],
                email=data['official_email'],
                user_type=User.UserType.FACULTY,
                is_active=True,
                must_change_password=True,
            )
            # Initial password = employee_code (same convention as student
            # onboarding: identifier-as-password + forced change on first login).
            user.set_password(data['employee_code'].strip())
            user.save()
            PasswordHistory.objects.create(user=user, password_hash=user.password)

            faculty = Faculty.objects.create(
                user=user,
                employee_code=data['employee_code'].strip(),
                first_name=data['first_name'].strip(),
                middle_name=(data.get('middle_name') or '').strip(),
                last_name=data['last_name'].strip(),
                department=department,
                designation=data['designation'],
                employment_type=data.get('employment_type') or Faculty.EmploymentType.REGULAR,
                employment_status=Faculty.EmploymentStatus.ACTIVE,
                date_of_joining=data['date_of_joining'],
                official_email=data['official_email'].strip(),
                mobile=(data.get('mobile') or '').strip(),
                is_active=True,
            )

            role = Role.objects.filter(codename=data['initial_role']).first()
            RoleAssignment.objects.create(
                user=user,
                role=role,
                department_id=department.id,
                division_id=data.get('division_id'),
                status=RoleAssignment.Status.ACTIVE,
                assigned_by=request.user if request.user.is_authenticated else None,
                reason='Sysadmin faculty onboarding',
            )
            # HOD / CLASS_TEACHER / ACCOUNTANT / ADMIN_HEAD also hold base FACULTY.
            if data['initial_role'] != 'FACULTY':
                base_role = Role.objects.filter(codename='FACULTY').first()
                if base_role:
                    RoleAssignment.objects.get_or_create(
                        user=user,
                        role=base_role,
                        department_id=department.id,
                        defaults={
                            'status': RoleAssignment.Status.ACTIVE,
                            'assigned_by': request.user if request.user.is_authenticated else None,
                            'reason': 'Base faculty role for operational role holder',
                        },
                    )

            audit_log(
                request=request,
                actor=request.user,
                action=AuditLog.Action.CREATE,
                target_type='Faculty',
                target_id=str(faculty.id),
                target_display=f'{faculty.display_name} ({faculty.employee_code})',
                new_value={
                    'employee_code': faculty.employee_code,
                    'official_email': faculty.official_email,
                    'department': department.code,
                    'designation': faculty.designation,
                    'username': user.username,
                    'role': data['initial_role'],
                },
                reason='Sysadmin faculty onboarding',
                description=(
                    f"Sysadmin created faculty '{faculty.display_name}' "
                    f"({faculty.employee_code}) with role {data['initial_role']}."
                ),
            )

        output = FacultyProfileSerializer(faculty).data
        output['username'] = user.username
        output['must_change_password'] = True
        return Response(output, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        return Response(
            {'detail': 'Faculty updates are not supported via this endpoint yet.'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def partial_update(self, request, *args, **kwargs):
        return Response(
            {'detail': 'Faculty updates are not supported via this endpoint yet.'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def destroy(self, request, *args, **kwargs):
        return Response(
            {'detail': 'Faculty records cannot be deleted.'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated:
            return Faculty.objects.none()

        qs = Faculty.objects.select_related('department').prefetch_related(
            'personal_details',
            'addresses',
            'qualifications',
            'experiences',
            'publications',
            'guidance_records',
            'bank_accounts',
            'documents',
            'teaching_assignments__academic_year',
            'teaching_assignments__department',
            'teaching_assignments__semester',
            'teaching_assignments__division',
        ).filter(is_active=True)

        scopes = get_user_scopes(user)

        # 1. Sysadmin / Admin Head / Accountant: institute-wide
        if scopes['is_system_wide'] or 'ADMIN_HEAD' in scopes['roles'] or 'ACCOUNTANT' in scopes['roles']:
            return self._apply_filters(qs)

        # 2. HOD: department-scoped
        if 'HOD' in scopes['roles']:
            dept_ids = scopes['department_ids']
            if dept_ids:
                return self._apply_filters(qs.filter(department_id__in=dept_ids))
            return self._apply_filters(qs)

        # 3. Faculty / Class Teacher / Student: institute directory (read-only)
        return self._apply_filters(qs)

    def _apply_filters(self, qs):
        dept = self.request.query_params.get('department_id')
        designation = self.request.query_params.get('designation')
        search = self.request.query_params.get('search')

        if dept:
            qs = qs.filter(department_id=dept)
        if designation:
            qs = qs.filter(designation=designation)
        if search:
            search = search.strip()
            qs = qs.filter(
                models.Q(display_name__icontains=search)
                | models.Q(employee_code__icontains=search)
                | models.Q(official_email__icontains=search)
            )
        return qs.distinct()

    @action(detail=False, methods=['get'], url_path='me')
    def me(self, request):
        """Retrieve the authenticated faculty member's own profile."""
        try:
            faculty = Faculty.objects.get(user_id=request.user.id, is_active=True)
        except Faculty.DoesNotExist:
            return Response(
                {'detail': 'Faculty profile not associated with this account.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = FacultyProfileSerializer(faculty)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='reveal')
    def reveal_sensitive(self, request, pk=None):
        """
        Reveal unmasked sensitive bank details with audit logging.
        Requires 'faculty.sensitive_reveal' permission or sysadmin.
        """
        faculty = self.get_object()

        # Authorization check
        if not user_has_permission(request.user, 'faculty.sensitive_reveal') and not request.user.is_superuser:
            return Response(
                {'detail': 'You do not have permission to reveal sensitive faculty financial data.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        reason = str(request.data.get('reason', '') or '').strip()
        if len(reason) < 5:
            return Response(
                {'detail': 'A justification reason of at least 5 characters is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Audit log the event
        audit_log(
            request=request,
            actor=request.user,
            action=AuditLog.Action.SENSITIVE_REVEAL,
            target_type='Faculty',
            target_id=str(faculty.id),
            target_display=faculty.display_name,
            reason=reason,
            description=f"Sensitive bank account reveal for faculty '{faculty.display_name}'.",
        )

        primary_bank = faculty.bank_accounts.filter(is_primary=True).first()

        return Response({
            'bank_account_number': (
                decrypt_value(primary_bank.account_number_encrypted)
                if primary_bank and getattr(primary_bank, 'account_number_encrypted', '') else None
            ),
            'revealed_at': timezone.now(),
            'message': 'Sensitive faculty bank details unmasked. Access has been recorded in the security audit trail.',
        }, status=status.HTTP_200_OK)


class TeachingAssignmentViewSet(viewsets.ModelViewSet):
    """Subject-teacher slots, owned by HOD (own dept) and Sysadmin.

    Assignment only — no verification rights flow from here. Replacing a
    holder deactivates the old row (history preserved); rows are never
    updated or deleted through this API.
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TeachingAssignmentWriteSerializer

    def get_queryset(self):
        qs = TeachingAssignment.objects.select_related(
            'faculty', 'academic_year', 'department', 'semester', 'division',
            'scheme_subject').all().order_by('-is_active', 'subject_code')
        user = self.request.user
        scopes = get_user_scopes(user)
        if not (scopes['is_system_wide'] or user.is_superuser):
            if 'HOD' in scopes['roles']:
                qs = qs.filter(department_id__in=scopes['department_ids'])
            elif 'ADMIN_HEAD' in scopes['roles']:
                pass
            else:
                qs = qs.filter(faculty__user_id=user.id)
        for param, field in (('division_id', 'division_id'), ('faculty_id', 'faculty_id'),
                             ('is_active', 'is_active'), ('semester', 'semester__number')):
            val = self.request.query_params.get(param, '')
            if isinstance(val, str):
                val = val.strip()
            if val != '' and val is not None:
                qs = qs.filter(**{field: val})
        return qs

    def _check_manage(self, department_id):
        from apps.authentication.permissions import user_has_permission, user_has_role
        from rest_framework.exceptions import PermissionDenied
        user = self.request.user
        if user.is_superuser or user_has_role(user, 'SYSADMIN') or user_has_permission(user, 'faculty.create'):
            return
        if user_has_role(user, 'HOD'):
            scopes = get_user_scopes(user)
            if str(department_id) in {str(d) for d in scopes.get('department_ids', [])}:
                return
            raise PermissionDenied('HOD may only manage subject teachers in their own department.')
        raise PermissionDenied('Only HOD or Sysadmin can manage subject teachers.')

    def perform_create(self, serializer):
        from apps.academic_structure.models import Division
        from rest_framework.exceptions import ValidationError
        division = serializer.validated_data.get('division')
        self._check_manage(division.department_id if division else None)
        with transaction.atomic():
            # Lock the division row and re-verify the slot under lock so two
            # concurrent assigns cannot both slip past serializer validation.
            # Replacement is explicit: deactivate the holder first, then create.
            if division is not None:
                Division.objects.select_for_update().filter(id=division.id).first()
                role = serializer.validated_data.get('role', TeachingAssignment.Role.PRIMARY_FACULTY)
                faculty = serializer.validated_data.get('faculty')
                code = (serializer.validated_data.get('subject_code') or '').strip().upper()
                clash = TeachingAssignment.objects.filter(
                    division=division, subject_code=code, is_active=True)
                if str(role) == TeachingAssignment.Role.LAB_INSTRUCTOR:
                    clash = clash.filter(role=TeachingAssignment.Role.LAB_INSTRUCTOR)
                else:
                    clash = clash.exclude(role=TeachingAssignment.Role.LAB_INSTRUCTOR)
                clash = clash.exclude(faculty=faculty).first()
                if clash:
                    raise ValidationError(
                        '%s is already taken by %s. Deactivate it first to replace.' % (
                            code, clash.faculty.display_name))
            obj = serializer.save()
            audit_log(
                request=self.request, actor=self.request.user,
                action=AuditLog.Action.CREATE, target_type='TeachingAssignment',
                target_id=str(obj.id),
                target_display=f'{obj.subject_code} -> {obj.faculty.display_name}',
                reason='HOD subject-teacher assignment',
                description=(
                    f"Assigned {obj.faculty.display_name} to {obj.subject_code} "
                    f"({obj.get_role_display()}) in {obj.division}."),
            )

    def update(self, request, *args, **kwargs):
        return Response({'detail': 'Assignments are immutable; deactivate and create anew.'},
                        status=status.HTTP_405_METHOD_NOT_ALLOWED)

    def partial_update(self, request, *args, **kwargs):
        return Response({'detail': 'Assignments are immutable; deactivate and create anew.'},
                        status=status.HTTP_405_METHOD_NOT_ALLOWED)

    def destroy(self, request, *args, **kwargs):
        return Response({'detail': 'Assignments cannot be deleted; deactivate instead.'},
                        status=status.HTTP_405_METHOD_NOT_ALLOWED)

    @action(detail=True, methods=['post'], url_path='deactivate')
    def deactivate(self, request, pk=None):
        obj = self.get_object()
        self._check_manage(obj.department_id)
        obj.is_active = False
        obj.save(update_fields=['is_active'])
        audit_log(
            request=request, actor=request.user, action=AuditLog.Action.UPDATE,
            target_type='TeachingAssignment', target_id=str(obj.id),
            target_display=f'{obj.subject_code} -> {obj.faculty.display_name}',
            reason=request.data.get('reason', 'HOD end of assignment') if request.data else 'HOD end of assignment',
            description=f"Deactivated {obj.faculty.display_name} from {obj.subject_code} in {obj.division}.",
        )
        return Response(TeachingAssignmentSerializer(obj).data, status=status.HTTP_200_OK)
