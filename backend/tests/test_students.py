"""
Tests for Phase 3 Student Foundation.

Covers:
- Student profile composition read projection
- Sensitive data masking by default (Aadhaar, Bank)
- IDOR protection (Student A cannot access Student B's profile)
- Scope-filtered directory listing (Student, Class Teacher, HOD, Sysadmin)
- Self-service endpoint /api/v1/students/me/
- Sensitive data reveal authorization and audit logging
"""
import datetime
import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from apps.academic_structure.models import (
    AcademicYear,
    Department,
    Division,
    Program,
    Semester,
)
from apps.audit.models import AuditLog
from apps.authentication.models import Permission, Role, RoleAssignment, RolePermission
from apps.students.models import (
    Student,
    StudentAadhaarDetail,
    StudentAddress,
    StudentBankAccount,
    StudentEnrollment,
    StudentGuardian,
    StudentPersonalDetail,
)

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def academic_setup(db):
    dept_cs = Department.objects.create(name='Computer Science', code='CSE', seat_capacity=60)
    dept_mech = Department.objects.create(name='Mechanical', code='MECH', seat_capacity=60)
    prog_cs = Program.objects.create(department=dept_cs, name='B.Tech CSE', code='BTECH_CSE')
    prog_mech = Program.objects.create(department=dept_mech, name='B.Tech MECH', code='BTECH_MECH')
    year = AcademicYear.objects.create(
        code='2026-27', name='2026-2027', start_date=datetime.date(2026, 7, 1), end_date=datetime.date(2027, 6, 30), is_current=True
    )
    sem1 = Semester.objects.create(number=1, name='Semester 1', year_level=1, term_type=Semester.TermType.ODD)
    div_cs_a = Division.objects.create(department=dept_cs, academic_year=year, semester=sem1, name='A')
    div_mech_a = Division.objects.create(department=dept_mech, academic_year=year, semester=sem1, name='A')

    return {
        'dept_cs': dept_cs,
        'dept_mech': dept_mech,
        'prog_cs': prog_cs,
        'prog_mech': prog_mech,
        'year': year,
        'sem1': sem1,
        'div_cs_a': div_cs_a,
        'div_mech_a': div_mech_a,
    }


@pytest.fixture
def student_data(db, academic_setup):
    # Student A (CSE)
    user_a = User.objects.create_user(username='student_a', password='Password12345!', user_type=User.UserType.STUDENT)
    role_student, _ = Role.objects.get_or_create(codename='STUDENT', defaults={'name': 'Student'})
    RoleAssignment.objects.create(user=user_a, role=role_student, status=RoleAssignment.Status.ACTIVE)

    student_a = Student.objects.create(
        user=user_a,
        enrollment_no='EN26001',
        application_id='APP26001',
        first_name='Aarav',
        last_name='Patil',
    )
    StudentPersonalDetail.objects.create(
        student=student_a,
        date_of_birth=datetime.date(2008, 5, 15),
        gender='MALE',
        student_email='aarav@example.com',
        student_mobile='9876543210',
    )
    StudentGuardian.objects.create(
        student=student_a, relationship='FATHER', name='Ramesh Patil', mobile='9876543211', is_primary=True
    )
    StudentAddress.objects.create(
        student=student_a, address_type='PERMANENT', address_line_1='Shivaji Nagar', district='Kolhapur'
    )
    StudentAadhaarDetail.objects.create(
        student=student_a,
        aadhaar_number_encrypted='encrypted_aadhaar_1234',
        aadhaar_number_masked='XXXX-XXXX-1234',
    )
    StudentBankAccount.objects.create(
        student=student_a,
        account_holder_name='Aarav Patil',
        bank_name='State Bank of India',
        ifsc_code='SBIN0001234',
        account_number_encrypted='encrypted_acc_9876',
        account_number_masked='XXXXXXXX9876',
        is_primary=True,
    )
    StudentEnrollment.objects.create(
        student=student_a,
        academic_year=academic_setup['year'],
        department=academic_setup['dept_cs'],
        program=academic_setup['prog_cs'],
        semester=academic_setup['sem1'],
        division=academic_setup['div_cs_a'],
        roll_number='101',
        is_current=True,
    )

    # Student B (MECH)
    user_b = User.objects.create_user(username='student_b', password='Password12345!', user_type=User.UserType.STUDENT)
    RoleAssignment.objects.create(user=user_b, role=role_student, status=RoleAssignment.Status.ACTIVE)

    student_b = Student.objects.create(
        user=user_b,
        enrollment_no='EN26002',
        application_id='APP26002',
        first_name='Sneha',
        last_name='Kadam',
    )
    StudentEnrollment.objects.create(
        student=student_b,
        academic_year=academic_setup['year'],
        department=academic_setup['dept_mech'],
        program=academic_setup['prog_mech'],
        semester=academic_setup['sem1'],
        division=academic_setup['div_mech_a'],
        roll_number='201',
        is_current=True,
    )

    return {'student_a': student_a, 'student_b': student_b, 'user_a': user_a, 'user_b': user_b}


