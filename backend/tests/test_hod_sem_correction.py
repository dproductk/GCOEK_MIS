"""HOD cross-semester placement: skip-with-reason vs deliberate correction."""
import datetime

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.academic_structure.models import (
    AcademicYear,
    Department,
    Division,
    Program,
    Semester,
)
from apps.authentication.models import Role, RoleAssignment
from apps.students.models import Student, StudentEnrollment
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


def _hod_setup():
    year = AcademicYear.objects.create(
        code='2026-27', name='2026-2027',
        start_date=datetime.date(2026, 7, 1), end_date=datetime.date(2027, 6, 30),
        is_current=True,
    )
    dept = Department.objects.create(name='Electrical Engineering', code='EE')
    sem4 = Semester.objects.create(number=4, name='Semester 4', year_level=2, term_type=Semester.TermType.EVEN)
    sem5 = Semester.objects.create(number=5, name='Semester 5', year_level=3, term_type=Semester.TermType.ODD)
    div4 = Division.objects.create(department=dept, academic_year=year, semester=sem4, name='A')
    prog = Program.objects.create(department=dept, name='B.Tech EE', code='BTECH_EE')
    hod_user = User.objects.create_user(username='hod_ee_semfix', password='Password123!')
    role, _ = Role.objects.get_or_create(codename='HOD', defaults={'name': 'HOD'})
    RoleAssignment.objects.create(user=hod_user, role=role, department_id=dept.id,
                                  status=RoleAssignment.Status.ACTIVE)
    stu = Student.objects.create(first_name='Cross', last_name='Sem', enrollment_no='PRN-SEM-001')
    StudentEnrollment.objects.create(
        student=stu, academic_year=year, department=dept, program=prog,
        semester=sem5, division=None, status='ACTIVE', is_current=True,
        placement_confirmed=False,
    )
    return {'year': year, 'dept': dept, 'sem4': sem4, 'sem5': sem5,
            'div4': div4, 'prog': prog, 'hod': hod_user, 'stu': stu}


@pytest.mark.django_db
def test_hod_cross_sem_skipped_with_reason(api_client):
    """Sem-5 student into Sem-4 div without correction: skipped, untouched."""
    s = _hod_setup()
    api_client.force_authenticate(user=s['hod'])
    res = api_client.post(
        f"/api/v1/academic/divisions/{s['div4'].id}/assign-students/",
        {'student_ids': [str(s['stu'].id)]}, format='json')
    assert res.status_code == status.HTTP_200_OK, res.data
    assert res.data['moved'] == []
    assert len(res.data['skipped']) == 1
    assert 'Semester 5' in res.data['skipped'][0]['reason']
    assert 'Semester 4' in res.data['skipped'][0]['reason']
    enr = s['stu'].enrollments.filter(is_current=True).first()
    assert enr.semester.number == 5 and enr.division_id is None


@pytest.mark.django_db
def test_hod_cross_sem_correction_moves_as_detained(api_client):
    """Same call WITH semester_id: moved, repeat+1, confirmed, audited."""
    s = _hod_setup()
    api_client.force_authenticate(user=s['hod'])
    res = api_client.post(
        f"/api/v1/academic/divisions/{s['div4'].id}/assign-students/",
        {'student_ids': [str(s['stu'].id)], 'semester_id': str(s['sem4'].id)},
        format='json')
    assert res.status_code == status.HTTP_200_OK, res.data
    assert res.data['moved'] == [str(s['stu'].id)]
    assert res.data['repeated'] == [str(s['stu'].id)]
    s['stu'].refresh_from_db()
    assert s['stu'].repeat_count == 1
    enr = s['stu'].enrollments.filter(is_current=True).first()
    assert enr.semester.number == 4 and enr.division_id == s['div4'].id
    assert enr.placement_confirmed is True
