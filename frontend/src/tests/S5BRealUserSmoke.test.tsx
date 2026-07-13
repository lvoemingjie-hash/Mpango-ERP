import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { AxiosAdapter, AxiosRequestConfig, AxiosResponse, InternalAxiosRequestConfig } from 'axios';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { App } from '@/App';
import { api } from '@/services/api';
import { useAuthStore } from '@/stores/authStore';
import { useToastStore } from '@/stores/toastStore';
import type { ApiResponse, PaginatedData } from '@/types/api';

const ADMIN_PERMISSIONS = [
  'dashboards:read',
  'inventory:read',
  'inventory:update',
  'orders:create',
  'orders:read',
  'orders:update',
  'payments:create',
  'payments:read',
  'pricing:read',
  'pricing:write',
  'reports:analyze',
  'reports:read',
  'retailers:read',
  'skus:create',
  'skus:import',
  'skus:read',
  'skus:update',
];

const originalAdapter = api.defaults.adapter;

function ok<T>(config: InternalAxiosRequestConfig, data: T): AxiosResponse<T> {
  return {
    data,
    status: 200,
    statusText: 'OK',
    headers: {},
    config,
  };
}

function apiResponse<T>(data: T): ApiResponse<T> {
  return {
    success: true,
    data,
    timestamp: '2026-06-24T00:00:00.000Z',
  };
}

function paginated<T>(items: T[], page = 1, size = 20): PaginatedData<T> {
  return {
    items,
    pagination: {
      page,
      size,
      total: items.length,
      pages: items.length === 0 ? 0 : Math.ceil(items.length / size),
    },
  };
}

function requestKey(config: AxiosRequestConfig): string {
  return `${(config.method ?? 'get').toUpperCase()} ${config.url ?? ''}`;
}

function installRealEndpointAdapter(): string[] {
  const handled: string[] = [];
  const adapter: AxiosAdapter = async (config) => {
    const key = requestKey(config);
    handled.push(key);

    switch (key) {
      case 'GET /dashboards/kpi/summary':
        return ok(config, {
          success: true,
          data: {
            tenant_id: 'tenant-s5b',
            generated_at: '2026-06-24T00:00:00.000Z',
            cards: [],
            currency: 'KES',
          },
          timestamp: '2026-06-24T00:00:00.000Z',
        });
      case 'GET /dashboards/charts/sales-trend':
        return ok(config, {
          success: true,
          data: {
            tenant_id: 'tenant-s5b',
            chart_type: 'sales-trend',
            granularity: 'day',
            data: [],
            currency: 'KES',
          },
          timestamp: '2026-06-24T00:00:00.000Z',
        });
      case 'GET /orders':
        return ok(config, apiResponse(paginated([], 1, 50)));
      case 'GET /skus':
        return ok(config, apiResponse(paginated([], 1, 100)));
      case 'GET /inventory/stocks':
        return ok(config, apiResponse(paginated([], 1, 50)));
      case 'GET /finance/summary':
        return ok(
          config,
          apiResponse({
            total_revenue: 0,
            total_cash_received: 0,
            outstanding_receivables: 0,
            overdue_receivables_count: 0,
            order_counts: {},
            total_orders: 0,
            generated_at: '2026-06-24T00:00:00.000Z',
          }),
        );
      case 'GET /finance/receivables/summary':
        return ok(
          config,
          apiResponse({
            total_outstanding: 0,
            retailer_count: 0,
            order_count: 0,
            credit_receivables: 0,
            unpaid_order_balance: 0,
            by_retailer: [],
          }),
        );
      case 'GET /finance/receivables/orders':
        return ok(config, apiResponse(paginated([], 1, 20)));
      case 'GET /payments?page=1&size=20':
        return ok(config, apiResponse(paginated([], 1, 20)));
      case 'GET /retailers?page=1&size=20':
      case 'GET /retailers?page=1&size=100':
        return ok(config, apiResponse(paginated([], 1, key.endsWith('size=100') ? 100 : 20)));
      default:
        return Promise.reject({
          isAxiosError: true,
          config,
          response: {
            status: 500,
            statusText: 'Unhandled mock route',
            headers: {},
            config,
            data: {
              error: {
                code: 'S5B_UNMOCKED_ENDPOINT',
                message: `Unhandled S5-B endpoint mock: ${key}`,
              },
            },
          },
        });
    }
  };

  api.defaults.adapter = adapter;
  return handled;
}

function seedAdminTenantContext() {
  useAuthStore.setState({
    accessToken: 's5b-contextual-admin-access-token',
    refreshToken: 's5b-contextual-admin-refresh-token',
    tenantCode: 'S5B',
    user: {
      id: 'user-s5b-admin',
      email: 's5b-admin@example.com',
      full_name: 'S5B Admin',
      tenant_id: 'tenant-s5b',
      tenant_schema: 't_s5b',
      roles: ['admin'],
      permissions: ADMIN_PERMISSIONS,
    },
  });
}

