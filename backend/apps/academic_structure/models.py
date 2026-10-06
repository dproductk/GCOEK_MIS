"""
Academic Structure models for GCOEK MIS.

Owns:
- Department (5 initial departments; extensible, data-driven)
- Program (Degree programs under departments)
- AcademicYear (Global academic year calendar)
- AcademicContext (College-wide active operational term context)
- Semester (Canonical semester levels 1-8)
- Division (Class section cohort per dept, year, semester, with assigned Class Teacher)

Per ARCHITECTURE.md and CONTEXT.md:
- Department choice code is used to match government admission imports.
- Global academic context is controlled centrally by Sysadmin.
- Student academic history stores explicit semester numbers (1-8), not just odd/even.
"""
from django.conf import settings
from django.db import models, transaction

from apps.common.models import BaseModel


class Department(BaseModel):
    """
    Academic Department (e.g., Computer Science and Engineering).
    Extensible and data-driven - not hard-coded in logic.
    """

    name = models.CharField(
        max_length=150,
        unique=True,
        help_text='Full department name.',
    )
    code = models.CharField(
        max_length=20,
        unique=True,
        help_text='Department short code (e.g., CSE, AI_DS, EE, ETC, MAE).',
    )
    choice_code = models.CharField(
        max_length=20,
        blank=True,
        default='',
        help_text='DTE government admission choice code for mapping import rows.',
    )
    alternate_choice_codes = models.JSONField(
        default=list,
        blank=True,
        help_text='Alternate choice codes for the same department (e.g. DSE/TFWS-style codes like 0603624211T).',
    )
    seat_capacity = models.PositiveIntegerField(
        default=60,
        help_text='Approved annual student intake capacity.',
    )
    start_date = models.DateField(
        null=True,
        blank=True,
        help_text='Date when department commenced operations.',
    )
    description = models.TextField(
        blank=True,
        default='',
        help_text='Department description and profile.',
    )
    is_active = models.BooleanField(
        default=True,
        help_text='Whether this department is currently active.',
    )

    class Meta:
        db_table = 'departments'
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.code})'


class Program(BaseModel):
    """
    Academic Degree Program under a Department (e.g., B.Tech in CSE).
    """

    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name='programs',
    )
    name = models.CharField(
        max_length=150,
        help_text='Full program title (e.g. B.Tech in Computer Science and Engineering).',
    )
    code = models.CharField(
        max_length=30,
        help_text='Program code (e.g., BTECH_CSE).',
    )
    university_program_code = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        unique=True,
        db_index=True,
        help_text='University-issued program code for admission imports (e.g. 11242 for CSE). Data-driven; never hard-coded in import logic.',
    )
    degree_type = models.CharField(
        max_length=30,
        default='B.Tech',
        help_text='Degree qualification (B.Tech, M.Tech, Ph.D).',
    )
    duration_years = models.PositiveSmallIntegerField(
        default=4,
        help_text='Normal duration in years.',
    )
    total_semesters = models.PositiveSmallIntegerField(
        default=8,
        help_text='Total semesters to complete program.',
    )
    is_active = models.BooleanField(
        default=True,
        help_text='Whether this program is currently active.',
    )

    class Meta:
        db_table = 'programs'
        ordering = ['department', 'name']
        unique_together = ['department', 'code']

    def __str__(self):
        return f'{self.name} ({self.code})'


class AcademicYear(BaseModel):
    """
    Global academic calendar year (e.g., 2026-27).
    """

    code = models.CharField(
        max_length=20,
        unique=True,
        help_text='Academic year code (e.g., 2026-27).',
    )
    name = models.CharField(
        max_length=50,
        help_text='Display title (e.g., Academic Year 2026-2027).',
    )
    start_date = models.DateField(
        help_text='Academic year commencement date.',
    )
    end_date = models.DateField(
        help_text='Academic year conclusion date.',
    )
    is_current = models.BooleanField(
        default=False,
        help_text='Whether this is the current active academic year for the college.',
    )
    is_active = models.BooleanField(
        default=True,
        help_text='Whether this academic year is active.',
    )

    class Meta:
        db_table = 'academic_years'
        ordering = ['-start_date']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        """Ensure only one academic year can be marked as current."""
        if self.is_current:
            with transaction.atomic():
                AcademicYear.objects.filter(is_current=True).exclude(id=self.id).update(is_current=False)
                super().save(*args, **kwargs)
        else:
            super().save(*args, **kwargs)


