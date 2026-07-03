/**
 * P22-C: Controlled Execution API client tests.
 *
 * Verifies that platformService calls the P22 endpoints with the correct URL,
 * params, and body, and that every typed response is treated as non-executing
 * (executed / execution_allowed / execution_started === false). No real network
 * calls: the api module is mocked via vi.fn().
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock the api module (both get and post are exercised by the P22 client).
vi.mock('@/services/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

import { platformService } from '@/services/platformApi';
import { api } from '@/services/api';

const mockGet = vi.mocked(api.get);
const mockPost = vi.mocked(api.post);

beforeEach(() => {
  vi.clearAllMocks();
});

describe('platformService P22 controlled execution', () => {
  it('P22-001: getExecutionCatalog calls GET /platform/p22/execution/catalog', async () => {
    mockGet.mockResolvedValueOnce({ data: { items: [], exclusions: [], total: 7 } });
    await platformService.getExecutionCatalog();
    expect(mockGet).toHaveBeenCalledWith('/platform/p22/execution/catalog');
  });

  it('P22-002: dryRunExecution calls POST /platform/p22/execution/dry-run with the payload', async () => {
    mockPost.mockResolvedValueOnce({ data: { verdict: 'blocked', executed: false } });
    const payload = {
      durable_approval_id: 'appr-1',
      action_type: 'backup.check',
      reason: 'routine review',
      idempotency_key: 'key-1',
      execution_mode: 'sync',
    };
    await platformService.dryRunExecution(payload);
    expect(mockPost).toHaveBeenCalledWith('/platform/p22/execution/dry-run', payload);
  });

  it('P22-003: recordExecutionRequest calls POST /platform/p22/execution/requests with the payload', async () => {
    mockPost.mockResolvedValueOnce({ data: { result_state: 'dry_run_passed', executed: false } });
    const payload = {
      durable_approval_id: 'appr-1',
      action_type: 'backup.check',
      reason: 'routine review',
      idempotency_key: 'key-1',
      dry_run_ref: 'dry-1',
      execution_ack: true,
      execution_mode: 'sync',
    };
    await platformService.recordExecutionRequest(payload);
    expect(mockPost).toHaveBeenCalledWith('/platform/p22/execution/requests', payload);
  });

  it('P22-004: listExecutionRequests uses default limit=50 offset=0 and no filters', async () => {
    mockGet.mockResolvedValueOnce({ data: { items: [], total: 0, limit: 50, offset: 0 } });
    await platformService.listExecutionRequests();
    expect(mockGet).toHaveBeenCalledWith('/platform/p22/execution/requests', {
      params: { limit: 50, offset: 0 },
    });
  });

  it('P22-005: listExecutionRequests forwards limit/offset and optional filters', async () => {
    mockGet.mockResolvedValueOnce({ data: { items: [], total: 0, limit: 10, offset: 5 } });
    await platformService.listExecutionRequests(10, 5, {
      result_state: 'blocked',
      action_type: 'backup.check',
      durable_approval_id: 'appr-1',
    });
    expect(mockGet).toHaveBeenCalledWith('/platform/p22/execution/requests', {
      params: {
        limit: 10,
        offset: 5,
        result_state: 'blocked',
        action_type: 'backup.check',
        durable_approval_id: 'appr-1',
      },
    });
  });

  it('P22-006: getExecutionRequest calls GET /platform/p22/execution/requests/:id', async () => {
    mockGet.mockResolvedValueOnce({ data: { execution_request_id: 'req-1', executed: false } });
    await platformService.getExecutionRequest('req-1');
    expect(mockGet).toHaveBeenCalledWith('/platform/p22/execution/requests/req-1');
  });

  it('P22-007: a catalog response is modelled as non-executing', async () => {
    // Contract fidelity: the typed catalog carries executed === false.
    const catalog = {
      items: [],
      exclusions: [],
      total: 7,
      contract: 'P22-A',
      storage: 'memory',
      executed: false,
    };
    mockGet.mockResolvedValueOnce({ data: catalog });
    const res = await platformService.getExecutionCatalog();
    expect(res.data.executed).toBe(false);
    expect(res.data.total).toBe(7);
  });

  it('P22-008: a recorded request response is modelled as non-executing', async () => {
    const recorded = {
      execution_request_id: 'req-1',
      result_state: 'dry_run_passed',
      result: 'recorded',
      executed: false,
      execution_started: false,
      execution_allowed: false,
    };
    mockPost.mockResolvedValueOnce({ data: recorded });
    const res = await platformService.recordExecutionRequest({
      durable_approval_id: 'appr-1',
      action_type: 'backup.check',
      reason: 'routine review',
      idempotency_key: 'key-1',
      dry_run_ref: 'dry-1',
      execution_ack: true,
      execution_mode: 'sync',
    });
    expect(res.data.executed).toBe(false);
    expect(res.data.execution_allowed).toBe(false);
    expect(res.data.execution_started).toBe(false);
    expect(res.data.result_state).toBe('dry_run_passed');
  });

  it('P22-E4-001: getBackupCheckSource calls GET /platform/p22/backup-check/source with no params when tenantId is omitted', async () => {
    mockGet.mockResolvedValueOnce({ data: { source_status: 'unknown', source_summary: 'unknown' } });
    await platformService.getBackupCheckSource();
    expect(mockGet).toHaveBeenCalledWith('/platform/p22/backup-check/source', {
      params: undefined,
    });
  });

  it('P22-E4-002: getBackupCheckSource forwards tenant_id when provided (blank is treated as platform-wide)', async () => {
    mockGet.mockResolvedValueOnce({ data: { source_status: 'known', source_summary: 'fresh_success' } });
    await platformService.getBackupCheckSource('  tenant-abc  ');
    expect(mockGet).toHaveBeenCalledWith('/platform/p22/backup-check/source', {
      params: { tenant_id: 'tenant-abc' },
    });
    // A blank tenantId is normalized to platform-wide (no param).
    mockGet.mockResolvedValueOnce({ data: { source_status: 'unknown', source_summary: 'unknown' } });
    await platformService.getBackupCheckSource('   ');
    expect(mockGet).toHaveBeenLastCalledWith('/platform/p22/backup-check/source', {
      params: undefined,
    });
  });

  it('P22-E4-003: a backup source response is modelled as non-executing and echo-safe', async () => {
    const source = {
      action_type: 'backup.check',
      action_class: 'read',
      binding: 'read_only_source_probe',
      adapter_result: 'not_implemented',
      source_status: 'known',
      source_summary: 'fresh_success',
      last_backup_status: 'success',
      last_backup_at: '2026-07-04T00:00:00Z',
      restore_test_status: 'passed',
      last_restore_test_at: '2026-07-03T00:00:00Z',
      failure_reason_redacted: null,
      export_available: true,
      retention_policy: '7 daily',
      p17_backup_source_status: 'available',
      realizes_execution: false,
      executed: false,
      execution_started: false,
      execution_allowed: false,
      result_state: 'blocked',
      read_only: true,
      redaction_applied: true,
      reason: null,
      checked_at: '2026-07-04T00:00:00Z',
    };
    mockGet.mockResolvedValueOnce({ data: source });
    const res = await platformService.getBackupCheckSource('tenant-abc');
    expect(res.data.executed).toBe(false);
    expect(res.data.execution_allowed).toBe(false);
    expect(res.data.execution_started).toBe(false);
    expect(res.data.realizes_execution).toBe(false);
    expect(res.data.result_state).toBe('blocked');
    expect(res.data.adapter_result).toBe('not_implemented');
    expect(res.data.source_status).toBe('known');
  });
});
