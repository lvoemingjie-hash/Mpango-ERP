import axios, { AxiosError, type AxiosAdapter, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { useEffect } from 'react';
import { api } from '@/services/api';
import { authService } from '@/services/authService';
import { useAuthStore } from '@/stores/authStore';
import { useToastStore } from '@/stores/toastStore';
import { LoginPage } from '@/pages/auth/LoginPage';
import { ClientLoginPage } from '@/pages/client/ClientLoginPage';
import { WorkspaceSelectorPage } from '@/pages/auth/WorkspaceSelectorPage';
import { OrderListPage } from '@/pages/orders/OrderListPage';
import type { CurrentUserData, TokenData } from '@/types/auth';

function deferred<T>() {
  let settled = false;
  let resolve!: (v: T) => void; let reject!: (e: unknown) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = value => { settled = true; yes(value); };
    reject = error => { settled = true; no(error); };
  });
  return { promise, resolve, reject, get settled() { return settled; } };
}
const tokens = (id: string): TokenData => ({ access_token: `${id}-access`, refresh_token: `${id}-refresh`, token_type: 'bearer', user_id: id, tenant_id: id, tenant_schema: `t_${id}`, roles: ['admin'] });
const person = (id: string): CurrentUserData => ({ id, email: null, full_name: id, tenant_id: id, tenant_schema: `t_${id}`, roles: ['admin'], permissions: ['orders:read', 'payments:create'] });
const ok = (config: InternalAxiosRequestConfig, data: unknown): AxiosResponse => ({ config, data: { success: true, data }, status: 200, statusText: 'OK', headers: {} });
const denied = (config: InternalAxiosRequestConfig, status = 401) => new AxiosError('controlled', AxiosError.ERR_BAD_REQUEST, config, undefined, { ...ok(config, {}), status });
const tenant = { id: 'A', code: 'A', name: 'Alpha Workspace' };
const identity = () => ({ ...tokens('identity'), available_tenants: [tenant] });
const order = { id: 'old-order', wholesaler_id: 'A', retailer_id: 'R', retailer_name: 'Retailer', status: 'confirmed', total_amount: '100.00', currency: 'KES', items: [], notes: null, created_by: null, created_at: '2026-10-27T00:00:00Z', updated_at: '2026-10-27T00:00:00Z' };
type Handler = (c: InternalAxiosRequestConfig) => Promise<AxiosResponse> | AxiosResponse;
let handlers: Record<string, Handler>; let calls: string[]; let navigations: string[];
let finishParked: Array<() => void>;
const originalApi = api.defaults.adapter; const originalGlobal = axios.defaults.adapter;
function establish(id: string) { useAuthStore.getState().retailerLogin(tokens(id), person(id), id); }
function snapshot() {
  const s = useAuthStore.getState();
  return { accessToken: s.accessToken, refreshToken: s.refreshToken, user: s.user, tenantCode: s.tenantCode, retailerPortalCode: s.retailerPortalCode, generation: s.sessionGeneration };
}
function LocationObserver() {
  const location = useLocation();
  useEffect(() => { navigations.push(location.pathname + location.search); }, [location]);
  return null;
}
function mount(path: string, state?: unknown) {
  return render(<MemoryRouter initialEntries={[{ pathname: path.split('?')[0], search: path.includes('?') ? '?' + path.split('?')[1] : '', state }]}>
    <LocationObserver /><Routes>
      <Route path="/login" element={<LoginPage />} /><Route path="/retail/login" element={<ClientLoginPage />} />
      <Route path="/select-workspace" element={<WorkspaceSelectorPage />} /><Route path="/orders" element={<OrderListPage />} />
      <Route path="*" element={<div>destination</div>} />
    </Routes></MemoryRouter>);
}
async function submit() {
  fireEvent.change(await screen.findByLabelText('Email'), { target: { value: 'owner@example.com' } });
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'controlled-input' } });
  fireEvent.click(screen.getByRole('button', { name: 'Sign In' }));
}
function park(path: string) {
  const entered = deferred<InternalAxiosRequestConfig>(); const result = deferred<AxiosResponse>();
  let config: InternalAxiosRequestConfig | undefined;
  handlers[path] = c => { config = c; entered.resolve(c); return result.promise; };
  finishParked.push(() => { if (config && !result.settled) result.reject(denied(config)); });
  return { entered, result };
}
async function releaseRejected(gate: ReturnType<typeof park>, status = 401) {
  const config = await gate.entered.promise;
  // Settle the actual request and let React drain its caller updates. An
  // interceptor registered after adapter entry cannot observe that request.
  await act(async () => { gate.result.reject(denied(config, status)); });
}
beforeEach(() => {
  handlers = {}; calls = []; navigations = []; finishParked = [];
  useAuthStore.getState().logout(); useToastStore.setState({ toasts: [] });
  const adapter: AxiosAdapter = async c => {
    const path = c.url || ''; calls.push(path);
    if (handlers[path]) return handlers[path](c);
    if (path === '/auth/login') return ok(c, identity());
    if (path === '/auth/select-tenant') return ok(c, tokens('A'));
    if (path === '/auth/me') return ok(c, person('A'));
    if (path === '/orders') return ok(c, { items: [], pagination: { page: 1, size: 20, total: 0, pages: 0 } });
    throw denied(c, 404);
  };
  api.defaults.adapter = adapter; axios.defaults.adapter = adapter;
  vi.spyOn(console, 'debug').mockImplementation(() => {});
});
afterEach(async () => {
  await act(async () => { finishParked.forEach(finish => finish()); });
  cleanup(); useAuthStore.getState().logout(); api.defaults.adapter = originalApi; axios.defaults.adapter = originalGlobal; vi.restoreAllMocks();
});

