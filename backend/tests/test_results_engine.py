"""
Automated tests for Results Calculation Engine and Eligibility Workflow.
Tests:
- 9-Point grading and SGPA computation
- Backlog detection and ATKT status calculation
- Multi-tier Eligibility workflow (Class Teacher -> HOD)
- Student self-result scope isolation
"""
import datetime
from decimal import Decimal
import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.academic_structure.models import AcademicYear, Department, Division, Program, Semester
from apps.authentication.models import Role, RoleAssignment, User
from apps.results.models import EligibilityVerification, SemesterResult, SubjectResult
from apps.results.services import (
    calculate_semester_metrics,
    evaluate_student_eligibility,
    grade_for_marks,
)
from apps.students.models import Student, StudentEnrollment


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def result_setup(db):
    year = AcademicYear.objects.create(
        code='2026-27', name='2026-2027',
        start_date=datetime.date(2026, 7, 1), end_date=datetime.date(2027, 6, 30),
        is_current=True
    )
    dept = Department.objects.create(name='Computer Science and Engineering', code='CSE')
    prog = Program.objects.create(department=dept, name='B.Tech Computer Science', code='BTECH_CSE')
    sem1 = Semester.objects.create(number=1, name='Semester 1', year_level=1, term_type=Semester.TermType.ODD)
    sem2 = Semester.objects.create(number=2, name='Semester 2', year_level=1, term_type=Semester.TermType.EVEN)
    sem3 = Semester.objects.create(number=3, name='Semester 3', year_level=2, term_type=Semester.TermType.ODD)

    role_ct, _ = Role.objects.get_or_create(codename='CLASS_TEACHER', defaults={'name': 'Class Teacher'})
    role_hod, _ = Role.objects.get_or_create(codename='HOD', defaults={'name': 'Head of Department'})
    role_student, _ = Role.objects.get_or_create(codename='STUDENT', defaults={'name': 'Student'})

    # Class Teacher
    user_ct = User.objects.create_user(username='ct_user', password='Password123!', user_type=User.UserType.FACULTY)
    RoleAssignment.objects.create(user=user_ct, role=role_ct, department_id=dept.id, status=RoleAssignment.Status.ACTIVE)

    # HOD
    user_hod = User.objects.create_user(username='hod_user', password='Password123!', user_type=User.UserType.FACULTY)
    RoleAssignment.objects.create(user=user_hod, role=role_hod, department_id=dept.id, status=RoleAssignment.Status.ACTIVE)

    # Student
    user_stu = User.objects.create_user(username='student_user', password='Password123!', user_type=User.UserType.STUDENT)
    RoleAssignment.objects.create(user=user_stu, role=role_student, status=RoleAssignment.Status.ACTIVE)

    student = Student.objects.create(
        user=user_stu,
        enrollment_no='EN26CSE001',
        application_id='APP26001',
        first_name='Rohan',
        last_name='Patil',
        display_name='Rohan Patil',
    )
    StudentEnrollment.objects.create(
        student=student,
        academic_year=year,
        department=dept,
        program=prog,
        semester=sem1,
        is_current=True,
    )

    return {
        'year': year,
        'dept': dept,
        'sem1': sem1,
        'sem2': sem2,
        'sem3': sem3,
        'student': student,
        'user_ct': user_ct,
        'user_hod': user_hod,
        'user_stu': user_stu,
    }


