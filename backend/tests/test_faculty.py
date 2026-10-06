"""
Tests for Faculty domain, profile projection, sensitive data masking, and scope enforcement.
"""
import datetime
import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.academic_structure.models import AcademicYear, Department, Division, Program, Semester
from apps.audit.models import AuditLog
from apps.authentication.models import Permission, Role, RoleAssignment, RolePermission, User
from apps.faculty.models import (
    Faculty,
    FacultyAddress,
    FacultyBankAccount,
    FacultyDocument,
    FacultyExperience,
    FacultyGuidance,
    FacultyPersonalDetail,
    FacultyPublication,
    FacultyQualification,
    TeachingAssignment,
)


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def academic_setup():
    year = AcademicYear.objects.create(
        code='2026-27', name='Academic Year 2026-2027',
        start_date=datetime.date(2026, 7, 1), end_date=datetime.date(2027, 6, 30),
        is_current=True
    )
    dept_cs = Department.objects.create(name='Computer Science and Engineering', code='CSE')
    dept_ee = Department.objects.create(name='Electrical Engineering', code='EE')
    sem1 = Semester.objects.create(number=1, name='Semester 1', year_level=1, term_type='ODD')
    return {'year': year, 'dept_cs': dept_cs, 'dept_ee': dept_ee, 'sem1': sem1}


@pytest.fixture
def faculty_data(academic_setup):
    role_fac, _ = Role.objects.get_or_create(codename='FACULTY', defaults={'name': 'Faculty'})
    role_admin, _ = Role.objects.get_or_create(codename='SYSADMIN', defaults={'name': 'System Administrator'})

    # Assign sensitive reveal permission to SYSADMIN
    perm_reveal, _ = Permission.objects.get_or_create(
        codename='faculty.sensitive_reveal',
        defaults={'name': 'Reveal Sensitive Faculty Data', 'module': 'faculty'}
    )
    RolePermission.objects.get_or_create(role=role_admin, permission=perm_reveal)

    # Faculty User
    user_fac = User.objects.create(username='prof_suresh', email='suresh@gceok.ac.in', user_type=User.UserType.FACULTY)
    user_fac.set_password('TestPass@123')
    user_fac.save()
    RoleAssignment.objects.create(user=user_fac, role=role_fac, status=RoleAssignment.Status.ACTIVE)

    # Admin User
    user_admin = User.objects.create(username='admin_user', email='admin@gceok.ac.in', user_type=User.UserType.SYSADMIN)
    user_admin.set_password('TestPass@123')
    user_admin.save()
    RoleAssignment.objects.create(user=user_admin, role=role_admin, status=RoleAssignment.Status.ACTIVE)

    faculty = Faculty.objects.create(
        user=user_fac,
        employee_code='EMP001',
        first_name='Suresh',
        last_name='Sharma',
        display_name='Dr. Suresh Sharma',
        department=academic_setup['dept_cs'],
        designation=Faculty.Designation.PROFESSOR,
        date_of_joining=datetime.date(2015, 6, 1),
        official_email='suresh@gceok.ac.in',
    )
    FacultyPersonalDetail.objects.create(
        faculty=faculty,
        date_of_birth=datetime.date(1980, 5, 20),
        gender=FacultyPersonalDetail.Gender.MALE,
    )
    FacultyAddress.objects.create(
        faculty=faculty,
        address_type=FacultyAddress.AddressType.PERMANENT,
        address_line_1='Campus Quarters',
        pincode='416012',
    )
    FacultyQualification.objects.create(
        faculty=faculty,
        qualification_level=FacultyQualification.Level.PHD,
        degree_name='Ph.D. Computer Science',
        institution_university='IIT Bombay',
        passing_year=2010,
        is_highest=True,
    )
    FacultyExperience.objects.create(
        faculty=faculty,
        experience_type=FacultyExperience.ExpType.TEACHING,
        organization='GCOEK',
        designation='Professor',
        start_date=datetime.date(2015, 6, 1),
        experience_years=11.0,
    )
    FacultyPublication.objects.create(
        faculty=faculty,
        title='Edge AI Architectures',
        journal_or_conference='IEEE Access',
        publication_year=2024,
    )
    FacultyBankAccount.objects.create(
        faculty=faculty,
        account_holder_name='Dr. Suresh Sharma',
        bank_name='State Bank of India',
        ifsc_code='SBIN0001234',
        account_number_encrypted='encrypted_fac_acc_123',
        account_number_masked='XXXXXXXX4412',
        is_primary=True,
    )
    TeachingAssignment.objects.create(
        faculty=faculty,
        academic_year=academic_setup['year'],
        department=academic_setup['dept_cs'],
        semester=academic_setup['sem1'],
        subject_name='Data Structures',
        subject_code='CS201',
    )

    return {
        'faculty': faculty,
        'user_fac': user_fac,
        'user_admin': user_admin,
    }


