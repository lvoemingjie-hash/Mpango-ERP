/**
 * PW1-R4-B4 — Retailer permission context hydration closure (frontend).
 *
 * Runs against the REAL <App /> router tree (real AppRouter, real
 * RetailerPermissionRoute guards, real pages). The login HTTP layer is
 * mocked at the authService boundary with REAL-shaped RetailerLoginResponse
 * payloads (including the new server-derived ``user.permissions``);
 * business GETs are served by a permissive recording axios adapter so the
 * guarded pages can mount.
 *
 * Mandatory coverage:
 *   T1  real RetailerLoginResponse writes ``permissions`` into the auth
 *       store verbatim (exact six client:* codes) after portal login
 *   T2  no permission data in the URL; no console error carrying
 *       permission strings (no URL/log leakage)
 *   T3  real AppRouter admits a permission-holding user into the
 *       declaration route (/client/orders/:id/declare) and the print
 *       route (/client/orders/:id/print) — the page mounts and the guard
 *       does NOT navigate away
 *   T4  a permission-EMPTY user is redirected off BOTH routes by
 *       RetailerPermissionRoute (fail closed; the frontend never
 *       auto-fills the six permissions)
 *   T5  updateTokens (the exact store action the refresh interceptor
 *       calls) preserves the user permission context
 *
 * Mutation REDs (scripted, captured as task evidence, not runtime
 * switches): removing ``permissions`` from the response, or restoring
 * ``permissions: []`` in ClientLoginPage, must turn T1 RED.
 */
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios';
import { render, screen, waitFor, cleanup, act, fireEvent } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import { App } from '@/App';
import { api } from '@/services/api';
import { authService } from '@/services/authService';
import { ClientLoginPage } from '@/pages/client/ClientLoginPage';
import { useAuthStore } from '@/stores/authStore';

vi.mock('@/services/authService', () => ({
  authService: { retailerLogin: vi.fn() },
}));

// ---------------------------------------------------------------------------
// Real-shaped fixtures
// ---------------------------------------------------------------------------
const SIX_PERMISSIONS = [
  'client:catalog:read',
  'client:finance:read',
  'client:orders:create',
  'client:orders:read',
  'client:payments:declare',
  'client:payments:read',
];

const LOGIN_RESPONSE = {
  success: true,
  data: {
    tokens: {
      access_token: 'ctx-access-token',
      refresh_token: 'ctx-refresh-token',
      token_type: 'bearer',
      user_id: '11111111-1111-1111-1111-111111111111',
      tenant_id: '22222222-2222-2222-2222-222222222222',
      tenant_schema: 't_22222222222222222222222222222222',
      roles: ['retailer_operator'],
    },
    user: {
      id: '11111111-1111-1111-1111-111111111111',
      email: 'retailer@b4.dev',
      full_name: 'PW1-R4-B4 Retailer',
      permissions: [...SIX_PERMISSIONS],
    },
    retailer: { id: '33333333-3333-3333-3333-333333333333', name: 'B4 Retailer' },
    wholesaler: { id: '22222222-2222-2222-2222-222222222222', code: 'PW1R4B4', name: 'B4 WS' },
  },
  timestamp: '2026-08-16T00:00:00.000Z',
};

function ok<T>(config: InternalAxiosRequestConfig, data: T): AxiosResponse<T> {
  return { data, status: 200, statusText: 'OK', headers: {}, config };
}

beforeEach(() => {
  window.localStorage.clear();
  vi.mocked(authService.retailerLogin).mockReset();
  // Permissive business-GET adapter (guarded pages may fetch on mount).
  api.defaults.adapter = (async (config: InternalAxiosRequestConfig) =>
    ok(config, { success: true, data: { items: [], total: 0 }, timestamp: '2026-08-16T00:00:00.000Z' })) as AxiosAdapter;
  useAuthStore.setState({
    accessToken: null,
    refreshToken: null,
    user: null,
    tenantCode: null,
    retailerPortalCode: null,
  });
});

afterEach(() => {
  cleanup();
  window.history.pushState({}, '', '/');
  act(() => {
    window.dispatchEvent(new PopStateEvent('popstate', { state: window.history.state }));
  });
  useAuthStore.setState({
    accessToken: null,
    refreshToken: null,
    user: null,
    tenantCode: null,
    retailerPortalCode: null,
  });
});

function renderAppAt(path: string) {
  // The AppRouter's browser router is a module-level singleton created at
  // location '/': a retailer-seeded FIRST mount at '/' redirects to
  // '/client' before the target sync lands. Pre-warm the subscription at
  // the retailer home first, then popstate-sync to the path under test
  // (same singleton-sync pattern as the PW1-R2 suite).
  window.history.pushState({}, '', '/client');
  const utils = render(<App />);
  act(() => {
    window.dispatchEvent(new PopStateEvent('popstate', { state: window.history.state }));
  });
  window.history.pushState({}, '', path);
  act(() => {
    window.dispatchEvent(new PopStateEvent('popstate', { state: window.history.state }));
  });
  return utils;
}

