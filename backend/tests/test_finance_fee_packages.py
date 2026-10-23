"""
Automated tests for the Fee Package feature (total-amount dropdown options).

Covers:
- Admin-Head-only write access (accountant gets 403; read is allowed)
- Server-side guarantees: total is ALWAYS recomputed (client-injected totals
  discarded), every item amount must be one of the head's allowed presets,
  heads must belong to the package's year and be active, duplicates rejected
- Live name resolution: head renames propagate to packages automatically
- Duplicate package name per year -> clean 400 (not a DB 500)
- Active/inactive scoping for non-configuration roles, year filtering
- End-to-end desk flow: a package's breakdown passes assessment validation
  unchanged (the exact accountant save path)
- Audit trail: CREATE / UPDATE / DELETE on FeePackage
"""
import datetime
from decimal import Decimal

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.academic_structure.models import AcademicYear, Department, Program
from apps.authentication.models import Role, RoleAssignment, User
from apps.finance.models import FeeHead, FeePackage, StudentFeeAssessment
from apps.students.models import Student


def _make_user(username, user_type, role_codename=None, superuser=False):
    if superuser:
        user = User.objects.create(
            username=username, email=f'{username}@x.in',
            user_type=user_type, is_superuser=True, is_staff=True)
        user.set_password('Password123!')
        user.save()
        return user
    user = User.objects.create_user(
        username=username, password='Password123!', user_type=user_type)
    if role_codename:
        role, _ = Role.objects.get_or_create(
            codename=role_codename,
            defaults={'name': role_codename.replace('_', ' ').title()})
        RoleAssignment.objects.create(
            user=user, role=role, status=RoleAssignment.Status.ACTIVE)
    return user


@pytest.fixture
def package_setup(db):
    """Mirrors the real 2026-27 configuration: four heads with presets whose
    largest values sum to the canonical 23675 example."""
    year = AcademicYear.objects.create(
        code='2026-27', name='2026-2027',
        start_date=datetime.date(2026, 7, 1), end_date=datetime.date(2027, 6, 30),
        is_current=True,
    )
    year2 = AcademicYear.objects.create(
        code='2025-26', name='2025-2026',
        start_date=datetime.date(2025, 7, 1), end_date=datetime.date(2026, 6, 30),
        is_current=False,
    )
    dept = Department.objects.create(name='Computer Science and Engineering', code='CSE-PKG')
    prog = Program.objects.create(
        department=dept, name='B.Tech Computer Science', code='BTECH_CSE_PKG')

    head_specs = [
        ('Tuition fee', 'TUITION_PKG', [0, 7500, 15000], FeeHead.FeeType.GOVERNMENT),
        ('Development fee', 'DEV_PKG', [0, 5000], FeeHead.FeeType.GOVERNMENT),
        ('Other fee', 'OTHER_PKG', [0, 3500], FeeHead.FeeType.INSTITUTE),
        ('Other fee (institutional)', 'OI_PKG', [175], FeeHead.FeeType.INSTITUTE),
    ]
    heads = {}
    for name, code, amounts, fee_type in head_specs:
        heads[name] = FeeHead.objects.create(
            name=name, code=code, academic_year=year, program=prog,
            allowed_amounts=amounts, fee_type=fee_type,
            amount=Decimal(str(max(amounts))),
        )
    # A head in ANOTHER year (used to prove cross-year rejection).
    other_year_head = FeeHead.objects.create(
        name='Old Tuition fee', code='OLD_TUITION_PKG', academic_year=year2,
        program=prog, allowed_amounts=[9000], amount=Decimal('9000'),
    )

    admin = _make_user('pkg_admin_head', User.UserType.FACULTY, 'ADMIN_HEAD')
    accountant = _make_user('pkg_accountant', User.UserType.FACULTY, 'ACCOUNTANT')
    sysadmin = _make_user('pkg_sysadmin', User.UserType.FACULTY, superuser=True)
    role_student, _ = Role.objects.get_or_create(
        codename='STUDENT', defaults={'name': 'Student'})
    student_user = User.objects.create_user(
        username='pkg_student', password='Password123!', user_type=User.UserType.STUDENT)
    RoleAssignment.objects.create(
        user=student_user, role=role_student, status=RoleAssignment.Status.ACTIVE)
    student = Student.objects.create(
        user=student_user, enrollment_no='PRN-PKG-001',
        first_name='Asha', last_name='Kulkarni',
    )

    client = APIClient()

    def as_admin():
        client.force_authenticate(user=admin)

    def as_accountant():
        client.force_authenticate(user=accountant)

    def pkg_items(selected=None, last=True):
        picks = selected if selected is not None else list(heads.values())
        out = []
        for h in picks:
            amounts = h.allowed_amounts or [0]
            out.append({'head': str(h.id), 'amount': amounts[-1] if last else amounts[0]})
        return out

    return {
        'year': year, 'year2': year2, 'prog': prog,
        'heads': heads, 'other_year_head': other_year_head,
        'admin': admin, 'accountant': accountant, 'sysadmin': sysadmin,
        'student_user': student_user, 'student': student,
        'client': client, 'as_admin': as_admin, 'as_accountant': as_accountant,
        'pkg_items': pkg_items,
        'URL': '/api/v1/finance/fee-packages/',
    }


