"""
Curriculum domain services: scheme resolution helpers.

- resolve_applicable_scheme(program, academic_year): published scheme whose
  effective range covers the admission year; falls back to latest published
  for the program.
- get_student_scheme(student): current enrollment's scheme (student stays in
  their entry scheme per CONTEXT Sec 9), else resolve from enrollment.
"""
from apps.curriculum.models import Scheme


def _in_range(scheme, year_code):
    from_code = scheme.effective_from_year.code if scheme.effective_from_year else ''
    to_code = scheme.effective_to_year.code if scheme.effective_to_year else None
    return year_code >= from_code and (to_code is None or year_code <= to_code)


def resolve_applicable_scheme(program, academic_year):
    if academic_year is None:
        return None
    base = Scheme.objects.filter(status=Scheme.Status.PUBLISHED).select_related(
        'effective_from_year', 'effective_to_year').order_by('-version')
    year_code = academic_year.code
    if program is not None:
        # 1. Program-specific scheme covering the year wins.
        for scheme in base.filter(program=program):
            if _in_range(scheme, year_code):
                return scheme
    # 2. Fall back to an all-programs scheme covering the year.
    for scheme in base.filter(program__isnull=True):
        if _in_range(scheme, year_code):
            return scheme
    # 3. Last resort: latest program scheme / latest all-program scheme.
    if program is not None:
        latest = base.filter(program=program).first()
        if latest:
            return latest
    return base.filter(program__isnull=True).first()


def get_student_scheme(student):
    enrollment = student.enrollments.filter(is_current=True).select_related(
        'scheme', 'program', 'academic_year').first()
    if enrollment is None:
        return None, {}
    if enrollment.scheme_id:
        return enrollment.scheme, {
            'min_theory': float(enrollment.scheme.min_theory_marks),
            'min_total': float(enrollment.scheme.min_total_marks),
            'max_backlogs': int(enrollment.scheme.max_backlogs_for_atkt),
        }
    scheme = resolve_applicable_scheme(enrollment.program, enrollment.academic_year)
    if scheme is None:
        return None, {}
    return scheme, {
        'min_theory': float(scheme.min_theory_marks),
        'min_total': float(scheme.min_total_marks),
        'max_backlogs': int(scheme.max_backlogs_for_atkt),
    }


def get_thresholds(student, defaults=(20.0, 40.0, 4)):
    """Return (min_theory, min_total, max_backlogs) for a student.

    Falls back to defaults when the student has no scheme configured.
    F-S6-006: logs a WARNING on fallback so misconfigured schemes are
    observable in production without silently accepting wrong rules.
    """
    import logging as _logging
    _logger = _logging.getLogger(__name__)
    try:
        _, rules = get_student_scheme(student)
        if rules:
            return rules['min_theory'], rules['min_total'], rules['max_backlogs']
    except Exception as _exc:
        _logger.warning(
            'get_thresholds: exception resolving scheme for student %s (%s); '
            'falling back to defaults %s. Error: %s',
            getattr(student, 'id', '?'),
            getattr(student, 'display_name', '?'),
            defaults,
            _exc,
        )
    _logger.warning(
        'get_thresholds: no scheme found for student %s (%s); '
        'using defaults %s. Assign a scheme to avoid this.',
        getattr(student, 'id', '?'),
        getattr(student, 'display_name', '?'),
        defaults,
    )
    return defaults


def ensure_assessment_components(scheme_subject):
    """Auto-create legacy split rows from the Subject master's exam scheme.

    The UI no longer asks for splits: theory subjects get
    THEORY_FA (CA + MSE combined) + THEORY_SA (ESE); laboratory subjects
    get PRACTICAL_FA (Practical CA) + PRACTICAL_SA (Practical ESE).
    Idempotent — existing rows are updated, never duplicated. Returns the
    number of component rows present afterwards (0 when the subject has
    no complete exam scheme, e.g. legacy code+title-only subjects).
    """
    from apps.curriculum.models import SchemeSubjectAssessmentComponent as Comp

    subject = scheme_subject.subject
    wanted = {}
    if subject.is_lab:
        if subject.practical_ca_max_marks is not None and subject.practical_ese_max_marks is not None:
            wanted = {
                Comp.ComponentType.PRACTICAL_FA: subject.practical_ca_max_marks,
                Comp.ComponentType.PRACTICAL_SA: subject.practical_ese_max_marks,
            }
    elif subject.theory_total is not None:
        wanted = {
            Comp.ComponentType.THEORY_FA: (
                float(subject.ca_max_marks) + float(subject.mse_max_marks)),
            Comp.ComponentType.THEORY_SA: subject.ese_max_marks,
        }
    elif subject.practical_total is not None:
        wanted = {
            Comp.ComponentType.PRACTICAL_FA: subject.practical_ca_max_marks,
            Comp.ComponentType.PRACTICAL_SA: subject.practical_ese_max_marks,
        }
    for order, (ctype, max_marks) in enumerate(wanted.items()):
        Comp.objects.update_or_create(
            scheme_subject=scheme_subject, component_type=ctype,
            defaults={'maximum_marks': max_marks, 'minimum_marks': 0,
                      'display_order': order})
    return scheme_subject.assessment_components.count()
