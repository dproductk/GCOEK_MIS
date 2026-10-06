"""
Seed standard Fee Heads and sample Payment Ledgers.
"""
import datetime
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.academic_structure.models import AcademicYear, Program
from apps.authentication.models import User
from apps.finance.models import FeeHead, PaymentLedger
from apps.students.models import Student


class Command(BaseCommand):
    help = 'Seed institutional fee heads and sample payment receipts.'

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write('Seeding fee heads and payment ledgers...')

        curr_year = AcademicYear.objects.filter(is_current=True).first()
        prog = Program.objects.first()
        admin_user = User.objects.filter(user_type=User.UserType.SYSADMIN).first()

        fee_heads = [
            {'name': 'Tuition Fee (OPEN)', 'code': 'TUIT_OPEN', 'amount': Decimal('15000.00'), 'cat': 'OPEN'},
            {'name': 'Tuition Fee (OBC/EBC)', 'code': 'TUIT_OBC', 'amount': Decimal('7500.00'), 'cat': 'OBC_EBC'},
            {'name': 'Development Fee', 'code': 'DEV_FEE', 'amount': Decimal('5000.00'), 'cat': 'ALL'},
            {'name': 'Gymkhana & Sports Fee', 'code': 'GYM_FEE', 'amount': Decimal('1500.00'), 'cat': 'ALL'},
            {'name': 'Training & Placement Activity', 'code': 'TPO_FEE', 'amount': Decimal('2000.00'), 'cat': 'ALL'},
            {'name': 'Autonomous Examination Fee', 'code': 'EXAM_FEE', 'amount': Decimal('3000.00'), 'cat': 'ALL'},
            {'name': 'Caution / Library Deposit', 'code': 'LIB_DEP', 'amount': Decimal('2000.00'), 'cat': 'ALL', 'ref': True},
        ]

        for fh in fee_heads:
            FeeHead.objects.get_or_create(
                code=fh['code'],
                defaults={
                    'name': fh['name'],
                    'academic_year': curr_year,
                    'program': prog,
                    'category_quota': fh.get('cat', 'ALL'),
                    'amount': fh['amount'],
                    'is_refundable': fh.get('ref', False),
                    'is_active': True,
                },
            )

        # Seed sample payment receipts for existing students
        students = Student.objects.all()[:3]
        for idx, s in enumerate(students, start=1):
            receipt_no = f"GCOEK/2026/FEE/{idx:03d}"
            PaymentLedger.objects.get_or_create(
                receipt_no=receipt_no,
                defaults={
                    'student': s,
                    'academic_year': curr_year,
                    'total_fee_due': Decimal('28500.00'),
                    'amount_paid': Decimal('28500.00'),
                    'balance_due': Decimal('0.00'),
                    'payment_mode': PaymentLedger.PaymentMode.ONLINE,
                    'transaction_ref': f"UPI2026090{idx}9918",
                    'status': PaymentLedger.PaymentStatus.PAID,
                    'payment_date': datetime.date(2026, 8, 26),
                    'collected_by': admin_user,
                    'remarks': 'Annual admission fee fully paid at registration desk',
                },
            )
            self.stdout.write(f"  - Created payment ledger {receipt_no} for {s.display_name}")

        self.stdout.write(self.style.SUCCESS('Successfully seeded fee heads and payment ledgers!'))
