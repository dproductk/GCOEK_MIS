"""
Serializers for Student domain.

Enforces:
- Sensitive data masking by default (Aadhaar & Bank numbers).
- Profile composition read projections per DATABASE_ARCHITECTURE_V2.md Section 9.
"""
from rest_framework import serializers

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


class StudentPersonalDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentPersonalDetail
        fields = [
            'date_of_birth',
            'gender',
            'place_of_birth',
            'religion',
            'nationality',
            'mother_tongue',
            'domicile_state',
            'student_email',
            'student_mobile',
            'blood_group',
            'caste',
            'marital_status',
            'abc_id',
        ]


class StudentGuardianSerializer(serializers.ModelSerializer):
    relationship_display = serializers.CharField(source='get_relationship_display', read_only=True)

    class Meta:
        model = StudentGuardian
        fields = [
            'id',
            'relationship',
            'relationship_display',
            'name',
            'mobile',
            'email',
            'occupation',
            'annual_income',
            'is_primary',
        ]


class StudentAddressSerializer(serializers.ModelSerializer):
    address_type_display = serializers.CharField(source='get_address_type_display', read_only=True)

    class Meta:
        model = StudentAddress
        fields = [
            'id',
            'address_type',
            'address_type_display',
            'address_line_1',
            'address_line_2',
            'address_line_3',
            'village',
            'taluka',
            'district',
            'state',
            'pincode',
            'is_current',
        ]


class StudentAadhaarMaskedSerializer(serializers.ModelSerializer):
    """Masked Aadhaar serializer. Plaintext/encrypted values are never exposed."""

    class Meta:
        model = StudentAadhaarDetail
        fields = [
            'aadhaar_number_masked',
            'enrolment_id',
            'verified',
        ]


class StudentBankAccountMaskedSerializer(serializers.ModelSerializer):
    """Masked Bank serializer."""

    class Meta:
        model = StudentBankAccount
        fields = [
            'id',
            'account_holder_name',
            'bank_name',
            'branch_name',
            'ifsc_code',
            'account_number_masked',
            'is_primary',
        ]


class StudentDocumentSerializer(serializers.ModelSerializer):
    document_type_display = serializers.CharField(source='get_document_type_display', read_only=True)

    class Meta:
        model = StudentDocument
        fields = [
            'id',
            'document_type',
            'document_type_display',
            'title',
            'file_size',
            'mime_type',
            'is_verified',
            'version',
            'created_at',
        ]


