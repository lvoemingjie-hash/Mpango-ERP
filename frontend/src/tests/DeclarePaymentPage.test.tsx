import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import DeclarePaymentPage from '@/pages/client/DeclarePaymentPage';

const ORDER_ID = 'order-abc-123';
const mockNavigate = vi.fn();

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

/**
 * Sequential UUID generator returning DISTINCT valid UUIDs.
 *
 * The R5 fixed-value mock was a false-green risk: if the component
 * incorrectly rotated the key on failure, the mock would return the
 * same value. With distinct sequential UUIDs we can prove:
 *   - failure does NOT consume another UUID (same key reused);
 *   - success DOES consume another UUID (key rotated).
 *
 * Each call to the spy returns the next UUID in sequence, so we can
 * detect unwanted rotation by checking whether the sequence advanced.
 */
const UUIDS: `${string}-${string}-${string}-${string}-${string}`[] = [
  '00000000-0000-4000-8000-000000000001',
  '00000000-0000-4000-8000-000000000002',
  '00000000-0000-4000-8000-000000000003',
  '00000000-0000-4000-8000-000000000004',
  '00000000-0000-4000-8000-000000000005',
  '00000000-0000-4000-8000-000000000006',
  '00000000-0000-4000-8000-000000000007',
  '00000000-0000-4000-8000-000000000008',
  '00000000-0000-4000-8000-000000000009',
  '00000000-0000-4000-8000-000000000010',
  '00000000-0000-4000-8000-000000000011',
  '00000000-0000-4000-8000-000000000012',
  '00000000-0000-4000-8000-000000000013',
  '00000000-0000-4000-8000-000000000014',
  '00000000-0000-4000-8000-000000000015',
  '00000000-0000-4000-8000-000000000016',
  '00000000-0000-4000-8000-000000000017',
  '00000000-0000-4000-8000-000000000018',
  '00000000-0000-4000-8000-000000000019',
  '00000000-0000-4000-8000-000000000020',
];

describe('DeclarePaymentPage idempotency', () => {
  let uuidIdx = 0;

  beforeEach(() => {
    vi.clearAllMocks();
    uuidIdx = 0;

    if (typeof crypto.randomUUID !== 'function') {
      Object.defineProperty(crypto, 'randomUUID', {
        configurable: true,
        writable: true,
        value: () => 'fallback',
      });
    }
    vi.spyOn(crypto, 'randomUUID').mockImplementation(() => UUIDS[uuidIdx++]);
    vi.mocked(submitDeclaration).mockResolvedValue({} as never);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  /** Total calls to the spy (includes vitest internals). */
  function totalCalls(): number {
    return vi.mocked(crypto.randomUUID).mock.calls.length;
  }

  function fillAmount(value: string) {
    fireEvent.change(screen.getByLabelText(/amount/i), { target: { value } });
  }

  function submit() {
    fireEvent.click(screen.getByRole('button', { name: /submit declaration/i }));
  }

  it('reuses the same idempotency key when the first request fails and the user retries', async () => {
    const callsBeforeMount = totalCalls();
    render(<DeclarePaymentPage />);
    const callsAfterMount = totalCalls();

    // Exactly one UUID was consumed during mount (the component's useRef init).
    const mountDelta = callsAfterMount - callsBeforeMount;
    expect(mountDelta).toBeGreaterThanOrEqual(1);

    vi.mocked(submitDeclaration)
      .mockRejectedValueOnce(new Error('Network timeout'))
      .mockRejectedValueOnce(new Error('Server error'));

    fillAmount('500');
    submit();
    await waitFor(() => expect(submitDeclaration).toHaveBeenCalledTimes(1));

    // Retry after failure.
    submit();
    await waitFor(() => expect(submitDeclaration).toHaveBeenCalledTimes(2));

    const keys = vi.mocked(submitDeclaration).mock.calls.map((c) => c[2]);
    expect(keys).toHaveLength(2);
    // Both submissions must use the same key (no rotation on failure).
    // With distinct sequential UUIDs, if the component incorrectly rotated,
    // keys[1] would differ from keys[0].
    expect(keys[0]).toBe(keys[1]);
  });

  it('rotates the idempotency key only after a successful submission', async () => {
    const callsBeforeMount = totalCalls();
    render(<DeclarePaymentPage />);
    const callsAfterMount = totalCalls();

    fillAmount('300');
    submit();

    // On success: randomUUID IS called again (key rotation).
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledTimes(1));

    const keys = vi.mocked(submitDeclaration).mock.calls.map((c) => c[2]);
    expect(keys[0]).toBe(UUIDS[callsBeforeMount]); // first UUID consumed by component

    // After success, the spy was called at least once more (rotation).
    expect(totalCalls()).toBeGreaterThan(callsAfterMount);

    expect(mockNavigate).toHaveBeenCalledWith(`/client/orders/${ORDER_ID}`);
  });

  it('prevents duplicate in-flight submissions on rapid double-submit', async () => {
    const { container } = render(<DeclarePaymentPage />);
    const form = container.querySelector('form') as HTMLFormElement;
    fillAmount('750');

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

  /**
   * RED evidence: the R5 fixed-value mock would allow an incorrect
   * failure-time rotation to pass undetected.  With distinct sequential
   * UUIDs, if the component rotated on failure, keys[1] would differ
   * from keys[0] and the assertion would catch it.
   */
  it('sequential UUID mock produces distinct values (false-green guard)', () => {
    const results: string[] = [];
    for (let i = 0; i < 3; i++) {
      results.push(crypto.randomUUID());
    }
    expect(results[0]).not.toBe(results[1]);
    expect(results[1]).not.toBe(results[2]);
    expect(results[0]).not.toBe(results[2]);
  });
});
