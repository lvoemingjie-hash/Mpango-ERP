/**
 * PlatformOperatorTasksPage -- P23 Operator Task / Notification Queue console
 * (P23-D, frontend-only).
 *
 * A TASK IS A VIEW, NOT AN EXECUTOR. A NOTIFICATION IS A RECORD, NOT A
 * DELIVERY. This page is the read / triage / record surface on top of the
 * P23-B/C backend skeleton. It lists the operator task queue, reads a single
 * task with its append-only audit history and its notification-event records,
 * runs the PRESENTATION-ONLY state machine (acknowledge / self-assign /
 * in-progress / complete / dismiss), and manually reads the safe source
 * surfaces through materialize. It never executes anything.
 *
 * Hard UI rules (P23-A, mirrored from the backend contract):
 *   - No execute / run / apply / dispatch / trigger control. The only controls
 *     are the triage transitions and a read-only materialize. There is no
 *     "execute", "approve", "decide", "send", "deliver", or "apply" button.
 *   - Completing a task records operator attention only; it never runs a P22
 *     action and never makes the completer the P22 executor. Complete requires
 *     a redacted evidence note OR a linked completed id (evidence_ref) AND a
 *     closed linked gate; a 409 denial (COMPLETE_DENIED_NO_EVIDENCE /
 *     COMPLETE_DENIED_GATE_OPEN) is surfaced cleanly inline.
 *   - source_unknown is NEVER healthy and backup_check_warning is NEVER success:
 *     the display badge is never green for either task type, regardless of the
 *     label the backend supplied (defended client-side in resolveOperatorDisplayTone).
 *   - Notification events are RECORDS of attention, never deliveries. No channel
 *     is wired; delivery_state is shown as recorded | suppressed only.
 *   - Redaction is total: only *_redacted / summary_redacted fields and echo-safe
 *     ids are rendered; redaction_applied === true is displayed. No raw reason,
 *     secret, DSN, host, port, token, cookie, auth header, or tenant-business
 *     payload is ever shown.
 *
 * storage is in-memory; the queue is a view, not the system of record; dismissed
 * / expired tasks retain their full audit history.
 *
 * Route is platform-only (/platform/operator-tasks) behind the identity-only
 * PlatformRoute guard. Reuses the existing platformService Axios client.
 */
import { useCallback, useEffect, useState } from 'react';
import { platformService } from '@/services/platformApi';
import { Skeleton } from '@/components/ui/Skeleton';
import { useAuthStore } from '@/stores/authStore';
import { isIdentityPlatformOperator } from '@/router/guards';
import {
  ALLOWED_OPERATOR_TRANSITIONS,
  OPERATOR_SEVERITIES,
  OPERATOR_SOURCE_STATUSES,
  OPERATOR_TASK_STATES,
  OPERATOR_TASK_TYPES,
  isTerminalOperatorTaskState,
  resolveOperatorDisplayTone,
  type OperatorDisplayStatus,
  type OperatorDisplayTone,
  type OperatorMaterializeSummary,
  type OperatorNotificationEvent,
  type OperatorOwnerRole,
  type OperatorTask,
  type OperatorTaskAuditEvent,
  type OperatorTaskDetail,
  type OperatorTaskListFilters,
  type OperatorTaskSeverity,
  type OperatorTaskState,
  type OperatorTaskTransitionRequest,
  type OperatorTaskType,
} from '@/types/platformOperatorTasks';

const DEFAULT_FILTERS: OperatorTaskListFilters = {
  severity: undefined,
  task_type: undefined,
  state: undefined,
  source_status: undefined,
};

// -- Tone maps (Tailwind classes) --------------------------------------------

const DISPLAY_TONE_CLASS: Record<OperatorDisplayTone, string> = {
  green: 'bg-green-100 text-green-800',
  yellow: 'bg-yellow-100 text-yellow-800',
  gray: 'bg-gray-100 text-gray-600',
  red: 'bg-red-100 text-red-800',
  blue: 'bg-blue-100 text-blue-800',
};

const SEVERITY_TONE: Record<OperatorTaskSeverity, string> = {
  high: 'bg-red-100 text-red-800',
  medium: 'bg-yellow-100 text-yellow-800',
  low: 'bg-gray-100 text-gray-600',
};

