/**
 * DC-12R1-S3-S2B-I2C-I2 — Printable workspace tests (Contracts A–C).
 *
 * Covers (required + binding corrections):
 *  - Correct GET endpoint + exactly one request per view (retailer + cashier).
 *  - No POST/PUT/PATCH/DELETE issued by any print view.
 *  - Deterministic rendering from server fixtures; no financial calculation.
 *  - Print action calls window.print().
 *  - Pending/rejected declarations: render the server non_receipt_notice
 *    (which legitimately contains "NOT A RECEIPT"); never rendered as a formal
 *    receipt, never show a receipt number, never show "Payment Received".
 *  - Receipt view uses ONLY the Contract C endpoint; 404 → neutral copy only
 *    (no eligibility/payment/binding/supplier/internal-id disclosure).
 *  - Money rendered with EXACT server precision (large + high-precision
 *    amounts); never rounded via Number/parseFloat/Intl.
 *  - 401/403/404/5xx are sanitized to fixed neutral strings.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, act, waitFor, cleanup } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { api } from '@/services/api';
import {
  clientOrderService,
} from '@/services/clientOrderService';
import { orderService } from '@/services/orderService';
import {
  getClientDeclarationPrint,
  getClientReceipt,
  getCashierDeclarationPrint,
  getCashierReceipt,
} from '@/services/declarationService';
// R1 Correction 2/3: authentic cashier confirmation + real AppRouter route tree.
import DeclarationQueuePage from '@/pages/finance/DeclarationQueuePage';
import { AppRouter } from '@/router/AppRouter';
import { useAuthStore } from '@/stores/authStore';
import { OrderPrintPage } from '@/pages/print/OrderPrintPage';
import { DeclarationPrintPage } from '@/pages/print/DeclarationPrintPage';
import { ReceiptPrintPage } from '@/pages/print/ReceiptPrintPage';
import { formatKes, formatDecimalMoney } from '@/utils/printFormat';
import { sanitizePrintError } from '@/utils/printError';
import type { AxiosError } from 'axios';
import type { PaymentDeclaration } from '@/types/declaration';

vi.mock('@/services/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

const mockGet = vi.mocked(api.get);

function data(body: unknown) {
  return { data: body };
}

/** Build a 200 envelope mirroring backend DataResponse. */
function ok<T>(d: T) {
  return data({ success: true, data: d, message: null, timestamp: '2026-08-09T10:00:00Z' });
}

/** Build an axios-like rejection carrying an HTTP status + a (non-neutral) body. */
function rejectWith(status: number, body: unknown): { response: { status: number; data: unknown } } {
  return { response: { status, data: body } };
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/client/orders/:orderId/print" element={<OrderPrintPage mode="client" />} />
        <Route path="/orders/:orderId/print" element={<OrderPrintPage mode="cashier" />} />
        <Route path="/client/declarations/:declarationId/print" element={<DeclarationPrintPage mode="client" />} />
        <Route path="/declarations/:declarationId/print" element={<DeclarationPrintPage mode="cashier" />} />
        <Route path="/client/declarations/:declarationId/receipt" element={<ReceiptPrintPage mode="client" />} />
        <Route path="/declarations/:declarationId/receipt" element={<ReceiptPrintPage mode="cashier" />} />
      </Routes>
    </MemoryRouter>,
  );
}

const ORDER_PRINT = {
  document_type: 'order',
  order_id: 'ord-123',
  status: 'CONFIRMED',
  supplier_name: 'Sunrise Wholesalers',
  retailer_name: 'Kibera Duka',
  items: [
    { product_name: 'Sugar 1kg', sku_code: 'SUG-1KG', quantity: 3, unit_price: '150.00', subtotal: '450.00' },
    { product_name: 'Rice 2kg', sku_code: 'RIC-2KG', quantity: 2, unit_price: '320.50', subtotal: '641.00' },
  ],
  total_amount: '1091.00',
  item_count: 2,
  notes: 'Handle with care',
  created_at: '2026-08-01T08:00:00Z',
  created_at_eat: '2026-08-01T11:00:00+03:00',
};

// Large + high-precision amounts (binding correction #1): values that would
// round/lose precision if parsed via Number/parseFloat.
const ORDER_PRINT_BIG = {
  ...ORDER_PRINT,
  order_id: 'ord-big',
  total_amount: '9007199254740993.125', // > 2^53 — Number() would corrupt this
  items: [
    { product_name: 'Bulk item', sku_code: 'BLK', quantity: 1, unit_price: '0.000001', subtotal: '9007199254740993.125' },
  ],
};

const DECL_PENDING = {
  document_type: 'payment_declaration',
  declaration_id: 'dec-pending',
  order_id: 'ord-123',
  supplier_name: 'Sunrise Wholesalers',
  retailer_name: 'Kibera Duka',
  status: 'pending',
  declared_amount: '1091.00',
  method: 'cash',
  transfer_reference: null,
  is_receipt: false,
  non_receipt_notice: 'This is a payment declaration and NOT A RECEIPT. It has not been confirmed.',
  rejection_reason: null,
  submitted_at: '2026-08-02T08:00:00Z',
  submitted_at_eat: '2026-08-02T11:00:00+03:00',
  confirmed_at: null,
  confirmed_at_eat: null,
  rejected_at: null,
  rejected_at_eat: null,
  order_status: 'CONFIRMED',
};

const DECL_REJECTED = {
  ...DECL_PENDING,
  declaration_id: 'dec-rejected',
  status: 'rejected',
  non_receipt_notice: 'This declaration was rejected and is NOT A RECEIPT.',
  rejection_reason: 'Could not verify transfer',
  rejected_at: '2026-08-02T10:00:00Z',
  rejected_at_eat: '2026-08-02T13:00:00+03:00',
};

const DECL_CONFIRMED = {
  ...DECL_PENDING,
  declaration_id: 'dec-confirmed',
  status: 'confirmed',
  is_receipt: true,
  non_receipt_notice: null,
  confirmed_at: '2026-08-02T09:00:00Z',
  confirmed_at_eat: '2026-08-02T12:00:00+03:00',
};

const RECEIPT = {
  document_type: 'receipt',
  declaration_id: 'dec-confirmed',
  order_id: 'ord-123',
  supplier_name: 'Sunrise Wholesalers',
  retailer_name: 'Kibera Duka',
  receipt_number: 'RCT-20260802-000001',
  confirmed_amount: '1091.00',
  method: 'cash',
  confirmed_at: '2026-08-02T09:00:00Z',
  confirmed_at_eat: '2026-08-02T12:00:00+03:00',
  declared_amount: '1091.00',
  order_status: 'CONFIRMED',
  order_total_amount: '1091.00',
};

