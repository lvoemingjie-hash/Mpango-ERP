/**
 * P11-C: PlatformTenantCard component tests.
 *
 * Verifies rendering with healthy, unknown, and null-field tenants.
 */
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { PlatformTenantCard } from '@/components/platform/PlatformTenantCard';
import type { PlatformTenantSummary } from '@/types/platform';

const healthyTenant: PlatformTenantSummary = {
  tenant_id: '550e8400-e29b-41d4-a716-446655440000',
  tenant_name: 'Acme Wholesale Ltd',
  tenant_schema: 'tenant_acme_wholesale',
  status: 'active',
  tier: 'professional',
  created_at: '2026-01-15T09:30:00.000Z',
  last_activity_at: '2026-06-05T08:12:00.000Z',
  user_count: 24,
  health_status: 'healthy',
  recent_error_count: 0,
  support_mode_active: false,
};

const unknownTenant: PlatformTenantSummary = {
  tenant_id: null,
  tenant_name: null,
  tenant_schema: 'tenant_phantom',
  status: 'unknown',
  tier: null,
  created_at: null,
  last_activity_at: null,
  user_count: null,
  health_status: 'unknown',
  recent_error_count: null,
  support_mode_active: false,
};

function renderCard(tenant: PlatformTenantSummary) {
  return render(
    <BrowserRouter>
      <PlatformTenantCard tenant={tenant} />
    </BrowserRouter>,
  );
}

describe('PlatformTenantCard', () => {
  it('TC-001: renders tenant name for healthy tenant', () => {
    renderCard(healthyTenant);
    expect(screen.getByText('Acme Wholesale Ltd')).toBeInTheDocument();
  });

  it('TC-002: shows healthy badge for healthy tenant', () => {
    renderCard(healthyTenant);
    const badges = screen.getAllByText('healthy');
    expect(badges.length).toBeGreaterThanOrEqual(1);
  });

  it('TC-003: shows unknown badge distinctly from healthy for unknown tenant', () => {
    renderCard(unknownTenant);
    // "Unknown Tenant" as fallback name
    expect(screen.getByText('Unknown Tenant')).toBeInTheDocument();
    // "unknown" appears in badge and status — badge should be gray
    const unknownEls = screen.getAllByText('unknown');
    // At least one is the badge
    const badgeEl = unknownEls.find((el) => el.className.includes('bg-gray-100'));
    expect(badgeEl).toBeTruthy();
    expect(badgeEl!.className).toContain('text-gray-600');
    // Badge is NOT green
    expect(badgeEl!.className).not.toContain('bg-green');
  });

  it('TC-004: displays N/A for null user_count (not "0")', () => {
    renderCard(unknownTenant);
    const naElements = screen.getAllByText('N/A');
    // user_count null + recent_error_count null + tier null + last_activity_at null
    expect(naElements.length).toBeGreaterThanOrEqual(1);
    // Ensure no "0" appears for null fields
    expect(screen.queryByText('0')).not.toBeInTheDocument();
  });

  it('TC-005: shows tier when available', () => {
    renderCard(healthyTenant);
    expect(screen.getByText('professional')).toBeInTheDocument();
  });

  it('TC-006: shows N/A for null tier', () => {
    renderCard(unknownTenant);
    const naElements = screen.getAllByText('N/A');
    expect(naElements.length).toBeGreaterThanOrEqual(3);
  });

  it('TC-007: shows tenant schema', () => {
    renderCard(unknownTenant);
    expect(screen.getByText('tenant_phantom')).toBeInTheDocument();
  });

  it('TF-001: no edit/delete/create buttons on tenant card', () => {
    const { container } = renderCard(healthyTenant);
    const buttons = container.querySelectorAll('button');
    expect(buttons.length).toBe(0);
  });
});
