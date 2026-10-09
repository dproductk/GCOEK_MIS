"""
Views for Fee Heads, Candidate Fee Desk, and Payment Ledger.
"""
import datetime
import logging
import uuid
from decimal import Decimal
from django.conf import settings
from django.db.models import Sum
from django.http import HttpResponseRedirect
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academic_structure.models import AcademicYear
from apps.audit.models import AuditLog
from apps.audit.services import audit_log, get_client_ip
from apps.authentication.permissions import get_user_scopes
from apps.finance.gateway.easebuzz import EasebuzzGateway
from apps.finance.models import (
    FeeHead,
    GatewayRawEvent,
    OnlinePaymentAttempt,
    PaymentLedger,
    StudentFeeAssessment,
)
from apps.finance.serializers import (
    FeeHeadSerializer,
    OnlinePaymentAttemptSerializer,
    OnlinePaymentTrackerSerializer,
    PaymentLedgerSerializer,
    StudentFeeAssessmentSerializer,
)
from apps.finance.services import apply_gateway_result, generate_next_receipt_no
from apps.results.models import EligibilityVerification
from apps.students.models import Student, StudentEnrollment

logger = logging.getLogger(__name__)


from rest_framework.pagination import PageNumberPagination


class FinancePagination(PageNumberPagination):
    """Large-page pagination for fee desk lists.

    Default page is 100 rows, but the desk passes ?page_size=500/1000
    so a full college roster fits in one request. Without
    page_size_query_param the global default (25, no override) silently
    truncated ledgers/assessments to the first 25 rows.
    """
    page_size = 100
    page_size_query_param = 'page_size'
    max_page_size = 1000