describe('real page attempt and caller boundaries', () => {
  it('BASE_COUNTER old owner cancellation cannot clear B', async () => {
    const gate = park('/auth/select-tenant'); mount('/login'); await submit(); await gate.entered.promise;
    act(() => establish('B')); const before = snapshot(); await releaseRejected(gate);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Sign In' })).not.toBeDisabled());
    expect(snapshot(), 'R2_STALE_LOGIN_CLEARED_NEW_SESSION').toEqual(before);
    expect(navigations.filter(n => n === '/')).toEqual([]);
  });
  it.each(['select', 'me'] as const)('old owner %s success/error cannot start next stage or navigate', async stage => {
    const gate = park(stage === 'select' ? '/auth/select-tenant' : '/auth/me'); mount('/login'); await submit();
    const config = await gate.entered.promise; act(() => establish('B')); const before = snapshot();
    await act(async () => { gate.result.resolve(ok(config, stage === 'select' ? tokens('A') : person('A'))); });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Sign In' })).not.toBeDisabled());
    expect(snapshot()).toEqual(before); expect(navigations.filter(n => n === '/')).toEqual([]);
    if (stage === 'select') expect(calls.filter(p => p === '/auth/me')).toEqual([]);
  });
  it('a newer authentication intent wins before either intent changes generation', async () => {
    const first = park('/auth/login'); const a = mount('/login'); await submit(); const ca = await first.entered.promise;
    a.unmount(); const second = park('/auth/login'); mount('/login'); await submit(); const cb = await second.entered.promise;
    const generation = useAuthStore.getState().sessionGeneration;
    await act(async () => { first.result.resolve(ok(ca, identity())); });
    expect(calls.filter(p => p === '/auth/select-tenant'), 'R2_OLD_INTENT_STARTED_NEXT_STAGE').toEqual([]);
    expect(useAuthStore.getState().sessionGeneration).toBe(generation);
    await act(async () => { second.result.resolve(ok(cb, identity())); });
    await waitFor(() => expect(useAuthStore.getState().accessToken).toBe('A-access'));
  });
  it.each(['success', 'error'] as const)('late retailer %s leaves B and portal unchanged', async result => {
    const gate = park('/client/auth/login'); mount('/retail/login?w=A'); await submit(); const config = await gate.entered.promise;
    act(() => establish('B')); const before = snapshot();
    if (result === 'error') await releaseRejected(gate);
    else await act(async () => { gate.result.resolve(ok(config, { tokens: tokens('A'), user: person('A'), wholesaler: { code: 'A' } })); });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Sign In' })).not.toBeDisabled());
    expect(snapshot()).toEqual(before); expect(navigations.filter(n => n === '/client')).toEqual([]);
  });
  it('BASE_COUNTER owned retailer failure invalidates old refresh and queued work', async () => {
    establish('A'); const refresh = park('/api/v1/auth/refresh');
    handlers['/old'] = c => Promise.reject(denied(c));
    const pending = api.get('/old').catch(e => e); const config = await refresh.entered.promise;
    const queuedEntered = deferred<void>();
    handlers['/queued'] = c => { queuedEntered.resolve(); return Promise.reject(denied(c)); };
    let queued!: Promise<unknown>;
    await act(async () => { queued = api.get('/queued').catch(e => e); await queuedEntered.promise; });
    handlers['/client/auth/login'] = c => Promise.reject(denied(c)); mount('/retail/login?w=B'); await submit();
    await waitFor(() => expect(screen.getByText('Invalid credentials')).toBeVisible());
    expect(axios.isCancel(await queued), 'R2_RETAILER_FAILURE_DID_NOT_CANCEL_QUEUED_WORK').toBe(true);
    await act(async () => { refresh.result.resolve(ok(config, tokens('A-fresh'))); await pending; });
    expect(useAuthStore.getState().accessToken, 'R2_RETAILER_FAILURE_RESTORED_OLD_TOKEN').toBeNull();
    expect(useAuthStore.getState().retailerPortalCode).toBe('B');
    expect(calls.filter(p => p === '/old')).toHaveLength(1);
    expect(calls.filter(p => p === '/queued')).toHaveLength(1);
  });
  it.each(['/retail/login?w=bad!', '/retail/login?w=A'])('invalid portal/form preserves the established session: %s', async path => {
    establish('B'); const before = snapshot(); mount(path);
    if (path.endsWith('A')) fireEvent.click(screen.getByRole('button', { name: 'Sign In' }));
    await act(async () => {});
    expect(calls).toEqual([]); expect(snapshot()).toEqual(before);
  });
  it.each(['success', 'error'] as const)('workspace late %s cannot replace a new login', async result => {
    useAuthStore.getState().beginWorkspaceSelection(tokens('identity'));
    const gate = park('/auth/select-tenant'); mount('/select-workspace', { availableTenants: [tenant] });
    fireEvent.click(screen.getByRole('button', { name: /Alpha Workspace/ })); const config = await gate.entered.promise;
    act(() => establish('B')); const before = snapshot();
    if (result === 'error') await releaseRejected(gate);
    else await act(async () => { gate.result.resolve(ok(config, tokens('A'))); });
    expect(snapshot()).toEqual(before); expect(calls.filter(p => p === '/auth/me')).toEqual([]);
    expect(navigations.filter(n => n === '/')).toEqual([]);
  });
  it('workspace signout fences its unfinished selection', async () => {
    useAuthStore.getState().beginWorkspaceSelection(tokens('identity'));
    const gate = park('/auth/select-tenant'); mount('/select-workspace', { availableTenants: [tenant] });
    fireEvent.click(screen.getByRole('button', { name: /Alpha Workspace/ })); const config = await gate.entered.promise;
    fireEvent.click(screen.getByText('Sign out and try another account')); const before = snapshot();
    await act(async () => { gate.result.resolve(ok(config, tokens('A'))); });
    expect(snapshot()).toEqual(before); expect(navigations[navigations.length - 1]).toBe('/login');
  });
  it('BASE_COUNTER old order fallback cannot emit toast for B', async () => {
    establish('A'); const gate = park('/orders/old-order'); mount('/orders?collect=old-order'); await gate.entered.promise;
    act(() => establish('B')); const before = snapshot(); await releaseRejected(gate, 404);
    expect(useToastStore.getState().toasts, 'R2_OLD_ORDER_TOAST_LEAK').toEqual([]); expect(snapshot()).toEqual(before);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
  it('old payment history cancellation cannot toast or open a modal', async () => {
    establish('A'); handlers['/orders'] = c => ok(c, { items: [order], pagination: { page: 1, size: 20, total: 1, pages: 1 } });
    const gate = park('/payments?order_id=old-order&page=1&size=100'); mount('/orders');
    fireEvent.click(await screen.findByRole('button', { name: 'Record Payment' })); await gate.entered.promise;
    act(() => establish('B')); await releaseRejected(gate, 404);
    expect(useToastStore.getState().toasts).toEqual([]); expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
  it.each(['fallback', 'history'] as const)('current %s real failure still produces the business toast', async mode => {
    establish('A');
    if (mode === 'history') handlers['/orders'] = c => ok(c, { items: [order], pagination: { page: 1, size: 20, total: 1, pages: 1 } });
    const gate = park(mode === 'fallback' ? '/orders/old-order' : '/payments?order_id=old-order&page=1&size=100');
    mount(mode === 'fallback' ? '/orders?collect=old-order' : '/orders');
    if (mode === 'history') fireEvent.click(await screen.findByRole('button', { name: 'Record Payment' }));
    await gate.entered.promise; await releaseRejected(gate, 404);
    await waitFor(() => expect(useToastStore.getState().toasts.some(t => t.title === (mode === 'fallback' ? 'Order Not Found' : 'Payment History Unavailable'))).toBe(true));
  });
  it.each(['fallback', 'history'] as const)('old %s success cannot open a modal or advance B navigation', async mode => {
    establish('A');
    if (mode === 'history') handlers['/orders'] = c => ok(c, { items: [order], pagination: { page: 1, size: 20, total: 1, pages: 1 } });
    const gate = park(mode === 'fallback' ? '/orders/old-order' : '/payments?order_id=old-order&page=1&size=100');
    mount(mode === 'fallback' ? '/orders?collect=old-order' : '/orders');
    if (mode === 'history') fireEvent.click(await screen.findByRole('button', { name: 'Record Payment' }));
    const config = await gate.entered.promise;
    act(() => establish('B')); const before = snapshot(); const routes = [...navigations];
    await act(async () => { gate.result.resolve(ok(config, mode === 'fallback' ? order : { items: [] })); });
    expect(snapshot()).toEqual(before); expect(navigations).toEqual(routes);
    expect(useToastStore.getState().toasts).toEqual([]);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    if (mode === 'fallback') expect(calls.filter(p => p.startsWith('/payments'))).toEqual([]);
  });
  it('authentication service refuses missing ownership before transport', async () => {
    // The cast models an untyped caller, not a production escape hatch.
    const randomBytes = crypto.getRandomValues(new Uint8Array(16));
    const oneTimeInput = Array.from(randomBytes, value => value.toString(16).padStart(2, '0')).join('');
    await expect(authService.login({ email: 'owner@example.com', password: oneTimeInput }, undefined as never)).rejects.toSatisfy(axios.isCancel);
    expect(calls).toEqual([]);
  });
  it('anonymous authentication intent is observable without any storage write', () => {
    // Establish absent storage before the measured action; keep fixture removal in the spy history.
    const writes = vi.spyOn(Storage.prototype, 'setItem');
    const removals = vi.spyOn(Storage.prototype, 'removeItem');
    const clears = vi.spyOn(Storage.prototype, 'clear');
    localStorage.removeItem('mpango-auth');
    expect(localStorage.getItem('mpango-auth')).toBeNull();
    const removalCount = removals.mock.calls.length;
    const before = useAuthStore.getState();
    const observed: number[] = [];
    const unsubscribe = useAuthStore.subscribe(state => observed.push(state.authAttemptSequence));
    try {
      const attempt = before.beginAuthAttempt();
      expect(writes.mock.calls.length, 'AUTH_INTENT_ANONYMOUS_STORAGE_WRITE').toBe(0);
      expect(removals).toHaveBeenCalledTimes(removalCount);
      expect(clears).not.toHaveBeenCalled();
      expect(localStorage.getItem('mpango-auth')).toBeNull();
      expect(useAuthStore.getState()).not.toBe(before);
      expect(attempt).toEqual({ generation: before.sessionGeneration, sequence: before.authAttemptSequence + 1 });
      expect(useAuthStore.getState().sessionGeneration).toBe(before.sessionGeneration);
      expect(observed).toEqual([attempt.sequence]);
      expect(useAuthStore.getState().ownsAuthAttempt(attempt)).toBe(true);
    } finally {
      unsubscribe();
    }
  });
  it('established authentication intent preserves storage bytes and supersedes its peer', () => {
    establish('B');
    const bytes = localStorage.getItem('mpango-auth');
    expect(bytes).not.toBeNull();
    const before = snapshot();
    const writes = vi.spyOn(Storage.prototype, 'setItem');
    const removals = vi.spyOn(Storage.prototype, 'removeItem');
    const clears = vi.spyOn(Storage.prototype, 'clear');
    const first = useAuthStore.getState().beginAuthAttempt();
    const second = useAuthStore.getState().beginAuthAttempt();
    expect(second).toEqual({ generation: first.generation, sequence: first.sequence + 1 });
    expect(useAuthStore.getState().ownsAuthAttempt(first)).toBe(false);
    expect(useAuthStore.getState().ownsAuthAttempt(second)).toBe(true);
    useAuthStore.getState().failAuthAttempt(first, 'A');
    expect(snapshot()).toEqual(before);
    expect(writes).not.toHaveBeenCalled();
    expect(removals).not.toHaveBeenCalled();
    expect(clears).not.toHaveBeenCalled();
    expect(localStorage.getItem('mpango-auth')).toBe(bytes);
  });
  it('real session transitions persist only the public DTO and invalidate old attempts', () => {
    const writes = vi.spyOn(Storage.prototype, 'setItem');
    const assertStored = () => {
      const stored = JSON.parse(localStorage.getItem('mpango-auth')!);
      const live = useAuthStore.getState();
      expect(stored).toEqual({ version: 0, state: {
        accessToken: live.accessToken, refreshToken: live.refreshToken, user: live.user,
        tenantCode: live.tenantCode, retailerPortalCode: live.retailerPortalCode,
      } });
      expect(Object.keys(stored.state).sort()).toEqual(['accessToken', 'refreshToken', 'retailerPortalCode', 'tenantCode', 'user']);
    };
    const anonymousAttempt = useAuthStore.getState().beginAuthAttempt();
    useAuthStore.getState().login(tokens('owner'), person('owner'), 'owner');
    expect(writes).toHaveBeenCalledTimes(1); assertStored();
    expect(useAuthStore.getState().ownsAuthAttempt(anonymousAttempt)).toBe(false);
    const ownerAttempt = useAuthStore.getState().beginAuthAttempt();
    establish('retailer');
    expect(writes).toHaveBeenCalledTimes(2); assertStored();
    expect(useAuthStore.getState().ownsAuthAttempt(ownerAttempt)).toBe(false);
    useAuthStore.getState().updateTokens(tokens('refreshed'));
    expect(writes).toHaveBeenCalledTimes(3); assertStored();
    const retailerAttempt = useAuthStore.getState().beginAuthAttempt();
    useAuthStore.getState().beginWorkspaceSelection(tokens('identity'));
    expect(writes).toHaveBeenCalledTimes(4); assertStored();
    expect(useAuthStore.getState().ownsAuthAttempt(retailerAttempt)).toBe(false);
    const workspaceAttempt = useAuthStore.getState().beginAuthAttempt();
    useAuthStore.getState().logout();
    expect(writes).toHaveBeenCalledTimes(5); assertStored();
    expect(useAuthStore.getState().ownsAuthAttempt(workspaceAttempt)).toBe(false);
    expect(snapshot().accessToken).toBeNull();
  });
});
