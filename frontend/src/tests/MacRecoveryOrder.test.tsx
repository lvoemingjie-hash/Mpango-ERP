import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { CreateOrderPage } from '@/pages/client/CreateOrderPage';
import { clientOrderService } from '@/services/clientOrderService';
import { useAuthStore } from '@/stores/authStore';

vi.mock('@/services/clientOrderService', () => ({ clientOrderService: { preview: vi.fn(), create: vi.fn(), replaceDraft: vi.fn(), getById: vi.fn() } }));
const quote = { quote_token: 'synthetic-unusable-quote', currency: 'KES', country: 'KE', total: '25.50', expires_at: 9999999999,
  lines: [{ sku_id: 'unit-one', sku_code: 'ONE', product_name: 'Synthetic juice', quantity: 1, unit: 'bottle', package_quantity: '1', display_label: 'bottle', unit_price: '25.50', subtotal: '25.50', revision: 1, source: 'BASE_PRICE' }] };
function page(replace = false) {
  return render(<MemoryRouter initialEntries={[{ pathname: '/client/orders/new', search: replace ? '?replace=old-draft' : '', state: { items: [
    { sellable_unit_id: 'unit-one', sku_code: 'ONE', name: 'Synthetic juice', quantity: 1, unit: 'bottle', package_quantity: 1 },
  ] } }]}><Routes><Route path="/client/orders/new" element={<CreateOrderPage />} /><Route path="/client/orders/:id" element={<p>Recovered draft</p>} /></Routes></MemoryRouter>);
}
beforeEach(() => {
  vi.resetAllMocks(); sessionStorage.clear(); localStorage.clear();
  useAuthStore.setState({ accessToken: 'synthetic-session', user: { id: 'actor-one', tenant_id: 'tenant-one', tenant_schema: 't_one', full_name: 'Synthetic', email: null, roles: ['retailer_operator'], permissions: ['client:orders:create','client:orders:read'] }, tenantCode: 'PORTAL', retailerPortalCode: 'PORTAL' });
  vi.mocked(clientOrderService.preview).mockResolvedValue({ data: { data: quote } } as never);
  vi.mocked(clientOrderService.getById).mockResolvedValue({ data: { data: { id: 'old-draft', status: 'CANCELLED', currency: 'KES' } } } as never);
});
afterEach(() => { vi.restoreAllMocks(); });

async function accept(replace = false) {
  fireEvent.click(screen.getByText('Review server quote'));
  await screen.findByText('Server total: KES 25.50');
  fireEvent.click(screen.getByText(replace ? 'Accept and replace old draft' : 'Accept these prices and create draft'));
}

describe('Mac ordinary order refresh recovery', () => {
  it('BASE B1: remount retains the accepted request instead of creating a second draft', async () => {
    const writes = new Map<string, unknown>();
    vi.mocked(clientOrderService.create).mockImplementation(async (body, key) => {
      if (!writes.has(key)) { writes.set(key, body); throw new Error('Synthetic response lost after server commit'); }
      return { data: { data: { id: 'same-draft' } } } as never;
    });
    const first = page();
    fireEvent.click(screen.getByText('Review server quote'));
    await screen.findByText('Server total: KES 25.50');
    fireEvent.click(screen.getByText('Accept these prices and create draft'));
    await screen.findByText('Retry same accepted submission');
    const sent = vi.mocked(clientOrderService.create).mock.calls[0];
    first.unmount(); page();
    fireEvent.click(await screen.findByText('Retry same accepted submission'));
    await screen.findByText('Recovered draft');
    expect(clientOrderService.create).toHaveBeenCalledTimes(2);
    expect(vi.mocked(clientOrderService.create).mock.calls[1]).toEqual(sent);
    expect(writes.size).toBe(1);
    expect(Object.keys(sessionStorage).filter(k => k.startsWith('mpango-pending:'))).toEqual([]);
  });
});

