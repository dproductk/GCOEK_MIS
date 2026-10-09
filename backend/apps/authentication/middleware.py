"""
MustChangePassword enforcement middleware.

When a user account has must_change_password=True, every authenticated
API request is blocked with HTTP 403 except:
  - POST /api/v1/auth/change-password/
  - POST /api/v1/auth/logout/
  - POST /api/v1/auth/refresh/      (needed to stay alive)
  - GET  /api/v1/auth/me/            (needed for the frontend to detect the flag)

Without this, the flag is advisory-only and any user can ignore it.
"""
import json
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin

# Endpoints allowed while must_change_password=True (exact matches).
_ALLOWED_PATHS = frozenset([
    '/api/v1/auth/change-password/',
    '/api/v1/auth/logout/',
    '/api/v1/auth/refresh/',
    '/api/v1/auth/me/',
])


class MustChangePasswordMiddleware(MiddlewareMixin):
    """Block API access for accounts that must change their password."""

    def process_request(self, request):
        # Endpoints allowed while must_change_password=True pass through immediately.
        if request.path in _ALLOWED_PATHS:
            return None

        # Session-authenticated users are visible here directly. JWT users are
        # NOT resolved until DRF dispatch, so resolve them here via a single
        # indexed lookup. Cost: one extra user query per request on views with
        # explicit permission_classes (views using DEFAULT_PERMISSION_CLASSES
        # are covered by MustChangePasswordPermission without this). Correctness
        # first: without this block, JWT users bypass enforcement entirely on
        # explicit-permission views (verified live: departments/ returned 200).
        user = getattr(request, 'user', None)
        if user is None or not user.is_authenticated:
            try:
                from rest_framework_simplejwt.authentication import JWTAuthentication
                auth_result = JWTAuthentication().authenticate(request)
                if auth_result:
                    user, _ = auth_result
                    request.user = user
            except Exception:
                pass

        if user and user.is_authenticated and getattr(user, 'must_change_password', False):
            return JsonResponse(
                {
                    'detail': 'You must change your password before accessing this resource.',
                    'code': 'must_change_password',
                },
                status=403,
            )
        return None