@pytest.mark.django_db
class TestGradeAndSGPACalculation:
    """Tests for 9-point grading and backlog aggregation."""

    def test_grade_for_marks_scale(self):
        # 9-point thresholds
        letter, gp, is_backlog = grade_for_marks(95)
        assert letter == 'O' and gp == 10 and not is_backlog

        letter, gp, is_backlog = grade_for_marks(82)
        assert letter == 'A+' and gp == 9 and not is_backlog

        letter, gp, is_backlog = grade_for_marks(71)
        assert letter == 'A' and gp == 8 and not is_backlog

        letter, gp, is_backlog = grade_for_marks(62)
        assert letter == 'B+' and gp == 7 and not is_backlog

        letter, gp, is_backlog = grade_for_marks(53)
        assert letter == 'B' and gp == 6 and not is_backlog

        letter, gp, is_backlog = grade_for_marks(46)
        assert letter == 'C' and gp == 5 and not is_backlog

        letter, gp, is_backlog = grade_for_marks(40)
        assert letter == 'P' and gp == 4 and not is_backlog

        letter, gp, is_backlog = grade_for_marks(32)
        assert letter == 'F' and gp == 0 and is_backlog

    def test_semester_sgpa_computation_and_pass_status(self, result_setup):
        student = result_setup['student']
        sem_res = SemesterResult.objects.create(
            student=student,
            academic_year=result_setup['year'],
            semester=result_setup['sem1'],
            exam_session='Winter 2026',
            is_published=True,
        )

        # Subject 1: 4 credits, Grade O (10 GP)
        SubjectResult.objects.create(
            semester_result=sem_res,
            course_code='CS101',
            course_name='Programming in C',
            credits=4,
            total_marks=92,
            grade_point=10,
            grade_letter='O',
            is_backlog=False,
        )

        # Subject 2: 4 credits, Grade A (8 GP)
        SubjectResult.objects.create(
            semester_result=sem_res,
            course_code='CS102',
            course_name='Discrete Mathematics',
            credits=4,
            total_marks=74,
            grade_point=8,
            grade_letter='A',
            is_backlog=False,
        )

        metrics = calculate_semester_metrics(sem_res.id)
        # SGPA: (4*10 + 4*8) / 8 = 72 / 8 = 9.00
        assert metrics.sgpa == Decimal('9.00')
        assert metrics.total_credits_earned == 8
        assert metrics.backlog_count == 0
        assert metrics.result_status == SemesterResult.ResultStatus.PASS

    def test_atkt_granted_for_under_4_backlogs(self, result_setup):
        student = result_setup['student']
        sem_res = SemesterResult.objects.create(
            student=student,
            academic_year=result_setup['year'],
            semester=result_setup['sem1'],
            exam_session='Winter 2026',
            is_published=True,
        )

        # 1 Passing subject
        SubjectResult.objects.create(
            semester_result=sem_res, course_code='CS101', course_name='Subject 1',
            credits=4, total_marks=80, grade_point=9, grade_letter='A+', is_backlog=False,
        )

        # 2 Backlogs
        SubjectResult.objects.create(
            semester_result=sem_res, course_code='CS102', course_name='Subject 2',
            credits=4, total_marks=25, grade_point=0, grade_letter='F', is_backlog=True,
        )
        SubjectResult.objects.create(
            semester_result=sem_res, course_code='CS103', course_name='Subject 3',
            credits=3, total_marks=20, grade_point=0, grade_letter='F', is_backlog=True,
        )

        metrics = calculate_semester_metrics(sem_res.id)
        assert metrics.backlog_count == 2
        assert metrics.result_status == SemesterResult.ResultStatus.ATKT


