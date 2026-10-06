"""
Management command to seed realistic faculty members, HODs, and class teachers.
Sets up:
- User accounts and role assignments with scope (HOD -> CSE, Class Teacher -> Div A)
- Detailed AICTE-format profiles (qualifications, experience, publications, guidance)
- Teaching assignments linked to academic structure
"""
import datetime
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.academic_structure.models import AcademicYear, Department, Division, Semester
from apps.authentication.models import Role, RoleAssignment, User
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


class Command(BaseCommand):
    help = 'Seed realistic faculty members with AICTE biodata details.'

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write('Seeding faculty records...')

        role_faculty = Role.objects.get(codename='FACULTY')
        role_hod = Role.objects.get(codename='HOD')
        role_ct = Role.objects.get(codename='CLASS_TEACHER')

        curr_year = AcademicYear.objects.filter(is_current=True).first()
        dept_cse = Department.objects.get(code='CSE')
        dept_aids = Department.objects.get(code='AI_DS')
        sem1 = Semester.objects.get(number=1)
        div_cse_a = Division.objects.filter(department=dept_cse, name='A').first()

        faculty_data = [
            {
                'username': 'hod_cse',
                'first_name': 'Suresh',
                'middle_name': 'Ramchandra',
                'last_name': 'Sharma',
                'code': 'FAC_CSE_001',
                'dept': dept_cse,
                'designation': Faculty.Designation.HOD,
                'email': 'suresh.sharma@gceok.ac.in',
                'mobile': '9822100001',
                'joining': datetime.date(2014, 7, 1),
                'role': role_hod,
                'scope_dept': dept_cse,
                'scope_div': None,
                'quals': [
                    {'level': 'PHD', 'degree': 'Ph.D. Computer Science & Engg', 'inst': 'IIT Bombay', 'year': 2012, 'grade': 'Awarded', 'highest': True},
                    {'level': 'PG', 'degree': 'M.Tech Computer Science', 'inst': 'COEP Pune', 'year': 2006, 'grade': 'First Class with Distinction', 'highest': False},
                    {'level': 'UG', 'degree': 'B.E. Computer Engineering', 'inst': 'Shivaji University', 'year': 2003, 'grade': 'First Class', 'highest': False},
                ],
                'exp': [
                    {'type': 'TEACHING', 'org': 'Government College of Engg, Kolhapur', 'desig': 'Professor & HOD', 'start': datetime.date(2014, 7, 1), 'years': 12.0, 'current': True},
                    {'type': 'TEACHING', 'org': 'Walchand College of Engineering, Sangli', 'desig': 'Assistant Professor', 'start': datetime.date(2006, 8, 1), 'end': datetime.date(2014, 6, 30), 'years': 7.8, 'current': False},
                ],
                'pubs': [
                    {'title': 'Deep Learning Frameworks for Edge Computing in Smart Grids', 'journal': 'IEEE Transactions on Smart Grid', 'year': 2023, 'type': 'JOURNAL', 'scope': 'INTERNATIONAL'},
                    {'title': 'Optimized Routing in Wireless Sensor Networks using Genetic Algorithms', 'journal': 'Springer Journal of Network Systems', 'year': 2021, 'type': 'JOURNAL', 'scope': 'INTERNATIONAL'},
                ],
                'guidance': [
                    {'type': 'PHD', 'name': 'Pooja Kadam', 'title': 'AI-driven Fault Detection in Solar Inverters', 'status': 'ONGOING'},
                    {'type': 'MASTERS_PROJECT', 'name': 'Aditya Shinde', 'title': 'Blockchain for Secure Academic Transcripts', 'status': 'COMPLETED', 'year': 2024},
                ],
                'subject': 'Data Structures & Algorithms',
                'sub_code': 'CS201',
            },
            {
                'username': 'faculty_priya',
                'first_name': 'Priya',
                'middle_name': 'Sunil',
                'last_name': 'Patil',
                'code': 'FAC_CSE_002',
                'dept': dept_cse,
                'designation': Faculty.Designation.ASSISTANT_PROFESSOR,
                'email': 'priya.patil@gceok.ac.in',
                'mobile': '9822100002',
                'joining': datetime.date(2018, 1, 15),
                'role': role_ct,
                'scope_dept': dept_cse,
                'scope_div': div_cse_a,
                'quals': [
                    {'level': 'PG', 'degree': 'M.Tech Software Engineering', 'inst': 'VJTI Mumbai', 'year': 2016, 'grade': 'First Class with Distinction', 'highest': True},
                    {'level': 'UG', 'degree': 'B.Tech Information Technology', 'inst': 'Shivaji University', 'year': 2014, 'grade': 'First Class', 'highest': False},
                ],
                'exp': [
                    {'type': 'TEACHING', 'org': 'Government College of Engg, Kolhapur', 'desig': 'Assistant Professor & Class Teacher', 'start': datetime.date(2018, 1, 15), 'years': 8.5, 'current': True},
                    {'type': 'INDUSTRY', 'org': 'Infosys Limited, Pune', 'desig': 'Systems Engineer', 'start': datetime.date(2016, 7, 1), 'end': datetime.date(2017, 12, 31), 'years': 1.5, 'current': False},
                ],
                'pubs': [
                    {'title': 'Microservices Architecture for Higher Education ERP Systems', 'journal': 'International Journal of Web Science', 'year': 2024, 'type': 'JOURNAL', 'scope': 'INTERNATIONAL'},
                ],
                'guidance': [
                    {'type': 'UG_PROJECT', 'name': 'Group 4 (Batch 2026)', 'title': 'Automated Timetable Generation via CSP', 'status': 'ONGOING'},
                ],
                'subject': 'Database Management Systems',
                'sub_code': 'CS204',
            },
        ]

        for fdata in faculty_data:
            user, created = User.objects.get_or_create(
                username=fdata['username'],
                defaults={
                    'email': fdata['email'],
                    'user_type': User.UserType.FACULTY,
                    'is_active': True,
                    'must_change_password': False,
                },
            )
            if created:
                user.set_password('Faculty@Gceok2026!')
                user.save()

            # Ensure role assignment
            dept_id = fdata['scope_dept'].id if fdata['scope_dept'] else None
            div_id = fdata['scope_div'].id if fdata['scope_div'] else None

            RoleAssignment.objects.get_or_create(
                user=user,
                role=fdata['role'],
                department_id=dept_id,
                division_id=div_id,
                defaults={'status': RoleAssignment.Status.ACTIVE},
            )

            # Also assign base FACULTY role if role is HOD or CLASS_TEACHER
            if fdata['role'].codename != 'FACULTY':
                RoleAssignment.objects.get_or_create(
                    user=user,
                    role=role_faculty,
                    department_id=dept_id,
                    defaults={'status': RoleAssignment.Status.ACTIVE},
                )

            faculty, f_created = Faculty.objects.get_or_create(
                employee_code=fdata['code'],
                defaults={
                    'user': user,
                    'first_name': fdata['first_name'],
                    'middle_name': fdata['middle_name'],
                    'last_name': fdata['last_name'],
                    'display_name': f"{fdata['first_name']} {fdata['last_name']}",
                    'department': fdata['dept'],
                    'designation': fdata['designation'],
                    'employment_type': Faculty.EmploymentType.REGULAR,
                    'employment_status': Faculty.EmploymentStatus.ACTIVE,
                    'date_of_joining': fdata['joining'],
                    'official_email': fdata['email'],
                    'mobile': fdata['mobile'],
                },
            )

            # Personal Details
            FacultyPersonalDetail.objects.get_or_create(
                faculty=faculty,
                defaults={
                    'date_of_birth': datetime.date(1982, 4, 12) if 'HOD' in faculty.designation else datetime.date(1992, 8, 25),
                    'gender': FacultyPersonalDetail.Gender.MALE if fdata['first_name'] == 'Suresh' else FacultyPersonalDetail.Gender.FEMALE,
                    'nationality': 'Indian',
                    'domicile_state': 'Maharashtra',
                    'constitutional_category': 'OPEN',
                    'blood_group': 'B_POS',
                },
            )

            # Address
            FacultyAddress.objects.get_or_create(
                faculty=faculty,
                address_type=FacultyAddress.AddressType.PERMANENT,
                defaults={
                    'address_line_1': 'Staff Quarters, GCOEK Campus',
                    'district': 'Kolhapur',
                    'state': 'Maharashtra',
                    'pincode': '416012',
                    'is_current': True,
                },
            )

            # Bank Account
            FacultyBankAccount.objects.get_or_create(
                faculty=faculty,
                defaults={
                    'account_holder_name': faculty.display_name,
                    'bank_name': 'State Bank of India',
                    'branch_name': 'Treasury Branch, Kolhapur',
                    'ifsc_code': 'SBIN0000412',
                    'account_number_encrypted': f"encrypted_fac_bank_{faculty.employee_code}",
                    'account_number_masked': 'XXXXXXXX8891',
                    'is_primary': True,
                },
            )

            # Qualifications
            for q in fdata['quals']:
                FacultyQualification.objects.get_or_create(
                    faculty=faculty,
                    degree_name=q['degree'],
                    defaults={
                        'qualification_level': q['level'],
                        'institution_university': q['inst'],
                        'passing_year': q['year'],
                        'class_or_grade': q['grade'],
                        'is_highest': q['highest'],
                    },
                )

            # Experience
            for e in fdata['exp']:
                FacultyExperience.objects.get_or_create(
                    faculty=faculty,
                    organization=e['org'],
                    designation=e['desig'],
                    defaults={
                        'experience_type': e['type'],
                        'start_date': e['start'],
                        'end_date': e.get('end'),
                        'is_current': e['current'],
                        'experience_years': e['years'],
                    },
                )

            # Publications
            for p in fdata['pubs']:
                FacultyPublication.objects.get_or_create(
                    faculty=faculty,
                    title=p['title'],
                    defaults={
                        'journal_or_conference': p['journal'],
                        'publication_year': p['year'],
                        'publication_type': p['type'],
                        'scope': p['scope'],
                    },
                )

            # Guidance
            for g in fdata['guidance']:
                FacultyGuidance.objects.get_or_create(
                    faculty=faculty,
                    candidate_name=g['name'],
                    project_title=g['title'],
                    defaults={
                        'guidance_type': g['type'],
                        'status': g['status'],
                        'completion_year': g.get('year'),
                    },
                )

            # Teaching Assignment
            TeachingAssignment.objects.get_or_create(
                faculty=faculty,
                academic_year=curr_year,
                department=fdata['dept'],
                semester=sem1,
                subject_code=fdata['sub_code'],
                defaults={
                    'division': fdata['scope_div'],
                    'subject_name': fdata['subject'],
                    'role': TeachingAssignment.Role.PRIMARY_FACULTY,
                    'is_active': True,
                },
            )

            self.stdout.write(f"  - Seeded faculty {faculty.display_name} ({faculty.employee_code})")

        self.stdout.write(self.style.SUCCESS('Successfully seeded faculty members!'))
