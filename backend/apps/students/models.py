"""
Student domain models for GCOEK MIS.

Normalized architecture per DATABASE_ARCHITECTURE_V2.md:
- Student: Stable student identity record.
- StudentPersonalDetail: DOB, gender, religion, contact.
- StudentGuardian: Normalized guardian records (father, mother, guardian).
- StudentAddress: Permanent and correspondence addresses.
- StudentAadhaarDetail: Sensitive - encrypted/masked with access audit.
- StudentBankAccount: Sensitive - encrypted/masked bank accounts.
- StudentDocument: Uploaded documents with versioning and checksums.
- StudentEnrollment: Authoritative academic lifecycle and current semester/division status.
"""
from django.conf import settings
from django.db import models, transaction

from apps.common.models import BaseModel, UUIDPrimaryKeyModel, TimestampedModel


class Student(BaseModel):
    """
    Authoritative student identity record.
    External business identifiers (enrollment_no, application_id) are unique columns, NOT PKs.
    """

    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active Enrolled'
        PASSED_OUT = 'PASSED_OUT', 'Graduated / Passed Out'
        DETAINED = 'DETAINED', 'Year Down / Detained'
        CANCELLED = 'CANCELLED', 'Admission Cancelled'
        TRANSFERRED = 'TRANSFERRED', 'Transferred to Other College'

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='student_record',
        help_text='Linked user login account.',
    )
    enrollment_no = models.CharField(
        max_length=50,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text='University enrollment number (e.g. DBATU PRN).',
    )
    application_id = models.CharField(
        max_length=50,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text='Government DTE admission application ID (e.g., EN26123456).',
    )
    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True, default='')
    last_name = models.CharField(max_length=100)
    display_name = models.CharField(
        max_length=255,
        blank=True,
        help_text='Full formatted name.',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    is_direct_second_year = models.BooleanField(
        default=False,
        db_index=True,
        help_text='Whether student was admitted via Direct Second Year (Lateral Entry).',
    )
    admission_year = models.ForeignKey(
        'academic_structure.AcademicYear',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='admitted_students',
        help_text='Academic year the student was admitted in (formula anchor).',
    )
    admission_type = models.CharField(
        max_length=20,
        blank=True,
        default='',
        db_index=True,
        help_text='FY (First Year) or DSE (Direct Second Year lateral entry).',
    )
    repeat_count = models.PositiveSmallIntegerField(
        default=0,
        help_text='Times the student repeated a year (detention); placement itself lives on enrollments.',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'students'
        ordering = ['last_name', 'first_name']

    def __str__(self):
        ident = self.enrollment_no or self.application_id or str(self.id)[:8]
        return f'{self.display_name or self.first_name + " " + self.last_name} ({ident})'

    def save(self, *args, **kwargs):
        if not self.display_name:
            names = [self.first_name, self.middle_name, self.last_name]
            self.display_name = ' '.join(n for n in names if n).strip()
        super().save(*args, **kwargs)


class StudentPersonalDetail(TimestampedModel):
    """
    One-to-one personal attributes of the student.
    """

    class Gender(models.TextChoices):
        MALE = 'MALE', 'Male'
        FEMALE = 'FEMALE', 'Female'
        OTHER = 'OTHER', 'Other'

    student = models.OneToOneField(
        Student,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name='personal_details',
    )
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, choices=Gender.choices, default=Gender.MALE)
    place_of_birth = models.CharField(max_length=100, blank=True, default='')
    religion = models.CharField(max_length=50, blank=True, default='')
    nationality = models.CharField(max_length=50, default='Indian')
    mother_tongue = models.CharField(max_length=50, blank=True, default='')
    domicile_state = models.CharField(max_length=50, default='Maharashtra')
    student_email = models.EmailField(blank=True, null=True)
    student_mobile = models.CharField(max_length=15, blank=True, default='')
    blood_group = models.CharField(max_length=10, blank=True, default='')
    caste = models.CharField(max_length=100, blank=True, default='', help_text='Sub-caste e.g. Maratha, Kunbi, Sutar.')
    marital_status = models.CharField(max_length=20, blank=True, default='Unmarried')
    abc_id = models.CharField(max_length=50, blank=True, default='', help_text='Academic Bank of Credits ID.')

    class Meta:
        db_table = 'student_personal_details'

    def __str__(self):
        return f'Personal Details: {self.student}'


class StudentGuardian(BaseModel):
    """
    Normalized guardian records (Father, Mother, or Local Guardian).
    """

    class Relationship(models.TextChoices):
        FATHER = 'FATHER', 'Father'
        MOTHER = 'MOTHER', 'Mother'
        GUARDIAN = 'GUARDIAN', 'Guardian'

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='guardians',
    )
    relationship = models.CharField(
        max_length=20,
        choices=Relationship.choices,
        default=Relationship.FATHER,
    )
    name = models.CharField(max_length=150)
    mobile = models.CharField(max_length=15, blank=True, default='')
    email = models.EmailField(blank=True, null=True)
    occupation = models.CharField(max_length=100, blank=True, default='')
    annual_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    is_primary = models.BooleanField(default=True)

    class Meta:
        db_table = 'student_guardians'
        ordering = ['student', 'relationship']

    def __str__(self):
        return f'{self.name} ({self.get_relationship_display()}) - {self.student}'


