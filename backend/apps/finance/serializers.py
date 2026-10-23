"""
Serializers for Fee Configuration and Payment Ledger.
"""
from decimal import Decimal

from rest_framework import serializers
from apps.finance.models import FeeHead, FeePackage, PaymentLedger, StudentFeeAssessment


class FeeHeadSerializer(serializers.ModelSerializer):
    category_quota_display = serializers.CharField(source='get_category_quota_display', read_only=True)
    fee_type_display = serializers.CharField(source='get_fee_type_display', read_only=True)
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
            'fee_type',
            'fee_type_display',
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


class FeePackageSerializer(serializers.ModelSerializer):
    """
    Administrative-Head-configured fee package (one dropdown option at the
    accountant desk). Items are validated server-side against the year's fee
    heads — every amount must be one of that head's allowed presets, so a
    saved package can never make the accountant's fee breakdown invalid.
    """

    academic_year_code = serializers.CharField(source='academic_year.code', read_only=True)
    total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    items_resolved = serializers.SerializerMethodField()

    class Meta:
        model = FeePackage
        fields = [
            'id',
            'name',
            'academic_year',
            'academic_year_code',
            'items',
            'items_resolved',
            'total',
            'display_order',
            'is_active',
            'created_at',
            'updated_at',
        ]
        # total is always recomputed server-side from items.
        read_only_fields = ['total']

    # ------------------------------------------------------------------
    # Read-side: resolve live head names/amounts
    # ------------------------------------------------------------------
    def get_items_resolved(self, obj):
        """items with live head names for the accountant dropdown flow.

        Dangling ids (head deleted since the package was written) degrade
        gracefully with a '(removed fee head)' name so the desk can see — and
        skip — broken packages instead of failing with a cryptic error.
        """
        items = obj.items if isinstance(obj.items, list) else []
        if not items:
            return []
        heads = {str(h.id): h for h in FeeHead.objects.filter(academic_year_id=obj.academic_year_id)}
        resolved = []
        for item in items:
            if not isinstance(item, dict):
                continue
            head = heads.get(str(item.get('head', '')))
            try:
                amount = Decimal(str(item.get('amount', 0)))
            except Exception:
                amount = Decimal('0')
            resolved.append({
                'head': str(item.get('head', '')),
                'head_code': head.code if head else '',
                'head_name': head.name if head else str(item.get('name') or '(removed fee head)'),
                'amount': float(amount),
                'is_valid': head is not None,
            })
        return resolved

    # ------------------------------------------------------------------
    # Write-side: validation is the guarantee of the whole feature
    # ------------------------------------------------------------------
    def _resolve_year(self, attrs):
        year = attrs.get('academic_year')
        if year is None and self.instance is not None:
            year = self.instance.academic_year
        if year is None:
            raise serializers.ValidationError({'academic_year': 'Academic year is required.'})
        return year

    @staticmethod
    def _to_decimal(value):
        try:
            return Decimal(str(value))
        except Exception:
            return None

    def validate_items(self, items):
        if not isinstance(items, list) or not items:
            raise serializers.ValidationError('At least one fee head with an amount is required.')
        cleaned = []
        for item in items:
            if not isinstance(item, dict):
                raise serializers.ValidationError('Each package item must map a fee head to an amount.')
            cleaned.append(item)
        return cleaned

    def validate(self, attrs):
        items = attrs.get('items', self.instance.items if self.instance else None)
        if not isinstance(items, list) or not items:
            raise serializers.ValidationError({'items': 'At least one fee head with an amount is required.'})

        year = self._resolve_year(attrs)

        # Clean 400 (not a DB 500) for duplicate names within a year; the
        # unique DB constraint remains the race-condition backstop.
        name = attrs.get('name') or (self.instance.name if self.instance else '')
        dupe = FeePackage.objects.filter(academic_year=year, name=name)
        if self.instance:
            dupe = dupe.exclude(pk=self.instance.pk)
        if name and dupe.exists():
            raise serializers.ValidationError(
                {'name': f'A fee package named "{name}" already exists for this academic year.'})

        heads = {str(h.id): h for h in FeeHead.objects.filter(academic_year=year, is_active=True)}

        name_owner = {}
        seen_ids = set()
        total = Decimal('0')
        cleaned_items = []
        for idx, item in enumerate(items):
            head_id = str(item.get('head') or '')
            head = heads.get(head_id)
            if head is None:
                raise serializers.ValidationError(
                    {'items': f'Item {idx + 1}: fee head is inactive or not configured for this year.'})
            if head_id in seen_ids:
                raise serializers.ValidationError(
                    {'items': f"'{head.name}' may appear only once in a package."})
            seen_ids.add(head_id)

            amount = self._to_decimal(item.get('amount'))
            if amount is None or amount < 0:
                raise serializers.ValidationError(
                    {'items': f"'{head.name}': invalid amount."})
            allowed = head.allowed_amounts or []
            if allowed and not any(self._to_decimal(a) == amount for a in allowed):
                raise serializers.ValidationError(
                    {'items': f'{amount.quantize(Decimal("0.01"))} is not an allowed preset for '
                              f"'{head.name}'. Configure it on the fee head first."})

            # Two different heads with the same name would corrupt the saved
            # breakdown (it is keyed by name) — block the package instead.
            if head.name in name_owner and name_owner[head.name] != head_id:
                raise serializers.ValidationError(
                    {'items': f"Two fee heads share the name '{head.name}'. "
                              'Fee head names within a year must be unique before packages can use them.'})
            name_owner[head.name] = head_id

            cleaned_items.append({
                'head': head_id,
                'name': head.name,  # snapshot refreshed to the live head name
                'amount': float(amount),
            })
            total += amount

        attrs['items'] = cleaned_items
        attrs['total'] = total.quantize(Decimal('0.01'))
        return attrs


