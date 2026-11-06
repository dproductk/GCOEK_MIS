"""
Management command: python manage.py report_last24h

Prints all payments recorded in the last 24 hours, including the
transaction_ref value the accountant enters (challan/bank/UPI reference).

Options:
    --days 7        look back further, e.g. last 7 days instead of 24 hrs
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.finance.models import PaymentLedger


class Command(BaseCommand):
    help = 'List payments recorded in the last 24 hours (transaction_ref included)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=0,
            help='Look back this many days instead of 24 hours. e.g. --days 7',
        )

    def handle(self, *args, **options):
        days = options['days']
        since = timezone.now() - (timedelta(days=days) if days else timedelta(hours=24))

        rows = (
            PaymentLedger.objects
            .filter(created_at__gte=since)
            .select_related('student')
            .order_by('created_at')
        )

        total = 0
        self.stdout.write('=' * 90)
        self.stdout.write(
            f'Payments since {since:%d-%b-%Y %H:%M}'
            + (f'  (last {days} days)' if days else '  (last 24 hrs)')
        )
        self.stdout.write('=' * 90)
        self.stdout.write(
            f'{"Receipt No":<28}{"Student":<28}{"Mode":<10}{"Amount":>10}  Transaction Ref'
        )
        self.stdout.write('-' * 90)

        for p in rows:
            total += p.amount_paid
            name = (p.student.display_name or '')[:27]
            self.stdout.write(
                f'{p.receipt_no:<28}{name:<28}{p.payment_mode:<10}'
                f'{p.amount_paid:>10}  {p.transaction_ref or "-"}'
            )

        self.stdout.write('-' * 90)
        self.stdout.write(f'Total records: {rows.count()}   Total collected: Rs. {total}')
