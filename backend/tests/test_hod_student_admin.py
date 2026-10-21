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
"""
import datetime

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from apps.academic_structure.models import AcademicYear, Department, Division, Program, Semester
from apps.audit.models import AuditLog
from apps.authentication.models import PasswordHistory, Role, RoleAssignment
from apps.students.models import Student, StudentEnrollment

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
        # Student re-locks themselves after the extra edit.
        api_client.force_authenticate(user=hod_setup['student_a'].user)
        lock_res = api_client.post('/api/v1/students/me/lock/', {}, format='json')
        assert lock_res.status_code == status.HTTP_200_OK, lock_res.data
        student.refresh_from_db()
        assert student.profile_locked is True


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
