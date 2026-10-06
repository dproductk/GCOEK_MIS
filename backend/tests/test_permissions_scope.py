"""
Tests for Phase 1 RBAC and Scope Permission Classes.

Covers:
- HasRolePermission (view-level permission enforcement)
- HasScopeAccess (object-level scope enforcement, IDOR / BOLA prevention)
- IsSysadmin permission class
"""
import uuid
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from apps.authentication.models import Permission, Role, RoleAssignment, RolePermission
from apps.authentication.permissions import (
    HasRolePermission,
    HasScopeAccess,
    IsSysadmin,
    get_user_permission_codenames,
    get_user_scopes,
)

User = get_user_model()


class MockTargetObject:
    """Mock domain object for testing object-level scope checks."""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class DummyView(APIView):
    permission_classes = [HasRolePermission]
    required_permission = 'student.view'


@pytest.fixture
def rf():
    return APIRequestFactory()


@pytest.fixture
def roles_and_permissions(db):
    perm_view, _ = Permission.objects.get_or_create(
        codename='student.view',
        defaults={'name': 'View student', 'module': 'student'},
    )
    perm_edit, _ = Permission.objects.get_or_create(
        codename='student.edit',
        defaults={'name': 'Edit student', 'module': 'student'},
    )

    role_student, _ = Role.objects.get_or_create(
        codename='STUDENT', defaults={'name': 'Student'}
    )
    role_hod, _ = Role.objects.get_or_create(
        codename='HOD', defaults={'name': 'Head of Department'}
    )
    role_ct, _ = Role.objects.get_or_create(
        codename='CLASS_TEACHER', defaults={'name': 'Class Teacher'}
    )
    role_admin_head, _ = Role.objects.get_or_create(
        codename='ADMIN_HEAD', defaults={'name': 'Admin Head'}
    )
    role_sysadmin, _ = Role.objects.get_or_create(
        codename='SYSADMIN', defaults={'name': 'Sysadmin'}
    )

    RolePermission.objects.get_or_create(role=role_student, permission=perm_view)
    RolePermission.objects.get_or_create(role=role_hod, permission=perm_view)
    RolePermission.objects.get_or_create(role=role_hod, permission=perm_edit)
    RolePermission.objects.get_or_create(role=role_ct, permission=perm_view)
    RolePermission.objects.get_or_create(role=role_admin_head, permission=perm_view)
    RolePermission.objects.get_or_create(role=role_admin_head, permission=perm_edit)

    return {
        'perm_view': perm_view,
        'perm_edit': perm_edit,
        'role_student': role_student,
        'role_hod': role_hod,
        'role_ct': role_ct,
        'role_admin_head': role_admin_head,
        'role_sysadmin': role_sysadmin,
    }


@pytest.mark.django_db
class TestHasRolePermission:
    """Tests for HasRolePermission at the view level."""

    def test_authenticated_user_with_permission_granted(self, rf, roles_and_permissions):
        user = User.objects.create_user(username='u1', password='Password12345!')
        RoleAssignment.objects.create(
            user=user,
            role=roles_and_permissions['role_student'],
            status=RoleAssignment.Status.ACTIVE,
        )

        request = rf.get('/dummy/')
        request.user = user

        perm = HasRolePermission()
        view = DummyView()
        assert perm.has_permission(request, view) is True

    def test_user_without_permission_denied(self, rf):
        role_no_perm = Role.objects.create(codename='LIMITED', name='Limited')
        user = User.objects.create_user(username='u2', password='Password12345!')
        RoleAssignment.objects.create(
            user=user,
            role=role_no_perm,
            status=RoleAssignment.Status.ACTIVE,
        )

        request = rf.get('/dummy/')
        request.user = user

        perm = HasRolePermission()
        view = DummyView()
        assert perm.has_permission(request, view) is False

    def test_superuser_always_granted(self, rf):
        superuser = User.objects.create_superuser(
            username='super', password='Password12345!'
        )
        request = rf.get('/dummy/')
        request.user = superuser

        perm = HasRolePermission()
        view = DummyView()
        assert perm.has_permission(request, view) is True