class StudentEnrollmentSerializer(serializers.ModelSerializer):
    department_code = serializers.CharField(source='department.code', read_only=True)
    department_name = serializers.CharField(source='department.name', read_only=True)
    program_name = serializers.CharField(source='program.name', read_only=True)
    semester_number = serializers.IntegerField(source='semester.number', read_only=True)
    division_name = serializers.CharField(source='division.name', read_only=True, default='')
    lab_batch_name = serializers.CharField(source='lab_batch.name', read_only=True, default='')
    academic_year_code = serializers.CharField(source='academic_year.code', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = StudentEnrollment
        fields = [
            'id',
            'academic_year',
            'academic_year_code',
            'department',
            'department_code',
            'department_name',
            'program',
            'program_name',
            'semester',
            'semester_number',
            'division',
            'division_name',
            'lab_batch',
            'lab_batch_name',
            'roll_number',
            'status',
            'status_display',
            'is_current',
        ]


class StudentListSerializer(serializers.ModelSerializer):
    """Lightweight summary serializer for directories and search."""

    department_code = serializers.SerializerMethodField()
    program_code = serializers.SerializerMethodField()
    semester_number = serializers.SerializerMethodField()
    division_id = serializers.SerializerMethodField()
    division_name = serializers.SerializerMethodField()
    lab_batch_id = serializers.SerializerMethodField()
    lab_batch_name = serializers.SerializerMethodField()
    year_level = serializers.SerializerMethodField()
    year_name = serializers.SerializerMethodField()
    father_name = serializers.SerializerMethodField()
    mobile = serializers.SerializerMethodField()
    gender = serializers.SerializerMethodField()
    username = serializers.SerializerMethodField()
    has_login = serializers.SerializerMethodField()
    is_eligible = serializers.SerializerMethodField()
    suggested_semester = serializers.SerializerMethodField()
    suggested_year = serializers.SerializerMethodField()
    placement_finalized = serializers.SerializerMethodField()
    admission_year_code = serializers.SerializerMethodField()
    admission_type = serializers.CharField(read_only=True)

    class Meta:
        model = Student
        fields = [
            'id',
            'enrollment_no',
            'application_id',
            'display_name',
            'first_name',
            'middle_name',
            'last_name',
            'status',
            'is_direct_second_year',
            'department_code',
            'program_code',
            'semester_number',
            'year_level',
            'year_name',
            'division_id',
            'division_name',
            'lab_batch_id',
            'lab_batch_name',
            'father_name',
            'mobile',
            'gender',
            'username',
            'has_login',
            'is_eligible',
            'suggested_semester',
            'suggested_year',
            'placement_finalized',
            'admission_year_code',
            'admission_type',
        ]

    def get_is_eligible(self, obj):
        # Use prefetched in-memory records to eliminate N+1 SQL queries
        if hasattr(obj, '_prefetched_objects_cache') and 'eligibility_records' in obj._prefetched_objects_cache:
            if any(r.final_eligible for r in obj.eligibility_records.all()):
                return True
        elif obj.eligibility_records.filter(final_eligible=True).exists():
            return True
        # First-year auto-eligibility by admission: FY in Sem 1, or DSE in
        # Sem 3, admitted in the current year — AND seated in a division
        # with an assigned class teacher (common rule: no class, no
        # verification/fee eligibility, for every year including FY).
        ctx = self._placement_ctx()
        current_year_id = ctx.get('current_year_id')
        if not current_year_id or str(getattr(obj, 'admission_year_id', '') or '') != str(current_year_id):
            return False
        curr = self._get_current(obj)
        sem_no = curr.semester.number if curr and curr.semester else None
        adm_type = (obj.admission_type or 'FY').upper()
        if not ((adm_type == 'FY' and sem_no == 1) or (adm_type == 'DSE' and sem_no == 3)):
            return False
        division = curr.division if curr and curr.division_id else None
        return bool(division is not None and getattr(division, 'class_teacher_id', None))

    def _placement_ctx(self):
        return self.context.get('placement') or {}

    def _suggestion(self, obj):
        from apps.students.placement import suggest_semester
        adm_year = getattr(obj, 'admission_year', None)
        ctx = self._placement_ctx()
        if not adm_year or not ctx.get('current_year_start'):
            return None, None
        try:
            sem, year, _ = suggest_semester(
                adm_year.code.split('-')[0], obj.admission_type or 'FY',
                ctx['current_year_start'], ctx.get('term', 'ODD'))
        except Exception:
            return None, None
        names = {1: 'FY', 2: 'SY', 3: 'TY', 4: 'Final Year'}
        return sem, names.get(year, 'Final Year')

    def get_suggested_semester(self, obj):
        sem, _ = self._suggestion(obj)
        return sem

    def get_suggested_year(self, obj):
        _, year = self._suggestion(obj)
        return year

    def get_placement_finalized(self, obj):
        curr = self._get_current(obj)
        return bool(curr and curr.placement_confirmed)

    def get_admission_year_code(self, obj):
        adm_year = getattr(obj, 'admission_year', None)
        return adm_year.code if adm_year else None

    def _get_current(self, obj):
        curr = getattr(obj, '_current_enrollment', None)
        if curr is None:
            curr = obj.enrollments.filter(is_current=True).first()
        return curr

    def get_department_code(self, obj):
        curr = self._get_current(obj)
        if curr and curr.department:
            return curr.department.code
        return None

    def get_program_code(self, obj):
        curr = self._get_current(obj)
        if curr and hasattr(curr, 'program') and curr.program:
            return curr.program.code
        dept = self.get_department_code(obj)
        return dept or 'B.Tech'

    def get_semester_number(self, obj):
        curr = self._get_current(obj)
        if curr and curr.semester:
            return curr.semester.number
        return None

    def get_year_level(self, obj):
        curr = self._get_current(obj)
        if curr and curr.semester:
            return curr.semester.year_level
        return 1

    def get_year_name(self, obj):
        yl = self.get_year_level(obj)
        names = {1: 'FY', 2: 'SY', 3: 'TY', 4: 'Final Year'}
        return names.get(yl, 'FY')

    def get_division_id(self, obj):
        curr = self._get_current(obj)
        if curr and curr.division_id:
            return str(curr.division_id)
        return None

    def get_division_name(self, obj):
        curr = self._get_current(obj)
        if curr and curr.division:
            return curr.division.name
        return None

    def get_lab_batch_id(self, obj):
        curr = self._get_current(obj)
        if curr and curr.lab_batch_id:
            return str(curr.lab_batch_id)
        return None

    def get_lab_batch_name(self, obj):
        curr = self._get_current(obj)
        if curr and curr.lab_batch:
            return curr.lab_batch.name
        return None

    def get_father_name(self, obj):
        # Look in prefetched guardians first
        if hasattr(obj, 'guardians'):
            for g in obj.guardians.all():
                if g.relationship == 'FATHER' or g.is_primary:
                    return g.name
        # Fallback to middle_name + last_name if available
        if obj.middle_name:
            return f"{obj.middle_name} {obj.last_name}".strip().upper()
        return '—'

    def get_mobile(self, obj):
        if hasattr(obj, 'personal_details') and obj.personal_details:
            return obj.personal_details.student_mobile or '—'
        return '—'

    def get_gender(self, obj):
        if hasattr(obj, 'personal_details') and obj.personal_details:
            return obj.personal_details.gender or 'MALE'
        return 'MALE'

    def get_username(self, obj):
        if obj.user:
            return obj.user.username
        return obj.enrollment_no or obj.application_id or f"EN{obj.id}"

    def get_has_login(self, obj):
        return bool(obj.user_id)


class StudentProfileSerializer(serializers.ModelSerializer):
    """
    Full UI profile composition projection reading from normalized child tables.
    """

    personal_details = StudentPersonalDetailSerializer(read_only=True)
    guardians = StudentGuardianSerializer(many=True, read_only=True)
    addresses = StudentAddressSerializer(many=True, read_only=True)
    aadhaar_details = StudentAadhaarMaskedSerializer(read_only=True)
    bank_accounts = StudentBankAccountMaskedSerializer(many=True, read_only=True)
    documents = StudentDocumentSerializer(many=True, read_only=True)
    current_enrollment = serializers.SerializerMethodField()
    enrollment_history = serializers.SerializerMethodField()
    admission_details = serializers.SerializerMethodField()

    class Meta:
        model = Student
        fields = [
            'id',
            'enrollment_no',
            'application_id',
            'first_name',
            'middle_name',
            'last_name',
            'display_name',
            'status',
            'is_direct_second_year',
            'admission_details',
            'personal_details',
            'guardians',
            'addresses',
            'aadhaar_details',
            'bank_accounts',
            'documents',
            'current_enrollment',
            'enrollment_history',
            'created_at',
            'updated_at',
        ]

    def get_admission_details(self, obj):
        adm = obj.admissions.select_related('source_import_row').first()
        if not adm:
            return None
        row = getattr(adm, 'source_import_row', None)
        normalized = getattr(row, 'normalized_data', None) or {}
        if not isinstance(normalized, dict):
            normalized = {}
        raw = getattr(row, 'raw_data', None) or {}
        if not isinstance(raw, dict):
            raw = {}
        board_refs = normalized.get('board_refs') or {}
        if not isinstance(board_refs, dict):
            board_refs = {}

        def _norm_key(key):
            return ''.join(ch for ch in str(key).lower() if ch.isalnum())

        def _pick(*keys):
            wanted = {_norm_key(k) for k in keys}
            for source in (board_refs, normalized, raw):
                if not isinstance(source, dict):
                    continue
                normed = {_norm_key(k): v for k, v in source.items()}
                for key in wanted:
                    value = normed.get(key)
                    if value not in (None, ''):
                        return value
            return ''

        return {
            'admission_type': adm.admission_type,
            'admission_year': getattr(adm.academic_year, 'code', '') or getattr(obj.admission_year, 'code', ''),
            'admission_date': str(adm.admission_date) if adm.admission_date else '',
            'application_id': adm.application_id,
            'category': adm.category,
            'seat_type': adm.seat_type,
            'allotted_seat_type': adm.allotted_seat_type or adm.seat_type,
            'merit_no': adm.merit_no,
            'merit_marks': str(adm.merit_marks) if adm.merit_marks is not None else '',
            'entrance_exam_type': adm.entrance_exam_type,
            'diploma_seat_no': _pick('diploma_seat_no', 'diploma seat no', 'diploma seat number', 'diploma roll no'),
            'diploma_board': _pick('diploma_board', 'diploma examining authority', 'msbte'),
            'diploma_percentage': _pick('diploma_percentage', 'diploma aggregate percentage', 'diploma marks percentage', 'diploma total percentage'),
            'diploma_college': _pick('diploma_college', 'diploma_institute', 'diploma institute', 'diploma college'),
        }

    def get_current_enrollment(self, obj):
        curr = obj.enrollments.filter(is_current=True).select_related(
            'department', 'program', 'semester', 'division', 'academic_year'
        ).first()
        if curr:
            return StudentEnrollmentSerializer(curr).data
        return None

    def get_enrollment_history(self, obj):
        history = obj.enrollments.all().select_related(
            'department', 'program', 'semester', 'division', 'academic_year'
        ).order_by('-academic_year__start_date', '-semester__number')
        return StudentEnrollmentSerializer(history, many=True).data