@pytest.mark.django_db
def test_admin_head_creates_package_total_computed_client_total_ignored(package_setup):
    """The canonical flow: four heads -> one package of 23675. Whatever total
    the client sends must be discarded; the server computes the real sum."""
    s = package_setup
    s['as_admin']()
    res = s['client'].post(s['URL'], {
        'name': 'Full Admission Regular',
        'academic_year': str(s['year'].id),
        'items': s['pkg_items'](),
        'total': '1.00',  # tampering attempt — must be ignored
    }, format='json')
    assert res.status_code == status.HTTP_201_CREATED, res.data
    assert res.data['total'] == '23675.00'
    resolved = res.data['items_resolved']
    assert resolved[0]['head_name'] == 'Tuition fee'
    assert resolved[0]['amount'] == 15000.0
    assert resolved[3]['head_name'] == 'Other fee (institutional)'
    assert resolved[3]['amount'] == 175.0
    assert all(r['is_valid'] for r in resolved)
    obj = FeePackage.objects.get(id=res.data['id'])
    assert obj.total == Decimal('23675.00')
    # name snapshot in storage refreshed to the live head name
    assert obj.items[0]['name'] == 'Tuition fee'


@pytest.mark.django_db
def test_accountant_cannot_write_packages_but_can_read(package_setup):
    """Write = Admin Head/Sysadmin only (403 for accountant). Read stays open
    to the fee desk so the accountant dropdown can be built."""
    s = package_setup
    items = s['pkg_items']()
    payload = {
        'name': 'Desk Attempt', 'academic_year': str(s['year'].id), 'items': items,
    }
    s['as_accountant']()
    res = s['client'].post(s['URL'], payload, format='json')
    assert res.status_code == status.HTTP_403_FORBIDDEN
    assert FeePackage.objects.count() == 0
    # Read allowed.
    list_res = s['client'].get(s['URL'])
    assert list_res.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_amount_must_be_an_allowed_preset(package_setup):
    s = package_setup
    s['as_admin']()
    head = s['heads']['Tuition fee']
    res = s['client'].post(s['URL'], {
        'name': 'Bad Amount', 'academic_year': str(s['year'].id),
        'items': [{'head': str(head.id), 'amount': 12345.5}],
    }, format='json')
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert 'is not an allowed preset' in str(res.data)


@pytest.mark.django_db
def test_inactive_head_rejected(package_setup):
    s = package_setup
    head = s['heads']['Development fee']
    head.is_active = False
    head.save(update_fields=['is_active'])
    s['as_admin']()
    res = s['client'].post(s['URL'], {
        'name': 'Inactive Head Pkg', 'academic_year': str(s['year'].id),
        'items': [{'head': str(head.id), 'amount': 5000}],
    }, format='json')
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert 'inactive or not configured' in str(res.data)


@pytest.mark.django_db
def test_head_from_other_year_rejected(package_setup):
    s = package_setup
    s['as_admin']()
    res = s['client'].post(s['URL'], {
        'name': 'Cross Year Pkg', 'academic_year': str(s['year'].id),
        'items': [{'head': str(s['other_year_head'].id), 'amount': 9000}],
    }, format='json')
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert 'inactive or not configured' in str(res.data)


@pytest.mark.django_db
def test_duplicate_head_within_package_rejected(package_setup):
    s = package_setup
    head = s['heads']['Other fee']
    s['as_admin']()
    res = s['client'].post(s['URL'], {
        'name': 'Dup Head Pkg', 'academic_year': str(s['year'].id),
        'items': [
            {'head': str(head.id), 'amount': 0},
            {'head': str(head.id), 'amount': 3500},
        ],
    }, format='json')
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert 'only once' in str(res.data)


