"""
Tests for Curriculum domain: scheme versioning, immutability, RBAC,
data-driven passing rules, and enrollment scheme binding.
"""
import datetime
import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.academic_structure.models import AcademicYear, Department, Program, Semester
from apps.authentication.models import Role, RoleAssignment, User
from apps.curriculum.models import Scheme, SchemeSubject, Subject
from apps.students.models import Student, StudentEnrollment


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def setup(db):
    year = AcademicYear.objects.create(
        code='2026-27', name='AY 2026-27',
        start_date=datetime.date(2026, 7, 1), end_date=datetime.date(2027, 6, 30),
        is_current=True)
    dept = Department.objects.create(name='Computer Science and Engineering', code='CSE')
    prog = Program.objects.create(department=dept, name='B.Tech CSE', code='BTECH_CSE')
    sem1 = Semester.objects.create(number=1, name='Semester 1', year_level=1, term_type='ODD')
    role_sys, _ = Role.objects.get_or_create(codename='SYSADMIN', defaults={'name': 'Sysadmin'})
    role_fac, _ = Role.objects.get_or_create(codename='FACULTY', defaults={'name': 'Faculty'})
    admin = User.objects.create(username='curr_admin', email='a@gceok.ac.in', user_type='SYSADMIN')
    admin.set_password('TestPass12345!')
    admin.save()
    RoleAssignment.objects.create(user=admin, role=role_sys, status='ACTIVE')
    fac = User.objects.create(username='curr_fac', email='f@gceok.ac.in', user_type='FACULTY')
    fac.set_password('TestPass12345!')
    fac.save()
    RoleAssignment.objects.create(user=fac, role=role_fac, status='ACTIVE')
    return {'year': year, 'dept': dept, 'prog': prog, 'sem1': sem1, 'admin': admin, 'fac': fac}


def _scheme_payload(setup, code='G', version=1):
    return {
        'code': code, 'name': f'{code} Scheme',
        'program': str(setup['prog'].id),
        'department': str(setup['dept'].id),
        'effective_from_year': str(setup['year'].id),
        'version': version,
        'min_theory_marks': '20.0', 'min_total_marks': '40.0',
        'max_backlogs_for_atkt': 4,
    }


def _complete_and_publish(api_client, setup, code):
    """Seed a publishable scheme: all 8 sems with split-defined subjects."""
    r = api_client.post('/api/v1/curriculum/schemes/', _scheme_payload(setup, code=code), format='json')
    assert r.status_code == status.HTTP_201_CREATED, r.data
    sid = r.data['id']
    for sem in range(1, 9):
        sub = api_client.post('/api/v1/curriculum/subjects/',
                              {'code': '%s%d' % (code, 200 + sem), 'title': 'Subject %d' % sem},
                              format='json').data
        ss = api_client.post('/api/v1/curriculum/scheme-subjects/', {
            'scheme': sid, 'subject': sub['id'], 'semester_number': sem,
            'course_code': '%s%d' % (code, 200 + sem), 'credits': 3, 'total_marks': 100},
            format='json').data
        api_client.post('/api/v1/curriculum/assessment-components/', {
            'scheme_subject': ss['id'], 'component_type': 'THEORY_SA',
            'maximum_marks': '70.0', 'minimum_marks': '20.0'}, format='json')
    pub = api_client.post(f'/api/v1/curriculum/schemes/{sid}/publish/')
    assert pub.status_code == status.HTTP_200_OK, pub.data
    return sid


