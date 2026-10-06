"""
Common base models for the GCOEK MIS project.

All domain models should inherit from BaseModel which provides:
- UUID primary key (prevents enumeration, separates internal ID from business IDs)
- Automatic created_at / updated_at timestamps
- Consistent __str__ and meta defaults

Per DATABASE_ARCHITECTURE_V2.md:
- UUID v4 for internal primary keys
- Business identifiers (enrollment_no, employee_code, application_id) use separate
  UNIQUE-constrained columns, never as PKs
"""
import uuid

from django.db import models


class UUIDPrimaryKeyModel(models.Model):
    """Abstract base model that uses UUID as the primary key."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text='Internal UUID primary key.',
    )

    class Meta:
        abstract = True


class TimestampedModel(models.Model):
    """Abstract base model with automatic created/updated timestamps."""

    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text='Record creation timestamp.',
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text='Last modification timestamp.',
    )

    class Meta:
        abstract = True


class BaseModel(UUIDPrimaryKeyModel, TimestampedModel):
    """
    Combined base model for all GCOEK MIS domain models.

    Provides:
    - id: UUID v4 primary key
    - created_at: auto-set on creation
    - updated_at: auto-set on every save

    Usage:
        class Student(BaseModel):
            enrollment_no = models.CharField(max_length=20, unique=True)
            ...
    """

    class Meta:
        abstract = True
        ordering = ['-created_at']
