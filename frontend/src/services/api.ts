import axios, {
  AxiosError,
  InternalAxiosRequestConfig,
} from 'axios';
import { useAuthStore } from '@/stores/authStore';
import type { LoginResponse } from '@/types/auth';

/**
 * Singleton Axios instance for all API calls.
 * Mirrors frontend_contract.md §3.1 — unified API client.
 *
 * Features:
 *   - Request interceptor: injects Bearer token from Zustand store
 *   - Response interceptor: atomic token refresh with request queueing
 *   - Avoids circular deps by using useAuthStore.getState() (not hooks)
 */
const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api/v1',
  timeout: 15_000,
  headers: { 'Content-Type': 'application/json' },
});

// ---------------------------------------------------------------------------
// Request Interceptor — inject Bearer token
// ---------------------------------------------------------------------------
api.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const { accessToken } = useAuthStore.getState();
    if (accessToken && config.headers) {
      config.headers.Authorization = `Bearer ${accessToken}`;
    }

    // Security: redact sensitive headers in dev-mode logging
    if (import.meta.env.DEV) {
      const safeHeaders = { ...config.headers } as Record<string, unknown>;
      if (safeHeaders.Authorization) safeHeaders.Authorization = '[REDACTED]';
      console.debug('[API →]', config.method?.toUpperCase(), config.url, {
        headers: safeHeaders,
      });
    }

    return config;
  },
  (error) => Promise.reject(error)
);

// ---------------------------------------------------------------------------
// Response Interceptor — atomic token refresh with queue
// ---------------------------------------------------------------------------

let isRefreshing = false;
let failedQueue: Array<{
  resolve: (token: string) => void;
  reject: (error: unknown) => void;
}> = [];

function processQueue(error: unknown, token: string | null) {
  failedQueue.forEach(({ resolve, reject }) => {
    if (error) {
      reject(error);
    } else {
      resolve(token!);
    }
  });
  failedQueue = [];
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & {
      _retry?: boolean;
    };

    // Only handle 401 — and only once per request
    if (error.response?.status !== 401 || originalRequest._retry) {
      return Promise.reject(error);
    }

    // Don't retry refresh or login endpoints (prevents infinite loop)
    const url = originalRequest.url || '';
    if (url.includes('/auth/refresh') || url.includes('/auth/login')) {
      return Promise.reject(error);
    }

    // If already refreshing, queue this request
    if (isRefreshing) {
      return new Promise<string>((resolve, reject) => {
        failedQueue.push({ resolve, reject });
      }).then((newToken) => {
        originalRequest.headers.Authorization = `Bearer ${newToken}`;
        return api(originalRequest);
      });
    }

    // Mark as refreshing + retrying
    originalRequest._retry = true;
    isRefreshing = true;

    const { refreshToken, logout, updateTokens } = useAuthStore.getState();

    if (!refreshToken) {
      isRefreshing = false;
      logout();
      window.location.href = '/login';
      return Promise.reject(error);
    }

    try {
      // Call refresh endpoint directly (bypass interceptor to avoid recursion)
      const { data } = await axios.post<LoginResponse>(
        `${api.defaults.baseURL}/auth/refresh`,
        { refresh_token: refreshToken },
        { headers: { 'Content-Type': 'application/json' } }
      );

      const newAccessToken = data.data.access_token;

      // Update store with new tokens
      updateTokens({
        access_token: newAccessToken,
        refresh_token: data.data.refresh_token,
      });

      // Process queued requests with new token
      processQueue(null, newAccessToken);

      // Retry original request
      originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
      return api(originalRequest);
    } catch (refreshError) {
      // Refresh failed — clear everything, redirect to login
      processQueue(refreshError, null);
      logout();
      window.location.href = '/login';
      return Promise.reject(refreshError);
    } finally {
      isRefreshing = false;
    }
  }
);

export { api };
