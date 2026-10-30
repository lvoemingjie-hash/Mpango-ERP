import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import DeclarePaymentPage from '@/pages/client/DeclarePaymentPage';
import { submitDeclaration } from '@/services/declarationService';
import { clientOrderService } from '@/services/clientOrderService';
import { useAuthStore } from '@/stores/authStore';
vi.mock('@/services/declarationService', () => ({ submitDeclaration: vi.fn() }));
vi.mock('@/services/clientOrderService', () => ({ clientOrderService: { getById: vi.fn() } }));
function page() { return render(<MemoryRouter initialEntries={['/client/orders/order-one/declare']}><Routes>
  <Route path="/client/orders/:orderId/declare" element={<DeclarePaymentPage />} />
  <Route path="/client/orders/:orderId" element={<p>Recovered declaration</p>} />
</Routes></MemoryRouter>); }
beforeEach(() => {
  vi.resetAllMocks();sessionStorage.clear();localStorage.clear();
  useAuthStore.setState({ accessToken: 'synthetic-session', user: { id: 'actor-one', tenant_id: 'tenant-one', tenant_schema: 't_one', full_name: 'Synthetic', email: null, roles: ['retailer_operator'], permissions: ['client:payments:declare','client:orders:read'] }, tenantCode: 'PORTAL', retailerPortalCode: 'PORTAL' });
  vi.mocked(clientOrderService.getById).mockResolvedValue({ data: { data: { id: 'order-one', currency: 'KES' } } } as never);
});
describe('Mac declaration refresh recovery', () => {
  it('BASE B2: remount recovers the original amount and key after a lost response', async () => {
    const writes = new Map<string, unknown>();
    vi.mocked(submitDeclaration).mockImplementation(async (id, body, key) => {
      if (!writes.has(key)) { writes.set(key, body); throw new Error('Synthetic response lost after server commit'); }
      return { success: true, data: { id: 'same-declaration', order_id: id, ...body, status: 'pending' } } as never;
    });
    const first=page();
    fireEvent.change(await screen.findByLabelText('Amount (KES)'), { target: { value: '25.50' } });
    fireEvent.click(screen.getByRole('button', {name: /submit declaration/i}));
    await waitFor(()=>expect(submitDeclaration).toHaveBeenCalledTimes(1));
    await screen.findByText(/try again later|result.*unknown/i);
    const sent=vi.mocked(submitDeclaration).mock.calls[0];
    first.unmount();page();
    fireEvent.click(await screen.findByRole('button', {name: 'Recover original declaration'}));
    await screen.findByText('Recovered declaration');
    expect(submitDeclaration).toHaveBeenCalledTimes(2);
    expect(vi.mocked(submitDeclaration).mock.calls[1]).toEqual(sent);
    expect(writes.size).toBe(1);
    expect(Object.keys(sessionStorage).filter(k=>k.startsWith('mpango-pending:'))).toEqual([]);
  });
});

