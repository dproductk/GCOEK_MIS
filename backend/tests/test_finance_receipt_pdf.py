"""
Official fee receipt PDF endpoint tests.

The official receipt is a server-rendered, exact-replica PDF of the paper
challan.  The student API must never expose it; only the accounts desk (and
college-wide role holders) may produce it, and only after full payment.
"""
import pytest
from decimal import Decimal
from rest_framework import status

from apps.finance.models import FeeHead, StudentFeeAssessment
from apps.finance.receipt_pdf import (
    CHALLAN_NUMBER_SIZE,
    ROW_WRAP_GAP,
    SMALL_SIZE,
    FeeReceiptData,
    ReceiptHead,
    _field_geometry,
    _fit_size,
    _plan_row_baselines,
    amount_in_words,
    build_receipt_data,
    generate_fee_receipt_pdf,
)
from apps.academic_structure.models import Program
from apps.finance.receipt_template import (
    CHALLAN_LABEL,
    COPIES,
    FEE_ROW_Y,
    FEE_TABLE_BOTTOM,
    FONT_BOLD,
    STATIC_TEXT,
)
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


@pytest.mark.django_db
class TestReceiptHeadOrder:
    """Printed row order follows FeeHead.display_order, per column.

    Payment snapshots arrive in Postgres jsonb order (name length then
    alphabetical), so the renderer must re-rank them against the fee desk's
    configured sequence rather than trusting dict insertion order.
    """

    def _add_heads(self, finance_setup, specs):
        year = finance_setup['year']
        program = finance_setup['prog']
        for name, code, order, fee_type in specs:
            FeeHead.objects.create(
                name=name,
                code=code,
                academic_year=year,
                program=program,
                display_order=order,
                fee_type=fee_type,
            )

    def test_each_column_is_sorted_by_display_order(self, finance_setup):
        self._add_heads(finance_setup, [
            ('Development Fee', 'DF-2026', 2, FeeHead.FeeType.INSTITUTE),
            ('Gymkhana Fees', 'GKF-2026', 3, FeeHead.FeeType.INSTITUTE),
            # 'Tuition Fee' already exists from the fixture with order 1.
        ])
        ledger = finance_setup['ledger1']
        # Snapshot deliberately scrambled — the order the DB gives back.
        ledger.fee_snapshot = {
            'Gymkhana Fees': '500.00',
            'Tuition Fee': '60000.00',
            'Development Fee': '10000.00',
        }
        ledger.fee_types_snapshot = {
            'Gymkhana Fees': 'INSTITUTE',
            'Tuition Fee': 'GOVERNMENT',
            'Development Fee': 'INSTITUTE',
        }
        ledger.save()

        data = build_receipt_data(ledger)

        assert [head.name for head in data.government_heads] == ['Tuition Fee']
        assert [head.name for head in data.non_government_heads] == [
            'Development Fee',
            'Gymkhana Fees',
        ]

    def test_changing_display_order_changes_receipt_order(self, finance_setup):
        self._add_heads(finance_setup, [
            ('Development Fee', 'DF-2026', 2, FeeHead.FeeType.INSTITUTE),
            ('Gymkhana Fees', 'GKF-2026', 3, FeeHead.FeeType.INSTITUTE),
        ])
        ledger = finance_setup['ledger1']
        ledger.fee_snapshot = {
            'Development Fee': '10000.00',
            'Gymkhana Fees': '500.00',
        }
        ledger.fee_types_snapshot = {
            'Development Fee': 'INSTITUTE',
            'Gymkhana Fees': 'INSTITUTE',
        }
        ledger.save()

        # Fee desk re-orders Gymkhana above Development.
        FeeHead.objects.filter(code='GKF-2026').update(display_order=1)
        FeeHead.objects.filter(code='DF-2026').update(display_order=9)

        data = build_receipt_data(ledger)
        assert [head.name for head in data.non_government_heads] == [
            'Gymkhana Fees',
            'Development Fee',
        ]

    def test_duplicate_head_names_across_programs_use_lowest_order(self, finance_setup):
        # Same name configured per program with different orders — the
        # lowest configured order must win deterministically.
        self._add_heads(finance_setup, [
            ('Development Fee', 'DF-CSE-2026', 7, FeeHead.FeeType.INSTITUTE),
        ])
        other_program = Program.objects.create(
            department=finance_setup['prog'].department,
            name='B.Tech Mechanical',
            code='BTECH_MECH',
        )
        FeeHead.objects.create(
            name='Development Fee', code='DF-MECH-2026',
            academic_year=finance_setup['year'], program=other_program,
            display_order=3, fee_type=FeeHead.FeeType.INSTITUTE,
        )
        ledger = finance_setup['ledger1']
        ledger.fee_snapshot = {
            'Development Fee': '10000.00',
            'Gymkhana Fees': '500.00',
        }
        ledger.fee_types_snapshot = {
            'Development Fee': 'INSTITUTE',
            'Gymkhana Fees': 'INSTITUTE',
        }
        ledger.save()

        data = build_receipt_data(ledger)
        # Development (rank 3) still precedes the unranked Gymkhana head.
        assert [head.name for head in data.non_government_heads] == [
            'Development Fee',
            'Gymkhana Fees',
        ]

    def test_deleted_head_stays_on_receipt_at_the_end_of_its_column(self, finance_setup):
        ledger = finance_setup['ledger1']
        ledger.fee_snapshot = {
            'Removed Fee Head': '300.00',
            'Tuition Fee': '60000.00',
        }
        ledger.fee_types_snapshot = {
            'Removed Fee Head': 'INSTITUTE',
            'Tuition Fee': 'INSTITUTE',
        }
        ledger.save()

        data = build_receipt_data(ledger)
        assert [head.name for head in data.non_government_heads] == [
            'Tuition Fee',
            'Removed Fee Head',
        ]
        assert sum(h.amount for h in data.non_government_heads) == Decimal('60300.00')


