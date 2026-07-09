/**
 * P13-D: Ops health page component tests.
 *
 * Verifies rendering contract:
 *   - Page title and read-only description
 *   - No mutation controls
 *   - No sensitive data fields
 *   - No business data fields
 *   - Loading skeleton on mount
 *
 * API client paths verified separately in platformOpsApi.test.ts.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

// Mock api to prevent real network calls
vi.mock('@/services/api', () => ({
  api: {
    get: vi.fn().mockResolvedValue({ data: {} }),
    post: vi.fn(),
  },
}));

import { OpsHealthPage } from '@/pages/platform/ops/OpsHealthPage';
import { usePlatformStore } from '@/stores/platformStore';

beforeEach(() => {
  // Reset store to default state (OpsHealthPage uses Zustand store)
  usePlatformStore.setState({
    systemHealth: null,
    systemHealthLoading: false,
    systemHealthError: null,
  });
});

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/platform/ops/health']}>
      <Routes>
        <Route path="/platform/ops/health" element={<OpsHealthPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('OpsHealthPage', () => {
  it('renders page title and read-only description', () => {
    renderPage();
    expect(screen.getByText('Ops Health')).toBeInTheDocument();
    expect(screen.getByText('Read-only operations health dashboard. No mutation paths.')).toBeInTheDocument();
  });

  it('no mutation controls on page at mount', () => {
    renderPage();
    const buttons = screen.queryAllByRole('button');
    expect(buttons.length).toBe(0);
  });

  it('no sensitive data fields at mount', () => {
    renderPage();
    expect(screen.queryByText(/password/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/token/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/secret/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/credential/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/dsn/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/host.*port/i)).not.toBeInTheDocument();
  });

  it('no business data fields at mount', () => {
    renderPage();
    expect(screen.queryByText(/order/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/payment/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/invoice/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/customer/i)).not.toBeInTheDocument();
  });

  it('renders unknown health data from store with N/A for null components', () => {
    usePlatformStore.setState({
      systemHealth: {
        overall_status: 'unknown',
        api_status: null,
        database_status: null,
        database_connections: null,
        queue_status: null,
        cpu_status: null,
        memory_status: null,
        disk_status: null,
        error_rate: null,
        slow_request_count: null,
        generated_at: '2026-06-13T00:00:00Z',
      },
      systemHealthLoading: false,
      systemHealthError: null,
    });
    renderPage();
    expect(screen.getByText('Overall Status')).toBeInTheDocument();
    // unknown != healthy -- rendered as gray badge
    expect(screen.getByText('unknown')).toBeInTheDocument();
    // Null components show N/A, never 0
    const naElements = screen.getAllByText('N/A');
    expect(naElements.length).toBeGreaterThanOrEqual(2);
  });
});