beforeEach(() => {
  vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// Services: correct endpoint + exactly one GET; no writes.
// ---------------------------------------------------------------------------

describe('I2C-I2 print services — endpoints', () => {
  it('clientOrderService.getPrint → GET /client/orders/:id/print (once)', async () => {
    mockGet.mockResolvedValueOnce(ok(ORDER_PRINT) as never);
    await clientOrderService.getPrint('ord-123');
    expect(mockGet).toHaveBeenCalledTimes(1);
    expect(mockGet).toHaveBeenCalledWith('/client/orders/ord-123/print');
  });

  it('orderService.getPrint → GET /orders/:id/print (once)', async () => {
    mockGet.mockResolvedValueOnce(ok(ORDER_PRINT) as never);
    await orderService.getPrint('ord-456');
    expect(mockGet).toHaveBeenCalledTimes(1);
    expect(mockGet).toHaveBeenCalledWith('/orders/ord-456/print');
  });

  it('getClientDeclarationPrint → GET /client/declarations/:id/print (once)', async () => {
    mockGet.mockResolvedValueOnce(ok(DECL_PENDING) as never);
    await getClientDeclarationPrint('dec-1');
    expect(mockGet).toHaveBeenCalledTimes(1);
    expect(mockGet).toHaveBeenCalledWith('/client/declarations/dec-1/print');
  });

  it('getCashierDeclarationPrint → GET /declarations/:id/print (once)', async () => {
    mockGet.mockResolvedValueOnce(ok(DECL_PENDING) as never);
    await getCashierDeclarationPrint('dec-2');
    expect(mockGet).toHaveBeenCalledTimes(1);
    expect(mockGet).toHaveBeenCalledWith('/declarations/dec-2/print');
  });

  it('getClientReceipt → GET /client/declarations/:id/receipt (Contract C only)', async () => {
    mockGet.mockResolvedValueOnce(ok(RECEIPT) as never);
    await getClientReceipt('dec-3');
    expect(mockGet).toHaveBeenCalledTimes(1);
    expect(mockGet).toHaveBeenCalledWith('/client/declarations/dec-3/receipt');
  });

  it('getCashierReceipt → GET /declarations/:id/receipt (Contract C only)', async () => {
    mockGet.mockResolvedValueOnce(ok(RECEIPT) as never);
    await getCashierReceipt('dec-4');
    expect(mockGet).toHaveBeenCalledTimes(1);
    expect(mockGet).toHaveBeenCalledWith('/declarations/dec-4/receipt');
  });

  it('encodes dynamic path segments (no injection / traversal)', async () => {
    mockGet.mockResolvedValueOnce(ok(ORDER_PRINT) as never);
    await clientOrderService.getPrint('a/b c');
    expect(mockGet).toHaveBeenCalledWith('/client/orders/a%2Fb%20c/print');
  });
});

// ---------------------------------------------------------------------------
// Order print view (Contract A)
// ---------------------------------------------------------------------------

describe('OrderPrintPage', () => {
  it('renders server-authoritative fields deterministically (retailer)', async () => {
    mockGet.mockResolvedValueOnce(ok(ORDER_PRINT) as never);
    renderAt('/client/orders/ord-123/print');

    expect(await screen.findByTestId('order-print-document')).toBeInTheDocument();
    expect(screen.getByText('Sunrise Wholesalers')).toBeInTheDocument();
    expect(screen.getByText('Kibera Duka')).toBeInTheDocument();
    expect(screen.getByText('Sugar 1kg')).toBeInTheDocument();
    // Exact server string rendered (no recompute): KES 1,091.00
    expect(screen.getByTestId('order-print-total')).toHaveTextContent('KES 1,091.00');
    // Exactly one GET, no writes.
    expect(mockGet).toHaveBeenCalledTimes(1);
    expect(mockGet).toHaveBeenCalledWith('/client/orders/ord-123/print');
    expect(api.post).not.toHaveBeenCalled();
    expect(api.put).not.toHaveBeenCalled();
    expect(api.patch).not.toHaveBeenCalled();
    expect(api.delete).not.toHaveBeenCalled();
  });

  it('uses the cashier endpoint under the cashier route', async () => {
    mockGet.mockResolvedValueOnce(ok(ORDER_PRINT) as never);
    renderAt('/orders/ord-123/print');
    await screen.findByTestId('order-print-document');
    expect(mockGet).toHaveBeenCalledWith('/orders/ord-123/print');
  });

  it('Print button calls window.print()', async () => {
    mockGet.mockResolvedValueOnce(ok(ORDER_PRINT) as never);
    const spy = vi.spyOn(window, 'print').mockImplementation(() => {});
    renderAt('/client/orders/ord-123/print');
    const btn = await screen.findByTestId('order-print-button');
    fireEvent.click(btn);
    expect(spy).toHaveBeenCalledTimes(1);
    spy.mockRestore();
  });

  it('renders exact large + high-precision amounts without rounding', async () => {
    mockGet.mockResolvedValueOnce(ok(ORDER_PRINT_BIG) as never);
    renderAt('/client/orders/ord-big/print');
    await screen.findByTestId('order-print-document');
    // > 2^53 preserved exactly; high-precision unit price preserved verbatim.
    expect(screen.getByTestId('order-print-total')).toHaveTextContent('KES 9,007,199,254,740,993.125');
    expect(screen.getByText('KES 0.000001')).toBeInTheDocument();
  });

  it('404 → neutral copy; never echoes server detail/internal id', async () => {
    mockGet.mockRejectedValueOnce(
      rejectWith(404, { detail: { code: 'ORDER_NOT_FOUND', message: 'Order ord-123 not found' } }) as never,
    );
    renderAt('/client/orders/ord-123/print');
    const err = await screen.findByTestId('order-print-error');
    expect(err).toHaveTextContent('This document is not available.');
    expect(err.textContent).not.toContain('ORDER_NOT_FOUND');
    expect(err.textContent).not.toContain('ord-123');
    expect(err.textContent).not.toContain('not found');
  });

  it('403 → neutral access copy', async () => {
    mockGet.mockRejectedValueOnce(
      rejectWith(403, { detail: { code: 'PERMISSION_DENIED', message: 'no orders:read' } }) as never,
    );
    renderAt('/client/orders/ord-123/print');
    const err = await screen.findByTestId('order-print-error');
    expect(err).toHaveTextContent('You do not have access to this document.');
    expect(err.textContent).not.toContain('PERMISSION_DENIED');
    expect(err.textContent).not.toContain('orders:read');
  });

  it('5xx → neutral unavailable copy', async () => {
    mockGet.mockRejectedValueOnce(
      rejectWith(500, { detail: { code: 'DB_ERROR', message: 'relation t_a.orders missing' } }) as never,
    );
    renderAt('/client/orders/ord-123/print');
    const err = await screen.findByTestId('order-print-error');
    expect(err).toHaveTextContent(/couldn’t load this document/i);
    expect(err.textContent).not.toContain('DB_ERROR');
    // Schema name must never leak.
    expect(err.textContent).not.toContain('t_a.orders');
  });
});

// ---------------------------------------------------------------------------
// Declaration print view (Contract B) — pending/rejected are NOT receipts
// ---------------------------------------------------------------------------

describe('DeclarationPrintPage — pending/rejected are NOT receipts', () => {
  it('renders the server non_receipt_notice verbatim (incl. "NOT A RECEIPT") for pending', async () => {
    mockGet.mockResolvedValueOnce(ok(DECL_PENDING) as never);
    renderAt('/client/declarations/dec-pending/print');
    const notice = await screen.findByTestId('declaration-non-receipt-notice');
    expect(notice).toHaveTextContent('NOT A RECEIPT');
    expect(notice.textContent).toContain('not been confirmed');
    // Never presented as a formal receipt / receipt number / Payment Received.
    expect(screen.queryByTestId('receipt-number')).not.toBeInTheDocument();
    expect(screen.queryByText(/Payment Received/i)).not.toBeInTheDocument();
  });

  it('pending status label never says "received" or "receipt"', async () => {
    mockGet.mockResolvedValueOnce(ok(DECL_PENDING) as never);
    renderAt('/client/declarations/dec-pending/print');
    await screen.findByTestId('declaration-print-document');
    const status = screen.getByTestId('declaration-status');
    expect(status.textContent).toMatch(/pending/i);
    expect(status.textContent).not.toMatch(/received|receipt/i);
  });

  it('rejected: shows reason + non-receipt notice, never a receipt number', async () => {
    mockGet.mockResolvedValueOnce(ok(DECL_REJECTED) as never);
    renderAt('/client/declarations/dec-rejected/print');
    await screen.findByTestId('declaration-print-document');
    expect(screen.getByTestId('declaration-non-receipt-notice')).toHaveTextContent('NOT A RECEIPT');
    expect(screen.getByText('Could not verify transfer')).toBeInTheDocument();
    expect(screen.queryByTestId('receipt-number')).not.toBeInTheDocument();
    expect(screen.queryByText(/Payment Received/i)).not.toBeInTheDocument();
  });

  it('confirmed: no non-receipt notice; declared amount rendered exactly', async () => {
    mockGet.mockResolvedValueOnce(ok(DECL_CONFIRMED) as never);
    renderAt('/client/declarations/dec-confirmed/print');
    await screen.findByTestId('declaration-print-document');
    expect(screen.queryByTestId('declaration-non-receipt-notice')).not.toBeInTheDocument();
    expect(screen.getByText('KES 1,091.00')).toBeInTheDocument();
  });

  it('uses cashier endpoint under cashier route; one GET; no writes', async () => {
    mockGet.mockResolvedValueOnce(ok(DECL_PENDING) as never);
    renderAt('/declarations/dec-pending/print');
    await screen.findByTestId('declaration-print-document');
    expect(mockGet).toHaveBeenCalledWith('/declarations/dec-pending/print');
    expect(api.post).not.toHaveBeenCalled();
  });

  it('Print button calls window.print()', async () => {
    mockGet.mockResolvedValueOnce(ok(DECL_PENDING) as never);
    const spy = vi.spyOn(window, 'print').mockImplementation(() => {});
    renderAt('/client/declarations/dec-pending/print');
    fireEvent.click(await screen.findByTestId('declaration-print-button'));
    expect(spy).toHaveBeenCalledTimes(1);
    spy.mockRestore();
  });
});

// ---------------------------------------------------------------------------
// Receipt print view (Contract C) — only Contract C endpoint; sanitized 404
// ---------------------------------------------------------------------------

describe('ReceiptPrintPage — Contract C only', () => {
  it('renders the receipt from the /receipt endpoint only', async () => {
    mockGet.mockResolvedValueOnce(ok(RECEIPT) as never);
    renderAt('/client/declarations/dec-confirmed/receipt');
    const doc = await screen.findByTestId('receipt-print-document');
    expect(doc).toBeInTheDocument();
    expect(screen.getByTestId('receipt-number')).toHaveTextContent('RCT-20260802-000001');
    expect(screen.getByTestId('receipt-confirmed-amount')).toHaveTextContent('KES 1,091.00');
    expect(mockGet).toHaveBeenCalledTimes(1);
    expect(mockGet).toHaveBeenCalledWith('/client/declarations/dec-confirmed/receipt');
    expect(api.post).not.toHaveBeenCalled();
    expect(api.put).not.toHaveBeenCalled();
    expect(api.patch).not.toHaveBeenCalled();
    expect(api.delete).not.toHaveBeenCalled();
  });

  it('uses cashier receipt endpoint under the cashier route', async () => {
    mockGet.mockResolvedValueOnce(ok(RECEIPT) as never);
    renderAt('/declarations/dec-confirmed/receipt');
    await screen.findByTestId('receipt-print-document');
    expect(mockGet).toHaveBeenCalledWith('/declarations/dec-confirmed/receipt');
  });

  it('Print button calls window.print()', async () => {
    mockGet.mockResolvedValueOnce(ok(RECEIPT) as never);
    const spy = vi.spyOn(window, 'print').mockImplementation(() => {});
    renderAt('/client/declarations/dec-confirmed/receipt');
    fireEvent.click(await screen.findByTestId('receipt-print-button'));
    expect(spy).toHaveBeenCalledTimes(1);
    spy.mockRestore();
  });

  it('receipt 404 → neutral copy only; no eligibility/payment/binding/supplier disclosure', async () => {
    // The real RECEIPT_NOT_AVAILABLE body is intentionally rich-looking; the UI
    // must surface ONLY the neutral string.
    mockGet.mockRejectedValueOnce(
      rejectWith(404, {
        detail: {
          code: 'RECEIPT_NOT_AVAILABLE',
          message: 'Receipt not available',
          eligibility: 'confirmed && payment_completed',
          payment_id: 'pay-internal-uuid',
          binding: 'inactive',
          supplier: 'Sunrise Wholesalers',
        },
      }) as never,
    );
    renderAt('/client/declarations/dec-confirmed/receipt');
    const err = await screen.findByTestId('receipt-print-error');
    expect(err).toHaveTextContent('This document is not available.');
    expect(err.textContent).not.toContain('RECEIPT_NOT_AVAILABLE');
    expect(err.textContent).not.toContain('eligibility');
    expect(err.textContent).not.toContain('payment_id');
    expect(err.textContent).not.toContain('pay-internal-uuid');
    expect(err.textContent).not.toContain('binding');
    expect(err.textContent).not.toContain('Sunrise Wholesalers');
    expect(err.textContent).not.toContain('Receipt not available');
  });

  it('receipt 403 → neutral access copy', async () => {
    mockGet.mockRejectedValueOnce(
      rejectWith(403, { detail: { code: 'PERMISSION_DENIED', message: 'no payments:read' } }) as never,
    );
    renderAt('/client/declarations/dec-confirmed/receipt');
    const err = await screen.findByTestId('receipt-print-error');
    expect(err).toHaveTextContent('You do not have access to this document.');
    expect(err.textContent).not.toContain('payments:read');
  });
});

// ---------------------------------------------------------------------------
// Money formatting unit: string-only, no Number/parseFloat/Intl parse
// ---------------------------------------------------------------------------

describe('printFormat — string-only, exact precision', () => {
  it('groups thousands without altering digits', () => {
    expect(formatDecimalMoney('1091.00')).toBe('1,091.00');
    expect(formatDecimalMoney('1234567.8900')).toBe('1,234,567.8900');
  });

  it('preserves large amounts beyond 2^53 exactly', () => {
    expect(formatDecimalMoney('9007199254740993.125')).toBe('9,007,199,254,740,993.125');
  });

  it('preserves high-precision decimals verbatim', () => {
    expect(formatDecimalMoney('0.000001')).toBe('0.000001');
    expect(formatDecimalMoney('0.5')).toBe('0.5');
  });

  it('handles sign and empty/malformed input defensively (no NaN)', () => {
    expect(formatDecimalMoney('-1250.5')).toBe('-1,250.5');
    expect(formatDecimalMoney('')).toBe('');
    expect(formatDecimalMoney(null)).toBe('');
    expect(formatDecimalMoney(undefined)).toBe('');
    expect(formatDecimalMoney('not-a-number')).toBe('not-a-number');
  });

  it('formatKes prefixes KES without rounding', () => {
    expect(formatKes('9007199254740993.125')).toBe('KES 9,007,199,254,740,993.125');
  });
});

// ---------------------------------------------------------------------------
// sanitizePrintError — status-only, never body-derived
// ---------------------------------------------------------------------------

describe('sanitizePrintError — status-only neutral copy', () => {
  const rich = { detail: { code: 'X', message: 'secret schema.t_a leak', id: 'uuid' } };

  it('401 → auth copy', () => {
    expect(sanitizePrintError(rejectWith(401, rich) as unknown as AxiosError)).toBe(
      'Please sign in to view this document.',
    );
  });
  it('403 → access copy', () => {
    expect(sanitizePrintError(rejectWith(403, rich) as unknown as AxiosError)).toBe(
      'You do not have access to this document.',
    );
  });
  it('404 → neutral not-available copy', () => {
    expect(sanitizePrintError(rejectWith(404, rich) as unknown as AxiosError)).toBe(
      'This document is not available.',
    );
  });
  it('500 → unavailable copy', () => {
    expect(sanitizePrintError(rejectWith(500, rich) as unknown as AxiosError)).toMatch(
      /couldn’t load this document/i,
    );
  });
  it('network (no response) → unavailable copy', () => {
    expect(sanitizePrintError({ request: {} } as unknown as AxiosError)).toMatch(
      /couldn’t load this document/i,
    );
  });
  it('never echoes server body/code/id regardless of status', () => {
    for (const status of [401, 403, 404, 500]) {
      const msg = sanitizePrintError(rejectWith(status, rich) as unknown as AxiosError);
      expect(msg).not.toContain('secret');
      expect(msg).not.toContain('schema.t_a');
      expect(msg).not.toContain('uuid');
      expect(msg).not.toContain('X');
    }
  });
});


// ===========================================================================
// R2 Correction 2 — authentic three-layer confirmation envelope.
//
// Reproduces the real boundary exactly:
//   AxiosResponse
//     .data = ApiResponse<DeclarationConfirmResponse>   ({ success, data, timestamp })
//       .data = DeclarationConfirmResponse               ({ id, ... })
//         .id = RESPONSE_ID
//
// confirmDeclaration's declared contract (declarationService.ts, NOT modified)
// is Promise<ApiResponse<DeclarationConfirmResponse>>; it returns resp.data
// (the ApiResponse envelope). So the receipt identity is at resp.data.id.
// ===========================================================================

/** Innermost DeclarationConfirmResponse shape (only `id` is consumed). */
function confirmResponsePayload(id: unknown) {
  return {
    id,
    order_id: 'ord-1',
    status: 'confirmed' as const,
    confirmation_payment_id: 'pay-1',
    receipt_number: 'RCT-20260802-000001',
    order_status: 'CONFIRMED',
    confirmed_at: '2026-08-02T09:00:00Z',
  };
}

/** ApiResponse<T> envelope: { success, data: T, timestamp }. */
function confirmApiEnvelope(payload: unknown) {
  return {
    success: true,
    data: payload,
    timestamp: '2026-08-09T10:00:00Z',
  };
}

/** AxiosResponse<T>: { data: T }. This is what api.post resolves with. */
function axiosResponse(body: unknown) {
  return { data: body };
}

/** Full authentic success: axiosResponse(confirmApiEnvelope(confirmResponsePayload(id))). */
function authenticConfirmSuccess(id: unknown) {
  return axiosResponse(confirmApiEnvelope(confirmResponsePayload(id)));
}

/** A pending declaration row used to seed the cashier queue. */
function pendingDeclaration(declId: string): PaymentDeclaration {
  return {
    id: declId,
    order_id: 'ord-1',
    declared_amount: '1091.00',
    method: 'cash',
    transfer_reference: null,
    status: 'pending',
    submitted_at: '2026-08-02T08:00:00Z',
    confirmed_at: null,
    rejected_at: null,
    reason: null,
    receipt_number: null,
    order_status: 'CONFIRMED',
  };
}

/** Authentic list response (axiosResponse(ApiResponse(PaginatedData))). */
function authenticListResponse(items: PaymentDeclaration[]) {
  return axiosResponse({
    success: true,
    data: { items, pagination: { page: 1, size: 20, total: items.length, pages: items.length ? 1 : 0 } },
    timestamp: '2026-08-09T10:00:00Z',
  });
}

const CASHIER_USER = {
  id: 'cashier-1',
  email: 'cashier@example.com',
  full_name: 'Cashier',
  tenant_id: 'tenant-a',
  tenant_schema: 't_a',
  roles: ['admin'],
  permissions: ['payments:read', 'payments:create'],
};

/** Seed the cashier queue with one pending declaration, then render it. */
async function renderQueueWithPending(declId: string) {
  useAuthStore.setState({
    accessToken: 't',
    refreshToken: 'r',
    user: CASHIER_USER,
    tenantCode: 'TENA',
    retailerPortalCode: null,
  });
  // Persistent authentic list response (queue reloads after confirm).
  mockGet.mockReturnValue(authenticListResponse([pendingDeclaration(declId)]) as never);
  const rendered = render(
    <MemoryRouter initialEntries={['/declarations']}>
      <Routes>
        <Route path="/declarations" element={<DeclarationQueuePage />} />
      </Routes>
    </MemoryRouter>,
  );
  // Anchor on the confirm button (present for a pending row; robust to formatting).
  await waitFor(() => expect(rendered.container.querySelector('button')).toBeTruthy());
  return rendered;
}

describe('R2 Correction 2 — authentic-envelope response-authoritative receipt link', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGet.mockReset();
    vi.mocked(api.post).mockReset();
    useAuthStore.setState({
      accessToken: null,
      refreshToken: null,
      user: null,
      tenantCode: null,
      retailerPortalCode: null,
    });
  });

  it('1. POST receives REQUEST_ID exactly once; RESPONSE_ID differs; link uses encoded RESPONSE_ID', async () => {
    const REQUEST_ID = 'dec-request-aaa';
    const RESPONSE_ID = 'dec-response-bbb';
    await renderQueueWithPending(REQUEST_ID);
    vi.mocked(api.post).mockResolvedValueOnce(authenticConfirmSuccess(RESPONSE_ID) as never);

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /confirm/i }));
    });

    expect(api.post).toHaveBeenCalledTimes(1);
    expect(api.post).toHaveBeenCalledWith(`/declarations/${REQUEST_ID}/confirm`);

    const link = await screen.findByTestId('confirmed-receipt-link');
    expect(link).toHaveAttribute('href', `/declarations/${encodeURIComponent(RESPONSE_ID)}/receipt`);
    expect(link.getAttribute('href')).not.toContain(REQUEST_ID);
    expect(REQUEST_ID).not.toBe(RESPONSE_ID);
  });

  it('2. no additional POST/PUT/PATCH/DELETE occurs', async () => {
    const REQUEST_ID = 'dec-req-2';
    const RESPONSE_ID = 'dec-resp-2';
    await renderQueueWithPending(REQUEST_ID);
    vi.mocked(api.post).mockResolvedValueOnce(authenticConfirmSuccess(RESPONSE_ID) as never);
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /confirm/i }));
    });
    await screen.findByTestId('confirmed-receipt-link');
    expect(api.post).toHaveBeenCalledTimes(1);
    expect(api.put).not.toHaveBeenCalled();
    expect(api.patch).not.toHaveBeenCalled();
    expect(api.delete).not.toHaveBeenCalled();
  });

  it('3. link uses encoded RESPONSE_ID from resp.data.id only', async () => {
    const REQUEST_ID = 'dec-req-3';
    const RESPONSE_ID = 'dec/resp with space';
    await renderQueueWithPending(REQUEST_ID);
    vi.mocked(api.post).mockResolvedValueOnce(authenticConfirmSuccess(RESPONSE_ID) as never);
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /confirm/i }));
    });
    const link = await screen.findByTestId('confirmed-receipt-link');
    expect(link).toHaveAttribute('href', `/declarations/${encodeURIComponent(RESPONSE_ID)}/receipt`);
  });

  it.each([
    ['missing outer data', { success: true, timestamp: 't' }],
    ['null outer data', { success: true, data: null, timestamp: 't' }],
  ])('5/6. response with %s exposes NO receipt link', async (_label, envelope) => {
    const REQUEST_ID = 'dec-req-env';
    await renderQueueWithPending(REQUEST_ID);
    // Authentic axiosResponse shape, but the ApiResponse envelope lacks valid data.
    vi.mocked(api.post).mockResolvedValueOnce(axiosResponse(envelope) as never);
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /confirm/i }));
    });
    await waitFor(() => expect(screen.queryByTestId('confirmed-receipt-link')).not.toBeInTheDocument());
    expect(screen.getByTestId('receipt-link-unavailable')).toBeInTheDocument();
    expect(api.post).toHaveBeenCalledTimes(1);
  });

  it('7. response with missing nested id exposes NO receipt link', async () => {
    const REQUEST_ID = 'dec-req-noid';
    await renderQueueWithPending(REQUEST_ID);
    // ApiResponse envelope present, inner object has no `id`.
    vi.mocked(api.post).mockResolvedValueOnce(
      axiosResponse(confirmApiEnvelope({ order_id: 'ord-1', status: 'confirmed' })) as never,
    );
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /confirm/i }));
    });
    await waitFor(() => expect(screen.queryByTestId('confirmed-receipt-link')).not.toBeInTheDocument());
    expect(screen.getByTestId('receipt-link-unavailable')).toBeInTheDocument();
  });

  it.each([
    ['null nested id', null],
    ['empty nested id', ''],
    ['non-string nested id (number)', 12345],
    ['non-string nested id (object)', { x: 1 }],
  ])('8. response with %s nested id exposes NO receipt link', async (_label, badId) => {
    const REQUEST_ID = 'dec-req-bad';
    await renderQueueWithPending(REQUEST_ID);
    vi.mocked(api.post).mockResolvedValueOnce(
      axiosResponse(confirmApiEnvelope(confirmResponsePayload(badId))) as never,
    );
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /confirm/i }));
    });
    await waitFor(() => expect(screen.queryByTestId('confirmed-receipt-link')).not.toBeInTheDocument());
    expect(screen.getByTestId('receipt-link-unavailable')).toBeInTheDocument();
  });

  it('9. flattened legacy mock exposes NO receipt link', async () => {
    const REQUEST_ID = 'dec-req-flat';
    // Forbidden flattened shape (missing the ApiResponse envelope layer).
    vi.mocked(api.post).mockResolvedValueOnce({ data: { id: 'flattened-id' } } as never);
    await renderQueueWithPending(REQUEST_ID);
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /confirm/i }));
    });
    await waitFor(() => expect(screen.queryByTestId('confirmed-receipt-link')).not.toBeInTheDocument());
    expect(screen.getByTestId('receipt-link-unavailable')).toBeInTheDocument();
  });

  it('10. confirmation rejection/error exposes NO receipt link', async () => {
    const REQUEST_ID = 'dec-req-rej';
    await renderQueueWithPending(REQUEST_ID);
    vi.mocked(api.post).mockRejectedValueOnce(rejectWith(409, { detail: { code: 'CONFLICT', message: 'already' } }) as never);
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /confirm/i }));
    });
    await waitFor(() => {
      expect(screen.queryByTestId('confirmed-receipt-link')).not.toBeInTheDocument();
      expect(screen.queryByTestId('receipt-link-unavailable')).not.toBeInTheDocument();
    });
    expect(api.post).toHaveBeenCalledTimes(1);
  });

  it('11/12. confirmation POST occurs exactly once; link href targets Contract C only', async () => {
    const REQUEST_ID = 'dec-req-link';
    const RESPONSE_ID = 'dec-resp-link';
    await renderQueueWithPending(REQUEST_ID);
    vi.mocked(api.post).mockResolvedValueOnce(authenticConfirmSuccess(RESPONSE_ID) as never);
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /confirm/i }));
    });
    const link = await screen.findByTestId('confirmed-receipt-link');
    // Link target is Contract C only (encoded RESPONSE_ID; excludes REQUEST_ID).
    expect(link).toHaveAttribute('href', `/declarations/${encodeURIComponent(RESPONSE_ID)}/receipt`);
    expect(link.getAttribute('href')).not.toContain(REQUEST_ID);
    // Confirm POST happened exactly once; no PUT/PATCH/DELETE.
    expect(api.post).toHaveBeenCalledTimes(1);
    expect(api.put).not.toHaveBeenCalled();
    expect(api.patch).not.toHaveBeenCalled();
    expect(api.delete).not.toHaveBeenCalled();
  });
});

