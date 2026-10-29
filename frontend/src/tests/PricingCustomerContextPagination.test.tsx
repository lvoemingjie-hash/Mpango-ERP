import { StrictMode } from 'react';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { RetailerPricingPage } from '@/pages/pricing/RetailerPricingPage';
import { retailerService, type RetailerWithBinding } from '@/services/retailerService';
import { pricingService } from '@/services/pricingService';
import type { RetailerPriceView } from '@/types/pricing';

const auth = vi.hoisted(() => ({ writable: true }));
vi.mock('@/stores/authStore', () => ({
  useAuthStore: (selector: (state: unknown) => unknown) => selector({
    user: { permissions: auth.writable ? ['pricing:write'] : [], roles: [] },
  }),
}));
vi.mock('@/services/retailerService', () => ({ retailerService: { getAll: vi.fn() } }));
vi.mock('@/services/pricingService', () => ({
  pricingService: { getPrices: vi.fn(), setPrice: vi.fn(), setBasePrice: vi.fn() },
}));

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function customer(id: string): RetailerWithBinding {
  return {
    retailer: { id, name: `Customer ${id}`, phone: '', email: null, address: null },
    binding_status: 'active', bound_at: '', join_source: 'invite',
  };
}
function customers(ids = ['A', 'B'], page = 1, total = ids.length) {
  return { data: { data: {
    items: ids.map(customer), pagination: { page, size: 100, total, pages: Math.ceil(total / 100) },
  } } };
}
function prices(id = 'A', override = '110', total = 1, retired = false, currency: 'UGX' | 'KES' = 'UGX') {
  const row: RetailerPriceView = {
    sku_id: 'shared-sku', sku_name: 'Shared grain', sku_code: 'GRAIN', retailer_id: id,
    base_price: '100', override_price: override, override_retired: retired, currency,
    price: retired ? '100' : override, price_source: retired ? 'BASE_PRICE' : 'CUSTOMER_PRICE',
    unorderable_reason: null, pricing_revision: 7, updated_at: null,
  };
  return { data: { data: { items: [row], total } } };
}
type PriceResponse = ReturnType<typeof prices>;
type CustomerResponse = ReturnType<typeof customers>;

async function settle<T>(pending: ReturnType<typeof deferred<T>>, result: T) {
  await act(async () => { pending.resolve(result); await pending.promise; });
}
async function refuse<T>(pending: ReturnType<typeof deferred<T>>, message: string) {
  await act(async () => { pending.reject(new Error(message)); await pending.promise.catch(() => undefined); });
}
async function selectCustomer(id: string) {
  await waitFor(() => expect(screen.getByRole('combobox', { name: 'Customer' })).toBeEnabled());
  await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Customer' }), id);
}
async function loaded() {
  await waitFor(() => expect(screen.getByRole('button', { name: 'Save customer price' })).toBeEnabled());
}
function customerNext() { return screen.getByRole('button', { name: 'Next customer page' }); }
function skuNext() { return screen.getByRole('button', { name: 'Next SKU page' }); }

beforeEach(() => {
  vi.resetAllMocks();
  auth.writable = true;
  vi.mocked(retailerService.getAll).mockResolvedValue(customers() as never);
  vi.mocked(pricingService.getPrices).mockImplementation(async id => prices(id, id === 'A' ? '110' : '220') as never);
  vi.mocked(pricingService.setPrice).mockResolvedValue({ data: { data: {} } } as never);
  vi.mocked(pricingService.setBasePrice).mockResolvedValue({ data: { data: {} } } as never);
});

