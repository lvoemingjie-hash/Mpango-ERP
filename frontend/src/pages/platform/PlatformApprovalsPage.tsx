/**
 * PlatformApprovalsPage -- P19 controlled-action APPROVAL console (P19-C).
 *
 * Approval is not execution. This page is the approval boundary on top of the
 * P18 request skeleton. It records approval requests, lists the ephemeral
 * approval queue, reads a single approval, and records approve / reject
 * decisions only. It never executes anything.
 *
 * Hard UI rules (P19-A section 9):
 *   - No execute / run / apply / dispatch / trigger control. The only decision
 *     controls are approve and reject, and both land only after an explicit
 *     confirmation token (the confirm checkbox).
 *   - An approved approval is shown as "execution blocked", never as executed,
 *     applied, running, or done. execution_blocked uses red (not green).
 *   - An unknown / unavailable P18 source_status is never shown as healthy and
 *     blocks approve for a write (red / gray badge, not green).
 *   - Tenant-contextual identities see no submit, approve, reject, or queue
 *     controls; the surface is hidden, not merely disabled.
 *
 * storage is always memory; execution_allowed is always false; executed is
 * always false. requested_by / reviewed_by are derived from the authenticated
 * identity-only platform operator and are never typed by the operator.
 *
 * Route is platform-only (/platform/approvals) behind the identity-only
 * PlatformRoute guard. Reuses the existing platformService Axios client.
 */
import { useCallback, useEffect, useState } from 'react';
import { platformService } from '@/services/platformApi';
import { Skeleton } from '@/components/ui/Skeleton';
import { useAuthStore } from '@/stores/authStore';
import { isIdentityPlatformOperator } from '@/router/guards';
import type {
  ApprovalDecisionType,
  ApprovalState,
  ControlledActionApprovalQueue,
  ControlledActionApprovalRecord,
  RegistrySourceStatus,
} from '@/types/platformApprovals';

// execution_blocked is RED (never green); unknown / unavailable sources are
// never green/healthy. pending_review is amber; terminal states are gray/red.
const STATE_TONE: Record<ApprovalState, string> = {
  requested: 'bg-gray-100 text-gray-700',
  pending_review: 'bg-yellow-100 text-yellow-800',
  approved: 'bg-blue-100 text-blue-800',
  execution_blocked: 'bg-red-100 text-red-800',
  rejected: 'bg-red-100 text-red-800',
  expired: 'bg-gray-100 text-gray-600',
  cancelled: 'bg-gray-100 text-gray-600',
};

const SOURCE_TONE: Record<RegistrySourceStatus, string> = {
  available: 'bg-green-100 text-green-800',
  unavailable: 'bg-red-100 text-red-800',
  unknown: 'bg-gray-100 text-gray-600',
};

// A far-future default expiry so an approval always expires (P19-A safety 5).
const DEFAULT_EXPIRES_AT = '2099-12-31T23:59';

function unwrap<T>(res: { data?: unknown }): T {
  const data = res.data as { data?: T } | T | undefined;
  if (data && typeof data === 'object' && 'data' in (data as Record<string, unknown>)) {
    return (data as { data: T }).data;
  }
  return data as T;
}

