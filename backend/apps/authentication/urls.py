"""
Authentication URL configuration.

Endpoints:
- POST /api/v1/auth/login/           - Authenticate and issue tokens
- POST /api/v1/auth/refresh/         - Refresh access token via cookie
- POST /api/v1/auth/logout/          - Blacklist refresh token and clear cookie
- GET  /api/v1/auth/me/              - Retrieve user profile and roles
- POST /api/v1/auth/change-password/ - Change password with history checks
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.authentication.views import (
    ChangePasswordView,
    CurrentUserView,
    LoginView,
    LogoutView,
    RoleAssignmentViewSet,
    RoleViewSet,
    TokenRefreshView,
    UserManagementViewSet,
)

router = DefaultRouter()
router.register('roles', RoleViewSet, basename='roles')
router.register('users', UserManagementViewSet, basename='admin-users')
router.register('role-assignments', RoleAssignmentViewSet, basename='role-assignments')

urlpatterns = [
    path('login/', LoginView.as_view(), name='auth-login'),
    path('refresh/', TokenRefreshView.as_view(), name='auth-refresh'),
    path('logout/', LogoutView.as_view(), name='auth-logout'),
    path('me/', CurrentUserView.as_view(), name='auth-me'),
    path('change-password/', ChangePasswordView.as_view(), name='auth-change-password'),
    path('', include(router.urls)),
]