describe('Pricing customer context and pagination', () => {
  it('UI01_STALE_SUCCESS keeps B rows and edited input when A finishes late with the same SKU revision', async () => {
    const old = deferred<PriceResponse>();
    vi.mocked(pricingService.getPrices).mockImplementation(async id => id === 'A' ? await old.promise as never : prices('B', '220') as never);
    render(<RetailerPricingPage />);
    await selectCustomer('A'); await selectCustomer('B'); await loaded();
    const input = screen.getByLabelText('Customer price value');
    await userEvent.clear(input); await userEvent.type(input, '222');
    await settle(old, prices('A', '110'));
    expect(screen.queryAllByText('UGX 110'), 'UI01_CURRENT_CUSTOMER_PRICE_ONLY').toHaveLength(0);
    expect(input).toHaveValue('222');
    await userEvent.click(screen.getByRole('button', { name: 'Save customer price' }));
    expect(pricingService.setPrice).toHaveBeenCalledWith({ sku_id: 'shared-sku', retailer_id: 'B', price: '222', expected_revision: 7 });
  });

  it('ignores A read error without disturbing B loading or permissions', async () => {
    const a = deferred<PriceResponse>(); const b = deferred<PriceResponse>();
    vi.mocked(pricingService.getPrices).mockImplementation(async id => await (id === 'A' ? a.promise : b.promise) as never);
    render(<RetailerPricingPage />);
    await selectCustomer('A'); await selectCustomer('B');
    await refuse(a, 'obsolete A failure');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Save customer price' })).not.toBeInTheDocument();
    await settle(b, prices('B', '220')); await loaded();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('ignores a late SKU page after returning to a newer first page', async () => {
    const oldPage = deferred<PriceResponse>();
    vi.mocked(pricingService.getPrices).mockImplementation(async (id, page) => page === 2 ? await oldPage.promise as never : prices(id, '110', 21) as never);
    render(<RetailerPricingPage />); await selectCustomer('A'); await loaded();
    await userEvent.click(skuNext());
    await userEvent.click(screen.getByRole('button', { name: 'Previous SKU page' })); await loaded();
    await settle(oldPage, prices('A', '999', 21));
    expect(screen.getByLabelText('Customer price value')).toHaveValue('110');
    expect(screen.queryAllByText('UGX 999')).toHaveLength(0);
  });

  it('resets SKU pagination on customer switch and does not reuse A editor or currency', async () => {
    const oldPage = deferred<PriceResponse>();
    vi.mocked(pricingService.getPrices).mockImplementation(async (id, page) => {
      if (id === 'B') return prices('B', '220', 1, false, 'KES') as never;
      return page === 2 ? await oldPage.promise as never : prices('A', '110', 21) as never;
    });
    render(<RetailerPricingPage />); await selectCustomer('A'); await loaded();
    await userEvent.click(skuNext()); await selectCustomer('B'); await loaded();
    expect(pricingService.getPrices).toHaveBeenLastCalledWith('B', 1, 20);
    await settle(oldPage, prices('A', '999', 21));
    expect(screen.getByLabelText('Customer price value')).toHaveValue('220');
    expect(screen.queryAllByText(/UGX/)).toHaveLength(0);
    const cells = screen.getAllByRole('cell');
    expect(cells[2]).toHaveTextContent('KES 220');
    expect(cells[3]).toHaveTextContent('KES 220');
  });

  it('preserves unsaved input across unrelated customer list rerenders', async () => {
    vi.mocked(retailerService.getAll).mockImplementation(async page => customers(page === 1 ? ['A', 'B'] : ['C'], page, 101) as never);
    render(<RetailerPricingPage />); await selectCustomer('A'); await loaded();
    const input = screen.getByLabelText('Customer price value');
    await userEvent.clear(input); await userEvent.type(input, '135');
    await userEvent.click(customerNext());
    await waitFor(() => expect(screen.getByRole('option', { name: 'Customer C' })).toBeInTheDocument());
    expect(screen.getByLabelText('Customer price value')).toHaveValue('135');
    expect(pricingService.getPrices).toHaveBeenCalledTimes(1);
  });

  it('an already started A save keeps its target and cannot reload B on completion', async () => {
    const save = deferred<unknown>();
    vi.mocked(pricingService.setPrice).mockReturnValue(save.promise as never);
    render(<RetailerPricingPage />); await selectCustomer('A'); await loaded();
    await userEvent.click(screen.getByRole('button', { name: 'Save customer price' }));
    await selectCustomer('B'); await loaded();
    await settle(save, {});
    expect(pricingService.setPrice).toHaveBeenCalledTimes(1);
    expect(pricingService.setPrice).toHaveBeenCalledWith({ retailer_id: 'A', sku_id: 'shared-sku', price: '110', expected_revision: 7 });
    expect(pricingService.getPrices).toHaveBeenCalledTimes(2);
    expect(screen.getByLabelText('Customer price value')).toHaveValue('220');
  });

  it('an obsolete save error cannot overwrite B and an active save error remains visible', async () => {
    const save = deferred<unknown>();
    vi.mocked(pricingService.setPrice).mockReturnValueOnce(save.promise as never).mockRejectedValueOnce(new Error('current B refusal'));
    render(<RetailerPricingPage />); await selectCustomer('A'); await loaded();
    await userEvent.click(screen.getByRole('button', { name: 'Save customer price' }));
    await selectCustomer('B'); await loaded(); await refuse(save, 'obsolete A write');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Save customer price' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('current B refusal');
    expect(pricingService.setPrice).toHaveBeenLastCalledWith({ retailer_id: 'B', sku_id: 'shared-sku', price: '220', expected_revision: 7 });
  });

  it('retire and restore bind customer, price and revision without replaying obsolete callbacks', async () => {
    const retire = deferred<unknown>();
    vi.mocked(pricingService.getPrices).mockImplementation(async id => prices(id, id === 'A' ? '110' : '220', 1, id === 'B') as never);
    vi.mocked(pricingService.setPrice).mockReturnValueOnce(retire.promise as never).mockResolvedValue({} as never);
    render(<RetailerPricingPage />); await selectCustomer('A'); await loaded();
    await userEvent.click(screen.getByRole('button', { name: 'Retire override' }));
    await selectCustomer('B'); await loaded(); await settle(retire, {});
    await userEvent.click(screen.getByRole('button', { name: 'Restore override' }));
    expect(vi.mocked(pricingService.setPrice).mock.calls).toEqual([
      [{ retailer_id: 'A', sku_id: 'shared-sku', price: '110', expected_revision: 7, retire: true }],
      [{ retailer_id: 'B', sku_id: 'shared-sku', price: '220', expected_revision: 7, retire: false }],
    ]);
  });

  it('unmount invalidates pending writes and reads without extra reloads', async () => {
    const save = deferred<unknown>(); const read = deferred<PriceResponse>();
    vi.mocked(pricingService.setBasePrice).mockReturnValue(save.promise as never);
    const view = render(<RetailerPricingPage />); await selectCustomer('A'); await loaded();
    await userEvent.click(screen.getByRole('button', { name: 'Save base price' }));
    vi.mocked(pricingService.getPrices).mockReturnValueOnce(read.promise as never);
    await selectCustomer('B'); view.unmount();
    await settle(save, {}); await settle(read, prices('B', '220'));
    expect(pricingService.getPrices).toHaveBeenCalledTimes(2);
    expect(pricingService.setBasePrice).toHaveBeenCalledTimes(1);
    expect(pricingService.setBasePrice).toHaveBeenCalledWith('shared-sku', '100', 7);
  });

  it('UI02_CUSTOMER_101 reaches the second customer page and preserves customer 100 until explicit selection', async () => {
    const first = Array.from({ length: 100 }, (_, i) => String(i + 1));
    vi.mocked(retailerService.getAll).mockImplementation(async page => customers(page === 1 ? first : ['101'], page, 101) as never);
    render(<RetailerPricingPage />); await selectCustomer('100'); await loaded();
    const next = screen.queryByRole('button', { name: 'Next customer page' });
    expect(next, 'UI02_SECOND_CUSTOMER_PAGE_REACHABLE').not.toBeNull();
    await userEvent.click(next!);
    await waitFor(() => expect(retailerService.getAll, 'UI02_REQUEST_PAGE_TWO').toHaveBeenCalledWith(2, 100));
    await waitFor(() => expect(screen.getByRole('option', { name: 'Customer 101' })).toBeInTheDocument());
    expect(screen.getByRole('combobox', { name: 'Customer' })).toHaveValue('100');
    expect(screen.getByRole('option', { name: 'Customer 100 (selected)' })).toBeInTheDocument();
    expect(pricingService.getPrices).toHaveBeenCalledTimes(1);
    await selectCustomer('101'); await loaded();
    expect(pricingService.getPrices).toHaveBeenLastCalledWith('101', 1, 20);
    expect(vi.mocked(retailerService.getAll).mock.calls).toEqual([[1, 100], [2, 100]]);
  });

  it('customer and SKU pagination are independent with explicit accessible controls', async () => {
    vi.mocked(retailerService.getAll).mockImplementation(async page => customers(page === 1 ? ['A'] : ['B'], page, 101) as never);
    vi.mocked(pricingService.getPrices).mockImplementation(async id => prices(id, '110', 21) as never);
    render(<RetailerPricingPage />); await selectCustomer('A'); await loaded();
    await userEvent.click(skuNext()); await loaded();
    await userEvent.click(customerNext());
    await waitFor(() => expect(screen.getByRole('option', { name: 'Customer B' })).toBeInTheDocument());
    expect(within(screen.getByRole('navigation', { name: 'SKU pagination' })).getByText('SKU page 2')).toBeInTheDocument();
    expect(pricingService.getPrices).toHaveBeenCalledTimes(2);
    await selectCustomer('B'); await loaded();
    expect(pricingService.getPrices).toHaveBeenLastCalledWith('B', 1, 20);
  });

  it('ignores stale customer page success after returning to page one', async () => {
    const old = deferred<CustomerResponse>();
    vi.mocked(retailerService.getAll).mockImplementation(async page => page === 2 ? await old.promise as never : customers(['A'], 1, 101) as never);
    render(<RetailerPricingPage />); await selectCustomer('A'); await loaded();
    await userEvent.click(customerNext());
    await userEvent.click(screen.getByRole('button', { name: 'Previous customer page' }));
    await waitFor(() => expect(screen.getByRole('combobox', { name: 'Customer' })).toBeEnabled());
    await settle(old, customers(['C'], 2, 101));
    expect(screen.queryByRole('option', { name: 'Customer C' })).not.toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Customer A' })).toBeInTheDocument();
    expect(pricingService.getPrices).toHaveBeenCalledTimes(1);
  });

  it('ignores stale customer page errors and exposes the current page error without changing selection', async () => {
    const old = deferred<CustomerResponse>();
    vi.mocked(retailerService.getAll).mockImplementation(async page => page === 2 ? await old.promise as never : customers(['A'], 1, 101) as never);
    render(<RetailerPricingPage />); await selectCustomer('A'); await loaded();
    await userEvent.click(customerNext());
    await userEvent.click(screen.getByRole('button', { name: 'Previous customer page' }));
    await waitFor(() => expect(screen.getByRole('combobox', { name: 'Customer' })).toBeEnabled());
    await refuse(old, 'obsolete customer page');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    vi.mocked(retailerService.getAll).mockRejectedValueOnce(new Error('current customer page'));
    await userEvent.click(customerNext());
    expect(await screen.findByRole('alert')).toHaveTextContent('current customer page');
    expect(screen.getByRole('combobox', { name: 'Customer' })).toHaveValue('A');
    expect(screen.getByLabelText('Customer price value')).toHaveValue('110');
  });

  it('empty customers and current read failures stay explicit with no available write', async () => {
    vi.mocked(retailerService.getAll).mockResolvedValueOnce(customers([]) as never);
    const view = render(<RetailerPricingPage />);
    expect(await screen.findByText('No customers found.')).toBeInTheDocument();
    expect(pricingService.getPrices).not.toHaveBeenCalled(); view.unmount();
    vi.mocked(pricingService.getPrices).mockRejectedValueOnce(new Error('current prices unavailable'));
    render(<RetailerPricingPage />); await selectCustomer('A');
    expect(await screen.findByRole('alert')).toHaveTextContent('current prices unavailable');
    expect(screen.queryByRole('button', { name: 'Save customer price' })).not.toBeInTheDocument();
    expect(pricingService.setPrice).not.toHaveBeenCalled();
  });

  it('read-only users can reach customer 101 but cannot save, retire or restore', async () => {
    auth.writable = false;
    vi.mocked(retailerService.getAll).mockImplementation(async page => customers(page === 1 ? ['A'] : ['101'], page, 101) as never);
    render(<RetailerPricingPage />);
    await waitFor(() => expect(customerNext()).toBeEnabled()); await userEvent.click(customerNext());
    await selectCustomer('101');
    await screen.findByLabelText('Customer price value');
    for (const name of ['Save base price', 'Save customer price', 'Retire override']) {
      const button = screen.getByRole('button', { name });
      expect(button).toBeDisabled(); await userEvent.click(button);
    }
    expect(pricingService.setBasePrice).not.toHaveBeenCalled(); expect(pricingService.setPrice).not.toHaveBeenCalled();
  });

  it('UI01_REQUEST_SEQUENCE rejects an older same-context request across StrictMode effect replay', async () => {
    const old = deferred<PriceResponse>();
    vi.mocked(pricingService.getPrices).mockReturnValueOnce(old.promise as never).mockResolvedValue(prices('A', '220') as never);
    render(<StrictMode><RetailerPricingPage /></StrictMode>);
    await selectCustomer('A'); await loaded();
    expect(pricingService.getPrices).toHaveBeenCalledTimes(2);
    await settle(old, prices('A', '999'));
    expect(screen.queryAllByText('UGX 999'), 'UI01_OBSOLETE_SEQUENCE_REJECTED').toHaveLength(0);
    expect(screen.getByLabelText('Customer price value')).toHaveValue('220');
  });
});
