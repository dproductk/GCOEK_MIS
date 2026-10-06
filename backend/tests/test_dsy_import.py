"""
Automated tests for Direct Second Year (DSY / Lateral Entry) Admission & Onboarding.
Tests:
- Upload with admission_type='DIRECT_SECOND_YEAR'
- Committing batch creates student with is_direct_second_year=True
- Student is enrolled in Semester 3 (SY / Year Level 2)
- Student filtering by FY / SY / TY
- HOD assignment of Division and LabBatch
"""
import datetime
import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.academic_structure.models import AcademicYear, Department, Division, LabBatch, Program, Semester
from apps.admissions.models import ImportBatch, ImportRow
from apps.authentication.models import Role, RoleAssignment, User
from apps.students.models import Student, StudentEnrollment


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def dsy_setup(db):
    year = AcademicYear.objects.create(
        code='2026-27', name='Academic Year 2026-2027',
        start_date=datetime.date(2026, 7, 1), end_date=datetime.date(2027, 6, 30),
        is_current=True,
    )
    dept_cs = Department.objects.create(name='Computer Science and Engineering', code='CSE', choice_code='627024210')
    prog_cs = Program.objects.create(department=dept_cs, name='B.Tech CSE', code='BTECH_CSE')
    sem1 = Semester.objects.create(number=1, name='Semester 1', year_level=1, term_type=Semester.TermType.ODD)
    sem3 = Semester.objects.create(number=3, name='Semester 3', year_level=2, term_type=Semester.TermType.ODD)

    div_cs_3a = Division.objects.create(department=dept_cs, academic_year=year, semester=sem3, name='A')
    div_cs_3b = Division.objects.create(department=dept_cs, academic_year=year, semester=sem3, name='B')
    batch_3a1 = LabBatch.objects.create(division=div_cs_3a, name='A1', seat_capacity=20)

    role_admin_head, _ = Role.objects.get_or_create(codename='ADMIN_HEAD', defaults={'name': 'Administrative Head'})
    role_hod, _ = Role.objects.get_or_create(codename='HOD', defaults={'name': 'Head of Department'})
    role_student, _ = Role.objects.get_or_create(codename='STUDENT', defaults={'name': 'Student'})

    user_admin_head = User.objects.create_user(username='admin_head_dsy', password='Password123!', user_type=User.UserType.SYSADMIN)
    RoleAssignment.objects.create(user=user_admin_head, role=role_admin_head, status=RoleAssignment.Status.ACTIVE)

    user_hod = User.objects.create_user(username='hod_cs_dsy', password='Password123!', user_type=User.UserType.FACULTY)
    RoleAssignment.objects.create(user=user_hod, role=role_hod, department_id=dept_cs.id, status=RoleAssignment.Status.ACTIVE)

    return {
        'year': year,
        'dept_cs': dept_cs,
        'prog_cs': prog_cs,
        'sem1': sem1,
        'sem3': sem3,
        'div_cs_3a': div_cs_3a,
        'div_cs_3b': div_cs_3b,
        'batch_3a1': batch_3a1,
        'user_admin_head': user_admin_head,
        'user_hod': user_hod,
    }


SAMPLE_DSY_CSV = (
    "Application ID,Candidate Name,Gender,Category,Mobile No,E-Mail ID,Choice Code,Course Name,Seat Type,Admission Date,Diploma Board,Diploma Percentage\n"
    "DSE26109999,Aarav Santosh Shinde,Male,OPEN,9876543210,aarav@example.com,627024210,Computer Science and Engineering,GOPENH,28/08/2026,MSBTE,88.40\n"
)


