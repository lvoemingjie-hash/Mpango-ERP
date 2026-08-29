import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import { ClientLoginPage } from '@/pages/client/ClientLoginPage';
import { RetailerForgotPasswordPage } from '@/pages/retailer/RetailerForgotPasswordPage';
import { RetailerResetPasswordPage } from '@/pages/retailer/RetailerResetPasswordPage';

/**
 * DC-12R1-MVP-L1-J1-H2-C-R1 — retailer password-recovery discovery.
 *
 * Frontend coverage for the H2-C contract node inventory (HC01-HC17):
 *  - HC01-HC10: discovery entry, invalid-portal zero-call, form validation,
 *    fixed neutral result, single POST on double click.
 *  - HC12: fragment w read BEFORE URL scrub; token/w never in query, storage,
 *    console, or the reset POST body (w is public: fragment + success URL
 *    only).
 *  - HC13: success CTA returns to /retail/login?w=<CODE>, never /login.
 *  - HC14: legacy link (no w) still completes the reset and shows only the
 *    neutral return-to-supplier guidance — no /login CTA, no guessing.
 *  - HC15: forged/expired token stays on the neutral invalid page behavior.
 *  - HC04/HC16 (390px no-overflow) and HC11/HC17 (email link content) are
 *    layout/browser and backend nodes: HC04/HC16 get jsdom structural
 *    coverage here (bounded max-w-sm + px-4 containers, same responsive
 *    pattern as the accepted credential pages); authoritative 390px
 *    execution is the later browser gate, and HC11/HC17 are covered by
 *    backend/tests/test_dc12r1_j1_h2c_retailer_recovery_discovery.py.
 */

const { mockPost } = vi.hoisted(() => ({
  mockPost: vi.fn(),
}));

vi.mock('@/services/api', () => ({
  api: {
    get: vi.fn(),
    post: mockPost,
  },
}));

function renderAt(path: string, element: React.ReactElement) {
  window.history.pushState({}, '', path);
  return render(<BrowserRouter>{element}</BrowserRouter>);
}

const NEUTRAL_OK = { data: { success: true, data: {}, message: 'neutral', timestamp: '2026-08-26T00:00:00Z' } };

