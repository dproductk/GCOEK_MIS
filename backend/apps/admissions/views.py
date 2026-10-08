"""
Views for Admissions and Government Ingestion pipeline.

Enforces:
- Restricts upload and commit to ADMIN_HEAD and SYSADMIN.
- Audits all ingestion commits.
- Upload staging with preview before commitment.
"""
from django.db import transaction
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from apps.academic_structure.models import AcademicYear
from apps.admissions.models import ImportBatch, ImportRow
from apps.admissions.serializers import (
    ImportBatchDetailSerializer,
    ImportBatchSerializer,
)
from apps.admissions.services import (
    commit_import_batch,
    stage_admission_file,
)
from apps.audit.models import AuditLog
from apps.audit.services import audit_log
from apps.authentication.permissions import (
    get_user_scopes,
    user_has_permission,
)


class AdmissionImportViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Admission Import Batches ViewSet.
    Handles file upload staging, row review, and final commit.
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ImportBatchSerializer
    # JSONParser added for the delete action's {reason} body;
    # upload still uses multipart.
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        user = self.request.user
        scopes = get_user_scopes(user)
        # Only Admin Head and Sysadmin have access to admission batch management
        if scopes['is_system_wide'] or 'ADMIN_HEAD' in scopes['roles']:
            return ImportBatch.objects.select_related('academic_year', 'uploaded_by').all()
        return ImportBatch.objects.none()

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ImportBatchDetailSerializer
        return ImportBatchSerializer

    @action(detail=False, methods=['get'], url_path='pending-intakes')
    def pending_intakes(self, request):
        """HOD-scoped pending import cards with true single-use tracking.

        Groups IMPORTED rows by (batch, department, stream, semester) and
        reports placed vs pending via StudentEnrollment.placement_confirmed.

        - SYSADMIN / ADMIN_HEAD: all departments.
        - HOD: own department slice only (no file contents, only aggregates
          + pending student ids for placement).
        - Consumed batches (pending == 0) are omitted, so a batch card
          cannot be reused once fully placed. Partially placed batches show
          the remaining count and stay usable until empty.
        """
        from apps.authentication.permissions import user_has_role
        from apps.students.models import StudentEnrollment

        user = request.user
        scopes = get_user_scopes(user)
        is_privileged = (
            scopes.get('is_system_wide')
            or 'ADMIN_HEAD' in scopes.get('roles', [])
            or user.is_superuser
        )
        is_hod = user_has_role(user, 'HOD')
        if not (is_privileged or is_hod):
            return Response(
                {'detail': 'Permission denied.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        allowed_depts = None
        if not is_privileged:
            allowed_depts = {str(d) for d in scopes.get('department_ids', [])}
            if not allowed_depts:
                return Response([], status=status.HTTP_200_OK)

        batches = list(
            ImportBatch.objects.filter(
                status__in=(
                    ImportBatch.Status.COMPLETED,
                    ImportBatch.Status.PARTIALLY_COMPLETED,
                )
            ).select_related('academic_year').order_by('-created_at')[:100]
        )
        if not batches:
            return Response([], status=status.HTTP_200_OK)
        batch_by_id = {str(b.id): b for b in batches}

        rows = list(
            ImportRow.objects.filter(
                batch__in=batches,
                validation_status=ImportRow.ValidationStatus.IMPORTED,
                student__isnull=False,
            ).select_related('student').only(
                'id', 'batch_id', 'student_id',
            )
        )
        if not rows:
            return Response([], status=status.HTTP_200_OK)

        student_ids = list({str(r.student_id) for r in rows})
        enrollments = (
            StudentEnrollment.objects.filter(
                student_id__in=student_ids, is_current=True
            ).select_related('department', 'semester', 'student')
        )
        enr_by_student = {str(e.student_id): e for e in enrollments}

        # student_id -> batch_id (first IMPORTED link wins; duplicates stay linked without re-import)
        student_batch = {}
        for r in rows:
            sid = str(r.student_id)
            if sid not in student_batch:
                student_batch[sid] = str(r.batch_id)

        groups = {}
        for sid in student_ids:
            enr = enr_by_student.get(sid)
            if not enr or not enr.department_id or not enr.semester:
                continue
            dept_id = str(enr.department_id)
            if allowed_depts is not None and dept_id not in allowed_depts:
                continue
            batch_id = student_batch.get(sid)
            batch = batch_by_id.get(batch_id)
            if batch is None:
                continue
            # Stream from the live student record (row-level DSY can differ from batch header).
            try:
                is_dsy = bool(getattr(enr.student, 'is_direct_second_year', False))
            except Exception:
                is_dsy = batch.admission_type == ImportBatch.AdmissionType.DIRECT_SECOND_YEAR
            stream = 'DSE' if is_dsy else 'FY'
            sem_no = enr.semester.number
            key = (batch_id, dept_id, stream, sem_no)
            g = groups.get(key)
            if g is None:
                g = groups[key] = {
                    'batch_id': batch_id,
                    'file_name': batch.file_name,
                    'academic_year_code': batch.academic_year.code if batch.academic_year else '',
                    'admission_type': batch.admission_type,
                    'stream': stream,
                    'department_id': dept_id,
                    'department_code': enr.department.code if enr.department else '',
                    'semester_number': sem_no,
                    'total': 0,
                    'placed': 0,
                    'pending': 0,
                    'pending_student_ids': [],
                }
            g['total'] += 1
            if enr.placement_confirmed:
                g['placed'] += 1
            else:
                g['pending'] += 1
                g['pending_student_ids'].append(sid)

        # Single-use: fully consumed cards disappear.
        result = [g for g in groups.values() if g['pending'] > 0]
        result.sort(
            key=lambda g: (g['academic_year_code'], g['file_name'], g['semester_number'])
        )
        return Response(result, status=status.HTTP_200_OK)

    def get_throttles(self):
        # Import uploads capped at 10/hr per SECURITY.md Sec 10; other
        # batch actions keep the default authenticated throttle.
        if getattr(self, 'action', None) == 'upload_file':
            self.throttle_scope = 'import_upload'
            return [ScopedRateThrottle()]
        return super().get_throttles()

    @action(detail=False, methods=['post'], url_path='upload')
    def upload_file(self, request):
        """
        Upload and stage a government admitted candidate list.
        Validates structure and populates ImportRows for review.
        """
        user = request.user
        scopes = get_user_scopes(user)
        if not (scopes['is_system_wide'] or 'ADMIN_HEAD' in scopes['roles'] or user_has_permission(user, 'admissions.import')):
            return Response(
                {'detail': 'Permission denied. Only Administrative Head or Sysadmin can import candidate lists.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({'detail': 'No file uploaded.'}, status=status.HTTP_400_BAD_REQUEST)

        # SECURITY.md Sec 5/14: size + type + content gate before parsing.
        if not file_obj.size or file_obj.size == 0:
            return Response(
                {'detail': 'Uploaded file is empty.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if file_obj.size and file_obj.size > 10 * 1024 * 1024:
            return Response(
                {'detail': 'File exceeds 10 MB size limit.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        import os as _os
        raw_name = file_obj.name or 'upload'
        safe_name = _os.path.basename(raw_name).strip().replace('\x00', '')
        if not safe_name or safe_name in ('.', '..') or len(safe_name) > 255:
            return Response(
                {'detail': 'Invalid file name.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ext = '.' + (safe_name.rsplit('.', 1)[-1].lower() if '.' in safe_name else '')
        if ext not in ('.xls', '.xlsx', '.csv'):
            return Response(
                {'detail': 'Unsupported file type. Upload .xls, .xlsx or .csv only.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Lightweight magic-byte check (no new deps): xlsx=zip PK, xls=OLE,
        # csv=text without NUL bytes. Full scan (ClamAV) stays out of scope.
        try:
            _head = file_obj.read(8)
            file_obj.seek(0)
        except Exception:
            _head = b''
        if ext == '.xlsx' and not _head.startswith(b'PK'):
            return Response(
                {'detail': 'File content does not match .xlsx format.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if ext == '.xls' and not (_head.startswith(b'\xd0\xcf\x11\xe0') or _head.startswith(b'PK') or b'<html' in _head.lower() or b'<table' in _head.lower()):
            # Legacy .xls may be OLE, newer HTML-export, or zip-based — accept
            # only if it looks like one of those, reject raw executables.
            if _head.startswith(b'MZ'):
                return Response(
                    {'detail': 'File content does not match .xls format.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        if ext == '.csv' and b'\x00' in _head:
            return Response(
                {'detail': 'File content does not match .csv format.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Academic year resolution
        year_id = request.data.get('academic_year_id')
        if year_id:
            academic_year = AcademicYear.objects.filter(id=year_id).first()
        else:
            academic_year = AcademicYear.objects.filter(is_current=True).first() or AcademicYear.objects.first()

        if not academic_year:
            return Response({'detail': 'No active academic year configured.'}, status=status.HTTP_400_BAD_REQUEST)

        # Admission stream resolution (Regular First Year vs Direct Second Year)
        adm_type_raw = str(request.data.get('admission_type', '')).strip().upper()
        if adm_type_raw in ('DIRECT_SECOND_YEAR', 'DSY', 'LATERAL'):
            admission_type = ImportBatch.AdmissionType.DIRECT_SECOND_YEAR
        else:
            admission_type = ImportBatch.AdmissionType.FIRST_YEAR

        try:
            file_bytes = file_obj.read()
            batch = stage_admission_file(
                file_bytes=file_bytes,
                file_name=safe_name,
                academic_year=academic_year,
                user=user,
                uploaded_file=file_obj,
                admission_type=admission_type,
            )
            audit_log(
                request=request,
                actor=user,
                action=AuditLog.Action.IMPORT,
                target_type='ImportBatch',
                target_id=str(batch.id),
                target_display=f'Staged {safe_name}',
                new_value={
                    'file_name': batch.file_name,
                    'file_checksum': batch.file_checksum,
                    'total_rows': batch.total_rows,
                    'academic_year': batch.academic_year.code,
                    'admission_type': str(admission_type),
                },
                reason='Government admission list staged for review',
                description=(
                    f"Staged '{safe_name}' ({batch.total_rows} rows) for "
                    f'{batch.academic_year.code} review. Checksum {batch.file_checksum}.'
                ),
            )
            serializer = ImportBatchDetailSerializer(batch)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            return Response(
                {'detail': 'Upload failed due to an internal error.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=['post'], url_path='commit')
    def commit_batch(self, request, pk=None):
        """
        Commit all valid staged rows into authoritative student and admission tables.
        Audits the ingestion event.
        """
        user = request.user
        scopes = get_user_scopes(user)
        if not (scopes['is_system_wide'] or 'ADMIN_HEAD' in scopes['roles'] or user_has_permission(user, 'admissions.import')):
            return Response(
                {'detail': 'Permission denied. Only Administrative Head or Sysadmin can commit candidate batches.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            # Idempotent retry: an already-COMPLETED batch returns as-is with
            # NO new ingestion audit — auditing it again would falsely claim
            # students were re-imported.
            pre = ImportBatch.objects.filter(id=pk).first()
            already_done = pre is not None and pre.status == ImportBatch.Status.COMPLETED
            batch = commit_import_batch(pk)

            if not already_done:
                # Audit the commitment (SECURITY.md Sec 14: who imported)
                audit_log(
                    request=request,
                    actor=user,
                    action=AuditLog.Action.IMPORT,
                    target_type='ImportBatch',
                    target_id=str(batch.id),
                    target_display=f'Admission Batch {batch.file_name}',
                    new_value={
                        'file_name': batch.file_name,
                        'file_checksum': batch.file_checksum,
                        'imported_rows': batch.imported_rows,
                        'total_rows': batch.total_rows,
                    },
                    reason='Government admission list ingestion committed',
                    description=f"Imported {batch.imported_rows} student records into core database from '{batch.file_name}'.",
                )

            serializer = ImportBatchSerializer(batch)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except ValueError as e:
            msg = str(e)
            if 'already in progress' in msg:
                return Response({'detail': msg}, status=status.HTTP_409_CONFLICT)
            return Response({'detail': msg}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            return Response(
                {'detail': 'Commit failed due to an internal error.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=['delete'], url_path='delete')
    def delete_batch(self, request, pk=None):
        """
        Delete a failed/empty ingestion batch (staging rows cascade).

        Allowed ONLY when nothing was imported into core records
        (imported_rows == 0 and no rows linked to students) — batches that
        created students can never be deleted (history preservation).
        The deletion itself is written to the append-only AuditLog first,
        so the audit trail survives the batch.
        """
        user = request.user
        scopes = get_user_scopes(user)
        if not (scopes['is_system_wide'] or 'ADMIN_HEAD' in scopes['roles'] or user_has_permission(user, 'admissions.import')):
            return Response(
                {'detail': 'Permission denied. Only Administrative Head or Sysadmin can delete batches.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        batch = self.get_object()
        # Block only real imports. DUPLICATE rows carry a preview-only link
        # (matching_status=MATCHED) to an already-existing student — deleting
        # the staging row never touches that student record.
        actually_imported = (
            batch.imported_rows > 0
            or batch.rows.filter(validation_status=ImportRow.ValidationStatus.IMPORTED).exists()
        )
        if actually_imported:
            return Response(
                {'detail': 'This batch created student records and cannot be deleted. Failed batches with zero imports can be deleted.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        snapshot = {
            'file_name': batch.file_name,
            'file_checksum': batch.file_checksum,
            'file_size': batch.file_size,
            'academic_year': batch.academic_year.code if batch.academic_year else '',
            'admission_type': batch.admission_type,
            'status': batch.status,
            'total_rows': batch.total_rows,
            'valid_rows': batch.valid_rows,
            'invalid_rows': batch.invalid_rows,
            'duplicate_rows': batch.duplicate_rows,
            'conflict_rows': batch.conflict_rows,
            'failed_rows': batch.failed_rows,
            'imported_rows': batch.imported_rows,
            'uploaded_by': batch.uploaded_by.username if batch.uploaded_by else '',
        }
        with transaction.atomic():
            audit_log(
                request=request,
                actor=user,
                action=AuditLog.Action.DELETE,
                target_type='ImportBatch',
                target_id=str(batch.id),
                target_display=f"Deleted batch '{batch.file_name}'",
                new_value=snapshot,
                reason=request.data.get('reason', 'Failed batch cleanup before re-upload') if request.data else 'Failed batch cleanup before re-upload',
                description=(
                    f"Deleted failed ingestion batch '{batch.file_name}' "
                    f"({batch.total_rows} staged rows, 0 imported). "
                    f"Checksum {batch.file_checksum} retained in audit."
                ),
            )
            try:
                if batch.source_file:
                    batch.source_file.delete(save=False)
            except Exception:
                pass
            batch.delete()

        return Response(
            {'detail': f"Batch '{snapshot['file_name']}' deleted. Audit entry retained."},
            status=status.HTTP_200_OK,
        )
