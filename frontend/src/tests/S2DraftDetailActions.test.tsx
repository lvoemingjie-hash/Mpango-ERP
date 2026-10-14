import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { OrderDetailPage } from '@/pages/client/OrderDetailPage';
import { clientOrderService } from '@/services/clientOrderService';
import type { ClientOrder } from '@/types/client';

vi.mock('@/services/clientOrderService', () => ({ clientOrderService: {
  getById: vi.fn(), cancel: vi.fn(), create: vi.fn(), replaceDraft: vi.fn(), submitReorder: vi.fn(),
} }));

const DRAFT = 'new-reorder-draft';
const SOURCE = 'historical-source-order';
const draft = (sourceOrderId?: string | null): ClientOrder => ({
  id: DRAFT, status: 'CREATED', source_order_id: sourceOrderId,
  total_amount: '220.00', currency: 'KES', item_count: 1, notes: null,
  created_at: '2026-10-14T07:00:00Z', items: [{
    sellable_unit_id: 'unit', identity_status: 'stable', product_name: 'Boxes', sku_code: 'BOX',
    unit_snapshot: 'box', package_quantity_snapshot: '12', display_label_snapshot: 'Boxes',
    quantity: 2, unit_price: '110.00', subtotal: '220.00',
  }],
});
function response(data: unknown, success = true) { return { data: { success, data } } as never; }
function CurrentRoute() {
  const location = useLocation();
  return <p data-testid="current-route">{location.pathname}{location.search}</p>;
}
async function mount(order = draft(SOURCE)) {
  vi.mocked(clientOrderService.getById).mockResolvedValue(response(order));
  render(<MemoryRouter initialEntries={[`/client/orders/${DRAFT}`]}>
    <Routes>
      <Route path="/client/orders/:orderId" element={<OrderDetailPage />} />
      <Route path="/client/orders/:orderId/reorder" element={<p>Historical reorder page</p>} />
      <Route path="/client/orders/new" element={<p>Ordinary replacement page</p>} />
    </Routes>
    <CurrentRoute />
  </MemoryRouter>);
  await screen.findByRole('heading', { name: 'Items' });
}
function expectNoFollowup() {
  expect(screen.queryByRole('link', { name: /Order again/i })).toBeNull();
  expect(screen.queryByRole('link', { name: 'Review new quote and replace this draft' })).toBeNull();
  expect(screen.getByTestId('current-route')).toHaveTextContent(`/client/orders/${DRAFT}`);
  expect(clientOrderService.create).not.toHaveBeenCalled();
  expect(clientOrderService.replaceDraft).not.toHaveBeenCalled();
  expect(clientOrderService.submitReorder).not.toHaveBeenCalled();
  expect(vi.mocked(clientOrderService.cancel).mock.calls.every(([id]) => id === DRAFT)).toBe(true);
}

