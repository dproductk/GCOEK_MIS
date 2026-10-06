"""
Finance, Fee Head Configuration, Candidate Fee Desk, and Payment Ledger Models.

Implements:
- Fee Head Configuration by Category / Quota (matching payhead setting page.png).
- Candidate Payment Ledger & Challan Generation (matching payment leger.png).
- Fee collection and accountant reconciliation.
"""
from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.academic_structure.models import AcademicYear, Program
from apps.common.models import BaseModel


class FeeHead(BaseModel):
    """
    Standard institutional fee component (Tuition, Development, Gymkhana, Library, Exam).
    """

    class CategoryQuota(models.TextChoices):
        ALL = 'ALL', 'All Categories'
        OPEN = 'OPEN', 'Open Category'
        OBC_EBC = 'OBC_EBC', 'OBC / EBC Category (50% Concession)'
        SC_ST = 'SC_ST', 'SC / ST Category (100% Tuition Waiver)'
        TFWS = 'TFWS', 'Tuition Fee Waiver Scheme (TFWS)'
        EWS = 'EWS', 'Economically Weaker Section (EWS)'

    name = models.CharField(max_length=150)
    code = models.CharField(max_length=50, unique=True)
    tag = models.CharField(max_length=20, blank=True, default='')
    description = models.CharField(max_length=255, blank=True, default='')
    allowed_amounts = models.JSONField(default=list, blank=True)
    display_order = models.PositiveIntegerField(default=1)
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name='fee_heads',
    )
    program = models.ForeignKey(
        Program,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='fee_heads',
    )
    category_quota = models.CharField(
        max_length=20,
        choices=CategoryQuota.choices,
        default=CategoryQuota.ALL,
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    is_refundable = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'finance_fee_heads'
        ordering = ['display_order', 'academic_year', 'name']

    def __str__(self):
        return f'{self.name} ({self.get_category_quota_display()}) - ₹{self.amount}'


class PaymentLedger(BaseModel):
    """
    Official institutional receipt and payment ledger per candidate.
    """

    class PaymentMode(models.TextChoices):
        ONLINE = 'ONLINE', 'Online Gateway (UPI/Netbanking)'
        DD = 'DD', 'Demand Draft'
        CHALLAN = 'CHALLAN', 'Bank Challan'
        CASH = 'CASH', 'Cash Counter'
        NEFT = 'NEFT', 'NEFT / RTGS Transfer'

    class PaymentStatus(models.TextChoices):
        PAID = 'PAID', 'Fully Paid'
        PARTIAL = 'PARTIAL', 'Partially Paid'
        PENDING = 'PENDING', 'Pending Payment'
        REFUNDED = 'REFUNDED', 'Refunded'

    receipt_no = models.CharField(max_length=50, unique=True, db_index=True)
    student = models.ForeignKey(
        'students.Student',
        on_delete=models.PROTECT,
        related_name='payment_records',
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name='payment_records',
    )
    total_fee_due = models.DecimalField(max_digits=10, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2)
    balance_due = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    payment_mode = models.CharField(max_length=20, choices=PaymentMode.choices, default=PaymentMode.ONLINE)
    transaction_ref = models.CharField(max_length=100, blank=True, default='')
    status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PAID, db_index=True)
    payment_date = models.DateField()
    collected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='collected_payments',
    )
    remarks = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'finance_payment_ledgers'
        ordering = ['-payment_date', '-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'academic_year'],
                name='uniq_payment_student_year',
            ),
        ]

    def __str__(self):
        return f'{self.receipt_no}: {self.student.display_name} - ₹{self.amount_paid} ({self.status})'

    def save(self, *args, **kwargs):
        self.balance_due = max(Decimal('0.0'), self.total_fee_due - self.amount_paid)
        if self.balance_due == Decimal('0.0') and self.amount_paid > Decimal('0.0'):
            self.status = self.PaymentStatus.PAID
        elif self.amount_paid > Decimal('0.0'):
            self.status = self.PaymentStatus.PARTIAL
        super().save(*args, **kwargs)


class StudentFeeAssessment(BaseModel):
    """
    Candidate admission fee assessment breakdown for an academic year.
    Matches 'Update Admission Fees' (Candidate Details + Admission Fee Details).
    """

    student = models.ForeignKey(
        'students.Student',
        on_delete=models.CASCADE,
        related_name='fee_assessments',
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name='fee_assessments',
    )
    fee_breakdown = models.JSONField(
        default=dict,
        blank=True,
        help_text='Mapping of fee head names to assessed amounts.',
    )
    total_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    is_marked = models.BooleanField(default=False)
    assessed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assessed_fees',
    )
    remarks = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'finance_student_fee_assessments'
        unique_together = ['student', 'academic_year']
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.student.display_name} ({self.academic_year.code}): ₹{self.total_fee}'