// ===========================================================================
// R2 Correction 3 — complete actual AppRouter guard/endpoint matrix.
//
// Renders the REAL <AppRouter/> (createBrowserRouter tree, real
// RetailerRoute/WholesalerRoute guards, real ClientLayout/MainLayout, real
// print pages). Parameterized over all six print/receipt routes for both
// retailer and wholesaler sessions. No fake guards, no source scanning, no
// guard edits.
// ===========================================================================

const ORDER_PRINT_FIXTURE = {
  document_type: 'order',
  order_id: 'ord-route',
  status: 'CONFIRMED',
  supplier_name: 'S',
  retailer_name: 'R',
  items: [],
  total_amount: '10.00',
  item_count: 0,
  notes: null,
  created_at: '2026-08-01T00:00:00Z',
  created_at_eat: '2026-08-01T00:00:00+03:00',
};
const DECL_PRINT_FIXTURE = {
  document_type: 'payment_declaration',
  declaration_id: 'dec-route',
  order_id: 'ord-route',
  supplier_name: 'S',
  retailer_name: 'R',
  status: 'pending',
  declared_amount: '10.00',
  method: 'cash',
  transfer_reference: null,
  is_receipt: false,
  non_receipt_notice: 'NOT A RECEIPT',
  rejection_reason: null,
  submitted_at: '2026-08-02T00:00:00Z',
  submitted_at_eat: '2026-08-02T00:00:00+03:00',
  confirmed_at: null,
  confirmed_at_eat: null,
  rejected_at: null,
  rejected_at_eat: null,
  order_status: 'CONFIRMED',
};
const RECEIPT_FIXTURE = {
  document_type: 'receipt',
  declaration_id: 'dec-route',
  order_id: 'ord-route',
  supplier_name: 'S',
  retailer_name: 'R',
  receipt_number: 'RCT-20260802-000001',
  confirmed_amount: '10.00',
  method: 'cash',
  confirmed_at: '2026-08-02T00:00:00Z',
  confirmed_at_eat: '2026-08-02T00:00:00+03:00',
  declared_amount: '10.00',
  order_status: 'CONFIRMED',
  order_total_amount: '10.00',
};

