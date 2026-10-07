"""
Tests for Candidate Onboarding Excel Ingestion & Profile Synchronization.

Validates:
1. Candidate ingestion from DBATU portal export structure (PRN-based without Application ID).
2. Per-row DSY detection via 'Student Admitted Semester' (SEMESTER - 3 -> DSY/Sem 3, SEMESTER - 1 -> FY/Sem 1).
3. Population of caste, marital_status, abc_id, blood_group, and structured address.
4. Profile API exposure and self-service updates by enrolled students.
"""
import datetime
import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.academic_structure.models import AcademicYear, Department, Division, Program, Semester
from apps.admissions.models import ImportBatch, ImportRow
from apps.admissions.services import commit_import_batch, stage_admission_file
from apps.authentication.models import Role, RoleAssignment, User
from apps.students.models import Student, StudentPersonalDetail


@pytest.fixture
def onboarding_setup(db):
    year = AcademicYear.objects.create(
        code='2025-26',
        name='Academic Year 2025-2026',
        start_date=datetime.date(2025, 7, 1),
        end_date=datetime.date(2026, 6, 30),
        is_current=True,
    )
    dept_cse = Department.objects.create(
        name='Computer Science and Engineering',
        code='CSE',
        choice_code='627024210',
    )
    prog_cse = Program.objects.create(
        department=dept_cse,
        name='B.Tech CSE',
        code='BTECH_CSE',
        university_program_code='11242',
    )
    sem1 = Semester.objects.create(number=1, name='Semester 1', year_level=1, term_type=Semester.TermType.ODD)
    sem3 = Semester.objects.create(number=3, name='Semester 3', year_level=2, term_type=Semester.TermType.ODD)

    Division.objects.create(department=dept_cse, academic_year=year, semester=sem1, name='A')
    Division.objects.create(department=dept_cse, academic_year=year, semester=sem3, name='A')

    role_admin, _ = Role.objects.get_or_create(codename='ADMIN_HEAD', defaults={'name': 'Administrative Head'})
    role_student, _ = Role.objects.get_or_create(codename='STUDENT', defaults={'name': 'Student'})

    admin_user = User.objects.create_user(username='admin_onboarding', password='Password123!', user_type=User.UserType.SYSADMIN)
    RoleAssignment.objects.create(user=admin_user, role=role_admin, status=RoleAssignment.Status.ACTIVE)

    return {
        'year': year,
        'dept_cse': dept_cse,
        'prog_cse': prog_cse,
        'sem1': sem1,
        'sem3': sem3,
        'admin_user': admin_user,
        'role_student': role_student,
    }


