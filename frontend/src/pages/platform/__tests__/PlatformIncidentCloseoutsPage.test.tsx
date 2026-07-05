/**
 * P24-C: Platform incident closeouts console component tests.
 *
 * Verifies the view-not-executor / pointer-not-execution / record-not-repair
 * contract on the frontend:
 *   - title / subtitle / invariants (a closeout is a view not an executor; a
 *     runbook step is a pointer not an execution; redaction_applied=true; the
 *     flag is mirrored read-only; no execute control; source_unknown never
 *     healthy; backup_check_warning / degraded never success; blocked step
 *     never healthy; closed comes from the backend)
 *   - the closeout queue renders, plus empty / loading / error states
 *   - filters apply to the list call
 *   - detail renders the redacted record, audit history, and runbook steps
 *   - closeout transition happy path posts target_state (actor never in body);
 *     a 409 denial is surfaced cleanly inline; after a transition the detail is
 *     re-read from the backend (closed is never produced by frontend optimism)
 *   - step transition happy path posts to the step transition URL
 *   - an observation `done` step requires an evidence note (disabled until then)
 *   - source_unknown is never styled healthy; degraded/backup_check_warning is
 *     never styled success; a blocked step is never styled healthy (defended
 *     client-side even when the backend label drifts)
 *   - NO execute / run / apply / dispatch / trigger / approve / send / deliver /
 *     clear-flag control
 *   - redaction_applied=true is displayed
 *   - terminal closeouts show no transition controls; terminal steps show none
 *   - tenant-contextual / non-platform identities see no controls and no queue
 */