@pytest.mark.django_db
def test_empty_items_rejected(package_setup):
    s = package_setup
    s['as_admin']()
    res = s['client'].post(s['URL'], {
        'name': 'Empty Pkg', 'academic_year': str(s['year'].id), 'items': [],
    }, format='json')
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert 'At least one fee head' in str(res.data)


@pytest.mark.django_db
def test_duplicate_name_same_year_clean_400(package_setup):
    """Same name twice in one year -> 400 from validation; a DB IntegrityError
    500 would be unacceptable at the desk."""
    s = package_setup
    s['as_admin']()
    payload = {
        'name': 'Full Admission', 'academic_year': str(s['year'].id),
        'items': s['pkg_items'](),
    }
    first = s['client'].post(s['URL'], payload, format='json')
    assert first.status_code == status.HTTP_201_CREATED, first.data
    second = s['client'].post(s['URL'], payload, format='json')
    assert second.status_code == status.HTTP_400_BAD_REQUEST
    assert 'already exists' in str(second.data)
    # Same name in a DIFFERENT year is fine.
    other_year = s['client'].post(s['URL'], {
        'name': 'Full Admission', 'academic_year': str(s['year2'].id),
        'items': [{'head': str(s['other_year_head'].id), 'amount': 9000}],
    }, format='json')
    assert other_year.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_head_rename_propagates_to_package(package_setup):
    """Renaming a head must flow into packages automatically (live name
    resolution), and editing the package refreshes its stored snapshot."""
    s = package_setup
    s['as_admin']()
    created = s['client'].post(s['URL'], {
        'name': 'Rename Pkg', 'academic_year': str(s['year'].id),
        'items': s['pkg_items'](),
    }, format='json')
    assert created.status_code == status.HTTP_201_CREATED
    pkg_id = created.data['id']

    head = s['heads']['Tuition fee']
    old_id = head.id
    head.name = 'Tuition Fee (Renamed)'
    head.save(update_fields=['name'])

    read_after_rename = s['client'].get(f"{s['URL']}{pkg_id}/")
    resolved = read_after_rename.data['items_resolved']
    renamed = next(r for r in resolved if r['head'] == str(old_id))
    assert renamed['head_name'] == 'Tuition Fee (Renamed)'
    assert renamed['is_valid'] is True

    # Editing the package (resave same items) refreshes the stored snapshot.
    patch = s['client'].patch(f"{s['URL']}{pkg_id}/", {
        'items': s['pkg_items'](),
    }, format='json')
    assert patch.status_code == status.HTTP_200_OK, patch.data
    obj = FeePackage.objects.get(id=pkg_id)
    assert obj.items[0]['name'] == 'Tuition Fee (Renamed)'


@pytest.mark.django_db
def test_inactive_package_hidden_from_accountant_visible_to_admin(package_setup):
    s = package_setup
    s['as_admin']()
    s['client'].post(s['URL'], {
        'name': 'Live Pkg', 'academic_year': str(s['year'].id),
        'items': s['pkg_items'](),
    }, format='json')
    made_inactive = s['client'].post(s['URL'], {
        'name': 'Draft Pkg', 'academic_year': str(s['year'].id),
        'items': s['pkg_items'](last=False),
        'is_active': False,
    }, format='json')
    assert made_inactive.status_code == status.HTTP_201_CREATED

    s['as_accountant']()
    rows = s['client'].get(s['URL']).data['results']
    names = {r['name'] for r in rows}
    assert 'Live Pkg' in names and 'Draft Pkg' not in names

    s['client'].force_authenticate(user=s['admin'])
    admin_rows = s['client'].get(s['URL']).data['results']
    assert {'Live Pkg', 'Draft Pkg'} <= {r['name'] for r in admin_rows}


@pytest.mark.django_db
def test_packages_filter_by_academic_year(package_setup):
    s = package_setup
    s['as_admin']()
    s['client'].post(s['URL'], {
        'name': 'Y26 Pkg', 'academic_year': str(s['year'].id),
        'items': s['pkg_items'](),
    }, format='json')
    s['client'].post(s['URL'], {
        'name': 'Y25 Pkg', 'academic_year': str(s['year2'].id),
        'items': [{'head': str(s['other_year_head'].id), 'amount': 9000}],
    }, format='json')
    s['as_accountant']()
    rows = s['client'].get(s['URL'], {'academic_year_id': str(s['year'].id)}).data['results']
    assert {r['name'] for r in rows} == {'Y26 Pkg'}