export function PlatformApprovalsPage() {
  const user = useAuthStore((s) => s.user);
  const canOperate = isIdentityPlatformOperator(user);
  const operatorId = user?.id ?? '';

  // -- approval queue --
  const [queue, setQueue] = useState<ControlledActionApprovalQueue | null>(null);
  const [queueLoading, setQueueLoading] = useState(false);
  const [queueError, setQueueError] = useState<string | null>(null);

  // -- create form --
  const [actionType, setActionType] = useState('tenant.pause');
  const [tenantId, setTenantId] = useState('');
  const [reason, setReason] = useState('');
  const [idempotencyKey, setIdempotencyKey] = useState('');
  const [expiresAt, setExpiresAt] = useState(DEFAULT_EXPIRES_AT);
  const [confirm, setConfirm] = useState(false);

  const [createResult, setCreateResult] = useState<ControlledActionApprovalRecord | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [createBusy, setCreateBusy] = useState(false);

  // -- detail + decision --
  const [detail, setDetail] = useState<ControlledActionApprovalRecord | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const [decisionReason, setDecisionReason] = useState('');
  const [decisionIdempotencyKey, setDecisionIdempotencyKey] = useState('');
  const [decisionConfirm, setDecisionConfirm] = useState(false);

  const [decisionResult, setDecisionResult] = useState<ControlledActionApprovalRecord | null>(null);
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const [decisionBusy, setDecisionBusy] = useState(false);

  const loadQueue = useCallback(() => {
    setQueueLoading(true);
    setQueueError(null);
    platformService
      .listApprovals(50, 0)
      .then((res) => setQueue(unwrap<ControlledActionApprovalQueue>(res)))
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : 'Failed to load approval queue';
        setQueueError(msg);
        setQueue(null);
      })
      .finally(() => setQueueLoading(false));
  }, []);

  useEffect(() => {
    if (canOperate) loadQueue();
  }, [canOperate, loadQueue]);

  const loadDetail = useCallback((approvalId: string) => {
    setDetailLoading(true);
    setDecisionError(null);
    platformService
      .getApproval(approvalId)
      .then((res) => setDetail(unwrap<ControlledActionApprovalRecord>(res)))
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : 'Failed to load approval detail';
        setQueueError(msg);
        setDetail(null);
      })
      .finally(() => setDetailLoading(false));
  }, []);

  const formValid =
    reason.trim().length > 0 &&
    idempotencyKey.trim().length > 0 &&
    expiresAt.trim().length > 0;

  const createApproval = () => {
    if (!formValid || createBusy) return;
    setCreateBusy(true);
    setCreateError(null);
    setCreateResult(null);
    platformService
      .createApprovalRequest({
        action_type: actionType.trim() ? actionType.trim() : null,
        tenant_id: tenantId.trim() ? tenantId.trim() : null,
        requested_by: operatorId,
        reason: reason.trim(),
        idempotency_key: idempotencyKey.trim(),
        expires_at: expiresAt.trim() ? expiresAt.trim() : null,
        confirm,
      })
      .then((res) => {
        setCreateResult(unwrap<ControlledActionApprovalRecord>(res));
        loadQueue();
      })
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : 'Approval request failed';
        setCreateError(msg);
      })
      .finally(() => setCreateBusy(false));
  };

  const decisionFormValid =
    decisionReason.trim().length > 0 && decisionIdempotencyKey.trim().length > 0;

  // approve additionally requires a verified-available P18 source.
  const sourceBlocksApprove = detail?.source_status !== 'available';
  const detailIsPending = detail?.state === 'pending_review';

  const submitDecision = (decision: ApprovalDecisionType) => {
    if (!detail || !detail.approval_id || !canOperate) return;
    if (!decisionFormValid || !decisionConfirm || decisionBusy) return;
    if (decision === 'approve' && sourceBlocksApprove) return;
    setDecisionBusy(true);
    setDecisionError(null);
    setDecisionResult(null);
    platformService
      .submitApprovalDecision(detail.approval_id, {
        decision,
        reviewed_by: operatorId,
        reason: decisionReason.trim(),
        idempotency_key: decisionIdempotencyKey.trim(),
        confirm: decisionConfirm,
      })
      .then((res) => {
        const rec = unwrap<ControlledActionApprovalRecord>(res);
        setDecisionResult(rec);
        if (rec.approval_id) loadDetail(rec.approval_id);
        loadQueue();
      })
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : 'Decision failed';
        setDecisionError(msg);
      })
      .finally(() => setDecisionBusy(false));
  };

  const selectApproval = (approvalId: string | null) => {
    setDecisionResult(null);
    setDecisionReason('');
    setDecisionIdempotencyKey('');
    setDecisionConfirm(false);
    if (!approvalId) {
      setDetail(null);
      return;
    }
    loadDetail(approvalId);
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900" data-testid="ap-title">
          Controlled Action Approvals
        </h1>
        <p className="mt-1 text-sm text-gray-500" data-testid="ap-subtitle">
          Approval is not execution. Approvals are recorded and decided here; they never run a
          controlled action and never change tenant state. An approved approval is execution
          blocked, not executed.
        </p>
      </div>

      {/* Persistent invariants (P19-A section 9) */}
      <section
        className="rounded-lg border border-gray-200 bg-gray-50 p-4"
        data-testid="ap-invariants"
      >
        <h2 className="text-sm font-semibold text-gray-700">Console invariants</h2>
        <ul className="mt-2 grid gap-1 text-xs text-gray-600 sm:grid-cols-2">
          <li>storage = memory</li>
          <li>execution_allowed = false</li>
          <li>executed = false</li>
          <li>approved is blocked from execution</li>
        </ul>
      </section>

      {(queueError || createError || decisionError) && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4">
          <p className="text-sm text-red-700" data-testid="ap-error">
            {queueError ?? createError ?? decisionError}
          </p>
        </div>
      )}

      {!canOperate ? (
        <div
          className="rounded-lg border border-gray-200 bg-white p-4"
          data-testid="ap-no-access"
        >
          <p className="text-sm text-gray-700">
            Approval controls are hidden for tenant-contextual identities. The platform approval
            surface is identity-only.
          </p>
        </div>
      ) : (
        <>
          {/* Create approval request (recorded, not executed) */}
          <section className="rounded-lg border border-gray-200 bg-white p-4">
            <h2 className="text-lg font-semibold text-gray-900 mb-1">
              Record an approval request
            </h2>
            <p className="mb-3 text-xs text-gray-500">
              Recorded at pending_review and audited. The request is not executed and no tenant
              state is changed.
            </p>
            <div className="grid gap-3">
              <label className="block text-sm text-gray-700">
                Action type
                <input
                  className="mt-1 block w-full rounded border border-gray-300 p-2"
                  value={actionType}
                  onChange={(e) => setActionType(e.target.value)}
                  data-testid="ap-action-input"
                />
              </label>
              <label className="block text-sm text-gray-700">
                Tenant id (optional)
                <input
                  className="mt-1 block w-full rounded border border-gray-300 p-2"
                  value={tenantId}
                  onChange={(e) => setTenantId(e.target.value)}
                  data-testid="ap-tenant-input"
                />
              </label>
              <label className="block text-sm text-gray-700">
                Reason (required)
                <textarea
                  className="mt-1 block w-full rounded border border-gray-300 p-2"
                  rows={2}
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  data-testid="ap-reason-input"
                />
              </label>
              <label className="block text-sm text-gray-700">
                Idempotency key (required)
                <input
                  className="mt-1 block w-full rounded border border-gray-300 p-2"
                  value={idempotencyKey}
                  onChange={(e) => setIdempotencyKey(e.target.value)}
                  data-testid="ap-idempotency-input"
                />
              </label>
              <label className="block text-sm text-gray-700">
                Expires at (required, future)
                <input
                  type="datetime-local"
                  className="mt-1 block w-full rounded border border-gray-300 p-2"
                  value={expiresAt}
                  onChange={(e) => setExpiresAt(e.target.value)}
                  data-testid="ap-expires-input"
                />
              </label>
              <label className="inline-flex items-center gap-2 text-sm text-gray-700">
                <input
                  type="checkbox"
                  checked={confirm}
                  onChange={(e) => setConfirm(e.target.checked)}
                  data-testid="ap-confirm-input"
                />
                Confirm acknowledgement (required to open the request)
              </label>
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={!formValid || !confirm || createBusy}
                  onClick={createApproval}
                  className="rounded bg-primary-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                  data-testid="ap-create-btn"
                >
                  Record approval
                </button>
              </div>
              {!formValid || !confirm ? (
                <p className="text-xs text-gray-400" data-testid="ap-form-hint">
                  A reason, an idempotency key, an expiry, and confirmation are required before an
                  approval request can be recorded.
                </p>
              ) : null}
            </div>
          </section>

          {/* Create result */}
          {createResult ? (
            <ResultSection
              heading="Recorded approval"
              record={createResult}
              testId="ap-create-result"
            />
          ) : null}

          {/* Approval queue */}
          <section
            className="rounded-lg border border-gray-200 bg-white p-4"
            data-testid="ap-queue"
          >
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">Approval queue</h2>
                <p className="text-xs text-gray-500">
                  Ephemeral memory queue; approvals are listed for review and are never executed.
                </p>
              </div>
              <button
                type="button"
                onClick={loadQueue}
                className="rounded bg-gray-200 px-3 py-2 text-sm font-medium text-gray-800"
                data-testid="ap-refresh-btn"
              >
                Refresh queue
              </button>
            </div>
            {queueLoading && !queue ? (
              <div className="mt-3">
                <Skeleton className="h-16 w-full rounded-lg" />
              </div>
            ) : queue ? (
              <div className="mt-3">
                <p className="text-xs text-gray-500" data-testid="ap-queue-summary">
                  {queue.total} recorded approvals; storage={queue.storage}; executed=
                  {String(queue.executed)}
                </p>
                {queue.items.length === 0 ? (
                  <p className="mt-2 text-xs text-gray-400" data-testid="ap-queue-empty">
                    No approvals recorded yet.
                  </p>
                ) : (
                  <ul className="mt-2 divide-y divide-gray-100">
                    {queue.items.map((item) => {
                      const selected = detail?.approval_id === item.approval_id;
                      return (
                        <li
                          key={item.approval_id ?? item.action_type ?? 'unknown'}
                          className="py-2"
                          data-testid="ap-queue-item"
                        >
                          <div className="flex flex-wrap items-center gap-2 text-sm">
                            <span className="font-mono text-gray-900">
                              {item.action_type ?? '(no action type)'}
                            </span>
                            <StateBadge state={item.state} />
                            <SourceBadge source={item.source_status} />
                            <span className="text-xs text-gray-400">
                              executed={String(item.executed)}
                            </span>
                            <span className="text-xs text-gray-400">
                              execution_allowed={String(item.execution_allowed)}
                            </span>
                            <button
                              type="button"
                              onClick={() => selectApproval(item.approval_id)}
                              className={`rounded px-2 py-1 text-xs font-medium ${
                                selected
                                  ? 'bg-primary-600 text-white'
                                  : 'bg-gray-200 text-gray-800'
                              }`}
                              data-testid="ap-review-btn"
                            >
                              Review
                            </button>
                          </div>
                          {item.approval_id ? (
                            <p className="mt-1 text-xs text-gray-500">
                              approval id: {item.approval_id}
                            </p>
                          ) : null}
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
            ) : (
              <p className="mt-3 text-xs text-gray-400">Refresh to load the approval queue.</p>
            )}
          </section>

          {/* Detail + decision panel */}
          {detail ? (
            <section
              className="space-y-4 rounded-lg border border-gray-200 bg-white p-4"
              data-testid="ap-detail"
            >
              <div>
                <h2 className="text-lg font-semibold text-gray-900">Approval detail</h2>
                <p className="text-xs text-gray-500">
                  Read-only request context. No raw reason, metadata, idempotency key, DSN, host,
                  or port is shown.
                </p>
              </div>
              {detailLoading ? (
                <Skeleton className="h-20 w-full rounded-lg" />
              ) : (
                <DetailGrid record={detail} />
              )}

              {sourceBlocksApprove ? (
                <div
                  className="rounded bg-yellow-50 p-3 text-xs text-yellow-800"
                  data-testid="ap-source-warning"
                >
                  The underlying P18 source status is {detail.source_status}. An unknown or
                  unavailable source is not healthy and blocks an approve; reject remains
                  available. Nothing is executed.
                </div>
              ) : null}

              {/* Decision controls: only on a pending approval, only for identity-only
                  super_admin, only after explicit confirmation. No execute control. */}
              {detailIsPending ? (
                <div className="rounded-lg border border-gray-200 p-3" data-testid="ap-decision">
                  <h3 className="text-sm font-semibold text-gray-800 mb-2">
                    Record a decision (not executed)
                  </h3>
                  <div className="grid gap-3">
                    <label className="block text-sm text-gray-700">
                      Decision reason (required)
                      <textarea
                        className="mt-1 block w-full rounded border border-gray-300 p-2"
                        rows={2}
                        value={decisionReason}
                        onChange={(e) => setDecisionReason(e.target.value)}
                        data-testid="ap-decision-reason-input"
                      />
                    </label>
                    <label className="block text-sm text-gray-700">
                      Decision idempotency key (required)
                      <input
                        className="mt-1 block w-full rounded border border-gray-300 p-2"
                        value={decisionIdempotencyKey}
                        onChange={(e) => setDecisionIdempotencyKey(e.target.value)}
                        data-testid="ap-decision-idempotency-input"
                      />
                    </label>
                    <label className="inline-flex items-center gap-2 text-sm text-gray-700">
                      <input
                        type="checkbox"
                        checked={decisionConfirm}
                        onChange={(e) => setDecisionConfirm(e.target.checked)}
                        data-testid="ap-decision-confirm-input"
                      />
                      Confirm decision (required; approve resolves to execution blocked)
                    </label>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        disabled={
                          !decisionFormValid ||
                          !decisionConfirm ||
                          decisionBusy ||
                          sourceBlocksApprove
                        }
                        onClick={() => submitDecision('approve')}
                        className="rounded bg-primary-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                        data-testid="ap-approve-btn"
                      >
                        Approve
                      </button>
                      <button
                        type="button"
                        disabled={!decisionFormValid || !decisionConfirm || decisionBusy}
                        onClick={() => submitDecision('reject')}
                        className="rounded bg-red-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                        data-testid="ap-reject-btn"
                      >
                        Reject
                      </button>
                    </div>
                  </div>
                </div>
              ) : (
                <p className="text-xs text-gray-500" data-testid="ap-no-decision">
                  This approval is not pending review; no decision control is available. Approve
                  resolves to execution blocked and is never executed.
                </p>
              )}
            </section>
          ) : null}

          {decisionResult ? (
            <ResultSection
              heading="Decision outcome"
              record={decisionResult}
              testId="ap-decision-result"
            />
          ) : null}
        </>
      )}
    </div>
  );
}

// -- Small presentational helpers (approval-is-not-execution aware) ----------

function StateBadge({ state }: { state: ApprovalState | null }) {
  const tone = state ? STATE_TONE[state] ?? 'bg-gray-100 text-gray-600' : 'bg-gray-100 text-gray-600';
  const label =
    state === 'execution_blocked'
      ? 'execution blocked'
      : state === 'pending_review'
        ? 'pending review'
        : state ?? 'unknown';
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${tone}`}
      data-testid="ap-state-badge"
    >
      {label}
    </span>
  );
}

function SourceBadge({ source }: { source: RegistrySourceStatus }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${SOURCE_TONE[source]}`}
      data-testid="ap-source-badge"
    >
      source: {source}
    </span>
  );
}

function DetailGrid({ record }: { record: ControlledActionApprovalRecord }) {
  return (
    <dl className="grid gap-x-4 gap-y-1 text-xs text-gray-700 sm:grid-cols-2" data-testid="ap-detail-grid">
      <DetailRow label="approval_id" value={record.approval_id} />
      <DetailRow label="action_id" value={record.action_id} />
      <DetailRow label="action_type" value={record.action_type} />
      <DetailRow label="tenant_id" value={record.tenant_id} />
      <DetailRow label="state" value={record.state} />
      <DetailRow label="source_status" value={record.source_status} />
      <DetailRow label="requested_by" value={record.requested_by} />
      <DetailRow label="requested_at" value={record.requested_at} />
      <DetailRow label="reviewed_by" value={record.reviewed_by} />
      <DetailRow label="reviewed_at" value={record.reviewed_at} />
      <DetailRow label="decision" value={record.decision} />
      <DetailRow label="reason (redacted)" value={record.reason} />
      <DetailRow label="expires_at" value={record.expires_at} />
      <DetailRow label="audit_event_id" value={record.audit_event_id} />
      <DetailRow label="storage" value={record.storage} />
      <DetailRow label="execution_allowed" value={String(record.execution_allowed)} />
      <DetailRow label="redaction_applied" value={String(record.redaction_applied)} />
      <DetailRow label="executed" value={String(record.executed)} />
    </dl>
  );
}

function DetailRow({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="flex gap-2">
      <dt className="font-mono text-gray-400">{label}</dt>
      <dd className="text-gray-800">{value === null || value === '' ? '(none)' : value}</dd>
    </div>
  );
}

function ResultSection({
  heading,
  record,
  testId,
}: {
  heading: string;
  record: ControlledActionApprovalRecord;
  testId: string;
}) {
  const blocked = record.state === 'execution_blocked' || record.result === 'approved';
  return (
    <section
      className="rounded-lg border border-gray-200 bg-white p-4"
      data-testid={testId}
    >
      <div className="flex flex-wrap items-center gap-3">
        <span
          className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
            record.result === 'recorded' || record.result === 'approved'
              ? 'bg-blue-100 text-blue-800'
              : record.result === 'rejected'
                ? 'bg-red-100 text-red-800'
                : 'bg-gray-100 text-gray-700'
          }`}
          data-testid="ap-result-badge"
        >
          {record.result}
        </span>
        <StateBadge state={record.state} />
        <SourceBadge source={record.source_status} />
        <span className="text-xs text-gray-400">executed={String(record.executed)}</span>
        <span className="text-xs text-gray-400">
          execution_allowed={String(record.execution_allowed)}
        </span>
      </div>
      <p className="mt-2 text-sm font-semibold text-gray-900" data-testid="ap-not-executed">
        {blocked
          ? 'Approved: resolves to execution blocked (executed=false).'
          : 'Recorded: not executed (executed=false).'}
      </p>
      <p className="mt-1 text-sm text-gray-700">{record.message}</p>
      {record.approval_id ? (
        <p className="mt-1 text-xs text-gray-500">approval id: {record.approval_id}</p>
      ) : null}
    </section>
  );
}
