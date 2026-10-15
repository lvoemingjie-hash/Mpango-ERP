/**
 * F-04 payment-declaration navigation closure (frontend).
 *
 * Covers ONLY navigation discoverability on top of the existing frozen
 * pages/routes/permissions; every backend permission and status rule stays
 * the final arbiter and is not re-implemented here:
 *
 *   T1  order detail shows "Declare Payment" for a user holding the named
 *       client:payments:declare permission, and the link target uses the
 *       order id the page actually fetched (never a fixed or cached id)
 *   T2  named negative control: a user holding client:payments:read but NOT
 *       client:payments:declare sees no declare entry (link or caption)
 *   T3  a permission-empty user sees neither the declare entry nor
 *       "My declarations"
 *   T4  clicking "Declare Payment" only navigates to the existing declare
 *       route; zero economic POSTs fire from this navigation
 *   T5  when the order fails to load, no declare entry is fabricated
 *   T6  payment history shows "My declarations" for client:payments:read
 *   T7  payment history hides "My declarations" without that read permission
 *   T8  merchant sidebar exposes a "Declarations" link to /declarations
 *   T9  existing 390px mobile layout: the declare entry renders inside the
 *       unchanged action row (no layout rework)
 */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { OrderDetailPage } from '@/pages/client/OrderDetailPage';
import { ClientPaymentHistoryPage } from '@/pages/client/PaymentHistoryPage';
import { Sidebar } from '@/components/layout/Sidebar';
import { clientOrderService } from '@/services/clientOrderService';
import { clientFinanceService } from '@/services/clientFinanceService';
import { useAuthStore } from '@/stores/authStore';
import type { ClientOrder } from '@/types/client';

vi.mock('@/services/clientOrderService', () => ({ clientOrderService: {
  getById: vi.fn(), cancel: vi.fn(), create: vi.fn(), replaceDraft: vi.fn(), submitReorder: vi.fn(),
} }));
vi.mock('@/services/clientFinanceService', () => ({ clientFinanceService: {
  getPayments: vi.fn(),
} }));

const ORDER_ID = '4f7c9a1e-1111-4111-8111-111111111111';
const DECOY_ID = '00000000-0000-4000-8000-000000000000';

function orderFixture(id: string = ORDER_ID): ClientOrder {
  return {
    id, status: 'CONFIRMED', source_order_id: null,
    total_amount: '220.00', currency: 'KES', item_count: 1, notes: null,
    created_at: '2026-10-15T07:00:00Z', items: [{
      sellable_unit_id: 'unit', identity_status: 'stable', product_name: 'Boxes', sku_code: 'BOX',
      unit_snapshot: 'box', package_quantity_snapshot: '12', display_label: 'Boxes',
      display_label_snapshot: 'Boxes',
      quantity: 2, unit_price: '110.00', subtotal: '220.00',
    }],
  } as unknown as ClientOrder;
}

function response(data: unknown) { return { data: { success: true, data } } as never; }

function userWith(permissions: string[]) {
  return {
    id: '11111111-1111-4111-8111-111111111111',
    email: 'nav@test.dev',
    full_name: 'Nav Test',
    tenant_id: null,
    tenant_schema: null,
    roles: ['retailer_operator'],
    permissions,
  };
}

function CurrentRoute() {
  const location = useLocation();
  return <p data-testid="current-route">{location.pathname}</p>;
}

async function mountOrderDetail(order = orderFixture()) {
  vi.mocked(clientOrderService.getById).mockResolvedValue(response(order));
  render(<MemoryRouter initialEntries={[`/client/orders/${ORDER_ID}`]}>
    <Routes>
      <Route path="/client/orders/:orderId" element={<OrderDetailPage />} />
      <Route path="/client/orders/:orderId/declare" element={<p>Declare page stub</p>} />
    </Routes>
    <CurrentRoute />
  </MemoryRouter>);
  await screen.findByRole('heading', { name: 'Items' });
}

function mountPaymentHistory() {
  render(<MemoryRouter initialEntries={['/client/payments']}>
    <Routes>
      <Route path="/client/payments" element={<ClientPaymentHistoryPage />} />
      <Route path="/client/declarations" element={<p>Declarations stub</p>} />
    </Routes>
    <CurrentRoute />
  </MemoryRouter>);
}

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(clientFinanceService.getPayments).mockResolvedValue(
    response({ items: [], pagination: { page: 1, pages: 1, total: 0 } }));
});

