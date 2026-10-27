import axios, {
  AxiosError,
  InternalAxiosRequestConfig,
} from 'axios';
import { useAuthStore } from '@/stores/authStore';
import { useToastStore } from '@/stores/toastStore';
import type { LoginResponse, CurrentUserResponse } from '@/types/auth';
import type { ApiErrorResponse } from '@/types/api';
import type { AuthAttempt } from '@/stores/authStore';

/**
 * DC-12R1-MVP-L1-J1-H2-A-R1: opt-out channel for deliberately PUBLIC,
 * credential-bearing requests (invitation lookup / retailer register).
 *
 * A caller that sets `skipAuthInterceptors: true` and sends an explicitly
 * EMPTY Authorization header gets:
 *   - no store-token injection (empty header wins per the interceptor below);
 *   - NO error toasts (the global interceptor never echoes the backend
 *     message for these requests);
 *   - NO 401 token-refresh/logout hijack (an anonymous public call must not
 *     tear down or refresh the caller's unrelated session).
 * The page-level fixed neutral error copy remains the only failure surface.
 */
declare module 'axios' {
  export interface AxiosRequestConfig {
    skipAuthInterceptors?: boolean;
    /** Local caller ownership only; never serialized into the HTTP payload. */
    authAttempt?: AuthAttempt;
    requiresAuthAttempt?: boolean;
  }
}

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

type SessionRequest = InternalAxiosRequestConfig & {
  _retry?: boolean;
  _sessionGeneration?: number;
  _storeAuthorization?: boolean;
};
const superseded = () => new axios.CanceledError('SESSION_SUPERSEDED');
const ownsSession = (generation: number | undefined) => generation === useAuthStore.getState().sessionGeneration;
const ownsCaller = (request: SessionRequest) => request.authAttempt
  ? useAuthStore.getState().ownsAuthAttempt(request.authAttempt)
  : !request.requiresAuthAttempt;

