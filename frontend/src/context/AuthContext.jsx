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
    try {
      setError(null);
      const response = await apiClient.post('/auth/login/', {
        username,
        password,
      });

      setAccessToken(response.data.access);

      const meResponse = await apiClient.get('/auth/me/');
      setUser(meResponse.data);

      return { success: true, must_change_password: response.data.must_change_password };
    } catch (err) {
      const message =
        err.response?.data?.detail ||
        err.response?.data?.error ||
        'Login failed. Please check your credentials.';
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
    try {
      setError(null);
      const response = await apiClient.post('/auth/change-password/', {
        current_password: currentPassword,
        new_password: newPassword,
        confirm_password: confirmPassword,
      });

      // Refresh user profile so must_change_password is updated
      const meResponse = await apiClient.get('/auth/me/');
      setUser(meResponse.data);

      return { success: true, message: response.data.detail };
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
