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
from apps.common.encryption import decrypt_value, encrypt_value
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
            if data['initial_role'] != 'FACULTY':
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
        permanent/correspondence addresses, primary bank account.
        Locked (silently ignored): employee_code, employment_type/status,
        qualifications, experiences, publications, guidance, documents,
        teaching assignments.
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
            dept_val = data.get('department_id', data.get('department', None))
            if dept_val not in (None, ''):
                dept = None
                try:
                    dept = Department.objects.filter(id=str(dept_val).strip()).first()
                except Exception:
                    dept = None
                if dept is None:
                    dept = Department.objects.filter(code__iexact=str(dept_val).strip()).first()
                if dept is None:
                    dept = Department.objects.filter(name__iexact=str(dept_val).strip()).first()
                if dept is None:
                    raise ValidationError({'department': 'Department not found.'})
                if faculty.department_id != dept.id:
                    faculty.department = dept
                    changed.append('department')

            # Designation: accept code (LECTURER) or display (Lecturer).
            if 'designation' in data and data.get('designation') not in (None, ''):
                raw = str(data.get('designation') or '').strip()
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
                except FacultyPersonalDetail.DoesNotExist:
                    personal = FacultyPersonalDetail(
                        faculty=faculty,
                        date_of_birth=faculty.date_of_joining,
                        gender=FacultyPersonalDetail.Gender.MALE,
                    )
                for field_name, value in personal_data.items():
                    if field_name not in allowed:
                        continue
                    if field_name == 'gender':
                        value = str(value or '').strip().upper()
                        if value not in ('MALE', 'FEMALE', 'OTHER'):
                            raise ValidationError({'personal.gender': 'Must be MALE, FEMALE or OTHER.'})
                    elif field_name == 'date_of_birth' and value:
                        try:
                            import datetime as _dt2
                            dob = value if hasattr(value, 'year') else _dt2.date.fromisoformat(str(value))
                        except ValueError:
                            raise ValidationError({'personal.date_of_birth': 'Use YYYY-MM-DD format.'})
                        if dob > __import__('datetime').date.today():
                            raise ValidationError({'personal.date_of_birth': 'Date of birth cannot be in the future.'})
                        value = dob
                    elif isinstance(value, str):
                        value = value.strip()
                    if getattr(personal, field_name) != value:
                        setattr(personal, field_name, value)
                        changed.append(f'personal.{field_name}')
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
                allowed_addr = {'address_line_1', 'address_line_2', 'district', 'state', 'pincode'}
                address, _ = faculty.addresses.get_or_create(
                    address_type=atype,
                    defaults={'address_line_1': '', 'pincode': ''},
                )
                for field_name, value in normalized.items():
                    if field_name not in allowed_addr:
                        continue
                    value = str(value or '').strip()
                    if field_name == 'address_line_1' and not value:
                        raise ValidationError({f'addresses.{alias}.address_line_1': 'Address cannot be empty.'})
                    if field_name == 'pincode' and value and not re.fullmatch(r'\d{6}', value):
                        raise ValidationError({f'addresses.{alias}.pincode': 'Pincode must be 6 digits.'})
                    if getattr(address, field_name) != value:
                        setattr(address, field_name, value)
                        changed.append(f'addresses.{alias}.{field_name}')
                address.save()

            # 4. Primary bank account (create if missing; number re-masked).
            bank_data = data.get('bank') or {}
            if isinstance(bank_data, dict) and bank_data:
                from apps.faculty.models import FacultyBankAccount
                allowed_bank = {
                    'account_holder_name', 'bank_name', 'branch_name',
                    'ifsc_code', 'account_number',
                }
                bank = faculty.bank_accounts.filter(is_primary=True).first()
                if bank is None:
                    if not bank_data.get('account_number'):
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
                for field_name, value in bank_data.items():
                    if field_name not in allowed_bank:
                        continue
                    value = str(value or '').strip()
                    if field_name == 'account_number' and value:
                        # Skip masked display values echoed back (contain X).
                        if 'X' in value.upper():
                            continue
                        digits = re.sub(r'\D', '', value)
                        if not 9 <= len(digits) <= 18:
                            raise ValidationError({'bank.account_number': 'Account number must be 9-18 digits.'})
                        bank.account_number_encrypted = encrypt_value(digits)
                        bank.account_number_masked = f'XXXXXXXX{digits[-4:]}'
                        changed.append('bank.account_number')
                    elif field_name == 'ifsc_code' and value:
                        value = value.upper()
                        if not re.fullmatch(r'[A-Z]{4}0[A-Z0-9]{6}', value):
                            raise ValidationError({'bank.ifsc_code': 'IFSC must look like SBIN0001234.'})
                        if bank.ifsc_code != value:
                            bank.ifsc_code = value
                            changed.append('bank.ifsc_code')
                    elif field_name in ('account_holder_name', 'bank_name', 'branch_name'):
                        if getattr(bank, field_name) != value:
                            setattr(bank, field_name, value)
                            changed.append(f'bank.{field_name}')
                bank.save()

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

        return Response({
            'bank_account_number': (
                decrypt_value(primary_bank.account_number_encrypted)
                if primary_bank and getattr(primary_bank, 'account_number_encrypted', '') else None
            ),
            'revealed_at': timezone.now(),
            'message': 'Sensitive faculty bank details unmasked. Access has been recorded in the security audit trail.',
        }, status=status.HTTP_200_OK)


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
