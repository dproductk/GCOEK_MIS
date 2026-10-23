/**
 * Authentication Context.
 *
 * Provides user state, login/logout actions, and role information
 * to all components via React Context.
 *
 * IMPORTANT: Frontend auth checks are for UX only (showing/hiding
 * routes and UI elements). Backend RBAC + scope is the security boundary.
 */
import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import apiClient, { setAccessToken, clearAccessToken } from '../api/client';

const AuthContext = createContext(null);

/**
 * Number of attempts used when re-fetching the user profile (/auth/me/)
 * right after the backend has already issued valid tokens. Transient
 * failures (network blip, 5xx, throttle) are absorbed here instead of
 * being misreported as credential errors.
 */
const PROFILE_FETCH_ATTEMPTS = 3;

/**
 * Fetch the authenticated user's profile with bounded retries.
 *
 * ONLY call this once valid tokens exist (post-login / post-password-change).
 * A failure at this stage is a connection/server issue — never a credential
 * issue — so callers must not surface it as "wrong credentials".
 *
 * A 401 response automatically triggers the refresh interceptor in
 * api/client.js; the backoff delay below gives that (and transient 5xx)
 * time to settle before the next attempt. Throws the last error after
 * all attempts are exhausted.
 */
async function fetchProfileWithRetry() {
  let lastError;
  for (let attempt = 1; attempt <= PROFILE_FETCH_ATTEMPTS; attempt++) {
    try {
      const meResponse = await apiClient.get('/auth/me/');
      return meResponse.data;
    } catch (err) {
      lastError = err;
      // Skip the delay after the final attempt — nothing left to retry.
      if (attempt < PROFILE_FETCH_ATTEMPTS) {
        await new Promise((resolve) => setTimeout(resolve, 750 * attempt));
      }
    }
  }
  throw lastError;
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  /**
   * Attempt to restore the session from the refresh token cookie.
   * Called on initial mount — if a valid refresh cookie exists,
   * the backend returns a new access token.
   */
  const restoreSession = useCallback(async () => {
    try {
      setLoading(true);
      const refreshResponse = await apiClient.post('/auth/refresh/', {});
      setAccessToken(refreshResponse.data.access);

      const meResponse = await apiClient.get('/auth/me/');
      setUser(meResponse.data);
      setError(null);
    } catch {
      // No valid session — user needs to log in
      clearAccessToken();
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    restoreSession();
  }, [restoreSession]);

  /**
   * Log in with username and password.
   * On success, stores access token in memory and refresh token
   * is set as HttpOnly cookie by the backend.
   */
  const login = async (username, password) => {
    // Phase 1 — credential verification. ONLY a failure here means the
    // credentials are wrong (or the account is locked/throttled), so only
    // this catch block may report "please check your credentials".
    let response;
    try {
      setError(null);
      response = await apiClient.post('/auth/login/', {
        username,
        password,
      });
    } catch (err) {
      const data = err.response?.data;
      // DRF wraps serializer-level errors (e.g. account lockout) under
      // non_field_errors; view-level errors arrive as detail/error.
      const nonFieldMessage = Array.isArray(data?.non_field_errors)
        ? data.non_field_errors[0]
        : data?.non_field_errors;
      const message =
        data?.detail ||
        data?.error ||
        nonFieldMessage ||
        (err.response
          ? 'Login failed. Please check your credentials.'
          : // No response at all = network failure; credentials were never verified.
            'Could not reach the server. Please check your connection and try again.');
      setError(message);
      return { success: false, error: message };
    }

    // Phase 2 — the backend has issued valid tokens (access token in memory,
    // refresh cookie set). Any failure from here on is a connection or
    // server problem, never a credential problem.
    setAccessToken(response.data.access);

    try {
      const profile = await fetchProfileWithRetry();
      setUser(profile);
      return { success: true, must_change_password: response.data.must_change_password };
    } catch {
      // Profile could not be loaded even after retries. Keep the issued
      // tokens — they are valid, so a page reload restores the session via
      // restoreSession() (refresh cookie) without asking for credentials
      // again. Never report this as "wrong credentials".
      const message =
        'You have been signed in successfully, but your profile could not be loaded due to a network issue. Please wait a few seconds and reload this page.';
      setError(message);
      return { success: false, error: message };
    }
  };

  /**
   * Log out — clear tokens and user state.
   */
  const logout = async () => {
    try {
      await apiClient.post('/auth/logout/');
    } catch {
      // Logout API may fail if token already expired — clear locally anyway
    } finally {
      clearAccessToken();
      setUser(null);
      setError(null);
    }
  };

  /**
   * Change user password.
   */
  const changePassword = async (currentPassword, newPassword, confirmPassword) => {
    // Phase 1 — the password change itself. Failures here are real
    // change failures (wrong current password, weak password, etc.).
    let response;
    try {
      setError(null);
      response = await apiClient.post('/auth/change-password/', {
        current_password: currentPassword,
        new_password: newPassword,
        confirm_password: confirmPassword,
      });
    } catch (err) {
      const data = err.response?.data;
      let message = 'Failed to change password.';
      if (data?.detail) {
        message = data.detail;
      } else if (typeof data === 'object') {
        message = Object.values(data).flat().join(' ');
      }
      setError(message);
      return { success: false, error: message };
    }

    // Phase 2 — the password HAS been changed at this point. Refreshing the
    // profile only updates must_change_password in client state, so a
    // transient failure here must NOT be reported as a failed change.
    try {
      const profile = await fetchProfileWithRetry();
      setUser(profile);
      return { success: true, message: response.data.detail };
    } catch {
      // Keep the valid tokens and report success. The backend already
      // accepted the change, so clear the cached must_change_password flag
      // (prevents the /change-password gate from bouncing the user back
      // with stale state). Server truth is re-synced on the next
      // successful /auth/me/ fetch.
      setUser((prev) => (prev ? { ...prev, must_change_password: false } : prev));
      return { success: true, message: response.data.detail, profile_stale: true };
    }
  };

  /**
   * Check if the current user has a specific role.
   * This is for UX purposes only — NOT a security check.
   */
  const hasRole = (roleCodename) => {
    if (!user?.roles) return false;
    return user.roles.some(
      (r) => r.codename === roleCodename && r.status === 'ACTIVE'
    );
  };

  /**
   * Get the user's primary/active role for display purposes.
   * Priority order: HOD / elevated roles win over base FACULTY role,
   * since HOD and CLASS_TEACHER users also hold a FACULTY assignment
   * (see backend seed_faculty.py) and /auth/me/ orders by -assigned_at
   * which would otherwise return FACULTY first.
   */
  const ROLE_PRIORITY = [
    'SYSADMIN',
    'ADMIN_HEAD',
    'HOD',
    'CLASS_TEACHER',
    'ACCOUNTANT',
    'FACULTY',
    'EMPLOYEE',
    'STUDENT',
  ];

  const activeRole = (() => {
    const activeRoles = (user?.roles || []).filter((r) => r.status === 'ACTIVE');
    if (activeRoles.length === 0) return null;
    const rank = (codename) => {
      const idx = ROLE_PRIORITY.indexOf(codename);
      return idx === -1 ? ROLE_PRIORITY.length : idx;
    };
    activeRoles.sort((a, b) => rank(a.codename) - rank(b.codename));
    return activeRoles[0] ?? null;
  })();

  const value = {
    user,
    loading,
    error,
    login,
    logout,
    changePassword,
    hasRole,
    activeRole,
    isAuthenticated: !!user,
    restoreSession,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/**
 * Hook to access the auth context.
 */
export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

export default AuthContext;
