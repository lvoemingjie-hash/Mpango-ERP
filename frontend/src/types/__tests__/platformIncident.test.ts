/**
 * P15-C: Platform incident type tests.
 *
 * Verifies type helpers enforce null != 0 and unknown != healthy.
 */
import { describe, it, expect } from 'vitest';
import {
  displayIncidentCount,
  healthStatusLabel,
  isStatusUnknown,
} from '@/types/platformIncident';
import type { IncidentTriageSnapshot, IncidentSignal } from '@/types/platformIncident';

describe('platformIncident types', () => {
  describe('displayIncidentCount', () => {
    it('displays N/A for null', () => {
      expect(displayIncidentCount(null)).toBe('N/A');
    });
    it('displays number as string', () => {
      expect(displayIncidentCount(0)).toBe('0');
      expect(displayIncidentCount(7)).toBe('7');
    });
    it('never displays 0 for null', () => {
      expect(displayIncidentCount(null)).not.toBe('0');
    });
  });

  describe('healthStatusLabel', () => {
    it('labels each status distinctly (unknown != healthy)', () => {
      expect(healthStatusLabel('healthy')).toBe('Healthy');
      expect(healthStatusLabel('unknown')).toBe('Unknown');
      expect(healthStatusLabel('degraded')).toBe('Degraded');
      expect(healthStatusLabel('unhealthy')).toBe('Unhealthy');
      expect(healthStatusLabel(null)).toBe('Unknown');
    });
  });

  describe('isStatusUnknown', () => {
    it('true for unknown/null/undefined', () => {
      expect(isStatusUnknown('unknown')).toBe(true);
      expect(isStatusUnknown(null)).toBe(true);
      expect(isStatusUnknown(undefined)).toBe(true);
    });
    it('false for measured statuses', () => {
      expect(isStatusUnknown('healthy')).toBe(false);
      expect(isStatusUnknown('degraded')).toBe(false);
    });
  });

  describe('IncidentTriageSnapshot type contract', () => {
    it('graceful_degraded snapshot with null counts is valid', () => {
      const snap: IncidentTriageSnapshot = {
        snapshot_id: 'x',
        generated_at: '2026-06-14T00:00:00Z',
        overall_status: 'unknown',
        signals: [],
        database_probe: null,
        system_health_overall: null,
        tenant_health_sample_count: null,
        tenant_health_unhealthy_count: null,
        degraded_reason: null,
        unavailable_reason: 'Database probe failed.',
        graceful_degraded: true,
      };
      expect(snap.graceful_degraded).toBe(true);
      expect(snap.tenant_health_sample_count).toBeNull();
      expect(snap.tenant_health_sample_count).not.toBe(0); // null != 0
    });

    it('IncidentSignal with unknown severity is distinct from healthy', () => {
      const sig: IncidentSignal = {
        signal_id: 's1', kind: 'system', severity: 'unknown',
        source_ref: 'p10', observed_value: null, source_status: 'unknown',
        unavailable_reason: 'system health stub', degraded_reason: null,
        observed_at: '2026-06-14T00:00:00Z',
      };
      expect(sig.severity).toBe('unknown');
      // no 'healthy' severity exists for signals
      expect((sig as unknown as { severity: string }).severity).not.toBe('healthy');
    });

    it('P15-R1 [P3]: IncidentSignal.observed_value accepts integer count', () => {
      const sig: IncidentSignal = {
        signal_id: 's2', kind: 'tenant_health', severity: 'warning',
        source_ref: 'p10.tenants.summary', observed_value: 7,
        source_status: 'available', unavailable_reason: null, degraded_reason: null,
        observed_at: '2026-06-14T00:00:00Z',
      };
      expect(sig.observed_value).toBe(7);
      expect(typeof sig.observed_value).toBe('number');
    });
  });
});
