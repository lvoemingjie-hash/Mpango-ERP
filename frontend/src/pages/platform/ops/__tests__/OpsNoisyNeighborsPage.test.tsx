/**
 * P13-D: Ops noisy neighbors page component tests.
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
function unwrapMock<T>(res: { data: unknown }): T {
  const body = res.data as Record<string, unknown> | undefined;
  return (body && typeof body === 'object' && 'data' in body ? body.data : body) as unknown as T;
}
vi.mock('@/services/platformApi', () => ({
  platformService: {
    getOpsNoisyNeighbors: vi.fn().mockResolvedValue({ data: {} }),
  },
  unwrapApiResponse: unwrapMock,
}));

import { platformService } from '@/services/platformApi';
import { OpsNoisyNeighborsPage } from '@/pages/platform/ops/OpsNoisyNeighborsPage';

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/platform/ops/noisy-neighbors']}>
      <Routes>
        <Route path="/platform/ops/noisy-neighbors" element={<OpsNoisyNeighborsPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('OpsNoisyNeighborsPage', () => {
  beforeEach(() => {
    vi.mocked(platformService.getOpsNoisyNeighbors).mockResolvedValue({ data: {} });
  });

  it('renders page title and read-only description', () => {
    renderPage();
    expect(screen.getByText('Noisy Neighbors')).toBeInTheDocument();
    expect(screen.getByText('Read-only noisy-neighbor analysis. No mutation paths.')).toBeInTheDocument();
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

  it('surfaces unavailable_reason in empty state when source unavailable (P14-C)', async () => {
    vi.mocked(platformService.getOpsNoisyNeighbors).mockResolvedValue({
      data: {
        window_minutes: 15,
        tenants: [],
        unavailable_reason: 'Cross-tenant activity telemetry is not available.',
        generated_at: '2026-06-13T00:00:00Z',
      },
    });
    renderPage();
    expect(await screen.findByTestId('unavailable-reason')).toHaveTextContent(
      'Cross-tenant activity telemetry is not available.',
    );
  });
});