// ---------------------------------------------------------------------------
// Request Interceptor — inject Bearer token
// ---------------------------------------------------------------------------
api.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const request = config as SessionRequest;
    if (!config.skipAuthInterceptors && !ownsCaller(request)) throw superseded();
    if (request._sessionGeneration === undefined) {
      request._sessionGeneration = useAuthStore.getState().sessionGeneration;
      request._storeAuthorization = !config.headers.has('Authorization');
    } else if (!config.skipAuthInterceptors && !ownsSession(request._sessionGeneration)) {
      throw superseded();
    }
    // PW1-R2-R2 (case-insensitive authorization precedence): a caller-provided
    // Authorization header ALWAYS wins, in ANY casing, including an explicitly
    // EMPTY value (the caller's deliberate fail-closed choice). Only when the
    // request carries no Authorization at all do we inject the Zustand store
    // access token. Presence is decided through the AxiosHeaders
    // case-insensitive API — never via `config.headers.Authorization` property
    // access, which misses lowercase/mixed-case headers.
    if (config.headers && !config.headers.has('Authorization')) {
      const { accessToken } = useAuthStore.getState();
      if (accessToken) {
        config.headers.set('Authorization', `Bearer ${accessToken}`);
      }
    }

    // Security: redact sensitive headers in dev-mode logging. Redaction is
    // CASE-INSENSITIVE: the header object is serialized via toJSON() and every
    // casing of the authorization key is replaced — never a spread that only
    // rewrites the canonical uppercase key.
    if (import.meta.env.DEV) {
      const rawHeaders = (config.headers?.toJSON?.() ?? {}) as Record<string, unknown>;
      const safeHeaders: Record<string, unknown> = {};
      for (const key of Object.keys(rawHeaders)) {
        safeHeaders[key] = /^authorization$/i.test(key) ? '[REDACTED]' : rawHeaders[key];
      }
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

type RefreshFlight = {
  generation: number;
  queue: Array<{ resolve: (token: string) => void; reject: (error: unknown) => void }>;
};
let refreshFlight: RefreshFlight | null = null;

function processQueue(flight: RefreshFlight, error: unknown, token: string | null) {
  const queue = flight.queue;
  flight.queue = [];
  queue.forEach(({ resolve, reject }) => {
    if (error) {
      reject(error);
    } else {
      resolve(token!);
    }
  });
}

// The store already uses browser events for context notifications. This
// signal carries no token and does not require a new public store interface.
if (typeof window !== 'undefined') {
  window.addEventListener('mpango-session-generation-changed', () => {
    if (refreshFlight && !ownsSession(refreshFlight.generation)) {
      const abandoned = refreshFlight;
      refreshFlight = null;
      processQueue(abandoned, superseded(), null);
    }
  });
}

api.interceptors.response.use(
  (response) => {
    const request = response.config as SessionRequest;
    if (!request.skipAuthInterceptors && (!ownsSession(request._sessionGeneration) || !ownsCaller(request))) throw superseded();
    return response;
  },
  async (error: AxiosError<ApiErrorResponse>) => {
    const originalRequest = error.config as SessionRequest | undefined;
    const status = error.response?.status;
    const detail = error.response?.data;
    const errorCode = detail && 'error' in detail ? detail.error.code : '';
    const errorMsg = detail && 'error' in detail ? detail.error.message : error.message;

    // DC-12R1-MVP-L1-J1-H2-A-R1: public credential-bearing requests opted
    // out via skipAuthInterceptors never reach the global toast echo nor the
    // 401 refresh/logout machinery — their only failure surface is the
    // page's fixed neutral copy.
    if (originalRequest?.skipAuthInterceptors) {
      return Promise.reject(error);
    }
    // Capture at send time, not when a late 401 finally arrives. No old
    // response may refresh, toast, revalidate authority, logout or redirect B.
    if (!originalRequest) return Promise.reject(error);
    if (!ownsSession(originalRequest._sessionGeneration) || !ownsCaller(originalRequest)) return Promise.reject(superseded());

    // -----------------------------------------------------------------------
    // Guardrail-aware error toasts (Track E3)
    // -----------------------------------------------------------------------
    if (status === 500 && (errorCode === 'TENANT_CONTEXT_MISSING' || errorMsg?.includes('tenant'))) {
      useToastStore.getState().addToast({
        type: 'error',
        title: 'Security Alert: Tenant Context Lost',
        message: 'Your session context was lost. Please refresh the page or log in again.',
      });
    } else if (status === 403) {
      void refreshCurrentAuthority();
      useToastStore.getState().addToast({
        type: 'warning',
        title: 'Access Denied',
        message: errorMsg || 'You do not have permission to perform this action.',
      });
    } else if (status === 409) {
      useToastStore.getState().addToast({
        type: 'warning',
        title: 'Action Not Allowed',
        message: errorMsg || 'This action conflicts with the current state.',
      });
    } else if (status && status >= 500) {
      useToastStore.getState().addToast({
        type: 'error',
        title: 'Server Error',
        message: errorMsg || 'An unexpected server error occurred. Please try again.',
      });
    }

    // Only handle 401 — and only once per request
    if (status !== 401 || originalRequest._retry) {
      return Promise.reject(error);
    }

    // Don't retry refresh or login endpoints (prevents infinite loop)
    const url = originalRequest.url || '';
    if (url.includes('/auth/refresh') || url.includes('/auth/login') || url.includes('/client/auth/login')) {
      return Promise.reject(error);
    }

    originalRequest._retry = true;
    const generation = originalRequest._sessionGeneration!;
    const currentToken = useAuthStore.getState().accessToken;
    if (originalRequest._storeAuthorization && currentToken
        && originalRequest.headers.get('Authorization') !== `Bearer ${currentToken}`) {
      originalRequest.headers.set('Authorization', `Bearer ${currentToken}`);
      return api(originalRequest);
    }

    // Queue only within the owning generation; retry ownership is retained.
    if (refreshFlight?.generation === generation) {
      const flight = refreshFlight;
      return new Promise<string>((resolve, reject) => {
        flight.queue.push({ resolve, reject });
      }).then((newToken) => {
        if (!ownsSession(generation)) throw superseded();
        if (originalRequest._storeAuthorization) originalRequest.headers.set('Authorization', `Bearer ${newToken}`);
        return api(originalRequest);
      });
    }

    const flight: RefreshFlight = { generation, queue: [] };
    refreshFlight = flight;

    const { refreshToken, logout, updateTokens } = useAuthStore.getState();

    if (!refreshToken) {
      if (refreshFlight === flight) refreshFlight = null;
      // DC-12R1-S2: redirect retailer sessions back to their supplier portal.
      const { retailerPortalCode } = useAuthStore.getState();
      logout();
      if (retailerPortalCode) {
        window.location.href = `/retail/login?w=${retailerPortalCode}`;
      } else {
        window.location.href = '/login';
      }
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

      if (!ownsSession(generation)) throw superseded();

      // Update store with new tokens
      updateTokens({
        access_token: newAccessToken,
        refresh_token: data.data.refresh_token,
      });

      // Process queued requests with new token
      processQueue(flight, null, newAccessToken);

      // Retry original request
      if (originalRequest._storeAuthorization) originalRequest.headers.set('Authorization', `Bearer ${newAccessToken}`);
      return api(originalRequest);
    } catch (refreshError) {
      if (!ownsSession(generation)) {
        processQueue(flight, superseded(), null);
        return Promise.reject(superseded());
      }
      // Refresh failed — clear everything, redirect to login
      processQueue(flight, refreshError, null);
      // DC-12R1-S2: redirect retailer sessions back to their supplier portal.
      const { retailerPortalCode } = useAuthStore.getState();
      logout();
      if (retailerPortalCode) {
        window.location.href = `/retail/login?w=${retailerPortalCode}`;
      } else {
        window.location.href = '/login';
      }
      return Promise.reject(refreshError);
    } finally {
      if (refreshFlight === flight) refreshFlight = null;
    }
  }
);

export { api };

let authorityRefresh: { key: string; promise: Promise<void> } | null = null;
export function refreshCurrentAuthority(): Promise<void> {
  const { accessToken, user, sessionGeneration } = useAuthStore.getState();
  if (!accessToken || !user?.tenant_id) return Promise.resolve();
  const tenant = user.tenant_id;
  const key = sessionGeneration + ':' + tenant + ':' + accessToken;
  if (authorityRefresh?.key === key) return authorityRefresh.promise;
  const promise = api.get<CurrentUserResponse>('/auth/me', {
    headers: { Authorization: `Bearer ${accessToken}` },
    skipAuthInterceptors: true,
  }).then(({ data }) => {
    const current = useAuthStore.getState();
    if (current.sessionGeneration !== sessionGeneration || current.accessToken !== accessToken || current.user?.tenant_id !== tenant) return;
    const fresh = data.data;
    if (fresh?.id !== current.user.id || fresh.tenant_id !== tenant
        || fresh.tenant_schema !== current.user.tenant_schema
        || !Array.isArray(fresh.permissions) || !fresh.permissions.every(code => typeof code === 'string')
        || !Array.isArray(fresh.roles) || !fresh.roles.every(role => typeof role === 'string')) {
      throw new Error('AUTHORITY_RESPONSE_MISMATCH');
    }
    current.setUser(fresh);
  }).catch((error: AxiosError) => {
    const current = useAuthStore.getState();
    if (current.sessionGeneration !== sessionGeneration) return;
    if (error.response?.status === 401 && current.accessToken === accessToken) current.logout();
    else if (current.accessToken === accessToken && current.user?.tenant_id === tenant) {
      current.setUser({ ...current.user, is_owner: false, permissions: [], authz_revision: null });
    }
  }).finally(() => { if (authorityRefresh?.key === key) authorityRefresh = null; });
  authorityRefresh = { key, promise };
  return promise;
}

if (typeof window !== 'undefined') {
  window.addEventListener('focus', () => { void refreshCurrentAuthority(); });
  window.addEventListener('mpango-authority-context-changed', () => { void refreshCurrentAuthority(); });
}
