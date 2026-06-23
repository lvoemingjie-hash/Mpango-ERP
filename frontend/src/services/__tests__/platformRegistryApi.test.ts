/**
 * P17-C: Platform registry API service tests.
 *
 * Verifies P17 read-only endpoint paths and parameters, and that the returned
 * payload is typed as the P17 registry contracts. Read-only: only GET is wired.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock the api module
vi.mock('@/services/api', () => ({
  api: {
    get: vi.fn(),
  },
}));

import { platformService } from '@/services/platformApi';
import { api } from '@/services/api';

const mockGet = vi.mocked(api.get);

beforeEach(() => {
  vi.clearAllMocks();
});

describe('platformService P17 registry endpoints', () => {
  it('P17-001: listTenantRegistry calls GET /platform/p17/registry with default paging', async () => {
    mockGet.mockResolvedValueOnce({ data: {} });
    await platformService.listTenantRegistry();
    expect(mockGet).toHaveBeenCalledWith('/platform/p17/registry', {
      params: { limit: 50, offset: 0 },
    });
  });

  it('P17-002: listTenantRegistry passes custom paging', async () => {
    mockGet.mockResolvedValueOnce({ data: {} });
    await platformService.listTenantRegistry(10, 20);
    expect(mockGet).toHaveBeenCalledWith('/platform/p17/registry', {
      params: { limit: 10, offset: 20 },
    });
  });

  it('P17-003: getTenantRegistry calls GET /platform/p17/registry/{tenantId}', async () => {
    mockGet.mockResolvedValueOnce({ data: {} });
    await platformService.getTenantRegistry('b2c3d4e5-f6a7-48b8-9c0d-1e2f3a4b5c6d');
    expect(mockGet).toHaveBeenCalledWith(
      '/platform/p17/registry/b2c3d4e5-f6a7-48b8-9c0d-1e2f3a4b5c6d',
    );
  });

  it('P17-004: returned list payload has the registry contract shape', async () => {
    const payload = {
      items: [
        {
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
          unavailable_reason: 'backup source unavailable',
        },
      ],
      total: 1,
      limit: 50,
      offset: 0,
      registry_source_status: 'available',
      unavailable_reason: 'backup source unavailable',
    };
    mockGet.mockResolvedValueOnce({ data: payload });
    const res = await platformService.listTenantRegistry();
    expect(res.data.total).toBe(1);
    expect(res.data.items[0].lifecycle_state.state).toBe('active');
    expect(res.data.items[0].provisioning_status).toBeNull();
    expect(res.data.items[0].backup_status).toBeNull();
  });
});
