"""
Seed realistic semester examination results and eligibility records.
"""
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.academic_structure.models import AcademicYear, Semester
from apps.results.models import EligibilityVerification, SemesterResult, SubjectResult
from apps.results.services import calculate_semester_metrics
from apps.students.models import Student


class Command(BaseCommand):
    help = 'Seed realistic examination marksheet and eligibility records.'

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write('Seeding semester results and marksheets...')

        curr_year = AcademicYear.objects.filter(is_current=True).first()
        sem1 = Semester.objects.get(number=1)
        sem2 = Semester.objects.get(number=2)

        students = Student.objects.filter(is_active=True)
        if not students.exists():
            self.stdout.write(self.style.WARNING('No students found. Run seed_students first.'))
            return

        courses = [
            {'code': 'CS101', 'name': 'Engineering Mathematics I', 'credits': 4, 'marks': 88, 'gp': 9, 'grade': 'A+'},
            {'code': 'CS102', 'name': 'Engineering Physics & Lab', 'credits': 4, 'marks': 82, 'gp': 9, 'grade': 'A+'},
            {'code': 'CS103', 'name': 'Structured Programming with C', 'credits': 4, 'marks': 94, 'gp': 10, 'grade': 'O'},
            {'code': 'CS104', 'name': 'Basic Electrical & Electronics', 'credits': 3, 'marks': 75, 'gp': 8, 'grade': 'A'},
            {'code': 'CS105', 'name': 'Indian Constitution & Ethics', 'credits': 2, 'marks': 80, 'gp': 9, 'grade': 'A+'},
        ]

        for student in students:
            # 1. Create published Winter 2026 Semester 1 Result
            sem_res, _ = SemesterResult.objects.get_or_create(
                student=student,
                academic_year=curr_year,
                semester=sem1,
                defaults={
                    'exam_session': 'Winter 2026',
                    'seat_number': f"W26_{student.enrollment_no[-6:]}",
                    'is_published': True,
                    'published_at': timezone.now(),
                },
            )

            for c in courses:
                SubjectResult.objects.get_or_create(
                    semester_result=sem_res,
                    course_code=c['code'],
                    defaults={
                        'course_name': c['name'],
                        'credits': c['credits'],
                        'theory_ese_marks': Decimal(str(c['marks'] * 0.6)),
                        'theory_ise_marks': Decimal(str(c['marks'] * 0.4)),
                        'total_marks': Decimal(str(c['marks'])),
                        'grade_point': c['gp'],
                        'grade_letter': c['grade'],
                        'is_backlog': False,
                    },
                )

            calculate_semester_metrics(sem_res.id)

            # 2. Create Eligibility Verification record for Sem 2
            enrollment = student.enrollments.filter(is_current=True).first()
            if enrollment:
                EligibilityVerification.objects.get_or_create(
                    student=student,
                    academic_year=curr_year,
                    target_semester=sem2,
                    defaults={
                        'department': enrollment.department,
                        'active_backlog_count': 0,
                        'total_credits_earned': sem_res.total_credits_earned,
                        'calculated_status': EligibilityVerification.CalculatedStatus.ELIGIBLE,
                        'class_teacher_status': EligibilityVerification.StageStatus.PENDING,
                        'class_teacher_remarks': '',
                        'class_teacher_reviewed_at': None,
                        'hod_status': EligibilityVerification.StageStatus.PENDING,
                        'hod_remarks': '',
                        'hod_reviewed_at': None,
                        'final_eligible': False,
                    },
                )

            self.stdout.write(f"  - Generated Sem 1 marksheet and eligibility for {student.display_name}")

        # ─── Semester 2 results for students currently in Sem 3+ ───
        # These students have completed Sem 1 AND Sem 2 already.
        # Uses DBATU NEP 2020 B.Tech AI & Allied Curriculum subjects.

        sem2_courses = [
            {'code': '25AF1000BS201', 'name': 'Engineering Mathematics II',           'credits': 3, 'marks': 85, 'gp': 9, 'grade': 'A+'},
            {'code': '25AF1000BS202', 'name': 'Engineering Chemistry',                'credits': 3, 'marks': 78, 'gp': 8, 'grade': 'A'},
            {'code': '25AF1245PC203', 'name': 'Object Oriented Programming with Java','credits': 3, 'marks': 91, 'gp': 10, 'grade': 'O'},
            {'code': '25AF1245PC204', 'name': 'Data Communication',                   'credits': 2, 'marks': 72, 'gp': 8, 'grade': 'A'},
            {'code': '25AF1000HS205', 'name': 'Universal Human Values',               'credits': 2, 'marks': 80, 'gp': 9, 'grade': 'A+'},
            {'code': '25AF1000BS206', 'name': 'Environmental Science & Sustainability','credits': 2, 'marks': 68, 'gp': 7, 'grade': 'B+'},
        ]

        sem3_students = Student.objects.filter(
            is_active=True,
            enrollments__semester=sem2,
            enrollments__is_current=False,
        ).distinct() | Student.objects.filter(
            is_active=True,
            enrollments__semester__number__gte=3,
            enrollments__is_current=True,
        ).distinct()

        for student in sem3_students:
            sem2_res, _ = SemesterResult.objects.get_or_create(
                student=student,
                academic_year=curr_year,
                semester=sem2,
                defaults={
                    'exam_session': 'Summer 2027',
                    'seat_number': f"S27_{student.enrollment_no[-6:]}",
                    'is_published': True,
                    'published_at': timezone.now(),
                },
            )

            for c in sem2_courses:
                SubjectResult.objects.get_or_create(
                    semester_result=sem2_res,
                    course_code=c['code'],
                    defaults={
                        'course_name': c['name'],
                        'credits': c['credits'],
                        'theory_ese_marks': Decimal(str(c['marks'] * 0.6)),
                        'theory_ise_marks': Decimal(str(c['marks'] * 0.4)),
                        'total_marks': Decimal(str(c['marks'])),
                        'grade_point': c['gp'],
                        'grade_letter': c['grade'],
                        'is_backlog': False,
                    },
                )

            calculate_semester_metrics(sem2_res.id)
            self.stdout.write(f"  - Generated Sem 2 marksheet for {student.display_name}")

        self.stdout.write(self.style.SUCCESS('Successfully seeded results & eligibility!'))
