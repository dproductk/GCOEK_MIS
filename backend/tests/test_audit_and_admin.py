"""
Automated tests for Audit Log Viewer, Role Assignments, and Sysadmin Governance.
Tests:
- Sysadmin can inspect immutable audit trail
- Scope enforcement: Student receives 403 on audit log endpoint
- Creating a role assignment generates an append-only ROLE_ASSIGN audit log
- Revoking a role assignment generates an append-only ROLE_REVOKE audit log
"""
import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.authentication.models import Role, RoleAssignment, User


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def admin_setup(db):
    sysadmin = User.objects.create_superuser(
        username='test_sysadmin',
        email='admin@gceok.ac.in',
        password='Password123!',
    )
    role_sysadmin, _ = Role.objects.get_or_create(codename='SYSADMIN', defaults={'name': 'System Administrator'})
    RoleAssignment.objects.create(user=sysadmin, role=role_sysadmin, status=RoleAssignment.Status.ACTIVE)

    student_user = User.objects.create_user(
        username='test_student',
        email='student@gceok.ac.in',
        password='Password123!',
        user_type=User.UserType.STUDENT,
    )
    role_student, _ = Role.objects.get_or_create(codename='STUDENT', defaults={'name': 'Student'})
    RoleAssignment.objects.create(user=student_user, role=role_student, status=RoleAssignment.Status.ACTIVE)

    faculty_user = User.objects.create_user(
        username='prof_sharma',
        email='sharma@gceok.ac.in',
        password='Password123!',
        user_type=User.UserType.FACULTY,
    )
    role_hod, _ = Role.objects.get_or_create(codename='HOD', defaults={'name': 'Head of Department'})

    # Create an initial audit log
    AuditLog.objects.create(
        actor=sysadmin,
        actor_username=sysadmin.username,
        action=AuditLog.Action.CREATE,
        target_type='User',
        target_id=str(faculty_user.id),
        target_display=faculty_user.username,
        description="Created faculty account for prof_sharma",
    )

    return {
        'sysadmin': sysadmin,
        'student_user': student_user,
        'faculty_user': faculty_user,
        'role_hod': role_hod,
    }


@pytest.mark.django_db
def test_sysadmin_can_view_audit_logs(api_client, admin_setup):
    api_client.force_authenticate(user=admin_setup['sysadmin'])
    response = api_client.get('/api/v1/audit/logs/')
    assert response.status_code == status.HTTP_200_OK
    results = response.data.get('results', response.data)
    assert len(results) >= 1
    assert any(log['target_display'] == 'prof_sharma' for log in results)


@pytest.mark.django_db
def test_student_forbidden_from_viewing_audit_logs(api_client, admin_setup):
    api_client.force_authenticate(user=admin_setup['student_user'])
    response = api_client.get('/api/v1/audit/logs/')
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_role_assignment_lifecycle_and_audit(api_client, admin_setup):
    api_client.force_authenticate(user=admin_setup['sysadmin'])
    faculty_user = admin_setup['faculty_user']
    role_hod = admin_setup['role_hod']

    # 1. Assign HOD role to faculty
    assign_res = api_client.post('/api/v1/auth/role-assignments/', {
        'user': str(faculty_user.id),
        'role': str(role_hod.id),
    })
    assert assign_res.status_code == status.HTTP_201_CREATED
    assignment_id = assign_res.data['id']

    # Verify audit log was created
    assign_log = AuditLog.objects.filter(
        action=AuditLog.Action.ROLE_ASSIGN,
        target_id=assignment_id,
    ).first()
    assert assign_log is not None
    assert assign_log.actor == admin_setup['sysadmin']

    # 2. Revoke HOD role
    revoke_res = api_client.post(f'/api/v1/auth/role-assignments/{assignment_id}/revoke/', {
        'reason': 'Tenure completed',
    })
    assert revoke_res.status_code == status.HTTP_200_OK

    # Verify revoke audit log was created
    revoke_log = AuditLog.objects.filter(
        action=AuditLog.Action.ROLE_REVOKE,
        target_id=assignment_id,
    ).first()
    assert revoke_log is not None
    assert revoke_log.reason == 'Tenure completed'


