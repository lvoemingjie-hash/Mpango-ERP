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
  let uuidCounter = 0;

  beforeEach(() => {
    vi.clearAllMocks();
    uuidCounter = 0;

    // Deterministic idempotency keys so we can assert exact values.
    if (typeof crypto.randomUUID !== 'function') {
      Object.defineProperty(crypto, 'randomUUID', {
        configurable: true,
        writable: true,
        value: () => 'fallback',
      });
    }
    vi.spyOn(crypto, 'randomUUID').mockImplementation(() => `00000000-0000-4000-8000-${String(++uuidCounter).padStart(12, '0')}`);

    // Default happy path.
    vi.mocked(submitDeclaration).mockResolvedValue({} as never);
  });

  function getRandomUuidCallCount() {
    // Count only calls that returned our format (filtering out vitest's own).
    return vi.mocked(crypto.randomUUID).mock.results.filter(
      (r) => typeof r.value === 'string' && r.value.startsWith('00000000-0000-4000-8000-')
    ).length;
  }

  afterEach(() => {
    vi.restoreAllMocks();
  });

  function fillAmount(value: string) {
    const input = document.querySelector('input[type="number"]') as HTMLInputElement;
    fireEvent.change(input, { target: { value } });
  }

  function submit() {
    fireEvent.click(screen.getByRole('button', { name: /submit declaration/i }));
  }

  it('reuses the same idempotency key when the first request fails and the user retries', async () => {
    render(<DeclarePaymentPage />);
    // Key minted exactly once when the form mounts (filter vitest's own calls).
    expect(getRandomUuidCallCount()).toBe(1);

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
    expect(keys[0]).toBe('00000000-0000-4000-8000-000000000001');
    expect(keys[1]).toBe('00000000-0000-4000-8000-000000000001');
    // Failures must NOT rotate the key (both calls used the same key value).
    expect(keys[0]).toBe(keys[1]);
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