@pytest.mark.django_db
class TestEligibilityWorkflow:
    """Tests for multi-tier Class Teacher -> HOD eligibility approval."""

    def test_eligibility_multi_tier_approval_flow(self, api_client, result_setup):
        student = result_setup['student']
        sem2 = result_setup['sem2']

        # 1. System calculates eligibility
        ev = evaluate_student_eligibility(student, sem2)
        assert ev.calculated_status == EligibilityVerification.CalculatedStatus.ELIGIBLE
        assert not ev.final_eligible

        # 2. Class Teacher reviews and approves
        api_client.force_authenticate(user=result_setup['user_ct'])
        res_ct = api_client.post(
            f'/api/v1/results/eligibility/{ev.id}/review-class-teacher/',
            {'status': 'APPROVED', 'remarks': 'Attendance 85%, verified clear'}
        )
        assert res_ct.status_code == status.HTTP_200_OK
        data_ct = res_ct.json()
        assert data_ct['class_teacher_status'] == 'APPROVED'
        assert not data_ct['final_eligible']  # Requires HOD approval too

        # 3. HOD endorses
        api_client.force_authenticate(user=result_setup['user_hod'])
        res_hod = api_client.post(
            f'/api/v1/results/eligibility/{ev.id}/endorse-hod/',
            {'status': 'APPROVED', 'remarks': 'Endorsed for Semester 2'}
        )
        assert res_hod.status_code == status.HTTP_200_OK
        data_hod = res_hod.json()
        assert data_hod['hod_status'] == 'APPROVED'
        assert data_hod['final_eligible'] is True  # Both endorsed!

    def test_class_teacher_locked_once_approved_until_hod_flags(self, api_client, result_setup):
        """Teacher confirmation locks the record from teacher editing unless returned by HOD."""
        student = result_setup['student']
        sem2 = result_setup['sem2']
        ev = evaluate_student_eligibility(student, sem2)

        # Class teacher approves
        api_client.force_authenticate(user=result_setup['user_ct'])
        res1 = api_client.post(
            f'/api/v1/results/eligibility/{ev.id}/review-class-teacher/',
            {'status': 'APPROVED', 'remarks': 'Verified'}
        )
        assert res1.status_code == status.HTTP_200_OK

        # Teacher tries to edit again -> LOCKED!
        res2 = api_client.post(
            f'/api/v1/results/eligibility/{ev.id}/review-class-teacher/',
            {'status': 'FLAGGED', 'remarks': 'Trying to re-edit'}
        )
        assert res2.status_code == status.HTTP_400_BAD_REQUEST
        assert 'locked' in res2.json()['detail'].lower()

        # HOD sees an issue and flags it back to teacher
        api_client.force_authenticate(user=result_setup['user_hod'])
        res_hod_flag = api_client.post(
            f'/api/v1/results/eligibility/{ev.id}/endorse-hod/',
            {'status': 'FLAGGED', 'remarks': 'Backlog subject missing, please re-check'}
        )
        assert res_hod_flag.status_code == status.HTTP_200_OK
        assert res_hod_flag.json()['hod_status'] == 'FLAGGED'
        assert not res_hod_flag.json()['final_eligible']

        # Now Teacher can edit because HOD returned it!
        api_client.force_authenticate(user=result_setup['user_ct'])
        res3 = api_client.post(
            f'/api/v1/results/eligibility/{ev.id}/review-class-teacher/',
            {'status': 'FLAGGED', 'remarks': 'Re-checking student records after HOD notice'}
        )
        assert res3.status_code == status.HTTP_200_OK
        assert res3.json()['class_teacher_status'] == 'FLAGGED'

    def test_student_submit_marks_and_eligibility_integration(self, api_client, result_setup):
        """Year-change marks route to the queue; other sems record without verification."""
        api_client.force_authenticate(user=result_setup['user_stu'])
        payload = {
            'semester_number': 2,
            'exam_session': 'Summer 2027',
            'subjects': [
                {
                    'course_code': 'CS201',
                    'course_name': 'Data Structures',
                    'credits': 4,
                    'theory_marks': 45,
                    'mid1_marks': 15,
                    'mid2_marks': 16,
                    'total_marks': 76,
                },
            ]
        }
        res = api_client.post('/api/v1/results/semester-results/submit-marks/', payload, format='json')
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data['semester_result']['result_status'] == 'PASS'
        assert data['eligibility']['class_teacher_status'] == 'PENDING'
        assert not data['eligibility']['final_eligible']

        # Sem 1 marks record results but spawn no verification row.
        payload['semester_number'] = 1
        res2 = api_client.post('/api/v1/results/semester-results/submit-marks/', payload, format='json')
        assert res2.status_code == status.HTTP_200_OK
        assert res2.json()['eligibility'] is None

    def test_eligible_only_filter_for_accountant(self, api_client, result_setup):
        """Student directory with ?eligible_only=true returns only HOD-endorsed students."""
        student = result_setup['student']
        sem2 = result_setup['sem2']
        ev = evaluate_student_eligibility(student, sem2)

        # Before HOD endorsement -> 0 eligible
        api_client.force_authenticate(user=result_setup['user_ct'])
        res_before = api_client.get('/api/v1/students/?eligible_only=true')
        assert res_before.status_code == status.HTTP_200_OK
        assert len(res_before.json()['results']) == 0

        # Teacher approves, HOD approves
        api_client.post(f'/api/v1/results/eligibility/{ev.id}/review-class-teacher/', {'status': 'APPROVED'})
        api_client.force_authenticate(user=result_setup['user_hod'])
        api_client.post(f'/api/v1/results/eligibility/{ev.id}/endorse-hod/', {'status': 'APPROVED'})

        # Now student appears in eligible_only filter!
        res_after = api_client.get('/api/v1/students/?eligible_only=true')
        assert res_after.status_code == status.HTTP_200_OK
        assert len(res_after.json()['results']) == 1
        assert res_after.json()['results'][0]['id'] == str(student.id)
        assert res_after.json()['results'][0]['is_eligible'] is True

    def test_automatic_promotion_on_hod_approval_and_fee_payment(self, api_client, result_setup):
        """
        Per CONTEXT.md Sec 7:
        Eligibility approved -> fees set -> fees paid -> student automatically moves to next year/sem.
        """
        from apps.authentication.models import Role, RoleAssignment, User
        from apps.finance.models import PaymentLedger
        from apps.students.models import StudentEnrollment

        student = result_setup['student']
        sem2 = result_setup['sem2']
        ev = evaluate_student_eligibility(student, sem2)

        # 1. Teacher approves
        api_client.force_authenticate(user=result_setup['user_ct'])
        api_client.post(f'/api/v1/results/eligibility/{ev.id}/review-class-teacher/', {'status': 'APPROVED'})

        # 2. HOD approves -> student is final_eligible
        api_client.force_authenticate(user=result_setup['user_hod'])
        api_client.post(f'/api/v1/results/eligibility/{ev.id}/endorse-hod/', {'status': 'APPROVED'})

        # 3. Accountant records payment at fee desk
        user_acct = User.objects.create_user(username='test_acct_promo', email='acct@gceok.ac.in', password='p')
        r_acct, _ = Role.objects.get_or_create(codename='ACCOUNTANT', defaults={'name': 'Accountant'})
        RoleAssignment.objects.create(user=user_acct, role=r_acct, status=RoleAssignment.Status.ACTIVE)

        api_client.force_authenticate(user=user_acct)
        # Real desk flow: configure head, set assessment, then mark.
        from apps.finance.models import FeeHead
        FeeHead.objects.create(
            name='Tuition Fee', code='TUI-PROMO', academic_year=result_setup['year'],
            category_quota='ALL', amount='15000.00', allowed_amounts=[15000])
        assess = api_client.post('/api/v1/finance/assessments/', {
            'student': str(student.id), 'academic_year': str(result_setup['year'].id),
            'fee_breakdown': {'Tuition Fee': 15000}, 'total_fee': '15000.00',
        }, format='json')
        assert assess.status_code in (200, 201), assess.data
        payment_payload = {
            'student': str(student.id),
            'academic_year': str(result_setup['year'].id),
            'total_fee_due': '15000.00',
            'amount_paid': '15000.00',
            'payment_mode': 'ONLINE',
            'transaction_ref': 'TXN-PROMO-123',
            'payment_date': '2026-09-28',
            'remarks': 'Annual fee paid in full',
        }
        res_pay = api_client.post('/api/v1/finance/ledger/', payment_payload, format='json')
        assert res_pay.status_code == status.HTTP_201_CREATED
        assert res_pay.data['receipt_no'].startswith('GCOEK/')

        # 4. Verify automatic promotion:
        # Old enrollment (Sem 1) archived with PROMOTED and is_current=False
        old_enrollment = StudentEnrollment.objects.get(student=student, semester=result_setup['sem1'])
        assert old_enrollment.status == StudentEnrollment.Status.PROMOTED
        assert not old_enrollment.is_current

        # New enrollment (Sem 2) created with ACTIVE and is_current=True
        new_enrollment = StudentEnrollment.objects.get(student=student, semester=sem2)
        assert new_enrollment.status == StudentEnrollment.Status.ACTIVE
        assert new_enrollment.is_current


