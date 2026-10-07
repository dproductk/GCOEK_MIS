"""
Authentication models — User, Role, Permission, RoleAssignment, PasswordHistory.

CRITICAL DESIGN RULE (from implementation plan Section 10):
- User.user_type is for account/person CLASSIFICATION only (STUDENT, FACULTY, SYSADMIN).
- user_type must NEVER be used for authorization decisions.
- All authorization uses: User → RoleAssignment → Role → Permission → Scope.
"""
import uuid

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models

from apps.common.models import BaseModel


# ---------------------------------------------------------------------------
# Custom User Manager
# ---------------------------------------------------------------------------
class UserManager(BaseUserManager):
    """Custom manager for the User model."""

    def create_user(self, username, email=None, password=None, **extra_fields):
        """Create and return a regular user."""
        if not username:
            raise ValueError('Username is required.')
        email = self.normalize_email(email) if email else None
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        """Create and return a superuser (Sysadmin)."""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('user_type', User.UserType.SYSADMIN)
        extra_fields.setdefault('must_change_password', False)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(username, email, password, **extra_fields)


# ---------------------------------------------------------------------------
# User Model
# ---------------------------------------------------------------------------
class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom User model for GCOEK MIS.

    IMPORTANT: user_type is for classification/routing purposes only.
    It identifies what KIND of person this account represents (student,
    faculty, sysadmin). It is NOT used for authorization.

    All authorization decisions use RoleAssignment → Role → Permission → Scope.
    """

    class UserType(models.TextChoices):
        STUDENT = 'STUDENT', 'Student'
        FACULTY = 'FACULTY', 'Faculty'
        SYSADMIN = 'SYSADMIN', 'System Administrator'

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    username = models.CharField(
        max_length=150,
        unique=True,
        help_text='Unique login identifier.',
    )
    email = models.EmailField(
        blank=True,
        null=True,
        help_text='Email address (optional for students).',
    )
    user_type = models.CharField(
        max_length=20,
        choices=UserType.choices,
        help_text=(
            'Account classification: STUDENT, FACULTY, or SYSADMIN. '
            'This is for routing/display only — NOT for authorization.'
        ),
    )

    # Account lifecycle
    is_active = models.BooleanField(
        default=True,
        help_text='Whether this user account is active.',
    )
    is_staff = models.BooleanField(
        default=False,
        help_text='Whether user can access Django admin (Sysadmin only).',
    )
    must_change_password = models.BooleanField(
        default=True,
        help_text='If True, user must change password on next login.',
    )

    # Security
    failed_login_attempts = models.PositiveIntegerField(
        default=0,
        help_text='Consecutive failed login attempts.',
    )
    locked_until = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Account locked until this time after too many failed attempts.',
    )

    # Timestamps
    date_joined = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['user_type']

    class Meta:
        db_table = 'users'
        ordering = ['-date_joined']

    def __str__(self):
        return f'{self.username} ({self.get_user_type_display()})'

    @property
    def full_display_name(self):
        """Return a display-friendly name."""
        return self.username

    def get_full_name(self):
        """Standard Django User method."""
        return self.username

    def get_short_name(self):
        """Standard Django User method."""
        return self.username


# ---------------------------------------------------------------------------
# Role Model
# ---------------------------------------------------------------------------
class Role(BaseModel):
    """
    Role definition in the RBAC system.

    Roles are not hard-coded in business logic. New roles can be added
    through the Role table without changing code.
    """

    codename = models.CharField(
        max_length=50,
        unique=True,
        help_text='Unique role code (e.g., STUDENT, FACULTY, HOD).',
    )
    name = models.CharField(
        max_length=100,
        help_text='Human-readable role name.',
    )
    description = models.TextField(
        blank=True,
        default='',
        help_text='Description of this role\'s purpose and responsibilities.',
    )
    is_active = models.BooleanField(
        default=True,
        help_text='Whether this role is currently active.',
    )

    class Meta:
        db_table = 'roles'
        ordering = ['codename']

    def __str__(self):
        return f'{self.name} ({self.codename})'


# ---------------------------------------------------------------------------
# Permission Model
# ---------------------------------------------------------------------------
class Permission(BaseModel):
    """
    Permission definition for fine-grained access control.

    Permissions are grouped by module (domain context).
    """

    codename = models.CharField(
        max_length=100,
        unique=True,
        help_text='Unique permission code (e.g., student.view, student.edit).',
    )
    name = models.CharField(
        max_length=200,
        help_text='Human-readable permission description.',
    )
    module = models.CharField(
        max_length=50,
        db_index=True,
        help_text='Module/domain this permission belongs to (e.g., student, faculty, finance).',
    )

    class Meta:
        db_table = 'permissions'
        ordering = ['module', 'codename']

    def __str__(self):
        return f'{self.module}:{self.codename}'


# ---------------------------------------------------------------------------
# Role-Permission Mapping
# ---------------------------------------------------------------------------
class RolePermission(BaseModel):
    """Maps permissions to roles."""

    role = models.ForeignKey(
        Role,
        on_delete=models.CASCADE,
        related_name='role_permissions',
    )
    permission = models.ForeignKey(
        Permission,
        on_delete=models.CASCADE,
        related_name='role_permissions',
    )

    class Meta:
        db_table = 'role_permissions'
        unique_together = ['role', 'permission']

    def __str__(self):
        return f'{self.role.codename} → {self.permission.codename}'


# ---------------------------------------------------------------------------
# Role Assignment
# ---------------------------------------------------------------------------
class RoleAssignment(BaseModel):
    """
    Assigns a role to a user with optional scope context.

    This is the AUTHORITATIVE link between a user and their roles.
    All authorization checks resolve through this table.

    Scope is determined by the combination of role + department + division:
    - SYSADMIN role → system-wide scope
    - ADMIN_HEAD role → college-wide scope
    - HOD role + department → department scope
    - CLASS_TEACHER role + department + division → division scope
    - STUDENT/FACULTY role → own-record scope (no department/division needed)
    """

    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'
        EXPIRED = 'EXPIRED', 'Expired'
        REVOKED = 'REVOKED', 'Revoked'

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='role_assignments',
    )
    role = models.ForeignKey(
        Role,
        on_delete=models.PROTECT,
        related_name='assignments',
    )

    # Scope context (optional, depends on role type)
    department_id = models.UUIDField(
        null=True,
        blank=True,
        help_text='Department scope for HOD, CLASS_TEACHER roles. FK managed at application level.',
    )
    division_id = models.UUIDField(
        null=True,
        blank=True,
        help_text='Division scope for CLASS_TEACHER role. FK managed at application level.',
    )

    # Lifecycle
    assigned_at = models.DateTimeField(auto_now_add=True)
    assigned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assignments_made',
        help_text='User who made this assignment.',
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When this role assignment expires (null = no expiry).',
    )
    revoked_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    revoked_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assignments_revoked',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    reason = models.TextField(
        blank=True,
        default='',
        help_text='Reason for assignment/revocation.',
    )

    class Meta:
        db_table = 'role_assignments'
        ordering = ['-assigned_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['role', 'status']),
        ]

    def __str__(self):
        scope = ''
        if self.department_id:
            scope = f' [dept:{self.department_id}]'
        if self.division_id:
            scope += f' [div:{self.division_id}]'
        return f'{self.user.username} → {self.role.codename}{scope} ({self.status})'


# ---------------------------------------------------------------------------
# Password History
# ---------------------------------------------------------------------------
class PasswordHistory(BaseModel):
    """
    Stores hashed previous passwords to prevent reuse.

    Per SECURITY.md: prevent reuse of last N passwords.
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='password_history',
    )
    password_hash = models.CharField(
        max_length=255,
        help_text='Hashed previous password.',
    )
    changed_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        db_table = 'password_history'
        ordering = ['-changed_at']

    def __str__(self):
        return f'{self.user.username} password change at {self.changed_at}'
