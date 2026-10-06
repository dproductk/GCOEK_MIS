"""
Serializers for Faculty domain.

Adheres to:
- Sensitive bank account masking (e.g. XXXXXXXX1234)
- Multi-section profile composition projection (AICTE biodata format)
- Scoped directory listing projection
"""
from rest_framework import serializers

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


class FacultyPersonalDetailSerializer(serializers.ModelSerializer):
    gender_display = serializers.CharField(source='get_gender_display', read_only=True)

    class Meta:
        model = FacultyPersonalDetail
        fields = [
            'date_of_birth',
            'gender',
            'gender_display',
            'nationality',
            'domicile_state',
            'constitutional_category',
            'blood_group',
        ]


class FacultyAddressSerializer(serializers.ModelSerializer):
    address_type_display = serializers.CharField(source='get_address_type_display', read_only=True)

    class Meta:
        model = FacultyAddress
        fields = [
            'id',
            'address_type',
            'address_type_display',
            'address_line_1',
            'address_line_2',
            'district',
            'state',
            'pincode',
            'is_current',
        ]


class FacultyQualificationSerializer(serializers.ModelSerializer):
    qualification_level_display = serializers.CharField(source='get_qualification_level_display', read_only=True)

    class Meta:
        model = FacultyQualification
        fields = [
            'id',
            'qualification_level',
            'qualification_level_display',
            'degree_name',
            'specialization',
            'institution_university',
            'passing_year',
            'percentage_or_cgpa',
            'class_or_grade',
            'is_highest',
            'remarks',
        ]


class FacultyExperienceSerializer(serializers.ModelSerializer):
    experience_type_display = serializers.CharField(source='get_experience_type_display', read_only=True)

    class Meta:
        model = FacultyExperience
        fields = [
            'id',
            'experience_type',
            'experience_type_display',
            'organization',
            'designation',
            'start_date',
            'end_date',
            'is_current',
            'experience_years',
            'remarks',
        ]


class FacultyPublicationSerializer(serializers.ModelSerializer):
    publication_type_display = serializers.CharField(source='get_publication_type_display', read_only=True)
    scope_display = serializers.CharField(source='get_scope_display', read_only=True)

    class Meta:
        model = FacultyPublication
        fields = [
            'id',
            'title',
            'journal_or_conference',
            'publication_type',
            'publication_type_display',
            'scope',
            'scope_display',
            'publication_year',
            'doi_or_issn',
            'indexing',
        ]


