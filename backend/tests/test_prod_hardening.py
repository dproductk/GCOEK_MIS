"""
Production-hardening regression tests for the post-audit fixes.

Covers: Subject result-field freeze on published use, scheme-clone version
guard, bulk-flag remarks cap, sensitive-reveal rate limit + no-store
headers, atomic staff unlock, unicode full names, board free-text markup
rejection, and the legacy plaintext ID backfill migration.
"""
import datetime

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.academic_structure.models import AcademicYear, Department, Semester
from apps.audit.models import AuditLog
from apps.authentication.models import Role, RoleAssignment, User
from apps.curriculum.models import Scheme, SchemeSubject, Subject
from apps.faculty.models import Faculty, FacultyDocument
from apps.students.models import Student


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def hardening_setup(db):
    year = AcademicYear.objects.create(
        code='2041-42', name='AY 2041-42',
        start_date=datetime.date(2041, 7, 1), end_date=datetime.date(2042, 6, 30),
        is_current=True,
    )
    dept = Department.objects.create(name='Hardening Dept', code='HRD')
    sem3 = Semester.objects.create(number=3, name='S3', year_level=2, term_type='ODD')
    admin = User.objects.create(username='hard_sys', email='hs@gceok.ac.in',
                                user_type=User.UserType.SYSADMIN)
    admin.set_password('TestPass123!')
    admin.is_superuser = True
    admin.save()

    subj = Subject.objects.create(code='HRD101', title='Hardening Sub',
                                  course_category='PCC', lecture_hours=3,
                                  ca_max_marks=20, mse_max_marks=20,
                                  ese_max_marks=60, credits=3)
    draft = Scheme.objects.create(code='HRD', name='Draft Scheme', version=1,
                                  effective_from_year=year, department=dept,
                                  min_theory_marks=20, min_total_marks=40,
                                  max_backlogs_for_atkt=4)
    SchemeSubject.objects.create(scheme=draft, subject=subj, semester_number=3,
                                 course_code='HRD101', credits=3, total_marks=100)
    pub = Scheme.objects.create(code='HRDP', name='Published Scheme', version=1,
                                effective_from_year=year, department=dept,
                                status=Scheme.Status.PUBLISHED,
                                min_theory_marks=20, min_total_marks=40,
                                max_backlogs_for_atkt=4)
    SchemeSubject.objects.create(scheme=pub, subject=subj, semester_number=3,
                                 course_code='HRD101', credits=3, total_marks=100)

    role_stu, _ = Role.objects.get_or_create(codename='STUDENT', defaults={'name': 'Student'})
    stu_user = User.objects.create(username='hard_stu', email='stu@gceok.ac.in',
                                   user_type=User.UserType.STUDENT)
    stu_user.set_password('TestPass123!')
    stu_user.save()
    RoleAssignment.objects.create(user=stu_user, role=role_stu,
                                  status=RoleAssignment.Status.ACTIVE)
    student = Student.objects.create(user=stu_user, enrollment_no='EN41HRD001',
                                     application_id='APP41001', first_name='Aarav',
                                     last_name='Patil', display_name='Aarav Patil')

    role_fac, _ = Role.objects.get_or_create(codename='FACULTY', defaults={'name': 'Faculty'})
    fac_user = User.objects.create(username='hard_fac', email='hf@gceok.ac.in',
                                   user_type=User.UserType.FACULTY)
    fac_user.set_password('TestPass123!')
    fac_user.save()
    RoleAssignment.objects.create(user=fac_user, role=role_fac,
                                  status=RoleAssignment.Status.ACTIVE)
    faculty = Faculty.objects.create(user=fac_user, employee_code='HRD_001',
                                     first_name='Hard', last_name='Fac',
                                     department=dept,
                                     date_of_joining=datetime.date(2020, 1, 1),
                                     official_email='hf@gceok.ac.in')
    return {'admin': admin, 'dept': dept, 'year': year, 'sem': sem3,
            'subject': subj, 'student': student, 'stu_user': stu_user,
            'faculty': faculty, 'fac_user': fac_user}


@pytest.mark.django_db
class TestSubjectFreezeGuard:
    def test_result_fields_frozen_on_published_use(self, api_client, hardening_setup):
        api_client.force_authenticate(user=hardening_setup['admin'])
        sid = hardening_setup['subject'].id
        bad = api_client.patch(f'/api/v1/curriculum/subjects/{sid}/',
                               {'credits': 4}, format='json')
        assert bad.status_code == status.HTTP_400_BAD_REQUEST, bad.data
        # Harmless metadata fix still allowed.
        ok = api_client.patch(f'/api/v1/curriculum/subjects/{sid}/',
                              {'title': 'Hardening Sub (Rev)'}, format='json')
        assert ok.status_code == status.HTTP_200_OK, ok.data

    def test_draft_only_use_stays_editable(self, api_client, hardening_setup):
        api_client.force_authenticate(user=hardening_setup['admin'])
        year, dept = hardening_setup['year'], hardening_setup['dept']
        only_draft = Subject.objects.create(code='HRD102', title='Draft Only',
                                            course_category='PCC', lecture_hours=3,
                                            ca_max_marks=20, mse_max_marks=20,
                                            ese_max_marks=60, credits=3)
        draft2 = Scheme.objects.create(code='HRD2', name='Draft 2', version=1,
                                       effective_from_year=year, department=dept,
                                       min_theory_marks=20, min_total_marks=40,
                                       max_backlogs_for_atkt=4)
        SchemeSubject.objects.create(scheme=draft2, subject=only_draft,
                                     semester_number=3, course_code='HRD102',
                                     credits=3, total_marks=100)
        res = api_client.patch(f'/api/v1/curriculum/subjects/{only_draft.id}/',
                               {'credits': 4}, format='json')
        assert res.status_code == status.HTTP_200_OK, res.data


