import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import DeclarePaymentPage from '@/pages/client/DeclarePaymentPage';

const ORDER_ID = 'order-abc-123';
const mockNavigate = vi.fn();

// Keep MemoryRouter etc. available; only stub the router hooks the page uses.
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    useParams: () => ({ orderId: ORDER_ID }),
  };
});

vi.mock('@/services/declarationService', () => ({
  submitDeclaration: vi.fn(),
}));

import { submitDeclaration } from '@/services/declarationService';

describe('DeclarePaymentPage idempotency', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    // Deterministic idempotency keys so we can assert exact values.
    // Use a stable UUID so retries reuse the same key regardless of call count.
    if (typeof crypto.randomUUID !== 'function') {
      Object.defineProperty(crypto, 'randomUUID', {
        configurable: true,
        writable: true,
        value: () => 'fallback',
      });
    }
    vi.spyOn(crypto, 'randomUUID').mockImplementation(() => '00000000-0000-4000-8000-000000000001');

    // Default happy path.
    vi.mocked(submitDeclaration).mockResolvedValue({} as never);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  function fillAmount(value: string) {
    fireEvent.change(screen.getByLabelText(/amount/i), { target: { value } });
  }

  function submit() {
    fireEvent.click(screen.getByRole('button', { name: /submit declaration/i }));
  }

  it('reuses the same idempotency key when the first request fails and the user retries', async () => {
    render(<DeclarePaymentPage />);

    // First attempt fails (e.g. timeout / network failure), then a retry also fails.
    vi.mocked(submitDeclaration)
      .mockRejectedValueOnce(new Error('Network timeout'))
      .mockRejectedValueOnce(new Error('Server error'));

    fillAmount('500');
    submit();
    await waitFor(() => expect(submitDeclaration).toHaveBeenCalledTimes(1));

    // Retry after the failure.
    submit();
    await waitFor(() => expect(submitDeclaration).toHaveBeenCalledTimes(2));

    const keys = vi.mocked(submitDeclaration).mock.calls.map((c) => c[2]);
    expect(keys).toHaveLength(2);
    // Both submissions must use the same idempotency key (no rotation on failure).
    expect(keys[0]).toBe('00000000-0000-4000-8000-000000000001');
    expect(keys[1]).toBe(keys[0]);
  });

  it('prevents duplicate in-flight submissions on rapid double-submit', async () => {
    const { container } = render(<DeclarePaymentPage />);
    const form = container.querySelector('form') as HTMLFormElement;
    fillAmount('750');

    // Fire two submits synchronously, before the first promise can settle.
    fireEvent.submit(form);
    fireEvent.submit(form);

    await waitFor(() => expect(submitDeclaration).toHaveBeenCalledTimes(1));
    expect(submitDeclaration).toHaveBeenCalledTimes(1);
  });

  it('navigates once after a successful submission', async () => {
    render(<DeclarePaymentPage />);

    fillAmount('300');
    submit();

    await waitFor(() => expect(mockNavigate).toHaveBeenCalledTimes(1));
    expect(mockNavigate).toHaveBeenCalledWith(`/client/orders/${ORDER_ID}`);
    expect(submitDeclaration).toHaveBeenCalledTimes(1);
  });

  it('does not touch localStorage or sessionStorage', async () => {
    const setItemSpy = vi.spyOn(Storage.prototype, 'setItem');
    const getItemSpy = vi.spyOn(Storage.prototype, 'getItem');
    const removeItemSpy = vi.spyOn(Storage.prototype, 'removeItem');

    render(<DeclarePaymentPage />);
    fillAmount('900');
    submit();

    await waitFor(() => expect(mockNavigate).toHaveBeenCalledTimes(1));

    expect(setItemSpy).not.toHaveBeenCalled();
    expect(getItemSpy).not.toHaveBeenCalled();
    expect(removeItemSpy).not.toHaveBeenCalled();
  });
});
