/**
 * P12: SupportConsolePage component tests.
 *
 * Verifies:
 *   - Empty reason blocks client-side (button disabled)
 *   - Short reason blocks client-side (button disabled)
 *   - Valid reason enables "Start Session" button
 *   - Backend 400 MISSING_REASON displays safe validation message
 *   - Backend 400 REASON_TOO_SHORT displays safe validation message
 *   - No mutation buttons / no impersonation controls rendered
 *   - P12-C0 limitation notice is removed (C1/C2 implemented)
 *   - Active session renders diagnostics panel and bundle card
 *   - Closed session hides diagnostics and bundle
 *
 * Uses fireEvent (not userEvent) to avoid adding package dependencies.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

// Mock the API module
vi.mock('@/services/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

// Mock auth store -- identity-only super_admin by default
vi.mock('@/stores/authStore', () => ({
  useAuthStore: vi.fn((selector: (s: Record<string, unknown>) => unknown) =>
    selector({
      user: {
        id: 'b2c3d4e5-f6a7-48b8-9c0d-1e2f3a4b5c6d',
        roles: ['super_admin'],
        tenant_id: null,
        tenant_schema: null,
      },
      accessToken: 'test-token',
    }),
  ),
}));

import { SupportConsolePage } from '@/pages/platform/SupportConsolePage';
import { api } from '@/services/api';

const mockPost = vi.mocked(api.post);
const mockGet = vi.mocked(api.get);

function renderPage() {
  return render(
    <MemoryRouter>
      <SupportConsolePage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('SupportConsolePage', () => {
  it('SP-001: renders reason textarea and category select', () => {
    renderPage();
    expect(screen.getByTestId('reason-input')).toBeInTheDocument();
    expect(screen.getByTestId('category-select')).toBeInTheDocument();
  });

  it('SP-002: empty reason disables Start Session button', () => {
    renderPage();
    const btn = screen.getByTestId('start-session-btn');
    expect(btn).toBeDisabled();
  });

  it('SP-003: short reason disables Start Session button', () => {
    renderPage();
    const input = screen.getByTestId('reason-input');
    fireEvent.change(input, { target: { value: 'short' } });
    const btn = screen.getByTestId('start-session-btn');
    expect(btn).toBeDisabled();
  });

  it('SP-004: valid reason enables Start Session button', () => {
    renderPage();
    const input = screen.getByTestId('reason-input');
    fireEvent.change(input, { target: { value: 'Tenant login failure triage -- users cannot authenticate' } });
    const btn = screen.getByTestId('start-session-btn');
    expect(btn).not.toBeDisabled();
  });

  it('SP-005: short reason shows validation error message', () => {
    renderPage();
    const input = screen.getByTestId('reason-input');
    fireEvent.change(input, { target: { value: 'short' } });
    const error = screen.getByTestId('reason-validation-error');
    expect(error).toBeInTheDocument();
    expect(error.textContent).toContain('at least 10 characters');
  });

  it('SP-006: backend 400 MISSING_REASON displays safe validation message', async () => {
    mockPost.mockRejectedValueOnce({
      response: {
        data: {
          detail: { code: 'MISSING_REASON', message: 'Support reason is required' },
        },
      },
    });
    renderPage();
    const input = screen.getByTestId('reason-input');
    fireEvent.change(input, { target: { value: 'Valid reason text for testing this' } });
    const btn = screen.getByTestId('start-session-btn');
    fireEvent.click(btn);
    await waitFor(() => {
      const errorDisplay = screen.getByTestId('error-display');
      expect(errorDisplay.textContent).toContain('required');
    });
  });

  it('SP-007: backend 400 REASON_TOO_SHORT displays safe validation message', async () => {
    mockPost.mockRejectedValueOnce({
      response: {
        data: {
          detail: { code: 'REASON_TOO_SHORT', message: 'Support reason must be at least 10 characters, got 5' },
        },
      },
    });
    renderPage();
    const input = screen.getByTestId('reason-input');
    fireEvent.change(input, { target: { value: 'Valid reason text for testing this' } });
    const btn = screen.getByTestId('start-session-btn');
    fireEvent.click(btn);
    await waitFor(() => {
      const errorDisplay = screen.getByTestId('error-display');
      expect(errorDisplay.textContent).toContain('at least 10 characters');
    });
  });

  it('SP-008: no impersonation or mutation controls rendered', () => {
    renderPage();
    expect(screen.queryByText(/impersonat/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/edit tenant/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/delete/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/modify/i)).not.toBeInTheDocument();
  });

  it('SP-009: P12-C0 limitation notice is removed (C1/C2 implemented)', () => {
    renderPage();
    expect(screen.queryByText(/wiring\/form shell only/i)).not.toBeInTheDocument();
  });

  it('SP-010: active session renders diagnostics panel', async () => {
    mockPost.mockResolvedValueOnce({
      data: {
        session_id: 'a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d',
        status: 'active',
        reason: 'Test reason',
        category: 'general',
        started_at: '2026-06-11T10:00:00Z',
        bundle_count: 0,
        expires_at: '2026-06-11T11:00:00Z',
      },
    });
    mockGet.mockResolvedValueOnce({ data: [] });
    renderPage();
    const input = screen.getByTestId('reason-input');
    fireEvent.change(input, { target: { value: 'Valid reason text for testing this' } });
    const btn = screen.getByTestId('start-session-btn');
    fireEvent.click(btn);
    await waitFor(() => {
      expect(screen.getByTestId('diagnostics-panel')).toBeInTheDocument();
    });
  });

  it('SP-011: active session renders bundle card', async () => {
    mockPost.mockResolvedValueOnce({
      data: {
        session_id: 'a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d',
        status: 'active',
        reason: 'Test reason',
        category: 'general',
        started_at: '2026-06-11T10:00:00Z',
        bundle_count: 0,
        expires_at: '2026-06-11T11:00:00Z',
      },
    });
    mockGet.mockResolvedValueOnce({ data: [] });
    renderPage();
    const input = screen.getByTestId('reason-input');
    fireEvent.change(input, { target: { value: 'Valid reason text for testing this' } });
    const btn = screen.getByTestId('start-session-btn');
    fireEvent.click(btn);
    await waitFor(() => {
      expect(screen.getByTestId('bundle-card')).toBeInTheDocument();
    });
  });

  it('SP-012: closed session does not render diagnostics or bundle', async () => {
    // Start session then close it
    mockPost
      .mockResolvedValueOnce({
        data: {
          session_id: 'a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d',
          status: 'active',
          reason: 'Test reason',
          category: 'general',
          started_at: '2026-06-11T10:00:00Z',
          bundle_count: 0,
          expires_at: '2026-06-11T11:00:00Z',
        },
      })
      .mockResolvedValueOnce({
        data: {
          session_id: 'a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d',
          status: 'closed',
          reason: 'Test reason',
          category: 'general',
          started_at: '2026-06-11T10:00:00Z',
          bundle_count: 0,
          closed_at: '2026-06-11T10:05:00Z',
        },
      });
    mockGet.mockResolvedValueOnce({ data: [] });
    renderPage();
    const input = screen.getByTestId('reason-input');
    fireEvent.change(input, { target: { value: 'Valid reason text for testing this' } });
    const startBtn = screen.getByTestId('start-session-btn');
    fireEvent.click(startBtn);
    await waitFor(() => {
      expect(screen.getByTestId('diagnostics-panel')).toBeInTheDocument();
    });
    const closeBtn = screen.getByTestId('close-session-btn');
    fireEvent.click(closeBtn);
    await waitFor(() => {
      expect(screen.queryByTestId('diagnostics-panel')).not.toBeInTheDocument();
      expect(screen.queryByTestId('bundle-card')).not.toBeInTheDocument();
    });
  });

  it('SP-013: Diagnostics and Bundle section headings visible in active session', async () => {
    mockPost.mockResolvedValueOnce({
      data: {
        session_id: 'a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d',
        status: 'active',
        reason: 'Test reason',
        category: 'general',
        started_at: '2026-06-11T10:00:00Z',
        bundle_count: 0,
        expires_at: '2026-06-11T11:00:00Z',
      },
    });
    mockGet.mockResolvedValueOnce({ data: [] });
    renderPage();
    const input = screen.getByTestId('reason-input');
    fireEvent.change(input, { target: { value: 'Valid reason text for testing this' } });
    const btn = screen.getByTestId('start-session-btn');
    fireEvent.click(btn);
    await waitFor(() => {
      expect(screen.getByText('Diagnostics')).toBeInTheDocument();
      expect(screen.getByText('Support Bundle')).toBeInTheDocument();
    });
  });

  it('SP-014: closed session shows bundle_count clearly', async () => {
    mockPost
      .mockResolvedValueOnce({
        data: {
          session_id: 'a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d',
          status: 'active',
          reason: 'Test reason',
          category: 'general',
          started_at: '2026-06-11T10:00:00Z',
          bundle_count: 0,
          expires_at: '2026-06-11T11:00:00Z',
        },
      })
      .mockResolvedValueOnce({
        data: {
          session_id: 'a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d',
          status: 'closed',
          reason: 'Test reason',
          category: 'general',
          started_at: '2026-06-11T10:00:00Z',
          bundle_count: 2,
          closed_at: '2026-06-11T10:05:00Z',
        },
      });
    mockGet.mockResolvedValueOnce({ data: [] });
    renderPage();
    const input = screen.getByTestId('reason-input');
    fireEvent.change(input, { target: { value: 'Valid reason text for testing this' } });
    const startBtn = screen.getByTestId('start-session-btn');
    fireEvent.click(startBtn);
    await waitFor(() => {
      expect(screen.getByTestId('diagnostics-panel')).toBeInTheDocument();
    });
    const closeBtn = screen.getByTestId('close-session-btn');
    fireEvent.click(closeBtn);
    await waitFor(() => {
      expect(screen.getByText(/Bundles generated: 2/)).toBeInTheDocument();
    });
  });
});
