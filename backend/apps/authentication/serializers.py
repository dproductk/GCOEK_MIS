"""
Authentication serializers — login, token, user profile, password change.

Per SECURITY.md:
- Passwords validated server-side (min 12 chars, history check, no common passwords)
- Sensitive fields never returned in API responses
- Login returns JWT access token (refresh set as HttpOnly cookie)
"""
from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import check_password
from django.utils import timezone

from rest_framework import serializers

from apps.authentication.models import (
    PasswordHistory,
    Permission,
    Role,
    RoleAssignment,
    User,
)


class LoginSerializer(serializers.Serializer):
    """Validates login credentials and checks account lockout."""

    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        username = attrs.get('username', '').strip()
        password = attrs.get('password', '')

        if not username or not password:
            raise serializers.ValidationError('Username and password are required.')

        # Check if user exists (by username, email, or student application_id / enrollment_no)
        from django.db.models import Q
        user = User.objects.filter(username=username).first()
        if not user:
            user = User.objects.filter(email__iexact=username).first()
        if not user:
            from apps.students.models import Student
            student = Student.objects.filter(
                Q(application_id__iexact=username) | Q(enrollment_no__iexact=username)
            ).select_related('user').first()
            if student and student.user:
                user = student.user
        if not user:
            raise serializers.ValidationError('Invalid username or password.')

        if not user.is_active:
            raise serializers.ValidationError('This account has been deactivated.')

        # Check lockout
        max_attempts = getattr(settings, 'MAX_FAILED_LOGIN_ATTEMPTS', 5)
        lockout_minutes = getattr(settings, 'LOGIN_LOCKOUT_DURATION_MINUTES', 15)

        if user.locked_until and user.locked_until > timezone.now():
            remaining = (user.locked_until - timezone.now()).seconds // 60
            raise serializers.ValidationError(
                f'Account is locked due to too many failed attempts. '
                f'Try again in {remaining + 1} minute(s).'
            )

        # Clear expired lockout
        if user.locked_until and user.locked_until <= timezone.now():
            user.locked_until = None
            user.failed_login_attempts = 0
            user.save(update_fields=['locked_until', 'failed_login_attempts'])

        # Authenticate
        authenticated_user = authenticate(
            request=self.context.get('request'),
            username=user.username,
            password=password,
        )

        if authenticated_user is None:
            # Increment failed attempts
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= max_attempts:
                user.locked_until = timezone.now() + timezone.timedelta(
                    minutes=lockout_minutes
                )
            user.save(update_fields=['failed_login_attempts', 'locked_until'])
            raise serializers.ValidationError('Invalid username or password.')

        # Reset failed attempts on success
        if user.failed_login_attempts > 0:
            user.failed_login_attempts = 0
            user.locked_until = None
            user.save(update_fields=['failed_login_attempts', 'locked_until'])

        attrs['user'] = authenticated_user
        return attrs


class UserProfileSerializer(serializers.ModelSerializer):
    """
    Serializes user profile with active roles for /auth/me/ endpoint.

    Returns user identity + active role assignments with permissions.
    Never returns sensitive fields (password, lockout, etc.).
    """

    roles = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'email',
            'user_type',
            'is_active',
            'must_change_password',
            'date_joined',
            'roles',
        ]
        read_only_fields = fields

    def get_roles(self, user):
        """Return active role assignments with permissions."""
        assignments = (
            RoleAssignment.objects.filter(user=user, status=RoleAssignment.Status.ACTIVE)
            .select_related('role')
            .order_by('-assigned_at')
        )

        result = []
        for assignment in assignments:
            # Get permissions for this role
            permission_codenames = list(
                assignment.role.role_permissions.values_list(
                    'permission__codename', flat=True
                )
            )

            result.append({
                'assignment_id': str(assignment.id),
                'codename': assignment.role.codename,
                'name': assignment.role.name,
                'department_id': str(assignment.department_id) if assignment.department_id else None,
                'division_id': str(assignment.division_id) if assignment.division_id else None,
                'status': assignment.status,
                'assigned_at': assignment.assigned_at.isoformat(),
                'permissions': permission_codenames,
            })

        return result


class ChangePasswordSerializer(serializers.Serializer):
    """
    Validates password change requests.

    Enforces:
    - Current password verification
    - Minimum length (from settings)
    - Password history check (prevent reuse of last N passwords)
    - New password != current password
    """

    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        if len(value) < 12:
            raise serializers.ValidationError(
                'Password must be at least 12 characters.'
            )
        return value

    def validate(self, attrs):
        user = self.context['request'].user

        # Verify current password
        if not user.check_password(attrs['current_password']):
            raise serializers.ValidationError(
                {'current_password': 'Current password is incorrect.'}
            )

        # Confirm new passwords match
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError(
                {'confirm_password': 'New passwords do not match.'}
            )

        # Check not same as current
        if attrs['current_password'] == attrs['new_password']:
            raise serializers.ValidationError(
                {'new_password': 'New password must be different from current password.'}
            )

        # Check password history
        history_count = getattr(settings, 'PASSWORD_HISTORY_COUNT', 5)
        recent_passwords = PasswordHistory.objects.filter(
            user=user
        ).order_by('-changed_at')[:history_count]

        for entry in recent_passwords:
            if check_password(attrs['new_password'], entry.password_hash):
                raise serializers.ValidationError(
                    {'new_password': f'Cannot reuse any of your last {history_count} passwords.'}
                )

        return attrs


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ['id', 'name', 'codename', 'description', 'is_active']


class RoleAssignmentSerializer(serializers.ModelSerializer):
    user_username = serializers.CharField(source='user.username', read_only=True)
    role_codename = serializers.CharField(source='role.codename', read_only=True)
    role_name = serializers.CharField(source='role.name', read_only=True)

    class Meta:
        model = RoleAssignment
        fields = [
            'id',
            'user',
            'user_username',
            'role',
            'role_codename',
            'role_name',
            'department_id',
            'division_id',
            'status',
            'assigned_at',
            'revoked_at',
        ]
        read_only_fields = ['id', 'assigned_at', 'revoked_at']


class UserAdminSerializer(serializers.ModelSerializer):
    roles = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'email',
            'user_type',
            'is_active',
            'must_change_password',
            'date_joined',
            'roles',
        ]

    def get_roles(self, user):
        if hasattr(user, '_prefetched_objects_cache') and 'role_assignments' in user._prefetched_objects_cache:
            assignments = [a for a in user.role_assignments.all() if a.status == RoleAssignment.Status.ACTIVE]
        else:
            assignments = user.role_assignments.filter(status=RoleAssignment.Status.ACTIVE).select_related('role')
        return [
            {
                'id': str(a.id),
                'role_id': str(a.role.id),
                'codename': a.role.codename,
                'name': a.role.name,
                'department_id': str(a.department_id) if a.department_id else None,
                'division_id': str(a.division_id) if a.division_id else None,
                'status': a.status,
            }
            for a in assignments
        ]
