"""Small HTTP response hardening helpers shared by apps serving PII."""

#: Sensitive reveal/download responses must never sit in browser or proxy
#: caches: Aadhaar/PAN/bank numbers and ID PDFs are replayable identity data.
_NO_STORE = 'no-store, no-cache, must-revalidate'


def no_store(response):
    """Apply private no-cache headers to a response carrying sensitive data."""
    response['Cache-Control'] = _NO_STORE
    response['Pragma'] = 'no-cache'
    response['X-Content-Type-Options'] = 'nosniff'
    return response