class FeeHeadViewSet(viewsets.ModelViewSet):
    """
    Fee Head Configuration.
    Only Administrative Head (or Sysadmin) has permission to create, update, or delete fee heads.
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = FeeHeadSerializer
    queryset = FeeHead.objects.select_related('academic_year', 'program').all()
    pagination_class = FinancePagination

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
            new_value={
                'name': head.name,
                'code': head.code,
                'amount': str(head.amount),
                'allowed_amounts': [str(a) for a in (head.allowed_amounts or [])],
                'category_quota': head.category_quota,
                'academic_year': head.academic_year.code if head.academic_year else '',
            },
            reason='Fee structure configuration',
            description=f"Configured fee head '{head.name}' for {head.academic_year.code}.",
        )

    def perform_update(self, serializer):
        old = serializer.instance
        old_snapshot = {
            'name': old.name,
            'code': old.code,
            'amount': str(old.amount),
            'allowed_amounts': [str(a) for a in (old.allowed_amounts or [])],
            'category_quota': old.category_quota,
        } if old else None
        head = serializer.save()
        audit_log(
            request=self.request,
            actor=self.request.user,
            action=AuditLog.Action.UPDATE,
            target_type='FeeHead',
            target_id=str(head.id),
            target_display=f'{head.name} ({head.code})',
            old_value=old_snapshot,
            new_value={
                'name': head.name,
                'code': head.code,
                'amount': str(head.amount),
                'allowed_amounts': [str(a) for a in (head.allowed_amounts or [])],
                'category_quota': head.category_quota,
            },
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
    pagination_class = FinancePagination

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

    def get_queryset(self):
        user = self.request.user
        scopes = get_user_scopes(user)

        if scopes['is_system_wide'] or 'ADMIN_HEAD' in scopes['roles'] or 'ACCOUNTANT' in scopes['roles']:
            qs = super().get_queryset()
            search = self.request.query_params.get('search')
            stat = self.request.query_params.get('status')
            year_id = self.request.query_params.get('academic_year') or self.request.query_params.get('academic_year_id')
            if search:
                search = search.strip()
                qs = qs.filter(
                    student__display_name__icontains=search
                ) | qs.filter(receipt_no__icontains=search) | qs.filter(student__enrollment_no__icontains=search)
            if stat:
                qs = qs.filter(status=stat)
            if year_id:
                qs = qs.filter(academic_year_id=year_id)
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
        # Validate amounts once (outside retry — deterministic).
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

        # F-S5-003: Check for in-flight online payment attempts within 15 minutes to prevent race with bank.
        cutoff = timezone.now() - datetime.timedelta(minutes=15)
        in_flight = OnlinePaymentAttempt.objects.filter(
            student=student,
            academic_year=academic_year,
            status__in=[
                OnlinePaymentAttempt.Status.INITIATED,
                OnlinePaymentAttempt.Status.REDIRECTED,
                OnlinePaymentAttempt.Status.PENDING,
            ],
            initiated_at__gte=cutoff,
        ).order_by('-initiated_at').first()
        if in_flight:
            from rest_framework.exceptions import APIException
            class PaymentConflict(APIException):
                status_code = 409
            raise PaymentConflict(
                f'An online payment attempt ({in_flight.transaction_id}) is currently in-flight. '
                'Please wait for the transaction to complete or reconcile via online tracker before collecting cash.'
            )
        # University rule: full payment only — partial payments are rejected
        # above (amount_paid must equal assessed total). No half-payment path.
        # Receipt numbers are ALWAYS backend-generated (GCOEK/<year>/FEE/<nnnn>).
        # Any client-supplied receipt_no is discarded so staff cannot inject
        # out-of-sequence or duplicate receipt numbers.
        serializer.validated_data.pop('receipt_no', None)
        # Retry loop for concurrent receipt-no collisions. Student-year
        # duplicates fail immediately; receipt collisions regenerate.
        # Receipt numbers are allocated INSIDE each retry transaction so the
        # FeeReceiptCounter row lock actually serializes concurrent writers.
        ledger = None
        for _attempt in range(3):
            try:
                with transaction.atomic():
                    # Lock existing row for this student-year if present.
                    if PaymentLedger.objects.select_for_update().filter(
                            student=student, academic_year=academic_year).exists():
                        raise ValidationError(
                            {'detail': 'Fee already recorded for this student and academic year. Duplicate payment blocked.'}
                        )
                    serializer.validated_data['receipt_no'] = generate_next_receipt_no(academic_year)
                    ledger = serializer.save(collected_by=self.request.user)
                break
            except ValidationError:
                raise
            except IntegrityError:
                # If student-year now exists, it's a real duplicate — stop.
                if PaymentLedger.objects.filter(student=student, academic_year=academic_year).exists():
                    raise ValidationError(
                        {'detail': 'Fee already recorded for this student and academic year. Duplicate payment blocked.'}
                    )
                # Else assume receipt-no collision — drop the stale number so
                # the next loop iteration allocates a fresh one inside its own
                # transaction instead of incrementing the counter outside it.
                serializer.validated_data.pop('receipt_no', None)
                continue

        if ledger is None:
            raise ValidationError(
                {'detail': 'Fee already recorded (duplicate receipt). Please retry.'}
            )
        audit_log(
            request=self.request,
            actor=self.request.user,
            action=AuditLog.Action.PAYMENT,
            target_type='PaymentLedger',
            target_id=str(ledger.id),
            target_display=f'Receipt {ledger.receipt_no}',
            new_value={
                'receipt_no': ledger.receipt_no,
                'amount_paid': str(ledger.amount_paid),
                'total_fee_due': str(ledger.total_fee_due),
                'balance_due': str(ledger.balance_due),
                'payment_mode': ledger.payment_mode,
                'transaction_ref': ledger.transaction_ref,
                'student': ledger.student.display_name,
            },
            reason='Payment recorded at fee desk',
            description=f"Collected {ledger.amount_paid} from {ledger.student.display_name} ({ledger.payment_mode}).",
        )
        # Promotion is best-effort and must NEVER fail the payment response.
        # Normal case: no HOD eligibility yet -> check returns (False, reason),
        # ledger stays PAID, student stays unpromoted (fee=paid, promotion=pending).
        # Rare case: unexpected exception (missing semester, audit failure) ->
        # log it and still return payment success. The receipt is already committed.
        if ledger.status == PaymentLedger.PaymentStatus.PAID or ledger.balance_due <= 0:
            try:
                from apps.students.services import check_and_promote_student
                check_and_promote_student(ledger.student_id, actor=self.request.user, request=self.request)
            except Exception:
                logger.exception(
                    "Promotion check failed after manual payment for ledger %s; payment stays PAID.",
                    ledger.receipt_no,
                )

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

        # Online payment gateway stats (Easebuzz attempts + online ledger slice).
        attempts = OnlinePaymentAttempt.objects.all()
        assessments = StudentFeeAssessment.objects.all()
        if year_id:
            attempts = attempts.filter(academic_year_id=year_id)
            assessments = assessments.filter(academic_year_id=year_id)

        S = OnlinePaymentAttempt.Status
        success_qs = attempts.filter(status=S.SUCCESS)
        pending_qs = attempts.filter(status__in=[S.INITIATED, S.REDIRECTED, S.PENDING])
        online_ledger_qs = ledgers.filter(payment_mode=PaymentLedger.PaymentMode.ONLINE)

        online_payment = {
            'enabled_students': assessments.filter(allow_online_payment=True).values('student').distinct().count(),
            'total_attempts': attempts.count(),
            'attempts_by_status': {
                st.value if hasattr(st, 'value') else str(st): attempts.filter(status=st).count()
                for st in S
            },
            'successful_payments': success_qs.count(),
            'successful_students': success_qs.values('student').distinct().count(),
            'successful_amount': float(success_qs.aggregate(s=Sum('amount'))['s'] or Decimal('0.0')),
            'pending_count': pending_qs.count(),
            'pending_students': pending_qs.values('student').distinct().count(),
            'pending_amount': float(pending_qs.aggregate(s=Sum('amount'))['s'] or Decimal('0.0')),
            'failed_count': attempts.filter(status=S.FAILED).count(),
            'cancelled_count': attempts.filter(status=S.CANCELLED).count(),
            'expired_count': attempts.filter(status=S.EXPIRED).count(),
            'ledger_online_count': online_ledger_qs.count(),
            'ledger_online_amount': float(online_ledger_qs.aggregate(s=Sum('amount_paid'))['s'] or Decimal('0.0')),
        }

        return Response({
            'total_collected': float(total_collected),
            'total_due': float(total_due),
            'total_balance': float(total_balance),
            'total_receipts': total_receipts,
            'collection_by_mode': by_mode,
            'online_payment': online_payment,
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
    pagination_class = FinancePagination

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

    @action(detail=True, methods=['post'], url_path='toggle-online-payment')
    def toggle_online_payment(self, request, pk=None):
        """Allows accountant to toggle allow_online_payment on an existing assessment."""
        self._check_write()
        obj = self.get_object()
        if self._frozen(obj.student, obj.academic_year):
            return Response(
                {'detail': 'Fee is already paid; assessment is frozen.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        previous_flag = bool(obj.allow_online_payment)
        new_val = request.data.get('allow_online_payment')
        if new_val is None:
            obj.allow_online_payment = not obj.allow_online_payment
        elif isinstance(new_val, str):
            obj.allow_online_payment = new_val.lower() in ('true', '1', 'yes')
        else:
            obj.allow_online_payment = bool(new_val)
        obj.save(update_fields=['allow_online_payment', 'updated_at'])

        audit_log(
            request=request, actor=request.user,
            action=AuditLog.Action.UPDATE, target_type='StudentFeeAssessment',
            target_id=str(obj.id),
            target_display=f"{obj.student.display_name} {obj.academic_year.code}",
            old_value={'allow_online_payment': previous_flag},
            new_value={'allow_online_payment': bool(obj.allow_online_payment)},
            reason='Toggled online payment permission',
            description=f"Set allow_online_payment={obj.allow_online_payment} for {obj.student.display_name}.",
        )
        return Response(StudentFeeAssessmentSerializer(obj).data, status=status.HTTP_200_OK)


# =============================================================================
# ONLINE PAYMENT GATEWAY VIEWS (EASEBUZZ)
# =============================================================================

def _is_gateway_ip_allowed(request):
    """Check Easebuzz webhook IP allowlist. Empty list = allow all (dev).

    Spoof-safe: trust REMOTE_ADDR (direct peer) first. X-Forwarded-For is
    only honored when the direct peer is a local proxy, and then the
    rightmost hop is used (closest untrusted hop), not index [0].
    F-S5-005: In production (EASEBUZZ_ENV == 'production' and not settings.DEBUG),
    an empty allowlist fails closed (returns False).
    """
    allowed = getattr(settings, 'EASEBUZZ_WEBHOOK_ALLOWED_IPS', [])
    easebuzz_env = getattr(settings, 'EASEBUZZ_ENV', 'sandbox')
    is_debug = getattr(settings, 'DEBUG', False)
    if not allowed:
        if easebuzz_env == 'production' and not is_debug:
            logger.warning("F-S5-005: EASEBUZZ_WEBHOOK_ALLOWED_IPS empty in production. Rejecting webhook.")
            return False
        return True
    allowed_set = {str(ip).strip() for ip in allowed if str(ip).strip()}
    remote = (request.META.get('REMOTE_ADDR') or '').strip()
    if remote and remote not in ('127.0.0.1', '::1'):
        return remote in allowed_set
    xff = request.META.get('HTTP_X_FORWARDED_FOR') or ''
    hops = [h.strip() for h in xff.split(',') if h.strip()]
    if not hops:
        return remote in allowed_set
    return hops[-1] in allowed_set


def _get_webhook_client_ip(request):
    """Best-effort client IP using the same spoof-safe rule as the allowlist."""
    remote = (request.META.get('REMOTE_ADDR') or '').strip()
    if remote and remote not in ('127.0.0.1', '::1'):
        return remote
    xff = request.META.get('HTTP_X_FORWARDED_FOR') or ''
    hops = [h.strip() for h in xff.split(',') if h.strip()]
    if hops:
        return hops[-1]
    return remote or None


class OnlinePaymentStatusView(APIView):
    """
    Student-facing check to see if online fee payment is active and eligible.
    Enforces all 7 conditions from prompt Section 4.
    """
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = 'payment_status'

    def get(self, request):
        student = Student.objects.filter(user=request.user).first()
        if not student:
            return Response({'detail': 'Student profile not found.'}, status=status.HTTP_404_NOT_FOUND)

        ay = AcademicYear.objects.filter(is_current=True).first()
        if not ay:
            return Response({'detail': 'Current academic year not found.'}, status=status.HTTP_400_BAD_REQUEST)

        assessment = StudentFeeAssessment.objects.filter(student=student, academic_year=ay).first()
        paid_ledger = PaymentLedger.objects.filter(student=student, academic_year=ay, status=PaymentLedger.PaymentStatus.PAID).first()

        # F-S5-002: Enforce ADR-017 eligibility predicate \u2014 same rule as initiate.
        # A division-less FY student in semester 1 does not need verification, but
        # any student in a year-change semester (3, 5, 7) MUST have HOD-approved
        # eligibility (final_eligible=True) before can_pay is True.
        eligibility = EligibilityVerification.objects.filter(student=student, academic_year=ay, final_eligible=True).first()
        needs_eligibility = StudentEnrollment.objects.filter(
            student=student, is_current=True,
            semester__number__in=[3, 5, 7],
        ).exists()
        is_eligible = (not needs_eligibility) or (eligibility is not None)


        # Check for in-flight active attempt
        in_flight = OnlinePaymentAttempt.objects.filter(
            student=student,
            academic_year=ay,
            status__in=[
                OnlinePaymentAttempt.Status.INITIATED,
                OnlinePaymentAttempt.Status.REDIRECTED,
                OnlinePaymentAttempt.Status.PENDING,
            ],
        ).order_by('-initiated_at').first()

        gateway_enabled = getattr(settings, 'EASEBUZZ_ENABLED', False)
        has_assessment = assessment is not None and assessment.total_fee > 0
        allow_online = assessment.allow_online_payment if assessment else False
        is_paid = paid_ledger is not None

        can_pay = (
            gateway_enabled and
            has_assessment and
            allow_online and
            is_eligible and
            not is_paid and
            in_flight is None
        )

        reasons = []
        if not gateway_enabled:
            reasons.append("Online payment gateway is temporarily disabled.")
        if not has_assessment:
            reasons.append("Admission fee has not been assessed yet. Please contact the college accounts desk.")
        elif not allow_online:
            reasons.append("Online payment is not enabled for your account yet. Please visit the accounts desk.")
        if not is_eligible:
            reasons.append("Academic progression verification pending approval by HOD.")
        if is_paid:
            reasons.append("Fee has already been fully paid.")
        if in_flight:
            reasons.append(f"A payment attempt ({in_flight.transaction_id}) is currently pending verification.")

        return Response({
            'can_pay': can_pay,
            'reason': " ".join(reasons) if reasons else "Eligible for online fee payment.",
            'gateway_enabled': gateway_enabled,
            'is_paid': is_paid,
            'receipt_no': paid_ledger.receipt_no if paid_ledger else None,
            'academic_year': {
                'id': str(ay.id),
                'code': ay.code,
                'name': ay.name,
            },
            'assessment': StudentFeeAssessmentSerializer(assessment).data if assessment else None,
            'in_flight_attempt': OnlinePaymentAttemptSerializer(in_flight).data if in_flight else None,
        }, status=status.HTTP_200_OK)


class OnlinePaymentInitiateView(APIView):
    """
    Idempotent payment initiation endpoint.
    Derives payable amount authoritatively from StudentFeeAssessment.
    Creates an OnlinePaymentAttempt and returns the Easebuzz checkout URL.
    """
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = 'payment_initiate'

    def post(self, request):
        if not getattr(settings, 'EASEBUZZ_ENABLED', False):
            return Response(
                {'detail': 'Online payment gateway is currently disabled by administration.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        student = Student.objects.filter(user=request.user).first()
        if not student:
            return Response({'detail': 'Student profile not found.'}, status=status.HTTP_404_NOT_FOUND)

        ay = AcademicYear.objects.filter(is_current=True).first()
        if not ay:
            return Response({'detail': 'Current academic year not found.'}, status=status.HTTP_400_BAD_REQUEST)

        # 1. Check if already paid
        if PaymentLedger.objects.filter(student=student, academic_year=ay, status=PaymentLedger.PaymentStatus.PAID).exists():
            return Response({'detail': 'Fee already recorded as paid. Duplicate payment blocked.'}, status=status.HTTP_400_BAD_REQUEST)

        # 2. Check assessment
        assessment = StudentFeeAssessment.objects.filter(student=student, academic_year=ay).first()
        if not assessment or assessment.total_fee <= Decimal('0.00'):
            return Response({'detail': 'Fee assessment not found. Please contact accounts desk.'}, status=status.HTTP_400_BAD_REQUEST)

        if not assessment.allow_online_payment:
            return Response({'detail': 'Online payment not enabled for this candidate.'}, status=status.HTTP_403_FORBIDDEN)

        # F-S5-002: Enforce eligibility prerequisite (same rule as desk payment).
        # Student must have HOD-approved eligibility (final_eligible=True) for the
        # current academic year before online payment is allowed.
        eligibility = EligibilityVerification.objects.filter(
            student=student,
            academic_year=ay,
            final_eligible=True,
        ).first()
        # First-year / direct-admission students without an eligibility cycle
        # (no year-change verification needed) are exempt.
        needs_eligibility = StudentEnrollment.objects.filter(
            student=student, is_current=True,
            semester__number__in=[3, 5, 7],
        ).exists()
        if needs_eligibility and not eligibility:
            return Response(
                {'detail': 'Academic progression verification must be approved by HOD before online payment.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        # 3. In-flight attempt check (prevents double clicks & parallel charge races)
        # Failed / cancelled / expired attempts never block: student can retry immediately.
        cutoff = timezone.now() - datetime.timedelta(minutes=15)
        in_flight = OnlinePaymentAttempt.objects.filter(
            student=student,
            academic_year=ay,
            status__in=[
                OnlinePaymentAttempt.Status.INITIATED,
                OnlinePaymentAttempt.Status.REDIRECTED,
                OnlinePaymentAttempt.Status.PENDING,
            ],
            initiated_at__gte=cutoff,
        ).order_by('-initiated_at').first()

        if in_flight:
            if in_flight.checkout_url:
                return Response({
                    'attempt_id': str(in_flight.id),
                    'transaction_id': in_flight.transaction_id,
                    'checkout_url': in_flight.checkout_url,
                    'access_key': in_flight.access_key,
                    'amount': str(in_flight.amount),
                    'is_existing_attempt': True,
                    'detail': 'Reconnecting to existing active payment session.',
                }, status=status.HTTP_200_OK)
            return Response(
                {'detail': f'A payment attempt ({in_flight.transaction_id}) is currently pending verification. Please wait before retrying.'},
                status=status.HTTP_409_CONFLICT,
            )

        # 3b. Stale pending check: an attempt older than 15 min may still be
        # pending at the bank. Never create a second live payment blindly —
        # recheck the old one with the bank first.
        stale = OnlinePaymentAttempt.objects.filter(
            student=student,
            academic_year=ay,
            status__in=[
                OnlinePaymentAttempt.Status.INITIATED,
                OnlinePaymentAttempt.Status.REDIRECTED,
                OnlinePaymentAttempt.Status.PENDING,
            ],
        ).order_by('-initiated_at').first()

        if stale:
            from apps.finance.services import apply_gateway_result as _apply
            gateway_probe = EasebuzzGateway()
            # Retrieve hash must reuse the exact initiation contact — never a
            # placeholder, or the gateway rejects the inquiry.
            probe_email = stale.customer_email or getattr(
                getattr(student, 'personal_details', None), 'student_email', ''
            ) or request.user.email or ''
            probe_phone = stale.customer_phone or getattr(
                getattr(student, 'personal_details', None), 'student_mobile', ''
            ) or ''
            if not (probe_email and probe_phone):
                return Response(
                    {'detail': 'A payment attempt is still pending, but no contact is on record for bank inquiry. Ask the accounts desk to reconcile it.'},
                    status=status.HTTP_409_CONFLICT,
                )
            try:
                probe_res = gateway_probe.retrieve_transaction(
                    stale.transaction_id, stale.amount, probe_email, probe_phone,
                )
            except Exception:
                probe_res = {'status': False, 'error': 'retrieve failed'}
            probe_msg = probe_res.get('msg', {}) if isinstance(probe_res.get('msg'), dict) else {}
            probe_status = str(probe_msg.get('status') or probe_res.get('status') or '').lower()
            if probe_status in ('success', 'successful', 'true', '1'):
                _apply(
                    stale.transaction_id, gateway_status='success',
                    easebuzz_txn_id=probe_msg.get('easepayid', ''),
                    raw_payload=probe_res,
                    payment_mode=probe_msg.get('mode', 'ONLINE'),
                    actor=request.user, request=request,
                )
                return Response(
                    {'detail': 'Your earlier payment is now confirmed as paid. Please check payment status.'},
                    status=status.HTTP_409_CONFLICT,
                )
            if probe_status in ('failure', 'failed', 'bounced', 'usercancelled',
                                'user_cancelled', 'cancelled', 'expired'):
                _apply(
                    stale.transaction_id, gateway_status=probe_status,
                    easebuzz_txn_id=probe_msg.get('easepayid', ''),
                    raw_payload=probe_res,
                    actor=request.user, request=request,
                )
                # Old attempt is now closed as failed — fall through and
                # create a fresh payment attempt below.
            else:
                # Still pending / unknown / gateway unreachable — stay safe,
                # do not create a second charge.
                return Response(
                    {'detail': f'A payment attempt ({stale.transaction_id}) is still pending with the bank. Please wait and use Re-Check Status.'},
                    status=status.HTTP_409_CONFLICT,
                )

        # 4. Idempotency control
        idempotency_key = (
            request.headers.get('Idempotency-Key') or
            request.data.get('idempotency_key') or
            str(uuid.uuid4())
        ).strip()

        existing_attempt = OnlinePaymentAttempt.objects.filter(
            student=student,
            idempotency_key=idempotency_key,
        ).first()

        if existing_attempt:
            if existing_attempt.status in (OnlinePaymentAttempt.Status.INITIATED, OnlinePaymentAttempt.Status.REDIRECTED):
                return Response({
                    'attempt_id': str(existing_attempt.id),
                    'transaction_id': existing_attempt.transaction_id,
                    'checkout_url': existing_attempt.checkout_url,
                    'access_key': existing_attempt.access_key,
                    'amount': str(existing_attempt.amount),
                }, status=status.HTTP_200_OK)
            if existing_attempt.status == OnlinePaymentAttempt.Status.SUCCESS:
                return Response({
                    'attempt_id': str(existing_attempt.id),
                    'transaction_id': existing_attempt.transaction_id,
                    'amount': str(existing_attempt.amount),
                    'detail': 'This payment was already confirmed. No new charge created.',
                }, status=status.HTTP_200_OK)
            # Terminal failure states reuse the same key: return the stored
            # outcome instead of violating uniq_online_payment_student_idempotency.
            return Response({
                'attempt_id': str(existing_attempt.id),
                'transaction_id': existing_attempt.transaction_id,
                'status': existing_attempt.status,
                'amount': str(existing_attempt.amount),
                'detail': (
                    f'Previous attempt ended as {existing_attempt.status}. '
                    'Retry with a fresh idempotency key for a new payment.'
                ),
            }, status=status.HTTP_409_CONFLICT)

        # 5. Generate unique transaction ID
        txnid = f"GCOEK_{int(timezone.now().timestamp())}_{uuid.uuid4().hex[:8]}"

        personal = getattr(student, 'personal_details', None)
        customer_email = (getattr(personal, 'student_email', '') or '').strip() or (request.user.email or '').strip()
        customer_phone = (getattr(personal, 'student_mobile', '') or '').strip()
        # Gateway hashes bind email+phone: placeholder contact would corrupt
        # initiation and every later inquiry. Require real contact instead.
        if not customer_email:
            return Response(
                {'detail': 'Add an email address to the student profile before starting online payment.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not customer_phone:
            return Response(
                {'detail': 'Add a mobile number to the student profile before starting online payment.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # F-S7-001: Handle concurrent same-key race: catch IntegrityError and re-fetch existing attempt
        from django.db import IntegrityError
        try:
            attempt = OnlinePaymentAttempt.objects.create(
                student=student,
                academic_year=ay,
                assessment=assessment,
                transaction_id=txnid,
                idempotency_key=idempotency_key,
                amount=assessment.total_fee,
                status=OnlinePaymentAttempt.Status.INITIATED,
                gateway_provider='EASEBUZZ',
                customer_email=customer_email,
                customer_phone=customer_phone,
            )
        except IntegrityError:
            attempt = OnlinePaymentAttempt.objects.filter(
                student=student,
                idempotency_key=idempotency_key,
            ).first()
            if attempt:
                return Response({
                    'attempt_id': str(attempt.id),
                    'transaction_id': attempt.transaction_id,
                    'checkout_url': attempt.checkout_url,
                    'access_key': attempt.access_key,
                    'amount': str(attempt.amount),
                }, status=status.HTTP_200_OK)
            raise

        audit_log(
            request=request,
            actor=request.user,
            action=AuditLog.Action.CREATE,
            target_type='OnlinePaymentAttempt',
            target_id=str(attempt.id),
            target_display=f"Payment Attempt {txnid}",
            reason='Initiated online fee payment',
            description=f"Initiated online fee payment of ₹{attempt.amount} for {student.display_name}.",
        )

        # 5. Call Easebuzz Gateway
        callback_url = request.build_absolute_uri('/api/v1/finance/online-payment/callback/')
        gateway = EasebuzzGateway()
        res = gateway.initiate_payment({
            'txnid': txnid,
            'amount': attempt.amount,
            'productinfo': f"Admission Fee {ay.code}",
            'firstname': student.first_name or student.display_name.split()[0],
            'email': customer_email,
            'phone': customer_phone,
            'surl': callback_url,
            'furl': callback_url,
            'udf1': str(student.id),
            'udf2': str(ay.id),
            'udf3': str(assessment.id),
            'udf4': student.enrollment_no or '',
        })

        if res['success']:
            attempt.status = OnlinePaymentAttempt.Status.REDIRECTED
            attempt.checkout_url = res['checkout_url']
            attempt.access_key = res['access_key']
            attempt.raw_initiation_response = res.get('raw_response', {})
            attempt.save(update_fields=['status', 'checkout_url', 'access_key', 'raw_initiation_response'])

            return Response({
                'attempt_id': str(attempt.id),
                'transaction_id': txnid,
                'checkout_url': attempt.checkout_url,
                'access_key': attempt.access_key,
                'amount': str(attempt.amount),
            }, status=status.HTTP_201_CREATED)
        else:
            attempt.status = OnlinePaymentAttempt.Status.FAILED
            attempt.failure_reason = res.get('error', 'Gateway initiation failed')
            attempt.raw_initiation_response = res.get('raw_response', {})
            attempt.save(update_fields=['status', 'failure_reason', 'raw_initiation_response'])
            audit_log(
                request=request,
                actor=request.user,
                action=AuditLog.Action.UPDATE,
                target_type='OnlinePaymentAttempt',
                target_id=str(attempt.id),
                target_display=f"Payment Attempt {txnid}",
                old_value={'status': 'INITIATED', 'amount': str(attempt.amount)},
                new_value={'status': attempt.status, 'failure_reason': attempt.failure_reason},
                reason='Gateway initiation failed',
                description=(
                    f"Online payment initiation {txnid} for {student.display_name} "
                    f"failed at gateway: {attempt.failure_reason}."
                ),
            )

            return Response(
                {'detail': res.get('error', 'Could not initialize payment gateway. Please retry.')},
                status=status.HTTP_502_BAD_GATEWAY,
            )


class OnlinePaymentAttemptDetailView(APIView):
    """
    Fetch status of a specific payment attempt.
    Students may only view their own; Accountants/Admins can inspect any.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        attempt = OnlinePaymentAttempt.objects.filter(id=pk).first()
        if not attempt:
            return Response({'detail': 'Payment attempt not found.'}, status=status.HTTP_404_NOT_FOUND)

        scopes = get_user_scopes(request.user)
        if not (scopes['is_system_wide'] or 'ADMIN_HEAD' in scopes['roles'] or 'ACCOUNTANT' in scopes['roles']):
            if attempt.student.user_id != request.user.id:
                return Response({'detail': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)

        ledger = PaymentLedger.objects.filter(
            student=attempt.student,
            academic_year=attempt.academic_year,
            status=PaymentLedger.PaymentStatus.PAID,
        ).first()

        data = OnlinePaymentAttemptSerializer(attempt).data
        data['receipt'] = PaymentLedgerSerializer(ledger).data if ledger else None
        return Response(data, status=status.HTTP_200_OK)


class OnlinePaymentAttemptVerifyView(APIView):
    """
    Reconciliation / status-check endpoint for pending or ambiguous transactions.
    """
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = 'payment_verify'

    def post(self, request, pk):
        attempt = OnlinePaymentAttempt.objects.filter(id=pk).first()
        if not attempt:
            return Response({'detail': 'Payment attempt not found.'}, status=status.HTTP_404_NOT_FOUND)

        scopes = get_user_scopes(request.user)
        if not (scopes['is_system_wide'] or 'ADMIN_HEAD' in scopes['roles'] or 'ACCOUNTANT' in scopes['roles']):
            if attempt.student.user_id != request.user.id:
                return Response({'detail': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)

        if attempt.status == OnlinePaymentAttempt.Status.SUCCESS:
            return Response({'status': 'SUCCESS', 'detail': 'Payment already confirmed.'}, status=status.HTTP_200_OK)

        # Query Easebuzz status API — reuse the exact email/phone sent at
        # initiation, otherwise the retrieve hash will not match.
        gateway = EasebuzzGateway()
        student = attempt.student
        email = attempt.customer_email or getattr(
            getattr(student, 'personal_details', None), 'student_email', ''
        ) or getattr(getattr(student, 'user', None), 'email', '') or ''
        phone = attempt.customer_phone or getattr(
            getattr(student, 'personal_details', None), 'student_mobile', ''
        ) or ''
        if not (email and phone):
            return Response(
                {'detail': 'This attempt has no gateway contact on record, so the bank cannot be queried. Ask the accounts desk to reconcile it.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        res = gateway.retrieve_transaction(attempt.transaction_id, attempt.amount, email, phone)
        msg_data = res.get('msg', {}) if isinstance(res.get('msg'), dict) else {}
        ease_status = msg_data.get('status') or res.get('status')

        if str(ease_status).lower() in ('success', 'successful', 'true', '1'):
            attempt, ok, msg = apply_gateway_result(
                attempt.transaction_id,
                gateway_status='success',
                easebuzz_txn_id=msg_data.get('easepayid', ''),
                raw_payload=res,
                payment_mode=msg_data.get('mode', 'ONLINE'),
                actor=request.user,
                request=request,
            )
            return Response({'status': attempt.status, 'detail': msg}, status=status.HTTP_200_OK)

        return Response({
            'status': attempt.status,
            'gateway_response': res,
            'detail': f"Gateway returned status: {ease_status or 'Pending'}",
        }, status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name='dispatch')
class EasebuzzCallbackView(APIView):
    """
    Public callback receiver where Easebuzz POSTs after user returns.
    Verifies reverse cryptographic hash, applies result, and redirects to frontend.
    """
    permission_classes = [permissions.AllowAny]
    throttle_scope = 'payment_callback'

    def post(self, request):
        if not getattr(settings, 'EASEBUZZ_ENABLED', False):
            return Response({'error': 'Online payment gateway is disabled'}, status=status.HTTP_404_NOT_FOUND)

        data = request.data or {}
        try:
            payload = data.dict() if hasattr(data, 'dict') else dict(data)
        except Exception:
            payload = {}
        if not payload:
            payload = request.POST.dict()
        txnid = str(payload.get('txnid', '')).strip()

        # Log raw event durably before processing
        # NOTE: callback comes from the student's browser (surl/furl), NOT
        # from Easebuzz servers — so NO IP allowlist here. Hash check below
        # is the protection. IP allowlist lives on webhook only.
        raw_event = GatewayRawEvent.objects.create(
            event_source='EASEBUZZ',
            event_type='CALLBACK',
            transaction_id=txnid,
            payload=payload,
            ip_address=get_client_ip(request),
        )

        gateway = EasebuzzGateway()
        # F-S5-004: Mock mode is ONLY active in local development (DEBUG=True).
        # A prod misconfiguration (wrong key name or EASEBUZZ_MOCK_MODE=True
        # in .env) must never allow unsigned callbacks to pass hash verification.
        _is_dev_env = getattr(settings, 'DEBUG', False)
        is_mock = _is_dev_env and (
            getattr(settings, 'EASEBUZZ_KEY', '') in ('mock', 'TEST_KEY', 'test_key')
            or getattr(settings, 'EASEBUZZ_MOCK_MODE', False)
        )
        is_verified = is_mock or gateway.verify_response_hash(payload)

        raw_event.is_verified = is_verified
        frontend_base = getattr(settings, 'FRONTEND_BASE_URL', 'http://localhost:5173').rstrip('/')
        from urllib.parse import quote as _quote
        safe_txnid = _quote(txnid, safe='')

        if not is_verified:
            raw_event.processing_error = 'Signature verification failed'
            raw_event.save(update_fields=['is_verified', 'processing_error'])
            logger.warning("Invalid response signature received from Easebuzz for txnid '%s'", txnid)
            audit_log(
                request=request,
                action=AuditLog.Action.UPDATE,
                target_type='GatewayRawEvent',
                target_id=str(raw_event.id),
                target_display=f"Unverified callback {txnid or 'unknown'}",
                new_value={'event_type': 'CALLBACK', 'transaction_id': txnid, 'is_verified': False},
                reason='Gateway signature verification failed',
                description=f"Rejected Easebuzz callback for txn {txnid or 'unknown'}: invalid signature.",
            )
            return HttpResponseRedirect(f"{frontend_base}/fees/payment/error?reason=invalid_signature&txnid={safe_txnid}")

        ease_status = payload.get('status', 'failure')
        easebuzz_txn_id = payload.get('easepayid', '')
        payment_mode = payload.get('mode', 'ONLINE')

        attempt, success, msg = apply_gateway_result(
            transaction_id=txnid,
            gateway_status=ease_status,
            easebuzz_txn_id=easebuzz_txn_id,
            raw_payload=payload,
            payment_mode=payment_mode,
            request=request,
        )

        raw_event.processed = bool(success)
        if not success:
            raw_event.processing_error = msg or f"Payment failed (gateway status: {ease_status})"
            raw_event.save(update_fields=['is_verified', 'processed', 'processing_error'])
        else:
            raw_event.save(update_fields=['is_verified', 'processed'])

        if attempt:
            return HttpResponseRedirect(f"{frontend_base}/fees/payment/{attempt.id}")
        return HttpResponseRedirect(f"{frontend_base}/fees/payment/error?reason=transaction_not_found&txnid={safe_txnid}")


@method_decorator(csrf_exempt, name='dispatch')
class EasebuzzWebhookView(APIView):
    """
    Public server-to-server webhook endpoint for async gateway notifications.
    """
    permission_classes = [permissions.AllowAny]
    throttle_scope = 'payment_callback'

    def post(self, request):
        if not getattr(settings, 'EASEBUZZ_ENABLED', False):
            return Response({'error': 'Online payment gateway is disabled'}, status=status.HTTP_404_NOT_FOUND)

        data = request.data or {}
        try:
            payload = data.dict() if hasattr(data, 'dict') else dict(data)
        except Exception:
            payload = {}
        if not payload:
            payload = request.POST.dict()
        txnid = str(payload.get('txnid', '')).strip()

        # Webhook is server-to-server from Easebuzz — IP allowlist applies here.
        raw_event = GatewayRawEvent.objects.create(
            event_source='EASEBUZZ',
            event_type='WEBHOOK',
            transaction_id=txnid,
            payload=payload,
            ip_address=_get_webhook_client_ip(request),
        )

        if not _is_gateway_ip_allowed(request):
            raw_event.processing_error = 'IP not in allowlist'
            raw_event.save(update_fields=['processing_error'])
            audit_log(
                request=request,
                action=AuditLog.Action.UPDATE,
                target_type='GatewayRawEvent',
                target_id=str(raw_event.id),
                target_display=f"Blocked webhook {txnid or 'unknown'}",
                new_value={'event_type': 'WEBHOOK', 'transaction_id': txnid, 'blocked': True},
                reason='Gateway IP allowlist rejection',
                description=f"Rejected Easebuzz webhook for txn {txnid or 'unknown'}: source IP not allowlisted.",
            )
            return Response({'error': 'Blocked'}, status=status.HTTP_403_FORBIDDEN)

        gateway = EasebuzzGateway()
        # F-S5-004: Same DEBUG+key double-gate for the webhook handler.
        _is_dev_env = getattr(settings, 'DEBUG', False)
        is_mock = _is_dev_env and (
            getattr(settings, 'EASEBUZZ_KEY', '') in ('mock', 'TEST_KEY', 'test_key')
            or getattr(settings, 'EASEBUZZ_MOCK_MODE', False)
        )
        is_verified = is_mock or gateway.verify_response_hash(payload)

        raw_event.is_verified = is_verified
        if not is_verified:
            raw_event.processing_error = 'Signature verification failed'
            raw_event.save(update_fields=['is_verified', 'processing_error'])
            audit_log(
                request=request,
                action=AuditLog.Action.UPDATE,
                target_type='GatewayRawEvent',
                target_id=str(raw_event.id),
                target_display=f"Unverified webhook {txnid or 'unknown'}",
                new_value={'event_type': 'WEBHOOK', 'transaction_id': txnid, 'is_verified': False},
                reason='Gateway signature verification failed',
                description=f"Rejected Easebuzz webhook for txn {txnid or 'unknown'}: invalid signature.",
            )
            return Response({'error': 'Invalid signature'}, status=status.HTTP_400_BAD_REQUEST)

        ease_status = payload.get('status', 'failure')
        easebuzz_txn_id = payload.get('easepayid', '')
        payment_mode = payload.get('mode', 'ONLINE')

        attempt, success, msg = apply_gateway_result(
            transaction_id=txnid,
            gateway_status=ease_status,
            easebuzz_txn_id=easebuzz_txn_id,
            raw_payload=payload,
            payment_mode=payment_mode,
            request=request,
        )

        raw_event.processed = bool(success)
        if not success:
            raw_event.processing_error = msg or f"Payment failed (gateway status: {ease_status})"
            raw_event.save(update_fields=['processed', 'is_verified', 'processing_error'])
        else:
            raw_event.save(update_fields=['processed', 'is_verified'])
        return Response({'status': 'success' if success else 'failed', 'message': msg}, status=status.HTTP_200_OK)


class OnlinePaymentTrackerView(APIView):
    """
    Accountant-facing view for the Online Payment Monitor Tab.
    Lists candidates with online payment status, latest attempts, and reconciliation actions.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        scopes = get_user_scopes(request.user)
        if not (scopes['is_system_wide'] or 'ADMIN_HEAD' in scopes['roles'] or 'ACCOUNTANT' in scopes['roles']):
            return Response({'detail': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)

        ay = request.query_params.get('academic_year')
        qs = StudentFeeAssessment.objects.select_related('student', 'academic_year').prefetch_related(
            'online_payment_attempts',
            'student__enrollments__department',
            'student__payment_records',
        ).all()

        if ay:
            qs = qs.filter(academic_year_id=ay)

        # Filter by online status if requested
        only_online = request.query_params.get('online_only', 'true').lower() in ('true', '1')
        if only_online:
            qs = qs.filter(allow_online_payment=True)

        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(student__display_name__icontains=search) | qs.filter(student__enrollment_no__icontains=search)

        serializer = OnlinePaymentTrackerSerializer(qs[:100], many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

