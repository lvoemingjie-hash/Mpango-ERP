import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { CreateOrderPage } from '@/pages/client/CreateOrderPage';
import { clientProductService } from '@/services/clientProductService';
import { clientOrderService } from '@/services/clientOrderService';
import type { ClientProduct } from '@/types/client';

vi.mock('@/services/clientProductService', () => ({ clientProductService: { getAll: vi.fn() } }));
vi.mock('@/services/clientOrderService', () => ({ clientOrderService: { preview: vi.fn(), create: vi.fn(), replaceDraft: vi.fn() } }));

const product: ClientProduct = {
  id: 'product-one', name: 'Riverside Juice', category: null, image: null,
  in_stock: true, stock_level: 'HIGH', can_order: true, unit_count: 2,
  units: [
    { sellable_unit_id: 'bottle-id', sku_code: 'JUICE-BTL', package_quantity: 1, unit: 'bottle',
      price: '25.50', currency: 'KES', in_stock: true, stock_level: 'MEDIUM', can_order: true },
    { sellable_unit_id: 'case-id', sku_code: 'JUICE-CASE', package_quantity: 12, unit: 'case',
      price: '289.00', currency: 'KES', in_stock: true, stock_level: 'HIGH', can_order: true },
  ],
};

function catalog(items = [product], page = 1, pages = 1) {
  return { data: { success: true, timestamp: 'fixture', data: {
    items, pagination: { page, size: 20, pages, total: pages * 20 },
  } } };
}

function serverQuote(total = '25.50') {
  return { data: { data: { quote_token: `server-quote-${total}`, currency: 'KES', total,
    lines: [{ sku_id: 'bottle-id', product_name: 'Riverside Juice', quantity: 1,
      unit: 'bottle', display_label: 'bottle', package_quantity: '1', unit_price: total, subtotal: total }],
  } } };
}

function page(initialItems = false) {
  return render(<MemoryRouter initialEntries={[{ pathname: '/client/orders/new', state: initialItems ? {
    items: [{ sellable_unit_id: 'bottle-id', sku_code: 'JUICE-BTL', name: product.name,
      quantity: 1, price: '25.50', currency: 'KES', unit: 'bottle', package_quantity: 1 }],
  } : null }]}>
    <Routes>
      <Route path="/client/orders/new" element={<CreateOrderPage />} />
      <Route path="/client/orders/created" element={<p>Created order</p>} />
    </Routes>
  </MemoryRouter>);
}

async function picker() {
  fireEvent.click(screen.getByRole('button', { name: 'Add Product' }));
  const dialog = await screen.findByRole('dialog');
  await within(dialog).findByTestId('picker-unit-JUICE-BTL');
  return dialog;
}

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(clientProductService.getAll).mockResolvedValue(catalog() as never);
  vi.mocked(clientOrderService.preview).mockResolvedValue(serverQuote() as never);
  vi.mocked(clientOrderService.create).mockResolvedValue({ data: { data: { id: 'created' } } } as never);
});
afterEach(() => { cleanup(); vi.useRealTimers(); });