@pytest.mark.django_db
class TestCloneVersionGuard:
    def test_clone_rejects_non_greater_version(self, api_client, hardening_setup):
        api_client.force_authenticate(user=hardening_setup['admin'])
        from apps.curriculum.models import Scheme as _Scheme
        scheme = _Scheme.objects.filter(code='HRD').first()
        before = _Scheme.objects.filter(code='HRD').count()
        res = api_client.post(f'/api/v1/curriculum/schemes/{scheme.id}/clone/',
                              {'version': 1}, format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST, res.data
        assert _Scheme.objects.filter(code='HRD').count() == before


@pytest.mark.django_db
class TestBulkFlagRemarksCap:
    def test_oversize_remarks_rejected(self, api_client, hardening_setup):
        api_client.force_authenticate(user=hardening_setup['admin'])
        res = api_client.post('/api/v1/results/eligibility/bulk-flag/',
                              {'student_id': str(hardening_setup['student'].id),
                               'target_semester_numbers': [3],
                               'remarks': 'x' * 501}, format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST, res.data


@pytest.mark.django_db
class TestRevealRateLimitAndHeaders:
    def test_reveal_no_store_and_429_after_burst(self, api_client, hardening_setup):
        api_client.force_authenticate(user=hardening_setup['fac_user'])
        api_client.patch('/api/v1/faculty/me/update/', {
            'identity_documents': {'pan_number': 'ABCDE1234F'},
        }, format='json')
        doc = FacultyDocument.objects.filter(
            faculty=hardening_setup['faculty'], document_type='PAN').first()
        assert doc is not None
        first = api_client.post(f'/api/v1/faculty/me/documents/{doc.id}/reveal/',
                                {'reason': 'verification check'})
        assert first.status_code == status.HTTP_200_OK, first.data
        assert 'no-store' in first.get('Cache-Control', '')
        # Simulate a scraping burst: 30 prior reveals in the hour.
        for _ in range(30):
            AuditLog.objects.create(actor=hardening_setup['fac_user'],
                                    actor_username='hard_fac',
                                    action=AuditLog.Action.SENSITIVE_REVEAL,
                                    target_type='FacultyDocument',
                                    target_id=str(doc.id))
        blocked = api_client.post(f'/api/v1/faculty/me/documents/{doc.id}/reveal/',
                                  {'reason': 'verification check'})
        assert blocked.status_code == 429, blocked.data


@pytest.mark.django_db
class TestStaffUnlock:
    def test_unlock_audited_and_idempotent(self, api_client, hardening_setup):
        api_client.force_authenticate(user=hardening_setup['admin'])
        student = hardening_setup['student']
        student.profile_locked = True
        student.save(update_fields=['profile_locked', 'updated_at'])
        res = api_client.post(f'/api/v1/students/{student.id}/unlock/',
                              {'reason': 'correction approved'}, format='json')
        assert res.status_code == status.HTTP_200_OK, res.data
        assert AuditLog.objects.filter(target_type='Student',
                                       target_id=str(student.id)).exists()
        again = api_client.post(f'/api/v1/students/{student.id}/unlock/',
                                {'reason': 'correction approved'}, format='json')
        assert again.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestStudentSelfServiceValidation:
    def test_unicode_full_name_accepted(self, api_client, hardening_setup):
        api_client.force_authenticate(user=hardening_setup['stu_user'])
        res = api_client.patch('/api/v1/students/me/update/',
                               {'full_name': 'Aarav Muñoz Patil'}, format='json')
        assert res.status_code == status.HTTP_200_OK, res.data
        assert 'full_name' in res.data.get('changed', [])

    def test_board_markup_rejected(self, api_client, hardening_setup):
        api_client.force_authenticate(user=hardening_setup['stu_user'])
        res = api_client.patch('/api/v1/students/me/update/',
                               {'ssc': {'board': '<script>alert(1)</script>'}},
                               format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST, res.data


@pytest.mark.django_db
class TestLegacyPlaintextBackfill:
    def test_migration_encrypts_and_clears_plaintext(self, hardening_setup):
        from apps.common.encryption import decrypt_value, is_encryption_configured
        if not is_encryption_configured():
            pytest.skip('FIELD_ENCRYPTION_KEY not configured in this environment')
        from django.apps import apps as _apps
        # Import the migration module by path (numeric-prefixed filename).
        import importlib.util as _ilu
        import pathlib as _pl
        path = (_pl.Path(__file__).resolve().parent.parent
                / 'apps' / 'faculty' / 'migrations'
                / '0008_backfill_encrypted_document_numbers.py')
        spec = _ilu.spec_from_file_location('mig0008', str(path))
        mod = _ilu.module_from_spec(spec)
        spec.loader.exec_module(mod)
        doc = FacultyDocument.objects.create(
            faculty=hardening_setup['faculty'], document_type='AADHAAR',
            title='Aadhaar Card', document_number='234567890123',
            document_number_encrypted='', document_number_masked='',
            file_path='legacy-scan.pdf')
        mod.backfill_encrypted_numbers(_apps, None)
        doc.refresh_from_db()
        assert doc.document_number == ''
        assert doc.document_number_masked == 'XXXX-XXXX-0123'
        assert decrypt_value(doc.document_number_encrypted) == '234567890123'
