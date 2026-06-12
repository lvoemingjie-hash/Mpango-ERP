/**
 * P12-C2: SupportBundleCard component tests.
 *
 * Verifies:
 *   - Bundle type select has all 3 options (full/technical/summary)
 *   - Default bundle type is full
 *   - Generate calls createBundle API with correct parameters
 *   - Loading state during generation
 *   - Bundle metadata display after generation
 *   - Diagnostics count and grouped display
 *   - Redaction shown as Yes
 *   - Error on generation failure
 *   - Error clears on successful retry
 *   - Different bundle types sent correctly
 *   - No download/export buttons
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import type { SupportBundle } from '@/types/support';

// Mock the API module
vi.mock('@/services/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

import { api } from '@/services/api';
import { SupportBundleCard } from '@/components/platform/SupportBundleCard';

const mockPost = vi.mocked(api.post);

const sessionId = 'a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d';

const mockBundle: SupportBundle = {
  bundle_id: 'f3a4b5c6-d7e8-4f9a-0b1c-2d3e4f5a6b7c',
  session_id: sessionId,
  actor_id: null,
  tenant_id: null,
  correlation_id: 'corr-001',
  generated_at: '2026-06-11T10:02:00Z',
  diagnostics: [
    {
      item_id: 'd1e2f3a4-b5c6-4d7e-8f9a-0b1c2d3e4f5a',
      bundle_id: 'f3a4b5c6-d7e8-4f9a-0b1c-2d3e4f5a6b7c',
      category: 'health_summary',
      label: 'Tenant Health',
      value: { status: 'healthy' },
      source_status: 'available',
      collected_at: '2026-06-11T10:02:00Z',
    },
  ],
  redaction_applied: true,
  bundle_type: 'full',
};

function renderCard() {
  return render(<SupportBundleCard sessionId={sessionId} />);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('SupportBundleCard', () => {
  it('SB-001: renders bundle type select with all three options', () => {
    renderCard();
    const select = screen.getByTestId('bundle-type-select');
    expect(select).toBeInTheDocument();
    expect(screen.getByText('Full')).toBeInTheDocument();
    expect(screen.getByText('Technical')).toBeInTheDocument();
    expect(screen.getByText('Summary')).toBeInTheDocument();
  });

  it('SB-002: default bundle type is full', () => {
    renderCard();
    const select = screen.getByTestId('bundle-type-select') as HTMLSelectElement;
    expect(select.value).toBe('full');
  });

  it('SB-003: generate calls createBundle API', async () => {
    mockPost.mockResolvedValueOnce({ data: mockBundle });
    renderCard();
    const btn = screen.getByTestId('generate-bundle-btn');
    fireEvent.click(btn);
    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith(
        `/platform/p12/sessions/${sessionId}/bundles`,
        { bundle_type: 'full' },
      );
    });
  });

  it('SB-004: loading state during generation', async () => {
    // Keep post hanging to show loading
    mockPost.mockReturnValue(new Promise(() => {}));
    renderCard();
    const btn = screen.getByTestId('generate-bundle-btn');
    fireEvent.click(btn);
    await waitFor(() => {
      expect(btn).toHaveTextContent('Generating...');
      expect(btn).toBeDisabled();
    });
  });

  it('SB-005: displays bundle metadata after generation', async () => {
    mockPost.mockResolvedValueOnce({ data: mockBundle });
    renderCard();
    const btn = screen.getByTestId('generate-bundle-btn');
    fireEvent.click(btn);
    await waitFor(() => {
      expect(screen.getByTestId('bundle-metadata')).toBeInTheDocument();
    });
    expect(screen.getByText(/f3a4b5c6/)).toBeInTheDocument();
    expect(screen.getByText('full')).toBeInTheDocument();
  });

  it('SB-006: displays diagnostics count in bundle', async () => {
    mockPost.mockResolvedValueOnce({ data: mockBundle });
    renderCard();
    const btn = screen.getByTestId('generate-bundle-btn');
    fireEvent.click(btn);
    await waitFor(() => {
      expect(screen.getByTestId('bundle-diagnostics-count')).toBeInTheDocument();
    });
    expect(screen.getByTestId('bundle-diagnostics-count').textContent).toContain('1 item');
  });

  it('SB-007: displays bundle diagnostics grouped by category', async () => {
    mockPost.mockResolvedValueOnce({ data: mockBundle });
    renderCard();
    const btn = screen.getByTestId('generate-bundle-btn');
    fireEvent.click(btn);
    await waitFor(() => {
      expect(screen.getByTestId('bundle-diagnostics')).toBeInTheDocument();
    });
    expect(screen.getByText('Health Summary')).toBeInTheDocument();
    expect(screen.getByText('Tenant Health')).toBeInTheDocument();
  });

  it('SB-008: shows redaction_applied as Yes', async () => {
    mockPost.mockResolvedValueOnce({ data: mockBundle });
    renderCard();
    const btn = screen.getByTestId('generate-bundle-btn');
    fireEvent.click(btn);
    await waitFor(() => {
      expect(screen.getByText('Yes')).toBeInTheDocument();
    });
  });

  it('SB-009: displays error on bundle generation failure', async () => {
    mockPost.mockRejectedValueOnce(new Error('Server error'));
    renderCard();
    const btn = screen.getByTestId('generate-bundle-btn');
    fireEvent.click(btn);
    await waitFor(() => {
      expect(screen.getByTestId('bundle-error')).toBeInTheDocument();
    });
    expect(screen.getByText('Failed to generate support bundle.')).toBeInTheDocument();
  });

  it('SB-010: error clears on successful retry', async () => {
    mockPost
      .mockRejectedValueOnce(new Error('Server error'))
      .mockResolvedValueOnce({ data: mockBundle });
    renderCard();
    const btn = screen.getByTestId('generate-bundle-btn');
    fireEvent.click(btn);
    await waitFor(() => {
      expect(screen.getByTestId('bundle-error')).toBeInTheDocument();
    });
    fireEvent.click(btn);
    await waitFor(() => {
      expect(screen.queryByTestId('bundle-error')).not.toBeInTheDocument();
      expect(screen.getByTestId('bundle-metadata')).toBeInTheDocument();
    });
  });

  it('SB-011: technical bundle type sent correctly', async () => {
    mockPost.mockResolvedValueOnce({ data: { ...mockBundle, bundle_type: 'technical' } });
    renderCard();
    const select = screen.getByTestId('bundle-type-select');
    fireEvent.change(select, { target: { value: 'technical' } });
    const btn = screen.getByTestId('generate-bundle-btn');
    fireEvent.click(btn);
    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith(
        `/platform/p12/sessions/${sessionId}/bundles`,
        { bundle_type: 'technical' },
      );
    });
  });

  it('SB-012: summary bundle type sent correctly', async () => {
    mockPost.mockResolvedValueOnce({ data: { ...mockBundle, bundle_type: 'summary' } });
    renderCard();
    const select = screen.getByTestId('bundle-type-select');
    fireEvent.change(select, { target: { value: 'summary' } });
    const btn = screen.getByTestId('generate-bundle-btn');
    fireEvent.click(btn);
    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith(
        `/platform/p12/sessions/${sessionId}/bundles`,
        { bundle_type: 'summary' },
      );
    });
  });

  it('SB-013: empty diagnostics shows 0 items', async () => {
    const emptyBundle = { ...mockBundle, diagnostics: [] };
    mockPost.mockResolvedValueOnce({ data: emptyBundle });
    renderCard();
    const btn = screen.getByTestId('generate-bundle-btn');
    fireEvent.click(btn);
    await waitFor(() => {
      expect(screen.getByTestId('bundle-diagnostics-count')).toBeInTheDocument();
    });
    expect(screen.getByTestId('bundle-diagnostics-count').textContent).toContain('0 items');
    expect(screen.queryByTestId('bundle-diagnostics')).not.toBeInTheDocument();
  });

  it('TF-002: no download/export buttons', async () => {
    mockPost.mockResolvedValueOnce({ data: mockBundle });
    renderCard();
    const btn = screen.getByTestId('generate-bundle-btn');
    fireEvent.click(btn);
    await waitFor(() => {
      expect(screen.getByTestId('bundle-metadata')).toBeInTheDocument();
    });
    expect(screen.queryByText(/download/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/export/i)).not.toBeInTheDocument();
  });
});
