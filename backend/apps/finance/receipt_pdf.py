"""
Official fee receipt PDF renderer.

The layout is a vector reproduction of
``design/GCOEK_ADMISSION_CHALLAN_Borders_Fixed.pdf``.  It is generated
server-side so the printed copy is identical on every machine: the same A4
landscape page, the same three copies, the same embedded Liberation Sans /
Carlito fonts, and the same static wording (including the source form's
spellings).

Fee heads are never hard-coded.  They come from the payment ledger's frozen
``fee_snapshot`` (falling back to the assessment only for legacy receipts),
and are split into the Government / Non-Government columns using the frozen
``fee_types_snapshot`` — including heads assessed at ``0``, which are printed
as ``0`` rows like the paper form.  Payments are full-payment only, so the
head total and the amount paid reconcile.

Row spacing is content-aware: every head name is measured first, then the
rows breathe at an even pitch between the form's first- and last-row
anchors, each row claiming exactly the room its (wrapped) name needs —
always staying above the table's bottom rule.

No browser/HTML print path is used.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, Sequence

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from .receipt_template import (
    ADDRESS_LABEL,
    ADDRESS_LINE_2,
    BRANCH_LABEL,
    CHALLAN_LABEL,
    COPIES,
    DATE_LABEL,
    FEE_ROW_Y,
    FEE_TABLE_BOTTOM,
    FONT_BOLD,
    FONT_REGULAR,
    FONT_URL,
    IN_WORDS_LABEL,
    LINES,
    MOBILE_LABEL,
    NAME_LABEL,
    PAGE_SIZE,
    STATIC_TEXT,
    TOTAL_LABEL,
)

ASSET_DIR = Path(__file__).resolve().parent / 'receipt_assets'

_FONT_FILES = {
    FONT_REGULAR: 'LiberationSans-Regular.ttf',
    FONT_BOLD: 'LiberationSans-Bold.ttf',
    FONT_URL: 'Carlito-Regular.ttf',
}

_FONTS_REGISTERED = False

# Row/field sizes taken from the source PDF.
BASE_SIZE = 7.71
SMALL_SIZE = 7.2
TOTAL_SIZE = 8.51
# Challan number: bold and one step larger than the other small fields so the
# printed receipt number stands out, while still fitting its underscore blank
# (the fitted draw shrinks back if a longer number ever needs the room).
CHALLAN_NUMBER_SIZE = 8.51
MIN_FIELD_SIZE = 5.0
MIN_FEE_SIZE = 5.4

# Content-aware fee-row layout.  ``FEE_ROW_Y[0]``/``FEE_ROW_Y[-1]`` stay as
# the top/bottom anchors; between them the rows breathe at an even pitch
# (capped so a short head list doesn't spread edge to edge), and a row whose
# name wraps grows by exactly the room its lines need.
ROW_GAP_MIN = 7.0         # minimum clearance between a wrapped block and the next baseline
ROW_GAP_FLOOR = 4.0       # absolute minimum gap in the overflow squeeze path
ROW_PITCH_CAP = 20.0      # maximum uniform row pitch for sparse head lists
ROW_WRAP_GAP = 7.0        # wrapped-line offset inside rows 2..
FIRST_ROW_WRAP_GAP = 8.6  # wrapped-line offset inside the taller first row


@dataclass(frozen=True)
class ReceiptHead:
    """One printed fee-head row."""

    name: str
    amount: Decimal


@dataclass(frozen=True)
class FeeReceiptData:
    """Everything the receipt template needs, independent of Django models."""

    student_name: str
    address: str
    student_mobile: str
    guardian_mobile: str
    branch: str
    receipt_no: str
    payment_date: date | None
    government_heads: Sequence[ReceiptHead]
    non_government_heads: Sequence[ReceiptHead]
    amount_paid: Decimal


def _register_fonts() -> None:
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return

    for alias, filename in _FONT_FILES.items():
        path = ASSET_DIR / filename
        if not path.exists():
            raise RuntimeError(
                f'Official receipt font is missing: {path}. '
                'The receipt PDF requires the bundled Liberation Sans / Carlito files.'
            )
        pdfmetrics.registerFont(TTFont(alias, str(path)))

    _FONTS_REGISTERED = True


def _as_decimal(value) -> Decimal:
    try:
        return Decimal(str(value)).quantize(Decimal('0.01'))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal('0.00')


def _money(value) -> str:
    """Format like the source challan: plain digits, no thousands separators."""
    amount = _as_decimal(value)
    if amount == amount.to_integral_value():
        return str(int(amount))
    return f'{amount:.2f}'


_ONES = (
    '', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight',
    'Nine', 'Ten', 'Eleven', 'Twelve', 'Thirteen', 'Fourteen', 'Fifteen',
    'Sixteen', 'Seventeen', 'Eighteen', 'Nineteen',
)
_TENS = ('', '', 'Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety')


def _two_digits(number: int) -> str:
    if number < 20:
        return _ONES[number]
    tens, ones = divmod(number, 10)
    return _TENS[tens] + (f'-{_ONES[ones]}' if ones else '')


def _indian_words(number: int) -> str:
    if number == 0:
        return 'Zero'

    parts: list[str] = []
    crore, number = divmod(number, 10_000_000)
    lakh, number = divmod(number, 100_000)
    thousand, number = divmod(number, 1_000)
    hundred, number = divmod(number, 100)

    if crore:
        parts.append(f'{_indian_words(crore)} Crore')
    if lakh:
        parts.append(f'{_two_digits(lakh)} Lakh')
    if thousand:
        parts.append(f'{_two_digits(thousand)} Thousand')
    if hundred:
        parts.append(f'{_ONES[hundred]} Hundred')
    if number:
        parts.append(_two_digits(number))

    return ' '.join(parts)


def amount_in_words(value) -> str:
    """Indian-numbering amount in words, e.g. 'Rupees Sixty-Five Thousand Only'."""
    amount = _as_decimal(value)
    rupees = int(amount)
    paise = int((amount - rupees) * 100)
    words = f'Rupees {_indian_words(rupees)}'
    if paise:
        words += f' and {_two_digits(paise)} Paise'
    return f'{words} Only'


def _fit_size(
    text: str,
    font: str,
    base_size: float,
    max_width: float,
    min_size: float = MIN_FIELD_SIZE,
) -> float:
    """Largest size <= base_size that keeps ``text`` on one line."""
    if max_width <= 0:
        return min_size
    if pdfmetrics.stringWidth(text, font, base_size) <= max_width:
        return base_size

    size = base_size
    while size > min_size:
        size = max(min_size, size - 0.1)
        if pdfmetrics.stringWidth(text, font, size) <= max_width:
            return size
    return min_size


def _truncate(text: str, font: str, size: float, max_width: float) -> str:
    """Ellipsis-fit a single line.  Used only for pathological field values."""
    if pdfmetrics.stringWidth(text, font, size) <= max_width:
        return text
    ellipsis = '...'
    available = max_width - pdfmetrics.stringWidth(ellipsis, font, size)
    if available <= 0:
        return ellipsis
    trimmed = text
    while trimmed and pdfmetrics.stringWidth(trimmed, font, size) > available:
        trimmed = trimmed[:-1]
    return (trimmed.rstrip() + ellipsis) if trimmed else ellipsis


def _draw_fitted(
    pdf: canvas.Canvas,
    text: str,
    x: float,
    y: float,
    max_width: float,
    font: str = FONT_REGULAR,
    base_size: float = BASE_SIZE,
    min_size: float = MIN_FIELD_SIZE,
    right_align: bool = False,
) -> None:
    if not text:
        return
    size = _fit_size(text, font, base_size, max_width, min_size)
    if pdfmetrics.stringWidth(text, font, size) > max_width:
        text = _truncate(text, font, size, max_width)
    pdf.setFont(font, size)
    if right_align:
        pdf.drawRightString(x, y, text)
    else:
        pdf.drawString(x, y, text)


def _wrap_text(
    text: str,
    font: str,
    size: float,
    max_width: float,
    max_lines: int,
) -> list[str]:
    """Greedy word wrap, with a hard character break for unbroken tokens."""
    words = text.split()
    if not words:
        return []

    lines: list[str] = []
    current = ''
    for word in words:
        candidate = f'{current} {word}'.strip()
        if pdfmetrics.stringWidth(candidate, font, size) <= max_width:
            current = candidate
            continue

        if current:
            lines.append(current)
            current = ''

        # A single word may be wider than the column (long code/name).
        if pdfmetrics.stringWidth(word, font, size) > max_width:
            chunk = ''
            for char in word:
                candidate_chunk = chunk + char
                if pdfmetrics.stringWidth(candidate_chunk, font, size) <= max_width:
                    chunk = candidate_chunk
                else:
                    if chunk:
                        lines.append(chunk)
                    chunk = char
            current = chunk
        else:
            current = word

        if len(lines) >= max_lines:
            break

    if current and len(lines) < max_lines:
        lines.append(current)

    if len(lines) > max_lines:
        lines = lines[:max_lines]
    return lines


def _wrap_for_widths(
    text: str,
    font: str,
    size: float,
    widths: Sequence[float],
    max_lines: int,
) -> list[str]:
    """Wrap into consecutive lines with different widths (Address line 1/2)."""
    words = text.split()
    if not words:
        return []

    lines: list[str] = []
    current = ''
    width_index = 0
    for word in words:
        max_width = widths[min(width_index, len(widths) - 1)]
        candidate = f'{current} {word}'.strip()
        if pdfmetrics.stringWidth(candidate, font, size) <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
            width_index += 1
            current = ''
            if len(lines) >= max_lines:
                break
        if pdfmetrics.stringWidth(word, font, size) > max_width:
            # Hard-break only as a last resort; the caller shrinks first.
            current = word
        else:
            current = word

    if current and len(lines) < max_lines:
        lines.append(current)
    return lines[:max_lines]


def _field_geometry(label: str, x: float, font: str, size: float) -> tuple[float, float]:
    """Return (value-start, field-end) for a label with underscore blanks."""
    prefix = label.split('_', 1)[0]
    start = x + pdfmetrics.stringWidth(prefix, font, size)
    end = x + pdfmetrics.stringWidth(label, font, size)
    return start, end


def _underscore_runs(label: str, x: float, font: str, size: float) -> list[tuple[float, float]]:
    runs: list[tuple[float, float]] = []
    for match in re.finditer(r'_+', label):
        start = x + pdfmetrics.stringWidth(label[:match.start()], font, size)
        end = x + pdfmetrics.stringWidth(label[:match.end()], font, size)
        runs.append((start, end))
    return runs


def _draw_static_furniture(pdf: canvas.Canvas) -> None:
    pdf.setLineCap(0)
    pdf.setLineJoin(1)

    for x, y, size, font, text in STATIC_TEXT:
        pdf.setFont(font, size)
        pdf.drawString(x, y, text)

    # URL underlines, matching the source's thin underline.
    pdf.setLineWidth(0.89)
    for x, y, size, font, text in STATIC_TEXT:
        if text.startswith('https://'):
            width = pdfmetrics.stringWidth(text, font, size)
            pdf.line(x, y - 1.2, x + width, y - 1.2)

    for x1, y1, x2, y2, line_width in LINES:
        pdf.setLineWidth(line_width)
        pdf.line(x1, y1, x2, y2)


def _draw_fields(pdf: canvas.Canvas, data: FeeReceiptData) -> None:
    date_text = data.payment_date.strftime('%d-%m-%Y') if data.payment_date else ''

    for copy in COPIES:
        # Date (no underscore blank in the source; value follows "Date -").
        date_x = copy['date_x'] + pdfmetrics.stringWidth(f'{DATE_LABEL} ', FONT_REGULAR, BASE_SIZE)
        _draw_fitted(
            pdf, date_text, date_x, 535.96,
            copy['right'] - date_x - 6, FONT_REGULAR, BASE_SIZE,
        )

        # Challan number.  Both label and value are bold; the blank geometry
        # is measured with the label's own font so the value lands on the
        # same underscore run the static label draws.
        start, end = _field_geometry(CHALLAN_LABEL, copy['challan_x'], FONT_BOLD, SMALL_SIZE)
        _draw_fitted(
            pdf, data.receipt_no, start + 0.5, 489.07,
            max(0, end - start - 1.0), FONT_BOLD, CHALLAN_NUMBER_SIZE, min_size=5.0,
        )

        # Branch.
        start, end = _field_geometry(BRANCH_LABEL, copy['branch_x'], FONT_REGULAR, SMALL_SIZE)
        _draw_fitted(
            pdf, data.branch, start + 0.5, 476.32,
            max(0, end - start - 1.0), FONT_REGULAR, SMALL_SIZE, min_size=5.0,
        )

        # Name.
        start, end = _field_geometry(NAME_LABEL, copy['name_x'], FONT_REGULAR, BASE_SIZE)
        _draw_fitted(
            pdf, data.student_name, start + 0.5, 450.59,
            max(0, end - start - 1.0), FONT_REGULAR, BASE_SIZE, min_size=5.2,
        )

        # Address: two ruled lines.  Shrink until it fits in two lines.
        addr_start, addr_end = _field_geometry(
            ADDRESS_LABEL, copy['address_x'], FONT_REGULAR, BASE_SIZE,
        )
        line_2_start = copy['address_x']
        line_2_end = line_2_start + pdfmetrics.stringWidth(ADDRESS_LINE_2, FONT_REGULAR, BASE_SIZE)
        widths = (max(0, addr_end - addr_start - 1.0), max(0, line_2_end - line_2_start - 1.0))

        address = data.address.strip()
        address_lines: list[str] = []
        address_size = BASE_SIZE
        for size in _descending_sizes(BASE_SIZE, 5.2):
            candidate = _wrap_for_widths(address, FONT_REGULAR, size, widths, max_lines=2)
            if len(candidate) <= 2:
                address_lines = candidate
                address_size = size
                break
        if not address_lines and address:
            address_lines = _wrap_for_widths(address, FONT_REGULAR, 5.2, widths, max_lines=2)
            address_size = 5.2
        for index, line in enumerate(address_lines[:2]):
            x = (addr_start + 0.5) if index == 0 else (line_2_start + 0.5)
            width = widths[index]
            pdf.setFont(FONT_REGULAR, address_size)
            pdf.drawString(x, 440.4 if index == 0 else 430.21, _truncate(line, FONT_REGULAR, address_size, width))

        # Mobile 1 (student) and Mobile 2 (guardian).
        mobile_runs = _underscore_runs(MOBILE_LABEL, copy['mobile_x'], FONT_REGULAR, BASE_SIZE)
        mobiles = (data.student_mobile, data.guardian_mobile)
        for index, (run_start, run_end) in enumerate(mobile_runs[:2]):
            _draw_fitted(
                pdf, mobiles[index] if index < len(mobiles) else '',
                run_start + 0.5, 420.02,
                max(0, run_end - run_start - 1.0),
                FONT_REGULAR, BASE_SIZE, min_size=5.5,
            )

    _draw_fee_rows(pdf, data)
    _draw_totals(pdf, data)


def _descending_sizes(base: float, floor: float):
    size = base
    while size >= floor:
        yield round(size, 2)
        size -= 0.1
    yield floor


def _layout_first_fee_name(name: str, max_width: float) -> tuple[float, list[str]]:
    """Taller first row: base size with up to three wrapped lines."""
    for size in _descending_sizes(BASE_SIZE, MIN_FEE_SIZE):
        lines = _wrap_text(name, FONT_REGULAR, size, max_width, max_lines=3)
        if len(lines) <= 3 and all(
            pdfmetrics.stringWidth(line, FONT_REGULAR, size) <= max_width for line in lines
        ):
            return size, lines
    return MIN_FEE_SIZE, _wrap_text(name, FONT_REGULAR, MIN_FEE_SIZE, max_width, max_lines=3)


def _layout_normal_fee_name(name: str, max_width: float) -> tuple[float, list[str]]:
    """Rows 2+: keep one line by shrinking; wrap to two lines only if needed."""
    size = _fit_size(name, FONT_REGULAR, BASE_SIZE, max_width, min_size=MIN_FEE_SIZE)
    if pdfmetrics.stringWidth(name, FONT_REGULAR, size) <= max_width:
        return size, [name]
    return MIN_FEE_SIZE, _wrap_text(name, FONT_REGULAR, MIN_FEE_SIZE, max_width, max_lines=2)


def _draw_name_lines(
    pdf: canvas.Canvas,
    lines: Sequence[str],
    size: float,
    x: float,
    y: float,
    max_width: float,
    wrap_gap: float,
) -> None:
    pdf.setFont(FONT_REGULAR, size)
    for offset, line in enumerate(lines):
        if pdfmetrics.stringWidth(line, FONT_REGULAR, size) > max_width:
            line = _truncate(line, FONT_REGULAR, size, max_width)
        pdf.drawString(x, y - (offset * wrap_gap), line)


def _plan_row_baselines(blocks: Sequence[float]) -> list[float]:
    """Content-aware, evenly spaced fee-row baselines.

    ``blocks[i]`` is how far row i's name reaches below its baseline
    (0 for single-line names).  Rows breathe uniformly: every consecutive
    pair keeps the same clearance after the taller row's wrapped lines, so
    short rows read airy instead of cramped.  The stack is pinned to the
    form's first-row anchor on top and its last-row anchor at the bottom;
    if the content cannot fit inside those bounds the row gaps are squeezed
    (never below ``ROW_GAP_FLOOR``) so nothing crosses the bottom rule.
    """
    count = len(blocks)
    if count == 0:
        return []
    if count == 1:
        return [FEE_ROW_Y[0]]

    top = FEE_ROW_Y[0]
    # A wrapped row that happens to sit last still needs its lines above
    # the table's bottom rule, so lower that anchor when required.
    bottom_anchor = max(FEE_ROW_Y[-1], FEE_TABLE_BOTTOM + blocks[-1])

    gap = (top - bottom_anchor - sum(blocks[:-1])) / (count - 1)
    gap = min(gap, ROW_PITCH_CAP)
    gap = max(gap, ROW_GAP_FLOOR)

    baselines = [top]
    for index in range(1, count):
        baselines.append(baselines[index - 1] - blocks[index - 1] - gap)
    return baselines


def _draw_fee_rows(pdf: canvas.Canvas, data: FeeReceiptData) -> None:
    government = list(data.government_heads)
    non_government = list(data.non_government_heads)
    row_count = max(len(government), len(non_government))
    if row_count == 0:
        return

    if row_count > len(FEE_ROW_Y):
        # More heads than the form's fixed rows: auto-shrink compact
        # fallback with uniform rows of smaller text.
        row_step = (FEE_ROW_Y[0] - FEE_TABLE_BOTTOM) / row_count
        fee_size = max(4.2, min(BASE_SIZE, row_step * 0.62))
        for copy in COPIES:
            _draw_fee_rows_compact(
                pdf, copy, government, non_government, row_count, row_step, fee_size,
            )
        return

    for copy in COPIES:
        # Measure first: how far below its baseline does each row's name
        # reach (either column)?  Name widths differ slightly per copy.
        blocks: list[float] = []
        column_plans: list[tuple[dict, float]] = []
        for index in range(row_count):
            wrap_gap = FIRST_ROW_WRAP_GAP if index == 0 else ROW_WRAP_GAP
            layout = _layout_first_fee_name if index == 0 else _layout_normal_fee_name
            row_plans: dict[str, tuple] = {}
            needed_lines = 1

            if index < len(government):
                head = government[index]
                amount_text = _money(head.amount)
                amount_width = pdfmetrics.stringWidth(amount_text, FONT_REGULAR, BASE_SIZE)
                # The Govt amount shares the row baseline, so reserve its
                # width before wrapping the name.
                name_max_width = max(
                    0,
                    copy['govt_amount_right'] - copy['govt_name_x'] - amount_width - 3,
                )
                size, lines = layout(head.name, name_max_width)
                row_plans['govt'] = (head, amount_text, size, lines, name_max_width)
                needed_lines = max(needed_lines, len(lines))

            if index < len(non_government):
                head = non_government[index]
                name_max_width = max(0, copy['name_divider'] - copy['nongovt_name_x'] - 1.5)
                size, lines = layout(head.name, name_max_width)
                row_plans['nongovt'] = (head, size, lines, name_max_width)
                needed_lines = max(needed_lines, len(lines))

            blocks.append((needed_lines - 1) * wrap_gap)
            column_plans.append((row_plans, wrap_gap))

        baselines = _plan_row_baselines(blocks)

        for index in range(row_count):
            y = baselines[index]
            row_plans, wrap_gap = column_plans[index]

            plan = row_plans.get('govt')
            if plan is not None:
                head, amount_text, name_size, name_lines, name_max_width = plan
                _draw_name_lines(
                    pdf, name_lines, name_size,
                    copy['govt_name_x'], y, name_max_width, wrap_gap,
                )
                _draw_fitted(
                    pdf, amount_text,
                    copy['govt_amount_right'], y,
                    max(0, copy['govt_end'] - copy['govt_name_x'] - 2),
                    FONT_REGULAR, BASE_SIZE,
                    min_size=5.0, right_align=True,
                )

            plan = row_plans.get('nongovt')
            if plan is not None:
                head, name_size, name_lines, name_max_width = plan
                pdf.setFont(FONT_REGULAR, BASE_SIZE)
                pdf.drawString(copy['serial_x'], y, str(index + 1))
                _draw_name_lines(
                    pdf, name_lines, name_size,
                    copy['nongovt_name_x'], y, name_max_width, wrap_gap,
                )
                _draw_fitted(
                    pdf, _money(head.amount),
                    copy['nongovt_amount_right'], y,
                    max(0, copy['nongovt_amount_right'] - copy['name_divider'] + 1),
                    FONT_REGULAR, BASE_SIZE,
                    min_size=5.0, right_align=True,
                )


def _draw_fee_rows_compact(
    pdf: canvas.Canvas,
    copy: dict,
    government: list,
    non_government: list,
    row_count: int,
    row_step: float,
    fee_size: float,
) -> None:
    """>10 heads: uniform rows of shrunk text, one line per name."""
    for index in range(row_count):
        y = FEE_ROW_Y[0] - (index * row_step)

        if index < len(government):
            head = government[index]
            amount_text = _money(head.amount)
            amount_width = pdfmetrics.stringWidth(amount_text, FONT_REGULAR, fee_size)
            govt_name_width = max(
                0, copy['govt_amount_right'] - copy['govt_name_x'] - amount_width - 3,
            )
            size = _fit_size(head.name, FONT_REGULAR, fee_size, govt_name_width, min_size=4.2)
            text = _truncate(head.name, FONT_REGULAR, size, govt_name_width)
            pdf.setFont(FONT_REGULAR, size)
            pdf.drawString(copy['govt_name_x'], y, text)
            _draw_fitted(
                pdf, _money(head.amount),
                copy['govt_amount_right'], y,
                max(0, copy['govt_end'] - copy['govt_name_x'] - 2),
                FONT_REGULAR, fee_size,
                min_size=5.0, right_align=True,
            )

        if index < len(non_government):
            head = non_government[index]
            name_max_width = max(0, copy['name_divider'] - copy['nongovt_name_x'] - 1.5)
            size = _fit_size(head.name, FONT_REGULAR, fee_size, name_max_width, min_size=4.2)
            text = _truncate(head.name, FONT_REGULAR, size, name_max_width)
            pdf.setFont(FONT_REGULAR, size)
            pdf.drawString(copy['nongovt_name_x'], y, text)
            _draw_fitted(
                pdf, _money(head.amount),
                copy['nongovt_amount_right'], y,
                max(0, copy['nongovt_amount_right'] - copy['name_divider'] + 1),
                FONT_REGULAR, fee_size,
                min_size=5.0, right_align=True,
            )


def _draw_totals(pdf: canvas.Canvas, data: FeeReceiptData) -> None:
    govt_total = sum((head.amount for head in data.government_heads), Decimal('0.00'))
    non_govt_total = sum((head.amount for head in data.non_government_heads), Decimal('0.00'))
    grand_total = data.amount_paid

    for copy in COPIES:
        # Total (A) - right aligned inside the Govt column.
        label_a_width = pdfmetrics.stringWidth('Total (A) > ', FONT_REGULAR, BASE_SIZE)
        _draw_fitted(
            pdf, _money(govt_total),
            copy['govt_amount_right'], 207.24,
            max(0, copy['govt_end'] - copy['left'] - label_a_width - 2),
            FONT_REGULAR, BASE_SIZE, min_size=6.0, right_align=True,
        )

        # Total (B) - right aligned inside the Non-Govt column.
        label_b_width = pdfmetrics.stringWidth('Total (B)> ', FONT_REGULAR, BASE_SIZE)
        _draw_fitted(
            pdf, _money(non_govt_total),
            copy['nongovt_amount_right'], 207.24,
            max(0, copy['nongovt_amount_right'] - copy['total_b_label_x'] - label_b_width - 2),
            FONT_REGULAR, BASE_SIZE, min_size=6.0, right_align=True,
        )

        # Grand total immediately after "Rs.".
        label_width = pdfmetrics.stringWidth(TOTAL_LABEL, FONT_BOLD, TOTAL_SIZE)
        amount_x = copy['grand_total_x'] + label_width + 8
        _draw_fitted(
            pdf, _money(grand_total), amount_x, 190.61,
            max(0, copy['right'] - amount_x - 3),
            FONT_BOLD, TOTAL_SIZE, min_size=6.0,
        )

        # Amount in words, wrapped into the large "In words" area.
        words_x = copy['in_words_x'] + pdfmetrics.stringWidth(f'{IN_WORDS_LABEL} ', FONT_REGULAR, BASE_SIZE)
        words_width = max(0, copy['right'] - words_x - 4)
        words = amount_in_words(grand_total)
        words_size = BASE_SIZE
        words_lines: list[str] = []
        for size in _descending_sizes(BASE_SIZE, 5.5):
            candidate = _wrap_text(words, FONT_REGULAR, size, words_width, max_lines=3)
            if candidate and all(
                pdfmetrics.stringWidth(line, FONT_REGULAR, size) <= words_width for line in candidate
            ):
                words_lines = candidate
                words_size = size
                break
        if not words_lines:
            words_lines = _wrap_text(words, FONT_REGULAR, 5.5, words_width, max_lines=3)
            words_size = 5.5
        pdf.setFont(FONT_REGULAR, words_size)
        for offset, line in enumerate(words_lines[:3]):
            pdf.drawString(words_x, 174.76 - (offset * 8.6), _truncate(line, FONT_REGULAR, words_size, words_width))


def generate_fee_receipt_pdf(data: FeeReceiptData) -> bytes:
    """Render the three-copy A4 landscape receipt and return PDF bytes."""
    _register_fonts()

    buffer = io.BytesIO()
    pdf = canvas.Canvas(
        buffer,
        pagesize=PAGE_SIZE,
        pageCompression=1,
        invariant=1,
    )
    pdf.setTitle(f'Official Fee Receipt - {data.receipt_no}')
    pdf.setAuthor('Government College of Engineering, Kolhapur')
    pdf.setSubject('Official institutional fee receipt')
    pdf.setCreator('GCOEK MIS')

    _draw_static_furniture(pdf)
    _draw_fields(pdf, data)

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Django adapter
# ---------------------------------------------------------------------------

def _student_address(student) -> str:
    """Permanent address first, then correspondence; comma-joined non-empty parts."""
    addresses = list(student.addresses.all())
    address = next(
        (a for a in addresses if a.address_type == 'PERMANENT'),
        None,
    )
    if address is None:
        address = next(
            (a for a in addresses if a.address_type == 'CORRESPONDENCE'),
            None,
        )
    if address is None:
        return ''

    parts = [
        address.address_line_1,
        address.address_line_2,
        address.address_line_3,
        address.village,
        address.taluka,
        address.district,
        address.state,
        address.pincode,
    ]
    cleaned: list[str] = []
    seen: set[str] = set()
    for part in parts:
        value = (part or '').strip().strip(',')
        key = value.lower()
        if value and key not in seen:
            cleaned.append(value)
            seen.add(key)
    return ', '.join(cleaned)


def _student_mobiles(student) -> tuple[str, str]:
    try:
        personal = student.personal_details
    except Exception:
        personal = None
    student_mobile = (getattr(personal, 'student_mobile', '') or '').strip() if personal else ''

    guardians = list(student.guardians.all())
    primary = next((g for g in guardians if g.is_primary), guardians[0] if guardians else None)
    guardian_mobile = (getattr(primary, 'mobile', '') or '').strip() if primary else ''

    if not student_mobile and guardian_mobile:
        return guardian_mobile, ''
    if guardian_mobile == student_mobile:
        guardian_mobile = ''
    return student_mobile, guardian_mobile


def _current_branch(student) -> str:
    enrollment = (
        student.enrollments.filter(is_current=True)
        .select_related('department')
        .first()
    )
    if enrollment is None:
        enrollment = (
            student.enrollments.select_related('department')
            .order_by('-academic_year__start_date', '-created_at')
            .first()
        )
    if enrollment and enrollment.department:
        return enrollment.department.code or enrollment.department.name
    return ''


def _fee_breakdown(ledger) -> dict:
    snapshot = getattr(ledger, 'fee_snapshot', None)
    if isinstance(snapshot, dict) and snapshot:
        return snapshot

    # Legacy receipt path: same fallback as PaymentLedgerSerializer.
    try:
        from .models import StudentFeeAssessment

        assessment = (
            StudentFeeAssessment.objects.filter(
                student_id=ledger.student_id,
                academic_year_id=ledger.academic_year_id,
            )
            .order_by('-updated_at')
            .first()
        )
        if assessment and isinstance(assessment.fee_breakdown, dict):
            return assessment.fee_breakdown
    except Exception:
        pass
    return {}


def _fee_types(ledger, breakdown: dict) -> dict:
    snapshot = getattr(ledger, 'fee_types_snapshot', None)
    if isinstance(snapshot, dict) and snapshot:
        return snapshot

    # Legacy receipt: immutable snapshot was not captured.  Resolve against
    # the fee-head configuration for that year, exactly like the serializer.
    try:
        from .models import PaymentLedger

        return PaymentLedger.build_head_types_map(ledger.academic_year, breakdown)
    except Exception:
        return {}


#: Snapshot keys arrive in Postgres jsonb order (length, then byte-wise), not
#: in the fee desk's configured sequence, so each column is re-sorted using the
#: FeeHead ``display_order`` for the ledger's academic year.  Heads unknown to
#: that configuration share the sentinel rank and keep their snapshot order.
_UNRANKED_HEAD = 10_000


def _display_order_map(ledger) -> dict[str, int]:
    """FeeHead ``display_order`` keyed by lowercased head name for that year.

    Heads may be configured per program, so the same name can appear more than
    once; the lowest configured order wins (deterministic regardless of query
    order).  Filtering by year also keeps heads with identical names across
    years from interfering.
    """
    try:
        from .models import FeeHead

        orders: dict[str, int] = {}
        for head in FeeHead.objects.filter(
            academic_year=ledger.academic_year,
        ).order_by('display_order', 'name'):
            orders.setdefault(head.name.lower(), head.display_order)
        return orders
    except Exception:
        return {}


def build_receipt_data(ledger) -> FeeReceiptData:
    """Assemble the immutable receipt payload from a PaymentLedger."""
    student = ledger.student
    name = (student.display_name or f'{student.first_name} {student.last_name}').strip()
    student_mobile, guardian_mobile = _student_mobiles(student)

    breakdown = _fee_breakdown(ledger)
    if not breakdown:
        breakdown = {'Fee (as assessed)': ledger.amount_paid}

    types = _fee_types(ledger, breakdown)
    government: list[ReceiptHead] = []
    non_government: list[ReceiptHead] = []

    for head_name, raw_amount in breakdown.items():
        amount = _as_decimal(raw_amount)
        fee_type = types.get(head_name)
        if fee_type is None:
            fee_type = next(
                (value for key, value in types.items() if key.lower() == head_name.lower()),
                'INSTITUTE',
            )
        head = ReceiptHead(name=str(head_name), amount=amount)
        if fee_type == 'GOVERNMENT':
            government.append(head)
        else:
            non_government.append(head)

    # Both columns must read in the fee desk's configured sequence:
    # Government side and Non-Government side each ranked on their own.
    display_order = _display_order_map(ledger)
    government.sort(
        key=lambda head: display_order.get(head.name.lower(), _UNRANKED_HEAD),
    )
    non_government.sort(
        key=lambda head: display_order.get(head.name.lower(), _UNRANKED_HEAD),
    )

    return FeeReceiptData(
        student_name=name,
        address=_student_address(student),
        student_mobile=student_mobile,
        guardian_mobile=guardian_mobile,
        branch=_current_branch(student),
        receipt_no=ledger.receipt_no,
        payment_date=ledger.payment_date,
        government_heads=government,
        non_government_heads=non_government,
        amount_paid=_as_decimal(ledger.amount_paid),
    )