const STATE_TONE: Record<OperatorTaskState, string> = {
  open: 'bg-blue-100 text-blue-800',
  acknowledged: 'bg-blue-100 text-blue-800',
  in_progress: 'bg-yellow-100 text-yellow-800',
  waiting_on_approval: 'bg-yellow-100 text-yellow-800',
  waiting_on_source: 'bg-yellow-100 text-yellow-800',
  completed: 'bg-gray-100 text-gray-600',
  dismissed: 'bg-gray-100 text-gray-600',
  expired: 'bg-gray-100 text-gray-600',
  failed: 'bg-red-100 text-red-800',
};

// -- Small helpers -----------------------------------------------------------

function unwrap<T>(res: { data?: unknown }): T {
  const data = res.data as { data?: T } | T | undefined;
  if (data && typeof data === 'object' && 'data' in (data as Record<string, unknown>)) {
    return (data as { data: T }).data;
  }
  return data as T;
}

/** Extract the P23 FastAPI HTTPException body ({detail: {code, message}}). */
function extractDenial(err: unknown): { code: string | null; message: string } {
  const anyErr = err as {
    response?: { data?: { detail?: { code?: string; message?: string } } };
    message?: string;
  } | undefined;
  const detail = anyErr?.response?.data?.detail;
  if (detail && (detail.code || detail.message)) {
    return { code: detail.code ?? null, message: detail.message ?? 'Transition denied.' };
  }
  return {
    code: null,
    message: err instanceof Error ? err.message : 'Transition failed.',
  };
}

const OWNER_ROLE_LABEL: Record<OperatorOwnerRole, string> = {
  super_admin: 'super admin',
  engineering_operator: 'engineering operator',
  support_operator: 'support operator',
};