const RETAILER_USER = {
  id: 'r1', email: 'r@e.com', full_name: 'R',
  tenant_id: 't1', tenant_schema: 't_1',
  roles: ['retailer_operator'], permissions: [],
};
const WHOLESALER_USER = {
  id: 'w1', email: 'w@e.com', full_name: 'W',
  tenant_id: 't1', tenant_schema: 't_1',
  roles: ['admin'], permissions: [],
};

/** The expected GET endpoint + print document testid for a route (allow cases). */
function routeExpectations(path: string): { endpoint: string; opposite: string; testid: string } | null {
  // endpoint must match concretePath() output (all :id → 'ord-route').
  if (path === '/client/orders/:id/print') return { endpoint: '/client/orders/ord-route/print', opposite: '/orders/ord-route/print', testid: 'order-print-document' };
  if (path === '/client/declarations/:id/print') return { endpoint: '/client/declarations/ord-route/print', opposite: '/declarations/ord-route/print', testid: 'declaration-print-document' };
  if (path === '/client/declarations/:id/receipt') return { endpoint: '/client/declarations/ord-route/receipt', opposite: '/declarations/ord-route/receipt', testid: 'receipt-print-document' };
  if (path === '/orders/:id/print') return { endpoint: '/orders/ord-route/print', opposite: '/client/orders/ord-route/print', testid: 'order-print-document' };
  if (path === '/declarations/:id/print') return { endpoint: '/declarations/ord-route/print', opposite: '/client/declarations/ord-route/print', testid: 'declaration-print-document' };
  if (path === '/declarations/:id/receipt') return { endpoint: '/declarations/ord-route/receipt', opposite: '/client/declarations/ord-route/receipt', testid: 'receipt-print-document' };
  return null;
}

