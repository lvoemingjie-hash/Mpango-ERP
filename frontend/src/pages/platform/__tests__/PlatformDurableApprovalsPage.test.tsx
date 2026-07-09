/**
 * P20-C: Platform durable approvals console component tests.
 *
 * Verifies the durability-is-not-execution + maker-checker contract on the
 * frontend:
 *   - title / subtitle / invariants (storage=memory, execution_allowed=false,
 *     execution_gate=blocked, executed=false, maker can never be a checker,
 *     quorum met is blocked from execution)
 *   - the durable approval queue renders, plus empty / loading / error states
 *   - create submits to the service with maker derived from the operator
 *   - maker-checker separation: the maker is offered NO decision control on an
 *     approval they opened (a distinct checker is required)
 *   - a non-maker checker approves / rejects only after explicit confirmation,
 *     to the right endpoints, with approver_id derived from the operator
 *   - a checker who already decided sees no further decision control
 *   - quorum progress is visualized (approve checkers / quorum_required)
 *   - NO execute / run / apply / dispatch / trigger control is rendered
 *   - approved_execution_blocked is shown as "execution blocked", never executed
 *   - quorum_met is styled red (the approved-vs-executed distinction)
 *   - executed=false, execution_allowed=false, execution_gate=blocked are shown
 *   - an unknown source_status or non-valid validation_status blocks approve
 *   - only the one-way digest is surfaced, never a raw idempotency key
 *   - service methods call the correct P20 endpoints
 *   - tenant-contextual / non-platform identities see no controls
 */
