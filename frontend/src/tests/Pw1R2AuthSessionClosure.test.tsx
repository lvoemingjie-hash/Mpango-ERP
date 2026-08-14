/**
 * PW1-R2 — Auth session state closure (D1 + D2) mandatory tests.
 *
 * Runs against the REAL <App /> router tree (createBrowserRouter, real
 * guards, real pages). The HTTP layer is served by a recording axios adapter
 * that returns real-shaped responses; every request is logged so ordering
 * and absence assertions are evidence-grade.
 *
 * Mandatory coverage map:
 *   M1  multi-tenant login 200 -> selector renders (real AppRouter)
 *   M2  no dashboard API request before the selector renders
 *   M3  selection: select-tenant 200 then me 200, then workspace entry
 *   M4  retailer_operator -> /client; owner -> /
 *   M5  single-tenant owner + super_admin flows do not regress
 *       (retailer portal regression covered by Dc12r1S2RetailerPortal.test.tsx)
 *   M6  pending identity session on protected route fails closed
 *   M7  pending identity session is NOT bounced off /login by PublicRoute
 *   M8  selector refresh losing navigation state -> /login, never the shell
 *   M9  select-tenant/me failure -> no contextual session, no business API
 *   M10 flat 401 / legacy envelope / malicious message -> fixed neutral copy
 *   M11 exactly ONE POST /auth/login per form submit
 *   M12/M13 (mutation RED) are executed as scripted mutations against this
 *       suite and captured in the task evidence, not as runtime switches.
 */
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios';
import { render, screen, waitFor, cleanup, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { App } from '@/App';
import { api } from '@/services/api';
import { useAuthStore, sessionKind } from '@/stores/authStore';
import { PublicRoute, ProtectedRoute, WholesalerRoute } from '@/router/guards';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Adapter scaffolding (records every request; real-shaped responses)
// ---------------------------------------------------------------------------
type Handler = (config: InternalAxiosRequestConfig) => AxiosResponse | Promise<AxiosResponse>;

function ok<T>(config: InternalAxiosRequestConfig, data: T): AxiosResponse<T> {
  return { data, status: 200, statusText: 'OK', headers: {}, config };
}

function apiResponse<T>(data: T) {
  return { success: true, data, timestamp: '2026-08-14T00:00:00.000Z' };
}

function httpError(config: InternalAxiosRequestConfig, status: number, body: unknown) {
  return Object.assign(new Error(`Request failed with status code ${status}`), {
    isAxiosError: true,
    config,
    response: { status, statusText: 'Error', headers: {}, data: body, config },
  });
}

const BUSINESS_API = /GET \/(dashboards|orders|inventory|skus|finance|payments|retailers|client)/;

function installAdapter(handlers: Record<string, Handler>) {
  const log: string[] = [];
  const adapter: AxiosAdapter = async (config) => {
    const key = `${(config.method ?? 'get').toUpperCase()} ${config.url ?? ''}`;
    log.push(key);
    const handler = handlers[key];
    if (handler) return await handler(config);
    // Unmatched endpoints fail with 404 (logged) — absence assertions rely on
    // the log, and pages treat this as an error state instead of hanging.
    throw httpError(config, 404, { code: 'NOT_FOUND', message: 'no adapter route' });
  };
  api.defaults.adapter = adapter;
  return log;
}

// Shared response fixtures ---------------------------------------------------
const TENANTS = [
  { id: '11111111-1111-1111-1111-111111111111', code: 'TENANT1', name: 'Alpha Wholesale' },
  { id: '22222222-2222-2222-2222-222222222222', code: 'TENANT2', name: 'Beta Wholesale' },
];

function identityLoginBody(roles: string[], tenants = TENANTS) {
  return {
    success: true,
    data: {
      access_token: 'identity-access-token',
      refresh_token: 'identity-refresh-token',
      token_type: 'bearer',
      user_id: '00000000-0000-0000-0000-000000000001',
      roles,
      available_tenants: tenants,
    },
    timestamp: '2026-08-14T00:00:00.000Z',
  };
}

function contextualBody(roles: string[], tenant: { id: string }) {
  return apiResponse({
    access_token: 'contextual-access-token',
    refresh_token: 'contextual-refresh-token',
    token_type: 'bearer',
    user_id: '00000000-0000-0000-0000-000000000001',
    tenant_id: tenant.id,
    tenant_schema: 't_test',
    roles,
  });
}

function meBody(roles: string[], tenantId: string | null) {
  return apiResponse({
    id: '00000000-0000-0000-0000-000000000001',
    email: 'owner@example.com',
    full_name: 'Owner',
    tenant_id: tenantId,
    tenant_schema: tenantId ? 't_test' : null,
    roles,
    permissions: [],
  });
}

function dashboardHandlers(): Record<string, Handler> {
  return {
    'GET /dashboards/kpi/summary': (c) => ok(c, apiResponse({ tenant_id: 't', generated_at: '2026-08-14T00:00:00Z', cards: [], currency: 'KES' })),
    'GET /dashboards/charts/sales-trend': (c) => ok(c, apiResponse({ tenant_id: 't', chart_type: 'sales-trend', granularity: 'day', data: [], currency: 'KES' })),
    'GET /orders': (c) => ok(c, apiResponse({ items: [], pagination: { page: 1, size: 50, total: 0, pages: 0 } })),
    'GET /inventory/stocks': (c) => ok(c, apiResponse({ items: [], pagination: { page: 1, size: 50, total: 0, pages: 0 } })),
    'GET /client/products': (c) => ok(c, apiResponse({ items: [], pagination: { page: 1, size: 20, total: 0, pages: 0 } })),
    'GET /client/orders': (c) => ok(c, apiResponse({ items: [], pagination: { page: 1, size: 20, total: 0, pages: 0 } })),
  };
}

// ---------------------------------------------------------------------------
// Harness
// ---------------------------------------------------------------------------
function resetAuth(partial: Partial<ReturnType<typeof useAuthStore.getState>> = {}) {
  // Merge (NOT replace): the replace flag would wipe the store actions.
  useAuthStore.setState({
    accessToken: null,
    refreshToken: null,
    user: null,
    tenantCode: null,
    retailerPortalCode: null,
    ...partial,
  });
}

function renderAppAt(path: string) {
  window.history.pushState({}, '', path);
  const utils = render(<App />);
  // The real AppRouter's browser router is a module-level singleton; it does
  // not re-read window.location on remount. It is subscribed now, so a
  // synthetic popstate syncs it to the path under test.
  act(() => {
    window.dispatchEvent(new PopStateEvent('popstate', { state: window.history.state }));
  });
  return utils;
}

async function submitLogin(email = 'owner@example.com', pass = 'pw1r2-login-input') {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText('Email'), email);
  await user.type(screen.getByLabelText('Password'), pass);
  await user.click(screen.getByRole('button', { name: /sign in/i }));
}

