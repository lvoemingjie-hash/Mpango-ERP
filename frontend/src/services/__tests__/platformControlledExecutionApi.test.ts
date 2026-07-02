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
});
