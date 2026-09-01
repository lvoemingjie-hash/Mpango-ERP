/**
 * DC-12R1-MVP-L1-SKU-R0-M1-R1-R1 — product-level multipackaging UX contract.
 *
 * Oracle: the REAL client pages under jsdom with a recording axios adapter
 * (real-shaped product-level payloads; no HTTP).
 *
 * Proven here:
 *   F1 one product container per CatalogProduct (two units -> ONE card, both
 *      packaging choices INSIDE that same container)
 *   F2 packaging selector updates the selected sellable_unit_id, the displayed
 *      price and the stock badge
 *   F3 the real order submission carries EXACTLY the selected stable
 *      sellable_unit_id UUID (captured POST body)
 */
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios';
import { render, screen, waitFor, cleanup, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import { api } from '@/services/api';
import { ProductListPage } from '@/pages/client/ProductListPage';
import { ProductDetailPage } from '@/pages/client/ProductDetailPage';
import { CreateOrderPage } from '@/pages/client/CreateOrderPage';

type Handler = (config: InternalAxiosRequestConfig) => AxiosResponse | Promise<AxiosResponse>;

function ok<T>(config: InternalAxiosRequestConfig, data: T): AxiosResponse<T> {
  return { data, status: 200, statusText: 'OK', headers: {}, config };
}

function apiResponse<T>(data: T) {
  return { success: true, data, timestamp: '2026-09-01T00:00:00.000Z' };
}

function installAdapter(handlers: Record<string, Handler>) {
  const log: string[] = [];
  const bodies: Record<string, unknown> = {};
  const adapter: AxiosAdapter = async (config) => {
    const key = `${(config.method ?? 'get').toUpperCase()} ${config.url ?? ''}`;
    log.push(key);
    if (config.data) bodies[key] = JSON.parse(String(config.data));
    const handler = handlers[key];
    if (handler) return await handler(config);
    return ok(config, apiResponse({ id: 'order-1' }));
  };
  api.defaults.adapter = adapter;
  axios.defaults.adapter = adapter;
  return { log, bodies };
}

const PRODUCT_ID = 'aaaaaaaa-1111-1111-1111-111111111111';
const BOTTLE_ID = 'bbbbbbbb-2222-2222-2222-222222222222';
const CASE_ID = 'cccccccc-3333-3333-3333-333333333333';

function productPayload() {
  return {
    items: [
      {
        id: PRODUCT_ID,
        name: 'Riverside Juice',
        category: 'staples',
        in_stock: true,
        stock_level: 'MEDIUM',
        can_order: true,
        unit_count: 2,
        units: [
          {
            sellable_unit_id: BOTTLE_ID,
            sku_code: 'JUICE-BTL',
            unit: 'bottle',
            package_quantity: 1,
            price: 25.5,
            in_stock: true,
            stock_level: 'MEDIUM',
            can_order: true,
          },
          {
            sellable_unit_id: CASE_ID,
            sku_code: 'JUICE-CASE',
            unit: 'case',
            package_quantity: 12,
            price: 289.0,
            in_stock: true,
            stock_level: 'HIGH',
            can_order: true,
          },
        ],
      },
    ],
    pagination: { page: 1, size: 20, total: 1, pages: 1 },
  };
}

function detailPayload() {
  return { ...productPayload().items[0], description: 'Fresh juice' };
}

describe('R1 product-level multipackaging UX', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    cleanup();
  });

  it('F1 renders ONE card per product with both packaging choices inside it', async () => {
    installAdapter({
      'GET /client/products': (c) => ok(c, apiResponse(productPayload())),
    });
    render(
      <MemoryRouter initialEntries={['/client']}>
        <Routes>
          <Route path="/client" element={<ProductListPage />} />
        </Routes>
      </MemoryRouter>
    );

    const cards = await screen.findAllByTestId('client-product-card');
    expect(cards).toHaveLength(1);
    const units = screen.getByTestId('client-product-units');
    expect(units).toHaveTextContent('JUICE-BTL');
    expect(units).toHaveTextContent('JUICE-CASE');
    // lowest unit price is displayed as the product "from" price
    expect(cards[0]).toHaveTextContent('25.50');
  });

  it('F2 packaging selector switches selected sellable_unit_id, price and stock', async () => {
    const user = userEvent.setup();
    installAdapter({
      'GET /client/products/juice-detail': (c) => ok(c, apiResponse(detailPayload())),
    });
    render(
      <MemoryRouter initialEntries={['/client/products/juice-detail']}>
        <Routes>
          <Route path="/client/products/:productId" element={<ProductDetailPage />} />
        </Routes>
      </MemoryRouter>
    );

    const orderSection = await screen.findByTestId('order-section');
    // default selection = first unit (deterministic backend order)
    expect(orderSection).toHaveAttribute('data-selected-sellable-unit-id', BOTTLE_ID);
    expect(screen.getByTestId('order-section')).toHaveTextContent('KES 25.50');
    expect(screen.getByTestId('selected-unit-stock')).toHaveTextContent('Limited Stock');

    const group = screen.getByRole('radiogroup', { name: 'Packaging' });
    const caseRadio = within(group).getByRole('radio', { name: /JUICE-CASE/ });
    expect(caseRadio).toHaveAttribute('data-sellable-unit-id', CASE_ID);
    await user.click(caseRadio);

    expect(orderSection).toHaveAttribute('data-selected-sellable-unit-id', CASE_ID);
    expect(screen.getByTestId('order-section')).toHaveTextContent('KES 289.00');
    expect(screen.getByTestId('selected-unit-stock')).toHaveTextContent('In Stock');

    const bottleRadio = within(group).getByRole('radio', { name: /JUICE-BTL/ });
    await user.click(bottleRadio);
    expect(orderSection).toHaveAttribute('data-selected-sellable-unit-id', BOTTLE_ID);
  });

  it('F3 the real order submission carries exactly the selected unit UUID', async () => {
    const user = userEvent.setup();
    const { bodies } = installAdapter({
      'GET /client/products/juice-detail': (c) => ok(c, apiResponse(detailPayload())),
      'POST /client/orders': (c) => ok(c, apiResponse({ id: 'order-1' })),
    });
    render(
      <MemoryRouter initialEntries={['/client/products/juice-detail']}>
        <Routes>
          <Route path="/client/products/:productId" element={<ProductDetailPage />} />
          <Route path="/client/orders/new" element={<CreateOrderPage />} />
        </Routes>
      </MemoryRouter>
    );

    await screen.findByTestId('order-section');
    await user.click(screen.getByRole('radio', { name: /JUICE-CASE/ }));
    await user.click(screen.getByRole('button', { name: 'Add to Order' }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Submit Order/i })).toBeEnabled();
    });
    await user.click(screen.getByRole('button', { name: /Submit Order/i }));

    await waitFor(() => {
      expect(bodies['POST /client/orders']).toBeTruthy();
    });
    const submitted = bodies['POST /client/orders'] as {
      items: Array<{ sellable_unit_id: string; sku_code: string }>;
    };
    expect(submitted.items).toHaveLength(1);
    expect(submitted.items[0].sellable_unit_id).toBe(CASE_ID);
    expect(submitted.items[0].sku_code).toBe('JUICE-CASE');
  });
});
