"""
Serializers for Audit Log entries.
All fields are strictly read-only.
"""
from rest_framework import serializers
from apps.audit.models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    action_display = serializers.CharField(source='get_action_display', read_only=True)

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
