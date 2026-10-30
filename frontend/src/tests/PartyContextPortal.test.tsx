import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { AxiosError, type InternalAxiosRequestConfig } from 'axios';
import { ClientLayout } from '@/components/layout/ClientLayout';
import { getClientPortalContext, getCashierReviewContext } from '@/services/partyContextService';
import { useAuthStore } from '@/stores/authStore';
import { useToastStore } from '@/stores/toastStore';
import { api } from '@/services/api';
import type { ClientPortalContext } from '@/types/partyContext';

vi.mock('@/services/partyContextService', () => ({ getClientPortalContext: vi.fn(), getCashierReviewContext: vi.fn() }));
function context(): ClientPortalContext {
  const user = useAuthStore.getState().user!;
  return { context: { user_id: user.id, tenant_id: user.tenant_id! },
    supplier: { id: user.tenant_id!, code: 'CURRENT', name: 'Current supplier', name_resolution: 'RESOLVED' },
    retailer: { id: 'retailer', name: 'Current retailer', name_resolution: 'RESOLVED' },
    binding: { id: 'active-binding', status: 'active' }, observed_at: '2026-10-30T00:00:00Z' };
}
const response = (data: ClientPortalContext) => ({ success: true, data, timestamp: data.observed_at });
function mount() { return render(<MemoryRouter initialEntries={['/client/orders']}><Routes>
  <Route element={<ClientLayout />}><Route path="/client/orders" element={<p>Protected child remains mounted</p>} /></Route>
</Routes></MemoryRouter>); }
function deferred<T>() {
  let resolve!: (value: T) => void; let reject!: (error: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject };
}
const adapterBefore = api.defaults.adapter;
beforeEach(() => {
  vi.resetAllMocks(); sessionStorage.clear(); useToastStore.setState({ toasts: [] });
  useAuthStore.setState({ accessToken: 'synthetic-session', sessionGeneration: 0, retailerPortalCode: 'CACHED-HINT', tenantCode: 'CACHED-HINT',
    user: { id: 'client', tenant_id: 'tenant', tenant_schema: 't_test', full_name: 'Private login name', email: null, roles: ['retailer_operator'], permissions: ['client:orders:read'] } });
  vi.mocked(getClientPortalContext).mockImplementation(async () => response(context()));
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); api.defaults.adapter = adapterBefore; });

