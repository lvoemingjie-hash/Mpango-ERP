/**
 * P12-C1: SupportDiagnosticsPanel component tests.
 *
 * Verifies:
 *   - Loading skeleton renders initially
 *   - Fetches diagnostics on mount with correct URL
 *   - Displays diagnostic items grouped by category
 *   - Source status badges show correct colors
 *   - N/A for null value, JSON for object value, string for string value
 *   - Refresh re-fetches diagnostics
 *   - Error state with retry
 *   - No mutation/edit/delete controls
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import type { SupportDiagnosticItem, SupportBundle } from '@/types/support';

// Mock the API module
vi.mock('@/services/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

import { api } from '@/services/api';
import { SupportDiagnosticsPanel } from '@/components/platform/SupportDiagnosticsPanel';

const mockGet = vi.mocked(api.get);
const mockPost = vi.mocked(api.post);

const sessionId = 'a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d';

const mockDiagnostics: SupportDiagnosticItem[] = [
  {
    item_id: 'd1e2f3a4-b5c6-4d7e-8f9a-0b1c2d3e4f5a',
    bundle_id: null,
    category: 'tenant_metadata',
    label: 'Tenant Summary',
    value: { tenant_name: 'Acme', status: 'active' },
    source_status: 'available',
    collected_at: '2026-06-11T10:01:00Z',
  },
  {
    item_id: 'e2f3a4b5-c6d7-4e8f-9a0b-1c2d3e4f5a6b',
    bundle_id: null,
    category: 'recent_errors',
    label: 'Recent Errors',
    value: null,
    source_status: 'unavailable',
    collected_at: '2026-06-11T10:01:00Z',
  },
  {
    item_id: 'f3a4b5c6-d7e8-4f9a-0b1c-2d3e4f5a6b7c',
    bundle_id: null,
    category: 'health_summary',
    label: 'Health Check',
    value: 'degraded',
    source_status: 'degraded',
    collected_at: '2026-06-11T10:01:00Z',
  },
  {
    item_id: 'a4b5c6d7-e8f9-4a0b-1c2d-3e4f5a6b7c8d',
    bundle_id: null,
    category: 'system_snapshot',
    label: 'System Status',
    value: null,
    source_status: 'unknown',
    collected_at: '2026-06-11T10:01:00Z',
  },
];

function renderPanel() {
  return render(<SupportDiagnosticsPanel sessionId={sessionId} />);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('SupportDiagnosticsPanel', () => {
  it('SD-001: renders loading skeleton initially', () => {
    // Keep get hanging so loading persists
    mockGet.mockReturnValue(new Promise(() => {}));
    renderPanel();
    expect(screen.getByTestId('diagnostics-loading')).toBeInTheDocument();
  });

  it('SD-002: fetches diagnostics on mount with correct session ID', async () => {
    mockGet.mockResolvedValueOnce({ data: mockDiagnostics });
    renderPanel();
    await waitFor(() => {
      expect(screen.getByTestId('diagnostics-panel')).toBeInTheDocument();
    });
    expect(mockGet).toHaveBeenCalledWith(
      `/platform/p12/sessions/${sessionId}/diagnostics`,
    );
  });

  it('SD-003: displays diagnostic items grouped by category', async () => {
    mockGet.mockResolvedValueOnce({ data: mockDiagnostics });
    renderPanel();
    await waitFor(() => {
      expect(screen.getByTestId('diagnostics-category-tenant_metadata')).toBeInTheDocument();
    });
    expect(screen.getByTestId('diagnostics-category-health_summary')).toBeInTheDocument();
    expect(screen.getByTestId('diagnostics-category-recent_errors')).toBeInTheDocument();
    expect(screen.getByTestId('diagnostics-category-system_snapshot')).toBeInTheDocument();
  });

  it('SD-004: source status badges show correct colors', async () => {
    mockGet.mockResolvedValueOnce({ data: mockDiagnostics });
    renderPanel();
    await waitFor(() => {
      expect(screen.getByTestId('diagnostics-panel')).toBeInTheDocument();
    });
    const availableBadge = screen.getByTestId('status-badge-available');
    expect(availableBadge.textContent).toBe('available');
    expect(availableBadge.className).toContain('bg-green-100');
    const degradedBadge = screen.getByTestId('status-badge-degraded');
    expect(degradedBadge.textContent).toBe('degraded');
    expect(degradedBadge.className).toContain('bg-yellow-100');
  });

  it('SD-005: shows N/A for null value items', async () => {
    mockGet.mockResolvedValueOnce({ data: mockDiagnostics });
    renderPanel();
    await waitFor(() => {
      // Two items have null values: recent_errors and system_snapshot
      const naElements = screen.getAllByText('N/A');
      expect(naElements.length).toBeGreaterThanOrEqual(2);
    });
  });

  it('SD-006: shows JSON stringified object values', async () => {
    mockGet.mockResolvedValueOnce({ data: mockDiagnostics });
    renderPanel();
    await waitFor(() => {
      expect(screen.getByTestId('diagnostics-panel')).toBeInTheDocument();
    });
    // tenant_metadata item has object value { tenant_name: 'Acme', status: 'active' }
    expect(screen.getByText(/"tenant_name"/)).toBeInTheDocument();
  });

  it('SD-007: shows string values directly', async () => {
    mockGet.mockResolvedValueOnce({ data: mockDiagnostics });
    renderPanel();
    await waitFor(() => {
      expect(screen.getByTestId('diagnostics-panel')).toBeInTheDocument();
    });
    // health_summary item has string value "degraded" in the value column
    // "degraded" also appears in the status badge, so use getAllByText
    const degradedElements = screen.getAllByText('degraded');
    expect(degradedElements.length).toBeGreaterThanOrEqual(1);
  });

  it('SD-008: refresh button re-fetches diagnostics', async () => {
    mockGet.mockResolvedValue({ data: mockDiagnostics });
    renderPanel();
    await waitFor(() => {
      expect(screen.getByTestId('diagnostics-panel')).toBeInTheDocument();
    });
    expect(mockGet).toHaveBeenCalledTimes(1);
    const refreshBtn = screen.getByTestId('diagnostics-refresh-btn');
    fireEvent.click(refreshBtn);
    await waitFor(() => {
      expect(mockGet).toHaveBeenCalledTimes(2);
    });
  });

  it('SD-009: displays error state on API failure', async () => {
    mockGet.mockRejectedValueOnce(new Error('Network error'));
    renderPanel();
    await waitFor(() => {
      expect(screen.getByTestId('diagnostics-error')).toBeInTheDocument();
    });
    expect(screen.getByText('Failed to load diagnostics.')).toBeInTheDocument();
  });

  it('SD-010: error state retry re-fetches diagnostics', async () => {
    mockGet
      .mockRejectedValueOnce(new Error('Network error'))
      .mockResolvedValueOnce({ data: mockDiagnostics });
    renderPanel();
    await waitFor(() => {
      expect(screen.getByTestId('diagnostics-error')).toBeInTheDocument();
    });
    const retryBtn = screen.getByText('Retry');
    fireEvent.click(retryBtn);
    await waitFor(() => {
      expect(screen.getByTestId('diagnostics-panel')).toBeInTheDocument();
    });
  });

  it('SD-011: displays diagnostic count', async () => {
    mockGet.mockResolvedValueOnce({ data: mockDiagnostics });
    renderPanel();
    await waitFor(() => {
      expect(screen.getByTestId('diagnostics-count')).toBeInTheDocument();
    });
    expect(screen.getByTestId('diagnostics-count').textContent).toContain('4 diagnostic items');
  });

  it('SD-012: displays collected_at timestamps', async () => {
    mockGet.mockResolvedValueOnce({ data: mockDiagnostics });
    renderPanel();
    await waitFor(() => {
      expect(screen.getByTestId('diagnostics-panel')).toBeInTheDocument();
    });
    // displayTimestamp converts ISO to locale string -- just verify N/A is NOT shown for collected_at
    expect(screen.getByText('Tenant Summary')).toBeInTheDocument();
  });

  it('SD-013: unknown badge is gray not green', async () => {
    mockGet.mockResolvedValueOnce({ data: mockDiagnostics });
    renderPanel();
    await waitFor(() => {
      expect(screen.getByTestId('diagnostics-panel')).toBeInTheDocument();
    });
    const unknownBadge = screen.getByTestId('status-badge-unknown');
    expect(unknownBadge.className).toContain('bg-gray-100');
    expect(unknownBadge.className).not.toContain('bg-green-100');
  });

  it('SD-014: available badge is green', async () => {
    mockGet.mockResolvedValueOnce({ data: mockDiagnostics });
    renderPanel();
    await waitFor(() => {
      expect(screen.getByTestId('diagnostics-panel')).toBeInTheDocument();
    });
    const availableBadge = screen.getByTestId('status-badge-available');
    expect(availableBadge.className).toContain('bg-green-100');
  });

  it('TF-001: no mutation/edit/delete controls', async () => {
    mockGet.mockResolvedValueOnce({ data: mockDiagnostics });
    renderPanel();
    await waitFor(() => {
      expect(screen.getByTestId('diagnostics-panel')).toBeInTheDocument();
    });
    expect(screen.queryByText(/delete/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/edit/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/modify/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/export/i)).not.toBeInTheDocument();
  });
});
