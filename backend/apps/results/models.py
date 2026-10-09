"""
Results and Academic Eligibility Models.

Implements:
- Authoritative Semester Result & Subject Marksheet records.
- 9-Point autonomous grading and backlog calculation.
- "Not Yet Held" workflow state for future/upcoming semester exams.
- Multi-tier Eligibility Verification Workflow:
  Calculated -> Class Teacher Review (Flag/Approve) -> HOD Review & Endorsement.
"""
from django.conf import settings
from django.db import models

from apps.academic_structure.models import AcademicYear, Department, Semester
from apps.common.models import BaseModel


class SemesterResult(BaseModel):
    """
    Consolidated examination performance for a student in a specific semester.
    """

    class ResultStatus(models.TextChoices):
        PASS = 'PASS', 'Pass'
        ATKT = 'ATKT', 'Allowed To Keep Term (Backlog)'
        FAIL = 'FAIL', 'Fail / Detained'
        NOT_YET_HELD = 'NOT_YET_HELD', 'Examination Not Yet Held'
        WITHHELD = 'WITHHELD', 'Result Withheld'

    # F-S4-004: PROTECT backstop so academic history is never silently deleted
    student = models.ForeignKey(
        'students.Student',
        on_delete=models.PROTECT,
        related_name='semester_results',
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name='semester_results',
    )
    semester = models.ForeignKey(
        Semester,
        on_delete=models.PROTECT,
        related_name='semester_results',
    )
    exam_session = models.CharField(
        max_length=50,
        help_text='e.g. Winter 2026, Summer 2027',
    )
    seat_number = models.CharField(max_length=50, blank=True, default='')
    sgpa = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    cgpa = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    total_credits_registered = models.PositiveSmallIntegerField(default=0)
    total_credits_earned = models.PositiveSmallIntegerField(default=0)
    backlog_count = models.PositiveSmallIntegerField(default=0)
    result_status = models.CharField(
        max_length=20,
        choices=ResultStatus.choices,
        default=ResultStatus.NOT_YET_HELD,
        db_index=True,
    )
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'results_semester_results'
        ordering = ['student', 'semester__number']
        unique_together = ['student', 'academic_year', 'semester']

    def __str__(self):
        return f'{self.student.display_name} - Sem {self.semester.number} ({self.exam_session}): {self.get_result_status_display()}'


class SubjectResult(BaseModel):
    """
    Individual course / subject score entry on a semester marksheet.
    """

    class Grade(models.TextChoices):
        O = 'O', 'Outstanding (10)'
        A_PLUS = 'A+', 'Excellent (9)'
        A = 'A', 'Very Good (8)'
        B_PLUS = 'B+', 'Good (7)'
        B = 'B', 'Above Average (6)'
        C = 'C', 'Average (5)'
        P = 'P', 'Pass (4)'
        F = 'F', 'Fail (0)'
        AB = 'AB', 'Absent (0)'
        NOT_YET_HELD = 'NYH', 'Not Yet Held'

    semester_result = models.ForeignKey(
        SemesterResult,
        on_delete=models.CASCADE,
        related_name='subject_results',
    )
    course_code = models.CharField(max_length=30)
    course_name = models.CharField(max_length=200)
    credits = models.PositiveSmallIntegerField(default=3)
    theory_ese_marks = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    theory_ise_marks = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    mid1_marks = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    mid2_marks = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    practical_marks = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    total_marks = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    grade_point = models.PositiveSmallIntegerField(default=0)
    grade_letter = models.CharField(max_length=5, choices=Grade.choices, default=Grade.NOT_YET_HELD)
    is_backlog = models.BooleanField(default=False)

    class Meta:
        db_table = 'results_subject_results'
        ordering = ['semester_result', 'course_code']

    def __str__(self):
        return f'{self.course_code} - {self.course_name} ({self.grade_letter})'


class EligibilityVerification(BaseModel):
    """
    Multi-stage verification workflow for term and annual progression eligibility.
    Calculated by system -> Reviewed by Class Teacher -> Approved by HOD.
    """

    class CalculatedStatus(models.TextChoices):
        ELIGIBLE = 'ELIGIBLE', 'Eligible for Promotion'
        NOT_ELIGIBLE = 'NOT_ELIGIBLE', 'Not Eligible (Exceeded Backlogs)'
        PROVISIONAL = 'PROVISIONAL', 'Provisionally Eligible'

    class StageStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending Review'
        APPROVED = 'APPROVED', 'Approved / Endorsed'
        FLAGGED = 'FLAGGED', 'Flagged with Remarks'
        REJECTED = 'REJECTED', 'Rejected'

    # F-S4-004: PROTECT backstop so eligibility records are never silently cascaded
    student = models.ForeignKey(
        'students.Student',
        on_delete=models.PROTECT,
        related_name='eligibility_records',
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        related_name='eligibility_verifications',
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name='eligibility_verifications',
    )
    target_semester = models.ForeignKey(
        Semester,
        on_delete=models.PROTECT,
        related_name='eligibility_verifications',
    )
    active_backlog_count = models.PositiveSmallIntegerField(default=0)
    total_credits_earned = models.PositiveSmallIntegerField(default=0)
    calculated_status = models.CharField(
        max_length=20,
        choices=CalculatedStatus.choices,
        default=CalculatedStatus.ELIGIBLE,
    )

    # Class Teacher Review Tier
    class_teacher_status = models.CharField(
        max_length=20,
        choices=StageStatus.choices,
        default=StageStatus.PENDING,
    )
    class_teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_eligibilities',
    )
    class_teacher_remarks = models.TextField(blank=True, default='')
    class_teacher_reviewed_at = models.DateTimeField(null=True, blank=True)

    # HOD Approval Tier
    hod_status = models.CharField(
        max_length=20,
        choices=StageStatus.choices,
        default=StageStatus.PENDING,
    )
    hod = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='endorsed_eligibilities',
    )
    hod_remarks = models.TextField(blank=True, default='')
    hod_reviewed_at = models.DateTimeField(null=True, blank=True)

    # Final Operational Outcome
    final_eligible = models.BooleanField(
        default=False,
        help_text='True once both Class Teacher and HOD endorse eligibility.',
    )

    class Meta:
        db_table = 'results_eligibility_verifications'
        ordering = ['department', '-academic_year__start_date', 'student']
        unique_together = ['student', 'academic_year', 'target_semester']
        indexes = [
            # Hot filter: HOD/fee-desk queues filter on department +
            # final_eligible (+ class_teacher_status). Backs
            # results/views.py eligible_candidates and students fee roster.
            models.Index(fields=['department', 'final_eligible', 'class_teacher_status'],
                         name='idx_elig_dept_final_ct'),
        ]

    def __str__(self):
        return f'Eligibility: {self.student.display_name} -> Sem {self.target_semester.number} ({self.calculated_status})'

    @property
    def is_locked_for_teacher(self):
        """
        Class Teacher cannot edit once decided (APPROVED or terminal FAIL),
        unless HOD has flagged it back for rework.
        """
        if self.hod_status == self.StageStatus.FLAGGED:
            return False
        return self.class_teacher_status in (
            self.StageStatus.APPROVED, self.StageStatus.REJECTED)

    @property
    def is_locked_for_student(self):
        """
        Student cannot edit once teacher decided (approved or failed),
        unless teacher (or HOD) flags it back for correction.
        """
        if self.hod_status == self.StageStatus.FLAGGED:
            return False
        return self.class_teacher_status in (
            self.StageStatus.APPROVED, self.StageStatus.REJECTED)