/** All six print-data GET endpoints (for exhaustive exclusivity assertions). */
const ALL_SIX_PRINT_ENDPOINTS = [
  '/client/orders/ord-route/print',
  '/client/declarations/ord-route/print',
  '/client/declarations/ord-route/receipt',
  '/orders/ord-route/print',
  '/declarations/ord-route/print',
  '/declarations/ord-route/receipt',
];

/** Filter a call list to only print-data GET URLs (order/declaration print + receipt). */
function printDataGetUrls(calls: unknown[][]): string[] {
  return calls
    .map((c) => String(c[0]))
    .filter((u) => (u.includes('/print') || u.includes('/receipt')) && (u.includes('/orders/') || u.includes('/declarations/')));
}

function concretePath(template: string): string {
  return template.replace(':id', 'ord-route');
}

/** Render the real AppRouter and navigate to a path (real data router). */
async function renderAppRouterAt(path: string) {
  // Clean up any prior render in the same test so DOM does not accumulate.
  cleanup();
  // Satisfy every GET the route tree may issue while navigating/printing.
  mockGet.mockImplementation(async (url: string) => {
    if (url.includes('/print') && url.includes('/orders/')) {
      return axiosResponse(ok(ORDER_PRINT_FIXTURE).data) as never;
    }
    if (url.includes('/print') && url.includes('/declarations/')) {
      return axiosResponse(ok(DECL_PRINT_FIXTURE).data) as never;
    }
    if (url.includes('/receipt')) {
      return axiosResponse(ok(RECEIPT_FIXTURE).data) as never;
    }
    return axiosResponse({ success: true, data: { items: [], pagination: { page: 1, size: 20, total: 0, pages: 0 } }, timestamp: 't' }) as never;
  });
  render(<AppRouter />);
  // First navigate to a neutral non-print path so the singleton data router is
  // not lingering on a prior test's print route; settle, then CLEAR the mock
  // call log so only the target route's GETs are counted by the caller.
  await act(async () => {
    window.history.pushState({}, '', '/');
    window.dispatchEvent(new PopStateEvent('popstate'));
  });
  await act(async () => { await new Promise((r) => setTimeout(r, 60)); });
  mockGet.mockClear();
  // Now navigate to the target path (real data router reacts).
  await act(async () => {
    window.history.pushState({}, '', path);
    window.dispatchEvent(new PopStateEvent('popstate'));
  });
  await act(async () => { await new Promise((r) => setTimeout(r, 80)); });
}