@pytest.mark.django_db
class TestDivisionTeacherAssignWithFacultyId:
    """HOD can assign by Faculty id (UI sends Faculty UUIDs, API wants Users)."""

    def test_patch_with_faculty_id_resolves_to_user(self, api_client):
        from apps.faculty.models import Faculty
        year = AcademicYear.objects.create(
            code='2027-28', name='AY 2027-28', start_date=datetime.date(2027, 7, 1),
            end_date=datetime.date(2028, 6, 30), is_current=False)
        dept = Department.objects.create(name='Test Dept', code='TST')
        sem1 = Semester.objects.create(number=9, name='S9', year_level=1, term_type='ODD')
        div = Division.objects.create(department=dept, academic_year=year, semester=sem1, name='A')
        hod = User.objects.create(username='hod_t', email='h@t.in', user_type='FACULTY')
        hod.set_password('TestPass12345!'); hod.save()
        role_hod, _ = Role.objects.get_or_create(codename='HOD', defaults={'name': 'HOD'})
        RoleAssignment.objects.create(user=hod, role=role_hod, department_id=dept.id, status='ACTIVE')
        Role.objects.get_or_create(codename='CLASS_TEACHER', defaults={'name': 'CT'})
        teacher = User.objects.create(username='teacher_t', email='t@t.in', user_type='FACULTY')
        teacher.set_password('TestPass12345!'); teacher.save()
        fac = Faculty.objects.create(
            user=teacher, employee_code='FAC_T_001', first_name='T', last_name='Each',
            department=dept, date_of_joining=datetime.date(2020, 1, 1),
            official_email='t@gceok.ac.in')
        api_client.force_authenticate(user=hod)
        res = api_client.patch(f'/api/v1/academic/divisions/{div.id}/',
                               {'class_teacher': str(fac.id)}, format='json')
        assert res.status_code == status.HTTP_200_OK, res.data
        div.refresh_from_db()
        assert div.class_teacher_id == teacher.id