class TestChallanNumberStyling:
    """The challan number is bold, larger, and fully fits its blank."""

    def _blank_width(self, copy):
        start, end = _field_geometry(CHALLAN_LABEL, copy['challan_x'], FONT_BOLD, SMALL_SIZE)
        return max(0, end - start - 1.0)

    def test_static_label_is_bold_and_matches_the_geometry_constant(self):
        challan_labels = [
            text for (x, y, size, font, text) in STATIC_TEXT
            if text.startswith('Challan No.')
        ]
        assert len(challan_labels) == 3
        assert all(text == CHALLAN_LABEL for text in challan_labels)
        challan_fonts = [
            font for (x, y, size, font, text) in STATIC_TEXT
            if text.startswith('Challan No.')
        ]
        assert challan_fonts == [FONT_BOLD, FONT_BOLD, FONT_BOLD]

    def test_realistic_receipt_number_fits_at_full_size_in_every_copy(self):
        number = 'I-2026-27-0002'
        for copy in COPIES:
            width = self._blank_width(copy)
            assert width > 0
            assert _fit_size(number, FONT_BOLD, CHALLAN_NUMBER_SIZE, width) == pytest.approx(
                CHALLAN_NUMBER_SIZE
            )

    def test_blank_stays_inside_each_copies_outer_boundary(self):
        from reportlab.pdfbase import pdfmetrics

        for copy in COPIES:
            label_end = copy['challan_x'] + pdfmetrics.stringWidth(
                CHALLAN_LABEL, FONT_BOLD, SMALL_SIZE,
            )
            assert label_end < copy['right']

    def test_receipt_with_a_long_number_still_renders(self):
        data = FeeReceiptData(
            student_name='Test Student',
            address='Kolhapur',
            student_mobile='',
            guardian_mobile='',
            branch='EE',
            receipt_no='I-2026-27-000299',
            payment_date=None,
            government_heads=[ReceiptHead('Tuition Fee', Decimal('1000'))],
            non_government_heads=[],
            amount_paid=Decimal('1000'),
        )
        pdf_bytes = generate_fee_receipt_pdf(data)
        assert pdf_bytes.startswith(b'%PDF')


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