import { beforeEach, describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

// Mock the axios singleton so no real network call is made. platformService
// calls api.get / api.post under the hood.
vi.mock('@/services/api', () => ({
  api: {
    get: vi.fn().mockResolvedValue({ data: {} }),
    post: vi.fn().mockResolvedValue({ data: {} }),
  },
}));

import { api } from '@/services/api';
import { useAuthStore } from '@/stores/authStore';
import { PlatformDurableApprovalsPage } from '@/pages/platform/PlatformDurableApprovalsPage';

const OPERATOR_ID = 'identity-super-admin';
const OTHER_MAKER = 'other-super-admin';

function setIdentityOperator() {
  useAuthStore.setState({
    user: {
      id: OPERATOR_ID,
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
    <MemoryRouter initialEntries={['/platform/durable-approvals']}>
      <Routes>
        <Route path="/platform/durable-approvals" element={<PlatformDurableApprovalsPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

// A pending durable approval OPENED BY ANOTHER identity-only super_admin, so the
// current operator is a distinct potential checker.
const DURABLE_PENDING_OTHER = {
  approval_id: 'dap-1',
  action_id: 'aid-1',
  tenant_id: 't-1',
  action_type: 'tenant.pause',
  action_class: 'write',
  state: 'pending_review',
  maker: OTHER_MAKER,
  maker_at: '2026-06-25T00:00:00Z',
  checkers: [],
  quorum_required: 2,
  quorum_met: false,
  decision: null,
  reason: '[redacted]',
  request_digest: 'a'.repeat(64),
  idempotency_key_digest: 'b'.repeat(64),
  expires_at: '2099-01-01T00:00:00Z',
  durable_retain_until: '2099-01-01T00:00:00Z',
  execution_allowed: false,
  execution_gate: 'blocked',
  redaction_applied: true,
  storage: 'memory',
  retention_class: 'standard',
  validation_status: 'valid',
  superseded_by: null,
  previous_state: null,
  audit_event_id: 'evt-1',
  correlation_id: null,
  source_status: 'available',
  result: 'recorded',
  message: 'Recorded: the durable approval request was recorded at pending_review.',
  executed: false,
  created_at: '2026-06-25T00:00:00Z',
  updated_at: '2026-06-25T00:00:00Z',
};

// A pending durable approval the CURRENT operator opened -- they are the maker.
const DURABLE_PENDING_SELF = { ...DURABLE_PENDING_OTHER, approval_id: 'dap-self', maker: OPERATOR_ID };

// A quorum-met durable approval: approved_execution_blocked (the ceiling).
const DURABLE_QUORUM_MET = {
  ...DURABLE_PENDING_OTHER,
  approval_id: 'dap-quorum',
  state: 'approved_execution_blocked',
  quorum_met: true,
  decision: 'approve',
  result: 'approved',
  checkers: [
    {
      checker_id: 'checker-a',
      decided_at: '2026-06-25T00:01:00Z',
      decision: 'approve',
      reason_redacted: '[redacted]',
      audit_event_id: 'evt-2',
    },
    {
      checker_id: 'checker-b',
      decided_at: '2026-06-25T00:02:00Z',
      decision: 'approve',
      reason_redacted: '[redacted]',
      audit_event_id: 'evt-3',
    },
  ],
  message: 'Approved: resolved to approved_execution_blocked; not executed.',
};

// A pending approval the operator already decided (one approve recorded).
const DURABLE_PENDING_ALREADY_DECIDED = {
  ...DURABLE_PENDING_OTHER,
  approval_id: 'dap-decided',
  quorum_required: 2,
  checkers: [
    {
      checker_id: OPERATOR_ID,
      decided_at: '2026-06-25T00:01:00Z',
      decision: 'approve',
      reason_redacted: '[redacted]',
      audit_event_id: 'evt-4',
    },
  ],
};

const DURABLE_UNKNOWN_SOURCE = {
  ...DURABLE_PENDING_OTHER,
  approval_id: 'dap-unknown',
  source_status: 'unknown',
  validation_status: 'source_unknown',
};

function queueWith(items: unknown[]) {
  return {
    items,
    total: items.length,
    limit: 50,
    offset: 0,
    storage: 'memory',
    executed: false,
  };
}

const QUEUE = queueWith([DURABLE_PENDING_OTHER]);
const EMPTY_QUEUE = queueWith([]);

// Route api.get by URL: list vs read-by-id. The decision endpoint is a POST.
function mockGet(listBody: unknown, detailBody: unknown = DURABLE_PENDING_OTHER) {
  vi.mocked(api.get).mockImplementation((url) => {
    const u = typeof url === 'string' ? url : '';
    // read-by-id: /platform/p20/durable-approvals/{approval_id} (no /decisions)
    if (/\/durable-approvals\/[^/?]+$/.test(u)) return Promise.resolve({ data: detailBody });
    // list: /platform/p20/durable-approvals
    return Promise.resolve({ data: listBody });
  });
}

function fillCreateForm() {
  fireEvent.change(screen.getByTestId('dap-reason-input'), { target: { value: 'routine review' } });
  fireEvent.change(screen.getByTestId('dap-idempotency-input'), { target: { value: 'key-1' } });
  fireEvent.change(screen.getByTestId('dap-expires-input'), { target: { value: '2099-12-31T23:59' } });
  fireEvent.click(screen.getByTestId('dap-confirm-input'));
}

function fillDecisionForm() {
  fireEvent.change(screen.getByTestId('dap-decision-reason-input'), { target: { value: 'ok to approve' } });
  fireEvent.change(screen.getByTestId('dap-decision-idempotency-input'), { target: { value: 'dec-1' } });
  fireEvent.click(screen.getByTestId('dap-decision-confirm-input'));
}

describe('PlatformDurableApprovalsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setIdentityOperator();
    vi.mocked(api.get).mockResolvedValue({ data: QUEUE });
    vi.mocked(api.post).mockResolvedValue({ data: {} });
  });

  it('renders title, not-executed subtitle, and the console invariants', async () => {
    renderPage();
    expect(screen.getByTestId('dap-title')).toHaveTextContent('Durable Approvals');
    const subtitle = screen.getByTestId('dap-subtitle').textContent ?? '';
    expect(subtitle.toLowerCase()).toContain('not executed');
    const invariants = screen.getByTestId('dap-invariants').textContent ?? '';
    expect(invariants).toContain('storage = memory');
    expect(invariants).toContain('execution_allowed = false');
    expect(invariants).toContain('execution_gate = blocked');
    expect(invariants).toContain('executed = false');
    expect(invariants.toLowerCase()).toContain('maker can never be a checker');
    expect(invariants.toLowerCase()).toContain('quorum met is blocked from execution');
    await screen.findByTestId('dap-queue-summary');
  });

  it('renders the durable approval queue after load with quorum progress', async () => {
    renderPage();
    const item = await screen.findByTestId('dap-queue-item');
    expect(item).toHaveTextContent('tenant.pause');
    expect(screen.getByTestId('dap-queue-summary').textContent ?? '').toContain('storage=memory');
    expect(item.textContent ?? '').toContain('executed=false');
    expect(item.textContent ?? '').toContain('execution_allowed=false');
    // quorum progress is visualized (0 distinct approve checkers / required 2).
    const quorum = withinItemQuorum(item);
    expect(quorum.textContent ?? '').toContain('0/2');
  });

  it('shows an empty-queue state when there are no durable approvals', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: EMPTY_QUEUE });
    renderPage();
    expect(await screen.findByTestId('dap-queue-empty')).toBeInTheDocument();
    expect(screen.queryByTestId('dap-queue-item')).not.toBeInTheDocument();
  });

  it('shows a loading skeleton before the queue resolves', () => {
    vi.mocked(api.get).mockReturnValue(new Promise(() => undefined));
    renderPage();
    expect(screen.getByTestId('dap-queue')).toBeInTheDocument();
    expect(screen.queryByTestId('dap-queue-summary')).not.toBeInTheDocument();
  });

  it('shows an error banner when the queue fails to load', async () => {
    vi.mocked(api.get).mockRejectedValue(new Error('network down'));
    renderPage();
    expect(await screen.findByTestId('dap-error')).toHaveTextContent('network down');
  });

  it('create submits to the create endpoint with operator-derived maker', async () => {
    mockGet(QUEUE);
    vi.mocked(api.post).mockResolvedValue({ data: DURABLE_PENDING_SELF });
    renderPage();
    await screen.findByTestId('dap-queue-item');
    fillCreateForm();
    fireEvent.click(screen.getByTestId('dap-create-btn'));
    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        '/platform/p20/durable-approvals',
        expect.objectContaining({
          action_type: 'tenant.pause',
          maker: OPERATOR_ID,
          reason: 'routine review',
          idempotency_key: 'key-1',
          confirm: true,
        }),
      );
    });
    expect(await screen.findByTestId('dap-create-result')).toBeInTheDocument();
  });

  it('create is disabled until reason, idempotency, expiry, and confirm are provided', async () => {
    renderPage();
    await screen.findByTestId('dap-queue-item');
    expect(screen.getByTestId('dap-create-btn')).toBeDisabled();
    fireEvent.change(screen.getByTestId('dap-reason-input'), { target: { value: 'r' } });
    fireEvent.change(screen.getByTestId('dap-idempotency-input'), { target: { value: 'k' } });
    expect(screen.getByTestId('dap-create-btn')).toBeDisabled();
    fireEvent.click(screen.getByTestId('dap-confirm-input'));
    expect(screen.getByTestId('dap-create-btn')).not.toBeDisabled();
  });

  it('maker-checker: the maker is offered NO decision control on their own request', async () => {
    mockGet(queueWith([DURABLE_PENDING_SELF]), DURABLE_PENDING_SELF);
    renderPage();
    await screen.findByTestId('dap-queue-item');
    fireEvent.click(screen.getByTestId('dap-review-btn'));
    expect(await screen.findByTestId('dap-maker-blocked')).toBeInTheDocument();
    // No decision controls for the maker.
    expect(screen.queryByTestId('dap-approve-btn')).not.toBeInTheDocument();
    expect(screen.queryByTestId('dap-reject-btn')).not.toBeInTheDocument();
  });

  it('a non-maker checker approves only after confirmation, to the decisions endpoint', async () => {
    mockGet(QUEUE, DURABLE_PENDING_OTHER);
    vi.mocked(api.post).mockResolvedValue({ data: DURABLE_QUORUM_MET });
    renderPage();
    await screen.findByTestId('dap-queue-item');
    fireEvent.click(screen.getByTestId('dap-review-btn'));
    await screen.findByTestId('dap-decision');
    expect(screen.getByTestId('dap-approve-btn')).toBeDisabled();
    fillDecisionForm();
    fireEvent.click(screen.getByTestId('dap-approve-btn'));
    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        '/platform/p20/durable-approvals/dap-1/decisions',
        expect.objectContaining({
          decision: 'approve',
          approver_id: OPERATOR_ID,
          reason: 'ok to approve',
          idempotency_key: 'dec-1',
          confirm: true,
        }),
      );
    });
    const result = await screen.findByTestId('dap-decision-result');
    expect(result.textContent ?? '').toContain('execution blocked');
    expect(screen.getByTestId('dap-not-executed').textContent ?? '').toContain('executed=false');
  });

  it('reject submits to the decisions endpoint with decision reject', async () => {
    mockGet(QUEUE, DURABLE_PENDING_OTHER);
    vi.mocked(api.post).mockResolvedValue({
      data: { ...DURABLE_PENDING_OTHER, state: 'rejected', decision: 'reject', result: 'rejected' },
    });
    renderPage();
    await screen.findByTestId('dap-queue-item');
    fireEvent.click(screen.getByTestId('dap-review-btn'));
    await screen.findByTestId('dap-decision');
    fillDecisionForm();
    fireEvent.click(screen.getByTestId('dap-reject-btn'));
    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        '/platform/p20/durable-approvals/dap-1/decisions',
        expect.objectContaining({ decision: 'reject', confirm: true, approver_id: OPERATOR_ID }),
      );
    });
    expect(await screen.findByTestId('dap-decision-result')).toHaveTextContent('rejected');
  });

  it('a checker who already decided sees no further decision control', async () => {
    mockGet(queueWith([DURABLE_PENDING_ALREADY_DECIDED]), DURABLE_PENDING_ALREADY_DECIDED);
    renderPage();
    await screen.findByTestId('dap-queue-item');
    fireEvent.click(screen.getByTestId('dap-review-btn'));
    expect(await screen.findByTestId('dap-already-decided')).toBeInTheDocument();
    expect(screen.queryByTestId('dap-approve-btn')).not.toBeInTheDocument();
    expect(screen.queryByTestId('dap-reject-btn')).not.toBeInTheDocument();
  });

  it('renders no execute / run / apply / dispatch / trigger control', async () => {
    renderPage();
    await screen.findByTestId('dap-queue-item');
    const verbs = /execute|run|apply|dispatch|trigger|suspend|destroy/i;
    for (const btn of screen.queryAllByRole('button')) {
      expect(verbs.test(btn.textContent ?? '')).toBe(false);
    }
    const labels = screen.queryAllByRole('button').map((b) => b.textContent ?? '');
    expect(labels).toEqual(
      expect.arrayContaining(['Open request', 'Refresh queue', 'Review']),
    );
  });

  it('approved_execution_blocked is shown as execution blocked, never executed, quorum red', async () => {
    mockGet(queueWith([DURABLE_QUORUM_MET]), DURABLE_QUORUM_MET);
    renderPage();
    const item = await screen.findByTestId('dap-queue-item');
    expect(item.textContent ?? '').toContain('execution blocked');
    expect(item.textContent ?? '').toContain('executed=false');
    // The state badge for approved_execution_blocked carries the red (not green) tone.
    const stateBadge = screen.getAllByTestId('dap-state-badge')[0];
    expect(stateBadge.className).toContain('red');
    expect(stateBadge.className).not.toContain('green');
    // quorum_met is red (approved-vs-executed distinction), never green.
    const quorum = withinItemQuorum(item);
    expect(quorum.textContent ?? '').toContain('quorum met');
    expect(quorum.className).toContain('red');
    expect(quorum.className).not.toContain('green');
  });

  it('an unknown source_status blocks approve; reject stays available', async () => {
    mockGet(queueWith([DURABLE_UNKNOWN_SOURCE]), DURABLE_UNKNOWN_SOURCE);
    renderPage();
    await screen.findByTestId('dap-queue-item');
    fireEvent.click(screen.getByTestId('dap-review-btn'));
    const detail = await screen.findByTestId('dap-detail');
    expect(detail.textContent ?? '').toContain('unknown');
    expect(screen.getByTestId('dap-source-warning')).toBeInTheDocument();
    expect(screen.getByTestId('dap-approve-btn')).toBeDisabled();
    // Reject remains enabled once the decision form is valid + confirmed.
    fillDecisionForm();
    expect(screen.getByTestId('dap-reject-btn')).not.toBeDisabled();
  });

  it('surfaces only the one-way digest, never a raw idempotency key', async () => {
    mockGet(QUEUE, DURABLE_PENDING_OTHER);
    renderPage();
    await screen.findByTestId('dap-queue-item');
    fireEvent.click(screen.getByTestId('dap-review-btn'));
    const grid = await screen.findByTestId('dap-detail-grid');
    const text = grid.textContent ?? '';
    // The digest fields are shown (truncated to 12 chars + ellipsis).
    expect(text).toContain('idempotency_key_digest');
    expect(text).toContain('request_digest');
    // The full 64-char raw digest is NOT shown in full (truncated display).
    expect(text).not.toContain('b'.repeat(64));
    expect(text).not.toContain('a'.repeat(64));
  });

  it('service methods call the correct P20 endpoints', async () => {
    mockGet(QUEUE, DURABLE_PENDING_OTHER);
    vi.mocked(api.post).mockResolvedValue({ data: DURABLE_PENDING_OTHER });
    renderPage();
    await screen.findByTestId('dap-queue-item');
    expect(api.get).toHaveBeenCalledWith(
      '/platform/p20/durable-approvals',
      expect.objectContaining({ params: expect.objectContaining({ limit: 50, offset: 0 }) }),
    );
    fireEvent.click(screen.getByTestId('dap-review-btn'));
    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith('/platform/p20/durable-approvals/dap-1');
    });
    fillCreateForm();
    fireEvent.click(screen.getByTestId('dap-create-btn'));
    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        '/platform/p20/durable-approvals',
        expect.objectContaining({ confirm: true }),
      );
    });
  });

  it('hides all controls for a tenant-contextual identity', () => {
    setTenantContextualOperator();
    vi.mocked(api.get).mockResolvedValue({ data: QUEUE });
    renderPage();
    expect(screen.getByTestId('dap-no-access')).toBeInTheDocument();
    expect(screen.queryByTestId('dap-create-btn')).not.toBeInTheDocument();
    expect(screen.queryByTestId('dap-queue')).not.toBeInTheDocument();
    expect(screen.queryByTestId('dap-approve-btn')).not.toBeInTheDocument();
    expect(api.get).not.toHaveBeenCalled();
  });
});

function withinItemQuorum(item: HTMLElement): HTMLElement {
  const badges = item.querySelectorAll('[data-testid="dap-quorum-badge"]');
  if (badges.length === 0) {
    throw new Error('no quorum badge rendered in queue item');
  }
  return badges[badges.length - 1] as HTMLElement;
}
