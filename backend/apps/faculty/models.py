"""
Faculty domain models.

Implements DATABASE_ARCHITECTURE_V2.md Sections 4 & 5:
- Stable faculty employment identity
- Normalized personal details, addresses, qualifications, experience, publications, guidance
- Sensitive bank details with masking
- Document metadata with verification
- Teaching assignments linked to academic structure
"""
from django.conf import settings
from django.db import models

from apps.academic_structure.models import AcademicYear, Department, Division, Semester
from apps.common.models import BaseModel, TimestampedModel


class Faculty(BaseModel):
    """
    Stable faculty / employee identity record.
    """

    class Designation(models.TextChoices):
        PROFESSOR = 'PROFESSOR', 'Professor'
        ASSOCIATE_PROFESSOR = 'ASSOCIATE_PROFESSOR', 'Associate Professor'
        ASSISTANT_PROFESSOR = 'ASSISTANT_PROFESSOR', 'Assistant Professor'
        ADJUNCT_PROFESSOR = 'ADJUNCT_PROFESSOR', 'Adjunct Professor'
        LECTURER = 'LECTURER', 'Lecturer'
        HOD = 'HOD', 'Head of Department'
        PRINCIPAL = 'PRINCIPAL', 'Principal'

    class EmploymentType(models.TextChoices):
        REGULAR = 'REGULAR', 'Regular / Permanent'
        CONTRACT = 'CONTRACT', 'Contractual'
        AD_HOC = 'AD_HOC', 'Ad-hoc'
        VISITING = 'VISITING', 'Visiting Faculty'

    class EmploymentStatus(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'
        ON_LEAVE = 'ON_LEAVE', 'On Leave'
        RELIEVED = 'RELIEVED', 'Relieved / Resigned'
        RETIRED = 'RETIRED', 'Retired'

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='faculty_profile',
    )
    employee_code = models.CharField(max_length=50, unique=True, db_index=True)
    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True, default='')
    last_name = models.CharField(max_length=100)
    display_name = models.CharField(max_length=255, blank=True)
    department = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        related_name='faculty_members',
    )
    designation = models.CharField(
        max_length=50,
        choices=Designation.choices,
        default=Designation.ASSISTANT_PROFESSOR,
    )
    employment_type = models.CharField(
        max_length=20,
        choices=EmploymentType.choices,
        default=EmploymentType.REGULAR,
    )
    employment_status = models.CharField(
        max_length=20,
        choices=EmploymentStatus.choices,
        default=EmploymentStatus.ACTIVE,
    )
    date_of_joining = models.DateField()
    date_of_relieving = models.DateField(null=True, blank=True)
    official_email = models.EmailField(unique=True)
    personal_email = models.EmailField(blank=True, null=True)
    mobile = models.CharField(max_length=15, blank=True, default='')
    residential_telephone = models.CharField(max_length=20, blank=True, default='')
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'faculties'
        ordering = ['department', 'last_name', 'first_name']

    def __str__(self):
        return f'{self.display_name} ({self.employee_code}) - {self.get_designation_display()}'

    def save(self, *args, **kwargs):
        if not self.display_name:
            parts = [self.first_name, self.middle_name, self.last_name]
            self.display_name = ' '.join(p for p in parts if p).strip()
        super().save(*args, **kwargs)


class FacultyPersonalDetail(TimestampedModel):
    """
    Controlled personal attributes for faculty members.
    """

    class Gender(models.TextChoices):
        MALE = 'MALE', 'Male'
        FEMALE = 'FEMALE', 'Female'
        OTHER = 'OTHER', 'Other'

    faculty = models.OneToOneField(
        Faculty,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name='personal_details',
    )
    date_of_birth = models.DateField()
    gender = models.CharField(max_length=10, choices=Gender.choices)
    nationality = models.CharField(max_length=50, default='Indian')
    domicile_state = models.CharField(max_length=50, default='Maharashtra')
    constitutional_category = models.CharField(max_length=50, blank=True, default='')
    blood_group = models.CharField(max_length=10, blank=True, default='')

    class Meta:
        db_table = 'faculty_personal_details'

    def __str__(self):
        return f'Personal Details: {self.faculty}'


