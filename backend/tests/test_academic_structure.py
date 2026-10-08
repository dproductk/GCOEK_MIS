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
class TestPromotionSeatingConfirmed:
    """Promotion seating counts as HOD placement: seated lands confirmed and
    never re-asks on pending-imports; unassigned (no class yet) stays open."""

    def _setup(self, with_successor=True):
        import datetime
        from apps.academic_structure.models import AcademicYear, Department, Division, Program, Semester
        from apps.authentication.models import Role, RoleAssignment, User
        from apps.finance.models import PaymentLedger
        from apps.results.models import EligibilityVerification
        from apps.students.models import Student, StudentEnrollment
        year = AcademicYear.objects.create(
            code='2042-43', name='AY 2042-43', start_date=datetime.date(2042, 7, 1),
            end_date=datetime.date(2043, 6, 30), is_current=True)
        dept = Department.objects.create(name='Confirm Dept', code='PCF')
        prog = Program.objects.create(department=dept, name='B.Tech P', code='BTECH_PCF')
        sem6 = Semester.objects.create(number=6, name='S6', year_level=3, term_type='EVEN')
        sem7 = Semester.objects.create(number=7, name='S7', year_level=4, term_type='ODD')
        div6 = Division.objects.create(department=dept, academic_year=year, semester=sem6, name='A')
        div7 = None
        if with_successor:
            div7 = Division.objects.create(department=dept, academic_year=year, semester=sem7, name='A')
        hod = User.objects.create_user(username='hod_pcf', password='Password123!', user_type=User.UserType.FACULTY)
        role_hod, _ = Role.objects.get_or_create(codename='HOD', defaults={'name': 'HOD'})
        RoleAssignment.objects.create(user=hod, role=role_hod, department_id=dept.id, status='ACTIVE')
        stu = User.objects.create_user(username='stu_pcf', password='Password123!', user_type=User.UserType.STUDENT)
        student = Student.objects.create(
            user=stu, first_name='P', last_name='C', application_id='ENPCF01', enrollment_no='ENPCF01')
        StudentEnrollment.objects.create(
            student=student, academic_year=year, department=dept, program=prog,
            semester=sem6, division=div6, status='ACTIVE', is_current=True)
        EligibilityVerification.objects.create(
            student=student, academic_year=year, target_semester=sem7, department=dept,
            active_backlog_count=0,
            calculated_status=EligibilityVerification.CalculatedStatus.ELIGIBLE,
            class_teacher_status=EligibilityVerification.StageStatus.APPROVED,
            hod_status=EligibilityVerification.StageStatus.APPROVED,
            final_eligible=True)
        PaymentLedger.objects.create(
            student=student, academic_year=year, receipt_no='GCOEK/2042/P/001',
            total_fee_due=10000, amount_paid=10000,
            payment_mode=PaymentLedger.PaymentMode.CASH, transaction_ref='CASH-P',
            payment_date=datetime.date.today(), collected_by=hod)
        return student, div6, div7, sem7

    def test_promoted_into_class_lands_confirmed(self):
        from apps.students.models import StudentEnrollment
        from apps.students.services import check_and_promote_student
        student, div6, div7, sem7 = self._setup(with_successor=True)
        ok, msg = check_and_promote_student(str(student.id))
        assert ok, msg
        enr = student.enrollments.filter(is_current=True).first()
        assert enr.semester.number == 7
        assert enr.division_id == div7.id
        assert enr.placement_confirmed is True

    def test_promoted_without_class_stays_unconfirmed(self):
        import datetime
        from apps.academic_structure.models import AcademicYear, Department, Division, Program, Semester
        from apps.authentication.models import Role, RoleAssignment, User
        from apps.finance.models import PaymentLedger
        from apps.results.models import EligibilityVerification
        from apps.students.models import Student, StudentEnrollment
        from apps.students.services import check_and_promote_student
        # Sem 5 -> 6: no flip trigger (flip only handles 2/4/6), no Sem-6
        # division exists, so the promotion must leave placement open.
        year = AcademicYear.objects.create(
            code='2043-44', name='AY 2043-44', start_date=datetime.date(2043, 7, 1),
            end_date=datetime.date(2044, 6, 30), is_current=True)
        dept = Department.objects.create(name='Open Dept', code='OPN')
        prog = Program.objects.create(department=dept, name='B.Tech O', code='BTECH_OPN')
        sem5 = Semester.objects.create(number=5, name='S5', year_level=3, term_type='ODD')
        sem6 = Semester.objects.create(number=6, name='S6', year_level=3, term_type='EVEN')
        div5 = Division.objects.create(department=dept, academic_year=year, semester=sem5, name='A')
        hod = User.objects.create_user(username='hod_opn', password='Password123!', user_type=User.UserType.FACULTY)
        stu = User.objects.create_user(username='stu_opn', password='Password123!', user_type=User.UserType.STUDENT)
        student = Student.objects.create(
            user=stu, first_name='O', last_name='P', application_id='ENOPN01', enrollment_no='ENOPN01')
        StudentEnrollment.objects.create(
            student=student, academic_year=year, department=dept, program=prog,
            semester=sem5, division=div5, status='ACTIVE', is_current=True)
        EligibilityVerification.objects.create(
            student=student, academic_year=year, target_semester=sem6, department=dept,
            active_backlog_count=0,
            calculated_status=EligibilityVerification.CalculatedStatus.ELIGIBLE,
            class_teacher_status=EligibilityVerification.StageStatus.APPROVED,
            hod_status=EligibilityVerification.StageStatus.APPROVED,
            final_eligible=True)
        PaymentLedger.objects.create(
            student=student, academic_year=year, receipt_no='GCOEK/2043/P/001',
            total_fee_due=10000, amount_paid=10000,
            payment_mode=PaymentLedger.PaymentMode.CASH, transaction_ref='CASH-O',
            payment_date=datetime.date.today(), collected_by=hod)
        ok, msg = check_and_promote_student(str(student.id))
        assert ok, msg
        enr = student.enrollments.filter(is_current=True).first()
        assert enr.semester.number == 6
        assert enr.division_id is None
        assert enr.placement_confirmed is False

    def test_seat_traced_lands_confirmed(self):
        from apps.academic_structure.services import seat_traced_students_to_division
        from apps.students.models import StudentEnrollment
        student, div6, div7, sem7 = self._setup(with_successor=True)
        cur = student.enrollments.filter(is_current=True).first()
        cur.is_current = False
        cur.status = StudentEnrollment.Status.PROMOTED
        cur.save(update_fields=['is_current', 'status'])
        new_enr = StudentEnrollment.objects.create(
            student=student, academic_year=cur.academic_year, department=cur.department,
            program=cur.program, semester=sem7, division=None,
            status=StudentEnrollment.Status.ACTIVE, is_current=True)
        moved = seat_traced_students_to_division(div7, original_div_id=div6.id)
        assert moved == 1
        new_enr.refresh_from_db()
        assert new_enr.division_id == div7.id
        assert new_enr.placement_confirmed is True


