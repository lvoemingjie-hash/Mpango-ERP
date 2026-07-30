/**
 * DC-12R1-H3: Payment UI Permission Contract Tests
 *
 * Proves that the "Record Payment" button and collect deep-link use
 * payments:create (not orders:update) as the authorization gate, matching
 * the backend POST /api/v1/orders/{order_id}/pay which requires payments:create.
 *
 * Scenarios:
 *  1. payments:create without orders:update CAN record payment (GREEN)
 *  2. orders:update without payments:create CANNOT open/submit payment (RED)
 *  3. Collect deep-link cannot bypass the permission gate
 *  4. Denied paths make zero payment API calls
 *  5. Admin works through its granted payments:create permission
 */
import { afterEach, describe, expect, it } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import { OrderListPage } from '@/pages/orders/OrderListPage';
import { useAuthStore } from '@/stores/authStore';
import { useToastStore } from '@/stores/toastStore';
import { api } from '@/services/api';
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios';
import type { Order } from '@/types/order';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const CONFIRMED_ORDER: Order = {
  id: 'order-aaaa-0001',
  wholesaler_id: 'ws-0001',
  retailer_id: 'ret-0001',
  retailer_name: 'Test Duka',
  status: 'confirmed',
  total_amount: 5000,
  items: [],
  notes: null,
  created_by: null,
  created_at: '2026-07-31T10:00:00Z',
  updated_at: '2026-07-31T10:00:00Z',
};

function mockPaginatedOrders(orders: Order[]) {
  return {
    success: true,
    data: { items: orders, total: orders.length, page: 1, size: 50 },
    timestamp: '2026-07-31T10:00:00Z',
  };
}

function mockEmptyPayments() {
  return {
    success: true,
    data: { items: [], total: 0, page: 1, size: 20 },
    timestamp: '2026-07-31T10:00:00Z',
  };
}

/**
 * Install a mock axios adapter that returns orders/payments and tracks
 * whether a payment POST was attempted.
 */
function installMockAdapter(onPay?: (url: string) => void) {
  const adapter: AxiosAdapter = async (config: InternalAxiosRequestConfig) => {
    const url = config.url || '';
    const method = (config.method || 'get').toLowerCase();

    // Pay endpoint
    if (url.includes('/pay') && method === 'post') {
      if (onPay) onPay(url);
      const resp: AxiosResponse = {
        data: {
          success: true,
          data: {
            order_id: 'order-aaaa-0001',
            status: 'paid',
            payment_id: 'pay-0001',
            payment_amount: 5000,
            payment_method: 'cash',
          },
          timestamp: '2026-07-31T10:00:00Z',
        },
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      };
      return resp;
    }

    // Payments list (for remaining balance) — matches /payments?order_id=
    if (url.includes('/payments') && method === 'get') {
      return { data: mockEmptyPayments(), status: 200, statusText: 'OK', headers: {}, config } as AxiosResponse;
    }

    // Single order (must be before orders list catch-all)
    if (url.match(/\/orders\/[^/]+$/) && method === 'get') {
      return { data: { success: true, data: CONFIRMED_ORDER, timestamp: '2026-07-31T10:00:00Z' }, status: 200, statusText: 'OK', headers: {}, config } as AxiosResponse;
    }

    // Orders list
    if (url.includes('/orders') && method === 'get') {
      return { data: mockPaginatedOrders([CONFIRMED_ORDER]), status: 200, statusText: 'OK', headers: {}, config } as AxiosResponse;
    }

    // Default
    return { data: { success: true, data: {}, timestamp: '2026-07-31T10:00:00Z' }, status: 200, statusText: 'OK', headers: {}, config } as AxiosResponse;
  };
  api.defaults.adapter = adapter;
  return adapter;
}

function setUser(permissions: string[], roles: string[] = []) {
  useAuthStore.setState({
    accessToken: 'test-token',
    refreshToken: 'test-refresh',
    user: {
      id: 'user-0001',
      email: 'test@mpango.test',
      full_name: 'Test User',
      tenant_id: 'tenant-0001',
      tenant_schema: 't_test',
      roles,
      permissions,
    },
    tenantCode: 'TEST001',
    retailerPortalCode: null,
  });
}

