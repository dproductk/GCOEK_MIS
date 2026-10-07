"""
Views for Curriculum domain.

- Read: any authenticated user (faculty/HOD/student read-only per CONTEXT).
- Write: sysadmin only (is_system_wide / curriculum.manage / superuser).
- Published schemes are immutable: only DRAFT rows can be edited; publishing
  is a one-way guarded transition DRAFT -> PUBLISHED -> RETIRED.
"""
from django.db import IntegrityError, transaction
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.audit.models import AuditLog
from apps.audit.services import audit_log
from apps.authentication.permissions import get_user_scopes, user_has_permission
from apps.curriculum.models import (
    Scheme,
    SchemeElectiveGroup,
    SchemeElectiveOption,
    SchemeSubject,
    SchemeSubjectAssessmentComponent,
    Subject,
)
from apps.curriculum.serializers import (
    AssessmentComponentSerializer,
    ElectiveGroupSerializer,
    ElectiveOptionSerializer,
    SchemeSerializer,
    SchemeSubjectSerializer,
    SubjectSerializer,
)


def _can_manage(user):
    if not user or not user.is_authenticated or not user.is_active:
        return False
    if user.is_superuser:
        return True
    scopes = get_user_scopes(user)
    return scopes['is_system_wide'] or user_has_permission(user, 'curriculum.manage')


