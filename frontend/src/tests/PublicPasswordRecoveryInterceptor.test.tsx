/**
 * DC-12R1-MVP-L1-J1-H2-B-R3 — Public password-recovery interceptor closure.
 *
 * Runs against the REAL api.ts interceptors (request + response, including
 * the refresh/queue/logout machinery) via a recording axios adapter on the
 * shared instance, and the REAL rendered pages. authService is NOT mocked.
 *
 * Truth coverage (task contract):
 *   T1  wholesaler forged/expired reset token -> 401 stays on /reset-password,
 *       fixed neutral error panel, zero refresh, zero logout, zero global
 *       toast, zero navigation, stale session untouched.
 *   T2  wholesaler 200 success path -> success panel (unchanged behavior).
 *   T3  retailer 401 stays on /retailer/reset-password with the same neutral
 *       copy.
 *   T4  under a stale contextual session all four public recovery calls send
 *       an EXPLICIT empty Authorization header and reject 401 raw (no
 *       refresh/logout/state rewrite).
 *   T5  a normal protected request's 401 still takes the legacy
 *       refresh/queue/logout contract (no regression from the caller-side
 *       opt-out).
 *   T6  no token/password/Authorization material leaks into request URLs,
 *       adapter logs, or the rendered error surface.
 *
 * Mutation gates M1–M5 (separate scripted runs against this file): removing
 * skipAuthInterceptors, removing the empty Authorization header, re-entering
 * the global 401 path, or weakening the stay-on-page/neutrality assertions
 * must turn the corresponding tests RED.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';

import { api } from '@/services/api';
import { authService } from '@/services/authService';
import { useAuthStore } from '@/stores/authStore';
import { useToastStore } from '@/stores/toastStore';
import { ResetPasswordPage } from '@/pages/auth/ResetPasswordPage';
import { RetailerResetPasswordPage } from '@/pages/retailer/RetailerResetPasswordPage';

// ---------------------------------------------------------------------------
// Recording adapter on the REAL api instance — the real interceptors run.
// ---------------------------------------------------------------------------

type Handler = (config: InternalAxiosRequestConfig) => AxiosResponse | Promise<AxiosResponse>;

interface Recorded {
  key: string;
  url: string;
  authorization: unknown;
  config: InternalAxiosRequestConfig;
}

function ok<T>(config: InternalAxiosRequestConfig, data: T): AxiosResponse<T> {
  return { data, status: 200, statusText: 'OK', headers: {}, config };
}

function httpError(config: InternalAxiosRequestConfig, status: number, body: unknown) {
  return Object.assign(new Error(`Request failed with status code ${status}`), {
    isAxiosError: true,
    config,
    response: { status, statusText: 'Error', headers: {}, data: body, config },
  });
}

// MUST throw (an arrow returning the error object would make the adapter
// RESOLVE with it — the 401 would silently become a success response).
const neutral401 = (config: InternalAxiosRequestConfig) => {
  throw httpError(config, 401, { error: { code: 'TOKEN_INVALID', message: 'reset link invalid or expired' } });
};

function installAdapter(handlers: Record<string, Handler>) {
  const log: string[] = [];
  const recorded: Recorded[] = [];
  const adapter: AxiosAdapter = async (config) => {
    const key = `${(config.method ?? 'get').toUpperCase()} ${config.url ?? ''}`;
    log.push(key);
    recorded.push({
      key,
      url: config.url ?? '',
      authorization: config.headers?.get?.('Authorization') ?? null,
      config,
    });
    const handler = handlers[key];
    if (handler) return await handler(config);
    throw httpError(config, 404, { error: { code: 'NOT_FOUND', message: 'no adapter route' } });
  };
  api.defaults.adapter = adapter;
  axios.defaults.adapter = adapter;
  return { log, recorded };
}

// ---------------------------------------------------------------------------
// Fixtures / harness
// ---------------------------------------------------------------------------

const STALE = {
  accessToken: 'stale-access-token-material',
  refreshToken: 'stale-refresh-token-material',
};

const STALE_USER = {
  id: 'user-1',
  email: 'stale@example.com',
  full_name: 'Stale Owner',
  roles: ['admin'],
} as unknown as ReturnType<typeof useAuthStore.getState>['user'];

function seedStaleSession() {
  useAuthStore.setState({
    accessToken: STALE.accessToken,
    refreshToken: STALE.refreshToken,
    user: STALE_USER,
    tenantCode: 'TENANT1',
    retailerPortalCode: null,
  });
}

function snapshotSession() {
  const s = useAuthStore.getState();
  return {
    accessToken: s.accessToken,
    refreshToken: s.refreshToken,
    user: s.user,
    tenantCode: s.tenantCode,
  };
}

function renderAt(path: string, element: React.ReactElement) {
  window.history.pushState({}, '', path);
  return render(<BrowserRouter>{element}</BrowserRouter>);
}

async function fillAndSubmitReset(password: string) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText(/new password/i), password);
  await user.click(screen.getByRole('button', { name: /reset password/i }));
}

const NEUTRAL_ERROR = 'This reset link is invalid or expired. Please request a new link.';

function installConsoleErrorSpy() {
  return vi.spyOn(console, 'error').mockImplementation(() => {});
}

let consoleErrorSpy: ReturnType<typeof installConsoleErrorSpy>;

beforeEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
  useAuthStore.setState({
    accessToken: null,
    refreshToken: null,
    user: null,
    tenantCode: null,
    retailerPortalCode: null,
  });
  useToastStore.setState({ toasts: [] });
  // jsdom reports hard navigations (window.location.href assignments in the
  // interceptor's logout path) through console.error — spying here lets the
  // tests assert ZERO navigation attempts.
  consoleErrorSpy = installConsoleErrorSpy();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// T1 — wholesaler forged reset token: raw 401 stays on the page
// ---------------------------------------------------------------------------

describe('H2-B-R3 T1: wholesaler reset 401 stays neutral on /reset-password', () => {
  it('renders the fixed neutral error, no refresh/logout/toast/navigation, session untouched', async () => {
    seedStaleSession();
    const before = snapshotSession();
    const { log } = installAdapter({
      'POST /auth/reset-password': neutral401,
    });

    renderAt('/reset-password#resetToken=forged-reset-token-xyz', <ResetPasswordPage />);
    await waitFor(() => expect(window.location.hash).toBe(''));
    await fillAndSubmitReset('NewStrongPass123');

    expect(await screen.findByText(NEUTRAL_ERROR)).toBeInTheDocument();
    await waitFor(() => expect(window.location.pathname).toBe('/reset-password'));

    expect(log).toContain('POST /auth/reset-password');
    expect(log.filter((k) => k === 'POST /auth/refresh')).toEqual([]);
    expect(log.filter((k) => k === 'POST /auth/logout')).toEqual([]);
    expect(useToastStore.getState().toasts).toEqual([]);
    expect(snapshotSession()).toEqual(before);
    const navigationAttempts = consoleErrorSpy.mock.calls
      .map((args) => args.join(' '))
      .filter((text) => text.includes('Not implemented: navigation'));
    expect(navigationAttempts).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// T2 — wholesaler success path unchanged
// ---------------------------------------------------------------------------

describe('H2-B-R3 T2: wholesaler reset 200 success panel unchanged', () => {
  it('shows the success panel and the Go to login link', async () => {
    const { log } = installAdapter({
      'POST /auth/reset-password': (c) => ok(c, { success: true, data: {}, message: 'neutral', timestamp: '2026-08-25T00:00:00Z' }),
    });

    renderAt('/reset-password#resetToken=valid-reset-token', <ResetPasswordPage />);
    await waitFor(() => expect(window.location.hash).toBe(''));
    await fillAndSubmitReset('NewStrongPass123');

    expect(await screen.findByText('Your password has been reset successfully.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /go to login/i })).toHaveAttribute('href', '/login');
    expect(log.filter((k) => k === 'POST /auth/reset-password')).toHaveLength(1);
  });
});

// ---------------------------------------------------------------------------
// T3 — retailer reset 401 stays on /retailer/reset-password
// ---------------------------------------------------------------------------

describe('H2-B-R3 T3: retailer reset 401 stays neutral on /retailer/reset-password', () => {
  it('renders the fixed neutral error, no refresh/logout/toast/navigation', async () => {
    seedStaleSession();
    const before = snapshotSession();
    const { log } = installAdapter({
      'POST /client/auth/reset-password': neutral401,
    });

    renderAt('/retailer/reset-password#resetToken=forged-retailer-token', <RetailerResetPasswordPage />);
    await waitFor(() => expect(window.location.hash).toBe(''));
    await fillAndSubmitReset('NewStrongPass123');

    expect(await screen.findByText(NEUTRAL_ERROR)).toBeInTheDocument();
    await waitFor(() => expect(window.location.pathname).toBe('/retailer/reset-password'));

    expect(log).toContain('POST /client/auth/reset-password');
    expect(log.filter((k) => k === 'POST /auth/refresh')).toEqual([]);
    expect(log.filter((k) => k === 'POST /auth/logout')).toEqual([]);
    expect(useToastStore.getState().toasts).toEqual([]);
    expect(snapshotSession()).toEqual(before);
    const navigationAttempts = consoleErrorSpy.mock.calls
      .map((args) => args.join(' '))
      .filter((text) => text.includes('Not implemented: navigation'));
    expect(navigationAttempts).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// T4 — all four public recovery calls carry an explicit empty Authorization
// ---------------------------------------------------------------------------

describe('H2-B-R3 T4: four public recovery calls send explicit empty Authorization under a stale session', () => {
  it('forgotPassword/resetPassword/retailerForgotPassword/retailerResetPassword all send Authorization === "" and reject 401 raw', async () => {
    seedStaleSession();
    const before = snapshotSession();
    const { log, recorded } = installAdapter({
      'POST /auth/forgot-password': neutral401,
      'POST /auth/reset-password': neutral401,
      'POST /client/auth/forgot-password': neutral401,
      'POST /client/auth/reset-password': neutral401,
    });

    const cases = [
      () => authService.forgotPassword({ email: 'person@example.com' }),
      () => authService.resetPassword({ resetToken: 'forged-reset-token-xyz', newPassword: 'NewStrongPass123' }), // pragma: allowlist secret
      () => authService.retailerForgotPassword({ email: 'retailer@example.com', wholesalerCode: 'WS1' }),
      () => authService.retailerResetPassword({ resetToken: 'forged-retailer-token', newPassword: 'NewStrongPass123' }), // pragma: allowlist secret
    ];
    for (const call of cases) {
      await expect(call()).rejects.toMatchObject({ response: { status: 401 } });
    }

    const publicKeys = [
      'POST /auth/forgot-password',
      'POST /auth/reset-password',
      'POST /client/auth/forgot-password',
      'POST /client/auth/reset-password',
    ];
    for (const key of publicKeys) {
      const hit = recorded.find((r) => r.key === key);
      expect(hit, `missing request ${key}`).toBeDefined();
      // Explicit empty string — the PW1-R2-R2 precedence guarantee that NO
      // stale store token is injected.
      expect(hit?.authorization).toBe('');
    }
    expect(log.filter((k) => k === 'POST /auth/refresh')).toEqual([]);
    expect(log.filter((k) => k === 'POST /auth/logout')).toEqual([]);
    expect(snapshotSession()).toEqual(before);
  });
});

// ---------------------------------------------------------------------------
// T5 — non-public requests keep the legacy 401 refresh contract
// ---------------------------------------------------------------------------

describe('H2-B-R3 T5: protected request 401 still refreshes (legacy contract intact)', () => {
  it('fires POST /auth/refresh and retries with the new token', async () => {
    seedStaleSession();
    let dashboardCalls = 0;
    const { log, recorded } = installAdapter({
      'GET /dashboards/summary': (c) => {
        dashboardCalls += 1;
        if (dashboardCalls === 1) {
          return neutral401(c);
        }
        return ok(c, { success: true, data: { revenue: 1 }, message: 'ok', timestamp: '2026-08-25T00:00:00Z' });
      },
      // The interceptor's refresh call uses the GLOBAL axios with the full
      // baseURL prefix in the URL (recursion-avoidance), so the adapter sees
      // '/api/v1/auth/refresh' — not the api-instance-relative path.
      'POST /api/v1/auth/refresh': (c) =>
        ok(c, {
          success: true,
          data: { access_token: 'fresh-access-token', refresh_token: 'fresh-refresh-token' },
          message: 'ok',
          timestamp: '2026-08-25T00:00:00Z',
        }),
    });

    await api.get('/dashboards/summary');

    expect(log.filter((k) => k === 'POST /api/v1/auth/refresh')).toHaveLength(1);
    expect(log.filter((k) => k === 'GET /dashboards/summary')).toHaveLength(2);
    const retry = recorded.filter((r) => r.key === 'GET /dashboards/summary')[1];
    expect(retry?.authorization).toBe('Bearer fresh-access-token');
    expect(useAuthStore.getState().accessToken).toBe('fresh-access-token');
  });
});

// ---------------------------------------------------------------------------
// T6 — no secret material in URLs, logs, or the rendered error surface
// ---------------------------------------------------------------------------

describe('H2-B-R3 T6: no token/password/Authorization leakage', () => {
  it('keeps request URLs and rendered DOM free of token and password material', async () => {
    seedStaleSession();
    const secretToken = 'forged-reset-token-leakprobe'; // pragma: allowlist secret
    const secretPassword = 'LeakProbePass123'; // pragma: allowlist secret
    const { log, recorded } = installAdapter({
      'POST /auth/reset-password': neutral401,
    });

    renderAt(`/reset-password#resetToken=${secretToken}`, <ResetPasswordPage />);
    await waitFor(() => expect(window.location.hash).toBe(''));
    await fillAndSubmitReset(secretPassword);

    expect(await screen.findByText(NEUTRAL_ERROR)).toBeInTheDocument();

    for (const r of recorded) {
      expect(r.url).not.toContain(secretToken);
      expect(r.url).not.toContain('resetToken');
      expect(r.url).not.toContain('newPassword');
    }
    expect(log.join('\n')).not.toContain(secretToken);
    expect(log.join('\n')).not.toContain(secretPassword);
    expect(document.body.textContent ?? '').not.toContain(secretToken);
    expect(document.body.textContent ?? '').not.toContain(secretPassword);
  });
});
