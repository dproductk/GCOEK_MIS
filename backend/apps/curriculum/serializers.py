"""
Serializers for Curriculum domain (schemes, subjects, electives).
"""
from rest_framework import serializers

from apps.curriculum.models import (
    Scheme,
    SchemeElectiveGroup,
    SchemeElectiveOption,
    SchemeSubject,
    SchemeSubjectAssessmentComponent,
    Subject,
)


class SubjectSerializer(serializers.ModelSerializer):
    category_display = serializers.SerializerMethodField()
    exam_total = serializers.SerializerMethodField()

    class Meta:
        model = Subject
        fields = ['id', 'code', 'title', 'abbreviation', 'is_active',
                  'course_category', 'category_display',
                  'lecture_hours', 'practical_hours',
                  'ca_max_marks', 'mse_max_marks', 'ese_max_marks',
                  'practical_ca_max_marks', 'practical_ese_max_marks',
                  'credits', 'exam_total',
                  'created_at', 'updated_at']
        read_only_fields = ['id', 'category_display', 'exam_total', 'created_at', 'updated_at']

    def get_category_display(self, obj):
        return obj.get_course_category_display() if obj.course_category else ''

    def get_exam_total(self, obj):
        return obj.exam_total

    def validate_code(self, value):
        code = (value or '').strip()
        if not code:
            raise serializers.ValidationError('Subject code is required.')
        qs = Subject.objects.filter(code__iexact=code)
        if self.instance:
            qs = qs.exclude(id=self.instance.id)
        if qs.exists():
            raise serializers.ValidationError('Subject code already exists.')
        return code

    def validate(self, attrs):
        category = attrs.get('course_category',
                             getattr(self.instance, 'course_category', '') or '')
        if not category:
            return attrs  # legacy subject (code + title only) — allowed
        errors = {}
        credits = attrs.get('credits', getattr(self.instance, 'credits', None))
        if credits is None:
            errors['credits'] = 'Credit is required.'
        if category in Subject.THEORY_CATEGORIES:
            for f in ('ca_max_marks', 'mse_max_marks', 'ese_max_marks'):
                val = attrs.get(f, getattr(self.instance, f, None))
                if val is None:
                    errors[f] = 'Required for theory subjects.'
                elif float(val) < 0:
                    errors[f] = 'Must be zero or more.'
        elif category == Subject.CourseCategory.PCC_LAB:
            for f in ('practical_ca_max_marks', 'practical_ese_max_marks'):
                val = attrs.get(f, getattr(self.instance, f, None))
                if val is None:
                    errors[f] = 'Required for laboratory subjects.'
                elif float(val) < 0:
                    errors[f] = 'Must be zero or more.'
        else:  # Project / Internship / Seminar accept either scheme
            inst = self.instance
            theory_ok = all(
                (attrs.get(f, getattr(inst, f, None)) is not None)
                for f in ('ca_max_marks', 'mse_max_marks', 'ese_max_marks'))
            pract_ok = all(
                (attrs.get(f, getattr(inst, f, None)) is not None)
                for f in ('practical_ca_max_marks', 'practical_ese_max_marks'))
            if not (theory_ok or pract_ok):
                errors['ca_max_marks'] = (
                    'Give either the theory scheme (CA + MSE + ESE) '
                    'or the practical scheme (Practical CA + Practical ESE).')
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class AssessmentComponentSerializer(serializers.ModelSerializer):
    component_type_display = serializers.CharField(source='get_component_type_display', read_only=True)

    class Meta:
        model = SchemeSubjectAssessmentComponent
        fields = [
            'id', 'scheme_subject', 'component_type', 'component_type_display',
            'maximum_marks', 'minimum_marks', 'display_order',
        ]
        read_only_fields = ['id']


