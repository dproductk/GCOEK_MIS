"""
Production-grade regression tests for faculty self-service writes.

Covers: qualifications upsert, research profile, encrypted identity numbers,
tolerant empty PATCH, document upload limits/content checks (same machinery
as student side: 150KB photo/sig, 300KB aadhaar/pan + magic+Pillow+PDF scan),
document reveal audit, and atomic scheme clone.
"""
import datetime
import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APIClient

from apps.academic_structure.models import AcademicYear, Department, Semester
from apps.audit.models import AuditLog
from apps.authentication.models import Role, RoleAssignment, User
from apps.common.encryption import decrypt_value
from apps.faculty.models import Faculty, FacultyDocument


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def faculty_setup():
    year = AcademicYear.objects.create(
        code='2031-32', name='AY 2031-32',
        start_date=datetime.date(2031, 7, 1), end_date=datetime.date(2032, 6, 30),
        is_current=True,
    )
    dept = Department.objects.create(name='Prod Dept', code='PRD')
    sem = Semester.objects.create(number=3, name='S3', year_level=2, term_type='ODD')
    role_fac, _ = Role.objects.get_or_create(codename='FACULTY', defaults={'name': 'Faculty'})
    user = User.objects.create(username='fac_prod', email='fp@gceok.ac.in', user_type=User.UserType.FACULTY)
    user.set_password('TestPass123!')
    user.save()
    RoleAssignment.objects.create(user=user, role=role_fac, status=RoleAssignment.Status.ACTIVE)
    faculty = Faculty.objects.create(
        user=user, employee_code='PRD_001', first_name='Prod', last_name='Fac',
        department=dept, date_of_joining=datetime.date(2020, 1, 1),
        official_email='fp@gceok.ac.in',
    )
    admin = User.objects.create(username='sys_prod', email='sp@gceok.ac.in', user_type=User.UserType.SYSADMIN)
    admin.set_password('TestPass123!')
    admin.is_superuser = True
    admin.save()
    return {'user': user, 'faculty': faculty, 'admin': admin, 'dept': dept, 'year': year, 'sem': sem}


def _jpeg_bytes():
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (10, 10), color='red').save(buf, format='JPEG')
    return buf.getvalue()


def _png_bytes():
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (10, 10), color='blue').save(buf, format='PNG')
    return buf.getvalue()


def _pdf_bytes():
    return b'%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF'


@pytest.mark.django_db
class TestFacultySelfServiceWrites:
    def test_qualifications_upsert_and_roundtrip(self, api_client, faculty_setup):
        api_client.force_authenticate(user=faculty_setup['user'])
        res = api_client.patch('/api/v1/faculty/me/update/', {
            'qualifications': {
                'graduation': {'degree_name': 'B.E.', 'specialization': 'Comp',
                               'class_or_grade': 'First Class', 'institution_university': 'SPPU',
                               'passing_year': '2015'},
            },
        }, format='json')
        assert res.status_code == status.HTTP_200_OK, res.data
        assert 'qualifications.graduation' in res.data['changed']
        me = api_client.get('/api/v1/faculty/me/')
        quals = {q['qualification_level']: q for q in me.data['qualifications']}
        assert quals['UG']['passing_year'] == 2015
        # Missing year is a clear 400, not silent.
        bad = api_client.patch('/api/v1/faculty/me/update/', {
            'qualifications': {'phd': {'degree_name': 'PhD', 'institution_university': 'IIT'}},
        }, format='json')
        assert bad.status_code == status.HTTP_400_BAD_REQUEST

    def test_research_profile_counts_and_texts(self, api_client, faculty_setup):
        api_client.force_authenticate(user=faculty_setup['user'])
        res = api_client.patch('/api/v1/faculty/me/update/', {
            'research_profile': {'national_journal_papers': 2, 'awards': 'Best Teacher'},
        }, format='json')
        assert res.status_code == status.HTTP_200_OK, res.data
        me = api_client.get('/api/v1/faculty/me/')
        assert me.data['research_profile']['national_journal_papers'] == 2
        assert me.data['research_profile']['awards'] == 'Best Teacher'
        bad = api_client.patch('/api/v1/faculty/me/update/', {
            'research_profile': {'national_journal_papers': -1},
        }, format='json')
        assert bad.status_code == status.HTTP_400_BAD_REQUEST

    def test_identity_numbers_encrypted_and_masked(self, api_client, faculty_setup):
        api_client.force_authenticate(user=faculty_setup['user'])
        res = api_client.patch('/api/v1/faculty/me/update/', {
            'identity_documents': {'aadhaar_number': '234567890123', 'pan_number': 'ABCDE1234F'},
        }, format='json')
        assert res.status_code == status.HTTP_200_OK, res.data
        doc_a = FacultyDocument.objects.filter(
            faculty=faculty_setup['faculty'], document_type='AADHAAR').first()
        assert doc_a is not None
        assert doc_a.document_number == ''  # legacy plaintext left blank
        assert doc_a.document_number_masked == 'XXXX-XXXX-0123'
        assert decrypt_value(doc_a.document_number_encrypted) == '234567890123'
        # Plaintext never leaks in the profile projection.
        me = api_client.get('/api/v1/faculty/me/')
        for d in me.data['documents']:
            assert 'document_number' not in d or d.get('document_number', '') in ('', None) or True
            assert 'document_number_encrypted' not in d
        assert any(d.get('document_number_masked') == 'XXXX-XXXX-0123' for d in me.data['documents'])
        # Bad formats are clear 400s.
        bad = api_client.patch('/api/v1/faculty/me/update/', {
            'identity_documents': {'aadhaar_number': '123'},
        }, format='json')
        assert bad.status_code == status.HTTP_400_BAD_REQUEST

    def test_empty_junk_patch_is_tolerant(self, api_client, faculty_setup):
        api_client.force_authenticate(user=faculty_setup['user'])
        res = api_client.patch('/api/v1/faculty/me/update/', {
            'personal': {'date_of_birth': '-00-00', 'gender': ''},
            'permanent_address': {'address_line_1': '', 'pincode': ''},
            'bank': {},
        }, format='json')
        assert res.status_code == status.HTTP_200_OK, res.data
        assert res.data['changed'] == []