class FacultyAddress(BaseModel):
    """
    Residential and correspondence addresses for faculty.
    """

    class AddressType(models.TextChoices):
        PERMANENT = 'PERMANENT', 'Permanent Address'
        CORRESPONDENCE = 'CORRESPONDENCE', 'Correspondence Address'

    faculty = models.ForeignKey(
        Faculty,
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
    district = models.CharField(max_length=100, default='Kolhapur')
    state = models.CharField(max_length=100, default='Maharashtra')
    pincode = models.CharField(max_length=10)
    is_current = models.BooleanField(default=True)

    class Meta:
        db_table = 'faculty_addresses'
        ordering = ['faculty', 'address_type']

    def __str__(self):
        return f'{self.get_address_type_display()} - {self.faculty}'


class FacultyQualification(BaseModel):
    """
    Academic qualifications (UG, PG, Ph.D., Postdoc).
    """

    class Level(models.TextChoices):
        UG = 'UG', 'Undergraduate (B.E./B.Tech)'
        PG = 'PG', 'Postgraduate (M.E./M.Tech)'
        PHD = 'PHD', 'Doctorate (Ph.D.)'
        POSTDOC = 'POSTDOC', 'Post-Doctoral'
        OTHER = 'OTHER', 'Other Certification'

    faculty = models.ForeignKey(
        Faculty,
        on_delete=models.CASCADE,
        related_name='qualifications',
    )
    qualification_level = models.CharField(max_length=20, choices=Level.choices)
    degree_name = models.CharField(max_length=100, help_text='e.g. B.E. Computer Science')
    specialization = models.CharField(max_length=150, blank=True, default='')
    institution_university = models.CharField(max_length=255)
    passing_year = models.PositiveSmallIntegerField()
    percentage_or_cgpa = models.CharField(max_length=20, blank=True, default='')
    class_or_grade = models.CharField(max_length=50, blank=True, default='First Class')
    is_highest = models.BooleanField(default=False)
    remarks = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        db_table = 'faculty_qualifications'
        ordering = ['faculty', '-passing_year']

    def __str__(self):
        return f'{self.degree_name} ({self.passing_year}) - {self.faculty}'


class FacultyExperience(BaseModel):
    """
    Employment history across Teaching, Industry, and Research.
    """

    class ExpType(models.TextChoices):
        TEACHING = 'TEACHING', 'Teaching Experience'
        INDUSTRY = 'INDUSTRY', 'Industry Experience'
        RESEARCH = 'RESEARCH', 'Research Experience'

    faculty = models.ForeignKey(
        Faculty,
        on_delete=models.CASCADE,
        related_name='experiences',
    )
    experience_type = models.CharField(max_length=20, choices=ExpType.choices, default=ExpType.TEACHING)
    organization = models.CharField(max_length=255)
    designation = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    is_current = models.BooleanField(default=False)
    experience_years = models.DecimalField(max_digits=4, decimal_places=1, default=0.0)
    remarks = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'faculty_experiences'
        ordering = ['faculty', '-start_date']

    def __str__(self):
        return f'{self.designation} at {self.organization} ({self.faculty})'


class FacultyPublication(BaseModel):
    """
    Research publications, conference papers, and patents.
    """

    class PubType(models.TextChoices):
        JOURNAL = 'JOURNAL', 'Journal Article'
        CONFERENCE = 'CONFERENCE', 'Conference Proceeding'
        BOOK = 'BOOK', 'Book / Book Chapter'
        PATENT = 'PATENT', 'Patent'

    class Scope(models.TextChoices):
        NATIONAL = 'NATIONAL', 'National'
        INTERNATIONAL = 'INTERNATIONAL', 'International'

    faculty = models.ForeignKey(
        Faculty,
        on_delete=models.CASCADE,
        related_name='publications',
    )
    title = models.CharField(max_length=350)
    journal_or_conference = models.CharField(max_length=300)
    publication_type = models.CharField(max_length=20, choices=PubType.choices, default=PubType.JOURNAL)
    scope = models.CharField(max_length=20, choices=Scope.choices, default=Scope.INTERNATIONAL)
    publication_year = models.PositiveSmallIntegerField()
    doi_or_issn = models.CharField(max_length=100, blank=True, default='')
    indexing = models.CharField(max_length=100, blank=True, default='Scopus / Web of Science')

    class Meta:
        db_table = 'faculty_publications'
        ordering = ['faculty', '-publication_year']

    def __str__(self):
        return f'{self.title} ({self.publication_year}) - {self.faculty}'


class FacultyGuidance(BaseModel):
    """
    Ph.D. and Master's thesis guidance records.
    """

    class GuidanceType(models.TextChoices):
        PHD = 'PHD', 'Ph.D. Thesis Guidance'
        MASTERS_PROJECT = 'MASTERS_PROJECT', "Master's Dissertation"
        UG_PROJECT = 'UG_PROJECT', 'B.Tech Capstone Project'

    class Status(models.TextChoices):
        ONGOING = 'ONGOING', 'Ongoing'
        COMPLETED = 'COMPLETED', 'Completed / Awarded'

    faculty = models.ForeignKey(
        Faculty,
        on_delete=models.CASCADE,
        related_name='guidance_records',
    )
    guidance_type = models.CharField(max_length=20, choices=GuidanceType.choices)
    candidate_name = models.CharField(max_length=150)
    project_title = models.CharField(max_length=300)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ONGOING)
    completion_year = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        db_table = 'faculty_guidance'
        ordering = ['faculty', '-status']

    def __str__(self):
        return f'{self.candidate_name} ({self.get_guidance_type_display()}) - {self.faculty}'