class SchemeSubjectSerializer(serializers.ModelSerializer):
    subject_code = serializers.CharField(source='subject.code', read_only=True)
    subject_title = serializers.CharField(source='subject.title', read_only=True)
    subject_category = serializers.CharField(source='subject.course_category', read_only=True)
    subject_category_display = serializers.SerializerMethodField()
    subject_lecture_hours = serializers.IntegerField(source='subject.lecture_hours', read_only=True)
    subject_practical_hours = serializers.IntegerField(source='subject.practical_hours', read_only=True)
    subject_ca_max_marks = serializers.DecimalField(
        source='subject.ca_max_marks', max_digits=6, decimal_places=1, read_only=True)
    subject_mse_max_marks = serializers.DecimalField(
        source='subject.mse_max_marks', max_digits=6, decimal_places=1, read_only=True)
    subject_ese_max_marks = serializers.DecimalField(
        source='subject.ese_max_marks', max_digits=6, decimal_places=1, read_only=True)
    subject_practical_ca_max_marks = serializers.DecimalField(
        source='subject.practical_ca_max_marks', max_digits=6, decimal_places=1, read_only=True)
    subject_practical_ese_max_marks = serializers.DecimalField(
        source='subject.practical_ese_max_marks', max_digits=6, decimal_places=1, read_only=True)
    subject_credits = serializers.IntegerField(source='subject.credits', read_only=True)
    subject_exam_total = serializers.SerializerMethodField()
    assessment_components = AssessmentComponentSerializer(many=True, read_only=True)

    class Meta:
        model = SchemeSubject
        fields = [
            'id', 'scheme', 'subject', 'subject_code', 'subject_title',
            'subject_category', 'subject_category_display',
            'subject_lecture_hours', 'subject_practical_hours',
            'subject_ca_max_marks', 'subject_mse_max_marks', 'subject_ese_max_marks',
            'subject_practical_ca_max_marks', 'subject_practical_ese_max_marks',
            'subject_credits', 'subject_exam_total',
            'semester_number', 'course_code', 'course_level_code', 'course_type_code',
            'credits', 'total_marks', 'is_elective', 'elective_group',
            'display_order', 'assessment_components',
        ]
        read_only_fields = ['id']
        extra_kwargs = {
            # Auto-filled from the Subject master when omitted (no retyping).
            'course_code': {'required': False, 'allow_blank': True},
            'credits': {'required': False},
            'total_marks': {'required': False},
        }
        # NOTE: the auto UniqueTogetherValidator is disabled on purpose.
        # DRF >= 3.15 forces an implied 'required' on every unique-together
        # member, which would re-require the auto-filled course_code before
        # validate() gets a chance to fill it. Uniqueness is enforced
        # manually in validate() instead (see below).
        validators = []

    def get_subject_category_display(self, obj):
        return obj.subject.get_course_category_display() if obj.subject.course_category else ''

    def get_subject_exam_total(self, obj):
        return obj.subject.exam_total

    def validate_semester_number(self, value):
        if not 1 <= value <= 8:
            raise serializers.ValidationError('Semester must be 1-8.')
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        subject = attrs.get('subject', getattr(self.instance, 'subject', None))
        creating = self.instance is None
        if subject is not None:
            if creating and not (attrs.get('course_code') or '').strip():
                attrs['course_code'] = subject.code
            elif 'course_code' in attrs and not (attrs.get('course_code') or '').strip():
                attrs['course_code'] = subject.code
            if creating and attrs.get('credits') is None:
                attrs['credits'] = subject.credits if subject.credits is not None else 3
            if creating and attrs.get('total_marks') is None:
                total = subject.exam_total
                attrs['total_marks'] = int(total) if total is not None else 100
        # Manual uniqueness guard for (scheme, semester, course) — replaces
        # the disabled auto UniqueTogetherValidator (see Meta.validators).
        # Raised on the visible Subject field so the UI can show it.
        scheme = attrs.get('scheme', getattr(self.instance, 'scheme', None))
        semester = attrs.get('semester_number', getattr(self.instance, 'semester_number', None))
        code = (attrs.get('course_code', getattr(self.instance, 'course_code', None)) or '').strip()
        if scheme is not None and semester is not None and code:
            dup = SchemeSubject.objects.filter(
                scheme=scheme, semester_number=semester, course_code__iexact=code)
            if self.instance is not None:
                dup = dup.exclude(id=self.instance.id)
            if dup.exists():
                raise serializers.ValidationError(
                    {'subject': 'This subject is already added to this semester of the scheme.'})
        return attrs


