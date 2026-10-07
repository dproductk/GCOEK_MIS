"""
Serializers for Results and Eligibility Domain.
"""
from rest_framework import serializers

from apps.results.models import (
    EligibilityVerification,
    SemesterResult,
    SubjectResult,
)


class SubjectResultSerializer(serializers.ModelSerializer):
    grade_letter_display = serializers.CharField(source='get_grade_letter_display', read_only=True)
    theory_marks = serializers.DecimalField(source='theory_ese_marks', max_digits=5, decimal_places=1, read_only=True)
    mid1_marks = serializers.SerializerMethodField()
    mid2_marks = serializers.SerializerMethodField()

    class Meta:
        model = SubjectResult
        fields = [
            'id',
            'course_code',
            'course_name',
            'credits',
            'mid1_marks',
            'mid2_marks',
            'theory_marks',
            'theory_ese_marks',
            'theory_ise_marks',
            'practical_marks',
            'total_marks',
            'grade_point',
            'grade_letter',
            'grade_letter_display',
            'is_backlog',
        ]

    def get_mid1_marks(self, obj):
        if obj.mid1_marks is not None:
            return obj.mid1_marks
        if obj.theory_ise_marks is not None:
            ise = float(obj.theory_ise_marks)
            return min(20.0, round(ise / 2.0, 1))
        return None

    def get_mid2_marks(self, obj):
        if obj.mid2_marks is not None:
            return obj.mid2_marks
        if obj.theory_ise_marks is not None:
            ise = float(obj.theory_ise_marks)
            m1 = min(20.0, round(ise / 2.0, 1))
            return max(0.0, round(ise - m1, 1))
        return None


class SemesterResultSerializer(serializers.ModelSerializer):
    result_status_display = serializers.CharField(source='get_result_status_display', read_only=True)
    academic_year_code = serializers.CharField(source='academic_year.code', read_only=True)
    semester_number = serializers.IntegerField(source='semester.number', read_only=True)
    student_name = serializers.CharField(source='student.display_name', read_only=True)
    enrollment_no = serializers.CharField(source='student.enrollment_no', read_only=True)
    subjects = SubjectResultSerializer(source='subject_results', many=True, read_only=True)

    class Meta:
        model = SemesterResult
        fields = [
            'id',
            'student_id',
            'student_name',
            'enrollment_no',
            'academic_year_code',
            'semester_number',
            'exam_session',
            'seat_number',
            'sgpa',
            'cgpa',
            'total_credits_registered',
            'total_credits_earned',
            'backlog_count',
            'result_status',
            'result_status_display',
            'is_published',
            'published_at',
            'subjects',
        ]


class EligibilityVerificationSerializer(serializers.ModelSerializer):
    calculated_status_display = serializers.CharField(source='get_calculated_status_display', read_only=True)
    class_teacher_status_display = serializers.CharField(source='get_class_teacher_status_display', read_only=True)
    hod_status_display = serializers.CharField(source='get_hod_status_display', read_only=True)

    student_name = serializers.CharField(source='student.display_name', read_only=True)
    enrollment_no = serializers.CharField(source='student.enrollment_no', read_only=True)
    department_code = serializers.CharField(source='department.code', read_only=True)
    target_semester_number = serializers.IntegerField(source='target_semester.number', read_only=True)
    is_locked_for_teacher = serializers.BooleanField(read_only=True)
    class_teacher_name = serializers.CharField(source='class_teacher.get_full_name', read_only=True)
    hod_name = serializers.CharField(source='hod.get_full_name', read_only=True)
    semester_results = serializers.SerializerMethodField()

    class Meta:
        model = EligibilityVerification
        fields = [
            'id',
            'student_id',
            'student_name',
            'enrollment_no',
            'department_code',
            'target_semester_number',
            'active_backlog_count',
            'total_credits_earned',
            'calculated_status',
            'calculated_status_display',
            'class_teacher_status',
            'class_teacher_status_display',
            'class_teacher_remarks',
            'class_teacher_reviewed_at',
            'class_teacher_name',
            'hod_status',
            'hod_status_display',
            'hod_remarks',
            'hod_reviewed_at',
            'hod_name',
            'final_eligible',
            'is_locked_for_teacher',
            'semester_results',
        ]

    def get_semester_results(self, obj):
        student = getattr(obj, 'student', None)
        if student and hasattr(student, '_prefetched_objects_cache') and 'semester_results' in student._prefetched_objects_cache:
            results = sorted(student.semester_results.all(), key=lambda r: (r.semester.number if r.semester else 0))
            return SemesterResultSerializer(results, many=True).data
        results = SemesterResult.objects.filter(
            student_id=obj.student_id
        ).prefetch_related('subject_results').order_by('semester__number')
        return SemesterResultSerializer(results, many=True).data
