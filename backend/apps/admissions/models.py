"""
Admissions and Government Candidate Ingestion Models.

Implements DATABASE_ARCHITECTURE_V2.md Section 7 & 8:
- Staging table for government admitted candidate list
- Import batches with tracking and error metrics
- Normalization into core Student and StudentAdmission entities
"""
from django.conf import settings
from django.db import models

from apps.academic_structure.models import AcademicYear
from apps.common.models import BaseModel


class ImportBatch(BaseModel):
    """
    Tracks an uploaded candidate list file and its ingestion lifecycle.

    Per CONTEXT.md Sec 15.1 + SECURITY.md Sec 14:
    - Original uploaded file preserved (source_file) for proof/audit.
    - Checksum + size stored for integrity verification.
    - Lifecycle: UPLOADED → VALIDATING → VALIDATED → IMPORTING →
      COMPLETED / PARTIALLY_COMPLETED / FAILED.
    """

    class Status(models.TextChoices):
        UPLOADED = 'UPLOADED', 'File Uploaded'
        VALIDATING = 'VALIDATING', 'Validating Rows'
        VALIDATED = 'VALIDATED', 'Validation Complete'
        IMPORTING = 'IMPORTING', 'Importing Into Core Records'
        COMPLETED = 'COMPLETED', 'Successfully Completed'
        PARTIALLY_COMPLETED = 'PARTIALLY_COMPLETED', 'Partially Completed'
        FAILED = 'FAILED', 'Failed with Errors'

    class AdmissionType(models.TextChoices):
        FIRST_YEAR = 'FIRST_YEAR', 'First Year (Regular Entry)'
        DIRECT_SECOND_YEAR = 'DIRECT_SECOND_YEAR', 'Direct Second Year (Lateral Entry)'

    file_name = models.CharField(max_length=255)
    admission_type = models.CharField(
        max_length=30,
        choices=AdmissionType.choices,
        default=AdmissionType.FIRST_YEAR,
        db_index=True,
        help_text='Stream classification: First Year or Direct Second Year.',
    )
    source_file = models.FileField(
        upload_to='admission_imports/%Y/%m/',
        null=True,
        blank=True,
        help_text='Preserved original uploaded file for proof/audit.',
    )
    file_checksum = models.CharField(max_length=64, blank=True, default='')
    file_size = models.PositiveIntegerField(
        default=0,
        help_text='Original file size in bytes.',
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name='import_batches',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.UPLOADED,
        db_index=True,
    )
    total_rows = models.PositiveIntegerField(default=0)
    valid_rows = models.PositiveIntegerField(default=0)
    invalid_rows = models.PositiveIntegerField(default=0)
    duplicate_rows = models.PositiveIntegerField(default=0)
    conflict_rows = models.PositiveIntegerField(
        default=0,
        help_text='Rows needing manual review (conflicting identity matches).',
    )
    failed_rows = models.PositiveIntegerField(
        default=0,
        help_text='Rows that failed during final import.',
    )
    imported_rows = models.PositiveIntegerField(default=0)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='uploaded_admission_batches',
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    summary_report = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'admission_import_batches'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.file_name} ({self.get_status_display()}) - {self.total_rows} rows'