/** Seed an authenticated retailer session exactly as retailerLogin does. */
function seedSession(permissions: string[]) {
  const d = LOGIN_RESPONSE.data;
  useAuthStore.setState({
    accessToken: d.tokens.access_token,
    refreshToken: d.tokens.refresh_token,
    retailerPortalCode: d.wholesaler.code,
    user: {
      id: d.user.id,
      email: d.user.email,
      full_name: d.user.full_name,
      tenant_id: d.tokens.tenant_id,
      tenant_schema: d.tokens.tenant_schema,
      roles: d.tokens.roles,
      permissions,
    },
  });
}

function renderLoginPage(search: string) {
  return render(
    <MemoryRouter initialEntries={[`/retail/login${search}`]}>
      <Routes>
        <Route path="/retail/login" element={<ClientLoginPage />} />
        <Route path="/client" element={<div>Client Home</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

async function submitPortalLogin() {
  fireEvent.change(screen.getByLabelText(/email/i), {
    target: { value: LOGIN_RESPONSE.data.user.email! },
  });
  fireEvent.change(screen.getByLabelText(/password/i), {
    target: { value: 'pw1r4b4-portal' },
  });
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));
  });
}

describe('PW1-R4-B4: retailer permission context hydration', () => {
  it('T1: real login response writes the exact server-derived permissions into the store', async () => {
    vi.mocked(authService.retailerLogin).mockResolvedValueOnce({
      data: LOGIN_RESPONSE,
    } as never);
    renderLoginPage('?w=PW1R4B4');
    await submitPortalLogin();

    await waitFor(() => {
      expect(authService.retailerLogin).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(useAuthStore.getState().user).not.toBeNull();
    });
    const user = useAuthStore.getState().user!;
    expect(user.permissions).toEqual(SIX_PERMISSIONS);
    expect(user.permissions).toHaveLength(6);
  });

  it('T2: no permission data in URL and no permission strings in console errors', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.mocked(authService.retailerLogin).mockResolvedValueOnce({
      data: LOGIN_RESPONSE,
    } as never);
    renderLoginPage('?w=PW1R4B4');
    await submitPortalLogin();
    await waitFor(() => {
      expect(useAuthStore.getState().user).not.toBeNull();
    });
    expect(window.location.search).not.toContain('permission');
    expect(window.location.href).not.toContain('client:');
    for (const call of errorSpy.mock.calls) {
      const text = JSON.stringify(call);
      expect(text).not.toContain('client:');
    }
    errorSpy.mockRestore();
  });

  it('T3: real AppRouter admits a permission-holding user into declaration and print routes', async () => {
    seedSession([...SIX_PERMISSIONS]);
    renderAppAt('/client/orders/ORD1/declare');
    // The guarded page mounts (content renders) and the permission guard
    // does NOT navigate away from the declaration route.
    await waitFor(() => {
      expect(document.body.textContent!.length).toBeGreaterThan(0);
    });
    expect(window.location.pathname).toBe('/client/orders/ORD1/declare');

    cleanup();
    seedSession([...SIX_PERMISSIONS]);
    renderAppAt('/client/orders/ORD1/print');
    await waitFor(() => {
      expect(document.body.textContent!.length).toBeGreaterThan(0);
    });
    expect(window.location.pathname).toBe('/client/orders/ORD1/print');
  });

  it('T4: permission-EMPTY user is denied the declaration and print routes (fail closed)', async () => {
    // RetailerPermissionRoute fails closed with Navigate to /client — the
    // guarded page must NEVER mount for a permission-empty user.
    seedSession([]);
    renderAppAt('/client/orders/ORD1/declare');
    await waitFor(() => {
      expect(window.location.pathname).toBe('/client');
    });

    cleanup();
    seedSession([]);
    renderAppAt('/client/orders/ORD1/print');
    await waitFor(() => {
      expect(window.location.pathname).toBe('/client');
    });
  });

  it('T5: updateTokens (refresh path) preserves the user permission context', async () => {
    seedSession([...SIX_PERMISSIONS]);
    const { updateTokens } = useAuthStore.getState();
    act(() => {
      updateTokens({
        access_token: 'ctx-access-token-2',
        refresh_token: 'ctx-refresh-token-2',
      });
    });
    const state = useAuthStore.getState();
    expect(state.accessToken).toBe('ctx-access-token-2');
    expect(state.user!.permissions).toEqual(SIX_PERMISSIONS);
  });
});
