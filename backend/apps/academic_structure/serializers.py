"""
Serializers for Academic Structure domain.
"""
from rest_framework import serializers

from apps.academic_structure.models import (
    AcademicContext,
    AcademicYear,
    Department,
    Division,
    LabBatch,
    Program,
    Semester,
)
from apps.authentication.models import User


class DepartmentSerializer(serializers.ModelSerializer):
    programs_count = serializers.SerializerMethodField()
    divisions_count = serializers.SerializerMethodField()

    class Meta:
        model = Department
        fields = [
            'id',
            'name',
            'code',
            'choice_code',
            'seat_capacity',
            'start_date',
            'description',
            'is_active',
            'programs_count',
            'divisions_count',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'programs_count', 'divisions_count']

    def get_programs_count(self, obj):
        annotated = getattr(obj, '_programs_count', None)
        if annotated is not None:
            return annotated
        return obj.programs.filter(is_active=True).count()

    def get_divisions_count(self, obj):
        annotated = getattr(obj, '_divisions_count', None)
        if annotated is not None:
            return annotated
        return obj.divisions.filter(is_active=True).count()


class ProgramSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source='department.name', read_only=True)
    department_code = serializers.CharField(source='department.code', read_only=True)

    class Meta:
        model = Program
        fields = [
            'id',
            'department',
            'department_name',
            'department_code',
            'name',
            'code',
            'university_program_code',
            'degree_type',
            'duration_years',
            'total_semesters',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class AcademicYearSerializer(serializers.ModelSerializer):
    class Meta:
        model = AcademicYear
        fields = [
            'id',
            'code',
            'name',
            'start_date',
            'end_date',
            'is_current',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {
            # Auto-generated when blank so the sysadmin form can leave it empty.
            'name': {'required': False, 'allow_blank': True},
        }

    def validate_code(self, value):
        """Normalize and validate the academic year code.

        Canonical form is ``YYYY-YY`` (e.g. ``2027-28``). The long form
        ``YYYY-YYYY`` (e.g. ``2027-2028``) and ``/`` separators are accepted
        and normalized to the canonical form.
        """
        import re

        raw = (value or '').strip().replace('/', '-')
        # Accept long form 2027-2028 -> 2027-28.
        m_long = re.fullmatch(r'\s*((?:19|20)\d{2})\s*-\s*((?:19|20)\d{2})\s*', raw)
        if m_long:
            start_full = int(m_long.group(1))
            end_full = int(m_long.group(2))
            if end_full != start_full + 1:
                raise serializers.ValidationError(
                    'Academic years must span consecutive years (e.g. 2027-28).'
                )
            raw = f'{start_full}-{str(end_full)[-2:]}'

        if not re.fullmatch(r'(?:19|20)\d{2}-\d{2}', raw):
            raise serializers.ValidationError(
                'Code must look like 2027-28 (start year plus last two digits of the next year).'
            )
        try:
            start_year = int(raw[:4])
            suffix = int(raw[5:7])
        except ValueError:
            raise serializers.ValidationError(
                'Code must look like 2027-28 (start year plus last two digits of the next year).'
            )
        if suffix != (start_year + 1) % 100:
            raise serializers.ValidationError(
                f'Code {raw} is inconsistent: the second part must be {(start_year + 1) % 100:02d} '
                f'for start year {start_year} (e.g. {start_year}-{(start_year + 1) % 100:02d}).'
            )

        qs = AcademicYear.objects.filter(code__iexact=raw)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                f"Academic year '{raw}' already exists."
            )
        return raw

    def validate(self, attrs):
        attrs = super().validate(attrs)

        instance = self.instance
        code = attrs.get('code', getattr(instance, 'code', None))
        start = attrs.get('start_date', getattr(instance, 'start_date', None))
        end = attrs.get('end_date', getattr(instance, 'end_date', None))
        name = attrs.get('name', getattr(instance, 'name', ''))

        if start is None or end is None:
            return attrs

        if start >= end:
            raise serializers.ValidationError({
                'end_date': 'Conclusion date must be after the commencement date.',
            })

        # An academic year is ~12 months (July -> June). Bounds keep typos
        # like 2027-07-01 -> 2027-08-01 out while tolerating leap years.
        duration_days = (end - start).days
        if duration_days < 300 or duration_days > 400:
            raise serializers.ValidationError({
                'end_date': (
                    'Academic year must span roughly 12 months '
                    f'(got {duration_days} days from {start} to {end}). '
                    'Expected e.g. 2027-07-01 to 2028-06-30.'
                ),
            })

        # Code/start-year consistency: 2027-28 must start in 2027 and end in 2028.
        if code:
            try:
                start_year = int(str(code)[:4])
                if start.year != start_year or end.year != start_year + 1:
                    raise serializers.ValidationError({
                        'start_date': (
                            f"Dates do not match code '{code}': expected commencement in "
                            f'{start_year} and conclusion in {start_year + 1} '
                            f'(e.g. {start_year}-07-01 to {start_year + 1}-06-30).'
                        ),
                    })
            except (ValueError, TypeError):
                pass

        # No overlapping date ranges with another academic year.
        overlap_qs = AcademicYear.objects.filter(
            start_date__lte=end,
            end_date__gte=start,
        )
        if instance is not None:
            overlap_qs = overlap_qs.exclude(pk=instance.pk)
        clash = overlap_qs.order_by('code').first()
        if clash:
            raise serializers.ValidationError({
                'start_date': (
                    f"Date range overlaps academic year '{clash.code}' "
                    f'({clash.start_date} to {clash.end_date}). '
                    'Academic years must not overlap.'
                ),
            })

        # Auto-generate a display name when left blank.
        if not (name or '').strip() and start and end:
            attrs['name'] = f'Academic Year {start.year}-{end.year}'

        return attrs


class AcademicContextSerializer(serializers.ModelSerializer):
    academic_year_code = serializers.CharField(source='academic_year.code', read_only=True)
    term_display = serializers.CharField(source='get_term_display', read_only=True)

    class Meta:
        model = AcademicContext
        fields = [
            'id',
            'academic_year',
            'academic_year_code',
            'term',
            'term_display',
            'start_date',
            'end_date',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class SemesterSerializer(serializers.ModelSerializer):
    term_type_display = serializers.CharField(source='get_term_type_display', read_only=True)

    class Meta:
        model = Semester
        fields = [
            'id',
            'number',
            'name',
            'year_level',
            'term_type',
            'term_type_display',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ClassTeacherField(serializers.PrimaryKeyRelatedField):
    """Accepts either a User ID or a Faculty ID and resolves to the User instance."""

    def to_internal_value(self, data):
        if not data:
            return None
        from django.core.exceptions import ValidationError as DjangoValidationError
        from apps.authentication.models import User
        from apps.faculty.models import Faculty
        # 1. Try as direct User ID
        try:
            return User.objects.get(id=data)
        except (User.DoesNotExist, ValueError, DjangoValidationError):
            pass
        # 2. Try as Faculty ID (HOD and Frontend pass Faculty.id)
        try:
            faculty = Faculty.objects.select_related('user').get(id=data)
        except (Faculty.DoesNotExist, ValueError, DjangoValidationError):
            faculty = None
        if faculty is None:
            raise serializers.ValidationError(
                f'Invalid class teacher "{data}" - neither a valid User nor Faculty ID.'
            )
        if faculty.user_id is None:
            raise serializers.ValidationError(
                f'{faculty.display_name} has no login account yet. Create one first.'
            )
        return faculty.user


class DivisionSerializer(serializers.ModelSerializer):
    department_code = serializers.CharField(source='department.code', read_only=True)
    department_name = serializers.CharField(source='department.name', read_only=True)
    academic_year_code = serializers.CharField(source='academic_year.code', read_only=True)
    semester_number = serializers.IntegerField(source='semester.number', read_only=True)
    semester_name = serializers.CharField(source='semester.name', read_only=True)
    year_level = serializers.IntegerField(source='semester.year_level', read_only=True)
    year_label = serializers.SerializerMethodField()
    class_code = serializers.SerializerMethodField()
    class_teacher = ClassTeacherField(queryset=User.objects.all(), required=False, allow_null=True)
    class_teacher_name = serializers.SerializerMethodField()
    class_teacher_faculty_id = serializers.SerializerMethodField()
    enrolled_count = serializers.SerializerMethodField()

    class Meta:
        model = Division
        fields = [
            'id',
            'department',
            'department_code',
            'department_name',
            'academic_year',
            'academic_year_code',
            'semester',
            'semester_number',
            'semester_name',
            'year_level',
            'year_label',
            'name',
            'class_code',
            'class_teacher',
            'class_teacher_name',
            'class_teacher_faculty_id',
            'seat_capacity',
            'is_active',
            'enrolled_count',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'enrolled_count', 'year_label', 'class_code', 'year_level', 'class_teacher_faculty_id']

    def get_year_label(self, obj):
        # Same mapping as StudentListSerializer.year_name (FY/SY/TY/Final Year).
        # Derived from semester.year_level — never stored (no duplicate truth).
        try:
            yl = obj.semester.year_level if obj.semester else None
        except AttributeError:
            yl = None
        return {1: 'FY', 2: 'SY', 3: 'TY', 4: 'Final Year'}.get(yl, 'FY')

    def get_class_code(self, obj):
        # Read-only display projection (dept + sem + division), e.g. CSE-Sem3-A.
        # Not a stored column: dept/year/sem/name unique_together is the truth.
        try:
            dept = obj.department.code if obj.department else 'DEPT'
            sem = obj.semester.number if obj.semester else '?'
            return f'{dept}-Sem{sem}-{obj.name}'
        except AttributeError:
            return f'Div {getattr(obj, "name", "?")}'

    def get_class_teacher_name(self, obj):
        user = obj.class_teacher
        if not user:
            return None
        # Division.class_teacher points at the login User; the human-readable
        # name lives on the linked Faculty profile (display_name).
        profile = getattr(user, 'faculty_profile', None)
        if profile and getattr(profile, 'display_name', ''):
            return profile.display_name
        full = user.get_full_name()
        return full or user.username

    def get_class_teacher_faculty_id(self, obj):
        user = obj.class_teacher
        if not user:
            return None
        profile = getattr(user, 'faculty_profile', None)
        return str(profile.id) if profile else None

    def get_enrolled_count(self, obj):
        # Prefers the annotated value from the ViewSet (no N+1). Falls back
        # to a single filtered count for un-annotated contexts (detail, tests).
        annotated = getattr(obj, '_annotated_enrolled_count', None)
        if annotated is not None:
            return annotated
        from apps.students.models import StudentEnrollment
        return StudentEnrollment.objects.filter(division=obj, is_current=True).count()


class LabBatchSerializer(serializers.ModelSerializer):
    division_name = serializers.CharField(source='division.name', read_only=True)
    department_code = serializers.CharField(source='division.department.code', read_only=True)

    class Meta:
        model = LabBatch
        fields = [
            'id',
            'division',
            'division_name',
            'department_code',
            'name',
            'seat_capacity',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
