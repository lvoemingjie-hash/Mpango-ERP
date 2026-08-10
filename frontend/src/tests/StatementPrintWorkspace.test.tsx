/**
 * DC-12R1-S3-S2B-I2C-I2B — Contract D statement print workspace tests.
 *
 * Covers (required + binding corrections):
 *  - Correct GET endpoint + exactly one request per view (retailer + cashier);
 *    dynamic query values encoded; opposite-side endpoint never called.
 *  - No POST/PUT/PATCH/DELETE issued by any statement view — and mutations are
 *    RED: any attempted write fails the test immediately.
 *  - Deterministic rendering from server fixtures; balances/totals/movements/
 *    payments rendered with EXACT server precision (string-only grouping; no
 *    Number/parseFloat/Intl — large + high-precision amounts preserved).
 *  - Movements and Settled Payments are visually independent sections; pending
 *    declarations render ONLY when explicitly requested (?include_pending=true).
 *  - Print action calls window.print() exactly once.
 *  - 401/403/404/409/5xx collapse to fixed neutral strings — a 409 (period /
 *    ledger-scope / reconciliation failure) is deliberately indistinguishable
 *    from any other not-available case; never leaks codes, schema names, or
 *    server text.
 *  - Real AppRouter guard matrix across ALL EIGHT print routes (Contracts
 *    A–D): retailer/wholesaler ALLOW + DENY with exact endpoint ownership.
 *  - Genuine entry links from the real finance pages (retailer + supplier).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, act, waitFor, cleanup } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { api } from '@/services/api';
import {
  getRetailerStatementPrint,
  getSupplierStatementPrint,
} from '@/services/statementService';
import { StatementPrintPage } from '@/pages/print/StatementPrintPage';
import { useAuthStore } from '@/stores/authStore';
import { AppRouter } from '@/router/AppRouter';
import { ClientFinanceBalancePage } from '@/pages/client/FinanceBalancePage';
import { FinancePage } from '@/pages/finance/FinancePage';
import { formatKes, eatDateFromUtc, eatToday, eatMonthRange, eatDefaultRange } from '@/utils/printFormat';
import { sanitizePrintError } from '@/utils/printError';
import type { AxiosError } from 'axios';
import type { StatementPrintView } from '@/types/statement';

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
  return data({ success: true, data: d, message: null, timestamp: '2026-08-10T10:00:00Z' });
}

/** Build an axios-like rejection carrying an HTTP status + a (non-neutral) body. */
function rejectWith(status: number, body: unknown): { response: { status: number; data: unknown } } {
  return { response: { status, data: body } };
}

// ---------------------------------------------------------------------------
// Fixtures — server-authoritative Contract D view
// ---------------------------------------------------------------------------

const STATEMENT: StatementPrintView = {
  document_type: 'statement',
  supplier_name: 'Sunrise Wholesalers',
  retailer_name: 'Kibera Duka',
  period_from: '2026-08-01',
  period_to: '2026-08-10',
  opening_balance: '2500.00',
  closing_balance: '2850.50',
  charge_total: '1050.50',
  collection_total: '700.00',
  net_movement: '350.50',
  settled_total: '700.00',
  movements: [
    {
      kind: 'charge',
      date: '2026-08-03T08:00:00Z',
      date_eat: '2026-08-03T11:00:00+03:00',
      signed_amount: '600.00',
      display_amount: '600.00',
      description: 'Order confirmation',
      reference_type: 'order',
      reference_id: 'aaaa1111-0000-0000-0000-000000000001',
    },
    {
      kind: 'collection',
      date: '2026-08-05T08:00:00Z',
      date_eat: '2026-08-05T11:00:00+03:00',
      signed_amount: '-700.00',
      display_amount: '700.00',
      description: 'Collection received',
      reference_type: 'order',
      reference_id: 'aaaa1111-0000-0000-0000-000000000001',
    },
    {
      kind: 'charge',
      date: '2026-08-07T08:00:00Z',
      date_eat: '2026-08-07T11:00:00+03:00',
      signed_amount: '450.50',
      display_amount: '450.50',
      description: null,
      reference_type: 'refund',
      reference_id: 'bbbb2222-0000-0000-0000-000000000002',
    },
  ],
  settled_payments: [
    {
      date: '2026-08-05T08:00:00Z',
      date_eat: '2026-08-05T11:00:00+03:00',
      order_id: 'aaaa1111-0000-0000-0000-000000000001',
      amount: '700.00',
      method: 'cash',
      receipt_number: 'RCT-20260805-000001',
    },
  ],
  pending_declarations: [],
  generated_at: '2026-08-10T08:00:00Z',
  generated_at_eat: '2026-08-10T11:00:00+03:00',
};

/** Large + high-precision amounts (binding correction #1): values that would
 *  round/lose precision if parsed via Number/parseFloat. */
