"""
Tests for the HOD ID-card export pack (summary + ZIP download).

Covered:
- Population: only first-year, current-enrollment students of the caller's
  department appear; locked students missing photo/signature are excluded
  from the ZIP and reported in the summary.
- ZIP layout: Excel at root + FILES/<PRN>/<PRN>_photo/sign files, images
  byte-identical to what was uploaded.
- Authorization: HOD scoped to own department (other dept's students never
  leak), faculty / class-teacher / accountant / plain student denied.
- Regression guard: regular student directory endpoint untouched.
"""
import datetime
import io
import zipfile

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient

from apps.academic_structure.models import (
    AcademicYear, Department, Division, Program, Semester,
)
from apps.authentication.models import Role, RoleAssignment
from apps.students.models import (
    Student, StudentEnrollment, StudentPersonalDetail,
)

User = get_user_model()


def _png_bytes(color='blue'):
    img = Image.new('RGB', (100, 100), color=color)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def _upload(client, student, content, name, doc_type, ctype='image/png'):
    f = SimpleUploadedFile(name, content, content_type=ctype)
    return client.post(
        f'/api/v1/students/{student.id}/documents/upload/',
        {'document_type': doc_type, 'file': f}, format='multipart')


def _seed_images(student, include_photo=True, include_signature=True):
    """Write storage + doc rows directly (locked students cannot self-upload)."""
    for doc_type, label, add in (
            ('PHOTO', 'photo', include_photo),
            ('SIGNATURE', 'sign', include_signature)):
        if not add:
            continue
        content = _png_bytes('red' if doc_type == 'PHOTO' else 'green')
        path = f'student_documents/{student.id}/{doc_type}_v1_{label}.png'
        default_storage.save(path, ContentFile(content))
        student.documents.create(
            document_type=doc_type, title=label, file_path=path,
            file_size=len(content), mime_type='image/png', version=1)


def _lock(student):
    Student.objects.filter(id=student.id).update(
        profile_locked=True,
        profile_locked_at=datetime.datetime(2026, 6, 1, tzinfo=datetime.timezone.utc))


@pytest.fixture
def id_setup(db):
    dept_IT = Department.objects.create(name='Information Technology', code='IT', seat_capacity=60)
    dept_CSE = Department.objects.create(name='Computer Engineering', code='CSE', seat_capacity=60)
    prog_IT = Program.objects.create(department=dept_IT, name='B.Tech IT', code='BTECH_IT')
    prog_CSE = Program.objects.create(department=dept_CSE, name='B.Tech CSE', code='BTECH_CSE')
    year = AcademicYear.objects.create(
        code='2026-27', name='2026-2027', start_date=datetime.date(2026, 7, 1),
        end_date=datetime.date(2027, 6, 30), is_current=True)
    sem1 = Semester.objects.create(number=1, name='Semester 1', year_level=1, term_type=Semester.TermType.ODD)
    sem3 = Semester.objects.create(number=3, name='Semester 3', year_level=2, term_type=Semester.TermType.ODD)
    div_IT = Division.objects.create(department=dept_IT, academic_year=year, semester=sem1, name='A')
    div_CSE = Division.objects.create(department=dept_CSE, academic_year=year, semester=sem1, name='A')

    counter = {'n': 0}

    def _student(username, dept, prog, sem, div):
        counter['n'] += 1
        u = User.objects.create_user(username=username, password='Password12345!', user_type=User.UserType.STUDENT)
        r, _ = Role.objects.get_or_create(codename='STUDENT', defaults={'name': 'Student'})
        RoleAssignment.objects.create(user=u, role=r, status=RoleAssignment.Status.ACTIVE)
        s = Student.objects.create(
            user=u, enrollment_no=f'266{counter["n"]:03d}', application_id=f'EN26{counter["n"]:06d}',
            first_name='Stu', middle_name='Mid', last_name=username)
        StudentPersonalDetail.objects.create(
            student=s, gender='MALE', date_of_birth=datetime.date(2010, 5, 14),
            student_email=f'{username}@ex.com', student_mobile='9604521205',
            place_of_birth='Kolhapur', blood_group='A+', marital_status='Unmarried',
            nationality='Indian', domicile_state='Maharashtra')
        StudentEnrollment.objects.create(
            student=s, academic_year=year, department=dept, program=prog,
            semester=sem, division=div, roll_number=str(counter['n']),
            status=StudentEnrollment.Status.ACTIVE, is_current=True)
        return s

    # IT department population (the HOD's department)
    ready = _student('it_ready', dept_IT, prog_IT, sem1, div_IT)
    locked_no_img = _student('it_locked_nodocs', dept_IT, prog_IT, sem1, div_IT)
    locked_partial = _student('it_locked_partial', dept_IT, prog_IT, sem1, div_IT)
    pending = _student('it_pending', dept_IT, prog_IT, sem1, div_IT)
    # Other department + other year — must never leak into the IT HOD's view
    _student('cse_ready', dept_CSE, prog_CSE, sem1, div_CSE)
    _student('it_sy', dept_IT, prog_IT, sem3, div_IT)

    def _staff(username, role, **scope):
        u = User.objects.create_user(username=username, password='Password12345!', user_type=User.UserType.FACULTY)
        r, _ = Role.objects.get_or_create(codename=role, defaults={'name': role})
        RoleAssignment.objects.create(user=u, role=r, status=RoleAssignment.Status.ACTIVE, **scope)
        return u

    hod = _staff('it_hod', 'HOD', department_id=dept_IT.id)
    fac = _staff('it_fac', 'FACULTY')
    acct = _staff('it_acct', 'ACCOUNTANT')
    ct = _staff('it_ct', 'CLASS_TEACHER', division_id=div_IT.id)

    return {
        'dept': dept_IT, 'other_dept': dept_CSE, 'hod': hod, 'fac': fac,
        'acct': acct, 'ct': ct,
        'ready': ready, 'locked_no_img': locked_no_img,
        'locked_partial': locked_partial, 'pending': pending,
    }


