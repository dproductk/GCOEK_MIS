"""
Production-grade tests for student document uploads.

Covers:
- Size policy: ALLOTMENT_LETTER max 200 KB, all others max 150 KB.
- Strong file check: magic bytes + Pillow verify (fake jpg/pdf rejected).
- Old-version cleanup: re-upload keeps only the latest version.
- Permissions: Aadhaar HOD/Class-Teacher scoped only; accountant may
  view/reset ONLY allotment letters; faculty denied; students isolated.
"""
import datetime
import io

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APIClient

from apps.academic_structure.models import AcademicYear, Department, Division, Program, Semester
from apps.authentication.models import Role, RoleAssignment
from apps.students.models import Student, StudentEnrollment, StudentPersonalDetail

User = get_user_model()


def _png_bytes(size_kb=10):
    from PIL import Image
    img = Image.new('RGB', (100, 100), color='blue')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    data = buf.getvalue()
    if len(data) < size_kb * 1024:
        data = data + b'\x00' * (size_kb * 1024 - len(data))
    return data


def _pdf_bytes(size_kb=10):
    body = b'%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n'
    if len(body) < size_kb * 1024:
        body = body + b'0' * (size_kb * 1024 - len(body))
    return body


@pytest.fixture
def doc_setup(db):
    dept = Department.objects.create(name='Computer Science', code='CSE', seat_capacity=60)
    prog = Program.objects.create(department=dept, name='B.Tech CSE', code='BTECH_CSE')
    year = AcademicYear.objects.create(
        code='2026-27', name='2026-2027', start_date=datetime.date(2026, 7, 1),
        end_date=datetime.date(2027, 6, 30), is_current=True)
    sem1 = Semester.objects.create(number=1, name='Semester 1', year_level=1, term_type=Semester.TermType.ODD)
    div = Division.objects.create(department=dept, academic_year=year, semester=sem1, name='A')

    def _student(username, enr):
        u = User.objects.create_user(username=username, password='Password12345!', user_type=User.UserType.STUDENT)
        r, _ = Role.objects.get_or_create(codename='STUDENT', defaults={'name': 'Student'})
        RoleAssignment.objects.create(user=u, role=r, status=RoleAssignment.Status.ACTIVE)
        s = Student.objects.create(user=u, enrollment_no=enr, application_id=f'APP{enr}', first_name='Stu', last_name=username)
        StudentPersonalDetail.objects.create(student=s, gender='MALE')
        StudentEnrollment.objects.create(
            student=s, academic_year=year, department=dept, program=prog,
            semester=sem1, division=div, status=StudentEnrollment.Status.ACTIVE, is_current=True)
        return u, s

    stu_user, stu = _student('doc_stu', 'EN90001')
    _, stu2 = _student('doc_stu2', 'EN90002')

    def _staff(username, role, **scope):
        u = User.objects.create_user(username=username, password='Password12345!', user_type=User.UserType.FACULTY)
        r, _ = Role.objects.get_or_create(codename=role, defaults={'name': role})
        RoleAssignment.objects.create(user=u, role=r, status=RoleAssignment.Status.ACTIVE, **scope)
        return u

    hod = _staff('doc_hod', 'HOD', department_id=dept.id)
    ct = _staff('doc_ct', 'CLASS_TEACHER', division_id=div.id)
    acct = _staff('doc_acct', 'ACCOUNTANT')
    fac = _staff('doc_fac', 'FACULTY')
    return {'dept': dept, 'div': div, 'stu_user': stu_user, 'stu': stu, 'stu2': stu2,
            'hod': hod, 'ct': ct, 'acct': acct, 'fac': fac}


def _upload(client, url, content, name, dtype, ctype='application/octet-stream'):
    f = SimpleUploadedFile(name, content, content_type=ctype)
    return client.post(url, {'document_type': dtype, 'file': f}, format='multipart')


@pytest.mark.django_db
def test_allotment_within_200kb_and_old_version_cleaned(doc_setup):
    c = APIClient()
    c.force_authenticate(user=doc_setup['stu_user'])
    s = doc_setup['stu']
    r1 = _upload(c, '/api/v1/students/me/documents/upload/', _pdf_bytes(50), 'cap1.pdf', 'ALLOTMENT_LETTER', 'application/pdf')
    assert r1.status_code == status.HTTP_201_CREATED, r1.data
    assert s.documents.filter(document_type='ALLOTMENT_LETTER').count() == 1
    r2 = _upload(c, '/api/v1/students/me/documents/upload/', _pdf_bytes(60), 'cap2.pdf', 'ALLOTMENT_LETTER', 'application/pdf')
    assert r2.status_code == status.HTTP_201_CREATED, r2.data
    # Old version cleaned: only latest remains.
    assert s.documents.filter(document_type='ALLOTMENT_LETTER').count() == 1
    assert r2.data['version'] == 2