@pytest.mark.django_db
class TestClassTeacherInvalidInputNever500:
    """Garbage teacher input must 400, never 500 (regression: raw UUID
    strings hit Django filters/lookups that raise ValidationError)."""

    def _setup(self):
        import datetime
        from apps.academic_structure.models import AcademicYear, Department, Division, Semester
        year = AcademicYear.objects.create(
            code='2044-45', name='AY 2044-45', start_date=datetime.date(2044, 7, 1),
            end_date=datetime.date(2045, 6, 30), is_current=False)
        dept = Department.objects.create(name='Input Dept', code='INP')
        sem = Semester.objects.create(number=9, name='S9', year_level=1, term_type='ODD')
        div = Division.objects.create(department=dept, academic_year=year, semester=sem, name='A')
        return div

    def test_garbage_teacher_id_is_400(self, api_client, sysadmin_user):
        div = self._setup()
        api_client.force_authenticate(user=sysadmin_user)
        res = api_client.patch(f'/api/v1/academic/divisions/{div.id}/',
                               {'class_teacher': 'not-a-uuid'}, format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST

    def test_unknown_teacher_uuid_is_400(self, api_client, sysadmin_user):
        div = self._setup()
        api_client.force_authenticate(user=sysadmin_user)
        res = api_client.patch(f'/api/v1/academic/divisions/{div.id}/',
                               {'class_teacher': '00000000-0000-0000-0000-000000000000'},
                               format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST

    def test_faculty_without_login_is_400_not_silent_clear(self, api_client, sysadmin_user):
        from apps.faculty.models import Faculty
        div = self._setup()
        dept = div.department
        fac = Faculty.objects.create(
            employee_code='INP_NOLOGIN', first_name='No', last_name='Login',
            department=dept, date_of_joining=datetime.date(2020, 1, 1),
            official_email='nologin@gceok.ac.in')
        assert fac.user_id is None
        api_client.force_authenticate(user=sysadmin_user)
        res = api_client.patch(f'/api/v1/academic/divisions/{div.id}/',
                               {'class_teacher': str(fac.id)}, format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        div.refresh_from_db()
        assert div.class_teacher_id is None


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
class TestSemesterDivisionConsistency:
    """Seating must never mix semesters: enrollment.semester == division.semester.

    Regression tests for the production incident where Sem-7 students were
    seated in a Sem-6 division (and Sem-3 in Sem-1), corrupting rosters,
    verification queues and result rows.
    """

    def _sem2_setup(self, seed):
        sem2 = Semester.objects.create(
            number=2, name='Semester 2', year_level=1,
            term_type=Semester.TermType.EVEN,
        )
        div_sem2 = Division.objects.create(
            department=seed['dept'], academic_year=seed['year'],
            semester=sem2, name='B')
        return sem2, div_sem2

    def _sem1_student(self, seed):
        from apps.students.models import Student, StudentEnrollment
        prog = Program.objects.create(department=seed['dept'], name='P', code='PX2')
        s = Student.objects.create(first_name='C', last_name='D', application_id='ENX2')
        StudentEnrollment.objects.create(
            student=s, academic_year=seed['year'], department=seed['dept'],
            program=prog, semester=seed['sem1'], division=None,
            status='ACTIVE', is_current=True)
        return s

    def test_assign_division_rejects_wrong_semester(self, api_client, sysadmin_user, academic_seed):
        seed = academic_seed
        _, div_sem2 = self._sem2_setup(seed)
        s = self._sem1_student(seed)
        api_client.force_authenticate(user=sysadmin_user)
        res = api_client.post(
            f'/api/v1/students/{s.id}/assign-division/',
            {'division_id': str(div_sem2.id)}, format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST, res.data
        enr = s.enrollments.filter(is_current=True).first()
        assert enr.semester.number == 1
        assert enr.division_id is None

    def test_bulk_assign_skips_wrong_semester(self, api_client, academic_seed):
        seed = academic_seed
        hod = TestBulkFinalize()._hod(seed['dept'])
        _, div_sem2 = self._sem2_setup(seed)
        s = self._sem1_student(seed)
        api_client.force_authenticate(user=hod)
        res = api_client.post(
            f"/api/v1/academic/divisions/{div_sem2.id}/assign-students/",
            {'student_ids': [str(s.id)]}, format='json')
        assert res.status_code == status.HTTP_200_OK, res.data
        assert res.data['moved'] == []
        assert len(res.data['skipped']) == 1
        enr = s.enrollments.filter(is_current=True).first()
        assert enr.semester.number == 1
        assert enr.division_id is None

    def test_bulk_assign_rejects_semester_correction_mismatch(self, api_client, academic_seed):
        seed = academic_seed
        hod = TestBulkFinalize()._hod(seed['dept'])
        sem2, _ = self._sem2_setup(seed)
        s = self._sem1_student(seed)
        api_client.force_authenticate(user=hod)
        # Correction targets Sem 2 but the division is a Sem-1 class.
        res = api_client.post(
            f"/api/v1/academic/divisions/{seed['div_a'].id}/assign-students/",
            {'student_ids': [str(s.id)], 'semester_id': str(sem2.id)}, format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST, res.data
        enr = s.enrollments.filter(is_current=True).first()
        assert enr.semester.number == 1
        assert enr.division_id is None


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


@pytest.mark.django_db
class TestDivisionSemesterLock:
    """HOD cannot change structural fields once students are seated."""

    def _hod_for(self, dept):
        hod = User.objects.create_user(
            username=f"hod_lock_{dept.code.lower()}", password='Password12345!',
            user_type=User.UserType.FACULTY)
        role, _ = Role.objects.get_or_create(codename='HOD', defaults={'name': 'HOD'})
        RoleAssignment.objects.create(
            user=hod, role=role, department_id=dept.id,
            status=RoleAssignment.Status.ACTIVE)
        return hod

    def _seated_setup(self, seed):
        import datetime
        from apps.students.models import Student, StudentEnrollment
        sem6 = Semester.objects.create(number=6, name='Semester 6', year_level=3, term_type=Semester.TermType.EVEN)
        div = Division.objects.create(
            department=seed['dept'], academic_year=seed['year'],
            semester=sem6, name='A', seat_capacity=60)
        prog = Program.objects.create(department=seed['dept'], name='P', code='PLOCK')
        s1 = Student.objects.create(first_name='A', last_name='B', application_id='ENLOCK1')
        StudentEnrollment.objects.create(
            student=s1, academic_year=seed['year'], department=seed['dept'],
            program=prog, semester=sem6, division=div,
            status='ACTIVE', is_current=True)
        return div, sem6

    def test_hod_semester_change_blocked_when_seated(self, api_client, academic_seed):
        seed = academic_seed
        div, _ = self._seated_setup(seed)
        sem7 = Semester.objects.create(number=7, name='Semester 7', year_level=4, term_type=Semester.TermType.ODD)
        api_client.force_authenticate(user=self._hod_for(seed['dept']))
        res = api_client.patch(f"/api/v1/academic/divisions/{div.id}/",
                               {'semester': str(sem7.id)}, format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST, res.data
        div.refresh_from_db()
        assert div.semester.number == 6

    def test_hod_teacher_change_still_allowed(self, api_client, academic_seed):
        seed = academic_seed
        div, _ = self._seated_setup(seed)
        api_client.force_authenticate(user=self._hod_for(seed['dept']))
        res = api_client.patch(f"/api/v1/academic/divisions/{div.id}/",
                               {'seat_capacity': 70}, format='json')
        assert res.status_code == status.HTTP_200_OK, res.data

    def test_hod_semester_change_allowed_when_empty(self, api_client, academic_seed, sysadmin_user):
        seed = academic_seed
        sem6 = Semester.objects.create(number=6, name='Semester 6', year_level=3, term_type=Semester.TermType.EVEN)
        sem7 = Semester.objects.create(number=7, name='Semester 7', year_level=4, term_type=Semester.TermType.ODD)
        div = Division.objects.create(
            department=seed['dept'], academic_year=seed['year'],
            semester=sem6, name='B', seat_capacity=60)
        api_client.force_authenticate(user=self._hod_for(seed['dept']))
        res = api_client.patch(f"/api/v1/academic/divisions/{div.id}/",
                               {'semester': str(sem7.id)}, format='json')
        assert res.status_code == status.HTTP_200_OK, res.data


@pytest.mark.django_db
class TestPromoteClass:
    """Year-change class promotion: full flip in place vs partial split."""

    def _hod_for(self, dept):
        hod = User.objects.create_user(
            username=f"hod_prom_{dept.code.lower()}", password='Password12345!',
            user_type=User.UserType.FACULTY)
        role, _ = Role.objects.get_or_create(codename='HOD', defaults={'name': 'HOD'})
        RoleAssignment.objects.create(
            user=hod, role=role, department_id=dept.id,
            status=RoleAssignment.Status.ACTIVE)
        return hod

    def _setup(self, seed, paying=1):
        import datetime
        from apps.finance.models import PaymentLedger
        from apps.results.models import EligibilityVerification
        from apps.students.models import Student, StudentEnrollment
        sem6 = Semester.objects.create(number=6, name='Semester 6', year_level=3, term_type=Semester.TermType.EVEN)
        sem7 = Semester.objects.create(number=7, name='Semester 7', year_level=4, term_type=Semester.TermType.ODD)
        teacher = User.objects.create_user(
            username=f"ct_prom_{seed['dept'].code.lower()}", password='Password12345!',
            user_type=User.UserType.FACULTY)
        div = Division.objects.create(
            department=seed['dept'], academic_year=seed['year'],
            semester=sem6, name='A', seat_capacity=60, class_teacher=teacher)
        prog = Program.objects.create(department=seed['dept'], name='P', code='PPROM')
        students = []
        for i in range(2):
            s = Student.objects.create(first_name=f'S{i}', last_name='T', application_id=f'ENPROM{i}')
            StudentEnrollment.objects.create(
                student=s, academic_year=seed['year'], department=seed['dept'],
                program=prog, semester=sem6, division=div,
                status='ACTIVE', is_current=True)
            EligibilityVerification.objects.create(
                student=s, academic_year=seed['year'], target_semester=sem7,
                department=seed['dept'], active_backlog_count=0,
                calculated_status=EligibilityVerification.CalculatedStatus.ELIGIBLE,
                class_teacher_status=EligibilityVerification.StageStatus.APPROVED,
                hod_status=EligibilityVerification.StageStatus.APPROVED,
                final_eligible=True)
            students.append(s)
        for s in students[:paying]:
            PaymentLedger.objects.create(
                student=s, academic_year=seed['year'], receipt_no=f'R{s.application_id}',
                total_fee_due=1000, amount_paid=1000, balance_due=0,
                status=PaymentLedger.PaymentStatus.PAID,
                payment_date=datetime.date(2026, 8, 1))
        return div, sem6, sem7, students

    def test_dry_run_reports_movers_and_stayers(self, api_client, academic_seed):
        seed = academic_seed
        div, _, _, _ = self._setup(seed, paying=1)
        api_client.force_authenticate(user=self._hod_for(seed['dept']))
        res = api_client.post(f"/api/v1/academic/divisions/{div.id}/promote-class/",
                              {'dry_run': True}, format='json')
        assert res.status_code == status.HTTP_200_OK, res.data
        assert res.data['will_promote'] == 1
        assert res.data['will_stay'] == 1
        assert res.data['full_flip'] is False

    def test_partial_split_creates_successor_with_same_teacher(self, api_client, academic_seed):
        from apps.students.models import StudentEnrollment
        seed = academic_seed
        div, _, sem7, students = self._setup(seed, paying=1)
        api_client.force_authenticate(user=self._hod_for(seed['dept']))
        res = api_client.post(f"/api/v1/academic/divisions/{div.id}/promote-class/",
                              {}, format='json')
        assert res.status_code == status.HTTP_200_OK, res.data
        assert res.data['flipped'] is False
        succ = Division.objects.get(id=res.data['successor_division_id'])
        assert succ.semester.number == 7
        assert succ.class_teacher_id == div.class_teacher_id
        moved_enr = StudentEnrollment.objects.filter(student=students[0], is_current=True).first()
        assert moved_enr.semester.number == 7 and moved_enr.division_id == succ.id
        left_enr = StudentEnrollment.objects.filter(student=students[1], is_current=True).first()
        assert left_enr.semester.number == 6 and left_enr.division_id == div.id

    def test_full_flip_reuses_same_row_and_clears_subject_slots(self, api_client, academic_seed):
        from apps.faculty.models import TeachingAssignment, Faculty
        from apps.students.models import StudentEnrollment
        seed = academic_seed
        div, sem6, sem7, students = self._setup(seed, paying=2)
        fac = Faculty.objects.create(
            employee_code='FLOCK1', first_name='F', last_name='T',
            department=seed['dept'], date_of_joining='2024-07-01',
            official_email='flock1@gcoek.ac.in')
        TeachingAssignment.objects.create(
            faculty=fac, academic_year=seed['year'], department=seed['dept'],
            semester=sem6, division=div, subject_name='Old Subj',
            subject_code='OLD101', role='PRIMARY_FACULTY', is_active=True)
        api_client.force_authenticate(user=self._hod_for(seed['dept']))
        res = api_client.post(f"/api/v1/academic/divisions/{div.id}/promote-class/",
                              {}, format='json')
        assert res.status_code == status.HTTP_200_OK, res.data
        assert res.data['flipped'] is True
        div.refresh_from_db()
        assert div.semester.number == 7
        for s in students:
            enr = StudentEnrollment.objects.filter(student=s, is_current=True).first()
            assert enr.semester.number == 7 and enr.division_id == div.id
        assert TeachingAssignment.objects.filter(division=div, is_active=True).count() == 0


@pytest.mark.django_db
class TestFailFlow:
    """Terminal FAIL: teacher/HOD fail locks the case; fees can never promote."""

    def _setup(self, seed):
        import datetime
        from apps.finance.models import PaymentLedger
        from apps.results.models import EligibilityVerification
        from apps.students.models import Student, StudentEnrollment
        sem6 = Semester.objects.create(number=6, name='Semester 6', year_level=3, term_type=Semester.TermType.EVEN)
        sem7 = Semester.objects.create(number=7, name='Semester 7', year_level=4, term_type=Semester.TermType.ODD)
        div = Division.objects.create(
            department=seed['dept'], academic_year=seed['year'],
            semester=sem6, name='A', seat_capacity=60)
        prog = Program.objects.create(department=seed['dept'], name='P', code='PFAIL')
        s = Student.objects.create(first_name='F', last_name='T', application_id='ENFAIL1')
        StudentEnrollment.objects.create(
            student=s, academic_year=seed['year'], department=seed['dept'],
            program=prog, semester=sem6, division=div,
            status='ACTIVE', is_current=True)
        ev = EligibilityVerification.objects.create(
            student=s, academic_year=seed['year'], target_semester=sem7,
            department=seed['dept'], active_backlog_count=0,
            calculated_status=EligibilityVerification.CalculatedStatus.ELIGIBLE)
        hod = User.objects.create_user(
            username=f"hod_fail_{seed['dept'].code.lower()}", password='Password12345!',
            user_type=User.UserType.FACULTY)
        role, _ = Role.objects.get_or_create(codename='HOD', defaults={'name': 'HOD'})
        RoleAssignment.objects.create(
            user=hod, role=role, department_id=seed['dept'].id,
            status=RoleAssignment.Status.ACTIVE)
        return div, sem6, sem7, s, ev, hod

    def test_teacher_fail_locks_and_blocks_promotion_despite_fees(self, academic_seed):
        import datetime
        from apps.finance.models import PaymentLedger
        from apps.results.services import class_teacher_review_eligibility, hod_endorse_eligibility
        from apps.students.services import check_and_promote_student
        seed = academic_seed
        div, sem6, sem7, s, ev, hod = self._setup(seed)
        teacher = User.objects.create_user(
            username='ct_fail1', password='Password12345!',
            user_type=User.UserType.FACULTY)
        ev = class_teacher_review_eligibility(
            str(ev.id), teacher, 'REJECTED', 'Failed 2 subjects.', request=None)
        assert ev.class_teacher_status == 'REJECTED'
        assert ev.is_locked_for_teacher is True
        assert ev.is_locked_for_student is True
        # HOD cannot approve a teacher-failed case.
        try:
            hod_endorse_eligibility(str(ev.id), hod, 'APPROVED', '', request=None)
            assert False, 'expected ValidationError'
        except Exception:
            pass
        # Even fully paid, a failed student never promotes.
        PaymentLedger.objects.create(
            student=s, academic_year=seed['year'], receipt_no='RFAIL1',
            total_fee_due=1000, amount_paid=1000, balance_due=0,
            status=PaymentLedger.PaymentStatus.PAID,
            payment_date=datetime.date(2026, 8, 1))
        ok, msg = check_and_promote_student(str(s.id))
        assert ok is False

    def test_hod_fail_is_terminal_but_flaggable_to_reopen(self, academic_seed):
        from apps.results.services import class_teacher_review_eligibility, hod_endorse_eligibility
        seed = academic_seed
        div, sem6, sem7, s, ev, hod = self._setup(seed)
        teacher = User.objects.create_user(
            username='ct_fail2', password='Password12345!',
            user_type=User.UserType.FACULTY)
        class_teacher_review_eligibility(str(ev.id), teacher, 'APPROVED', 'ok', request=None)
        ev = hod_endorse_eligibility(str(ev.id), hod, 'REJECTED', 'Failed final viva.', request=None)
        assert ev.final_eligible is False
        # Teacher cannot touch a HOD-failed case.
        try:
            class_teacher_review_eligibility(str(ev.id), teacher, 'APPROVED', 'retry', request=None)
            assert False, 'expected ValidationError'
        except Exception:
            pass
        # HOD flag reopens it.
        ev = hod_endorse_eligibility(str(ev.id), hod, 'FLAGGED', 'recheck', request=None)
        assert ev.hod_status == 'FLAGGED'
        assert ev.is_locked_for_teacher is False

    def test_promote_class_blocked_until_all_decided(self, api_client, academic_seed):
        seed = academic_seed
        div, sem6, sem7, s, ev, hod = self._setup(seed)
        api_client.force_authenticate(user=hod)
        res = api_client.post(f"/api/v1/academic/divisions/{div.id}/promote-class/",
                              {'dry_run': True}, format='json')
        assert res.status_code == status.HTTP_200_OK, res.data
        assert res.data['blocked'] == 1
        assert res.data['ready'] is False
        res = api_client.post(f"/api/v1/academic/divisions/{div.id}/promote-class/",
                              {}, format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST, res.data
        assert not hasattr(seed['div_a'], 'class_code') or getattr(seed['div_a'], 'class_code', None) in (None, '')


@pytest.mark.django_db
class TestTwelveStudentRepeaterScenario:
    """Tests the exact 12-student transition, repeater class, late promotion, and HOD action."""

    def _hod_for(self, dept):
        hod = User.objects.create_user(
            username=f"hod_twelve_{dept.code.lower()}", password='Password12345!',
            user_type=User.UserType.FACULTY)
        role, _ = Role.objects.get_or_create(codename='HOD', defaults={'name': 'HOD'})
        RoleAssignment.objects.create(
            user=hod, role=role, department_id=dept.id,
            status=RoleAssignment.Status.ACTIVE)
        return hod

    def test_twelve_student_repeater_and_late_promotion_lifecycle(self, api_client, academic_seed):
        import datetime
        from apps.finance.models import PaymentLedger
        from apps.results.models import EligibilityVerification, SemesterResult
        from apps.students.models import Student, StudentEnrollment
        from apps.students.services import check_and_promote_student
        from apps.results.services import hod_endorse_eligibility, class_teacher_review_eligibility
        from apps.audit.models import AuditLog

        seed = academic_seed
        dept = seed['dept']
        ay = seed['year']
        sem6 = Semester.objects.create(number=6, name='Semester 6', year_level=3, term_type=Semester.TermType.EVEN)
        sem7 = Semester.objects.create(number=7, name='Semester 7', year_level=4, term_type=Semester.TermType.ODD)
        teacher = User.objects.create_user(username='ct_twelve', password='Password12345!', user_type=User.UserType.FACULTY)
        div = Division.objects.create(
            department=dept, academic_year=ay, semester=sem6, name='A',
            seat_capacity=60, class_teacher=teacher)
        prog = Program.objects.create(department=dept, name='ProgTwelve', code='PTWELVE')
        hod = self._hod_for(dept)

        # 12 students:
        # 0-8: 9 students already promoted to Sem 7
        # 9: 1 student eligible but fees pending
        # 10-11: 2 students failed
        students = []
        for i in range(12):
            s = Student.objects.create(first_name=f'Stu{i}', last_name='Test', application_id=f'ENTWELVE{i}')
            students.append(s)

        # Setup 9 already promoted students:
        # In Sem 6, they had an enrollment now PROMOTED (is_current=False),
        # and currently they have an enrollment in Sem 7 (is_current=True, division=None pending class flip)
        for s in students[:9]:
            old_enr = StudentEnrollment.objects.create(
                student=s, academic_year=ay, department=dept, program=prog,
                semester=sem6, division=div, status=StudentEnrollment.Status.PROMOTED,
                is_current=False)
            curr_enr = StudentEnrollment.objects.create(
                student=s, academic_year=ay, department=dept, program=prog,
                semester=sem7, division=None, status=StudentEnrollment.Status.ACTIVE,
                is_current=True)
            EligibilityVerification.objects.create(
                student=s, academic_year=ay, target_semester=sem7, department=dept,
                active_backlog_count=0,
                calculated_status=EligibilityVerification.CalculatedStatus.ELIGIBLE,
                class_teacher_status=EligibilityVerification.StageStatus.APPROVED,
                hod_status=EligibilityVerification.StageStatus.APPROVED,
                final_eligible=True)

        # Student 9: eligible but unpaid
        s_unpaid = students[9]
        StudentEnrollment.objects.create(
            student=s_unpaid, academic_year=ay, department=dept, program=prog,
            semester=sem6, division=div, status=StudentEnrollment.Status.ACTIVE,
            is_current=True)
        ev_unpaid = EligibilityVerification.objects.create(
            student=s_unpaid, academic_year=ay, target_semester=sem7, department=dept,
            active_backlog_count=0,
            calculated_status=EligibilityVerification.CalculatedStatus.ELIGIBLE,
            class_teacher_status=EligibilityVerification.StageStatus.APPROVED,
            hod_status=EligibilityVerification.StageStatus.APPROVED,
            final_eligible=True)
        SemesterResult.objects.create(
            student=s_unpaid, academic_year=ay, semester=sem6, is_published=True,
            result_status=SemesterResult.ResultStatus.PASS)

        # Student 10 & 11: failed
        s_fail1 = students[10]
        StudentEnrollment.objects.create(
            student=s_fail1, academic_year=ay, department=dept, program=prog,
            semester=sem6, division=div, status=StudentEnrollment.Status.ACTIVE,
            is_current=True)
        ev_fail1 = EligibilityVerification.objects.create(
            student=s_fail1, academic_year=ay, target_semester=sem7, department=dept,
            active_backlog_count=3,
            calculated_status=EligibilityVerification.CalculatedStatus.NOT_ELIGIBLE,
            class_teacher_status=EligibilityVerification.StageStatus.REJECTED,
            hod_status=EligibilityVerification.StageStatus.REJECTED,
            final_eligible=False)
        SemesterResult.objects.create(
            student=s_fail1, academic_year=ay, semester=sem6, is_published=True,
            result_status=SemesterResult.ResultStatus.FAIL)

        s_fail2 = students[11]
        StudentEnrollment.objects.create(
            student=s_fail2, academic_year=ay, department=dept, program=prog,
            semester=sem6, division=div, status=StudentEnrollment.Status.ACTIVE,
            is_current=True)
        ev_fail2 = EligibilityVerification.objects.create(
            student=s_fail2, academic_year=ay, target_semester=sem7, department=dept,
            active_backlog_count=2,
            calculated_status=EligibilityVerification.CalculatedStatus.NOT_ELIGIBLE,
            class_teacher_status=EligibilityVerification.StageStatus.REJECTED,
            hod_status=EligibilityVerification.StageStatus.REJECTED,
            final_eligible=False)
        SemesterResult.objects.create(
            student=s_fail2, academic_year=ay, semester=sem6, is_published=True,
            result_status=SemesterResult.ResultStatus.FAIL)

        api_client.force_authenticate(user=hod)

        # STEP A: HOD opens Promote (dry run preview)
        res_preview = api_client.post(f"/api/v1/academic/divisions/{div.id}/promote-class/",
                                      {'dry_run': True}, format='json')
        assert res_preview.status_code == status.HTTP_200_OK, res_preview.data
        data = res_preview.data
        assert data['already_promoted_count'] == 9
        assert data['fees_pending_count'] == 1
        assert data['failed_count'] == 2
        assert data['ready_to_move_count'] == 0
        assert data['blocked_count'] == 0
        assert data['will_promote'] == 0
        assert data['ready'] is True

        # Preselected repeater IDs: failed students
        default_rep = data['default_repeater']
        assert default_rep['division_name'] == 'R'
        assert default_rep['semester_number'] == 6
        assert set(default_rep['preselected_student_ids']) == {str(s_fail1.id), str(s_fail2.id)}
        assert default_rep['optional_student_ids'] == [str(s_unpaid.id)]

        # STEP B: HOD selects all 3 students (2 failed + 1 unpaid) to move to repeater
        rep_ids = [str(s_fail1.id), str(s_fail2.id), str(s_unpaid.id)]
        res_promote = api_client.post(
            f"/api/v1/academic/divisions/{div.id}/promote-class/",
            {
                'repeater_student_ids': rep_ids,
                'repeater_division_name': 'R',
            },
            format='json'
        )
        assert res_promote.status_code == status.HTTP_200_OK, res_promote.data
        assert res_promote.data['flipped'] is True
        assert len(res_promote.data['moved_to_repeater']) == 3

        # Check Division state:
        div.refresh_from_db()
        assert div.semester.number == 7  # Flips to Sem 7 in place!
        assert div.name == 'A'

        # Check Repeater Division:
        rep_div = Division.objects.get(name='R', semester=sem6, department=dept, academic_year=ay)
        assert rep_div.class_teacher_id == teacher.id

        # Sem 6 Div R has exactly 3 active students
        r_enrs = StudentEnrollment.objects.filter(division=rep_div, is_current=True)
        assert r_enrs.count() == 3
        assert {e.student_id for e in r_enrs} == {s_fail1.id, s_fail2.id, s_unpaid.id}

        # Sem 7 Div A has exactly 9 active students (the 9 already promoted were seated into it)
        a_enrs = StudentEnrollment.objects.filter(division=div, is_current=True)
        assert a_enrs.count() == 9
        for s in students[:9]:
            assert StudentEnrollment.objects.filter(student=s, is_current=True, division=div, semester=sem7).exists()

        # Sem 6 Div A has 0 active students
        assert StudentEnrollment.objects.filter(division=div, is_current=True, semester=sem6).count() == 0

        # Check audit log records
        assert AuditLog.objects.filter(target_type='Division', target_id=str(rep_div.id), action=AuditLog.Action.CREATE).exists()
        assert AuditLog.objects.filter(target_type='Division', target_id=str(div.id), action=AuditLog.Action.UPDATE).exists()

        # STEP C: Later, unpaid repeater student pays fees -> auto promotes to existing Sem 7 Div A
        PaymentLedger.objects.create(
            student=s_unpaid, academic_year=ay, receipt_no='RUNPAID1',
            total_fee_due=5000, amount_paid=5000, balance_due=0,
            status=PaymentLedger.PaymentStatus.PAID,
            payment_date=datetime.date(2026, 8, 15)
        )
        ok_unpaid, msg_unpaid = check_and_promote_student(str(s_unpaid.id), actor=hod)
        assert ok_unpaid is True
        enr_unpaid_promoted = StudentEnrollment.objects.filter(student=s_unpaid, is_current=True).first()
        assert enr_unpaid_promoted.semester.number == 7
        assert enr_unpaid_promoted.division_id == div.id  # Placed in Sem 7 Div A!

        # Sem 7 Div A now has 10 active students
        assert StudentEnrollment.objects.filter(division=div, is_current=True).count() == 10
        # Sem 6 Div R now has 2 active students
        assert StudentEnrollment.objects.filter(division=rep_div, is_current=True).count() == 2

        # STEP D: Later, failed repeater student gets result corrected and reopened
        # 1. HOD verification page allows action on teacher-failed student
        roster_res = api_client.get(f"/api/v1/results/eligibility/class-roster/?division_id={rep_div.id}")
        assert roster_res.status_code == status.HTTP_200_OK
        fail1_row = next(r for r in roster_res.data['students'] if r['student_id'] == str(s_fail1.id))
        assert fail1_row['can_endorse_hod'] is True  # HOD can act on failed student!

        # 2. HOD flags to reopen
        endorse_res = api_client.post(f"/api/v1/results/eligibility/{ev_fail1.id}/endorse-hod/",
                                      {'status': 'FLAGGED', 'remarks': 'Re-evaluation viva passed.'},
                                      format='json')
        assert endorse_res.status_code == status.HTTP_200_OK
        ev_fail1.refresh_from_db()
        assert ev_fail1.hod_status == 'FLAGGED'
        assert ev_fail1.is_locked_for_teacher is False

        # 3. Teacher re-reviews and approves
        class_teacher_review_eligibility(str(ev_fail1.id), teacher, 'APPROVED', 'Marks corrected.', request=None)
        # 4. HOD endorses
        hod_endorse_eligibility(str(ev_fail1.id), hod, 'APPROVED', 'Endorsed.', request=None)
        ev_fail1.refresh_from_db()
        assert ev_fail1.final_eligible is True

        # 5. Fee paid and student promoted
        PaymentLedger.objects.create(
            student=s_fail1, academic_year=ay, receipt_no='RFAILPAID1',
            total_fee_due=5000, amount_paid=5000, balance_due=0,
            status=PaymentLedger.PaymentStatus.PAID,
            payment_date=datetime.date(2026, 8, 20)
        )
        ok_fail1, msg_fail1 = check_and_promote_student(str(s_fail1.id), actor=hod)
        assert ok_fail1 is True
        enr_fail1_promoted = StudentEnrollment.objects.filter(student=s_fail1, is_current=True).first()
        assert enr_fail1_promoted.semester.number == 7
        assert enr_fail1_promoted.division_id == div.id  # Placed in Sem 7 Div A!

        # Sem 7 Div A now has 11 active students
        assert StudentEnrollment.objects.filter(division=div, is_current=True).count() == 11
        # Sem 6 Div R now has 1 active student
        assert StudentEnrollment.objects.filter(division=rep_div, is_current=True).count() == 1

        # No duplicate class created in Sem 7
        assert Division.objects.filter(department=dept, semester=sem7, name='A').count() == 1
        assert not Division.objects.filter(department=dept, semester=sem7, name='R').exists()

        # Idempotency check: promoting already-promoted student does not duplicate
        ok_again, _ = check_and_promote_student(str(s_fail1.id), actor=hod)
        assert ok_again is True
        assert StudentEnrollment.objects.filter(student=s_fail1, is_current=True).count() == 1