@pytest.mark.django_db
class TestHasScopeAccess:
    """Tests for HasScopeAccess at the object level (IDOR protection)."""

    def test_student_can_only_access_own_record(self, rf, roles_and_permissions):
        student_a = User.objects.create_user(username='student_a', password='Password12345!')
        student_b = User.objects.create_user(username='student_b', password='Password12345!')

        RoleAssignment.objects.create(
            user=student_a,
            role=roles_and_permissions['role_student'],
            status=RoleAssignment.Status.ACTIVE,
        )

        scope_checker = HasScopeAccess()
        view = DummyView()

        # Target object belonging to student_a
        obj_a = MockTargetObject(user_id=student_a.id)
        # Target object belonging to student_b
        obj_b = MockTargetObject(user_id=student_b.id)

        req = rf.get('/student/')
        req.user = student_a

        # Allowed for own record
        assert scope_checker.has_object_permission(req, view, obj_a) is True
        # Denied for another student's record (IDOR prevented!)
        assert scope_checker.has_object_permission(req, view, obj_b) is False

    def test_hod_scoped_to_assigned_department(self, rf, roles_and_permissions):
        dept_cs_id = uuid.uuid4()
        dept_mech_id = uuid.uuid4()

        hod = User.objects.create_user(username='hod_cs', password='Password12345!')
        RoleAssignment.objects.create(
            user=hod,
            role=roles_and_permissions['role_hod'],
            department_id=dept_cs_id,
            status=RoleAssignment.Status.ACTIVE,
        )

        scope_checker = HasScopeAccess()
        view = DummyView()

        obj_cs = MockTargetObject(department_id=dept_cs_id)
        obj_mech = MockTargetObject(department_id=dept_mech_id)

        req = rf.get('/department/')
        req.user = hod

        # Allowed within own department
        assert scope_checker.has_object_permission(req, view, obj_cs) is True
        # Denied outside assigned department
        assert scope_checker.has_object_permission(req, view, obj_mech) is False

    def test_class_teacher_scoped_to_assigned_division(self, rf, roles_and_permissions):
        div_a_id = uuid.uuid4()
        div_b_id = uuid.uuid4()

        ct = User.objects.create_user(username='ct_div_a', password='Password12345!')
        RoleAssignment.objects.create(
            user=ct,
            role=roles_and_permissions['role_ct'],
            division_id=div_a_id,
            status=RoleAssignment.Status.ACTIVE,
        )

        scope_checker = HasScopeAccess()
        view = DummyView()

        obj_div_a = MockTargetObject(division_id=div_a_id)
        obj_div_b = MockTargetObject(division_id=div_b_id)

        req = rf.get('/division/')
        req.user = ct

        assert scope_checker.has_object_permission(req, view, obj_div_a) is True
        assert scope_checker.has_object_permission(req, view, obj_div_b) is False

    def test_admin_head_has_college_wide_access_except_sysadmin_only(self, rf, roles_and_permissions):
        admin_head = User.objects.create_user(username='admin_head', password='Password12345!')
        RoleAssignment.objects.create(
            user=admin_head,
            role=roles_and_permissions['role_admin_head'],
            status=RoleAssignment.Status.ACTIVE,
        )

        scope_checker = HasScopeAccess()
        view = DummyView()

        student_obj = MockTargetObject(user_id=uuid.uuid4(), department_id=uuid.uuid4())
        sysadmin_config_obj = MockTargetObject(is_sysadmin_only=True)

        req = rf.get('/college/')
        req.user = admin_head

        # College-wide access to student/department records
        assert scope_checker.has_object_permission(req, view, student_obj) is True
        # Denied for sysadmin-only objects
        assert scope_checker.has_object_permission(req, view, sysadmin_config_obj) is False
