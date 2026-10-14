import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { ReorderPage } from '@/pages/client/ReorderPage';
import { clientOrderService } from '@/services/clientOrderService';
import { clientProductService } from '@/services/clientProductService';
import { useAuthStore } from '@/stores/authStore';
import type { ClientProduct, ReorderPreview, ReorderSelection } from '@/types/client';
import type { ServerQuote } from '@/types/pricing';

vi.mock('@/services/clientOrderService', () => ({ clientOrderService: { previewReorder: vi.fn(), submitReorder: vi.fn() } }));
vi.mock('@/services/clientProductService', () => ({ clientProductService: { getAll: vi.fn() } }));

const SOURCE = 'source-order';
const UNIT = 'verified-unit';
const REPLACEMENT = 'replacement-unit';
const storageKey = `mpango-s2-reorder:tenant:actor:${SOURCE}`;
const quote = (total = '220.00', currency: 'KES' | 'UGX' = 'KES'): ServerQuote => ({
  quote_token: `unusable-synthetic-${total}`, total, currency, country: currency === 'UGX' ? 'UG' : 'KE', expires_at: 9999999999,
  lines: [{ sku_id: UNIT, sku_code: 'BOX', product_name: 'Verified boxes', quantity: 2,
    unit: 'box', package_quantity: '12', display_label: 'Boxes', unit_price: total === '220.00' ? '110.00' : '120.00',
    subtotal: total, revision: 2, source: 'BASE_PRICE' }],
});
function preview(options: { unavailable?: boolean; selections?: ReorderSelection[]; currency?: 'KES' | 'UGX'; unknownCurrency?: boolean;
  total?: string; stockWarning?: boolean; quantity?: number } = {}): ReorderPreview {
  const { unavailable = false, selections = [], currency = 'KES', unknownCurrency = false, total = '220.00', quantity = 2 } = options;
  const currentQuote = quote(total, currency);
  currentQuote.lines[0].quantity = quantity;
  const rows: ReorderPreview['rows'] = [{ source_item_id: 'line-01', original: {
    product_name: 'Historical boxes', sku_code: 'OLD-BOX', sellable_unit_id: UNIT, identity_status: 'linked_legacy',
    unit: 'box', package_quantity: '12', display_label: 'Boxes', quantity, unit_price: '90.00', subtotal: '180.00',
  }, selection: selections.find(value => value.source_item_id === 'line-01') || { source_item_id: 'line-01', action: 'keep' },
  status: 'READY', reason: null, current: currentQuote.lines[0], stock_warning: options.stockWarning ? 'INSUFFICIENT_STOCK' : null }];
  if (unavailable) {
    const selection = selections.find(value => value.source_item_id === 'line-02') || { source_item_id: 'line-02', action: 'keep' };
    rows.push({ source_item_id: 'line-02', original: {
      product_name: 'Historical inactive item', sku_code: 'INACTIVE', sellable_unit_id: null, identity_status: 'legacy',
      unit: null, package_quantity: null, display_label: null, quantity: 1, unit_price: '50.00', subtotal: '50.00',
    }, selection, status: selection.action === 'remove' ? 'REMOVED' : selection.action === 'replace' ? 'READY' : 'UNAVAILABLE',
    reason: selection.action === 'keep' ? 'LEGACY_IDENTITY_UNRESOLVED' : null,
    current: selection.action === 'replace' ? { ...currentQuote.lines[0], sku_id: REPLACEMENT, product_name: 'Chosen replacement', quantity: 1 } : null,
    stock_warning: null });
  }
  const ready = rows.every(row => row.status !== 'UNAVAILABLE');
  return { source_order_id: SOURCE, order_basis: 'HISTORICAL_ITEM_ID', historical_total: unavailable ? '230.00' : '180.00',
    historical_currency: unknownCurrency ? null : currency,
    historical_currency_status: unknownCurrency ? 'LEGACY_CURRENCY_UNVERIFIED' : 'KNOWN', rows, ready,
    quote: ready ? currentQuote : null, current_total: ready ? total : null, current_currency: currency,
    delta: ready && !unknownCurrency ? unavailable ? '-10.00' : '40.00' : null };
}
function response(data: unknown) { return { data: { data } } as never; }
function mount() {
  return render(<MemoryRouter initialEntries={[`/client/orders/${SOURCE}/reorder`]}><Routes>
    <Route path="/client/orders/:orderId/reorder" element={<ReorderPage />} />
    <Route path="/client/orders/:orderId" element={<p>Draft detail</p>} />
  </Routes></MemoryRouter>);
}
async function reviewAndAccept() {
  fireEvent.click(await screen.findByRole('button', { name: 'Review server quote' }));
  await screen.findByRole('button', { name: 'Accept these prices and create draft' });
  fireEvent.click(screen.getByRole('button', { name: 'Accept these prices and create draft' }));
}

