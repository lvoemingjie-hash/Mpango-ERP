import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PaymentRecordModal } from '@/components/ui/PaymentRecordModal';
import { RetailerPricingPage } from '@/pages/pricing/RetailerPricingPage';
import { pricingService } from '@/services/pricingService';

// Payment currency pass-through (P1) and pricing discoverability (P2).
// OrderList helpers are imported dynamically inside their tests so that a
// baseline lacking them yields per-test RED instead of a file-level failure.

vi.mock('@/services/retailerService', () => ({
  retailerService: {
    getAll: vi.fn().mockResolvedValue({
      data: { data: { items: [{ retailer: { id: 'retailer-1', name: 'Jeff Retailer UG' } }] } },
    }),
  },
}));

vi.mock('@/services/pricingService', () => ({
  pricingService: {
    getPrices: vi.fn().mockResolvedValue({
      data: {
        data: {
          items: [{
            sku_id: 'sku-1',
            sku_name: 'PWJEFF demo grain',
            sku_code: 'PWUG-TEST-U1',
            base_price: '1000',
            override_price: null,
            override_retired: false,
            currency: 'UGX',
            price: '1000',
            price_source: 'BASE_PRICE',
            unorderable_reason: null,
            pricing_revision: 1,
          }],
          total: 1,
        },
      },
    }),
    setBasePrice: vi.fn().mockResolvedValue({ data: { data: {} } }),
    setPrice: vi.fn().mockResolvedValue({ data: { data: {} } }),
  },
}));

vi.mock('@/stores/authStore', () => ({
  useAuthStore: (selector: (s: { user: unknown }) => unknown) =>
    selector({ user: { permissions: ['pricing:write'], roles: ['admin'] } }),
}));

function renderModal(currency: string | null | undefined, overrides?: { remainingAmount?: number }) {
  return render(
    <PaymentRecordModal
      open={true}
      onClose={vi.fn()}
      onSubmit={vi.fn().mockResolvedValue(undefined)}
      orderId="12345678-1234-1234-1234-123456789abc"
      orderTotal={5000}
      remainingAmount={overrides?.remainingAmount ?? 5000}
      currency={currency}
    />,
  );
}

