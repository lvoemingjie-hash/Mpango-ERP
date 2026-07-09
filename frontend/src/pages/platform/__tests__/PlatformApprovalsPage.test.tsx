/**
 * P19-C: Platform approvals console component tests.
 *
 * Verifies the approval-is-not-execution contract on the frontend:
 *   - title / subtitle / invariants (storage=memory, execution_allowed=false,
 *     executed=false, approved is blocked from execution)
 *   - the approval queue renders, plus empty / loading / error states
 *   - create submits to the service with requested_by derived from the operator
 *   - approve / reject submit only after explicit confirmation, to the right
 *     endpoints, with reviewed_by derived from the operator
 *   - NO execute / run / apply / dispatch / trigger control is rendered
 *   - execution_blocked is shown as "execution blocked", never as executed
 *   - executed=false and execution_allowed=false are displayed
 *   - an unknown source_status is not styled healthy and blocks approve
 *   - service methods call the correct P19 endpoints
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
import { PlatformApprovalsPage } from '@/pages/platform/PlatformApprovalsPage';

const OPERATOR_ID = 'identity-super-admin';

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
    <MemoryRouter initialEntries={['/platform/approvals']}>
      <Routes>
        <Route path="/platform/approvals" element={<PlatformApprovalsPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

const APPROVAL_PENDING = {
  action_id: 'aid-1',
  approval_id: 'appr-1',
  tenant_id: 't-1',
  action_type: 'tenant.pause',
  state: 'pending_review',
  requested_by: OPERATOR_ID,
  requested_at: '2026-06-24T00:00:00Z',
  reviewed_by: null,
  reviewed_at: null,
  decision: null,
  reason: '[redacted]',
  expires_at: '2099-01-01T00:00:00Z',
  execution_allowed: false,
  redaction_applied: true,
  idempotency_key: '[redacted]',
  source_status: 'available',
  previous_state: null,
  storage: 'memory',
  audit_event_id: 'evt-1',
  correlation_id: null,
  result: 'recorded',
  message: 'Recorded: the approval request was recorded at pending_review.',
  executed: false,
  created_at: '2026-06-24T00:00:00Z',
  updated_at: '2026-06-24T00:00:00Z',
};

const APPROVAL_APPROVED = {
  ...APPROVAL_PENDING,
  state: 'execution_blocked',
  decision: 'approve',
  reviewed_by: OPERATOR_ID,
  reviewed_at: '2026-06-24T00:01:00Z',
  result: 'approved',
  message: 'Approved: resolved to execution_blocked; not executed.',
};

const APPROVAL_REJECTED = {
  ...APPROVAL_PENDING,
  state: 'rejected',
  decision: 'reject',
  reviewed_by: OPERATOR_ID,
  reviewed_at: '2026-06-24T00:01:00Z',
  result: 'rejected',
  message: 'Rejected: reject is final.',
};

const APPROVAL_UNKNOWN_SOURCE = {
  ...APPROVAL_PENDING,
  approval_id: 'appr-unknown',
  source_status: 'unknown',
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

const QUEUE = queueWith([APPROVAL_PENDING]);
const EMPTY_QUEUE = queueWith([]);

// Route api.get by URL: list vs read-by-id. The decision endpoint is a POST.
function mockGet(listBody: unknown, detailBody: unknown = APPROVAL_PENDING) {
  vi.mocked(api.get).mockImplementation((url) => {
    const u = typeof url === 'string' ? url : '';
    // read-by-id: /platform/p19/approvals/{approval_id} (no trailing /decision)
    if (/\/approvals\/[^/?]+$/.test(u)) return Promise.resolve({ data: detailBody });
    // list: /platform/p19/approvals
    return Promise.resolve({ data: listBody });
  });
}

function fillCreateForm() {
  fireEvent.change(screen.getByTestId('ap-reason-input'), { target: { value: 'routine review' } });
  fireEvent.change(screen.getByTestId('ap-idempotency-input'), { target: { value: 'key-1' } });
  fireEvent.change(screen.getByTestId('ap-expires-input'), { target: { value: '2099-12-31T23:59' } });
  fireEvent.click(screen.getByTestId('ap-confirm-input'));
}

function fillDecisionForm() {
  fireEvent.change(screen.getByTestId('ap-decision-reason-input'), { target: { value: 'ok to approve' } });
  fireEvent.change(screen.getByTestId('ap-decision-idempotency-input'), { target: { value: 'dec-1' } });
  fireEvent.click(screen.getByTestId('ap-decision-confirm-input'));
}

describe('PlatformApprovalsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setIdentityOperator();
    vi.mocked(api.get).mockResolvedValue({ data: QUEUE });
    vi.mocked(api.post).mockResolvedValue({ data: {} });
  });

  it('renders title, not-executed subtitle, and the console invariants', async () => {
    renderPage();
    expect(screen.getByTestId('ap-title')).toHaveTextContent('Controlled Action Approvals');
    const subtitle = screen.getByTestId('ap-subtitle').textContent ?? '';
    expect(subtitle.toLowerCase()).toContain('not executed');
    const invariants = screen.getByTestId('ap-invariants').textContent ?? '';
    expect(invariants).toContain('storage = memory');
    expect(invariants).toContain('execution_allowed = false');
    expect(invariants).toContain('executed = false');
    expect(invariants.toLowerCase()).toContain('approved is blocked from execution');
    // Await the mount-time useEffect queue load so the async state update
    // (setQueue / setQueueLoading(false)) settles within act(...) and emits no
    // React act warning.
    await screen.findByTestId('ap-queue-summary');
  });

  it('renders the approval queue after load', async () => {
    renderPage();
    const item = await screen.findByTestId('ap-queue-item');
    expect(item).toHaveTextContent('tenant.pause');
    expect(screen.getByTestId('ap-queue-summary').textContent ?? '').toContain('storage=memory');
    expect(item.textContent ?? '').toContain('executed=false');
    expect(item.textContent ?? '').toContain('execution_allowed=false');
  });

  it('shows an empty-queue state when there are no approvals', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: EMPTY_QUEUE });
    renderPage();
    expect(await screen.findByTestId('ap-queue-empty')).toBeInTheDocument();
    expect(screen.queryByTestId('ap-queue-item')).not.toBeInTheDocument();
  });

  it('shows a loading skeleton before the queue resolves', () => {
    // Never-resolving promise keeps the component in the loading branch.
    vi.mocked(api.get).mockReturnValue(new Promise(() => undefined));
    renderPage();
    expect(screen.getByTestId('ap-queue')).toBeInTheDocument();
    // The skeleton is the first child container of the queue while loading.
    expect(screen.queryByTestId('ap-queue-summary')).not.toBeInTheDocument();
  });

  it('shows an error banner when the queue fails to load', async () => {
    vi.mocked(api.get).mockRejectedValue(new Error('network down'));
    renderPage();
    expect(await screen.findByTestId('ap-error')).toHaveTextContent('network down');
  });

  it('create submits to the create endpoint with operator-derived requested_by', async () => {
    mockGet(QUEUE);
    vi.mocked(api.post).mockResolvedValue({ data: APPROVAL_PENDING });
    renderPage();
    await screen.findByTestId('ap-queue-item');
    fillCreateForm();
    fireEvent.click(screen.getByTestId('ap-create-btn'));
    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        '/platform/p19/approvals',
        expect.objectContaining({
          action_type: 'tenant.pause',
          requested_by: OPERATOR_ID,
          reason: 'routine review',
          idempotency_key: 'key-1',
          confirm: true,
        }),
      );
    });
    expect(await screen.findByTestId('ap-create-result')).toBeInTheDocument();
  });

  it('create is disabled until reason, idempotency, expiry, and confirm are provided', async () => {
    renderPage();
    await screen.findByTestId('ap-queue-item');
    expect(screen.getByTestId('ap-create-btn')).toBeDisabled();
    fireEvent.change(screen.getByTestId('ap-reason-input'), { target: { value: 'r' } });
    fireEvent.change(screen.getByTestId('ap-idempotency-input'), { target: { value: 'k' } });
    // Still disabled: confirm not yet checked.
    expect(screen.getByTestId('ap-create-btn')).toBeDisabled();
    fireEvent.click(screen.getByTestId('ap-confirm-input'));
    expect(screen.getByTestId('ap-create-btn')).not.toBeDisabled();
  });

  it('approve submits to the decision endpoint only after confirmation', async () => {
    mockGet(QUEUE, APPROVAL_PENDING);
    vi.mocked(api.post).mockResolvedValue({ data: APPROVAL_APPROVED });
    renderPage();
    await screen.findByTestId('ap-queue-item');
    fireEvent.click(screen.getByTestId('ap-review-btn'));
    await screen.findByTestId('ap-detail');
    // Approve disabled before the confirmation token is supplied.
    expect(screen.getByTestId('ap-approve-btn')).toBeDisabled();
    fillDecisionForm();
    fireEvent.click(screen.getByTestId('ap-approve-btn'));
    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        '/platform/p19/approvals/appr-1/decision',
        expect.objectContaining({
          decision: 'approve',
          reviewed_by: OPERATOR_ID,
          reason: 'ok to approve',
          idempotency_key: 'dec-1',
          confirm: true,
        }),
      );
    });
    const result = await screen.findByTestId('ap-decision-result');
    // execution_blocked, never executed.
    expect(result.textContent ?? '').toContain('execution blocked');
    expect(screen.getByTestId('ap-not-executed').textContent ?? '').toContain('executed=false');
  });

  it('reject submits to the decision endpoint with decision reject', async () => {
    mockGet(QUEUE, APPROVAL_PENDING);
    vi.mocked(api.post).mockResolvedValue({ data: APPROVAL_REJECTED });
    renderPage();
    await screen.findByTestId('ap-queue-item');
    fireEvent.click(screen.getByTestId('ap-review-btn'));
    await screen.findByTestId('ap-detail');
    fillDecisionForm();
    fireEvent.click(screen.getByTestId('ap-reject-btn'));
    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        '/platform/p19/approvals/appr-1/decision',
        expect.objectContaining({ decision: 'reject', confirm: true, reviewed_by: OPERATOR_ID }),
      );
    });
    expect(await screen.findByTestId('ap-decision-result')).toHaveTextContent('rejected');
  });

  it('renders no execute / run / apply / dispatch / trigger control', async () => {
    renderPage();
    await screen.findByTestId('ap-queue-item');
    const verbs = /execute|run|apply|dispatch|trigger|suspend|destroy/i;
    for (const btn of screen.queryAllByRole('button')) {
      expect(verbs.test(btn.textContent ?? '')).toBe(false);
    }
    // The only decision controls are approve / reject (plus record / refresh / review).
    const labels = screen.queryAllByRole('button').map((b) => b.textContent ?? '');
    expect(labels).toEqual(expect.arrayContaining(['Record approval', 'Refresh queue', 'Review']));
  });

  it('execution_blocked is never shown as executed', async () => {
    mockGet(queueWith([APPROVAL_APPROVED]), APPROVAL_APPROVED);
    renderPage();
    const item = await screen.findByTestId('ap-queue-item');
    // The approved approval is execution_blocked; it explicitly says executed=false.
    expect(item.textContent ?? '').toContain('execution blocked');
    expect(item.textContent ?? '').toContain('executed=false');
    // The state badge for execution_blocked carries the red (not green) tone.
    const stateBadge = screen.getAllByTestId('ap-state-badge')[0];
    expect(stateBadge.className).toContain('red');
    expect(stateBadge.className).not.toContain('green');
  });

  it('an unknown source_status is not styled healthy and blocks approve', async () => {
    mockGet(queueWith([APPROVAL_UNKNOWN_SOURCE]), APPROVAL_UNKNOWN_SOURCE);
    renderPage();
    const item = await screen.findByTestId('ap-queue-item');
    // The source badge for unknown is gray, not green/healthy.
    const sourceBadge = withinItemSourceBadge(item);
    expect(sourceBadge.className).toContain('gray');
    expect(sourceBadge.className).not.toContain('green');
    fireEvent.click(screen.getByTestId('ap-review-btn'));
    const detail = await screen.findByTestId('ap-detail');
    expect(detail.textContent ?? '').toContain('unknown');
    expect(screen.getByTestId('ap-source-warning')).toBeInTheDocument();
    // Approve is disabled against an unknown source; reject stays available.
    expect(screen.getByTestId('ap-approve-btn')).toBeDisabled();
  });

  it('service methods call the correct P19 endpoints', async () => {
    mockGet(QUEUE, APPROVAL_PENDING);
    vi.mocked(api.post).mockResolvedValue({ data: APPROVAL_PENDING });
    renderPage();
    await screen.findByTestId('ap-queue-item');
    // list -> GET /platform/p19/approvals
    expect(api.get).toHaveBeenCalledWith(
      '/platform/p19/approvals',
      expect.objectContaining({ params: expect.objectContaining({ limit: 50, offset: 0 }) }),
    );
    // read-by-id -> GET /platform/p19/approvals/{id}
    fireEvent.click(screen.getByTestId('ap-review-btn'));
    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith('/platform/p19/approvals/appr-1');
    });
    // create -> POST /platform/p19/approvals
    fillCreateForm();
    fireEvent.click(screen.getByTestId('ap-create-btn'));
    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        '/platform/p19/approvals',
        expect.objectContaining({ confirm: true }),
      );
    });
  });

  it('hides all controls for a tenant-contextual identity', () => {
    setTenantContextualOperator();
    vi.mocked(api.get).mockResolvedValue({ data: QUEUE });
    renderPage();
    expect(screen.getByTestId('ap-no-access')).toBeInTheDocument();
    expect(screen.queryByTestId('ap-create-btn')).not.toBeInTheDocument();
    expect(screen.queryByTestId('ap-queue')).not.toBeInTheDocument();
    expect(screen.queryByTestId('ap-approve-btn')).not.toBeInTheDocument();
    // The platform surface does not even load the queue for a tenant-contextual user.
    expect(api.get).not.toHaveBeenCalled();
  });
});

// The queue item renders the source badge inline; grab it by its test id.
function withinItemSourceBadge(item: HTMLElement): HTMLElement {
  const badges = item.querySelectorAll('[data-testid="ap-source-badge"]');
  if (badges.length === 0) {
    throw new Error('no source badge rendered in queue item');
  }
  return badges[badges.length - 1] as HTMLElement;
}