@pytest.mark.django_db
def test_size_limits_enforced(doc_setup):
    c = APIClient()
    c.force_authenticate(user=doc_setup['stu_user'])
    big_allot = _upload(c, '/api/v1/students/me/documents/upload/', _pdf_bytes(201), 'big.pdf', 'ALLOTMENT_LETTER', 'application/pdf')
    assert big_allot.status_code == status.HTTP_400_BAD_REQUEST
    big_photo = _upload(c, '/api/v1/students/me/documents/upload/', _png_bytes(151), 'big.png', 'PHOTO', 'image/png')
    assert big_photo.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_fake_files_rejected(doc_setup):
    c = APIClient()
    c.force_authenticate(user=doc_setup['stu_user'])
    fake_jpg = _upload(c, '/api/v1/students/me/documents/upload/', b'not an image at all', 'fake.jpg', 'PHOTO', 'image/jpeg')
    assert fake_jpg.status_code == status.HTTP_400_BAD_REQUEST
    fake_pdf = _upload(c, '/api/v1/students/me/documents/upload/', b'hello world', 'fake.pdf', 'ALLOTMENT_LETTER', 'application/pdf')
    assert fake_pdf.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_accountant_allotment_only(doc_setup):
    c = APIClient()
    c.force_authenticate(user=doc_setup['stu_user'])
    s = doc_setup['stu']
    _upload(c, '/api/v1/students/me/documents/upload/', _pdf_bytes(20), 'cap.pdf', 'ALLOTMENT_LETTER', 'application/pdf')
    _upload(c, '/api/v1/students/me/documents/upload/', _png_bytes(10), 'aad.png', 'AADHAAR', 'image/png')
    allot = s.documents.filter(document_type='ALLOTMENT_LETTER').first()
    aad = s.documents.filter(document_type='AADHAAR').first()

    c.force_authenticate(user=doc_setup['acct'])
    ok = c.get(f'/api/v1/students/{s.id}/documents/{allot.id}/download/')
    assert ok.status_code == status.HTTP_200_OK
    denied = c.get(f'/api/v1/students/{s.id}/documents/{aad.id}/download/')
    assert denied.status_code == status.HTTP_403_FORBIDDEN
    # Accountant cannot delete non-allotment docs.
    no_del = c.delete(f'/api/v1/students/{s.id}/documents/{aad.id}/')
    assert no_del.status_code == status.HTTP_403_FORBIDDEN
    # Accountant CAN reset the allotment letter.
    yes_del = c.delete(f'/api/v1/students/{s.id}/documents/{allot.id}/')
    assert yes_del.status_code == status.HTTP_200_OK
    assert s.documents.filter(document_type='ALLOTMENT_LETTER').count() == 0


@pytest.mark.django_db
def test_aadhaar_hod_ct_only(doc_setup):
    c = APIClient()
    c.force_authenticate(user=doc_setup['stu_user'])
    s = doc_setup['stu']
    _upload(c, '/api/v1/students/me/documents/upload/', _png_bytes(10), 'aad.png', 'AADHAAR', 'image/png')
    aad = s.documents.filter(document_type='AADHAAR').first()

    c.force_authenticate(user=doc_setup['hod'])
    assert c.get(f'/api/v1/students/{s.id}/documents/{aad.id}/download/').status_code == status.HTTP_200_OK
    c.force_authenticate(user=doc_setup['ct'])
    assert c.get(f'/api/v1/students/{s.id}/documents/{aad.id}/download/').status_code == status.HTTP_200_OK
    c.force_authenticate(user=doc_setup['fac'])
    assert c.get(f'/api/v1/students/{s.id}/documents/{aad.id}/download/').status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_student_isolation(doc_setup):
    c = APIClient()
    c.force_authenticate(user=doc_setup['stu_user'])
    s = doc_setup['stu']
    _upload(c, '/api/v1/students/me/documents/upload/', _pdf_bytes(20), 'cap.pdf', 'ALLOTMENT_LETTER', 'application/pdf')
    allot = s.documents.filter(document_type='ALLOTMENT_LETTER').first()
    # Another student (not owner) cannot download via staff endpoint.
    other = User.objects.get(username='doc_stu2')
    c.force_authenticate(user=other)
    assert c.get(f'/api/v1/students/{s.id}/documents/{allot.id}/download/').status_code in (
        status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)