@pytest.mark.django_db
class TestCurriculumRBACAndVersioning:
    def test_sysadmin_can_create_scheme_and_subject(self, api_client, setup):
        api_client.force_authenticate(user=setup['admin'])
        r = api_client.post('/api/v1/curriculum/subjects/',
                            {'code': 'CS201', 'title': 'Data Structures'}, format='json')
        assert r.status_code == status.HTTP_201_CREATED
        r = api_client.post('/api/v1/curriculum/schemes/', _scheme_payload(setup), format='json')
        assert r.status_code == status.HTTP_201_CREATED, r.data
        assert r.data['status'] == 'DRAFT'

    def test_faculty_write_denied_read_allowed(self, api_client, setup):
        api_client.force_authenticate(user=setup['admin'])
        api_client.post('/api/v1/curriculum/subjects/',
                        {'code': 'CS202', 'title': 'DBMS'}, format='json')
        api_client.force_authenticate(user=setup['fac'])
        r = api_client.get('/api/v1/curriculum/subjects/')
        assert r.status_code == status.HTTP_200_OK
        r = api_client.post('/api/v1/curriculum/subjects/',
                            {'code': 'CS203', 'title': 'OS'}, format='json')
        assert r.status_code == status.HTTP_403_FORBIDDEN
        r = api_client.post('/api/v1/curriculum/schemes/', _scheme_payload(setup, code='H'), format='json')
        assert r.status_code == status.HTTP_403_FORBIDDEN

    def test_duplicate_code_version_blocked(self, api_client, setup):
        api_client.force_authenticate(user=setup['admin'])
        r1 = api_client.post('/api/v1/curriculum/schemes/', _scheme_payload(setup), format='json')
        assert r1.status_code == status.HTTP_201_CREATED
        r2 = api_client.post('/api/v1/curriculum/schemes/', _scheme_payload(setup), format='json')
        assert r2.status_code == status.HTTP_400_BAD_REQUEST

    def _complete_and_publish(self, api_client, setup, code='G'):
        """Seed a publishable scheme: all 8 sems with split-defined subjects."""
        return _complete_and_publish(api_client, setup, code)

    def test_publish_blocked_until_complete(self, api_client, setup):
        api_client.force_authenticate(user=setup['admin'])
        r = api_client.post('/api/v1/curriculum/schemes/', _scheme_payload(setup, code='INC'), format='json')
        sid = r.data['id']
        pub = api_client.post(f'/api/v1/curriculum/schemes/{sid}/publish/')
        assert pub.status_code == status.HTTP_400_BAD_REQUEST
        assert 'semesters' in pub.data['detail']

    def test_publish_blocked_on_duplicate_year_scope(self, api_client, setup):
        api_client.force_authenticate(user=setup['admin'])
        self._complete_and_publish(api_client, setup, code='G')
        r = api_client.post('/api/v1/curriculum/schemes/', _scheme_payload(setup, code='H'), format='json')
        sid = r.data['id']
        for sem in range(1, 9):
            sub = api_client.post('/api/v1/curriculum/subjects/',
                                  {'code': 'HX%d' % (300 + sem), 'title': 'H %d' % sem},
                                  format='json').data
            ss = api_client.post('/api/v1/curriculum/scheme-subjects/', {
                'scheme': sid, 'subject': sub['id'], 'semester_number': sem,
                'course_code': 'HX%d' % (300 + sem), 'credits': 3, 'total_marks': 100},
                format='json').data
            api_client.post('/api/v1/curriculum/assessment-components/', {
                'scheme_subject': ss['id'], 'component_type': 'THEORY_SA',
                'maximum_marks': '70.0', 'minimum_marks': '20.0'}, format='json')
        pub = api_client.post(f'/api/v1/curriculum/schemes/{sid}/publish/')
        assert pub.status_code == status.HTTP_400_BAD_REQUEST
        assert 'already covers' in pub.data['detail']

    def test_published_scheme_immutable(self, api_client, setup):
        api_client.force_authenticate(user=setup['admin'])
        sid = self._complete_and_publish(api_client, setup, code='G')
        # edit blocked
        upd = api_client.patch(f'/api/v1/curriculum/schemes/{sid}/', {'name': 'Changed'}, format='json')
        assert upd.status_code == status.HTTP_400_BAD_REQUEST
        # child write blocked
        sub2 = api_client.post('/api/v1/curriculum/subjects/',
                               {'code': 'CS205', 'title': 'AI'}, format='json').data
        add = api_client.post('/api/v1/curriculum/scheme-subjects/', {
            'scheme': sid, 'subject': sub2['id'], 'semester_number': 3,
            'course_code': 'CS205', 'credits': 3, 'total_marks': 100}, format='json')
        assert add.status_code == status.HTTP_400_BAD_REQUEST
        # delete blocked
        dele = api_client.delete(f'/api/v1/curriculum/schemes/{sid}/')
        assert dele.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestAllProgramsAndDeptDerivation:
    def test_all_programs_scheme_and_dept_auto_derived(self, api_client, setup):
        api_client.force_authenticate(user=setup['admin'])
        # All-programs scheme (no program)
        payload = _scheme_payload(setup, code='ALL')
        del payload['program']
        r = api_client.post('/api/v1/curriculum/schemes/', payload, format='json')
        assert r.status_code == status.HTTP_201_CREATED, r.data
        assert r.data['program'] is None
        # Program scheme auto-derives department from program
        r2 = api_client.post('/api/v1/curriculum/schemes/', _scheme_payload(setup, code='G2'), format='json')
        assert r2.status_code == status.HTTP_201_CREATED, r2.data
        obj = Scheme.objects.get(id=r2.data['id'])
        assert str(obj.department_id) == str(setup['dept'].id)

    def test_program_scheme_beats_all_programs(self, api_client, setup):
        from apps.curriculum.services import resolve_applicable_scheme
        api_client.force_authenticate(user=setup['admin'])
        payload = _scheme_payload(setup, code='ALL')
        del payload['program']
        r = api_client.post('/api/v1/curriculum/schemes/', payload, format='json')
        all_id = r.data['id']
        # complete both schemes so they can publish
        for sid, prefix in ((all_id, 'AX'),):
            for sem in range(1, 9):
                sub = api_client.post('/api/v1/curriculum/subjects/',
                                      {'code': '%s%d' % (prefix, 200 + sem), 'title': 'S %d' % sem},
                                      format='json').data
                ss = api_client.post('/api/v1/curriculum/scheme-subjects/', {
                    'scheme': sid, 'subject': sub['id'], 'semester_number': sem,
                    'course_code': '%s%d' % (prefix, 200 + sem), 'credits': 3, 'total_marks': 100},
                    format='json').data
                api_client.post('/api/v1/curriculum/assessment-components/', {
                    'scheme_subject': ss['id'], 'component_type': 'THEORY_SA',
                    'maximum_marks': '70.0', 'minimum_marks': '20.0'}, format='json')
        prog_id = _complete_and_publish(api_client, setup, 'G3')
        api_client.post(f'/api/v1/curriculum/schemes/{all_id}/publish/')
        chosen = resolve_applicable_scheme(setup['prog'], setup['year'])
        assert str(chosen.id) == prog_id
        # Other program (no specific scheme) falls back to all-programs
        dept2 = Department.objects.create(name='Mechanical X', code='MEX')
        prog2 = Program.objects.create(department=dept2, name='B.Tech MEX', code='BTECH_MEX')
        fallback = resolve_applicable_scheme(prog2, setup['year'])
        assert str(fallback.id) == all_id
