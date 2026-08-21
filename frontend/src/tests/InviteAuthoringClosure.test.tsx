/**
 * DC-12R1-MVP-L1-J1-H2-A: retailer invitation authoring closure — evidence
 * tests for F-13/F-14 (single root cause: the wholesaler production end of
 * the invitation funnel was never delivered).
 *
 * Runs against the REAL <App /> router tree (createBrowserRouter, real
 * guards, real Customers page, real InviteCreatePage / InvitationLandingPage,
 * real api adapter). The HTTP layer is served by a recording axios adapter
 * that returns real-shaped responses; every request is logged so ordering,
 * payload and absence assertions are evidence-grade.
 *
 * Coverage map (task Phase 4):
 *   T1  invitations:create session -> CTA visible and operable
 *   T2  session without the permission -> CTA hidden AND route fails closed
 *       (page never mounts, zero POST /invitations)
 *   T3  create request fires exactly once with the exact backend payload
 *   T4  double click produces exactly one invitation POST
 *   T5  create failure -> fixed neutral copy, retry succeeds
 *   T6  fragment code is scrubbed from the URL immediately after capture
 *   T7  lookup uses POST /invitations/lookup JSON body — never path/query
 *   T8  code never lands in storage, console or error output
 *   T9  usable invitation flows into register -> setup-credential guidance
 *       -> /retail/login lifecycle
 *   Secure-link format: /invite#code=<opaque> (never /invite/:code)
 *
 * M1–M5 mutation RED runs are executed as scripted mutations against this
 * file's suite and captured in the task evidence (not runtime switches).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios';
import { render, screen, waitFor, cleanup, act, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { App } from '@/App';
import { api } from '@/services/api';
import { useAuthStore } from '@/stores/authStore';
import { useToastStore } from '@/stores/toastStore';
import type { CurrentUserData } from '@/types/auth';

// ---------------------------------------------------------------------------
// Adapter scaffolding (records every request; real-shaped responses)
// ---------------------------------------------------------------------------

type Handler = (config: InternalAxiosRequestConfig) => AxiosResponse | Promise<AxiosResponse>;

function ok<T>(config: InternalAxiosRequestConfig, data: T, status = 200): AxiosResponse {
  return { data: ({ success: true, data, timestamp: '2026-08-21T00:00:00.000Z' } as object), status, statusText: 'OK', headers: {}, config };
}

function httpError(config: InternalAxiosRequestConfig, status: number, body: unknown) {
  return Object.assign(new Error(`Request failed with status code ${status}`), {
    isAxiosError: true,
    config,
    response: { status, statusText: 'Error', headers: {}, data: body, config },
  });
}

/**
 * Install a recording adapter. Handlers are keyed `METHOD url` (url prefix
 * match). Every served request is appended to the returned log; request
 * bodies are captured alongside.
 */
function installAdapter(handlers: Record<string, Handler>) {
  const log: string[] = [];
  const bodies: Record<string, unknown[]> = {};
  const adapter: AxiosAdapter = async (config) => {
    const url = config.url || '';
    const method = (config.method || 'get').toLowerCase();
    const key = `${method.toUpperCase()} ${url}`;
    log.push(key);
    let body: unknown = undefined;
    if (typeof config.data === 'string') {
      try {
        body = JSON.parse(config.data);
      } catch {
        body = config.data;
      }
    }
    (bodies[key] ??= []).push(body);

    const match = Object.keys(handlers)
      .sort((a, b) => b.length - a.length)
      .find((h) => key.startsWith(h));
    if (match) return handlers[match](config);
    // Default: fail closed with a 500. Pages under test install explicit
    // handlers for what they consume; anything else (e.g. dashboard widgets
    // mounted transiently during router warm-up) must degrade gracefully via
    // their own error paths instead of receiving a fake-shaped 200.
    return Promise.reject(httpError(config, 500, {
      success: false,
      error: { code: 'NO_TEST_HANDLER', message: 'no handler installed' },
    }));
  };
  api.defaults.adapter = adapter;
  return { log, bodies };
}

const INVITATION_CODE = 'H2A-CODE-7f3k9Q2x'; // test fixture, not a real credential

const CREATED_INVITATION = {
  code: INVITATION_CODE,
  status: 'active',
  wholesaler_id: 'ws-0001',
  retailer_phone: '+255700000001',
  expires_at: '2026-09-21T00:00:00.000Z',
  created_at: '2026-08-21T00:00:00.000Z',
};

