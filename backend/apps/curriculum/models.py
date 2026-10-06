"""
Curriculum domain models.

Implements DATABASE_ARCHITECTURE_V2.md Section 6 + CONTEXT.md Sections 8-12
+ ARCHITECTURE.md Section 23:

- Scheme: versioned curriculum rulebook (code + version unique). Published
  schemes are immutable: results/enrollments stay tied to their scheme.
- Subject: reusable subject identity (code unique).
- SchemeSubject: subject placed in a scheme+semester with credits/marks.
- SchemeSubjectAssessmentComponent: normalized assessment split
  (THEORY_FA/SA, PRACTICAL_FA/SA, SLA) with max/min marks.
- SchemeElectiveGroup / SchemeElectiveOption: elective slots + options.
- Eligibility thresholds live on Scheme (data-driven, not hard-coded):
  min_theory_marks, min_total_marks, max_backlogs_for_atkt.

Student binding: StudentEnrollment.scheme (nullable FK, PROTECT) records the
scheme the student entered under. Promotion preserves it. Admissions commit
resolves the applicable published scheme for the admission year+program.
"""
from django.db import models

from apps.common.models import BaseModel


class Subject(BaseModel):
    """Reusable subject identity (not tied to one scheme version).

    Holds the full examination scheme (Image 1 form): course category,
    weekly hours (L/P), and max marks. Theory subjects carry
    CA + MSE + ESE; laboratory subjects (PCC Lab) carry
    Practical CA + Practical ESE instead. Credits live here; linking a
    subject into a scheme auto-fills code/credits/marks (no retyping).
    """

    class CourseCategory(models.TextChoices):
        PCC = 'PCC', 'PCC — Program Core Course'
        PEC = 'PEC', 'PEC — Program Elective Course'
        OE = 'OE', 'OE — Open Elective'
        MDM = 'MDM', 'MDM — Multidisciplinary Minor'
        VEC = 'VEC', 'VEC — Value Education Course'
        PCC_LAB = 'PCC_LAB', 'PCC Lab — Program Core Course Laboratory'
        PROJECT = 'PROJECT', 'Project / Project Phase'
        INTERNSHIP = 'INTERNSHIP', 'Internship'
        SEMINAR = 'SEMINAR', 'Seminar'

    #: Categories evaluated as pure theory (CA + MSE + ESE).
    THEORY_CATEGORIES = frozenset({'PCC', 'PEC', 'OE', 'MDM', 'VEC'})

    code = models.CharField(max_length=30, unique=True, db_index=True)
    title = models.CharField(max_length=200)
    abbreviation = models.CharField(max_length=20, blank=True, default='')
    is_active = models.BooleanField(default=True)
    course_category = models.CharField(
        max_length=20, choices=CourseCategory.choices, blank=True, default='',
        db_index=True,
        help_text='Empty = legacy subject created before categories existed.',
    )
    lecture_hours = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text='Weekly lecture hours (L).')
    practical_hours = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text='Weekly practical hours (P).')
    # Theory examination scheme (max marks per head).
    ca_max_marks = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True)
    mse_max_marks = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True)
    ese_max_marks = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True)
    # Laboratory examination scheme (max marks per head).
    practical_ca_max_marks = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True)
    practical_ese_max_marks = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True)
    credits = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        db_table = 'curriculum_subjects'
        ordering = ['code']

    def __str__(self):
        return f'{self.code} - {self.title}'

    @property
    def is_lab(self):
        return self.course_category == self.CourseCategory.PCC_LAB

    @property
    def theory_total(self):
        if self.ca_max_marks is None or self.mse_max_marks is None or self.ese_max_marks is None:
            return None
        return float(self.ca_max_marks) + float(self.mse_max_marks) + float(self.ese_max_marks)

    @property
    def practical_total(self):
        if self.practical_ca_max_marks is None or self.practical_ese_max_marks is None:
            return None
        return float(self.practical_ca_max_marks) + float(self.practical_ese_max_marks)

    @property
    def exam_total(self):
        """Total marks for the subject (lab → practical sum, else theory sum)."""
        if self.is_lab:
            return self.practical_total
        total = self.theory_total
        if total is None:
            total = self.practical_total
        return total

    @property
    def has_complete_exam_scheme(self):
        if self.is_lab:
            return self.practical_total is not None
        if self.course_category in self.THEORY_CATEGORIES:
            return self.theory_total is not None
        # Project / Internship / Seminar accept either scheme.
        return self.theory_total is not None or self.practical_total is not None