class ImportRow(BaseModel):
    """
    Staged row holding raw columns from government admission Excel.

    Per CONTEXT.md Sec 15.2 + ARCHITECTURE.md Sec 15/21:
    - raw_data preserved unchanged (immutable source history).
    - normalized_data holds cleaned values (trimmed/normalized).
    - matching_status/matching_detail hold identity-matching outcome
      per precedence: Application ID > Enrollment No > Board identifiers.
    - validation_status is the row gate: only VALID rows reach final import.
      DUPLICATE/CONFLICT/INVALID never auto-create students.
    Never corrupts core tables if validation fails.
    """

    class ValidationStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending Validation'
        VALID = 'VALID', 'Valid'
        INVALID = 'INVALID', 'Invalid'
        DUPLICATE = 'DUPLICATE', 'Duplicate / Already Exists'
        CONFLICT = 'CONFLICT', 'Conflict — Needs Manual Review'
        IMPORTED = 'IMPORTED', 'Imported into Student Records'
        FAILED = 'FAILED', 'Import Failed'

    class MatchingStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending Matching'
        NO_MATCH = 'NO_MATCH', 'No Existing Match (New Student)'
        MATCHED = 'MATCHED', 'Matched Single Existing Student'
        CONFLICT = 'CONFLICT', 'Conflicting Matches — Manual Review'

    batch = models.ForeignKey(
        ImportBatch,
        on_delete=models.CASCADE,
        related_name='rows',
    )
    row_number = models.PositiveIntegerField()
    application_id = models.CharField(max_length=50, blank=True, default='', db_index=True)
    enrollment_no = models.CharField(
        max_length=50,
        blank=True,
        default='',
        db_index=True,
        help_text='Enrollment No from source file when provided.',
    )
    choice_code = models.CharField(
        max_length=50,
        blank=True,
        default='',
        db_index=True,
        help_text='Government choice code driving department/program mapping.',
    )
    program_code = models.CharField(
        max_length=50,
        blank=True,
        default='',
        db_index=True,
        help_text='University-issued program code driving department/program mapping when choice code is absent.',
    )
    candidate_name = models.CharField(max_length=255, blank=True, default='')
    allotted_course = models.CharField(max_length=255, blank=True, default='')
    raw_data = models.JSONField(
        default=dict,
        help_text='Complete dictionary of raw columns extracted from source sheet (immutable).',
    )
    normalized_data = models.JSONField(
        default=dict,
        blank=True,
        help_text='Cleaned/normalized values derived from raw_data (trimmed names, dates, mobiles).',
    )
    matching_status = models.CharField(
        max_length=20,
        choices=MatchingStatus.choices,
        default=MatchingStatus.PENDING,
        db_index=True,
        help_text='Identity-matching outcome per precedence rules.',
    )
    matching_detail = models.JSONField(
        default=dict,
        blank=True,
        help_text='Matched student reference / conflict explanation for manual review.',
    )
    validation_status = models.CharField(
        max_length=20,
        choices=ValidationStatus.choices,
        default=ValidationStatus.PENDING,
        db_index=True,
    )
    validation_errors = models.JSONField(default=list, blank=True)
    import_error = models.TextField(
        blank=True,
        default='',
        help_text='Per-row failure reason when final import fails (retryable).',
    )
    student = models.ForeignKey(
        'students.Student',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='source_import_rows',
    )

    class Meta:
        db_table = 'admission_import_rows'
        ordering = ['batch', 'row_number']
        constraints = [
            models.UniqueConstraint(
                fields=['batch', 'row_number'],
                name='uniq_import_row_batch_number',
            ),
        ]
        indexes = [
            models.Index(fields=['batch', 'validation_status']),
            models.Index(fields=['batch', 'matching_status']),
        ]

    def __str__(self):
        return f'Row {self.row_number}: {self.application_id} ({self.candidate_name}) - {self.validation_status}'


class StudentAdmission(BaseModel):
    """
    Authoritative admission record per student.
    Separates admission event metadata from stable student identity.
    """

    student = models.ForeignKey(
        'students.Student',
        on_delete=models.CASCADE,
        related_name='admissions',
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name='student_admissions',
    )
    application_id = models.CharField(max_length=50, db_index=True)
    admission_date = models.DateField(null=True, blank=True)
    admission_type = models.CharField(max_length=50, default='CAP')
    category = models.CharField(
        max_length=20,
        blank=True,
        default='',
        db_index=True,
        help_text='Government admission category (OPEN/OBC/SC/ST/VJ/NT-B/NT-C/NT-D/SBC/SEBC/EWS/TFWS/PWD/DEF/ORPHAN).',
    )
    candidature_type = models.CharField(max_length=50, blank=True, default='')
    institute_code = models.CharField(max_length=20, default='6270')
    institute_name = models.CharField(max_length=255, default='Government College of Engineering, Kolhapur')
    choice_code = models.CharField(max_length=50, blank=True, default='')
    program_code = models.CharField(max_length=50, blank=True, default='')
    seat_type = models.CharField(max_length=50, blank=True, default='')
    allotted_seat_type = models.CharField(max_length=50, blank=True, default='')
    merit_no = models.PositiveIntegerField(null=True, blank=True)
    merit_marks = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    entrance_exam_type = models.CharField(max_length=50, blank=True, default='MHT-CET')
    entrance_percentile = models.DecimalField(max_digits=7, decimal_places=4, null=True, blank=True)
    reported_date = models.DateField(null=True, blank=True)
    source_import_row = models.ForeignKey(
        ImportRow,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_admissions',
    )

    class Meta:
        db_table = 'student_admissions'
        ordering = ['-academic_year__start_date', 'merit_no']

    def __str__(self):
        return f'Admission: {self.application_id} - {self.student.display_name} ({self.seat_type})'