afterEach(() => { vi.restoreAllMocks(); });
async function submitOriginal(value = '25.50', transfer = false) {
  fireEvent.change(await screen.findByLabelText('Amount (KES)'), { target: { value } });
  if (transfer) {
    fireEvent.change(screen.getByLabelText('Method'), { target: { value: 'transfer' } });
    fireEvent.change(screen.getByLabelText('Transfer Reference'), { target: { value: '  SYNTHETIC-REF  ' } });
  }
  fireEvent.click(screen.getByRole('button', { name: 'Submit Declaration' }));
}
describe('Mac declaration recovery controls', () => {
  it('retains exact amount strings and trimmed transfer reference; success clears and an explicit new visit uses a new key', async () => {
    vi.mocked(submitDeclaration).mockRejectedValueOnce(new Error('lost'))
      .mockResolvedValue({ data: { id: 'confirmed-declaration', order_id: 'order-one' } } as never);
    const first = page(); await submitOriginal('9007199254740993.1250', true);
    await screen.findByRole('button', { name: 'Recover original declaration' });
    const sent = vi.mocked(submitDeclaration).mock.calls[0];
    expect(sent[1]).toEqual({ declared_amount: '9007199254740993.1250', method: 'transfer', transfer_reference: 'SYNTHETIC-REF' });
    first.unmount(); const second = page();
    expect(screen.getByLabelText(/Amount/)).toHaveValue('9007199254740993.1250');
    expect(screen.getByLabelText(/Amount/)).toBeDisabled();
    expect(screen.getByLabelText('Transfer Reference')).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Recover original declaration' }));
    await screen.findByText('Recovered declaration');
    expect(vi.mocked(submitDeclaration).mock.calls[1]).toEqual(sent);
    expect(Object.keys(sessionStorage)).toEqual([]);
    second.unmount(); page(); await submitOriginal('10'); await screen.findByText('Recovered declaration');
    expect(vi.mocked(submitDeclaration).mock.calls[2][2]).not.toBe(sent[2]);
  });
  it.each(['account', 'tenant', 'portal'])('isolates the retained declaration across %s changes', async axis => {
    vi.mocked(submitDeclaration).mockRejectedValue(new Error('lost'));
    const first = page(); await submitOriginal(); await screen.findByRole('button', { name: 'Recover original declaration' }); first.unmount();
    const user = useAuthStore.getState().user!;
    useAuthStore.setState(axis === 'account' ? { user: { ...user, id: 'actor-two' } } : axis === 'tenant' ? { user: { ...user, tenant_schema: 't_two' } } : { retailerPortalCode: 'OTHER' });
    page();
    expect(screen.queryByRole('button', { name: 'Recover original declaration' })).not.toBeInTheDocument();
    expect(screen.getByLabelText(/Amount/)).toHaveValue('');
    expect(submitDeclaration).toHaveBeenCalledTimes(1);
  });
  it.each(['throws', 'readback'])('does not submit when storage %s', async failure => {
    if (failure === 'throws') vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('quota'); });
    else vi.spyOn(Storage.prototype, 'getItem').mockReturnValue(null);
    page(); await submitOriginal(); await screen.findByText(/cannot be safely retained/);
    expect(submitDeclaration).not.toHaveBeenCalled();
  });
  it('does not read a malformed version or discard it', async () => {
    vi.mocked(submitDeclaration).mockRejectedValue(new Error('lost'));
    const first = page(); await submitOriginal(); await screen.findByRole('button', { name: 'Recover original declaration' }); first.unmount();
    const key = Object.keys(sessionStorage)[0]; const record = JSON.parse(sessionStorage.getItem(key)!); record.version = 99;
    sessionStorage.setItem(key, JSON.stringify(record)); page();
    expect(screen.getByRole('alert')).toHaveTextContent('cannot be safely retained');
    expect(screen.getByRole('button', { name: 'Submit Declaration' })).toBeDisabled();
    expect(submitDeclaration).toHaveBeenCalledTimes(1);
  });
  it.each([401, 403])('recovery reaches current backend authorization and preserves the request after %s', async status => {
    vi.mocked(submitDeclaration).mockRejectedValueOnce(new Error('lost')).mockRejectedValue({ response: { status } });
    const first = page(); await submitOriginal(); await screen.findByRole('button', { name: 'Recover original declaration' }); first.unmount(); page();
    fireEvent.click(screen.getByRole('button', { name: 'Recover original declaration' }));
    await waitFor(() => expect(submitDeclaration).toHaveBeenCalledTimes(2));
    expect(vi.mocked(submitDeclaration).mock.calls[1]).toEqual(vi.mocked(submitDeclaration).mock.calls[0]);
    expect(screen.queryByText('Recovered declaration')).not.toBeInTheDocument();
    expect(Object.keys(sessionStorage)).toHaveLength(1);
  });
  it('blocks blank transfer references and unverified currency for new operations', async () => {
    const first = page(); await screen.findByLabelText('Amount (KES)');
    fireEvent.change(screen.getByLabelText('Method'), { target: { value: 'transfer' } });
    fireEvent.change(screen.getByLabelText(/Amount/), { target: { value: '5.50' } });
    fireEvent.change(screen.getByLabelText('Transfer Reference'), { target: { value: '   ' } });
    fireEvent.submit(screen.getByRole('button', { name: 'Submit Declaration' }).closest('form')!);
    await screen.findByText('Enter the transfer reference from your payment record.'); expect(submitDeclaration).not.toHaveBeenCalled();
    first.unmount(); vi.mocked(clientOrderService.getById).mockResolvedValue({ data: { data: { currency: null } } } as never); page();
    await screen.findByText(/Currency unavailable/);
    expect(screen.getByRole('button', { name: 'Submit Declaration' })).toBeDisabled();
    expect(submitDeclaration).not.toHaveBeenCalled();
  });
  it('shows UGX from the server and transmits a cash amount unchanged', async () => {
    vi.mocked(clientOrderService.getById).mockResolvedValue({ data: { data: { currency: 'UGX' } } } as never);
    vi.mocked(submitDeclaration).mockRejectedValue(new Error('lost')); page();
    fireEvent.change(await screen.findByLabelText('Amount (UGX)'), { target: { value: '5000' } });
    fireEvent.click(screen.getByRole('button', { name: 'Submit Declaration' }));
    await waitFor(() => expect(submitDeclaration).toHaveBeenCalledTimes(1));
    expect(vi.mocked(submitDeclaration).mock.calls[0][1]).toEqual({ declared_amount: '5000', method: 'cash' });
  });
  it('lets a retained historical NULL-currency request reach strict same-body backend replay', async () => {
    vi.mocked(submitDeclaration).mockRejectedValueOnce(new Error('lost')).mockResolvedValue({ data: { id: 'historical', order_id: 'order-one' } } as never);
    const first = page(); await submitOriginal(); await screen.findByRole('button', { name: 'Recover original declaration' }); first.unmount();
    const original = vi.mocked(submitDeclaration).mock.calls[0];
    const key = Object.keys(sessionStorage)[0]; const record = JSON.parse(sessionStorage.getItem(key)!); record.currency = null; sessionStorage.setItem(key, JSON.stringify(record));
    vi.mocked(clientOrderService.getById).mockResolvedValue({ data: { data: { currency: null } } } as never);
    page(); fireEvent.click(screen.getByRole('button', { name: 'Recover original declaration' }));
    await screen.findByText('Recovered declaration');
    expect(vi.mocked(submitDeclaration).mock.calls[1]).toEqual(original);
  });
  it('ignores a late success after logout and retains the operation for authenticated recovery', async () => {
    let resolve!: (v: never) => void;
    vi.mocked(submitDeclaration).mockReturnValue(new Promise(r => { resolve = r; }));
    page(); await submitOriginal(); await waitFor(() => expect(submitDeclaration).toHaveBeenCalledTimes(1));
    act(() => useAuthStore.getState().logout());
    await act(async () => resolve({ data: { id: 'old', order_id: 'order-one' } } as never));
    expect(screen.queryByText('Recovered declaration')).not.toBeInTheDocument();
    expect(Object.keys(sessionStorage)).toHaveLength(1);
  });
});

