"""
Seed initial academic structure for GCOEK MIS.

Seeds:
- 5 Verified Departments from CONTEXT.md Section 4
- B.Tech degree programs
- Semesters 1 through 8
- Academic Year 2026-27 (current)
- Active Academic Context (2026-27 Odd Semester)
- Initial Division A cohorts for Semester 1 and Semester 3

Usage:
    python manage.py seed_academic_structure
"""
from datetime import date
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.academic_structure.models import (
    AcademicContext,
    AcademicYear,
    Department,
    Division,
    Program,
    Semester,
)


class Command(BaseCommand):
    help = 'Seeds initial departments, programs, semesters, academic year, and divisions.'

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE('Seeding academic structure...'))

        # 1. 5 Core Departments
        # FY choice codes + DSE/TFWS-style alternate codes (with leading
        # zero + T suffix) as issued in government candidate lists.
        dept_data = [
            {
                'name': 'Computer Science and Engineering',
                'code': 'CSE',
                'choice_code': '603624210',
                'alternate_choice_codes': ['0603624211T'],
                'seat_capacity': 60,
                'description': 'Department of Computer Science and Engineering at GCOE Kolhapur.',
            },
            {
                'name': 'Artificial Intelligence and Data Science',
                'code': 'AI_DS',
                'choice_code': '603626310',
                'alternate_choice_codes': ['0603626311T'],
                'seat_capacity': 60,
                'description': 'Department of Artificial Intelligence and Data Science.',
            },
            {
                'name': 'Electrical Engineering',
                'code': 'EE',
                'choice_code': '603629310',
                'alternate_choice_codes': ['0603629311T'],
                'seat_capacity': 60,
                'description': 'Department of Electrical Engineering.',
            },
            {
                'name': 'Electronics and Telecommunication Engineering',
                'code': 'ETC',
                'choice_code': '603637210',
                'alternate_choice_codes': ['0603637211T'],
                'seat_capacity': 60,
                'description': 'Department of Electronics and Telecommunication Engineering.',
            },
            {
                'name': 'Mechanical and Automation Engineering',
                'code': 'MAE',
                'choice_code': '603661510',
                'alternate_choice_codes': ['0603661511T'],
                'seat_capacity': 60,
                'description': 'Department of Mechanical and Automation Engineering.',
            },
        ]

        departments = {}
        for d in dept_data:
            dept, created = Department.objects.get_or_create(
                code=d['code'],
                defaults=d,
            )
            if not created and (
                dept.choice_code != d['choice_code']
                or (dept.alternate_choice_codes or []) != d['alternate_choice_codes']
            ):
                # Repair wrong/legacy codes on re-seed (e.g. 6270-prefixed).
                dept.choice_code = d['choice_code']
                dept.alternate_choice_codes = d['alternate_choice_codes']
                dept.save(update_fields=['choice_code', 'alternate_choice_codes', 'updated_at'])
            departments[d['code']] = dept

        self.stdout.write(self.style.SUCCESS(f'Verified {len(departments)} departments.'))

        # 2. B.Tech Programs (+ university program codes for admission imports).
        # University-issued program codes are data, not logic (ARCH Sec 12):
        # CSE 11242, AI&DS 11263, EE 11293, ETC 11372, MAE 11615.
        university_codes = {
            'CSE': '11242',
            'AI_DS': '11263',
            'EE': '11293',
            'ETC': '11372',
            'MAE': '11615',
        }
        programs_created = 0
        for code, dept in departments.items():
            prog, created = Program.objects.get_or_create(
                department=dept,
                code=f'BTECH_{code}',
                defaults={
                    'name': f'B.Tech in {dept.name}',
                    'degree_type': 'B.Tech',
                    'duration_years': 4,
                    'total_semesters': 8,
                    'university_program_code': university_codes.get(code),
                },
            )
            if created:
                programs_created += 1
            elif prog.university_program_code != university_codes.get(code):
                prog.university_program_code = university_codes.get(code)
                prog.save(update_fields=['university_program_code', 'updated_at'])

        self.stdout.write(self.style.SUCCESS(f'Verified B.Tech programs ({programs_created} created).'))

        # 3. Canonical Semesters 1 to 8
        semesters_data = [
            (1, 'Semester 1', 1, Semester.TermType.ODD),
            (2, 'Semester 2', 1, Semester.TermType.EVEN),
            (3, 'Semester 3', 2, Semester.TermType.ODD),
            (4, 'Semester 4', 2, Semester.TermType.EVEN),
            (5, 'Semester 5', 3, Semester.TermType.ODD),
            (6, 'Semester 6', 3, Semester.TermType.EVEN),
            (7, 'Semester 7', 4, Semester.TermType.ODD),
            (8, 'Semester 8', 4, Semester.TermType.EVEN),
        ]

        semesters = {}
        for num, name, yr, term in semesters_data:
            sem, _ = Semester.objects.get_or_create(
                number=num,
                defaults={
                    'name': name,
                    'year_level': yr,
                    'term_type': term,
                },
            )
            semesters[num] = sem

        self.stdout.write(self.style.SUCCESS(f'Verified {len(semesters)} canonical semesters.'))

        # 4. Academic Year 2026-27
        acad_year, _ = AcademicYear.objects.get_or_create(
            code='2026-27',
            defaults={
                'name': 'Academic Year 2026-2027',
                'start_date': date(2026, 7, 1),
                'end_date': date(2027, 6, 30),
                'is_current': True,
            },
        )
        if not acad_year.is_current:
            acad_year.is_current = True
            acad_year.save()

        self.stdout.write(self.style.SUCCESS(f'Verified Academic Year: {acad_year.code} (Current).'))

        # 5. Active Academic Context (Odd Semester Term)
        acad_context, _ = AcademicContext.objects.get_or_create(
            academic_year=acad_year,
            term=AcademicContext.Term.ODD,
            defaults={
                'is_active': True,
                'start_date': date(2026, 7, 15),
                'end_date': date(2026, 12, 15),
            },
        )
        if not acad_context.is_active:
            acad_context.is_active = True
            acad_context.save()

        self.stdout.write(self.style.SUCCESS(f'Verified Academic Context: {acad_context} (Active).'))

        # 6. Initial Division A cohorts for Semester 1 (FE) and Semester 3 (DSE)
        divisions_created = 0
        for code, dept in departments.items():
            for sem_num in [1, 3]:
                _, created = Division.objects.get_or_create(
                    department=dept,
                    academic_year=acad_year,
                    semester=semesters[sem_num],
                    name='A',
                    defaults={'seat_capacity': 60},
                )
                if created:
                    divisions_created += 1

        self.stdout.write(self.style.SUCCESS(f'Verified initial Divisions ({divisions_created} created).'))
        self.stdout.write(self.style.SUCCESS('Academic structure seeding completed successfully.'))