@pytest.mark.django_db
class TestDataDrivenRules:
    def test_scheme_thresholds_used_for_pass(self, api_client, setup):
        from apps.results.services import submit_semester_marks
        api_client.force_authenticate(user=setup['admin'])
        scheme_id = api_client.post('/api/v1/curriculum/schemes/', {
            **_scheme_payload(setup), 'min_theory_marks': '30.0',
            'min_total_marks': '50.0', 'max_backlogs_for_atkt': 2}, format='json').data['id']
        for sem in range(1, 9):
            sub = api_client.post('/api/v1/curriculum/subjects/',
                                  {'code': 'MA2%02d' % sem, 'title': 'Maths %d' % sem},
                                  format='json').data
            ss = api_client.post('/api/v1/curriculum/scheme-subjects/', {
                'scheme': scheme_id, 'subject': sub['id'], 'semester_number': sem,
                'course_code': 'MA201' if sem == 1 else 'MA2%02d' % sem,
                'credits': 4, 'total_marks': 100}, format='json').data
            api_client.post('/api/v1/curriculum/assessment-components/', {
                'scheme_subject': ss['id'], 'component_type': 'THEORY_SA',
                'maximum_marks': '70.0', 'minimum_marks': '30.0'}, format='json')
        pub = api_client.post(f'/api/v1/curriculum/schemes/{scheme_id}/publish/')
        assert pub.status_code == status.HTTP_200_OK, pub.data

        scheme = Scheme.objects.get(id=scheme_id)
        student = Student.objects.create(first_name='A', last_name='B', enrollment_no='ENQ1')
        StudentEnrollment.objects.create(
            student=student, academic_year=setup['year'], department=setup['dept'],
            program=setup['prog'], semester=setup['sem1'], scheme=scheme,
            status='ACTIVE', is_current=True)
        # theory 25 >= default 20 but < scheme 30 -> must be backlog under scheme rules
        sem_res, _ = submit_semester_marks(
            student, 1, 'Winter 2026',
            [{'course_code': 'MA201', 'course_name': 'Maths', 'credits': 4,
              'theory_marks': 25, 'total_marks': 45}])
        subj = sem_res.subject_results.first()
        assert subj.is_backlog is True
        assert subj.grade_letter == 'F'


