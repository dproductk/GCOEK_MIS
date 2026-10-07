"""
Views for querying immutable institutional audit logs.
Strictly read-only and restricted to SYSADMIN and ADMIN_HEAD.

Per SECURITY.md Sec 12/24: audit trail is append-only. This module offers
filtered browsing plus CSV export for archival/review. Export never deletes
rows — retention/deletion requires an explicit approved policy.
"""
import csv
from datetime import datetime

from django.http import HttpResponse
from django.utils.dateparse import parse_date, parse_datetime
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.audit.models import AuditLog
from apps.audit.serializers import AuditLogSerializer
from apps.authentication.permissions import get_user_scopes


class IsAuditViewer(permissions.BasePermission):
    """Only SYSADMIN or ADMIN_HEAD can inspect the security audit trail."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        scopes = get_user_scopes(request.user)
        return scopes['is_system_wide'] or 'ADMIN_HEAD' in scopes['roles'] or 'SYSADMIN' in scopes['roles']


def _parse_bound(value, end_of_day=False):
    """Accept YYYY-MM-DD or full datetime; return aware datetime or None."""
    if not value:
        return None
    value = str(value).strip()
    dt = parse_datetime(value)
    if dt is not None:
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        return dt
    day = parse_date(value)
    if day is None:
        # Plain YYYY-MM-DDTHH:MM without seconds sometimes fails parse_datetime.
        try:
            dt = datetime.fromisoformat(value)
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt, timezone.get_current_timezone())
            return dt
        except (ValueError, TypeError):
            return None
    if end_of_day:
        dt = datetime.combine(day, datetime.max.time())
    else:
        dt = datetime.combine(day, datetime.min.time())
    return timezone.make_aware(dt, timezone.get_current_timezone())


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only audit log viewer.

    Filters (all applied in PostgreSQL, AGENTS.md Sec 12):
      action, target_type, actor (username icontains), target_id,
      date_from / date_to (YYYY-MM-DD or ISO datetime, inclusive),
      search (description / target_display / reason / actor_username).
    Ordering: ?ordering=timestamp | -timestamp (default -timestamp).
    Standard DRF pagination applies (?page=). Use /export/ for CSV archival.
    """

    permission_classes = [permissions.IsAuthenticated, IsAuditViewer]
    serializer_class = AuditLogSerializer
    queryset = AuditLog.objects.select_related('actor').all().order_by('-timestamp')

    def _filtered_queryset(self):
        qs = AuditLog.objects.select_related('actor').all().order_by('-timestamp')
        params = self.request.query_params
        action_param = (params.get('action') or '').strip()
        target_type = (params.get('target_type') or '').strip()
        actor = (params.get('actor') or '').strip()
        target_id = (params.get('target_id') or '').strip()
        search = (params.get('search') or '').strip()

        if action_param:
            qs = qs.filter(action=action_param)
        if target_type:
            qs = qs.filter(target_type__iexact=target_type)
        if actor:
            qs = qs.filter(actor_username__icontains=actor)
        if target_id:
            qs = qs.filter(target_id__icontains=target_id)
        date_from = _parse_bound(params.get('date_from'), end_of_day=False)
        date_to = _parse_bound(params.get('date_to'), end_of_day=True)
        if date_from:
            qs = qs.filter(timestamp__gte=date_from)
        if date_to:
            qs = qs.filter(timestamp__lte=date_to)
        if search:
            qs = (
                qs.filter(description__icontains=search)
                | qs.filter(target_display__icontains=search)
                | qs.filter(reason__icontains=search)
                | qs.filter(actor_username__icontains=search)
                | qs.filter(target_type__icontains=search)
            ).distinct()

        ordering = (params.get('ordering') or '').strip()
        if ordering in ('timestamp', '-timestamp'):
            qs = qs.order_by(ordering)
        return qs

    def get_queryset(self):
        return self._filtered_queryset()

    @action(detail=False, methods=['get'], url_path='export')
    def export(self, request):
        """Download filtered audit trail as CSV (archival, never deletes rows).

        Honors the same filters as list. Capped at 10,000 newest rows to
        protect the database (AGENTS.md Sec 13/22). For larger archives,
        narrow date_from/date_to and export in slices.
        """
        qs = self._filtered_queryset()[:10000]
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = (
            f'attachment; filename="audit_logs_{timestamp}.csv"'
        )
        def _csv_cell(value):
            """Neutralize spreadsheet formula injection (CSV injection).

            Cells starting with =,+,-,@ (after leading whitespace) execute on
            import into Excel/Sheets. Prefix them so user-controlled audit text
            (description, reason, user-agent, display names) stays inert.
            """
            text = '' if value is None else str(value)
            if text.lstrip().startswith(('=', '+', '-', '@')):
                return "'" + text
            return text

        writer = csv.writer(response)
        writer.writerow([
            'id', 'timestamp', 'actor_username', 'actor_role', 'action',
            'action_display', 'target_type', 'target_id', 'target_display',
            'description', 'reason', 'old_value', 'new_value',
            'ip_address', 'user_agent',
        ])
        for log in qs.iterator(chunk_size=1000):
            import json as _json
            writer.writerow([
                _csv_cell(str(log.id)),
                _csv_cell(log.timestamp.isoformat() if log.timestamp else ''),
                _csv_cell(log.actor_username or ''),
                _csv_cell(log.actor_role or ''),
                _csv_cell(log.action or ''),
                _csv_cell(log.get_action_display() if hasattr(log, 'get_action_display') else ''),
                _csv_cell(log.target_type or ''),
                _csv_cell(log.target_id or ''),
                _csv_cell(log.target_display or ''),
                _csv_cell(log.description or ''),
                _csv_cell(log.reason or ''),
                _csv_cell(_json.dumps(log.old_value, default=str) if log.old_value is not None else ''),
                _csv_cell(_json.dumps(log.new_value, default=str) if log.new_value is not None else ''),
                _csv_cell(str(log.ip_address or '')),
                _csv_cell(log.user_agent or ''),
            ])
        # The export itself is a security-relevant read; record it without
        # logging secrets (SECURITY.md Sec 12 never-log list respected by
        # the audit service redaction).
        from apps.audit.services import audit_log as _audit
        try:
            _audit(
                request=request,
                action=AuditLog.Action.EXPORT,
                target_type='AuditLog',
                target_display='Audit trail CSV export',
                reason='Sysadmin audit archival/review',
                description=(
                    'Exported filtered audit trail to CSV '
                    f'(action={request.query_params.get("action", "")}, '
                    f'target_type={request.query_params.get("target_type", "")}).'
                ),
            )
        except Exception:
            pass
        return response
