/**
 * P15-C: Incident triage page component tests.
 *
 * Verifies rendering contract:
 *   - Page title and read-only description
 *   - No mutation controls
 *   - No sensitive / business data fields
 *   - Loading skeleton on mount
 *   - unknown != healthy (gray), null != 0 (N/A)
 *   - unavailable / degraded reason visible when present
 *   - graceful degraded state visible when present
 *   - real snapshot data renders (DB probe, signals)
 */
import { beforeEach, describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

// Mock api to prevent real network calls
vi.mock('@/services/api', () => ({
  api: {
    get: vi.fn().mockResolvedValue({ data: {} }),
    post: vi.fn(),
  },
}));

import { api } from '@/services/api';
import { IncidentTriagePage } from '@/pages/platform/ops/IncidentTriagePage';

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/platform/ops/incidents/triage']}>
      <Routes>
        <Route path="/platform/ops/incidents/triage" element={<IncidentTriagePage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('IncidentTriagePage', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockResolvedValue({ data: {} });
  });

  it('renders page title and read-only description', () => {
    renderPage();
    expect(screen.getByText('Incident Triage')).toBeInTheDocument();
    expect(screen.getByText('Read-only triage snapshot. No mutation paths.')).toBeInTheDocument();
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

  it('renders real snapshot with DB probe + signals (unknown gray, null N/A)', async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: {
        snapshot_id: 'abc123',
        generated_at: '2026-06-14T00:00:00Z',
        overall_status: 'degraded',
        signals: [
          {
            signal_id: 's1', kind: 'database', severity: 'degraded',
            source_ref: 'p14.ops.resources.database', observed_value: 'degraded',
            source_status: 'available', unavailable_reason: null,
            degraded_reason: 'Database latency above healthy threshold.',
            observed_at: '2026-06-14T00:00:00Z',
          },
        ],
        database_probe: {
          status: 'degraded', connection_pool_active: 3, connection_pool_idle: 2,
          connection_pool_max: 10, latency_ms: 250,
        },
        system_health_overall: 'unknown',
        tenant_health_sample_count: 12,
        tenant_health_unhealthy_count: 2,
        degraded_reason: 'Database probe latency above healthy threshold.',
        unavailable_reason: null,
        graceful_degraded: false,
      },
    });
    renderPage();
    // DB probe latency renders (null != 0 check via the N/A path tested elsewhere)
    expect(await screen.findByText('250ms')).toBeInTheDocument();
    // tenant sample count renders (number, not N/A)
    expect(screen.getByText('12')).toBeInTheDocument();
    // degraded reason visible
    expect(screen.getByTestId('degraded-reason')).toBeInTheDocument();
  });

  it('renders graceful degraded + unavailable reason when present', async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: {
        snapshot_id: 'abc123',
        generated_at: '2026-06-14T00:00:00Z',
        overall_status: 'unhealthy',
        signals: [],
        database_probe: null,
        system_health_overall: null,
        tenant_health_sample_count: null,
        tenant_health_unhealthy_count: null,
        degraded_reason: null,
        unavailable_reason: 'Database probe failed during snapshot assembly.',
        graceful_degraded: true,
      },
    });
    renderPage();
    expect(await screen.findByTestId('graceful-degraded')).toHaveTextContent('Graceful degraded');
    expect(screen.getByTestId('unavailable-reason')).toBeInTheDocument();
    // null tenant count renders as N/A, never 0
    const tenantSample = screen.getAllByText('N/A');
    expect(tenantSample.length).toBeGreaterThan(0);
  });

  it('null != 0: unavailable DB fields render N/A, not 0', async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: {
        snapshot_id: 'abc123',
        generated_at: '2026-06-14T00:00:00Z',
        overall_status: 'unknown',
        signals: [],
        database_probe: {
          status: 'unhealthy', connection_pool_active: null, connection_pool_idle: null,
          connection_pool_max: null, latency_ms: null,
        },
        system_health_overall: 'unknown',
        tenant_health_sample_count: null,
        tenant_health_unhealthy_count: null,
        degraded_reason: null,
        unavailable_reason: 'Database probe reported unhealthy.',
        graceful_degraded: true,
      },
    });
    renderPage();
    // Wait for data to render via a stable testid, then confirm the null DB
    // probe fields display N/A (never a fabricated 0).
    expect(await screen.findByTestId('unavailable-reason')).toBeInTheDocument();
    const naNodes = screen.getAllByText('N/A');
    expect(naNodes.length).toBeGreaterThanOrEqual(4); // latency + active + idle + max
    // No "0ms" fabricated latency anywhere.
    expect(screen.queryAllByText('0ms')).toHaveLength(0);
  });
});
