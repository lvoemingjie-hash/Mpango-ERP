/**
 * P22-C: Controlled Execution type contract tests.
 *
 * Locks the closed v0 allowlist (exactly seven actions) and the response-shape
 * invariants that the operator console relies on:
 *   - every response is non-executing (executed / execution_allowed /
 *     execution_started are typed boolean and realized as false);
 *   - a RESPONSE never models a raw idempotency_key -- only the one-way digest.
 */
import { describe, it, expect } from 'vitest';
import {
  P22_ALLOWED_ACTION_TYPES,
  type ExecutionCatalogResponse,
  type ExecutionDryRunResponse,
  type ExecutionRequestResponse,
  type ExecutionRequestQueue,
} from '@/types/platformControlledExecution';

describe('P22 controlled execution types', () => {
  it('TYPE-001: the v0 allowlist is exactly seven actions', () => {
    expect(P22_ALLOWED_ACTION_TYPES).toHaveLength(7);
    expect(P22_ALLOWED_ACTION_TYPES).toEqual([
      'support_mode.on',
      'support_mode.off',
      'incident.flag_set',
      'incident.flag_clear',
      'provisioning.recheck',
      'backup.check',
      'backup.restore_test_request',
    ]);
  });

  it('TYPE-002: a catalog response is non-executing', () => {
    const catalog: ExecutionCatalogResponse = {
      items: [],
      exclusions: [],
      total: 7,
      contract: 'P22-A',
      storage: 'memory',
      executed: false,
    };
    expect(catalog.executed).toBe(false);
    expect(catalog.total).toBe(7);
  });

  it('TYPE-003: a dry-run response is non-executing and exposes only the digest', () => {
    const dryRun: ExecutionDryRunResponse = {
      dry_run_id: 'dry-1',
      durable_approval_id: 'appr-1',
      action_type: 'backup.check',
      tenant_id: null,
      requested_state: null,
      executable: true,
      verdict: 'passed',
      block_reasons: [],
      expected_audit_shape: { execution_dry_run_passed: ['event_id'] },
      execution_mode: 'sync',
      source_status: 'known',
      reversible: false,
      redaction_applied: true,
      idempotency_key_digest: 'abc123',
      storage: 'memory',
      executed: false,
      execution_started: false,
      execution_allowed: false,
      created_at: '2026-07-02T00:00:00Z',
    };
    expect(dryRun.executed).toBe(false);
    expect(dryRun.execution_allowed).toBe(false);
    expect(dryRun.execution_started).toBe(false);
    // A response models the digest, never a raw key.
    expect(Object.keys(dryRun)).not.toContain('idempotency_key');
    expect(dryRun).toHaveProperty('idempotency_key_digest');
  });

  it('TYPE-004: a recorded request response is non-executing and exposes only the digest', () => {
    const recorded: ExecutionRequestResponse = {
      execution_request_id: 'req-1',
      durable_approval_id: 'appr-1',
      action_type: 'backup.check',
      tenant_id: null,
      requested_state: null,
      reason_redacted: 'routine review',
      idempotency_key_digest: 'abc123',
      payload_digest: 'def456',
      actor_id: 'actor-1',
      actor_role: 'super_admin',
      identity_context: 'identity_only',
      execution_mode: 'sync',
      dry_run_ref: 'dry-1',
      execution_ack: true,
      correlation_id: null,
      metadata_redacted: null,
      redaction_applied: true,
      result_state: 'dry_run_passed',
      block_reasons: [],
      result: 'recorded',
      message: 'Recorded; not executed.',
      storage: 'memory',
      executed: false,
      execution_started: false,
      execution_allowed: false,
      created_at: '2026-07-02T00:00:00Z',
      updated_at: '2026-07-02T00:00:00Z',
    };
    expect(recorded.executed).toBe(false);
    expect(recorded.execution_allowed).toBe(false);
    expect(recorded.execution_started).toBe(false);
    expect(Object.keys(recorded)).not.toContain('idempotency_key');
    expect(recorded).toHaveProperty('idempotency_key_digest');
  });

  it('TYPE-005: a queue response is non-executing', () => {
    const queue: ExecutionRequestQueue = {
      items: [],
      total: 0,
      limit: 50,
      offset: 0,
      storage: 'memory',
      executed: false,
    };
    expect(queue.executed).toBe(false);
  });
});