describe('retailer mobile order selection', () => {
  it('keeps the accessible picker open for multiple packs and retains exact stable identities', async () => {
    const user = userEvent.setup();
    page();
    const dialog = await picker();
    expect(within(dialog).getByRole('heading', { name: 'Add products' })).toHaveFocus();
    fireEvent.click(within(dialog).getByTestId('picker-unit-JUICE-BTL'));
    fireEvent.click(within(dialog).getByTestId('picker-unit-JUICE-BTL'));
    fireEvent.click(within(dialog).getByTestId('picker-unit-JUICE-CASE'));
    expect(within(dialog).getByTestId('picker-unit-JUICE-BTL')).toHaveTextContent('2 selected');
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: 'Done' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(screen.getByRole('button', { name: 'Add Product' })).toHaveFocus();
    expect(screen.getByLabelText('Quantity for JUICE-BTL')).toHaveValue('2');
    expect(screen.getByLabelText('Quantity for JUICE-CASE')).toHaveValue('1');
    expect(within(screen.getByRole('article', { name: 'Selected JUICE-CASE' })).getByText('12 × case')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Review server quote'));
    await waitFor(() => expect(clientOrderService.preview).toHaveBeenCalledWith({ items: [
      { sellable_unit_id: 'bottle-id', sku_code: 'JUICE-BTL', quantity: 2 },
      { sellable_unit_id: 'case-id', sku_code: 'JUICE-CASE', quantity: 1 },
    ] }));
    expect(clientOrderService.create).not.toHaveBeenCalled();
  });

  it('supports Escape and restores focus without discarding selected packs', async () => {
    const user = userEvent.setup();
    page();
    const dialog = await picker();
    fireEvent.click(within(dialog).getByTestId('picker-unit-JUICE-BTL'));
    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(screen.getByLabelText('Quantity for JUICE-BTL')).toHaveValue('1');
    expect(screen.getByRole('button', { name: 'Add Product' })).toHaveFocus();
  });

  it.each(['', '0', '-1', '1.5', '1e3', '9007199254740992'])('blocks preview and clears an old quote for invalid quantity %j', async value => {
    page(true);
    fireEvent.click(screen.getByText('Review server quote'));
    await screen.findByText('Server total: KES 25.50');
    fireEvent.change(screen.getByLabelText('Quantity for JUICE-BTL'), { target: { value } });
    expect(screen.getByLabelText('Quantity for JUICE-BTL')).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByText('Review server quote')).toBeDisabled();
    expect(screen.queryByText('Server total: KES 25.50')).toBeNull();
    expect(clientOrderService.create).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('Quantity for JUICE-BTL'), { target: { value: '24' } });
    expect(screen.getByText('Review server quote')).toBeEnabled();
    fireEvent.click(screen.getByText('Review server quote'));
    await waitFor(() => expect(clientOrderService.preview).toHaveBeenLastCalledWith({ items: [
      { sellable_unit_id: 'bottle-id', sku_code: 'JUICE-BTL', quantity: 24 },
    ] }));
  });

  it('does not remove a line by accidental decrement at one; explicit removal clears invalid state', () => {
    page(true);
    expect(screen.getByRole('button', { name: 'Decrease JUICE-BTL' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Quantity for JUICE-BTL'), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: 'Remove JUICE-BTL' }));
    expect(screen.queryByRole('alert')).toBeNull();
    expect(screen.getByText('Review server quote')).toBeDisabled();
  });

  it('pages beyond the first results without losing prior selection or showing unorderable packs', async () => {
    const unavailable = { ...product.units[0], sellable_unit_id: 'hidden', sku_code: 'HIDDEN', can_order: false };
    vi.mocked(clientProductService.getAll)
      .mockResolvedValueOnce(catalog([{ ...product, units: [...product.units, unavailable] }], 1, 3) as never)
      .mockResolvedValueOnce(catalog([{ ...product, id: 'last-page', name: 'Last page product' }], 2, 3) as never);
    page();
    const dialog = await picker();
    expect(within(dialog).queryByTestId('picker-unit-HIDDEN')).toBeNull();
    fireEvent.click(within(dialog).getByTestId('picker-unit-JUICE-BTL'));
    fireEvent.click(within(dialog).getByText('Next page'));
    await within(dialog).findByRole('heading', { name: 'Last page product' });
    expect(clientProductService.getAll).toHaveBeenLastCalledWith(2, 20, { search: undefined });
    expect(within(dialog).getByTestId('picker-unit-JUICE-BTL')).toHaveTextContent('1 selected');
    expect(within(dialog).getByText('Page 2 of 3')).toBeInTheDocument();
    fireEvent.change(within(dialog).getByLabelText('Search products'), { target: { value: 'juice' } });
    await waitFor(() => expect(clientProductService.getAll).toHaveBeenLastCalledWith(1, 20, { search: 'juice' }));
  });

  it('debounces typing, rejects out-of-order responses and resets search to page one', async () => {
    page();
    const dialog = await picker();
    let finishOld!: (value: never) => void;
    vi.mocked(clientProductService.getAll)
      .mockImplementationOnce(() => new Promise(resolve => { finishOld = resolve; }))
      .mockResolvedValueOnce(catalog([{ ...product, id: 'fresh', name: 'Fresh result' }]) as never);
    vi.useFakeTimers();
    fireEvent.change(within(dialog).getByLabelText('Search products'), { target: { value: 'r' } });
    fireEvent.change(within(dialog).getByLabelText('Search products'), { target: { value: 'rice' } });
    await act(async () => { vi.advanceTimersByTime(299); });
    expect(clientProductService.getAll).toHaveBeenCalledTimes(1);
    await act(async () => { vi.advanceTimersByTime(1); });
    expect(clientProductService.getAll).toHaveBeenCalledTimes(2);
    fireEvent.change(within(dialog).getByLabelText('Search products'), { target: { value: 'fresh' } });
    await act(async () => { vi.advanceTimersByTime(300); });
    await act(async () => { finishOld(catalog([{ ...product, name: 'Stale result' }]) as never); });
    vi.useRealTimers();
    expect(within(dialog).getByRole('heading', { name: 'Fresh result' })).toBeInTheDocument();
    expect(within(dialog).queryByRole('heading', { name: 'Stale result' })).toBeNull();
    expect(clientProductService.getAll).toHaveBeenLastCalledWith(1, 20, { search: 'fresh' });
  });

  it('shows retryable load failure without discarding selected items', async () => {
    page(true);
    vi.mocked(clientProductService.getAll).mockRejectedValueOnce(new Error('offline'));
    fireEvent.click(screen.getByText('Add Product'));
    const dialog = await screen.findByRole('dialog');
    await within(dialog).findByRole('alert');
    fireEvent.click(within(dialog).getByText('Retry loading products'));
    expect(await within(dialog).findByTestId('picker-unit-JUICE-BTL')).toHaveTextContent('1 selected');
  });

  it('locks editing during an unknown result and retries the original body with the same key', async () => {
    let reject!: (error: unknown) => void;
    vi.mocked(clientOrderService.create).mockImplementationOnce(() => new Promise((_resolve, fail) => { reject = fail; }));
    page(true);
    fireEvent.click(screen.getByText('Review server quote'));
    await screen.findByText('Server total: KES 25.50');
    fireEvent.click(screen.getByText('Accept these prices and create draft'));
    expect(screen.getByLabelText('Quantity for JUICE-BTL')).toBeDisabled();
    expect(screen.getByText('Add Product')).toBeDisabled();
    expect(screen.getByLabelText('Notes (optional)')).toBeDisabled();
    await act(async () => { reject(new Error('connection lost')); });
    expect(screen.getByLabelText('Quantity for JUICE-BTL')).toBeDisabled();
    const first = vi.mocked(clientOrderService.create).mock.calls[0];
    expect(first[0]).toEqual({ items: [{ sellable_unit_id: 'bottle-id', sku_code: 'JUICE-BTL', quantity: 1 }],
      notes: undefined, quote_token: 'server-quote-25.50' });
    expect(first[1]).toEqual(expect.any(String));
    fireEvent.click(screen.getByText('Retry same accepted submission'));
    await screen.findByText('Created order');
    expect(clientOrderService.create).toHaveBeenCalledTimes(2);
    expect(vi.mocked(clientOrderService.create).mock.calls[1]).toEqual(first);
  });

  it('requires fresh explicit consent on changed server prices, without auto retry', async () => {
    vi.mocked(clientOrderService.create).mockRejectedValueOnce({ response: { status: 409, data: {
      code: 'PRICE_PREVIEW_STALE', details: { old_total: '25.50', new_total: '30.00', delta: '4.50', quote: serverQuote('30.00').data.data },
    } } });
    page(true);
    fireEvent.click(screen.getByText('Review server quote'));
    await screen.findByText('Server total: KES 25.50');
    fireEvent.click(screen.getByText('Accept these prices and create draft'));
    await screen.findByText('Server total: KES 30.00');
    expect(clientOrderService.create).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText('Quantity for JUICE-BTL')).toBeEnabled();
    fireEvent.click(screen.getByText('Accept these prices and create draft'));
    await screen.findByText('Created order');
    expect(vi.mocked(clientOrderService.create).mock.calls[1][0].quote_token).toBe('server-quote-30.00');
  });
});