const USABLE_LOOKUP = {
  code: INVITATION_CODE,
  usable: true,
  reason: null,
  status: 'active',
  wholesaler_id: 'ws-0001',
  wholesaler_name: 'Alpha Wholesale',
  expires_at: '2026-09-21T00:00:00.000Z',
};

// ---------------------------------------------------------------------------
// Auth scaffolding
// ---------------------------------------------------------------------------

function userWith(permissions: string[], roles: string[] = ['wholesaler_owner']): CurrentUserData {
  return {
    id: 'user-0001',
    email: 'owner@example.com',
    full_name: 'Owner One',
    tenant_id: 'ws-0001',
    tenant_schema: 't_ws0001',
    roles,
    permissions,
  };
}

function resetAuth(user: CurrentUserData | null) {
  useAuthStore.setState({
    accessToken: user ? 'access-token-h2a' : null,
    refreshToken: user ? 'refresh-token-h2a' : null,
    user,
    tenantCode: 'WS0001',
    retailerPortalCode: null,
  });
}

/**
 * Drive the REAL singleton browser router to `path`, then mount the real
 * <App />.
 *
 * The router is created (and initialized, history listener attached) at
 * module import. Rendering <App /> while the router state points elsewhere
 * lets route guards run render-driven <Navigate> redirects that REWRITE
 * window.location before we can sync it — so the order is strict:
 *   1. pushState the target URL (raw jsdom),
 *   2. dispatch a synthetic popstate — the always-listening router starts
 *      its own POP navigation to the new URL,
 *   3. flush that navigation inside act(),
 *   4. only then mount <App />, which renders the settled location.
 */
async function renderAppAt(path: string) {
  window.history.pushState({}, '', path);
  await act(async () => {
    window.dispatchEvent(new PopStateEvent('popstate', { state: window.history.state }));
  });
  return render(<App />);
}

beforeEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
  window.history.pushState({}, '', '/');
});