def test_onboarding_ingestion_and_profile(onboarding_setup):
    """
    Test onboarding students using university excel columns:
    - Row 1: Regular First Year (SEMESTER - 1)
    - Row 2: Direct Second Year (SEMESTER - 3)
    Verify PRN-only identifier, caste, abc_id, marital_status, and profile synchronization.
    """
    admin_user = onboarding_setup['admin_user']
    year = onboarding_setup['year']

    # CSV simulation of the 58-column DBATU excel export
    csv_content = (
        "PRN,Students Full Name,Gender,DOB,Category,Mobile No,Email-Id,Blood Group,Program Code,"
        "Program Name,Student Admitted Semester,Student Admitted Year,Cast,MARITAL STATUS,ABC Id,"
        "Student Location Category,Student State,Student District,Student Taluka,Student_City/Village,Student Location Pincode,Admitted_Category\n"
        "23060361242001,PATIL SHIVTEJ JAYPRAKASH,Male,15/08/2005,OPEN,9876543210,shivtej@gmail.com,O+,11242,"
        "B.Tech CSE,SEMESTER - 1,2025-26,MARATHA,Unmarried,605-880-265-207,Urban,Maharashtra,Kolhapur,Karveer,Kolhapur,416004,General\n"
        "24060361242502,KAMBLE RAHUL ANAND,Male,20/03/2004,SC,9876543211,rahul@gmail.com,B+,11242,"
        "B.Tech CSE,SEMESTER - 3,2025-26,MAHAR,Unmarried,712-440-123-999,Urban,Maharashtra,Kolhapur,Hatkanangle,Ichalkaranji,416115,SC\n"
    ).encode('utf-8')

    batch = stage_admission_file(
        file_bytes=csv_content,
        file_name='CSE_Onboarding_Test.csv',
        academic_year=year,
        user=admin_user,
    )

    assert batch.status == ImportBatch.Status.VALIDATED
    assert batch.total_rows == 2
    assert batch.valid_rows == 2

    # Commit batch into core models
    committed_batch = commit_import_batch(batch.id)
    assert committed_batch.status == ImportBatch.Status.COMPLETED

    # Verify regular FY student (Row 1)
    s1 = Student.objects.get(enrollment_no='23060361242001')
    assert s1.display_name == 'PATIL SHIVTEJ JAYPRAKASH'
    assert s1.is_direct_second_year is False
    assert s1.admission_type == 'FY'
    assert s1.personal_details.caste == 'MARATHA'
    assert s1.personal_details.marital_status == 'Unmarried'
    assert s1.personal_details.abc_id == '605-880-265-207'
    assert s1.personal_details.blood_group == 'O+'

    perm_addr1 = s1.addresses.get(address_type='PERMANENT')
    assert perm_addr1.district == 'Kolhapur'
    assert perm_addr1.taluka == 'Karveer'
    assert perm_addr1.pincode == '416004'

    enr1 = s1.enrollments.get(is_current=True)
    assert enr1.semester.number == 1

    # Verify DSY student (Row 2)
    s2 = Student.objects.get(enrollment_no='24060361242502')
    assert s2.display_name == 'KAMBLE RAHUL ANAND'
    assert s2.is_direct_second_year is True
    assert s2.admission_type == 'DSE'
    assert s2.personal_details.caste == 'MAHAR'
    assert s2.personal_details.abc_id == '712-440-123-999'

    enr2 = s2.enrollments.get(is_current=True)
    assert enr2.semester.number == 3

    # Verify student self-profile API update
    client = APIClient()
    client.force_authenticate(user=s1.user)

    # 1. Fetch own profile
    res = client.get('/api/v1/students/me/')
    assert res.status_code == status.HTTP_200_OK
    assert res.data['enrollment_no'] == '23060361242001'
    assert res.data['personal_details']['caste'] == 'MARATHA'
    assert res.data['personal_details']['abc_id'] == '605-880-265-207'

    # 2. Update profile (e.g. adding mother's name, bank account, and editing caste/place of birth)
    update_payload = {
        'personal': {
            'place_of_birth': 'Kolhapur',
            'caste': 'MARATHA 96 KULI',
            'marital_status': 'Unmarried',
            'student_mobile': '9876543210',
        },
        'guardians': [
            {'relationship': 'MOTHER', 'name': 'SUNITA PATIL'},
        ],
        'bank': {
            'account_holder_name': 'PATIL SHIVTEJ',
            'bank_name': 'Bank of Maharashtra',
            'branch_name': 'Kolhapur Main',
            'account_number': '60123456789',
            'ifsc_code': 'MAHB0000123',
        },
    }
    update_res = client.patch('/api/v1/students/me/update/', update_payload, format='json')
    assert update_res.status_code == status.HTTP_200_OK

    # Verify updated values in DB
    s1.refresh_from_db()
    assert s1.personal_details.place_of_birth == 'Kolhapur'
    assert s1.personal_details.caste == 'MARATHA 96 KULI'
    assert s1.guardians.filter(relationship='MOTHER', name='SUNITA PATIL').exists()
    assert s1.bank_accounts.filter(bank_name='Bank of Maharashtra').exists()


