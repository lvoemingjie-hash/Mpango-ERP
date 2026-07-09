/**
 * P12-C0: Support console types and helpers tests.
 *
 * Verifies:
 *   - isReasonValid: null/empty/short/valid
 *   - getReasonValidationError: correct messages
 *   - Type conformance for SupportSession, SupportBundle, SupportDiagnosticItem
 *   - Error shapes for MISSING_REASON and REASON_TOO_SHORT
 */
import { describe, it, expect } from 'vitest';
import {
  isReasonValid,
  getReasonValidationError,
  REASON_MIN_LENGTH,
} from '@/types/support';
import type {
  SupportCategory,
  SupportSession,
  SupportDiagnosticItem,
  SupportBundle,
  SupportErrorDetail,
  DiagnosticSourceStatus,
} from '@/types/support';

describe('isReasonValid', () => {
  it('returns false for null', () => {
    expect(isReasonValid(null)).toBe(false);
  });

  it('returns false for undefined', () => {
    expect(isReasonValid(undefined)).toBe(false);
  });

  it('returns false for empty string', () => {
    expect(isReasonValid('')).toBe(false);
  });

  it('returns false for whitespace-only string', () => {
    expect(isReasonValid('   ')).toBe(false);
  });

  it('returns false for string shorter than 10 chars', () => {
    expect(isReasonValid('short')).toBe(false);
  });

  it('returns false for string with 9 chars', () => {
    expect(isReasonValid('123456789')).toBe(false);
  });

  it('returns true for string with exactly 10 chars', () => {
    expect(isReasonValid('1234567890')).toBe(true);
  });

  it('returns true for long valid reason', () => {
    expect(isReasonValid('Tenant login failure triage -- users cannot authenticate')).toBe(true);
  });
});

describe('getReasonValidationError', () => {
  it('returns required message for null', () => {
    expect(getReasonValidationError(null)).toBe('Support reason is required.');
  });

  it('returns required message for empty string', () => {
    expect(getReasonValidationError('')).toBe('Support reason is required.');
  });

  it('returns too-short message with char count', () => {
    const error = getReasonValidationError('short');
    expect(error).toContain('at least 10 characters');
    expect(error).toContain('currently 5');
  });

  it('returns null for valid reason', () => {
    expect(getReasonValidationError('A valid reason with enough characters')).toBeNull();
  });
});

describe('REASON_MIN_LENGTH', () => {
  it('is 10', () => {
    expect(REASON_MIN_LENGTH).toBe(10);
  });
});

describe('SupportSession type conformance', () => {
  it('accepts a valid active session', () => {
    const session: SupportSession = {
      session_id: 'a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d',
      actor_id: 'b2c3d4e5-f6a7-48b8-9c0d-1e2f3a4b5c6d',
      actor_role: 'super_admin',
      tenant_id: 'a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d',
      reason: 'Tenant login failure triage',
      category: 'login_issue',
      correlation_id: 'corr-001',
      status: 'active',
      started_at: '2026-06-11T10:00:00Z',
      closed_at: null,
      expires_at: '2026-06-11T11:00:00Z',
      bundle_count: 0,
    };
    expect(session.status).toBe('active');
    expect(session.reason).toBe('Tenant login failure triage');
  });
});

describe('SupportDiagnosticItem type conformance', () => {
  it('accepts available diagnostic item', () => {
    const item: SupportDiagnosticItem = {
      item_id: 'd1e2f3a4-b5c6-4d7e-8f9a-0b1c2d3e4f5a',
      bundle_id: null,
      category: 'tenant_metadata',
      label: 'Tenant Summary',
      value: { tenant_name: 'Acme' },
      source_status: 'available',
      collected_at: '2026-06-11T10:01:00Z',
    };
    expect(item.source_status).toBe('available');
  });

  it('accepts unavailable diagnostic item with null value', () => {
    const item: SupportDiagnosticItem = {
      item_id: 'e2f3a4b5-c6d7-4e8f-9a0b-1c2d3e4f5a6b',
      bundle_id: null,
      category: 'recent_errors',
      label: 'Recent Errors',
      value: null,
      source_status: 'unavailable',
      collected_at: '2026-06-11T10:01:00Z',
    };
    expect(item.source_status).toBe('unavailable');
    expect(item.value).toBeNull();
  });
});

describe('SupportBundle type conformance', () => {
  it('accepts a valid bundle with diagnostics', () => {
    const bundle: SupportBundle = {
      bundle_id: 'f3a4b5c6-d7e8-4f9a-0b1c-2d3e4f5a6b7c',
      session_id: 'a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d',
      actor_id: null,
      tenant_id: null,
      correlation_id: 'corr-001-b-f3a4b5c6',
      generated_at: '2026-06-11T10:02:00Z',
      diagnostics: [
        {
          item_id: 'd1e2f3a4-b5c6-4d7e-8f9a-0b1c2d3e4f5a',
          bundle_id: 'f3a4b5c6-d7e8-4f9a-0b1c-2d3e4f5a6b7c',
          category: 'health_summary',
          label: 'Tenant Health',
          value: {},
          source_status: 'available',
          collected_at: '2026-06-11T10:02:00Z',
        },
      ],
      redaction_applied: true,
      bundle_type: 'full',
    };
    expect(bundle.redaction_applied).toBe(true);
    expect(bundle.diagnostics.length).toBeGreaterThan(0);
  });
});

describe('SupportErrorDetail type conformance', () => {
  it('accepts MISSING_REASON error', () => {
    const err: SupportErrorDetail = {
      code: 'MISSING_REASON',
      message: 'Support reason is required',
    };
    expect(err.code).toBe('MISSING_REASON');
  });

  it('accepts REASON_TOO_SHORT error', () => {
    const err: SupportErrorDetail = {
      code: 'REASON_TOO_SHORT',
      message: 'Support reason must be at least 10 characters, got 5',
    };
    expect(err.code).toBe('REASON_TOO_SHORT');
  });
});
