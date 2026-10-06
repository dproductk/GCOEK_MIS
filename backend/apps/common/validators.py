"""
Common validators for the GCOEK MIS project.

Shared validation utilities used across multiple domains.
"""
import re

from django.core.exceptions import ValidationError


def validate_mobile_number(value):
    """Validate Indian mobile number format (10 digits, starting with 6-9)."""
    if not re.match(r'^[6-9]\d{9}$', value):
        raise ValidationError(
            '%(value)s is not a valid Indian mobile number. '
            'Must be 10 digits starting with 6-9.',
            params={'value': value},
        )


def validate_email_format(value):
    """Validate basic email format."""
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', value):
        raise ValidationError(
            '%(value)s is not a valid email address.',
            params={'value': value},
        )


def validate_pincode(value):
    """Validate Indian PIN code (6 digits, not starting with 0)."""
    if not re.match(r'^[1-9]\d{5}$', value):
        raise ValidationError(
            '%(value)s is not a valid Indian PIN code. Must be 6 digits.',
            params={'value': value},
        )


def validate_no_special_chars(value):
    """Validate that a string contains only alphanumeric characters and spaces."""
    if not re.match(r'^[a-zA-Z0-9\s\-\.]+$', value):
        raise ValidationError(
            'Value contains invalid special characters.',
        )
