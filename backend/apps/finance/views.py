"""
Views for Fee Heads, Candidate Fee Desk, and Payment Ledger.
"""
from decimal import Decimal
from django.db.models import Sum
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.audit.models import AuditLog
from apps.audit.services import audit_log
from apps.authentication.permissions import get_user_scopes
from apps.finance.models import FeeHead, PaymentLedger, StudentFeeAssessment
from apps.finance.serializers import (
    FeeHeadSerializer,
    PaymentLedgerSerializer,
    StudentFeeAssessmentSerializer,
)


class FeeHeadViewSet(viewsets.ModelViewSet):
    """
    Fee Head Configuration.
    Only Administrative Head (or Sysadmin) has permission to create, update, or delete fee heads.
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = FeeHeadSerializer
    queryset = FeeHead.objects.select_related('academic_year', 'program').all()

    def check_permissions(self, request):
        super().check_permissions(request)
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            scopes = get_user_scopes(request.user)
            if not (scopes['is_system_wide'] or 'ADMIN_HEAD' in scopes['roles']):
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied('Only the Administrative Head has permission to configure fee heads.')

    def get_queryset(self):
        qs = super().get_queryset()
        ay = self.request.query_params.get('academic_year_id')
        cat = self.request.query_params.get('category_quota')
        if ay:
            qs = qs.filter(academic_year_id=ay)
        if cat:
            qs = qs.filter(category_quota=cat)
        return qs

    def perform_create(self, serializer):
        head = serializer.save()
        audit_log(
            request=self.request,
            actor=self.request.user,
            action=AuditLog.Action.CREATE,
            target_type='FeeHead',
            target_id=str(head.id),
            target_display=f'{head.name} ({head.code})',
            reason='Fee structure configuration',
            description=f"Configured fee head '{head.name}' for {head.academic_year.code}.",
        )

    def perform_update(self, serializer):
        head = serializer.save()
        audit_log(
            request=self.request,
            actor=self.request.user,
            action=AuditLog.Action.UPDATE,
            target_type='FeeHead',
            target_id=str(head.id),
            target_display=f'{head.name} ({head.code})',
            reason='Fee structure configuration',
            description=f"Updated fee head '{head.name}' for {head.academic_year.code}.",
        )

    def perform_destroy(self, instance):
        label = f'{instance.name} ({instance.code})'
        head_id = str(instance.id)
        instance.delete()
        audit_log(
            request=self.request,
            actor=self.request.user,
            action=AuditLog.Action.DELETE,
            target_type='FeeHead',
            target_id=head_id,
            target_display=label,
            reason='Fee structure configuration',
            description=f"Removed fee head {label}.",
        )


class PaymentLedgerViewSet(viewsets.ModelViewSet):
    """
    Candidate Payment Ledger & Receipt Desk.
    Recorded rows are permanent (ARCH 18/28): no edits, no deletes.
    Corrections use future reversal records.
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PaymentLedgerSerializer
    queryset = PaymentLedger.objects.select_related('student', 'academic_year', 'collected_by').all()

    def update(self, request, *args, **kwargs):
        return Response(
            {'detail': 'Recorded payments are permanent and cannot be edited.'},
            status=status.HTTP_400_BAD_REQUEST)

    def partial_update(self, request, *args, **kwargs):
        return Response(
            {'detail': 'Recorded payments are permanent and cannot be edited.'},
            status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, *args, **kwargs):
        return Response(
            {'detail': 'Recorded payments are permanent and cannot be deleted.'},
            status=status.HTTP_400_BAD_REQUEST)

    def _next_receipt_no(self, academic_year):
        """Yearly sequence GCOEK/<year-code>/FEE/<nnnn>, unique-guarded."""
        base = f'GCOEK/{academic_year.code}/FEE/'
        taken = set(PaymentLedger.objects.filter(
            receipt_no__startswith=base).values_list('receipt_no', flat=True))
        n = len(taken) + 1
        candidate = f'{base}{n:04d}'
        while candidate in taken:
            n += 1
            candidate = f'{base}{n:04d}'
        return candidate

    def get_queryset(self):
        user = self.request.user
        scopes = get_user_scopes(user)

        if scopes['is_system_wide'] or 'ADMIN_HEAD' in scopes['roles'] or 'ACCOUNTANT' in scopes['roles']:
            qs = super().get_queryset()
            search = self.request.query_params.get('search')
            stat = self.request.query_params.get('status')
            if search:
                search = search.strip()
                qs = qs.filter(
                    student__display_name__icontains=search
                ) | qs.filter(receipt_no__icontains=search) | qs.filter(student__enrollment_no__icontains=search)
            if stat:
                qs = qs.filter(status=stat)
            return qs

        if 'STUDENT' in scopes['roles']:
            return PaymentLedger.objects.filter(student__user_id=user.id)

        return PaymentLedger.objects.none()

    def _check_write(self):
        scopes = get_user_scopes(self.request.user)
        if not (scopes['is_system_wide'] or 'ADMIN_HEAD' in scopes['roles']
                or 'ACCOUNTANT' in scopes['roles']):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('Only the fee desk (Sysadmin/Admin Head/Accountant) can record payments.')

    def perform_create(self, serializer):
        from django.db import IntegrityError, transaction
        from rest_framework.exceptions import ValidationError

        self._check_write()
        student = serializer.validated_data.get('student')
        academic_year = serializer.validated_data.get('academic_year')
        try:
            with transaction.atomic():
                # One fee record per student per academic year — block double marking.
                if PaymentLedger.objects.filter(student=student, academic_year=academic_year).exists():
                    raise ValidationError(
                        {'detail': 'Fee already recorded for this student and academic year. Duplicate payment blocked.'}
                    )
                # Marking records the SET fee: amounts must equal the assessment.
                assessment = StudentFeeAssessment.objects.filter(
                    student=student, academic_year=academic_year).first()
                if assessment is None:
                    raise ValidationError(
                        {'detail': 'Set the admission fee first before marking payment.'}
                    )
                total_due = serializer.validated_data.get('total_fee_due')
                amount_paid = serializer.validated_data.get('amount_paid')
                if total_due is None or Decimal(str(total_due)) != assessment.total_fee:
                    raise ValidationError(
                        {'detail': f'Marked total must equal the assessed fee ₹{assessment.total_fee}.'})
                if amount_paid is None or Decimal(str(amount_paid)) != assessment.total_fee:
                    raise ValidationError(
                        {'detail': f'Marked payment must equal the assessed fee ₹{assessment.total_fee}.'})
                if not serializer.validated_data.get('receipt_no'):
                    serializer.validated_data['receipt_no'] = self._next_receipt_no(academic_year)
                ledger = serializer.save(collected_by=self.request.user)
        except IntegrityError:
            raise ValidationError(
                {'detail': 'Fee already recorded (duplicate receipt). Duplicate payment blocked.'}
            )
        audit_log(
            request=self.request,
            actor=self.request.user,
            action=AuditLog.Action.CREATE,
            target_type='PaymentLedger',
            target_id=str(ledger.id),
            target_display=f'Receipt {ledger.receipt_no}',
            reason='Payment recorded at fee desk',
            description=f"Collected ₹{ledger.amount_paid} from {ledger.student.display_name} ({ledger.payment_mode}).",
        )
        if ledger.status == PaymentLedger.PaymentStatus.PAID or ledger.balance_due <= 0:
            from apps.students.services import check_and_promote_student
            check_and_promote_student(ledger.student_id, actor=self.request.user, request=self.request)

    @action(detail=False, methods=['get'], url_path='my-payments')
    def my_payments(self, request):
        """Student view of their own fee payment records."""
        payments = PaymentLedger.objects.filter(
            student__user_id=request.user.id
        ).order_by('-payment_date')
        return Response(PaymentLedgerSerializer(payments, many=True).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='analytics')
    def analytics(self, request):
        """Executive summary of fee collections and outstanding balances."""
        user = request.user
        scopes = get_user_scopes(user)
        if not (scopes['is_system_wide'] or 'ADMIN_HEAD' in scopes['roles'] or 'ACCOUNTANT' in scopes['roles']):
            return Response({'detail': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)

        ledgers = PaymentLedger.objects.all()
        year_id = request.query_params.get('academic_year') or request.query_params.get('academic_year_id')
        if year_id:
            ledgers = ledgers.filter(academic_year_id=year_id)

        total_collected = ledgers.aggregate(s=Sum('amount_paid'))['s'] or Decimal('0.0')
        total_due = ledgers.aggregate(s=Sum('total_fee_due'))['s'] or Decimal('0.0')
        total_balance = ledgers.aggregate(s=Sum('balance_due'))['s'] or Decimal('0.0')
        total_receipts = ledgers.count()

        by_mode = {}
        for mode, label in PaymentLedger.PaymentMode.choices:
            amt = ledgers.filter(payment_mode=mode).aggregate(s=Sum('amount_paid'))['s'] or Decimal('0.0')
            by_mode[label] = float(amt)

        return Response({
            'total_collected': float(total_collected),
            'total_due': float(total_due),
            'total_balance': float(total_balance),
            'total_receipts': total_receipts,
            'collection_by_mode': by_mode,
        }, status=status.HTTP_200_OK)


class StudentFeeAssessmentViewSet(viewsets.ModelViewSet):
    """Candidate fee assessment (Set Fee), replacing the localStorage draft.

    Accountant/Admin/Sysadmin write; students read their own. Amounts are
    validated server-side against AH-configured fee heads (allowed presets)
    and the total must equal the breakdown sum. Once a PAID ledger exists
    for (student, year), the assessment is frozen.
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = StudentFeeAssessmentSerializer
    queryset = StudentFeeAssessment.objects.select_related(
        'student', 'academic_year').all().order_by('-created_at')

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        scopes = get_user_scopes(user)
        if scopes['is_system_wide'] or 'ADMIN_HEAD' in scopes['roles'] or 'ACCOUNTANT' in scopes['roles']:
            student = self.request.query_params.get('student')
            year = self.request.query_params.get('academic_year')
            if student:
                qs = qs.filter(student_id=student)
            if year:
                qs = qs.filter(academic_year_id=year)
            return qs
        if 'STUDENT' in scopes['roles']:
            return qs.filter(student__user_id=user.id)
        return StudentFeeAssessment.objects.none()

    def _check_write(self):
        scopes = get_user_scopes(self.request.user)
        if not (scopes['is_system_wide'] or 'ADMIN_HEAD' in scopes['roles']
                or 'ACCOUNTANT' in scopes['roles']):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('Only the fee desk can set assessments.')

    def _validate_against_heads(self, validated):
        from decimal import Decimal as _Decimal
        from rest_framework.exceptions import ValidationError
        breakdown = validated.get('fee_breakdown') or {}
        total = validated.get('total_fee')
        if not isinstance(breakdown, dict) or not breakdown:
            raise ValidationError({'fee_breakdown': 'Breakdown by fee head is required.'})
        heads = {h.name: h for h in FeeHead.objects.filter(
            academic_year=validated.get('academic_year'), is_active=True)}
        for name, amount in breakdown.items():
            head = heads.get(name)
            if head is None:
                raise ValidationError(
                    {'fee_breakdown': f"Fee head '{name}' is not configured for this year."})
            try:
                amt = _Decimal(str(amount))
            except Exception:
                raise ValidationError({'fee_breakdown': f"Invalid amount for '{name}'."})
            allowed = head.allowed_amounts or []
            if allowed and not any(_Decimal(str(a)) == amt for a in allowed):
                raise ValidationError(
                    {'fee_breakdown': f"₹{amt} is not an allowed preset for '{name}'."})
        if total is None or abs(_Decimal(str(total)) - sum(
                (_Decimal(str(v)) for v in breakdown.values()), _Decimal('0'))) > _Decimal('0.01'):
            raise ValidationError({'total_fee': 'Total must equal the breakdown sum.'})

    def _frozen(self, student, academic_year):
        ledger = PaymentLedger.objects.filter(
            student=student, academic_year=academic_year).first()
        return ledger is not None and (
            ledger.status == PaymentLedger.PaymentStatus.PAID or ledger.balance_due <= 0)

    def perform_create(self, serializer):
        from django.db import transaction
        from rest_framework.exceptions import ValidationError
        self._check_write()
        with transaction.atomic():
            student = serializer.validated_data.get('student')
            year = serializer.validated_data.get('academic_year')
            if StudentFeeAssessment.objects.filter(student=student, academic_year=year).exists():
                raise ValidationError(
                    {'detail': 'Assessment already set for this student and year. Edit it instead.'})
            self._validate_against_heads(serializer.validated_data)
            obj = serializer.save(assessed_by=self.request.user, is_marked=True)
            audit_log(
                request=self.request, actor=self.request.user,
                action=AuditLog.Action.CREATE, target_type='StudentFeeAssessment',
                target_id=str(obj.id),
                target_display=f'{obj.student.display_name} {obj.academic_year.code}',
                new_value={'total_fee': str(obj.total_fee), 'breakdown': obj.fee_breakdown},
                reason='Fee assessment at candidate desk',
                description=f"Set admission fee ₹{obj.total_fee} for {obj.student.display_name}.",
            )

    def perform_update(self, serializer):
        from rest_framework.exceptions import ValidationError
        self._check_write()
        old = self.get_object()
        if self._frozen(old.student, old.academic_year):
            raise ValidationError({'detail': 'Fee is already paid; assessment is frozen.'})
        old_total = str(old.total_fee)
        self._validate_against_heads({**serializer.validated_data,
                                      'academic_year': old.academic_year})
        obj = serializer.save(assessed_by=self.request.user, is_marked=True)
        audit_log(
            request=self.request, actor=self.request.user,
            action=AuditLog.Action.UPDATE, target_type='StudentFeeAssessment',
            target_id=str(obj.id),
            target_display=f'{obj.student.display_name} {obj.academic_year.code}',
            old_value={'total_fee': old_total},
            new_value={'total_fee': str(obj.total_fee), 'breakdown': obj.fee_breakdown},
            reason='Fee assessment correction before payment',
            description=f"Updated admission fee {old_total} -> ₹{obj.total_fee} for {obj.student.display_name}.",
        )

    def perform_destroy(self, instance):
        from rest_framework.exceptions import ValidationError
        self._check_write()
        if self._frozen(instance.student, instance.academic_year):
            raise ValidationError({'detail': 'Fee is already paid; assessment cannot be removed.'})
        label = f'{instance.student.display_name} {instance.academic_year.code}'
        instance_id = str(instance.id)
        instance.delete()
        audit_log(
            request=self.request, actor=self.request.user,
            action=AuditLog.Action.DELETE, target_type='StudentFeeAssessment',
            target_id=instance_id, target_display=label,
            reason='Unpaid assessment withdrawn',
            description=f"Withdrew unpaid fee assessment {label}.",
        )
