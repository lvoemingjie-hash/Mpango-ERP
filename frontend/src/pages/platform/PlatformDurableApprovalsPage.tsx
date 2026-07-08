/**
 * PlatformDurableApprovalsPage -- P20 durable approval governance console (P20-C).
 *
 * Durability is not execution. This page is the durable approval boundary on
 * top of the P20-B backend skeleton and the P18 request skeleton. It opens
 * durable approval requests, lists the ephemeral queue, reads a single record,
 * and records per-checker approve / reject DECISIONS only. It never executes
 * anything and never changes tenant state.
 *
 * Hard UI rules (P20-A section 4 / 5 and the P20-B entry gate):
 *   - No execute / run / apply / dispatch / trigger control. The only decision
 *     controls are approve and reject, and both land only after an explicit
 *     confirmation token (the confirm checkbox).
 *   - A quorum-met approval is shown as approved_execution_blocked (red, "quorum
 *     met / execution blocked"), never as executed, applied, running, or done.
 *   - Maker-checker separation: the maker (the authenticated identity-only
 *     super_admin who opened the request) can never be a checker. If the current
 *     operator is the maker, NO decision control is offered to them -- a
 *     distinct identity-only super_admin checker is required. Each checker
 *     records at most one decision.
 *   - An unknown / unavailable P18 source_status, or a non-valid
 *     validation_status, is never shown as healthy and blocks approve (red /
 *     gray badge, not green); reject remains available.
 *   - No raw idempotency key, reason, metadata, DSN, host, or port is shown.
 *     Only the one-way idempotency_key_digest and request_digest are surfaced.
 *   - Tenant-contextual identities see no submit, decision, or queue controls;
 *     the surface is hidden, not merely disabled.
 *
 * storage is always memory; execution_allowed is always false; execution_gate
 * is always blocked; executed is always false. The maker and the approver are
 * derived from the authenticated identity-only platform operator and are never
 * typed by the operator (they bind to the authenticated actor on the server).
 *
 * Route is platform-only (/platform/durable-approvals) behind the identity-only
 * PlatformRoute guard. Reuses the existing platformService Axios client.
 */
import { useCallback, useEffect, useState } from 'react';
import { platformService } from '@/services/platformApi';
import { Skeleton } from '@/components/ui/Skeleton';
import { useAuthStore } from '@/stores/authStore';
import { isIdentityPlatformOperator } from '@/router/guards';
import type {
  CheckerDecisionSummary,
  DurableActionClass,
  DurableApprovalDecisionType,
  DurableApprovalQueue,
  DurableApprovalRecord,
  DurableApprovalState,
  RegistrySourceStatus,
} from '@/types/platformDurableApprovals';

// approved_execution_blocked is RED (never green); unknown / unavailable sources
// are never green/healthy. pending_review is amber; terminal states are gray/red.
const STATE_TONE: Record<DurableApprovalState, string> = {
  pending_review: 'bg-yellow-100 text-yellow-800',
  approved_execution_blocked: 'bg-red-100 text-red-800',
  rejected: 'bg-red-100 text-red-800',
  expired: 'bg-gray-100 text-gray-600',
  cancelled: 'bg-gray-100 text-gray-600',
  superseded: 'bg-gray-100 text-gray-600',
  failed_validation: 'bg-gray-100 text-gray-600',
};

const SOURCE_TONE: Record<RegistrySourceStatus, string> = {
  available: 'bg-green-100 text-green-800',
  unavailable: 'bg-red-100 text-red-800',
  unknown: 'bg-gray-100 text-gray-600',
};

// A far-future default expiry so a durable approval always expires (P20-A 5).
const DEFAULT_EXPIRES_AT = '2099-12-31T23:59';

function unwrap<T>(res: { data?: unknown }): T {
  const data = res.data as { data?: T } | T | undefined;
  if (data && typeof data === 'object' && 'data' in (data as Record<string, unknown>)) {
    return (data as { data: T }).data;
  }
  return data as T;
}

