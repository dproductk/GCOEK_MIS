"""
Tests for Phase 2 Academic Structure domain.

Covers:
- Department CRUD for Sysadmin
- Role-based access control (read-only for students/faculty, write restricted to Sysadmin)
- Unauthenticated access rejection
- AcademicYear single-active invariant and set_current action
- AcademicContext single-active invariant and current endpoint
- Division querying and unique constraints
- AuditLog generation for academic structure mutations
"""
import datetime
import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from apps.academic_structure.models import (
    AcademicContext,
    AcademicYear,
    Department,
    Division,
    Program,
    Semester,
)
from apps.audit.models import AuditLog
from apps.authentication.models import Role, RoleAssignment
from apps.audit.models import AuditLog

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def sysadmin_user(db):
    user = User.objects.create_superuser(
        username='sysadmin_test',
        email='sysadmin@gcoek.ac.in',
        password='Password12345!',
    )
    role, _ = Role.objects.get_or_create(
        codename='SYSADMIN', defaults={'name': 'Sysadmin'}
    )
    RoleAssignment.objects.create(
        user=user, role=role, status=RoleAssignment.Status.ACTIVE
    )
    return user


@pytest.fixture
def student_user(db):
    user = User.objects.create_user(
        username='student_test',
        email='student@gcoek.ac.in',
        password='Password12345!',
        user_type=User.UserType.STUDENT,
    )
    role, _ = Role.objects.get_or_create(
        codename='STUDENT', defaults={'name': 'Student'}
    )
    RoleAssignment.objects.create(
        user=user, role=role, status=RoleAssignment.Status.ACTIVE
    )
    return user


@pytest.fixture
def academic_seed(db):
    dept = Department.objects.create(
        name='Civil Engineering',
        code='CIVIL',
        choice_code='627019110',
        seat_capacity=60,
    )
    year = AcademicYear.objects.create(
        code='2026-27',
        name='Academic Year 2026-2027',
        start_date=datetime.date(2026, 7, 1),
        end_date=datetime.date(2027, 6, 30),
        is_current=True,
    )
    context = AcademicContext.objects.create(
        academic_year=year,
        term=AcademicContext.Term.ODD,
        is_active=True,
    )
    sem1 = Semester.objects.create(
        number=1,
        name='Semester 1',
        year_level=1,
        term_type=Semester.TermType.ODD,
    )
    div_a = Division.objects.create(
        department=dept,
        academic_year=year,
        semester=sem1,
        name='A',
        seat_capacity=60,
    )
    return {
        'dept': dept,
        'year': year,
        'context': context,
        'sem1': sem1,
        'div_a': div_a,
    }


@pytest.mark.django_db
class TestDivisionDeleteEmptyOnly:
    """HOD/sysadmin can delete empty divisions; populated ones are blocked."""

    def _hod_for(self, dept):
        hod = User.objects.create_user(
            username=f"hod_{dept.code.lower()}", password='Password12345!',
            user_type=User.UserType.FACULTY,
        )
        role, _ = Role.objects.get_or_create(codename='HOD', defaults={'name': 'HOD'})
        RoleAssignment.objects.create(
            user=hod, role=role, department_id=dept.id,
            status=RoleAssignment.Status.ACTIVE)
        return hod

    def test_sysadmin_can_delete_empty_division(self, api_client, sysadmin_user, academic_seed):
        from apps.students.models import Student
        div = academic_seed['div_a']
        api_client.force_authenticate(user=sysadmin_user)
        assert api_client.get('/api/v1/academic/divisions/').json()['results'][0]['enrolled_count'] == 0
        res = api_client.delete(f"/api/v1/academic/divisions/{div.id}/")
        assert res.status_code == status.HTTP_204_NO_CONTENT
        assert Student.objects.count() == 0  # nothing else touched

    def test_delete_blocked_when_students_assigned(self, api_client, sysadmin_user, academic_seed):
        from apps.students.models import Student, StudentEnrollment
        seed = academic_seed
        api_client.force_authenticate(user=sysadmin_user)
        student = Student.objects.create(first_name='A', last_name='B', application_id='EN26000099')
        prog = Program.objects.create(department=seed['dept'], name='B.Tech Civ', code='BTECH_CIV')
        StudentEnrollment.objects.create(
            student=student, academic_year=seed['year'], department=seed['dept'],
            program=prog, semester=seed['sem1'], division=seed['div_a'],
            status='ACTIVE', is_current=True)
        res = api_client.delete(f"/api/v1/academic/divisions/{seed['div_a'].id}/")
        assert res.status_code == status.HTTP_400_BAD_REQUEST

    def test_hod_can_delete_own_empty_division(self, api_client, academic_seed):
        hod = self._hod_for(academic_seed['dept'])
        api_client.force_authenticate(user=hod)
        res = api_client.delete(f"/api/v1/academic/divisions/{academic_seed['div_a'].id}/")
        assert res.status_code == status.HTTP_204_NO_CONTENT

    def test_student_cannot_delete_division(self, api_client, student_user, academic_seed):
        api_client.force_authenticate(user=student_user)
        res = api_client.delete(f"/api/v1/academic/divisions/{academic_seed['div_a'].id}/")
        assert res.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)