describe('R2 Correction 3 — complete actual AppRouter guard/endpoint matrix', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGet.mockReset();
    vi.mocked(api.post).mockReset();
    useAuthStore.setState({
      accessToken: null, refreshToken: null, user: null,
      tenantCode: null, retailerPortalCode: null,
    });
  });

  // Retailer ALLOW — all three /client routes admitted + exact endpoint list.
  describe('retailer ALLOW (3 client routes)', () => {
    for (const tpl of ['/client/orders/:id/print', '/client/declarations/:id/print', '/client/declarations/:id/receipt']) {
      it(`admits ${tpl}; print-data GET list == [expected] only; opposite + 4 others never called`, async () => {
        useAuthStore.setState({ accessToken: 't', refreshToken: 'r', user: RETAILER_USER, tenantCode: null, retailerPortalCode: 'SUPP42' });
        const exp = routeExpectations(tpl)!;
        await renderAppRouterAt(concretePath(tpl));
        await waitFor(() => expect(screen.queryByTestId(exp.testid)).not.toBeNull(), { timeout: 3000 });
        // Complete print-data GET list must equal exactly [expectedEndpoint].
        const printUrls = printDataGetUrls(mockGet.mock.calls);
        expect(printUrls).toEqual([exp.endpoint]);
        // Opposite-side endpoint never called.
        expect(mockGet).not.toHaveBeenCalledWith(exp.opposite);
        // All other five print endpoints never called.
        for (const other of ALL_SIX_PRINT_ENDPOINTS) {
          if (other !== exp.endpoint) expect(mockGet).not.toHaveBeenCalledWith(other);
        }
        expect(api.post).not.toHaveBeenCalled();
        expect(api.put).not.toHaveBeenCalled();
        expect(api.patch).not.toHaveBeenCalled();
        expect(api.delete).not.toHaveBeenCalled();
      });
    }
  });

  // Retailer DENY — all three supplier routes redirected; empty print-data GET list.
  describe('retailer DENY (3 supplier routes)', () => {
    for (const tpl of ['/orders/:id/print', '/declarations/:id/print', '/declarations/:id/receipt']) {
      it(`denies ${tpl} (no document; print-data GET list empty; no writes)`, async () => {
        useAuthStore.setState({ accessToken: 't', refreshToken: 'r', user: RETAILER_USER, tenantCode: null, retailerPortalCode: 'SUPP42' });
        const exp = routeExpectations(tpl)!;
        await renderAppRouterAt(concretePath(tpl));
        await waitFor(() => expect(screen.queryByTestId(exp.testid)).not.toBeInTheDocument(), { timeout: 3000 });
        // Denied routes execute no print-data GET at all.
        expect(printDataGetUrls(mockGet.mock.calls)).toEqual([]);
        for (const ep of ALL_SIX_PRINT_ENDPOINTS) expect(mockGet).not.toHaveBeenCalledWith(ep);
        expect(api.post).not.toHaveBeenCalled();
        expect(api.put).not.toHaveBeenCalled();
        expect(api.patch).not.toHaveBeenCalled();
        expect(api.delete).not.toHaveBeenCalled();
      });
    }
  });

  // Wholesaler ALLOW — all three supplier routes admitted + exact endpoint list.
  describe('wholesaler ALLOW (3 supplier routes)', () => {
    for (const tpl of ['/orders/:id/print', '/declarations/:id/print', '/declarations/:id/receipt']) {
      it(`admits ${tpl}; print-data GET list == [expected] only; opposite + 4 others never called`, async () => {
        useAuthStore.setState({ accessToken: 't', refreshToken: 'r', user: WHOLESALER_USER, tenantCode: 'TENA', retailerPortalCode: null });
        const exp = routeExpectations(tpl)!;
        await renderAppRouterAt(concretePath(tpl));
        await waitFor(() => expect(screen.queryByTestId(exp.testid)).not.toBeNull(), { timeout: 3000 });
        const printUrls = printDataGetUrls(mockGet.mock.calls);
        expect(printUrls).toEqual([exp.endpoint]);
        expect(mockGet).not.toHaveBeenCalledWith(exp.opposite);
        for (const other of ALL_SIX_PRINT_ENDPOINTS) {
          if (other !== exp.endpoint) expect(mockGet).not.toHaveBeenCalledWith(other);
        }
        expect(api.post).not.toHaveBeenCalled();
        expect(api.put).not.toHaveBeenCalled();
        expect(api.patch).not.toHaveBeenCalled();
        expect(api.delete).not.toHaveBeenCalled();
      });
    }
  });

  // Wholesaler DENY — all three /client routes redirected; empty print-data GET list.
  describe('wholesaler DENY (3 client routes)', () => {
    for (const tpl of ['/client/orders/:id/print', '/client/declarations/:id/print', '/client/declarations/:id/receipt']) {
      it(`denies ${tpl} (no document; print-data GET list empty; no writes)`, async () => {
        useAuthStore.setState({ accessToken: 't', refreshToken: 'r', user: WHOLESALER_USER, tenantCode: 'TENA', retailerPortalCode: null });
        const exp = routeExpectations(tpl)!;
        await renderAppRouterAt(concretePath(tpl));
        await waitFor(() => expect(screen.queryByTestId(exp.testid)).not.toBeInTheDocument(), { timeout: 3000 });
        expect(printDataGetUrls(mockGet.mock.calls)).toEqual([]);
        for (const ep of ALL_SIX_PRINT_ENDPOINTS) expect(mockGet).not.toHaveBeenCalledWith(ep);
        expect(api.post).not.toHaveBeenCalled();
        expect(api.put).not.toHaveBeenCalled();
        expect(api.patch).not.toHaveBeenCalled();
        expect(api.delete).not.toHaveBeenCalled();
      });
    }
  });

  // Static endpoint ownership: opposite client/supplier endpoint never called.
  it('static endpoint ownership — each route never calls its opposite-side endpoint', async () => {
    useAuthStore.setState({ accessToken: 't', refreshToken: 'r', user: RETAILER_USER, tenantCode: null, retailerPortalCode: 'SUPP42' });
    await renderAppRouterAt('/client/orders/ord-route/print');
    await waitFor(() => expect(screen.queryByTestId('order-print-document')).not.toBeNull(), { timeout: 3000 });
    // Client order print must NEVER call the supplier endpoint.
    expect(mockGet).not.toHaveBeenCalledWith('/orders/ord-route/print');

    cleanup();
    mockGet.mockReset();
    vi.clearAllMocks();
    useAuthStore.setState({ accessToken: 't', refreshToken: 'r', user: WHOLESALER_USER, tenantCode: 'TENA', retailerPortalCode: null });
    await renderAppRouterAt('/orders/ord-route/print');
    await waitFor(() => expect(screen.queryByTestId('order-print-document')).not.toBeNull(), { timeout: 3000 });
    // Supplier order print must NEVER call the client endpoint.
    expect(mockGet).not.toHaveBeenCalledWith('/client/orders/ord-route/print');
  });
});

