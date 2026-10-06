/**
 * Axios API client with JWT authentication interceptor.
 *
 * - Injects access token from memory into every request
 * - Automatically refreshes expired access tokens using HttpOnly refresh cookie
 * - Queues failed requests during token refresh to prevent race conditions
 * - Redirects to login on authentication failure
 */
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const apiClient = axios.create({
  baseURL: `${API_BASE_URL}/api/v1`,
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true, // Required for HttpOnly refresh cookie
});

// In-memory access token storage (never in localStorage for security)
let accessToken = null;
let isRefreshing = false;
let failedQueue = [];

/**
 * Set the access token in memory.
 * Called after login and after token refresh.
 */
export function setAccessToken(token) {
  accessToken = token;
}

/**
 * Get the current access token.
 */
export function getAccessToken() {
  return accessToken;
}

/**
 * Clear the access token (on logout).
 */
export function clearAccessToken() {
  accessToken = null;
}

/**
 * Process the queue of failed requests after token refresh.
 */
function processQueue(error, token = null) {
  failedQueue.forEach(({ resolve, reject }) => {
    if (error) {
      reject(error);
    } else {
      resolve(token);
    }
  });
  failedQueue = [];
}

// Request interceptor: inject access token
apiClient.interceptors.request.use(
  (config) => {
    if (accessToken) {
      config.headers.Authorization = `Bearer ${accessToken}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor: handle 401 with token refresh
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // Do NOT attempt refresh on auth endpoints (login, refresh) or if already retried
    const isAuthUrl = originalRequest?.url?.includes('/auth/login') || originalRequest?.url?.includes('/auth/refresh');

    if (error.response?.status === 401 && !originalRequest?._retry && !isAuthUrl) {
      if (isRefreshing) {
        // Queue this request while refresh is in progress
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        }).then((token) => {
          originalRequest.headers.Authorization = `Bearer ${token}`;
          return apiClient(originalRequest);
        });
      }

      originalRequest._retry = true;
      isRefreshing = true;

      try {
        const response = await axios.post(
          `${API_BASE_URL}/api/v1/auth/refresh/`,
          {},
          { withCredentials: true }
        );

        const newToken = response.data.access;
        setAccessToken(newToken);
        processQueue(null, newToken);

        originalRequest.headers.Authorization = `Bearer ${newToken}`;
        return apiClient(originalRequest);
      } catch (refreshError) {
        processQueue(refreshError, null);
        clearAccessToken();
        // Redirect to login only if not already there
        if (window.location.pathname !== '/login') {
          window.location.href = '/login';
        }
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);

export default apiClient;
