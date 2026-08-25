import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import { RetailerSetupCredentialPage } from '@/pages/retailer/RetailerSetupCredentialPage';
import { RetailerResetPasswordPage } from '@/pages/retailer/RetailerResetPasswordPage';

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

describe('DC-12R1-S1 retailer credential pages', () => {
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

  // Fragment token -> JSON body only, URL scrubbed, no storage.
  it('setup page sends fragment setupToken in JSON body only and clears URL', async () => {
    mockPost.mockResolvedValue({ data: { success: true } });
    const storageSetItem = vi.spyOn(Storage.prototype, 'setItem');

    renderAt('/retailer/setup-credential#setupToken=setup-token-123', <RetailerSetupCredentialPage />);

    await waitFor(() => {
      expect(window.location.hash).toBe('');
    });

    await userEvent.type(screen.getByLabelText(/^password/i), 'StrongPass123');
    await userEvent.click(screen.getByRole('button', { name: /set password/i }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledTimes(1);
    });
    // JSON body only — snake_case field names, token in body not URL.
    expect(mockPost).toHaveBeenCalledWith('/retailers/setup-credential', {
      setup_token: 'setup-token-123',
      new_password: 'StrongPass123', // pragma: allowlist secret
    });
    expect(mockPost.mock.calls[0][0]).not.toContain('?');
    expect(mockPost.mock.calls[0][0]).not.toContain('setupToken');
    expect(storageSetItem).not.toHaveBeenCalled();
    expect(await screen.findByRole('link', { name: /go to login/i })).toHaveAttribute('href', '/login');
  });

  it('reset page sends fragment resetToken in JSON body only and clears URL', async () => {
    mockPost.mockResolvedValue({ data: { success: true } });
    const storageSetItem = vi.spyOn(Storage.prototype, 'setItem');

    renderAt('/retailer/reset-password#resetToken=reset-token-456', <RetailerResetPasswordPage />);

    await waitFor(() => {
      expect(window.location.hash).toBe('');
    });

    await userEvent.type(screen.getByLabelText(/new password/i), 'StrongPass123');
    await userEvent.click(screen.getByRole('button', { name: /reset password/i }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith('/client/auth/reset-password', {
        reset_token: 'reset-token-456',
        new_password: 'StrongPass123', // pragma: allowlist secret
      },
      // H2-B-R3: public recovery call opts out of auth interceptors.
      expect.objectContaining({ headers: { Authorization: '' }, skipAuthInterceptors: true }));
    });
    expect(mockPost.mock.calls[0][0]).not.toContain('?');
    expect(storageSetItem).not.toHaveBeenCalled();
  });

  // Query-only token -> rejected, zero API calls.
  it('setup page rejects query-string token without calling API', async () => {
    renderAt('/retailer/setup-credential?setupToken=query-token', <RetailerSetupCredentialPage />);

    await waitFor(() => {
      expect(screen.getByText('Invalid Link')).toBeDefined();
    });
    expect(mockPost).not.toHaveBeenCalled();
  });

  it('reset page rejects query-string token without calling API', async () => {
    renderAt('/retailer/reset-password?resetToken=query-token', <RetailerResetPasswordPage />);

    await waitFor(() => {
      expect(screen.getByText('Invalid Link')).toBeDefined();
    });
    expect(mockPost).not.toHaveBeenCalled();
  });

  // Mixed query + fragment -> rejected (sensitive query takes precedence), zero API calls.
  it('setup page rejects mixed query+fragment without calling API', async () => {
    renderAt(
      '/retailer/setup-credential?token=leak#setupToken=frag-token',
      <RetailerSetupCredentialPage />,
    );

    await waitFor(() => {
      expect(screen.getByText('Invalid Link')).toBeDefined();
    });
    expect(mockPost).not.toHaveBeenCalled();
  });

  it('reset page rejects mixed query+fragment without calling API', async () => {
    renderAt(
      '/retailer/reset-password?reset_token=leak#resetToken=frag-token',
      <RetailerResetPasswordPage />,
    );

    await waitFor(() => {
      expect(screen.getByText('Invalid Link')).toBeDefined();
    });
    expect(mockPost).not.toHaveBeenCalled();
  });

  // Missing token -> controlled invalid-link state, zero API calls.
  it('setup page with no token shows invalid-link state without calling API', async () => {
    renderAt('/retailer/setup-credential', <RetailerSetupCredentialPage />);

    await waitFor(() => {
      expect(screen.getByText('Invalid Link')).toBeDefined();
    });
    expect(mockPost).not.toHaveBeenCalled();
  });

  it('reset page with no token shows invalid-link state without calling API', async () => {
    renderAt('/retailer/reset-password', <RetailerResetPasswordPage />);

    await waitFor(() => {
      expect(screen.getByText('Invalid Link')).toBeDefined();
    });
    expect(mockPost).not.toHaveBeenCalled();
  });

  // Neutral server error path: never reveals token validity, no storage.
  it('setup page surfaces neutral error and never stores token on failure', async () => {
    mockPost.mockRejectedValue(new Error('invalid'));
    const storageSetItem = vi.spyOn(Storage.prototype, 'setItem');

    renderAt('/retailer/setup-credential#setupToken=fail-token', <RetailerSetupCredentialPage />);
    await waitFor(() => expect(window.location.hash).toBe(''));

    await userEvent.type(screen.getByLabelText(/^password/i), 'StrongPass123');
    await userEvent.click(screen.getByRole('button', { name: /set password/i }));

    await waitFor(() => {
      expect(screen.getByText(/invalid or expired/i)).toBeDefined();
    });
    expect(storageSetItem).not.toHaveBeenCalled();
  });
});
