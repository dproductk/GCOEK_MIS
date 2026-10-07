"""
Admissions Ingestion and Validation Engine.

Implements CONTEXT.md Sec 13/15/16 + DATABASE_ARCHITECTURE_V2.md Sec 8
+ ARCHITECTURE.md Sec 12/15/19/20/21/22:

Pipeline: Upload → ImportBatch → Staging Rows → Validation →
Cleaning/Normalization → Matching → Preview → Final Import →
Student + Enrollment + Login (per Sec 13).

Key contracts:
- Raw source preserved unchanged (raw_data); cleaned values in normalized_data.
- Department mapping is data-driven via Department.choice_code (never hard-coded).
- Identity matching precedence: Application ID > Enrollment No > board refs.
  Conflicts never auto-merge → CONFLICT for manual review.
- Login per Sec 13: username = enrollment_no if available else application_id;
  initial password = same identifier; must_change_password=True.
  Password is only set on account creation, never reset on re-import.
- Final import is idempotent + retry-safe: only VALID rows imported,
  per-row transactions, PARTIALLY_COMPLETED on partial failure.
"""
import csv
import datetime
import hashlib
import io
import re
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from apps.academic_structure.models import (
    AcademicContext, AcademicYear, Department, Division, Program, Semester,
)
from apps.admissions.models import ImportBatch, ImportRow, StudentAdmission
from apps.authentication.models import Role, RoleAssignment, User
from apps.students.models import (
    Student,
    StudentAddress,
    StudentEnrollment,
    StudentGuardian,
    StudentPersonalDetail,
)

MAX_IMPORT_BYTES = 10 * 1024 * 1024  # 10 MB, mirrors FILE_UPLOAD_MAX_MEMORY_SIZE
ALLOWED_EXTENSIONS = ('.xls', '.xlsx', '.csv')

ALLOWED_CATEGORIES = {
    'OPEN', 'OBC', 'SC', 'ST', 'VJ', 'NT-B', 'NT-C', 'NT-D',
    'SBC', 'SEBC', 'EWS', 'TFWS', 'PWD', 'DEF', 'ORPHAN',
    # Legacy values already present in older files / staging rows.
    'NT', 'NT-A', 'GENERAL', 'DT/VJ', 'VJ/DT',
}

# Spelling variants seen in government files, mapped to canonical form.
CATEGORY_ALIASES = {
    'DT-VJ': 'DT/VJ',
    'VJ-DT': 'VJ/DT',
    'NT-1': 'NT-B',
    'NT-2': 'NT-C',
    'NT-3': 'NT-D',
    'NT1': 'NT-B',
    'NT2': 'NT-C',
    'NT3': 'NT-D',
    'NTA': 'NT-A',
    'NTB': 'NT-B',
    'NTC': 'NT-C',
    'NTD': 'NT-D',
    'DEFENCE': 'DEF',
    'PH': 'PWD',
    'PWD-BLIND': 'PWD',
}


def normalize_category(raw):
    """Normalize a government category value for validation.

    Government sheets carry footnote markers ('SEBC$', 'OBC$#') and
    descriptive forms ('NT 2 (NT-C)'). This strips footnote symbols,
    prefers the parenthetical canonical code when present, then applies
    spacing/hyphen cleanup and alias mapping. Returns canonical upper-case.
    """
    text = (raw or '').strip().upper()
    paren = re.search(r'\(([^)]+)\)', text)
    if paren:
        # 'NT 2 (NT-C)' → trust the parenthetical canonical code, but only
        # if it is a real category ('NT(B)' falls through to full parsing).
        inner = re.sub(r'\s*([/-])\s*', r'\1', paren.group(1).strip())
        inner = CATEGORY_ALIASES.get(inner, inner)
        if inner in ALLOWED_CATEGORIES:
            return inner
    text = text.rstrip('/$#').strip()
    text = text.replace('(', '-').replace(')', '')
    text = re.sub(r'\s*([/-])\s*', r'\1', text)
    text = re.sub(r'\s+', '', text)
    return CATEGORY_ALIASES.get(text, text)


def normalize_choice_code(code):
    """Normalize a choice code for comparison.

    Government files vary: FY codes may carry a leading zero ('0603626310'
    vs '603626310') and DSE/TFWS codes carry a 'T' suffix ('0603626311T').
    Comparison strips leading zeros but preserves the rest (incl. suffix).
    """
    text = (code or '').strip().upper()
    stripped = text.lstrip('0')
    return stripped or text


def normalize_program_code(code):
    """Normalize a university program code for comparison.

    University program codes are short numeric identifiers (e.g. '11242'
    for CSE). Comparison strips whitespace and leading zeros so '011242'
    and '11242' resolve to the same program. Empty input returns ''.
    """
    text = (code or '').strip().upper()
    if not text:
        return ''
    stripped = text.lstrip('0')
    return stripped or text


def build_dept_choice_map(departments):
    """Map normalized primary + alternate choice codes to departments."""
    mapping = {}
    for dept in departments:
        primary = normalize_choice_code(getattr(dept, 'choice_code', ''))
        if primary:
            mapping.setdefault(primary, dept)
        for alt in (getattr(dept, 'alternate_choice_codes', None) or []):
            norm = normalize_choice_code(alt)
            if norm:
                mapping.setdefault(norm, dept)
    return mapping


def build_dept_program_map(programs):
    """Map normalized university program codes to departments.

    Data-driven: reads Program.university_program_code (never hard-coded).
    Each program belongs to a department, so the map resolves a program
    code directly to its owning department.
    """
    mapping = {}
    for prog in programs:
        norm = normalize_program_code(getattr(prog, 'university_program_code', ''))
        if norm:
            dept = getattr(prog, 'department', None)
            if dept is not None:
                mapping.setdefault(norm, dept)
    return mapping
ALLOWED_GENDERS = {'MALE', 'FEMALE', 'OTHER'}

