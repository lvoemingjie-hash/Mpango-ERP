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

  it('setup page sends setupToken in JSON body only and clears it from the visible URL', async () => {
    mockPost.mockResolvedValue({ data: { success: true } });
    const storageSetItem = vi.spyOn(Storage.prototype, 'setItem');

    renderAt('/setup-credential?setupToken=setup-token-123&next=login', <SetupCredentialPage />);

    await waitFor(() => {
      expect(window.location.search).not.toContain('setupToken');
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

  it('forgot password page always shows neutral success copy', async () => {
    mockPost.mockRejectedValue(new Error('network unavailable'));

    renderAt('/forgot-password', <ForgotPasswordPage />);

    await userEvent.type(screen.getByLabelText(/email/i), 'person@example.com');
    await userEvent.click(screen.getByRole('button', { name: /send reset instructions/i }));

    expect(await screen.findByText('If an account exists, reset instructions will be sent.')).toBeInTheDocument();
    expect(mockPost).toHaveBeenCalledWith('/auth/forgot-password', { email: 'person@example.com' });
  });

  it('reset page sends resetToken in JSON body only and clears it from the visible URL', async () => {
    mockPost.mockResolvedValue({ data: { success: true } });
    const storageSetItem = vi.spyOn(Storage.prototype, 'setItem');

    renderAt('/reset-password?resetToken=reset-token-456&source=email', <ResetPasswordPage />);

    await waitFor(() => {
      expect(window.location.search).not.toContain('resetToken');
    });

    await userEvent.type(screen.getByLabelText(/new password/i), 'NewStrongPass123');
    await userEvent.click(screen.getByRole('button', { name: /reset password/i }));

    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith('/auth/reset-password', {
        resetToken: 'reset-token-456',
        newPassword: 'NewStrongPass123', // pragma: allowlist secret
      });
    });
    expect(mockPost.mock.calls[0][0]).not.toContain('?');
    expect(mockPost.mock.calls[0][0]).not.toContain('resetToken');
    expect(storageSetItem).not.toHaveBeenCalled();
    expect(await screen.findByRole('link', { name: /go to login/i })).toHaveAttribute('href', '/login');
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