class Scheme(BaseModel):
    """Versioned curriculum/scheme rulebook (e.g. G Scheme v1)."""

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        PUBLISHED = 'PUBLISHED', 'Published'
        RETIRED = 'RETIRED', 'Retired'

    code = models.CharField(max_length=30, db_index=True)
    name = models.CharField(max_length=150)
    program = models.ForeignKey(
        'academic_structure.Program',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='schemes',
        help_text='Null = applies to all programs.',
    )
    department = models.ForeignKey(
        'academic_structure.Department',
        on_delete=models.PROTECT,
        related_name='schemes',
        null=True,
        blank=True,
        help_text='Auto-derived from program; informational only.',
    )
    effective_from_year = models.ForeignKey(
        'academic_structure.AcademicYear',
        on_delete=models.PROTECT,
        related_name='schemes_starting',
    )
    effective_to_year = models.ForeignKey(
        'academic_structure.AcademicYear',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='schemes_ending',
    )
    version = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    # Data-driven eligibility / passing rules (CONTEXT Sec 12)
    min_theory_marks = models.DecimalField(max_digits=5, decimal_places=1, default=20.0)
    min_total_marks = models.DecimalField(max_digits=5, decimal_places=1, default=40.0)
    max_backlogs_for_atkt = models.PositiveSmallIntegerField(default=4)

    class Meta:
        db_table = 'curriculum_schemes'
        ordering = ['code', 'version']
        constraints = [
            models.UniqueConstraint(fields=['code', 'version'], name='uniq_scheme_code_version'),
        ]

    def __str__(self):
        return f'{self.code} v{self.version} ({self.get_status_display()})'

    @property
    def is_mutable(self):
        return self.status == self.Status.DRAFT


class SchemeSubject(BaseModel):
    """A subject as defined inside one scheme and semester."""

    scheme = models.ForeignKey(Scheme, on_delete=models.CASCADE, related_name='scheme_subjects')
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name='scheme_occurrences')
    semester_number = models.PositiveSmallIntegerField()
    course_code = models.CharField(max_length=30)
    course_level_code = models.CharField(max_length=20, blank=True, default='')
    course_type_code = models.CharField(max_length=20, blank=True, default='')
    credits = models.PositiveSmallIntegerField(default=3)
    total_marks = models.PositiveSmallIntegerField(default=100)
    is_elective = models.BooleanField(default=False)
    elective_group = models.ForeignKey(
        'curriculum.SchemeElectiveGroup',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='scheme_subjects',
    )
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = 'curriculum_scheme_subjects'
        ordering = ['scheme', 'semester_number', 'display_order', 'course_code']
        constraints = [
            models.UniqueConstraint(
                fields=['scheme', 'semester_number', 'course_code'],
                name='uniq_scheme_sem_course',
            ),
        ]

    def __str__(self):
        return f'{self.course_code} Sem {self.semester_number} ({self.scheme})'


class SchemeSubjectAssessmentComponent(BaseModel):
    """Normalized assessment split for one scheme subject."""

    class ComponentType(models.TextChoices):
        THEORY_FA = 'THEORY_FA', 'Theory Formative Assessment'
        THEORY_SA = 'THEORY_SA', 'Theory Summative Assessment'
        PRACTICAL_FA = 'PRACTICAL_FA', 'Practical Formative Assessment'
        PRACTICAL_SA = 'PRACTICAL_SA', 'Practical Summative Assessment'
        SLA = 'SLA', 'Self Learning Assessment'

    scheme_subject = models.ForeignKey(
        SchemeSubject, on_delete=models.CASCADE, related_name='assessment_components'
    )
    component_type = models.CharField(max_length=20, choices=ComponentType.choices)
    maximum_marks = models.DecimalField(max_digits=6, decimal_places=1)
    minimum_marks = models.DecimalField(max_digits=6, decimal_places=1, default=0.0)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = 'curriculum_assessment_components'
        ordering = ['scheme_subject', 'display_order']
        constraints = [
            models.UniqueConstraint(
                fields=['scheme_subject', 'component_type'],
                name='uniq_subject_component',
            ),
        ]

    def __str__(self):
        return f'{self.scheme_subject.course_code}:{self.component_type} max={self.maximum_marks}'


class SchemeElectiveGroup(BaseModel):
    """Elective slot (e.g. ELECTIVE I) within a scheme+semester."""

    scheme = models.ForeignKey(Scheme, on_delete=models.CASCADE, related_name='elective_groups')
    semester_number = models.PositiveSmallIntegerField()
    group_code = models.CharField(max_length=30)
    title = models.CharField(max_length=200, blank=True, default='')
    minimum_selection = models.PositiveSmallIntegerField(default=1)
    maximum_selection = models.PositiveSmallIntegerField(default=1)

    class Meta:
        db_table = 'curriculum_elective_groups'
        ordering = ['scheme', 'semester_number', 'group_code']
        constraints = [
            models.UniqueConstraint(
                fields=['scheme', 'semester_number', 'group_code'],
                name='uniq_scheme_sem_elective_group',
            ),
        ]

    def __str__(self):
        return f'{self.group_code} Sem {self.semester_number} ({self.scheme})'


class SchemeElectiveOption(BaseModel):
    """One subject option inside an elective group."""

    elective_group = models.ForeignKey(
        SchemeElectiveGroup, on_delete=models.CASCADE, related_name='options'
    )
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name='elective_options')
    scheme_subject = models.ForeignKey(
        SchemeSubject,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='elective_options',
    )
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = 'curriculum_elective_options'
        ordering = ['elective_group', 'display_order']

    def __str__(self):
        return f'{self.subject.code} in {self.elective_group.group_code}'