beforeEach(() => {
  vi.resetAllMocks();
  vi.spyOn(window, 'confirm').mockReturnValue(true);
  vi.mocked(clientOrderService.cancel).mockResolvedValue(response({ ...draft(SOURCE), status: 'CANCELLED' }));
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe('S2 draft detail cancellation and historical reorder', () => {
  it.each([undefined, null])('preserves ordinary S1 draft replacement with source %s', async source => {
    await mount(draft(source));
    expect(screen.getByRole('link', { name: 'Review new quote and replace this draft' }))
      .toHaveAttribute('href', `/client/orders/new?replace=${DRAFT}`);
    expect(screen.getByRole('link', { name: 'Order again' })).toHaveAttribute('href', `/client/orders/${DRAFT}/reorder`);
    expect(screen.getByRole('button', { name: 'Cancel Order' })).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Reorder draft actions' })).toBeNull();
    expect(clientOrderService.cancel).not.toHaveBeenCalled();
  });

  it('guides an S2 draft through cancellation without exposing ordinary replacement or early reorder', async () => {
    await mount();
    expect(screen.getByRole('region', { name: 'Reorder draft actions' }))
      .toHaveTextContent('After cancellation succeeds, order again from the historical order.');
    expect(screen.getByRole('link', { name: /historical order #/ })).toHaveAttribute('href', `/client/orders/${SOURCE}`);
    expect(screen.getByRole('button', { name: 'Cancel this draft to order again' })).toBeInTheDocument();
    expectNoFollowup();
    expect(clientOrderService.cancel).not.toHaveBeenCalled();
  });

  it('requires explicit confirmation before cancelling only the new draft', async () => {
    vi.mocked(window.confirm).mockReturnValue(false);
    await mount();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel this draft to order again' }));
    expect(window.confirm).toHaveBeenCalledWith(
      'Cancel this draft before ordering again? Only this draft will be cancelled; the historical order will remain unchanged.',
    );
    expect(clientOrderService.cancel).not.toHaveBeenCalled();
    expectNoFollowup();
  });

  it('waits for cancellation success and then lets the user order again from the historical source', async () => {
    let resolve!: (value: never) => void;
    vi.mocked(clientOrderService.cancel).mockImplementation(() => new Promise(done => { resolve = done; }));
    await mount();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel this draft to order again' }));
    expect(vi.mocked(clientOrderService.cancel).mock.calls).toEqual([[DRAFT]]);
    expect(screen.getByRole('button', { name: 'Cancelling...' })).toBeDisabled();
    expectNoFollowup();
    await act(async () => resolve(response({ ...draft(SOURCE), status: 'CANCELLED' })));
    const followup = await screen.findByRole('link', { name: 'Order again from historical order' });
    expect(followup).toHaveAttribute('href', `/client/orders/${SOURCE}/reorder`);
    expect(screen.getByRole('status')).toHaveTextContent('This draft is cancelled.');
    expect(screen.getByTestId('current-route')).toHaveTextContent(`/client/orders/${DRAFT}`);
    expect(screen.queryByRole('button', { name: 'Cancel this draft to order again' })).toBeNull();
    expect(clientOrderService.create).not.toHaveBeenCalled();
    expect(clientOrderService.submitReorder).not.toHaveBeenCalled();
    fireEvent.click(followup);
    await screen.findByText('Historical reorder page');
    expect(screen.getByTestId('current-route')).toHaveTextContent(`/client/orders/${SOURCE}/reorder`);
    expect(vi.mocked(clientOrderService.cancel).mock.calls).toEqual([[DRAFT]]);
    expect(clientOrderService.create).not.toHaveBeenCalled();
    expect(clientOrderService.replaceDraft).not.toHaveBeenCalled();
    expect(clientOrderService.submitReorder).not.toHaveBeenCalled();
  });

  it.each([
    ['denied', { response: { status: 403, data: { detail: { message: 'Cancellation denied.' } } } }, 'Cancellation denied.'],
    ['server failure', { response: { status: 500 } }, 'Internal server error. Please try again or contact support.'],
    ['unknown network result', new Error('Network response unknown.'), 'Network response unknown.'],
  ])('does not navigate or create after cancellation %s', async (_name, failure, message) => {
    vi.mocked(clientOrderService.cancel).mockRejectedValue(failure);
    await mount();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel this draft to order again' }));
    await screen.findByText(message as string);
    expect(vi.mocked(clientOrderService.cancel).mock.calls).toEqual([[DRAFT]]);
    expect(screen.getByRole('button', { name: 'Cancel this draft to order again' })).toBeEnabled();
    expectNoFollowup();
  });

  it('does not treat an unsuccessful response envelope as confirmed cancellation', async () => {
    vi.mocked(clientOrderService.cancel).mockResolvedValue(response({ ...draft(SOURCE), status: 'CANCELLED' }, false));
    await mount();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel this draft to order again' }));
    await screen.findByText('Cancellation could not be confirmed. Check this draft\'s status before ordering again.');
    expect(vi.mocked(clientOrderService.cancel).mock.calls).toEqual([[DRAFT]]);
    expectNoFollowup();
  });

  it.each([
    ['still created', draft(SOURCE)],
    ['another order', { ...draft(SOURCE), id: SOURCE, status: 'CANCELLED' }],
    ['missing order', null],
  ])('requires a confirmed cancellation of this draft when response is %s', async (_name, result) => {
    vi.mocked(clientOrderService.cancel).mockResolvedValue(response(result));
    await mount();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel this draft to order again' }));
    await screen.findByText('Cancellation could not be confirmed. Check this draft\'s status before ordering again.');
    expect(vi.mocked(clientOrderService.cancel).mock.calls).toEqual([[DRAFT]]);
    expectNoFollowup();
  });

  it('keeps the existing ordinary S1 cancellation confirmation and target', async () => {
    vi.mocked(clientOrderService.cancel).mockResolvedValue(response({ ...draft(), status: 'CANCELLED' }));
    await mount(draft());
    fireEvent.click(screen.getByRole('button', { name: 'Cancel Order' }));
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Cancel Order' })).toBeNull());
    expect(window.confirm).toHaveBeenCalledWith('Are you sure you want to cancel this order?');
    expect(vi.mocked(clientOrderService.cancel).mock.calls).toEqual([[DRAFT]]);
    expect(screen.getByRole('link', { name: 'Order again' })).toHaveAttribute('href', `/client/orders/${DRAFT}/reorder`);
    expect(screen.queryByRole('link', { name: 'Order again from historical order' })).toBeNull();
    expect(screen.queryByRole('link', { name: 'Review new quote and replace this draft' })).toBeNull();
  });
});