@pytest.mark.django_db
class TestFacultyProfileAndMasking:
    """Tests for faculty profile composition and sensitive masking."""

    def test_faculty_profile_composition(self, api_client, faculty_data):
        faculty = faculty_data['faculty']
        api_client.force_authenticate(user=faculty_data['user_fac'])

        res = api_client.get(f'/api/v1/faculty/{faculty.id}/')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()

        assert data['employee_code'] == 'EMP001'
        assert data['display_name'] == 'Dr. Suresh Sharma'
        assert data['department_code'] == 'CSE'
        assert len(data['qualifications']) == 1
        assert data['qualifications'][0]['degree_name'] == 'Ph.D. Computer Science'
        assert len(data['experiences']) == 1
        assert len(data['publications']) == 1
        assert len(data['teaching_assignments']) == 1
        assert data['teaching_assignments'][0]['subject_code'] == 'CS201'

        # Sensitive bank data must be masked
        assert data['bank_accounts'][0]['account_number_masked'] == 'XXXXXXXX4412'
        assert 'encrypted_fac_acc_123' not in str(data)

    def test_faculty_me_endpoint(self, api_client, faculty_data):
        api_client.force_authenticate(user=faculty_data['user_fac'])

        res = api_client.get('/api/v1/faculty/me/')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data['employee_code'] == 'EMP001'


@pytest.mark.django_db
class TestFacultySensitiveReveal:
    """Tests for faculty sensitive data unmasking and audit logging."""

    def test_reveal_denied_without_permission(self, api_client, faculty_data):
        faculty = faculty_data['faculty']
        api_client.force_authenticate(user=faculty_data['user_fac'])

        res = api_client.post(f'/api/v1/faculty/{faculty.id}/reveal/', {'reason': 'Checking my account'})
        assert res.status_code == status.HTTP_403_FORBIDDEN

    def test_reveal_allowed_for_sysadmin_and_audited(self, api_client, faculty_data):
        faculty = faculty_data['faculty']
        api_client.force_authenticate(user=faculty_data['user_admin'])

        res = api_client.post(
            f'/api/v1/faculty/{faculty.id}/reveal/',
            {'reason': 'Salary disbursement audit verification'}
        )
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert 'bank_account_number' in data

        # Check AuditLog entry
        audit_entry = AuditLog.objects.filter(
            target_type='Faculty',
            target_id=str(faculty.id),
            action=AuditLog.Action.SENSITIVE_REVEAL,
        ).first()
        assert audit_entry is not None
        assert audit_entry.reason == 'Salary disbursement audit verification'