@pytest.mark.django_db
class TestEligibilityInitialize:
    """Initialize bootstraps the verification queue for a class/department."""

    def _setup(self):
        from apps.students.models import Student, StudentEnrollment
        year = AcademicYear.objects.create(
            code='2028-29', name='AY 2028-29', start_date=datetime.date(2028, 7, 1),
            end_date=datetime.date(2029, 6, 30), is_current=False)
        dept = Department.objects.create(name='Init Dept', code='INI')
        prog = Program.objects.create(department=dept, name='B.Tech Ini', code='BTECH_INI')
        sem2 = Semester.objects.create(number=2, name='S2', year_level=1, term_type='EVEN')
        Semester.objects.create(number=3, name='S3', year_level=2, term_type='ODD')
        div = Division.objects.create(department=dept, academic_year=year, semester=sem2, name='A')
        teacher = User.objects.create(username='ct_init', email='c@i.in', user_type='FACULTY')
        teacher.set_password('TestPass12345!'); teacher.save()
        role_ct, _ = Role.objects.get_or_create(codename='CLASS_TEACHER', defaults={'name': 'CT'})
        RoleAssignment.objects.create(user=teacher, role=role_ct, department_id=dept.id,
                                      division_id=div.id, status='ACTIVE')
        student = Student.objects.create(first_name='S', last_name='T', application_id='EN26000991')
        StudentEnrollment.objects.create(
            student=student, academic_year=year, department=dept, program=prog,
            semester=sem2, division=div, status='ACTIVE', is_current=True)
        return teacher, student

    def test_odd_sem_students_skipped_by_initialize(self, api_client):
        """Sem-1 freshers never enter the queue, even via initialize."""
        import datetime
        from apps.academic_structure.models import AcademicYear, Department, Division, Program, Semester
        from apps.authentication.models import Role, RoleAssignment, User
        from apps.students.models import Student, StudentEnrollment
        year = AcademicYear.objects.create(
            code='2034-35', name='AY 2034-35', start_date=datetime.date(2034, 7, 1),
            end_date=datetime.date(2035, 6, 30), is_current=False)
        dept = Department.objects.create(name='Skip Dept', code='SKP')
        prog = Program.objects.create(department=dept, name='B.Tech S', code='BTECH_S')
        sem1 = Semester.objects.create(number=1, name='S1', year_level=1, term_type='ODD')
        div = Division.objects.create(department=dept, academic_year=year, semester=sem1, name='A')
        teacher = User.objects.create(username='ct_skip', email='s@k.in', user_type='FACULTY')
        teacher.set_password('TestPass12345!'); teacher.save()
        role_ct, _ = Role.objects.get_or_create(codename='CLASS_TEACHER', defaults={'name': 'CT'})
        RoleAssignment.objects.create(user=teacher, role=role_ct, department_id=dept.id,
                                      division_id=div.id, status='ACTIVE')
        student = Student.objects.create(first_name='F', last_name='R', application_id='EN34001')
        StudentEnrollment.objects.create(
            student=student, academic_year=year, department=dept, program=prog,
            semester=sem1, division=div, status='ACTIVE', is_current=True)
        api_client.force_authenticate(user=teacher)
        res = api_client.post('/api/v1/results/eligibility/initialize/', {}, format='json')
        assert res.status_code == status.HTTP_200_OK, res.data
        assert res.data['created'] == 0
        assert res.data['total'] == 0

    def test_teacher_initialize_creates_and_is_idempotent(self, api_client):
        teacher, student = self._setup()
        api_client.force_authenticate(user=teacher)
        r1 = api_client.post('/api/v1/results/eligibility/initialize/', {}, format='json')
        assert r1.status_code == status.HTTP_200_OK, r1.data
        assert r1.data['created'] == 1
        assert EligibilityVerification.objects.filter(student=student).count() == 1
        r2 = api_client.post('/api/v1/results/eligibility/initialize/', {}, format='json')
        assert r2.data['created'] == 0
        assert EligibilityVerification.objects.filter(student=student).count() == 1

    def test_student_cannot_initialize(self, api_client):
        teacher, _ = self._setup()
        s_user = User.objects.create(username='s_init', email='s@i.in', user_type='STUDENT')
        s_user.set_password('TestPass12345!'); s_user.save()
        role_s, _ = Role.objects.get_or_create(codename='STUDENT', defaults={'name': 'Student'})
        RoleAssignment.objects.create(user=s_user, role=role_s, status='ACTIVE')
        api_client.force_authenticate(user=s_user)
        res = api_client.post('/api/v1/results/eligibility/initialize/', {}, format='json')
        assert res.status_code == status.HTTP_403_FORBIDDEN

    def test_marks_correction_audited_with_old_new(self, api_client, result_setup):
        """ARCH 24 evidence: changed marks write old/new audit entries."""
        from apps.audit.models import AuditLog
        from apps.results.services import submit_semester_marks
        student = result_setup['student']
        first = {'course_code': 'CS101', 'course_name': 'C', 'credits': 4,
                 'theory_marks': 45, 'mid1_marks': 15, 'mid2_marks': 16, 'total_marks': 76}
        submit_semester_marks(student, 1, 'Winter 2026', [dict(first)])
        assert not AuditLog.objects.filter(target_type='SubjectResult').exists()
        changed = dict(first, theory_marks=50, total_marks=81)
        submit_semester_marks(student, 1, 'Winter 2026', [changed])
        entry = AuditLog.objects.filter(target_type='SubjectResult').first()
        assert entry is not None
        assert entry.old_value['total_marks'] == '76.0'
        assert entry.new_value['total_marks'] == '81.0'