describe('Mac order recovery boundaries', () => {
  it('replays a replace against an already cancelled source with its original notes and body', async () => {
    const writes = new Map<string, unknown>();
    vi.mocked(clientOrderService.replaceDraft).mockImplementation(async (_id, body, key) => {
      if (!writes.has(key)) { writes.set(key, body); throw new Error('lost'); }
      return { data: { data: { id: 'replacement' } } } as never;
    });
    const first = page(true);
    fireEvent.change(screen.getByLabelText('Notes (optional)'), { target: { value: 'Original instructions' } });
    await accept(true); await screen.findByText('Retry same accepted submission');
    const original = vi.mocked(clientOrderService.replaceDraft).mock.calls[0];
    first.unmount(); page(true);
    expect(screen.getByLabelText('Notes (optional)')).toBeDisabled();
    fireEvent.click(screen.getByText('Retry same accepted submission'));
    await screen.findByText('Recovered draft');
    expect(clientOrderService.replaceDraft).toHaveBeenCalledTimes(2);
    expect(vi.mocked(clientOrderService.replaceDraft).mock.calls[1]).toEqual(original);
    expect(original[0]).toBe('old-draft');
    expect(original[1].notes).toBe('Original instructions');
    expect(writes.size).toBe(1);
  });
  it.each(['account', 'tenant', 'portal'])('does not restore another %s operation', async axis => {
    vi.mocked(clientOrderService.create).mockRejectedValue(new Error('lost'));
    const first = page(); await accept(); await screen.findByText('Retry same accepted submission'); first.unmount();
    const user = useAuthStore.getState().user!;
    useAuthStore.setState(axis === 'account' ? { user: { ...user, id: 'actor-two' } } : axis === 'tenant' ? { user: { ...user, tenant_id: 'tenant-two' } } : { retailerPortalCode: 'OTHER' });
    page();
    expect(screen.queryByText('Retry same accepted submission')).not.toBeInTheDocument();
    expect(clientOrderService.create).toHaveBeenCalledTimes(1);
  });
  it('blocks a corrupt retained request without deleting it or sending', async () => {
    vi.mocked(clientOrderService.create).mockRejectedValue(new Error('lost'));
    const first = page(); await accept(); await screen.findByText('Retry same accepted submission'); first.unmount();
    const key = Object.keys(sessionStorage).find(k => k.startsWith('mpango-pending:'))!;
    sessionStorage.setItem(key, '{broken'); page();
    expect(screen.getByRole('alert')).toHaveTextContent('cannot be safely retained');
    expect(screen.getByText('Review server quote')).toBeDisabled();
    expect(clientOrderService.create).toHaveBeenCalledTimes(1);
    expect(sessionStorage.getItem(key)).toBe('{broken');
  });
  it.each(['throws', 'readback'])('refuses a first write when storage %s', async failure => {
    if (failure === 'throws') vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('quota'); });
    else vi.spyOn(Storage.prototype, 'getItem').mockReturnValue(null);
    page(); await accept();
    await screen.findByText(/Unable to retain/);
    expect(clientOrderService.create).not.toHaveBeenCalled();
  });
  it.each([401, 403])('keeps the original after current authentication rejects %s, with no success', async status => {
    vi.mocked(clientOrderService.create).mockRejectedValue({ response: { status } });
    page(); await accept(); await screen.findByText(/This session cannot recover/);
    fireEvent.click(screen.getByText('Retry same accepted submission'));
    await waitFor(() => expect(clientOrderService.create).toHaveBeenCalledTimes(2));
    expect(vi.mocked(clientOrderService.create).mock.calls[1]).toEqual(vi.mocked(clientOrderService.create).mock.calls[0]);
    expect(screen.queryByText('Recovered draft')).not.toBeInTheDocument();
  });
  it('ignores a success arriving after the account changed', async () => {
    let resolve!: (value: never) => void;
    vi.mocked(clientOrderService.create).mockReturnValue(new Promise(r => { resolve = r; }));
    page(); await accept(); await waitFor(() => expect(clientOrderService.create).toHaveBeenCalledTimes(1));
    act(() => useAuthStore.setState({ user: { ...useAuthStore.getState().user!, id: 'other-account' } }));
    await act(async () => resolve({ data: { data: { id: 'old-success' } } } as never));
    expect(screen.queryByText('Recovered draft')).not.toBeInTheDocument();
    expect(screen.queryByText('Retry same accepted submission')).not.toBeInTheDocument();
  });
});

it('keeps a confirmed order entry and prevents another send if clearing browser retention fails', async () => {
  vi.mocked(clientOrderService.create).mockResolvedValue({ data: { data: { id: 'created-with-retained-record' } } } as never);
  vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => { throw new Error('blocked'); });
  page(); await accept();
  expect(await screen.findByRole('link', { name: 'View created draft' })).toHaveAttribute('href', '/client/orders/created-with-retained-record');
  expect(screen.getByRole('alert')).toHaveTextContent('draft was created');
  expect(screen.queryByText('Retry same accepted submission')).not.toBeInTheDocument();
  expect(clientOrderService.create).toHaveBeenCalledTimes(1);
});

it('retains unknown order data after current permissions are removed and does not replay it', async () => {
  vi.mocked(clientOrderService.create).mockRejectedValue(new Error('lost'));
  page(); await accept(); await screen.findByText('Retry same accepted submission');
  act(() => useAuthStore.setState({ user: { ...useAuthStore.getState().user!, permissions: [] } }));
  expect(screen.getByText('Retry same accepted submission')).toBeDisabled();
  fireEvent.click(screen.getByText('Retry same accepted submission'));
  expect(clientOrderService.create).toHaveBeenCalledTimes(1);
});
