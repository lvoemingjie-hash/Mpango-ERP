import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderNegotiationPanel } from '@/components/orders/OrderNegotiationPanel';
import { orderNegotiationService, type OrderNegotiation } from '@/services/orderNegotiationService';
import { useAuthStore } from '@/stores/authStore';

vi.mock('@/services/orderNegotiationService', () => ({ orderNegotiationService: {
  list: vi.fn(), propose: vi.fn(), accept: vi.fn(), reject: vi.fn(), withdraw: vi.fn(),
} }));

const items = [{ sellable_unit_id: 'sku-one', product_name: 'Box of soap', quantity: 2,
  unit_price: '90.00', unit_snapshot: 'Box', package_quantity_snapshot: '12' }];
const proposal: OrderNegotiation = {
  id: 'proposal-one', source_order_id: 'original', version: 1, digest: 'a'.repeat(64), status: 'pending',
  expires_at: '2099-10-19T12:30:00+00:00', expired: false, accepted_order_id: null,
  country: 'KE', currency: 'KES', total: '140.00', original_total: '180.00',
  lines: [{ sku_id: 'sku-one', sku_code: 'SOAP', product_name: 'Box of soap', quantity: 2,
    unit: 'Box', package_quantity: '12', display_label: 'Box', unit_price: '70.00', subtotal: '140.00' }],
  original_lines: [{ sku_id: 'sku-one', sku_code: 'SOAP', product_name: 'Box of soap', quantity: 2,
    unit: 'Box', package_quantity: '12', display_label: 'Box', unit_price: '90.00', subtotal: '180.00' }],
};
const response = (data: unknown) => ({ data: { success: true, data } }) as never;
const user = (permissions: string[]) => ({ id: 'customer', email: null, full_name: 'Test customer',
  tenant_id: 'tenant', tenant_schema: 'schema', roles: ['retailer_operator'], permissions });
const customerPermissions = ['client:orders:read', 'client:orders:create'];

function panel(client = true) {
  return render(<MemoryRouter><OrderNegotiationPanel orderId="original" items={items} currency="KES" draft client={client} /></MemoryRouter>);
}

describe('S3 explicit immutable proposal consent', () => {
  beforeEach(() => {
    vi.resetAllMocks(); sessionStorage.clear();
    useAuthStore.setState({ user: user(customerPermissions) });
    vi.mocked(orderNegotiationService.list).mockResolvedValue(response({ items: [proposal] }));
  });

  it('shows exact agreed lines and a zoned deadline, never accepting automatically', async () => {
    panel();
    await screen.findByText('Proposal 1');
    expect(screen.getByText('KES 70.00')).toBeTruthy();
    expect(screen.getByText(/Agreed total: KES 140.00/)).toBeTruthy();
    expect(document.querySelector('time')?.getAttribute('datetime')).toBe(proposal.expires_at);
    expect(screen.getByRole('button', { name: 'Accept agreed prices' })).toBeDisabled();
    expect(orderNegotiationService.accept).not.toHaveBeenCalled();
  });

  it('retains the exact proposal and key across an unknown response retry', async () => {
    vi.mocked(orderNegotiationService.accept).mockRejectedValueOnce(new Error('network'))
      .mockResolvedValueOnce(response({ ...proposal, status: 'accepted', accepted_order_id: 'replacement', replayed: true }));
    panel();
    await screen.findByText('Proposal 1');
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: 'Accept agreed prices' }));
    await screen.findByRole('button', { name: 'Retry same acceptance' });
    fireEvent.click(screen.getByRole('button', { name: 'Retry same acceptance' }));
    await waitFor(() => expect(orderNegotiationService.accept).toHaveBeenCalledTimes(2));
    const calls = vi.mocked(orderNegotiationService.accept).mock.calls;
    expect(calls[1]).toEqual(calls[0]);
    expect(calls[0][1]).toEqual(proposal);
    expect(calls[0][2]).toMatch(/^[0-9a-f-]{36}$/);
  });

  it('does not grant a read-only retailer acceptance or rejection controls', async () => {
    useAuthStore.setState({ user: user(['client:orders:read']) });
    panel();
    await screen.findByText('Proposal 1');
    expect(screen.queryByRole('button', { name: 'Accept agreed prices' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Reject proposal' })).toBeNull();
  });

  it('blocks new acceptance when the server marks the proposal expired', async () => {
    vi.mocked(orderNegotiationService.list).mockResolvedValue(response({ items: [{ ...proposal, expired: true }] }));
    panel();
    await screen.findByText('Proposal 1');
    fireEvent.click(screen.getByRole('checkbox'));
    expect(screen.getByRole('button', { name: 'Accept agreed prices' })).toBeDisabled();
  });

  it('requires an explicit merchant deadline and sends immutable units only as prices', async () => {
    useAuthStore.setState({ user: user(['pricing:write', 'orders:update']) });
    vi.mocked(orderNegotiationService.list).mockResolvedValue(response({ items: [] }));
    vi.mocked(orderNegotiationService.propose).mockResolvedValue(response(proposal));
    panel(false);
    const button = await screen.findByRole('button', { name: 'Send price proposal' });
    expect(button).toBeDisabled();
    const date = screen.getByLabelText(/Accept and confirm deadline/);
    expect(date).toHaveValue('');
    fireEvent.change(screen.getByLabelText('Proposed unit price for Box of soap'), { target: { value: '70.00' } });
    fireEvent.change(date, { target: { value: '2099-10-19T15:30' } });
    fireEvent.click(button);
    await waitFor(() => expect(orderNegotiationService.propose).toHaveBeenCalledTimes(1));
    const args = vi.mocked(orderNegotiationService.propose).mock.calls[0];
    expect(args[1]).toEqual([{ sku_id: 'sku-one', unit_price: '70.00' }]);
    expect(args[2]).toBe(new Date('2099-10-19T15:30').toISOString());
  });

  it('does not offer merchant proposal entry to pricing-only staff', async () => {
    useAuthStore.setState({ user: user(['pricing:write']) });
    vi.mocked(orderNegotiationService.list).mockResolvedValue(response({ items: [] }));
    panel(false);
    await screen.findByText('No negotiated proposal for this order.');
    expect(screen.queryByRole('button', { name: 'Send price proposal' })).toBeNull();
  });
});