def _theory_subject_payload(code='25AF1245PC302'):
    return {
        'course_category': 'PCC', 'code': code, 'title': 'Data Structures',
        'lecture_hours': 3, 'practical_hours': 0,
        'ca_max_marks': '20.0', 'mse_max_marks': '20.0', 'ese_max_marks': '60.0',
        'credits': 3,
    }


def _lab_subject_payload(code='25AF1245PL302'):
    return {
        'course_category': 'PCC_LAB', 'code': code, 'title': 'OS Lab',
        'lecture_hours': 0, 'practical_hours': 4,
        'practical_ca_max_marks': '25.0', 'practical_ese_max_marks': '25.0',
        'credits': 2,
    }


@pytest.mark.django_db
class TestSubjectExamScheme:
    def test_create_theory_subject_with_scheme(self, api_client, setup):
        api_client.force_authenticate(user=setup['admin'])
        r = api_client.post('/api/v1/curriculum/subjects/',
                            _theory_subject_payload(), format='json')
        assert r.status_code == status.HTTP_201_CREATED, r.data
        assert r.data['exam_total'] == 100.0
        assert r.data['category_display'].startswith('PCC')

    def test_create_lab_subject_without_theory(self, api_client, setup):
        api_client.force_authenticate(user=setup['admin'])
        r = api_client.post('/api/v1/curriculum/subjects/',
                            _lab_subject_payload(), format='json')
        assert r.status_code == status.HTTP_201_CREATED, r.data
        assert r.data['exam_total'] == 50.0

    def test_theory_subject_missing_mse_blocked(self, api_client, setup):
        api_client.force_authenticate(user=setup['admin'])
        payload = _theory_subject_payload()
        del payload['mse_max_marks']
        r = api_client.post('/api/v1/curriculum/subjects/', payload, format='json')
        assert r.status_code == status.HTTP_400_BAD_REQUEST
        assert 'mse_max_marks' in r.data

    def test_link_autofills_code_credits_and_splits(self, api_client, setup):
        api_client.force_authenticate(user=setup['admin'])
        sub = api_client.post('/api/v1/curriculum/subjects/',
                              _theory_subject_payload(), format='json').data
        sch = api_client.post('/api/v1/curriculum/schemes/',
                              _scheme_payload(setup, code='AUTO'), format='json').data
        # Only subject + semester — no retyping of code/credits/marks.
        ss = api_client.post('/api/v1/curriculum/scheme-subjects/', {
            'scheme': sch['id'], 'subject': sub['id'], 'semester_number': 3},
            format='json').data
        assert ss['course_code'] == '25AF1245PC302'
        assert ss['credits'] == 3
        assert ss['total_marks'] == 100
        comps = {c['component_type']: c for c in ss['assessment_components']}
        assert float(comps['THEORY_FA']['maximum_marks']) == 40.0  # CA + MSE
        assert float(comps['THEORY_SA']['maximum_marks']) == 60.0  # ESE

    def test_lab_link_creates_practical_splits(self, api_client, setup):
        api_client.force_authenticate(user=setup['admin'])
        sub = api_client.post('/api/v1/curriculum/subjects/',
                              _lab_subject_payload(), format='json').data
        sch = api_client.post('/api/v1/curriculum/schemes/',
                              _scheme_payload(setup, code='LAB'), format='json').data
        ss = api_client.post('/api/v1/curriculum/scheme-subjects/', {
            'scheme': sch['id'], 'subject': sub['id'], 'semester_number': 3},
            format='json').data
        comps = {c['component_type']: c for c in ss['assessment_components']}
        assert float(comps['PRACTICAL_FA']['maximum_marks']) == 25.0
        assert float(comps['PRACTICAL_SA']['maximum_marks']) == 25.0

    def test_used_subject_cannot_be_deleted(self, api_client, setup):
        api_client.force_authenticate(user=setup['admin'])
        sub = api_client.post('/api/v1/curriculum/subjects/',
                              _theory_subject_payload(), format='json').data
        sch = api_client.post('/api/v1/curriculum/schemes/',
                              _scheme_payload(setup, code='DEL'), format='json').data
        api_client.post('/api/v1/curriculum/scheme-subjects/', {
            'scheme': sch['id'], 'subject': sub['id'], 'semester_number': 1},
            format='json')
        r = api_client.delete(f"/api/v1/curriculum/subjects/{sub['id']}/")
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_link_legacy_subject_without_exam_scheme(self, api_client, setup):
        # Legacy master row (code + title only, like cs112): link must still
        # succeed with auto-filled defaults and zero split rows.
        api_client.force_authenticate(user=setup['admin'])
        sub = api_client.post('/api/v1/curriculum/subjects/',
                              {'code': 'CS112', 'title': 'Data Sets'},
                              format='json').data
        sch = api_client.post('/api/v1/curriculum/schemes/',
                              _scheme_payload(setup, code='LEG'), format='json').data
        r = api_client.post('/api/v1/curriculum/scheme-subjects/', {
            'scheme': sch['id'], 'subject': sub['id'], 'semester_number': 1},
            format='json')
        assert r.status_code == status.HTTP_201_CREATED, r.data
        assert r.data['course_code'] == 'CS112'
        assert r.data['assessment_components'] == []

    def test_publish_works_without_manual_splits(self, api_client, setup):
        api_client.force_authenticate(user=setup['admin'])
        sch = api_client.post('/api/v1/curriculum/schemes/',
                              _scheme_payload(setup, code='NEW'), format='json').data
        for sem in range(1, 9):
            sub = api_client.post('/api/v1/curriculum/subjects/',
                                  _theory_subject_payload(code='NW%02d' % sem),
                                  format='json').data
            api_client.post('/api/v1/curriculum/scheme-subjects/', {
                'scheme': sch['id'], 'subject': sub['id'],
                'semester_number': sem}, format='json')
        pub = api_client.post(f"/api/v1/curriculum/schemes/{sch['id']}/publish/")
        assert pub.status_code == status.HTTP_200_OK, pub.data