const STATEMENT_BIG: StatementPrintView = {
  ...STATEMENT,
  opening_balance: '9007199254740993.125',
  closing_balance: '9007199254740993.125',
  charge_total: '9007199254740993.125',
  collection_total: '0.000001',
  net_movement: '9007199254740993.124999',
  movements: [
    {
      kind: 'collection',
      date: '2026-08-03T08:00:00Z',
      date_eat: '2026-08-03T11:00:00+03:00',
      signed_amount: '-1250.50',
      display_amount: '1250.50',
      description: 'High-precision collection',
      reference_type: 'order',
      reference_id: 'cccc3333-0000-0000-0000-000000000003',
    },
  ],
  settled_payments: [],
  pending_declarations: [],
};

/** A statement carrying pending declarations (non-accounting context). */
const STATEMENT_WITH_PENDING: StatementPrintView = {
  ...STATEMENT,
  pending_declarations: [
    {
      declaration_id: 'dddd4444-0000-0000-0000-000000000004',
      order_id: 'aaaa1111-0000-0000-0000-000000000002',
      declared_amount: '1500.00',
      method: 'mpesa',
      status: 'pending',
      submitted_at: '2026-08-09T08:00:00Z',
      submitted_at_eat: '2026-08-09T11:00:00+03:00',
      transfer_reference: 'TRF-123',
    },
  ],
};