# Header aliases (case-insensitive) for the 59-column government file.
_APP_ID_KEYS = ('application id', 'application no', 'candidate id')
_ENR_KEYS = (
    'enrollment no', 'enrolment no', 'enrollment no.', 'enrolment no.',
    'enrollment number', 'enrolment number', 'prn', 'university prn',
)
_CHOICE_KEYS = ('choice code', 'choicecode')
_PROGRAM_KEYS = (
    'program code', 'programme code', 'programcode', 'programmecode',
    'university program code', 'university programme code',
    'program_code', 'programme_code', 'branch code',
)
_COURSE_KEYS = ('course name', 'course', 'branch', 'allotted course')
_NAME_KEYS = ('candidate name', 'student name', 'name', 'students full name', 'student full name', 'full name')
_MOBILE_KEYS = ('mobile no', 'mobile', 'contact', 'mobile number')
_EMAIL_KEYS = ('e-mail id', 'email id', 'email', 'e-mail')
_DOB_KEYS = ('dob', 'date of birth')
_GENDER_KEYS = ('gender', 'sex')
_CATEGORY_KEYS = ('category', 'reservation category')
_ADM_DATE_KEYS = ('admission date',)
_REP_DATE_KEYS = ('reported date',)
_ADMITTED_YEAR_KEYS = (
    'student admitted year', 'admitted year', 'admission year', 'year of admission',
)
_FILE_ACADEMIC_YEAR_KEYS = ('academic year', 'academic_year', 'acad year')


def _lookup(row, *aliases):
    """Case-insensitive column lookup; returns stripped string."""
    lowered = {str(k).strip().lower(): v for k, v in row.items()}
    for alias in aliases:
        if alias in lowered:
            val = lowered[alias]
            return '' if val is None else str(val).strip()
    return ''


def extract_table_rows(content_bytes, file_name):
    """
    Extract headers and row dicts from Excel/HTML table/CSV.
    Handles legacy OLE .xls (xlrd), HTML table-formatted .xls,
    modern .xlsx (openpyxl), and .csv.
    """
    _head = (content_bytes or b'')[:8]
    _is_ole = _head.startswith(b'\xd0\xcf\x11\xe0')
    _is_zip = _head.startswith(b'PK')

    # 0. Legacy OLE .xls straight to xlrd: binary must never reach the
    # CSV sniffer below (decoded ZIP/OLE garbage can look like CSV).
    if _is_ole:
        try:
            import xlrd
            book = xlrd.open_workbook(file_contents=content_bytes)
            best_headers, best_rows = [], []
            for sheet in book.sheets():
                if sheet.nrows == 0:
                    continue
                headers = [
                    str(sheet.cell_value(0, c) or '').strip()
                    for c in range(sheet.ncols)
                ]
                headers = [h for h in headers if h]
                if not headers:
                    continue
                data_rows = []
                for r in range(1, sheet.nrows):
                    if all(
                        sheet.cell_value(r, c) in (None, '')
                        or str(sheet.cell_value(r, c)).strip() == ''
                        for c in range(sheet.ncols)
                    ):
                        continue
                    row_dict = {}
                    for idx, h in enumerate(headers):
                        if idx >= sheet.ncols:
                            row_dict[h] = ''
                            continue
                        ctype = sheet.cell_type(r, idx)
                        val = sheet.cell_value(r, idx)
                        if ctype == xlrd.XL_CELL_DATE:
                            try:
                                val = xlrd.xldate_as_datetime(val, book.datemode).date().isoformat()
                            except Exception:
                                val = str(val or '').strip()
                        elif isinstance(val, float) and val.is_integer():
                            val = str(int(val))
                        else:
                            val = str(val or '').strip()
                        row_dict[h] = val
                    data_rows.append(row_dict)
                if len(data_rows) > len(best_rows) or (not best_headers and headers):
                    best_headers, best_rows = headers, data_rows
            if best_headers or best_rows:
                return best_headers, best_rows
        except Exception:
            pass
        return [], []

    # 1. Check if HTML table (common for DTE government exports)
    try:
        text_sample = content_bytes[:2048].decode('utf-8', errors='ignore')
        if '<table' in text_sample.lower() or '<tr' in text_sample.lower():
            full_text = content_bytes.decode('utf-8', errors='ignore')
            headers = [
                re.sub(r'<[^>]+>', '', h).strip()
                for h in re.findall(r'<th[^>]*>(.*?)</th>', full_text, re.I | re.S)
            ]
            trs = re.findall(r'<tr[^>]*>(.*?)</tr>', full_text, re.I | re.S)
            data_rows = []
            for tr in trs[1:]:
                tds = [
                    re.sub(r'<[^>]+>', '', td).strip()
                    for td in re.findall(r'<td[^>]*>(.*?)</td>', tr, re.I | re.S)
                ]
                if len(tds) == len(headers):
                    data_rows.append(dict(zip(headers, tds)))
                elif len(tds) > 0:
                    row = {headers[i]: tds[i] for i in range(min(len(headers), len(tds)))}
                    data_rows.append(row)
            return headers, data_rows
    except Exception:
        pass

    # 2. Try CSV (text uploads only — never binary workbooks)
    if not _is_zip:
        try:
            full_text = content_bytes.decode('utf-8', errors='ignore')
            reader = csv.DictReader(io.StringIO(full_text))
            rows = list(reader)
            if rows and len(reader.fieldnames) > 5:
                return reader.fieldnames, rows
        except Exception:
            pass

    # 3. Try openpyxl (scan every sheet: uploads sometimes open with an
    # empty cover sheet active while the roster sits in Sheet2).
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(content_bytes), data_only=True)
        best_headers, best_rows = [], []
        for sheet in wb.worksheets:
            try:
                all_rows = list(sheet.iter_rows(values_only=True))
            except Exception:
                continue
            if not all_rows:
                continue
            headers = [str(h).strip() for h in all_rows[0] if h is not None]
            if not headers:
                continue
            data_rows = []
            for r in all_rows[1:]:
                if r is None or all(v is None or str(v).strip() == '' for v in r):
                    continue
                row_dict = {}
                for idx, h in enumerate(headers):
                    val = r[idx] if idx < len(r) else ''
                    row_dict[h] = str(val or '').strip()
                data_rows.append(row_dict)
            # Prefer the sheet with the most student rows; keep headers even
            # when a sheet has none so callers can report "headers, no rows".
            if len(data_rows) > len(best_rows) or (not best_headers and headers):
                best_headers, best_rows = headers, data_rows
        if best_headers or best_rows:
            return best_headers, best_rows
    except Exception:
        pass

    return [], []


def normalize_mobile(raw):
    """Return (10-digit mobile or '', error or None)."""
    if not raw:
        return '', None
    digits = re.sub(r'\D', '', str(raw))
    # Allow +91 / 91 country prefix.
    if len(digits) == 12 and digits.startswith('91'):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith('0'):
        digits = digits[1:]
    if len(digits) != 10 or not digits.startswith(('6', '7', '8', '9')):
        return '', f"Invalid mobile number '{raw}'."
    return digits, None


