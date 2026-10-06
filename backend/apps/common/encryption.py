"""
Field-level encryption for sensitive PII (Aadhaar, bank account numbers).

Uses Fernet (AES-128-CBC + HMAC) from `cryptography`, with the key supplied
via the FIELD_ENCRYPTION_KEY environment variable (see settings).

decrypt_value() is migration-tolerant: values written before encryption was
enabled (plaintext digits or "encrypted_..." seed placeholders) are returned
as-is so existing rows keep working until re-saved encrypted.
"""
from django.conf import settings

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
        # No key configured (e.g. tests without env): fall back to plaintext
        # so dev/test flows keep working. Production requires the key
        # (settings raises when DEBUG=False and key is missing).
        return text
    return fernet.encrypt(text.encode()).decode()


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