class AcademicContext(BaseModel):
    """
    College-wide active operational term context.
    Controls whether the institution is currently running Odd, Even, or Summer session.
    """

    class Term(models.TextChoices):
        ODD = 'ODD', 'Odd Semester Term'
        EVEN = 'EVEN', 'Even Semester Term'
        SUMMER = 'SUMMER', 'Summer Term'

    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name='contexts',
    )
    term = models.CharField(
        max_length=20,
        choices=Term.choices,
        default=Term.ODD,
        help_text='Active operational term.',
    )
    start_date = models.DateField(
        null=True,
        blank=True,
    )
    end_date = models.DateField(
        null=True,
        blank=True,
    )
    is_active = models.BooleanField(
        default=True,
        help_text='Whether this academic context is currently active.',
    )

    class Meta:
        db_table = 'academic_contexts'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.academic_year.code} - {self.get_term_display()}'

    def save(self, *args, **kwargs):
        """Ensure only one AcademicContext is active at a time."""
        if self.is_active:
            with transaction.atomic():
                AcademicContext.objects.filter(is_active=True).exclude(id=self.id).update(is_active=False)
                super().save(*args, **kwargs)
        else:
            super().save(*args, **kwargs)


class Semester(BaseModel):
    """
    Canonical semester level (Semesters 1 through 8).
    """

    class TermType(models.TextChoices):
        ODD = 'ODD', 'Odd Semester'
        EVEN = 'EVEN', 'Even Semester'

    number = models.PositiveSmallIntegerField(
        unique=True,
        help_text='Semester sequence number (1-8).',
    )
    name = models.CharField(
        max_length=50,
        help_text='Display name (e.g., Semester 1).',
    )
    year_level = models.PositiveSmallIntegerField(
        help_text='Academic year level: 1 (First Year), 2 (Second Year), 3 (Third Year), 4 (Final Year).',
    )
    term_type = models.CharField(
        max_length=10,
        choices=TermType.choices,
        help_text='Odd or Even term classification.',
    )
    is_active = models.BooleanField(
        default=True,
        help_text='Whether this semester is active.',
    )

    class Meta:
        db_table = 'semesters'
        ordering = ['number']

    def __str__(self):
        return f'{self.name} (Year {self.year_level})'


class Division(BaseModel):
    """
    Class section cohort within a department, academic year, and semester.
    Assigns a Class Teacher who holds division-scoped verification authority.
    """

    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name='divisions',
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name='divisions',
    )
    semester = models.ForeignKey(
        Semester,
        on_delete=models.PROTECT,
        related_name='divisions',
    )
    name = models.CharField(
        max_length=20,
        help_text='Division identifier (e.g. A, B).',
    )
    class_teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_divisions',
        help_text='Faculty assigned as Class Teacher for this division.',
    )
    seat_capacity = models.PositiveIntegerField(
        default=60,
        help_text='Maximum student capacity for this division.',
    )
    is_active = models.BooleanField(
        default=True,
        help_text='Whether this division is active.',
    )

    class Meta:
        db_table = 'divisions'
        ordering = ['department', 'semester', 'name']
        unique_together = ['department', 'academic_year', 'semester', 'name']

    def __str__(self):
        return f'{self.department.code} Sem {self.semester.number} Div {self.name} ({self.academic_year.code})'


class LabBatch(BaseModel):
    """
    Lab / practical sub-group within a Division (e.g. A1, A2, A3).
    Created by HOD via Student Divisions & Batches workflow.
    """

    division = models.ForeignKey(
        Division,
        on_delete=models.CASCADE,
        related_name='lab_batches',
    )
    name = models.CharField(
        max_length=20,
        help_text='Batch identifier within division (e.g. A1, A2, A3).',
    )
    seat_capacity = models.PositiveIntegerField(
        default=20,
        help_text='Maximum student capacity for this lab batch.',
    )
    is_active = models.BooleanField(
        default=True,
        help_text='Whether this lab batch is active.',
    )

    class Meta:
        db_table = 'lab_batches'
        ordering = ['division', 'name']
        unique_together = ['division', 'name']

    def __str__(self):
        return f'{self.division} Batch {self.name}'
