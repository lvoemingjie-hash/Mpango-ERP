/**
 * C910 R4 frozen directed controls: PaymentListPage currency display + order-page safety.
 *
 * The SAME bytes run against BASE (c9106057) and the candidate. Component
 * level, mocked api client, no real service.
 *
 * Pre-declared BASE semantic failures: hardcoded-KES rows (1,2), mixed-page
 * single-currency total (3), float-rounded page total (4). Protection
 * assertions (5) must be green on BOTH sides — importing it on BASE proves
 * the new fields do not migrate the order page's payment-modal logic.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { PaymentListPage } from '@/pages/finance/PaymentListPage';
import { calculatePaymentModalState } from '@/pages/orders/OrderListPage';
import { api } from '@/services/api';
import type { PaymentData, PaymentListItem } from '@/services/paymentService';
import type { Order } from '@/types/order';

function item(over: Record<string, unknown>): PaymentListItem {
  return {
    id: `pay-${Math.random().toString(36).slice(2)}`,
    order_id: '12345678-1234-1234-1234-123456789abc',
    retailer_id: '9abcdef0-1234-1234-1234-123456789abc',
    transaction_id: null,
    amount: 100,
    method: 'cash',
    status: 'completed',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    currency: 'KES',
    currency_status: 'KNOWN',
    ...over,
  } as unknown as PaymentListItem;
}

function pageResponse(items: PaymentListItem[]) {
  return {
    data: {
      data: {
        items,
        pagination: { page: 1, size: 20, total: items.length, pages: 1 },
      },
    },
  };
}

function renderPage() {
  return render(
    <MemoryRouter>
      <PaymentListPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('PaymentListPage currency display (R4)', () => {
  it('shows each row with its own order snapshot currency (UGX and KES)', async () => {
    vi.spyOn(api, 'get').mockResolvedValue(
      pageResponse([
        item({ amount: '10.50', currency: 'KES', currency_status: 'KNOWN' }),
        item({ amount: '3000', currency: 'UGX', currency_status: 'KNOWN' }),
      ]) as never,
    );
    renderPage();

    expect(await screen.findByText('KES 10.50')).toBeTruthy();
    expect(screen.getByText('UGX 3,000')).toBeTruthy();
    // counter-proof: the UGX row must not carry the KES label
    expect(screen.queryByText('KES 3,000')).toBeNull();
  });

  it('labels unknown/legacy currency rows without guessing KES', async () => {
    vi.spyOn(api, 'get').mockResolvedValue(
      pageResponse([
        item({ amount: '125', currency: null, currency_status: 'LEGACY_CURRENCY_UNVERIFIED' }),
        item({ amount: '80', currency: undefined, currency_status: undefined }),
      ]) as never,
    );
    renderPage();

    expect(await screen.findByText('LEGACY_CURRENCY_UNVERIFIED 125')).toBeTruthy();
    expect(screen.getByText('LEGACY_CURRENCY_UNVERIFIED 80')).toBeTruthy();
    expect(screen.queryByText('KES 125')).toBeNull();
    expect(screen.queryByText('KES 80')).toBeNull();
    expect(await screen.findByText(/Page total: not shown/i)).toBeTruthy();
  });

  it('does not sum a mixed-currency page', async () => {
    vi.spyOn(api, 'get').mockResolvedValue(
      pageResponse([
        item({ amount: '10.50', currency: 'KES', currency_status: 'KNOWN' }),
        item({ amount: '3000', currency: 'UGX', currency_status: 'KNOWN' }),
      ]) as never,
    );
    renderPage();

    expect(await screen.findByText(/Page total: not shown/i)).toBeTruthy();
    expect(screen.queryByText(/4,?250/)).toBeNull();
    expect(screen.queryByText(/3,010/)).toBeNull();
  });

  it('sums a single verified currency exactly, with no float rounding', async () => {
    vi.spyOn(api, 'get').mockResolvedValue(
      pageResponse([
        item({ amount: '1250.10', currency: 'KES', currency_status: 'KNOWN' }),
        item({ amount: '3000.255', currency: 'KES', currency_status: 'KNOWN' }),
      ]) as never,
    );
    renderPage();

    // exact decimal total; the float/Intl path renders 4,250.36 (rounded)
    expect(await screen.findByText('Page total: KES 4,250.355')).toBeTruthy();
    expect(screen.queryByText('KES 4,250.36')).toBeNull();
    expect(screen.queryByText('KES 4,250.35')).toBeNull();
  });

  it('keeps the order page payment-modal logic identical with the extra fields', async () => {
    const order = {
      id: '12345678-1234-1234-1234-123456789abc',
      total_amount: 5000,
      status: 'APPROVED',
    } as unknown as Order;
    const plain: PaymentData[] = [
      { id: 'p1', order_id: order.id, retailer_id: 'r', transaction_id: null,
        amount: 1000, method: 'cash', status: 'completed',
        created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' },
    ];
    const withCurrency = plain.map((p) => ({ ...p, currency: 'KES', currency_status: 'KNOWN' }));

    const fromPlain = calculatePaymentModalState(order, plain);
    const fromWithCurrency = calculatePaymentModalState(order, withCurrency as PaymentData[]);

    // protection: identical modal state with and without the new wire fields
    expect(fromWithCurrency).toEqual(fromPlain);
    expect(fromWithCurrency.remainingAmount).toBe(4000);
    expect(fromWithCurrency.allowCreditSale).toBe(false);
  });
});
