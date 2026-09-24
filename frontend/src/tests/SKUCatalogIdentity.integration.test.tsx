import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { SKUFormModal } from '@/pages/skus/SKUFormModal';
import { SKUListPage } from '@/pages/skus/SKUListPage';
import { api } from '@/services/api';
import { useAuthStore } from '@/stores/authStore';

const originalAdapter = api.defaults.adapter;

function response<T>(config: InternalAxiosRequestConfig, data: T): AxiosResponse<T> {
  return { data, status: 200, statusText: 'OK', headers: {}, config };
}

function seedUser(permissions: string[]) {
  useAuthStore.setState({
    accessToken: 'sku-integration-token',
    refreshToken: 'sku-integration-refresh',
    tenantCode: 'SKU-M1',
    retailerPortalCode: null,
    user: {
      id: 'user-1',
      email: 'catalog@example.test',
      full_name: 'Catalog Operator',
      tenant_id: 'tenant-1',
      tenant_schema: 't_tenant_1',
      roles: [],
      permissions,
    },
  });
}

beforeEach(() => {
  window.localStorage.clear();
  seedUser(['skus:read', 'skus:create', 'skus:update']);
});

afterEach(() => {
  cleanup();
  api.defaults.adapter = originalAdapter;
  useAuthStore.setState({
    accessToken: null,
    refreshToken: null,
    user: null,
    tenantCode: null,
    retailerPortalCode: null,
  });
});

describe('SKU catalog identity HTTP boundary', () => {
  it('loads product-centered packaging through the real service and API client', async () => {
    const requests: InternalAxiosRequestConfig[] = [];
    api.defaults.adapter = (async (config: InternalAxiosRequestConfig) => {
      requests.push(config);
      return response(config, {
        success: true,
        data: {
          items: [{
            id: 'product-1',
            name: 'Premium Rice',
            description: 'Customer-facing product',
            category: 'Staples',
            is_active: true,
            created_at: '2026-08-30T00:00:00Z',
            updated_at: '2026-08-30T00:00:00Z',
            sellable_units: [
              {
                id: 'unit-each',
                catalog_product_id: 'product-1',
                sku_code: 'RICE-EACH-1',
                unit: 'bag',
                package_quantity: 1,
                is_active: true,
                created_at: '2026-08-30T00:00:00Z',
                updated_at: '2026-08-30T00:00:00Z',
              },
              {
                id: 'unit-case',
                catalog_product_id: 'product-1',
                sku_code: 'RICE-CASE-12',
                unit: 'case',
                package_quantity: 12,
                is_active: true,
                created_at: '2026-08-30T00:00:00Z',
                updated_at: '2026-08-30T00:00:00Z',
              },
            ],
          }],
          total: 1,
          page: 1,
          size: 100,
        },
        timestamp: '2026-08-30T00:00:00Z',
      });
    }) as AxiosAdapter;

    render(<SKUListPage />);

    expect(await screen.findByRole('heading', { name: 'Premium Rice' })).toBeInTheDocument();
    expect(screen.getByText('RICE-EACH-1')).toBeInTheDocument();
    expect(screen.getByText('RICE-CASE-12')).toBeInTheDocument();
    expect(requests).toHaveLength(1);
    expect(requests[0].url).toBe('/catalog-products');
    expect(requests[0].params).toEqual({ page: 1, size: 100 });
    expect(requests[0].headers.get('Authorization')).toBe('Bearer sku-integration-token');
  });

  it('posts one product with multiple packaging options through the real API client', async () => {
    const writes: InternalAxiosRequestConfig[] = [];
    api.defaults.adapter = (async (config: InternalAxiosRequestConfig) => {
      writes.push(config);
      return response(config, {
        success: true,
        data: { id: 'product-created' },
        timestamp: '2026-08-30T00:00:00Z',
      });
    }) as AxiosAdapter;
    const user = userEvent.setup();

    render(
      <SKUFormModal
        isOpen
        product={null}
        onClose={vi.fn()}
        onSuccess={vi.fn()}
      />,
    );

    await user.type(screen.getByLabelText('Product Name'), 'Premium Rice');
    await user.type(screen.getByLabelText('SKU Code'), 'RICE-EACH-1');
    await user.clear(screen.getByLabelText('Unit'));
    await user.type(screen.getByLabelText('Unit'), 'bag');
    await user.click(screen.getByRole('button', { name: 'Add packaging' }));
    const codes = screen.getAllByLabelText('SKU Code');
    const quantities = screen.getAllByLabelText('Pack quantity');
    const units = screen.getAllByLabelText('Unit');
    await user.type(codes[1], 'RICE-CASE-12');
    await user.clear(quantities[1]);
    await user.type(quantities[1], '12');
    await user.clear(units[1]);
    await user.type(units[1], 'case');
    await user.click(screen.getByRole('button', { name: 'Save Product' }));

    await waitFor(() => expect(writes).toHaveLength(1));
    expect(writes[0].method).toBe('post');
    expect(writes[0].url).toBe('/catalog-products');
    expect(JSON.parse(writes[0].data as string)).toEqual({
      name: 'Premium Rice',
      description: '',
      category: '',
      is_active: true,
      sellable_units: [
        { sku_code: 'RICE-EACH-1', unit: 'bag', package_quantity: 1, is_active: true },
        { sku_code: 'RICE-CASE-12', unit: 'case', package_quantity: 12, is_active: true },
      ],
    });
  });
});
