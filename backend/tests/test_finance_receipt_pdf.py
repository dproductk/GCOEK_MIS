"""
Official fee receipt PDF endpoint tests.

The official receipt is a server-rendered, exact-replica PDF of the paper
challan.  The student API must never expose it; only the accounts desk (and
college-wide role holders) may produce it, and only after full payment.
"""
import pytest
from decimal import Decimal
from rest_framework import status

from apps.finance.models import StudentFeeAssessment
from apps.finance.receipt_pdf import (
    ROW_WRAP_GAP,
    _plan_row_baselines,
    amount_in_words,
    build_receipt_data,
    generate_fee_receipt_pdf,
)
from apps.finance.receipt_template import FEE_ROW_Y, FEE_TABLE_BOTTOM
from apps.students.models import (
    StudentAddress,
    StudentGuardian,
    StudentPersonalDetail,
)

from .test_finance import api_client, finance_setup


@pytest.mark.django_db
class TestReceiptPdfEndpoint:
    def test_accountant_can_fetch_paid_receipt_pdf(self, finance_setup, api_client):
        ledger = finance_setup['ledger1']
        assert ledger.amount_paid == ledger.total_fee_due

        StudentPersonalDetail.objects.create(
            student=ledger.student,
            student_mobile='9012345678',
        )
        StudentGuardian.objects.create(
            student=ledger.student,
            relationship=StudentGuardian.Relationship.FATHER,
            name='Guardian Shinde',
            mobile='9012345679',
            is_primary=True,
        )
        StudentAddress.objects.create(
            student=ledger.student,
            address_type=StudentAddress.AddressType.PERMANENT,
            address_line_1='Plot 10, Shivaji Nagar',
            district='Kolhapur',
            state='Maharashtra',
            pincode='416001',
        )

        api_client.force_authenticate(user=finance_setup['user_acc'])
        response = api_client.get(f'/api/v1/finance/ledger/{ledger.id}/receipt-pdf/')

        assert response.status_code == status.HTTP_200_OK
        assert response['Content-Type'] == 'application/pdf'
        assert response.content.startswith(b'%PDF')
        content_disposition = response['Content-Disposition']
        assert content_disposition.startswith('inline; filename="Fee_Receipt_')
        assert response['Cache-Control'] == 'private, no-store'

    def test_student_cannot_download_official_receipt(self, finance_setup, api_client):
        ledger = finance_setup['ledger1']
        api_client.force_authenticate(user=finance_setup['user_stu1'])
        response = api_client.get(f'/api/v1/finance/ledger/{ledger.id}/receipt-pdf/')

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_unpaid_ledger_cannot_mint_a_receipt(self, finance_setup, api_client):
        ledger = finance_setup['ledger2']
        assert ledger.amount_paid < ledger.total_fee_due

        api_client.force_authenticate(user=finance_setup['user_acc'])
        response = api_client.get(f'/api/v1/finance/ledger/{ledger.id}/receipt-pdf/')

        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestReceiptSnapshot:
    def test_snapshot_heads_split_into_government_and_institute(self, finance_setup):
        ledger = finance_setup['ledger1']
        ledger.fee_snapshot = {
            'Tuition Fee': '45000.00',
            'Development Fee': '10000.00',
            'Gymkhana Fees': '500.00',
        }
        ledger.fee_types_snapshot = {
            'Tuition Fee': 'GOVERNMENT',
            'Development Fee': 'INSTITUTE',
            'Gymkhana Fees': 'INSTITUTE',
        }
        ledger.save()

        data = build_receipt_data(ledger)
        assert [head.name for head in data.government_heads] == ['Tuition Fee']
        assert [head.name for head in data.non_government_heads] == [
            'Development Fee',
            'Gymkhana Fees',
        ]
        assert data.amount_paid == ledger.amount_paid

    def test_legacy_receipt_falls_back_to_assessment_breakdown(self, finance_setup):
        ledger = finance_setup['ledger1']
        StudentFeeAssessment.objects.create(
            student=ledger.student,
            academic_year=ledger.academic_year,
            fee_breakdown={'Tuition Fee': '65000.00'},
        )

        data = build_receipt_data(ledger)
        assert len(data.non_government_heads) == 1
        assert data.non_government_heads[0].amount == ledger.amount_paid
        assert data.amount_paid == ledger.amount_paid

    def test_empty_breakdown_falls_back_to_a_single_line(self, finance_setup):
        ledger = finance_setup['ledger1']
        data = build_receipt_data(ledger)
        assert len(data.non_government_heads) == 1
        assert data.non_government_heads[0].name == 'Fee (as assessed)'
        assert data.non_government_heads[0].amount == ledger.amount_paid

    def test_zero_amount_head_is_printed(self, finance_setup):
        """A head assessed at 0 must still appear on the receipt as a 0 row."""
        ledger = finance_setup['ledger1']
        ledger.fee_snapshot = {
            'Tuition Fee': '60000.00',
            'Library Fee': '0.00',
        }
        ledger.fee_types_snapshot = {
            'Tuition Fee': 'INSTITUTE',
            'Library Fee': 'INSTITUTE',
        }
        ledger.save()

        data = build_receipt_data(ledger)
        heads = {(head.name, head.amount) for head in data.non_government_heads}
        assert ('Library Fee', Decimal('0.00')) in heads
        # The zero head draws without crashing and without adding to Total (B).
        pdf_bytes = generate_fee_receipt_pdf(data)
        assert pdf_bytes.startswith(b'%PDF')
        assert sum(h.amount for h in data.non_government_heads) == Decimal('60000.00')