const PENDING_TOKENS = {
  accessToken: 'identity-access-token',
  refreshToken: 'identity-refresh-token',
};

beforeEach(() => {
  window.localStorage.clear();
  resetAuth();
  // jsdom starts each test wherever the previous one ended; normalize.
  window.history.pushState({}, '', '/login');
});

afterEach(() => {
  // The real AppRouter's browser router is a module-level singleton shared by
  // every <App /> render; it only re-syncs from window.history while mounted
  // (via popstate). Reset the session FIRST (so the still-mounted PublicRoute
  // cannot bounce us back to '/'), then walk the router home, then unmount.
  resetAuth();
  window.history.pushState({}, '', '/login');
  window.dispatchEvent(new PopStateEvent('popstate', { state: window.history.state }));
  cleanup();
  // Restore the default axios adapter so later suites are unaffected.
  api.defaults.adapter = undefined;
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// M1/M2/M11 — multi-tenant handoff: selector renders, no business API, 1 POST
// ---------------------------------------------------------------------------
describe('PW1-R2 M1/M2/M11: multi-tenant login hands off to the workspace selector', () => {
  it('login 200 -> selector renders both tenants at /select-workspace; no dashboard API fired', async () => {
    const log = installAdapter({
      'POST /auth/login': (c) => ok(c, identityLoginBody(['admin'])),
      ...dashboardHandlers(),
    });

    renderAppAt('/login');
    await submitLogin();

    // M1: selector renders (real AppRouter)
    expect(await screen.findByText('Welcome Back')).toBeVisible();
    expect(await screen.findByText('Alpha Wholesale')).toBeVisible();
    expect(await screen.findByText('Beta Wholesale')).toBeVisible();
    await waitFor(() => expect(window.location.pathname).toBe('/select-workspace'));

    // M2: no business/dashboard API request may fire before selection
    const businessBeforeSelector = log.filter((k) => BUSINESS_API.test(k));
    expect(businessBeforeSelector, `business API fired pre-selection: ${businessBeforeSelector}`).toEqual([]);

    // M11: exactly ONE login POST for a single submit
    await new Promise((r) => setTimeout(r, 300)); // let any stray duplicate land
    expect(log.filter((k) => k === 'POST /auth/login')).toHaveLength(1);

    // Session is a PENDING identity session, not a contextual one
    const s = useAuthStore.getState();
    expect(s.accessToken).toBe('identity-access-token');
    expect(s.user).toBeNull();
    expect(sessionKind(s)).toBe('pending-identity');
    expect(window.location.search).toBe(''); // no tenants/tokens in the URL
  });
});

// ---------------------------------------------------------------------------
// M3/M4 — atomic completion and role-correct workspace entry
// ---------------------------------------------------------------------------
describe('PW1-R2 M3/M4: selection completes atomically into the correct workspace', () => {
  it('owner (admin): select-tenant 200 -> me 200 -> / with contextual session', async () => {
    const log = installAdapter({
      'POST /auth/login': (c) => ok(c, identityLoginBody(['admin'])),
      'POST /auth/select-tenant': (c) => ok(c, contextualBody(['admin'], TENANTS[0])),
      'GET /auth/me': (c) => ok(c, meBody(['admin'], TENANTS[0].id)),
      ...dashboardHandlers(),
    });

    renderAppAt('/login');
    await submitLogin();
    await screen.findByText('Alpha Wholesale');
    const preSelect = log.indexOf('POST /auth/select-tenant');

    await userEvent.click(screen.getByText('Alpha Wholesale'));

    await waitFor(() => expect(window.location.pathname).toBe('/'));
    // M3: order is login -> select-tenant -> me
    const iSelect = log.indexOf('POST /auth/select-tenant');
    const iMe = log.indexOf('GET /auth/me');
    expect(iSelect).toBeGreaterThan(log.indexOf('POST /auth/login'));
    expect(iMe).toBeGreaterThan(iSelect);
    expect(preSelect).toBe(-1); // no select call before the click
    // Contextual session committed atomically
    const s = useAuthStore.getState();
    expect(sessionKind(s)).toBe('contextual');
    expect(s.user?.roles).toContain('admin');
    expect(s.tenantCode).toBe('TENANT1');
  });

  it('retailer_operator: selection lands on /client (not the wholesaler shell)', async () => {
    installAdapter({
      'POST /auth/login': (c) => ok(c, identityLoginBody(['retailer_operator'])),
      'POST /auth/select-tenant': (c) => ok(c, contextualBody(['retailer_operator'], TENANTS[0])),
      'GET /auth/me': (c) => ok(c, meBody(['retailer_operator'], TENANTS[0].id)),
      ...dashboardHandlers(),
    });

    renderAppAt('/login');
    await submitLogin();
    await screen.findByText('Alpha Wholesale');

    await userEvent.click(screen.getByText('Alpha Wholesale'));

    await waitFor(() => expect(window.location.pathname).toBe('/client'), { timeout: 5000 });
    const s = useAuthStore.getState();
    expect(sessionKind(s)).toBe('contextual');
    expect(s.user?.roles).toContain('retailer_operator');
  });
});

// ---------------------------------------------------------------------------
// M5 — regression: single-tenant owner and super_admin
// ---------------------------------------------------------------------------
describe('PW1-R2 M5: single-tenant owner / super_admin flows do not regress', () => {
  it('single-tenant owner: auto select-tenant -> me -> / with contextual session', async () => {
    const log = installAdapter({
      'POST /auth/login': (c) => ok(c, identityLoginBody(['admin'], [TENANTS[0]])),
      'POST /auth/select-tenant': (c) => ok(c, contextualBody(['admin'], TENANTS[0])),
      'GET /auth/me': (c) => ok(c, meBody(['admin'], TENANTS[0].id)),
      ...dashboardHandlers(),
    });

    renderAppAt('/login');
    await submitLogin();

    await waitFor(() => expect(window.location.pathname).toBe('/'));
    expect(log).toContain('POST /auth/select-tenant');
    expect(log.indexOf('GET /auth/me')).toBeGreaterThan(log.indexOf('POST /auth/select-tenant'));
    const s = useAuthStore.getState();
    expect(sessionKind(s)).toBe('contextual');
    expect(s.tenantCode).toBe('TENANT1');
  });

  it('super_admin: identity me -> / without tenant selection', async () => {
    const log = installAdapter({
      'POST /auth/login': (c) => ok(c, identityLoginBody(['super_admin'])),
      'GET /auth/me': (c) => ok(c, meBody(['super_admin'], null)),
      ...dashboardHandlers(),
    });

    renderAppAt('/login');
    await submitLogin();

    await waitFor(() => expect(window.location.pathname).toBe('/'));
    expect(log).not.toContain('POST /auth/select-tenant');
    const s = useAuthStore.getState();
    expect(sessionKind(s)).toBe('contextual');
    expect(s.user?.roles).toContain('super_admin');
    expect(s.tenantCode).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// M6/M7/M8 — pending identity session guard closure
// ---------------------------------------------------------------------------
describe('PW1-R2 M6/M7/M8: pending identity session fails closed everywhere', () => {
  it('M6: pending session on / is redirected to /login; no business API fires', async () => {
    const log = installAdapter({ ...dashboardHandlers() });
    resetAuth({ ...PENDING_TOKENS });

    renderAppAt('/');

    await waitFor(() => expect(window.location.pathname).toBe('/login'));
    // login form visible; business shell never mounted
    expect(await screen.findByLabelText('Email')).toBeVisible();
    await new Promise((r) => setTimeout(r, 200));
    expect(log.filter((k) => BUSINESS_API.test(k))).toEqual([]);
    expect(sessionKind(useAuthStore.getState())).toBe('pending-identity');
  });

  it('M6: pending session never renders MainLayout content (no dashboard shell)', async () => {
    installAdapter({ ...dashboardHandlers() });
    resetAuth({ ...PENDING_TOKENS });
    renderAppAt('/orders');
    await waitFor(() => expect(window.location.pathname).toBe('/login'));
    expect(screen.queryByText('Dashboard')).toBeNull();
  });

  it('M7: pending session is NOT redirected off /login by PublicRoute', async () => {
    installAdapter({ ...dashboardHandlers() });
    resetAuth({ ...PENDING_TOKENS });

    renderAppAt('/login');

    // Give any (incorrect) redirect a chance to fire
    await new Promise((r) => setTimeout(r, 200));
    expect(window.location.pathname).toBe('/login');
    expect(await screen.findByLabelText('Email')).toBeVisible();
  });

  it('M8: /select-workspace without navigation state returns to /login, never the shell', async () => {
    const log = installAdapter({ ...dashboardHandlers() });
    resetAuth({ ...PENDING_TOKENS });

    renderAppAt('/select-workspace');

    await waitFor(() => expect(window.location.pathname).toBe('/login'));
    await new Promise((r) => setTimeout(r, 200));
    expect(log.filter((k) => BUSINESS_API.test(k))).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// M9 — selection failure leaves no contextual session and no business API
// ---------------------------------------------------------------------------
describe('PW1-R2 M9: select-tenant/me failure keeps the session pending and retry-safe', () => {
  it('select-tenant 500: neutral error, no user, no business API; retry succeeds', async () => {
    let selectFails = true;
    const log = installAdapter({
      'POST /auth/login': (c) => ok(c, identityLoginBody(['admin'])),
      'POST /auth/select-tenant': (c) => {
        if (selectFails) throw httpError(c, 500, { code: 'INTERNAL_SERVER_ERROR', message: 'SECRETS: internal detail' });
        return ok(c, contextualBody(['admin'], TENANTS[0]));
      },
      'GET /auth/me': (c) => ok(c, meBody(['admin'], TENANTS[0].id)),
      ...dashboardHandlers(),
    });

    renderAppAt('/login');
    await submitLogin();
    await screen.findByText('Alpha Wholesale');

    await userEvent.click(screen.getByText('Alpha Wholesale'));

    // Neutral copy only; session stays pending; no business API
    expect(await screen.findByText('Failed to select workspace. Please try again.')).toBeVisible();
    expect(useAuthStore.getState().user).toBeNull();
    expect(useAuthStore.getState().accessToken).toBe('identity-access-token');
    await new Promise((r) => setTimeout(r, 200));
    expect(log.filter((k) => BUSINESS_API.test(k))).toEqual([]);

    // Retry (adapter now healthy) completes atomically
    selectFails = false;
    await userEvent.click(screen.getByText('Alpha Wholesale'));
    await waitFor(() => expect(window.location.pathname).toBe('/'));
    expect(sessionKind(useAuthStore.getState())).toBe('contextual');
  });

  it('me 500 after select-tenant 200: NO contextual session is committed', async () => {
    const log = installAdapter({
      'POST /auth/login': (c) => ok(c, identityLoginBody(['admin'])),
      'POST /auth/select-tenant': (c) => ok(c, contextualBody(['admin'], TENANTS[0])),
      'GET /auth/me': (c) => {
        throw httpError(c, 500, { code: 'X', message: 'boom' });
      },
      ...dashboardHandlers(),
    });

    renderAppAt('/login');
    await submitLogin();
    await screen.findByText('Alpha Wholesale');

    await userEvent.click(screen.getByText('Alpha Wholesale'));

    expect(await screen.findByText('Failed to select workspace. Please try again.')).toBeVisible();
    // The contextual token from select-tenant must NOT have been committed
    expect(useAuthStore.getState().accessToken).toBe('identity-access-token');
    expect(useAuthStore.getState().user).toBeNull();
    expect(sessionKind(useAuthStore.getState())).toBe('pending-identity');
    await new Promise((r) => setTimeout(r, 200));
    expect(log.filter((k) => BUSINESS_API.test(k))).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// M10 — D2: fixed neutral copy on owner login failures
// ---------------------------------------------------------------------------
describe('PW1-R2 M10: owner login failures show fixed neutral copy only', () => {
  it('flat-envelope 401 with malicious message renders exactly "Invalid credentials"', async () => {
    installAdapter({
      'POST /auth/login': (c) => {
        throw httpError(c, 401, {
          code: 'INVALID_CREDENTIALS',
          message: 'SECRETS: password hash salt = xyz', // malicious backend message
          request_id: 'req-secret-123',
        });
      },
    });

    renderAppAt('/login');
    await submitLogin();

    const alert = await screen.findByText('Invalid credentials');
    expect(alert).toBeVisible();
    // None of the internal material may reach the UI
    expect(screen.queryByText(/SECRETS/i)).toBeNull();
    expect(screen.queryByText(/req-secret-123/i)).toBeNull();
    expect(document.body.textContent).not.toContain('INVALID_CREDENTIALS');
    // Failure keeps URL + zero token persistence + zero navigation
    expect(window.location.pathname).toBe('/login');
    expect(useAuthStore.getState().accessToken).toBeNull();
  });

  it('legacy envelope 401 renders exactly "Invalid credentials" (no legacy message leak)', async () => {
    installAdapter({
      'POST /auth/login': (c) => {
        throw httpError(c, 401, { error: { code: 'LEGACY', message: 'EVIL-INTERNAL-DETAIL' } });
      },
    });

    renderAppAt('/login');
    await submitLogin();

    expect(await screen.findByText('Invalid credentials')).toBeVisible();
    expect(screen.queryByText(/EVIL-INTERNAL-DETAIL/i)).toBeNull();
  });

  it('non-401 (500) with malicious message renders the fixed neutral fallback', async () => {
    installAdapter({
      'POST /auth/login': (c) => {
        throw httpError(c, 500, { code: 'BOOM', message: 'sqlalchemy traceback SECRETS' });
      },
    });

    renderAppAt('/login');
    await submitLogin();

    expect(await screen.findByText('Unable to sign in. Please try again.')).toBeVisible();
    expect(screen.queryByText(/sqlalchemy/i)).toBeNull();
    expect(screen.queryByText(/SECRETS/i)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Minimal guard harness (no App singleton): fast, loop-free RED evidence for
// the token-only guard mutations (M12). Behavioral render+assert — the guard
// component under test is the REAL production component.
// ---------------------------------------------------------------------------
describe('PW1-R2 guard contract (minimal harness, real guard components)', () => {
  it('PublicRoute admits a pending identity session on /login (no bounce to /)', async () => {
    resetAuth({ ...PENDING_TOKENS });
    render(
      <MemoryRouter initialEntries={['/login']}>
        <Routes>
          <Route element={<PublicRoute />}>
            <Route path="/login" element={<div data-testid="login-page">Login</div>} />
          </Route>
          <Route path="/" element={<div data-testid="home-page">Dashboard</div>} />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByTestId('login-page')).toBeVisible();
    expect(screen.queryByTestId('home-page')).toBeNull();
  });

  it('PublicRoute redirects a contextual session to /', async () => {
    resetAuth({
      accessToken: 'ctx',
      refreshToken: 'ctx-r',
      user: { id: 'u', email: 'e', full_name: null, tenant_id: 't', tenant_schema: 's', roles: ['admin'], permissions: [] },
    });
    render(
      <MemoryRouter initialEntries={['/login']}>
        <Routes>
          <Route element={<PublicRoute />}>
            <Route path="/login" element={<div data-testid="login-page">Login</div>} />
          </Route>
          <Route path="/" element={<div data-testid="home-page">Dashboard</div>} />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByTestId('home-page')).toBeVisible();
    expect(screen.queryByTestId('login-page')).toBeNull();
  });

  it('ProtectedRoute rejects a pending identity session (fail closed to /login)', async () => {
    resetAuth({ ...PENDING_TOKENS });
    render(
      <MemoryRouter initialEntries={['/orders']}>
        <Routes>
          <Route element={<ProtectedRoute />}>
            <Route path="/orders" element={<div data-testid="orders-page">Orders</div>} />
          </Route>
          <Route path="/login" element={<div data-testid="login-page">Login</div>} />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByTestId('login-page')).toBeVisible();
    expect(screen.queryByTestId('orders-page')).toBeNull();
  });

  it('ProtectedRoute admits a contextual session', async () => {
    resetAuth({
      accessToken: 'ctx',
      refreshToken: 'ctx-r',
      user: { id: 'u', email: 'e', full_name: null, tenant_id: 't', tenant_schema: 's', roles: ['admin'], permissions: [] },
    });
    render(
      <MemoryRouter initialEntries={['/orders']}>
        <Routes>
          <Route element={<ProtectedRoute />}>
            <Route path="/orders" element={<div data-testid="orders-page">Orders</div>} />
          </Route>
          <Route path="/login" element={<div data-testid="login-page">Login</div>} />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByTestId('orders-page')).toBeVisible();
    expect(screen.queryByTestId('login-page')).toBeNull();
  });

  it('WholesalerRoute rejects a pending identity session on its own authority', async () => {
    resetAuth({ ...PENDING_TOKENS });
    render(
      <MemoryRouter initialEntries={['/orders']}>
        <Routes>
          <Route element={<WholesalerRoute />}>
            <Route path="/orders" element={<div data-testid="orders-page">Orders</div>} />
          </Route>
          <Route path="/login" element={<div data-testid="login-page">Login</div>} />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByTestId('login-page')).toBeVisible();
    expect(screen.queryByTestId('orders-page')).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Store contract unit checks (binding derived facts)
// ---------------------------------------------------------------------------
describe('PW1-R2 binding session contract (derived facts)', () => {
  it('sessionKind derives anonymous / pending-identity / contextual', () => {
    expect(sessionKind({ accessToken: null, user: null })).toBe('anonymous');
    expect(sessionKind({ accessToken: 't', user: null })).toBe('pending-identity');
    expect(sessionKind({ accessToken: 't', user: {} as never })).toBe('contextual');
    // token-less user is anonymous (never admitted)
    expect(sessionKind({ accessToken: null, user: {} as never })).toBe('anonymous');
  });

  it('beginWorkspaceSelection writes a pending session and clears portal context', () => {
    resetAuth({ retailerPortalCode: 'PORTAL1', tenantCode: 'OLD' });
    useAuthStore.getState().beginWorkspaceSelection({
      access_token: 'identity-access-token',
      refresh_token: 'identity-refresh-token',
    });
    const s = useAuthStore.getState();
    expect(s.accessToken).toBe('identity-access-token');
    expect(s.refreshToken).toBe('identity-refresh-token');
    expect(s.user).toBeNull();
    expect(s.tenantCode).toBeNull();
    expect(s.retailerPortalCode).toBeNull();
    expect(sessionKind(s)).toBe('pending-identity');
  });

  it('updateTokens keeps a pending session pending (refresh-only semantics)', () => {
    resetAuth({ ...PENDING_TOKENS });
    useAuthStore.getState().updateTokens({ access_token: 'fresh', refresh_token: 'fresh-r' });
    const s = useAuthStore.getState();
    expect(s.accessToken).toBe('fresh');
    expect(s.user).toBeNull();
    expect(sessionKind(s)).toBe('pending-identity');
  });

  it('logout preserves the retailer portal code (DC-12R1-S2 regression guard)', () => {
    resetAuth({
      accessToken: 'ctx',
      refreshToken: 'ctx-r',
      user: meBody(['retailer_operator'], 't1').data,
      tenantCode: 'PORTAL1',
      retailerPortalCode: 'PORTAL1',
    });
    useAuthStore.getState().logout();
    const s = useAuthStore.getState();
    expect(s.retailerPortalCode).toBe('PORTAL1');
    expect(sessionKind(s)).toBe('anonymous');
  });
});
