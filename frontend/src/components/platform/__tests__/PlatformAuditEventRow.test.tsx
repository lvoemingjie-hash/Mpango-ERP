/**
 * P11-C: PlatformAuditEventRow component tests.
 *
 * Verifies rendering of audit event rows with correct result coloring.
 * Ensures metadata_redacted is never rendered as raw text.
 */
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PlatformAuditEventRow } from '@/components/platform/PlatformAuditEventRow';
import type { PlatformAuditEvent } from '@/types/platform';

const allowedEvent: PlatformAuditEvent = {
  event_id: '880e8400-e29b-41d4-a716-446655440003',
  actor_id: 'operator-42',
  actor_role: 'super_admin',
  tenant_id: null,
  scope: 'global',
  action: 'platform.overview_view',
  reason: null,
  result: 'allowed',
  metadata_redacted: { some: 'sensitive', data: 'here' },
  correlation_id: 'corr-001',
  created_at: '2026-06-05T09:20:01.000Z',
};

const deniedEvent: PlatformAuditEvent = {
  event_id: '990e8400-e29b-41d4-a716-446655440004',
  actor_id: 'user-99',
  actor_role: 'admin',
  tenant_id: '660e8400-e29b-41d4-a716-446655440001',
  scope: 'tenant',
  action: 'tenant.status_change',
  reason: 'policy violation',
  result: 'denied',
  metadata_redacted: null,
  correlation_id: null,
  created_at: '2026-06-05T09:22:00.000Z',
};

function renderRow(event: PlatformAuditEvent) {
  return render(
    <table>
      <tbody>
        <PlatformAuditEventRow event={event} />
      </tbody>
    </table>,
  );
}

describe('PlatformAuditEventRow', () => {
  it('renders action name', () => {
    renderRow(allowedEvent);
    expect(screen.getByText('platform.overview_view')).toBeInTheDocument();
  });

  it('renders actor id', () => {
    renderRow(allowedEvent);
    expect(screen.getByText(/operator-42/)).toBeInTheDocument();
  });

  it('renders actor role in parentheses', () => {
    renderRow(allowedEvent);
    expect(screen.getByText('(super_admin)')).toBeInTheDocument();
  });

  it('renders scope badge', () => {
    renderRow(allowedEvent);
    expect(screen.getByText('global')).toBeInTheDocument();
  });

  it('renders result with correct color for allowed', () => {
    const { container } = renderRow(allowedEvent);
    const resultEl = screen.getByText('allowed');
    expect(resultEl.className).toContain('text-green-700');
  });

  it('renders result with correct color for denied', () => {
    renderRow(deniedEvent);
    const resultEl = screen.getByText('denied');
    expect(resultEl.className).toContain('text-red-700');
  });

  it('renders System for null actor_id', () => {
    const systemEvent: PlatformAuditEvent = {
      ...allowedEvent,
      actor_id: null,
      actor_role: null,
    };
    renderRow(systemEvent);
    expect(screen.getByText('System')).toBeInTheDocument();
  });

  it('TF-002: metadata_redacted is never rendered as raw text', () => {
    const { container } = renderRow(allowedEvent);
    // metadata_redacted exists in the event but must NOT appear in rendered output
    expect(container.textContent).not.toContain('sensitive');
    expect(container.textContent).not.toContain('{"some":"sensitive"}');
  });
});