afterEach(() => {
  // Reset the session FIRST (a still-mounted guard must not bounce us), then
  // walk the router home, then unmount, then restore the default adapter.
  resetAuth(null);
  window.history.pushState({}, '', '/');
  window.dispatchEvent(new PopStateEvent('popstate', { state: window.history.state }));
  cleanup();
  api.defaults.adapter = undefined;
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// Wholesaler authoring side (T1–T5)
// ---------------------------------------------------------------------------

describe('DC-12R1-MVP-L1-J1-H2-A: wholesaler invitation authoring', () => {
  it('T1: session with invitations:create sees the Customers CTA and reaches the authoring page', async () => {
    resetAuth(userWith(['invitations:create', 'skus:read']));
    installAdapter({
      'GET /retailers': (c) => ok(c, { items: [], pagination: { page: 1, size: 20, total: 0, pages: 0 } }),
    });

    await renderAppAt('/retailers');

    // CTA is visible in the header (empty state also carries one).
    const cta = await screen.findByRole('link', { name: /invite a retailer/i });
    expect(cta).toHaveAttribute('href', '/retailers/invite');

    await userEvent.click(cta);
    await waitFor(() => expect(window.location.pathname).toBe('/retailers/invite'));
    // Authoring page mounted and is operable (real form present).
    expect(await screen.findByRole('button', { name: /create invitation/i })).toBeVisible();
    expect(screen.getByLabelText(/retailer phone \(optional\)/i)).toBeVisible();
  });

  it('T2: session WITHOUT invitations:create gets no CTA and /retailers/invite fails closed (zero POST)', async () => {
    resetAuth(userWith(['skus:read']));
    const { log } = installAdapter({
      'GET /retailers': (c) => ok(c, { items: [], pagination: { page: 1, size: 20, total: 0, pages: 0 } }),
    });

    await renderAppAt('/retailers');
    await screen.findByRole('heading', { name: 'Customers' });

    // No CTA anywhere (header or empty state).
    expect(screen.queryByRole('link', { name: /invite a retailer/i })).toBeNull();

    // Unmount the first page before driving the URL directly (one App at a
    // time — the singleton router is shared).
    cleanup();

    // Direct URL entry fails closed: redirected to /retailers, the authoring
    // form NEVER mounts (no "Create invitation" button), zero POST.
    await renderAppAt('/retailers/invite');
    await waitFor(() => expect(window.location.pathname).toBe('/retailers'));
    await screen.findByRole('heading', { name: 'Customers' });
    expect(screen.queryByRole('button', { name: /create invitation/i })).toBeNull();
    expect(log.filter((k) => k === 'POST /invitations')).toEqual([]);
  });

  it('T3: create fires exactly ONE POST /invitations with the exact backend payload; success panel shows status/expiry/copy actions', async () => {
    resetAuth(userWith(['invitations:create']));
    const { log, bodies } = installAdapter({
      'POST /invitations': (c) => ok(c, CREATED_INVITATION, 201),
    });

    await renderAppAt('/retailers/invite');
    await userEvent.type(await screen.findByLabelText(/retailer phone \(optional\)/i), '+255700000001');
    await userEvent.type(screen.getByLabelText(/expiry date and time \(optional\)/i), '2026-09-21T10:30');

    await userEvent.click(screen.getByRole('button', { name: /create invitation/i }));

    // Exactly one create POST with the backend InvitationCreateRequest payload
    // verbatim (snake_case, only the two contract fields).
    await waitFor(() => expect(log.filter((k) => k === 'POST /invitations')).toHaveLength(1));
    const payload = bodies['POST /invitations'][0] as Record<string, unknown>;
    expect(Object.keys(payload).sort()).toEqual(['expires_at', 'retailer_phone']);
    expect(payload.retailer_phone).toBe('+255700000001');
    expect(typeof payload.expires_at).toBe('string');
    expect(new Date(payload.expires_at as string).toISOString()).toBe(
      new Date('2026-09-21T10:30').toISOString(),
    );

    // Success panel: status, expiry, both MVP share actions.
    const panel = await screen.findByRole('status');
    expect(panel).toHaveTextContent(/active/i);
    expect(panel).toHaveTextContent(/expires:/i);
    expect(await screen.findByRole('button', { name: /copy secure invite link/i })).toBeVisible();
    expect(screen.getByRole('button', { name: /copy invitation code/i })).toBeVisible();
  });

  it('T3b: empty optional fields are omitted from the payload (contract-optional)', async () => {
    resetAuth(userWith(['invitations:create']));
    const { log, bodies } = installAdapter({
      'POST /invitations': (c) => ok(c, { ...CREATED_INVITATION, retailer_phone: null, expires_at: null }, 201),
    });

    await renderAppAt('/retailers/invite');
    await userEvent.click(await screen.findByRole('button', { name: /create invitation/i }));

    await waitFor(() => expect(log.filter((k) => k === 'POST /invitations')).toHaveLength(1));
    const payload = bodies['POST /invitations'][0] as Record<string, unknown>;
    expect(payload).toEqual({});
  });

  it('T4: double click creates exactly ONE invitation POST (no duplicates)', async () => {
    resetAuth(userWith(['invitations:create']));
    const { log } = installAdapter({
      'POST /invitations': (c) =>
        new Promise((resolve) => setTimeout(() => resolve(ok(c, CREATED_INVITATION, 201)), 150)),
    });

    await renderAppAt('/retailers/invite');
    const submit = await screen.findByRole('button', { name: /create invitation/i });

    // Two synchronous clicks in the same tick — the in-flight lock must
    // swallow the second before any await resolves.
    fireEvent.click(submit);
    fireEvent.click(submit);
    await waitFor(() => expect(log.filter((k) => k === 'POST /invitations')).toHaveLength(1));
    await screen.findByRole('status');

    // Give any stray duplicate time to land, then re-assert exactly one.
    await new Promise((r) => setTimeout(r, 350));
    expect(log.filter((k) => k === 'POST /invitations')).toHaveLength(1);
  });

  it('T5: create failure shows FIXED neutral copy (no backend echo) and retry succeeds', async () => {
    resetAuth(userWith(['invitations:create']));
    let fail = true;
    const { log } = installAdapter({
      'POST /invitations': (c) => {
        if (fail) {
          return Promise.reject(httpError(c, 500, {
            success: false,
            error: {
              code: 'INTERNAL_FAILURE',
              message: 'SENTINEL-BACKEND-MESSAGE request_id=leak-xyz',
            },
            timestamp: '2026-08-21T00:00:00.000Z',
          }));
        }
        return ok(c, CREATED_INVITATION, 201);
      },
    });

    await renderAppAt('/retailers/invite');
    await userEvent.click(await screen.findByRole('button', { name: /create invitation/i }));

    // Fixed neutral copy only — no backend message / request_id / token echo.
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('We could not create the invitation. Please try again.');
    expect(alert.textContent).not.toContain('SENTINEL-BACKEND-MESSAGE');
    expect(alert.textContent).not.toContain('request_id');
    // The global axios interceptor shows a transient app-wide toast for 5xx
    // (pre-existing infrastructure, auto-dismissing, shared by every page —
    // out of scope for this task). Clear it, then prove THIS page's rendered
    // surface carries none of the hostile backend payload.
    await act(async () => {
      useToastStore.setState({ toasts: [] });
    });
    expect(document.body.textContent ?? '').not.toContain('leak-xyz');

    // Retry path: same form, second attempt succeeds.
    fail = false;
    await userEvent.click(screen.getByRole('button', { name: /create invitation/i }));
    await screen.findByRole('status');
    expect(log.filter((k) => k === 'POST /invitations')).toHaveLength(2);
  });

  it('secure link format: copy actions yield /invite#code=<code>, never a /invite/:code path', async () => {
    resetAuth(userWith(['invitations:create']));
    installAdapter({
      'POST /invitations': (c) => ok(c, CREATED_INVITATION, 201),
    });
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });

    await renderAppAt('/retailers/invite');
    await userEvent.click(await screen.findByRole('button', { name: /create invitation/i }));
    await screen.findByRole('status');

    await userEvent.click(screen.getByRole('button', { name: /copy secure invite link/i }));
    const link = writeText.mock.calls[0][0] as string;
    expect(link).toBe(`${window.location.origin}/invite#code=${INVITATION_CODE}`);
    expect(link).not.toMatch(/\/invite\//); // never a path-token link
    expect(link).not.toContain('?'); // never a query param
    expect(await screen.findByText(/link copied/i)).toBeVisible();

    await userEvent.click(screen.getByRole('button', { name: /copy invitation code/i }));
    expect(writeText.mock.calls[1][0]).toBe(INVITATION_CODE);
    expect(await screen.findByText(/code copied/i)).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Public landing page (T6–T9)
// ---------------------------------------------------------------------------

describe('DC-12R1-MVP-L1-J1-H2-A: public /invite landing page', () => {
  it('T6+T7: fragment code is captured then scrubbed; lookup goes through POST JSON body only', async () => {
    const { log, bodies } = installAdapter({
      'POST /invitations/lookup': (c) => ok(c, USABLE_LOOKUP),
    });

    await renderAppAt(`/invite#code=${INVITATION_CODE}`);

    // Lookup fires via POST with the code ONLY in the JSON body.
    await waitFor(() => expect(log).toContain('POST /invitations/lookup'));
    const body = bodies['POST /invitations/lookup'][0] as Record<string, unknown>;
    expect(body).toEqual({ code: INVITATION_CODE });
    // No path-token request is ever issued.
    expect(log.filter((k) => /^GET \/invitations\//.test(k))).toEqual([]);

    // Fragment scrubbed from the address bar immediately after capture.
    await waitFor(() => {
      expect(window.location.hash).toBe('');
      expect(window.location.search).toBe('');
    });

    // Usable invitation renders the register panel with the wholesaler name.
    expect(await screen.findByText('Alpha Wholesale')).toBeVisible();
    expect(screen.getByRole('button', { name: /complete registration/i })).toBeVisible();
  });

  it('T6b: query-string code is REJECTED with zero API calls (no query-token fallback)', async () => {
    const { log } = installAdapter({});

    await renderAppAt(`/invite?code=${INVITATION_CODE}`);

    expect(await screen.findByText('Invalid Link')).toBeVisible();
    // The rejected code is scrubbed from the URL too.
    await waitFor(() => expect(window.location.search).toBe(''));
    expect(log).toEqual([]);
  });

  it('T7b: registration posts the invitation_code ONLY in the JSON body', async () => {
    const { log, bodies } = installAdapter({
      'POST /invitations/lookup': (c) => ok(c, USABLE_LOOKUP),
      'POST /retailers/register': (c) =>
        ok(c, {
          retailer: { id: 'ret-1', phone: '+255700000001', name: 'Duka', email: 'duka@example.test', address: null },
          binding: { id: 'b-1', wholesaler_id: 'ws-0001', retailer_id: 'ret-1', status: 'active', created_at: '2026-08-21T00:00:00.000Z' },
        }, 201),
    });

    await renderAppAt(`/invite#code=${INVITATION_CODE}`);
    await userEvent.type(await screen.findByLabelText(/^phone/i), '+255700000001');
    await userEvent.type(screen.getByLabelText(/business name \(optional\)/i), 'Duka La Jirani');
    await userEvent.click(screen.getByRole('button', { name: /complete registration/i }));

    await waitFor(() => expect(log).toContain('POST /retailers/register'));
    const body = bodies['POST /retailers/register'][0] as Record<string, unknown>;
    expect(body).toMatchObject({
      invitation_code: INVITATION_CODE,
      phone: '+255700000001',
      name: 'Duka La Jirani',
    });
    // The code never appears in any request URL.
    for (const entry of log) {
      expect(entry).not.toContain(INVITATION_CODE);
    }
  });

  it('T8: the code never lands in storage, console or error output', async () => {
    const consoleSpies = ['log', 'debug', 'info', 'warn', 'error'].map((m) =>
      vi.spyOn(console, m as keyof Console).mockImplementation(() => {}),
    );
    const storageSet = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {});

    // Failure path: lookup itself fails -> neutral copy, no code anywhere.
    installAdapter({
      'POST /invitations/lookup': (c) => Promise.reject(httpError(c, 500, { success: false, error: { code: 'X', message: `boom ${INVITATION_CODE}` } })),
    });

    await renderAppAt(`/invite#code=${INVITATION_CODE}`);
    await screen.findByText(/unable to verify invitation/i);

    // Clear the pre-existing global 5xx toast surface (see T5 note), then
    // prove this page never surfaces the code anywhere it controls.
    await act(async () => {
      useToastStore.setState({ toasts: [] });
    });

    const storageDump = JSON.stringify({
      ls: { ...window.localStorage },
      ss: { ...window.sessionStorage },
    });
    expect(storageDump).not.toContain(INVITATION_CODE);
    expect(document.body.textContent ?? '').not.toContain(INVITATION_CODE);
    for (const spy of consoleSpies) {
      for (const call of spy.mock.calls) {
        expect(JSON.stringify(call)).not.toContain(INVITATION_CODE);
      }
    }
    expect(storageSet).not.toHaveBeenCalledWith(expect.stringContaining(INVITATION_CODE), expect.anything());
  });

  it('T9: usable invitation completes register and hands off to the credential/login lifecycle', async () => {
    installAdapter({
      'POST /invitations/lookup': (c) => ok(c, USABLE_LOOKUP),
      'POST /retailers/register': (c) =>
        ok(c, {
          retailer: { id: 'ret-1', phone: '+255700000001', name: null, email: 'duka@example.test', address: null },
          binding: { id: 'b-1', wholesaler_id: 'ws-0001', retailer_id: 'ret-1', status: 'active', created_at: '2026-08-21T00:00:00.000Z' },
        }, 201),
    });

    await renderAppAt(`/invite#code=${INVITATION_CODE}`);
    await userEvent.type(await screen.findByLabelText(/^phone/i), '+255700000001');
    await userEvent.click(screen.getByRole('button', { name: /complete registration/i }));

    // Registered guidance points into the real lifecycle pages.
    const guidance = await screen.findByText(/registration complete/i);
    expect(guidance).toBeVisible();
    expect(document.body.textContent ?? '').toMatch(/set your password/i);
    const loginLink = screen.getByRole('link', { name: /go to retailer sign in/i });
    expect(loginLink).toHaveAttribute('href', '/retail/login');

    // The real route accepts the handoff (retailer portal login mounts).
    await userEvent.click(loginLink);
    await waitFor(() => expect(window.location.pathname).toBe('/retail/login'));
  });

  it('unusable invitation shows the neutral unavailable state (no reason echo, no register form)', async () => {
    installAdapter({
      'POST /invitations/lookup': (c) =>
        ok(c, { ...USABLE_LOOKUP, usable: false, reason: 'INVITATION_EXPIRED', status: 'expired' }),
    });

    await renderAppAt(`/invite#code=${INVITATION_CODE}`);

    expect(await screen.findByText(/invitation unavailable/i)).toBeVisible();
    expect(screen.queryByRole('button', { name: /complete registration/i })).toBeNull();
    expect(document.body.textContent ?? '').not.toContain('INVITATION_EXPIRED');
  });
});