@pytest.mark.django_db
def test_package_breakdown_passes_assessment_validation_e2e(package_setup):
    """THE critical flow: admin creates the package, the accountant saves the
    assessment using exactly the package's resolved breakdown — it must pass
    head validation with zero manual entry, and the saved total must equal
    the package's server-computed total (receipt shows the same values)."""
    s = package_setup
    s['as_admin']()
    pkg = s['client'].post(s['URL'], {
        'name': 'Desk E2E', 'academic_year': str(s['year'].id),
        'items': s['pkg_items'](),
    }, format='json')
    assert pkg.status_code == status.HTTP_201_CREATED, pkg.data

    s['as_accountant']()
    breakdown = {
        it['head_name']: it['amount']
        for it in pkg.data['items_resolved'] if it['is_valid']
    }
    res = s['client'].post('/api/v1/finance/assessments/', {
        'student': str(s['student'].id),
        'academic_year': str(s['year'].id),
        'fee_breakdown': breakdown,
        'total_fee': pkg.data['total'],
    }, format='json')
    assert res.status_code in (200, 201), res.data
    assessment = StudentFeeAssessment.objects.get(
        student=s['student'], academic_year=s['year'])
    assert assessment.total_fee == Decimal('23675.00')
    assert assessment.fee_breakdown['Tuition fee'] == 15000
    assert assessment.fee_breakdown['Development fee'] == 5000
    assert assessment.fee_breakdown['Other fee'] == 3500
    assert assessment.fee_breakdown['Other fee (institutional)'] == 175
    # And no stray heads leaked into the breakdown.
    assert set(assessment.fee_breakdown.keys()) == set(breakdown.keys())


@pytest.mark.django_db
def test_partial_package_works_with_heads_not_covered(package_setup):
    """A package covering only some heads saves fine: uncovered heads are
    simply absent from the breakdown (validate-against-heads only checks
    provided names — matching the desk's '0 for uncovered heads' display)."""
    s = package_setup
    s['as_admin']()
    pkg = s['client'].post(s['URL'], {
        'name': 'Tuition Only', 'academic_year': str(s['year'].id),
        'items': [{'head': str(s['heads']['Tuition fee'].id), 'amount': 7500}],
    }, format='json')
    assert pkg.status_code == status.HTTP_201_CREATED, pkg.data
    assert pkg.data['total'] == '7500.00'

    s['as_accountant']()
    res = s['client'].post('/api/v1/finance/assessments/', {
        'student': str(s['student'].id),
        'academic_year': str(s['year'].id),
        'fee_breakdown': {'Tuition fee': 7500},
        'total_fee': pkg.data['total'],
    }, format='json')
    assert res.status_code in (200, 201), res.data


@pytest.mark.django_db
def test_package_write_actions_fully_audited(package_setup):
    s = package_setup
    from apps.audit.models import AuditLog
    s['as_admin']()
    created = s['client'].post(s['URL'], {
        'name': 'Audit Pkg', 'academic_year': str(s['year'].id),
        'items': s['pkg_items'](),
    }, format='json')
    assert created.status_code == status.HTTP_201_CREATED
    pkg_id = created.data['id']
    s['client'].patch(f"{s['URL']}{pkg_id}/", {
        'items': s['pkg_items'](last=False),
    }, format='json')
    s['client'].delete(f"{s['URL']}{pkg_id}/")
    actions = list(
        AuditLog.objects.filter(target_type='FeePackage')
        .order_by('timestamp').values_list('action', flat=True)
    )
    assert actions == ['CREATE', 'UPDATE', 'DELETE'], actions


@pytest.mark.django_db
def test_broken_package_marked_not_valid_when_head_removed(package_setup):
    """Deleting a head leaves its id dangling inside stored items. The read
    side must flag is_valid=False (desk shows 'misconfigured') instead of
    crashing — while write-side validation still refuses to accept the
    dangling id."""
    s = package_setup
    s['as_admin']()
    head = s['heads']['Other fee']
    created = s['client'].post(s['URL'], {
        'name': 'Delete Head Pkg', 'academic_year': str(s['year'].id),
        'items': [{'head': str(head.id), 'amount': 3500}],
    }, format='json')
    assert created.status_code == status.HTTP_201_CREATED
    pkg_id = created.data['id']
    head.delete()
    read = s['client'].get(f"{s['URL']}{pkg_id}/")
    resolved = read.data['items_resolved']
    assert resolved[0]['is_valid'] is False
    assert resolved[0]['head_name'] == 'Other fee'  # snapshot fallback, never blank
    assert resolved[0]['amount'] == 3500.0
