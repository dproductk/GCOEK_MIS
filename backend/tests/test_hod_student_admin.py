"""
HOD Student Admin tests — department-scoped profile unlock + password reset.

Covers:
1. HOD can unlock a locked student in their own department (audited).
2. HOD is denied for another department's student (403).
3. HOD is denied for a student with no current enrollment (403).
4. STUDENT tokens are denied on both actions — and prove no partial writes.
5. HOD can reset own-department student's password: new password works,
   old password fails, must_change_password=True forced, password history
   recorded, audit row created.
6. Validation: short reason, weak password, password == username → 400,
   nothing mutated.
7. SYSADMIN scope unchanged (regression).
8. After an unlock, the student can self-lock again (re-lock loop works).
9. One-time self-lock completeness gate: lock is blocked while any field
   or required document is missing; a complete profile locks and loops.
10. Blood group self-service writes are canonicalized ('B_POS' → 'B+')
    and invalid values are rejected without partial writes.
"""
import datetime

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from apps.academic_structure.models import AcademicYear, Department, Division, Program, Semester
from apps.audit.models import AuditLog
from apps.authentication.models import PasswordHistory, Role, RoleAssignment
from apps.students.models import (
    Student,
    StudentAddress,
    StudentAadhaarDetail,
    StudentBankAccount,
    StudentBoardRecord,
    StudentDocument,
    StudentEnrollment,
    StudentGuardian,
    StudentPersonalDetail,
)

User = get_user_model()

GOOD_PASSWORD = 'FreshStart2026!'
GOOD_REASON = 'student forgot password'


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def hod_setup(db):
    """Two departments, HOD scoped to dept A, students with enrollments."""
    year = AcademicYear.objects.create(
        code='2043-44', name='AY 2043-44',
        start_date=datetime.date(2043, 7, 1), end_date=datetime.date(2044, 6, 30),
        is_current=True,
    )
    dept_a = Department.objects.create(name='Admin Dept A', code='ADSA')
    dept_b = Department.objects.create(name='Admin Dept B', code='ADSB')
    sem1 = Semester.objects.create(number=1, name='S1', year_level=1, term_type='ODD')
    prog_a = Program.objects.create(department=dept_a, name='ADM A Program', code='ADPA')
    prog_b = Program.objects.create(department=dept_b, name='ADM B Program', code='ADPB')
    div_a = Division.objects.create(department=dept_a, academic_year=year, semester=sem1, name='A')
    div_b = Division.objects.create(department=dept_b, academic_year=year, semester=sem1, name='B')

    role_hod, _ = Role.objects.get_or_create(codename='HOD', defaults={'name': 'Head of Department'})
    role_stu, _ = Role.objects.get_or_create(codename='STUDENT', defaults={'name': 'Student'})

    hod_user = User.objects.create(username='hod_admin', email='hod@gceok.ac.in',
                                   user_type=User.UserType.FACULTY)
    hod_user.set_password('HodPass123456!')
    hod_user.save()
    RoleAssignment.objects.create(user=hod_user, role=role_hod,
                                  department_id=str(dept_a.id),
                                  status=RoleAssignment.Status.ACTIVE)

    def make_student(username, first, last, dept, prog, div):
        stu_user = User.objects.create(username=username, email=f'{username}@gceok.ac.in',
                                       user_type=User.UserType.STUDENT)
        stu_user.set_password('StudentOld123!')
        stu_user.must_change_password = False
        stu_user.save()
        RoleAssignment.objects.create(user=stu_user, role=role_stu,
                                      status=RoleAssignment.Status.ACTIVE)
        student = Student.objects.create(user=stu_user, enrollment_no=f'EN43{username[:7]}',
                                         application_id=f'APP{username}',
                                         first_name=first, last_name=last,
                                         display_name=f'{first} {last}')
        StudentEnrollment.objects.create(
            student=student, academic_year=year, department=dept,
            program=prog, semester=sem1, division=div,
        )
        return student

    student_a = make_student('stua43', 'Alpha', 'One', dept_a, prog_a, div_a)
    student_b = make_student('stub43', 'Beta', 'Two', dept_b, prog_b, div_b)

    # sysadmin for regression proof
    role_sys, _ = Role.objects.get_or_create(codename='SYSADMIN', defaults={'name': 'Sysadmin'})
    sys_user = User.objects.create(username='sys_admin', email='sys@gceok.ac.in',
                                   user_type=User.UserType.SYSADMIN)
    sys_user.is_superuser = True
    sys_user.set_password('SysPass123456!')
    sys_user.save()
    RoleAssignment.objects.create(user=sys_user, role=role_sys,
                                  status=RoleAssignment.Status.ACTIVE)

    return {'year': year, 'dept_a': dept_a, 'dept_b': dept_b,
            'hod_user': hod_user, 'sys_user': sys_user,
            'student_a': student_a, 'student_b': student_b}


