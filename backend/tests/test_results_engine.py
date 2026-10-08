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

    def test_admission_form_data_and_pdf_download(self, api_client, result_setup):
        """
        Tests that an eligible student can retrieve their admission verification
        form data and download the official 1-page PDF clearance with CT/HOD timestamps.
        """
        student = result_setup['student']
        sem2 = result_setup['sem2']

        # 1. System calculates eligibility & teacher approves
        ev = evaluate_student_eligibility(student, sem2)
        api_client.force_authenticate(user=result_setup['user_ct'])
        api_client.post(f'/api/v1/results/eligibility/{ev.id}/review-class-teacher/', {'status': 'APPROVED'})

        # 2. HOD endorses
        api_client.force_authenticate(user=result_setup['user_hod'])
        api_client.post(f'/api/v1/results/eligibility/{ev.id}/endorse-hod/', {'status': 'APPROVED'})

        # 3. Student requests their admission form data
        api_client.force_authenticate(user=result_setup['user_stu'])
        res_data = api_client.get('/api/v1/results/eligibility/admission-form-data/')
        assert res_data.status_code == status.HTTP_200_OK
        data = res_data.json()
        assert data['full_name'] == student.display_name
        assert data['final_eligible'] is True
        assert data['class_teacher_verification']['is_approved'] is True
        assert data['class_teacher_verification']['timestamp'] != '—'
        assert data['hod_verification']['is_approved'] is True
        assert data['hod_verification']['timestamp'] != '—'
        assert 'Application Form for Admission' in data['form_title']

        # 4. Student downloads the PDF
        res_pdf = api_client.get('/api/v1/results/eligibility/admission-form-pdf/')
        assert res_pdf.status_code == status.HTTP_200_OK
        assert res_pdf['Content-Type'] == 'application/pdf'
        assert 'attachment; filename=' in res_pdf['Content-Disposition']
        assert len(res_pdf.content) > 1000

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
        # Required workflow: teacher assigned to the class before verification.
        div.class_teacher = teacher
        div.save(update_fields=['class_teacher'])
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
class TestVerificationRequiresClassTeacher:
    """Verification cannot start for a class with no assigned teacher."""

    def _setup(self):
        import datetime
        from apps.academic_structure.models import AcademicYear, Department, Division, Program, Semester
        from apps.authentication.models import Role, RoleAssignment, User
        from apps.students.models import Student, StudentEnrollment
        year = AcademicYear.objects.create(
            code='2040-41', name='AY 2040-41', start_date=datetime.date(2040, 7, 1),
            end_date=datetime.date(2041, 6, 30), is_current=False)
        dept = Department.objects.create(name='Gate Dept', code='GTE')
        prog = Program.objects.create(department=dept, name='B.Tech G', code='BTECH_GTE')
        sem2 = Semester.objects.create(number=2, name='S2', year_level=1, term_type='EVEN')
        Semester.objects.create(number=3, name='S3', year_level=2, term_type='ODD')
        div = Division.objects.create(department=dept, academic_year=year, semester=sem2, name='A')
        hod = User.objects.create_user(username='hod_gate', password='Password123!', user_type=User.UserType.FACULTY)
        role_hod, _ = Role.objects.get_or_create(codename='HOD', defaults={'name': 'HOD'})
        RoleAssignment.objects.create(user=hod, role=role_hod, department_id=dept.id, status='ACTIVE')
        student = Student.objects.create(first_name='G', last_name='S', application_id='ENGATE01')
        StudentEnrollment.objects.create(
            student=student, academic_year=year, department=dept, program=prog,
            semester=sem2, division=div, status='ACTIVE', is_current=True)
        return hod, div

    def test_start_blocked_without_teacher(self, api_client):
        hod, div = self._setup()
        api_client.force_authenticate(user=hod)
        res = api_client.post(
            '/api/v1/results/eligibility/start-class-verification/',
            {'division_id': str(div.id)}, format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert 'class teacher' in str(res.data).lower()

    def test_start_allowed_after_teacher_assigned(self, api_client):
        from apps.authentication.models import User
        hod, div = self._setup()
        teacher = User.objects.create_user(username='ct_gate', password='Password123!', user_type=User.UserType.FACULTY)
        div.class_teacher = teacher
        div.save(update_fields=['class_teacher'])
        api_client.force_authenticate(user=hod)
        res = api_client.post(
            '/api/v1/results/eligibility/start-class-verification/',
            {'division_id': str(div.id)}, format='json')
        assert res.status_code == status.HTTP_200_OK, res.data
        assert res.data['created'] == 1

    def test_initialize_skips_teacherless_division(self, api_client):
        hod, div = self._setup()
        api_client.force_authenticate(user=hod)
        res = api_client.post('/api/v1/results/eligibility/initialize/', {}, format='json')
        assert res.status_code == status.HTTP_200_OK, res.data
        assert res.data['created'] == 0
        assert res.data['skipped_no_teacher'] == 1

    def test_classes_card_flags_no_teacher(self, api_client):
        hod, div = self._setup()
        api_client.force_authenticate(user=hod)
        data = api_client.get('/api/v1/results/eligibility/classes/').json()
        card = next((c for c in data if c['division_id'] == str(div.id)), None)
        assert card is not None
        assert card['has_class_teacher'] is False
        assert card['can_start_verification'] is False


@pytest.mark.django_db
class TestBacklogSubmitUsesClassWindow:
    """Backlog fills ride the open class window, never a stale first-year cycle.

    Regression: a senior in Sem-6 Div A (verification started → EV target 7)
    filling Sem-2 backlog was 403'd demanding an EV row targeting Sem 3.
    """

    def _setup(self):
        import datetime
        from apps.academic_structure.models import AcademicYear, Department, Division, Program, Semester
        from apps.authentication.models import User
        from apps.students.models import Student, StudentEnrollment
        year = AcademicYear.objects.create(
            code='2041-42', name='AY 2041-42', start_date=datetime.date(2041, 7, 1),
            end_date=datetime.date(2042, 6, 30), is_current=False)
        dept = Department.objects.create(name='Backlog Dept', code='BLG')
        prog = Program.objects.create(department=dept, name='B.Tech B', code='BTECH_BLG')
        sem2 = Semester.objects.create(number=2, name='S2', year_level=1, term_type='EVEN')
        Semester.objects.create(number=3, name='S3', year_level=2, term_type='ODD')
        sem6 = Semester.objects.create(number=6, name='S6', year_level=3, term_type='EVEN')
        sem7 = Semester.objects.create(number=7, name='S7', year_level=4, term_type='ODD')
        div6 = Division.objects.create(department=dept, academic_year=year, semester=sem6, name='A')
        div2 = Division.objects.create(department=dept, academic_year=year, semester=sem2, name='A')

        def _student(username, app_id, div, sem):
            u = User.objects.create_user(username=username, password='Password123!', user_type=User.UserType.STUDENT)
            s = Student.objects.create(
                user=u, first_name='S', last_name=username, display_name=username,
                enrollment_no='EN' + app_id, application_id=app_id)
            StudentEnrollment.objects.create(
                student=s, academic_year=year, department=dept, program=prog,
                semester=sem, division=div, status='ACTIVE', is_current=True)
            return u, s
        return year, dept, sem7, div6, div2, _student

    def _submit(self, api_client, sem_num, passed=True):
        th, m1, m2 = (45, 15, 16) if passed else (10, 5, 5)
        return api_client.post('/api/v1/results/semester-results/submit-marks/', {
            'semester_number': sem_num, 'exam_session': 'Winter 2041',
            'subjects': [{'course_code': 'BLG201', 'course_name': 'Backlog Subject',
                          'credits': 3, 'theory_marks': th,
                          'mid1_marks': m1, 'mid2_marks': m2}],
        }, format='json')

    def test_backlog_allowed_when_window_open_no_stale_birth(self, api_client):
        from apps.results.services import evaluate_student_eligibility
        from apps.results.models import EligibilityVerification
        year, dept, sem7, div6, div2, mk = self._setup()
        u, s = mk('senior_bl', 'ENBLO01', div6, div6.semester)
        evaluate_student_eligibility(s, sem7)  # HOD opened the Sem-6 class window
        api_client.force_authenticate(user=u)
        res = self._submit(api_client, 2)
        assert res.status_code == status.HTTP_200_OK, res.data
        # No stale Sem-3 cycle birthed for the senior.
        assert not EligibilityVerification.objects.filter(
            student=s, target_semester__number=3).exists()
        assert EligibilityVerification.objects.filter(
            student=s, target_semester__number=7).count() == 1

    def test_backlog_blocked_when_window_closed(self, api_client):
        year, dept, sem7, div6, div2, mk = self._setup()
        u, s = mk('senior_nb', 'ENBLO02', div6, div6.semester)
        api_client.force_authenticate(user=u)
        res = self._submit(api_client, 2)
        assert res.status_code == status.HTTP_403_FORBIDDEN
        assert 'verification' in str(res.data).lower()

    def test_current_fill_still_gated(self, api_client):
        from apps.results.services import evaluate_student_eligibility
        from apps.academic_structure.models import Semester as _Sem
        year, dept, sem7, div6, div2, mk = self._setup()
        u, s = mk('junior_bl', 'ENBLO03', div2, div2.semester)
        api_client.force_authenticate(user=u)
        assert self._submit(api_client, 2).status_code == status.HTTP_403_FORBIDDEN
        evaluate_student_eligibility(s, _Sem.objects.get(number=3))
        res = self._submit(api_client, 2)
        assert res.status_code == status.HTTP_200_OK, res.data

    def test_backlog_fail_refreshes_window_counts(self, api_client):
        from apps.results.services import evaluate_student_eligibility
        from apps.results.models import EligibilityVerification
        year, dept, sem7, div6, div2, mk = self._setup()
        u, s = mk('senior_fb', 'ENBLO04', div6, div6.semester)
        ev = evaluate_student_eligibility(s, sem7)
        assert ev.active_backlog_count == 0
        api_client.force_authenticate(user=u)
        res = self._submit(api_client, 2, passed=False)
        assert res.status_code == status.HTTP_200_OK, res.data
        ev.refresh_from_db()
        assert ev.active_backlog_count == 1


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


class TestClassVerificationWorkflow:
    """Tests for class cards, roster pipeline stages, and per-class verification start."""

    def test_classes_and_roster_workflow(self, api_client, result_setup):
        from apps.academic_structure.models import Division
        user_ct = result_setup['user_ct']
        user_hod = result_setup['user_hod']
        student = result_setup['student']
        div = Division.objects.create(
            department=result_setup['dept'],
            academic_year=result_setup['year'],
            semester=result_setup['sem2'],
            name='A',
            class_teacher=user_ct,
        )
        enr = student.enrollments.filter(is_current=True).first()
        enr.semester = result_setup['sem2']
        enr.division = div
        enr.save(update_fields=['semester', 'division'])

        # 1. CT checks /classes/
        api_client.force_authenticate(user=user_ct)
        res_classes = api_client.get('/api/v1/results/eligibility/classes/')
        assert res_classes.status_code == status.HTTP_200_OK
        data = res_classes.json()
        assert len(data) >= 1
        cls_card = next((c for c in data if c['division_id'] == str(div.id)), None)
        assert cls_card is not None
        assert cls_card['total_students'] >= 1
        assert 'results_filled_count' in cls_card
        assert 'teacher_approved_count' in cls_card
        assert 'can_start_verification' in cls_card

        # 2. CT checks /class-roster/
        res_roster = api_client.get(f'/api/v1/results/eligibility/class-roster/?division_id={div.id}')
        assert res_roster.status_code == status.HTTP_200_OK
        roster = res_roster.json()
        assert roster['total_students'] >= 1
        stu_entry = next((s for s in roster['students'] if s['student_id'] == str(student.id)), None)
        assert stu_entry is not None
        assert 'pipeline_stage' in stu_entry
        assert 'result_filled' in stu_entry
        assert 'final_eligible' in stu_entry

        # 3. HOD starts class verification
        api_client.force_authenticate(user=user_hod)
        res_start = api_client.post(
            '/api/v1/results/eligibility/start-class-verification/',
            {'division_id': str(div.id)}, format='json')
        assert res_start.status_code == status.HTTP_200_OK
        assert 'created' in res_start.json()


@pytest.mark.django_db
class TestPromotedStudentsVisibleInRoster:
    """A student promoted out of a class must still show in that class roster
    (with the new semester), and staff names must be Faculty display names."""

    def _setup(self):
        import datetime
        from apps.faculty.models import Faculty
        year = AcademicYear.objects.create(
            code='2026-27', name='2026-2027',
            start_date=datetime.date(2026, 7, 1), end_date=datetime.date(2027, 6, 30),
            is_current=True)
        dept = Department.objects.create(name='Electronics and Telecommunication', code='ETC')
        prog = Program.objects.create(department=dept, name='B.Tech ETC', code='BTECH_ETC')
        sem6 = Semester.objects.create(number=66, name='S66', year_level=3, term_type='EVEN')
        sem7 = Semester.objects.create(number=67, name='S67', year_level=4, term_type='ODD')
        div = Division.objects.create(department=dept, academic_year=year, semester=sem6, name='A')
        hod = User.objects.create_user(username='hod_prom', password='Password123!', user_type=User.UserType.FACULTY)
        role_hod, _ = Role.objects.get_or_create(codename='HOD', defaults={'name': 'HOD'})
        RoleAssignment.objects.create(user=hod, role=role_hod, department_id=dept.id, status='ACTIVE')
        teacher = User.objects.create_user(username='faculty_prom', password='Password123!', user_type=User.UserType.FACULTY)
        Faculty.objects.create(
            user=teacher, employee_code='FAC_PROM_001', first_name='Sneha', last_name='Deshmukh',
            display_name='Sneha Deshmukh', department=dept,
            date_of_joining=datetime.date(2020, 1, 1), official_email='sneha@gceok.ac.in')
        div.class_teacher = teacher
        div.save(update_fields=['class_teacher'])
        # One student stays, one gets promoted Sem 6 -> Sem 7 (no Sem 7 division).
        stayer = Student.objects.create(
            first_name='Stay', last_name='Er', display_name='Stay Er',
            enrollment_no='EN66STAY01', application_id='APP66S01')
        StudentEnrollment.objects.create(
            student=stayer, academic_year=year, department=dept, program=prog,
            semester=sem6, division=div, status='ACTIVE', is_current=True)
        mover = Student.objects.create(
            first_name='Move', last_name='Er', display_name='Move Er',
            enrollment_no='EN66MOVE01', application_id='APP66M01')
        old = StudentEnrollment.objects.create(
            student=mover, academic_year=year, department=dept, program=prog,
            semester=sem6, division=div, status='ACTIVE', is_current=True)
        old.is_current = False
        old.status = StudentEnrollment.Status.PROMOTED
        old.save(update_fields=['is_current', 'status'])
        StudentEnrollment.objects.create(
            student=mover, academic_year=year, department=dept, program=prog,
            semester=sem7, division=None, status='ACTIVE', is_current=True)
        return hod, div, stayer, mover

    def test_roster_lists_promoted_student_with_new_sem(self, api_client):
        hod, div, stayer, mover = self._setup()
        api_client.force_authenticate(user=hod)
        res = api_client.get(f'/api/v1/results/eligibility/class-roster/?division_id={div.id}')
        assert res.status_code == status.HTTP_200_OK, res.data
        roster = res.json()
        current_ids = [s['student_id'] for s in roster['students']]
        assert str(stayer.id) in current_ids
        assert str(mover.id) not in current_ids
        assert roster['total_students'] == 1
        promoted = roster['promoted_students']
        assert len(promoted) == 1
        row = promoted[0]
        assert row['student_id'] == str(mover.id)
        assert row['student_name'] == 'Move Er'
        assert row['current_semester'] == 67
        assert row['pipeline_stage'] == 'PROMOTED'
        assert row['moved_up'] is True
        assert row['can_review_teacher'] is False
        assert row['can_endorse_hod'] is False

    def test_classes_list_shows_faculty_display_name(self, api_client):
        hod, div, stayer, mover = self._setup()
        api_client.force_authenticate(user=hod)
        res = api_client.get('/api/v1/results/eligibility/classes/')
        assert res.status_code == status.HTTP_200_OK
        cls_card = next((c for c in res.json() if c['division_id'] == str(div.id)), None)
        assert cls_card is not None
        assert cls_card['class_teacher_name'] == 'Sneha Deshmukh'