@pytest.mark.django_db
class TestSubjectTeacherRules:
    """One subject per teacher per class; one teacher per slot; history kept."""

    def _setup(self):
        import datetime
        from apps.academic_structure.models import AcademicYear, Department, Division, Program, Semester
        year = AcademicYear.objects.create(
            code='2030-31', name='AY 2030-31', start_date=datetime.date(2030, 7, 1),
            end_date=datetime.date(2031, 6, 30), is_current=False)
        dept = Department.objects.create(name='Rule Dept', code='RUL')
        prog = Program.objects.create(department=dept, name='B.Tech R', code='BTECH_R')
        sem = Semester.objects.create(number=21, name='S21', year_level=1, term_type='ODD')
        div = Division.objects.create(department=dept, academic_year=year, semester=sem, name='A')
        hod = User.objects.create(username='hod_rul', email='h@r.in', user_type='FACULTY')
        hod.set_password('TestPass12345!'); hod.save()
        role_hod, _ = Role.objects.get_or_create(codename='HOD', defaults={'name': 'HOD'})
        RoleAssignment.objects.create(user=hod, role=role_hod, department_id=dept.id, status='ACTIVE')
        t1 = User.objects.create(username='t1_rul', email='t1@r.in', user_type='FACULTY')
        t1.set_password('TestPass12345!'); t1.save()
        t2 = User.objects.create(username='t2_rul', email='t2@r.in', user_type='FACULTY')
        t2.set_password('TestPass12345!'); t2.save()
        f1 = Faculty.objects.create(
            user=t1, employee_code='RUL_001', first_name='One', last_name='T',
            department=dept, date_of_joining=datetime.date(2020, 1, 1),
            official_email='t1@gceok.ac.in')
        f2 = Faculty.objects.create(
            user=t2, employee_code='RUL_002', first_name='Two', last_name='T',
            department=dept, date_of_joining=datetime.date(2020, 1, 1),
            official_email='t2@gceok.ac.in')
        return hod, div, f1, f2

    def _assign(self, api_client, hod, div, fac, code, role='PRIMARY_FACULTY'):
        api_client.force_authenticate(user=hod)
        return api_client.post('/api/v1/faculty/assignments/', {
            'faculty': str(fac.id), 'division': str(div.id),
            'subject_name': 'Subject %s' % code, 'subject_code': code, 'role': role,
        }, format='json')

    def test_one_subject_per_teacher_per_class(self, api_client):
        hod, div, f1, f2 = self._setup()
        assert self._assign(api_client, hod, div, f1, 'CS101').status_code == status.HTTP_201_CREATED
        res = self._assign(api_client, hod, div, f1, 'CS102')
        assert res.status_code == status.HTTP_400_BAD_REQUEST

    def test_one_teacher_per_slot_and_replace_keeps_history(self, api_client):
        from apps.faculty.models import TeachingAssignment
        hod, div, f1, f2 = self._setup()
        assert self._assign(api_client, hod, div, f1, 'CS101').status_code == status.HTTP_201_CREATED
        res = self._assign(api_client, hod, div, f2, 'CS101')
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        # deactivate then assign = replace with history
        old = TeachingAssignment.objects.get(division=div, subject_code='CS101', is_active=True)
        api_client.force_authenticate(user=hod)
        d = api_client.post(f'/api/v1/faculty/assignments/{old.id}/deactivate/', {'reason': 'swap'}, format='json')
        assert d.status_code == status.HTTP_200_OK
        assert self._assign(api_client, hod, div, f2, 'CS101').status_code == status.HTTP_201_CREATED
        assert TeachingAssignment.objects.filter(division=div, subject_code='CS101').count() == 2
        assert TeachingAssignment.objects.filter(division=div, subject_code='CS101', is_active=True).count() == 1

    def test_lab_theory_split_allowed(self, api_client):
        hod, div, f1, f2 = self._setup()
        assert self._assign(api_client, hod, div, f1, 'CS101', 'PRIMARY_FACULTY').status_code == status.HTTP_201_CREATED
        assert self._assign(api_client, hod, div, f2, 'CS101', 'LAB_INSTRUCTOR').status_code == status.HTTP_201_CREATED