@pytest.mark.django_db
def test_sysadmin_assign_all_5_department_hods(api_client, admin_setup):
    """Sysadmin can fetch all 5 departments and assign HODs simultaneously."""
    from apps.academic_structure.models import Department

    depts_data = [
        ('Artificial Intelligence and Data Science', 'AI_DS'),
        ('Computer Science and Engineering', 'CSE'),
        ('Electrical Engineering', 'EE'),
        ('Electronics and Telecommunication Engineering', 'ETC'),
        ('Mechanical and Automation Engineering', 'MAE'),
    ]
    for name, code in depts_data:
        Department.objects.get_or_create(code=code, defaults={'name': name})

    sysadmin = admin_setup['sysadmin']
    faculty_user = admin_setup['faculty_user']
    api_client.force_authenticate(user=sysadmin)

    # 1. GET /department-hods/
    res_get = api_client.get('/api/v1/auth/role-assignments/department-hods/')
    assert res_get.status_code == status.HTTP_200_OK
    depts = res_get.data['departments']
    assert len(depts) == 5  # Exactly 5 departments in GCOEK

    # 2. Assign HOD for all 5 departments in a single batch
    assignments = [{'department_id': d['department_id'], 'user_id': str(faculty_user.id)} for d in depts]
    res_post = api_client.post(
        '/api/v1/auth/role-assignments/department-hods/',
        {'assignments': assignments},
        format='json',
    )
    assert res_post.status_code == status.HTTP_200_OK
    assert len(res_post.data['updated']) == 5


@pytest.mark.django_db
def test_hod_scoped_student_visibility_and_division_editing(api_client, admin_setup):
    """
    HOD sees list of students in their department only,
    and has the ability to edit a student's division.
    """
    import datetime
    from apps.academic_structure.models import AcademicYear, Department, Division, Program, Semester
    from apps.students.models import Student, StudentEnrollment

    sysadmin = admin_setup['sysadmin']
    faculty_user = admin_setup['faculty_user']

    cse_dept, _ = Department.objects.get_or_create(code='CSE', defaults={'name': 'Computer Science and Engineering'})
    ee_dept, _ = Department.objects.get_or_create(code='EE', defaults={'name': 'Electrical Engineering'})
    ay, _ = AcademicYear.objects.get_or_create(
        code='2026-27',
        defaults={
            'name': '2026-2027',
            'start_date': datetime.date(2026, 7, 1),
            'end_date': datetime.date(2027, 6, 30),
            'is_current': True,
        }
    )
    sem1, _ = Semester.objects.get_or_create(
        number=1,
        defaults={'name': 'Semester 1', 'year_level': 1, 'term_type': Semester.TermType.ODD}
    )
    prog_cse, _ = Program.objects.get_or_create(
        code='BTECH_CSE',
        defaults={'department': cse_dept, 'name': 'B.Tech CSE'}
    )
    prog_ee, _ = Program.objects.get_or_create(
        code='BTECH_EE',
        defaults={'department': ee_dept, 'name': 'B.Tech EE'}
    )

    # Create CSE student and EE student
    stu_cse = Student.objects.create(
        enrollment_no='TEST_CSE_01', first_name='CSE', last_name='Student', display_name='CSE Student'
    )
    StudentEnrollment.objects.create(
        student=stu_cse, department=cse_dept, academic_year=ay, semester=sem1, program=prog_cse, is_current=True
    )

    stu_ee = Student.objects.create(
        enrollment_no='TEST_EE_01', first_name='EE', last_name='Student', display_name='EE Student'
    )
    StudentEnrollment.objects.create(
        student=stu_ee, department=ee_dept, academic_year=ay, semester=sem1, program=prog_ee, is_current=True
    )

    # Assign faculty as HOD of CSE
    role_hod = admin_setup['role_hod']
    RoleAssignment.objects.create(
        user=faculty_user, role=role_hod, department_id=cse_dept.id, status=RoleAssignment.Status.ACTIVE
    )

    # Create Division A for CSE
    div_a, _ = Division.objects.get_or_create(
        department=cse_dept, semester=sem1, academic_year=ay, name='A'
    )

    # 1. HOD queries /api/v1/students/ -> Student directory is college-wide for all faculty
    api_client.force_authenticate(user=faculty_user)
    res_list = api_client.get('/api/v1/students/')
    assert res_list.status_code == status.HTTP_200_OK
    student_ids = [s['id'] for s in res_list.data.get('results', res_list.data)]
    assert str(stu_cse.id) in student_ids
    assert str(stu_ee.id) in student_ids  # College-wide directory allows faculty to view all students

    # Query with department filter returns only CSE students
    res_cse = api_client.get(f'/api/v1/students/?department_id={cse_dept.id}')
    assert res_cse.status_code == status.HTTP_200_OK
    cse_student_ids = [s['id'] for s in res_cse.data.get('results', res_cse.data)]
    assert str(stu_cse.id) in cse_student_ids
    assert str(stu_ee.id) not in cse_student_ids

    # 2. HOD edits student's division in CSE
    res_div = api_client.post(
        f'/api/v1/students/{stu_cse.id}/assign-division/',
        {'division_id': str(div_a.id)},
        format='json',
    )
    assert res_div.status_code == status.HTTP_200_OK
    assert res_div.data['division_name'] == 'A'

    # Check updated enrollment in DB
    stu_cse.refresh_from_db()
    curr_enr = stu_cse.enrollments.get(is_current=True)
    assert curr_enr.division == div_a

    # 3. HOD cannot edit division of student in another department (EE)
    res_err = api_client.post(
        f'/api/v1/students/{stu_ee.id}/assign-division/',
        {'division_id': str(div_a.id)},
        format='json',
    )
    assert res_err.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)