// Distinct approve checkers recorded so far (the maker is excluded by the
// backend; the checkers list never contains the maker).
function approveCount(checkers: CheckerDecisionSummary[]): number {
  return checkers.filter((c) => c.decision === 'approve').length;
}

export function PlatformDurableApprovalsPage() {
  const user = useAuthStore((s) => s.user);
  const canOperate = isIdentityPlatformOperator(user);
  const operatorId = user?.id ?? '';

  // -- durable approval queue --
  const [queue, setQueue] = useState<DurableApprovalQueue | null>(null);
  const [queueLoading, setQueueLoading] = useState(false);
  const [queueError, setQueueError] = useState<string | null>(null);

  // -- create form --
  const [actionId, setActionId] = useState('');
  const [actionType, setActionType] = useState('tenant.pause');
  const [tenantId, setTenantId] = useState('');
  const [reason, setReason] = useState('');
  const [idempotencyKey, setIdempotencyKey] = useState('');
  const [expiresAt, setExpiresAt] = useState(DEFAULT_EXPIRES_AT);
  const [retainUntil, setRetainUntil] = useState('');
  const [confirm, setConfirm] = useState(false);

  const [createResult, setCreateResult] = useState<DurableApprovalRecord | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [createBusy, setCreateBusy] = useState(false);

  // -- detail + decision --
  const [detail, setDetail] = useState<DurableApprovalRecord | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const [decisionReason, setDecisionReason] = useState('');
  const [decisionIdempotencyKey, setDecisionIdempotencyKey] = useState('');
  const [decisionConfirm, setDecisionConfirm] = useState(false);

  const [decisionResult, setDecisionResult] = useState<DurableApprovalRecord | null>(null);
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const [decisionBusy, setDecisionBusy] = useState(false);

  const loadQueue = useCallback(() => {
    setQueueLoading(true);
    setQueueError(null);
    platformService
      .listDurableApprovals(50, 0)
      .then((res) => setQueue(unwrap<DurableApprovalQueue>(res)))
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : 'Failed to load durable approval queue';
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
      .getDurableApproval(approvalId)
      .then((res) => setDetail(unwrap<DurableApprovalRecord>(res)))
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : 'Failed to load durable approval detail';
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
    if (!formValid || !confirm || createBusy) return;
    setCreateBusy(true);
    setCreateError(null);
    setCreateResult(null);
    platformService
      .createDurableApproval({
        action_id: actionId.trim() ? actionId.trim() : null,
        action_type: actionType.trim() ? actionType.trim() : null,
        tenant_id: tenantId.trim() ? tenantId.trim() : null,
        // The maker binds to the authenticated actor on the server; sending it
        // here is an explicit assertion that MUST equal that actor (spoof denied).
        maker: operatorId,
        reason: reason.trim(),
        idempotency_key: idempotencyKey.trim(),
        expires_at: expiresAt.trim() ? expiresAt.trim() : null,
        durable_retain_until: retainUntil.trim() ? retainUntil.trim() : null,
        confirm,
      })
      .then((res) => {
        setCreateResult(unwrap<DurableApprovalRecord>(res));
        loadQueue();
      })
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : 'Durable approval request failed';
        setCreateError(msg);
      })
      .finally(() => setCreateBusy(false));
  };

  const decisionFormValid =
    decisionReason.trim().length > 0 && decisionIdempotencyKey.trim().length > 0;

  // Maker-checker separation: the current operator is forbidden from deciding an
  // approval they opened (the maker can never be a checker).
  const isMaker = !!detail && detail.maker === operatorId;
  // Each checker records at most one decision.
  const myDecision =
    detail?.checkers.find((c) => c.checker_id === operatorId)?.decision ?? null;

  // Approve additionally requires a verified-available P18 source and a valid
  // re-validation status.
  const sourceBlocksApprove =
    !!detail && (detail.source_status !== 'available' || detail.validation_status !== 'valid');
  const detailIsPending = detail?.state === 'pending_review';

  // The decision controls are offered only to a non-maker checker who has not
  // yet decided, on a pending approval.
  const canDecide = !!detail && detailIsPending && !isMaker && myDecision === null;

  const submitDecision = (decision: DurableApprovalDecisionType) => {
    if (!detail || !detail.approval_id || !canOperate) return;
    if (!canDecide || !decisionFormValid || !decisionConfirm || decisionBusy) return;
    if (decision === 'approve' && sourceBlocksApprove) return;
    setDecisionBusy(true);
    setDecisionError(null);
    setDecisionResult(null);
    platformService
      .submitDurableApprovalDecision(detail.approval_id, {
        decision,
        // The approver binds to the authenticated actor on the server.
        approver_id: operatorId,
        reason: decisionReason.trim(),
        idempotency_key: decisionIdempotencyKey.trim(),
        confirm: decisionConfirm,
      })
      .then((res) => {
        const rec = unwrap<DurableApprovalRecord>(res);
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
        <h1 className="text-2xl font-bold text-gray-900" data-testid="dap-title">
          Durable Approvals
        </h1>
        <p className="mt-1 text-sm text-gray-500" data-testid="dap-subtitle">
          Durability is not execution. Durable approvals are opened and decided here under
          maker-checker dual control with quorum; they never run a controlled action and never
          change tenant state. A quorum-met approval is approved_execution_blocked, not executed.
        </p>
      </div>

      {/* Persistent invariants (P20-A section 4 / 5) */}
      <section
        className="rounded-lg border border-gray-200 bg-gray-50 p-4"
        data-testid="dap-invariants"
      >
        <h2 className="text-sm font-semibold text-gray-700">Console invariants</h2>
        <ul className="mt-2 grid gap-1 text-xs text-gray-600 sm:grid-cols-2">
          <li>storage = memory</li>
          <li>execution_allowed = false</li>
          <li>execution_gate = blocked</li>
          <li>executed = false</li>
          <li>maker can never be a checker</li>
          <li>quorum met is blocked from execution</li>
        </ul>
      </section>

      {(queueError || createError || decisionError) && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4">
          <p className="text-sm text-red-700" data-testid="dap-error">
            {queueError ?? createError ?? decisionError}
          </p>
        </div>
      )}

      {!canOperate ? (
        <div
          className="rounded-lg border border-gray-200 bg-white p-4"
          data-testid="dap-no-access"
        >
          <p className="text-sm text-gray-700">
            Durable approval controls are hidden for tenant-contextual identities. The platform
            durable approval surface is identity-only.
          </p>
        </div>
      ) : (
        <>
          {/* Open a durable approval request (recorded, not executed) */}
          <section className="rounded-lg border border-gray-200 bg-white p-4">
            <h2 className="text-lg font-semibold text-gray-900 mb-1">
              Open a durable approval request
            </h2>
            <p className="mb-1 text-xs text-gray-500">
              Recorded at pending_review and audited. The request is not executed and no tenant
              state is changed. The maker binds to you (the authenticated identity-only
              super_admin).
            </p>
            <p className="mb-3 text-xs text-gray-400" data-testid="dap-maker-readonly">
              maker (you) = {operatorId || '(unknown)'}
            </p>
            <div className="grid gap-3">
              <label className="block text-sm text-gray-700">
                Action id (optional; a recorded P18 request id)
                <input
                  className="mt-1 block w-full rounded border border-gray-300 p-2"
                  value={actionId}
                  onChange={(e) => setActionId(e.target.value)}
                  data-testid="dap-action-id-input"
                />
              </label>
              <label className="block text-sm text-gray-700">
                Action type (optional; resolves class + source when no action id)
                <input
                  className="mt-1 block w-full rounded border border-gray-300 p-2"
                  value={actionType}
                  onChange={(e) => setActionType(e.target.value)}
                  data-testid="dap-action-type-input"
                />
              </label>
              <label className="block text-sm text-gray-700">
                Tenant id (optional)
                <input
                  className="mt-1 block w-full rounded border border-gray-300 p-2"
                  value={tenantId}
                  onChange={(e) => setTenantId(e.target.value)}
                  data-testid="dap-tenant-input"
                />
              </label>
              <label className="block text-sm text-gray-700">
                Reason (required)
                <textarea
                  className="mt-1 block w-full rounded border border-gray-300 p-2"
                  rows={2}
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  data-testid="dap-reason-input"
                />
              </label>
              <label className="block text-sm text-gray-700">
                Idempotency key (required; only its SHA-256 digest is ever stored)
                <input
                  className="mt-1 block w-full rounded border border-gray-300 p-2"
                  value={idempotencyKey}
                  onChange={(e) => setIdempotencyKey(e.target.value)}
                  data-testid="dap-idempotency-input"
                />
              </label>
              <label className="block text-sm text-gray-700">
                Expires at (required, future)
                <input
                  type="datetime-local"
                  className="mt-1 block w-full rounded border border-gray-300 p-2"
                  value={expiresAt}
                  onChange={(e) => setExpiresAt(e.target.value)}
                  data-testid="dap-expires-input"
                />
              </label>
              <label className="block text-sm text-gray-700">
                Durable retain until (optional; defaults to expires_at)
                <input
                  type="datetime-local"
                  className="mt-1 block w-full rounded border border-gray-300 p-2"
                  value={retainUntil}
                  onChange={(e) => setRetainUntil(e.target.value)}
                  data-testid="dap-retain-input"
                />
              </label>
              <label className="inline-flex items-center gap-2 text-sm text-gray-700">
                <input
                  type="checkbox"
                  checked={confirm}
                  onChange={(e) => setConfirm(e.target.checked)}
                  data-testid="dap-confirm-input"
                />
                Confirm acknowledgement (required to open the request)
              </label>
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={!formValid || !confirm || createBusy}
                  onClick={createApproval}
                  className="rounded bg-primary-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                  data-testid="dap-create-btn"
                >
                  Open request
                </button>
              </div>
              {!formValid || !confirm ? (
                <p className="text-xs text-gray-400" data-testid="dap-form-hint">
                  A reason, an idempotency key, an expiry, and confirmation are required before a
                  durable approval request can be opened.
                </p>
              ) : null}
            </div>
          </section>

          {/* Create result */}
          {createResult ? (
            <ResultSection
              heading="Opened durable approval"
              record={createResult}
              testId="dap-create-result"
            />
          ) : null}

          {/* Durable approval queue */}
          <section
            className="rounded-lg border border-gray-200 bg-white p-4"
            data-testid="dap-queue"
          >
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">Durable approval queue</h2>
                <p className="text-xs text-gray-500">
                  Ephemeral memory queue; durable approvals are listed for review and are never
                  executed.
                </p>
              </div>
              <button
                type="button"
                onClick={loadQueue}
                className="rounded bg-gray-200 px-3 py-2 text-sm font-medium text-gray-800"
                data-testid="dap-refresh-btn"
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
                <p className="text-xs text-gray-500" data-testid="dap-queue-summary">
                  {queue.total} durable approvals; storage={queue.storage}; executed=
                  {String(queue.executed)}
                </p>
                {queue.items.length === 0 ? (
                  <p className="mt-2 text-xs text-gray-400" data-testid="dap-queue-empty">
                    No durable approvals opened yet.
                  </p>
                ) : (
                  <ul className="mt-2 divide-y divide-gray-100">
                    {queue.items.map((item) => {
                      const selected = detail?.approval_id === item.approval_id;
                      return (
                        <li
                          key={item.approval_id ?? item.action_type ?? 'unknown'}
                          className="py-2"
                          data-testid="dap-queue-item"
                        >
                          <div className="flex flex-wrap items-center gap-2 text-sm">
                            <span className="font-mono text-gray-900">
                              {item.action_type ?? '(no action type)'}
                            </span>
                            <StateBadge state={item.state} />
                            <SourceBadge source={item.source_status} />
                            <ActionClassBadge cls={item.action_class} />
                            <QuorumBadge record={item} />
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
                              data-testid="dap-review-btn"
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
              <p className="mt-3 text-xs text-gray-400">Refresh to load the durable approval queue.</p>
            )}
          </section>

          {/* Detail + decision panel */}
          {detail ? (
            <section
              className="space-y-4 rounded-lg border border-gray-200 bg-white p-4"
              data-testid="dap-detail"
            >
              <div>
                <h2 className="text-lg font-semibold text-gray-900">Durable approval detail</h2>
                <p className="text-xs text-gray-500">
                  Read-only request context. No raw reason, metadata, idempotency key, DSN, host,
                  or port is shown (only the one-way idempotency_key_digest / request_digest).
                </p>
              </div>
              {detailLoading ? (
                <Skeleton className="h-20 w-full rounded-lg" />
              ) : (
                <>
                  <DetailGrid record={detail} operatorId={operatorId} />
                  <CheckersLog checkers={detail.checkers} operatorId={operatorId} />
                </>
              )}

              {sourceBlocksApprove && detailIsPending ? (
                <div
                  className="rounded bg-yellow-50 p-3 text-xs text-yellow-800"
                  data-testid="dap-source-warning"
                >
                  The underlying P18 source status is {detail.source_status} and validation_status
                  is {detail.validation_status}. An unknown / unavailable or non-valid source is not
                  healthy and blocks an approve; reject remains available. Nothing is executed.
                </div>
              ) : null}

              {/* Decision controls: only on a pending approval, only for a
                  non-maker identity-only super_admin checker who has not yet
                  decided, and only after explicit confirmation. No execute
                  control. The maker is offered NO decision control. */}
              {detailIsPending ? (
                isMaker ? (
                  <div
                    className="rounded-lg border border-gray-200 bg-gray-50 p-3"
                    data-testid="dap-maker-blocked"
                  >
                    <h3 className="text-sm font-semibold text-gray-800 mb-1">
                      You are the maker on this durable approval
                    </h3>
                    <p className="text-xs text-gray-600">
                      Maker-checker separation forbids you from approving or rejecting a durable
                      approval you opened. A distinct identity-only super_admin checker must decide
                      it. No decision control is available to you here; nothing is executed.
                    </p>
                  </div>
                ) : myDecision !== null ? (
                  <div
                    className="rounded-lg border border-gray-200 bg-gray-50 p-3"
                    data-testid="dap-already-decided"
                  >
                    <h3 className="text-sm font-semibold text-gray-800 mb-1">
                      You already recorded a {myDecision} decision
                    </h3>
                    <p className="text-xs text-gray-600">
                      Each checker records at most one decision on a durable approval. No further
                      decision control is available to you here; nothing is executed.
                    </p>
                  </div>
                ) : (
                  <div className="rounded-lg border border-gray-200 p-3" data-testid="dap-decision">
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
                          data-testid="dap-decision-reason-input"
                        />
                      </label>
                      <label className="block text-sm text-gray-700">
                        Decision idempotency key (required)
                        <input
                          className="mt-1 block w-full rounded border border-gray-300 p-2"
                          value={decisionIdempotencyKey}
                          onChange={(e) => setDecisionIdempotencyKey(e.target.value)}
                          data-testid="dap-decision-idempotency-input"
                        />
                      </label>
                      <label className="inline-flex items-center gap-2 text-sm text-gray-700">
                        <input
                          type="checkbox"
                          checked={decisionConfirm}
                          onChange={(e) => setDecisionConfirm(e.target.checked)}
                          data-testid="dap-decision-confirm-input"
                        />
                        Confirm decision (required; approve resolves to approved_execution_blocked)
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
                          data-testid="dap-approve-btn"
                        >
                          Approve
                        </button>
                        <button
                          type="button"
                          disabled={!decisionFormValid || !decisionConfirm || decisionBusy}
                          onClick={() => submitDecision('reject')}
                          className="rounded bg-red-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                          data-testid="dap-reject-btn"
                        >
                          Reject
                        </button>
                      </div>
                    </div>
                  </div>
                )
              ) : (
                <p className="text-xs text-gray-500" data-testid="dap-no-decision">
                  This durable approval is not pending review; no decision control is available.
                  Approve resolves to approved_execution_blocked and is never executed.
                </p>
              )}
            </section>
          ) : null}

          {decisionResult ? (
            <ResultSection
              heading="Decision outcome"
              record={decisionResult}
              testId="dap-decision-result"
            />
          ) : null}
        </>
      )}
    </div>
  );
}

// -- Small presentational helpers (durability-is-not-execution aware) --------

function StateBadge({ state }: { state: DurableApprovalState | null }) {
  const tone = state ? STATE_TONE[state] ?? 'bg-gray-100 text-gray-600' : 'bg-gray-100 text-gray-600';
  const label =
    state === 'approved_execution_blocked'
      ? 'execution blocked'
      : state === 'pending_review'
        ? 'pending review'
        : state === 'failed_validation'
          ? 'failed validation'
          : state ?? 'unknown';
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${tone}`}
      data-testid="dap-state-badge"
    >
      {label}
    </span>
  );
}

function SourceBadge({ source }: { source: RegistrySourceStatus }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${SOURCE_TONE[source]}`}
      data-testid="dap-source-badge"
    >
      source: {source}
    </span>
  );
}

function ActionClassBadge({ cls }: { cls: DurableActionClass | null }) {
  return (
    <span
      className="inline-flex items-center rounded-full bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-800"
      data-testid="dap-class-badge"
    >
      class: {cls ?? 'unknown'}
    </span>
  );
}

function QuorumBadge({ record }: { record: DurableApprovalRecord }) {
  // quorum_met is shown RED: it means approved_execution_blocked (the ceiling),
  // never a green success. Pending quorum progress is amber/gray.
  const approve = approveCount(record.checkers);
  const met = record.quorum_met;
  const tone = met
    ? 'bg-red-100 text-red-800'
    : approve > 0
      ? 'bg-yellow-100 text-yellow-800'
      : 'bg-gray-100 text-gray-600';
  const label = met
    ? `quorum met ${approve}/${record.quorum_required}`
    : `quorum ${approve}/${record.quorum_required}`;
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${tone}`}
      data-testid="dap-quorum-badge"
    >
      {label}
    </span>
  );
}

function DetailGrid({
  record,
  operatorId,
}: {
  record: DurableApprovalRecord;
  operatorId: string;
}) {
  return (
    <dl
      className="grid gap-x-4 gap-y-1 text-xs text-gray-700 sm:grid-cols-2"
      data-testid="dap-detail-grid"
    >
      <DetailRow label="approval_id" value={record.approval_id} />
      <DetailRow label="action_id" value={record.action_id} />
      <DetailRow label="action_type" value={record.action_type} />
      <DetailRow label="action_class" value={record.action_class} />
      <DetailRow label="tenant_id" value={record.tenant_id} />
      <DetailRow label="state" value={record.state} />
      <DetailRow label="maker" value={record.maker} highlight={record.maker === operatorId} />
      <DetailRow label="maker_at" value={record.maker_at} />
      <DetailRow label="quorum_required" value={String(record.quorum_required)} />
      <DetailRow label="quorum_met" value={String(record.quorum_met)} />
      <DetailRow label="decision" value={record.decision} />
      <DetailRow label="source_status" value={record.source_status} />
      <DetailRow label="validation_status" value={record.validation_status} />
      <DetailRow label="reason (redacted)" value={record.reason} />
      <DetailRow label="request_digest" value={shortDigest(record.request_digest)} />
      <DetailRow label="idempotency_key_digest" value={shortDigest(record.idempotency_key_digest)} />
      <DetailRow label="execution_gate" value={record.execution_gate} />
      <DetailRow label="execution_allowed" value={String(record.execution_allowed)} />
      <DetailRow label="redaction_applied" value={String(record.redaction_applied)} />
      <DetailRow label="retention_class" value={record.retention_class} />
      <DetailRow label="expires_at" value={record.expires_at} />
      <DetailRow label="durable_retain_until" value={record.durable_retain_until} />
      <DetailRow label="audit_event_id" value={record.audit_event_id} />
      <DetailRow label="storage" value={record.storage} />
      <DetailRow label="executed" value={String(record.executed)} />
    </dl>
  );
}

function shortDigest(value: string | null): string {
  // Only the first 12 hex chars of a one-way digest are shown -- enough to
  // identify the record, never a raw key. A 12-char run is also well under the
  // detect-secrets high-entropy threshold.
  if (!value) return '(none)';
  return value.length > 12 ? `${value.slice(0, 12)}...` : value;
}

function CheckersLog({
  checkers,
  operatorId,
}: {
  checkers: CheckerDecisionSummary[];
  operatorId: string;
}) {
  if (checkers.length === 0) {
    return (
      <p className="text-xs text-gray-400" data-testid="dap-checkers-empty">
        No checker decisions recorded yet.
      </p>
    );
  }
  return (
    <div data-testid="dap-checkers-log">
      <p className="mb-1 text-xs font-semibold text-gray-700">Checker decisions</p>
      <ul className="divide-y divide-gray-100">
        {checkers.map((c, idx) => (
          <li key={`${c.checker_id}-${idx}`} className="py-1 text-xs text-gray-700">
            <span className="font-mono">{c.checker_id}</span>
            {c.checker_id === operatorId ? ' (you)' : ''}
            {' -- '}
            <span
              className={
                c.decision === 'approve'
                  ? 'font-medium text-blue-700'
                  : 'font-medium text-red-700'
              }
            >
              {c.decision}
            </span>
            {' at '}
            <span className="text-gray-500">{c.decided_at}</span>
            {c.reason_redacted ? ` -- ${c.reason_redacted}` : ''}
          </li>
        ))}
      </ul>
    </div>
  );
}

function DetailRow({
  label,
  value,
  highlight,
}: {
  label: string;
  value: string | null;
  highlight?: boolean;
}) {
  return (
    <div className="flex gap-2">
      <dt className="font-mono text-gray-400">{label}</dt>
      <dd className={highlight ? 'font-semibold text-primary-700' : 'text-gray-800'}>
        {value === null || value === '' ? '(none)' : value}
      </dd>
    </div>
  );
}

function ResultSection({
  heading,
  record,
  testId,
}: {
  heading: string;
  record: DurableApprovalRecord;
  testId: string;
}) {
  const blocked =
    record.state === 'approved_execution_blocked' || record.result === 'approved';
  return (
    <section
      className="rounded-lg border border-gray-200 bg-white p-4"
      data-testid={testId}
    >
      <h3 className="mb-2 text-sm font-semibold text-gray-900">{heading}</h3>
      <div className="flex flex-wrap items-center gap-3">
        <span
          className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
            record.result === 'recorded' || record.result === 'approved'
              ? 'bg-blue-100 text-blue-800'
              : record.result === 'rejected'
                ? 'bg-red-100 text-red-800'
                : record.result === 'quorum_pending'
                  ? 'bg-yellow-100 text-yellow-800'
                  : 'bg-gray-100 text-gray-700'
          }`}
          data-testid="dap-result-badge"
        >
          {record.result}
        </span>
        <StateBadge state={record.state} />
        <SourceBadge source={record.source_status} />
        <ActionClassBadge cls={record.action_class} />
        {record.state === 'pending_review' || record.state === 'approved_execution_blocked' ? (
          <QuorumBadge record={record} />
        ) : null}
        <span className="text-xs text-gray-400">executed={String(record.executed)}</span>
        <span className="text-xs text-gray-400">
          execution_allowed={String(record.execution_allowed)}
        </span>
      </div>
      <p className="mt-2 text-sm font-semibold text-gray-900" data-testid="dap-not-executed">
        {blocked
          ? 'Approved: resolves to approved_execution_blocked (executed=false).'
          : 'Recorded: not executed (executed=false).'}
      </p>
      <p className="mt-1 text-sm text-gray-700">{record.message}</p>
      {record.approval_id ? (
        <p className="mt-1 text-xs text-gray-500">approval id: {record.approval_id}</p>
      ) : null}
    </section>
  );
}