it('prevents sending while retained storage cannot even be read', async () => {
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('denied'); });
  page(); await screen.findByLabelText('Amount (KES)');
  expect(screen.getByRole('alert')).toHaveTextContent('cannot be safely retained');
  expect(screen.getByRole('button', { name: 'Submit Declaration' })).toBeDisabled();
  expect(submitDeclaration).not.toHaveBeenCalled();
});
it('does not replay after current permissions were removed', async () => {
  vi.mocked(submitDeclaration).mockRejectedValue(new Error('lost'));
  page(); await submitOriginal(); await screen.findByRole('button', { name: 'Recover original declaration' });
  act(() => useAuthStore.setState({ user: { ...useAuthStore.getState().user!, permissions: [] } }));
  expect(screen.getByRole('button', { name: 'Recover original declaration' })).toBeDisabled();
  expect(submitDeclaration).toHaveBeenCalledTimes(1);
});
it('distinguishes input rejection from unknown result and only rotates on an explicit new operation', async () => {
  vi.mocked(submitDeclaration).mockRejectedValueOnce({ response: { status: 422 } }).mockRejectedValue(new Error('unknown'));
  page(); await submitOriginal();
  fireEvent.click(await screen.findByRole('button', { name: 'Edit rejected input and start a new declaration' }));
  fireEvent.change(screen.getByLabelText(/Amount/), { target: { value: '10.00' } });
  fireEvent.click(screen.getByRole('button', { name: 'Submit Declaration' }));
  await waitFor(() => expect(submitDeclaration).toHaveBeenCalledTimes(2));
  const calls = vi.mocked(submitDeclaration).mock.calls;
  expect(calls[1][2]).not.toBe(calls[0][2]);
  expect(calls[1][1].declared_amount).toBe('10.00');
  expect(screen.queryByRole('button', { name: 'Edit rejected input and start a new declaration' })).not.toBeInTheDocument();
});