class _SysadminWriteMixin:
    """Blocks non-sysadmin writes; read stays authenticated."""

    def _deny_unless_manager(self):
        if not _can_manage(self.request.user):
            return Response(
                {'detail': 'Only Sysadmin can manage schemes and subjects.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        return None


class SubjectViewSet(_SysadminWriteMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SubjectSerializer

    def get_queryset(self):
        qs = Subject.objects.all().order_by('code')
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(code__icontains=search) | qs.filter(title__icontains=search)
        return qs

    def create(self, request, *args, **kwargs):
        denied = self._deny_unless_manager()
        if denied:
            return denied
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        with transaction.atomic():
            obj = serializer.save()
            audit_log(request=self.request, actor=self.request.user,
                      action=AuditLog.Action.CREATE, target_type='Subject',
                      target_id=str(obj.id), target_display=f'{obj.code} - {obj.title}',
                      new_value={'code': obj.code, 'title': obj.title},
                      reason='Sysadmin curriculum configuration',
                      description=f"Created subject {obj.code}.")

    def update(self, request, *args, **kwargs):
        denied = self._deny_unless_manager()
        if denied:
            return denied
        return super().update(request, *args, **kwargs)

    def perform_update(self, serializer):
        with transaction.atomic():
            obj = serializer.save()
            audit_log(request=self.request, actor=self.request.user,
                      action=AuditLog.Action.UPDATE, target_type='Subject',
                      target_id=str(obj.id), target_display=f'{obj.code}',
                      reason='Sysadmin curriculum configuration',
                      description=f"Updated subject {obj.code}.")

    def destroy(self, request, *args, **kwargs):
        denied = self._deny_unless_manager()
        if denied:
            return denied
        obj = self.get_object()
        if obj.scheme_occurrences.exists() or obj.elective_options.exists():
            return Response({'detail': 'Subject is used by a scheme and cannot be deleted.'},
                            status=status.HTTP_400_BAD_REQUEST)
        code = obj.code
        sid = str(obj.id)
        try:
            obj.delete()
        except Exception:
            return Response({'detail': 'Subject is in use and cannot be deleted.'},
                            status=status.HTTP_400_BAD_REQUEST)
        audit_log(request=request, actor=request.user, action=AuditLog.Action.DELETE,
                  target_type='Subject', target_id=sid, target_display=code,
                  reason='Sysadmin curriculum configuration',
                  description=f"Deleted subject {code}.")
        return Response(status=status.HTTP_204_NO_CONTENT)


class SchemeViewSet(_SysadminWriteMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SchemeSerializer

    def _covering_clash(self, scheme):
        """Another PUBLISHED scheme covering the same year + program scope."""
        others = Scheme.objects.filter(status=Scheme.Status.PUBLISHED).exclude(id=scheme.id)
        if scheme.program_id:
            others = others.filter(program_id=scheme.program_id)
        else:
            others = others.filter(program__isnull=True)
        mine_from = scheme.effective_from_year.code if scheme.effective_from_year else ''
        mine_to = scheme.effective_to_year.code if scheme.effective_to_year else None
        for other in others.select_related('effective_from_year', 'effective_to_year'):
            o_from = other.effective_from_year.code if other.effective_from_year else ''
            o_to = other.effective_to_year.code if other.effective_to_year else None
            if mine_from <= (o_to or '9999') and (mine_to or '9999') >= o_from:
                return other
        return None

    def get_queryset(self):
        qs = Scheme.objects.select_related(
            'program', 'department', 'effective_from_year', 'effective_to_year'
        ).prefetch_related('scheme_subjects__subject', 'scheme_subjects__assessment_components',
                            'elective_groups__options').all().order_by('code', 'version')
        for param, field in (('program', 'program_id'), ('department', 'department_id'),
                             ('status', 'status'), ('code', 'code__iexact')):
            val = self.request.query_params.get(param, '').strip()
            if val:
                qs = qs.filter(**{field: val})
        return qs

    def create(self, request, *args, **kwargs):
        denied = self._deny_unless_manager()
        if denied:
            return denied
        try:
            with transaction.atomic():
                resp = super().create(request, *args, **kwargs)
                obj = Scheme.objects.get(id=resp.data['id'])
                audit_log(request=request, actor=request.user, action=AuditLog.Action.CREATE,
                          target_type='Scheme', target_id=str(obj.id),
                          target_display=f'{obj.code} v{obj.version}',
                          new_value={'code': obj.code, 'version': obj.version, 'status': obj.status},
                          reason='Sysadmin curriculum configuration',
                          description=f"Created scheme {obj.code} v{obj.version}.")
                return resp
        except IntegrityError:
            return Response({'detail': 'Scheme code+version already exists.'},
                            status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, *args, **kwargs):
        denied = self._deny_unless_manager()
        if denied:
            return denied
        obj = self.get_object()
        if not obj.is_mutable:
            return Response({'detail': 'Only DRAFT schemes can be edited. Create a new version instead.'},
                            status=status.HTTP_400_BAD_REQUEST)
        # Forbid code/version change on update (new version = new row)
        for locked in ('code', 'version'):
            if locked in request.data and str(request.data[locked]).strip().lower() != str(getattr(obj, locked)).lower():
                return Response({locked: 'Create a new scheme version instead of renaming.'},
                                status=status.HTTP_400_BAD_REQUEST)
        return super().update(request, *args, **kwargs)

    def perform_update(self, serializer):
        with transaction.atomic():
            obj = serializer.save()
            audit_log(request=self.request, actor=self.request.user, action=AuditLog.Action.UPDATE,
                      target_type='Scheme', target_id=str(obj.id),
                      target_display=f'{obj.code} v{obj.version}',
                      reason='Sysadmin curriculum configuration',
                      description=f"Updated scheme {obj.code} v{obj.version}.")

    def destroy(self, request, *args, **kwargs):
        denied = self._deny_unless_manager()
        if denied:
            return denied
        obj = self.get_object()
        # Only DRAFT schemes that were never used can be deleted.
        # PUBLISHED / RETIRED are historical records — retire instead.
        if obj.status != Scheme.Status.DRAFT:
            return Response({'detail': 'Only DRAFT schemes can be deleted. Published/retired schemes must be retired instead.'},
                            status=status.HTTP_400_BAD_REQUEST)
        if obj.enrollments.exists():
            return Response({'detail': 'Scheme is used by student enrollments and cannot be deleted.'},
                            status=status.HTTP_400_BAD_REQUEST)
        display = f'{obj.code} v{obj.version}'
        scheme_id = str(obj.id)
        # CASCADE removes its draft subjects / splits / elective groups.
        # Teaching assignments referencing those slots are SET_NULL, so this is safe.
        obj.delete()
        audit_log(request=request, actor=request.user, action=AuditLog.Action.DELETE,
                  target_type='Scheme', target_id=scheme_id, target_display=display,
                  reason='Sysadmin curriculum configuration',
                  description=f"Deleted draft scheme {display}.")
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], url_path='publish')
    def publish(self, request, pk=None):
        from django.db import transaction
        denied = self._deny_unless_manager()
        if denied:
            return denied
        with transaction.atomic():
            try:
                obj = Scheme.objects.select_for_update().get(id=self.get_object().id)
            except Scheme.DoesNotExist:
                return Response({'detail': 'Scheme not found.'},
                                status=status.HTTP_404_NOT_FOUND)
            if obj.status != Scheme.Status.DRAFT:
                return Response({'detail': 'Only DRAFT schemes can be published.'},
                                status=status.HTTP_400_BAD_REQUEST)
            # Completeness: all 8 semesters must carry subjects, each with a
            # defined examination scheme. Splits are derived from the Subject
            # master, so heal missing rows before judging.
            from apps.curriculum.services import ensure_assessment_components
            sems_covered = set(obj.scheme_subjects.values_list('semester_number', flat=True))
            missing = [n for n in range(1, 9) if n not in sems_covered]
            if missing:
                return Response(
                    {'detail': 'Cannot publish: semesters %s have no subjects yet.' % (
                        ', '.join(str(n) for n in missing))},
                    status=status.HTTP_400_BAD_REQUEST)
            for ss in obj.scheme_subjects.select_related('subject').all():
                if not ss.assessment_components.exists():
                    ensure_assessment_components(ss)
            bare = obj.scheme_subjects.filter(assessment_components__isnull=True)
            if bare.exists():
                codes = ', '.join(sorted({s.course_code for s in bare[:10]}))
                return Response(
                    {'detail': 'Cannot publish: subjects without examination scheme: %s. '
                               'Edit the subject master to add CA + MSE + ESE '
                               '(or Practical CA + Practical ESE for labs).' % codes},
                    status=status.HTTP_400_BAD_REQUEST)
            # One scheme per year: no other PUBLISHED scheme may cover the same
            # admission year for the same program scope.
            clash = self._covering_clash(obj)
            if clash:
                return Response(
                    {'detail': 'Cannot publish: %s v%s already covers %s for this program scope.' % (
                        clash.code, clash.version, clash.effective_from_year.code)},
                    status=status.HTTP_400_BAD_REQUEST)
            obj.status = Scheme.Status.PUBLISHED
            obj.save(update_fields=['status', 'updated_at'])
            audit_log(request=request, actor=request.user, action=AuditLog.Action.STATUS_CHANGE,
                      target_type='Scheme', target_id=str(obj.id),
                      target_display=f'{obj.code} v{obj.version}',
                      reason='Scheme published for admissions',
                      description=f"Published scheme {obj.code} v{obj.version}.")
            return Response(SchemeSerializer(obj).data)

    @action(detail=True, methods=['post'], url_path='retire')
    def retire(self, request, pk=None):
        denied = self._deny_unless_manager()
        if denied:
            return denied
        obj = self.get_object()
        if obj.status != Scheme.Status.PUBLISHED:
            return Response({'detail': 'Only PUBLISHED schemes can be retired.'},
                            status=status.HTTP_400_BAD_REQUEST)
        obj.status = Scheme.Status.RETIRED
        obj.save(update_fields=['status', 'updated_at'])
        audit_log(request=request, actor=request.user, action=AuditLog.Action.STATUS_CHANGE,
                  target_type='Scheme', target_id=str(obj.id),
                  target_display=f'{obj.code} v{obj.version}',
                  reason='Scheme retired',
                  description=f"Retired scheme {obj.code} v{obj.version}.")
        return Response(SchemeSerializer(obj).data)


class _SchemeChildMixin(_SysadminWriteMixin):
    """Guards child writes against published parents."""

    def _parent_scheme(self, serializer_or_obj):
        raise NotImplementedError

    def _deny_if_locked(self, scheme):
        if scheme is not None and not scheme.is_mutable:
            return Response(
                {'detail': 'Parent scheme is published/retired and immutable. Create a new version.'},
                status=status.HTTP_400_BAD_REQUEST)
        return None


class SchemeSubjectViewSet(_SchemeChildMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SchemeSubjectSerializer

    def get_queryset(self):
        qs = SchemeSubject.objects.select_related('scheme', 'subject', 'elective_group').prefetch_related(
            'assessment_components').all().order_by('scheme__code', 'semester_number', 'display_order')
        for param, field in (('scheme', 'scheme_id'), ('semester', 'semester_number')):
            val = self.request.query_params.get(param, '').strip()
            if val:
                qs = qs.filter(**{field: val})
        return qs

    @action(detail=False, methods=['get'], url_path='my-subjects')
    def my_subjects(self, request):
        """Scheme subject list for the requesting student's own sem.

        Query: ?semester=N. Resolves the student's current enrollment scheme;
        returns [] when the student has no scheme (old record) so the UI can
        fall back to free entry.
        """
        from apps.students.models import Student
        student = Student.objects.filter(user_id=request.user.id).first()
        if not student:
            return Response([], status=status.HTTP_200_OK)
        enr = student.enrollments.filter(is_current=True).select_related('scheme').first()
        if not enr or not enr.scheme_id:
            return Response([], status=status.HTTP_200_OK)
        try:
            sem_no = int(request.query_params.get('semester', enr.semester.number if enr.semester else 1))
        except (ValueError, TypeError):
            sem_no = 1
        qs = self.get_queryset().filter(scheme_id=enr.scheme_id, semester_number=sem_no)
        return Response(SchemeSubjectSerializer(qs, many=True).data, status=status.HTTP_200_OK)

    def _parent_scheme(self, validated):
        scheme = validated.get('scheme')
        return scheme if hasattr(scheme, 'is_mutable') else Scheme.objects.filter(id=scheme).first()

    def create(self, request, *args, **kwargs):
        denied = self._deny_unless_manager()
        if denied:
            return denied
        ser = SchemeSubjectSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        denied = self._deny_if_locked(self._parent_scheme(ser.validated_data))
        if denied:
            return denied
        resp = super().create(request, *args, **kwargs)
        # Code/credits/marks were auto-filled from the Subject master;
        # mirror its exam scheme into legacy split rows (idempotent).
        try:
            from apps.curriculum.services import ensure_assessment_components
            ss = SchemeSubject.objects.select_related('subject').get(id=resp.data['id'])
            ensure_assessment_components(ss)
            resp.data = SchemeSubjectSerializer(ss).data
        except Exception:
            pass
        return resp

    def update(self, request, *args, **kwargs):
        denied = self._deny_unless_manager()
        if denied:
            return denied
        denied = self._deny_if_locked(self.get_object().scheme)
        if denied:
            return denied
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        denied = self._deny_unless_manager()
        if denied:
            return denied
        denied = self._deny_if_locked(self.get_object().scheme)
        if denied:
            return denied
        return super().destroy(request, *args, **kwargs)

    def perform_create(self, serializer):
        with transaction.atomic():
            obj = serializer.save()
            audit_log(request=self.request, actor=self.request.user,
                      action=AuditLog.Action.CREATE, target_type='SchemeSubject',
                      target_id=str(obj.id),
                      target_display=f'{obj.course_code} ({obj.scheme.code if obj.scheme else "?"})',
                      new_value={'course_code': obj.course_code, 'semester': obj.semester_number},
                      reason='Sysadmin curriculum configuration',
                      description=f"Added {obj.course_code} to scheme {obj.scheme.code if obj.scheme else '?'}. ")

    def perform_update(self, serializer):
        with transaction.atomic():
            old = serializer.instance
            old_code = old.course_code if old else ''
            obj = serializer.save()
            audit_log(request=self.request, actor=self.request.user,
                      action=AuditLog.Action.UPDATE, target_type='SchemeSubject',
                      target_id=str(obj.id),
                      target_display=f'{obj.course_code}',
                      old_value={'course_code': old_code},
                      new_value={'course_code': obj.course_code},
                      reason='Sysadmin curriculum configuration',
                      description=f"Updated scheme subject {obj.course_code}.")

    def perform_destroy(self, instance):
        label = getattr(instance, 'course_code', str(instance.id))
        sid = str(instance.id)
        instance.delete()
        audit_log(request=self.request, actor=self.request.user,
                  action=AuditLog.Action.DELETE, target_type='SchemeSubject',
                  target_id=sid, target_display=label,
                  reason='Sysadmin curriculum configuration',
                  description=f"Removed scheme subject {label}.")


class AssessmentComponentViewSet(_SchemeChildMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AssessmentComponentSerializer

    def get_queryset(self):
        qs = AssessmentComponentSerializer.Meta.model.objects.select_related('scheme_subject').all()
        val = self.request.query_params.get('scheme_subject', '').strip()
        if val:
            qs = qs.filter(scheme_subject_id=val)
        return qs

    def _check(self, scheme_subject_id):
        from apps.curriculum.models import SchemeSubject as SS
        ss = SS.objects.select_related('scheme').filter(id=scheme_subject_id).first()
        return self._deny_if_locked(ss.scheme if ss else None)

    def create(self, request, *args, **kwargs):
        denied = self._deny_unless_manager()
        if denied:
            return denied
        denied = self._check(request.data.get('scheme_subject'))
        if denied:
            return denied
        # Idempotent: re-posting the same (subject, type) updates the split
        # instead of failing on the unique constraint.
        ctype = request.data.get('component_type')
        ss_id = request.data.get('scheme_subject')
        if ctype and ss_id:
            existing = self.get_queryset().filter(
                scheme_subject_id=ss_id, component_type=ctype).first()
            if existing:
                ser = self.get_serializer(
                    existing, data=request.data, partial=True)
                ser.is_valid(raise_exception=True)
                updated = ser.save()
                audit_log(request=request, actor=request.user,
                          action=AuditLog.Action.UPDATE, target_type='AssessmentComponent',
                          target_id=str(updated.id),
                          target_display=f'{updated.component_type}',
                          reason='Sysadmin curriculum configuration',
                          description=f"Updated assessment split {updated.component_type} (idempotent re-post).")
                return Response(ser.data, status=status.HTTP_200_OK)
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        denied = self._deny_unless_manager()
        if denied:
            return denied
        denied = self._check(self.get_object().scheme_subject_id)
        if denied:
            return denied
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        denied = self._deny_unless_manager()
        if denied:
            return denied
        denied = self._check(self.get_object().scheme_subject_id)
        if denied:
            return denied
        return super().destroy(request, *args, **kwargs)

    def perform_create(self, serializer):
        obj = serializer.save()
        audit_log(request=self.request, actor=self.request.user,
                  action=AuditLog.Action.CREATE, target_type='AssessmentComponent',
                  target_id=str(obj.id),
                  target_display=f'{obj.component_type} ({obj.scheme_subject_id})',
                  new_value={'component_type': str(obj.component_type)},
                  reason='Sysadmin curriculum configuration',
                  description=f"Configured assessment split {obj.component_type}.")

    def perform_update(self, serializer):
        obj = serializer.save()
        audit_log(request=self.request, actor=self.request.user,
                  action=AuditLog.Action.UPDATE, target_type='AssessmentComponent',
                  target_id=str(obj.id),
                  target_display=f'{obj.component_type}',
                  reason='Sysadmin curriculum configuration',
                  description=f"Updated assessment split {obj.component_type}.")

    def perform_destroy(self, instance):
        label = str(getattr(instance, 'component_type', instance.id))
        sid = str(instance.id)
        instance.delete()
        audit_log(request=self.request, actor=self.request.user,
                  action=AuditLog.Action.DELETE, target_type='AssessmentComponent',
                  target_id=sid, target_display=label,
                  reason='Sysadmin curriculum configuration',
                  description=f"Removed assessment split {label}.")


class ElectiveGroupViewSet(_SchemeChildMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ElectiveGroupSerializer

    def get_queryset(self):
        qs = SchemeElectiveGroup.objects.prefetch_related('options').all()
        val = self.request.query_params.get('scheme', '').strip()
        if val:
            qs = qs.filter(scheme_id=val)
        return qs

    def create(self, request, *args, **kwargs):
        denied = self._deny_unless_manager()
        if denied:
            return denied
        scheme = Scheme.objects.filter(id=request.data.get('scheme')).first()
        denied = self._deny_if_locked(scheme)
        if denied:
            return denied
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        denied = self._deny_unless_manager()
        if denied:
            return denied
        denied = self._deny_if_locked(self.get_object().scheme)
        if denied:
            return denied
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        denied = self._deny_unless_manager()
        if denied:
            return denied
        denied = self._deny_if_locked(self.get_object().scheme)
        if denied:
            return denied
        return super().destroy(request, *args, **kwargs)

    def perform_create(self, serializer):
        obj = serializer.save()
        audit_log(request=self.request, actor=self.request.user,
                  action=AuditLog.Action.CREATE, target_type='ElectiveGroup',
                  target_id=str(obj.id),
                  target_display=str(obj.id),
                  reason='Sysadmin curriculum configuration',
                  description='Created elective group.')

    def perform_update(self, serializer):
        obj = serializer.save()
        audit_log(request=self.request, actor=self.request.user,
                  action=AuditLog.Action.UPDATE, target_type='ElectiveGroup',
                  target_id=str(obj.id),
                  target_display=str(obj.id),
                  reason='Sysadmin curriculum configuration',
                  description='Updated elective group.')

    def perform_destroy(self, instance):
        sid = str(instance.id)
        instance.delete()
        audit_log(request=self.request, actor=self.request.user,
                  action=AuditLog.Action.DELETE, target_type='ElectiveGroup',
                  target_id=sid, target_display=sid,
                  reason='Sysadmin curriculum configuration',
                  description='Removed elective group.')


class ElectiveOptionViewSet(_SysadminWriteMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ElectiveOptionSerializer

    def get_queryset(self):
        qs = SchemeElectiveOption.objects.select_related('elective_group', 'subject').all()
        val = self.request.query_params.get('elective_group', '').strip()
        if val:
            qs = qs.filter(elective_group_id=val)
        return qs

    def create(self, request, *args, **kwargs):
        denied = self._deny_unless_manager()
        if denied:
            return denied
        grp = SchemeElectiveGroup.objects.select_related('scheme').filter(
            id=request.data.get('elective_group')).first()
        if grp and not grp.scheme.is_mutable:
            return Response({'detail': 'Parent scheme is immutable. Create a new version.'},
                            status=status.HTTP_400_BAD_REQUEST)
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        denied = self._deny_unless_manager()
        if denied:
            return denied
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        denied = self._deny_unless_manager()
        if denied:
            return denied
        return super().destroy(request, *args, **kwargs)

    def perform_create(self, serializer):
        obj = serializer.save()
        audit_log(request=self.request, actor=self.request.user,
                  action=AuditLog.Action.CREATE, target_type='ElectiveOption',
                  target_id=str(obj.id), target_display=str(obj.id),
                  reason='Sysadmin curriculum configuration',
                  description='Created elective option.')

    def perform_update(self, serializer):
        obj = serializer.save()
        audit_log(request=self.request, actor=self.request.user,
                  action=AuditLog.Action.UPDATE, target_type='ElectiveOption',
                  target_id=str(obj.id), target_display=str(obj.id),
                  reason='Sysadmin curriculum configuration',
                  description='Updated elective option.')

    def perform_destroy(self, instance):
        sid = str(instance.id)
        instance.delete()
        audit_log(request=self.request, actor=self.request.user,
                  action=AuditLog.Action.DELETE, target_type='ElectiveOption',
                  target_id=sid, target_display=sid,
                  reason='Sysadmin curriculum configuration',
                  description='Removed elective option.')