describe('PaymentRecordModal currency display (P1)', () => {
  it('shows UGX total/label and no KES residue for a UGX order', () => {
    renderModal('UGX');
    expect(screen.getAllByText('UGX 5,000').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByLabelText('Amount (UGX) *')).toBeInTheDocument();
    expect(screen.queryByText(/KES 5,000/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Amount (KES) *')).not.toBeInTheDocument();
  });

  it('shows KES copy for a KES order', () => {
    renderModal('KES');
    expect(screen.getAllByText('KES 5,000').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByLabelText('Amount (KES) *')).toBeInTheDocument();
  });

  it('switches currency when the same modal is reused for another order', () => {
    const view = renderModal('UGX');
    expect(screen.getByLabelText('Amount (UGX) *')).toBeInTheDocument();
    view.rerender(
      <PaymentRecordModal
        open={true}
        onClose={vi.fn()}
        onSubmit={vi.fn().mockResolvedValue(undefined)}
        orderId="12345678-1234-1234-1234-123456789abc"
        orderTotal={5000}
        remainingAmount={5000}
        currency="KES"
      />,
    );
    expect(screen.getByLabelText('Amount (KES) *')).toBeInTheDocument();
    expect(screen.queryByLabelText('Amount (UGX) *')).not.toBeInTheDocument();
  });

  it('marks an unknown currency explicitly instead of defaulting to KES', () => {
    renderModal('XYZ');
    expect(screen.getAllByText(/LEGACY_CURRENCY_UNVERIFIED 5,000/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByLabelText(/Amount \(LEGACY_CURRENCY_UNVERIFIED\) \*/)).toBeInTheDocument();
    expect(screen.queryByText(/KES 5,000/)).not.toBeInTheDocument();
  });

  it('marks a missing currency explicitly instead of defaulting to KES', () => {
    renderModal(undefined);
    expect(screen.getAllByText(/LEGACY_CURRENCY_UNVERIFIED 5,000/).length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText(/KES 5,000/)).not.toBeInTheDocument();
  });

  it('shows the over-limit validation error in the order currency', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    const view = render(
      <PaymentRecordModal
        open={true}
        onClose={vi.fn()}
        onSubmit={onSubmit}
        orderId="12345678-1234-1234-1234-123456789abc"
        orderTotal={5000}
        remainingAmount={2000}
        currency="UGX"
      />,
    );
    await userEvent.selectOptions(screen.getByLabelText(/payment method/i), 'cash');
    await userEvent.type(screen.getByLabelText(/amount/i), '3000');
    // client guard: over-limit amount disables submission, so no POST can occur
    expect(screen.getByRole('button', { name: /record payment/i })).toBeDisabled();
    await userEvent.click(screen.getByRole('button', { name: /record payment/i }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(view.container.textContent).not.toContain('KES');
  });

  it('shows the full-credit validation error in the order currency', async () => {
    render(
      <PaymentRecordModal
        open={true}
        onClose={vi.fn()}
        onSubmit={vi.fn().mockResolvedValue(undefined)}
        orderId="12345678-1234-1234-1234-123456789abc"
        orderTotal={5000}
        remainingAmount={5000}
        currency="UGX"
        allowCreditSale={true}
      />,
    );
    await userEvent.selectOptions(screen.getByLabelText(/payment method/i), 'credit');
    const amount = screen.getByLabelText(/amount/i) as HTMLInputElement;
    expect(amount.readOnly).toBe(true);
    const note = screen.getByText(/Credit Sale:/).closest('div');
    expect(note).not.toBeNull();
    expect(note!.textContent).toContain('UGX 5,000');
    expect(note!.textContent).not.toContain('KES');
    expect(screen.queryByText(/KES 5,000/)).not.toBeInTheDocument();
  });

  it('keeps the submit payload unchanged and retries with the same idempotency key after a failure', async () => {
    const onSubmit = vi.fn()
      .mockRejectedValueOnce(new Error('gateway down'))
      .mockResolvedValueOnce(undefined);
    render(
      <PaymentRecordModal
        open={true}
        onClose={vi.fn()}
        onSubmit={onSubmit}
        orderId="12345678-1234-1234-1234-123456789abc"
        orderTotal={5000}
        remainingAmount={5000}
        currency="UGX"
      />,
    );
    await userEvent.selectOptions(screen.getByLabelText(/payment method/i), 'cash');
    await userEvent.type(screen.getByLabelText(/amount/i), '1250');
    await userEvent.click(screen.getByRole('button', { name: /record payment/i }));
    await screen.findByText(/gateway down/i);
    const retry = screen.getByRole('button', { name: /record payment/i });
    await waitFor(() => expect(retry).toBeEnabled());
    await userEvent.click(retry);
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(2));
    expect(onSubmit.mock.calls[0][0]).toEqual({ method: 'cash', amount: 1250 });
    expect(onSubmit.mock.calls[1][0]).toEqual(onSubmit.mock.calls[0][0]);
    expect(onSubmit.mock.calls[0][1]).toBe(onSubmit.mock.calls[1][1]);
  });

  it('carries order currency through the order-list modal bindings', async () => {
    const mod = (await import('@/pages/orders/OrderListPage')) as unknown as {
      paymentModalBindings?: (order: unknown, remaining: number | null) => unknown;
    };
    expect(typeof mod.paymentModalBindings).toBe('function');
    expect(mod.paymentModalBindings!(
      { id: 'ab-1', total_amount: '3600', currency: 'UGX' },
      1800,
    )).toEqual({ orderId: 'ab-1', orderTotal: 3600, remainingAmount: 1800, currency: 'UGX' });
  });

  it('formats the order-list success toast in the order currency', async () => {
    const mod = (await import('@/pages/orders/OrderListPage')) as unknown as {
      buildPaymentSuccessMessage?: (
        resp: { payment_id?: string | null; payment_amount?: string | number | null; payment_method?: string | null; status: string },
        currency: string | null | undefined,
        orderId: string,
      ) => string;
    };
    expect(typeof mod.buildPaymentSuccessMessage).toBe('function');
    const msg = mod.buildPaymentSuccessMessage!(
      { payment_id: 'p-1', payment_amount: '1200', payment_method: 'cash', status: 'partially_paid' },
      'UGX',
      '4f11254a-509a-445f-814d-674f7524fdb5',
    );
    expect(msg.startsWith('UGX 1,200')).toBe(true);
    expect(msg.includes('KES')).toBe(false);
  });
});

describe('RetailerPricingPage discoverability (P2)', () => {
  const oneRow = {
    data: { data: { items: [{
      sku_id: 'sku-1', sku_name: 'PWJEFF demo grain', sku_code: 'PWUG-TEST-U1',
      base_price: '1000', override_price: null, override_retired: false,
      currency: 'UGX', price: '1000', price_source: 'BASE_PRICE',
      unorderable_reason: null, pricing_revision: 1,
    }], total: 1 } },
  } as never;

  async function openWithRows(rowsResponse: Record<string, unknown> | null) {
    vi.mocked(pricingService.getPrices).mockReset();
    vi.mocked(pricingService.getPrices).mockResolvedValue((rowsResponse ?? oneRow) as never);
    render(<RetailerPricingPage />);
    const combo = screen.getByRole('combobox', { name: /customer/i }) as HTMLSelectElement;
    await waitFor(() => expect(combo.options.length).toBeGreaterThan(1), { timeout: 4000 });
    await userEvent.selectOptions(combo, 'retailer-1');
  }

  it('explains that a customer must be selected before rows appear', () => {
    const { container } = render(<RetailerPricingPage />);
    expect(screen.getByRole('status')).toHaveTextContent(/select a customer/i);
    expect(container.querySelector('tbody tr')).toBeNull();
  });

  it('names the two save actions distinctly per column', async () => {
    await openWithRows(null);
    expect(await screen.findByText(/PWJEFF demo grain/, undefined, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save base price' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save customer price' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Save$/ })).not.toBeInTheDocument();
  });

  it('distinguishes an empty result from the no-customer state', async () => {
    await openWithRows({ data: { data: { items: [], total: 0 } } });
    expect(await screen.findByRole('status', undefined, { timeout: 4000 })).toHaveTextContent(/no sellable units/i);
  });

  it('keeps base-price and customer-price saves on their own service calls', async () => {
    await openWithRows(null);
    const baseSave = await screen.findByRole('button', { name: 'Save base price' }, { timeout: 4000 });
    const baseInput = screen.getByLabelText('Base price value');
    await userEvent.clear(baseInput);
    await userEvent.type(baseInput, '1200');
    await userEvent.click(baseSave);
    await waitFor(() => expect(pricingService.setBasePrice).toHaveBeenCalledWith('sku-1', '1200', 1), { timeout: 4000 });
    expect(pricingService.setPrice).not.toHaveBeenCalled();
  });
});
