/**
 * P17-C: platformRegistry type + helper tests.
 *
 * Verifies the display-rule helpers that enforce the P17 contract:
 *   - unknown != healthy / active (gray, never green)
 *   - null != 0 / false (N/A, never 0)
 * and that the TS contract mirrors carry the expected shape.
 */
import { describe, it, expect } from 'vitest';
import {
  displayRegistryCount,
  displayNullable,
  displayNullableBool,
  isLifecycleUnknown,
  lifecycleStateLabel,
  lifecycleStateTone,
  sourceStatusTone,
  type PlatformTenantRegistry,
  type PlatformTenantRegistryList,
} from '@/types/platformRegistry';

describe('platformRegistry helpers', () => {
  describe('displayRegistryCount (null != 0)', () => {
    it('null -> "N/A", never "0"', () => {
      expect(displayRegistryCount(null)).toBe('N/A');
    });
    it('number -> string', () => {
      expect(displayRegistryCount(7)).toBe('7');
      expect(displayRegistryCount(0)).toBe('0');
    });
  });

  describe('displayNullable / displayNullableBool', () => {
    it('null/empty -> "N/A"', () => {
      expect(displayNullable(null)).toBe('N/A');
      expect(displayNullable('')).toBe('N/A');
      expect(displayNullable('schema_create_failed')).toBe('schema_create_failed');
    });
    it('boolean null -> "N/A"; true -> "Yes"; false -> "No"', () => {
      expect(displayNullableBool(null)).toBe('N/A');
      expect(displayNullableBool(true)).toBe('Yes');
      expect(displayNullableBool(false)).toBe('No');
    });
  });

  describe('lifecycleStateLabel (unknown != healthy)', () => {
    it('labels every state distinctly', () => {
      expect(lifecycleStateLabel('active')).toBe('Active');
      expect(lifecycleStateLabel('unknown')).toBe('Unknown');
      expect(lifecycleStateLabel('failed_provisioning')).toBe('Failed provisioning');
    });
    it('null/undefined -> "Unknown"', () => {
      expect(lifecycleStateLabel(null)).toBe('Unknown');
      expect(lifecycleStateLabel(undefined)).toBe('Unknown');
    });
  });

  describe('isLifecycleUnknown', () => {
    it('true for null/undefined/unknown', () => {
      expect(isLifecycleUnknown(null)).toBe(true);
      expect(isLifecycleUnknown('unknown')).toBe(true);
    });
    it('false for a real operational state', () => {
      expect(isLifecycleUnknown('active')).toBe(false);
    });
  });

  describe('lifecycleStateTone (never green for unknown/degraded)', () => {
    it('active -> green', () => {
      expect(lifecycleStateTone('active')).toBe('green');
    });
    it('unknown -> gray, never green', () => {
      expect(lifecycleStateTone('unknown')).toBe('gray');
      expect(lifecycleStateTone(null)).toBe('gray');
    });
    it('suspended/failed_provisioning -> red', () => {
      expect(lifecycleStateTone('suspended')).toBe('red');
      expect(lifecycleStateTone('failed_provisioning')).toBe('red');
    });
  });

  describe('sourceStatusTone', () => {
    it('available -> green; unavailable/unknown -> gray', () => {
      expect(sourceStatusTone('available')).toBe('green');
      expect(sourceStatusTone('unavailable')).toBe('gray');
      expect(sourceStatusTone('unknown')).toBe('gray');
      expect(sourceStatusTone(null)).toBe('gray');
    });
  });
});

describe('platformRegistry contract shape', () => {
  it('a full registry record satisfies the PlatformTenantRegistry shape', () => {
    const rec: PlatformTenantRegistry = {
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
    };
    expect(rec.tenant_id).toBe('b2c3d4e5-f6a7-48b8-9c0d-1e2f3a4b5c6d');
    expect(rec.lifecycle_state.state).toBe('active');
    expect(rec.provisioning_status).toBeNull();
  });

  it('a list payload satisfies PlatformTenantRegistryList', () => {
    const list: PlatformTenantRegistryList = {
      items: [],
      total: 0,
      limit: 50,
      offset: 0,
      registry_source_status: 'unavailable',
      unavailable_reason: 'identity source unavailable',
    };
    expect(list.registry_source_status).toBe('unavailable');
    expect(list.items).toEqual([]);
  });
});