function renderOrderListPage(initialPath = '/orders') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/orders" element={<OrderListPage />} />
        <Route path="/finance" element={<div>Finance Page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

const originalAdapter = api.defaults.adapter;

afterEach(() => {
  api.defaults.adapter = originalAdapter;
  useAuthStore.setState({
    accessToken: null,
    refreshToken: null,
    user: null,
    tenantCode: null,
    retailerPortalCode: null,
  });
  useToastStore.setState({ toasts: [] });
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('DC-12R1-H3: Payment permission contract', () => {

  // Scenario 1: payments:create without orders:update CAN record payment
  it('payments:create without orders:update can open payment modal and submit', async () => {
    setUser(['payments:create', 'orders:read'], ['cashier']);
    let payCalled = false;
    installMockAdapter(() => { payCalled = true; });

    renderOrderListPage();

    // Wait for orders to load
    await waitFor(() => {
      expect(screen.getByText('Record Payment')).toBeInTheDocument();
    });

    // Button should be enabled (has payments:create)
    const payButton = screen.getByRole('button', { name: /record payment/i });
    expect(payButton).not.toBeDisabled();

    // Click to open modal
    await userEvent.click(payButton);

    // Wait for modal
    await waitFor(() => {
      expect(screen.getByLabelText(/payment method/i)).toBeInTheDocument();
    });

    // Fill and submit
    await userEvent.selectOptions(screen.getByLabelText(/payment method/i), 'cash');
    await userEvent.type(screen.getByLabelText(/amount/i), '5000');
    await userEvent.click(screen.getByRole('button', { name: /record payment/i }));

    await waitFor(() => {
      expect(payCalled).toBe(true);
    });
  });

  // Scenario 2: orders:update without payments:create CANNOT open/submit payment
  it('orders:update without payments:create cannot record payment (button disabled)', async () => {
    setUser(['orders:update', 'orders:read', 'orders:create'], ['sales']);
    let payCalled = false;
    installMockAdapter(() => { payCalled = true; });

    renderOrderListPage();

    await waitFor(() => {
      expect(screen.getByText('Record Payment')).toBeInTheDocument();
    });

    // Button should be disabled (lacks payments:create)
    const payButton = screen.getByRole('button', { name: /record payment/i });
    expect(payButton).toBeDisabled();
    expect(payButton).toHaveAttribute('title', 'Permission Denied');

    // Cannot open modal
    await userEvent.click(payButton);
    await waitFor(() => {
      expect(screen.queryByLabelText(/payment method/i)).not.toBeInTheDocument();
    });

    // Zero payment API calls
    expect(payCalled).toBe(false);
  });

  // Scenario 3: Collect deep-link cannot bypass the permission gate
  it('collect deep-link denied for user without payments:create', async () => {
    setUser(['orders:update', 'orders:read'], ['sales']);
    installMockAdapter();

    // Render with collect deep-link
    renderOrderListPage('/orders?collect=order-aaaa-0001&returnTo=finance');

    // Should show permission-denied toast, NOT open the payment modal
    await waitFor(() => {
      const toasts = useToastStore.getState().toasts;
      const deniedToast = toasts.find(
        (t) => t.message?.includes('do not have permission to record payments'),
      );
      expect(deniedToast).toBeDefined();
    });

    // Modal should NOT be open
    expect(screen.queryByLabelText(/payment method/i)).not.toBeInTheDocument();
  });

  // Scenario 4: Collect deep-link works for user WITH payments:create
  it('collect deep-link opens modal for user with payments:create', async () => {
    setUser(['payments:create', 'orders:read'], ['cashier']);
    installMockAdapter();

    renderOrderListPage('/orders?collect=order-aaaa-0001&returnTo=finance');

    await waitFor(() => {
      expect(screen.getByLabelText(/payment method/i)).toBeInTheDocument();
    });
  });

  // Scenario 5: Admin works through its granted payments:create permission
  it('admin with payments:create in permission set can record payment', async () => {
    // Admin has payments:create in its permission set (not via role-name shortcut)
    setUser(
      ['orders:create', 'orders:read', 'orders:update', 'payments:create', 'payments:read'],
      ['admin'],
    );
    let payCalled = false;
    installMockAdapter(() => { payCalled = true; });

    renderOrderListPage();

    await waitFor(() => {
      expect(screen.getByText('Record Payment')).toBeInTheDocument();
    });

    const payButton = screen.getByRole('button', { name: /record payment/i });
    expect(payButton).not.toBeDisabled();

    await userEvent.click(payButton);
    await waitFor(() => {
      expect(screen.getByLabelText(/payment method/i)).toBeInTheDocument();
    });

    await userEvent.selectOptions(screen.getByLabelText(/payment method/i), 'cash');
    await userEvent.type(screen.getByLabelText(/amount/i), '5000');
    await userEvent.click(screen.getByRole('button', { name: /record payment/i }));

    await waitFor(() => {
      expect(payCalled).toBe(true);
    });
  });

  // Scenario 5b: Admin WITHOUT payments:create in permission set cannot pay
  // (proves role-name shortcut is NOT used)
  it('admin role without payments:create permission cannot record payment', async () => {
    setUser(['orders:create', 'orders:read', 'orders:update'], ['admin']);
    let payCalled = false;
    installMockAdapter(() => { payCalled = true; });

    renderOrderListPage();

    await waitFor(() => {
      expect(screen.getByText('Record Payment')).toBeInTheDocument();
    });

    const payButton = screen.getByRole('button', { name: /record payment/i });
    expect(payButton).toBeDisabled();
    expect(payCalled).toBe(false);
  });
});