@pytest.mark.django_db
class TestEligibilityDirectWriteBlocked:
    """ARCH 17: no direct PUT/PATCH/DELETE on verification rows."""

    def test_direct_patch_put_delete_return_405(self, api_client):
        from apps.results.services import evaluate_student_eligibility
        import datetime
        from apps.academic_structure.models import AcademicYear, Department, Division, Program, Semester
        from apps.students.models import Student, StudentEnrollment
        year = AcademicYear.objects.create(
            code='2036-37', name='AY 2036-37', start_date=datetime.date(2036, 7, 1),
            end_date=datetime.date(2037, 6, 30), is_current=False)
        dept = Department.objects.create(name='Blk Dept', code='BLK')
        prog = Program.objects.create(department=dept, name='B.Tech B', code='BTECH_BLK')
        sem2 = Semester.objects.create(number=2, name='S2', year_level=1, term_type='EVEN')
        Semester.objects.create(number=3, name='S3', year_level=2, term_type='ODD')
        div = Division.objects.create(department=dept, academic_year=year, semester=sem2, name='A')
        teacher = User.objects.create(username='ct_blk', email='cb@x.in', user_type='FACULTY')
        teacher.set_password('TestPass12345!'); teacher.save()
        role_ct, _ = Role.objects.get_or_create(codename='CLASS_TEACHER', defaults={'name': 'CT'})
        RoleAssignment.objects.create(user=teacher, role=role_ct, department_id=dept.id,
                                      division_id=div.id, status='ACTIVE')
        div.class_teacher = teacher
        div.save(update_fields=['class_teacher'])
        student = Student.objects.create(first_name='B', last_name='L', application_id='EN36001')
        StudentEnrollment.objects.create(
            student=student, academic_year=year, department=dept, program=prog,
            semester=sem2, division=div, status='ACTIVE', is_current=True)
        ev = evaluate_student_eligibility(student, Semester.objects.get(number=3))
        api_client.force_authenticate(user=teacher)
        assert api_client.patch(
            f'/api/v1/results/eligibility/{ev.id}/',
            {'final_eligible': True}, format='json').status_code == status.HTTP_405_METHOD_NOT_ALLOWED
        assert api_client.put(
            f'/api/v1/results/eligibility/{ev.id}/',
            {'final_eligible': True}, format='json').status_code == status.HTTP_405_METHOD_NOT_ALLOWED
        assert api_client.delete(
            f'/api/v1/results/eligibility/{ev.id}/').status_code == status.HTTP_405_METHOD_NOT_ALLOWED
        # Workflow buttons still work.
        ok = api_client.post(
            f'/api/v1/results/eligibility/{ev.id}/review-class-teacher/',
            {'status': 'APPROVED', 'remarks': 'fine'}, format='json')
        assert ok.status_code == status.HTTP_200_OK