class ElectiveOptionSerializer(serializers.ModelSerializer):
    subject_code = serializers.CharField(source='subject.code', read_only=True)

    class Meta:
        model = SchemeElectiveOption
        fields = ['id', 'elective_group', 'subject', 'subject_code', 'scheme_subject', 'display_order']
        read_only_fields = ['id']


class ElectiveGroupSerializer(serializers.ModelSerializer):
    options = ElectiveOptionSerializer(many=True, read_only=True)

    class Meta:
        model = SchemeElectiveGroup
        fields = [
            'id', 'scheme', 'semester_number', 'group_code', 'title',
            'minimum_selection', 'maximum_selection', 'options',
        ]
        read_only_fields = ['id']


class SchemeSerializer(serializers.ModelSerializer):
    program_name = serializers.CharField(source='program.name', read_only=True, default=None)
    department_code = serializers.CharField(source='department.code', read_only=True, default=None)
    from_year_code = serializers.CharField(source='effective_from_year.code', read_only=True)
    to_year_code = serializers.CharField(source='effective_to_year.code', read_only=True, default=None)
    scheme_subjects = SchemeSubjectSerializer(many=True, read_only=True)
    elective_groups = ElectiveGroupSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Scheme
        fields = [
            'id', 'code', 'name', 'program', 'program_name',
            'department', 'department_code',
            'effective_from_year', 'from_year_code',
            'effective_to_year', 'to_year_code',
            'version', 'status', 'status_display',
            'min_theory_marks', 'min_total_marks', 'max_backlogs_for_atkt',
            'scheme_subjects', 'elective_groups',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'department', 'created_at', 'updated_at']
        extra_kwargs = {'program': {'required': False, 'allow_null': True}}

    def validate(self, attrs):
        from apps.academic_structure.models import AcademicYear, Program

        program = attrs.get('program', getattr(self.instance, 'program', None))
        if program is not None:
            prog_id = program.id if hasattr(program, 'id') else program
            if not Program.objects.filter(id=prog_id).exists():
                raise serializers.ValidationError({'program': 'Program not found.'})
        from_y = attrs.get('effective_from_year') or (self.instance.effective_from_year if self.instance else None)
        if from_y is not None:
            from_id = from_y.id if hasattr(from_y, 'id') else from_y
            if not AcademicYear.objects.filter(id=from_id).exists():
                raise serializers.ValidationError({'effective_from_year': 'Academic year not found.'})
        to_y = attrs.get('effective_to_year', getattr(self.instance, 'effective_to_year', None))
        if to_y is not None:
            to_id = to_y.id if hasattr(to_y, 'id') else to_y
            if not AcademicYear.objects.filter(id=to_id).exists():
                raise serializers.ValidationError({'effective_to_year': 'Academic year not found.'})
        code = attrs.get('code', getattr(self.instance, 'code', None))
        version = attrs.get('version', getattr(self.instance, 'version', None))
        if code is not None and version is not None:
            qs = Scheme.objects.filter(code__iexact=str(code).strip(), version=version)
            if self.instance:
                qs = qs.exclude(id=self.instance.id)
            if qs.exists():
                raise serializers.ValidationError('Scheme code+version already exists.')
        return attrs

    def create(self, validated_data):
        # Department is derived from program; never asked from the user.
        program = validated_data.get('program')
        if program is not None and not validated_data.get('department'):
            dept_id = program.department_id if hasattr(program, 'department_id') else None
            if dept_id:
                from apps.academic_structure.models import Department
                validated_data['department'] = Department.objects.filter(id=dept_id).first()
        return super().create(validated_data)
