/**
 * P23-D: Platform operator tasks console component tests.
 *
 * Verifies the view-not-executor / record-not-delivery contract on the frontend:
 *   - title / subtitle / invariants (a task is a view not an executor; a
 *     notification is a record not a delivery; redaction_applied=true; no
 *     execute control; source_unknown never healthy; backup_check_warning never
 *     success)
 *   - the task queue renders, plus empty / loading / error states
 *   - filters apply to the list call
 *   - materialize calls the read-only materialize endpoint and renders the
 *     per-source summary
 *   - detail renders the redacted record, audit history, and notification events
 *   - acknowledge / complete transitions POST to the right endpoints with the
 *     actor never in the body
 *   - complete is gated on evidence + closed gate + confirmation; a 409 denial
 *     is surfaced cleanly inline
 *   - NO execute / run / apply / dispatch / trigger / send / deliver control
 *   - source_unknown is never styled healthy (never green); backup_check_warning
 *     is never styled success (never green) -- defended client-side even when
 *     the backend label drifts
 *   - redaction_applied=true is displayed
 *   - tenant-contextual / non-platform identities see no controls and no queue
 */
import { beforeEach, describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

vi.mock('@/services/api', () => ({
  api: {
    get: vi.fn().mockResolvedValue({ data: {} }),
    post: vi.fn().mockResolvedValue({ data: {} }),
  },
}));

import { api } from '@/services/api';
import { useAuthStore } from '@/stores/authStore';
import { PlatformOperatorTasksPage } from '@/pages/platform/PlatformOperatorTasksPage';

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
    <MemoryRouter initialEntries={['/platform/operator-tasks']}>
      <Routes>
        <Route path="/platform/operator-tasks" element={<PlatformOperatorTasksPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

const TASK_OPEN = {
  task_id: 't-1',
  task_type: 'approval_pending',
  severity: 'medium',
  state: 'open',
  display_status: 'healthy',
  tenant_id: 't-tenant',
  actor_scope: 'platform',
  owner_role: null,
  owner_actor_id: null,
  correlation_id: 'corr-1',
  linked_action_id: null,
  linked_approval_id: 'appr-1',
  linked_execution_id: null,
  linked_dry_run_ref: null,
  linked_source_ref: null,
  linked_incident_id: null,
  summary_redacted: '[redacted summary]',
  reason_redacted: null,
  evidence_ref: null,
  source_status: 'known',
  linked_gate_open: false,
  dedup_key_digest: 'abc123',
  ttl_expires_at: null,
  created_at: '2026-07-05T00:00:00Z',
  updated_at: '2026-07-05T00:00:00Z',
  redaction_applied: true,
};

const TASK_SOURCE_UNKNOWN = {
  ...TASK_OPEN,
  task_id: 't-su',
  task_type: 'source_unknown',
  severity: 'high',
  display_status: 'unknown',
  source_status: 'unknown',
};

const TASK_BACKUP_WARN = {
  ...TASK_OPEN,
  task_id: 't-bc',
  task_type: 'backup_check_warning',
  display_status: 'warning',
  source_status: 'degraded',
};

const AUDIT_EVENT = {
  event_id: 'evt-1',
  task_id: 't-1',
  task_type: 'approval_pending',
  actor_id: 'identity-super-admin',
  actor_role: 'super_admin',
  tenant_id: 't-tenant',
  transition: 'open->acknowledged',
  previous_state: 'open',
  next_state: 'acknowledged',
  reason_redacted: '[redacted]',
  denial_code: null,
  correlation_id: 'corr-1',
  linked_action_id: null,
  linked_approval_id: 'appr-1',
  linked_execution_id: null,
  linked_source_ref: null,
  linked_incident_id: null,
  redaction_applied: true,
  sequence_no: 1,
  created_at: '2026-07-05T00:00:00Z',
};

const NOTIF_EVENT = {
  event_id: 'ne-1',
  task_id: 't-1',
  channel: 'in_app',
  delivery_state: 'recorded',
  severity: 'medium',
  tenant_id: 't-tenant',
  actor_scope: 'platform',
  recipient_role: 'super_admin',
  summary_redacted: '[redacted notif]',
  correlation_id: 'corr-1',
  redaction_applied: true,
  created_at: '2026-07-05T00:00:00Z',
};

function detailFor(task: typeof TASK_OPEN, extra: Record<string, unknown> = {}) {
  return { ...task, ...extra, audit_events: [AUDIT_EVENT], notification_events: [NOTIF_EVENT] };
}

function queueWith(tasks: unknown[]) {
  return {
    tasks,
    total: tasks.length,
    active_count: tasks.length,
    limit: 50,
    offset: 0,
  };
}

const QUEUE = queueWith([TASK_OPEN]);
const EMPTY_QUEUE = queueWith([]);

// Route api.get by URL: list vs read-by-id.
function mockGet(listBody: unknown, detailBody: unknown = detailFor(TASK_OPEN)) {
  vi.mocked(api.get).mockImplementation((url) => {
    const u = typeof url === 'string' ? url : '';
    if (/\/operator-tasks\/[^/?]+$/.test(u)) return Promise.resolve({ data: detailBody });
    return Promise.resolve({ data: listBody });
  });
}

function deniedError(code: string, message = 'denied:complete') {
  return {
    response: {
      data: {
        detail: { code, message },
      },
    },
  };
}

describe('PlatformOperatorTasksPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setIdentityOperator();
    vi.mocked(api.get).mockResolvedValue({ data: QUEUE });
    vi.mocked(api.post).mockResolvedValue({ data: {} });
  });

  it('renders title, view-not-executor subtitle, and the console invariants', async () => {
    renderPage();
    expect(screen.getByTestId('ot-title')).toHaveTextContent('Operator Tasks');
    const subtitle = (screen.getByTestId('ot-subtitle').textContent ?? '').toLowerCase();
    expect(subtitle).toContain('view, not an executor');
    expect(subtitle).toContain('record, not a delivery');
    const invariants = (screen.getByTestId('ot-invariants').textContent ?? '').toLowerCase();
    expect(invariants).toContain('redaction_applied = true');
    expect(invariants).toContain('source_unknown is never healthy');
    expect(invariants).toContain('backup_check_warning is never success');
    expect(invariants).toContain('no execute');
    await screen.findByTestId('ot-queue-summary');
  });

  it('renders the task queue after load with redaction_applied shown', async () => {
    renderPage();
    const item = await screen.findByTestId('ot-queue-item');
    expect(item).toHaveTextContent('approval_pending');
    expect((screen.getByTestId('ot-queue-summary').textContent ?? '')).toContain('redaction_applied=true');
    expect(item.textContent ?? '').toContain('redaction_applied=true');
  });

  it('shows an empty-queue state when there are no tasks', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: EMPTY_QUEUE });
    renderPage();
    expect(await screen.findByTestId('ot-queue-empty')).toBeInTheDocument();
    expect(screen.queryByTestId('ot-queue-item')).not.toBeInTheDocument();
  });

  it('shows a loading skeleton before the queue resolves', () => {
    vi.mocked(api.get).mockReturnValue(new Promise(() => undefined));
    renderPage();
    expect(screen.getByTestId('ot-queue')).toBeInTheDocument();
    expect(screen.queryByTestId('ot-queue-summary')).not.toBeInTheDocument();
  });

  it('shows an error banner when the queue fails to load', async () => {
    vi.mocked(api.get).mockRejectedValue(new Error('network down'));
    renderPage();
    expect(await screen.findByTestId('ot-error')).toHaveTextContent('network down');
  });

  it('materialize calls the read-only materialize endpoint and renders the per-source summary', async () => {
    mockGet(QUEUE);
    vi.mocked(api.post).mockResolvedValue({
      data: {
        sources: [
          {
            source: 'p19_approvals',
            read: 3,
            created: 1,
            deduped: 1,
            skipped: 1,
            unavailable: 0,
            task_ids: ['t-1'],
          },
        ],
        total_created: 1,
        total_deduped: 1,
        total_skipped: 1,
        total_unavailable: 0,
        materialized_at: '2026-07-05T00:00:00Z',
      },
    });
    renderPage();
    await screen.findByTestId('ot-queue-item');
    fireEvent.click(screen.getByTestId('ot-materialize-btn'));
    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith('/platform/p23/operator-tasks/internal/materialize');
    });
    expect(await screen.findByTestId('ot-materialize-result')).toBeInTheDocument();
    expect((screen.getByTestId('ot-materialize-summary').textContent ?? '')).toContain('created=1');
    expect(screen.getByTestId('ot-materialize-source').textContent ?? '').toContain('p19_approvals');
  });

  it('apply filters forwards the selected filters to the list call', async () => {
    mockGet(QUEUE);
    renderPage();
    await screen.findByTestId('ot-queue-item');
    fireEvent.change(screen.getByTestId('ot-filter-severity'), { target: { value: 'high' } });
    fireEvent.change(screen.getByTestId('ot-filter-task-type'), { target: { value: 'source_unknown' } });
    fireEvent.click(screen.getByTestId('ot-filter-apply'));
    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith(
        '/platform/p23/operator-tasks',
        expect.objectContaining({
          params: expect.objectContaining({ severity: 'high', task_type: 'source_unknown' }),
        }),
      );
    });
  });

  it('reset clears the filters', async () => {
    mockGet(QUEUE);
    renderPage();
    await screen.findByTestId('ot-queue-item');
    fireEvent.change(screen.getByTestId('ot-filter-severity'), { target: { value: 'high' } });
    fireEvent.click(screen.getByTestId('ot-filter-reset'));
    await waitFor(() => {
      expect(api.get).toHaveBeenLastCalledWith(
        '/platform/p23/operator-tasks',
        expect.objectContaining({
          params: expect.objectContaining({ limit: 50, offset: 0, severity: undefined }),
        }),
      );
    });
  });

  it('view loads the detail with audit history and notification events', async () => {
    mockGet(QUEUE, detailFor(TASK_OPEN));
    renderPage();
    await screen.findByTestId('ot-queue-item');
    fireEvent.click(screen.getByTestId('ot-view-btn'));
    expect(await screen.findByTestId('ot-detail')).toBeInTheDocument();
    expect(screen.getByTestId('ot-detail-grid').textContent ?? '').toContain('task_id');
    expect(screen.getByTestId('ot-audit-list').textContent ?? '').toContain('open->acknowledged');
    expect(screen.getByTestId('ot-notification-list').textContent ?? '').toContain('recorded');
    // Notification events are surfaced as records, not deliveries.
    const notifText = (screen.getByTestId('ot-notification-list').textContent ?? '').toLowerCase();
    expect(notifText).toContain('records, not deliveries');
  });

  it('acknowledge submits to the acknowledge endpoint with no actor in the body', async () => {
    mockGet(QUEUE, detailFor(TASK_OPEN));
    vi.mocked(api.post).mockResolvedValue({
      data: {
        accepted: true,
        task: { ...TASK_OPEN, state: 'acknowledged' },
        transition: 'open->acknowledged',
        previous_state: 'open',
        next_state: 'acknowledged',
        denial_code: null,
      },
    });
    renderPage();
    await screen.findByTestId('ot-queue-item');
    fireEvent.click(screen.getByTestId('ot-view-btn'));
    await screen.findByTestId('ot-detail');
    fireEvent.click(screen.getByTestId('ot-ack-btn'));
    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        '/platform/p23/operator-tasks/t-1/acknowledge',
        expect.not.objectContaining({ actor_id: expect.anything() }),
      );
    });
    expect(await screen.findByTestId('ot-transition-ok')).toHaveTextContent('Acknowledge');
  });

  it('a 409 transition denial is surfaced cleanly inline with the denial code', async () => {
    mockGet(QUEUE, detailFor(TASK_OPEN));
    vi.mocked(api.post).mockRejectedValue(
      deniedError('TRANSITION_DENIED_INVALID', 'denied:acknowledge'),
    );
    renderPage();
    await screen.findByTestId('ot-queue-item');
    fireEvent.click(screen.getByTestId('ot-view-btn'));
    await screen.findByTestId('ot-detail');
    fireEvent.click(screen.getByTestId('ot-ack-btn'));
    expect(await screen.findByTestId('ot-denial')).toHaveTextContent('TRANSITION_DENIED_INVALID');
    expect(screen.getByTestId('ot-denial').textContent ?? '').toContain('not changed');
  });

  it('complete is disabled until evidence and confirmation are provided', async () => {
    const inProgress = { ...TASK_OPEN, state: 'in_progress' };
    mockGet(QUEUE, detailFor(inProgress, { state: 'in_progress' }));
    renderPage();
    await screen.findByTestId('ot-queue-item');
    fireEvent.click(screen.getByTestId('ot-view-btn'));
    await screen.findByTestId('ot-complete');
    expect(screen.getByTestId('ot-complete-btn')).toBeDisabled();
    fireEvent.change(screen.getByTestId('ot-evidence-input'), { target: { value: 'checked source' } });
    expect(screen.getByTestId('ot-complete-btn')).toBeDisabled();
    fireEvent.click(screen.getByTestId('ot-complete-confirm'));
    expect(screen.getByTestId('ot-complete-btn')).not.toBeDisabled();
  });

  it('complete posts the evidence payload to the complete endpoint', async () => {
    const inProgress = { ...TASK_OPEN, state: 'in_progress' };
    mockGet(QUEUE, detailFor(inProgress, { state: 'in_progress' }));
    vi.mocked(api.post).mockResolvedValue({
      data: {
        accepted: true,
        task: { ...inProgress, state: 'completed', display_status: 'completed' },
        transition: 'in_progress->completed',
        previous_state: 'in_progress',
        next_state: 'completed',
        denial_code: null,
      },
    });
    renderPage();
    await screen.findByTestId('ot-queue-item');
    fireEvent.click(screen.getByTestId('ot-view-btn'));
    await screen.findByTestId('ot-complete');
    fireEvent.change(screen.getByTestId('ot-evidence-input'), { target: { value: 'checked source' } });
    fireEvent.click(screen.getByTestId('ot-complete-confirm'));
    fireEvent.click(screen.getByTestId('ot-complete-btn'));
    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        '/platform/p23/operator-tasks/t-1/complete',
        expect.objectContaining({ evidence: 'checked source' }),
      );
    });
  });

  it('a complete denial (gate open / no evidence) is surfaced with the denial code', async () => {
    const inProgress = { ...TASK_OPEN, state: 'in_progress' };
    mockGet(QUEUE, detailFor(inProgress, { state: 'in_progress' }));
    vi.mocked(api.post).mockRejectedValue(
      deniedError('COMPLETE_DENIED_GATE_OPEN'),
    );
    renderPage();
    await screen.findByTestId('ot-queue-item');
    fireEvent.click(screen.getByTestId('ot-view-btn'));
    await screen.findByTestId('ot-complete');
    fireEvent.change(screen.getByTestId('ot-evidence-input'), { target: { value: 'done' } });
    fireEvent.click(screen.getByTestId('ot-complete-confirm'));
    fireEvent.click(screen.getByTestId('ot-complete-btn'));
    expect(await screen.findByTestId('ot-denial')).toHaveTextContent('COMPLETE_DENIED_GATE_OPEN');
  });

  it('complete is blocked while the linked gate is open (warning + disabled)', async () => {
    const inProgress = { ...TASK_OPEN, state: 'in_progress', linked_gate_open: true };
    mockGet(QUEUE, detailFor(inProgress, { state: 'in_progress', linked_gate_open: true }));
    renderPage();
    await screen.findByTestId('ot-queue-item');
    fireEvent.click(screen.getByTestId('ot-view-btn'));
    await screen.findByTestId('ot-complete');
    expect(screen.getByTestId('ot-gate-warning')).toBeInTheDocument();
    fireEvent.change(screen.getByTestId('ot-evidence-input'), { target: { value: 'done' } });
    fireEvent.click(screen.getByTestId('ot-complete-confirm'));
    expect(screen.getByTestId('ot-complete-btn')).toBeDisabled();
  });

  it('a terminal task shows no transition controls', async () => {
    const completed = { ...TASK_OPEN, state: 'completed', display_status: 'completed' };
    mockGet(queueWith([completed]), detailFor(completed, { state: 'completed', display_status: 'completed' }));
    renderPage();
    await screen.findByTestId('ot-queue-item');
    fireEvent.click(screen.getByTestId('ot-view-btn'));
    await screen.findByTestId('ot-detail');
    expect(screen.getByTestId('ot-terminal-note')).toBeInTheDocument();
    expect(screen.queryByTestId('ot-transitions')).not.toBeInTheDocument();
    expect(screen.queryByTestId('ot-ack-btn')).not.toBeInTheDocument();
  });

  it('source_unknown is never styled healthy (display badge never green)', async () => {
    const su = { ...TASK_SOURCE_UNKNOWN };
    mockGet(queueWith([su]), detailFor(su));
    renderPage();
    const item = await screen.findByTestId('ot-queue-item');
    const badge = item.querySelector('[data-testid="ot-display-badge"]') as HTMLElement;
    expect(badge.getAttribute('data-tone')).toBe('gray');
    expect(badge.className).not.toContain('green');
  });

  it('backup_check_warning is never styled success (display badge never green)', async () => {
    const bc = { ...TASK_BACKUP_WARN };
    mockGet(queueWith([bc]), detailFor(bc));
    renderPage();
    const item = await screen.findByTestId('ot-queue-item');
    const badge = item.querySelector('[data-testid="ot-display-badge"]') as HTMLElement;
    expect(badge.getAttribute('data-tone')).toBe('yellow');
    expect(badge.className).not.toContain('green');
  });

  it('source_unknown stays non-green even if the backend label drifts to healthy (client-side defense)', async () => {
    // Malformed response: source_unknown with a (wrong) display_status 'healthy'.
    const drifted = { ...TASK_SOURCE_UNKNOWN, display_status: 'healthy' as never };
    mockGet(queueWith([drifted]), detailFor(drifted));
    renderPage();
    const item = await screen.findByTestId('ot-queue-item');
    const badge = item.querySelector('[data-testid="ot-display-badge"]') as HTMLElement;
    expect(badge.className).not.toContain('green');
    expect(badge.getAttribute('data-tone')).toBe('gray');
  });

  it('a normal healthy task IS styled green (sanity that green is type-gated, not removed)', async () => {
    mockGet(QUEUE, detailFor(TASK_OPEN));
    renderPage();
    const item = await screen.findByTestId('ot-queue-item');
    const badge = item.querySelector('[data-testid="ot-display-badge"]') as HTMLElement;
    expect(badge.className).toContain('green');
  });

  it('renders no execute / run / apply / dispatch / trigger / send / deliver control', async () => {
    mockGet(QUEUE, detailFor(TASK_OPEN));
    renderPage();
    await screen.findByTestId('ot-queue-item');
    fireEvent.click(screen.getByTestId('ot-view-btn'));
    await screen.findByTestId('ot-detail');
    // No button is labelled with a bare execute-class verb. Substrings inside a
    // larger label (e.g. "Apply filters") are fine; a button literally named
    // Execute / Run / Apply / Dispatch / Trigger / Send / Deliver is not.
    const bareVerb = /^(execute|run|apply|dispatch|trigger|send|deliver)$/i;
    for (const btn of screen.queryAllByRole('button')) {
      const label = (btn.textContent ?? '').trim();
      expect(bareVerb.test(label)).toBe(false);
    }
  });

  it('hides all controls for a tenant-contextual identity and does not load the queue', () => {
    setTenantContextualOperator();
    vi.mocked(api.get).mockResolvedValue({ data: QUEUE });
    renderPage();
    expect(screen.getByTestId('ot-no-access')).toBeInTheDocument();
    expect(screen.queryByTestId('ot-queue')).not.toBeInTheDocument();
    expect(screen.queryByTestId('ot-materialize-btn')).not.toBeInTheDocument();
    expect(screen.queryByTestId('ot-ack-btn')).not.toBeInTheDocument();
    expect(api.get).not.toHaveBeenCalled();
  });

  it('list and read call the correct P23 endpoints', async () => {
    mockGet(QUEUE, detailFor(TASK_OPEN));
    renderPage();
    await screen.findByTestId('ot-queue-item');
    expect(api.get).toHaveBeenCalledWith(
      '/platform/p23/operator-tasks',
      expect.objectContaining({ params: expect.objectContaining({ limit: 50, offset: 0 }) }),
    );
    fireEvent.click(screen.getByTestId('ot-view-btn'));
    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith('/platform/p23/operator-tasks/t-1');
    });
  });
});