class StudentAddress(BaseModel):
    """
    Normalized addresses (Permanent or Correspondence).
    """

    class AddressType(models.TextChoices):
        PERMANENT = 'PERMANENT', 'Permanent Address'
        CORRESPONDENCE = 'CORRESPONDENCE', 'Correspondence Address'

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='addresses',
    )
    address_type = models.CharField(
        max_length=20,
        choices=AddressType.choices,
        default=AddressType.PERMANENT,
    )
    address_line_1 = models.CharField(max_length=255)
    address_line_2 = models.CharField(max_length=255, blank=True, default='')
    address_line_3 = models.CharField(max_length=255, blank=True, default='')
    village = models.CharField(max_length=100, blank=True, default='')
    taluka = models.CharField(max_length=100, blank=True, default='')
    district = models.CharField(max_length=100, blank=True, default='')
    state = models.CharField(max_length=100, default='Maharashtra')
    pincode = models.CharField(max_length=10, blank=True, default='')
    is_current = models.BooleanField(default=True)

    class Meta:
        db_table = 'student_addresses'
        ordering = ['student', 'address_type']

    def __str__(self):
        return f'{self.get_address_type_display()} - {self.student}'


class StudentAadhaarDetail(TimestampedModel):
    """
    Sensitive Aadhaar details.
    Always masked by default in serializers and UI. Full reveal requires audit.
    """

    student = models.OneToOneField(
        Student,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name='aadhaar_details',
    )
    aadhaar_number_encrypted = models.CharField(
        max_length=255,
        help_text='Encrypted Aadhaar number.',
    )
    aadhaar_number_masked = models.CharField(
        max_length=20,
        help_text='Masked representation (e.g. XXXX-XXXX-1234).',
    )
    enrolment_id = models.CharField(max_length=50, blank=True, default='')
    verified = models.BooleanField(default=False)

    class Meta:
        db_table = 'student_aadhaar_details'

    def __str__(self):
        return f'Aadhaar: {self.aadhaar_number_masked} ({self.student})'


class StudentBankAccount(BaseModel):
    """
    Sensitive student bank account information.
    Masked by default in serializers.
    """

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='bank_accounts',
    )
    account_holder_name = models.CharField(max_length=150)
    bank_name = models.CharField(max_length=150)
    branch_name = models.CharField(max_length=150, blank=True, default='')
    ifsc_code = models.CharField(max_length=20)
    account_number_encrypted = models.CharField(max_length=255)
    account_number_masked = models.CharField(max_length=30)
    is_primary = models.BooleanField(default=True)

    class Meta:
        db_table = 'student_bank_accounts'
        ordering = ['student', '-is_primary']

    def __str__(self):
        return f'{self.bank_name} - {self.account_number_masked} ({self.student})'