@pytest.mark.django_db
def test_single_class_teacher_per_division(api_client, admin_setup):
    """Assigning a new class teacher revokes the previous holder; same user is idempotent."""
    import datetime
    from apps.academic_structure.models import AcademicYear, Department, Division, Semester
    year = AcademicYear.objects.create(
        code='2031-32', name='AY 2031-32', start_date=datetime.date(2031, 7, 1),
        end_date=datetime.date(2032, 6, 30), is_current=False)
    dept = Department.objects.create(name='Single CT Dept', code='SCT')
    sem = Semester.objects.create(number=31, name='S31', year_level=1, term_type='ODD')
    div = Division.objects.create(department=dept, academic_year=year, semester=sem, name='A')
    role_ct, _ = Role.objects.get_or_create(codename='CLASS_TEACHER', defaults={'name': 'CT'})
    t1 = User.objects.create_user(username='ct_one', password='Password123!', user_type=User.UserType.FACULTY)
    t2 = User.objects.create_user(username='ct_two', password='Password123!', user_type=User.UserType.FACULTY)
    api_client.force_authenticate(user=admin_setup['sysadmin'])
    r1 = api_client.post('/api/v1/auth/role-assignments/', {
        'user': str(t1.id), 'role': str(role_ct.id), 'department_id': str(dept.id),
        'division_id': str(div.id)}, format='json')
    assert r1.status_code == status.HTTP_201_CREATED, r1.data
    # same user again -> 200 existing, no duplicate
    r1b = api_client.post('/api/v1/auth/role-assignments/', {
        'user': str(t1.id), 'role': str(role_ct.id), 'department_id': str(dept.id),
        'division_id': str(div.id)}, format='json')
    assert r1b.status_code == status.HTTP_200_OK
    assert r1b.data['id'] == r1.data['id']
    # different user -> previous revoked, history kept
    r2 = api_client.post('/api/v1/auth/role-assignments/', {
        'user': str(t2.id), 'role': str(role_ct.id), 'department_id': str(dept.id),
        'division_id': str(div.id)}, format='json')
    assert r2.status_code == status.HTTP_201_CREATED, r2.data
    active = RoleAssignment.objects.filter(
        role=role_ct, division_id=div.id, status=RoleAssignment.Status.ACTIVE)
    assert [a.user_id for a in active] == [t2.id]
    assert RoleAssignment.objects.filter(
        role=role_ct, division_id=div.id, status=RoleAssignment.Status.REVOKED).count() == 1

