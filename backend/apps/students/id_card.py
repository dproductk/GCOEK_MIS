"""
ID-card data pack generation for the HOD portal.

Builds the HOD-facing "ID Card Export" (read-only, no writes anywhere):

- A summary of every first-year student of the HOD's department with their
  lock state and photo/signature file status, so the HOD can see who is
  ready and who still needs to upload / lock before an ID card can be made.
- A downloadable ZIP (matching the institutional sample layout learned from
  design/ folder):

      ID_Card_Data_<DEPT>_FY_<YYYYMMDD>_<HHMMSS>.zip
      ├── ID_Card_Students_Data_<DEPT>_FY.xlsx     (full info sheet)
      └── FILES/
          └── <PRN>/
              ├── <PRN>_photo.<jpg|jpeg|png>       (student's uploaded photo)
              └── <PRN>_sign.<jpg|jpeg|png>        (student's uploaded signature)

Inclusion rules (deliberately strict — images are verified on-disk at
export time, never trusted from the lock flag alone):

- Only FIRST-YEAR students (current enrollment semester year_level == 1).
- Only profile_locked == True students (the system only allows locking a
  complete profile, but historically-locked rows may predate the photo /
  signature requirement, so files are re-verified here).
- A student is packaged only when a valid, existing PHOTO and SIGNATURE
  file can be resolved. Everyone else stays out of the ZIP and is reported
  in the summary instead (the page shows them as "Needs attention").

Privacy policy: the Excel carries all informational fields stored about the
student (identity, contact, address, parents, board history, academic
placement). Aadhaar numbers and bank account details are encrypted PII and
are intentionally EXCLUDED from the export.
"""
import datetime
import io
import re
import zipfile

from django.core.files.storage import default_storage

from apps.students.models import Student

#: Documents that must physically exist for a student to be ID-card ready.
REQUIRED_IMAGE_TYPES = ('PHOTO', 'SIGNATURE')

#: Excel sheet — the canonical first-9 columns mirror the institutional
#: sample (ID_Card_Students_Data_06_FY.xlsx), the rest extend it with every
#: informational field kept in the MIS. Aadhaar number/bank details are
#: excluded by policy (encrypted PII — see module docstring).
EXCEL_COLUMNS = [
    'Enroll No', 'App ID', 'Student Name', 'Department', 'Date of Birth',
    'Email', 'Mobile', 'Gender', 'Address',
    'Place of Birth', 'Marital Status', 'Blood Group', 'Category',
    'Religion', 'Nationality', 'Mother Tongue', 'Domicile State', 'ABC ID',
    'Village', 'Taluka', 'District', 'State', 'Pincode',
    'Father Name', 'Father Mobile', 'Father Occupation', 'Father Annual Income',
    'Mother Name',
    'SSC Board', 'SSC School', 'SSC Passing Year', 'SSC Seat No',
    'SSC Marks', 'SSC Percentage',
    'HSC/Diploma Level', 'HSC/Diploma Stream', 'HSC/Diploma Board',
    'HSC/Diploma College', 'HSC/Diploma Passing Year', 'HSC/Diploma Seat No',
    'HSC/Diploma Marks', 'HSC/Diploma Percentage',
    'Photo File', 'Signature File',
]


def _safe_token(value):
    """Filesystem-safe token (PRN / dept code) for archive paths / names."""
    token = re.sub(r'[^A-Za-z0-9_.-]', '_', str(value or '').strip())
    return token or 'UNKNOWN'


def id_card_students(department_ids):
    """
    First-year students for the given departments, fully prefetched.

    Used by both the summary and the export actions so page and download
    always agree on the population ("Ready" count == FILES/ folder count).
    ``department_ids=None`` means college-wide (Admin Head / Sysadmin) and
    applies no department filter.
    """
    base_filter = {
        'is_active': True,
        'enrollments__is_current': True,
        'enrollments__semester__year_level': 1,
    }
    if department_ids is not None:
        base_filter['enrollments__department_id__in'] = department_ids
    return (
        Student.objects.filter(**base_filter)
        .prefetch_related(
            'personal_details',
            'guardians',
            'addresses',
            'board_records',
            'documents',  # Meta ordering (-version) keeps latest-first per type
            'enrollments__department',
            'enrollments__semester',
            'enrollments__division',
        )
        .distinct()
        .order_by('last_name', 'first_name')
    )


