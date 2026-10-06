"""
RBAC and Scope-based permission classes for GCOEK MIS.

Core rules (from ARCHITECTURE.md and SECURITY.md):
1. User.user_type is for classification only (STUDENT, FACULTY, SYSADMIN).
   It is NEVER used for authorization.
2. Authorization strictly checks: User → RoleAssignment → Role → Permission → Scope.
3. Least privilege and deny by default.
4. Backend authorization is authoritative; frontend checks are UX only.
5. Scopes prevent IDOR / BOLA vulnerabilities.
"""
from rest_framework import permissions

from apps.authentication.models import RoleAssignment


def get_active_role_assignments(user):
    """Return active RoleAssignment queryset for the given user."""
    if not user or not user.is_authenticated or not user.is_active:
        return RoleAssignment.objects.none()
    return (
        RoleAssignment.objects.filter(user=user, status=RoleAssignment.Status.ACTIVE)
        .select_related('role')
        .prefetch_related('role__role_permissions__permission')
    )


def get_user_role_codenames(user):
    """Return set of active role codenames for the user."""
    if not user or not user.is_authenticated:
        return set()
    return set(
        get_active_role_assignments(user).values_list('role__codename', flat=True)
    )


def get_user_permission_codenames(user):
    """Return set of all permission codenames the user holds via active roles."""
    if not user or not user.is_authenticated or not user.is_active:
        return set()

    if user.is_superuser:
        return {'sysadmin.all'}

    assignments = get_active_role_assignments(user)
    codenames = set()
    for assignment in assignments:
        for rp in assignment.role.role_permissions.all():
            codenames.add(rp.permission.codename)
    return codenames


def user_has_role(user, role_codenames):
    """
    Check if the user has any of the specified roles.
    role_codenames can be a string or iterable of strings.
    """
    if not user or not user.is_authenticated:
        return False
    if isinstance(role_codenames, str):
        role_codenames = [role_codenames]
    user_roles = get_user_role_codenames(user)
    return any(r in user_roles for r in role_codenames)


def user_has_permission(user, permission_codename):
    """Check if the user holds a specific permission codename."""
    if not user or not user.is_authenticated or not user.is_active:
        return False
    if user.is_superuser:
        return True
    user_perms = get_user_permission_codenames(user)
    return 'sysadmin.all' in user_perms or permission_codename in user_perms


def get_user_scopes(user):
    """
    Return dictionary summarizing the user's active scopes:
    - roles: list of active role codenames
    - department_ids: list of UUIDs where user has department-level scope
    - division_ids: list of UUIDs where user has division-level scope
    - is_system_wide: True if SYSADMIN or superuser
    - is_college_wide: True if ADMIN_HEAD
    """
    if not user or not user.is_authenticated:
        return {
            'roles': [],
            'department_ids': [],
            'division_ids': [],
            'is_system_wide': False,
            'is_college_wide': False,
        }

    assignments = get_active_role_assignments(user)
    roles = []
    dept_ids = []
    div_ids = []
    is_system_wide = user.is_superuser
    is_college_wide = False

    for a in assignments:
        code = a.role.codename
        roles.append(code)
        if code == 'SYSADMIN':
            is_system_wide = True
        elif code == 'ADMIN_HEAD':
            is_college_wide = True
        if a.department_id:
            dept_ids.append(a.department_id)
        if a.division_id:
            div_ids.append(a.division_id)

    return {
        'roles': roles,
        'department_ids': dept_ids,
        'division_ids': div_ids,
        'is_system_wide': is_system_wide,
        'is_college_wide': is_college_wide,
    }