describe('H2-C-R1 retailer recovery discovery (HC01-HC17 frontend nodes)', () => {
  beforeEach(() => {
    mockPost.mockReset();
    window.localStorage.clear();
    window.sessionStorage.clear();
    window.history.pushState({}, '', '/');
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  // HC01: valid portal shows the discovery entry with the normalized code.
  it('HC01: valid portal /retail/login?w=VALID shows Forgot password entry carrying the code', () => {
    renderAt('/retail/login?w=VALID', <ClientLoginPage />);
    const link = screen.getByRole('link', { name: /forgot password\?/i });
    expect(link).toHaveAttribute('href', '/retailer/forgot-password?w=VALID');
  });

  // HC01 (normalization): lowercase input is normalized before the href.
  it('HC01: lowercase portal code is normalized to UPPERCASE in the entry href', () => {
    renderAt('/retail/login?w=acme01', <ClientLoginPage />);
    expect(screen.getByRole('link', { name: /forgot password\?/i })).toHaveAttribute(
      'href',
      '/retailer/forgot-password?w=ACME01',
    );
  });

  // HC02: missing w AND explicitly malformed w=BAD%21 both hide the entry
  // and render the neutral invalid-portal state.
  it('HC02: missing w shows no entry and the neutral invalid-portal state', () => {
    renderAt('/retail/login', <ClientLoginPage />);
    expect(screen.getByText('Invalid Portal')).toBeDefined();
    expect(screen.queryByRole('link', { name: /forgot password\?/i })).toBeNull();
  });

  it('HC02: malformed w=BAD%21 shows no entry and the neutral invalid-portal state', () => {
    renderAt('/retail/login?w=BAD%21', <ClientLoginPage />);
    expect(screen.getByText('Invalid Portal')).toBeDefined();
    expect(screen.queryByRole('link', { name: /forgot password\?/i })).toBeNull();
  });

  // HC03: the discovery route renders the email form for a valid portal.
  it('HC03: /retailer/forgot-password?w=VALID renders the email form and portal back-link', () => {
    renderAt('/retailer/forgot-password?w=VALID', <RetailerForgotPasswordPage />);
    expect(screen.getByLabelText(/^email/i)).toBeDefined();
    expect(screen.getByRole('button', { name: /send reset link/i })).toBeDefined();
    expect(screen.getByRole('link', { name: /back to sign in/i })).toHaveAttribute(
      'href',
      '/retail/login?w=VALID',
    );
  });

  // HC04 (jsdom structural coverage; authoritative 390px is the browser gate).
  it('HC04: forgot page uses the bounded responsive container pattern', () => {
    const { container } = renderAt('/retailer/forgot-password?w=VALID', <RetailerForgotPasswordPage />);
    expect(container.querySelector('.w-full.max-w-sm')).not.toBeNull();
    expect(container.querySelector('.min-h-screen.px-4')).not.toBeNull();
  });

  // Invalid portal on the forgot page itself: zero recovery POST.
  it('HC04b: forgot page with missing/malformed w shows invalid portal and never posts', () => {
    const { unmount } = renderAt('/retailer/forgot-password', <RetailerForgotPasswordPage />);
    expect(screen.getByText('Invalid Portal')).toBeDefined();
    expect(mockPost).not.toHaveBeenCalled();
    unmount();

    renderAt('/retailer/forgot-password?w=BAD%21', <RetailerForgotPasswordPage />);
    expect(screen.getByText('Invalid Portal')).toBeDefined();
    expect(mockPost).not.toHaveBeenCalled();
  });

  // HC05: client-side validation blocks invalid emails with zero POSTs.
  it('HC05: empty and malformed emails are blocked client-side with zero recovery POST', async () => {
    renderAt('/retailer/forgot-password?w=VALID', <RetailerForgotPasswordPage />);
    await userEvent.click(screen.getByRole('button', { name: /send reset link/i }));
    expect(await screen.findByText(/please enter a valid email address/i)).toBeDefined();

    await userEvent.type(screen.getByLabelText(/^email/i), 'not-an-email');
    await userEvent.click(screen.getByRole('button', { name: /send reset link/i }));
    expect(await screen.findByText(/please enter a valid email address/i)).toBeDefined();
    expect(mockPost).not.toHaveBeenCalled();
  });

  // HC06: a fast double click produces exactly ONE recovery POST. The two
  // clicks are dispatched SYNCHRONOUSLY (fireEvent) so the second lands
  // before React re-renders with isSubmitting — only the in-flight ref guard
  // can suppress it (M9 mutation anchor).
  it('HC06: double click submits exactly one POST /client/auth/forgot-password', async () => {
    mockPost.mockImplementation(() => new Promise((resolve) => setTimeout(() => resolve(NEUTRAL_OK), 50)));
    renderAt('/retailer/forgot-password?w=VALID', <RetailerForgotPasswordPage />);

    await userEvent.type(screen.getByLabelText(/^email/i), 'retailer@example.com');
    const button = screen.getByRole('button', { name: /send reset link/i });
    // Both clicks inside ONE act batch: React cannot re-render and disable
    // the button between them, so only the synchronous ref guard can
    // suppress the duplicate submit.
    act(() => {
      button.click();
      button.click();
    });

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledTimes(1);
    });
    expect(mockPost).toHaveBeenCalledWith(
      '/client/auth/forgot-password',
      { email: 'retailer@example.com', wholesaler_code: 'VALID' },
      expect.objectContaining({ headers: { Authorization: '' }, skipAuthInterceptors: true }),
    );
  });

  // HC07-HC10 (frontend half): the four outcome cases render the SAME fixed
  // neutral copy; the API response is canonical-neutral (backend half is the
  // canonical response equality proof in the backend suite).
  it.each([
    ['HC07', 'existing-verified@example.com'],
    ['HC08', 'no-account@example.com'],
    ['HC09', 'wrong-supplier@example.com'],
    ['HC10', 'unverified@example.com'],
  ])('%s: %s renders the identical fixed neutral result', async (_id, email) => {
    mockPost.mockResolvedValue(NEUTRAL_OK);
    renderAt('/retailer/forgot-password?w=VALID', <RetailerForgotPasswordPage />);

    await userEvent.type(screen.getByLabelText(/^email/i), email);
    await userEvent.click(screen.getByRole('button', { name: /send reset link/i }));

    expect(await screen.findByTestId('forgot-neutral-result')).toBeDefined();
    expect(screen.getByTestId('forgot-neutral-result').textContent).toBe(
      'If an account exists for this email at this supplier, a password reset link has been sent.',
    );
    expect(screen.queryByText(/no account/i)).toBeNull();
    expect(screen.queryByText(/not found/i)).toBeNull();
  });

  // M3: a transport failure renders ONLY fixed neutral copy — never the raw
  // error, response body, or any account-existence signal.
  it('M3: transport failure shows fixed neutral copy and never leaks the raw error', async () => {
    mockPost.mockRejectedValue(new Error('ECONNREFUSED database detail user_exists=true'));
    renderAt('/retailer/forgot-password?w=VALID', <RetailerForgotPasswordPage />);

    await userEvent.type(screen.getByLabelText(/^email/i), 'retailer@example.com');
    await userEvent.click(screen.getByRole('button', { name: /send reset link/i }));

    expect(await screen.findByText('Something went wrong. Please try again.')).toBeDefined();
    expect(screen.queryByText(/ECONNREFUSED/i)).toBeNull();
    expect(screen.queryByText(/user_exists/i)).toBeNull();
    // The call still goes through the existing service route with the
    // interceptor opt-out — no bypass.
    expect(mockPost).toHaveBeenCalledWith(
      '/client/auth/forgot-password',
      expect.objectContaining({ wholesaler_code: 'VALID' }),
      expect.objectContaining({ headers: { Authorization: '' }, skipAuthInterceptors: true }),
    );
  });

  // HC12: w is read from the pre-scrub fragment; the token and w stay out of
  // query/storage/console; the reset POST body carries neither token in URL
  // nor w in the body.
  it('HC12: reset page reads w before scrub, posts body without w, no storage/console leak', async () => {
    mockPost.mockResolvedValue(NEUTRAL_OK);
    const storageSetItem = vi.spyOn(Storage.prototype, 'setItem');
    const consoleSpy = vi.spyOn(console, 'log');

    renderAt('/retailer/reset-password#resetToken=reset-secret-1&w=VALID', <RetailerResetPasswordPage />);
    await waitFor(() => expect(window.location.hash).toBe(''));
    await waitFor(() => expect(window.location.search).toBe(''));

    await userEvent.type(screen.getByLabelText(/new password/i), 'StrongPass123');
    await userEvent.click(screen.getByRole('button', { name: /reset password/i }));

    await waitFor(() => expect(mockPost).toHaveBeenCalledTimes(1));
    expect(mockPost).toHaveBeenCalledWith(
      '/client/auth/reset-password',
      { reset_token: 'reset-secret-1', new_password: 'StrongPass123' }, // pragma: allowlist secret
      expect.objectContaining({ headers: { Authorization: '' }, skipAuthInterceptors: true }),
    );
    // The public w code never enters the POST body or URL.
    expect(mockPost.mock.calls[0][0]).not.toContain('?');
    expect(mockPost.mock.calls[0][0]).not.toContain('w=');
    expect(JSON.stringify(mockPost.mock.calls[0][1])).not.toContain('VALID');
    expect(storageSetItem).not.toHaveBeenCalled();
    for (const call of consoleSpy.mock.calls) {
      expect(String(call)).not.toContain('reset-secret-1');
    }
  });

  // HC13: with a valid w the success CTA returns to the supplier portal,
  // never the wholesaler /login.
  it('HC13: success with w returns CTA to /retail/login?w=VALID and never /login', async () => {
    mockPost.mockResolvedValue(NEUTRAL_OK);
    renderAt('/retailer/reset-password#resetToken=reset-secret-2&w=VALID', <RetailerResetPasswordPage />);
    await waitFor(() => expect(window.location.hash).toBe(''));

    await userEvent.type(screen.getByLabelText(/new password/i), 'StrongPass123');
    await userEvent.click(screen.getByRole('button', { name: /reset password/i }));

    const cta = await screen.findByTestId('reset-success-portal-link');
    expect(cta).toHaveAttribute('href', '/retail/login?w=VALID');
    expect(screen.queryByRole('link', { name: /go to login/i })).toBeNull();
  });

  // HC14: legacy link (no w) with a VALID token still completes the reset;
  // success shows only the neutral guidance — no /login CTA, no portal guess.
  it('HC14: legacy valid-token link completes reset and shows neutral guidance without /login CTA', async () => {
    mockPost.mockResolvedValue(NEUTRAL_OK);
    renderAt('/retailer/reset-password#resetToken=legacy-valid-token', <RetailerResetPasswordPage />);
    await waitFor(() => expect(window.location.hash).toBe(''));

    await userEvent.type(screen.getByLabelText(/new password/i), 'StrongPass123');
    await userEvent.click(screen.getByRole('button', { name: /reset password/i }));

    await waitFor(() => expect(mockPost).toHaveBeenCalledTimes(1));
    const legacy = await screen.findByTestId('reset-success-legacy');
    expect(legacy.textContent).toContain('Your password has been reset successfully.');
    expect(legacy.textContent).toContain('Return to the portal link your supplier provided to sign in.');
    // No wholesaler login CTA and no guessed portal link anywhere.
    expect(screen.queryByRole('link', { name: /go to login/i })).toBeNull();
    expect(screen.queryByTestId('reset-success-portal-link')).toBeNull();
  });

  // HC14b: a malformed w is treated as unusable (legacy guidance), never as
  // a portal to link back to.
  it('HC14b: malformed w behaves like legacy (guidance only, no portal CTA)', async () => {
    mockPost.mockResolvedValue(NEUTRAL_OK);
    renderAt('/retailer/reset-password#resetToken=reset-secret-3&w=BAD%21', <RetailerResetPasswordPage />);
    await waitFor(() => expect(window.location.hash).toBe(''));

    await userEvent.type(screen.getByLabelText(/new password/i), 'StrongPass123');
    await userEvent.click(screen.getByRole('button', { name: /reset password/i }));

    await screen.findByTestId('reset-success-legacy');
    expect(screen.queryByTestId('reset-success-portal-link')).toBeNull();
  });

  // HC15: a forged/expired token keeps the neutral invalid-or-expired page
  // behavior (no raw error, no token-validity signal).
  it('HC15: forged token reset failure shows the neutral invalid/expired message', async () => {
    mockPost.mockRejectedValue({
      response: { status: 401, data: { code: 'TOKEN_INVALID', message: 'raw internal detail' } },
    });
    renderAt('/retailer/reset-password#resetToken=forged-token&w=VALID', <RetailerResetPasswordPage />);
    await waitFor(() => expect(window.location.hash).toBe(''));

    await userEvent.type(screen.getByLabelText(/new password/i), 'StrongPass123');
    await userEvent.click(screen.getByRole('button', { name: /reset password/i }));

    expect(await screen.findByText(/invalid or expired/i)).toBeDefined();
    expect(screen.queryByText(/raw internal detail/i)).toBeNull();
  });

  // HC16 (jsdom structural coverage; authoritative 390px is the browser gate).
  it('HC16: reset page uses the bounded responsive container pattern', () => {
    const { container } = renderAt(
      '/retailer/reset-password#resetToken=x&w=VALID',
      <RetailerResetPasswordPage />,
    );
    expect(container.querySelector('.w-full.max-w-sm')).not.toBeNull();
  });
});