def _unlocked_to_locked(student):
    student.profile_locked = True
    student.profile_locked_at = None
    student.save(update_fields=['profile_locked', 'profile_locked_at'])
    return student


def _complete_profile_for_lock(student):
    """Fill every field + upload every document the self-lock gate requires.

    Mirrors the one-time lock completeness rule in apps/students/views.py:
    personal details (incl. blood group), guardians, address, Aadhaar,
    bank, SSC + HSC board records and all mandatory documents.
    """
    StudentPersonalDetail.objects.create(
        student=student,
        date_of_birth=datetime.date(2006, 1, 15),
        gender='MALE',
        place_of_birth='Kolhapur',
        student_email=f'{student.enrollment_no.lower()}@example.com',
        student_mobile='9876543210',
        blood_group='O+',
        abc_id='1234-5678-9012',
        marital_status='Unmarried',
    )
    StudentGuardian.objects.create(
        student=student, relationship='FATHER', name='Father Name',
        mobile='9876543211', annual_income=500000,
    )
    StudentGuardian.objects.create(
        student=student, relationship='MOTHER', name='Mother Name', mobile='9876543212',
    )
    StudentAddress.objects.create(
        student=student, address_type='PERMANENT',
        address_line_1='Shivaji Nagar', district='Kolhapur',
        state='Maharashtra', pincode='416001',
    )
    StudentAadhaarDetail.objects.create(
        student=student,
        aadhaar_number_encrypted='encrypted_aadhaar_1234',
        aadhaar_number_masked='XXXX-XXXX-1234',
        enrolment_id='ENR-1234',
        name_as_per_aadhaar=student.display_name,
    )
    StudentBankAccount.objects.create(
        student=student,
        account_holder_name=student.display_name,
        bank_name='State Bank of India',
        branch_name='Kolhapur Main',
        ifsc_code='SBIN0001234',
        account_number_encrypted='encrypted_acc_9876',
        account_number_masked='XXXXXXXX9876',
        is_primary=True,
    )
    StudentBoardRecord.objects.create(
        student=student, level='SSC', board='MSBSHSE',
        school_college='Example High School', passing_year='2023',
        seat_no='S123456', marks_obtained='500', percentage='89.56',
    )
    StudentBoardRecord.objects.create(
        student=student, level='HSC', stream='Science',
        board='MSBSHSE', school_college='Example College', passing_year='2025',
        seat_no='H123456', marks_obtained='450', percentage='75.00',
    )
    for doc_type in (
        'PHOTO', 'SIGNATURE', 'AADHAAR', 'ALLOTMENT_LETTER',
        'SSC_MARKSHEET', 'HSC_MARKSHEET',
    ):
        StudentDocument.objects.create(
            student=student, document_type=doc_type,
            title=doc_type, file_path=f'students/{doc_type}.pdf',
        )