def latest_documents(student):
    """
    Latest-version PHOTO / SIGNATURE rows for the student.

    dicts prefer prefetched rows (zero extra queries); falls back to the
    latest row by version. dict keys: 'PHOTO', 'SIGNATURE' (may be None).
    """
    docs = {'PHOTO': None, 'SIGNATURE': None}
    for doc in student.documents.all():  # prefetched; ordering: -version
        key = doc.document_type
        if key in docs and docs[key] is None:
            docs[key] = doc
    return docs


def _file_on_disk(doc):
    """True when the document's stored file really exists (not just the row)."""
    if doc is None:
        return False
    try:
        return bool(doc.file_path) and default_storage.exists(doc.file_path)
    except Exception:
        return False


def doc_file_state(student, doc_type):
    """
    'OK' when a usable file is on disk for the type, else a state code.

    Codes: 'OK' | 'NO_IMAGE' (no upload row) | 'FILE_MISSING' (row exists
    but the underlying file is gone — e.g. media cleaned up incorrectly).
    """
    doc = latest_documents(student).get(doc_type)
    if doc is None:
        return 'NO_IMAGE'
    if _file_on_disk(doc):
        return 'OK'
    return 'FILE_MISSING'


def classify_student(student):
    """
    One student's export posture: READY / LOCKED_INCOMPLETE / PENDING plus
    the machine-readable reason tags the UI shows alongside each row.
    """
    if not student.profile_locked:
        return {
            'status': 'PENDING',
            'photo': 'UNKNOWN',
            'signature': 'UNKNOWN',
            'missing': ['PROFILE_LOCK'],
        }
    photo = doc_file_state(student, 'PHOTO')
    signature = doc_file_state(student, 'SIGNATURE')
    missing = []
    if photo != 'OK':
        missing.append('PHOTO')
    if signature != 'OK':
        missing.append('SIGNATURE')
    status = 'READY' if not missing else 'LOCKED_INCOMPLETE'
    return {'status': status, 'photo': photo, 'signature': signature, 'missing': missing}


def build_summary(students):
    """
    Page payload for the HOD ID-card screen: aggregate counters plus the
    per-student rows (sorted worst-offenders first: LOCKED_INCOMPLETE,
    then PENDING, then READY).
    """
    rows = []
    counts = {'total': 0, 'locked': 0, 'not_locked': 0, 'ready': 0, 'locked_incomplete': 0}
    order = {'LOCKED_INCOMPLETE': 0, 'PENDING': 1, 'READY': 2}
    departments = {}

    for student in students:
        state = classify_student(student)
        counts['total'] += 1
        if student.profile_locked:
            counts['locked'] += 1
        else:
            counts['not_locked'] += 1
        if state['status'] == 'READY':
            counts['ready'] += 1
        elif state['status'] == 'LOCKED_INCOMPLETE':
            counts['locked_incomplete'] += 1

        enrollment = student._current_enrollment if hasattr(student, '_current_enrollment') else None
        if enrollment is None:
            enrollment = next(
                (e for e in student.enrollments.all() if e.is_current), None)
        if enrollment is not None and enrollment.department_id:
            departments[enrollment.department_id] = (
                enrollment.department.code or '', enrollment.department.name or '')
        division = enrollment.division if enrollment else None

        rows.append({
            'id': str(student.id),
            'prn': student.enrollment_no or student.application_id or '',
            'display_name': student.display_name,
            'department_code': (enrollment.department.code if enrollment else '') or '',
            'division_name': (division.name if division else '') or '',
            'semester_number': (enrollment.semester.number if enrollment else None),
            'roll_number': (enrollment.roll_number if enrollment else '') or '',
            'profile_locked': student.profile_locked,
            'profile_locked_at': (
                student.profile_locked_at.isoformat() if student.profile_locked_at else None),
            'photo_status': state['photo'],
            'signature_status': state['signature'],
            'missing': state['missing'],
            'export_status': state['status'],
        })

    rows.sort(key=lambda r: (order[r['export_status']], r['display_name'] or ''))
    return {
        'count': len(rows),
        'departments': [
            {'id': str(pk), 'code': code, 'name': name}
            for pk, (code, name) in sorted(departments.items(), key=lambda kv: kv[1][0])
        ],
        'stats': counts,
        'students': rows,
    }