class FacultyBankAccount(BaseModel):
    """
    Sensitive faculty salary bank account details.
    Always masked by default; full access requires audit.
    """

    faculty = models.ForeignKey(
        Faculty,
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
        db_table = 'faculty_bank_accounts'
        ordering = ['faculty', '-is_primary']

    def __str__(self):
        return f'{self.bank_name} - {self.account_number_masked} ({self.faculty})'


class FacultyDocument(BaseModel):
    """
    Faculty document metadata (photo, resume, appointment letter, degrees).
    """

    class DocType(models.TextChoices):
        PHOTO = 'PHOTO', 'Photograph'
        SIGNATURE = 'SIGNATURE', 'Signature'
        AADHAAR = 'AADHAAR', 'Aadhaar Card'
        PAN = 'PAN', 'PAN Card'
        APPOINTMENT_LETTER = 'APPOINTMENT_LETTER', 'Appointment Order'
        DEGREE_CERTIFICATE = 'DEGREE_CERTIFICATE', 'Degree Certificate'
        RESUME = 'RESUME', 'Curriculum Vitae (AICTE Format)'
        OTHER = 'OTHER', 'Other Document'

    faculty = models.ForeignKey(
        Faculty,
        on_delete=models.CASCADE,
        related_name='documents',
    )
    document_type = models.CharField(max_length=30, choices=DocType.choices)
    title = models.CharField(max_length=255)
    file_path = models.CharField(max_length=500)
    file_size = models.PositiveIntegerField(default=0)
    mime_type = models.CharField(max_length=100, default='application/pdf')
    checksum = models.CharField(max_length=64, blank=True, default='')
    is_verified = models.BooleanField(default=False)
    version = models.PositiveSmallIntegerField(default=1)

    class Meta:
        db_table = 'faculty_documents'
        ordering = ['faculty', 'document_type', '-version']

    def __str__(self):
        return f'{self.get_document_type_display()} - {self.faculty}'


class TeachingAssignment(BaseModel):
    """
    Authoritative course / subject teaching assignment per term.
    """

    class Role(models.TextChoices):
        PRIMARY_FACULTY = 'PRIMARY_FACULTY', 'Primary Course Instructor'
        CO_FACULTY = 'CO_FACULTY', 'Co-Instructor'
        LAB_INSTRUCTOR = 'LAB_INSTRUCTOR', 'Lab Practical Incharge'

    faculty = models.ForeignKey(
        Faculty,
        on_delete=models.CASCADE,
        related_name='teaching_assignments',
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name='teaching_assignments',
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        related_name='teaching_assignments',
    )
    semester = models.ForeignKey(
        Semester,
        on_delete=models.PROTECT,
        related_name='teaching_assignments',
    )
    division = models.ForeignKey(
        Division,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='teaching_assignments',
    )
    subject_name = models.CharField(max_length=200)
    subject_code = models.CharField(max_length=30)
    scheme_subject = models.ForeignKey(
        'curriculum.SchemeSubject',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='teaching_assignments',
        help_text='Scheme-defined subject slot; fills name/code automatically.',
    )
    role = models.CharField(max_length=30, choices=Role.choices, default=Role.PRIMARY_FACULTY)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'faculty_teaching_assignments'
        ordering = ['-academic_year__start_date', 'semester__number', 'subject_code']
        constraints = [
            # One active teacher per (division, subject, role) slot.
            # The one-subject-per-teacher rule stays in serializer validation
            # (it compares across rows, which a constraint cannot express).
            models.UniqueConstraint(
                fields=['division', 'subject_code', 'role'],
                condition=models.Q(is_active=True),
                name='uniq_active_slot_teacher',
            ),
        ]

    def save(self, *args, **kwargs):
        # Normalize so the slot constraint compares canonically.
        if self.subject_code:
            self.subject_code = self.subject_code.strip().upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.subject_name} ({self.subject_code}) - {self.faculty.display_name}'
