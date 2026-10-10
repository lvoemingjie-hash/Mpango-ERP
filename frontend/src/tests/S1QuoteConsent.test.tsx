import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QuoteConsent } from '@/components/pricing/QuoteConsent';
import { formatMoney } from '@/utils/printFormat';
import type { ServerQuote } from '@/types/pricing';

const quote = (total = '180.00'): ServerQuote => ({
  quote_token: 'synthetic-unusable-quote', country: 'KE', currency: 'KES', expires_at: 9999999999,
  total, lines: [{ sku_id: 'sku', sku_code: 'BOX', product_name: 'Boxes', quantity: 2,
    unit: 'Box', display_label: 'Boxes', package_quantity: '12', unit_price: '90.00',
    subtotal: total, revision: 1, source: 'BASE_PRICE' }],
});

describe('S1 explicit server consent', () => {
  beforeEach(() => { vi.restoreAllMocks(); });
  it('requires a preview and a separate explicit acceptance', async () => {
    const submit = vi.fn().mockResolvedValue(undefined);
    render(<QuoteConsent intent="one" preview={vi.fn().mockResolvedValue(quote())} submit={submit} />);
    expect(screen.queryByText('Accept these prices and create draft')).toBeNull();
    fireEvent.click(screen.getByText('Review server quote'));
    await screen.findByText('Server total: KES 180.00');
    expect(submit).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('Accept these prices and create draft'));
    await waitFor(() => expect(submit).toHaveBeenCalledTimes(1));
    expect(submit.mock.calls[0][0]).toEqual(quote());
  });

  it('does not automatically accept a replacement price, including another change', async () => {
    const submit = vi.fn().mockRejectedValue({ response: { status: 409, data: {
      code: 'PRICE_PREVIEW_STALE', details: { old_total: '180.00', new_total: '220.00',
        delta: '40.00', quote: quote('220.00') } } } });
    render(<QuoteConsent intent="one" preview={vi.fn().mockResolvedValue(quote())} submit={submit} />);
    fireEvent.click(screen.getByText('Review server quote'));
    await screen.findByText('Server total: KES 180.00');
    fireEvent.click(screen.getByText('Accept these prices and create draft'));
    await screen.findByText('Server total: KES 220.00');
    expect(submit).toHaveBeenCalledTimes(1);
    submit.mockRejectedValue({ response: { status: 409, data: { code: 'PRICE_PREVIEW_STALE',
      details: { old_total: '220.00', new_total: '240.00', delta: '20.00', quote: quote('240.00') } } } });
    fireEvent.click(screen.getByText('Accept these prices and create draft'));
    await screen.findByText('Server total: KES 240.00');
    expect(submit).toHaveBeenCalledTimes(2);
    expect(submit.mock.calls[1][0].total).toBe('220.00');
  });

  it.each([undefined, 500, 408])('unknown result (%s) keeps original closure, quote and key', async (status) => {
    const original = vi.fn().mockRejectedValue(status ? { response: { status } } : new Error('network'));
    const newer = vi.fn();
    const props = { intent: 'one', preview: vi.fn().mockResolvedValue(quote()), submit: original };
    const view = render(<QuoteConsent {...props} />);
    fireEvent.click(screen.getByText('Review server quote'));
    await screen.findByText('Server total: KES 180.00');
    fireEvent.click(screen.getByText('Accept these prices and create draft'));
    await screen.findByText('Retry same accepted submission');
    view.rerender(<QuoteConsent {...props} intent="changed" submit={newer} />);
    original.mockResolvedValue(undefined);
    fireEvent.click(screen.getByText('Retry same accepted submission'));
    await waitFor(() => expect(original).toHaveBeenCalledTimes(2));
    expect(original.mock.calls[1]).toEqual(original.mock.calls[0]);
    expect(newer).not.toHaveBeenCalled();
  });

  it('discards a late preview after the selection changed', async () => {
    let resolve!: (q: ServerQuote) => void;
    const props = { preview: () => new Promise<ServerQuote>((done) => { resolve = done; }), submit: vi.fn() };
    const view = render(<QuoteConsent {...props} intent="old" />);
    fireEvent.click(screen.getByText('Review server quote'));
    view.rerender(<QuoteConsent {...props} intent="new" />);
    await act(async () => resolve(quote()));
    expect(screen.queryByText('Server total: KES 180.00')).toBeNull();
  });

  it('warns explicitly before the atomic cancellation and replacement', () => {
    render(<QuoteConsent intent="replace" replacing preview={vi.fn()} submit={vi.fn()} />);
    expect(screen.getByText(/cancels the old draft and creates a new draft atomically/)).toBeTruthy();
  });

  it('keeps large exact string digits and makes old/mixed currency unknown', () => {
    expect(formatMoney('9007199254740993.125', 'UGX')).toBe('UGX 9,007,199,254,740,993.125');
    expect(formatMoney('50.00', null)).toBe('LEGACY_CURRENCY_UNVERIFIED 50.00');
    expect(formatMoney('50.00', 'MIXED')).toBe('LEGACY_CURRENCY_UNVERIFIED 50.00');
  });
});
