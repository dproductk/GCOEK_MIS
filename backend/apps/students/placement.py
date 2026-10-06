"""Admission placement formula (single source of truth, never edited per-student).

Inputs:
- admission_year: starting year of the admission academic year (2025 for 2025-26)
- admission_type: FY or DSE
- current_year: starting year of the current academic year (2026 for 2026-27)
- term: ODD (Jul-Dec) or EVEN (Jan-May; still belongs to the starting year,
  e.g. Feb 2027 is 2026-27 so current_year=2026)

Formulas:
    elapsed = current_year - admission_year
    FY:  base_sem = elapsed * 2 + 1
    DSE: base_sem = elapsed * 2 + 3
    EVEN term: semester = base_sem + 1, else semester = base_sem
    year = ceil(semester / 2)
    semester > 8 → Graduated | elapsed < 0 → Not yet admitted

Computed once per import; HOD confirms or corrects the suggestion
(correction overwrites the unconfirmed suggestion). Detentions are tracked
via Student.repeat_count and HOD placement, never by editing this formula.
"""
import math


class FutureAdmissionError(ValueError):
    """Raised when the admission year lies after the current academic year."""


FY = 'FY'
DSE = 'DSE'


def year_start(code):
    """Starting year int from an academic-year code like '2026-27'."""
    try:
        return int(str(code).split('-')[0])
    except (ValueError, IndexError, AttributeError):
        raise ValueError('Unparseable academic year code %r.' % (code,))


def suggest_semester(admission_year_start, admission_type, current_year_start, term):
    """Return (semester, year_level, placement_status)."""
    elapsed = int(current_year_start) - int(admission_year_start)
    if elapsed < 0:
        raise FutureAdmissionError(
            'Admission year %s is after current academic year %s.' % (
                admission_year_start, current_year_start)
        )
    base_sem = elapsed * 2 + (3 if str(admission_type).upper() == DSE else 1)
    semester = base_sem + (1 if str(term).upper() == 'EVEN' else 0)
    if semester > 8:
        return semester, math.ceil(semester / 2), 'GRADUATED'
    semester = max(semester, 1)
    return semester, math.ceil(semester / 2), 'STUDYING'
