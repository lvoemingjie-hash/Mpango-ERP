import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { DashboardPage } from '@/pages/DashboardPage';
import { ProductListPage } from '@/pages/client/ProductListPage';
import DeclarationQueuePage from '@/pages/finance/DeclarationQueuePage';
import { Modal } from '@/components/ui/Modal';
import { useAuthStore } from '@/stores/authStore';
import { dashboardService } from '@/services/dashboardService';
import { orderService } from '@/services/orderService';
import { inventoryService } from '@/services/inventoryService';
import { clientProductService } from '@/services/clientProductService';
import { listDeclarations, getCashierDeclarationPrint, confirmDeclaration } from '@/services/declarationService';
import { financeService } from '@/services/financeService';
import { getCashierReviewContext } from '@/services/partyContextService';
vi.mock('@/services/dashboardService', () => ({ dashboardService: { getKpiSummary: vi.fn(), getSalesTrend: vi.fn() } }));
vi.mock('@/services/orderService', () => ({ orderService: { getAll: vi.fn() } }));
vi.mock('@/services/inventoryService', () => ({ inventoryService: { getStocks: vi.fn() } }));
vi.mock('@/services/clientProductService', () => ({ clientProductService: { getAll: vi.fn() } }));
vi.mock('@/services/declarationService', () => ({ listDeclarations: vi.fn(), getCashierDeclarationPrint: vi.fn(), confirmDeclaration: vi.fn(), rejectDeclaration: vi.fn() }));
vi.mock('@/services/financeService', () => ({ financeService: { getInvoice: vi.fn() } }));
vi.mock('@/services/partyContextService', () => ({ getCashierReviewContext: vi.fn() }));
const row = { id: 'declaration-one', order_id: 'order-full-identity', declared_amount: '25.50', currency: 'KES', currency_status: 'KNOWN', method: 'transfer', transfer_reference: 'SYNTHETIC-TRANSFER', status: 'pending', submitted_at: '2026-10-29T00:00:00Z' };
const reviewContext = {
  context: { user_id: 'cashier-one', tenant_id: 'tenant-one' },
  declaration: { id: row.id, order_id: row.order_id, status: 'pending', declared_amount: row.declared_amount, method: row.method, transfer_reference: row.transfer_reference },
  order: { id: row.order_id, status: 'confirmed' },
  retailer: { id: 'retailer-one', name: 'Synthetic customer', name_resolution: 'RESOLVED' },
  supplier: { id: 'tenant-one', code: 'PORTAL', name: 'Synthetic supplier', name_resolution: 'RESOLVED' },
  binding: { id: 'binding-one', status: 'active' },
  money: { currency: 'KES', currency_status: 'KNOWN', balance_due: '125.50', balance_status: 'VERIFIED' },
  review_state: 'READY', reason_codes: [], observed_at: '2026-10-30T00:00:00Z',
};
const envelope = (data: unknown) => ({ data: { data } } as never);
function mount(element: React.ReactNode) { return render(<MemoryRouter>{element}</MemoryRouter>); }
function catalog(name = 'Current product', pages = 3, items = true) {
  return envelope({ items: items ? [{ id: name, name, can_order: true, stock_level: 'HIGH', unit_count: 2, units: [
    { sellable_unit_id: 'closed', sku_code: 'CLOSED', unit: 'case', package_quantity: 12, can_order: false, price: '1.00', currency: 'UGX' },
    { sellable_unit_id: 'ready', sku_code: 'READY', unit: 'bottle', package_quantity: 1, can_order: true, price: '25.50', currency: 'KES' },
  ] }] : [], pagination: { pages } });
}
beforeEach(() => {
  vi.resetAllMocks(); sessionStorage.clear();
  useAuthStore.setState({ accessToken: 'synthetic-session', user: { id: 'cashier-one', tenant_id: 'tenant-one', tenant_schema: 't_one', email: null, full_name: 'Synthetic', roles: ['staff_finance'], permissions: ['payments:read', 'orders:read', 'payments:confirm_declaration'] } });
  vi.mocked(dashboardService.getKpiSummary).mockResolvedValue(envelope({ cards: [{ label: 'Cash received', value: 10, currency: 'KES' }], currency: 'KES' }));
  vi.mocked(dashboardService.getSalesTrend).mockResolvedValue(envelope({ data: [{ date: '2026-10-29', value: 20, currency: 'UGX' }], currency: 'UGX' }));
  vi.mocked(orderService.getAll).mockResolvedValue(envelope({ items: [{ id: 'current-order', retailer_name: 'Visible customer', total_amount: 30, currency: 'UGX', status: 'confirmed' }] }));
  vi.mocked(inventoryService.getStocks).mockResolvedValue(envelope({ items: [] }));
  vi.mocked(clientProductService.getAll).mockResolvedValue(catalog());
  vi.mocked(listDeclarations).mockResolvedValue({ data: { items: [row], pagination: { pages: 1 } } } as never);
  vi.mocked(getCashierReviewContext).mockResolvedValue({ success: true, data: reviewContext, timestamp: reviewContext.observed_at } as never);
  vi.mocked(confirmDeclaration).mockResolvedValue({ data: { id: 'response-only-receipt' } } as never);
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe('Mac dashboard partial failure', () => {
  it('retains successful orders and trend on summary permission denial and retries only that section', async () => {
    vi.mocked(dashboardService.getKpiSummary).mockRejectedValueOnce({ response: { status: 403 } });
    mount(<DashboardPage />);
    expect(await screen.findByText('Visible customer')).toBeInTheDocument();
    expect(screen.getByText('2026-10-29')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('Your role does not have access');
    expect(screen.getByText('UGX 30')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Retry Business summary' }));
    await screen.findByText('Cash received');
    expect(dashboardService.getKpiSummary).toHaveBeenCalledTimes(2);
    expect(dashboardService.getSalesTrend).toHaveBeenCalledTimes(1);
    expect(orderService.getAll).toHaveBeenCalledTimes(1);
    expect(inventoryService.getStocks).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
  it('does not block successful sections behind a slow stock request', async () => {
    vi.mocked(inventoryService.getStocks).mockReturnValue(new Promise(() => {}));
    mount(<DashboardPage />);
    await screen.findByText('Visible customer');
    expect(screen.getByText('Cash received')).toBeInTheDocument();
    expect(screen.getByText('Loading Stock…')).toBeInTheDocument();
  });
  it('offers setup links only for current permissions', async () => {
    mount(<DashboardPage />); await screen.findByText('Visible customer');
    const guide = screen.getByRole('region', { name: 'Getting started' });
    expect(within(guide).getByRole('link', { name: /Review orders/ })).toHaveAttribute('href', '/orders');
    expect(within(guide).queryByRole('link', { name: /Invite/ })).not.toBeInTheDocument();
  });
});

describe('Mac product query ownership', () => {
  it('starts a new search from page one after page three and Enter does not duplicate the request', async () => {
    mount(<ProductListPage />); await screen.findByText('Page 1 of 3');
    fireEvent.click(screen.getByRole('button', { name: 'Next' })); await screen.findByText('Page 2 of 3');
    fireEvent.click(screen.getByRole('button', { name: 'Next' })); await screen.findByText('Page 3 of 3');
    fireEvent.change(screen.getByLabelText('Search products'), { target: { value: 'juice' } });
    await screen.findByText('Page 1 of 3');
    expect(clientProductService.getAll).toHaveBeenLastCalledWith(1, 20, { search: 'juice' });
    const count = vi.mocked(clientProductService.getAll).mock.calls.length;
    fireEvent.submit(screen.getByLabelText('Search products').closest('form')!);
    expect(clientProductService.getAll).toHaveBeenCalledTimes(count);
  });
  it.each(['success', 'failure'])('ignores an old query %s arriving after the current result', async mode => {
    mount(<ProductListPage />); await screen.findByText('Current product');
    let settle!: (value: never) => void;
    vi.mocked(clientProductService.getAll).mockImplementationOnce(() => new Promise((resolve, reject) => { settle = mode === 'success' ? resolve : reject; }))
      .mockResolvedValueOnce(catalog('Fresh product'));
    fireEvent.change(screen.getByLabelText('Search products'), { target: { value: 'old' } });
    fireEvent.change(screen.getByLabelText('Search products'), { target: { value: 'fresh' } });
    await screen.findByText('Fresh product');
    await act(async () => settle((mode === 'success' ? catalog('Old result') : new Error('old failure')) as never));
    expect(screen.getByText('Fresh product')).toBeInTheDocument();
    expect(screen.queryByText('Old result')).not.toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
  it('distinguishes empty search, clear, error and retry; main price uses its own packaging and currency', async () => {
    mount(<ProductListPage />); await screen.findByText('Current product');
    expect(screen.getByText('KES 25.50')).toBeInTheDocument();
    expect(screen.getByText('per 1 × bottle')).toBeInTheDocument();
    expect(screen.queryByText(/UGX 25.50/)).not.toBeInTheDocument();
    vi.mocked(clientProductService.getAll).mockResolvedValueOnce(catalog('', 0, false));
    fireEvent.change(screen.getByLabelText('Search products'), { target: { value: 'absent' } });
    await screen.findByText('No matching products');
    vi.mocked(clientProductService.getAll).mockResolvedValueOnce(catalog('', 0, false));
    fireEvent.click(screen.getByText('Clear search')); await screen.findByText('No products available');
    vi.mocked(clientProductService.getAll).mockRejectedValueOnce(new Error('offline'));
    fireEvent.change(screen.getByLabelText('Search products'), { target: { value: 'retry' } }); await screen.findByRole('alert');
    fireEvent.click(screen.getByText('Retry products')); await screen.findByText('Current product');
  });
});

async function review() {
  mount(<DeclarationQueuePage />);
  fireEvent.click(await screen.findByRole('button', { name: 'Review payment' }));
}
describe('Mac cashier deliberate review', () => {
  it('requires customer, complete order, amount, currency, reference, receivable and explicit receipt verification before one confirmation', async () => {
    await review();
    const checkbox = await screen.findByRole('checkbox');
    const region = screen.getByRole('region', { name: 'Payment review' });
    for (const value of ['Synthetic customer', 'order-full-identity', 'KES 25.50', 'KES 125.50']) expect(within(region).getByText(value)).toBeInTheDocument();
    expect(within(region).getByText('transfer / SYNTHETIC-TRANSFER')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirm' })).toBeDisabled();
    expect(confirmDeclaration).not.toHaveBeenCalled();
    fireEvent.click(checkbox);
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    fireEvent.click(screen.getByRole('button', { name: /Confirm/ }));
    expect(await screen.findByTestId('confirmed-receipt-link')).toHaveAttribute('href', '/declarations/response-only-receipt/receipt');
    expect(confirmDeclaration).toHaveBeenCalledTimes(1);
    expect(confirmDeclaration).toHaveBeenCalledWith(row.id);
  });
  it.each(['missing customer', 'wrong order', 'wrong currency', 'missing balance', 'unsafe balance', 'unknown currency', 'read error'])('blocks confirmation for %s', async scenario => {
    const data = structuredClone(reviewContext) as Record<string, any>;
    if (scenario === 'missing customer') { data.retailer = { ...data.retailer, name: null, name_resolution: 'MISSING' }; data.review_state = 'UNRESOLVED'; data.reason_codes = ['NAME_UNRESOLVED']; }
    if (scenario === 'wrong order') data.order.id = 'another-order';
    if (scenario === 'wrong currency') data.money.currency = 'UGX';
    if (scenario === 'missing balance') delete data.money.balance_due;
    if (scenario === 'unsafe balance') data.money.balance_due = Number.MAX_VALUE;
    if (scenario === 'unknown currency') { data.money = { currency: null, currency_status: 'LEGACY_CURRENCY_UNVERIFIED', balance_due: null, balance_status: 'UNVERIFIED' }; data.review_state = 'UNRESOLVED'; data.reason_codes = ['CURRENCY_UNVERIFIED']; }
    vi.mocked(getCashierReviewContext).mockResolvedValue({ success: true, data, timestamp: reviewContext.observed_at } as never);
    if (scenario === 'read error') vi.mocked(getCashierReviewContext).mockRejectedValue({ response: { status: 403 } });
    await review(); await screen.findByRole('alert');
    expect(screen.queryByRole('button', { name: 'Confirm' })).not.toBeInTheDocument();
    expect(confirmDeclaration).not.toHaveBeenCalled();
  });
  it('does not request unavailable permissions and does not elevate the role', async () => {
    useAuthStore.setState({ user: { ...useAuthStore.getState().user!, permissions: ['payments:read', 'payments:confirm_declaration'] } });
    await review(); await screen.findByRole('checkbox');
    expect(getCashierReviewContext).toHaveBeenCalledTimes(1);
    expect(getCashierDeclarationPrint).not.toHaveBeenCalled(); expect(financeService.getInvoice).not.toHaveBeenCalled();
    expect(confirmDeclaration).not.toHaveBeenCalled();
  });
  it('does not reuse a cached receipt id when a later confirmation response omits it', async () => {
    await review(); fireEvent.click(await screen.findByRole('checkbox')); fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    await screen.findByTestId('confirmed-receipt-link');
    vi.mocked(confirmDeclaration).mockResolvedValue({ data: {} } as never);
    fireEvent.click(screen.getByRole('button', { name: 'Review payment' }));
    fireEvent.click(await screen.findByRole('checkbox')); fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    await screen.findByTestId('receipt-link-unavailable');
    expect(screen.queryByTestId('confirmed-receipt-link')).not.toBeInTheDocument();
  });
});

it('gives the modal icon close control a usable accessible name', async () => {
  const close = vi.fn(); mount(<Modal open onClose={close} title="Review"><p>Context</p></Modal>);
  fireEvent.click(await screen.findByRole('button', { name: 'Close dialog' }));
  expect(close).toHaveBeenCalledOnce();
});
