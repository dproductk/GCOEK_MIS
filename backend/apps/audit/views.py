"""
Views for querying immutable institutional audit logs.
Strictly read-only and restricted to SYSADMIN and ADMIN_HEAD.
"""
from rest_framework import permissions, status, viewsets
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


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only audit log viewer.
    Supports filtering by action, target_type, actor_username, and full-text search.
    """

    permission_classes = [permissions.IsAuthenticated, IsAuditViewer]
    serializer_class = AuditLogSerializer
    queryset = AuditLog.objects.all().order_by('-timestamp')

    def get_queryset(self):
        qs = super().get_queryset()
        action_param = self.request.query_params.get('action')
        target_type = self.request.query_params.get('target_type')
        actor = self.request.query_params.get('actor')
        search = self.request.query_params.get('search')

        if action_param:
            qs = qs.filter(action=action_param)
        if target_type:
            qs = qs.filter(target_type__iexact=target_type)
        if actor:
            qs = qs.filter(actor_username__icontains=actor)
        if search:
            search = search.strip()
            qs = qs.filter(
                description__icontains=search
            ) | qs.filter(target_display__icontains=search) | qs.filter(reason__icontains=search)

        return qs
