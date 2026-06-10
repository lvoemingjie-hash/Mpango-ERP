/**
 * P11-B1: Platform types and helpers tests.
 *
 * Verifies:
 *   - displayCount: null → "N/A", number → string
 *   - displayTimestamp: null → "N/A", valid ISO → locale string
 *   - Type conformance (compile-time via TypeScript)
 */
import { describe, it, expect } from 'vitest';
import { displayCount, displayTimestamp } from '@/types/platform';
import type {
  PlatformTenantSummary,
  PlatformTenantHealth,
  PlatformSystemHealth,
  PlatformAuditEvent,
  HealthStatus,
  TenantStatus,
} from '@/types/platform';

describe('displayCount', () => {
  it('returns "N/A" for null', () => {
    expect(displayCount(null)).toBe('N/A');
  });

  it('returns "0" for zero', () => {
    expect(displayCount(0)).toBe('0');
  });

  it('returns "42" for 42', () => {
    expect(displayCount(42)).toBe('42');
  });
});

describe('displayTimestamp', () => {
  it('returns "N/A" for null', () => {
    expect(displayTimestamp(null)).toBe('N/A');
  });

  it('returns locale string for valid ISO timestamp', () => {
    const result = displayTimestamp('2026-06-05T08:12:00.000Z');
    expect(result).not.toBe('N/A');
    expect(result.length).toBeGreaterThan(0);
  });

  it('returns "N/A" for invalid string', () => {
    expect(displayTimestamp('not-a-date')).toBe('N/A');
  });
});

describe('PlatformTenantSummary type conformance', () => {
  it('accepts a valid tenant summary matching P10-A contract', () => {
    const tenant: PlatformTenantSummary = {
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
    expect(tenant.status).toBe('active');
    expect(tenant.health_status).toBe('healthy');
  });

  it('accepts unknown state with null fields', () => {
    const tenant: PlatformTenantSummary = {
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
    expect(tenant.status).toBe('unknown');
    expect(tenant.user_count).toBeNull();
  });
});

describe('PlatformSystemHealth type conformance', () => {
  it('accepts degraded system health with null component statuses', () => {
    const health: PlatformSystemHealth = {
      overall_status: 'degraded',
      api_status: 'degraded',
      database_status: 'healthy',
      database_connections: { active: 8, idle: 3, max: 20, saturation_pct: 40.0 },
      queue_status: 'healthy',
      cpu_status: null,
      memory_status: null,
      disk_status: null,
      error_rate: 0.12,
      slow_request_count: 3,
      generated_at: '2026-06-05T09:00:00.000Z',
    };
    expect(health.overall_status).toBe('degraded');
    expect(health.cpu_status).toBeNull();
  });
});

describe('PlatformAuditEvent type conformance', () => {
  it('accepts a valid audit event', () => {
    const event: PlatformAuditEvent = {
      event_id: '880e8400-e29b-41d4-a716-446655440003',
      actor_id: 'operator-42',
      actor_role: 'super_admin',
      tenant_id: '550e8400-e29b-41d4-a716-446655440000',
      scope: 'global',
      action: 'platform.overview_view',
      reason: null,
      result: 'allowed',
      metadata_redacted: null,
      correlation_id: null,
      created_at: '2026-06-05T09:20:01.000Z',
    };
    expect(event.scope).toBe('global');
    expect(event.result).toBe('allowed');
  });
});
