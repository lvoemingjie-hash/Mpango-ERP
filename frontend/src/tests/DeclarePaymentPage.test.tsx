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

// ===========================================================================
// DC-12R1-MVP-R0-R1 (WPR-003): neutral, status-derived declaration error copy.
//
// The declaration UI must NEVER render the backend body, error code, schema
// name, internal id, or raw exception text. Only fixed, status-derived public
// copy is shown. These tests prove a malicious/verbose payload cannot reach
// the UI, and that the idempotency contract is preserved (same key on failure).
// ===========================================================================

describe('DeclarePaymentPage neutral error copy (WPR-003)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    if (typeof crypto.randomUUID !== 'function') {
      Object.defineProperty(crypto, 'randomUUID', {
        configurable: true, writable: true, value: () => 'fallback',
      });
    }
    vi.spyOn(crypto, 'randomUUID').mockReturnValue('11111111-1111-4111-8111-111111111111');
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

  // A payload a verbose/malicious backend might return. None of it may appear.
  const MALICIOUS_MESSAGE = 'SQLSTATE 23505 duplicate key value violates payments_declare_xact schema=public tenant_user_id=9f3e raw: ERROR: relation "public.payments" does not exist';
  const MALICIOUS_CODE = 'STATEMENT_INTERNAL_INCONSISTENT';

  it('never renders the backend body message / code / schema / internal id on a 409', async () => {
    vi.mocked(submitDeclaration).mockRejectedValueOnce({
      response: {
        status: 409,
        data: { message: MALICIOUS_MESSAGE, code: MALICIOUS_CODE },
      },
    });
    render(<DeclarePaymentPage />);
    fillAmount('500');
    submit();
    await waitFor(() => expect(screen.queryByText(/could not be processed/i)).not.toBeNull());

    // The malicious payload MUST NOT leak into the UI.
    expect(screen.queryByText(/SQLSTATE/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/23505/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/payments_declare_xact/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/schema=public/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/tenant_user_id/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/9f3e/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/relation "public.payments"/i)).not.toBeInTheDocument();
    expect(screen.queryByText(new RegExp(MALICIOUS_CODE))).not.toBeInTheDocument();
    expect(screen.queryByText(new RegExp(MALICIOUS_MESSAGE.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')))).not.toBeInTheDocument();
  });

  it('shows the fixed neutral 409 copy (status-derived), not the backend message', async () => {
    vi.mocked(submitDeclaration).mockRejectedValueOnce({
      response: { status: 409, data: { message: MALICIOUS_MESSAGE } },
    });
    render(<DeclarePaymentPage />);
    fillAmount('500');
    submit();
    await waitFor(() => expect(screen.getByText(/This declaration could not be processed\. Please review and try again\./i)).toBeInTheDocument());
  });

  it('never renders the raw Error.message on a network/timeout failure', async () => {
    vi.mocked(submitDeclaration).mockRejectedValueOnce(new Error('Network timeout ECONNREFUSED 10.0.0.5:5432'));
    render(<DeclarePaymentPage />);
    fillAmount('300');
    submit();
    await waitFor(() => expect(screen.queryByText(/could not submit your declaration right now/i)).not.toBeNull());
    // Raw exception text MUST NOT leak.
    expect(screen.queryByText(/Network timeout/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/ECONNREFUSED/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/10\.0\.0\.5/i)).not.toBeInTheDocument();
  });

  it('preserves the idempotency key across a neutral-copy failure (same key on retry)', async () => {
    vi.spyOn(crypto, 'randomUUID').mockReturnValueOnce('22222222-2222-4222-8222-222222222222');
    vi.mocked(submitDeclaration)
      .mockRejectedValueOnce({ response: { status: 500, data: { message: 'boom' } } })
      .mockRejectedValueOnce({ response: { status: 409, data: { message: 'dup' } } });
    render(<DeclarePaymentPage />);
    fillAmount('750');
    submit();
    await waitFor(() => expect(submitDeclaration).toHaveBeenCalledTimes(1));
    submit();
    await waitFor(() => expect(submitDeclaration).toHaveBeenCalledTimes(2));
    const keys = vi.mocked(submitDeclaration).mock.calls.map((c) => c[2]);
    expect(keys).toHaveLength(2);
    // Same key reused across failures (no rotation on failure) — unchanged.
    expect(keys[0]).toBe(keys[1]);
    expect(keys[0]).toBe('22222222-2222-4222-8222-222222222222');
  });
});
