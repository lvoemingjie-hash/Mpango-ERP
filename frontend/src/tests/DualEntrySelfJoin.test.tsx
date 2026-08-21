/**
 * DC-12R1-MVP-L1-J1-H2-A-R1: dual-entry retailer self-join — evidence tests.
 *
 * Runs against the REAL <App /> router tree (real guards, real pages, real
 * api adapter); the HTTP layer is a recording axios adapter returning
 * real-shaped responses. Coverage map (task Phase 4 / dual-entry contract):
 *
 *   T2  code lookup -> preview identity -> explicit confirm -> register with
 *       join_intent -> auto-bind (exactly one POST, no wholesaler_id key)
 *   T3  unknown code -> neutral miss, no preview, zero register POSTs
 *   T5  payloads carry EXACTLY ONE entry credential (both/neither impossible
 *       from the shipped UI surfaces)
 *   T7  double submit -> exactly one relationship POST
 *   T9  stale contextual session: public join unaffected (empty
 *       Authorization, no refresh, session intact)
 *   T12 register -> server-verified portal handoff -> real ClientLoginPage
 *       mounts with a valid w (never bare /retail/login, never /login)
 *   T13 the register payload NEVER contains a client wholesaler_id; a
 *       tampered intent (backend JOIN_INTENT_INVALID) binds nothing
 *   T14 Web Share unsupported/failure -> safe copy fallback
 *   Customers page: join_source display + permission-gated deactivate
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
// Recording adapter (same evidence pattern as InviteAuthoringClosure)
// ---------------------------------------------------------------------------

type Handler = (config: InternalAxiosRequestConfig) => AxiosResponse | Promise<AxiosResponse>;

function ok(config: InternalAxiosRequestConfig, data: unknown, status = 200): AxiosResponse {
  return {
    data: { success: true, data, timestamp: '2026-08-21T00:00:00.000Z' } as object,
    status,
    statusText: 'OK',
    headers: {},
    config,
  };
}

function httpError(config: InternalAxiosRequestConfig, status: number, body: unknown) {
  return Object.assign(new Error(`Request failed with status code ${status}`), {
    isAxiosError: true,
    config,
    response: { status, statusText: 'Error', headers: {}, data: body, config },
  });
}

function installAdapter(handlers: Record<string, Handler>) {
  const log: string[] = [];
  const bodies: Record<string, unknown[]> = {};
  const headers: Record<string, unknown[]> = {};
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
    const authz =
      typeof config.headers?.get === 'function'
        ? config.headers.get('Authorization')
        : undefined;
    (headers[key] ??= []).push(authz as unknown as string);

    const match = Object.keys(handlers)
      .sort((a, b) => b.length - a.length)
      .find((h) => key.startsWith(h));
    if (match) return handlers[match](config);
    return Promise.reject(
      httpError(config, 500, {
        success: false,
        error: { code: 'NO_TEST_HANDLER', message: 'no handler installed' },
      }),
    );
  };
  api.defaults.adapter = adapter;
  return { log, bodies, headers };
}

const SUPPLIER_CODE = 'ALPHA42';
const JOIN_INTENT = 'r1joinintent.testsig';

const PREVIEW_FOUND = {
  found: true,
  name: 'Alpha Wholesale',
  region: '12 Supplier Avenue',
  contact_masked: '+25********56',
  join_intent: JOIN_INTENT,
  expires_at: '2026-08-21T00:15:00.000Z',
};

const REGISTERED = {
  retailer: { id: 'ret-9', phone: '+255700099901', name: 'Duka', email: 'duka@example.com', address: null },
  binding: {
    id: 'bind-9',
    wholesaler_id: 'ws-0001',
    retailer_id: 'ret-9',
    status: 'active',
    created_at: '2026-08-21T00:00:00.000Z',
  },
  wholesaler_code: SUPPLIER_CODE,
};

// ---------------------------------------------------------------------------
// Auth / router helpers
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
    accessToken: user ? 'access-token-r1' : null,
    refreshToken: user ? 'refresh-token-r1' : null,
    user,
    tenantCode: 'WS0001',
    retailerPortalCode: null,
  });
}

async function renderAppAt(path: string) {
  window.history.pushState({}, '', path);
  await act(async () => {
    window.dispatchEvent(new PopStateEvent('popstate', { state: window.history.state }));
  });
  return render(<App />);
}

async function goViaCodeEntry() {
  await renderAppAt('/retail/join');
  await userEvent.click(screen.getByRole('tab', { name: /supplier code/i }));
  await userEvent.type(screen.getByLabelText(/supplier code/i), SUPPLIER_CODE);
  await userEvent.click(screen.getByRole('button', { name: /find my supplier/i }));
  await screen.findByTestId('supplier-preview');
}

beforeEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
  window.history.pushState({}, '', '/');
  useToastStore.setState({ toasts: [] });
});

afterEach(() => {
  resetAuth(null);
  window.history.pushState({}, '', '/');
  window.dispatchEvent(new PopStateEvent('popstate', { state: window.history.state }));
  cleanup();
  api.defaults.adapter = undefined;
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// T2 / T5 / T13 — code entry happy path and payload contracts
// ---------------------------------------------------------------------------

describe('DC-12R1-MVP-L1-J1-H2-A-R1: dual-entry self-join', () => {
  it('T2: code lookup -> preview identity -> explicit confirm -> auto-bind via join_intent', async () => {
    const { log, bodies, headers } = installAdapter({
      'POST /wholesalers/lookup-code': (c) => ok(c, PREVIEW_FOUND),
      'POST /retailers/register': (c) => ok(c, REGISTERED, 201),
    });

    await goViaCodeEntry();

    // Preview shows the safe identity fields BEFORE any commitment.
    expect(screen.getByTestId('preview-name')).toHaveTextContent('Alpha Wholesale');
    expect(screen.getByText(/12 Supplier Avenue/i)).toBeVisible();
    expect(screen.getByText(/\+25\*+56/)).toBeVisible();

    // Explicit confirmation is required to reach the register form.
    await userEvent.click(screen.getByRole('button', { name: /confirm joining this supplier/i }));

    await userEvent.type(screen.getByLabelText(/^phone/i), '+255700099901');
    await userEvent.type(screen.getByLabelText(/^email/i), 'duka@example.com');
    await userEvent.click(screen.getByRole('button', { name: /complete registration/i }));

    await waitFor(() => expect(log).toContain('POST /retailers/register'));
    const body = bodies['POST /retailers/register'][0] as Record<string, unknown>;

    // T5/T13: exactly ONE entry credential; NEVER a client wholesaler_id.
    expect(body.join_intent).toBe(JOIN_INTENT);
    expect(body.invitation_code).toBeUndefined();
    expect(body.wholesaler_id).toBeUndefined();
    expect(body.email).toBe('duka@example.com');

    // R1: public calls carry an explicitly EMPTY Authorization.
    expect(headers['POST /wholesalers/lookup-code'][0]).toBe('');
    expect(headers['POST /retailers/register'][0]).toBe('');
  });

  it('T3: unknown supplier code -> neutral miss, zero register POSTs', async () => {
    const { log } = installAdapter({
      'POST /wholesalers/lookup-code': (c) => ok(c, { found: false }),
    });

    await renderAppAt('/retail/join');
    await userEvent.click(screen.getByRole('tab', { name: /supplier code/i }));
    await userEvent.type(screen.getByLabelText(/supplier code/i), 'WRONG99');
    await userEvent.click(screen.getByRole('button', { name: /find my supplier/i }));

    expect(await screen.findByRole('status')).toHaveTextContent(/could not find a supplier/i);
    expect(screen.queryByTestId('supplier-preview')).toBeNull();
    expect(screen.queryByRole('button', { name: /complete registration/i })).toBeNull();
    expect(log.filter((k) => k === 'POST /retailers/register')).toEqual([]);
  });

  it('T4/T13: tampered join_intent (server rejection) binds nothing, neutral copy only', async () => {
    const { log } = installAdapter({
      'POST /wholesalers/lookup-code': (c) => ok(c, PREVIEW_FOUND),
      'POST /retailers/register': (c) =>
        Promise.reject(
          httpError(c, 400, {
            success: false,
            error: { code: 'JOIN_INTENT_INVALID', message: 'SENTINEL tampered-xyz' },
          }),
        ),
    });

    await goViaCodeEntry();
    await userEvent.click(screen.getByRole('button', { name: /confirm joining this supplier/i }));
    await userEvent.type(screen.getByLabelText(/^phone/i), '+255700099901');
    await userEvent.type(screen.getByLabelText(/^email/i), 'duka@example.com');
    await userEvent.click(screen.getByRole('button', { name: /complete registration/i }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(
      'We could not complete your registration. Please check your details and try again.',
    );
    expect(document.body.textContent ?? '').not.toContain('tampered-xyz');
    // No portal handoff was produced (nothing bound).
    expect(screen.queryByRole('link', { name: /go to supplier portal sign in/i })).toBeNull();
    expect(useToastStore.getState().toasts).toEqual([]);
    expect(log.filter((k) => k === 'POST /retailers/register')).toHaveLength(1);
  });

  it('T7: double submit produces exactly ONE relationship POST', async () => {
    const { log } = installAdapter({
      'POST /wholesalers/lookup-code': (c) => ok(c, PREVIEW_FOUND),
      'POST /retailers/register': (c) =>
        new Promise((resolve) => setTimeout(() => resolve(ok(c, REGISTERED, 201)), 150)),
    });

    await goViaCodeEntry();
    await userEvent.click(screen.getByRole('button', { name: /confirm joining this supplier/i }));
    await userEvent.type(screen.getByLabelText(/^phone/i), '+255700099901');
    await userEvent.type(screen.getByLabelText(/^email/i), 'duka@example.com');
    const submit = screen.getByRole('button', { name: /complete registration/i });
    const form = submit.closest('form') as HTMLFormElement;

    // Two SYNCHRONOUS form submits in the same tick — this bypasses the
    // button's disabled state entirely, so ONLY the in-flight lock can
    // prevent the second POST.
    fireEvent.submit(form);
    fireEvent.submit(form);

    await waitFor(() =>
      expect(log.filter((k) => k === 'POST /retailers/register')).toHaveLength(1),
    );
    await screen.findByText(/registration complete/i);
    await new Promise((r) => setTimeout(r, 300));
    expect(log.filter((k) => k === 'POST /retailers/register')).toHaveLength(1);
  });

  it('T6: no-email submission on the JOIN page is blocked client-side (zero POSTs)', async () => {
    const { log } = installAdapter({
      'POST /wholesalers/lookup-code': (c) => ok(c, PREVIEW_FOUND),
      'POST /retailers/register': (c) => ok(c, REGISTERED, 201),
    });

    await goViaCodeEntry();
    await userEvent.click(screen.getByRole('button', { name: /confirm joining this supplier/i }));
    await userEvent.type(screen.getByLabelText(/^phone/i), '+255700099901');
    // Email intentionally left empty — the RED path.
    await userEvent.click(screen.getByRole('button', { name: /complete registration/i }));

    expect(await screen.findByText(/email is required/i)).toBeVisible();
    expect(log).toEqual(['POST /wholesalers/lookup-code']);
    expect(screen.getByRole('button', { name: /complete registration/i })).toBeVisible();
  });

  it('T9: stale contextual session never leaks into the public join flow', async () => {
    resetAuth(userWith(['client:orders:read'], ['retailer_operator']));
    const { log, headers } = installAdapter({
      'POST /wholesalers/lookup-code': (c) => ok(c, PREVIEW_FOUND),
      'POST /retailers/register': (c) => ok(c, REGISTERED, 201),
    });

    await goViaCodeEntry();
    await userEvent.click(screen.getByRole('button', { name: /confirm joining this supplier/i }));
    await userEvent.type(screen.getByLabelText(/^phone/i), '+255700099901');
    await userEvent.type(screen.getByLabelText(/^email/i), 'duka@example.com');
    await userEvent.click(screen.getByRole('button', { name: /complete registration/i }));

    await screen.findByText(/registration complete/i);
    expect(headers['POST /wholesalers/lookup-code'][0]).toBe('');
    expect(headers['POST /retailers/register'][0]).toBe('');
    expect(log.filter((k) => k.includes('/auth/refresh'))).toEqual([]);
    const s = useAuthStore.getState();
    expect(s.accessToken).toBe('access-token-r1');
    expect(s.user?.id).toBe('user-0001');
  });

  it('T12: register hands off to the SERVER-VERIFIED portal login URL on the real router', async () => {
    installAdapter({
      'POST /wholesalers/lookup-code': (c) => ok(c, PREVIEW_FOUND),
      'POST /retailers/register': (c) => ok(c, REGISTERED, 201),
    });

    await goViaCodeEntry();
    await userEvent.click(screen.getByRole('button', { name: /confirm joining this supplier/i }));
    await userEvent.type(screen.getByLabelText(/^phone/i), '+255700099901');
    await userEvent.type(screen.getByLabelText(/^email/i), 'duka@example.com');
    await userEvent.click(screen.getByRole('button', { name: /complete registration/i }));

    // The portal code comes from the register RESPONSE (server context).
    const link = await screen.findByRole('link', { name: /go to supplier portal sign in/i });
    expect(link).toHaveAttribute('href', `/retail/login?w=${SUPPLIER_CODE}`);
    await userEvent.click(link);

    await waitFor(() => expect(window.location.pathname).toBe('/retail/login'));
    expect(window.location.search).toBe(`?w=${SUPPLIER_CODE}`);
    // Real ClientLoginPage mounted with a VALID portal (login form visible).
    await waitFor(() => expect(screen.getByLabelText(/email/i)).toBeVisible());
  });

  it('entry A on /retail/join: pasted invitation LINK re-uses POST /invitations/lookup', async () => {
    const { log, bodies } = installAdapter({
      'POST /invitations/lookup': (c) =>
        ok(c, {
          code: 'H2A-CODE-7f3k9Q2x',
          usable: true,
          reason: null,
          status: 'active',
          wholesaler_id: 'ws-0001',
          wholesaler_name: 'Alpha Wholesale',
          wholesaler_code: SUPPLIER_CODE,
          expires_at: '2026-09-21T00:00:00.000Z',
        }),
      'POST /retailers/register': (c) => ok(c, REGISTERED, 201),
    });

    await renderAppAt('/retail/join');
    await userEvent.type(
      screen.getByLabelText(/invitation link or code/i),
      'http://localhost:3000/invite#code=H2A-CODE-7f3k9Q2x',
    );
    await userEvent.click(screen.getByRole('button', { name: /continue with invitation/i }));

    await waitFor(() => expect(log).toContain('POST /invitations/lookup'));
    expect(bodies['POST /invitations/lookup'][0]).toEqual({ code: 'H2A-CODE-7f3k9Q2x' });
    // Fragment credential accepted ONLY from the fragment — the URL query
    // was never involved.
    expect(log.some((k) => k.includes('?'))).toBe(false);

    await userEvent.type(await screen.findByLabelText(/^phone/i), '+255700099901');
    await userEvent.type(screen.getByLabelText(/^email/i), 'duka@example.com');
    await userEvent.click(screen.getByRole('button', { name: /complete registration/i }));
    await waitFor(() => expect(log).toContain('POST /retailers/register'));
    const body = bodies['POST /retailers/register'][0] as Record<string, unknown>;
    expect(body.invitation_code).toBe('H2A-CODE-7f3k9Q2x');
    expect(body.join_intent).toBeUndefined();
  });

  it('T14: Web Share unavailable -> safe copy fallback (no share-internals echo)', async () => {
    resetAuth(userWith(['invitations:create']));
    // navigator.share is undefined in jsdom — the unsupported path.
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });

    installAdapter({
      'POST /invitations': (c) =>
        ok(
          c,
          {
            code: 'H2A-CODE-7f3k9Q2x',
            status: 'active',
            wholesaler_id: 'ws-0001',
            retailer_phone: null,
            expires_at: null,
            created_at: '2026-08-21T00:00:00.000Z',
          },
          201,
        ),
    });

    await renderAppAt('/retailers/invite');
    await userEvent.click(await screen.findByRole('button', { name: /create invitation/i }));
    await screen.findByRole('status');

    await userEvent.click(screen.getByRole('button', { name: /share invite/i }));
    expect(await screen.findByTestId('share-fallback')).toHaveTextContent(/copy buttons/i);

    // Fallback copy still works and stays fragment-only.
    await userEvent.click(screen.getByRole('button', { name: /copy secure invite link/i }));
    const link = writeText.mock.calls[0][0] as string;
    expect(link).toBe(`${window.location.origin}/invite#code=H2A-CODE-7f3k9Q2x`);
    expect(link).not.toMatch(/\/invite\//);
    expect(link).not.toContain('wa.me');
    expect(link).not.toContain('?');
  });

  it('F4: no rendered link is EVER bare /retail/login; failed/miss lookups render no portal link', async () => {
    const bareLinks = () =>
      Array.from(document.querySelectorAll('a[href="/retail/login"]'));
    const portalLinks = () =>
      Array.from(document.querySelectorAll('a[href^="/retail/login"]'));

    installAdapter({
      'POST /wholesalers/lookup-code': (c) => ok(c, PREVIEW_FOUND),
    });

    // Entry state (both tabs): no portal link at all.
    await renderAppAt('/retail/join');
    expect(bareLinks()).toEqual([]);
    expect(portalLinks()).toEqual([]);
    await userEvent.click(screen.getByRole('tab', { name: /supplier code/i }));
    expect(bareLinks()).toEqual([]);

    // Failed lookup -> no portal link (neutral miss).
    const missAdapter = installAdapter({
      'POST /wholesalers/lookup-code': (c) => ok(c, { found: false }),
    });
    expect(missAdapter).toBeDefined();
    await userEvent.type(screen.getByLabelText(/supplier code/i), 'WRONG99');
    await userEvent.click(screen.getByRole('button', { name: /find my supplier/i }));
    expect(await screen.findByRole('status')).toHaveTextContent(/could not find/i);
    expect(bareLinks()).toEqual([]);
    expect(portalLinks()).toEqual([]);

    // Successful lookup -> the ONLY portal link carries the verified code.
    const okAdapter = installAdapter({
      'POST /wholesalers/lookup-code': (c) => ok(c, PREVIEW_FOUND),
    });
    expect(okAdapter).toBeDefined();
    const input = screen.getByLabelText(/supplier code/i);
    await userEvent.clear(input);
    await userEvent.type(input, SUPPLIER_CODE);
    await userEvent.click(screen.getByRole('button', { name: /find my supplier/i }));
    await screen.findByTestId('supplier-preview');
    expect(bareLinks()).toEqual([]);
    const links = portalLinks();
    expect(links).toHaveLength(1);
    expect(links[0].getAttribute('href')).toBe(`/retail/login?w=${SUPPLIER_CODE}`);
  });

  it('Customers page shows join source and deactivates (permission-gated)', async () => {
    resetAuth(userWith(['retailers:read', 'retailers:deactivate', 'invitations:create']));
    let status = 'active';
    const { log } = installAdapter({
      'GET /retailers': (c) =>
        ok(c, {
          items: [
            {
              retailer: { id: 'ret-7', phone: '+255700000007', name: 'Invite Duka', email: 'a@example.com', address: null },
              binding_status: status,
              bound_at: '2026-08-01T00:00:00.000Z',
              join_source: 'invite',
            },
            {
              retailer: { id: 'ret-8', phone: '+255700000008', name: 'Code Duka', email: 'b@example.com', address: null },
              binding_status: status,
              bound_at: '2026-08-02T00:00:00.000Z',
              join_source: 'code',
            },
          ],
          pagination: { page: 1, size: 20, total: 2, pages: 1 },
        }),
      'POST /retailers/ret-7/deactivate': (c) => {
        status = 'inactive';
        return ok(c, { id: 'bind-7', status: 'inactive' });
      },
    });

    await renderAppAt('/retailers');
    expect(await screen.findByText('Invite Duka')).toBeVisible();
    expect(screen.getByText('Invite link')).toBeVisible();
    expect(screen.getByText('Supplier code')).toBeVisible();

    const buttons = screen.getAllByRole('button', { name: /deactivate/i });
    expect(buttons).toHaveLength(2); // both rows active + permission held
    await userEvent.click(buttons[0]);

    await waitFor(() =>
      expect(log).toContain('POST /retailers/ret-7/deactivate'),
    );
  });

  it('Customers page hides deactivate without the permission (fail closed)', async () => {
    resetAuth(userWith(['retailers:read']));
    installAdapter({
      'GET /retailers': (c) =>
        ok(c, {
          items: [
            {
              retailer: { id: 'ret-7', phone: '+255700000007', name: 'Invite Duka', email: 'a@example.com', address: null },
              binding_status: 'active',
              bound_at: '2026-08-01T00:00:00.000Z',
              join_source: 'invite',
            },
          ],
          pagination: { page: 1, size: 20, total: 1, pages: 1 },
        }),
    });

    await renderAppAt('/retailers');
    await screen.findByText('Invite Duka');
    expect(screen.queryByRole('button', { name: /deactivate/i })).toBeNull();
  });
});