@pytest.mark.django_db
class TestDSYOnboardingPipeline:
    def test_dsy_upload_and_commit_enrolls_into_sem3(self, api_client, dsy_setup):
        api_client.force_authenticate(user=dsy_setup['user_admin_head'])

        csv_file = SAMPLE_DSY_CSV.encode('utf-8')
        from django.core.files.uploadedfile import SimpleUploadedFile
        upload = SimpleUploadedFile('dsy_merit_list.csv', csv_file, content_type='text/csv')

        res_upload = api_client.post(
            '/api/v1/admissions/batches/upload/',
            {'file': upload, 'admission_type': 'DIRECT_SECOND_YEAR'},
            format='multipart',
        )
        assert res_upload.status_code == status.HTTP_201_CREATED
        batch_id = res_upload.data['id']
        assert res_upload.data['admission_type'] == 'DIRECT_SECOND_YEAR'
        assert res_upload.data['valid_rows'] == 1

        # Commit batch
        res_commit = api_client.post(f'/api/v1/admissions/batches/{batch_id}/commit/')
        assert res_commit.status_code == status.HTTP_200_OK

        # Verify student created and marked as DSY
        student = Student.objects.get(application_id='DSE26109999')
        assert student.is_direct_second_year is True

        # Verify enrolled in Semester 3 (SY)
        enrollment = StudentEnrollment.objects.get(student=student, is_current=True)
        assert enrollment.semester.number == 3
        assert enrollment.semester.year_level == 2

    def test_student_filtering_by_year_level(self, api_client, dsy_setup):
        api_client.force_authenticate(user=dsy_setup['user_admin_head'])

        # Create 1 FY student and 1 SY (DSY) student
        s_fy = Student.objects.create(application_id='EN26100001', first_name='FY', last_name='Student', is_direct_second_year=False)
        StudentEnrollment.objects.create(
            student=s_fy, academic_year=dsy_setup['year'], department=dsy_setup['dept_cs'],
            program=dsy_setup['prog_cs'], semester=dsy_setup['sem1'], is_current=True
        )

        s_sy = Student.objects.create(application_id='DSE26100002', first_name='SY', last_name='Student', is_direct_second_year=True)
        StudentEnrollment.objects.create(
            student=s_sy, academic_year=dsy_setup['year'], department=dsy_setup['dept_cs'],
            program=dsy_setup['prog_cs'], semester=dsy_setup['sem3'], is_current=True
        )

        # Filter by SY
        res_sy = api_client.get('/api/v1/students/', {'year_level': 2})
        assert res_sy.status_code == status.HTTP_200_OK
        ids_sy = [s['application_id'] for s in res_sy.data['results']]
        assert 'DSE26100002' in ids_sy
        assert 'EN26100001' not in ids_sy

        # Filter by FY
        res_fy = api_client.get('/api/v1/students/', {'class_year': 'FY'})
        assert res_fy.status_code == status.HTTP_200_OK
        ids_fy = [s['application_id'] for s in res_fy.data['results']]
        assert 'EN26100001' in ids_fy
        assert 'DSE26100002' not in ids_fy

    def test_hod_assign_division_and_lab_batch(self, api_client, dsy_setup):
        # Authenticate as CSE HOD
        api_client.force_authenticate(user=dsy_setup['user_hod'])

        s_sy = Student.objects.create(application_id='DSE26100003', first_name='DSY', last_name='Candidate', is_direct_second_year=True)
        enrollment = StudentEnrollment.objects.create(
            student=s_sy, academic_year=dsy_setup['year'], department=dsy_setup['dept_cs'],
            program=dsy_setup['prog_cs'], semester=dsy_setup['sem3'], is_current=True
        )

        res_assign = api_client.post(
            f'/api/v1/students/{s_sy.id}/assign-division/',
            {
                'division_id': str(dsy_setup['div_cs_3a'].id),
                'lab_batch_id': str(dsy_setup['batch_3a1'].id),
            }
        )
        assert res_assign.status_code == status.HTTP_200_OK
        enrollment.refresh_from_db()
        assert enrollment.division == dsy_setup['div_cs_3a']
        assert enrollment.lab_batch == dsy_setup['batch_3a1']
