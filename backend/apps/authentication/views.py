"""
Authentication views — Login, Token Refresh, Logout, Current User, and Password Change.

Per SECURITY.md:
- Refresh tokens are delivered and received via HttpOnly cookies.
- Access tokens are returned in the response body to be kept in-memory on the frontend.
- Account lockout is enforced after 5 consecutive failed attempts.
- Password change requires current password verification and enforces history of 5.
- All auth events (login, login failure, logout, password change) generate append-only audit logs.
"""
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit.models import AuditLog
from apps.audit.services import audit_log
from apps.authentication.models import PasswordHistory, Role, RoleAssignment, User
from apps.authentication.permissions import IsSysadmin
from apps.authentication.serializers import (
    ChangePasswordSerializer,
    LoginSerializer,
    RoleAssignmentSerializer,
    RoleSerializer,
    UserAdminSerializer,
    UserProfileSerializer,
)


def _set_refresh_cookie(response, refresh_token_str):
    """Utility to attach the HttpOnly refresh token cookie to the response."""
    refresh_lifetime = settings.SIMPLE_JWT.get('REFRESH_TOKEN_LIFETIME')
    max_age = int(refresh_lifetime.total_seconds()) if refresh_lifetime else 604800

    response.set_cookie(
        key='refresh_token',
        value=refresh_token_str,
        max_age=max_age,
        httponly=True,
        secure=not settings.DEBUG,
        samesite='Lax' if settings.DEBUG else 'Strict',
        path='/api/v1/auth/',
    )


class LoginView(APIView):
    """
    Authenticate user with credentials, check lockout, and issue JWT tokens.

    POST /api/v1/auth/login/
    Rate-limited to 5/min per SECURITY.md Sec 10 (plus account lockout).
    """

    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            raw_username = request.data.get('username', '').strip()
            audit_log(
                request=request,
                action=AuditLog.Action.LOGIN_FAILED,
                target_type='User',
                target_display=raw_username,
                description=f"Failed login attempt for username '{raw_username}'.",
            )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = serializer.validated_data['user']

        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)

        # Audit log successful login
        audit_log(
            request=request,
            actor=user,
            action=AuditLog.Action.LOGIN,
            target_type='User',
            target_id=str(user.id),
            target_display=user.username,
            description=f"User '{user.username}' logged in successfully.",
        )

        user_data = UserProfileSerializer(user).data

        response = Response(
            {
                'access': access_token,
                'user': user_data,
                'must_change_password': user.must_change_password,
            },
            status=status.HTTP_200_OK,
        )

        # Store refresh token in HttpOnly cookie
        _set_refresh_cookie(response, str(refresh))
        return response