/** Full-UUID pattern — the printable DOM must never contain one (R1). */
const FULL_UUID_RE = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/client/statements/print" element={<StatementPrintPage mode="client" />} />
        <Route path="/statements/print" element={<StatementPrintPage mode="cashier" />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// Services — endpoint ownership + encoding; GET-only
// ---------------------------------------------------------------------------

describe('I2C-I2B statement services — endpoints', () => {
  it('getRetailerStatementPrint → GET /client/statements/print (once, encoded params)', async () => {
    mockGet.mockResolvedValueOnce(ok(STATEMENT) as never);
    await getRetailerStatementPrint('2026-08-01', '2026-08-10');
    expect(mockGet).toHaveBeenCalledTimes(1);
    expect(mockGet).toHaveBeenCalledWith('/client/statements/print', {
      params: { from: '2026-08-01', to: '2026-08-10', include_pending: false },
    });
  });

  it('getSupplierStatementPrint → GET /statements/print (once, encoded params)', async () => {
    mockGet.mockResolvedValueOnce(ok(STATEMENT) as never);
    await getSupplierStatementPrint('ret-a-1', '2026-08-01', '2026-08-10', true);
    expect(mockGet).toHaveBeenCalledTimes(1);
    expect(mockGet).toHaveBeenCalledWith('/statements/print', {
      params: {
        retailer_id: 'ret-a-1',
        from: '2026-08-01',
        to: '2026-08-10',
        include_pending: true,
      },
    });
  });

  it('encodes dynamic values (no injection / traversal)', async () => {
    mockGet.mockResolvedValueOnce(ok(STATEMENT) as never);
    await getSupplierStatementPrint('a/b?c', '2026-08-01', '2026-08-10');
    expect(mockGet).toHaveBeenCalledWith('/statements/print', {
      params: {
        retailer_id: 'a%2Fb%3Fc',
        from: '2026-08-01',
        to: '2026-08-10',
        include_pending: false,
      },
    });
  });
});

// ---------------------------------------------------------------------------
// StatementPrintPage — deterministic rendering, independent sections
// ---------------------------------------------------------------------------

describe('StatementPrintPage', () => {
  it('renders server-authoritative fields deterministically (retailer)', async () => {
    mockGet.mockResolvedValueOnce(ok(STATEMENT) as never);
    renderAt('/client/statements/print?from=2026-08-01&to=2026-08-10');

    const doc = await screen.findByTestId('statement-print-document');
    expect(doc).toBeInTheDocument();
    expect(screen.getByText('Sunrise Wholesalers')).toBeInTheDocument();
    expect(screen.getByText('Kibera Duka')).toBeInTheDocument();
    expect(screen.getByText(/Period 2026-08-01 to 2026-08-10/)).toBeInTheDocument();
    // Exact server strings rendered (no recompute).
    expect(screen.getByTestId('statement-opening-balance')).toHaveTextContent('KES 2,500.00');
    expect(screen.getByTestId('statement-closing-balance')).toHaveTextContent('KES 2,850.50');
    expect(screen.getByTestId('statement-charge-total')).toHaveTextContent('KES 1,050.50');
    expect(screen.getByTestId('statement-collection-total')).toHaveTextContent('KES 700.00');
    expect(screen.getByTestId('statement-net-movement')).toHaveTextContent('KES 350.50');
    // R1: settled_total rendered from the independent settled list.
    expect(screen.getByTestId('statement-settled-total')).toHaveTextContent('KES 700.00');
    // R1: movements render server-classified kind + display_amount verbatim.
    const movements = screen.getByTestId('statement-movements-section');
    expect(movements).toHaveTextContent('charge');
    expect(movements).toHaveTextContent('collection');
    expect(movements).toHaveTextContent('KES 600.00');
    expect(movements).toHaveTextContent('KES 450.50');
    // R1: no full UUID in the printable DOM (short references only).
    expect(screen.queryByText(FULL_UUID_RE)).not.toBeInTheDocument();
    expect(doc.textContent).not.toMatch(FULL_UUID_RE);
    // Exactly one GET, no writes.
    expect(mockGet).toHaveBeenCalledTimes(1);
    expect(mockGet).toHaveBeenCalledWith('/client/statements/print', {
      params: { from: '2026-08-01', to: '2026-08-10', include_pending: false },
    });
    expect(api.post).not.toHaveBeenCalled();
    expect(api.put).not.toHaveBeenCalled();
    expect(api.patch).not.toHaveBeenCalled();
    expect(api.delete).not.toHaveBeenCalled();
  });

  it('uses the cashier endpoint under the cashier route (retailer_id selector)', async () => {
    mockGet.mockResolvedValueOnce(ok(STATEMENT) as never);
    renderAt('/statements/print?retailer_id=ret-a-1&from=2026-08-01&to=2026-08-10');
    await screen.findByTestId('statement-print-document');
    expect(mockGet).toHaveBeenCalledTimes(1);
    expect(mockGet).toHaveBeenCalledWith('/statements/print', {
      params: { retailer_id: 'ret-a-1', from: '2026-08-01', to: '2026-08-10', include_pending: false },
    });
  });

  it('movements and settled payments are independent sections; no cross-association', async () => {
    mockGet.mockResolvedValueOnce(ok(STATEMENT) as never);
    renderAt('/client/statements/print?from=2026-08-01&to=2026-08-10');
    await screen.findByTestId('statement-print-document');

    const movements = screen.getByTestId('statement-movements-section');
    const settled = screen.getByTestId('statement-settled-payments-section');
    expect(movements).toBeInTheDocument();
    expect(settled).toBeInTheDocument();
    // Movement rows live in their own section; payment rows in theirs.
    expect(movements).toHaveTextContent('Order confirmation');
    expect(movements).toHaveTextContent('KES 600.00');
    expect(settled).toHaveTextContent('RCT-20260805-000001');
    expect(settled).toHaveTextContent('KES 700.00');
    // The payment row is NOT duplicated inside the movements section.
    expect(movements).not.toHaveTextContent('RCT-20260805-000001');
    expect(movements).not.toHaveTextContent('RCT-');
    // R1: no full UUID anywhere in the document.
    expect(screen.getByTestId('statement-print-document').textContent).not.toMatch(FULL_UUID_RE);
  });

  it('pending declarations render ONLY when explicitly requested', async () => {
    // Without include_pending the backend returns an EMPTY pending list — the
    // section must not render even though the view model allows the field.
    mockGet.mockResolvedValueOnce(ok(STATEMENT) as never);
    renderAt('/client/statements/print?from=2026-08-01&to=2026-08-10');
    await screen.findByTestId('statement-print-document');
    expect(screen.queryByTestId('statement-pending-declarations-section')).not.toBeInTheDocument();
    expect(screen.queryByText('TRF-123')).not.toBeInTheDocument();
    // Explicit include_pending=true → backend returns the list; section renders.
    cleanup();
    mockGet.mockClear();
    mockGet.mockResolvedValueOnce(ok(STATEMENT_WITH_PENDING) as never);
    renderAt('/client/statements/print?from=2026-08-01&to=2026-08-10&include_pending=true');
    await screen.findByTestId('statement-print-document');
    const pending = screen.getByTestId('statement-pending-declarations-section');
    expect(pending).toHaveTextContent('TRF-123');
    expect(pending).toHaveTextContent('KES 1,500.00');
    expect(mockGet).toHaveBeenCalledWith('/client/statements/print', {
      params: { from: '2026-08-01', to: '2026-08-10', include_pending: true },
    });
  });

  it('Print button calls window.print() exactly once', async () => {
    mockGet.mockResolvedValueOnce(ok(STATEMENT) as never);
    const spy = vi.spyOn(window, 'print').mockImplementation(() => {});
    renderAt('/client/statements/print?from=2026-08-01&to=2026-08-10');
    const btn = await screen.findByTestId('statement-print-button');
    fireEvent.click(btn);
    expect(spy).toHaveBeenCalledTimes(1);
    spy.mockRestore();
  });

  it('renders exact large + high-precision amounts without rounding', async () => {
    mockGet.mockResolvedValueOnce(ok(STATEMENT_BIG) as never);
    renderAt('/client/statements/print?from=2026-08-01&to=2026-08-10');
    await screen.findByTestId('statement-print-document');
    // > 2^53 preserved exactly; high-precision values verbatim.
    expect(screen.getByTestId('statement-opening-balance')).toHaveTextContent(
      'KES 9,007,199,254,740,993.125',
    );
    expect(screen.getByTestId('statement-collection-total')).toHaveTextContent('KES 0.000001');
    expect(screen.getByTestId('statement-net-movement')).toHaveTextContent(
      'KES 9,007,199,254,740,993.124999',
    );
    // R1: the movement renders display_amount=abs(signed_amount) verbatim with
    // the server-classified kind — never the raw signed value.
    const movements = screen.getByTestId('statement-movements-section');
    expect(movements).toHaveTextContent('collection');
    expect(movements).toHaveTextContent('KES 1,250.50');
    expect(movements).not.toHaveTextContent('KES -1,250.50');
    expect(movements).not.toHaveTextContent('-1,250.50');
  });

  it('cashier view without retailer_id fails closed: neutral copy, ZERO GETs', async () => {
    renderAt('/statements/print?from=2026-08-01&to=2026-08-10');
    const err = await screen.findByTestId('statement-print-error');
    expect(err).toHaveTextContent('This document is not available.');
    expect(mockGet).not.toHaveBeenCalled();
    expect(screen.queryByTestId('statement-print-document')).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// StatementPrintPage — neutral sanitized failure states (401/403/404/409/5xx)
// ---------------------------------------------------------------------------

describe('StatementPrintPage — status-only neutral copy', () => {
  it.each([
    [
      '401',
      rejectWith(401, { detail: { code: 'UNAUTHORIZED', message: 'token expired', request_id: 'r1' } }),
      'Please sign in to view this document.',
    ],
    [
      '403',
      rejectWith(403, { detail: { code: 'PERMISSION_DENIED', message: 'no client:finance:read' } }),
      'You do not have access to this document.',
    ],
    [
      '404',
      rejectWith(404, { detail: { code: 'BINDING_NOT_ACTIVE', message: 'binding missing' } }),
      'This document is not available.',
    ],
    [
      '409',
      rejectWith(409, {
        detail: {
          code: 'STATEMENT_LEDGER_SCOPE_INCOMPLETE',
          message: 'orphan ledger ref t_a.ledger_entries 999.00',
          request_id: 'rid-409',
        },
      }),
      'We couldn’t load this document. Please try again later.',
    ],
    [
      '500',
      rejectWith(500, { detail: { code: 'DB_ERROR', message: 'relation t_a.orders missing' } }),
      'We couldn’t load this document. Please try again later.',
    ],
  ])('%s → neutral copy; never echoes server body', async (_label, rejection, neutral) => {
    mockGet.mockRejectedValueOnce(rejection as never);
    renderAt('/client/statements/print?from=2026-08-01&to=2026-08-10');
    const err = await screen.findByTestId('statement-print-error');
    expect(err).toHaveTextContent(neutral);
    // None of the internal details may leak.
    expect(err.textContent).not.toContain('STATEMENT_');
    expect(err.textContent).not.toContain('UNAUTHORIZED');
    expect(err.textContent).not.toContain('PERMISSION_DENIED');
    expect(err.textContent).not.toContain('BINDING_NOT_ACTIVE');
    expect(err.textContent).not.toContain('DB_ERROR');
    expect(err.textContent).not.toContain('t_a.');
    expect(err.textContent).not.toContain('client:finance:read');
    expect(err.textContent).not.toContain('request_id');
    expect(screen.queryByTestId('statement-print-document')).not.toBeInTheDocument();
  });

  it('sanitizePrintError(409) is neutral and identical to other unavailable cases', () => {
    const msg = sanitizePrintError(      rejectWith(409, {
        detail: { code: 'STATEMENT_RECONCILIATION_FAILED', message: 'ledger vs cached balance' },
      }) as unknown as AxiosError,
    );
    expect(msg).toMatch(/couldn’t load this document/i);
    expect(msg).not.toContain('STATEMENT_RECONCILIATION_FAILED');
    expect(msg).not.toContain('ledger');
    expect(msg).not.toContain('cached');
  });

  // R1 rule 5: a 400 (INVALID_DATE_RANGE / STATEMENT_RANGE_TOO_LARGE) shows
  // the fixed neutral "Choose a shorter date range." — status-only, never
  // echoing the body.
  it.each([
    [
      'INVALID_DATE_RANGE',
      rejectWith(400, { detail: { code: 'INVALID_DATE_RANGE', message: 'Invalid date range.' } }),
    ],
    [
      'STATEMENT_RANGE_TOO_LARGE',
      rejectWith(400, {
        detail: { code: 'STATEMENT_RANGE_TOO_LARGE', message: 'Statement range is too large. Choose a shorter date range.' },
      }),
    ],
  ])('400 %s → fixed shorter-range copy; never echoes the body', async (_label, rejection) => {
    mockGet.mockRejectedValueOnce(rejection as never);
    renderAt('/client/statements/print?from=2026-08-01&to=2026-08-10');
    const err = await screen.findByTestId('statement-print-error');
    expect(err).toHaveTextContent('Choose a shorter date range.');
    expect(err.textContent).not.toContain('INVALID_DATE_RANGE');
    expect(err.textContent).not.toContain('STATEMENT_RANGE_TOO_LARGE');
    expect(err.textContent).not.toContain('Invalid date range');
    expect(screen.queryByTestId('statement-print-document')).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Zero mutation + mutation RED
// ---------------------------------------------------------------------------

describe('StatementPrintPage — zero mutation, mutations RED', () => {
  it('a successful view issues exactly one GET and NEVER any write', async () => {
    // Any write attempt throws; if the view tried to write, the test fails.
    vi.mocked(api.post).mockImplementation(() => {
      throw new Error('mutation attempted (POST)');
    });
    vi.mocked(api.put).mockImplementation(() => {
      throw new Error('mutation attempted (PUT)');
    });
    vi.mocked(api.patch).mockImplementation(() => {
      throw new Error('mutation attempted (PATCH)');
    });
    vi.mocked(api.delete).mockImplementation(() => {
      throw new Error('mutation attempted (DELETE)');
    });
    mockGet.mockResolvedValueOnce(ok(STATEMENT) as never);
    renderAt('/client/statements/print?from=2026-08-01&to=2026-08-10');
    await screen.findByTestId('statement-print-document');
    expect(mockGet).toHaveBeenCalledTimes(1);
    expect(api.post).not.toHaveBeenCalled();
    expect(api.put).not.toHaveBeenCalled();
    expect(api.patch).not.toHaveBeenCalled();
    expect(api.delete).not.toHaveBeenCalled();
  });

  it('an error view never writes either', async () => {
    vi.mocked(api.post).mockImplementation(() => {
      throw new Error('mutation attempted (POST)');
    });
    vi.mocked(api.delete).mockImplementation(() => {
      throw new Error('mutation attempted (DELETE)');
    });
    mockGet.mockRejectedValueOnce(rejectWith(404, { detail: {} }) as never);
    renderAt('/client/statements/print?from=2026-08-01&to=2026-08-10');
    await screen.findByTestId('statement-print-error');
    expect(api.post).not.toHaveBeenCalled();
    expect(api.put).not.toHaveBeenCalled();
    expect(api.patch).not.toHaveBeenCalled();
    expect(api.delete).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Real AppRouter guard matrix — ALL EIGHT print routes (Contracts A–D)
// ---------------------------------------------------------------------------

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

/** All eight print-data GET endpoints (for exhaustive exclusivity assertions). */
const ALL_EIGHT_PRINT_ENDPOINTS = [
  '/client/orders/ord-route/print',
  '/client/declarations/ord-route/print',
  '/client/declarations/ord-route/receipt',
  '/client/statements/print',
  '/orders/ord-route/print',
  '/declarations/ord-route/print',
  '/declarations/ord-route/receipt',
  '/statements/print',
];

/** Expected GET endpoint + document testid for a route (allow cases). */
function routeExpectations(tpl: string): { endpoint: string; opposite: string; testid: string } | null {
  if (tpl === '/client/orders/:id/print') return { endpoint: '/client/orders/ord-route/print', opposite: '/orders/ord-route/print', testid: 'order-print-document' };
  if (tpl === '/client/declarations/:id/print') return { endpoint: '/client/declarations/ord-route/print', opposite: '/declarations/ord-route/print', testid: 'declaration-print-document' };
  if (tpl === '/client/declarations/:id/receipt') return { endpoint: '/client/declarations/ord-route/receipt', opposite: '/declarations/ord-route/receipt', testid: 'receipt-print-document' };
  if (tpl === '/client/statements/print') return { endpoint: '/client/statements/print', opposite: '/statements/print', testid: 'statement-print-document' };
  if (tpl === '/orders/:id/print') return { endpoint: '/orders/ord-route/print', opposite: '/client/orders/ord-route/print', testid: 'order-print-document' };
  if (tpl === '/declarations/:id/print') return { endpoint: '/declarations/ord-route/print', opposite: '/client/declarations/ord-route/print', testid: 'declaration-print-document' };
  if (tpl === '/declarations/:id/receipt') return { endpoint: '/declarations/ord-route/receipt', opposite: '/client/declarations/ord-route/receipt', testid: 'receipt-print-document' };
  if (tpl === '/statements/print') return { endpoint: '/statements/print', opposite: '/client/statements/print', testid: 'statement-print-document' };
  return null;
}

/** Filter a call list to only print-data GET URLs (A–D). */
function printDataGetUrls(calls: unknown[][]): string[] {
  return calls
    .map((c) => String(c[0]))
    .filter(
      (u) =>
        (u.includes('/print') || u.includes('/receipt')) &&
        (u.includes('/orders/') || u.includes('/declarations/') || u.includes('/statements/print')),
    );
}

function concretePath(template: string): string {
  if (template === '/statements/print') {
    return '/statements/print?retailer_id=ret-route&from=2026-08-01&to=2026-08-10';
  }
  if (template === '/client/statements/print') {
    return '/client/statements/print?from=2026-08-01&to=2026-08-10';
  }
  return template.replace(':id', 'ord-route');
}

/** Render the real AppRouter and navigate to a path (real data router). */
async function renderAppRouterAt(path: string) {
  cleanup();
  mockGet.mockImplementation(async (url: string) => {
    if (url.includes('/statements/print')) {
      return data(ok(STATEMENT).data) as never;
    }
    if (url.includes('/print') && url.includes('/orders/')) {
      return data(ok(ORDER_PRINT_FIXTURE).data) as never;
    }
    if (url.includes('/print') && url.includes('/declarations/')) {
      return data(ok(DECL_PRINT_FIXTURE).data) as never;
    }
    if (url.includes('/receipt')) {
      return data(ok(RECEIPT_FIXTURE).data) as never;
    }
    return data({ success: true, data: { items: [], pagination: { page: 1, size: 20, total: 0, pages: 0 } }, timestamp: 't' }) as never;
  });
  render(<AppRouter />);
  await act(async () => {
    window.history.pushState({}, '', '/');
    window.dispatchEvent(new PopStateEvent('popstate'));
  });
  await act(async () => { await new Promise((r) => setTimeout(r, 60)); });
  mockGet.mockClear();
  await act(async () => {
    window.history.pushState({}, '', path);
    window.dispatchEvent(new PopStateEvent('popstate'));
  });
  await act(async () => { await new Promise((r) => setTimeout(r, 80)); });
}

describe('I2C-I2B — actual AppRouter guard matrix across all 8 print routes', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGet.mockReset();
    vi.mocked(api.post).mockReset();
    useAuthStore.setState({
      accessToken: null, refreshToken: null, user: null,
      tenantCode: null, retailerPortalCode: null,
    });
  });

  const CLIENT_TPL = ['/client/orders/:id/print', '/client/declarations/:id/print', '/client/declarations/:id/receipt', '/client/statements/print'];
  const SUPPLIER_TPL = ['/orders/:id/print', '/declarations/:id/print', '/declarations/:id/receipt', '/statements/print'];

  describe('retailer ALLOW (4 client routes)', () => {
    for (const tpl of CLIENT_TPL) {
      it(`admits ${tpl}; print-data GET list == [expected] only; opposite + 7 others never called`, async () => {
        useAuthStore.setState({ accessToken: 't', refreshToken: 'r', user: RETAILER_USER, tenantCode: null, retailerPortalCode: 'SUPP42' });
        const exp = routeExpectations(tpl)!;
        await renderAppRouterAt(concretePath(tpl));
        await waitFor(() => expect(screen.queryByTestId(exp.testid)).not.toBeNull(), { timeout: 3000 });
        const printUrls = printDataGetUrls(mockGet.mock.calls);
        expect(printUrls).toEqual([exp.endpoint]);
        expect(mockGet).not.toHaveBeenCalledWith(exp.opposite);
        for (const other of ALL_EIGHT_PRINT_ENDPOINTS) {
          if (other !== exp.endpoint) expect(mockGet).not.toHaveBeenCalledWith(other);
        }
        expect(api.post).not.toHaveBeenCalled();
        expect(api.put).not.toHaveBeenCalled();
        expect(api.patch).not.toHaveBeenCalled();
        expect(api.delete).not.toHaveBeenCalled();
      });
    }
  });

  describe('retailer DENY (4 supplier routes)', () => {
    for (const tpl of SUPPLIER_TPL) {
      it(`denies ${tpl} (no document; print-data GET list empty; no writes)`, async () => {
        useAuthStore.setState({ accessToken: 't', refreshToken: 'r', user: RETAILER_USER, tenantCode: null, retailerPortalCode: 'SUPP42' });
        const exp = routeExpectations(tpl)!;
        await renderAppRouterAt(concretePath(tpl));
        await waitFor(() => expect(screen.queryByTestId(exp.testid)).not.toBeInTheDocument(), { timeout: 3000 });
        expect(printDataGetUrls(mockGet.mock.calls)).toEqual([]);
        for (const ep of ALL_EIGHT_PRINT_ENDPOINTS) expect(mockGet).not.toHaveBeenCalledWith(ep);
        expect(api.post).not.toHaveBeenCalled();
        expect(api.put).not.toHaveBeenCalled();
        expect(api.patch).not.toHaveBeenCalled();
        expect(api.delete).not.toHaveBeenCalled();
      });
    }
  });

  describe('wholesaler ALLOW (4 supplier routes)', () => {
    for (const tpl of SUPPLIER_TPL) {
      it(`admits ${tpl}; print-data GET list == [expected] only; opposite + 7 others never called`, async () => {
        useAuthStore.setState({ accessToken: 't', refreshToken: 'r', user: WHOLESALER_USER, tenantCode: 'TENA', retailerPortalCode: null });
        const exp = routeExpectations(tpl)!;
        await renderAppRouterAt(concretePath(tpl));
        await waitFor(() => expect(screen.queryByTestId(exp.testid)).not.toBeNull(), { timeout: 3000 });
        const printUrls = printDataGetUrls(mockGet.mock.calls);
        expect(printUrls).toEqual([exp.endpoint]);
        expect(mockGet).not.toHaveBeenCalledWith(exp.opposite);
        for (const other of ALL_EIGHT_PRINT_ENDPOINTS) {
          if (other !== exp.endpoint) expect(mockGet).not.toHaveBeenCalledWith(other);
        }
        expect(api.post).not.toHaveBeenCalled();
        expect(api.put).not.toHaveBeenCalled();
        expect(api.patch).not.toHaveBeenCalled();
        expect(api.delete).not.toHaveBeenCalled();
      });
    }
  });

  describe('wholesaler DENY (4 client routes)', () => {
    for (const tpl of CLIENT_TPL) {
      it(`denies ${tpl} (no document; print-data GET list empty; no writes)`, async () => {
        useAuthStore.setState({ accessToken: 't', refreshToken: 'r', user: WHOLESALER_USER, tenantCode: 'TENA', retailerPortalCode: null });
        const exp = routeExpectations(tpl)!;
        await renderAppRouterAt(concretePath(tpl));
        await waitFor(() => expect(screen.queryByTestId(exp.testid)).not.toBeInTheDocument(), { timeout: 3000 });
        expect(printDataGetUrls(mockGet.mock.calls)).toEqual([]);
        for (const ep of ALL_EIGHT_PRINT_ENDPOINTS) expect(mockGet).not.toHaveBeenCalledWith(ep);
        expect(api.post).not.toHaveBeenCalled();
        expect(api.put).not.toHaveBeenCalled();
        expect(api.patch).not.toHaveBeenCalled();
        expect(api.delete).not.toHaveBeenCalled();
      });
    }
  });

  it('statement endpoint exclusivity — client never calls supplier statement endpoint and vice versa', async () => {
    useAuthStore.setState({ accessToken: 't', refreshToken: 'r', user: RETAILER_USER, tenantCode: null, retailerPortalCode: 'SUPP42' });
    await renderAppRouterAt('/client/statements/print?from=2026-08-01&to=2026-08-10');
    await waitFor(() => expect(screen.queryByTestId('statement-print-document')).not.toBeNull(), { timeout: 3000 });
    expect(mockGet).not.toHaveBeenCalledWith('/statements/print');

    cleanup();
    mockGet.mockReset();
    vi.clearAllMocks();
    useAuthStore.setState({ accessToken: 't', refreshToken: 'r', user: WHOLESALER_USER, tenantCode: 'TENA', retailerPortalCode: null });
    await renderAppRouterAt('/statements/print?retailer_id=ret-a-1&from=2026-08-01&to=2026-08-10');
    await waitFor(() => expect(screen.queryByTestId('statement-print-document')).not.toBeNull(), { timeout: 3000 });
    expect(mockGet).not.toHaveBeenCalledWith('/client/statements/print');
  });
});

// ---------------------------------------------------------------------------
// Genuine entry links from the real finance pages
// ---------------------------------------------------------------------------

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

describe('I2C-I2B — statement entry links from real finance pages', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGet.mockReset();
  });

  it('retailer FinanceBalancePage links to /client/statements/print with a valid period', async () => {
    mockGet.mockResolvedValueOnce(
      data(ok({ outstanding_balance: '1000.00', has_outstanding_balance: true, updated_at: '2026-08-10T08:00:00Z' }).data) as never,
    );
    render(
      <MemoryRouter initialEntries={['/client/finance']}>
        <Routes>
          <Route path="/client/finance" element={<ClientFinanceBalancePage />} />
        </Routes>
      </MemoryRouter>,
    );
    const link = await screen.findByTestId('retailer-statement-print-link');
    const href = link.getAttribute('href') ?? '';
    expect(href).toMatch(/^\/client\/statements\/print\?from=\d{4}-\d{2}-\d{2}&to=\d{4}-\d{2}-\d{2}$/);
    const params = new URLSearchParams(href.split('?')[1]);
    expect(params.get('from')).toMatch(DATE_RE);
    expect(params.get('to')).toMatch(DATE_RE);
    expect(link.textContent).toContain('statement');
  });

  it('supplier FinancePage links each receivable row to /statements/print with retailer_id', async () => {
    mockGet.mockImplementation(async (url: string) => {
      if (url === '/finance/summary') {
        return data(ok({
          total_revenue: 5000, total_cash_received: 700, outstanding_receivables: 350.5,
          overdue_receivables_count: 0, order_counts: {}, total_orders: 1,
          generated_at: '2026-08-10T08:00:00Z',
        }).data) as never;
      }
      if (url === '/finance/receivables/summary') {
        return data(ok({
          total_outstanding: 350.5, retailer_count: 1, order_count: 1,
          credit_receivables: 350.5, unpaid_order_balance: 0, by_retailer: [],
        }).data) as never;
      }
      if (url === '/finance/receivables/orders') {
        return data(ok({
          items: [{
            order_id: 'ord-1', retailer_id: 'ret-a-1', retailer_name: 'Kibera Duka',
            status: 'CONFIRMED', classification: 'credit_receivable', payment_method: 'credit',
            total_amount: 1050.5, cash_paid: 700, credit_amount: 350.5, balance_due: 350.5,
            age_days: 5,
          }],
          pagination: { page: 1, size: 20, total: 1, pages: 1 },
        }).data) as never;
      }
      return data(ok({ items: [], pagination: { page: 1, size: 20, total: 0, pages: 0 } }).data) as never;
    });
    render(
      <MemoryRouter initialEntries={['/finance']}>
        <Routes>
          <Route path="/finance" element={<FinancePage />} />
        </Routes>
      </MemoryRouter>,
    );
    const link = await screen.findByTestId('statement-link-ret-a-1');
    const href = link.getAttribute('href') ?? '';
    expect(href).toMatch(/^\/statements\/print\?retailer_id=ret-a-1&from=\d{4}-\d{2}-\d{2}&to=\d{4}-\d{2}-\d{2}$/);
    const params = new URLSearchParams(href.split('?')[1]);
    expect(params.get('retailer_id')).toBe('ret-a-1');
    expect(params.get('from')).toMatch(DATE_RE);
    expect(params.get('to')).toMatch(DATE_RE);
  });
});

// ---------------------------------------------------------------------------
// Money formatting sanity (reuses the shared string-only util)
// ---------------------------------------------------------------------------

describe('statement money — formatKes string-only', () => {
  it('exact grouping including signs and high precision', () => {
    expect(formatKes('2500.00')).toBe('KES 2,500.00');
    expect(formatKes('-700.00')).toBe('KES -700.00');
    expect(formatKes('9007199254740993.124999')).toBe('KES 9,007,199,254,740,993.124999');
    expect(formatKes('0.000001')).toBe('KES 0.000001');
  });
});

// ---------------------------------------------------------------------------
// R1 rule 6 — fixed Africa/Nairobi (EAT) calendar dates.
//
// Statement default/monthly ranges must NEVER use browser-local dates. These
// tests freeze "now" at 2026-08-10T22:30:00Z — an instant where the UTC
// calendar date (2026-08-10) differs from the EAT calendar date
// (2026-08-11, 01:30) — and prove the helpers return the EAT date.
// Date.now is stubbed (never fake timers, which would stall waitFor).
// ---------------------------------------------------------------------------

describe('R1 rule 6 — EAT calendar dates (never browser-local)', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('eatDateFromUtc converts a UTC instant to the Africa/Nairobi calendar date', () => {
    // 2026-08-10T22:30:00Z == 2026-08-11 01:30 EAT.
    expect(eatDateFromUtc('2026-08-10T22:30:00Z')).toBe('2026-08-11');
    // Late EAT evening is still the same EAT calendar day.
    expect(eatDateFromUtc('2026-08-11T20:59:59Z')).toBe('2026-08-11');
    // The EAT day boundary: 21:00 UTC == next EAT midnight.
    expect(eatDateFromUtc('2026-08-11T21:00:00Z')).toBe('2026-08-12');
  });

  it('frozen time: the UTC calendar date differs from EAT; eatToday picks EAT', () => {
    vi.spyOn(Date, 'now').mockReturnValue(Date.parse('2026-08-10T22:30:00Z'));
    // At this frozen instant the UTC calendar date is still 2026-08-10, while
    // Africa/Nairobi is already 2026-08-11 — the boundary that browser-local
    // date handling would get wrong.
    const utcDate = new Intl.DateTimeFormat('en-CA', {
      timeZone: 'UTC',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).format(new Date());
    expect(utcDate).toBe('2026-08-10');

    expect(eatToday()).toBe('2026-08-11');
    expect(eatToday()).not.toBe(utcDate);

    // Month + default ranges anchor on EAT dates.
    expect(eatMonthRange()).toEqual({ from: '2026-08-01', to: '2026-08-11' });
    expect(eatDefaultRange().to).toBe('2026-08-11');
  });

  it('entry links and the print page use EAT anchors (render path)', async () => {
    vi.spyOn(Date, 'now').mockReturnValue(Date.parse('2026-08-10T22:30:00Z'));
    // The retailer page link must carry EAT dates (from=2026-08-01, to=2026-08-11).
    mockGet.mockResolvedValueOnce(
      data(ok({ outstanding_balance: '1000.00', has_outstanding_balance: true, updated_at: '2026-08-10T08:00:00Z' }).data) as never,
    );
    render(
      <MemoryRouter initialEntries={['/client/finance']}>
        <Routes>
          <Route path="/client/finance" element={<ClientFinanceBalancePage />} />
        </Routes>
      </MemoryRouter>,
    );
    const link = await screen.findByTestId('retailer-statement-print-link');
    const href = link.getAttribute('href') ?? '';
    expect(href).toBe('/client/statements/print?from=2026-08-01&to=2026-08-11');
  });
});
