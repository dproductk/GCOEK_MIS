"""
Serializers for Fee Configuration and Payment Ledger.
"""
from rest_framework import serializers
from apps.finance.models import FeeHead, PaymentLedger, StudentFeeAssessment


class FeeHeadSerializer(serializers.ModelSerializer):
    category_quota_display = serializers.CharField(source='get_category_quota_display', read_only=True)
    academic_year_code = serializers.CharField(source='academic_year.code', read_only=True)
    program_name = serializers.CharField(source='program.name', read_only=True, default='')
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, default=0.0)

    class Meta:
        model = FeeHead
        fields = [
            'id',
            'name',
            'code',
            'tag',
            'description',
            'allowed_amounts',
            'display_order',
            'academic_year',
            'academic_year_code',
            'program',
            'program_name',
            'category_quota',
            'category_quota_display',
            'amount',
            'is_refundable',
            'is_active',
        ]

    def create(self, validated_data):
        if not validated_data.get('tag'):
            # Auto fallback tag from code or initials
            code = validated_data.get('code', '')
            validated_data['tag'] = code[:10].upper()
        # If amount not specified but allowed_amounts is present, set amount to highest allowed amount
        if (not validated_data.get('amount') or validated_data.get('amount') == 0) and validated_data.get('allowed_amounts'):
            try:
                validated_data['amount'] = max(float(x) for x in validated_data['allowed_amounts'])
            except Exception:
                pass
        return super().create(validated_data)


class PaymentLedgerSerializer(serializers.ModelSerializer):
    payment_mode_display = serializers.CharField(source='get_payment_mode_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    student_name = serializers.CharField(source='student.display_name', read_only=True)
    enrollment_no = serializers.CharField(source='student.enrollment_no', read_only=True)
    academic_year_code = serializers.CharField(source='academic_year.code', read_only=True)
    collected_by_name = serializers.CharField(source='collected_by.username', read_only=True, default='')

    class Meta:
        model = PaymentLedger
        fields = [
            'id',
            'receipt_no',
            'student',
            'student_name',
            'enrollment_no',
            'academic_year',
            'academic_year_code',
            'total_fee_due',
            'amount_paid',
            'balance_due',
            'payment_mode',
            'payment_mode_display',
            'transaction_ref',
            'status',
            'status_display',
            'payment_date',
            'collected_by_name',
            'remarks',
            'created_at',
        ]
        # Receipt numbers are server-sequenced; clients may omit them.
        extra_kwargs = {'receipt_no': {'required': False, 'allow_blank': True}}


class StudentFeeAssessmentSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.display_name', read_only=True)
    enrollment_no = serializers.CharField(source='student.enrollment_no', read_only=True)
    academic_year_code = serializers.CharField(source='academic_year.code', read_only=True)

    class Meta:
        model = StudentFeeAssessment
        fields = [
            'id',
            'student',
            'student_name',
            'enrollment_no',
            'academic_year',
            'academic_year_code',
            'fee_breakdown',
            'total_fee',
            'is_marked',
            'remarks',
            'created_at',
            'updated_at',
        ]
