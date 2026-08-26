import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import { ForgotPasswordPage } from '@/pages/auth/ForgotPasswordPage';
import { LoginPage } from '@/pages/auth/LoginPage';
import { ResetPasswordPage } from '@/pages/auth/ResetPasswordPage';
import { SetupCredentialPage } from '@/pages/auth/SetupCredentialPage';

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

describe('credential lifecycle frontend', () => {
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

  // DC-12A-R3: Tests use fragment tokens (not query)
  it('setup page sends fragment setupToken in JSON body only and clears URL', async () => {
    mockPost.mockResolvedValue({ data: { success: true } });
    const storageSetItem = vi.spyOn(Storage.prototype, 'setItem');

    renderAt('/setup-credential#setupToken=setup-token-123', <SetupCredentialPage />);

    await waitFor(() => {
      expect(window.location.hash).toBe('');
    });

    await userEvent.type(screen.getByLabelText(/new password/i), 'StrongPass123');
    await userEvent.click(screen.getByRole('button', { name: /set password/i }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith('/auth/onboarding/setup-credential', {
        setupToken: 'setup-token-123',
        password: 'StrongPass123', // pragma: allowlist secret
      });
    });
    expect(mockPost.mock.calls[0][0]).not.toContain('?');
    expect(mockPost.mock.calls[0][0]).not.toContain('setupToken');
    expect(storageSetItem).not.toHaveBeenCalled();
    expect(await screen.findByRole('link', { name: /go to login/i })).toHaveAttribute('href', '/login');
  });

  it('setup page rejects query-string token without calling API', async () => {
    renderAt('/setup-credential?setupToken=query-token', <SetupCredentialPage />);

    await waitFor(() => {
      expect(screen.getByText('Invalid Link')).toBeDefined();
    });
    expect(mockPost).not.toHaveBeenCalled();
  });

  it.each(['setupToken', 'setup_token', 'password'])(
    'setup page rejects sensitive query parameter %s without calling API',
    async (paramName) => {
      renderAt(`/setup-credential?${paramName}=query#setupToken=fragment`, <SetupCredentialPage />);

      expect(await screen.findByText('Invalid Link')).toBeDefined();
      expect(window.location.search).toBe('');
      expect(window.location.hash).toBe('');
      expect(mockPost).not.toHaveBeenCalled();
    },
  );

  it('setup page rejects mixed query and fragment setup tokens without calling API', async () => {
    renderAt('/setup-credential?setupToken=query#setupToken=fragment', <SetupCredentialPage />);

    expect(await screen.findByText('Invalid Link')).toBeDefined();
    expect(screen.getByText(/latest link from your email/i)).toBeDefined();
    expect(window.location.search).toBe('');
    expect(window.location.hash).toBe('');
    expect(mockPost).not.toHaveBeenCalled();
  });

  it('forgot password page always shows neutral success copy', async () => {
    mockPost.mockRejectedValue(new Error('network unavailable'));

    renderAt('/forgot-password', <ForgotPasswordPage />);

    await userEvent.type(screen.getByLabelText(/email/i), 'person@example.com');
    await userEvent.click(screen.getByRole('button', { name: /send reset instructions/i }));

    expect(await screen.findByText('If an account exists, reset instructions will be sent.')).toBeInTheDocument();
    expect(mockPost).toHaveBeenCalledWith('/auth/forgot-password', { email: 'person@example.com' },
      // H2-B-R3: public recovery call opts out of auth interceptors.
      expect.objectContaining({ headers: { Authorization: '' }, skipAuthInterceptors: true }));
  });

  // DC-12A-R3: Tests use fragment tokens (not query)
  it('reset page sends fragment resetToken in JSON body only and clears URL', async () => {
    mockPost.mockResolvedValue({ data: { success: true } });
    const storageSetItem = vi.spyOn(Storage.prototype, 'setItem');

    renderAt('/reset-password#resetToken=reset-token-456', <ResetPasswordPage />);

    await waitFor(() => {
      expect(window.location.hash).toBe('');
    });

    await userEvent.type(screen.getByLabelText(/new password/i), 'NewStrongPass123');
    await userEvent.click(screen.getByRole('button', { name: /reset password/i }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith('/auth/reset-password', {
        resetToken: 'reset-token-456',
        newPassword: 'NewStrongPass123', // pragma: allowlist secret
      },
      // H2-B-R3: public recovery call opts out of auth interceptors.
      expect.objectContaining({ headers: { Authorization: '' }, skipAuthInterceptors: true }));
    });
    expect(mockPost.mock.calls[0][0]).not.toContain('?');
    expect(mockPost.mock.calls[0][0]).not.toContain('resetToken');
    expect(storageSetItem).not.toHaveBeenCalled();
    expect(await screen.findByRole('link', { name: /go to login/i })).toHaveAttribute('href', '/login');
  });

  it('reset page rejects query-string token without calling API', async () => {
    renderAt('/reset-password?resetToken=query-token', <ResetPasswordPage />);

    await waitFor(() => {
      expect(screen.getByText('Invalid Link')).toBeDefined();
    });
    expect(mockPost).not.toHaveBeenCalled();
  });

  it.each(['resetToken', 'reset_token', 'token', 'newPassword', 'new_password'])(
    'reset page rejects sensitive query parameter %s without calling API',
    async (paramName) => {
      renderAt(`/reset-password?${paramName}=query#resetToken=fragment`, <ResetPasswordPage />);

      expect(await screen.findByText('Invalid Link')).toBeDefined();
      expect(window.location.search).toBe('');
      expect(window.location.hash).toBe('');
      expect(mockPost).not.toHaveBeenCalled();
    },
  );

  it('reset page rejects mixed query and fragment reset tokens without calling API', async () => {
    renderAt('/reset-password?resetToken=query#resetToken=fragment', <ResetPasswordPage />);

    expect(await screen.findByText('Invalid Link')).toBeDefined();
    expect(screen.getByText(/request a new password reset/i)).toBeDefined();
    expect(window.location.search).toBe('');
    expect(window.location.hash).toBe('');
    expect(mockPost).not.toHaveBeenCalled();
  });

  it('login page links to forgot password', () => {
    renderAt('/login', <LoginPage />);

    expect(screen.getByRole('link', { name: /forgot password/i })).toHaveAttribute(
      'href',
      '/forgot-password',
    );
  });

  it('login page submits lowercase trimmed email', async () => {
    mockPost.mockResolvedValue({
      data: {
        data: {
          access_token: 'identity-access-value',
          refresh_token: 'identity-refresh-value',
          roles: [],
          available_tenants: [],
        },
      },
    });

    renderAt('/login', <LoginPage />);

    await userEvent.type(screen.getByLabelText(/email/i), '  Owner@Example.COM  ');
    await userEvent.type(screen.getByLabelText(/password/i), 'valid-passphrase');
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith('/auth/login', {
        email: 'owner@example.com',
        password: 'valid-passphrase', // pragma: allowlist secret
      });
    });
  });
});