class StudentDocument(BaseModel):
    """
    Student document metadata with versioning and security verification.
    """

    class DocType(models.TextChoices):
        PHOTO = 'PHOTO', 'Passport Photograph'
        SIGNATURE = 'SIGNATURE', 'Student Signature'
        AADHAAR = 'AADHAAR', 'Aadhaar Card'
        ALLOTMENT_LETTER = 'ALLOTMENT_LETTER', 'CAP Allotment Letter'
        SSC_MARKSHEET = 'SSC_MARKSHEET', '10th / SSC Marksheet'
        HSC_MARKSHEET = 'HSC_MARKSHEET', '12th / HSC Marksheet'
        DIPLOMA_MARKSHEET = 'DIPLOMA_MARKSHEET', 'Diploma Marksheet'
        CASTE_CERTIFICATE = 'CASTE_CERTIFICATE', 'Caste Certificate'
        INCOME_CERTIFICATE = 'INCOME_CERTIFICATE', 'Income Certificate'
        OTHER = 'OTHER', 'Other Supporting Document'

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='documents',
    )
    document_type = models.CharField(
        max_length=50,
        choices=DocType.choices,
        default=DocType.OTHER,
        db_index=True,
    )
    title = models.CharField(max_length=200)
    file_path = models.CharField(max_length=500, help_text='Secure storage file reference.')
    file_size = models.PositiveIntegerField(default=0, help_text='File size in bytes.')
    mime_type = models.CharField(max_length=100, default='application/pdf')
    checksum = models.CharField(max_length=64, blank=True, default='', help_text='SHA-256 hash.')
    is_verified = models.BooleanField(default=False)
    version = models.PositiveSmallIntegerField(default=1)

    class Meta:
        db_table = 'student_documents'
        ordering = ['student', 'document_type', '-version']

    def __str__(self):
        return f'{self.get_document_type_display()} (v{self.version}) - {self.student}'


class StudentEnrollment(BaseModel):
    """
    Authoritative academic lifecycle association.
    Determines student's current department, semester, division, and progression state.
    """

    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Currently Enrolled'
        COMPLETED = 'COMPLETED', 'Semester Term Completed'
        PROMOTED = 'PROMOTED', 'Promoted to Next Semester'
        DETAINED = 'DETAINED', 'Detained / Not Promoted'
        BACKLOG = 'BACKLOG', 'Has Backlogs'
        DROPOUT = 'DROPOUT', 'Discontinued'

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='enrollments',
    )
    academic_year = models.ForeignKey(
        'academic_structure.AcademicYear',
        on_delete=models.PROTECT,
        related_name='student_enrollments',
    )
    department = models.ForeignKey(
        'academic_structure.Department',
        on_delete=models.PROTECT,
        related_name='student_enrollments',
    )
    program = models.ForeignKey(
        'academic_structure.Program',
        on_delete=models.PROTECT,
        related_name='student_enrollments',
    )
    semester = models.ForeignKey(
        'academic_structure.Semester',
        on_delete=models.PROTECT,
        related_name='student_enrollments',
    )
    division = models.ForeignKey(
        'academic_structure.Division',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='enrolled_students',
    )
    scheme = models.ForeignKey(
        'curriculum.Scheme',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='enrollments',
        help_text='Curriculum scheme the student entered under; preserved on promotion.',
    )
    lab_batch = models.ForeignKey(
        'academic_structure.LabBatch',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='enrolled_students',
        help_text='Assigned laboratory / practical batch (e.g., A1, A2).',
    )
    roll_number = models.CharField(max_length=20, blank=True, default='')
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    is_current = models.BooleanField(
        default=True,
        help_text='Whether this is the student active operational enrollment record.',
    )
    placement_confirmed = models.BooleanField(
        default=False,
        db_index=True,
        help_text='HOD confirmed the sem/division placement (formula suggestion accepted or corrected).',
    )

    class Meta:
        db_table = 'student_enrollments'
        ordering = ['-academic_year__start_date', '-semester__number']
        unique_together = ['student', 'academic_year', 'semester']
        constraints = [
            # Exactly one current enrollment per student, enforced at the
            # database level so two concurrent first writes cannot both win
            # (the save() sibling-lock locks nothing when no sibling exists).
            models.UniqueConstraint(
                fields=['student'],
                condition=models.Q(is_current=True),
                name='uniq_current_enrollment_per_student',
            ),
        ]
        indexes = [
            # Hot filters: directory/rollover/HOD queue filter on
            # is_current + department (+ division). Backs the queries in
            # students/views.py, results/views.py, academic_structure/views.py.
            models.Index(fields=['is_current', 'department', 'division'],
                         name='idx_enr_current_dept_div'),
        ]

    def __str__(self):
        return f'{self.student.display_name} - {self.department.code} Sem {self.semester.number} ({self.academic_year.code})'

    def save(self, *args, **kwargs):
        """Ensure only one current enrollment record per student."""
        if self.is_current:
            with transaction.atomic():
                # Lock sibling rows so concurrent saves can't create two currents.
                list(StudentEnrollment.objects.select_for_update().filter(
                    student=self.student, is_current=True
                ).exclude(id=self.id)[:10])
                StudentEnrollment.objects.filter(
                    student=self.student, is_current=True
                ).exclude(id=self.id).update(is_current=False)
                super().save(*args, **kwargs)
        else:
            super().save(*args, **kwargs)