describe('Portal current commercial identity is local display, not a route gate', () => {
  it('shows current supplier/retailer separately from personal login and saved portal hints', async () => {
    mount(); await screen.findByText('Supplier: Current supplier · CURRENT');
    expect(screen.getByText('Retailer: Current retailer')).toBeInTheDocument();
    expect(screen.getByText(/Saved portal hint: CACHED-HINT.*Signed in as Private login name/)).toBeInTheDocument();
    expect(screen.getByText('Protected child remains mounted')).toBeInTheDocument();
    expect(getCashierReviewContext).not.toHaveBeenCalled();
  });
  it.each(['literal names', 'missing names'])('uses resolution rather than an English blacklist for %s', async mode => {
    const c = context();
    c.supplier.name = mode === 'literal names' ? 'Supplier' : null;
    c.retailer.name = mode === 'literal names' ? 'Retailer' : null;
    if (mode === 'missing names') { c.supplier.name_resolution = 'MISSING'; c.retailer.name_resolution = 'MISSING'; }
    vi.mocked(getClientPortalContext).mockResolvedValue(response(c)); mount();
    await screen.findByText(mode === 'literal names' ? 'Supplier: Supplier · CURRENT' : 'Supplier: Supplier name not verified · CURRENT');
    expect(screen.getByText(mode === 'literal names' ? 'Retailer: Retailer' : 'Retailer: Retailer name not verified')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument(); expect(screen.getByText('Protected child remains mounted')).toBeInTheDocument();
  });
  it.each([403, 404, 409, 'network'])('refusal %s does not replace current identity with login/cache or block the child', async status => {
    vi.mocked(getClientPortalContext).mockRejectedValueOnce(status === 'network' ? new Error('offline') : { response: { status } });
    mount(); await screen.findByRole('alert');
    expect(screen.queryByText('Retailer: Private login name')).not.toBeInTheDocument();
    expect(screen.getByText('Protected child remains mounted')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Refresh business identity' }));
    await screen.findByText('Supplier: Current supplier · CURRENT'); expect(getClientPortalContext).toHaveBeenCalledTimes(2);
  });
  it.each(['user', 'tenant', 'supplier', 'binding', 'financial field'])('rejects %s mismatch in the self-only DTO', async field => {
    const c = context();
    if (field === 'user') c.context.user_id = 'someone-else';
    if (field === 'tenant') c.context.tenant_id = 'elsewhere';
    if (field === 'supplier') c.supplier.id = 'elsewhere';
    if (field === 'binding') c.binding.id = '';
    if (field === 'financial field') Object.assign(c, { money: { balance_due: '100.00' } });
    vi.mocked(getClientPortalContext).mockResolvedValue(response(c)); mount(); await screen.findByRole('alert');
    expect(screen.queryByText('Retailer: Current retailer')).not.toBeInTheDocument();
    expect(screen.getByText('Protected child remains mounted')).toBeInTheDocument();
  });
  it('a failed envelope cannot authenticate commercial names from its data', async () => {
    vi.mocked(getClientPortalContext).mockResolvedValue({ ...response(context()), success: false } as never);
    mount(); await screen.findByRole('alert'); expect(screen.queryByText('Retailer: Current retailer')).not.toBeInTheDocument();
    expect(screen.getByText('Protected child remains mounted')).toBeInTheDocument();
  });
  it.each(['account', 'tenant', 'portal', 'generation'])('clears an existing name before the new %s response arrives', async axis => {
    mount(); await screen.findByText('Supplier: Current supplier · CURRENT');
    const next = deferred<ReturnType<typeof response>>(); vi.mocked(getClientPortalContext).mockReturnValueOnce(next.promise);
    act(() => { const s = useAuthStore.getState(); useAuthStore.setState(axis === 'generation' ? { sessionGeneration: s.sessionGeneration + 1 }
      : axis === 'portal' ? { retailerPortalCode: 'NEW-HINT' }
      : { user: { ...s.user!, ...(axis === 'account' ? { id: 'new-client' } : { tenant_id: 'new-tenant' }) } }); });
    expect(screen.queryByText('Supplier: Current supplier · CURRENT')).not.toBeInTheDocument();
    expect(screen.getByText('Protected child remains mounted')).toBeInTheDocument();
    await act(async () => next.resolve(response(context()))); await screen.findByText('Supplier: Current supplier · CURRENT');
  });
  it.each(['success', 'failure'])('ignores late old-portal %s after a new identity and aborts the old request', async mode => {
    const old = deferred<ReturnType<typeof response>>(); const previous = context(); previous.supplier.name = 'Old supplier';
    vi.mocked(getClientPortalContext).mockReturnValueOnce(old.promise).mockImplementation(async () => {
      const fresh = context(); fresh.supplier.name = 'New supplier'; return response(fresh);
    });
    mount();
    await vi.waitFor(() => expect(getClientPortalContext).toHaveBeenCalledTimes(1));
    act(() => useAuthStore.setState({ retailerPortalCode: 'NEW' }));
    await screen.findByText('Supplier: New supplier · CURRENT');
    expect(vi.mocked(getClientPortalContext).mock.calls[0][0]?.aborted).toBe(true);
    await act(async () => { if (mode === 'success') old.resolve(response(previous)); else old.reject({ response: { status: 403 } }); });
    expect(screen.queryByText(/Old supplier/)).not.toBeInTheDocument(); expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});

describe('Original API transport ownership', () => {
  it('encodes only the selected declaration id and uses the exact nonfinancial self endpoint', async () => {
    const service = await vi.importActual<typeof import('@/services/partyContextService')>('@/services/partyContextService');
    const spy = vi.spyOn(api, 'get').mockResolvedValue({ data: { success: true, data: {} } } as never);
    const controller = new AbortController();
    await service.getCashierReviewContext('id/with space?', controller.signal);
    await service.getClientPortalContext(controller.signal);
    expect(spy).toHaveBeenNthCalledWith(1, '/declarations/id%2Fwith%20space%3F/review-context', { signal: controller.signal });
    expect(spy).toHaveBeenNthCalledWith(2, '/client/auth/context', { signal: controller.signal });
    expect(spy).toHaveBeenCalledTimes(2);
  });
  it.each([403, 409])('original interceptor does not toast or refresh authority for canceled old %s', async status => {
    const service = await vi.importActual<typeof import('@/services/partyContextService')>('@/services/partyContextService');
    let reject!: (error: unknown) => void; let config!: InternalAxiosRequestConfig;
    api.defaults.adapter = c => new Promise((_resolve, no) => { config = c; reject = no; });
    const controller = new AbortController();
    const pending = service.getCashierReviewContext('old', controller.signal).catch(e => e);
    await vi.waitFor(() => expect(reject).toBeTypeOf('function'));
    controller.abort();
    reject(new AxiosError('old response', 'ERR_BAD_REQUEST', config, undefined, {
      status, statusText: 'Refused', config, headers: {}, data: { error: { code: 'SYNTHETIC_OLD_ERROR', message: 'Old view error' } },
    }));
    await pending;
    expect(useToastStore.getState().toasts).toEqual([]);
    expect(useAuthStore.getState().user?.permissions).toEqual(['client:orders:read']);
  });
});
