"""
Serializers for Audit Log entries.
All fields are strictly read-only.
"""
from rest_framework import serializers
from apps.audit.models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    action_display = serializers.CharField(source='get_action_display', read_only=True)
    # Privacy hardening: ip_address is masked to /24 prefix for callers below
    # ADMIN_HEAD. Full IP is surfaced to superuser / SYSADMIN / ADMIN_HEAD.
    ip_address = serializers.SerializerMethodField()

    def get_ip_address(self, obj):
        request = self.context.get('request')
        if request is None:
            return None
        user = request.user
        if not user or not user.is_authenticated:
            return None
        # Full IP for superusers / SYSADMIN / ADMIN_HEAD (incident forensics).
        if user.is_superuser or getattr(user, 'user_type', '') == 'SYSADMIN':
            return str(obj.ip_address) if obj.ip_address else None
        from apps.authentication.permissions import user_has_role
        if user_has_role(user, 'ADMIN_HEAD'):
            return str(obj.ip_address) if obj.ip_address else None
        # ADMIN_HEAD and others see subnet only (last octet masked)
        ip = str(obj.ip_address) if obj.ip_address else None
        if ip:
            parts = ip.split('.')
            if len(parts) == 4:
                return f"{parts[0]}.{parts[1]}.{parts[2]}.*"
        return ip

    class Meta:
        model = AuditLog
        fields = [
            'id',
            'actor',
            'actor_username',
            'actor_role',
            'action',
            'action_display',
            'description',
            'target_type',
            'target_id',
            'target_display',
            'old_value',
            'new_value',
            'reason',
            'ip_address',
            'user_agent',
            'timestamp',
        ]
        read_only_fields = fields
