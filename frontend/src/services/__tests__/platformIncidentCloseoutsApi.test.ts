/**
 * P24-C: Incident + Runbook Closeout API client tests.
 *
 * Verifies that platformService calls the P24 endpoints with the correct URL,
 * params, and body, and that every typed response is treated as a view, not an
 * executor (redaction_applied === true; transitions carry the backend verdict
 * accepted / denial_code; the actor is never sent in the body). No real network
 * calls: the api module is mocked via vi.fn().
 *
 * No intake endpoint is exercised here: intake is internal/system-only and is
 * out of scope for the operator console (P24-C).
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
import type {
  CloseoutTransitionRequest,
  StepTransitionRequest,
} from '@/types/platformIncidentCloseout';

const mockGet = vi.mocked(api.get);
const mockPost = vi.mocked(api.post);

beforeEach(() => {
  vi.clearAllMocks();
});

describe('platformService P24 incident closeouts', () => {
  it('P24-001: listIncidentCloseouts calls GET /platform/p24/incident-closeouts with default limit/offset', async () => {
    mockGet.mockResolvedValueOnce({
      data: { closeouts: [], total: 0, active_count: 0, limit: 50, offset: 0 },
    });
    await platformService.listIncidentCloseouts();
    expect(mockGet).toHaveBeenCalledWith('/platform/p24/incident-closeouts', {
      params: { limit: 50, offset: 0 },
    });
  });

  it('P24-002: listIncidentCloseouts forwards limit/offset and optional filters', async () => {
    mockGet.mockResolvedValueOnce({
      data: { closeouts: [], total: 0, active_count: 0, limit: 10, offset: 5 },
    });
    await platformService.listIncidentCloseouts(10, 5, {
      state: 'awaiting_closeout',
      classification: 'database',
      severity: 'high',
      tenant_id: 't-1',
      flag_observed: 'observed_true',
      owner_actor_id: 'op-1',
      correlation_id: 'corr-1',
    });
    expect(mockGet).toHaveBeenCalledWith('/platform/p24/incident-closeouts', {
      params: {
        limit: 10,
        offset: 5,
        state: 'awaiting_closeout',
        classification: 'database',
        severity: 'high',
        tenant_id: 't-1',
        flag_observed: 'observed_true',
        owner_actor_id: 'op-1',
        correlation_id: 'corr-1',
      },
    });
  });

  it('P24-003: getIncidentCloseout calls GET /platform/p24/incident-closeouts/:id', async () => {
    mockGet.mockResolvedValueOnce({
      data: { closeout_id: 'c-1', audit_events: [], steps: [] },
    });
    await platformService.getIncidentCloseout('c-1');
    expect(mockGet).toHaveBeenCalledWith('/platform/p24/incident-closeouts/c-1');
  });

  it('P24-004: getRunbook calls GET /platform/p24/incident-closeouts/:id/runbook', async () => {
    mockGet.mockResolvedValueOnce({ data: { closeout_id: 'c-1', steps: [] } });
    await platformService.getRunbook('c-1');
    expect(mockGet).toHaveBeenCalledWith('/platform/p24/incident-closeouts/c-1/runbook');
  });

  it('P24-005: selfAssignCloseout calls POST /:id/self-assign with NO body (actor from token)', async () => {
    mockPost.mockResolvedValueOnce({ data: { accepted: true } });
    await platformService.selfAssignCloseout('c-1');
    expect(mockPost).toHaveBeenCalledWith(
      '/platform/p24/incident-closeouts/c-1/self-assign',
    );
  });

  it('P24-006: transitionCloseout posts the closed target_state + reason (no actor in body)', async () => {
    mockPost.mockResolvedValueOnce({ data: { accepted: true } });
    const payload: CloseoutTransitionRequest = {
      target_state: 'awaiting_closeout',
      reason: 'triaged',
    };
    await platformService.transitionCloseout('c-1', payload);
    expect(mockPost).toHaveBeenCalledWith(
      '/platform/p24/incident-closeouts/c-1/transition',
      payload,
    );
    // The actor is never carried in the body (read from the token in the route).
    expect(payload).not.toHaveProperty('actor_id');
    expect(payload).not.toHaveProperty('actor_role');
  });

  it('P24-007: transitionCloseout sends only target_state when reason is omitted', async () => {
    mockPost.mockResolvedValueOnce({ data: { accepted: true } });
    await platformService.transitionCloseout('c-1', { target_state: 'withdrawn' });
    expect(mockPost).toHaveBeenCalledWith(
      '/platform/p24/incident-closeouts/c-1/transition',
      { target_state: 'withdrawn' },
    );
  });

  it('P24-008: transitionRunbookStep posts to the step transition URL with target + evidence', async () => {
    mockPost.mockResolvedValueOnce({ data: { accepted: true } });
    const payload: StepTransitionRequest = {
      target_state: 'done',
      evidence: 'verified terminal exec',
      reason: 'ok',
    };
    await platformService.transitionRunbookStep('c-1', 's-9', payload);
    expect(mockPost).toHaveBeenCalledWith(
      '/platform/p24/incident-closeouts/c-1/runbook/s-9/transition',
      payload,
    );
    expect(payload).not.toHaveProperty('actor_id');
  });

  it('P24-009: a list response is modelled with total / active_count and redacted closeouts', async () => {
    const list = {
      closeouts: [
        {
          closeout_id: 'c-1',
          state: 'awaiting_closeout',
          display_status: 'healthy',
          severity: 'high',
          source_status: 'known',
          linked_execution_warning: false,
          redaction_applied: true,
          summary_redacted: '[redacted]',
        },
      ],
      total: 1,
      active_count: 1,
      limit: 50,
      offset: 0,
    };
    mockGet.mockResolvedValueOnce({ data: list });
    const res = await platformService.listIncidentCloseouts();
    expect(res.data.total).toBe(1);
    expect(res.data.active_count).toBe(1);
    expect(res.data.closeouts[0].redaction_applied).toBe(true);
  });

  it('P24-010: a source_unknown closeout carries the honest unknown label (never healthy)', async () => {
    const list = {
      closeouts: [
        {
          closeout_id: 'c-su',
          state: 'awaiting_closeout',
          display_status: 'unknown',
          severity: 'high',
          source_status: 'unknown',
          linked_execution_warning: false,
          redaction_applied: true,
        },
      ],
      total: 1,
      active_count: 1,
      limit: 50,
      offset: 0,
    };
    mockGet.mockResolvedValueOnce({ data: list });
    const res = await platformService.listIncidentCloseouts();
    expect(res.data.closeouts[0].display_status).toBe('unknown');
    expect(res.data.closeouts[0].source_status).toBe('unknown');
  });

  it('P24-011: a transition success carries the backend verdict (accepted=true; view not executor)', async () => {
    mockPost.mockResolvedValueOnce({
      data: {
        closeout: {
          closeout_id: 'c-1',
          state: 'awaiting_closeout',
          display_status: 'healthy',
          redaction_applied: true,
        },
        step: null,
        created: false,
        deduped: false,
        accepted: true,
        denial_code: null,
      },
    });
    const res = await platformService.transitionCloseout('c-1', {
      target_state: 'awaiting_closeout',
    });
    expect(res.data.accepted).toBe(true);
    expect(res.data.denial_code).toBeNull();
    expect(res.data.closeout.redaction_applied).toBe(true);
  });

  it('P24-012: a denied transition is observable as the backend verdict (denial is a record, not an execute verdict)', async () => {
    // Denied transitions raise HTTPException (409) at the route; the API client
    // surfaces that as a thrown error whose body carries {detail:{code,message}}.
    // The success-shape denial_code field exists for the intake path; here we
    // confirm the typed response can carry an accepted=false verdict too.
    mockPost.mockResolvedValueOnce({
      data: {
        closeout: {
          closeout_id: 'c-1',
          state: 'awaiting_closeout',
          display_status: 'warning',
          redaction_applied: true,
        },
        step: null,
        created: false,
        deduped: false,
        accepted: false,
        denial_code: 'CLOSE_DENIED_FLAG_STILL_SET',
      },
    });
    const res = await platformService.transitionCloseout('c-1', {
      target_state: 'closed',
    });
    expect(res.data.accepted).toBe(false);
    expect(res.data.denial_code).toBe('CLOSE_DENIED_FLAG_STILL_SET');
  });

  it('P24-013: a step transition success carries the affected step (a pointer, not an execution)', async () => {
    mockPost.mockResolvedValueOnce({
      data: {
        closeout: {
          closeout_id: 'c-1',
          state: 'in_remediation',
          display_status: 'healthy',
          redaction_applied: true,
        },
        step: {
          step_id: 's-9',
          closeout_id: 'c-1',
          step_kind: 'action_pointer',
          step_state: 'done',
          display_status: 'completed',
          linked_execution_terminal: true,
          redaction_applied: true,
        },
        created: false,
        deduped: false,
        accepted: true,
        denial_code: null,
      },
    });
    const res = await platformService.transitionRunbookStep('c-1', 's-9', {
      target_state: 'done',
    });
    expect(res.data.accepted).toBe(true);
    expect(res.data.step?.step_state).toBe('done');
    expect(res.data.step?.linked_execution_terminal).toBe(true);
  });
});
