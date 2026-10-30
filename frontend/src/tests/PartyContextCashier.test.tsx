import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import DeclarationQueuePage from '@/pages/finance/DeclarationQueuePage';
import { listDeclarations, confirmDeclaration } from '@/services/declarationService';
import { getCashierReviewContext } from '@/services/partyContextService';
import { financeService } from '@/services/financeService';
import { getCashierDeclarationPrint } from '@/services/declarationService';
import { useAuthStore } from '@/stores/authStore';
import type { PaymentDeclaration } from '@/types/declaration';
import type { CashierReviewContext } from '@/types/partyContext';

vi.mock('@/services/declarationService', () => ({ listDeclarations: vi.fn(), confirmDeclaration: vi.fn(), rejectDeclaration: vi.fn(), getCashierDeclarationPrint: vi.fn() }));
vi.mock('@/services/partyContextService', () => ({ getCashierReviewContext: vi.fn() }));
vi.mock('@/services/financeService', () => ({ financeService: { getInvoice: vi.fn() } }));
const first: PaymentDeclaration = { id: 'dec-one', order_id: 'order-one', declared_amount: '25.50', currency: 'KES', currency_status: 'KNOWN', method: 'cash', status: 'pending', submitted_at: '2026-10-30T00:00:00Z' };
const second: PaymentDeclaration = { ...first, id: 'dec-two', order_id: 'order-two' };
function data(row = first): CashierReviewContext {
  const user = useAuthStore.getState().user!;
  return { context: { user_id: user.id, tenant_id: user.tenant_id! },
    declaration: { id: row.id, order_id: row.order_id, status: 'pending', declared_amount: row.declared_amount, method: row.method, transfer_reference: row.transfer_reference ?? null },
    order: { id: row.order_id, status: 'confirmed' },
    supplier: { id: user.tenant_id!, code: 'PORTAL', name: 'Supplier', name_resolution: 'RESOLVED' },
    retailer: { id: 'retailer-one', name: 'Retailer', name_resolution: 'RESOLVED' },
    binding: { id: 'binding-one', status: 'active' },
    money: { currency: 'KES', currency_status: 'KNOWN', balance_due: '60.10', balance_status: 'VERIFIED' },
    review_state: 'READY', reason_codes: [], observed_at: '2026-10-30T00:00:00Z' };
}
const response = (d: CashierReviewContext) => ({ success: true, data: d, timestamp: d.observed_at });
function mount() { return render(<MemoryRouter><DeclarationQueuePage /></MemoryRouter>); }
async function open(id = first.id) {
  fireEvent.click(within(await screen.findByRole('article', { name: `Declaration ${id}` })).getByRole('button', { name: 'Review payment' }));
}
function deferred<T>() {
  let resolve!: (value: T) => void; let reject!: (value: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
beforeEach(() => {
  vi.resetAllMocks(); sessionStorage.clear();
  useAuthStore.setState({ accessToken: 'synthetic-session', sessionGeneration: 0,
    user: { id: 'cashier', tenant_id: 'tenant', tenant_schema: 't_test', full_name: 'Personal name', email: null, roles: ['staff_finance'], permissions: ['payments:read', 'payments:confirm_declaration'] } });
  vi.mocked(listDeclarations).mockResolvedValue({ success: true, data: { items: [first, second], pagination: { pages: 1 } }, timestamp: 't' } as never);
  vi.mocked(getCashierReviewContext).mockImplementation(async id => response(data(id === second.id ? second : first)));
  vi.mocked(confirmDeclaration).mockResolvedValue({ data: { id: 'response-only' } } as never);
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe('Current cashier read authority', () => {
  it('read-only without orders:read uses just the new GET and cannot confirm', async () => {
    useAuthStore.setState({ user: { ...useAuthStore.getState().user!, permissions: ['payments:read'] } });
    mount(); await open();
    expect(await screen.findByText('You can review this payment, but cannot confirm it.')).toBeInTheDocument();
    const region = screen.getByRole('region', { name: 'Payment review' });
    expect(within(region).getByText('Supplier', { selector: 'dd' })).toBeInTheDocument();
    expect(within(region).getByText('Retailer')).toBeInTheDocument();
    expect(within(region).getByText('KES 60.10')).toBeInTheDocument();
    expect(within(region).getByText('binding-one')).toBeInTheDocument();
    expect(getCashierReviewContext).toHaveBeenCalledWith(first.id, expect.any(AbortSignal));
    expect(financeService.getInvoice).not.toHaveBeenCalled(); expect(getCashierDeclarationPrint).not.toHaveBeenCalled();
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument(); expect(confirmDeclaration).not.toHaveBeenCalled();
  });
  it('confirm-only cannot borrow read permission or issue a context GET', async () => {
    useAuthStore.setState({ user: { ...useAuthStore.getState().user!, permissions: ['payments:confirm_declaration'] } });
    mount(); await open(); await screen.findByText(/Payment review permission is required/);
    expect(getCashierReviewContext).not.toHaveBeenCalled(); expect(confirmDeclaration).not.toHaveBeenCalled();
  });
  it('current READY plus manual check sends exactly one original POST and uses response receipt id', async () => {
    const post = deferred<never>(); vi.mocked(confirmDeclaration).mockReturnValue(post.promise);
    mount(); await open(); const check = await screen.findByRole('checkbox');
    expect(screen.getByRole('button', { name: 'Confirm' })).toBeDisabled();
    fireEvent.click(check); fireEvent.click(screen.getByRole('button', { name: 'Confirm' })); fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    expect(confirmDeclaration).toHaveBeenCalledTimes(1); expect(confirmDeclaration).toHaveBeenCalledWith(first.id);
    await act(async () => post.resolve({ data: { id: 'response/only receipt' } } as never));
    expect(await screen.findByTestId('confirmed-receipt-link')).toHaveAttribute('href', '/declarations/response%2Fonly%20receipt/receipt');
  });
  it.each(['UGX', 'large KES', 'zero', 'null', 'unsupported', 'missing name', 'not actionable'])('renders %s without float reconstruction or blind confirmation', async mode => {
    const row = { ...first }; const ctx = data();
    let display = 'KES 60.10';
    if (mode === 'UGX') { row.currency = 'UGX'; row.declared_amount = '25'; ctx.declaration.declared_amount = '25'; ctx.money.currency = 'UGX'; ctx.money.balance_due = '9007199254740993'; display = 'UGX 9007199254740993'; }
    if (mode === 'large KES') { ctx.money.balance_due = '9007199254740993.10'; display = 'KES 9007199254740993.10'; }
    if (mode === 'zero') { ctx.money.balance_due = '0.00'; ctx.review_state = 'NOT_ACTIONABLE'; ctx.reason_codes = ['NO_REMAINING_BALANCE']; display = 'KES 0.00'; }
    if (mode === 'null' || mode === 'unsupported') { ctx.money = { currency: null, currency_status: mode === 'null' ? 'LEGACY_CURRENCY_UNVERIFIED' : 'UNSUPPORTED', balance_due: null, balance_status: 'UNVERIFIED' }; ctx.review_state = 'UNRESOLVED'; ctx.reason_codes = ['CURRENCY_UNVERIFIED']; display = 'Balance not verified'; }
    if (mode === 'missing name') { ctx.retailer = { ...ctx.retailer, name: null, name_resolution: 'MISSING' }; ctx.review_state = 'UNRESOLVED'; ctx.reason_codes = ['NAME_UNRESOLVED']; }
    if (mode === 'not actionable') { ctx.review_state = 'NOT_ACTIONABLE'; ctx.reason_codes = ['DECLARATION_NOT_PENDING']; }
    vi.mocked(listDeclarations).mockResolvedValue({ data: { items: [row], pagination: { pages: 1 } } } as never);
    vi.mocked(getCashierReviewContext).mockResolvedValue(response(ctx)); mount(); await open();
    const region = await screen.findByRole('region', { name: 'Payment review' });
    expect(await within(region).findByText(display)).toBeInTheDocument();
    if (!['UGX', 'large KES'].includes(mode)) expect(screen.queryByRole('button', { name: 'Confirm' })).not.toBeInTheDocument();
    expect(confirmDeclaration).not.toHaveBeenCalled();
  });
  it.each(['user', 'tenant', 'supplier', 'declaration', 'order', 'binding', 'missing money', 'numeric balance', 'missing observed'])('rejects malformed or mismatched %s with no fallback', async field => {
    const ctx = data();
    if (field === 'user') ctx.context.user_id = 'other';
    if (field === 'tenant') ctx.context.tenant_id = 'other';
    if (field === 'supplier') ctx.supplier.id = 'other';
    if (field === 'declaration') ctx.declaration.id = 'other';
    if (field === 'order') ctx.order.id = 'other';
    if (field === 'binding') ctx.binding.id = '';
    if (field === 'missing money') delete (ctx as Partial<CashierReviewContext>).money;
    if (field === 'numeric balance') (ctx.money as unknown as { balance_due: unknown }).balance_due = 60.1;
    if (field === 'missing observed') ctx.observed_at = '';
    vi.mocked(getCashierReviewContext).mockResolvedValue(response(ctx)); mount(); await open(); await screen.findByRole('alert');
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument(); expect(confirmDeclaration).not.toHaveBeenCalled();
    expect(financeService.getInvoice).not.toHaveBeenCalled(); expect(getCashierDeclarationPrint).not.toHaveBeenCalled();
  });
  it.each([403, 404, 409])('refresh refusal %s clears the old manual check and reopens unchecked only on explicit retry', async status => {
    mount(); await open(); fireEvent.click(await screen.findByRole('checkbox'));
    vi.mocked(getCashierReviewContext).mockRejectedValueOnce({ response: { status } });
    fireEvent.click(screen.getByRole('button', { name: 'Refresh review' })); await screen.findByRole('alert');
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument(); expect(confirmDeclaration).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Refresh review' }));
    expect(await screen.findByRole('checkbox')).not.toBeChecked(); expect(screen.getByRole('button', { name: 'Confirm' })).toBeDisabled();
  });
  it.each(['success', 'failure'])('discards out-of-order selection %s and aborts its transport', async mode => {
    const old = deferred<ReturnType<typeof response>>(); const previous = data();
    previous.retailer.name = 'Old customer';
    vi.mocked(getCashierReviewContext).mockReturnValueOnce(old.promise);
    mount(); await open(first.id); await open(second.id); await screen.findByRole('checkbox');
    expect(vi.mocked(getCashierReviewContext).mock.calls[0][1]?.aborted).toBe(true);
    await act(async () => { if (mode === 'success') old.resolve(response(previous)); else old.reject({ response: { status: 409 } }); });
    expect(screen.queryByText('Old customer')).not.toBeInTheDocument(); expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByRole('checkbox')).not.toBeChecked(); expect(confirmDeclaration).not.toHaveBeenCalled();
  });
  it.each(['account', 'tenant', 'generation', 'permission'])('clears checked review on %s change', async axis => {
    mount(); await open(); fireEvent.click(await screen.findByRole('checkbox'));
    act(() => { const state = useAuthStore.getState();
      useAuthStore.setState(axis === 'generation' ? { sessionGeneration: state.sessionGeneration + 1 } :
        { user: { ...state.user!, ...(axis === 'account' ? { id: 'new-user' } : axis === 'tenant' ? { tenant_id: 'new-tenant' } : { permissions: [] }) } });
    });
    await screen.findByRole('article', { name: 'Declaration dec-one' });
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument(); expect(confirmDeclaration).not.toHaveBeenCalled();
  });
  it.each(['account', 'tenant', 'generation', 'logout'])('discards a late old response after %s invalidates its owner', async axis => {
    const old = deferred<ReturnType<typeof response>>(); const previous = data(); previous.retailer.name = 'Stale identity';
    vi.mocked(getCashierReviewContext).mockReturnValueOnce(old.promise);
    mount(); await open();
    act(() => { const s = useAuthStore.getState();
      if (axis === 'logout') s.logout();
      else useAuthStore.setState(axis === 'generation' ? { sessionGeneration: s.sessionGeneration + 1 }
        : { user: { ...s.user!, ...(axis === 'account' ? { id: 'new-user' } : { tenant_id: 'new-tenant' }) } });
    });
    await act(async () => old.resolve(response(previous)));
    expect(screen.queryByText('Stale identity')).not.toBeInTheDocument();
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument(); expect(confirmDeclaration).not.toHaveBeenCalled();
  });
  it('does not accept a failed envelope even if its data looks complete', async () => {
    vi.mocked(getCashierReviewContext).mockResolvedValue({ ...response(data()), success: false } as never);
    mount(); await open(); await screen.findByRole('alert');
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument(); expect(confirmDeclaration).not.toHaveBeenCalled();
  });
  it('a zero balance does not become confirmation permission even with a contradictory READY flag', async () => {
    const c = data(); c.money.balance_due = '0.00';
    vi.mocked(getCashierReviewContext).mockResolvedValue(response(c)); mount(); await open();
    await screen.findByText('KES 0.00'); expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
    expect(confirmDeclaration).not.toHaveBeenCalled();
  });
  it('confirmation refusal re-reads, clears check and never automatically resends a write', async () => {
    vi.mocked(confirmDeclaration).mockRejectedValue({ response: { status: 409 } });
    mount(); await open(); fireEvent.click(await screen.findByRole('checkbox')); fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    await screen.findByText(/no payment was automatically resent/);
    expect(confirmDeclaration).toHaveBeenCalledTimes(1); expect(getCashierReviewContext).toHaveBeenCalledTimes(2);
    expect(screen.getByRole('checkbox')).not.toBeChecked(); expect(screen.getByRole('button', { name: 'Confirm' })).toBeDisabled();
  });
  it('historical bad-precision review 409 preserves display and clears any old confirmation without a POST', async () => {
    const historic = { ...second, declared_amount: '100.000001', currency: 'UGX' };
    vi.mocked(listDeclarations).mockResolvedValue({ data: { items: [first, historic], pagination: { pages: 1 } } } as never);
    mount(); await open(); fireEvent.click(await screen.findByRole('checkbox'));
    vi.mocked(getCashierReviewContext).mockRejectedValueOnce({ response: { status: 409, data: { error: { code: 'REVIEW_CONTEXT_INTEGRITY' } } } });
    await open(historic.id); await screen.findByRole('alert');
    expect(within(screen.getByRole('article', { name: 'Declaration dec-two' })).getByText('UGX 100.000001 · cash')).toBeInTheDocument();
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument(); expect(screen.queryByRole('button', { name: 'Confirm' })).not.toBeInTheDocument();
    expect(confirmDeclaration).not.toHaveBeenCalled();
  });
});
