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


class DivisionSerializer(serializers.ModelSerializer):
    department_code = serializers.CharField(source='department.code', read_only=True)
    department_name = serializers.CharField(source='department.name', read_only=True)
    academic_year_code = serializers.CharField(source='academic_year.code', read_only=True)
    semester_number = serializers.IntegerField(source='semester.number', read_only=True)
    semester_name = serializers.CharField(source='semester.name', read_only=True)
    year_level = serializers.IntegerField(source='semester.year_level', read_only=True)
    year_label = serializers.SerializerMethodField()
    class_code = serializers.SerializerMethodField()
    class_teacher_name = serializers.SerializerMethodField()
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
            'seat_capacity',
            'is_active',
            'enrolled_count',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'enrolled_count', 'year_label', 'class_code', 'year_level']

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
        if obj.class_teacher:
            return obj.class_teacher.username
        return None

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