@pytest.mark.django_db
class TestStudentProfileAndMasking:
    """Tests for student profile projection and sensitive data masking."""

    def test_profile_composition_and_masking(self, api_client, student_data):
        student_a = student_data['student_a']
        api_client.force_authenticate(user=student_data['user_a'])

        res = api_client.get(f'/api/v1/students/{student_a.id}/')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()

        # Identity
        assert data['first_name'] == 'Aarav'
        assert data['last_name'] == 'Patil'
        assert data['enrollment_no'] == 'EN26001'

        # Personal details
        assert data['personal_details']['gender'] == 'MALE'
        assert data['personal_details']['student_email'] == 'aarav@example.com'

        # Masked Aadhaar
        assert data['aadhaar_details']['aadhaar_number_masked'] == 'XXXX-XXXX-1234'
        assert 'encrypted_aadhaar_1234' not in str(data)

        # Masked Bank
        assert len(data['bank_accounts']) == 1
        assert data['bank_accounts'][0]['account_number_masked'] == 'XXXXXXXX9876'
        assert 'encrypted_acc_9876' not in str(data)

        # Current enrollment
        assert data['current_enrollment']['department_code'] == 'CSE'
        assert data['current_enrollment']['roll_number'] == '101'

    def test_student_me_endpoint(self, api_client, student_data):
        api_client.force_authenticate(user=student_data['user_a'])

        res = api_client.get('/api/v1/students/me/')
        assert res.status_code == status.HTTP_200_OK
        assert res.json()['first_name'] == 'Aarav'


@pytest.mark.django_db
class TestStudentScopeEnforcementAndIDOR:
    """Tests for scope isolation and IDOR prevention."""

    def test_student_idor_prevented(self, api_client, student_data):
        student_b = student_data['student_b']
        api_client.force_authenticate(user=student_data['user_a'])

        # Student A trying to access Student B's profile - must be denied (403 or 404 for enumeration protection)
        res = api_client.get(f'/api/v1/students/{student_b.id}/')
        assert res.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)

    def test_student_directory_shows_own_record_only(self, api_client, student_data):
        api_client.force_authenticate(user=student_data['user_a'])

        res = api_client.get('/api/v1/students/')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert len(data['results']) == 1
        assert data['results'][0]['id'] == str(student_data['student_a'].id)

    def test_hod_scoped_directory(self, api_client, academic_setup, student_data):
        # Student directory is college-wide for faculty & HOD to browse all students
        hod_user = User.objects.create_user(username='hod_cse', password='Password12345!')
        role_hod, _ = Role.objects.get_or_create(codename='HOD', defaults={'name': 'Head of Department'})
        RoleAssignment.objects.create(
            user=hod_user,
            role=role_hod,
            department_id=academic_setup['dept_cs'].id,
            status=RoleAssignment.Status.ACTIVE,
        )

        api_client.force_authenticate(user=hod_user)
        # 1. Directory without filter returns all students across college
        res = api_client.get('/api/v1/students/')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        results = data['results']
        assert len(results) == 2

        # 2. Directory with department filter returns department students
        res_filtered = api_client.get(f'/api/v1/students/?department={academic_setup["dept_cs"].code}')
        assert res_filtered.status_code == status.HTTP_200_OK
        filtered_results = res_filtered.json()['results']
        assert len(filtered_results) == 1
        assert filtered_results[0]['id'] == str(student_data['student_a'].id)


