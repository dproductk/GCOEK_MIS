"""
Field-level encryption for sensitive PII (Aadhaar, bank account numbers).

Uses Fernet (AES-128-CBC + HMAC) from `cryptography`, with the key supplied
via the FIELD_ENCRYPTION_KEY environment variable (see settings).

decrypt_value() is migration-tolerant: values written before encryption was
enabled (plaintext digits or "encrypted_..." seed placeholders) are returned
as-is so existing rows keep working until re-saved encrypted.

encrypt_value() fails closed in production: when no key is configured it
logs a security warning and — unless DEBUG is on — raises instead of
silently storing plaintext in a column callers believe is encrypted.
"""
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

_fernet = None
_fernet_error = None


def _get_fernet():
    global _fernet, _fernet_error
    if _fernet is not None:
        return _fernet
    if _fernet_error is not None:
        return None
    key = getattr(settings, 'FIELD_ENCRYPTION_KEY', '') or ''
    if not key:
        return None
    try:
        from cryptography.fernet import Fernet
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
        return _fernet
    except Exception as exc:  # invalid key format etc.
        _fernet_error = exc
        return None


def is_encryption_configured():
    return _get_fernet() is not None


def encrypt_value(plaintext):
    """Encrypt a string value. Returns (ciphertext_str)."""
    if plaintext is None:
        return ''
    text = str(plaintext)
    if text == '':
        return ''
    fernet = _get_fernet()
    if fernet is None:
        # No key configured: never silently store plaintext where callers
        # expect ciphertext. Dev/test (DEBUG) keeps working with a loudly
        # logged warning; production fails closed so the write is retried
        # after the key is configured instead of leaking PII.
        logger.warning(
            'encrypt_value without FIELD_ENCRYPTION_KEY: refusing silent '
            'plaintext storage (DEBUG=%s).',
            bool(getattr(settings, 'DEBUG', False)),
        )
        if not getattr(settings, 'DEBUG', False):
            from django.core.exceptions import ImproperlyConfigured
            raise ImproperlyConfigured(
                'FIELD_ENCRYPTION_KEY is required to store sensitive values.'
            )
        return text
    return fernet.encrypt(text.encode()).decode()


def require_encryption_for_write():
    """Raise DRF ValidationError when sensitive writes cannot be encrypted.

    Call at the top of any view path that persists Aadhaar/PAN/bank numbers
    when encryption is unavailable outside DEBUG. Returns None when writes
    are safe. Keeping this check in views (not encrypt_value) lets API
    callers get a 400/503-style response instead of a 500.
    """
    if is_encryption_configured() or getattr(settings, 'DEBUG', False):
        return None
    from rest_framework.exceptions import ValidationError
    raise ValidationError(
        'Encrypted storage is currently unavailable. '
        'Sensitive numbers cannot be saved right now; contact the administrator.'
    )


def decrypt_value(stored):
    """Decrypt a stored value. Plaintext legacy values pass through."""
    if stored is None:
        return None
    text = str(stored)
    if text == '':
        return ''
    fernet = _get_fernet()
    if fernet is None:
        return text
    # Heuristic: Fernet tokens are base64 url-safe and ~100+ chars for short
    # inputs; legacy plaintext (digits, "encrypted_...") is short or non-b64.
    try:
        from cryptography.fernet import InvalidToken
    except Exception:
        return text
    try:
        return fernet.decrypt(text.encode()).decode()
    except Exception:
        # Legacy plaintext or seed placeholder — return as-is.
        return text
