import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { FinancePage } from '@/pages/finance/FinancePage';
import { financeService } from '@/services/financeService';

vi.mock('@/services/financeService', () => ({
  financeService: {
    getSummary: vi.fn(), getReceivablesSummary: vi.fn(), getReceivablesOrders: vi.fn(),
  },
}));

afterEach(() => { cleanup(); vi.resetAllMocks(); });

function arrange(currency: string | null, mixed = false) {
  vi.mocked(financeService.getSummary).mockResolvedValue({ data: { data: {
    currency, currency_status: mixed ? 'mixed' : currency ? 'verified_snapshot' : 'unverified',
    outstanding_receivables: mixed ? null : 100000,
    total_cash_received: mixed ? null : 0, total_revenue: mixed ? null : 0,
    overdue_receivables_count: 0, order_counts: {}, total_orders: 1,
    generated_at: '2026-10-23T00:00:00Z', outstanding_by_currency: { KES: 50, UGX: 100000 },
  } } } as never);
  vi.mocked(financeService.getReceivablesSummary).mockResolvedValue({ data: { data: {
    total_outstanding: 100000, retailer_count: 1, order_count: 1,
    credit_receivables: 0, unpaid_order_balance: 100000, by_retailer: [],
  } } } as never);
  vi.mocked(financeService.getReceivablesOrders).mockResolvedValue({ data: { data: {
    items: [], pagination: { page: 1, size: 20, total: 0, pages: 0 },
  } } } as never);
  render(<MemoryRouter><FinancePage /></MemoryRouter>);
}

describe('Finance currency is a server fact, not a fixed viewer locale', () => {
  it('does not present existing ledger revenue as a complete sales account', async () => {
    arrange('KES');
    expect(await screen.findByText('Existing ledger only. Not a complete sales revenue or refund statement.')).toBeInTheDocument();
  });
  it.each(['UGX', 'KES'])('labels %s without relabelling or converting', async currency => {
    arrange(currency);
    expect(await screen.findByText(`${currency} 100,000`)).toBeInTheDocument();
    expect(screen.queryByText(/Ksh/)).not.toBeInTheDocument();
  });

  it('marks unknown history explicitly instead of defaulting to KES', async () => {
    arrange(null);
    expect(await screen.findByText('LEGACY_CURRENCY_UNVERIFIED 100,000')).toBeInTheDocument();
    expect(screen.queryByText(/KES 100,000/)).not.toBeInTheDocument();
  });

  it('shows separate currency buckets instead of a mixed grand total', async () => {
    arrange(null, true);
    expect(await screen.findByRole('region', { name: 'Receivables by currency' })).toBeInTheDocument();
    expect(screen.getByText('KES 50')).toBeInTheDocument();
    expect(screen.getByText('UGX 100,000')).toBeInTheDocument();
    expect(screen.queryByText(/KES 100,050/)).not.toBeInTheDocument();
  });
});