// ===========================================================================
// R3 Correction 1 — genuine link-follow through the real AppRouter.
//
// Exercises the full authentic path with REAL user navigation (no direct
// mockGet, no getCashierReceipt, no separate ReceiptPrintPage render, no manual
// window.location, no reconstructed route):
//   real AppRouter @ /declarations (wholesaler)
//     -> DeclarationQueuePage
//     -> real Confirm button
//     -> authentic AxiosResponse -> ApiResponse -> confirmation payload (RESPONSE_ID)
//     -> rendered View/Print receipt Link
//     -> click the Link through React Router
//     -> real AppRouter / WholesalerRoute / MainLayout / real ReceiptPrintPage
//     -> getCashierReceipt -> supplier Contract C GET
//
// Placed after all const fixture/helper definitions so they are in scope.
// ===========================================================================

describe('R3 Correction 1 — genuine link-follow to ReceiptPrintPage (Contract C only)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGet.mockReset();
    vi.mocked(api.post).mockReset();
    useAuthStore.setState({
      accessToken: null, refreshToken: null, user: null,
      tenantCode: null, retailerPortalCode: null,
    });
  });

  it('follows the rendered receipt Link through React Router to the real ReceiptPrintPage', async () => {
    const REQUEST_ID = 'dec-req-link';
    const RESPONSE_ID = 'dec-resp-link';
    useAuthStore.setState({ accessToken: 't', refreshToken: 'r', user: WHOLESALER_USER, tenantCode: 'TENA', retailerPortalCode: null });

    // Real AppRouter GET responses: the cashier queue carries REQUEST_ID; the
    // receipt page resolves its own fixture when navigated to.
    mockGet.mockImplementation(async (url: string) => {
      if (url === '/declarations' || (url.startsWith('/declarations') && url.includes('page='))) {
        return authenticListResponse([pendingDeclaration(REQUEST_ID)]) as never;
      }
      if (url.includes('/receipt')) return axiosResponse(ok(RECEIPT_FIXTURE).data) as never;
      if (url.includes('/print') && url.includes('/declarations/')) return axiosResponse(ok(DECL_PRINT_FIXTURE).data) as never;
      if (url.includes('/print') && url.includes('/orders/')) return axiosResponse(ok(ORDER_PRINT_FIXTURE).data) as never;
      return axiosResponse({ success: true, data: { items: [], pagination: { page: 1, size: 20, total: 0, pages: 0 } }, timestamp: 't' }) as never;
    });
    // One authentic confirmation response carrying the distinct RESPONSE_ID.
    vi.mocked(api.post).mockImplementation(async (url: string) => {
      if (url === `/declarations/${REQUEST_ID}/confirm`) {
        return authenticConfirmSuccess(RESPONSE_ID) as never;
      }
      throw new Error(`unexpected POST ${url}`);
    });

    cleanup();
    render(<AppRouter />);
    await act(async () => {
      window.history.pushState({}, '', '/declarations');
      window.dispatchEvent(new PopStateEvent('popstate'));
    });
    // Wait for the cashier queue + the real Confirm button.
    await waitFor(() => expect(screen.getByRole('button', { name: /confirm/i })).toBeInTheDocument(), { timeout: 3000 });

    // Click the real Confirm button.
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /confirm/i }));
    });

    // Wait for the rendered View/Print receipt Link; assert its href.
    const link = await screen.findByTestId('confirmed-receipt-link', {}, { timeout: 3000 });
    expect(link).toHaveAttribute('href', `/declarations/${encodeURIComponent(RESPONSE_ID)}/receipt`);
    expect(link.getAttribute('href')).not.toContain(REQUEST_ID);

    // Snapshot call counts BEFORE navigating, then FOLLOW the rendered Link via
    // real React Router (a click, not window.location, not mockGet).
    const getBefore = mockGet.mock.calls.length;
    const postBefore = vi.mocked(api.post).mock.calls.length;
    await act(async () => {
      fireEvent.click(link);
    });
    // Wait for the real ReceiptPrintPage document to render.
    await waitFor(() => expect(screen.queryByTestId('receipt-print-document')).not.toBeNull(), { timeout: 3000 });

    // Exactly one supplier Contract C GET issued by following the link.
    const getAfter = mockGet.mock.calls.slice(getBefore);
    expect(getAfter.filter((c) => String(c[0]) === `/declarations/${RESPONSE_ID}/receipt`).length).toBe(1);
    // No client Contract C endpoint called.
    expect(getAfter.filter((c) => String(c[0]).startsWith('/client/declarations/')).length).toBe(0);
    // No declaration-print or order-print endpoint called.
    expect(getAfter.filter((c) => String(c[0]).includes('/print')).length).toBe(0);
    // Confirmation POST occurred exactly once; no further writes after navigation.
    expect(vi.mocked(api.post).mock.calls.length).toBe(postBefore);
    expect(vi.mocked(api.post).mock.calls.length).toBe(1);
    expect(api.put).not.toHaveBeenCalled();
    expect(api.patch).not.toHaveBeenCalled();
    expect(api.delete).not.toHaveBeenCalled();
  });
});
