"""
Views for Faculty domain.

Enforces:
- Scope-aware directory querysets.
- Self-profile access via /me/.
- Sensitive bank account unmasking with mandatory audit logging.
- IDOR prevention via scope checks.
"""
from django.db import models, transaction
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.audit.models import AuditLog
from apps.audit.services import audit_log
from apps.common.encryption import decrypt_value, encrypt_value, require_encryption_for_write
from django.utils import timezone
from apps.authentication.permissions import (
    HasScopeAccess,
    get_user_scopes,
    user_has_permission,
)
from apps.academic_structure.models import Department
from apps.authentication.models import PasswordHistory, Role, RoleAssignment, User
from apps.faculty.models import (
    Faculty,
    FacultyBankAccount,
    TeachingAssignment,
)
from apps.faculty.serializers import (
    FacultyCreateSerializer,
    FacultyListSerializer,
    FacultyProfileSerializer,
    TeachingAssignmentSerializer,
    TeachingAssignmentWriteSerializer,
)


class FacultyViewSet(viewsets.ModelViewSet):
    """
    Faculty ViewSet supporting institute directory, profile composition,
    self-service /me/ endpoint, audited sensitive data reveal,
    and sysadmin-only faculty onboarding via POST /.
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = FacultyProfileSerializer

    def get_serializer_class(self):
        if self.action == 'list':
            return FacultyListSerializer
        if self.action == 'create':
            return FacultyCreateSerializer
        return FacultyProfileSerializer

    def create(self, request, *args, **kwargs):
        """Sysadmin-only faculty onboarding: User + Faculty + RoleAssignment."""
        scopes = get_user_scopes(request.user)
        allowed = (
            scopes['is_system_wide']
            or request.user.is_superuser
            or user_has_permission(request.user, 'faculty.create')
        )
        if not allowed:
            return Response(
                {'detail': 'Only Sysadmin can add faculty members.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = FacultyCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        department = Department.objects.filter(id=data['department_id']).first()
        if not department:
            return Response(
                {'department_id': 'Department not found.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            user = User(
                username=data['username'],
                email=data['official_email'],
                user_type=User.UserType.FACULTY,
                is_active=True,
                must_change_password=True,
            )
            # Initial password = employee_code (same convention as student
            # onboarding: identifier-as-password + forced change on first login).
            user.set_password(data['employee_code'].strip())
            user.save()
            PasswordHistory.objects.create(user=user, password_hash=user.password)

            faculty = Faculty.objects.create(
                user=user,
                employee_code=data['employee_code'].strip(),
                first_name=data['first_name'].strip(),
                middle_name=(data.get('middle_name') or '').strip(),
                last_name=data['last_name'].strip(),
                department=department,
                designation=data['designation'],
                employment_type=data.get('employment_type') or Faculty.EmploymentType.REGULAR,
                employment_status=Faculty.EmploymentStatus.ACTIVE,
                date_of_joining=data['date_of_joining'],
                official_email=data['official_email'].strip(),
                mobile=(data.get('mobile') or '').strip(),
                is_active=True,
            )

            role = Role.objects.filter(codename=data['initial_role']).first()
            RoleAssignment.objects.create(
                user=user,
                role=role,
                department_id=department.id,
                division_id=data.get('division_id'),
                status=RoleAssignment.Status.ACTIVE,
                assigned_by=request.user if request.user.is_authenticated else None,
                reason='Sysadmin faculty onboarding',
            )
            # HOD / CLASS_TEACHER / ACCOUNTANT / ADMIN_HEAD also hold base FACULTY.
            # EMPLOYEE must NOT get base FACULTY — it carries student.view/results.view.
            if data['initial_role'] not in ('FACULTY', 'EMPLOYEE'):
                base_role = Role.objects.filter(codename='FACULTY').first()
                if base_role:
                    RoleAssignment.objects.get_or_create(
                        user=user,
                        role=base_role,
                        department_id=department.id,
                        defaults={
                            'status': RoleAssignment.Status.ACTIVE,
                            'assigned_by': request.user if request.user.is_authenticated else None,
                            'reason': 'Base faculty role for operational role holder',
                        },
                    )

            audit_log(
                request=request,
                actor=request.user,
                action=AuditLog.Action.CREATE,
                target_type='Faculty',
                target_id=str(faculty.id),
                target_display=f'{faculty.display_name} ({faculty.employee_code})',
                new_value={
                    'employee_code': faculty.employee_code,
                    'official_email': faculty.official_email,
                    'department': department.code,
                    'designation': faculty.designation,
                    'username': user.username,
                    'role': data['initial_role'],
                },
                reason='Sysadmin faculty onboarding',
                description=(
                    f"Sysadmin created faculty '{faculty.display_name}' "
                    f"({faculty.employee_code}) with role {data['initial_role']}."
                ),
            )

        output = FacultyProfileSerializer(faculty).data
        output['username'] = user.username
        output['must_change_password'] = True
        return Response(output, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        return Response(
            {'detail': 'Faculty updates are not supported via this endpoint yet.'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def partial_update(self, request, *args, **kwargs):
        return Response(
            {'detail': 'Faculty updates are not supported via this endpoint yet.'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def destroy(self, request, *args, **kwargs):
        return Response(
            {'detail': 'Faculty records cannot be deleted.'},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated:
            return Faculty.objects.none()

        qs = Faculty.objects.select_related('department').prefetch_related(
            'personal_details',
            'research_profile',
            'addresses',
            'qualifications',
            'experiences',
            'publications',
            'guidance_records',
            'bank_accounts',
            'documents',
            'teaching_assignments__academic_year',
            'teaching_assignments__department',
            'teaching_assignments__semester',
            'teaching_assignments__division',
        ).filter(is_active=True)

        scopes = get_user_scopes(user)

        # 1. Sysadmin / Admin Head / Accountant: institute-wide
        if scopes['is_system_wide'] or 'ADMIN_HEAD' in scopes['roles'] or 'ACCOUNTANT' in scopes['roles']:
            return self._apply_filters(qs)

        # 2. HOD: department-scoped
        if 'HOD' in scopes['roles']:
            dept_ids = scopes['department_ids']
            if dept_ids:
                return self._apply_filters(qs.filter(department_id__in=dept_ids))
            return self._apply_filters(qs)

        # 3. Faculty / Class Teacher / Student: institute directory (read-only)
        return self._apply_filters(qs)

    def _apply_filters(self, qs):
        dept = self.request.query_params.get('department_id')
        designation = self.request.query_params.get('designation')
        search = self.request.query_params.get('search')

        if dept:
            qs = qs.filter(department_id=dept)
        if designation:
            qs = qs.filter(designation=designation)
        if search:
            search = search.strip()
            qs = qs.filter(
                models.Q(display_name__icontains=search)
                | models.Q(employee_code__icontains=search)
                | models.Q(official_email__icontains=search)
            )
        return qs.distinct()

    @action(detail=False, methods=['get'], url_path='me')
    def me(self, request):
        """Retrieve the authenticated faculty member's own profile."""
        try:
            faculty = Faculty.objects.get(user_id=request.user.id, is_active=True)
        except Faculty.DoesNotExist:
            return Response(
                {'detail': 'Faculty profile not associated with this account.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = FacultyProfileSerializer(faculty)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['patch'], url_path='me/update')
    def update_me(self, request):
        """
        Faculty self-service profile update (own record only).

        Editable: names (first/middle/last/display_name), department,
        designation, contact (mobile, personal/official email,
        residential telephone, date_of_joining), personal details,
        permanent/correspondence addresses, primary bank account,
        qualifications (UG/PG/PHD/OTHER upsert), research_profile
        (paper counts + achievements), identity_documents (photo /
        signature filenames + Aadhaar / PAN numbers + filenames).
        Locked (silently ignored): employee_code, employment_type/status,
        experiences, publications, guidance, teaching assignments.
        Empty / placeholder values mean "no change" (partial PATCH).
        All changes are audited.
        """
        import re

        from django.core.exceptions import ValidationError as DjangoValidationError
        from django.core.validators import validate_email
        from rest_framework.exceptions import ValidationError

        try:
            faculty = Faculty.objects.get(user_id=request.user.id, is_active=True)
        except Faculty.DoesNotExist:
            return Response(
                {'detail': 'Faculty profile not associated with this account.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        data = request.data or {}
        changed = []

        def clean_mobile(value, field_name):
            value = str(value or '').strip().replace(' ', '')
            if value and not re.fullmatch(r'\+?\d{10,15}', value):
                raise ValidationError({field_name: 'Enter a valid 10-15 digit mobile number.'})
            return value

        with transaction.atomic():
            # 1. Top-level identity + contact fields.
            for field_name in ('first_name', 'middle_name', 'last_name'):
                if field_name in data:
                    value = str(data.get(field_name) or '').strip()
                    if field_name in ('first_name', 'last_name') and not value:
                        raise ValidationError({field_name: 'This field cannot be empty.'})
                    if getattr(faculty, field_name) != value:
                        setattr(faculty, field_name, value)
                        changed.append(field_name)

            # Single-string display name (frontend "Faculty Name" input):
            # split into parts so directory/search (which read display_name
            # live) stay in sync with first/middle/last.
            if 'display_name' in data and 'first_name' not in data and 'last_name' not in data:
                full = str(data.get('display_name') or '').strip()
                if not full:
                    raise ValidationError({'display_name': 'Faculty name cannot be empty.'})
                parts = full.split()
                first = parts[0] if parts else ''
                last = parts[-1] if len(parts) > 1 else ''
                middle = ' '.join(parts[1:-1]) if len(parts) > 2 else ''
                if faculty.first_name != first:
                    faculty.first_name = first
                    changed.append('first_name')
                if faculty.middle_name != middle:
                    faculty.middle_name = middle
                    changed.append('middle_name')
                if faculty.last_name != last:
                    faculty.last_name = last
                    changed.append('last_name')
                if faculty.display_name != full:
                    faculty.display_name = full
                    changed.append('display_name')
            elif 'display_name' in data:
                full = str(data.get('display_name') or '').strip()
                if full and faculty.display_name != full:
                    faculty.display_name = full
                    changed.append('display_name')

            # Department: accept id, code, or name.
            # Production-grade PATCH: empty / placeholder strings mean
            # "no change", never a lookup for "Select Department".
            _DEPT_PLACEHOLDERS = {'', 'select', 'select department', 'select department *'}
            dept_val = data.get('department_id', data.get('department', None))
            if dept_val not in (None, ''):
                dept_raw = str(dept_val).strip()
                if dept_raw.lower() not in _DEPT_PLACEHOLDERS:
                    dept = None
                    try:
                        dept = Department.objects.filter(id=dept_raw).first()
                    except Exception:
                        dept = None
                    if dept is None:
                        dept = Department.objects.filter(code__iexact=dept_raw).first()
                    if dept is None:
                        dept = Department.objects.filter(name__iexact=dept_raw).first()
                    if dept is None:
                        raise ValidationError({'department': 'Department not found.'})
                    if faculty.department_id != dept.id:
                        faculty.department = dept
                        changed.append('department')

            # Designation: accept code (LECTURER) or display (Lecturer).
            # Empty / placeholder means "no change".
            if 'designation' in data and data.get('designation') not in (None, ''):
                raw = str(data.get('designation') or '').strip()
                if raw.lower() in ('select', 'select designation'):
                    raw = ''
                if raw != '':
                    code = raw.strip().upper().replace(' ', '_').replace('-', '_')
                    valid_codes = {c for c, _ in Faculty.Designation.choices}
                    display_map = {str(disp).strip().upper(): c for c, disp in Faculty.Designation.choices}
                    # Special-case common UI labels.
                    display_map.setdefault('HEAD OF DEPARTMENT (HOD)', Faculty.Designation.HOD)
                    display_map.setdefault('HEAD OF DEPARTMENT', Faculty.Designation.HOD)
                    resolved = None
                    if raw.strip().upper() in display_map:
                        resolved = display_map[raw.strip().upper()]
                    elif code in valid_codes:
                        resolved = code
                    if resolved is None:
                        raise ValidationError({'designation': 'Invalid designation.'})
                    if faculty.designation != resolved:
                        faculty.designation = resolved
                        changed.append('designation')

            if 'mobile' in data:
                value = clean_mobile(data.get('mobile'), 'mobile')
                if faculty.mobile != value:
                    faculty.mobile = value
                    changed.append('mobile')

            for email_field in ('personal_email', 'official_email'):
                if email_field in data:
                    value = str(data.get(email_field) or '').strip()
                    if value:
                        try:
                            validate_email(value)
                        except DjangoValidationError:
                            raise ValidationError({email_field: 'Enter a valid email address.'})
                        if email_field == 'official_email':
                            qs = Faculty.objects.filter(official_email__iexact=value).exclude(id=faculty.id)
                            if qs.exists():
                                raise ValidationError({email_field: 'Official email already in use.'})
                    if getattr(faculty, email_field) != value:
                        setattr(faculty, email_field, value)
                        changed.append(email_field)

            if 'residential_telephone' in data:
                value = str(data.get('residential_telephone') or '').strip()
                if faculty.residential_telephone != value:
                    faculty.residential_telephone = value
                    changed.append('residential_telephone')

            if 'date_of_joining' in data and data.get('date_of_joining') not in (None, ''):
                try:
                    import datetime as _dt
                    doj = data.get('date_of_joining')
                    doj = doj if hasattr(doj, 'year') else _dt.date.fromisoformat(str(doj))
                except ValueError:
                    raise ValidationError({'date_of_joining': 'Use YYYY-MM-DD format.'})
                if faculty.date_of_joining != doj:
                    faculty.date_of_joining = doj
                    changed.append('date_of_joining')

            # Keep display_name in sync when names changed without explicit display_name.
            if 'display_name' not in data and any(c in changed for c in ('first_name', 'middle_name', 'last_name')):
                parts = [faculty.first_name, faculty.middle_name, faculty.last_name]
                faculty.display_name = ' '.join(p for p in parts if p).strip()
                if 'display_name' not in changed:
                    changed.append('display_name')

            faculty.save()

            # 2. Personal details (create row if missing).
            personal_data = data.get('personal') or {}
            if isinstance(personal_data, dict) and personal_data:
                from apps.faculty.models import FacultyPersonalDetail
                allowed = {
                    'date_of_birth', 'gender', 'nationality',
                    'domicile_state', 'constitutional_category', 'blood_group',
                }
                try:
                    personal = faculty.personal_details
                    _personal_is_new = False
                except FacultyPersonalDetail.DoesNotExist:
                    personal = FacultyPersonalDetail(
                        faculty=faculty,
                        date_of_birth=faculty.date_of_joining,
                        gender=FacultyPersonalDetail.Gender.MALE,
                    )
                    _personal_is_new = True
                _personal_touched = False
                for field_name, value in personal_data.items():
                    if field_name not in allowed:
                        continue
                    # PATCH semantics: empty / placeholder means "no change",
                    # never wipe or 400 on "-00-00" / "" from untouched dropdowns.
                    if value is None:
                        continue
                    if isinstance(value, str):
                        _v = value.strip()
                        if _v == '' or _v == '-00-00' or _v.lower() in ('select', 'select department'):
                            continue
                        value = _v
                    if field_name == 'gender':
                        value = str(value or '').strip().upper()
                        if value == '':
                            continue
                        if value not in ('MALE', 'FEMALE', 'OTHER'):
                            raise ValidationError({'personal.gender': 'Must be MALE, FEMALE or OTHER.'})
                    elif field_name == 'date_of_birth':
                        if not value:
                            continue
                        try:
                            import datetime as _dt2
                            _s = str(value).strip()
                            # Guard junk built by empty dropdowns ("-00-00", "None-00-00").
                            if '00' in _s.split('-') or 'None' in _s:
                                continue
                            dob = value if hasattr(value, 'year') else _dt2.date.fromisoformat(_s)
                        except ValueError:
                            raise ValidationError({'personal.date_of_birth': 'Use YYYY-MM-DD format.'})
                        if dob > __import__('datetime').date.today():
                            raise ValidationError({'personal.date_of_birth': 'Date of birth cannot be in the future.'})
                        value = dob
                    elif isinstance(value, str):
                        value = value.strip()
                        if value == '':
                            continue
                    if getattr(personal, field_name) != value:
                        setattr(personal, field_name, value)
                        changed.append(f'personal.{field_name}')
                    _personal_touched = True
                # Only create/save the row when the client actually sent a
                # usable value; untouched forms must not conjure empty rows.
                if _personal_touched:
                    personal.save()

            # 3. Addresses (permanent / correspondence).
            from apps.faculty.models import FacultyAddress
            addr_payload = {}
            if isinstance(data.get('addresses'), dict):
                addr_payload = data.get('addresses') or {}
            for alias, atype in (
                ('permanent_address', FacultyAddress.AddressType.PERMANENT),
                ('correspondence_address', FacultyAddress.AddressType.CORRESPONDENCE),
                ('permanent', FacultyAddress.AddressType.PERMANENT),
                ('correspondence', FacultyAddress.AddressType.CORRESPONDENCE),
            ):
                block = addr_payload.get(alias) if isinstance(addr_payload, dict) else None
                if block is None and isinstance(data.get(alias), dict):
                    block = data.get(alias)
                if not isinstance(block, dict) or not block:
                    continue
                normalized = dict(block)
                # Frontend aliases: address -> address_line_1.
                if 'address' in normalized and 'address_line_1' not in normalized:
                    normalized['address_line_1'] = normalized.pop('address')
                # All-blank block means "no change" — never create an empty
                # address row or 400 on untouched forms.
                if not any(str(v or '').strip() for v in normalized.values()):
                    continue
                allowed_addr = {'address_line_1', 'address_line_2', 'district', 'state', 'pincode'}
                # Skip placeholder-only address lines ("Select", etc).
                _line = str(normalized.get('address_line_1', '') or '').strip()
                if _line.lower() in ('select',):
                    continue
                address, _ = faculty.addresses.get_or_create(
                    address_type=atype,
                    defaults={'address_line_1': '', 'pincode': ''},
                )
                _addr_touched = False
                for field_name, value in normalized.items():
                    if field_name not in allowed_addr:
                        continue
                    value = str(value or '').strip()
                    if value == '':
                        continue
                    if field_name == 'address_line_1' and not value:
                        raise ValidationError({f'addresses.{alias}.address_line_1': 'Address cannot be empty.'})
                    if field_name == 'pincode' and value and not re.fullmatch(r'\d{6}', value):
                        raise ValidationError({f'addresses.{alias}.pincode': 'Pincode must be 6 digits.'})
                    if getattr(address, field_name) != value:
                        setattr(address, field_name, value)
                        changed.append(f'addresses.{alias}.{field_name}')
                    _addr_touched = True
                if _addr_touched:
                    # New row without a real address line is useless — drop it.
                    if not str(address.address_line_1 or '').strip():
                        address.delete()
                    else:
                        address.save()

            # 4. Primary bank account (create if missing; number re-masked).
            # All-blank bank payloads mean "no change" — never create empty rows.
            bank_data = data.get('bank') or {}
            if isinstance(bank_data, dict) and bank_data:
                from apps.faculty.models import FacultyBankAccount
                allowed_bank = {
                    'account_holder_name', 'bank_name', 'branch_name',
                    'ifsc_code', 'account_number',
                }
                _usable_bank = {
                    k: str(v or '').strip()
                    for k, v in bank_data.items()
                    if k in allowed_bank and str(v or '').strip() != ''
                }
                # Ignore echoed masked numbers ("XXXXXXXX4412").
                if 'account_number' in _usable_bank and 'X' in _usable_bank['account_number'].upper():
                    del _usable_bank['account_number']
                if _usable_bank:
                    bank = faculty.bank_accounts.filter(is_primary=True).first()
                    if bank is None:
                        if not _usable_bank.get('account_number'):
                            raise ValidationError({'bank.account_number': 'Account number is required.'})
                        bank = FacultyBankAccount(
                            faculty=faculty,
                            account_holder_name='',
                            bank_name='',
                            ifsc_code='',
                            account_number_encrypted='',
                            account_number_masked='',
                            is_primary=True,
                        )
                    _bank_touched = False
                    for field_name, value in bank_data.items():
                        if field_name not in allowed_bank:
                            continue
                        value = str(value or '').strip()
                        if value == '':
                            continue
                        if field_name == 'account_number' and value:
                            # Skip masked display values echoed back (contain X).
                            if 'X' in value.upper():
                                continue
                            digits = re.sub(r'\D', '', value)
                            if not 9 <= len(digits) <= 18:
                                raise ValidationError({'bank.account_number': 'Account number must be 9-18 digits.'})
                            require_encryption_for_write()
                            bank.account_number_encrypted = encrypt_value(digits)
                            bank.account_number_masked = f'XXXXXXXX{digits[-4:]}'
                            changed.append('bank.account_number')
                            _bank_touched = True
                        elif field_name == 'ifsc_code' and value:
                            value = value.upper()
                            if not re.fullmatch(r'[A-Z]{4}0[A-Z0-9]{6}', value):
                                raise ValidationError({'bank.ifsc_code': 'IFSC must look like SBIN0001234.'})
                            if bank.ifsc_code != value:
                                bank.ifsc_code = value
                                changed.append('bank.ifsc_code')
                            _bank_touched = True
                        elif field_name in ('account_holder_name', 'bank_name', 'branch_name'):
                            if getattr(bank, field_name) != value:
                                setattr(bank, field_name, value)
                                changed.append(f'bank.{field_name}')
                            _bank_touched = True
                    if _bank_touched:
                        bank.save()

            # 5. Qualifications: upsert one row per level (UG/PG/PHD/OTHER).
            # Frontend sends {"graduation": {...}, "post_graduation": {...},
            # "phd": {...}, "other": {...}} with degree_name, specialization,
            # class_or_grade, institution_university, passing_year.
            # All-blank block = no change (never delete on untouched forms).
            qual_data = data.get('qualifications') or {}
            if isinstance(qual_data, dict) and qual_data:
                from apps.faculty.models import FacultyQualification
                import datetime as _dtq
                _level_map = {
                    'graduation': FacultyQualification.Level.UG,
                    'ug': FacultyQualification.Level.UG,
                    'post_graduation': FacultyQualification.Level.PG,
                    'postgraduation': FacultyQualification.Level.PG,
                    'pg': FacultyQualification.Level.PG,
                    'phd': FacultyQualification.Level.PHD,
                    'other': FacultyQualification.Level.OTHER,
                }
                _current_year = _dtq.date.today().year
                for _key, _level in _level_map.items():
                    if _key not in qual_data:
                        continue
                    _block = qual_data.get(_key) or {}
                    if not isinstance(_block, dict):
                        continue
                    _deg = str(_block.get('degree_name', '') or '').strip()
                    _spec = str(_block.get('specialization', '') or '').strip()
                    _cls = str(_block.get('class_or_grade', '') or '').strip()
                    _uni = str(_block.get('institution_university', '') or '').strip()
                    _py = _block.get('passing_year', '')
                    _py = str(_py or '').strip()
                    if not _deg and not _spec and not _cls and not _uni and not _py:
                        continue
                    if not _deg:
                        raise ValidationError({f'qualifications.{_key}.degree_name': 'Course is required.'})
                    if not _uni or _uni.lower() in ('select',):
                        raise ValidationError({f'qualifications.{_key}.institution_university': 'University is required.'})
                    if not _py:
                        raise ValidationError({f'qualifications.{_key}.passing_year': 'Passing year is required.'})
                    try:
                        _py_int = int(_py)
                    except (TypeError, ValueError):
                        raise ValidationError({f'qualifications.{_key}.passing_year': 'Passing year must be a year.'})
                    if not 1950 <= _py_int <= _current_year + 1:
                        raise ValidationError({f'qualifications.{_key}.passing_year': f'Passing year must be 1950-{_current_year + 1}.'})
                    _row = FacultyQualification.objects.filter(faculty=faculty, qualification_level=_level).first()
                    if _row is None:
                        _row = FacultyQualification(
                            faculty=faculty,
                            qualification_level=_level,
                            degree_name=_deg,
                            specialization=_spec,
                            institution_university=_uni,
                            passing_year=_py_int,
                            class_or_grade=_cls or 'First Class',
                        )
                        _row.save()
                        changed.append(f'qualifications.{_key}')
                    else:
                        _dirty = False
                        for _f, _nv in (
                            ('degree_name', _deg),
                            ('specialization', _spec),
                            ('institution_university', _uni),
                            ('passing_year', _py_int),
                            ('class_or_grade', _cls or _row.class_or_grade),
                        ):
                            if getattr(_row, _f) != _nv:
                                setattr(_row, _f, _nv)
                                _dirty = True
                        if _dirty:
                            _row.save()
                            changed.append(f'qualifications.{_key}')

            # 6. Research profile: counts + free-text achievements (one row).
            # Empty payload = no change. Counts must be 0-100000 integers.
            research_data = data.get('research_profile') or {}
            if isinstance(research_data, dict) and research_data:
                from apps.faculty.models import FacultyResearchProfile
                _count_fields = (
                    'national_journal_papers', 'international_journal_papers',
                    'national_conference_papers', 'international_conference_papers',
                )
                _text_fields = (
                    'books_patents', 'professional_membership',
                    'consultancy_activities', 'awards',
                    'grants_fetched', 'interaction_institution',
                )
                _clean = {}
                for _f in _count_fields:
                    if _f not in research_data:
                        continue
                    _raw = research_data.get(_f)
                    if _raw is None or (isinstance(_raw, str) and _raw.strip() == ''):
                        continue
                    try:
                        _iv = int(str(_raw).strip())
                    except (TypeError, ValueError):
                        raise ValidationError({f'research_profile.{_f}': 'Must be a whole number.'})
                    if not 0 <= _iv <= 100000:
                        raise ValidationError({f'research_profile.{_f}': 'Must be 0-100000.'})
                    _clean[_f] = _iv
                for _f in _text_fields:
                    if _f not in research_data:
                        continue
                    _v = research_data.get(_f)
                    _v = '' if _v is None else str(_v).strip()
                    # Empty text = no change (avoid wiping achievements).
                    if _v == '':
                        continue
                    if len(_v) > 5000:
                        raise ValidationError({f'research_profile.{_f}': 'Too long (max 5000 chars).'})
                    _clean[_f] = _v
                if _clean:
                    _rp, _ = FacultyResearchProfile.objects.get_or_create(faculty=faculty)
                    for _f, _v in _clean.items():
                        if getattr(_rp, _f) != _v:
                            setattr(_rp, _f, _v)
                            changed.append(f'research_profile.{_f}')
                    _rp.save()

            # 7. Identity documents: photo/signature filenames + Aadhaar/PAN
            # numbers + filenames, stored as FacultyDocument rows
            # (PHOTO/SIGNATURE/AADHAAR/PAN, is_verified=False until admin).
            # Frontend only picks filenames (no bytes yet); file_path stores
            # the filename placeholder. Empty payload = no change.
            identity_data = data.get('identity_documents') or {}
            if isinstance(identity_data, dict) and identity_data:
                from apps.faculty.models import FacultyDocument
                _aad = str(identity_data.get('aadhaar_number', '') or '').strip().replace(' ', '')
                _pan = str(identity_data.get('pan_number', '') or '').strip().upper()
                _photo = str(identity_data.get('photo_filename', '') or '').strip()
                _sig = str(identity_data.get('signature_filename', '') or '').strip()
                _aad_file = str(identity_data.get('aadhaar_filename', '') or '').strip()
                _pan_file = str(identity_data.get('pan_filename', '') or '').strip()
                if _aad:
                    if not re.fullmatch(r'[2-9]\d{11}', _aad):
                        raise ValidationError({'identity_documents.aadhaar_number': 'Aadhaar must be 12 digits starting 2-9.'})
                if _pan:
                    if not re.fullmatch(r'[A-Z]{5}[0-9]{4}[A-Z]', _pan):
                        raise ValidationError({'identity_documents.pan_number': 'PAN must look like ABCDE1234F.'})
                for _fn, _key in ((_photo, 'photo'), (_sig, 'sig'), (_aad_file, 'aadhaar'), (_pan_file, 'pan')):
                    if _fn and len(_fn) > 255:
                        raise ValidationError({f'identity_documents.{_key}_filename': 'Filename too long.'})
                if _photo and not re.search(r'\.(jpg|jpeg|png)$', _photo, re.IGNORECASE):
                    raise ValidationError({'identity_documents.photo_filename': 'Photo must be JPG/PNG.'})
                if _sig and not re.search(r'\.(jpg|jpeg|png)$', _sig, re.IGNORECASE):
                    raise ValidationError({'identity_documents.signature_filename': 'Signature must be JPG/PNG.'})
                if _aad_file and not _aad_file.lower().endswith('.pdf'):
                    raise ValidationError({'identity_documents.aadhaar_filename': 'Aadhaar file must be PDF.'})
                if _pan_file and not _pan_file.lower().endswith('.pdf'):
                    raise ValidationError({'identity_documents.pan_filename': 'PAN file must be PDF.'})

                def _mask_number(_dtype, _number):
                    if not _number:
                        return ''
                    if _dtype == FacultyDocument.DocType.AADHAAR:
                        return f'XXXX-XXXX-{_number[-4:]}'
                    if _dtype == FacultyDocument.DocType.PAN:
                        return f'XXXXX{_number[-4:]}'
                    return ''

                def _upsert_doc(_dtype, _title, _number, _fpath):
                    if not _fpath and not _number:
                        return
                    if _number:
                        # New ID numbers must never land in plaintext storage.
                        require_encryption_for_write()
                    _doc = FacultyDocument.objects.filter(faculty=faculty, document_type=_dtype).order_by('-version').first()
                    _mime = 'application/pdf'
                    if _fpath.lower().endswith(('.jpg', '.jpeg')):
                        _mime = 'image/jpeg'
                    elif _fpath.lower().endswith('.png'):
                        _mime = 'image/png'
                    _masked = _mask_number(_dtype, _number) if _number else ''
                    if _doc is None:
                        FacultyDocument.objects.create(
                            faculty=faculty,
                            document_type=_dtype,
                            title=_title,
                            document_number='',  # legacy column left blank for new rows
                            document_number_encrypted=encrypt_value(_number) if _number else '',
                            document_number_masked=_masked,
                            file_path=_fpath or _title,
                            mime_type=_mime,
                            is_verified=False,
                        )
                        changed.append(f'documents.{_dtype.lower()}')
                    else:
                        _dirty = False
                        # Migrate legacy plaintext rows on touch.
                        _legacy = str(getattr(_doc, 'document_number', '') or '').strip()
                        if _legacy and not _doc.document_number_encrypted:
                            _doc.document_number_encrypted = encrypt_value(_legacy)
                            _doc.document_number_masked = _mask_number(_dtype, _legacy)
                            _doc.document_number = ''
                            _dirty = True
                        if _number:
                            _cur = decrypt_value(_doc.document_number_encrypted) if _doc.document_number_encrypted else ''
                            if _cur != _number:
                                _doc.document_number_encrypted = encrypt_value(_number)
                                _doc.document_number_masked = _masked
                                _dirty = True
                        if _fpath and _doc.file_path != _fpath:
                            _doc.file_path = _fpath
                            _doc.mime_type = _mime
                            _dirty = True
                        if _doc.title != _title:
                            _doc.title = _title
                            _dirty = True
                        if _dirty:
                            _doc.is_verified = False
                            _doc.save()
                            changed.append(f'documents.{_dtype.lower()}')

                _upsert_doc(FacultyDocument.DocType.PHOTO, 'Passport Photo', '', _photo)
                _upsert_doc(FacultyDocument.DocType.SIGNATURE, 'Signature', '', _sig)
                _upsert_doc(FacultyDocument.DocType.AADHAAR, 'Aadhaar Card', _aad, _aad_file)
                _upsert_doc(FacultyDocument.DocType.PAN, 'PAN Card', _pan, _pan_file)

        if changed:
            audit_log(
                request=request,
                actor=request.user,
                action=AuditLog.Action.UPDATE,
                target_type='Faculty',
                target_id=str(faculty.id),
                target_display=faculty.display_name,
                reason='Faculty self-service profile update',
                description=f"Faculty updated own profile: {', '.join(sorted(set(changed)))}.",
            )

        serializer = FacultyProfileSerializer(faculty)
        return Response(
            {'detail': 'Profile updated successfully.', 'changed': sorted(set(changed)), 'profile': serializer.data},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=['post'], url_path='reveal')
    def reveal_sensitive(self, request, pk=None):
        """
        Reveal unmasked sensitive bank details with audit logging.
        Requires 'faculty.sensitive_reveal' permission or sysadmin.
        """
        faculty = self.get_object()

        # Authorization check
        if not user_has_permission(request.user, 'faculty.sensitive_reveal') and not request.user.is_superuser:
            return Response(
                {'detail': 'You do not have permission to reveal sensitive faculty financial data.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        reason = str(request.data.get('reason', '') or '').strip()
        if len(reason) < 5:
            return Response(
                {'detail': 'A justification reason of at least 5 characters is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from apps.audit.services import sensitive_reveal_allowed
        from apps.common.http import no_store
        if not sensitive_reveal_allowed(request.user):
            return Response(
                {'detail': 'Too many reveals in the last hour. Try again later.'},
                status=429,
            )

        # Audit log the event
        audit_log(
            request=request,
            actor=request.user,
            action=AuditLog.Action.SENSITIVE_REVEAL,
            target_type='Faculty',
            target_id=str(faculty.id),
            target_display=faculty.display_name,
            reason=reason,
            description=f"Sensitive bank account reveal for faculty '{faculty.display_name}'.",
        )

        primary_bank = faculty.bank_accounts.filter(is_primary=True).first()

        return no_store(Response({
            'bank_account_number': (
                decrypt_value(primary_bank.account_number_encrypted)
                if primary_bank and getattr(primary_bank, 'account_number_encrypted', '') else None
            ),
            'revealed_at': timezone.now(),
            'message': 'Sensitive faculty bank details unmasked. Access has been recorded in the security audit trail.',
        }, status=status.HTTP_200_OK))

    # ─── Faculty identity document uploads (photo / signature / aadhaar / pan) ───
    # Same machinery as student documents: extension + magic bytes + Pillow
    # verify + PDF active-content scan, latest-only per type, bytes in
    # default_storage (local MEDIA_ROOT dev / S3 when set), metadata in row.
    # Limits (per UI instruction boxes, same code path as students):
    # PHOTO / SIGNATURE 150 KB (jpg/png); AADHAAR / PAN 300 KB (pdf).
    DOCUMENT_SIZE_LIMITS = {
        'PHOTO': 150 * 1024,
        'SIGNATURE': 150 * 1024,
        'AADHAAR': 300 * 1024,
        'PAN': 300 * 1024,
    }
    DOCUMENT_ALLOWED_EXTS = {
        'PHOTO': {'jpg', 'jpeg', 'png'},
        'SIGNATURE': {'jpg', 'jpeg', 'png'},
        'AADHAAR': {'pdf'},
        'PAN': {'pdf'},
    }

    def _doc_limit_for(self, doc_type):
        return self.DOCUMENT_SIZE_LIMITS.get(doc_type, 150 * 1024)

    def _get_owned_faculty(self, request):
        try:
            return Faculty.objects.get(user_id=request.user.id, is_active=True)
        except Faculty.DoesNotExist:
            return None

    def _validate_doc_content(self, content, ext):
        from rest_framework.exceptions import ValidationError
        if not content:
            raise ValidationError({'file': 'Empty file.'})
        head = bytes(content[:8])
        is_jpg = head[:3] == b'\xff\xd8\xff'
        is_png = head[:8] == b'\x89PNG\r\n\x1a\n'
        is_pdf = content[:5] == b'%PDF-'
        if ext in ('jpg', 'jpeg'):
            if not is_jpg:
                raise ValidationError({'file': 'File content is not a valid JPEG.'})
        elif ext == 'png':
            if not is_png:
                raise ValidationError({'file': 'File content is not a valid PNG.'})
        elif ext == 'pdf':
            if not is_pdf:
                raise ValidationError({'file': 'File content is not a valid PDF.'})
        else:
            raise ValidationError({'file': f'Extension .{ext} not allowed.'})
        if ext in ('jpg', 'jpeg', 'png'):
            try:
                from io import BytesIO
                from PIL import Image
                img = Image.open(BytesIO(content))
                img.verify()
            except Exception:
                raise ValidationError({'file': 'Corrupt or fake image file.'})
        if ext == 'pdf':
            lowered = content.lower()
            for marker in (b'/javascript', b'/js ', b'/launch', b'/embeddedfile', b'/xfa'):
                if marker in lowered:
                    raise ValidationError({'file': 'PDF contains active content and is not allowed.'})

    @action(detail=False, methods=['post'], url_path='me/documents/upload')
    def upload_own_document(self, request):
        from rest_framework.exceptions import ValidationError
        faculty = self._get_owned_faculty(request)
        if faculty is None:
            return Response(
                {'detail': 'Faculty profile not associated with this account.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        doc_type = str(request.data.get('document_type') or '').strip().upper()
        from apps.faculty.models import FacultyDocument
        valid_types = {'PHOTO', 'SIGNATURE', 'AADHAAR', 'PAN'}
        if doc_type not in valid_types:
            raise ValidationError({'document_type': f"Must be one of {sorted(valid_types)}."})
        uploaded_file = request.FILES.get('file')
        if not uploaded_file:
            raise ValidationError({'file': 'No file uploaded.'})
        max_bytes = self._doc_limit_for(doc_type)
        if uploaded_file.size > max_bytes:
            raise ValidationError({
                'file': f"File too large ({uploaded_file.size // 1024} KB). Max for {doc_type} is {max_bytes // 1024} KB."
            })
        if uploaded_file.size == 0:
            raise ValidationError({'file': 'Empty file.'})
        import hashlib
        import mimetypes
        import os
        import re as _re
        from django.core.files.storage import default_storage
        orig_name = getattr(uploaded_file, 'name', '') or 'upload'
        if len(orig_name) > 120:
            raise ValidationError({'file': 'Filename too long (max 120 chars).'})
        ext = (os.path.splitext(orig_name)[1] or '').lower().lstrip('.')
        allowed = self.DOCUMENT_ALLOWED_EXTS.get(doc_type, set())
        if ext not in allowed:
            raise ValidationError({'file': f"Extension .{ext or '?'} not allowed for {doc_type}. Allowed: {sorted(allowed)}."})
        uploaded_file.seek(0)
        content = uploaded_file.read()
        uploaded_file.seek(0)
        if not content:
            raise ValidationError({'file': 'Could not read uploaded file.'})
        self._validate_doc_content(content, ext)
        safe_base = _re.sub(r'[^A-Za-z0-9._-]', '_', orig_name)[-80:] or f'upload.{ext}'
        latest = faculty.documents.filter(document_type=doc_type).order_by('-version').first()
        version = (latest.version + 1) if latest else 1
        # Preserve encrypted ID numbers across re-uploads of the same type.
        keep_enc = getattr(latest, 'document_number_encrypted', '') if latest else ''
        keep_mask = getattr(latest, 'document_number_masked', '') if latest else ''
        if not keep_enc and latest and str(getattr(latest, 'document_number', '') or '').strip():
            keep_enc = encrypt_value(str(latest.document_number).strip())
            keep_mask = (
                f"XXXX-XXXX-{str(latest.document_number).strip()[-4:]}"
                if doc_type == 'AADHAAR'
                else f"XXXXX{str(latest.document_number).strip()[-4:]}"
            )
        rel_path = f"faculty_documents/{faculty.id}/{doc_type}_v{version}_{safe_base}"
        checksum = hashlib.sha256(content).hexdigest()
        saved_path = default_storage.save(rel_path, uploaded_file)
        mime = mimetypes.guess_type(saved_path)[0] or getattr(uploaded_file, 'content_type', '') or 'application/octet-stream'
        titles = {'PHOTO': 'Passport Photo', 'SIGNATURE': 'Signature', 'AADHAAR': 'Aadhaar Card', 'PAN': 'PAN Card'}
        doc = faculty.documents.create(
            document_type=doc_type,
            title=titles.get(doc_type, doc_type),
            document_number='',
            document_number_encrypted=keep_enc,
            document_number_masked=keep_mask,
            file_path=saved_path,
            file_size=len(content),
            mime_type=mime[:100],
            checksum=checksum,
            version=version,
        )
        try:
            stale = list(faculty.documents.filter(document_type=doc_type).exclude(id=doc.id))
            for old in stale:
                try:
                    if old.file_path and default_storage.exists(old.file_path):
                        # Only delete storage paths we manage (not legacy filename placeholders).
                        if str(old.file_path).startswith('faculty_documents/'):
                            default_storage.delete(old.file_path)
                except Exception:
                    pass
                old.delete()
        except Exception:
            pass
        audit_log(
            request=request, actor=request.user, action=AuditLog.Action.UPDATE,
            target_type='FacultyDocument', target_id=str(doc.id),
            target_display=f"{faculty.display_name} - {doc.document_type} v{doc.version}",
            reason='Faculty document upload',
            description=f"Faculty uploaded {doc.document_type} ({doc.file_size} bytes).",
        )
        from apps.faculty.serializers import FacultyDocumentSerializer
        return Response(FacultyDocumentSerializer(doc).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'], url_path=r'me/documents/(?P<doc_id>[0-9a-fA-F-]{36})/download')
    def download_own_document(self, request, doc_id=None):
        from django.http import FileResponse, Http404
        from django.core.files.storage import default_storage
        faculty = self._get_owned_faculty(request)
        if faculty is None:
            return Response(
                {'detail': 'Faculty profile not associated with this account.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        doc = faculty.documents.filter(id=doc_id).first()
        if doc is None:
            raise Http404('Document not found.')
        if not doc.file_path or not default_storage.exists(doc.file_path):
            raise Http404('File missing on server (metadata-only row, re-upload the file).')
        fh = default_storage.open(doc.file_path, 'rb')
        from apps.common.http import no_store as _no_store_docs
        return _no_store_docs(FileResponse(fh, content_type=doc.mime_type or 'application/octet-stream', as_attachment=True))

    @action(detail=False, methods=['post'], url_path=r'me/documents/(?P<doc_id>[0-9a-fA-F-]{36})/reveal')
    def reveal_own_document_number(self, request, doc_id=None):
        faculty = self._get_owned_faculty(request)
        if faculty is None:
            return Response(
                {'detail': 'Faculty profile not associated with this account.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        reason = str(request.data.get('reason', '') or '').strip()
        if len(reason) < 5:
            return Response(
                {'detail': 'A justification reason of at least 5 characters is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        from apps.audit.services import sensitive_reveal_allowed as _reveal_allowed
        from apps.common.http import no_store as _no_store_reveal
        if not _reveal_allowed(request.user):
            return Response(
                {'detail': 'Too many reveals in the last hour. Try again later.'},
                status=429,
            )
        doc = faculty.documents.filter(id=doc_id).first()
        if doc is None:
            return Response({'detail': 'Document not found.'}, status=status.HTTP_404_NOT_FOUND)
        number = None
        if getattr(doc, 'document_number_encrypted', ''):
            number = decrypt_value(doc.document_number_encrypted)
        elif str(getattr(doc, 'document_number', '') or '').strip():
            number = str(doc.document_number).strip()
        audit_log(
            request=request, actor=request.user, action=AuditLog.Action.SENSITIVE_REVEAL,
            target_type='FacultyDocument', target_id=str(doc.id),
            target_display=f"{faculty.display_name} - {doc.document_type}",
            reason=reason,
            description=f"Faculty revealed own {doc.document_type} number.",
        )
        return _no_store_reveal(Response({
            'document_type': doc.document_type,
            'document_number': number,
            'document_number_masked': getattr(doc, 'document_number_masked', ''),
            'revealed_at': timezone.now(),
            'message': 'Access has been recorded in the security audit trail.',
        }, status=status.HTTP_200_OK))


class TeachingAssignmentViewSet(viewsets.ModelViewSet):
    """Subject-teacher slots, owned by HOD (own dept) and Sysadmin.

    Assignment only — no verification rights flow from here. Replacing a
    holder deactivates the old row (history preserved); rows are never
    updated or deleted through this API.
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TeachingAssignmentWriteSerializer

    def get_queryset(self):
        qs = TeachingAssignment.objects.select_related(
            'faculty', 'academic_year', 'department', 'semester', 'division',
            'scheme_subject').all().order_by('-is_active', 'subject_code')
        user = self.request.user
        scopes = get_user_scopes(user)
        if not (scopes['is_system_wide'] or user.is_superuser):
            if 'HOD' in scopes['roles']:
                qs = qs.filter(department_id__in=scopes['department_ids'])
            elif 'ADMIN_HEAD' in scopes['roles']:
                pass
            else:
                qs = qs.filter(faculty__user_id=user.id)
        for param, field in (('division_id', 'division_id'), ('faculty_id', 'faculty_id'),
                             ('is_active', 'is_active'), ('semester', 'semester__number')):
            val = self.request.query_params.get(param, '')
            if isinstance(val, str):
                val = val.strip()
            if val != '' and val is not None:
                if field == 'is_active':
                    # Browsers send lowercase 'true'/'false'; Django's
                    # BooleanField rejects those raw with a 500. Coerce
                    # case-insensitively; unknown flags ignore the filter.
                    lowered = str(val).lower()
                    if lowered in ('true', '1', 'yes'):
                        val = True
                    elif lowered in ('false', '0', 'no'):
                        val = False
                    else:
                        continue
                elif field == 'semester__number':
                    try:
                        val = int(val)
                    except (TypeError, ValueError):
                        continue
                qs = qs.filter(**{field: val})
        return qs

    def _check_manage(self, department_id):
        from apps.authentication.permissions import user_has_permission, user_has_role
        from rest_framework.exceptions import PermissionDenied
        user = self.request.user
        if user.is_superuser or user_has_role(user, 'SYSADMIN') or user_has_permission(user, 'faculty.create'):
            return
        if user_has_role(user, 'HOD'):
            scopes = get_user_scopes(user)
            if str(department_id) in {str(d) for d in scopes.get('department_ids', [])}:
                return
            raise PermissionDenied('HOD may only manage subject teachers in their own department.')
        raise PermissionDenied('Only HOD or Sysadmin can manage subject teachers.')

    def perform_create(self, serializer):
        from apps.academic_structure.models import Division
        from rest_framework.exceptions import ValidationError
        division = serializer.validated_data.get('division')
        self._check_manage(division.department_id if division else None)
        with transaction.atomic():
            # Lock the division row and re-verify the slot under lock so two
            # concurrent assigns cannot both slip past serializer validation.
            # Replacement is explicit: deactivate the holder first, then create.
            if division is not None:
                Division.objects.select_for_update().filter(id=division.id).first()
                role = serializer.validated_data.get('role', TeachingAssignment.Role.PRIMARY_FACULTY)
                faculty = serializer.validated_data.get('faculty')
                code = (serializer.validated_data.get('subject_code') or '').strip().upper()
                clash = TeachingAssignment.objects.filter(
                    division=division, subject_code=code, is_active=True)
                if str(role) == TeachingAssignment.Role.LAB_INSTRUCTOR:
                    clash = clash.filter(role=TeachingAssignment.Role.LAB_INSTRUCTOR)
                else:
                    clash = clash.exclude(role=TeachingAssignment.Role.LAB_INSTRUCTOR)
                clash = clash.exclude(faculty=faculty).first()
                if clash:
                    raise ValidationError(
                        '%s is already taken by %s. Deactivate it first to replace.' % (
                            code, clash.faculty.display_name))
            obj = serializer.save(is_active=True)
            audit_log(
                request=self.request, actor=self.request.user,
                action=AuditLog.Action.CREATE, target_type='TeachingAssignment',
                target_id=str(obj.id),
                target_display=f'{obj.subject_code} -> {obj.faculty.display_name}',
                reason='HOD subject-teacher assignment',
                description=(
                    f"Assigned {obj.faculty.display_name} to {obj.subject_code} "
                    f"({obj.get_role_display()}) in {obj.division}."),
            )

    def update(self, request, *args, **kwargs):
        return Response({'detail': 'Assignments are immutable; deactivate and create anew.'},
                        status=status.HTTP_405_METHOD_NOT_ALLOWED)

    def partial_update(self, request, *args, **kwargs):
        return Response({'detail': 'Assignments are immutable; deactivate and create anew.'},
                        status=status.HTTP_405_METHOD_NOT_ALLOWED)

    def destroy(self, request, *args, **kwargs):
        return Response({'detail': 'Assignments cannot be deleted; deactivate instead.'},
                        status=status.HTTP_405_METHOD_NOT_ALLOWED)

    @action(detail=True, methods=['post'], url_path='deactivate')
    def deactivate(self, request, pk=None):
        obj = self.get_object()
        self._check_manage(obj.department_id)
        obj.is_active = False
        obj.save(update_fields=['is_active'])
        audit_log(
            request=request, actor=request.user, action=AuditLog.Action.UPDATE,
            target_type='TeachingAssignment', target_id=str(obj.id),
            target_display=f'{obj.subject_code} -> {obj.faculty.display_name}',
            reason=request.data.get('reason', 'HOD end of assignment') if request.data else 'HOD end of assignment',
            description=f"Deactivated {obj.faculty.display_name} from {obj.subject_code} in {obj.division}.",
        )
        return Response(TeachingAssignmentSerializer(obj).data, status=status.HTTP_200_OK)
