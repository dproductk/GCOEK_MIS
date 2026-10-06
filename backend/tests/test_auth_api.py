"""
Tests for Phase 1 Authentication APIs.

Covers:
- Login success / failure
- Account lockout after 5 failed attempts
- Token refresh with rotation and blacklisting
- Logout with token revocation
- Current user (/auth/me/) profile & roles
- Password change validation, history prevention, and must_change_password clearing
- Audit log creation for all authentication events
"""
from datetime import timedelta
import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit.models import AuditLog
from apps.authentication.models import PasswordHistory, Role, RoleAssignment

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def test_user(db):
    user = User.objects.create_user(
        username='student1',
        email='student1@gcoek.ac.in',
        password='InitialPassword123!',
        user_type=User.UserType.STUDENT,
        must_change_password=True,
    )
    role, _ = Role.objects.get_or_create(
        codename='STUDENT',
        defaults={'name': 'Student'},
    )
    RoleAssignment.objects.create(
        user=user,
        role=role,
        status=RoleAssignment.Status.ACTIVE,
    )
    return user


@pytest.mark.django_db
class TestLoginAPI:
    """Tests for POST /api/v1/auth/login/"""

    def test_login_success(self, api_client, test_user):
        response = api_client.post(
            '/api/v1/auth/login/',
            {'username': 'student1', 'password': 'InitialPassword123!'},
            format='json',
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert 'access' in data
        assert data['must_change_password'] is True
        assert data['user']['username'] == 'student1'
        assert len(data['user']['roles']) == 1
        assert data['user']['roles'][0]['codename'] == 'STUDENT'

        # Refresh token must be in HttpOnly cookie
        assert 'refresh_token' in response.cookies
        cookie = response.cookies['refresh_token']
        assert cookie['httponly'] is True

        # Audit log verification
        audit = AuditLog.objects.filter(
            actor=test_user,
            action=AuditLog.Action.LOGIN,
        ).first()
        assert audit is not None
        assert audit.target_type == 'User'

    def test_login_invalid_credentials(self, api_client, test_user):
        response = api_client.post(
            '/api/v1/auth/login/',
            {'username': 'student1', 'password': 'WrongPassword!'},
            format='json',
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        test_user.refresh_from_db()
        assert test_user.failed_login_attempts == 1

        # Audit log for failed attempt
        audit = AuditLog.objects.filter(
            action=AuditLog.Action.LOGIN_FAILED,
            target_display='student1',
        ).first()
        assert audit is not None

    def test_account_lockout_after_5_failures(self, api_client, test_user):
        # Isolate from the login throttle bucket (shared test-client IP).
        from django.core.cache import cache
        cache.clear()
        # Attempt 5 incorrect logins
        for i in range(5):
            response = api_client.post(
                '/api/v1/auth/login/',
                {'username': 'student1', 'password': 'WrongPassword!'},
                format='json',
            )
            assert response.status_code == status.HTTP_400_BAD_REQUEST

        test_user.refresh_from_db()
        assert test_user.failed_login_attempts >= 5
        assert test_user.locked_until is not None
        assert test_user.locked_until > timezone.now()

        # 6th attempt with correct credentials should be rejected due to lockout.
        # Clear the login throttle so this asserts the lockout logic itself
        # (throttling has its own dedicated test).
        cache.clear()
        response = api_client.post(
            '/api/v1/auth/login/',
            {'username': 'student1', 'password': 'InitialPassword123!'},
            format='json',
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        error_msg = str(response.json())
        assert 'locked' in error_msg.lower()


@pytest.mark.django_db
class TestTokenRefreshAndLogout:
    """Tests for token refresh rotation and logout revocation."""

    def test_token_refresh_rotation(self, api_client, test_user):
        refresh = RefreshToken.for_user(test_user)
        refresh_str = str(refresh)

        # Set cookie and request refresh
        api_client.cookies['refresh_token'] = refresh_str
        response = api_client.post('/api/v1/auth/refresh/', {}, format='json')

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert 'access' in data

        # New refresh token must be issued in cookie
        assert 'refresh_token' in response.cookies
        new_refresh_str = response.cookies['refresh_token'].value
        assert new_refresh_str != refresh_str

        # Old refresh token must now be blacklisted
        api_client.cookies['refresh_token'] = refresh_str
        failed_response = api_client.post('/api/v1/auth/refresh/', {}, format='json')
        assert failed_response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_logout_blacklists_token_and_clears_cookie(self, api_client, test_user):
        refresh = RefreshToken.for_user(test_user)
        access = str(refresh.access_token)
        refresh_str = str(refresh)

        api_client.cookies['refresh_token'] = refresh_str
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')

        response = api_client.post('/api/v1/auth/logout/', {}, format='json')
        assert response.status_code == status.HTTP_200_OK

        # Cookie deleted
        cookie = response.cookies.get('refresh_token')
        assert cookie is None or cookie.value == ''

        # Token is blacklisted
        api_client.credentials()
        api_client.cookies['refresh_token'] = refresh_str
        refresh_response = api_client.post('/api/v1/auth/refresh/', {}, format='json')
        assert refresh_response.status_code == status.HTTP_401_UNAUTHORIZED

        # Audit log for logout
        assert AuditLog.objects.filter(
            actor=test_user,
            action=AuditLog.Action.LOGOUT,
        ).exists()


@pytest.mark.django_db
class TestCurrentUserAndChangePassword:
    """Tests for /auth/me/ and /auth/change-password/"""

    def test_current_user_me(self, api_client, test_user):
        refresh = RefreshToken.for_user(test_user)
        access = str(refresh.access_token)
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')

        response = api_client.get('/api/v1/auth/me/')
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data['username'] == 'student1'
        assert data['email'] == 'student1@gcoek.ac.in'
        assert data['user_type'] == 'STUDENT'
        assert len(data['roles']) == 1

    def test_change_password_enforces_rules(self, api_client, test_user):
        refresh = RefreshToken.for_user(test_user)
        access = str(refresh.access_token)
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')

        # 1. Reject length < 12
        res = api_client.post(
            '/api/v1/auth/change-password/',
            {
                'current_password': 'InitialPassword123!',
                'new_password': 'Short1!',
                'confirm_password': 'Short1!',
            },
            format='json',
        )
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert '12 characters' in str(res.json())

        # 2. Reject incorrect current password
        res = api_client.post(
            '/api/v1/auth/change-password/',
            {
                'current_password': 'WrongInitialPassword!',
                'new_password': 'BrandNewPassword1234!',
                'confirm_password': 'BrandNewPassword1234!',
            },
            format='json',
        )
        assert res.status_code == status.HTTP_400_BAD_REQUEST

        # 3. Successful password change
        res = api_client.post(
            '/api/v1/auth/change-password/',
            {
                'current_password': 'InitialPassword123!',
                'new_password': 'BrandNewPassword1234!',
                'confirm_password': 'BrandNewPassword1234!',
            },
            format='json',
        )
        assert res.status_code == status.HTTP_200_OK

        test_user.refresh_from_db()
        assert test_user.check_password('BrandNewPassword1234!')
        assert test_user.must_change_password is False

        # PasswordHistory record created
        assert PasswordHistory.objects.filter(user=test_user).count() == 1

        # 4. Reject reusing password in history
        res = api_client.post(
            '/api/v1/auth/change-password/',
            {
                'current_password': 'BrandNewPassword1234!',
                'new_password': 'BrandNewPassword1234!',
                'confirm_password': 'BrandNewPassword1234!',
            },
            format='json',
        )
        assert res.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestLoginThrottle:
    """SECURITY.md Sec 10: login capped at 5/min (isolated cache per test)."""

    def test_sixth_rapid_login_is_throttled(self, api_client):
        from django.core.cache import cache
        from apps.authentication.models import User
        cache.clear()
        user = User.objects.create_user(
            username='throttle_user', password='ThrottlePass123!',
            user_type=User.UserType.STUDENT, must_change_password=False)
        codes = []
        for _ in range(6):
            res = api_client.post('/api/v1/auth/login/', {
                'username': 'throttle_user', 'password': 'ThrottlePass123!'}, format='json')
            codes.append(res.status_code)
        assert codes[:5] == [status.HTTP_200_OK] * 5, codes
        assert codes[5] == 429, codes