import { beforeEach, describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

vi.mock('@/services/api', () => ({
  api: {
    get: vi.fn().mockResolvedValue({ data: {} }),
    post: vi.fn().mockResolvedValue({ data: {} }),
  },
}));

import { api } from '@/services/api';
import { useAuthStore } from '@/stores/authStore';
import { PlatformIncidentCloseoutsPage } from '@/pages/platform/PlatformIncidentCloseoutsPage';

function setIdentityOperator() {
  useAuthStore.setState({
    user: {
      id: 'identity-super-admin',
      email: 'admin@mpango.com',
      full_name: 'Admin',
      roles: ['super_admin'],
      tenant_id: null,
      tenant_schema: null,
      permissions: [],
    },
    accessToken: 'test-token',
  });
}

function setTenantContextualOperator() {
  useAuthStore.setState({
    user: {
      id: 'ctx-admin',
      email: 'admin@mpango.com',
      full_name: 'Admin',
      roles: ['super_admin'],
      tenant_id: 'tenant-123',
      tenant_schema: 't_test',
      permissions: [],
    },
    accessToken: 'test-token',
  });
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/platform/incident-closeouts']}>
      <Routes>
        <Route
          path="/platform/incident-closeouts"
          element={<PlatformIncidentCloseoutsPage />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

const CLOSEOUT_AWAITING = {
  closeout_id: 'c-1',
  state: 'awaiting_closeout',
  display_status: 'healthy',
  classification: 'database',
  severity: 'medium',
  tenant_id: 't-tenant',
  actor_scope: 'platform',
  owner_role: null,
  owner_actor_id: null,
  correlation_id: 'corr-1',
  flag_observed: 'observed_false',
  flag_ever_set: false,
  linked_incident_id: 'inc-1',
  linked_triage_snapshot_ref: null,
  linked_handoff_ref: null,
  summary_redacted: '[redacted closeout summary]',
  reason_redacted: null,
  source_status: 'known',
  linked_execution_warning: false,
  dedup_key_digest: 'abc123',
  ttl_expires_at: null,
  linked_followup_task_id: null,
  followup_owed: false,
  created_at: '2026-07-06T00:00:00Z',
  updated_at: '2026-07-06T00:00:00Z',
  redaction_applied: true,
};

const CLOSEOUT_SOURCE_UNKNOWN = {
  ...CLOSEOUT_AWAITING,
  closeout_id: 'c-su',
  severity: 'high',
  display_status: 'unknown',
  source_status: 'unknown',
};

const CLOSEOUT_BACKUP_WARN = {
  ...CLOSEOUT_AWAITING,
  closeout_id: 'c-bc',
  display_status: 'warning',
  source_status: 'degraded',
  linked_execution_warning: true,
};

const AUDIT_EVENT = {
  event_id: 'evt-1',
  closeout_id: 'c-1',
  state: 'awaiting_closeout',
  actor_id: 'identity-super-admin',
  actor_role: 'super_admin',
  tenant_id: 't-tenant',
  transition: 'flagged_active->awaiting_closeout',
  previous_state: 'flagged_active',
  next_state: 'awaiting_closeout',
  flag_observed: 'observed_false',
  reason_redacted: '[redacted]',
  denial_code: null,
  correlation_id: 'corr-1',
  linked_incident_id: 'inc-1',
  linked_action_id: null,
  linked_approval_id: null,
  linked_execution_id: null,
  redaction_applied: true,
  sequence_no: 1,
  created_at: '2026-07-06T00:00:00Z',
};

const STEP_ACTION_POINTER = {
  step_id: 's-1',
  closeout_id: 'c-1',
  sequence_no: 1,
  step_kind: 'action_pointer',
  step_state: 'owed',
  display_status: 'healthy',
  tenant_id: 't-tenant',
  correlation_id: 'corr-1',
  linked_action_id: 'act-1',
  linked_approval_id: null,
  linked_execution_id: 'exec-1',
  linked_source_ref: null,
  evidence_ref: null,
  summary_redacted: '[redacted step summary]',
  reason_redacted: null,
  source_status: 'known',
  linked_execution_terminal: true,
  linked_approval_resolved: false,
  linked_execution_warning: false,
  dedup_key_digest: 'stepdigest1',
  linked_task_id: 't-step-1',
  created_at: '2026-07-06T00:00:00Z',
  updated_at: '2026-07-06T00:00:00Z',
  redaction_applied: true,
};

const STEP_OBSERVATION = {
  ...STEP_ACTION_POINTER,
  step_id: 's-2',
  sequence_no: 2,
  step_kind: 'observation',
  step_state: 'owed',
  linked_action_id: null,
  linked_execution_id: null,
  linked_execution_terminal: false,
  dedup_key_digest: 'stepdigest2',
};

const STEP_BLOCKED_SOURCE_UNKNOWN = {
  ...STEP_ACTION_POINTER,
  step_id: 's-3',
  sequence_no: 3,
  step_state: 'blocked',
  display_status: 'unknown',
  source_status: 'unknown',
  linked_action_id: null,
  linked_execution_id: null,
  dedup_key_digest: 'stepdigest3',
};

function detailFor(closeout: typeof CLOSEOUT_AWAITING, steps: unknown[] = []) {
  return {
    ...closeout,
    audit_events: [AUDIT_EVENT],
    steps,
  };
}

function listWith(closeouts: unknown[]) {
  return {
    closeouts,
    total: closeouts.length,
    active_count: closeouts.length,
    limit: 50,
    offset: 0,
  };
}

const LIST = listWith([CLOSEOUT_AWAITING]);
const EMPTY_LIST = listWith([]);

// Route api.get by URL: list vs read-by-id vs runbook.
function mockGet(listBody: unknown, detailBody: unknown = detailFor(CLOSEOUT_AWAITING, [STEP_ACTION_POINTER])) {
  vi.mocked(api.get).mockImplementation((url) => {
    const u = typeof url === 'string' ? url : '';
    if (/\/incident-closeouts\/[^/?]+$/.test(u)) return Promise.resolve({ data: detailBody });
    return Promise.resolve({ data: listBody });
  });
}

function deniedError(code: string, message = 'denied:close') {
  return {
    response: {
      data: {
        detail: { code, message },
      },
    },
  };
}

describe('PlatformIncidentCloseoutsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setIdentityOperator();
    vi.mocked(api.get).mockResolvedValue({ data: LIST });
    vi.mocked(api.post).mockResolvedValue({ data: {} });
  });

  it('renders title, view-not-executor subtitle, and the console invariants', async () => {
    renderPage();
    expect(screen.getByTestId('ic-title')).toHaveTextContent('Incident Closeouts');
    const subtitle = (screen.getByTestId('ic-subtitle').textContent ?? '').toLowerCase();
    expect(subtitle).toContain('view, not an executor');
    expect(subtitle).toContain('pointer, not an execution');
    expect(subtitle).toContain('record, not a repair');
    expect(subtitle).toContain('flag');
    const invariants = (screen.getByTestId('ic-invariants').textContent ?? '').toLowerCase();
    expect(invariants).toContain('redaction_applied = true');
    expect(invariants).toContain('source_unknown is never healthy');
    expect(invariants).toContain('backup_check_warning / degraded is never success');
    expect(invariants).toContain('no execute');
    await screen.findByTestId('ic-queue-summary');
  });

  it('renders the queue after load with redaction_applied shown', async () => {
    renderPage();
    const item = await screen.findByTestId('ic-queue-item');
    expect(item).toHaveTextContent('awaiting_closeout');
    expect((screen.getByTestId('ic-queue-summary').textContent ?? '')).toContain('redaction_applied=true');
    expect(item.textContent ?? '').toContain('redaction_applied=true');
  });

  it('shows an empty-queue state when there are no closeouts', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: EMPTY_LIST });
    renderPage();
    expect(await screen.findByTestId('ic-queue-empty')).toBeInTheDocument();
    expect(screen.queryByTestId('ic-queue-item')).not.toBeInTheDocument();
  });

  it('shows a loading skeleton before the queue resolves', () => {
    vi.mocked(api.get).mockReturnValue(new Promise(() => undefined));
    renderPage();
    expect(screen.getByTestId('ic-queue')).toBeInTheDocument();
    expect(screen.queryByTestId('ic-queue-summary')).not.toBeInTheDocument();
  });

  it('shows an error banner when the queue fails to load', async () => {
    vi.mocked(api.get).mockRejectedValue(new Error('network down'));
    renderPage();
    expect(await screen.findByTestId('ic-error')).toHaveTextContent('network down');
  });

  it('apply filters forwards the selected filters to the list call', async () => {
    mockGet(LIST);
    renderPage();
    await screen.findByTestId('ic-queue-item');
    fireEvent.change(screen.getByTestId('ic-filter-state'), { target: { value: 'awaiting_closeout' } });
    fireEvent.change(screen.getByTestId('ic-filter-severity'), { target: { value: 'high' } });
    fireEvent.click(screen.getByTestId('ic-filter-apply'));
    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith(
        '/platform/p24/incident-closeouts',
        expect.objectContaining({
          params: expect.objectContaining({
            state: 'awaiting_closeout',
            severity: 'high',
          }),
        }),
      );
    });
  });

  it('reset clears the filters', async () => {
    mockGet(LIST);
    renderPage();
    await screen.findByTestId('ic-queue-item');
    fireEvent.change(screen.getByTestId('ic-filter-severity'), { target: { value: 'high' } });
    fireEvent.click(screen.getByTestId('ic-filter-reset'));
    await waitFor(() => {
      expect(api.get).toHaveBeenLastCalledWith(
        '/platform/p24/incident-closeouts',
        expect.objectContaining({
          params: expect.objectContaining({ limit: 50, offset: 0, severity: undefined }),
        }),
      );
    });
  });

  it('view loads the detail with the redacted grid, audit history, and runbook steps', async () => {
    mockGet(LIST, detailFor(CLOSEOUT_AWAITING, [STEP_ACTION_POINTER]));
    renderPage();
    await screen.findByTestId('ic-queue-item');
    fireEvent.click(screen.getByTestId('ic-view-btn'));
    expect(await screen.findByTestId('ic-detail')).toBeInTheDocument();
    expect(screen.getByTestId('ic-detail-grid').textContent ?? '').toContain('closeout_id');
    expect(screen.getByTestId('ic-audit-list').textContent ?? '').toContain('flagged_active->awaiting_closeout');
    expect(screen.getByTestId('ic-runbook').textContent ?? '').toContain('action pointer');
  });

  it('list and read call the correct P24 endpoints', async () => {
    mockGet(LIST, detailFor(CLOSEOUT_AWAITING, []));
    renderPage();
    await screen.findByTestId('ic-queue-item');
    expect(api.get).toHaveBeenCalledWith(
      '/platform/p24/incident-closeouts',
      expect.objectContaining({ params: expect.objectContaining({ limit: 50, offset: 0 }) }),
    );
    fireEvent.click(screen.getByTestId('ic-view-btn'));
    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith('/platform/p24/incident-closeouts/c-1');
    });
  });

  it('closeout transition happy path posts target_state with the actor never in the body', async () => {
    mockGet(LIST, detailFor(CLOSEOUT_AWAITING, []));
    vi.mocked(api.post).mockResolvedValue({
      data: {
        closeout: { ...CLOSEOUT_AWAITING, state: 'in_remediation' },
        step: null,
        created: false,
        deduped: false,
        accepted: true,
        denial_code: null,
      },
    });
    renderPage();
    await screen.findByTestId('ic-queue-item');
    fireEvent.click(screen.getByTestId('ic-view-btn'));
    await screen.findByTestId('ic-transitions');
    fireEvent.change(screen.getByTestId('ic-closeout-target'), {
      target: { value: 'in_remediation' },
    });
    fireEvent.click(screen.getByTestId('ic-closeout-submit'));
    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        '/platform/p24/incident-closeouts/c-1/transition',
        expect.objectContaining({ target_state: 'in_remediation' }),
      );
    });
    // Actor never carried in the body.
    expect(api.post).toHaveBeenCalledWith(
      '/platform/p24/incident-closeouts/c-1/transition',
      expect.not.objectContaining({ actor_id: expect.anything() }),
    );
    expect(await screen.findByTestId('ic-transition-ok')).toBeInTheDocument();
  });

  it('a closeout transition to closed requires confirmation (disabled until confirmed)', async () => {
    mockGet(LIST, detailFor(CLOSEOUT_AWAITING, []));
    renderPage();
    await screen.findByTestId('ic-queue-item');
    fireEvent.click(screen.getByTestId('ic-view-btn'));
    await screen.findByTestId('ic-transitions');
    fireEvent.change(screen.getByTestId('ic-closeout-target'), { target: { value: 'closed' } });
    // gate is open? awaiting_closeout + source known + flag not ever set + no followup =>
    // gate closed here, so only the confirm gate applies.
    expect(screen.getByTestId('ic-closeout-submit')).toBeDisabled();
    fireEvent.click(screen.getByTestId('ic-close-confirm'));
    expect(screen.getByTestId('ic-closeout-submit')).not.toBeDisabled();
  });

  it('a 409 closeout denial is surfaced cleanly inline with the denial code', async () => {
    mockGet(LIST, detailFor(CLOSEOUT_AWAITING, []));
    vi.mocked(api.post).mockRejectedValue(
      deniedError('CLOSE_DENIED_FLAG_STILL_SET', 'denied:close'),
    );
    renderPage();
    await screen.findByTestId('ic-queue-item');
    fireEvent.click(screen.getByTestId('ic-view-btn'));
    await screen.findByTestId('ic-transitions');
    fireEvent.change(screen.getByTestId('ic-closeout-target'), { target: { value: 'closed' } });
    fireEvent.click(screen.getByTestId('ic-close-confirm'));
    fireEvent.click(screen.getByTestId('ic-closeout-submit'));
    expect(await screen.findByTestId('ic-denial')).toHaveTextContent(
      'CLOSE_DENIED_FLAG_STILL_SET',
    );
    expect(screen.getByTestId('ic-denial').textContent ?? '').toContain('not changed');
  });

  it('after a successful closeout transition the detail is re-read from the backend (no frontend optimism)', async () => {
    mockGet(LIST, detailFor(CLOSEOUT_AWAITING, []));
    vi.mocked(api.post).mockResolvedValue({
      data: {
        closeout: { ...CLOSEOUT_AWAITING, state: 'closed', display_status: 'closed' },
        step: null,
        created: false,
        deduped: false,
        accepted: true,
        denial_code: null,
      },
    });
    renderPage();
    await screen.findByTestId('ic-queue-item');
    fireEvent.click(screen.getByTestId('ic-view-btn'));
    await screen.findByTestId('ic-transitions');
    fireEvent.change(screen.getByTestId('ic-closeout-target'), { target: { value: 'closed' } });
    fireEvent.click(screen.getByTestId('ic-close-confirm'));
    fireEvent.click(screen.getByTestId('ic-closeout-submit'));
    // The page re-reads the detail from the backend after the transition.
    await waitFor(() => {
      const reads = vi.mocked(api.get).mock.calls.filter(
        ([url]) => typeof url === 'string' && url.endsWith('/incident-closeouts/c-1'),
      );
      expect(reads.length).toBeGreaterThanOrEqual(2);
    });
  });

  it('self-assign posts to the self-assign endpoint with no body', async () => {
    mockGet(LIST, detailFor(CLOSEOUT_AWAITING, []));
    vi.mocked(api.post).mockResolvedValue({
      data: { closeout: CLOSEOUT_AWAITING, step: null, created: false, deduped: false, accepted: true, denial_code: null },
    });
    renderPage();
    await screen.findByTestId('ic-queue-item');
    fireEvent.click(screen.getByTestId('ic-view-btn'));
    await screen.findByTestId('ic-transitions');
    fireEvent.click(screen.getByTestId('ic-self-assign-btn'));
    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        '/platform/p24/incident-closeouts/c-1/self-assign',
      );
    });
  });

  it('step transition happy path posts target_state to the step transition URL', async () => {
    mockGet(LIST, detailFor(CLOSEOUT_AWAITING, [STEP_ACTION_POINTER]));
    vi.mocked(api.post).mockResolvedValue({
      data: {
        closeout: CLOSEOUT_AWAITING,
        step: { ...STEP_ACTION_POINTER, step_state: 'done', display_status: 'completed' },
        created: false,
        deduped: false,
        accepted: true,
        denial_code: null,
      },
    });
    renderPage();
    await screen.findByTestId('ic-queue-item');
    fireEvent.click(screen.getByTestId('ic-view-btn'));
    const stepPanel = await screen.findByTestId('ic-step-transition');
    fireEvent.change(within(stepPanel).getByTestId('ic-step-target'), {
      target: { value: 'done' },
    });
    fireEvent.click(within(stepPanel).getByTestId('ic-step-submit'));
    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        '/platform/p24/incident-closeouts/c-1/runbook/s-1/transition',
        expect.objectContaining({ target_state: 'done' }),
      );
    });
  });

  it('a step done denial (gate open) is surfaced with the denial code', async () => {
    mockGet(LIST, detailFor(CLOSEOUT_AWAITING, [STEP_ACTION_POINTER]));
    vi.mocked(api.post).mockRejectedValue(deniedError('STEP_DONE_DENIED_GATE_OPEN'));
    renderPage();
    await screen.findByTestId('ic-queue-item');
    fireEvent.click(screen.getByTestId('ic-view-btn'));
    const stepPanel = await screen.findByTestId('ic-step-transition');
    fireEvent.change(within(stepPanel).getByTestId('ic-step-target'), {
      target: { value: 'done' },
    });
    fireEvent.click(within(stepPanel).getByTestId('ic-step-submit'));
    expect(await screen.findByTestId('ic-denial')).toHaveTextContent(
      'STEP_DONE_DENIED_GATE_OPEN',
    );
  });

  it('an observation done step requires an evidence note before it can be recorded', async () => {
    mockGet(LIST, detailFor(CLOSEOUT_AWAITING, [STEP_OBSERVATION]));
    renderPage();
    await screen.findByTestId('ic-queue-item');
    fireEvent.click(screen.getByTestId('ic-view-btn'));
    const stepPanel = await screen.findByTestId('ic-step-transition');
    fireEvent.change(within(stepPanel).getByTestId('ic-step-target'), {
      target: { value: 'done' },
    });
    // evidence input appears; submit disabled until evidence provided
    expect(within(stepPanel).getByTestId('ic-step-evidence')).toBeInTheDocument();
    expect(within(stepPanel).getByTestId('ic-step-submit')).toBeDisabled();
    fireEvent.change(within(stepPanel).getByTestId('ic-step-evidence'), {
      target: { value: 'verified manually' },
    });
    expect(within(stepPanel).getByTestId('ic-step-submit')).not.toBeDisabled();
  });

  it('source_unknown closeout is never styled healthy (display badge never green)', async () => {
    const su = { ...CLOSEOUT_SOURCE_UNKNOWN };
    mockGet(listWith([su]), detailFor(su, []));
    renderPage();
    const item = await screen.findByTestId('ic-queue-item');
    const badge = item.querySelector('[data-testid="ic-display-badge"]') as HTMLElement;
    expect(badge.getAttribute('data-tone')).toBe('gray');
    expect(badge.className).not.toContain('green');
  });

  it('source_unknown closeout stays non-green even if the backend label drifts to healthy', async () => {
    const drifted = { ...CLOSEOUT_SOURCE_UNKNOWN, display_status: 'healthy' as never };
    mockGet(listWith([drifted]), detailFor(drifted, []));
    renderPage();
    const item = await screen.findByTestId('ic-queue-item');
    const badge = item.querySelector('[data-testid="ic-display-badge"]') as HTMLElement;
    expect(badge.className).not.toContain('green');
    expect(badge.getAttribute('data-tone')).toBe('gray');
  });

  it('backup_check_warning / degraded closeout is never styled success (never green)', async () => {
    const bc = { ...CLOSEOUT_BACKUP_WARN };
    mockGet(listWith([bc]), detailFor(bc, []));
    renderPage();
    const item = await screen.findByTestId('ic-queue-item');
    const badge = item.querySelector('[data-testid="ic-display-badge"]') as HTMLElement;
    expect(badge.getAttribute('data-tone')).toBe('yellow');
    expect(badge.className).not.toContain('green');
  });

  it('a source_unknown blocked step is never styled healthy (display badge never green)', async () => {
    mockGet(LIST, detailFor(CLOSEOUT_AWAITING, [STEP_BLOCKED_SOURCE_UNKNOWN]));
    renderPage();
    await screen.findByTestId('ic-queue-item');
    fireEvent.click(screen.getByTestId('ic-view-btn'));
    const stepItem = await screen.findByTestId('ic-step-item');
    const badge = stepItem.querySelector(
      '[data-testid="ic-step-display-badge"]',
    ) as HTMLElement;
    expect(badge.className).not.toContain('green');
    expect(badge.getAttribute('data-tone')).toBe('gray');
  });

  it('a normal healthy closeout IS styled green (sanity that green is source-gated)', async () => {
    mockGet(LIST, detailFor(CLOSEOUT_AWAITING, []));
    renderPage();
    const item = await screen.findByTestId('ic-queue-item');
    const badge = item.querySelector('[data-testid="ic-display-badge"]') as HTMLElement;
    expect(badge.className).toContain('green');
  });

  it('renders no execute / run / apply / dispatch / trigger / approve / send / deliver / clear control', async () => {
    mockGet(LIST, detailFor(CLOSEOUT_AWAITING, [STEP_ACTION_POINTER]));
    renderPage();
    await screen.findByTestId('ic-queue-item');
    fireEvent.click(screen.getByTestId('ic-view-btn'));
    await screen.findByTestId('ic-detail');
    // No button is labelled with a bare execute/approve/send/deliver/clear verb.
    // Substrings inside a larger label (e.g. "Apply filters", "Record step
    // transition") are fine; a button literally named Execute/Run/Apply/
    // Dispatch/Trigger/Approve/Send/Deliver/Clear is not.
    const bareVerb = /^(execute|run|apply|dispatch|trigger|approve|send|deliver|clear|close)$/i;
    for (const btn of screen.queryAllByRole('button')) {
      const label = (btn.textContent ?? '').trim();
      expect(bareVerb.test(label)).toBe(false);
    }
  });

  it('a terminal closeout shows no transition controls', async () => {
    const closed = { ...CLOSEOUT_AWAITING, state: 'closed', display_status: 'closed' };
    mockGet(listWith([closed]), detailFor(closed, []));
    renderPage();
    await screen.findByTestId('ic-queue-item');
    fireEvent.click(screen.getByTestId('ic-view-btn'));
    await screen.findByTestId('ic-detail');
    expect(screen.getByTestId('ic-terminal-note')).toBeInTheDocument();
    expect(screen.queryByTestId('ic-transitions')).not.toBeInTheDocument();
    expect(screen.queryByTestId('ic-closeout-submit')).not.toBeInTheDocument();
  });

  it('a terminal step shows no step transition controls', async () => {
    const done = { ...STEP_ACTION_POINTER, step_state: 'done', display_status: 'completed' };
    mockGet(LIST, detailFor(CLOSEOUT_AWAITING, [done]));
    renderPage();
    await screen.findByTestId('ic-queue-item');
    fireEvent.click(screen.getByTestId('ic-view-btn'));
    await screen.findByTestId('ic-detail');
    expect(screen.getByTestId('ic-step-terminal')).toBeInTheDocument();
    expect(screen.queryAllByTestId('ic-step-transition').length).toBe(0);
    expect(screen.queryByTestId('ic-step-submit')).not.toBeInTheDocument();
  });

  it('hides all controls for a tenant-contextual identity and does not load the queue', () => {
    setTenantContextualOperator();
    vi.mocked(api.get).mockResolvedValue({ data: LIST });
    renderPage();
    expect(screen.getByTestId('ic-no-access')).toBeInTheDocument();
    expect(screen.queryByTestId('ic-queue')).not.toBeInTheDocument();
    expect(screen.queryByTestId('ic-closeout-submit')).not.toBeInTheDocument();
    expect(api.get).not.toHaveBeenCalled();
  });
});