def parse_date_flexible(raw):
    """Return date or None. Accepts common govt formats + Excel datetimes.

    Excel/openpyxl date cells stringify as 'YYYY-MM-DD HH:MM:SS'
    (e.g. '2005-10-09 00:00:00'), which must validate as the calendar
    date, not INVALID.
    """
    if raw is None or raw == '':
        return None
    if isinstance(raw, datetime.datetime):
        return raw.date()
    if isinstance(raw, datetime.date):
        return raw
    text = str(raw).strip()
    if not text:
        return None
    # ISO calendar date and datetime ('YYYY-MM-DD[ HH:MM[:SS]]', with T or space).
    # The [:10] fast-path only applies when the 11th char is a date/time
    # separator, so trailing junk like '2005-10-09XYZ' still fails.
    if len(text) >= 10 and (len(text) == 10 or text[10] in (' ', 'T')):
        try:
            return datetime.date.fromisoformat(text[:10])
        except ValueError:
            pass
    try:
        return datetime.datetime.fromisoformat(text).date()
    except ValueError:
        pass
    for fmt in (
        '%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%d.%m.%Y', '%d/%m/%y',
        '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%dT%H:%M:%S',
        '%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M',
        '%d-%m-%Y %H:%M:%S', '%d-%m-%Y %H:%M',
        '%d.%m.%Y %H:%M:%S', '%d.%m.%Y %H:%M',
    ):
        try:
            return datetime.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _parse_file_year(raw):
    """Starting-year int from file text like '2023-24', '2023-2024' or '2023'.

    Returns None for anything else — including wide spans like '2017-24',
    which indicate unreliable source data rather than a real admission
    year (a valid academic year spans at most one year boundary).
    """
    text = str(raw or '').strip()
    if not text:
        return None
    m = re.match(r'^((?:19|20)\d{2})\s*[-/]\s*(\d{2}|\d{4})$', text)
    if m:
        start = int(m.group(1))
        end_raw = m.group(2)
        end = int(end_raw) if len(end_raw) == 4 else (start // 100) * 100 + int(end_raw)
        if end < start:
            end += 100
        if 0 <= end - start <= 1 and 2000 <= start <= 2100:
            return start
        return None
    m = re.match(r'^((?:19|20)\d{2})$', text)
    if m:
        return int(m.group(1))
    return None


def normalize_gender(raw):
    text = str(raw or '').strip().upper()
    if text.startswith('M'):
        return 'MALE'
    if text.startswith('F'):
        return 'FEMALE'
    if text.startswith(('O', 'T')):
        return 'OTHER'
    return ''


def resolve_department(choice_code, course_name, dept_by_choice, departments, program_code='', dept_by_program=None):
    """Data-driven dept resolution: choice_code, else program_code, else course-name.

    Precedence: normalized choice_code → normalized university program_code
    (via Program.university_program_code) → course-name substring match.
    Never hard-codes department keywords or program numbers. Falls back to
    matching the course text against Department.name so legacy/test rows
    without a configured code still resolve; returns None when
    unresolvable (→ INVALID).
    """
    code = normalize_choice_code(choice_code)
    if code and code in dept_by_choice:
        return dept_by_choice[code], 'choice_code'
    prog = normalize_program_code(program_code)
    if prog and dept_by_program and prog in dept_by_program:
        return dept_by_program[prog], 'program_code'
    course = (course_name or '').strip().upper()
    if course:
        # Prefer longer names first (e.g. ETC before EE on substring match).
        for dept in sorted(departments, key=lambda d: -len(d.name)):
            dept_name = (dept.name or '').strip().upper()
            if dept_name and (dept_name in course or course in dept_name):
                return dept, 'course_name'
    return None, ''


def parse_annual_income(raw_val):
    if not raw_val:
        return None
    val_str = str(raw_val).replace('&gt;', '>').replace('&lt;', '<').strip()
    if '-' in val_str:
        parts = val_str.split('-')
        upper = re.sub(r'[^\d.]', '', parts[-1])
        try:
            return float(upper) if upper else None
        except ValueError:
            pass
    num_str = re.sub(r'[^\d.]', '', val_str)
    try:
        return float(num_str) if num_str else None
    except ValueError:
        return None


def stage_admission_file(file_bytes, file_name, academic_year, user, uploaded_file=None, admission_type=ImportBatch.AdmissionType.FIRST_YEAR):
    """
    Stage an uploaded file into ImportBatch and ImportRow entities.
    Performs validation + normalization + matching without touching core tables
    (except linking already-existing students for preview traceability).

    Re-uploading the same file never creates duplicates: rows matching an
    existing student are marked DUPLICATE/MATCHED, conflicts → CONFLICT.
    """
    if not file_bytes:
        raise ValueError('Empty file uploaded.')
    if len(file_bytes) > MAX_IMPORT_BYTES:
        raise ValueError('File exceeds 10 MB size limit.')
    ext = '.' + (file_name.rsplit('.', 1)[-1].lower() if '.' in file_name else '')
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError('Unsupported file type. Upload .xls, .xlsx or .csv only.')

    checksum = hashlib.sha256(file_bytes).hexdigest()
    headers, rows = extract_table_rows(file_bytes, file_name)

    if not rows:
        if headers:
            raise ValueError(
                'File %r has headers (%d columns) but no student rows. '
                'The sheet filter likely removed everything (e.g. filtering '
                "'Student Admitted Year' for a value the file does not contain) "
                'or the roster sits on another sheet. Open the file and check '
                'row count below the header.' % (file_name, len(headers)))
        raise ValueError('Unable to parse rows from file. Ensure it is a valid government candidate list.')

    # Admission year from the file itself ("Student Admitted Year" first,
    # then "Academic Year"), falling back to the AH-selected/current default.
    # The file wins only when it parses AND a matching AcademicYear is
    # configured; future years stay blocked by the guard below. The winning
    # source is recorded per-row in normalized_data for review.
    from collections import Counter
    admitted_votes, academic_votes = Counter(), Counter()
    for _row in rows:
        _admitted = _parse_file_year(_lookup(_row, *_ADMITTED_YEAR_KEYS))
        if _admitted is not None:
            admitted_votes[_admitted] += 1
        else:
            _acad = _parse_file_year(_lookup(_row, *_FILE_ACADEMIC_YEAR_KEYS))
            if _acad is not None:
                academic_votes[_acad] += 1
    _file_year = (
        admitted_votes.most_common(1)[0][0]
        if admitted_votes
        else (academic_votes.most_common(1)[0][0] if academic_votes else None)
    )
    _year_source = (
        'file:admitted-year'
        if admitted_votes
        else ('file:academic-year' if academic_votes else 'default')
    )
    batch_year = academic_year
    if _file_year is not None:
        _configured = None
        for _ay in AcademicYear.objects.all():
            try:
                from apps.students.placement import year_start as _ys
                if _ys(_ay.code) == _file_year:
                    _configured = _ay
                    break
            except ValueError:
                continue
        if _configured is not None:
            batch_year = _configured

    # Auto-detect DSY if not explicitly provided
    if admission_type == ImportBatch.AdmissionType.FIRST_YEAR:
        fn_upper = file_name.upper()
        if 'DSE' in fn_upper or 'DSY' in fn_upper or 'DIRECT SECOND' in fn_upper:
            admission_type = ImportBatch.AdmissionType.DIRECT_SECOND_YEAR

    # Block future-dated imports: admission year must not lie after the
    # current academic year.
    from apps.students.placement import FutureAdmissionError, year_start
    current_year = AcademicYear.objects.filter(is_current=True).first() or batch_year
    try:
        if year_start(batch_year.code) > year_start(current_year.code):
            raise ValueError(
                'This file belongs to future academic year %s; current year is %s. '
                'Future admissions cannot be imported yet.' % (
                    batch_year.code, current_year.code)
            )
    except FutureAdmissionError:
        raise
    except ValueError as e:
        if 'future academic year' in str(e):
            raise
    active_ctx = AcademicContext.objects.filter(is_active=True).first()
    current_term = active_ctx.term if active_ctx else 'ODD'

    # Placement suggestions computed once per import (same admission year
    # for every row — single-year files per ADR-009/018). Formula lives once
    # in apps.students.placement and is reused here, never reimplemented.
    # Both FY and DSE suggestions are computed so mixed FY/DSE rows
    # (row-level 'Student Admitted Semester == SEMESTER - 3') each get the
    # correct formula result: senior DSE uses elapsed*2+3, not hardcoded Sem 3.
    from apps.students.placement import DSE, suggest_semester
    batch_adm_type = DSE if admission_type == ImportBatch.AdmissionType.DIRECT_SECOND_YEAR else 'FY'
    try:
        suggested_sem, suggested_year, _placement = suggest_semester(
            year_start(batch_year.code), batch_adm_type,
            year_start(current_year.code), current_term)
        _dse_sem, _dse_year, _dse_place = suggest_semester(
            year_start(batch_year.code), DSE,
            year_start(current_year.code), current_term)
        _fy_sem, _fy_year, _fy_place = suggest_semester(
            year_start(batch_year.code), 'FY',
            year_start(current_year.code), current_term)
    except FutureAdmissionError:
        raise ValueError(
            'This file belongs to future academic year %s; current year is %s. '
            'Future admissions cannot be imported yet.' % (
                batch_year.code, current_year.code)
        )

    # Data-driven department maps (no hard-coded keywords anywhere).
    # Choice codes live on Department; university program codes live on
    # Program (Program.university_program_code → owning department).
    departments = list(Department.objects.all())
    dept_by_choice = build_dept_choice_map(departments)
    dept_by_program = build_dept_program_map(list(Program.objects.select_related('department').all()))

    # Existing identity maps for precedence matching (single queries, no N+1).
    app_map = dict(Student.objects.exclude(application_id__isnull=True).exclude(
        application_id='').values_list('application_id', 'id'))
    enr_map = dict(Student.objects.exclude(enrollment_no__isnull=True).exclude(
        enrollment_no='').values_list('enrollment_no', 'id'))

    with transaction.atomic():
        batch = ImportBatch.objects.create(
            file_name=file_name,
            file_checksum=checksum,
            file_size=len(file_bytes),
            academic_year=batch_year,
            admission_type=admission_type,
            status=ImportBatch.Status.VALIDATING,
            total_rows=len(rows),
            uploaded_by=user,
        )
        # Preserve original source file for proof/audit (SECURITY.md Sec 14).
        try:
            batch.source_file.save(file_name, ContentFile(file_bytes), save=True)
        except Exception:
            # Preservation failure must not lose checksum/size metadata.
            pass

        valid_count = invalid_count = duplicate_count = conflict_count = 0
        seen_apps, seen_enrs = set(), set()
        staged = []

        for idx, row in enumerate(rows, start=1):
            app_id = _lookup(row, *_APP_ID_KEYS)
            enr_no = _lookup(row, *_ENR_KEYS)
            choice_code = _lookup(row, *_CHOICE_KEYS)
            program_code = _lookup(row, *_PROGRAM_KEYS)
            course = _lookup(row, *_COURSE_KEYS)
            name = _lookup(row, *_NAME_KEYS)
            mobile_raw = _lookup(row, *_MOBILE_KEYS)
            email_raw = _lookup(row, *_EMAIL_KEYS)
            dob_raw = _lookup(row, *_DOB_KEYS)
            gender_raw = _lookup(row, *_GENDER_KEYS)
            category_raw = _lookup(row, *_CATEGORY_KEYS)

            errors = []

            # --- Required identifiers (at least one authoritative ID) ---
            if not app_id and not enr_no:
                errors.append('Missing mandatory Application ID / Enrollment No.')

            # --- Duplicate inside this batch (idempotency within upload) ---
            in_batch_dup = bool(
                (app_id and app_id in seen_apps)
                or (enr_no and enr_no in seen_enrs)
            )
            if app_id and app_id in seen_apps:
                errors.append(f'Application ID {app_id} appears multiple times in this batch.')
            if enr_no and enr_no in seen_enrs:
                errors.append(f'Enrollment No {enr_no} appears multiple times in this batch.')
            if app_id:
                seen_apps.add(app_id)
            if enr_no:
                seen_enrs.add(enr_no)

            if not name:
                errors.append('Missing mandatory Candidate Name.')

            # --- Cleaning / normalization (raw preserved untouched) ---
            mobile, mobile_err = normalize_mobile(mobile_raw)
            if mobile_err:
                errors.append(mobile_err)
            dob = parse_date_flexible(dob_raw)
            if dob_raw and dob is None:
                errors.append(f"Invalid DOB '{dob_raw}'. Expected DD/MM/YYYY.")
            gender = normalize_gender(gender_raw)
            if gender_raw and not gender:
                errors.append(f"Invalid gender '{gender_raw}'.")
            category = normalize_category(category_raw)
            if not category:
                errors.append('Missing mandatory Category.')
            elif category not in ALLOWED_CATEGORIES:
                errors.append(f"Invalid category '{category_raw}'.")
            email = email_raw.strip()
            if email and not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
                errors.append(f"Invalid email '{email_raw}'.")

            # --- Department mapping (data-driven): choice_code → program_code → course ---
            dept, match_method = resolve_department(
                choice_code, course, dept_by_choice, departments,
                program_code=program_code, dept_by_program=dept_by_program,
            )
            if dept is None:
                if choice_code and program_code:
                    errors.append(f"Unmapped Choice Code '{choice_code}' and Program Code '{program_code}'.")
                elif choice_code:
                    errors.append(f"Unmapped Choice Code '{choice_code}'.")
                elif program_code:
                    errors.append(f"Unmapped Program Code '{program_code}'.")
                else:
                    errors.append('Missing Choice Code / Program Code and course could not be mapped to a department.')

            # Per-row stream: whole-DSE files are all DSE; FY files may still
            # carry individual 'SEMESTER - 3' rows (lateral entry). Each row
            # gets its matching formula suggestion (FY vs DSE).
            _row_adm_sem_raw = _lookup(row, 'student admitted semester', 'admitted semester', 'admission semester')
            _row_is_dse_preview = (
                batch_adm_type == DSE
                or ('3' in (_row_adm_sem_raw or '') or 'III' in (_row_adm_sem_raw or '').upper())
            )
            _row_sug_sem = _dse_sem if _row_is_dse_preview else _fy_sem
            _row_sug_year = _dse_year if _row_is_dse_preview else _fy_year

            normalized = {
                'application_id': app_id,
                'enrollment_no': enr_no,
                'candidate_name': re.sub(r'\s+', ' ', name).strip(),
                'choice_code': choice_code.strip(),
                'program_code': program_code.strip(),
                'course': course.strip(),
                'department_code': dept.code if dept else '',
                'department_match': match_method,
                'admitted_year_raw': _lookup(row, *_ADMITTED_YEAR_KEYS) or _lookup(row, *_FILE_ACADEMIC_YEAR_KEYS),
                'admitted_year_source': _year_source,
                'mobile': mobile,
                'email': email,
                'dob': dob.isoformat() if dob else '',
                'gender': gender,
                'category': category,
                'admitted_semester': _row_adm_sem_raw,
                'caste': _lookup(row, 'cast', 'caste', 'sub caste', 'sub-caste'),
                'marital_status': _lookup(row, 'marital status'),
                'abc_id': _lookup(row, 'abc id', 'abc_id', 'academic bank of credits id'),
                'blood_group': _lookup(row, 'blood group', 'blood_group'),
                'admitted_category': _lookup(row, 'admitted_category', 'admitted category', 'seat type'),
                'suggested_semester': _row_sug_sem,
                'suggested_year': _row_sug_year,
                'board_refs': {
                    'ssc_seat_no': _lookup(row, 'ssc seat no'),
                    'hsc_seat_no': _lookup(row, 'hsc seat no'),
                    'diploma_seat_no': _lookup(row, 'diploma seat no', 'diploma seat number', 'diploma roll no'),
                    'diploma_board': _lookup(row, 'diploma board', 'diploma examining authority', 'msbte'),
                    'diploma_percentage': _lookup(row, 'diploma percentage', 'diploma aggregate percentage', 'diploma marks percentage', 'diploma total percentage'),
                    'qualifying_exam': _lookup(row, 'qualifying exam', 'qualifying examination') or ('Diploma' if admission_type == ImportBatch.AdmissionType.DIRECT_SECOND_YEAR else 'HSC'),
                    'cet_roll_no': _lookup(row, 'cet roll no'),
                    'jee_application_no': _lookup(row, 'jee application no'),
                },
            }

            # --- Identity matching: Application ID > Enrollment No ---
            # Board refs (SSC/HSC seat nos) have no Student column, so they are
            # preserved in normalized_data for manual review, not auto-matched.
            app_match = app_map.get(app_id) if app_id else None
            enr_match = enr_map.get(enr_no) if enr_no else None
            matched_uuid = None
            if in_batch_dup:
                matching_status = ImportRow.MatchingStatus.PENDING
                matching_detail = {'reason': 'Duplicate identifier inside this batch.'}
                status = ImportRow.ValidationStatus.DUPLICATE
            elif app_match and enr_match and app_match != enr_match:
                matching_status = ImportRow.MatchingStatus.CONFLICT
                matching_detail = {
                    'reason': 'Application ID and Enrollment No point to different students.',
                    'application_student_id': str(app_match),
                    'enrollment_student_id': str(enr_match),
                }
                status = ImportRow.ValidationStatus.CONFLICT
                errors.append('Conflicting identity match — requires manual review; never auto-merged.')
            elif app_match or enr_match:
                matched_uuid = app_match or enr_match
                matching_status = ImportRow.MatchingStatus.MATCHED
                matching_detail = {
                    'matched_via': 'application_id' if app_match else 'enrollment_no',
                    'student_id': str(matched_uuid),
                }
                status = ImportRow.ValidationStatus.DUPLICATE
                errors.append(
                    f"Already exists as a student; re-upload does not create a duplicate."
                )
            elif errors:
                matching_status = ImportRow.MatchingStatus.NO_MATCH
                matching_detail = {}
                status = ImportRow.ValidationStatus.INVALID
            else:
                matching_status = ImportRow.MatchingStatus.NO_MATCH
                matching_detail = {}
                status = ImportRow.ValidationStatus.VALID

            if status == ImportRow.ValidationStatus.VALID:
                valid_count += 1
            elif status == ImportRow.ValidationStatus.DUPLICATE:
                duplicate_count += 1
            elif status == ImportRow.ValidationStatus.CONFLICT:
                conflict_count += 1
            else:
                invalid_count += 1

            staged.append(ImportRow(
                batch=batch,
                row_number=idx,
                application_id=app_id,
                enrollment_no=enr_no,
                choice_code=choice_code.strip(),
                program_code=program_code.strip(),
                candidate_name=re.sub(r'\s+', ' ', name).strip(),
                allotted_course=course.strip(),
                raw_data=row,
                normalized_data=normalized,
                matching_status=matching_status,
                matching_detail=matching_detail,
                validation_status=status,
                validation_errors=errors,
                student_id=matched_uuid,
            ))

        ImportRow.objects.bulk_create(staged)

        batch.valid_rows = valid_count
        batch.invalid_rows = invalid_count
        batch.duplicate_rows = duplicate_count
        batch.conflict_rows = conflict_count
        batch.status = ImportBatch.Status.VALIDATED
        batch.summary_report = {
            'total': len(rows),
            'valid': valid_count,
            'invalid': invalid_count,
            'duplicate': duplicate_count,
            'conflict': conflict_count,
            'headers': headers,
        }
        batch.save()

    return batch


def _get_or_create_division(dept, academic_year, sem1):
    """Scoped Division A lookup for freshers; created if missing."""
    if not (dept and academic_year and sem1):
        return None
    div, _ = Division.objects.get_or_create(
        department=dept,
        academic_year=academic_year,
        semester=sem1,
        name='A',
        defaults={'seat_capacity': dept.seat_capacity or 60},
    )
    return div


def commit_import_batch(batch_id):
    """
    Commit all VALID rows into core records (Student + Enrollment + Login).

    Idempotent + retry-safe: only VALID rows are processed, each in its own
    transaction; IMPORTED/DUPLICATE/CONFLICT/INVALID rows are never re-created.
    Partial failure → PARTIALLY_COMPLETED with per-row import_error.
    """
    from django.db import transaction as _tx
    with _tx.atomic():
        try:
            batch = ImportBatch.objects.select_for_update().get(id=batch_id)
        except ImportBatch.DoesNotExist:
            raise ValueError('Batch not found.')
        # Idempotent repeat: an already-completed batch returns as-is so a
        # retried commit never errors and never duplicates students.
        if batch.status == ImportBatch.Status.COMPLETED:
            return batch
        # Fence concurrent workers: only one may hold IMPORTING at a time.
        if batch.status == ImportBatch.Status.IMPORTING:
            raise ValueError('Batch import already in progress. Please wait and refresh.')
        allowed = (
            ImportBatch.Status.VALIDATED,
            ImportBatch.Status.FAILED,
            ImportBatch.Status.PARTIALLY_COMPLETED,
        )
        if batch.status not in allowed:
            raise ValueError(f'Batch cannot be committed from status {batch.status}.')

        batch.status = ImportBatch.Status.IMPORTING
        batch.save(update_fields=['status'])

    # Only VALID rows proceed (CONTEXT.md Sec 15.6). IMPORTED rows stay done.
    valid_rows = list(batch.rows.filter(
        validation_status=ImportRow.ValidationStatus.VALID
    ).order_by('row_number'))

    try:
        role_student = Role.objects.get(codename='STUDENT')
    except Role.DoesNotExist:
        batch.status = ImportBatch.Status.FAILED
        batch.summary_report = {'error': 'STUDENT role not configured.'}
        batch.save(update_fields=['status', 'summary_report'])
        raise ValueError('STUDENT role not configured.')

    is_dsy = (batch.admission_type == ImportBatch.AdmissionType.DIRECT_SECOND_YEAR)
    # Placement from the admission formula (single source in
    # apps.students.placement, reused here — never reimplemented).
    # Both FY and DSE outcomes are computed so senior lateral-entry rows
    # land on the formula sem (e.g. 2023 DSE in 2024-25 EVEN -> Sem 6),
    # not hardcoded Sem 3. HOD confirms or corrects it later (Div A landing).
    from apps.students.placement import (
        DSE as _DSE,
        FutureAdmissionError as _FutureError,
        suggest_semester as _suggest,
        year_start as _ystart,
    )
    _current = AcademicYear.objects.filter(is_current=True).first() or batch.academic_year
    _ctx = AcademicContext.objects.filter(is_active=True).first()
    _term = _ctx.term if _ctx else 'ODD'
    try:
        _sem_no, _, _place = _suggest(
            _ystart(batch.academic_year.code),
            _DSE if is_dsy else 'FY',
            _ystart(_current.code), _term)
        _fy_no, _, _fy_place = _suggest(
            _ystart(batch.academic_year.code), 'FY',
            _ystart(_current.code), _term)
        _dse_no, _, _dse_place = _suggest(
            _ystart(batch.academic_year.code), _DSE,
            _ystart(_current.code), _term)
    except _FutureError:
        raise ValueError('Batch admission year is in the future; cannot commit.')
    if _place == 'GRADUATED':
        _sem_no = 8
    if _fy_place == 'GRADUATED':
        _fy_no = 8
    if _dse_place == 'GRADUATED':
        _dse_no = 8
    target_sem = (
        Semester.objects.filter(number=_sem_no).first()
        or Semester.objects.filter(number=1).first()
    )

    departments = list(Department.objects.all())
    dept_by_choice = build_dept_choice_map(departments)
    all_programs = list(Program.objects.select_related('department').all())
    dept_by_program = build_dept_program_map(all_programs)
    programs = {p.department_id: p for p in all_programs}

    imported_count = 0
    failed_count = 0

    for row in valid_rows:
        norm = row.normalized_data or {}
        app_id = (norm.get('application_id') or row.application_id or '').strip()
        file_enr = (norm.get('enrollment_no') or row.enrollment_no or '').strip()
        full_name = (norm.get('candidate_name') or row.candidate_name or '').strip()

        try:
            with transaction.atomic():
                if not app_id and not file_enr:
                    raise ValueError('Missing Application ID and Enrollment No / PRN at import.')

                # Re-check identity under lock: never create duplicates.
                existing = None
                if app_id:
                    existing = Student.objects.filter(application_id=app_id).first()
                if existing is None and file_enr:
                    existing = Student.objects.filter(enrollment_no=file_enr).first()

                # Data-driven department resolution (same rule as staging).
                dept, _ = resolve_department(
                    norm.get('choice_code', '') or getattr(row, 'choice_code', ''),
                    norm.get('course', ''),
                    dept_by_choice, departments,
                    program_code=norm.get('program_code', '') or getattr(row, 'program_code', ''),
                    dept_by_program=dept_by_program,
                )
                if dept is None:
                    raise ValueError(
                        f"Unmapped Choice Code '{norm.get('choice_code', '')}' / "
                        f"Program Code '{norm.get('program_code', '')}'."
                    )
                prog = programs.get(dept.id) or Program.objects.filter(department=dept).first()
                # Division is per-row: senior DSE rows land in a different
                # semester than FY rows, so each gets its own Div A.
                # (Resolved fully after row_is_dsy is known below; see div fixup.)
                div = None

                # Sec 13: username = enrollment_no if available else application_id;
                # initial password = same identifier.
                login_id = file_enr or app_id
                enrollment_val = file_enr or app_id
                app_id_val = app_id or None

                existing_enr_query = Student.objects.filter(enrollment_no=enrollment_val)
                if app_id:
                    existing_enr_query = existing_enr_query.exclude(application_id=app_id)
                existing_enr = existing_enr_query.first()
                if existing_enr:
                    counter = 1
                    base = enrollment_val
                    while True:
                        q = Student.objects.filter(enrollment_no=enrollment_val)
                        if app_id:
                            q = q.exclude(application_id=app_id)
                        if not q.exists():
                            break
                        enrollment_val = f'{base}_{counter}'
                        counter += 1
                    login_id = enrollment_val if file_enr else (app_id or enrollment_val)

                if existing is not None:
                    student = existing
                    # Link missing login without touching existing credentials.
                    if student.user is None:
                        user = User.objects.filter(username=login_id).first()
                        if user is None:
                            user = User(
                                username=login_id,
                                email=norm.get('email') or f'{login_id}@gceok.ac.in',
                                user_type=User.UserType.STUDENT,
                                is_active=True,
                                must_change_password=True,
                            )
                            user.set_password(login_id)
                            user.save()
                            RoleAssignment.objects.get_or_create(
                                user=user, role=role_student,
                                defaults={'status': RoleAssignment.Status.ACTIVE},
                            )
                        student.user = user
                        student.save(update_fields=['user'])
                    # Fill admission anchor on older records that lack it.
                    _anchor_updates = {}
                    if student.admission_year_id is None:
                        _anchor_updates['admission_year'] = batch.academic_year
                    if not student.admission_type:
                        _anchor_updates['admission_type'] = 'DSE' if is_dsy else 'FY'
                    if _anchor_updates:
                        for _k, _v in _anchor_updates.items():
                            setattr(student, _k, _v)
                        student.save(update_fields=list(_anchor_updates.keys()))
                    row.student = student
                    row.validation_status = ImportRow.ValidationStatus.DUPLICATE
                    row.validation_errors = (row.validation_errors or []) + [
                        'Student already exists; linked without creating a duplicate.'
                    ]
                    row.save(update_fields=['student', 'validation_status', 'validation_errors'])
                    continue

                # Guard: never hijack an unrelated login account.
                taken = User.objects.filter(username=login_id).first()
                if taken is not None:
                    raise ValueError(
                        f"Login identifier '{login_id}' is already taken by another account."
                    )

                # 1. Login account (password set once, never reset on re-import).
                user = User(
                    username=login_id,
                    email=norm.get('email') or f'{login_id}@gceok.ac.in',
                    user_type=User.UserType.STUDENT,
                    is_active=True,
                    must_change_password=True,
                )
                user.set_password(login_id)
                user.save()

                RoleAssignment.objects.get_or_create(
                    user=user,
                    role=role_student,
                    defaults={'status': RoleAssignment.Status.ACTIVE},
                )

                # Row-level DSY (e.g. Admitted Semester == SEMESTER - 3).
                # Senior laterals use the DSE formula outcome (elapsed*2+3),
                # NOT hardcoded Sem 3 — e.g. 2023 DSE in 2024-25 EVEN -> Sem 6.
                row_admitted_sem = (norm.get('admitted_semester') or _lookup(row.raw_data, 'student admitted semester', 'admitted semester') or '').strip()
                row_is_dsy = is_dsy or ('3' in row_admitted_sem or 'III' in row_admitted_sem.upper())
                _row_no = _dse_no if row_is_dsy else _fy_no
                row_target_sem = (
                    Semester.objects.filter(number=_row_no).first() or target_sem
                )
                div = _get_or_create_division(dept, batch.academic_year, row_target_sem)

                # 2. Student identity (stable internal UUID PK; govt IDs unique cols).
                name_parts = full_name.split()
                first_name = name_parts[0] if name_parts else 'Candidate'
                middle_name = ' '.join(name_parts[1:-1]) if len(name_parts) > 2 else ''
                last_name = name_parts[-1] if len(name_parts) > 1 else 'Student'

                student = Student.objects.create(
                    user=user,
                    application_id=app_id_val,
                    enrollment_no=enrollment_val,
                    first_name=first_name[:100],
                    middle_name=middle_name[:100],
                    last_name=last_name[:100],
                    display_name=full_name[:255],
                    status=Student.Status.ACTIVE,
                    is_direct_second_year=row_is_dsy,
                    admission_year=batch.academic_year,
                    admission_type='DSE' if row_is_dsy else 'FY',
                )

                # 3. Personal details (no fabricated defaults).
                dob = None
                if norm.get('dob'):
                    try:
                        dob = datetime.date.fromisoformat(norm['dob'])
                    except ValueError:
                        dob = None
                gender = norm.get('gender') or 'OTHER'
                if gender not in ALLOWED_GENDERS:
                    gender = 'OTHER'

                caste_val = (norm.get('caste') or _lookup(row.raw_data, 'cast', 'caste', 'sub caste', 'sub-caste'))[:100]
                marital_val = (norm.get('marital_status') or _lookup(row.raw_data, 'marital status') or 'Unmarried')[:20]
                abc_id_val = (norm.get('abc_id') or _lookup(row.raw_data, 'abc id', 'abc_id', 'academic bank of credits id'))[:50]
                blood_group_val = (norm.get('blood_group') or _lookup(row.raw_data, 'blood group', 'blood_group'))[:10]
                state_val = (_lookup(row.raw_data, 'student state', 'state') or 'Maharashtra').strip()[:50]

                StudentPersonalDetail.objects.get_or_create(
                    student=student,
                    defaults={
                        'date_of_birth': dob,
                        'gender': gender,
                        'religion': (row.raw_data.get('Religion') or '').strip()[:50],
                        'nationality': 'Indian',
                        'mother_tongue': (row.raw_data.get('Mother Tongue') or '').strip()[:50],
                        'domicile_state': state_val,
                        'student_email': norm.get('email') or f'{login_id}@gceok.ac.in',
                        'student_mobile': norm.get('mobile') or '',
                        'blood_group': blood_group_val,
                        'caste': caste_val,
                        'marital_status': marital_val,
                        'abc_id': abc_id_val,
                    },
                )

                # 4. Guardian (father when provided).
                father_name = (row.raw_data.get('Father Name') or '').strip()
                if not father_name and middle_name:
                    father_name = middle_name
                if father_name:
                    StudentGuardian.objects.get_or_create(
                        student=student,
                        relationship=StudentGuardian.Relationship.FATHER,
                        defaults={
                            'name': father_name[:150],
                            'mobile': '',
                            'annual_income': parse_annual_income(
                                row.raw_data.get('Annual Family Income')),
                            'is_primary': True,
                        },
                    )

                # 5. Permanent address (raw values; no invented city/pincode).
                city_val = _lookup(row.raw_data, 'student_city/village', 'student city/village', 'city/village', 'village', 'address line 1')
                taluka_val = _lookup(row.raw_data, 'student taluka', 'taluka')
                dist_val = _lookup(row.raw_data, 'student district', 'district')
                st_val = _lookup(row.raw_data, 'student state', 'state') or 'Maharashtra'
                pin_val = _lookup(row.raw_data, 'student location pincode', 'pincode', 'pin code')
                addr_line_1 = ', '.join(filter(None, [city_val, taluka_val])) or city_val or 'Address Not Provided'

                StudentAddress.objects.get_or_create(
                    student=student,
                    address_type=StudentAddress.AddressType.PERMANENT,
                    defaults={
                        'address_line_1': addr_line_1[:255],
                        'address_line_2': (row.raw_data.get('Address Line 2') or '').strip()[:255],
                        'address_line_3': (row.raw_data.get('Address Line 3') or '').strip()[:255],
                        'village': city_val[:100],
                        'taluka': taluka_val[:100],
                        'district': dist_val[:100],
                        'state': st_val[:100],
                        'pincode': pin_val[:10],
                        'is_current': True,
                    },
                )

                # 6. Admission event (authoritative, linked to source row).
                raw = row.raw_data
                merit_no_val = _to_int(raw.get('Merit No'))
                merit_marks_val = _to_float(raw.get('Merit Marks'))
                cet_perc_val = _to_float(raw.get('CET Percentile'))
                admission_date = parse_date_flexible(
                    raw.get('Admission Date') or _lookup(raw, *_ADM_DATE_KEYS))
                reported_date = parse_date_flexible(
                    raw.get('Reported Date') or _lookup(raw, *_REP_DATE_KEYS))
                adm_type = 'DIRECT_SECOND_YEAR' if row_is_dsy else 'CAP'
                adm_app_id = app_id or file_enr or f'ADM_{student.id}'
                allotted_seat = (norm.get('admitted_category') or _lookup(raw, 'admitted_category', 'admitted category', 'seat type') or (raw.get('Seat Type') or '').strip())

                StudentAdmission.objects.get_or_create(
                    student=student,
                    academic_year=batch.academic_year,
                    application_id=adm_app_id,
                    defaults={
                        'admission_type': adm_type,
                        'category': (norm.get('category') or '').strip()[:20],
                        'candidature_type': (raw.get('Candidature Type') or ('Type A' if row_is_dsy else '')).strip()[:50],
                        'institute_code': (raw.get('Institute Code') or '6270').strip()[:20],
                        'choice_code': (norm.get('choice_code') or '').strip()[:50],
                        'program_code': (norm.get('program_code') or '').strip()[:50],
                        'seat_type': (raw.get('Seat Type') or allotted_seat).strip()[:50],
                        'allotted_seat_type': allotted_seat[:50],
                        'merit_no': merit_no_val,
                        'merit_marks': merit_marks_val,
                        'entrance_percentile': cet_perc_val,
                        'admission_date': admission_date,
                        'reported_date': reported_date,
                        'source_import_row': row,
                    },
                )

                # 7. Enrollment (target_sem: Sem 3 for DSY, Sem 1 for regular FY; history preserved per enrollment).
                if row_target_sem and prog:
                    try:
                        from apps.curriculum.services import resolve_applicable_scheme
                        enrollment_scheme = resolve_applicable_scheme(prog, batch.academic_year)
                    except Exception:
                        enrollment_scheme = None
                    StudentEnrollment.objects.get_or_create(
                        student=student,
                        academic_year=batch.academic_year,
                        semester=row_target_sem,
                        defaults={
                            'department': dept,
                            'program': prog,
                            'division': div,
                            'scheme': enrollment_scheme,
                            'status': StudentEnrollment.Status.ACTIVE,
                            'is_current': True,
                        },
                    )

                # NOTE: Aadhaar/bank records are NOT fabricated at onboarding;
                # the government file carries none. Students provide them later
                # through protected sensitive-data flows.

                row.validation_status = ImportRow.ValidationStatus.IMPORTED
                row.student = student
                row.import_error = ''
                row.save(update_fields=['validation_status', 'student', 'import_error'])
                imported_count += 1

        except Exception as exc:
            # Per-row failure: mark FAILED, keep batch alive for retry.
            try:
                with transaction.atomic():
                    locked = ImportRow.objects.select_for_update().get(id=row.id)
                    locked.validation_status = ImportRow.ValidationStatus.FAILED
                    locked.import_error = str(exc)[:1000]
                    locked.save(update_fields=['validation_status', 'import_error'])
            except Exception:
                pass
            failed_count += 1

    # Recompute batch counters from staging truth (no in-memory drift).
    counts = {}
    for st, _ in ImportRow.ValidationStatus.choices:
        counts[st] = batch.rows.filter(validation_status=st).count()
    batch.valid_rows = counts.get('VALID', 0)
    batch.invalid_rows = counts.get('INVALID', 0)
    batch.duplicate_rows = counts.get('DUPLICATE', 0)
    batch.conflict_rows = batch.rows.filter(
        validation_status=ImportRow.ValidationStatus.CONFLICT).count()
    batch.failed_rows = counts.get('FAILED', 0)
    batch.imported_rows = counts.get('IMPORTED', 0)

    if failed_count == 0:
        batch.status = ImportBatch.Status.COMPLETED
    elif imported_count > 0:
        batch.status = ImportBatch.Status.PARTIALLY_COMPLETED
    else:
        batch.status = ImportBatch.Status.FAILED
    if batch.status in (ImportBatch.Status.COMPLETED, ImportBatch.Status.PARTIALLY_COMPLETED):
        batch.completed_at = timezone.now()
    batch.summary_report = {
        'total': batch.total_rows,
        'valid_remaining': batch.valid_rows,
        'invalid': batch.invalid_rows,
        'duplicate': batch.duplicate_rows,
        'conflict': batch.conflict_rows,
        'failed': batch.failed_rows,
        'imported': batch.imported_rows,
    }
    batch.save()
    return batch


def _to_int(val):
    try:
        if val is None or str(val).strip() == '':
            return None
        return int(float(str(val).strip()))
    except (ValueError, TypeError):
        return None


def _to_float(val):
    try:
        if val is None or str(val).strip() == '':
            return None
        return float(str(val).strip())
    except (ValueError, TypeError):
        return None