@pytest.mark.django_db
class TestStudentSelfUpdate:
    """Students may update their own allowed fields; locked fields and others are protected."""

    def test_student_can_update_own_contact_address_bank(self, api_client, student_data):
        api_client.force_authenticate(user=student_data['user_a'])
        res = api_client.patch('/api/v1/students/me/update/', {
            'personal': {'student_mobile': '9000000001', 'place_of_birth': 'Sangli'},
            'guardians': [{'relationship': 'FATHER', 'name': 'Ramesh Patil', 'mobile': '9000000002'}],
            'address': {'address_line_1': 'New Line Road', 'district': 'Sangli', 'state': 'Maharashtra', 'pincode': '416416'},
            'bank': {'account_holder_name': 'Aarav Patil', 'bank_name': 'Bank of Maharashtra', 'branch_name': 'Sangli', 'ifsc_code': 'MAHB0001234', 'account_number': '123456789012'},
        }, format='json')
        assert res.status_code == status.HTTP_200_OK
        student = Student.objects.get(id=student_data['student_a'].id)
        assert student.personal_details.student_mobile == '9000000001'
        assert student.addresses.get(address_type='PERMANENT').district == 'Sangli'
        assert student.bank_accounts.get(is_primary=True).bank_name == 'Bank of Maharashtra'
        assert student.bank_accounts.get(is_primary=True).account_number_masked == 'XXXXXXXX9012'

    def test_locked_identity_fields_are_ignored(self, api_client, student_data):
        api_client.force_authenticate(user=student_data['user_a'])
        res = api_client.patch('/api/v1/students/me/update/', {
            'enrollment_no': 'HACKED001',
            'application_id': 'HACKEDAPP',
            'first_name': 'Hacker',
            'personal': {'student_mobile': '9000000003'},
        }, format='json')
        assert res.status_code == status.HTTP_200_OK
        student = Student.objects.get(id=student_data['student_a'].id)
        assert student.enrollment_no == 'EN26001'
        assert student.application_id == 'APP26001'
        assert student.first_name == 'Aarav'
        assert student.personal_details.student_mobile == '9000000003'

    def test_invalid_data_rejected(self, api_client, student_data):
        api_client.force_authenticate(user=student_data['user_a'])
        res = api_client.patch('/api/v1/students/me/update/', {
            'bank': {'ifsc_code': 'BADCODE'},
        }, format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST

    def test_teacher_cannot_use_self_update(self, api_client, academic_setup):
        hod_user = User.objects.create_user(username='hod_no_student', password='Password12345!')
        role_hod, _ = Role.objects.get_or_create(codename='HOD', defaults={'name': 'Head of Department'})
        RoleAssignment.objects.create(
            user=hod_user, role=role_hod,
            department_id=academic_setup['dept_cs'].id, status=RoleAssignment.Status.ACTIVE,
        )
        api_client.force_authenticate(user=hod_user)
        res = api_client.patch('/api/v1/students/me/update/', {
            'personal': {'student_mobile': '9000000004'},
        }, format='json')
        assert res.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestEligibleRequiresClass:
    """Common rule: no division + class teacher → no fee/verification eligibility (all years incl. FY)."""

    def _fy_student(self, academic_setup, username, division):
        user = User.objects.create_user(username=username, password='Password12345!')
        student = Student.objects.create(
            user=user, enrollment_no=f'EN-{username}', application_id=f'APP-{username}',
            first_name='Test', last_name='Fresher',
            admission_year=academic_setup['year'], admission_type='FY',
        )
        StudentEnrollment.objects.create(
            student=student, academic_year=academic_setup['year'],
            department=academic_setup['dept_cs'], program=academic_setup['prog_cs'],
            semester=academic_setup['sem1'], division=division, is_current=True,
        )
        return student

    def _hod_client(self, api_client, academic_setup):
        hod_user = User.objects.create_user(username='hod_elig', password='Password12345!')
        role_hod, _ = Role.objects.get_or_create(codename='HOD', defaults={'name': 'Head of Department'})
        RoleAssignment.objects.create(
            user=hod_user, role=role_hod,
            department_id=academic_setup['dept_cs'].id, status=RoleAssignment.Status.ACTIVE,
        )
        api_client.force_authenticate(user=hod_user)
        return api_client

    def _eligible_ids(self, api_client):
        res = api_client.get('/api/v1/students/?eligible_only=true')
        assert res.status_code == status.HTTP_200_OK
        return {r['id'] for r in res.json()['results']}

    def test_fresher_without_teacher_excluded(self, api_client, academic_setup):
        student = self._fy_student(academic_setup, 'fresher_no_teacher', academic_setup['div_cs_a'])
        api_client = self._hod_client(api_client, academic_setup)
        assert str(student.id) not in self._eligible_ids(api_client)
        res = api_client.get('/api/v1/students/')
        row = next(r for r in res.json()['results'] if r['id'] == str(student.id))
        assert row['is_eligible'] is False

    def test_fresher_with_teacher_included(self, api_client, academic_setup):
        teacher = User.objects.create_user(username='teacher_ct', password='Password12345!')
        academic_setup['div_cs_a'].class_teacher = teacher
        academic_setup['div_cs_a'].save(update_fields=['class_teacher'])
        student = self._fy_student(academic_setup, 'fresher_with_teacher', academic_setup['div_cs_a'])
        api_client = self._hod_client(api_client, academic_setup)
        assert str(student.id) in self._eligible_ids(api_client)
        res = api_client.get('/api/v1/students/')
        row = next(r for r in res.json()['results'] if r['id'] == str(student.id))
        assert row['is_eligible'] is True

    def test_fresher_without_division_excluded(self, api_client, academic_setup):
        student = self._fy_student(academic_setup, 'fresher_no_div', None)
        api_client = self._hod_client(api_client, academic_setup)
        assert str(student.id) not in self._eligible_ids(api_client)


@pytest.mark.django_db
class TestSensitiveDataReveal:
    """Tests for sensitive data reveal endpoint and audit logging."""

    def test_reveal_denied_without_permission(self, api_client, student_data):
        student_a = student_data['student_a']
        api_client.force_authenticate(user=student_data['user_a'])

        # Student does not have 'student.sensitive_reveal' permission
        res = api_client.post(f'/api/v1/students/{student_a.id}/reveal/')
        assert res.status_code == status.HTTP_403_FORBIDDEN

    def test_reveal_allowed_with_permission_and_audited(self, api_client, student_data):
        admin_user = User.objects.create_superuser(username='admin_reveal', password='Password12345!')
        perm, _ = Permission.objects.get_or_create(codename='student.sensitive_reveal', defaults={'module': 'student', 'name': 'Reveal'})
        role, _ = Role.objects.get_or_create(codename='ADMIN_HEAD', defaults={'name': 'Admin Head'})
        RolePermission.objects.get_or_create(role=role, permission=perm)
        RoleAssignment.objects.create(user=admin_user, role=role, status=RoleAssignment.Status.ACTIVE)

        student_a = student_data['student_a']
        api_client.force_authenticate(user=admin_user)

        res = api_client.post(
            f'/api/v1/students/{student_a.id}/reveal/',
            {'reason': 'Admission verification by Registrar'},
            format='json',
        )
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert 'aadhaar_number' in data
        assert 'bank_account_number' in data

        # Verify AuditLog created
        audit = AuditLog.objects.filter(
            actor=admin_user,
            action=AuditLog.Action.SENSITIVE_REVEAL,
            target_id=str(student_a.id),
        ).first()
        assert audit is not None
        assert 'Admission verification' in audit.reason