def test_senior_2023_cohort_lands_even_sem_via_formula(db):
    """Senior backfill: 2023-24 admitted rows land on formula sems in an EVEN term.

    FY 2023 in 2024-25 EVEN -> Sem 4; DSE 2023 in 2024-25 EVEN -> Sem 6
    (elapsed*2+1 / elapsed*2+3 + 1). DSE must NOT collapse to hardcoded Sem 3.
    This is the backfill step before results 1..4 / 1..6, verification,
    fee marking, and promotion to Sem 5 / Sem 7.
    """
    import datetime
    from apps.academic_structure.models import (
        AcademicContext, AcademicYear, Department, Division, Program, Semester,
    )
    from apps.admissions.models import ImportBatch
    from apps.admissions.services import commit_import_batch, stage_admission_file
    from apps.authentication.models import Role, RoleAssignment, User
    from apps.students.models import Student

    past = AcademicYear.objects.create(
        code='2023-24', name='Academic Year 2023-2024',
        start_date=datetime.date(2023, 7, 1), end_date=datetime.date(2024, 6, 30),
        is_current=False,
    )
    current = AcademicYear.objects.create(
        code='2024-25', name='Academic Year 2024-2025',
        start_date=datetime.date(2024, 7, 1), end_date=datetime.date(2025, 6, 30),
        is_current=True,
    )
    AcademicContext.objects.create(academic_year=current, term='EVEN', is_active=True)
    dept = Department.objects.create(
        name='Computer Science and Engineering', code='CSE', choice_code='627024210')
    Program.objects.create(
        department=dept, name='B.Tech CSE', code='BTECH_CSE',
        university_program_code='11242')
    for n, yl, tt in ((4, 2, Semester.TermType.EVEN), (6, 3, Semester.TermType.EVEN)):
        Semester.objects.create(number=n, name=f'Semester {n}', year_level=yl, term_type=tt)
    role_admin, _ = Role.objects.get_or_create(codename='ADMIN_HEAD', defaults={'name': 'Administrative Head'})
    Role.objects.get_or_create(codename='STUDENT', defaults={'name': 'Student'})
    admin = User.objects.create_user(username='admin_senior', password='Password123!', user_type=User.UserType.SYSADMIN)
    RoleAssignment.objects.create(user=admin, role=role_admin, status=RoleAssignment.Status.ACTIVE)

    csv_content = (
        "PRN,Students Full Name,Gender,DOB,Category,Mobile No,Email-Id,Blood Group,Program Code,"
        "Program Name,Student Admitted Semester,Student Admitted Year,Cast,MARITAL STATUS,ABC Id,"
        "Student Location Category,Student State,Student District,Student Taluka,Student_City/Village,Student Location Pincode,Admitted_Category\n"
        "23060361242011,SENIOR FY STUDENT,Male,15/08/2005,OPEN,9876543220,fy@gmail.com,O+,11242,"
        "B.Tech CSE,SEMESTER - 1,2023-24,MARATHA,Unmarried,605-880-265-207,Urban,Maharashtra,Kolhapur,Karveer,Kolhapur,416004,General\n"
        "23060361242512,SENIOR DSE STUDENT,Male,20/03/2004,SC,9876543221,dse@gmail.com,B+,11242,"
        "B.Tech CSE,SEMESTER - 3,2023-24,MAHAR,Unmarried,712-440-123-999,Urban,Maharashtra,Kolhapur,Hatkanangle,Ichalkaranji,416115,SC\n"
    ).encode('utf-8')

    batch = stage_admission_file(
        file_bytes=csv_content, file_name='CSE_Senior_2023.csv',
        academic_year=current, user=admin)
    assert batch.status == ImportBatch.Status.VALIDATED
    assert batch.academic_year.code == '2023-24'

    committed = commit_import_batch(batch.id)
    assert committed.status == ImportBatch.Status.COMPLETED

    s_fy = Student.objects.get(enrollment_no='23060361242011')
    assert s_fy.admission_year.code == '2023-24'
    assert s_fy.admission_type == 'FY'
    assert s_fy.enrollments.get(is_current=True).semester.number == 4

    s_dse = Student.objects.get(enrollment_no='23060361242512')
    assert s_dse.is_direct_second_year is True
    assert s_dse.admission_type == 'DSE'
    assert s_dse.enrollments.get(is_current=True).semester.number == 6
    assert past.code == '2023-24'