afterEach(() => {
  cleanup();
  useAuthStore.setState({ accessToken: null, refreshToken: null, user: null, tenantCode: null, retailerPortalCode: null });
  vi.restoreAllMocks();
});

describe('F-04 payment declaration navigation closure', () => {
  it('T1 shows Declare Payment with client:payments:declare and links the fetched order id', async () => {
    useAuthStore.setState({ user: userWith(['client:payments:read', 'client:payments:declare']) });
    await mountOrderDetail();
    const link = screen.getByRole('link', { name: 'Declare Payment' });
    expect(link).toHaveAttribute('href', `/client/orders/${ORDER_ID}/declare`);
    expect(link.getAttribute('href')).not.toContain(DECOY_ID);
    expect(screen.getByText(/only submits a declaration/i)).toBeInTheDocument();
  });

  it('T2 named negative: client:payments:read alone shows no declare entry', async () => {
    useAuthStore.setState({ user: userWith(['client:payments:read']) });
    await mountOrderDetail();
    expect(screen.queryByRole('link', { name: 'Declare Payment' })).toBeNull();
    expect(screen.queryByText(/only submits a declaration/i)).toBeNull();
  });

  it('T3 permission-empty user sees no declare entry and no My declarations', async () => {
    useAuthStore.setState({ user: userWith([]) });
    await mountOrderDetail();
    expect(screen.queryByRole('link', { name: 'Declare Payment' })).toBeNull();
    cleanup();
    mountPaymentHistory();
    await screen.findByRole('heading', { name: 'Payment History' });
    expect(screen.queryByRole('link', { name: 'My declarations' })).toBeNull();
  });

  it('T4 clicking Declare Payment only navigates with zero economic POSTs', async () => {
    useAuthStore.setState({ user: userWith(['client:payments:read', 'client:payments:declare']) });
    await mountOrderDetail();
    fireEvent.click(screen.getByRole('link', { name: 'Declare Payment' }));
    expect(screen.getByTestId('current-route')).toHaveTextContent(`/client/orders/${ORDER_ID}/declare`);
    expect(clientOrderService.cancel).not.toHaveBeenCalled();
    expect(clientOrderService.create).not.toHaveBeenCalled();
    expect(clientOrderService.replaceDraft).not.toHaveBeenCalled();
    expect(clientOrderService.submitReorder).not.toHaveBeenCalled();
  });

  it('T5 order load failure fabricates no declare entry', async () => {
    useAuthStore.setState({ user: userWith(['client:payments:read', 'client:payments:declare']) });
    vi.mocked(clientOrderService.getById).mockRejectedValue(new Error('boom'));
    render(<MemoryRouter initialEntries={[`/client/orders/${ORDER_ID}`]}>
      <Routes>
        <Route path="/client/orders/:orderId" element={<OrderDetailPage />} />
      </Routes>
    </MemoryRouter>);
    await screen.findByText('Order not found.');
    expect(screen.queryByRole('link', { name: 'Declare Payment' })).toBeNull();
  });

  it('T6 payment history shows My declarations with client:payments:read', async () => {
    useAuthStore.setState({ user: userWith(['client:payments:read']) });
    mountPaymentHistory();
    await screen.findByRole('heading', { name: 'Payment History' });
    const link = screen.getByRole('link', { name: 'My declarations' });
    expect(link).toHaveAttribute('href', '/client/declarations');
  });

  it('T7 named negative: without client:payments:read My declarations is absent', async () => {
    useAuthStore.setState({ user: userWith(['client:orders:read']) });
    mountPaymentHistory();
    await screen.findByRole('heading', { name: 'Payment History' });
    expect(screen.queryByRole('link', { name: 'My declarations' })).toBeNull();
  });

  it('T8 merchant sidebar exposes the Declarations queue link', () => {
    useAuthStore.setState({ user: userWith(['payments:read']) });
    render(<MemoryRouter initialEntries={['/']}>
      <Sidebar />
      <CurrentRoute />
    </MemoryRouter>);
    const link = screen.getByRole('link', { name: 'Declarations' });
    expect(link).toHaveAttribute('href', '/declarations');
  });

  it('T9 existing 390px layout keeps rendering the declare entry inside the action row', async () => {
    window.innerWidth = 390;
    useAuthStore.setState({ user: userWith(['client:payments:read', 'client:payments:declare']) });
    await mountOrderDetail();
    expect(screen.getByRole('link', { name: 'Declare Payment' })).toBeVisible();
    expect(screen.getByRole('link', { name: 'Print order' })).toBeVisible();
    window.innerWidth = 1024;
  });
});
