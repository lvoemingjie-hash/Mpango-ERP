/**
 * P13-D: Ops slow routes page component tests.
 *
 * Verifies rendering contract:
 *   - Page title and read-only description
 *   - No mutation controls
 *   - No sensitive data fields
 *   - Loading skeleton on mount
 *
 * API client paths verified separately in platformOpsApi.test.ts.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

vi.mock('@/services/api', () => ({
  api: {
    get: vi.fn().mockResolvedValue({ data: {} }),
    post: vi.fn(),
  },
}));

import { OpsSlowRoutesPage } from '@/pages/platform/ops/OpsSlowRoutesPage';

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/platform/ops/slow-routes']}>
      <Routes>
        <Route path="/platform/ops/slow-routes" element={<OpsSlowRoutesPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('OpsSlowRoutesPage', () => {
  it('renders page title and read-only description', () => {
    renderPage();
    expect(screen.getByText('Slow Routes')).toBeInTheDocument();
    expect(screen.getByText('Read-only slow route analysis. No mutation paths.')).toBeInTheDocument();
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
  });

  it('shows loading skeleton on mount', () => {
    renderPage();
    const skeletons = document.querySelectorAll('.animate-pulse');
    expect(skeletons.length).toBeGreaterThan(0);
  });
});