@pytest.mark.django_db
class TestHodUnlock:
    def test_hod_unlocks_own_department_student(self, api_client, hod_setup):
        student = _unlocked_to_locked(hod_setup['student_a'])
        api_client.force_authenticate(user=hod_setup['hod_user'])
        res = api_client.post(f'/api/v1/students/{student.id}/unlock/',
                              {'reason': GOOD_REASON}, format='json')
        assert res.status_code == status.HTTP_200_OK, res.data
        student.refresh_from_db()
        assert student.profile_locked is False
        assert AuditLog.objects.filter(actor=hod_setup['hod_user'],
                                       target_type='Student',
                                       target_id=str(student.id)).exists()

    def test_hod_cannot_unlock_other_department(self, api_client, hod_setup):
        student = _unlocked_to_locked(hod_setup['student_b'])
        api_client.force_authenticate(user=hod_setup['hod_user'])
        res = api_client.post(f'/api/v1/students/{student.id}/unlock/',
                              {'reason': GOOD_REASON}, format='json')
        assert res.status_code == status.HTTP_403_FORBIDDEN, res.data
        student.refresh_from_db()
        assert student.profile_locked is True

    def test_hod_cannot_unlock_student_without_current_enrollment(self, api_client, hod_setup):
        stu_user = User.objects.create(username='stunroll43', email='n43@gceok.ac.in',
                                       user_type=User.UserType.STUDENT)
        stu_user.set_password('NoEnroll123!')
        stu_user.save()
        RoleAssignment.objects.create(
            user=stu_user,
            role=Role.objects.get(codename='STUDENT'),
            status=RoleAssignment.Status.ACTIVE)
        student = Student.objects.create(user=stu_user, enrollment_no='EN43NOROLL',
                                         application_id='APPNOROLL43',
                                         first_name='No', last_name='Enroll',
                                         display_name='No Enroll')
        _unlocked_to_locked(student)
        api_client.force_authenticate(user=hod_setup['hod_user'])
        res = api_client.post(f'/api/v1/students/{student.id}/unlock/',
                              {'reason': GOOD_REASON}, format='json')
        assert res.status_code == status.HTTP_403_FORBIDDEN, res.data
        student.refresh_from_db()
        assert student.profile_locked is True

    def test_student_token_denied_on_unlock_no_partial_write(self, api_client, hod_setup):
        """STUDENT class JWT must not unlock itself or anyone: no partial writes."""
        student = _unlocked_to_locked(hod_setup['student_a'])
        api_client.force_authenticate(user=hod_setup['student_a'].user)
        res = api_client.post(f'/api/v1/students/{student.id}/unlock/',
                              {'reason': GOOD_REASON}, format='json')
        assert res.status_code in (
            status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND), res.data
        student.refresh_from_db()
        assert student.profile_locked is True

    def test_relock_after_unlock_works(self, api_client, hod_setup):
        """unlock → student edits → student re-locks (one-time loop repeats)."""
        student = _unlocked_to_locked(hod_setup['student_a'])
        api_client.force_authenticate(user=hod_setup['hod_user'])
        res = api_client.post(f'/api/v1/students/{student.id}/unlock/',
                              {'reason': GOOD_REASON}, format='json')
        assert res.status_code == status.HTTP_200_OK, res.data
        student.refresh_from_db()
        assert student.profile_locked is False
        # Student re-locks themselves after the extra edit — only allowed
        # once the profile is fully complete (fields + documents).
        _complete_profile_for_lock(student)
        api_client.force_authenticate(user=student.user)
        lock_res = api_client.post('/api/v1/students/me/lock/', {}, format='json')
        assert lock_res.status_code == status.HTTP_200_OK, lock_res.data
        student.refresh_from_db()
        assert student.profile_locked is True


