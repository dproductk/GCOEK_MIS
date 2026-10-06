"""
Views for Student domain.

Enforces:
- Scope-based query filtering for directories.
- HasScopeAccess object permission on profile retrieval to prevent IDOR / BOLA.
- Sensitive data reveal action protected by 'student.sensitive_reveal' permission with audit logging.
- Student self-profile endpoint /api/v1/students/me/.
"""
import uuid
from django.db import models
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from apps.audit.models import AuditLog
from apps.audit.services import audit_log
from apps.common.encryption import decrypt_value, encrypt_value
from apps.authentication.permissions import (
    HasRolePermission,
    HasScopeAccess,
    get_user_scopes,
    user_has_permission,
    user_has_role,
)
from apps.students.models import (
    Student,
    StudentAadhaarDetail,
    StudentAddress,
    StudentBankAccount,
    StudentEnrollment,
)
from apps.students.serializers import (
    StudentListSerializer,
    StudentProfileSerializer,
)


class StudentDirectoryPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 500


class StudentViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Student viewset supporting directory search, profile retrieval,
    self-service /me/ endpoint, and audited sensitive data reveal.
    """

    permission_classes = [permissions.IsAuthenticated, HasScopeAccess]
    serializer_class = StudentProfileSerializer
    pagination_class = StudentDirectoryPagination

    def get_serializer_class(self):
        if self.action == 'list':
            return StudentListSerializer
        return StudentProfileSerializer

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        # Placement suggestion context, computed once per request.
        placement = self._placement_context()

        page = self.paginate_queryset(queryset)
        if page is not None:
            page_student_ids = [s.id for s in page]
            current_enrollments = {
                e.student_id: e
                for e in StudentEnrollment.objects.filter(
                    student_id__in=page_student_ids, is_current=True
                ).select_related('department', 'semester', 'division')
            }
            for s in page:
                s._current_enrollment = current_enrollments.get(s.id)

            serializer = self.get_serializer(
                page, many=True, context={**self.get_serializer_context(), 'placement': placement})
            return self.get_paginated_response(serializer.data)

        student_ids = [s.id for s in queryset]
        current_enrollments = {
            e.student_id: e
            for e in StudentEnrollment.objects.filter(
                student_id__in=student_ids, is_current=True
            ).select_related('department', 'semester', 'division')
        }
        for s in queryset:
            s._current_enrollment = current_enrollments.get(s.id)

        serializer = self.get_serializer(
            queryset, many=True, context={**self.get_serializer_context(), 'placement': placement})
        return Response(serializer.data)

    def _placement_context(self):
        """Current year start + term for the admission formula suggestion."""
        from apps.academic_structure.models import AcademicContext, AcademicYear
        year = AcademicYear.objects.filter(is_current=True).first()
        ctx = AcademicContext.objects.filter(is_active=True).first()
        try:
            start = int(str(year.code).split('-')[0]) if year else None
        except (ValueError, IndexError):
            start = None
        return {
            'current_year_start': start,
            'current_year_id': str(year.id) if year else None,
            'term': ctx.term if ctx else 'ODD',
        }

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated:
            return Student.objects.none()

        qs = Student.objects.select_related('admission_year').prefetch_related(
            'personal_details',
            'guardians',
            'addresses',
            'aadhaar_details',
            'bank_accounts',
            'documents',
            'enrollments__department',
            'enrollments__semester',
            'enrollments__division',
            'enrollments__academic_year',
        ).filter(is_active=True)

        scopes = get_user_scopes(user)

        # 1. Sysadmin: system-wide
        if scopes['is_system_wide']:
            return self._apply_filters(qs)

        # 2. Admin Head / Accountant: college-wide
        if 'ADMIN_HEAD' in scopes['roles'] or 'ACCOUNTANT' in scopes['roles']:
            return self._apply_filters(qs)

        # 3. HOD / Class Teacher / Faculty: college-wide student directory (all faculty can browse all students)
        if any(r in scopes['roles'] for r in ('HOD', 'CLASS_TEACHER', 'FACULTY')):
            return self._apply_filters(qs)

        # 6. Student: own record only (strict isolation)
        if 'STUDENT' in scopes['roles']:
            return qs.filter(user_id=user.id)

        return Student.objects.none()

    def _apply_filters(self, qs):
        dept = self.request.query_params.get('department_id') or self.request.query_params.get('department')
        sem = self.request.query_params.get('semester_number') or self.request.query_params.get('semester')
        div = self.request.query_params.get('division_id') or self.request.query_params.get('division')
        search = self.request.query_params.get('search')
        gender = self.request.query_params.get('gender')
        status_param = self.request.query_params.get('status')
        has_login = self.request.query_params.get('has_login')

        if dept:
            try:
                uuid.UUID(str(dept))
                qs = qs.filter(enrollments__department_id=dept, enrollments__is_current=True)
            except ValueError:
                code_str = str(dept).upper().replace('-', '_')
                if code_str in ('AIDS', 'AI_DS'):
                    qs = qs.filter(
                        models.Q(enrollments__department__code__iexact='AI_DS') |
                        models.Q(enrollments__department__code__iexact='AIDS'),
                        enrollments__is_current=True,
                    )
                elif code_str in ('ME', 'MAE'):
                    qs = qs.filter(
                        models.Q(enrollments__department__code__iexact='MAE') |
                        models.Q(enrollments__department__code__iexact='ME'),
                        enrollments__is_current=True,
                    )
                else:
                    qs = qs.filter(enrollments__department__code__iexact=dept, enrollments__is_current=True)
        if sem:
            qs = qs.filter(enrollments__semester__number=sem, enrollments__is_current=True)
        if div:
            try:
                uuid.UUID(str(div))
                qs = qs.filter(enrollments__division_id=div, enrollments__is_current=True)
            except ValueError:
                qs = qs.filter(enrollments__division__name__iexact=div, enrollments__is_current=True)
        if gender:
            qs = qs.filter(personal_details__gender__iexact=gender)
        if status_param:
            qs = qs.filter(status__iexact=status_param)
        if has_login is not None and has_login != '':
            if str(has_login).lower() in ('true', '1', 'yes'):
                qs = qs.filter(user__isnull=False)
            elif str(has_login).lower() in ('false', '0', 'no'):
                qs = qs.filter(user__isnull=True)
        year_level = self.request.query_params.get('year_level') or self.request.query_params.get('class_year') or self.request.query_params.get('year')
        if year_level:
            yl_str = str(year_level).strip().upper()
            if yl_str in ('1', 'FY', 'FIRST_YEAR', 'FIRST YEAR'):
                qs = qs.filter(enrollments__semester__year_level=1, enrollments__is_current=True)
            elif yl_str in ('2', 'SY', 'SECOND_YEAR', 'SECOND YEAR'):
                qs = qs.filter(enrollments__semester__year_level=2, enrollments__is_current=True)
            elif yl_str in ('3', 'TY', 'THIRD_YEAR', 'THIRD YEAR'):
                qs = qs.filter(enrollments__semester__year_level=3, enrollments__is_current=True)
            elif yl_str in ('4', 'FINAL', 'FINAL_YEAR', 'FINAL YEAR', 'BTECH', 'B_TECH'):
                qs = qs.filter(enrollments__semester__year_level=4, enrollments__is_current=True)
            elif yl_str.isdigit():
                qs = qs.filter(enrollments__semester__year_level=int(yl_str), enrollments__is_current=True)

        is_dsy = self.request.query_params.get('is_direct_second_year') or self.request.query_params.get('is_dsy')
        if is_dsy is not None and is_dsy != '':
            if str(is_dsy).lower() in ('true', '1', 'yes'):
                qs = qs.filter(is_direct_second_year=True)
            elif str(is_dsy).lower() in ('false', '0', 'no'):
                qs = qs.filter(is_direct_second_year=False)

        eligible_only = self.request.query_params.get('eligible_only') or self.request.query_params.get('is_eligible')
        if eligible_only and str(eligible_only).lower() in ('true', '1', 'yes'):
            # Common rule (all years incl. FY): HOD-endorsed rows plus
            # freshers (FY Sem 1 / DSE Sem 3 admitted in the current year)
            # ONLY when seated in an HOD-created division WITH an assigned
            # class teacher. Import lands students in Div A but teacher-less,
            # so nobody reaches the fee/verification lists until the HOD
            # confirms the class and assigns its teacher.
            from apps.academic_structure.models import AcademicYear
            from django.db.models import Exists, OuterRef, Q
            current_year = AcademicYear.objects.filter(is_current=True).first()
            _cur = StudentEnrollment.objects.filter(student_id=OuterRef('pk'), is_current=True)
            _fresh = models.Q()
            if current_year is not None:
                _fresh = (
                    models.Q(admission_year=current_year, admission_type='FY',
                             _fy_fresh=True)
                    | models.Q(admission_year=current_year, admission_type='DSE',
                               _dse_fresh=True)
                )
            _in_class = dict(division__isnull=False, division__class_teacher__isnull=False)
            qs = qs.annotate(
                _fy_fresh=Exists(_cur.filter(semester__number=1, **_in_class)),
                _dse_fresh=Exists(_cur.filter(semester__number=3, **_in_class)),
            ).filter(
                models.Q(eligibility_records__final_eligible=True) | _fresh
            ).distinct()
        if search:
            search = search.strip()
            qs = qs.filter(
                models.Q(display_name__icontains=search)
                | models.Q(first_name__icontains=search)
                | models.Q(last_name__icontains=search)
                | models.Q(enrollment_no__icontains=search)
                | models.Q(application_id__icontains=search)
                | models.Q(user__username__icontains=search)
            )
        return qs.distinct()

    @action(detail=False, methods=['get'], url_path='me')
    def me(self, request):
        """Retrieve the authenticated student's own full profile."""
        try:
            student = Student.objects.get(user_id=request.user.id, is_active=True)
        except Student.DoesNotExist:
            return Response(
                {'detail': 'Student profile not associated with this account.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = StudentProfileSerializer(student)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['patch'], url_path='me/update')
    def update_me(self, request):
        """
        Student self-service profile update.

        Only the authenticated student may update their OWN record.
        Locked (silently ignored, never written):
          enrollment_no, application_id, names, status, admission data,
          enrollments, Aadhaar number/verified flag, documents/marksheets.
        Editable: personal contact/demographic details, guardians,
        permanent address, primary bank account. All changes audited.
        """
        import re

        from django.core.exceptions import ValidationError as DjangoValidationError
        from django.core.validators import validate_email
        from django.db import transaction
        from rest_framework.exceptions import PermissionDenied, ValidationError

        from apps.students.models import StudentGuardian, StudentPersonalDetail

        if not user_has_role(request.user, 'STUDENT'):
            raise PermissionDenied('Only students may update their own profile.')
        try:
            student = Student.objects.get(user_id=request.user.id, is_active=True)
        except Student.DoesNotExist:
            return Response(
                {'detail': 'Student profile not associated with this account.'},
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
            # 1. Personal details (create row if missing)
            personal_data = data.get('personal') or {}
            if isinstance(personal_data, dict) and personal_data:
                allowed = {
                    'date_of_birth', 'gender', 'place_of_birth', 'religion',
                    'nationality', 'mother_tongue', 'domicile_state',
                    'student_email', 'student_mobile', 'blood_group',
                }
                personal, _ = StudentPersonalDetail.objects.get_or_create(student=student)
                for field_name, value in personal_data.items():
                    if field_name not in allowed:
                        continue
                    if field_name == 'gender':
                        value = str(value or '').strip().upper()
                        if value not in ('MALE', 'FEMALE', 'OTHER'):
                            raise ValidationError({'personal.gender': 'Must be MALE, FEMALE or OTHER.'})
                    elif field_name == 'date_of_birth' and value:
                        try:
                            dob = value if hasattr(value, 'year') else __import__('datetime').date.fromisoformat(str(value))
                        except ValueError:
                            raise ValidationError({'personal.date_of_birth': 'Use YYYY-MM-DD format.'})
                        if dob > __import__('datetime').date.today():
                            raise ValidationError({'personal.date_of_birth': 'Date of birth cannot be in the future.'})
                        value = dob
                    elif field_name == 'student_mobile':
                        value = clean_mobile(value, 'personal.student_mobile')
                    elif field_name == 'student_email' and value:
                        try:
                            validate_email(str(value).strip())
                        except DjangoValidationError:
                            raise ValidationError({'personal.student_email': 'Enter a valid email address.'})
                        value = str(value).strip()
                    elif isinstance(value, str):
                        value = value.strip()
                    if getattr(personal, field_name) != value:
                        setattr(personal, field_name, value)
                        changed.append(f'personal.{field_name}')
                personal.save()

            # 2. Guardians (match by relationship, create if missing)
            guardians_data = data.get('guardians') or []
            if isinstance(guardians_data, list):
                for entry in guardians_data:
                    if not isinstance(entry, dict):
                        continue
                    rel = str(entry.get('relationship') or '').strip().upper()
                    if rel not in ('FATHER', 'MOTHER', 'GUARDIAN'):
                        continue
                    guardian, _ = student.guardians.get_or_create(
                        relationship=rel, defaults={'name': ''}
                    )
                    for field_name in ('name', 'mobile', 'email', 'occupation'):
                        if field_name not in entry:
                            continue
                        value = entry[field_name]
                        if field_name == 'mobile':
                            value = clean_mobile(value, f'guardians.{rel}.mobile')
                        elif field_name == 'email' and value:
                            try:
                                validate_email(str(value).strip())
                            except DjangoValidationError:
                                raise ValidationError({f'guardians.{rel}.email': 'Enter a valid email address.'})
                            value = str(value).strip()
                        elif isinstance(value, str):
                            value = value.strip()
                            if field_name == 'name' and not value:
                                raise ValidationError({f'guardians.{rel}.name': 'Name cannot be empty.'})
                        if getattr(guardian, field_name) != value:
                            setattr(guardian, field_name, value)
                            changed.append(f'guardians.{rel}.{field_name}')
                    guardian.save()

            # 3. Permanent address (create if missing)
            address_data = data.get('address') or {}
            if isinstance(address_data, dict) and address_data:
                allowed = {
                    'address_line_1', 'address_line_2', 'address_line_3',
                    'village', 'taluka', 'district', 'state', 'pincode',
                }
                address, _ = student.addresses.get_or_create(
                    address_type=StudentAddress.AddressType.PERMANENT,
                    defaults={'address_line_1': '', 'state': 'Maharashtra'},
                )
                for field_name, value in address_data.items():
                    if field_name not in allowed:
                        continue
                    value = str(value or '').strip()
                    if field_name == 'address_line_1' and not value:
                        raise ValidationError({'address.address_line_1': 'Address cannot be empty.'})
                    if field_name == 'pincode' and value and not re.fullmatch(r'\d{6}', value):
                        raise ValidationError({'address.pincode': 'Pincode must be 6 digits.'})
                    if getattr(address, field_name) != value:
                        setattr(address, field_name, value)
                        changed.append(f'address.{field_name}')
                address.save()

            # 4. Primary bank account (create if missing; number re-masked)
            bank_data = data.get('bank') or {}
            if isinstance(bank_data, dict) and bank_data:
                allowed = {
                    'account_holder_name', 'bank_name', 'branch_name',
                    'ifsc_code', 'account_number',
                }
                bank = student.bank_accounts.filter(is_primary=True).first()
                if bank is None:
                    if not bank_data.get('account_number'):
                        raise ValidationError({'bank.account_number': 'Account number is required.'})
                    bank = StudentBankAccount(
                        student=student,
                        account_holder_name='',
                        bank_name='',
                        ifsc_code='',
                        account_number_encrypted='',
                        account_number_masked='',
                        is_primary=True,
                    )
                for field_name, value in bank_data.items():
                    if field_name not in allowed:
                        continue
                    value = str(value or '').strip()
                    if field_name == 'account_number' and value:
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
                        if field_name in ('account_holder_name', 'bank_name') and not value:
                            raise ValidationError({f'bank.{field_name}': 'This field cannot be empty.'})
                        if getattr(bank, field_name) != value:
                            setattr(bank, field_name, value)
                            changed.append(f'bank.{field_name}')
                bank.save()

        if changed:
            audit_log(
                request=request,
                actor=request.user,
                action=AuditLog.Action.UPDATE,
                target_type='Student',
                target_id=str(student.id),
                target_display=student.display_name,
                reason='Student self-service profile update',
                description=f"Student updated own profile: {', '.join(sorted(set(changed)))}.",
            )

        serializer = StudentProfileSerializer(student)
        return Response(
            {'detail': 'Profile updated successfully.', 'changed': sorted(set(changed)), 'profile': serializer.data},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=['post'], url_path='reveal')
    def reveal_sensitive(self, request, pk=None):
        """
        Reveal unmasked sensitive values (Aadhaar, Bank) with mandatory audit logging.
        Requires 'student.sensitive_reveal' permission.
        """
        student = self.get_object()

        # Authorization check
        if not user_has_permission(request.user, 'student.sensitive_reveal') and not request.user.is_superuser:
            return Response(
                {'detail': 'You do not have permission to reveal sensitive student data.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        reason = str(request.data.get('reason', '') or '').strip()
        if len(reason) < 5:
            return Response(
                {'detail': 'A justification reason of at least 5 characters is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Audit log the reveal event
        audit_log(
            request=request,
            actor=request.user,
            action=AuditLog.Action.SENSITIVE_REVEAL,
            target_type='Student',
            target_id=str(student.id),
            target_display=student.display_name,
            reason=reason,
            description=f"Sensitive data reveal for student '{student.display_name}'.",
        )

        aadhaar = getattr(student, 'aadhaar_details', None)
        bank_account = student.bank_accounts.filter(is_primary=True).first()

        aadhaar_number = (
            decrypt_value(aadhaar.aadhaar_number_encrypted)
            if aadhaar and getattr(aadhaar, 'aadhaar_number_encrypted', '') else None
        )
        bank_account_number = (
            decrypt_value(bank_account.account_number_encrypted)
            if bank_account and getattr(bank_account, 'account_number_encrypted', '') else None
        )

        return Response({
            'aadhaar_number': aadhaar_number,
            'bank_account_number': bank_account_number,
            'revealed_at': timezone.now(),
            'message': 'Sensitive data unmasked. Access has been logged to the security audit trail.',
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='assign-division')
    def assign_division(self, request, pk=None):
        """
        HOD / Sysadmin / Admin Head assigns or edits a student's division.
        HOD can only edit division for students enrolled in their own department.
        """
        student = self.get_object()
        user = request.user
        scopes = get_user_scopes(user)

        current_enrollment = student.enrollments.filter(is_current=True).first()
        if not current_enrollment:
            return Response(
                {'detail': 'Student has no active enrollment record.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Permission check: Sysadmin, Admin Head, or HOD of this student's department
        is_sysadmin = scopes['is_system_wide'] or user.is_superuser
        is_admin_head = 'ADMIN_HEAD' in scopes['roles']
        is_dept_hod = (
            'HOD' in scopes['roles']
            and current_enrollment.department_id in scopes['department_ids']
        )

        if not (is_sysadmin or is_admin_head or is_dept_hod):
            return Response(
                {'detail': 'Only the department HOD or an Administrator can assign or edit student divisions.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        division_id = request.data.get('division_id')
        division_obj = None

        if division_id:
            from apps.academic_structure.models import Division
            try:
                division_obj = Division.objects.get(id=division_id)
            except (Division.DoesNotExist, ValueError):
                return Response(
                    {'detail': 'Specified division does not exist.'},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Ensure division belongs to the student's department
            if division_obj.department_id != current_enrollment.department_id:
                return Response(
                    {'detail': f"Division '{division_obj.name}' belongs to a different department ({division_obj.department.code})."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        lab_batch_id = request.data.get('lab_batch_id')
        lab_batch_obj = None
        if lab_batch_id:
            from apps.academic_structure.models import LabBatch
            try:
                lab_batch_obj = LabBatch.objects.get(id=lab_batch_id)
            except (LabBatch.DoesNotExist, ValueError):
                return Response(
                    {'detail': 'Specified lab batch does not exist.'},
                    status=status.HTTP_404_NOT_FOUND,
                )

            target_div = division_obj or current_enrollment.division
            if target_div and lab_batch_obj.division_id != target_div.id:
                return Response(
                    {'detail': f"Lab batch '{lab_batch_obj.name}' does not belong to Division '{target_div.name}'."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        old_div_name = current_enrollment.division.name if current_enrollment.division else 'Unassigned'
        old_batch_name = current_enrollment.lab_batch.name if current_enrollment.lab_batch else 'Unassigned'

        update_fields = ['updated_at']
        if division_id is not None or 'division_id' in request.data:
            current_enrollment.division = division_obj
            update_fields.append('division')
        if lab_batch_id is not None or 'lab_batch_id' in request.data:
            current_enrollment.lab_batch = lab_batch_obj
            update_fields.append('lab_batch')
        # HOD touch = placement finalized (formula suggestion accepted/corrected).
        if not current_enrollment.placement_confirmed:
            current_enrollment.placement_confirmed = True
            update_fields.append('placement_confirmed')

        current_enrollment.save(update_fields=update_fields)

        new_div_name = current_enrollment.division.name if current_enrollment.division else 'Unassigned'
        new_batch_name = current_enrollment.lab_batch.name if current_enrollment.lab_batch else 'Unassigned'

        audit_log(
            request=request,
            actor=user,
            action=AuditLog.Action.UPDATE,
            target_type='StudentEnrollment',
            target_id=str(current_enrollment.id),
            target_display=f"{student.display_name} -> Div {new_div_name} / Batch {new_batch_name}",
            reason=request.data.get('reason', 'HOD student division/batch allocation'),
            description=f"Changed division ({old_div_name} -> {new_div_name}) and lab batch ({old_batch_name} -> {new_batch_name}) for {student.display_name}.",
        )

        return Response({
            'detail': f"Student division/batch updated to Div {new_div_name} / Batch {new_batch_name}.",
            'student_id': str(student.id),
            'division_id': str(current_enrollment.division_id) if current_enrollment.division_id else None,
            'division_name': new_div_name,
            'lab_batch_id': str(current_enrollment.lab_batch_id) if current_enrollment.lab_batch_id else None,
            'lab_batch_name': new_batch_name,
        }, status=status.HTTP_200_OK)