@pytest.mark.django_db
class TestDepartmentAccessAndCRUD:
    """Tests for /api/v1/academic/departments/"""

    def test_unauthenticated_request_denied(self, api_client):
        response = api_client.get('/api/v1/academic/departments/')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_student_read_allowed_write_denied(self, api_client, student_user, academic_seed):
        api_client.force_authenticate(user=student_user)

        # Read allowed
        get_res = api_client.get('/api/v1/academic/departments/')
        assert get_res.status_code == status.HTTP_200_OK
        data = get_res.json()
        assert len(data['results']) >= 1

        # Write denied (403 Forbidden)
        post_res = api_client.post(
            '/api/v1/academic/departments/',
            {'name': 'Chemical Engineering', 'code': 'CHEM', 'seat_capacity': 60},
            format='json',
        )
        assert post_res.status_code == status.HTTP_403_FORBIDDEN

    def test_sysadmin_crud_workflow(self, api_client, sysadmin_user):
        api_client.force_authenticate(user=sysadmin_user)

        # 1. Create
        create_res = api_client.post(
            '/api/v1/academic/departments/',
            {
                'name': 'Robotics Engineering',
                'code': 'ROBO',
                'choice_code': '627099999',
                'seat_capacity': 60,
                'description': 'New department for robotics.',
            },
            format='json',
        )
        assert create_res.status_code == status.HTTP_201_CREATED
        dept_id = create_res.json()['id']

        # AuditLog verified
        assert AuditLog.objects.filter(
            actor=sysadmin_user,
            action=AuditLog.Action.CREATE,
            target_type='Department',
            target_id=dept_id,
        ).exists()

        # 2. Retrieve
        retrieve_res = api_client.get(f'/api/v1/academic/departments/{dept_id}/')
        assert retrieve_res.status_code == status.HTTP_200_OK
        assert retrieve_res.json()['code'] == 'ROBO'

        # 3. Update
        update_res = api_client.patch(
            f'/api/v1/academic/departments/{dept_id}/',
            {'seat_capacity': 120},
            format='json',
        )
        assert update_res.status_code == status.HTTP_200_OK
        assert update_res.json()['seat_capacity'] == 120

        # 4. Delete
        delete_res = api_client.delete(f'/api/v1/academic/departments/{dept_id}/')
        assert delete_res.status_code == status.HTTP_204_NO_CONTENT
        assert not Department.objects.filter(id=dept_id).exists()


@pytest.mark.django_db
class TestAcademicYearAndContext:
    """Tests for AcademicYear and AcademicContext single-active rules."""

    def test_academic_year_single_current_invariant(self, api_client, sysadmin_user, academic_seed):
        api_client.force_authenticate(user=sysadmin_user)

        # Create new year 2027-28 and mark it current
        res = api_client.post(
            '/api/v1/academic/years/',
            {
                'code': '2027-28',
                'name': 'Academic Year 2027-2028',
                'start_date': '2027-07-01',
                'end_date': '2028-06-30',
                'is_current': True,
            },
            format='json',
        )
        assert res.status_code == status.HTTP_201_CREATED

        # Old year 2026-27 must no longer be current
        old_year = academic_seed['year']
        old_year.refresh_from_db()
        assert old_year.is_current is False

        # Set 2026-27 back as current via custom action
        set_res = api_client.post(f'/api/v1/academic/years/{old_year.id}/set_current/')
        assert set_res.status_code == status.HTTP_200_OK

        old_year.refresh_from_db()
        assert old_year.is_current is True

    def test_current_academic_context_endpoint(self, api_client, student_user, academic_seed):
        api_client.force_authenticate(user=student_user)

        res = api_client.get('/api/v1/academic/contexts/current/')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data['term'] == 'ODD'
        assert data['academic_year_code'] == '2026-27'
        assert data['is_active'] is True


