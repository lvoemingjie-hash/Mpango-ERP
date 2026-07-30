import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { api } from '@/services/api';
import { useAuthStore } from '@/stores/authStore';
import { ClientLayout } from '@/components/layout/ClientLayout';
import { clientFinanceService } from '@/services/clientFinanceService';
import { ClientPaymentHistoryPage } from '@/pages/client/PaymentHistoryPage';
import { ClientFinanceBalancePage } from '@/pages/client/FinanceBalancePage';

vi.mock('@/services/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

const paymentResponse = {
  data: {
    success: true,
    data: {
      items: [
        {
          id: 'pay-1',
          order_id: 'order-1',
          amount: '1250.50',
          method: 'credit',
          status: 'pending',
          created_at: '2026-07-30T08:00:00Z',
        },
      ],
      pagination: { page: 1, size: 20, total: 1, pages: 1 },
    },
    timestamp: '2026-07-30T08:00:00Z',
  },
};

const balanceResponse = {
  data: {
    success: true,
    data: {
      outstanding_balance: '345.67',
      has_outstanding_balance: true,
      updated_at: '2026-07-30T08:00:00Z',
    },
    timestamp: '2026-07-30T08:00:00Z',
  },
};

beforeEach(() => {
  vi.clearAllMocks();
  useAuthStore.setState({
    accessToken: 'retailer-token',
    refreshToken: 'refresh-token',
    user: {
      id: 'retailer-user',
      email: 'retailer@example.com',
      full_name: 'Retailer One',
      tenant_id: 'tenant-a',
      tenant_schema: 't_a',
      roles: ['retailer_operator'],
      permissions: ['client:payments:read', 'client:finance:read'],
    },
    tenantCode: null,
    retailerPortalCode: 'SUPP42',
  });
});

describe('DC-12R1-S3-S2 clientFinanceService', () => {
  it('uses only GET client financial endpoints with contextual JWT', async () => {
    vi.mocked(api.get).mockResolvedValueOnce(paymentResponse as never).mockResolvedValueOnce(balanceResponse as never);

    await clientFinanceService.getPayments(1, 20, { method: 'credit', status: 'pending', order_id: 'order-1' });
    await clientFinanceService.getBalance();

    expect(api.get).toHaveBeenNthCalledWith(1, '/client/payments', {
      params: { page: 1, size: 20, method: 'credit', status: 'pending', order_id: 'order-1' },
    });
    expect(api.get).toHaveBeenNthCalledWith(2, '/client/finance/balance');
    expect(api.post).not.toHaveBeenCalled();
    expect(api.put).not.toHaveBeenCalled();
    expect(api.patch).not.toHaveBeenCalled();
    expect(api.delete).not.toHaveBeenCalled();
  });
});

describe('DC-12R1-S3-S2 retailer finance pages', () => {
  it('renders payment history and pagination without write requests', async () => {
    vi.mocked(api.get).mockResolvedValueOnce(paymentResponse as never);

    render(
      <MemoryRouter initialEntries={['/client/payments']}>
        <Routes>
          <Route path="/client/payments" element={<ClientPaymentHistoryPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText(/loading payments/i)).toBeInTheDocument();
    expect(await screen.findByText(/payment history/i)).toBeInTheDocument();
    expect(screen.getByText(/KES\s*1,250\.50/i)).toBeInTheDocument();
    expect(screen.getByText(/credit sale/i)).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('renders the authoritative outstanding balance without recomputing it', async () => {
    vi.mocked(api.get).mockResolvedValueOnce(balanceResponse as never);

    render(
      <MemoryRouter initialEntries={['/client/finance']}>
        <Routes>
          <Route path="/client/finance" element={<ClientFinanceBalancePage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText(/loading balance/i)).toBeInTheDocument();
    expect(await screen.findByText(/outstanding balance/i)).toBeInTheDocument();
    expect(screen.getByText(/KES\s*345\.67/i)).toBeInTheDocument();
    expect(screen.getByText(/from your supplier relationship/i)).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('shows empty and error states', async () => {
    vi.mocked(api.get).mockResolvedValueOnce({
      data: { success: true, data: { items: [], pagination: { page: 1, size: 20, total: 0, pages: 0 } }, timestamp: 't' },
    } as never);

    const empty = render(
      <MemoryRouter initialEntries={['/client/payments']}>
        <Routes>
          <Route path="/client/payments" element={<ClientPaymentHistoryPage />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByText(/no payments yet/i)).toBeInTheDocument();
    empty.unmount();

    vi.mocked(api.get).mockRejectedValueOnce(new Error('network'));
    render(
      <MemoryRouter initialEntries={['/client/payments']}>
        <Routes>
          <Route path="/client/payments" element={<ClientPaymentHistoryPage />} />
        </Routes>
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText(/failed to load payments/i)).toBeInTheDocument());
    expect(api.post).not.toHaveBeenCalled();
  });
});

describe('DC-12R1-S3-S2 ClientLayout finance navigation', () => {
  it('adds read-only payment and finance navigation entries', () => {
    vi.mocked(api.get).mockResolvedValue(balanceResponse as never);

    render(
      <MemoryRouter initialEntries={['/client/finance']}>
        <Routes>
          <Route element={<ClientLayout />}>
            <Route path="/client/finance" element={<div>Finance child</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByRole('link', { name: /payments/i })).toHaveAttribute('href', '/client/payments');
    expect(screen.getByRole('link', { name: /finance/i })).toHaveAttribute('href', '/client/finance');
    expect(screen.getByText(/finance child/i)).toBeInTheDocument();
  });
});