@pytest.mark.django_db
class TestGraduationConfirm:
    """HOD confirms graduation for Sem-8 PASS students."""

    def _setup(self):
        import datetime
        from apps.academic_structure.models import AcademicYear, Department, Division, Program, Semester
        year = AcademicYear.objects.create(
            code='2035-36', name='AY 2035-36', start_date=datetime.date(2035, 7, 1),
            end_date=datetime.date(2036, 6, 30), is_current=False)
        dept = Department.objects.create(name='Grad Dept', code='GRD')
        prog = Program.objects.create(department=dept, name='B.Tech G', code='BTECH_G')
        sem8 = Semester.objects.create(number=8, name='S8', year_level=4, term_type='EVEN')
        div = Division.objects.create(department=dept, academic_year=year, semester=sem8, name='A')
        hod = User.objects.create(username='hod_grd', email='hg@x.in', user_type='FACULTY')
        hod.set_password('TestPass12345!'); hod.save()
        role_hod, _ = Role.objects.get_or_create(codename='HOD', defaults={'name': 'HOD'})
        RoleAssignment.objects.create(user=hod, role=role_hod, department_id=dept.id, status='ACTIVE')
        teacher = User.objects.create(username='ct_grd', email='cg@x.in', user_type='FACULTY')
        teacher.set_password('TestPass12345!'); teacher.save()
        role_ct, _ = Role.objects.get_or_create(codename='CLASS_TEACHER', defaults={'name': 'CT'})
        RoleAssignment.objects.create(user=teacher, role=role_ct, department_id=dept.id,
                                      division_id=div.id, status='ACTIVE')
        student = Student.objects.create(first_name='G', last_name='R', application_id='EN35001')
        StudentEnrollment.objects.create(
            student=student, academic_year=year, department=dept, program=prog,
            semester=sem8, division=div, status='ACTIVE', is_current=True)
        sem_res = SemesterResult.objects.create(
            student=student, academic_year=year, semester=sem8, exam_session='Summer',
            sgpa='8.50', total_credits_registered=20, total_credits_earned=20,
            backlog_count=0, result_status=SemesterResult.ResultStatus.PASS,
            is_published=True)
        return hod, teacher, student, sem_res

    def test_pending_lists_and_hod_confirms(self, api_client):
        hod, _, student, sem_res = self._setup()
        api_client.force_authenticate(user=hod)
        lst = api_client.get('/api/v1/results/semester-results/graduation-pending/')
        assert lst.status_code == status.HTTP_200_OK, lst.data
        assert [r['id'] for r in (lst.data['results'] if isinstance(lst.data, dict) else lst.data)] == [str(sem_res.id)]
        res = api_client.post(
            f'/api/v1/results/semester-results/{sem_res.id}/confirm-graduation/', {}, format='json')
        assert res.status_code == status.HTTP_200_OK, res.data
        student.refresh_from_db()
        assert student.status == 'PASSED_OUT'
        lst2 = api_client.get('/api/v1/results/semester-results/graduation-pending/')
        rows = lst2.data['results'] if isinstance(lst2.data, dict) else lst2.data
        assert rows == []

    def test_teacher_cannot_confirm(self, api_client):
        _, teacher, _, sem_res = self._setup()
        api_client.force_authenticate(user=teacher)
        res = api_client.post(
            f'/api/v1/results/semester-results/{sem_res.id}/confirm-graduation/', {}, format='json')
        assert res.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestAssignedTeacherOnlyReview:
    """Teacher step is locked to the student's assigned division teacher."""

    def _setup(self):
        import datetime
        from apps.academic_structure.models import AcademicYear, Department, Division, Program, Semester
        from apps.results.services import evaluate_student_eligibility
        from apps.students.models import Student, StudentEnrollment
        year = AcademicYear.objects.create(
            code='2032-33', name='AY 2032-33', start_date=datetime.date(2032, 7, 1),
            end_date=datetime.date(2033, 6, 30), is_current=False)
        dept = Department.objects.create(name='Assign Dept', code='ASG')
        prog = Program.objects.create(department=dept, name='B.Tech A', code='BTECH_A')
        sem1 = Semester.objects.create(number=41, name='S41', year_level=1, term_type='ODD')
        sem2 = Semester.objects.create(number=42, name='S42', year_level=1, term_type='EVEN')
        div_a = Division.objects.create(department=dept, academic_year=year, semester=sem1, name='A')
        div_b = Division.objects.create(department=dept, academic_year=year, semester=sem1, name='B')
        role_ct, _ = Role.objects.get_or_create(codename='CLASS_TEACHER', defaults={'name': 'CT'})
        role_hod, _ = Role.objects.get_or_create(codename='HOD', defaults={'name': 'HOD'})
        t_a = User.objects.create(username='ct_a', email='a@x.in', user_type='FACULTY')
        t_a.set_password('TestPass12345!'); t_a.save()
        t_b = User.objects.create(username='ct_b', email='b@x.in', user_type='FACULTY')
        t_b.set_password('TestPass12345!'); t_b.save()
        hod = User.objects.create(username='hod_asg', email='h@x.in', user_type='FACULTY')
        hod.set_password('TestPass12345!'); hod.save()
        RoleAssignment.objects.create(user=t_a, role=role_ct, department_id=dept.id,
                                      division_id=div_a.id, status='ACTIVE')
        RoleAssignment.objects.create(user=t_b, role=role_ct, department_id=dept.id,
                                      division_id=div_b.id, status='ACTIVE')
        RoleAssignment.objects.create(user=hod, role=role_hod, department_id=dept.id, status='ACTIVE')
        div_a.class_teacher = t_a
        div_a.save(update_fields=['class_teacher'])
        student = Student.objects.create(first_name='S', last_name='A', application_id='EN32A')
        StudentEnrollment.objects.create(
            student=student, academic_year=year, department=dept, program=prog,
            semester=sem1, division=div_a, status='ACTIVE', is_current=True)
        ev = evaluate_student_eligibility(student, sem2)
        return t_a, t_b, hod, ev

    def test_assigned_teacher_can_review(self, api_client):
        t_a, _, _, ev = self._setup()
        api_client.force_authenticate(user=t_a)
        res = api_client.post(
            f'/api/v1/results/eligibility/{ev.id}/review-class-teacher/',
            {'status': 'APPROVED', 'remarks': 'ok'}, format='json')
        assert res.status_code == status.HTTP_200_OK, res.data

    def test_other_division_teacher_forbidden(self, api_client):
        _, t_b, _, ev = self._setup()
        api_client.force_authenticate(user=t_b)
        res = api_client.post(
            f'/api/v1/results/eligibility/{ev.id}/review-class-teacher/',
            {'status': 'APPROVED', 'remarks': 'ok'}, format='json')
        # 403 forbidden, or 404 when scope filtering hides the row entirely.
        assert res.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)

    def test_hod_must_use_endorse_step(self, api_client):
        _, _, hod, ev = self._setup()
        api_client.force_authenticate(user=hod)
        res = api_client.post(
            f'/api/v1/results/eligibility/{ev.id}/review-class-teacher/',
            {'status': 'APPROVED', 'remarks': 'ok'}, format='json')
        assert res.status_code == status.HTTP_403_FORBIDDEN