class PaymentLedgerSerializer(serializers.ModelSerializer):
    payment_mode_display = serializers.CharField(source='get_payment_mode_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    student_name = serializers.CharField(source='student.display_name', read_only=True)
    enrollment_no = serializers.CharField(source='student.enrollment_no', read_only=True)
    academic_year_code = serializers.CharField(source='academic_year.code', read_only=True)
    collected_by_name = serializers.CharField(source='collected_by.username', read_only=True, default='')
    fee_breakdown = serializers.SerializerMethodField()
    fee_types = serializers.SerializerMethodField()

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
            'fee_breakdown',
            'fee_types',
            'fee_snapshot',
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
        # value is ignored (backend always generates <ROMAN><YY><YY>-<nnnn>,
        # e.g. IV2627-0001).
        # status is derived in PaymentLedger.save(); full payment only.
        # fee_snapshot is server-frozen from assessment; never client-writable.
        extra_kwargs = {
            'receipt_no': {'read_only': True},
            'status': {'read_only': True},
            'balance_due': {'read_only': True},
            'fee_snapshot': {'read_only': True},
        }

    def get_fee_breakdown(self, obj):
        # Frozen snapshot first (immutable receipt). Fallback to live
        # assessment only for pre-snapshot legacy receipts.
        try:
            snap = getattr(obj, 'fee_snapshot', None)
            if isinstance(snap, dict) and snap:
                return snap
            assessment = StudentFeeAssessment.objects.filter(
                student_id=obj.student_id,
                academic_year_id=obj.academic_year_id,
            ).order_by('-updated_at').first()
            if assessment and isinstance(assessment.fee_breakdown, dict):
                return assessment.fee_breakdown
        except Exception:
            pass
        return {}

    def get_fee_types(self, obj):
        """Head-name -> fee_type (GOVERNMENT/INSTITUTE) shown on the receipt.

        Frozen `fee_types_snapshot` first (immutable receipt). Fallback for
        pre-classification legacy receipts: look the heads up live by name
        against the current fee-head configuration for the receipt's year.
       """
        try:
            snap = getattr(obj, 'fee_types_snapshot', None)
            if isinstance(snap, dict) and snap:
                return snap
            heads = self.get_fee_breakdown(obj) or {}
            if not heads:
                return {}
            # Case-insensitive match (legacy breakdowns may differ in casing
            # from the configured head names).
            lookup = {n.lower(): fee_type or FeeHead.FeeType.INSTITUTE for n, fee_type in FeeHead.objects.filter(
                academic_year_id=obj.academic_year_id,
            ).values_list('name', 'fee_type')}
            return {
                name: lookup.get(name.lower(), FeeHead.FeeType.INSTITUTE)
                for name in heads.keys()
            }
        except Exception:
            return {}

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


class MyPaymentSerializer(serializers.ModelSerializer):
    """Student-facing slice of the payment ledger.

    Students may see THAT their fee is paid (amount, date, status) — never
    the official receipt fields. Receipt number, fee-head breakup, snapshot
    and collector details are fee-desk-only: the official receipt is printed
    at the accounts counter, not downloaded by the student.
    """

    payment_mode_display = serializers.CharField(source='get_payment_mode_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    student_name = serializers.CharField(source='student.display_name', read_only=True)
    enrollment_no = serializers.CharField(source='student.enrollment_no', read_only=True)
    academic_year_code = serializers.CharField(source='academic_year.code', read_only=True)

    class Meta:
        model = PaymentLedger
        fields = [
            'id',
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
            'status',
            'status_display',
            'payment_date',
            'created_at',
        ]


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