async function assertNoGuardrailToasts() {
  await waitFor(() => {
    expect(screen.queryByText('Access Denied')).not.toBeInTheDocument();
    expect(screen.queryByText('Server Error')).not.toBeInTheDocument();
    expect(screen.queryByText('Security Alert: Tenant Context Lost')).not.toBeInTheDocument();
  });
}

describe('S5-B frontend real user smoke gate', () => {
  beforeEach(() => {
    window.history.pushState({}, '', '/');
    window.localStorage.clear();
    useToastStore.setState({ toasts: [] });
    seedAdminTenantContext();
  });

  afterEach(() => {
    api.defaults.adapter = originalAdapter;
    vi.restoreAllMocks();
    useAuthStore.getState().logout();
    useToastStore.setState({ toasts: [] });
    window.localStorage.clear();
  });

  it('lets an authenticated admin click the MVP sidebar pages without 403 or 500 toasts', async () => {
    const user = userEvent.setup();
    const handled = installRealEndpointAdapter();

    render(<App />);

    await screen.findByRole('heading', { name: 'Home' });
    expect(screen.getByText('Welcome to your dashboard')).toBeInTheDocument();
    await assertNoGuardrailToasts();

    await user.click(screen.getByRole('link', { name: 'Sales' }));
    await screen.findByRole('heading', { name: 'Sales' });
    expect(screen.getAllByRole('button', { name: 'Create Order' })[0]).toBeEnabled();
    expect(screen.getByText('Ready to make your first sale?')).toBeInTheDocument();
    await assertNoGuardrailToasts();

    await user.click(screen.getByRole('link', { name: 'Products' }));
    await screen.findByRole('heading', { name: 'Products (SKUs)' });
    expect(screen.getAllByRole('button', { name: /add product/i })[0]).toBeInTheDocument();
    const importEntry = screen.getAllByRole('button', { name: /import catalog skus/i })[0];
    expect(importEntry).toBeVisible();
    await user.click(importEntry);
    expect(await screen.findByRole('dialog', { name: 'Import Catalog SKUs' })).toBeInTheDocument();
    expect(screen.getByLabelText('Click to select a CSV file')).toBeInTheDocument();
    expect(screen.getByText(/Upload a CSV file with your catalog SKU data/i)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    await waitFor(() => {
      expect(screen.queryByRole('dialog', { name: 'Import Catalog SKUs' })).not.toBeInTheDocument();
    });
    await assertNoGuardrailToasts();

    await user.click(screen.getByRole('link', { name: 'Stock' }));
    await screen.findByRole('heading', { name: 'Stock' });
    expect(screen.getByRole('link', { name: 'View Logs' })).toBeInTheDocument();
    expect(screen.getByText('No stock yet')).toBeInTheDocument();
    await assertNoGuardrailToasts();

    await user.click(screen.getByRole('link', { name: 'Finance' }));
    await screen.findByRole('heading', { name: 'Accounts Receivable' });
    expect(screen.getByRole('button', { name: 'Record Repayment' })).toBeInTheDocument();
    expect(screen.getByText('No outstanding receivables')).toBeInTheDocument();
    await assertNoGuardrailToasts();

    await user.click(screen.getByRole('link', { name: 'Payments' }));
    await screen.findByRole('heading', { name: 'Payments' });
    expect(screen.getByRole('button', { name: 'Refresh' })).toBeInTheDocument();
    expect(screen.getByText('No payments yet')).toBeInTheDocument();
    await assertNoGuardrailToasts();

    await user.click(screen.getByRole('link', { name: 'Customers' }));
    await screen.findByRole('heading', { name: 'Customers' });
    expect(screen.getByRole('button', { name: 'Refresh' })).toBeInTheDocument();
    expect(screen.getByText('No customers yet')).toBeInTheDocument();
    await assertNoGuardrailToasts();

    await user.click(screen.getByRole('link', { name: 'Pricing' }));
    await screen.findByRole('heading', { name: 'Customer Pricing' });
    expect(screen.getByRole('button', { name: 'Set New Price' })).toBeDisabled();
    expect(screen.getByText('Select a customer to manage pricing')).toBeInTheDocument();
    await assertNoGuardrailToasts();

    expect(handled).toEqual(
      expect.arrayContaining([
        'GET /dashboards/kpi/summary',
        'GET /dashboards/charts/sales-trend',
        'GET /orders',
        'GET /skus',
        'GET /inventory/stocks',
        'GET /finance/summary',
        'GET /finance/receivables/summary',
        'GET /finance/receivables/orders',
        'GET /payments?page=1&size=20',
        'GET /retailers?page=1&size=20',
        'GET /retailers?page=1&size=100',
      ]),
    );
  });
});
