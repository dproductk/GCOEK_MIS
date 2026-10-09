import os, sys, django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gceok_core.settings')
django.setup()

from django.conf import settings as _settings
if not _settings.DEBUG:
    print('ERROR: This script is for development only. Set DEBUG=True to use it.')
    sys.exit(1)
from datetime import date
from django.db import transaction
from apps.academic_structure.models import AcademicYear
from apps.curriculum.models import Scheme, Subject, SchemeSubject
from apps.curriculum.services import ensure_assessment_components, resolve_applicable_scheme

with transaction.atomic():
    years = [
        ('2023-24', 'Academic Year 2023-2024', date(2023, 7, 1), date(2024, 6, 30)),
        ('2024-25', 'Academic Year 2024-2025', date(2024, 7, 1), date(2025, 6, 30)),
        ('2025-26', 'Academic Year 2025-2026', date(2025, 7, 1), date(2026, 6, 30)),
    ]
    for code, name, s, e in years:
        y, created = AcademicYear.objects.get_or_create(
            code=code, defaults={'name': name, 'start_date': s, 'end_date': e, 'is_current': False})
        updated = []
        if y.start_date != s: y.start_date = s; updated.append('start_date')
        if y.end_date != e: y.end_date = e; updated.append('end_date')
        if code != '2026-27' and y.is_current: y.is_current = False; updated.append('is_current')
        if updated: y.save()
        print(f"YEAR {code} created={created} fixed={updated} current={y.is_current}")

    y2324 = AcademicYear.objects.get(code='2023-24')
    scheme = Scheme.objects.get(code='G', version=1)
    print(f"SCHEME before: {scheme.code} v{scheme.version} status={scheme.status} from={scheme.effective_from_year.code}")
    scheme.effective_from_year = y2324
    scheme.effective_to_year = None
    scheme.name = 'G Scheme'
    scheme.min_theory_marks = 20.0
    scheme.min_total_marks = 40.0
    scheme.max_backlogs_for_atkt = 4
    scheme.save()
    print(f"SCHEME range: from=2023-24 to=None (covers all years incl. 26-27)")

    # One subject per semester so the scheme can publish (API requires sems 1-8).
    # Sem 7 uses the real ENTC subjects; others are generic placeholders with full exam scheme.
    placeholders = [
        (2, 'G201', 'G Scheme Semester 2 Subject'),
        (3, 'G301', 'G Scheme Semester 3 Subject'),
        (4, 'G401', 'G Scheme Semester 4 Subject'),
        (5, 'G501', 'G Scheme Semester 5 Subject'),
        (6, 'G601', 'G Scheme Semester 6 Subject'),
        (8, 'G801', 'G Scheme Project Work'),
    ]
    for sem, code, title in placeholders:
        subj, _ = Subject.objects.get_or_create(
            code=code, defaults={'title': title, 'course_category': 'PCC',
                                 'lecture_hours': 3, 'ca_max_marks': 20,
                                 'mse_max_marks': 20, 'ese_max_marks': 60,
                                 'credits': 3, 'is_active': True})
        subj.title = title; subj.course_category = 'PCC'; subj.lecture_hours = 3
        subj.ca_max_marks = 20; subj.mse_max_marks = 20; subj.ese_max_marks = 60
        subj.credits = 3; subj.is_active = True; subj.save()
        ss, created = SchemeSubject.objects.get_or_create(
            scheme=scheme, semester_number=sem, course_code=code,
            defaults={'subject': subj, 'credits': 3, 'total_marks': 100, 'display_order': 1})
        ss.subject = subj; ss.credits = 3; ss.total_marks = 100; ss.save()
        n = ensure_assessment_components(ss)
        print(f"SEM {sem}: {code} scheme_link_created={created} components={n}")

    # Link real ENTC subjects into Sem 7
    for sem, code in [(7, 'ETC301'), (7, 'ETC302')]:
        subj = Subject.objects.get(code=code)
        ss, created = SchemeSubject.objects.get_or_create(
            scheme=scheme, semester_number=sem, course_code=code,
            defaults={'subject': subj, 'credits': 3, 'total_marks': 100, 'display_order': 1})
        ss.subject = subj; ss.credits = 3; ss.total_marks = 100; ss.save()
        n = ensure_assessment_components(ss)
        print(f"SEM {sem}: {code} scheme_link_created={created} components={n}")

    # Ensure sem-1 row also has components
    for ss in SchemeSubject.objects.filter(scheme=scheme):
        ensure_assessment_components(ss)

    # Publish (direct, test-data setup bypasses the API guard — content already satisfies it)
    scheme.status = Scheme.Status.PUBLISHED
    scheme.save(update_fields=['status', 'updated_at'])
    print(f"SCHEME published: {scheme.code} v{scheme.version}")

print("=== RESOLUTION CHECK ===")
for code in ['2023-24', '2024-25', '2025-26', '2026-27']:
    y = AcademicYear.objects.get(code=code)
    s = resolve_applicable_scheme(None, y)
    print(f"{code} -> {s.code if s else None} v{s.version if s else ''} ({s.status if s else ''})")
print("DONE")