class TestContentAwareRowLayout:
    """Fee rows: even airy pitch, growing where wrapped names need room."""

    def test_rows_spread_evenly_between_the_form_anchors(self):
        baselines = _plan_row_baselines([0.0] * len(FEE_ROW_Y))

        assert baselines[0] == FEE_ROW_Y[0]
        assert baselines[-1] == pytest.approx(FEE_ROW_Y[-1], abs=1e-6)
        pitches = [higher - lower for higher, lower in zip(baselines, baselines[1:])]
        assert all(abs(pitch - pitches[0]) < 1e-6 for pitch in pitches)
        # Airier than the old cramped slots (row text is 7.71pt tall).
        assert pitches[0] >= ROW_WRAP_GAP + 6.0

    def test_wrapped_rows_claim_needed_space_but_stay_on_the_form(self):
        # Worst realistic case: every row's name wraps to two lines.
        blocks = [ROW_WRAP_GAP] * len(FEE_ROW_Y)
        baselines = _plan_row_baselines(blocks)

        assert baselines[0] == FEE_ROW_Y[0]
        assert all(higher > lower for higher, lower in zip(baselines, baselines[1:]))
        # Every wrapped line clears its successor by at least the gap floor.
        assert all(
            higher - block >= lower - 1e-6
            for higher, lower, block in zip(baselines, baselines[1:], blocks[:-1])
        )
        assert baselines[-1] - ROW_WRAP_GAP >= FEE_TABLE_BOTTOM - 1e-6

    def test_last_row_wrapping_pushes_its_anchor_down_not_off_the_form(self):
        # A two-line name on the final row raises that row's anchor so the
        # wrapped line stays above the table's bottom rule.
        blocks = [0.0] * (len(FEE_ROW_Y) - 1) + [ROW_WRAP_GAP]
        baselines = _plan_row_baselines(blocks)

        assert baselines[0] == FEE_ROW_Y[0]
        assert baselines[-1] - ROW_WRAP_GAP >= FEE_TABLE_BOTTOM - 1e-6


def test_amount_in_words_indian_numbering():
    assert amount_in_words('65000') == 'Rupees Sixty-Five Thousand Only'
    assert amount_in_words('23725') == (
        'Rupees Twenty-Three Thousand Seven Hundred Twenty-Five Only'
    )
    assert amount_in_words('100000') == 'Rupees One Lakh Only'
    assert amount_in_words('1500000') == 'Rupees Fifteen Lakh Only'
