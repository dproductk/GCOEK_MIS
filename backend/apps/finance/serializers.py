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
        # Receipt numbers are server-sequenced and read-only; any client
        # value is ignored (backend always generates GCOEK/<year>/FEE/<nnnn>).
        # status is derived in PaymentLedger.save(); full payment only.
        extra_kwargs = {
            'receipt_no': {'read_only': True},
            'status': {'read_only': True},
            'balance_due': {'read_only': True},
        }

    def validate(self, attrs):
        # University rule: full payment only. Reject half payments early
        # with a clear message (backend perform_create double-checks
        # against the assessment total as well).
        total = attrs.get('total_fee_due')
        paid = attrs.get('amount_paid')
        if total is not None and paid is not None and total != paid:
            from rest_framework import serializers as _s
            raise _s.ValidationError(
                {'amount_paid': 'Full payment only: amount paid must equal total fee due.'}
            )
        return attrs


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
            'allow_online_payment',
            'remarks',
            'created_at',
            'updated_at',
        ]


class OnlinePaymentAttemptSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    student_name = serializers.CharField(source='student.display_name', read_only=True)
    enrollment_no = serializers.CharField(source='student.enrollment_no', read_only=True)
    academic_year_code = serializers.CharField(source='academic_year.code', read_only=True)

    class Meta:
        from apps.finance.models import OnlinePaymentAttempt
        model = OnlinePaymentAttempt
        fields = [
            'id',
            'transaction_id',
            'student',
            'student_name',
            'enrollment_no',
            'academic_year',
            'academic_year_code',
            'assessment',
            'amount',
            'currency',
            'status',
            'status_display',
            'gateway_provider',
            'easebuzz_txn_id',
            'easebuzz_status',
            'payment_mode',
            'checkout_url',
            'access_key',
            'failure_reason',
            'initiated_at',
            'completed_at',
        ]
        read_only_fields = fields


class OnlinePaymentTrackerSerializer(serializers.ModelSerializer):
    """
    Serializer for the Accountant Online Payment Monitor / Tracker.
    """
    student_name = serializers.CharField(source='student.display_name', read_only=True)
    enrollment_no = serializers.CharField(source='student.enrollment_no', read_only=True)
    department_name = serializers.SerializerMethodField()
    latest_attempt = serializers.SerializerMethodField()
    is_paid = serializers.SerializerMethodField()
    receipt_no = serializers.SerializerMethodField()

    class Meta:
        model = StudentFeeAssessment
        fields = [
            'id',
            'student',
            'student_name',
            'enrollment_no',
            'department_name',
            'academic_year',
            'total_fee',
            'allow_online_payment',
            'is_paid',
            'receipt_no',
            'latest_attempt',
            'updated_at',
        ]

    @staticmethod
    def _is_prefetched(instance, rel_name):
        """True if rel_name was prefetched on this model instance.

        Prefetched relations live on the INSTANCE's
        _prefetched_objects_cache dict — never on the related manager.
        """
        cache = getattr(instance, '_prefetched_objects_cache', None)
        return isinstance(cache, dict) and rel_name in cache

    def get_department_name(self, obj):
        # Uses the student__enrollments__department prefetch from the tracker
        # view — no extra query. Falls back to a query only if unprefetched.
        student = getattr(obj, 'student', None)
        if student is not None and self._is_prefetched(student, 'enrollments'):
            for enrollment in student.enrollments.all():
                if getattr(enrollment, 'is_current', False):
                    dept = getattr(enrollment, 'department', None)
                    return getattr(dept, 'name', '') or ''
            return ''
        enrollment = obj.student.enrollments.filter(is_current=True).first()
        return enrollment.department.name if enrollment and enrollment.department else ''

    def get_latest_attempt(self, obj):
        # Uses the online_payment_attempts prefetch (newest-first in Python).
        # .all() on a prefetched manager serves from cache; .order_by() or
        # .first() with ordering would issue a fresh query, so avoid them.
        attempt = None
        if self._is_prefetched(obj, 'online_payment_attempts'):
            try:
                attempt = max(obj.online_payment_attempts.all(), key=lambda a: a.initiated_at)
            except ValueError:
                attempt = None
        else:
            attempt = obj.online_payment_attempts.order_by('-initiated_at').first()
        if not attempt:
            return None
        return {
            'id': str(attempt.id),
            'transaction_id': attempt.transaction_id,
            'status': attempt.status,
            'status_display': attempt.get_status_display(),
            'easebuzz_txn_id': attempt.easebuzz_txn_id,
            'payment_mode': attempt.payment_mode,
            'initiated_at': attempt.initiated_at,
            'completed_at': attempt.completed_at,
        }

    def _paid_ledger_from_prefetch(self, obj):
        student = getattr(obj, 'student', None)
        if student is not None and self._is_prefetched(student, 'payment_records'):
            for ledger in student.payment_records.all():
                if (getattr(ledger, 'academic_year_id', None) == getattr(obj, 'academic_year_id', None)
                        and ledger.status == PaymentLedger.PaymentStatus.PAID):
                    return ledger
            return None
        return None

    def _payment_records_prefetched(self, obj):
        student = getattr(obj, 'student', None)
        return student is not None and self._is_prefetched(student, 'payment_records')

    def get_is_paid(self, obj):
        hit = self._paid_ledger_from_prefetch(obj)
        if hit is not None:
            return True
        # Prefetched but absent → not paid (no query). Unprefetched → query.
        if self._payment_records_prefetched(obj):
            return False
        ledger = getattr(obj.student, 'payment_records', None)
        if ledger:
            return ledger.filter(academic_year=obj.academic_year, status=PaymentLedger.PaymentStatus.PAID).exists()
        return False

    def get_receipt_no(self, obj):
        hit = self._paid_ledger_from_prefetch(obj)
        if hit is not None:
            return hit.receipt_no
        if self._payment_records_prefetched(obj):
            return None
        ledger = PaymentLedger.objects.filter(
            student=obj.student,
            academic_year=obj.academic_year,
            status=PaymentLedger.PaymentStatus.PAID
        ).first()
        return ledger.receipt_no if ledger else None