@pytest.mark.django_db
class TestOneTimeLockCompleteness:
    """Self-lock only succeeds when every field + document is complete."""

    def test_lock_blocked_when_profile_incomplete(self, api_client, hod_setup):
        student = hod_setup['student_a']
        assert student.profile_locked is False
        api_client.force_authenticate(user=student.user)
        res = api_client.post('/api/v1/students/me/lock/', {}, format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST, res.data
        student.refresh_from_db()
        assert student.profile_locked is False
        missing = res.data.get('missing')
        assert isinstance(missing, list) and missing
        # Personal details row absent → single consolidated label; the
        # address and every document still get their own entries.
        assert 'Personal details (all fields)' in missing
        assert any('Address' in item for item in missing)
        assert any('Photo' in item for item in missing)

    def test_lock_allowed_when_complete_and_blood_group_stored(self, api_client, hod_setup):
        student = hod_setup['student_a']
        _complete_profile_for_lock(student)
        api_client.force_authenticate(user=student.user)
        res = api_client.post('/api/v1/students/me/lock/', {}, format='json')
        assert res.status_code == status.HTTP_200_OK, res.data
        student.refresh_from_db()
        assert student.profile_locked is True
        assert student.profile_locked_at is not None
        assert student.personal_details.blood_group == 'O+'

    def test_missing_marksheet_blocks_lock(self, api_client, hod_setup):
        student = hod_setup['student_a']
        _complete_profile_for_lock(student)
        # Delete the HSC marksheet to prove the document gate alone blocks.
        StudentDocument.objects.filter(student=student, document_type='HSC_MARKSHEET').delete()
        api_client.force_authenticate(user=student.user)
        res = api_client.post('/api/v1/students/me/lock/', {}, format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST, res.data
        student.refresh_from_db()
        assert student.profile_locked is False
        assert any('HSC' in item and 'document' in item for item in res.data['missing'])


@pytest.mark.django_db
class TestBloodGroupSelfService:
    """Blood group self-service writes are canonical and validated."""

    def test_variant_write_is_canonicalized(self, api_client, hod_setup):
        student = hod_setup['student_a']
        StudentPersonalDetail.objects.create(student=student, gender='MALE', student_mobile='9999999999')
        api_client.force_authenticate(user=student.user)
        res = api_client.patch('/api/v1/students/me/update/',
                               {'personal': {'blood_group': 'B_POS'}}, format='json')
        assert res.status_code == status.HTTP_200_OK, res.data
        student.personal_details.refresh_from_db()
        assert student.personal_details.blood_group == 'B+'

    def test_spelled_out_variant_is_canonicalized(self, api_client, hod_setup):
        student = hod_setup['student_a']
        StudentPersonalDetail.objects.create(student=student, gender='MALE', student_mobile='9999999999')
        api_client.force_authenticate(user=student.user)
        res = api_client.patch('/api/v1/students/me/update/',
                               {'personal': {'blood_group': 'ab negative'}}, format='json')
        assert res.status_code == status.HTTP_200_OK, res.data
        student.personal_details.refresh_from_db()
        assert student.personal_details.blood_group == 'AB-'

    def test_invalid_blood_group_rejected_no_partial_write(self, api_client, hod_setup):
        student = hod_setup['student_a']
        StudentPersonalDetail.objects.create(student=student, gender='MALE', student_mobile='9999999999')
        api_client.force_authenticate(user=student.user)
        res = api_client.patch('/api/v1/students/me/update/',
                               {'personal': {'blood_group': 'BANANA'}}, format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST, res.data
        student.personal_details.refresh_from_db()
        assert student.personal_details.blood_group == ''
        # Bare group letter without rhesus is ambiguous — rejected too.
        res = api_client.patch('/api/v1/students/me/update/',
                               {'personal': {'blood_group': 'A'}}, format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST, res.data


@pytest.mark.django_db
class TestHodPasswordReset:
    def test_hod_resets_own_department_student_password(self, api_client, hod_setup):
        student = hod_setup['student_a']
        api_client.force_authenticate(user=hod_setup['hod_user'])
        res = api_client.post(f'/api/v1/students/{student.id}/reset-password/',
                              {'new_password': GOOD_PASSWORD, 'reason': GOOD_REASON},
                              format='json')
        assert res.status_code == status.HTTP_200_OK, res.data
        target_user = student.user
        target_user.refresh_from_db()
        assert target_user.check_password(GOOD_PASSWORD) is True
        assert target_user.check_password('StudentOld123!') is False
        assert target_user.must_change_password is True
        # History rows: previous hash + temp password hash.
        assert PasswordHistory.objects.filter(user=target_user).count() == 2
        assert AuditLog.objects.filter(actor=hod_setup['hod_user'],
                                       target_type='User',
                                       target_id=str(target_user.id)).exists()
        # Detail must never echo the password.
        assert GOOD_PASSWORD not in str(res.data)

    def test_hod_cannot_reset_other_department_student(self, api_client, hod_setup):
        student = hod_setup['student_b']
        before = student.user.password
        api_client.force_authenticate(user=hod_setup['hod_user'])
        res = api_client.post(f'/api/v1/students/{student.id}/reset-password/',
                              {'new_password': GOOD_PASSWORD, 'reason': GOOD_REASON},
                              format='json')
        assert res.status_code == status.HTTP_403_FORBIDDEN, res.data
        student.user.refresh_from_db()
        assert student.user.password == before

    def test_student_token_denied_on_reset_no_partial_write(self, api_client, hod_setup):
        student = hod_setup['student_a']
        before = student.user.password
        api_client.force_authenticate(user=student.user)
        res = api_client.post(f'/api/v1/students/{student.id}/reset-password/',
                              {'new_password': GOOD_PASSWORD, 'reason': GOOD_REASON},
                              format='json')
        assert res.status_code in (
            status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND), res.data
        student.user.refresh_from_db()
        assert student.user.password == before
        assert student.user.must_change_password is False

    def test_weak_password_rejected(self, api_client, hod_setup):
        student = hod_setup['student_a']
        before = student.user.password
        api_client.force_authenticate(user=hod_setup['hod_user'])
        res = api_client.post(f'/api/v1/students/{student.id}/reset-password/',
                              {'new_password': 'short123', 'reason': GOOD_REASON},
                              format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST, res.data
        student.user.refresh_from_db()
        assert student.user.password == before

    def test_password_same_as_username_rejected(self, api_client, hod_setup):
        student = hod_setup['student_a']
        before = student.user.password
        api_client.force_authenticate(user=hod_setup['hod_user'])
        res = api_client.post(f'/api/v1/students/{student.id}/reset-password/',
                              {'new_password': 'stua43', 'reason': GOOD_REASON},
                              format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST, res.data
        student.user.refresh_from_db()
        assert student.user.password == before

    def test_short_reason_rejected_no_mutation(self, api_client, hod_setup):
        student = hod_setup['student_a']
        before = student.user.password
        api_client.force_authenticate(user=hod_setup['hod_user'])
        res = api_client.post(f'/api/v1/students/{student.id}/reset-password/',
                              {'new_password': GOOD_PASSWORD, 'reason': 'why'},
                              format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST, res.data
        student.user.refresh_from_db()
        assert student.user.password == before

    def test_sysadmin_can_reset_any_department(self, api_client, hod_setup):
        student = hod_setup['student_b']
        api_client.force_authenticate(user=hod_setup['sys_user'])
        res = api_client.post(f'/api/v1/students/{student.id}/reset-password/',
                              {'new_password': GOOD_PASSWORD, 'reason': GOOD_REASON},
                              format='json')
        assert res.status_code == status.HTTP_200_OK, res.data
        student.user.refresh_from_db()
        assert student.user.check_password(GOOD_PASSWORD) is True
        assert student.user.must_change_password is True

    def test_sysadmin_unlock_any_department_unchanged(self, api_client, hod_setup):
        """Regression: sysadmin unlock path behaves exactly as before."""
        student = _unlocked_to_locked(hod_setup['student_b'])
        api_client.force_authenticate(user=hod_setup['sys_user'])
        res = api_client.post(f'/api/v1/students/{student.id}/unlock/',
                              {'reason': GOOD_REASON}, format='json')
        assert res.status_code == status.HTTP_200_OK, res.data
        student.refresh_from_db()
        assert student.profile_locked is False