class TokenRefreshView(APIView):
    """
    Refresh expired access token using the HttpOnly refresh cookie.

    POST /api/v1/auth/refresh/
    Rate-limited to 5/min to prevent token refresh abuse (F-S4-002).
    """

    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'

    def post(self, request):
        refresh_token = request.COOKIES.get('refresh_token') or request.data.get('refresh')
        if not refresh_token:
            return Response(
                {'detail': 'Refresh token missing.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        serializer = TokenRefreshSerializer(data={'refresh': refresh_token})
        try:
            serializer.is_valid(raise_exception=True)
        except (TokenError, InvalidToken) as e:
            return Response(
                {'detail': 'Token is invalid or expired.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        data = {'access': serializer.validated_data['access']}
        response = Response(data, status=status.HTTP_200_OK)

        # If token was rotated, update cookie with new refresh token
        new_refresh = serializer.validated_data.get('refresh')
        if new_refresh:
            _set_refresh_cookie(response, new_refresh)

        return response


class LogoutView(APIView):
    """
    Log out user, blacklist refresh token, and clear HttpOnly cookie.

    POST /api/v1/auth/logout/
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        refresh_token = request.COOKIES.get('refresh_token') or request.data.get('refresh')
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except Exception:
                pass

        if request.user and request.user.is_authenticated:
            audit_log(
                request=request,
                actor=request.user,
                action=AuditLog.Action.LOGOUT,
                target_type='User',
                target_id=str(request.user.id),
                target_display=request.user.username,
                description=f"User '{request.user.username}' logged out.",
            )

        response = Response({'detail': 'Successfully logged out.'}, status=status.HTTP_200_OK)
        response.delete_cookie('refresh_token', path='/api/v1/auth/')
        return response


class CurrentUserView(APIView):
    """
    Retrieve authenticated user profile and active roles.

    GET /api/v1/auth/me/
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = UserProfileSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ChangePasswordView(APIView):
    """
    Change user password with minimum length and history validation.

    POST /api/v1/auth/change-password/
    Rate-limited to prevent brute-force against own account (F-S4-001).
    """

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'

    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)

        user = request.user
        new_password = serializer.validated_data['new_password']

        user.set_password(new_password)
        user.must_change_password = False
        user.save(update_fields=['password', 'must_change_password', 'updated_at'])

        # Record password history to prevent reuse
        PasswordHistory.objects.create(
            user=user,
            password_hash=user.password,
        )

        # Audit log password change
        audit_log(
            request=request,
            actor=user,
            action=AuditLog.Action.PASSWORD_CHANGE,
            target_type='User',
            target_id=str(user.id),
            target_display=user.username,
            description=f"User '{user.username}' changed their password.",
        )

        return Response(
            {'detail': 'Password changed successfully.'},
            status=status.HTTP_200_OK,
        )


class RoleViewSet(viewsets.ReadOnlyModelViewSet):
    """List available institutional roles (sysadmin only to prevent role mining)."""
    permission_classes = [IsSysadmin]
    serializer_class = RoleSerializer
    queryset = Role.objects.filter(is_active=True).order_by('name')


class UserManagementViewSet(viewsets.ReadOnlyModelViewSet):
    """
    User account directory for Sysadmins.
    """
    permission_classes = [IsSysadmin]
    serializer_class = UserAdminSerializer
    queryset = User.objects.prefetch_related('role_assignments__role').all().order_by('-date_joined')

    def get_queryset(self):
        qs = super().get_queryset()
        user_type = self.request.query_params.get('user_type')
        search = self.request.query_params.get('search')
        if user_type:
            qs = qs.filter(user_type=user_type)
        if search:
            search = search.strip()
            qs = qs.filter(username__icontains=search) | qs.filter(email__icontains=search)
        return qs


class RoleAssignmentViewSet(viewsets.ModelViewSet):
    """
    Manage user role assignments and department/division scopes.
    Sysadmin-only by default to prevent privilege escalation.
    Exception: HOD may create CLASS_TEACHER assignments within their own
    department (single-owner sync path). All other writes are sysadmin-only.
    Every assignment and revocation generates an audit trail.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = RoleAssignmentSerializer
    queryset = RoleAssignment.objects.select_related('user', 'role').all().order_by('-assigned_at')

    def _is_sysadmin(self, user):
        from apps.authentication.permissions import get_user_scopes
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        scopes = get_user_scopes(user)
        return bool(scopes.get('is_system_wide'))

    def _is_hod_ct_create_allowed(self, request):
        """HOD may assign CLASS_TEACHER only within their own department.

        Security: the target user MUST be FACULTY type — granting CT to a
        student or sysadmin is a privilege-escalation vector (F-S3-003).
        """
        from apps.authentication.permissions import get_user_scopes
        try:
            data = request.data or {}
            role_id = data.get('role')
            department_id = data.get('department_id')
            division_id = data.get('division_id')
            user_id = data.get('user')
            if not (role_id and department_id and division_id):
                return False
            from apps.authentication.models import Role as _Role
            role = _Role.objects.filter(id=role_id).first()
            if not role or role.codename != 'CLASS_TEACHER':
                return False
            # F-S3-003: Target user must be FACULTY, never a STUDENT.
            if user_id:
                target_user = User.objects.filter(id=user_id).first()
                if not target_user or target_user.user_type != User.UserType.FACULTY:
                    return False
            scopes = get_user_scopes(request.user)
            if 'HOD' not in scopes.get('roles', []):
                return False
            import uuid as _uuid
            try:
                dept_uuid = _uuid.UUID(str(department_id))
            except Exception:
                return False
            if dept_uuid not in scopes.get('department_ids', []):
                return False
            # Division must belong to that department.
            from apps.academic_structure.models import Division
            try:
                div = Division.objects.filter(id=division_id).first()
            except Exception:
                return False
            if div is None or div.department_id != dept_uuid:
                return False
            return True
        except Exception:
            return False

    def check_permissions(self, request):
        super().check_permissions(request)
        # Read endpoints: sysadmin-only (prevents user/role mining).
        # Create: sysadmin, or HOD creating CT in own dept.
        # All other writes (update/destroy/revoke): sysadmin-only.
        if self.action in ('list', 'retrieve'):
            if not self._is_sysadmin(request.user):
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied('Only Sysadmin can view role assignments.')
        elif self.action == 'create':
            if self._is_sysadmin(request.user):
                return
            if self._is_hod_ct_create_allowed(request):
                return
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('Only Sysadmin can create role assignments (HOD may assign Class Teacher in own department).')
        elif self.action in ('update', 'partial_update', 'destroy'):
            if not self._is_sysadmin(request.user):
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied('Only Sysadmin can modify role assignments.')
        # Custom @action methods (revoke, department-hods) enforce their own checks.

    def get_queryset(self):
        qs = super().get_queryset()
        if not self._is_sysadmin(self.request.user):
            # Non-sysadmin (HOD CT idempotency path) sees nothing by default.
            # Scoped reads are not required for the CT create flow.
            return qs.none()
        user_id = self.request.query_params.get('user_id')
        role_id = self.request.query_params.get('role_id')
        active_only = self.request.query_params.get('active_only')

        if user_id:
            qs = qs.filter(user_id=user_id)
        if role_id:
            qs = qs.filter(role_id=role_id)
        if active_only == 'true':
            qs = qs.filter(status=RoleAssignment.Status.ACTIVE)
        return qs

    def create(self, request, *args, **kwargs):
        # Idempotent class-teacher assignment: same user+division returns
        # the existing row instead of duplicating it.
        resp = self._maybe_existing_ct_assignment(request)
        if resp is not None:
            return resp
        return super().create(request, *args, **kwargs)

    def _maybe_existing_ct_assignment(self, request):
        try:
            data = request.data or {}
            role_id = data.get('role')
            user_id = data.get('user')
            division_id = data.get('division_id')
            if not (role_id and user_id and division_id):
                return None
            from apps.authentication.models import Role as _Role
            role = _Role.objects.filter(id=role_id).first()
            if not role or role.codename != 'CLASS_TEACHER':
                return None
            existing = RoleAssignment.objects.filter(
                user_id=user_id, role=role, division_id=division_id,
                status=RoleAssignment.Status.ACTIVE).first()
            if not existing:
                return None
            audit_log(
                request=request,
                actor=request.user,
                action=AuditLog.Action.ROLE_ASSIGN,
                target_type='RoleAssignment',
                target_id=str(existing.id),
                target_display='Class-teacher assignment already active',
                reason='Duplicate class-teacher assignment ignored',
                description='Re-assignment matched an existing active row; no change.',
            )
            return Response(RoleAssignmentSerializer(existing).data, status=status.HTTP_200_OK)
        except Exception:
            return None

    def perform_create(self, serializer):
        role = serializer.validated_data.get('role')
        user = serializer.validated_data.get('user')
        division_id = serializer.validated_data.get('division_id')
        status_active = RoleAssignment.Status.ACTIVE
        # Class-teacher assignments go through the single-owner sync service
        # so Division.class_teacher and the RoleAssignment never drift apart.
        if role and role.codename == 'CLASS_TEACHER' and division_id:
            from apps.academic_structure.models import Division
            from apps.academic_structure.services import sync_class_teacher
            division = Division.objects.filter(id=division_id).first()
            if division is None:
                from rest_framework.exceptions import ValidationError
                raise ValidationError({'division_id': 'Division not found.'})
            assignment, _ = sync_class_teacher(
                division, user, self.request.user, self.request,
                reason='Class-teacher role assignment')
            serializer.instance = assignment
            return
        assignment = serializer.save(status=status_active)
        audit_log(
            request=self.request,
            actor=self.request.user,
            action=AuditLog.Action.ROLE_ASSIGN,
            target_type='RoleAssignment',
            target_id=str(assignment.id),
            target_display=f"{assignment.user.username} -> {assignment.role.name}",
            reason='Administrative role assignment',
            description=f"Assigned role '{assignment.role.name}' to user '{assignment.user.username}'.",
        )

    def perform_update(self, serializer):
        old = serializer.instance
        old_snapshot = {
            'status': old.status,
            'role': old.role.codename if old.role else '',
            'user': old.user.username if old.user else '',
        } if old else None
        assignment = serializer.save()
        audit_log(
            request=self.request,
            actor=self.request.user,
            action=AuditLog.Action.UPDATE,
            target_type='RoleAssignment',
            target_id=str(assignment.id),
            target_display=f"{assignment.user.username} -> {assignment.role.name}",
            old_value=old_snapshot,
            new_value={'status': assignment.status},
            reason='Administrative role assignment update',
            description=f"Updated role assignment '{assignment.role.name}' for user '{assignment.user.username}'.",
        )

    def perform_destroy(self, instance):
        label = f"{instance.user.username} -> {instance.role.name}" if instance.user and instance.role else str(instance.id)
        aid = str(instance.id)
        # F-S3-002: Clear stale Division.class_teacher before deletion.
        if instance.role and instance.role.codename == 'CLASS_TEACHER' and instance.user_id:
            from apps.academic_structure.models import Division
            Division.objects.filter(class_teacher_id=instance.user_id).update(class_teacher=None)
        instance.delete()
        audit_log(
            request=self.request,
            actor=self.request.user,
            action=AuditLog.Action.ROLE_REVOKE,
            target_type='RoleAssignment',
            target_id=aid,
            target_display=label,
            reason='Administrative role assignment deleted',
            description=f"Deleted role assignment {label}. Row removed; audit entry retained.",
        )

    @action(detail=True, methods=['post'], url_path='revoke')
    def revoke(self, request, pk=None):
        if not self._is_sysadmin(request.user):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('Only Sysadmin can revoke role assignments.')
        assignment = self.get_object()
        assignment.status = RoleAssignment.Status.REVOKED
        assignment.revoked_at = timezone.now()
        assignment.save(update_fields=['status', 'revoked_at', 'updated_at'])

        # F-S3-002: Clear stale Division.class_teacher on CT revocation.
        if assignment.role and assignment.role.codename == 'CLASS_TEACHER' and assignment.user_id:
            from apps.academic_structure.models import Division
            Division.objects.filter(class_teacher_id=assignment.user_id).update(class_teacher=None)

        audit_log(
            request=request,
            actor=request.user,
            action=AuditLog.Action.ROLE_REVOKE,
            target_type='RoleAssignment',
            target_id=str(assignment.id),
            target_display=f"{assignment.user.username} -> {assignment.role.name}",
            reason=request.data.get('reason', 'Administrative role revocation'),
            description=f"Revoked role '{assignment.role.name}' from user '{assignment.user.username}'.",
        )
        return Response({'detail': f"Role '{assignment.role.name}' revoked successfully."}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get', 'post'], url_path='department-hods')
    def department_hods(self, request):
        """
        Sysadmin manages HOD assignments for all 5 departments.
        GET: Returns all 5 departments with their currently assigned active HOD,
             plus a list of candidate faculty users.
        POST: Accepts a batch assignment list:
              {"assignments": [{"department_id": "...", "user_id": "..."}, ...]}
              Assigns HODs across the departments (up to all 5 at a time),
              revoking any previous active HOD for each department.
        """
        from apps.academic_structure.models import Department
        from apps.authentication.models import Role, RoleAssignment, User
        from apps.authentication.permissions import get_user_scopes

        user = request.user
        scopes = get_user_scopes(user)
        if not (scopes['is_system_wide'] or request.user.is_superuser):
            return Response(
                {'detail': 'Only Sysadmin can manage department HOD assignments.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        hod_role, _ = Role.objects.get_or_create(codename='HOD', defaults={'name': 'Head of Department'})
        departments = Department.objects.all().order_by('name')

        if request.method == 'GET':
            active_hod_assignments = {
                str(ra.department_id): ra
                for ra in RoleAssignment.objects.filter(
                    role=hod_role, status=RoleAssignment.Status.ACTIVE, department_id__isnull=False
                ).select_related('user')
            }

            dept_list = []
            for d in departments:
                assigned_ra = active_hod_assignments.get(str(d.id))
                dept_list.append({
                    'department_id': str(d.id),
                    'department_name': d.name,
                    'department_code': d.code,
                    'hod_assignment_id': str(assigned_ra.id) if assigned_ra else None,
                    'hod_user_id': str(assigned_ra.user.id) if assigned_ra else None,
                    'hod_username': assigned_ra.user.username if assigned_ra else None,
                    'hod_display_name': getattr(assigned_ra.user, 'full_display_name', assigned_ra.user.username) if assigned_ra else None,
                    'hod_email': assigned_ra.user.email if assigned_ra else None,
                })

            faculty_users = User.objects.filter(
                user_type=User.UserType.FACULTY, is_active=True
            ).order_by('username').values('id', 'username', 'email')

            return Response({
                'departments': dept_list,
                'faculty_users': list(faculty_users),
            }, status=status.HTTP_200_OK)

        elif request.method == 'POST':
            assignments_data = request.data.get('assignments', [])
            if not isinstance(assignments_data, list):
                return Response({'detail': 'Invalid assignments payload, list expected.'}, status=status.HTTP_400_BAD_REQUEST)

            updated = []
            with transaction.atomic():
                for item in assignments_data:
                    dept_id = item.get('department_id')
                    target_user_id = item.get('user_id')
                    if not dept_id:
                        continue

                    dept = Department.objects.filter(id=dept_id).first()
                    if not dept:
                        continue

                    current_active = RoleAssignment.objects.filter(
                        role=hod_role, department_id=dept.id, status=RoleAssignment.Status.ACTIVE
                    )

                    if target_user_id:
                        target_user = User.objects.filter(id=target_user_id, is_active=True).first()
                        if not target_user:
                            continue

                        for ca in current_active:
                            if ca.user_id != target_user.id:
                                ca.status = RoleAssignment.Status.REVOKED
                                ca.revoked_at = timezone.now()
                                ca.revoked_by = request.user
                                ca.save(update_fields=['status', 'revoked_at', 'revoked_by', 'updated_at'])
                                audit_log(
                                    request=request,
                                    actor=request.user,
                                    action=AuditLog.Action.ROLE_REVOKE,
                                    target_type='RoleAssignment',
                                    target_id=str(ca.id),
                                    target_display=f"HOD: {dept.code} <- {ca.user.username if ca.user else '?'}",
                                    reason='Sysadmin department HOD replacement',
                                    description=f"Revoked HOD of {dept.name} ({dept.code}) from user '{ca.user.username if ca.user else '?'}'.",
                                )

                        assignment, created = RoleAssignment.objects.get_or_create(
                            user=target_user,
                            role=hod_role,
                            department_id=dept.id,
                            defaults={
                                'status': RoleAssignment.Status.ACTIVE,
                                'assigned_by': request.user,
                            }
                        )
                        if not created and assignment.status != RoleAssignment.Status.ACTIVE:
                            assignment.status = RoleAssignment.Status.ACTIVE
                            assignment.assigned_by = request.user
                            assignment.revoked_at = None
                            assignment.revoked_by = None
                            assignment.save(update_fields=['status', 'assigned_by', 'revoked_at', 'revoked_by', 'updated_at'])

                        audit_log(
                            request=request,
                            actor=request.user,
                            action=AuditLog.Action.ROLE_ASSIGN,
                            target_type='RoleAssignment',
                            target_id=str(assignment.id),
                            target_display=f"HOD: {dept.code} -> {target_user.username}",
                            reason='Sysadmin department HOD assignment',
                            description=f"Assigned HOD of {dept.name} ({dept.code}) to user '{target_user.username}'.",
                        )

                        updated.append({
                            'department_id': str(dept.id),
                            'department_code': dept.code,
                            'hod_user_id': str(target_user.id),
                            'hod_username': target_user.username,
                        })
                    else:
                        for ca in current_active:
                            ca.status = RoleAssignment.Status.REVOKED
                            ca.revoked_at = timezone.now()
                            ca.revoked_by = request.user
                            ca.save(update_fields=['status', 'revoked_at', 'revoked_by', 'updated_at'])
                            audit_log(
                                request=request,
                                actor=request.user,
                                action=AuditLog.Action.ROLE_REVOKE,
                                target_type='RoleAssignment',
                                target_id=str(ca.id),
                                target_display=f"HOD: {dept.code} <- {ca.user.username if ca.user else '?'}",
                                reason='Sysadmin department HOD cleared',
                                description=f"Cleared HOD of {dept.name} ({dept.code}); revoked from '{ca.user.username if ca.user else '?'}'.",
                            )

            return Response({
                'detail': f'HOD assignments successfully updated for {len(updated)} department(s).',
                'updated': updated,
            }, status=status.HTTP_200_OK)

