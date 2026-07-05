/**
 * P23-D: Operator Task / Notification Queue API client tests.
 *
 * Verifies that platformService calls the P23 endpoints with the correct URL,
 * params, and body, and that every typed response is treated as a view, not an
 * executor (redaction_applied === true; transitions carry accepted / denial_code;
 * materialize is a read-only summary). No real network calls: the api module is
 * mocked via vi.fn().
 *
 * No intake endpoint is exercised here: intake is internal/system-only and is
 * out of scope for the operator console (P23-D).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

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

describe('platformService P23 operator tasks', () => {
  it('P23-001: listOperatorTasks calls GET /platform/p23/operator-tasks with default limit/offset', async () => {
    mockGet.mockResolvedValueOnce({ data: { tasks: [], total: 0, active_count: 0, limit: 50, offset: 0 } });
    await platformService.listOperatorTasks();
    expect(mockGet).toHaveBeenCalledWith('/platform/p23/operator-tasks', {
      params: { limit: 50, offset: 0 },
    });
  });

  it('P23-002: listOperatorTasks forwards limit/offset and optional filters', async () => {
    mockGet.mockResolvedValueOnce({ data: { tasks: [], total: 0, active_count: 0, limit: 10, offset: 5 } });
    await platformService.listOperatorTasks(10, 5, {
      severity: 'high',
      task_type: 'source_unknown',
      state: 'open',
      source_status: 'unknown',
    });
    expect(mockGet).toHaveBeenCalledWith('/platform/p23/operator-tasks', {
      params: {
        limit: 10,
        offset: 5,
        severity: 'high',
        task_type: 'source_unknown',
        state: 'open',
        source_status: 'unknown',
      },
    });
  });

  it('P23-003: getOperatorTask calls GET /platform/p23/operator-tasks/:id', async () => {
    mockGet.mockResolvedValueOnce({ data: { task_id: 't-1', audit_events: [], notification_events: [] } });
    await platformService.getOperatorTask('t-1');
    expect(mockGet).toHaveBeenCalledWith('/platform/p23/operator-tasks/t-1');
  });

  it('P23-004: materializeOperatorTasks calls POST /platform/p23/operator-tasks/internal/materialize', async () => {
    mockPost.mockResolvedValueOnce({
      data: { sources: [], total_created: 0, total_deduped: 0, total_skipped: 0, total_unavailable: 0, materialized_at: '2026-07-05T00:00:00Z' },
    });
    await platformService.materializeOperatorTasks();
    expect(mockPost).toHaveBeenCalledWith(
      '/platform/p23/operator-tasks/internal/materialize',
    );
  });

  it('P23-005: acknowledgeOperatorTask calls POST /:id/acknowledge with the payload (actor never in body)', async () => {
    mockPost.mockResolvedValueOnce({ data: { accepted: true, transition: 'open->acknowledged' } });
    const payload = { reason: 'looking at it' };
    await platformService.acknowledgeOperatorTask('t-1', payload);
    expect(mockPost).toHaveBeenCalledWith(
      '/platform/p23/operator-tasks/t-1/acknowledge',
      payload,
    );
  });

  it('P23-006: acknowledgeOperatorTask defaults the body to {} (no identity field)', async () => {
    mockPost.mockResolvedValueOnce({ data: { accepted: true } });
    await platformService.acknowledgeOperatorTask('t-1');
    expect(mockPost).toHaveBeenCalledWith(
      '/platform/p23/operator-tasks/t-1/acknowledge',
      {},
    );
  });

  it('P23-007: selfAssignOperatorTask calls POST /:id/self-assign', async () => {
    mockPost.mockResolvedValueOnce({ data: { accepted: true } });
    await platformService.selfAssignOperatorTask('t-1');
    expect(mockPost).toHaveBeenCalledWith(
      '/platform/p23/operator-tasks/t-1/self-assign',
      {},
    );
  });

  it('P23-008: markOperatorTaskInProgress calls POST /:id/in-progress', async () => {
    mockPost.mockResolvedValueOnce({ data: { accepted: true } });
    await platformService.markOperatorTaskInProgress('t-1', { reason: 'triaging' });
    expect(mockPost).toHaveBeenCalledWith(
      '/platform/p23/operator-tasks/t-1/in-progress',
      { reason: 'triaging' },
    );
  });

  it('P23-009: completeOperatorTask calls POST /:id/complete with the evidence payload', async () => {
    mockPost.mockResolvedValueOnce({ data: { accepted: true } });
    const payload = { evidence: 'checked source', evidence_ref: 'note:abc123' };
    await platformService.completeOperatorTask('t-1', payload);
    expect(mockPost).toHaveBeenCalledWith(
      '/platform/p23/operator-tasks/t-1/complete',
      payload,
    );
  });

  it('P23-010: dismissOperatorTask calls POST /:id/dismiss', async () => {
    mockPost.mockResolvedValueOnce({ data: { accepted: true } });
    await platformService.dismissOperatorTask('t-1', { reason: 'duplicate' });
    expect(mockPost).toHaveBeenCalledWith(
      '/platform/p23/operator-tasks/t-1/dismiss',
      { reason: 'duplicate' },
    );
  });

  it('P23-011: a queue response is modelled with total / active_count and redacted tasks', async () => {
    const queue = {
      tasks: [
        {
          task_id: 't-1',
          task_type: 'source_unknown',
          severity: 'high',
          state: 'open',
          display_status: 'unknown',
          redaction_applied: true,
          summary_redacted: '[redacted]',
        },
      ],
      total: 1,
      active_count: 1,
      limit: 50,
      offset: 0,
    };
    mockGet.mockResolvedValueOnce({ data: queue });
    const res = await platformService.listOperatorTasks();
    expect(res.data.total).toBe(1);
    expect(res.data.active_count).toBe(1);
    expect(res.data.tasks[0].redaction_applied).toBe(true);
    // source_unknown -> display_status is the honest 'unknown' (never healthy).
    expect(res.data.tasks[0].display_status).toBe('unknown');
  });

  it('P23-012: a transition response carries accepted + denial_code (denial is observable, not an execute verdict)', async () => {
    const denied = {
      accepted: false,
      task: { task_id: 't-1', state: 'open', display_status: 'unknown', redaction_applied: true },
      transition: 'denied:complete',
      previous_state: 'open',
      next_state: 'open',
      denial_code: 'COMPLETE_DENIED_NO_EVIDENCE',
    };
    mockPost.mockResolvedValueOnce({ data: denied });
    const res = await platformService.completeOperatorTask('t-1', { evidence_ref: 'note:x' });
    expect(res.data.accepted).toBe(false);
    expect(res.data.denial_code).toBe('COMPLETE_DENIED_NO_EVIDENCE');
    expect(res.data.task.redaction_applied).toBe(true);
  });

  it('P23-013: a materialize summary is a read-only aggregate (no execute / delivery field)', async () => {
    const summary = {
      sources: [
        {
          source: 'p19_approvals',
          read: 3,
          created: 1,
          deduped: 1,
          skipped: 1,
          unavailable: 0,
          task_ids: ['t-1', 't-2'],
        },
      ],
      total_created: 1,
      total_deduped: 1,
      total_skipped: 1,
      total_unavailable: 0,
      materialized_at: '2026-07-05T00:00:00Z',
    };
    mockPost.mockResolvedValueOnce({ data: summary });
    const res = await platformService.materializeOperatorTasks();
    expect(res.data.total_created).toBe(1);
    expect(res.data.sources[0].source).toBe('p19_approvals');
    expect(res.data.sources[0].task_ids).toEqual(['t-1', 't-2']);
  });
});