@pytest.mark.django_db
class TestDivisionsAndConstraints:
    """Tests for Division model constraints and querying."""

    def test_division_unique_constraint(self, academic_seed):
        # Creating duplicate division with same dept, year, sem, name should fail
        with pytest.raises(Exception):
            Division.objects.create(
                department=academic_seed['dept'],
                academic_year=academic_seed['year'],
                semester=academic_seed['sem1'],
                name='A',
            )

    def test_division_filtering(self, api_client, student_user, academic_seed):
        api_client.force_authenticate(user=student_user)

        dept_id = str(academic_seed['dept'].id)
        res = api_client.get(f'/api/v1/academic/divisions/?department_id={dept_id}')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert len(data['results']) == 1
        assert data['results'][0]['name'] == 'A'


class TestPlacementFormula:
    """Admission formula unit tests (no DB): elapsed math, DSE base, graduation."""

    def test_fy_fresher(self):
        from apps.students.placement import suggest_semester
        assert suggest_semester(2026, 'FY', 2026, 'ODD') == (1, 1, 'STUDYING')
        assert suggest_semester(2026, 'FY', 2026, 'EVEN') == (2, 1, 'STUDYING')

    def test_dse_example_from_spec(self):
        from apps.students.placement import suggest_semester
        assert suggest_semester(2025, 'DSE', 2026, 'ODD') == (5, 3, 'STUDYING')
        assert suggest_semester(2026, 'DSE', 2026, 'ODD') == (3, 2, 'STUDYING')

    def test_graduated_and_future(self):
        import pytest
        from apps.students.placement import FutureAdmissionError, suggest_semester
        assert suggest_semester(2022, 'FY', 2026, 'ODD')[2] == 'GRADUATED'
        try:
            suggest_semester(2027, 'FY', 2026, 'ODD')
            assert False, 'expected FutureAdmissionError'
        except FutureAdmissionError:
            pass


@pytest.mark.django_db
class TestBulkFinalize:
    """HOD bulk finalize: placement_confirmed, repeat rule, cross-dept skip."""

    def _hod(self, dept):
        hod = User.objects.create_user(
            username=f"hod bulk {dept.code}".replace(' ', '_').lower(),
            password='Password12345!', user_type=User.UserType.FACULTY)
        role, _ = Role.objects.get_or_create(codename='HOD', defaults={'name': 'HOD'})
        RoleAssignment.objects.create(
            user=hod, role=role, department_id=dept.id, status=RoleAssignment.Status.ACTIVE)
        return hod

    def test_bulk_move_confirms_and_counts_repeat(self, api_client, academic_seed):
        from apps.students.models import Student, StudentEnrollment
        seed = academic_seed
        hod = self._hod(seed['dept'])
        div_b = Division.objects.create(
            department=seed['dept'], academic_year=seed['year'],
            semester=seed['sem1'], name='B')
        prog = Program.objects.create(department=seed['dept'], name='P', code='PX')
        s1 = Student.objects.create(first_name='A', last_name='B', application_id='ENX1')
        StudentEnrollment.objects.create(
            student=s1, academic_year=seed['year'], department=seed['dept'],
            program=prog, semester=seed['sem1'], division=seed['div_a'],
            status='ACTIVE', is_current=True)
        api_client.force_authenticate(user=hod)
        res = api_client.post(
            f"/api/v1/academic/divisions/{div_b.id}/assign-students/",
            {'student_ids': [str(s1.id)], 'semester_id': str(seed['sem1'].id)},
            format='json')
        assert res.status_code == status.HTTP_200_OK, res.data
        assert res.data['repeated'] == [str(s1.id)]  # same sem -> repeat
        s1.refresh_from_db()
        assert s1.repeat_count == 1
        enr = s1.enrollments.filter(is_current=True).first()
        assert enr.division_id == div_b.id
        assert enr.placement_confirmed is True