class FacultyGuidanceSerializer(serializers.ModelSerializer):
    guidance_type_display = serializers.CharField(source='get_guidance_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = FacultyGuidance
        fields = [
            'id',
            'guidance_type',
            'guidance_type_display',
            'candidate_name',
            'project_title',
            'status',
            'status_display',
            'completion_year',
        ]


class FacultyBankAccountMaskedSerializer(serializers.ModelSerializer):
    """Masked bank details."""

    class Meta:
        model = FacultyBankAccount
        fields = [
            'id',
            'account_holder_name',
            'bank_name',
            'branch_name',
            'ifsc_code',
            'account_number_masked',
            'is_primary',
        ]


class FacultyDocumentSerializer(serializers.ModelSerializer):
    document_type_display = serializers.CharField(source='get_document_type_display', read_only=True)

    class Meta:
        model = FacultyDocument
        fields = [
            'id',
            'document_type',
            'document_type_display',
            'title',
            'file_path',
            'file_size',
            'mime_type',
            'is_verified',
            'version',
        ]


class TeachingAssignmentSerializer(serializers.ModelSerializer):
    department_code = serializers.CharField(source='department.code', read_only=True)
    academic_year_code = serializers.CharField(source='academic_year.code', read_only=True)
    semester_number = serializers.IntegerField(source='semester.number', read_only=True)
    division_name = serializers.CharField(source='division.name', default='', read_only=True)
    role_display = serializers.CharField(source='get_role_display', read_only=True)

    class Meta:
        model = TeachingAssignment
        fields = [
            'id',
            'subject_name',
            'subject_code',
            'department_code',
            'academic_year_code',
            'semester_number',
            'division_name',
            'role',
            'role_display',
            'is_active',
        ]


class FacultyCreateSerializer(serializers.Serializer):
    """Sysadmin-only write serializer to onboard a faculty member.

    Creates User + Faculty + RoleAssignment atomically in the view.
    Follows student onboarding convention (CONTEXT Sec 13 / ADR-008):
    username defaults to employee_code, initial password = employee_code,
    must_change_password=True. Password is set only on creation.
    """

    username = serializers.CharField(required=False, allow_blank=True, max_length=150)
    employee_code = serializers.CharField(max_length=50)
    first_name = serializers.CharField(max_length=100)
    middle_name = serializers.CharField(required=False, allow_blank=True, default='')
    last_name = serializers.CharField(max_length=100)
    department_id = serializers.UUIDField()
    designation = serializers.ChoiceField(choices=Faculty.Designation.choices)
    employment_type = serializers.ChoiceField(
        choices=Faculty.EmploymentType.choices,
        required=False,
        default=Faculty.EmploymentType.REGULAR,
    )
    date_of_joining = serializers.DateField()
    official_email = serializers.EmailField()
    mobile = serializers.CharField(required=False, allow_blank=True, default='', max_length=15)
    initial_role = serializers.CharField(required=False, allow_blank=True, default='FACULTY')
    division_id = serializers.UUIDField(required=False, allow_null=True, default=None)

    def validate_employee_code(self, value):
        code = (value or '').strip()
        if not code:
            raise serializers.ValidationError('Employee code is required.')
        if Faculty.objects.filter(employee_code__iexact=code).exists():
            raise serializers.ValidationError('Employee code already exists.')
        return code

    def validate_official_email(self, value):
        email = (value or '').strip()
        if Faculty.objects.filter(official_email__iexact=email).exists():
            raise serializers.ValidationError('Official email already exists.')
        return email

    def validate(self, attrs):
        from apps.academic_structure.models import Department, Division
        from apps.authentication.models import Role, User

        username = (attrs.get('username') or '').strip() or (attrs.get('employee_code') or '').strip()
        if User.objects.filter(username__iexact=username).exists():
            raise serializers.ValidationError({'username': 'Username already exists.'})
        attrs['username'] = username

        if not Department.objects.filter(id=attrs['department_id']).exists():
            raise serializers.ValidationError({'department_id': 'Department not found.'})

        role_code = (attrs.get('initial_role') or 'FACULTY').strip().upper() or 'FACULTY'
        allowed_roles = {'FACULTY', 'HOD', 'CLASS_TEACHER', 'ACCOUNTANT', 'ADMIN_HEAD'}
        if role_code not in allowed_roles:
            raise serializers.ValidationError(
                {'initial_role': f"Must be one of: {', '.join(sorted(allowed_roles))}."}
            )
        if not Role.objects.filter(codename=role_code).exists():
            raise serializers.ValidationError({'initial_role': 'Role does not exist.'})
        attrs['initial_role'] = role_code

        division_id = attrs.get('division_id')
        if division_id is not None and not Division.objects.filter(id=division_id).exists():
            raise serializers.ValidationError({'division_id': 'Division not found.'})
        if role_code == 'CLASS_TEACHER' and not division_id:
            raise serializers.ValidationError(
                {'division_id': 'Division is required for CLASS_TEACHER.'}
            )

        return attrs


class TeachingAssignmentWriteSerializer(serializers.ModelSerializer):
    """HOD-owned write path for subject-teacher slots.

    Rules (user-confirmed):
    - one teacher holds at most one subject per division (same subject's
      theory+lab may share a teacher);
    - one teacher per (division, subject, lab-ness) slot;
    - scheme_subject, when given, fills subject_name/code automatically.
    Replacing a holder deactivates the old row (history preserved).
    """

    class Meta:
        model = TeachingAssignment
        fields = [
            'id', 'faculty', 'academic_year', 'department', 'semester',
            'division', 'scheme_subject', 'subject_name', 'subject_code',
            'role', 'is_active',
        ]
        read_only_fields = ['id']
        extra_kwargs = {
            # Derived from division in validate(); never typed by hand.
            'academic_year': {'required': False},
            'department': {'required': False},
            'semester': {'required': False},
            'subject_name': {'required': False, 'allow_blank': True},
        }

    @staticmethod
    def _is_lab(role):
        return str(role) == TeachingAssignment.Role.LAB_INSTRUCTOR

    def validate(self, attrs):
        from apps.academic_structure.models import Division
        scheme_subject = attrs.get('scheme_subject') or (
            self.instance.scheme_subject if self.instance else None)
        if scheme_subject:
            attrs['subject_name'] = scheme_subject.subject.title
            attrs['subject_code'] = scheme_subject.course_code
        division = attrs.get('division') or (self.instance.division if self.instance else None)
        if division is not None:
            # Derive term context from the division; never trust mismatches.
            attrs.setdefault('academic_year', division.academic_year)
            attrs.setdefault('department', division.department)
            attrs.setdefault('semester', division.semester)
            if scheme_subject and scheme_subject.semester_number != division.semester.number:
                raise serializers.ValidationError(
                    {'scheme_subject': 'Subject belongs to Sem %s, division is Sem %s.' % (
                        scheme_subject.semester_number, division.semester.number)})
        faculty = attrs.get('faculty') or (self.instance.faculty if self.instance else None)
        code = (attrs.get('subject_code') or (self.instance.subject_code if self.instance else '') or '').strip().upper()
        role = attrs.get('role') or (self.instance.role if self.instance else TeachingAssignment.Role.PRIMARY_FACULTY)
        if not code:
            raise serializers.ValidationError({'subject_code': 'Subject is required.'})
        if division is not None:
            qs = TeachingAssignment.objects.filter(division=division, is_active=True)
            if self.instance:
                qs = qs.exclude(id=self.instance.id)
            # Rule 1: this teacher holds no *other* subject in the division.
            other = qs.filter(faculty=faculty).exclude(subject_code__iexact=code).first()
            if faculty is not None and other:
                raise serializers.ValidationError(
                    '%s already teaches %s in this division (one subject per teacher per class).' % (
                        other.faculty.display_name, other.subject_code))
            # Rule 2: this slot has no other active teacher.
            holder = qs.filter(subject_code__iexact=code)
            holder = holder.filter(
                role=TeachingAssignment.Role.LAB_INSTRUCTOR) if self._is_lab(role) else holder.exclude(
                role=TeachingAssignment.Role.LAB_INSTRUCTOR)
            holder = holder.exclude(faculty=faculty).first()
            if holder:
                raise serializers.ValidationError(
                    '%s is already taken by %s. Deactivate it first to replace.' % (
                        code, holder.faculty.display_name))
        return attrs


class FacultyListSerializer(serializers.ModelSerializer):
    """Compact serializer for faculty directory search."""

    department_name = serializers.CharField(source='department.name', read_only=True)
    department_code = serializers.CharField(source='department.code', read_only=True)
    designation_display = serializers.CharField(source='get_designation_display', read_only=True)

    class Meta:
        model = Faculty
        fields = [
            'id',
            'employee_code',
            'first_name',
            'last_name',
            'display_name',
            'department_id',
            'department_name',
            'department_code',
            'designation',
            'designation_display',
            'employment_type',
            'employment_status',
            'official_email',
            'mobile',
        ]


class FacultyProfileSerializer(serializers.ModelSerializer):
    """
    Full composed projection for faculty profile page.
    Matches AICTE biodata standards.
    """

    department_name = serializers.CharField(source='department.name', read_only=True)
    department_code = serializers.CharField(source='department.code', read_only=True)
    designation_display = serializers.CharField(source='get_designation_display', read_only=True)
    employment_type_display = serializers.CharField(source='get_employment_type_display', read_only=True)
    employment_status_display = serializers.CharField(source='get_employment_status_display', read_only=True)

    personal_details = FacultyPersonalDetailSerializer(read_only=True)
    addresses = FacultyAddressSerializer(many=True, read_only=True)
    qualifications = FacultyQualificationSerializer(many=True, read_only=True)
    experiences = FacultyExperienceSerializer(many=True, read_only=True)
    publications = FacultyPublicationSerializer(many=True, read_only=True)
    guidance_records = FacultyGuidanceSerializer(many=True, read_only=True)
    bank_accounts = FacultyBankAccountMaskedSerializer(many=True, read_only=True)
    documents = FacultyDocumentSerializer(many=True, read_only=True)
    teaching_assignments = TeachingAssignmentSerializer(many=True, read_only=True)

    class Meta:
        model = Faculty
        fields = [
            'id',
            'employee_code',
            'first_name',
            'middle_name',
            'last_name',
            'display_name',
            'department_id',
            'department_name',
            'department_code',
            'designation',
            'designation_display',
            'employment_type',
            'employment_type_display',
            'employment_status',
            'employment_status_display',
            'date_of_joining',
            'date_of_relieving',
            'official_email',
            'personal_email',
            'mobile',
            'residential_telephone',
            'personal_details',
            'addresses',
            'qualifications',
            'experiences',
            'publications',
            'guidance_records',
            'bank_accounts',
            'documents',
            'teaching_assignments',
            'created_at',
            'updated_at',
        ]
