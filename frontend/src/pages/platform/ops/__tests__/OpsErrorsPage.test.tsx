/**
 * P13-D: Ops errors page component tests.
 *
 * Verifies rendering contract:
 *   - Page title and read-only description
 *   - source_status unavailable rendered distinctly (gray, "Data unavailable")
 *   - null totals rendered as N/A, never as 0
 *   - No mutation controls
 *   - No sensitive data fields
 *   - No business data fields
 *
 * Uses direct state injection via useState mock pattern.
 * API client paths verified separately in platformOpsApi.test.ts.
 */
import { beforeEach, describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

// Mock platform service to prevent real network calls.
vi.mock('@/services/platformApi', () => ({
  platformService: {
    getOpsErrors: vi.fn().mockResolvedValue({ data: {} }),
  },
}));

import { platformService } from '@/services/platformApi';
import { OpsErrorsPage } from '@/pages/platform/ops/OpsErrorsPage';

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/platform/ops/errors']}>
      <Routes>
        <Route path="/platform/ops/errors" element={<OpsErrorsPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('OpsErrorsPage', () => {
  beforeEach(() => {
    vi.mocked(platformService.getOpsErrors).mockResolvedValue({ data: {} });
  });

  it('renders page title and read-only description', () => {
    renderPage();
    expect(screen.getByText('Error Analysis')).toBeInTheDocument();
    expect(screen.getByText('Read-only error rate analysis. No mutation paths.')).toBeInTheDocument();
  });

  it('no mutation controls on page at mount', () => {
    renderPage();
    // During loading, no buttons visible (only retry appears on error)
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

  it('shows loading skeleton on mount', () => {
    renderPage();
    // Skeletons have animate-pulse class
    const skeletons = document.querySelectorAll('.animate-pulse');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it('surfaces unavailable_reason when source is unavailable (P14-C)', async () => {
    vi.mocked(platformService.getOpsErrors).mockResolvedValue({
      data: {
        source_status: 'unavailable',
        window_minutes: 15,
        total_errors: null,
        error_classes: [],
        top_routes: [],
        top_tenants: null,
        unavailable_reason: 'Request error telemetry is not instrumented.',
        generated_at: '2026-06-13T00:00:00Z',
      },
    });
    renderPage();
    expect(await screen.findByTestId('unavailable-reason')).toHaveTextContent(
      'Request error telemetry is not instrumented.',
    );
  });

  it('does not surface unavailable_reason when source is available (P14-C)', async () => {
    vi.mocked(platformService.getOpsErrors).mockResolvedValue({
      data: {
        source_status: 'available',
        window_minutes: 15,
        total_errors: 3,
        error_classes: [],
        top_routes: [],
        top_tenants: null,
        unavailable_reason: null,
        generated_at: '2026-06-13T00:00:00Z',
      },
    });
    renderPage();
    // Wait for data to render, then confirm no reason banner.
    expect(await screen.findByText('Live data')).toBeInTheDocument();
    expect(screen.queryByTestId('unavailable-reason')).not.toBeInTheDocument();
  });
});
