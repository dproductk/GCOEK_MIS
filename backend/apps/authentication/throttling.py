"""
Rate throttling for authentication endpoints.

Replaces the original single per-IP 'login' scope (5/minute) with a
two-layer scheme so that many students sharing one campus/lab IP do not
throttle each other, while abuse protection is preserved:

1. LoginUserRateThrottle — 5/min keyed per (client IP + target account).
   Used for:
     - POST /auth/login/           → keyed on the submitted username
     - POST /auth/change-password/ → keyed on the authenticated user's pk
   Twenty different students behind one lab IP each get their own bucket,
   so simultaneous sign-ins never compete. An attacker guessing ONE
   account's password is still capped at 5 attempts/min from any single IP,
   on top of the account lockout (5 consecutive failures → 15 min lock).

2. LoginIPRateThrottle — 30/min keyed per client IP as a backstop against
   password spraying (one candidate password tried across many different
   usernames) and general abuse from a single network. Also applied to
   token refresh, which is high-frequency by design and has no username
   in the request body.

Rates are configured in settings.DEFAULT_THROTTLE_RATES ('login_user',
'login_ip'). Client-ident resolution (REMOTE_ADDR / X-Forwarded-For with
settings.NUM_PROXIES support) is inherited from DRF's SimpleRateThrottle.
"""
from rest_framework.throttling import SimpleRateThrottle

# Bound cache-key length even if a client submits an unusually long username.
_MAX_USERNAME_KEY_CHARS = 150


class LoginUserRateThrottle(SimpleRateThrottle):
    """5/min per (client IP, account) — per-student buckets, per-account cap."""

    scope = 'login_user'

    def get_cache_key(self, request, view):
        ident = self.get_ident(request)
        if not ident:
            # DRF convention: None cache key means "do not throttle".
            return None

        target = None
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated:
            # Signed-in endpoint (change-password): bucket on the account
            # itself, regardless of IP — protects the user's own password
            # field from brute force.
            target = f'user:{user.pk}'
        else:
            if isinstance(request.data, dict):
                username = str(request.data.get('username', '')).strip().lower()
                if username:
                    # lower() merges case variants of the same username so an
                    # attacker cannot open a fresh bucket by flipping case.
                    target = f'username:{username[:_MAX_USERNAME_KEY_CHARS]}'

        if target is None:
            # No account identity available (malformed/missing body).
            # These anonymous attempts share one bucket per IP; requests
            # without an IP are excluded by the guard above.
            target = 'anon'

        return self.cache_format % {
            'scope': self.scope,
            'ident': f'{ident}_{target}',
        }


class LoginIPRateThrottle(SimpleRateThrottle):
    """30/min per client IP — backstop against password spraying."""

    scope = 'login_ip'

    def get_cache_key(self, request, view):
        ident = self.get_ident(request)
        if not ident:
            return None
        return self.cache_format % {'scope': self.scope, 'ident': ident}