@pytest.mark.django_db
def test_summary_and_zip_include_only_locked_with_images(id_setup):
    s = id_setup

    # ready student: through the real upload route BEFORE locking (self-service path)
    client = APIClient()
    client.force_authenticate(user=s['ready'].user)
    photo = _upload(client, s['ready'], _png_bytes('red'), 'p.png', 'PHOTO')
    sign = _upload(client, s['ready'], _png_bytes('green'), 's2.png', 'SIGNATURE')
    assert photo.status_code == status.HTTP_201_CREATED, photo.data
    assert sign.status_code == status.HTTP_201_CREATED, sign.data

    _lock(s['ready'])
    _lock(s['locked_no_img'])
    _lock(s['locked_partial'])
    _seed_images(s['locked_partial'], include_photo=True, include_signature=False)

    client = APIClient()
    client.force_authenticate(user=s['hod'])

    summary = client.get('/api/v1/students/id-card-summary/')
    assert summary.status_code == status.HTTP_200_OK, summary.data
    data = summary.data
    # Only IT first-year: ready, locked_no_img, locked_partial, pending
    assert data['stats']['total'] == 4, data['stats']
    assert data['stats']['locked'] == 3
    assert data['stats']['not_locked'] == 1
    assert data['stats']['ready'] == 1
    assert data['stats']['locked_incomplete'] == 2
    assert data['stats']['ready'] + data['stats']['locked_incomplete'] == data['stats']['locked']

    rows = {r['prn']: r for r in data['students']}
    assert len(rows) == 4  # other-department + second-year students never leak in

    ready_row = rows[s['ready'].enrollment_no]
    assert ready_row['export_status'] == 'READY'
    assert ready_row['photo_status'] == 'OK'
    partial_row = rows[s['locked_partial'].enrollment_no]
    assert partial_row['export_status'] == 'LOCKED_INCOMPLETE'
    assert 'SIGNATURE' in partial_row['missing']
    pending_row = rows[s['pending'].enrollment_no]
    assert pending_row['export_status'] == 'PENDING'
    assert 'PROFILE_LOCK' in pending_row['missing']

    # ── ZIP ──
    export = client.get('/api/v1/students/id-card-export/')
    assert export.status_code == status.HTTP_200_OK
    assert export['Content-Type'] == 'application/zip'
    assert export['Content-Disposition'].startswith('attachment; filename="ID_Card_Data_')
    zf = zipfile.ZipFile(io.BytesIO(export.content))
    names = zf.namelist()
    xlsx = [n for n in names if n.endswith('.xlsx')]
    assert len(xlsx) == 1  # exactly one Excel at the archive root

    # The Excel must be a valid workbook with the canonical sample columns
    # and must NEVER contain Aadhaar / bank PII columns (privacy policy).
    from openpyxl import load_workbook
    workbook = load_workbook(io.BytesIO(zf.read(xlsx[0])))
    sheet = workbook.active
    headers = [c.value for c in next(sheet.iter_rows(min_row=1, max_row=1))]
    for canonical in ('Enroll No', 'App ID', 'Student Name', 'Department',
                      'Date of Birth', 'Email', 'Mobile', 'Gender', 'Address'):
        assert canonical in headers
    joined = ' '.join(headers).upper()
    assert 'AADHAAR' not in joined
    assert 'BANK' not in joined and 'ACCOUNT' not in joined and 'IFSC' not in joined
    # One data row for the single ready student, with real values filled in.
    assert sheet.max_row == 2
    assert str(sheet.cell(row=2, column=1).value) == s['ready'].enrollment_no
    assert 'INFORMATION TECHNOLOGY' in str(sheet.cell(row=2, column=4).value).upper()

    files = [n for n in names if n.startswith('FILES/')]
    # Only the READY student's photo+sign files exist in FILES/
    assert len(files) == 2
    prn = s['ready'].enrollment_no
    assert f'FILES/{prn}/{prn}_photo.png' in files
    assert f'FILES/{prn}/{prn}_sign.png' in files
    # Stored photo is byte-identical to the uploaded bytes
    original = default_storage.open(
        s['ready'].documents.filter(document_type='PHOTO').first().file_path, 'rb').read()
    assert zf.read(f'FILES/{prn}/{prn}_photo.png') == original
    assert export['X-Id-Card-Included'] == '1'
    assert export['X-Id-Card-Skipped'] == '3'