def page_summary(payload, page=1, page_size=500):
    """
    Status-board pagination (§22 AGENTS.md): stats/departments stay global,
    only ``students`` is windowed. Page size is capped at 500 rows.
    """
    try:
        page = max(int(str(page)), 1)
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = min(max(int(str(page_size)), 1), 500)
    except (TypeError, ValueError):
        page_size = 500
    start = (page - 1) * page_size
    windowed = dict(payload)
    windowed['students'] = payload['students'][start:start + page_size]
    windowed['page'] = page
    windowed['page_size'] = page_size
    windowed['num_pages'] = max(
        (payload['count'] + page_size - 1) // page_size, 1)
    return windowed


def _address_parts(student):
    """Permanent address row preferred; any saved row accepted (lock rule).

    Uses the prefetched rows (no extra DB query per student).
    """
    addresses = student.addresses.all()
    return next(
        (a for a in addresses if a.address_type == 'PERMANENT'),
        addresses[0] if addresses else None,
    )


def _xlsx_bytes(students, photo_map):
    """Render the info sheet for the ready students (openpyxl, in memory)."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'ID Card Data'

    header_font = Font(bold=True, color='FFFFFF')
    header_fill = PatternFill(start_color='1E3A8A', end_color='1E3A8A', fill_type='solid')
    for col_idx, label in enumerate(EXCEL_COLUMNS, start=1):
        cell = sheet.cell(row=1, column=col_idx, value=label)
        cell.font = header_font
        cell.fill = header_fill
    sheet.freeze_panes = 'A2'

    row_no = 1
    for student in students:
        documents = latest_documents(student)
        personal = getattr(student, 'personal_details', None)
        address = _address_parts(student)
        guardians = {g.relationship: g for g in student.guardians.all()}
        father = guardians.get('FATHER')
        mother = guardians.get('MOTHER')
        ssc = next((b for b in student.board_records.all() if b.level == 'SSC'), None)
        senior = next(
            (b for b in student.board_records.all() if b.level in ('HSC', 'DIPLOMA')), None)
        enrollment = next(
            (e for e in student.enrollments.all() if e.is_current), None)

        photo_doc = photo_map.get(student.id, {}).get('PHOTO')
        sign_doc = photo_map.get(student.id, {}).get('SIGNATURE')
        prn = _safe_token(student.enrollment_no or student.application_id or student.id)

        birth = ''
        if personal is not None and getattr(personal, 'date_of_birth', None):
            birth = personal.date_of_birth.strftime('%d-%m-%Y')

        address_text = ''
        if address is not None:
            address_text = ', '.join(p for p in (
                address.address_line_1, address.address_line_2, address.address_line_3,
                address.village, address.taluka, address.district, address.state,
                address.pincode,
            ) if str(p or '').strip())

        gender_map = {'MALE': 'M', 'FEMALE': 'F', 'OTHER': 'OTHER'}
        row_no += 1
        values = [
            student.enrollment_no or '',
            student.application_id or '',
            student.display_name or '',
            (enrollment.department.name if enrollment else '') or '',
            birth,
            (personal.student_email if personal is not None else '') or '',
            (personal.student_mobile if personal is not None else '') or '',
            gender_map.get(personal.gender, '') if personal is not None else '',
            address_text,
            (personal.place_of_birth if personal is not None else '') or '',
            (personal.marital_status if personal is not None else '') or '',
            (personal.blood_group if personal is not None else '') or '',
            (personal.caste if personal is not None else '') or '',
            (personal.religion if personal is not None else '') or '',
            (personal.nationality if personal is not None else '') or '',
            (personal.mother_tongue if personal is not None else '') or '',
            (personal.domicile_state if personal is not None else '') or '',
            (personal.abc_id if personal is not None else '') or '',
            (address.village if address is not None else '') or '',
            (address.taluka if address is not None else '') or '',
            (address.district if address is not None else '') or '',
            (address.state if address is not None else '') or '',
            (address.pincode if address is not None else '') or '',
            (father.name if father is not None else '') or '',
            (father.mobile if father is not None else '') or '',
            (father.occupation if father is not None else '') or '',
            (str(father.annual_income) if father is not None and father.annual_income is not None else '') or '',
            (mother.name if mother is not None else '') or '',
            (ssc.board if ssc is not None else '') or '',
            (ssc.school_college if ssc is not None else '') or '',
            (ssc.passing_year if ssc is not None else '') or '',
            (ssc.seat_no if ssc is not None else '') or '',
            (ssc.marks_obtained if ssc is not None else '') or '',
            (ssc.percentage if ssc is not None else '') or '',
            (senior.level if senior is not None else '') or '',
            (senior.stream if senior is not None else '') or '',
            (senior.board if senior is not None else '') or '',
            (senior.school_college if senior is not None else '') or '',
            (senior.passing_year if senior is not None else '') or '',
            (senior.seat_no if senior is not None else '') or '',
            (senior.marks_obtained if senior is not None else '') or '',
            (senior.percentage if senior is not None else '') or '',
            f'{prn}_photo.{_safe_token(photo_doc.file_path.rsplit(".", 1)[-1]) if photo_doc is not None else ""}'.rstrip('.'),
            f'{prn}_sign.{_safe_token(sign_doc.file_path.rsplit(".", 1)[-1]) if sign_doc is not None else ""}'.rstrip('.'),
        ]
        for col_idx, value in enumerate(values, start=1):
            sheet.cell(row=row_no, column=col_idx, value=value)

    # Reasonable column widths (bounded so nothing becomes a megabyte-wide monolith).
    for col_idx, label in enumerate(EXCEL_COLUMNS, start=1):
        width = max(len(str(label)) + 2, 12)
        sheet.column_dimensions[get_column_letter(col_idx)].width = min(width, 42)

    out = io.BytesIO()
    workbook.save(out)
    return out.getvalue()


def build_export_zip(students):
    """
    Build the ZIP for a first-year, already-department-scoped queryset.

    Returns (zip_filename, zip_bytes, report) where report keeps the counts
    and the skip list so the caller can surface them on the page and in the
    audit trail. Students without both valid files are skipped here and
    reported — they are never silently dropped.
    """
    ready, skipped = [], []
    for student in students:
        state = classify_student(student)
        if state['status'] == 'READY':
            ready.append(student)
        else:
            skipped.append({
                'prn': student.enrollment_no or student.application_id or '',
                'name': student.display_name,
                'reason': state['status'],
                'missing': state['missing'],
            })

    primary_dept = ''
    for student in ready:
        enrollment = next((e for e in student.enrollments.all() if e.is_current), None)
        if enrollment is not None and enrollment.department_id:
            primary_dept = enrollment.department.code or ''
            break
    dept_token = _safe_token(primary_dept.upper() if primary_dept else 'ALL')

    now = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    excel_name = f'ID_Card_Students_Data_{dept_token}_FY.xlsx'
    zip_name = f'ID_Card_Data_{dept_token}_FY_{now}.zip'

    photo_map = {s.id: latest_documents(s) for s in ready}
    excel_bytes = _xlsx_bytes(ready, photo_map)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(excel_name, excel_bytes)
        for student in ready:
            prn = _safe_token(student.enrollment_no or student.application_id or student.id)
            for doc_type, label in (('PHOTO', 'photo'), ('SIGNATURE', 'sign')):
                doc = photo_map.get(student.id, {}).get(doc_type)
                if doc is None or not _file_on_disk(doc):
                    continue  # raced-away file: stay consistent with the Excel rows
                ext = _safe_token(doc.file_path.rsplit('.', 1)[-1]) if '.' in (doc.file_path or '') else 'jpg'
                with default_storage.open(doc.file_path, 'rb') as stored:
                    payload = stored.read()
                archive.writestr(f'FILES/{prn}/{prn}_{label}.{ext}', payload)

    report = {
        'included': len(ready),
        'skipped': len(skipped),
        'skipped_students': skipped,
        'excel_name': excel_name,
        'zip_name': zip_name,
        'department_code': dept_token,
    }
    return zip_name, buffer.getvalue(), report