class HasRolePermission(permissions.BasePermission):
    """
    Verifies that the user has an active role granting the required permission.

    Usage on Views / ViewSets:
        permission_classes = [HasRolePermission]
        required_permission = 'student.view'

    Or method map:
        permission_map = {
            'GET': 'student.view',
            'POST': 'student.create',
            'PUT': 'student.edit',
            'PATCH': 'student.edit',
            'DELETE': 'student.delete',
        }
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated or not request.user.is_active:
            return False

        if request.user.is_superuser:
            return True

        user_perms = get_user_permission_codenames(request.user)
        if 'sysadmin.all' in user_perms:
            return True

        # Check explicit permission required on the view
        required = getattr(view, 'required_permission', None)
        if required:
            return required in user_perms

        # Check permission map by HTTP method
        perm_map = getattr(view, 'permission_map', None)
        if perm_map and request.method in perm_map:
            needed = perm_map[request.method]
            if isinstance(needed, (list, tuple)):
                return all(p in user_perms for p in needed)
            return needed in user_perms

        # Check multiple required permissions
        required_list = getattr(view, 'required_permissions', None)
        if required_list:
            return all(p in user_perms for p in required_list)

        # If no permission requirement specified on the view, deny by default
        return False


class HasScopeAccess(permissions.BasePermission):
    """
    Object-level permission check to prevent IDOR / BOLA vulnerabilities.

    Verifies that the target object falls within the scope granted to the user:
    - SYSADMIN: system-wide access (all objects)
    - ADMIN_HEAD: college-wide access (all departments/students/faculty)
    - HOD: objects matching user's assigned department_id
    - CLASS_TEACHER: objects matching user's assigned division_id (or department_id)
    - FACULTY: own record or objects associated with teaching assignment
    - STUDENT: own student record only
    """

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated or not request.user.is_active:
            return False

        if request.user.is_superuser:
            return True

        scopes = get_user_scopes(request.user)
        if scopes['is_system_wide']:
            return True

        roles = scopes['roles']

        # ADMIN_HEAD has college-wide access to academic and student data
        if 'ADMIN_HEAD' in roles:
            # Prevent non-sysadmin from modifying sysadmin-specific configuration
            if getattr(obj, 'is_sysadmin_only', False):
                return False
            return True

        # HOD / Class Teacher / Faculty: college-wide READ for Student directory+profiles.
        # Write remains blocked (StudentViewSet is read-only); sensitive reveal still
        # requires 'student.sensitive_reveal'.
        if request.method in permissions.SAFE_METHODS and any(
            r in roles for r in ('HOD', 'CLASS_TEACHER', 'FACULTY')
        ):
            # Student-like object (Student model has enrollment_no / application_id)
            if hasattr(obj, 'enrollment_no') or hasattr(obj, 'application_id'):
                return True
            # Student-related object linked via .student (e.g. enrollment, result)
            student_obj = getattr(obj, 'student', None)
            if student_obj is not None:
                return True

        # HOD check: object must belong to user's assigned department
        if 'HOD' in roles:
            obj_dept_id = (
                getattr(obj, 'department_id', None)
                or getattr(obj, 'department_uuid', None)
            )
            if not obj_dept_id and hasattr(obj, 'enrollments'):
                curr = obj.enrollments.filter(is_current=True).first()
                if curr:
                    obj_dept_id = curr.department_id

            if obj_dept_id and obj_dept_id in scopes['department_ids']:
                return True
            # If object is a Department instance
            if hasattr(obj, 'id') and obj.id in scopes['department_ids']:
                return True

        # CLASS_TEACHER check: object must belong to user's assigned division
        if 'CLASS_TEACHER' in roles:
            obj_div_id = (
                getattr(obj, 'division_id', None)
                or getattr(obj, 'division_uuid', None)
            )
            if obj_div_id and obj_div_id in scopes['division_ids']:
                return True

        # FACULTY check: own record
        if 'FACULTY' in roles:
            if hasattr(obj, 'user_id') and obj.user_id == request.user.id:
                return True
            if hasattr(obj, 'id') and obj.id == request.user.id:
                return True

        # STUDENT check: own record only (strict IDOR protection)
        if 'STUDENT' in roles:
            # Direct User instance
            if hasattr(obj, 'id') and obj.id == request.user.id:
                return True
            # Model with user foreign key / user_id
            if getattr(obj, 'user_id', None) == request.user.id:
                return True
            # Model linked via student relation
            student_obj = getattr(obj, 'student', None)
            if student_obj and getattr(student_obj, 'user_id', None) == request.user.id:
                return True

        return False


class IsSysadmin(permissions.BasePermission):
    """Allows access only to users with the SYSADMIN role or superuser status."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_active
            and (request.user.is_superuser or user_has_role(request.user, 'SYSADMIN'))
        )