@pytest.mark.django_db
def test_zip_skips_locked_without_images(id_setup):
    s = id_setup
    _seed_images(s['locked_no_img'], include_photo=True, include_signature=False)
    _lock(s['locked_no_img'])
    _lock(s['ready'])  # locked but never uploaded anything

    client = APIClient()
    client.force_authenticate(user=s['hod'])
    export = client.get('/api/v1/students/id-card-export/')
    zf = zipfile.ZipFile(io.BytesIO(export.content))
    files = [n for n in zf.namelist() if n.startswith('FILES/')]
    assert files == []  # nothing half-complete gets packaged
    # All 4 IT FY students are skipped: ready (no images), locked_no_img
    # (missing signature), plus locked_partial & pending (profiles unlocked).
    assert export['X-Id-Card-Skipped'] == '4'
    # Excel still exists even when zero folders were packaged
    assert [n for n in zf.namelist() if n.endswith('.xlsx')]


@pytest.mark.django_db
def test_non_hod_roles_denied(id_setup):
    s = id_setup
    for user in (s['fac'], s['acct'], s['ct']):
        client = APIClient()
        client.force_authenticate(user=user)
        assert client.get('/api/v1/students/id-card-summary/').status_code == status.HTTP_403_FORBIDDEN
        assert client.get('/api/v1/students/id-card-export/').status_code == status.HTTP_403_FORBIDDEN

    # A plain student cannot see anything either (no STUDENT leak).
    client = APIClient()
    client.force_authenticate(user=Student.objects.get(enrollment_no=s['ready'].enrollment_no).user)
    assert client.get('/api/v1/students/id-card-summary/').status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_admin_head_sees_all_departments(id_setup):
    """College-wide callers (Admin Head / Sysadmin) export without the HOD pin."""
    s = id_setup
    _seed_images(s['ready'])
    _lock(s['ready'])

    from apps.authentication.models import Role, RoleAssignment
    admin = User.objects.create_user(username='admin_head', password='Password12345!', user_type=User.UserType.FACULTY)
    admin_role, _ = Role.objects.get_or_create(codename='ADMIN_HEAD', defaults={'name': 'Administrative Head'})
    RoleAssignment.objects.create(user=admin, role=admin_role, status=RoleAssignment.Status.ACTIVE)

    client = APIClient()
    client.force_authenticate(user=admin)
    summary = client.get('/api/v1/students/id-card-summary/')
    assert summary.status_code == status.HTTP_200_OK
    # College-wide: BOTH departments' first-year students are visible.
    assert summary.data['stats']['total'] == 5  # 4 IT FY + 1 CSE FY (SY student excluded)
    assert summary.data['stats']['ready'] == 1
    assert len(summary.data['departments']) == 2


