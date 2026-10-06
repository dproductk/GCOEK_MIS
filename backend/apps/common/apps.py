"""
Common app — shared base models, validators, and utilities used across all domains.

This app provides:
- UUIDPrimaryKeyModel: base model with UUID primary key
- TimestampedModel: base model with created_at/updated_at timestamps
- BaseModel: combined UUID + timestamped base for all domain models
"""
from django.apps import AppConfig


class CommonConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.common'
    verbose_name = 'Common Utilities'
