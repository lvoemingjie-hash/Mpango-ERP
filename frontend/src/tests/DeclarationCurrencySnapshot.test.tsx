import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import DeclarationHistoryPage from '@/pages/client/DeclarationHistoryPage';
import DeclarationQueuePage from '@/pages/finance/DeclarationQueuePage';
import { api } from '@/services/api';
import type { PaymentDeclaration } from '@/types/declaration';

vi.mock('@/services/api', () => ({ api: {
  get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn(),
} }));

function row(extra: Partial<PaymentDeclaration> = {}): PaymentDeclaration {
  return { id: 'declaration-1', order_id: 'order-1', declared_amount: '9007199254740993.1250',
    status: 'pending', method: 'cash', submitted_at: '2026-10-15T00:00:00Z', ...extra };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(navigator, 'language', 'get').mockReturnValue('en-KE');
  vi.mocked(api.post).mockResolvedValue({ data: { success: true, data: { id: 'confirmed-from-server' } } });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

for (const [name, Page, endpoint] of [
  ['history', DeclarationHistoryPage, '/client/declarations'],
  ['queue', DeclarationQueuePage, '/declarations'],
] as const) {
  describe(`${name} server currency snapshot`, () => {
    it.each([
      ['UGX', 'KNOWN', 'UGX'],
      ['KES', 'KNOWN', 'KES'],
      [undefined, undefined, 'LEGACY_CURRENCY_UNVERIFIED'],
      ['XXX', 'KNOWN', 'LEGACY_CURRENCY_UNVERIFIED'],
      ['KES', 'LEGACY_CURRENCY_UNVERIFIED', 'LEGACY_CURRENCY_UNVERIFIED'],
    ])('renders %s/%s without rounding or currency inference', async (currency, currency_status, label) => {
      const original = row({ currency, currency_status });
      vi.mocked(api.get).mockResolvedValue({ data: { success: true, data: {
        items: [original], pagination: { pages: 1 },
      } } });
      render(<MemoryRouter><Page /></MemoryRouter>);
      expect(await screen.findByText(`${label} 9,007,199,254,740,993.1250`, { exact: false })).toBeInTheDocument();
      expect(original.declared_amount).toBe('9007199254740993.1250');
      expect(api.get).toHaveBeenCalledTimes(1);
      expect(api.get).toHaveBeenCalledWith(endpoint, expect.any(Object));
      expect(api.post).not.toHaveBeenCalled();
      expect(api.put).not.toHaveBeenCalled();
      expect(api.patch).not.toHaveBeenCalled();
      expect(api.delete).not.toHaveBeenCalled();
    });

    it('keeps mixed historical rows independent of the KE viewer and confirmation explicit', async () => {
      const items = [row({ id: 'ug', currency: 'UGX', currency_status: 'KNOWN', declared_amount: '100.000001' }),
        row({ id: 'ke', currency: 'KES', currency_status: 'KNOWN', declared_amount: '20.5000' })];
      const before = JSON.stringify(items);
      vi.mocked(api.get).mockResolvedValue({ data: { success: true, data: { items, pagination: { pages: 1 } } } });
      render(<MemoryRouter><Page /></MemoryRouter>);
      expect(await screen.findByText('UGX 100.000001', { exact: false })).toBeInTheDocument();
      expect(screen.getByText('KES 20.5000', { exact: false })).toBeInTheDocument();
      expect(JSON.stringify(items)).toBe(before);
      expect(api.get).toHaveBeenCalledTimes(1);
      expect(api.post).not.toHaveBeenCalled();
      expect(screen.queryByTestId('confirmed-receipt-banner')).not.toBeInTheDocument();
      if (name === 'queue') {
        fireEvent.click(screen.getAllByRole('button', { name: /^Confirm$/ })[0]);
        await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
        expect(api.post).toHaveBeenCalledWith('/declarations/ug/confirm');
        expect(await screen.findByTestId('confirmed-receipt-link')).toHaveAttribute('href', '/declarations/confirmed-from-server/receipt');
      } else {
        expect(screen.getAllByText('Payment Declaration — Not Received')).toHaveLength(2);
        expect(screen.queryByText('Payment Received')).not.toBeInTheDocument();
      }
    });
  });
}
