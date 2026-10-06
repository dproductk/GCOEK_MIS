"""
Serializers for Admissions Ingestion Domain.
"""
from rest_framework import serializers
from apps.admissions.models import ImportBatch, ImportRow, StudentAdmission


class ImportRowSerializer(serializers.ModelSerializer):
    validation_status_display = serializers.CharField(source='get_validation_status_display', read_only=True)
    matching_status_display = serializers.CharField(source='get_matching_status_display', read_only=True)

    class Meta:
        model = ImportRow
        fields = [
            'id',
            'row_number',
            'application_id',
            'enrollment_no',
            'choice_code',
            'program_code',
            'candidate_name',
            'allotted_course',
            'validation_status',
            'validation_status_display',
            'validation_errors',
            'matching_status',
            'matching_status_display',
            'matching_detail',
            'normalized_data',
            'import_error',
            'student_id',
        ]


class ImportBatchSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    admission_type_display = serializers.CharField(source='get_admission_type_display', read_only=True)
    academic_year_code = serializers.CharField(source='academic_year.code', read_only=True)
    uploaded_by_name = serializers.CharField(source='uploaded_by.username', read_only=True)

    class Meta:
        model = ImportBatch
        fields = [
            'id',
            'file_name',
            'admission_type',
            'admission_type_display',
            'file_size',
            'file_checksum',
            'academic_year_id',
            'academic_year_code',
            'status',
            'status_display',
            'total_rows',
            'valid_rows',
            'invalid_rows',
            'duplicate_rows',
            'conflict_rows',
            'failed_rows',
            'imported_rows',
            'uploaded_by_name',
            'created_at',
            'completed_at',
            'summary_report',
        ]


class ImportBatchDetailSerializer(ImportBatchSerializer):
    rows = ImportRowSerializer(many=True, read_only=True)

    class Meta(ImportBatchSerializer.Meta):
        fields = ImportBatchSerializer.Meta.fields + ['rows']
