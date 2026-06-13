/**
 * P13-D: Ops resources page component tests.
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
import { beforeEach, describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

// Mock platform service to prevent real network calls.
vi.mock('@/services/platformApi', () => ({
  platformService: {
    getOpsResources: vi.fn().mockResolvedValue({ data: {} }),
  },
}));

import { platformService } from '@/services/platformApi';
import { OpsResourcesPage } from '@/pages/platform/ops/OpsResourcesPage';

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/platform/ops/resources']}>
      <Routes>
        <Route path="/platform/ops/resources" element={<OpsResourcesPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('OpsResourcesPage', () => {
  beforeEach(() => {
    vi.mocked(platformService.getOpsResources).mockResolvedValue({ data: {} });
  });

  it('renders page title and read-only description', () => {
    renderPage();
    expect(screen.getByText('Resources')).toBeInTheDocument();
    expect(screen.getByText('Read-only resource health summary. No mutation paths.')).toBeInTheDocument();
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

  it('shows loading skeleton on mount', () => {
    renderPage();
    const skeletons = document.querySelectorAll('.animate-pulse');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it('renders live DB probe badge and measured latency when data present (P14-C real signal)', async () => {
    vi.mocked(platformService.getOpsResources).mockResolvedValue({
      data: {
        database: {
          status: 'healthy',
          connection_pool_active: 2,
          connection_pool_idle: 4,
          connection_pool_max: 10,
          latency_ms: 7,
        },
        queue: null,
        memory: null,
        cpu: null,
        disk: null,
        generated_at: '2026-06-13T00:00:00Z',
      },
    });
    renderPage();
    expect(await screen.findByTestId('db-source')).toHaveTextContent('Live probe');
    expect(screen.getByText('7ms')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument(); // active connections
  });
});