@pytest.mark.django_db
class TestTermRollover:
    """Sysadmin term flip auto-advances odd sems; skips repeaters; idempotent."""

    def _setup(self):
        import datetime
        from apps.academic_structure.models import AcademicContext, AcademicYear, Department, Division, Program, Semester
        from apps.students.models import Student, StudentEnrollment
        year = AcademicYear.objects.create(
            code='2036-37', name='AY 2036-37', start_date=datetime.date(2036, 7, 1),
            end_date=datetime.date(2037, 6, 30), is_current=True)
        AcademicContext.objects.create(academic_year=year, term='ODD', is_active=True)
        dept = Department.objects.create(name='Roll Dept', code='RLL')
        prog = Program.objects.create(department=dept, name='B.Tech R', code='BTECH_RL')
        sem1 = Semester.objects.create(number=1, name='S1', year_level=1, term_type='ODD')
        Semester.objects.create(number=2, name='S2', year_level=1, term_type='EVEN')
        div = Division.objects.create(department=dept, academic_year=year, semester=sem1, name='A')
        s1 = Student.objects.create(first_name='A', last_name='B', application_id='ENR1')
        StudentEnrollment.objects.create(
            student=s1, academic_year=year, department=dept, program=prog,
            semester=sem1, division=div, status='ACTIVE', is_current=True)
        s2 = Student.objects.create(first_name='C', last_name='D', application_id='ENR2', repeat_count=1)
        StudentEnrollment.objects.create(
            student=s2, academic_year=year, department=dept, program=prog,
            semester=sem1, division=div, status='ACTIVE', is_current=True)
        return year, s1, s2

    def test_even_flip_advances_and_skips_repeaters(self, api_client, sysadmin_user):
        from apps.students.models import Student
        year, s1, s2 = self._setup()
        api_client.force_authenticate(user=sysadmin_user)
        res = api_client.post('/api/v1/academic/contexts/rollover/',
                              {'academic_year_id': str(year.id), 'term': 'EVEN'}, format='json')
        assert res.status_code == status.HTTP_200_OK, res.data
        assert res.data['advanced'] == 1
        assert res.data['skipped_repeats'] == 1
        s1.refresh_from_db()
        assert s1.enrollments.filter(is_current=True).first().semester.number == 2
        # idempotent rerun
        res2 = api_client.post('/api/v1/academic/contexts/rollover/',
                               {'academic_year_id': str(year.id), 'term': 'EVEN'}, format='json')
        assert res2.data['advanced'] == 0

    def test_non_sysadmin_forbidden(self, api_client, student_user):
        self._setup()
        api_client.force_authenticate(user=student_user)
        res = api_client.post('/api/v1/academic/contexts/rollover/', {'term': 'EVEN'}, format='json')
        assert res.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestClassTeacherSingleOwner:
    """Division patch and role-assignment POST stay in sync via one service."""

    def _setup(self):
        import datetime
        dept = Department.objects.create(name='Sync Dept', code='SYN')
        year = AcademicYear.objects.get(code='2026-27') if AcademicYear.objects.filter(code='2026-27').exists() else AcademicYear.objects.create(
            code='2026-27', name='AY 2026-2027', start_date=datetime.date(2026, 7, 1),
            end_date=datetime.date(2027, 6, 30), is_current=True)
        sem = Semester.objects.create(number=51, name='S51', year_level=1, term_type='ODD')
        div = Division.objects.create(department=dept, academic_year=year, semester=sem, name='A')
        hod = User.objects.create_user(username='hod_syn', password='Password123!', user_type=User.UserType.FACULTY)
        role_hod, _ = Role.objects.get_or_create(codename='HOD', defaults={'name': 'HOD'})
        RoleAssignment.objects.create(user=hod, role=role_hod, department_id=dept.id, status='ACTIVE')
        role_ct, _ = Role.objects.get_or_create(codename='CLASS_TEACHER', defaults={'name': 'CT'})
        t1 = User.objects.create_user(username='syn_t1', password='Password123!', user_type=User.UserType.FACULTY)
        t2 = User.objects.create_user(username='syn_t2', password='Password123!', user_type=User.UserType.FACULTY)
        return hod, div, role_ct, t1, t2

    def test_division_patch_creates_role_assignment(self, api_client):
        hod, div, role_ct, t1, t2 = self._setup()
        api_client.force_authenticate(user=hod)
        res = api_client.patch(f'/api/v1/academic/divisions/{div.id}/',
                               {'class_teacher': str(t1.id)}, format='json')
        assert res.status_code == status.HTTP_200_OK, res.data
        div.refresh_from_db()
        assert div.class_teacher_id == t1.id
        assert RoleAssignment.objects.filter(
            role=role_ct, division_id=div.id, user=t1,
            status=RoleAssignment.Status.ACTIVE).exists()

    def test_role_post_updates_division_fk_and_revokes_old(self, api_client):
        from apps.audit.models import AuditLog
        hod, div, role_ct, t1, t2 = self._setup()
        api_client.force_authenticate(user=hod)
        api_client.patch(f'/api/v1/academic/divisions/{div.id}/',
                         {'class_teacher': str(t1.id)}, format='json')
        res = api_client.post('/api/v1/auth/role-assignments/', {
            'user': str(t2.id), 'role': str(role_ct.id),
            'department_id': str(div.department_id), 'division_id': str(div.id),
        }, format='json')
        assert res.status_code == status.HTTP_201_CREATED, res.data
        div.refresh_from_db()
        assert div.class_teacher_id == t2.id
        actives = RoleAssignment.objects.filter(
            role=role_ct, division_id=div.id, status=RoleAssignment.Status.ACTIVE)
        assert [a.user_id for a in actives] == [t2.id]
        entry = AuditLog.objects.filter(
            target_type='Division', target_id=str(div.id)).order_by('-timestamp').first()
        assert entry is not None
        assert (entry.old_value or {}).get('class_teacher') == 'syn_t1'
        assert (entry.new_value or {}).get('class_teacher') == 'syn_t2'