@pytest.mark.django_db
def test_summary_query_count_stays_bounded(id_setup):
    """
    AGENTS.md §10/§24: the summary must not run one query per student.

    Bulk-create a realistic FY batch and assert the endpoint's query count
    stays well under any per-student N+1 pattern.
    """
    s = id_setup
    dept_IT = s['dept']
    year = AcademicYear.objects.get(is_current=True)
    sem1 = Semester.objects.get(number=1, year_level=1)
    div = Division.objects.filter(department=dept_IT, semester=sem1).first()
    prog = Program.objects.get(department=dept_IT)

    users = [
        User(username=f'bulk_{i}', password='x', user_type=User.UserType.STUDENT)
        for i in range(40)
    ]
    User.objects.bulk_create(users)
    student_role, _ = Role.objects.get_or_create(codename='STUDENT', defaults={'name': 'Student'})
    RoleAssignment.objects.bulk_create([
        RoleAssignment(user=u, role=student_role, status=RoleAssignment.Status.ACTIVE)
        for u in users
    ])
    from django.utils import timezone as djtz
    students = [
        Student(
            user=u, enrollment_no=f'27100{i:03d}', application_id=f'EN27{i:06d}',
            first_name='Bulk', last_name=f'Student{i:03d}',
            display_name=f'Bulk Student{i:03d}',
            profile_locked=(i % 2 == 0),
            profile_locked_at=(djtz.now() if i % 2 == 0 else None),
        )
        for i, u in enumerate(users)
    ]
    Student.objects.bulk_create(students)
    from apps.students.models import StudentPersonalDetail as _SPD
    _SPD.objects.bulk_create([
        StudentPersonalDetail(student=st, gender='MALE', date_of_birth=datetime.date(2010, 1, 1))
        for st in students
    ])
    StudentEnrollment.objects.bulk_create([
        StudentEnrollment(student=st, academic_year=year, department=dept_IT, program=prog,
                          semester=sem1, division=div, is_current=True,
                          status=StudentEnrollment.Status.ACTIVE)
        for st in students
    ])

    client = APIClient()
    client.force_authenticate(user=s['hod'])
    with django_db_capture_queries() as capture:
        summary = client.get('/api/v1/students/id-card-summary/')
    assert summary.status_code == status.HTTP_200_OK
    data = summary.data
    # 44 IT FY students now (4 fixtures + 40 bulk): whole batch is served.
    assert data['count'] == 4 + 40
    # Bound: fixed overhead + 2 storage exists() calls per *locked* student,
    # but ZERO extra DB queries per student beyond prefetching.
    assert len(capture) < 25, f'N+1 suspected: {len(capture)} queries'


# capture helper imported here to keep the top imports tidy for readers
def django_db_capture_queries():
    from django.test.utils import CaptureQueriesContext
    from django.db import connection

    return CaptureQueriesContext(connection)


@pytest.mark.django_db
def test_directory_list_untouched_regression(id_setup):
    """Guard: the new actions did not disturb the regular student directory."""
    s = id_setup
    client = APIClient()
    client.force_authenticate(user=s['hod'])
    res = client.get('/api/v1/students/?year_level=1&department=IT')
    assert res.status_code == status.HTTP_200_OK
    payload = res.data
    results = payload['results'] if isinstance(payload, dict) else payload
    assert len(results) >= 4  # IT FY students still listed normally