beforeEach(() => {
  vi.resetAllMocks();
  sessionStorage.clear();
  useAuthStore.setState({ user: { id: 'actor', tenant_id: 'tenant', tenant_schema: 't_tenant', email: null, full_name: null,
    roles: ['retailer_operator'], permissions: [] } });
  vi.mocked(clientOrderService.previewReorder).mockResolvedValue(response(preview()));
  vi.mocked(clientOrderService.submitReorder).mockResolvedValue(response({ id: 'new-draft', source_order_id: SOURCE }));
});
afterEach(() => { cleanup(); sessionStorage.clear(); useAuthStore.setState({ user: null }); vi.restoreAllMocks(); });

describe('S2 reorder client intent and server consent', () => {
  it('submits S2 through the native durable orders path while leaving ordinary S1 create intact', async () => {
    const { api } = await import('@/services/api');
    const actual = await vi.importActual<typeof import('@/services/clientOrderService')>('@/services/clientOrderService');
    const post = vi.spyOn(api, 'post').mockResolvedValue(response({ id: 'new-draft' }));
    const data = { selections: [{ source_item_id: 'line-01', action: 'keep' } as ReorderSelection],
      quote_token: quote().quote_token, notes: 'accepted notes' };
    await actual.clientOrderService.submitReorder(SOURCE, data, 'same-reorder-key');
    expect(post).toHaveBeenNthCalledWith(1, '/client/orders', { ...data, source_order_id: SOURCE },
      { headers: { 'X-Idempotency-Key': 'same-reorder-key' } });
    const ordinary = { items: [{ sellable_unit_id: UNIT, quantity: 2 }], quote_token: quote().quote_token };
    await actual.clientOrderService.create(ordinary, 'ordinary-key');
    expect(post).toHaveBeenNthCalledWith(2, '/client/orders', ordinary,
      { headers: { 'X-Idempotency-Key': 'ordinary-key' } });
  });

  it('keeps every historical row and requires explicit handling before a complete quote', async () => {
    vi.mocked(clientOrderService.previewReorder).mockImplementation(async (_source, selections) => response(preview({ unavailable: true, selections })));
    mount();
    const unavailable = await screen.findByTestId('reorder-row-line-02');
    expect(screen.getAllByTestId(/^reorder-row-/)).toHaveLength(2);
    expect(within(unavailable).getByText('LEGACY_IDENTITY_UNRESOLVED')).toBeInTheDocument();
    expect(screen.queryByText(/Current total:/)).toBeNull();
    expect(clientOrderService.submitReorder).not.toHaveBeenCalled();
    fireEvent.click(within(unavailable).getByRole('button', { name: 'Remove line 2' }));
    expect(within(unavailable).getByText(/explicitly removed/)).toBeInTheDocument();
    expect(screen.getAllByTestId(/^reorder-row-/)).toHaveLength(2);
    fireEvent.click(screen.getByRole('button', { name: 'Review server quote' }));
    await screen.findByText('Server total: KES 220.00');
    expect(clientOrderService.submitReorder).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Accept these prices and create draft' }));
    await waitFor(() => expect(clientOrderService.submitReorder).toHaveBeenCalledTimes(1));
    expect(vi.mocked(clientOrderService.submitReorder).mock.calls[0]).toEqual([SOURCE, {
      selections: [{ source_item_id: 'line-01', action: 'keep' }, { source_item_id: 'line-02', action: 'remove' }],
      notes: undefined, quote_token: quote().quote_token,
    }, expect.any(String)]);
  });

  it.each(['KES', 'UGX'] as const)('displays historical 180, current 220 and exact +40 in %s', async currency => {
    vi.mocked(clientOrderService.previewReorder).mockResolvedValue(response(preview({ currency })));
    mount();
    const totals = await screen.findByRole('region', { name: 'Historical and current totals' });
    expect(within(totals).getByText(`${currency} 180.00`)).toBeInTheDocument();
    expect(within(totals).getByText(`${currency} 220.00`)).toBeInTheDocument();
    expect(within(totals).getByText(`${currency} +40.00`)).toBeInTheDocument();
    expect(clientOrderService.submitReorder).not.toHaveBeenCalled();
  });

  it('recognizes reviewed removal despite null optional fields in the API decision', async () => {
    vi.mocked(clientOrderService.previewReorder).mockImplementation(async (_source, selections) => {
      const result = preview({ unavailable: true, selections });
      result.rows = result.rows.map(row => ({ ...row, selection: row.selection.action === 'replace' ? row.selection
        : { ...row.selection, sellable_unit_id: null, quantity: null } as unknown as ReorderSelection }));
      return response(result);
    });
    mount();
    const row = await screen.findByTestId('reorder-row-line-02');
    fireEvent.click(within(row).getByRole('button', { name: 'Remove line 2' }));
    expect(within(row).getByText('Selection changed. Review the complete current quote.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Review server quote' }));
    await screen.findByText('Server total: KES 220.00');
    expect(within(row).queryByText('Selection changed. Review the complete current quote.')).toBeNull();
    expect(within(row).getByText(/explicitly removed/)).toBeInTheDocument();
  });

  it('does not invent a difference for unverified historical currency', async () => {
    vi.mocked(clientOrderService.previewReorder).mockResolvedValue(response(preview({ unknownCurrency: true })));
    mount();
    expect(await screen.findByText(/No price difference is calculated/)).toBeInTheDocument();
    expect(screen.getAllByText(/LEGACY_CURRENCY_UNVERIFIED/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/Change from historical total:/)).toBeNull();
  });

  it('uses an explicit legal picker replacement with its stable identity and requested quantity', async () => {
    vi.mocked(clientOrderService.previewReorder).mockImplementation(async (_source, selections) => response(preview({ unavailable: true, selections })));
    const product: ClientProduct = { id: 'product', name: 'Chosen replacement', category: null, in_stock: true,
      stock_level: 'HIGH', can_order: true, unit_count: 1, units: [{ sellable_unit_id: REPLACEMENT, sku_code: 'NEW-BOX',
        unit: 'box', package_quantity: 6, price: '110.00', currency: 'KES', can_order: true, in_stock: true, stock_level: 'HIGH' }] };
    vi.mocked(clientProductService.getAll).mockResolvedValue(response({ items: [product] }));
    mount();
    fireEvent.click(await screen.findByRole('button', { name: 'Choose replacement for line 2' }));
    fireEvent.click(await screen.findByTestId('replacement-unit-NEW-BOX'));
    expect(screen.getByText(/Decision: explicit replacement/)).toBeInTheDocument();
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Requested replacement quantity' }), { target: { value: '3' } });
    await reviewAndAccept();
    await waitFor(() => expect(clientOrderService.submitReorder).toHaveBeenCalledTimes(1));
    const selection = vi.mocked(clientOrderService.submitReorder).mock.calls[0][1].selections[1];
    expect(selection).toEqual({ source_item_id: 'line-02', action: 'replace', sellable_unit_id: REPLACEMENT, quantity: 3 });
  });

  it('keeps quantity 10 with a stock warning and does not expose exact availability', async () => {
    vi.mocked(clientOrderService.previewReorder).mockResolvedValue(response(preview({ quantity: 10, stockWarning: true, total: '1000.00' })));
    mount();
    expect(await screen.findByText(/keeps your full request/)).toBeInTheDocument();
    expect(screen.getByText(/requested quantity 10/)).toBeInTheDocument();
    expect(screen.queryByText(/available quantity|stock: 6/i)).toBeNull();
    await reviewAndAccept();
    await waitFor(() => expect(clientOrderService.submitReorder).toHaveBeenCalled());
    expect(vi.mocked(clientOrderService.submitReorder).mock.calls[0][1].selections).toEqual([{ source_item_id: 'line-01', action: 'keep' }]);
  });

  it('locks choices on unknown network and retries the exact source, selections, quote and key', async () => {
    vi.mocked(clientOrderService.submitReorder).mockRejectedValueOnce(new Error('network'));
    mount();
    await reviewAndAccept();
    await screen.findByRole('button', { name: 'Retry same accepted submission' });
    expect(screen.getByRole('button', { name: 'Remove line 1' })).toBeDisabled();
    expect(screen.getByRole('textbox', { name: 'Notes for the new draft (optional)' })).toBeDisabled();
    const first = vi.mocked(clientOrderService.submitReorder).mock.calls[0];
    const stored = JSON.parse(sessionStorage.getItem(storageKey)!);
    expect(stored.key).toBe(first[2]);
    expect(stored.source_order_id).toBe(SOURCE);
    fireEvent.click(screen.getByRole('button', { name: 'Retry same accepted submission' }));
    await waitFor(() => expect(clientOrderService.submitReorder).toHaveBeenCalledTimes(2));
    expect(vi.mocked(clientOrderService.submitReorder).mock.calls[1]).toEqual(first);
    expect(sessionStorage.getItem(storageKey)).toBeNull();
  });

  it('restores the unknown accepted request after a fresh authorized preview and retries the original key', async () => {
    sessionStorage.setItem(storageKey, JSON.stringify({ version: 1, source_order_id: SOURCE,
      selections: [{ source_item_id: 'line-01', action: 'keep' }], notes: 'original intent', quote: quote(), key: 'original-key' }));
    mount();
    fireEvent.click(await screen.findByRole('button', { name: 'Retry same accepted submission' }));
    await waitFor(() => expect(clientOrderService.submitReorder).toHaveBeenCalledTimes(1));
    expect(clientOrderService.previewReorder).toHaveBeenCalledWith(SOURCE, [{ source_item_id: 'line-01', action: 'keep' }]);
    expect(clientOrderService.submitReorder).toHaveBeenCalledWith(SOURCE, {
      selections: [{ source_item_id: 'line-01', action: 'keep' }], notes: 'original intent', quote_token: quote().quote_token,
    }, 'original-key');
  });

  it('clears an accepted cache after neutral source denial and exposes no cached quote', async () => {
    sessionStorage.setItem(storageKey, JSON.stringify({ version: 1, source_order_id: SOURCE,
      selections: [{ source_item_id: 'line-01', action: 'keep' }], notes: '', quote: quote(), key: 'denied-key' }));
    vi.mocked(clientOrderService.previewReorder).mockRejectedValue({ response: { status: 404 } });
    mount();
    expect(await screen.findByText('Order not found or no longer available.')).toBeInTheDocument();
    expect(screen.queryByText('Server total: KES 220.00')).toBeNull();
    expect(sessionStorage.getItem(storageKey)).toBeNull();
    expect(clientOrderService.submitReorder).not.toHaveBeenCalled();
  });

  it('refreshes source rows after economic stale and requires another explicit acceptance', async () => {
    vi.mocked(clientOrderService.submitReorder).mockRejectedValueOnce({ response: { status: 409,
      data: { code: 'REORDER_PREVIEW_STALE', details: { old_total: '220.00', new_total: '240.00', delta: '20.00', quote: quote('240.00') } } } });
    vi.mocked(clientOrderService.previewReorder).mockResolvedValueOnce(response(preview()))
      .mockResolvedValueOnce(response(preview())).mockResolvedValueOnce(response(preview({ total: '240.00' })));
    mount();
    await reviewAndAccept();
    await screen.findByText('Server total: KES 240.00');
    expect(clientOrderService.previewReorder).toHaveBeenCalledTimes(3);
    expect(clientOrderService.submitReorder).toHaveBeenCalledTimes(1);
    expect(sessionStorage.getItem(storageKey)).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Accept these prices and create draft' }));
    await waitFor(() => expect(clientOrderService.submitReorder).toHaveBeenCalledTimes(2));
    expect(vi.mocked(clientOrderService.submitReorder).mock.calls[1][1].quote_token).toBe(quote('240.00').quote_token);
  });

  it('prevents accepting the supplied stale quote when refreshed rows have become unavailable', async () => {
    vi.mocked(clientOrderService.submitReorder).mockRejectedValueOnce({ response: { status: 409,
      data: { code: 'REORDER_PREVIEW_STALE', details: { old_total: '220.00', new_total: '240.00', delta: '20.00', quote: quote('240.00') } } } });
    const unavailable = preview();
    unavailable.rows[0] = { ...unavailable.rows[0], current: null, status: 'UNAVAILABLE', reason: 'SELLABLE_UNIT_UNAVAILABLE' };
    unavailable.ready = false; unavailable.quote = null; unavailable.current_total = null; unavailable.delta = null;
    vi.mocked(clientOrderService.previewReorder).mockResolvedValueOnce(response(preview()))
      .mockResolvedValueOnce(response(preview())).mockResolvedValueOnce(response(unavailable));
    mount();
    await reviewAndAccept();
    await screen.findByText('SELLABLE_UNIT_UNAVAILABLE');
    expect(screen.queryByRole('button', { name: 'Accept these prices and create draft' })).toBeNull();
    expect(clientOrderService.submitReorder).toHaveBeenCalledTimes(1);
  });

  it('refreshes the unavailable reason after a fresh submit rejects a changed unit', async () => {
    vi.mocked(clientOrderService.submitReorder).mockRejectedValueOnce({ response: { status: 409,
      data: { code: 'REORDER_SELECTION_UNAVAILABLE', message: 'The historical unit cannot be reused with a changed definition',
        details: { source_item_id: 'line-01', reason: 'PACKAGING_IDENTITY_CHANGED' } } } });
    const unavailable = preview();
    unavailable.rows[0] = { ...unavailable.rows[0], current: null, status: 'UNAVAILABLE', reason: 'PACKAGING_IDENTITY_CHANGED' };
    unavailable.ready = false; unavailable.quote = null; unavailable.current_total = null; unavailable.delta = null;
    vi.mocked(clientOrderService.previewReorder).mockResolvedValueOnce(response(preview()))
      .mockResolvedValueOnce(response(preview())).mockResolvedValueOnce(response(unavailable));
    mount();
    await reviewAndAccept();
    await screen.findByText('PACKAGING_IDENTITY_CHANGED');
    expect(screen.queryByRole('button', { name: 'Accept these prices and create draft' })).toBeNull();
    expect(clientOrderService.submitReorder).toHaveBeenCalledTimes(1);
    expect(sessionStorage.getItem(storageKey)).toBeNull();
  });

  it('sends only once during a rapid double acceptance', async () => {
    let resolve!: (value: never) => void;
    vi.mocked(clientOrderService.submitReorder).mockImplementation(() => new Promise(done => { resolve = done; }));
    mount();
    fireEvent.click(await screen.findByRole('button', { name: 'Review server quote' }));
    const accept = await screen.findByRole('button', { name: 'Accept these prices and create draft' });
    fireEvent.click(accept); fireEvent.click(accept);
    expect(clientOrderService.submitReorder).toHaveBeenCalledTimes(1);
    await act(async () => { resolve(response({ id: 'new-draft' })); });
  });
});