@pytest.mark.django_db
class TestDivisionIntakeProjections:
    """HOD intake cards need class_code/year_label/enrolled_count (ADR-015).

    Projections are read-only derivations (no new columns, no migration).
    enrolled_count must come from a single annotated query (no N+1).
    """

    def test_list_exposes_projections_and_counts(self, api_client, sysadmin_user, academic_seed):
        from apps.students.models import Student, StudentEnrollment
        from apps.academic_structure.models import Program
        seed = academic_seed
        prog = Program.objects.create(department=seed['dept'], name='B.Tech Civ', code='BTECH_CIV')
        s1 = Student.objects.create(first_name='P', last_name='Q', application_id='ENP1')
        StudentEnrollment.objects.create(
            student=s1, academic_year=seed['year'], department=seed['dept'],
            program=prog, semester=seed['sem1'], division=seed['div_a'],
            status='ACTIVE', is_current=True)
        api_client.force_authenticate(user=sysadmin_user)
        with self.assertNumQueriesLessThan(15):
            res = api_client.get('/api/v1/academic/divisions/')
        assert res.status_code == status.HTTP_200_OK, res.data
        rows = res.data['results'] if isinstance(res.data, dict) and 'results' in res.data else res.data
        row = next((r for r in rows if str(r['id']) == str(seed['div_a'].id)), None)
        assert row is not None
        assert row['year_label'] == 'FY'
        assert row['year_level'] == 1
        assert row['class_code'] == f"CIVIL-Sem1-{seed['div_a'].name}"
        assert row['enrolled_count'] == 1

    def assertNumQueriesLessThan(self, n):
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        class Ctx:
            def __init__(self, limit):
                self.limit = limit
                self.ctx = CaptureQueriesContext(connection)

            def __enter__(self):
                self.ctx.__enter__()
                return self

            def __exit__(self, *args):
                self.ctx.__exit__(*args)
                assert len(self.ctx.captured_queries) < self.limit, (
                    f"Too many queries: {len(self.ctx.captured_queries)} >= {self.limit}"
                )
                return False

        return Ctx(n)

    def test_projections_are_read_only(self, api_client, sysadmin_user, academic_seed):
        seed = academic_seed
        api_client.force_authenticate(user=sysadmin_user)
        res = api_client.patch(
            f"/api/v1/academic/divisions/{seed['div_a'].id}/",
            {'class_code': 'HACK', 'year_label': 'SY', 'seat_capacity': 60},
            format='json')
        assert res.status_code == status.HTTP_200_OK, res.data
        seed['div_a'].refresh_from_db()
        assert seed['div_a'].seat_capacity == 60
        # No such columns exist — values are ignored, truth unchanged.
        assert not hasattr(seed['div_a'], 'class_code') or getattr(seed['div_a'], 'class_code', None) in (None, '')
