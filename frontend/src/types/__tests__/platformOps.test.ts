/**
 * P13-D: Platform ops type tests.
 *
 * Verifies type helpers enforce null != 0 contract.
 */
import { describe, it, expect } from 'vitest';
import {
  displayOpsCount,
  sourceStatusLabel,
  isSourceUnavailable,
} from '@/types/platformOps';
import type {
  ErrorRateSummary,
  SlowRouteSummary,
  OpsSourceStatus,
} from '@/types/platformOps';

describe('platformOps types', () => {
  describe('displayOpsCount', () => {
    it('displays N/A for null', () => {
      expect(displayOpsCount(null)).toBe('N/A');
    });

    it('displays number as string', () => {
      expect(displayOpsCount(0)).toBe('0');
      expect(displayOpsCount(42)).toBe('42');
    });

    it('never displays 0 for null', () => {
      expect(displayOpsCount(null)).not.toBe('0');
    });
  });

  describe('sourceStatusLabel', () => {
    it('returns correct labels', () => {
      expect(sourceStatusLabel('available')).toBe('Live data');
      expect(sourceStatusLabel('unavailable')).toBe('Data unavailable');
      expect(sourceStatusLabel('unknown')).toBe('Not instrumented');
    });
  });

  describe('isSourceUnavailable', () => {
    it('returns true for unavailable', () => {
      expect(isSourceUnavailable('unavailable')).toBe(true);
    });

    it('returns true for unknown', () => {
      expect(isSourceUnavailable('unknown')).toBe(true);
    });

    it('returns false for available', () => {
      expect(isSourceUnavailable('available')).toBe(false);
    });
  });

  describe('ErrorRateSummary type contract', () => {
    it('unavailable summary has null total_errors', () => {
      const summary: ErrorRateSummary = {
        source_status: 'unavailable',
        window_minutes: 15,
        total_errors: null,
        error_classes: [],
        top_routes: [],
        top_tenants: null,
        generated_at: '2026-06-13T00:00:00Z',
      };
      expect(summary.total_errors).toBeNull();
      expect(summary.total_errors).not.toBe(0);
    });

    it('available summary has integer total_errors', () => {
      const summary: ErrorRateSummary = {
        source_status: 'available',
        window_minutes: 15,
        total_errors: 42,
        error_classes: [],
        top_routes: [],
        top_tenants: null,
        generated_at: '2026-06-13T00:00:00Z',
      };
      expect(summary.total_errors).toBe(42);
      expect(typeof summary.total_errors).toBe('number');
    });
  });

  describe('SlowRouteSummary type contract', () => {
    it('unavailable summary has null total_slow_requests', () => {
      const summary: SlowRouteSummary = {
        source_status: 'unavailable',
        window_minutes: 15,
        threshold_ms: 1000,
        total_slow_requests: null,
        routes: [],
        generated_at: '2026-06-13T00:00:00Z',
      };
      expect(summary.total_slow_requests).toBeNull();
      expect(summary.total_slow_requests).not.toBe(0);
    });

    it('available summary has integer total_slow_requests', () => {
      const summary: SlowRouteSummary = {
        source_status: 'available',
        window_minutes: 15,
        threshold_ms: 1000,
        total_slow_requests: 5,
        routes: [],
        generated_at: '2026-06-13T00:00:00Z',
      };
      expect(summary.total_slow_requests).toBe(5);
    });
  });
});