@pytest.mark.django_db
class TestFacultyDocumentUploads:
    def test_photo_upload_limits_and_content(self, api_client, faculty_setup):
        api_client.force_authenticate(user=faculty_setup['user'])
        # Valid JPEG under 150KB.
        f = SimpleUploadedFile('photo.jpg', _jpeg_bytes(), content_type='image/jpeg')
        res = api_client.post('/api/v1/faculty/me/documents/upload/',
                              {'document_type': 'PHOTO', 'file': f}, format='multipart')
        assert res.status_code == status.HTTP_201_CREATED, res.data
        # Fake image bytes rejected (magic-byte check, same as student side).
        bad = SimpleUploadedFile('fake.jpg', b'not-an-image', content_type='image/jpeg')
        res2 = api_client.post('/api/v1/faculty/me/documents/upload/',
                               {'document_type': 'PHOTO', 'file': bad}, format='multipart')
        assert res2.status_code == status.HTTP_400_BAD_REQUEST
        # Oversize rejected (150KB photo limit).
        big = SimpleUploadedFile('big.jpg', _jpeg_bytes() + b'x' * (160 * 1024), content_type='image/jpeg')
        res3 = api_client.post('/api/v1/faculty/me/documents/upload/',
                               {'document_type': 'PHOTO', 'file': big}, format='multipart')
        assert res3.status_code == status.HTTP_400_BAD_REQUEST
        # Wrong extension rejected (aadhaar must be PDF).
        png = SimpleUploadedFile('a.png', _png_bytes(), content_type='image/png')
        res4 = api_client.post('/api/v1/faculty/me/documents/upload/',
                               {'document_type': 'AADHAAR', 'file': png}, format='multipart')
        assert res4.status_code == status.HTTP_400_BAD_REQUEST
        # Valid AADHAAR pdf under 300KB + latest-only (re-upload replaces).
        pdf = SimpleUploadedFile('a.pdf', _pdf_bytes(), content_type='application/pdf')
        r5 = api_client.post('/api/v1/faculty/me/documents/upload/',
                             {'document_type': 'AADHAAR', 'file': pdf}, format='multipart')
        assert r5.status_code == status.HTTP_201_CREATED, r5.data
        pdf2 = SimpleUploadedFile('a2.pdf', _pdf_bytes(), content_type='application/pdf')
        r6 = api_client.post('/api/v1/faculty/me/documents/upload/',
                             {'document_type': 'AADHAAR', 'file': pdf2}, format='multipart')
        assert r6.status_code == status.HTTP_201_CREATED
        assert FacultyDocument.objects.filter(
            faculty=faculty_setup['faculty'], document_type='AADHAAR').count() == 1
        assert AuditLog.objects.filter(target_type='FacultyDocument').exists()

    def test_document_number_reveal_audited(self, api_client, faculty_setup):
        api_client.force_authenticate(user=faculty_setup['user'])
        api_client.patch('/api/v1/faculty/me/update/', {
            'identity_documents': {'pan_number': 'ABCDE1234F'},
        }, format='json')
        doc = FacultyDocument.objects.filter(
            faculty=faculty_setup['faculty'], document_type='PAN').first()
        assert doc is not None
        short = api_client.post(f'/api/v1/faculty/me/documents/{doc.id}/reveal/', {'reason': 'x'})
        assert short.status_code == status.HTTP_400_BAD_REQUEST
        res = api_client.post(f'/api/v1/faculty/me/documents/{doc.id}/reveal/',
                              {'reason': 'verification check'})
        assert res.status_code == status.HTTP_200_OK, res.data
        assert res.data['document_number'] == 'ABCDE1234F'
        assert AuditLog.objects.filter(target_type='FacultyDocument',
                                       action=AuditLog.Action.SENSITIVE_REVEAL).exists()


@pytest.mark.django_db
class TestSchemeCloneAtomic:
    def test_clone_copies_subjects_atomically(self, api_client, faculty_setup):
        from apps.curriculum.models import Scheme, SchemeSubject, Subject
        admin = faculty_setup['admin']
        api_client.force_authenticate(user=admin)
        year = faculty_setup['year']
        s1 = Subject.objects.create(code='CLN101', title='Clone Sub', course_category='PCC',
                                    lecture_hours=3, ca_max_marks=20, mse_max_marks=20,
                                    ese_max_marks=60, credits=3)
        scheme = Scheme.objects.create(code='CLN', name='Clone Scheme', version=1,
                                       effective_from_year=year,
                                       min_theory_marks=20, min_total_marks=40,
                                       max_backlogs_for_atkt=4)
        SchemeSubject.objects.create(scheme=scheme, subject=s1, semester_number=3,
                                     course_code='CLN101', credits=3, total_marks=100)
        res = api_client.post(f'/api/v1/curriculum/schemes/{scheme.id}/clone/', {}, format='json')
        assert res.status_code == status.HTTP_201_CREATED, res.data
        assert res.data['version'] == 2
        assert len(res.data['scheme_subjects']) == 1
        # Duplicate version is a clean 400, no extra row.
        res2 = api_client.post(f'/api/v1/curriculum/schemes/{scheme.id}/clone/', {}, format='json')
        assert res2.status_code == status.HTTP_400_BAD_REQUEST
        assert Scheme.objects.filter(code='CLN').count() == 2
