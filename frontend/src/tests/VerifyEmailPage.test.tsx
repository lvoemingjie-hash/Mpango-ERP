import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { VerifyEmailPage } from '@/pages/auth/VerifyEmailPage';

// Mock authService
vi.mock('@/services/authService', () => ({
  authService: {
    verifyEmail: vi.fn(),
  },
}));

import { authService } from '@/services/authService';

function renderWithHash(hash: string, search = '') {
  const url = `/verify-email${search}${hash}`;
  window.history.replaceState({}, '', url);
  return render(
    <MemoryRouter>
      <VerifyEmailPage />
    </MemoryRouter>
  );
}

describe('VerifyEmailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    window.history.replaceState({}, '', '/');
  });

  it('renders processing state initially with fragment token', async () => {
    vi.mocked(authService.verifyEmail).mockResolvedValueOnce({} as never);
    renderWithHash('#token=will-succeed');
    // Processing state is shown while the API call is in flight
    expect(screen.getByText('Verifying your email...')).toBeDefined();
  });

  it('shows success after verifyEmail resolves with fragment token', async () => {
    vi.mocked(authService.verifyEmail).mockResolvedValueOnce({} as never);
    renderWithHash('#token=valid-token');
    await waitFor(() => {
      expect(screen.getByText('Email Verified!')).toBeDefined();
    });
    expect(authService.verifyEmail).toHaveBeenCalledWith({ token: 'valid-token' });
  });

  it('shows no-token state when no fragment and no query', async () => {
    renderWithHash('');
    expect(await screen.findByText(/No verification token was found/i)).toBeDefined();
    expect(screen.queryByText('Verifying your email...')).toBeNull();
    expect(authService.verifyEmail).not.toHaveBeenCalled();
  });

  it('shows invalid state when verifyEmail rejects', async () => {
    vi.mocked(authService.verifyEmail).mockRejectedValueOnce(new Error('invalid') as never);
    renderWithHash('#token=bad-token');
    await waitFor(() => {
      expect(screen.getByText('Verification Failed')).toBeDefined();
    });
  });

  it('rejects query-string tokens without calling API', async () => {
    renderWithHash('', '?token=query-token');
    await waitFor(() => {
      expect(screen.getByText('Invalid Link')).toBeDefined();
    });
    expect(authService.verifyEmail).not.toHaveBeenCalled();
  });

  it.each(['token', 'verificationToken', 'verification_token'])(
    'rejects sensitive query parameter %s without calling API',
    async (paramName) => {
      renderWithHash('#token=fragment-token', `?${paramName}=query-token`);

      expect(await screen.findByText('Invalid Link')).toBeDefined();
      expect(window.location.search).toBe('');
      expect(window.location.hash).toBe('');
      expect(authService.verifyEmail).not.toHaveBeenCalled();
    },
  );

  it('rejects mixed query and fragment verification tokens without calling API', async () => {
    renderWithHash('#token=fragment', '?token=query');

    expect(await screen.findByText('Invalid Link')).toBeDefined();
    expect(screen.getByText(/latest link from your signup email/i)).toBeDefined();
    expect(window.location.search).toBe('');
    expect(window.location.hash).toBe('');
    expect(authService.verifyEmail).not.toHaveBeenCalled();
  });

  it('scrubs URL after reading fragment token', async () => {
    vi.mocked(authService.verifyEmail).mockResolvedValueOnce({} as never);
    renderWithHash('#token=scrub-test');
    await waitFor(() => {
      expect(screen.getByText('Email Verified!')).toBeDefined();
    });
    expect(window.location.hash).toBe('');
    expect(window.location.search).toBe('');
  });

  it('does not store token in localStorage or sessionStorage', async () => {
    vi.mocked(authService.verifyEmail).mockResolvedValueOnce({} as never);
    renderWithHash('#token=storage-test');
    await waitFor(() => {
      expect(screen.getByText('Email Verified!')).toBeDefined();
    });
    expect(localStorage.getItem('token')).toBeNull();
    expect(sessionStorage.getItem('token')).toBeNull();
  });
});