export function PlatformOperatorTasksPage() {
  const user = useAuthStore((s) => s.user);
  const canOperate = isIdentityPlatformOperator(user);

  // -- queue + filters --
  const [queue, setQueue] = useState<OperatorTask[] | null>(null);
  const [queueMeta, setQueueMeta] = useState<{
    total: number;
    active_count: number;
    limit: number;
    offset: number;
  } | null>(null);
  const [queueLoading, setQueueLoading] = useState(false);
  const [queueError, setQueueError] = useState<string | null>(null);

  const [draftFilters, setDraftFilters] =
    useState<OperatorTaskListFilters>(DEFAULT_FILTERS);
  const [appliedFilters, setAppliedFilters] =
    useState<OperatorTaskListFilters>(DEFAULT_FILTERS);

  // -- materialize (P23-C) --
  const [materializeResult, setMaterializeResult] =
    useState<OperatorMaterializeSummary | null>(null);
  const [materializeBusy, setMaterializeBusy] = useState(false);
  const [materializeError, setMaterializeError] = useState<string | null>(null);

  // -- detail + transitions --
  const [detail, setDetail] = useState<OperatorTaskDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const [evidence, setEvidence] = useState('');
  const [evidenceRef, setEvidenceRef] = useState('');
  const [transitionReason, setTransitionReason] = useState('');
  const [completeConfirm, setCompleteConfirm] = useState(false);

  const [transitionBusy, setTransitionBusy] = useState(false);
  const [denial, setDenial] = useState<{ code: string | null; message: string } | null>(null);
  const [transitionMessage, setTransitionMessage] = useState<string | null>(null);

  const loadQueue = useCallback(() => {
    setQueueLoading(true);
    setQueueError(null);
    platformService
      .listOperatorTasks(50, 0, appliedFilters)
      .then((res) => {
        const body = unwrap<OperatorTask[] | { tasks: OperatorTask[] }>(res);
        // Defensive: accept either the queue object or its tasks array.
        const tasks = Array.isArray(body)
          ? body
          : (body as { tasks?: OperatorTask[] }).tasks ?? [];
        const meta = unwrap<{ total: number; active_count: number; limit: number; offset: number }>(res);
        setQueue(tasks);
        setQueueMeta({
          total: meta.total ?? tasks.length,
          active_count: meta.active_count ?? tasks.length,
          limit: meta.limit ?? 50,
          offset: meta.offset ?? 0,
        });
      })
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : 'Failed to load operator task queue';
        setQueueError(msg);
        setQueue(null);
        setQueueMeta(null);
      })
      .finally(() => setQueueLoading(false));
  }, [appliedFilters]);

  useEffect(() => {
    if (canOperate) loadQueue();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canOperate, loadQueue]);

  const loadDetail = useCallback((taskId: string) => {
    setDetailLoading(true);
    platformService
      .getOperatorTask(taskId)
      .then((res) => setDetail(unwrap<OperatorTaskDetail>(res)))
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : 'Failed to load task detail';
        setQueueError(msg);
        setDetail(null);
      })
      .finally(() => setDetailLoading(false));
  }, []);

  const runMaterialize = () => {
    if (!canOperate || materializeBusy) return;
    setMaterializeBusy(true);
    setMaterializeError(null);
    setMaterializeResult(null);
    platformService
      .materializeOperatorTasks()
      .then((res) => {
        setMaterializeResult(unwrap<OperatorMaterializeSummary>(res));
        loadQueue();
      })
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : 'Materialize failed';
        setMaterializeError(msg);
      })
      .finally(() => setMaterializeBusy(false));
  };

  const selectTask = (taskId: string | null) => {
    setDenial(null);
    setTransitionMessage(null);
    setEvidence('');
    setEvidenceRef('');
    setTransitionReason('');
    setCompleteConfirm(false);
    if (!taskId) {
      setDetail(null);
      return;
    }
    loadDetail(taskId);
  };

  const applyFilters = () => {
    setAppliedFilters({ ...draftFilters });
    // loadQueue fires via the appliedFilters effect dependency.
  };

  const resetFilters = () => {
    setDraftFilters(DEFAULT_FILTERS);
    setAppliedFilters(DEFAULT_FILTERS);
  };

  // -- transition plumbing ---------------------------------------------------

  const payloadFor = (): OperatorTaskTransitionRequest => {
    const p: OperatorTaskTransitionRequest = {};
    const reason = transitionReason.trim();
    if (reason) p.reason = reason;
    return p;
  };

  const runTransition = (
    fn: (taskId: string, payload: OperatorTaskTransitionRequest) =>
      Promise<{ data?: unknown }>,
    label: string,
  ) => {
    if (!detail || !canOperate || transitionBusy) return;
    setTransitionBusy(true);
    setDenial(null);
    setTransitionMessage(null);
    fn(detail.task_id, payloadFor())
      .then((res) => {
        const result = unwrap<{ task: OperatorTask; transition: string }>(res);
        setTransitionMessage(`${label}: ${result.transition}`);
        // Refresh the authoritative detail + queue from the returned task.
        if (result.task?.task_id) loadDetail(result.task.task_id);
        loadQueue();
      })
      .catch((err: unknown) => {
        const d = extractDenial(err);
        setDenial(d);
      })
      .finally(() => setTransitionBusy(false));
  };

  // -- complete gate ---------------------------------------------------------

  const evidenceProvided =
    evidence.trim().length > 0 || evidenceRef.trim().length > 0;
  const gateOpen = detail?.linked_gate_open === true;
  const canReachCompleted =
    !!detail && ALLOWED_OPERATOR_TRANSITIONS[detail.state].includes('completed');
  const completeDisabled =
    !canReachCompleted ||
    !evidenceProvided ||
    gateOpen ||
    !completeConfirm ||
    transitionBusy;

  const submitComplete = () => {
    if (!detail || completeDisabled) return;
    setTransitionBusy(true);
    setDenial(null);
    setTransitionMessage(null);
    const payload: OperatorTaskTransitionRequest = {};
    const ev = evidence.trim();
    const ref = evidenceRef.trim();
    if (ev) payload.evidence = ev;
    if (ref) payload.evidence_ref = ref;
    const reason = transitionReason.trim();
    if (reason) payload.reason = reason;
    platformService
      .completeOperatorTask(detail.task_id, payload)
      .then((res) => {
        const result = unwrap<{ task: OperatorTask; transition: string }>(res);
        setTransitionMessage(`Complete: ${result.transition}`);
        if (result.task?.task_id) loadDetail(result.task.task_id);
        loadQueue();
      })
      .catch((err: unknown) => {
        setDenial(extractDenial(err));
      })
      .finally(() => setTransitionBusy(false));
  };

  const queueErrorBanner = queueError || materializeError;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900" data-testid="ot-title">
          Operator Tasks
        </h1>
        <p className="mt-1 text-sm text-gray-500" data-testid="ot-subtitle">
          A task is a view, not an executor. A notification is a record, not a delivery. Tasks are
          listed, read, and triaged here; completing one records operator attention only and never
          runs a controlled action. No execution, approval decision, or notification delivery
          happens on this page.
        </p>
      </div>

      {/* Persistent invariants */}
      <section
        className="rounded-lg border border-gray-200 bg-gray-50 p-4"
        data-testid="ot-invariants"
      >
        <h2 className="text-sm font-semibold text-gray-700">Console invariants</h2>
        <ul className="mt-2 grid gap-1 text-xs text-gray-600 sm:grid-cols-2">
          <li>a task is a view, not an executor</li>
          <li>a notification is a record, not a delivery</li>
          <li>redaction_applied = true (every free-text field)</li>
          <li>source_unknown is never healthy</li>
          <li>backup_check_warning is never success</li>
          <li>no execute / run / apply / dispatch control</li>
        </ul>
      </section>

      {queueErrorBanner && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4">
          <p className="text-sm text-red-700" data-testid="ot-error">
            {queueErrorBanner}
          </p>
        </div>
      )}

      {!canOperate ? (
        <div
          className="rounded-lg border border-gray-200 bg-white p-4"
          data-testid="ot-no-access"
        >
          <p className="text-sm text-gray-700">
            Operator task controls are hidden for tenant-contextual identities. The platform
            operator task surface is identity-only.
          </p>
        </div>
      ) : (
        <>
          {/* Materialize (P23-C; read-only; NOT a scheduler / worker) */}
          <section
            className="rounded-lg border border-gray-200 bg-white p-4"
            data-testid="ot-materialize"
          >
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">
                  Materialize tasks from sources
                </h2>
                <p className="text-xs text-gray-500">
                  Read-only. Reads the safe P19 approval and P22 backup-check source surfaces and
                  materializes typed, redacted tasks. This is a manual read/materialize operation: it
                  is not a scheduler, not a worker, executes nothing, approves nothing, and delivers
                  nothing.
                </p>
              </div>
              <button
                type="button"
                onClick={runMaterialize}
                disabled={materializeBusy}
                className="rounded bg-gray-200 px-3 py-2 text-sm font-medium text-gray-800 disabled:opacity-50"
                data-testid="ot-materialize-btn"
              >
                {materializeBusy ? 'Materializing...' : 'Materialize tasks'}
              </button>
            </div>
            {materializeResult ? (
              <div className="mt-3" data-testid="ot-materialize-result">
                <p className="text-xs text-gray-500" data-testid="ot-materialize-summary">
                  created={materializeResult.total_created} deduped={materializeResult.total_deduped}{' '}
                  skipped={materializeResult.total_skipped} unavailable={materializeResult.total_unavailable}
                </p>
                <ul className="mt-2 divide-y divide-gray-100">
                  {materializeResult.sources.map((s) => (
                    <li key={s.source} className="py-1 text-xs text-gray-600" data-testid="ot-materialize-source">
                      <span className="font-mono text-gray-800">{s.source}</span>: read={s.read} created=
                      {s.created} deduped={s.deduped} skipped={s.skipped} unavailable={s.unavailable}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </section>

          {/* Filters */}
          <section
            className="rounded-lg border border-gray-200 bg-white p-4"
            data-testid="ot-filters"
          >
            <h2 className="text-lg font-semibold text-gray-900 mb-2">Filters</h2>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <label className="block text-sm text-gray-700">
                Severity
                <select
                  className="mt-1 block w-full rounded border border-gray-300 p-2"
                  value={draftFilters.severity ?? ''}
                  onChange={(e) =>
                    setDraftFilters({
                      ...draftFilters,
                      severity: (e.target.value || undefined) as OperatorTaskSeverity | undefined,
                    })
                  }
                  data-testid="ot-filter-severity"
                >
                  <option value="">(any)</option>
                  {OPERATOR_SEVERITIES.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-sm text-gray-700">
                Task type
                <select
                  className="mt-1 block w-full rounded border border-gray-300 p-2"
                  value={draftFilters.task_type ?? ''}
                  onChange={(e) =>
                    setDraftFilters({
                      ...draftFilters,
                      task_type: (e.target.value || undefined) as OperatorTaskType | undefined,
                    })
                  }
                  data-testid="ot-filter-task-type"
                >
                  <option value="">(any)</option>
                  {OPERATOR_TASK_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-sm text-gray-700">
                State
                <select
                  className="mt-1 block w-full rounded border border-gray-300 p-2"
                  value={draftFilters.state ?? ''}
                  onChange={(e) =>
                    setDraftFilters({
                      ...draftFilters,
                      state: (e.target.value || undefined) as OperatorTaskState | undefined,
                    })
                  }
                  data-testid="ot-filter-state"
                >
                  <option value="">(any)</option>
                  {OPERATOR_TASK_STATES.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-sm text-gray-700">
                Source status
                <select
                  className="mt-1 block w-full rounded border border-gray-300 p-2"
                  value={draftFilters.source_status ?? ''}
                  onChange={(e) =>
                    setDraftFilters({
                      ...draftFilters,
                      source_status: (e.target.value || undefined) as
                        | (typeof OPERATOR_SOURCE_STATUSES)[number]
                        | undefined,
                    })
                  }
                  data-testid="ot-filter-source-status"
                >
                  <option value="">(any)</option>
                  {OPERATOR_SOURCE_STATUSES.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="mt-3 flex gap-2">
              <button
                type="button"
                onClick={applyFilters}
                className="rounded bg-primary-600 px-3 py-2 text-sm font-medium text-white"
                data-testid="ot-filter-apply"
              >
                Apply filters
              </button>
              <button
                type="button"
                onClick={resetFilters}
                className="rounded bg-gray-200 px-3 py-2 text-sm font-medium text-gray-800"
                data-testid="ot-filter-reset"
              >
                Reset
              </button>
            </div>
          </section>

          {/* Queue */}
          <section
            className="rounded-lg border border-gray-200 bg-white p-4"
            data-testid="ot-queue"
          >
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">Task queue</h2>
                <p className="text-xs text-gray-500">
                  Read-only; ranked by severity then recency. The queue is a view, not the system of
                  record; dismissed / expired tasks retain their full audit history.
                </p>
              </div>
              <button
                type="button"
                onClick={loadQueue}
                className="rounded bg-gray-200 px-3 py-2 text-sm font-medium text-gray-800"
                data-testid="ot-refresh-btn"
              >
                Refresh
              </button>
            </div>
            {queueLoading && !queue ? (
              <div className="mt-3">
                <Skeleton className="h-16 w-full rounded-lg" />
              </div>
            ) : queue ? (
              <div className="mt-3">
                <p className="text-xs text-gray-500" data-testid="ot-queue-summary">
                  {queueMeta ? `${queueMeta.total} tasks (${queueMeta.active_count} active)` : ''};
                  redaction_applied=true
                </p>
                {queue.length === 0 ? (
                  <p className="mt-2 text-xs text-gray-400" data-testid="ot-queue-empty">
                    No operator tasks match the current filters.
                  </p>
                ) : (
                  <ul className="mt-2 divide-y divide-gray-100">
                    {queue.map((item) => (
                      <li key={item.task_id} className="py-2" data-testid="ot-queue-item">
                        <div className="flex flex-wrap items-center gap-2 text-sm">
                          <DisplayBadge taskType={item.task_type} displayStatus={item.display_status} />
                          <span
                            className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${SEVERITY_TONE[item.severity]}`}
                            data-testid="ot-severity-badge"
                          >
                            severity: {item.severity}
                          </span>
                          <span
                            className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${STATE_TONE[item.state]}`}
                            data-testid="ot-state-badge"
                          >
                            {item.state}
                          </span>
                          <span className="font-mono text-gray-900">{item.task_type}</span>
                          <span className="text-xs text-gray-400">
                            redaction_applied={String(item.redaction_applied)}
                          </span>
                          <button
                            type="button"
                            onClick={() => selectTask(item.task_id)}
                            className={`rounded px-2 py-1 text-xs font-medium ${
                              detail?.task_id === item.task_id
                                ? 'bg-primary-600 text-white'
                                : 'bg-gray-200 text-gray-800'
                            }`}
                            data-testid="ot-view-btn"
                          >
                            View
                          </button>
                        </div>
                        <p className="mt-1 truncate text-xs text-gray-600" data-testid="ot-queue-summary-text">
                          {item.summary_redacted}
                        </p>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ) : (
              <p className="mt-3 text-xs text-gray-400">Refresh to load the task queue.</p>
            )}
          </section>

          {/* Detail + transition panel */}
          {detail ? (
            <section
              className="space-y-4 rounded-lg border border-gray-200 bg-white p-4"
              data-testid="ot-detail"
            >
              <div>
                <h2 className="text-lg font-semibold text-gray-900">Task detail</h2>
                <p className="text-xs text-gray-500">
                  Read-only. Only redacted fields and echo-safe ids are shown; no raw reason, secret,
                  DSN, host, port, token, or tenant-business payload is displayed.
                </p>
              </div>
              {detailLoading ? (
                <Skeleton className="h-20 w-full rounded-lg" />
              ) : (
                <DetailGrid record={detail} />
              )}

              {/* Audit history */}
              <div data-testid="ot-audit-list">
                <h3 className="mb-1 text-sm font-semibold text-gray-800">
                  Audit history ({detail.audit_events.length}; append-only)
                </h3>
                {detail.audit_events.length === 0 ? (
                  <p className="text-xs text-gray-400">No audit events recorded.</p>
                ) : (
                  <ul className="divide-y divide-gray-100">
                    {detail.audit_events.map((ev) => (
                      <AuditRow key={ev.event_id} event={ev} />
                    ))}
                  </ul>
                )}
              </div>

              {/* Notification events (records, not deliveries) */}
              <div data-testid="ot-notification-list">
                <h3 className="mb-1 text-sm font-semibold text-gray-800">
                  Notification events ({detail.notification_events.length}; records, not deliveries)
                </h3>
                <p className="mb-1 text-xs text-gray-500">
                  These are records of attention. No channel is wired; nothing is delivered.
                </p>
                {detail.notification_events.length === 0 ? (
                  <p className="text-xs text-gray-400">No notification events recorded.</p>
                ) : (
                  <ul className="divide-y divide-gray-100">
                    {detail.notification_events.map((ev) => (
                      <NotificationRow key={ev.event_id} event={ev} />
                    ))}
                  </ul>
                )}
              </div>

              {/* Transition controls (presentation only; no execute control) */}
              {isTerminalOperatorTaskState(detail.state) ? (
                <p className="text-xs text-gray-500" data-testid="ot-terminal-note">
                  This task is in a terminal state ({detail.state}); no transition is available. The
                  audit history is retained. Nothing is executed.
                </p>
              ) : (
                <div className="rounded-lg border border-gray-200 p-3" data-testid="ot-transitions">
                  <h3 className="mb-2 text-sm font-semibold text-gray-800">
                    Triage (state management only; not executed)
                  </h3>

                  {gateOpen && canReachCompleted ? (
                    <div
                      className="mb-3 rounded bg-yellow-50 p-3 text-xs text-yellow-800"
                      data-testid="ot-gate-warning"
                    >
                      The linked gate is still open (linked_gate_open=true). Completing this task is
                      blocked until the gate closes. Nothing is executed.
                    </div>
                  ) : null}

                  <label className="block text-sm text-gray-700">
                    Triage reason (optional; redacted)
                    <textarea
                      className="mt-1 block w-full rounded border border-gray-300 p-2"
                      rows={2}
                      value={transitionReason}
                      onChange={(e) => setTransitionReason(e.target.value)}
                      data-testid="ot-reason-input"
                    />
                  </label>

                  <div className="mt-3 flex flex-wrap gap-2">
                    <TransitionButton
                      testId="ot-ack-btn"
                      label="Acknowledge"
                      disabled={
                        transitionBusy ||
                        !ALLOWED_OPERATOR_TRANSITIONS[detail.state].includes('acknowledged')
                      }
                      onClick={() =>
                        runTransition(
                          (id, p) => platformService.acknowledgeOperatorTask(id, p),
                          'Acknowledge',
                        )
                      }
                    />
                    <TransitionButton
                      testId="ot-in-progress-btn"
                      label="In progress"
                      disabled={
                        transitionBusy ||
                        !ALLOWED_OPERATOR_TRANSITIONS[detail.state].includes('in_progress')
                      }
                      onClick={() =>
                        runTransition(
                          (id, p) => platformService.markOperatorTaskInProgress(id, p),
                          'In progress',
                        )
                      }
                    />
                    <TransitionButton
                      testId="ot-self-assign-btn"
                      label="Self-assign"
                      disabled={transitionBusy}
                      onClick={() =>
                        runTransition(
                          (id, p) => platformService.selfAssignOperatorTask(id, p),
                          'Self-assign',
                        )
                      }
                    />
                    <TransitionButton
                      testId="ot-dismiss-btn"
                      label="Dismiss"
                      disabled={
                        transitionBusy ||
                        !ALLOWED_OPERATOR_TRANSITIONS[detail.state].includes('dismissed')
                      }
                      onClick={() =>
                        runTransition(
                          (id, p) => platformService.dismissOperatorTask(id, p),
                          'Dismiss',
                        )
                      }
                    />
                  </div>

                  {/* Complete gate */}
                  {canReachCompleted ? (
                    <div className="mt-3 rounded border border-gray-200 p-3" data-testid="ot-complete">
                      <h4 className="text-sm font-semibold text-gray-800">
                        Complete (records attention only; never executes)
                      </h4>
                      <p className="mt-1 text-xs text-gray-500">
                        Requires a redacted evidence note or a linked completed id, AND a closed
                        linked gate. Completing this task does not run a P22 action and does not make
                        you the P22 executor.
                      </p>
                      <div className="mt-2 grid gap-3">
                        <label className="block text-sm text-gray-700">
                          Evidence note (required, or evidence ref)
                          <textarea
                            className="mt-1 block w-full rounded border border-gray-300 p-2"
                            rows={2}
                            value={evidence}
                            onChange={(e) => setEvidence(e.target.value)}
                            data-testid="ot-evidence-input"
                          />
                        </label>
                        <label className="block text-sm text-gray-700">
                          Evidence ref (linked completed id; alternative to note)
                          <input
                            className="mt-1 block w-full rounded border border-gray-300 p-2"
                            value={evidenceRef}
                            onChange={(e) => setEvidenceRef(e.target.value)}
                            data-testid="ot-evidence-ref-input"
                          />
                        </label>
                        <label className="inline-flex items-center gap-2 text-sm text-gray-700">
                          <input
                            type="checkbox"
                            checked={completeConfirm}
                            onChange={(e) => setCompleteConfirm(e.target.checked)}
                            data-testid="ot-complete-confirm"
                          />
                          Confirm completion (records attention; not executed)
                        </label>
                        <div className="flex gap-2">
                          <button
                            type="button"
                            disabled={completeDisabled}
                            onClick={submitComplete}
                            className="rounded bg-primary-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                            data-testid="ot-complete-btn"
                          >
                            Complete
                          </button>
                        </div>
                        {completeDisabled && !completeConfirm ? (
                          <p className="text-xs text-gray-400" data-testid="ot-complete-hint">
                            A redacted evidence note or evidence ref, and confirmation, are required
                            before this task can be completed.
                          </p>
                        ) : null}
                      </div>
                    </div>
                  ) : null}

                  {denial ? (
                    <div
                      className="mt-3 rounded bg-red-50 p-3 text-xs text-red-800"
                      data-testid="ot-denial"
                    >
                      <span className="font-mono">{denial.code ?? 'DENIED'}</span>: {denial.message}{' '}
                      The task state was not changed; the denial is recorded in the audit history.
                    </div>
                  ) : null}

                  {transitionMessage ? (
                    <div
                      className="mt-3 rounded bg-blue-50 p-3 text-xs text-blue-800"
                      data-testid="ot-transition-ok"
                    >
                      {transitionMessage}
                    </div>
                  ) : null}
                </div>
              )}
            </section>
          ) : null}
        </>
      )}
    </div>
  );
}

// -- Small presentational helpers (view-not-executor aware) ------------------

function DisplayBadge({
  taskType,
  displayStatus,
}: {
  taskType: OperatorTaskType;
  displayStatus: OperatorDisplayStatus;
}) {
  const tone = resolveOperatorDisplayTone(taskType, displayStatus);
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${DISPLAY_TONE_CLASS[tone]}`}
      data-testid="ot-display-badge"
      data-tone={tone}
    >
      display: {displayStatus}
    </span>
  );
}

function DetailGrid({ record }: { record: OperatorTaskDetail }) {
  return (
    <dl
      className="grid gap-x-4 gap-y-1 text-xs text-gray-700 sm:grid-cols-2"
      data-testid="ot-detail-grid"
    >
      <DetailRow label="task_id" value={record.task_id} />
      <DetailRow label="task_type" value={record.task_type} />
      <DetailRow label="state" value={record.state} />
      <DetailRow label="severity" value={record.severity} />
      <DetailRow label="display_status" value={record.display_status} />
      <DetailRow label="source_status" value={record.source_status} />
      <DetailRow label="tenant_id" value={record.tenant_id} />
      <DetailRow label="actor_scope" value={record.actor_scope} />
      <DetailRow label="owner_role" value={record.owner_role ? OWNER_ROLE_LABEL[record.owner_role] : null} />
      <DetailRow label="owner_actor_id" value={record.owner_actor_id} />
      <DetailRow label="summary (redacted)" value={record.summary_redacted} />
      <DetailRow label="reason (redacted)" value={record.reason_redacted} />
      <DetailRow label="evidence_ref" value={record.evidence_ref} />
      <DetailRow label="linked_action_id" value={record.linked_action_id} />
      <DetailRow label="linked_approval_id" value={record.linked_approval_id} />
      <DetailRow label="linked_execution_id" value={record.linked_execution_id} />
      <DetailRow label="linked_dry_run_ref" value={record.linked_dry_run_ref} />
      <DetailRow label="linked_source_ref" value={record.linked_source_ref} />
      <DetailRow label="linked_incident_id" value={record.linked_incident_id} />
      <DetailRow label="linked_gate_open" value={String(record.linked_gate_open)} />
      <DetailRow label="correlation_id" value={record.correlation_id} />
      <DetailRow label="dedup_key_digest" value={record.dedup_key_digest} />
      <DetailRow label="ttl_expires_at" value={record.ttl_expires_at} />
      <DetailRow label="created_at" value={record.created_at} />
      <DetailRow label="updated_at" value={record.updated_at} />
      <DetailRow label="redaction_applied" value={String(record.redaction_applied)} />
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

function AuditRow({ event }: { event: OperatorTaskAuditEvent }) {
  return (
    <li className="py-2 text-xs text-gray-700" data-testid="ot-audit-item">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-gray-900">{event.transition}</span>
        <span className="text-gray-500">
          {event.previous_state} -&gt; {event.next_state}
        </span>
        <span className="text-gray-400">
          {event.actor_id ?? 'system'} ({event.actor_role})
        </span>
        {event.denial_code ? (
          <span className="inline-flex items-center rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-800">
            denied: {event.denial_code}
          </span>
        ) : null}
      </div>
      {event.reason_redacted ? (
        <p className="mt-1 text-gray-600">reason (redacted): {event.reason_redacted}</p>
      ) : null}
    </li>
  );
}

function NotificationRow({ event }: { event: OperatorNotificationEvent }) {
  return (
    <li className="py-2 text-xs text-gray-700" data-testid="ot-notification-item">
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
            event.delivery_state === 'suppressed'
              ? 'bg-gray-100 text-gray-600'
              : 'bg-blue-100 text-blue-800'
          }`}
        >
          {event.delivery_state}
        </span>
        <span className="font-mono text-gray-900">{event.channel}</span>
        <span className="text-gray-500">severity: {event.severity}</span>
        <span className="text-gray-400">
          redaction_applied={String(event.redaction_applied)}
        </span>
      </div>
      <p className="mt-1 text-gray-600">summary (redacted): {event.summary_redacted}</p>
    </li>
  );
}

function TransitionButton({
  testId,
  label,
  disabled,
  onClick,
}: {
  testId: string;
  label: string;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className="rounded bg-gray-200 px-3 py-2 text-sm font-medium text-gray-800 disabled:opacity-50"
      data-testid={testId}
    >
      {label}
    </button>
  );
}
