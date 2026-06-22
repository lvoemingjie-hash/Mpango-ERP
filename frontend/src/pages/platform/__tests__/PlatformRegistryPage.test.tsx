/**
 * P17-C: Platform registry page component tests.
 *
 * Verifies rendering contract:
 *   - Page title and read-only description
 *   - No mutation controls (buttons) at mount or after data
 *   - No sensitive / business data fields
 *   - Loading skeleton on mount
 *   - unknown != healthy (gray badge, never green/active)
 *   - null != 0 / false (N/A, never 0)
 *   - unavailable reason visible when present
 *   - real registry data renders (tenant rows, lifecycle, source status)
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
import { PlatformRegistryPage } from '@/pages/platform/PlatformRegistryPage';

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/platform/registry']}>
      <Routes>
        <Route path="/platform/registry" element={<PlatformRegistryPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

const UNKNOWN_TENANT = {
  tenant_id: 'c3d4e5f6-a7b8-49c0-9d1e-2f3a4b5c6d7e',
  tenant_name: 'Unknown Corp',
  tenant_schema: null,
  tier: null,
  created_at: null,
  lifecycle_state: {
    state: 'unknown',
    previous_state: null,
    entered_at: null,
    last_actor_id: null,
    last_actor_role: null,
    transition_reason: null,
    last_audit_event_id: null,
    state_source_status: 'unknown',
  },
  operational_flags: {
    support_mode_active: false,
    incident_active: false,
    login_paused: false,
    writes_paused: false,
    billing_hold: false,
    backup_attention_required: false,
    migration_attention_required: false,
    quota_attention_required: false,
    flags_source_status: 'unavailable',
    flags_updated_at: null,
    flags_unavailable_reason: 'telemetry not instrumented',
  },
  provisioning_status: null,
  backup_status: null,
  last_registry_update_at: null,
  registry_source_status: 'unknown',
  unavailable_reason: 'Provisioning and backup sources unavailable.',
};

const ACTIVE_TENANT = {
  tenant_id: 'b2c3d4e5-f6a7-48b8-9c0d-1e2f3a4b5c6d',
  tenant_name: 'Acme',
  tenant_schema: 't_acme',
  tier: null,
  created_at: '2026-06-01T00:00:00Z',
  lifecycle_state: {
    state: 'active',
    previous_state: null,
    entered_at: null,
    last_actor_id: null,
    last_actor_role: null,
    transition_reason: null,
    last_audit_event_id: null,
    state_source_status: 'available',
  },
  operational_flags: {
    support_mode_active: false,
    incident_active: false,
    login_paused: false,
    writes_paused: false,
    billing_hold: false,
    backup_attention_required: false,
    migration_attention_required: false,
    quota_attention_required: false,
    flags_source_status: 'unavailable',
    flags_updated_at: null,
    flags_unavailable_reason: 'telemetry not instrumented',
  },
  provisioning_status: null,
  backup_status: null,
  last_registry_update_at: null,
  registry_source_status: 'available',
  unavailable_reason: 'Backup source unavailable.',
};

describe('PlatformRegistryPage', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockResolvedValue({ data: {} });
  });

  it('renders page title and read-only description', () => {
    renderPage();
    expect(screen.getByText('Platform Registry')).toBeInTheDocument();
    expect(screen.getByText('Read-only tenant registry. No mutation controls.')).toBeInTheDocument();
  });

  it('no mutation controls (buttons) on page at mount', () => {
    renderPage();
    expect(screen.queryAllByRole('button')).toHaveLength(0);
  });

  it('no sensitive data fields at mount', () => {
    renderPage();
    expect(screen.queryByText(/password/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/secret/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/credential/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/dsn/i)).not.toBeInTheDocument();
  });

  it('no tenant business data fields at mount', () => {
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

  it('renders real registry rows (active tenant + lifecycle badge)', async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: { items: [ACTIVE_TENANT], total: 1, limit: 50, offset: 0,
        registry_source_status: 'available', unavailable_reason: 'Backup source unavailable.' },
    });
    renderPage();
    expect(await screen.findByText('Acme')).toBeInTheDocument();
    // lifecycle badge renders the active state label
    expect(screen.getByText('Active')).toBeInTheDocument();
    // null provisioning / backup render N/A, never 0
    expect(screen.getAllByText('N/A').length).toBeGreaterThan(0);
    // source status surfaced
    expect(screen.getByTestId('registry-source-status')).toHaveTextContent('available');
  });

  it('unknown tenant renders gray, never active/green (unknown != healthy)', async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: { items: [UNKNOWN_TENANT], total: 1, limit: 50, offset: 0,
        registry_source_status: 'unknown', unavailable_reason: 'Provisioning and backup sources unavailable.' },
    });
    renderPage();
    expect(await screen.findByText('Unknown Corp')).toBeInTheDocument();
    // lifecycle badge is 'Unknown' (never 'Active')
    const badges = screen.getAllByTestId('lifecycle-badge');
    expect(badges.some((b) => b.textContent === 'Unknown')).toBe(true);
    expect(screen.queryByText('Active')).not.toBeInTheDocument();
    // source badge is gray (unknown) -- the registry-level source status text is 'unknown'
    expect(screen.getByTestId('registry-source-status')).toHaveTextContent('unknown');
  });

  it('null != 0: total and nullable fields render, no fabricated "0" count', async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: { items: [ACTIVE_TENANT], total: 1, limit: 50, offset: 0,
        registry_source_status: 'available', unavailable_reason: 'Backup source unavailable.' },
    });
    renderPage();
    await screen.findByText('Acme');
    // tenant count renders as "1 tenant(s)" -- a real count, not a fabricated 0
    expect(screen.getByText(/1 tenant\(s\)/)).toBeInTheDocument();
    // N/A appears for null provisioning/backup (never a fabricated value)
    expect(screen.getAllByText('N/A').length).toBeGreaterThan(0);
  });

  it('unavailable reason visible when present', async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: { items: [ACTIVE_TENANT], total: 1, limit: 50, offset: 0,
        registry_source_status: 'available', unavailable_reason: 'Backup source unavailable.' },
    });
    renderPage();
    expect(await screen.findByTestId('unavailable-reason')).toHaveTextContent(
      'Backup source unavailable.',
    );
  });

  it('still no buttons after data loads (read-only)', async () => {
    vi.mocked(api.get).mockResolvedValue({
      data: { items: [ACTIVE_TENANT], total: 1, limit: 50, offset: 0,
        registry_source_status: 'available', unavailable_reason: 'Backup source unavailable.' },
    });
    renderPage();
    await screen.findByText('Acme');
    expect(screen.queryAllByRole('button')).toHaveLength(0);
  });
});
