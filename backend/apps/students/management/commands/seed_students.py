"""
Management command to seed realistic student records across GCOEK departments.
Creates:
- Student accounts (student1, student2, etc.)
- Personal details, guardians, addresses
- Masked Aadhaar and bank details
- Current enrollments linked to Academic Structure (Sem 1, Sem 3, etc.)
"""
import datetime
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.academic_structure.models import AcademicYear, Department, Division, Program, Semester
from apps.authentication.models import Role, RoleAssignment, User
from apps.students.models import (
    Student,
    StudentAadhaarDetail,
    StudentAddress,
    StudentBankAccount,
    StudentDocument,
    StudentEnrollment,
    StudentGuardian,
    StudentPersonalDetail,
)


class Command(BaseCommand):
    help = 'Seed realistic student records across departments.'

    @transaction.atomic
    def handle(self, *args, **options):
        from django.conf import settings
        # F-S6-001: This command creates known accounts — development only.
        if not settings.DEBUG:
            self.stderr.write(self.style.ERROR(
                '[SECURITY] seed_students refused: DEBUG=False. '
                'This command must never run against a production database. '
                'Onboard real students via the admission import workflow.'
            ))
            raise SystemExit(1)
        self.stdout.write('[DEV] Seeding student records...')

        role_student = Role.objects.get(codename='STUDENT')
        curr_year = AcademicYear.objects.filter(is_current=True).first()
        if not curr_year:
            curr_year = AcademicYear.objects.first()

        dept_cse = Department.objects.get(code='CSE')
        dept_aids = Department.objects.get(code='AI_DS')
        dept_ee = Department.objects.get(code='EE')

        prog_cse = Program.objects.filter(department=dept_cse).first()
        prog_aids = Program.objects.filter(department=dept_aids).first()
        prog_ee = Program.objects.filter(department=dept_ee).first()

        sem1 = Semester.objects.get(number=1)
        sem3 = Semester.objects.get(number=3)
        div_cse_a = Division.objects.filter(department=dept_cse, name='A').first()
        div_aids_a = Division.objects.filter(department=dept_aids, name='A').first()
        div_aids_a_sem3 = Division.objects.filter(department=dept_aids, name='A', semester=sem3).first()

        students_data = [
            {
                'username': 'student',
                'first_name': 'Aarav',
                'middle_name': 'Sanjay',
                'last_name': 'Patil',
                'enrollment_no': 'EN262421001',
                'application_id': 'EN26105432',
                'gender': 'MALE',
                'dob': datetime.date(2008, 5, 14),
                'email': 'aarav.patil@gceok.ac.in',
                'mobile': '9822012345',
                'blood_group': 'O_POS',
                'dept': dept_cse,
                'prog': prog_cse,
                'sem': sem1,
                'div': div_cse_a,
                'roll': '101',
                'father_name': 'Sanjay Patil',
                'father_mobile': '9822099991',
                'father_occ': 'Government Service',
                'income': 350000,
                'address': 'Plot 42, Shivaji Park, Kolhapur',
                'district': 'Kolhapur',
                'pincode': '416001',
                'aadhaar_masked': 'XXXX-XXXX-4819',
                'bank_name': 'State Bank of India',
                'acc_masked': 'XXXXXXXX5521',
                'ifsc': 'SBIN0001234',
            },
            {
                'username': 'student_ananya',
                'first_name': 'Ananya',
                'middle_name': 'Rajesh',
                'last_name': 'Kulkarni',
                'enrollment_no': 'EN262421002',
                'application_id': 'EN26108765',
                'gender': 'FEMALE',
                'dob': datetime.date(2008, 9, 21),
                'email': 'ananya.kulkarni@gceok.ac.in',
                'mobile': '9822012346',
                'blood_group': 'B_POS',
                'dept': dept_cse,
                'prog': prog_cse,
                'sem': sem1,
                'div': div_cse_a,
                'roll': '102',
                'father_name': 'Rajesh Kulkarni',
                'father_mobile': '9822099992',
                'father_occ': 'Private Business',
                'income': 600000,
                'address': 'Flat 302, Rajarampuri 5th Lane, Kolhapur',
                'district': 'Kolhapur',
                'pincode': '416008',
                'aadhaar_masked': 'XXXX-XXXX-9124',
                'bank_name': 'Bank of Maharashtra',
                'acc_masked': 'XXXXXXXX8812',
                'ifsc': 'MAHB0000341',
            },
            {
                'username': 'student_rohit',
                'first_name': 'Rohit',
                'middle_name': 'Vikas',
                'last_name': 'Deshmukh',
                'enrollment_no': 'EN262631001',
                'application_id': 'EN26103322',
                'gender': 'MALE',
                'dob': datetime.date(2007, 11, 3),
                'email': 'rohit.deshmukh@gceok.ac.in',
                'mobile': '9822012347',
                'blood_group': 'A_POS',
                'dept': dept_aids,
                'prog': prog_aids,
                'sem': sem1,
                'div': div_aids_a,
                'roll': '201',
                'father_name': 'Vikas Deshmukh',
                'father_mobile': '9822099993',
                'father_occ': 'Agriculture',
                'income': 180000,
                'address': 'At Post Shirol, Taluka Shirol',
                'district': 'Kolhapur',
                'pincode': '416103',
                'aadhaar_masked': 'XXXX-XXXX-7731',
                'bank_name': 'Union Bank of India',
                'acc_masked': 'XXXXXXXX1940',
                'ifsc': 'UBIN0542312',
            },
            {
                'username': 'demo_sarthak',
                'first_name': 'Sarthak',
                'middle_name': 'Manoj',
                'last_name': 'Desai',
                'enrollment_no': 'EN262631002',
                'application_id': 'EN26109876',
                'gender': 'MALE',
                'dob': datetime.date(2006, 3, 22),
                'email': 'sarthak.desai@gceok.ac.in',
                'mobile': '9822012350',
                'blood_group': 'A_POS',
                'dept': dept_aids,
                'prog': prog_aids,
                'sem': sem3,
                'div': div_aids_a_sem3,
                'roll': '202',
                'father_name': 'Manoj Desai',
                'father_mobile': '9822099995',
                'father_occ': 'Business',
                'income': 480000,
                'address': '12, Laxmipuri, Kolhapur',
                'district': 'Kolhapur',
                'pincode': '416002',
                'aadhaar_masked': 'XXXX-XXXX-3347',
                'bank_name': 'Bank of India',
                'acc_masked': 'XXXXXXXX6629',
                'ifsc': 'BKID0001234',
            },
            {
                'username': 'demo_priya',
                'first_name': 'Priya',
                'middle_name': 'Sunil',
                'last_name': 'Jadhav',
                'enrollment_no': 'EN262631003',
                'application_id': 'EN26110234',
                'gender': 'FEMALE',
                'dob': datetime.date(2006, 7, 10),
                'email': 'priya.jadhav@gceok.ac.in',
                'mobile': '9822012351',
                'blood_group': 'B_POS',
                'dept': dept_aids,
                'prog': prog_aids,
                'sem': sem3,
                'div': div_aids_a_sem3,
                'roll': '203',
                'father_name': 'Sunil Jadhav',
                'father_mobile': '9822099996',
                'father_occ': 'Teaching',
                'income': 550000,
                'address': 'Near Mahalaxmi Temple, Sangli Road, Kolhapur',
                'district': 'Kolhapur',
                'pincode': '416012',
                'aadhaar_masked': 'XXXX-XXXX-5512',
                'bank_name': 'Maharashtra Gramin Bank',
                'acc_masked': 'XXXXXXXX7743',
                'ifsc': 'MAHG0004567',
            },
        ]

        import secrets
        import string
        _pw_alphabet = string.ascii_letters + string.digits + '!@#$%'

        for sdata in students_data:
            user, created = User.objects.get_or_create(
                username=sdata['username'],
                defaults={
                    'email': sdata['email'],
                    'user_type': User.UserType.STUDENT,
                    'is_active': True,
                    # F-S6-001: random password, must change on first login.
                    'must_change_password': True,
                },
            )
            if created:
                # Random 16-char password — never echoed to stdout.
                _pw = ''.join(secrets.choice(_pw_alphabet) for _ in range(16))
                user.set_password(_pw)
                user.must_change_password = True
                user.save()
                RoleAssignment.objects.create(
                    user=user,
                    role=role_student,
                    status=RoleAssignment.Status.ACTIVE,
                )

            student, s_created = Student.objects.get_or_create(
                enrollment_no=sdata['enrollment_no'],
                defaults={
                    'user': user,
                    'application_id': sdata['application_id'],
                    'first_name': sdata['first_name'],
                    'middle_name': sdata['middle_name'],
                    'last_name': sdata['last_name'],
                    'display_name': f"{sdata['first_name']} {sdata['last_name']}",
                    'status': Student.Status.ACTIVE,
                },
            )

            # Personal Details
            StudentPersonalDetail.objects.get_or_create(
                student=student,
                defaults={
                    'date_of_birth': sdata['dob'],
                    'gender': sdata['gender'],
                    'place_of_birth': 'Kolhapur',
                    'religion': 'Hindu',
                    'nationality': 'Indian',
                    'mother_tongue': 'Marathi',
                    'domicile_state': 'Maharashtra',
                    'student_email': sdata['email'],
                    'student_mobile': sdata['mobile'],
                    'blood_group': sdata['blood_group'],
                },
            )

            # Guardian
            StudentGuardian.objects.get_or_create(
                student=student,
                relationship=StudentGuardian.Relationship.FATHER,
                defaults={
                    'name': sdata['father_name'],
                    'mobile': sdata['father_mobile'],
                    'occupation': sdata['father_occ'],
                    'annual_income': sdata['income'],
                    'is_primary': True,
                },
            )

            # Address
            StudentAddress.objects.get_or_create(
                student=student,
                address_type=StudentAddress.AddressType.PERMANENT,
                defaults={
                    'address_line_1': sdata['address'],
                    'district': sdata['district'],
                    'state': 'Maharashtra',
                    'pincode': sdata['pincode'],
                    'is_current': True,
                },
            )

            # Aadhaar
            StudentAadhaarDetail.objects.get_or_create(
                student=student,
                defaults={
                    'aadhaar_number_encrypted': f"encrypted_aadhaar_{student.enrollment_no}",
                    'aadhaar_number_masked': sdata['aadhaar_masked'],
                    'verified': True,
                },
            )

            # Bank
            StudentBankAccount.objects.get_or_create(
                student=student,
                bank_name=sdata['bank_name'],
                defaults={
                    'account_holder_name': f"{sdata['first_name']} {sdata['last_name']}",
                    'branch_name': 'Kolhapur Main Branch',
                    'ifsc_code': sdata['ifsc'],
                    'account_number_encrypted': f"encrypted_bank_{student.enrollment_no}",
                    'account_number_masked': sdata['acc_masked'],
                    'is_primary': True,
                },
            )

            # Enrollment
            StudentEnrollment.objects.get_or_create(
                student=student,
                academic_year=curr_year,
                semester=sdata['sem'],
                defaults={
                    'department': sdata['dept'],
                    'program': sdata['prog'],
                    'division': sdata['div'],
                    'roll_number': sdata['roll'],
                    'status': StudentEnrollment.Status.ACTIVE,
                    'is_current': True,
                },
            )

            # Sample Document
            StudentDocument.objects.get_or_create(
                student=student,
                document_type=StudentDocument.DocType.SSC_MARKSHEET,
                defaults={
                    'title': '10th SSC Passing Marksheet',
                    'file_path': f'/media/documents/{student.enrollment_no}_ssc.pdf',
                    'file_size': 245000,
                    'is_verified': True,
                    'version': 1,
                },
            )

            self.stdout.write(f"  - Seeded student {student.display_name} ({student.enrollment_no})")

        self.stdout.write(self.style.SUCCESS('Successfully seeded student records!'))
