/**
 * PlatformIncidentCloseoutsPage -- P24 Incident + Runbook Closeout console
 * (P24-C, frontend-only).
 *
 * A CLOSEOUT IS A VIEW, NOT AN EXECUTOR. A RUNBOOK STEP IS A POINTER, NOT AN
 * EXECUTION. A FOLLOW-UP TASK IS A RECORD, NOT A REPAIR. This page is the read
 * / triage / record surface on top of the P24-B backend skeleton. It lists the
 * incident closeout queue, reads a single closeout with its append-only audit
 * history and its ordered runbook steps, runs the PRESENTATION-ONLY closeout
 * lifecycle and step state machine (self-assign / closeout transition / step
 * transition), and shows the linked P23 follow-up / step task ids. It never
 * executes anything.
 *
 * Hard UI rules (P24-A, mirrored from the backend contract):
 *   - No execute / run / apply / dispatch / trigger / approve / send / deliver
 *     control, and no "clear flag" control. The only controls are self-assign,
 *     the closeout judgment transition, and the per-step runbook transition.
 *     P24 NEVER sets or clears the P17 incident_active flag; the flag is mirrored
 *     (flag_observed / flag_ever_set) and read-only here.
 *   - Recording a transition records operator judgment only; it never runs a P22
 *     action, never decides a P19/P20/P21 approval, never mutates a registry
 *     field, and never delivers a notification. Approvals are not execution: an
 *     action_pointer step is done only when the linked execution is observed
 *     terminal, not on approval alone -- the backend enforces this and a 409
 *     denial (STEP_DONE_DENIED_GATE_OPEN / STEP_DONE_DENIED_NO_EVIDENCE) is
 *     surfaced cleanly inline. A close to `closed` is rejected (409) while the
 *     honest close gate is open (flag still set, owed tasks non-terminal, source
 *     still unknown, or linked execution at backup_check_warning).
 *   - source_unknown is NEVER healthy and a degraded source / backup_check_warning
 *     linked execution is NEVER success: the display badge is never green for
 *     either, regardless of the label the backend supplied (defended client-side
 *     in resolveCloseoutDisplayTone / resolveStepDisplayTone). A blocked runbook
 *     step is never healthy.
 *   - `closed` is never produced by frontend optimism. The page only ever reads
 *     state / display_status back from the backend response after a transition;
 *     it never flips a local closeout to closed on its own.
 *   - Redaction is total: only *_redacted fields and echo-safe ids are rendered;
 *     redaction_applied === true is displayed. No raw reason, secret, DSN, host,
 *     port, token, cookie, auth header, or tenant-business payload is shown.
 *
 * Storage is in-memory; the closeout queue is a view, not the system of record;
 * withdrawn / expired closeouts retain their full audit history and steps.
 *
 * Route is platform-only (/platform/incident-closeouts) behind the identity-only
 * PlatformRoute guard. Reuses the existing platformService Axios client. No
 * intake endpoint is exposed here (intake is system-only).
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { platformService } from '@/services/platformApi';
import { Skeleton } from '@/components/ui/Skeleton';
import { useAuthStore } from '@/stores/authStore';
import { isIdentityPlatformOperator } from '@/router/guards';
import {
  ALLOWED_CLOSEOUT_TRANSITIONS,
  ALLOWED_STEP_TRANSITIONS,
  CLASSIFICATIONS,
  CLOSEOUT_STATES,
  FLAG_OBSERVED_VALUES,
  SEVERITIES,
  isTerminalCloseoutState,
  isTerminalStepState,
  resolveCloseoutDisplayTone,
  resolveStepDisplayTone,
  type Classification,
  type CloseoutState,
  type CloseoutTransitionRequest,
  type DisplayStatus,
  type FlagObserved,
  type IncidentCloseout,
  type IncidentCloseoutAuditEvent,
  type IncidentCloseoutDetail,
  type IncidentCloseoutList,
  type IncidentCloseoutListFilters,
  type IncidentDisplayTone,
  type OwnerRole,
  type RunbookStep,
  type Severity,
  type SourceStatus,
  type StepKind,
  type StepState,
  type StepTransitionRequest,
} from '@/types/platformIncidentCloseout';

const DEFAULT_FILTERS: IncidentCloseoutListFilters = {
  state: undefined,
  classification: undefined,
  severity: undefined,
  flag_observed: undefined,
};

// -- Tone maps (Tailwind classes) --------------------------------------------

const DISPLAY_TONE_CLASS: Record<IncidentDisplayTone, string> = {
  green: 'bg-green-100 text-green-800',
  yellow: 'bg-yellow-100 text-yellow-800',
  gray: 'bg-gray-100 text-gray-600',
  red: 'bg-red-100 text-red-800',
  blue: 'bg-blue-100 text-blue-800',
};

const SEVERITY_TONE: Record<Severity, string> = {
  high: 'bg-red-100 text-red-800',
  medium: 'bg-yellow-100 text-yellow-800',
  low: 'bg-gray-100 text-gray-600',
};

const CLOSEOUT_STATE_TONE: Record<CloseoutState, string> = {
  detected: 'bg-blue-100 text-blue-800',
  triaged: 'bg-blue-100 text-blue-800',
  flagged_active: 'bg-yellow-100 text-yellow-800',
  in_remediation: 'bg-yellow-100 text-yellow-800',
  awaiting_closeout: 'bg-blue-100 text-blue-800',
  closed: 'bg-gray-100 text-gray-600',
  withdrawn: 'bg-gray-100 text-gray-600',
  expired: 'bg-gray-100 text-gray-600',
};

const STEP_STATE_TONE: Record<StepState, string> = {
  owed: 'bg-yellow-100 text-yellow-800',
  in_progress: 'bg-yellow-100 text-yellow-800',
  done: 'bg-gray-100 text-gray-600',
  not_applicable: 'bg-gray-100 text-gray-600',
  blocked: 'bg-red-100 text-red-800',
};

const STEP_KIND_LABEL: Record<StepKind, string> = {
  observation: 'observation',
  action_pointer: 'action pointer (-> P18/P22)',
  approval_pointer: 'approval pointer (-> P21)',
};

const OWNER_ROLE_LABEL: Record<OwnerRole, string> = {
  super_admin: 'super admin',
  engineering_operator: 'engineering operator',
  support_operator: 'support operator',
};

// -- Small helpers -----------------------------------------------------------

function unwrap<T>(res: { data?: unknown }): T {
  const data = res.data as { data?: T } | T | undefined;
  if (data && typeof data === 'object' && 'data' in (data as Record<string, unknown>)) {
    return (data as { data: T }).data;
  }
  return data as T;
}

/** Extract the P24 FastAPI HTTPException body ({detail: {code, message}}). */
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

interface StepDraft {
  target: StepState | '';
  evidence: string;
  reason: string;
  confirm: boolean;
}

const EMPTY_STEP_DRAFT: StepDraft = { target: '', evidence: '', reason: '', confirm: false };

export function PlatformIncidentCloseoutsPage() {
  const user = useAuthStore((s) => s.user);
  const canOperate = isIdentityPlatformOperator(user);

  // -- queue + filters --
  const [closeouts, setCloseouts] = useState<IncidentCloseout[] | null>(null);
  const [listMeta, setListMeta] = useState<{
    total: number;
    active_count: number;
    limit: number;
    offset: number;
  } | null>(null);
  const [listLoading, setListLoading] = useState(false);
  const [listError, setListError] = useState<string | null>(null);

  const [draftFilters, setDraftFilters] =
    useState<IncidentCloseoutListFilters>(DEFAULT_FILTERS);
  const [appliedFilters, setAppliedFilters] =
    useState<IncidentCloseoutListFilters>(DEFAULT_FILTERS);

  // -- detail + transitions --
  const [detail, setDetail] = useState<IncidentCloseoutDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // closeout transition form
  const [closeoutTarget, setCloseoutTarget] = useState<CloseoutState | ''>('');
  const [closeoutReason, setCloseoutReason] = useState('');
  const [closeoutConfirm, setCloseoutConfirm] = useState(false);

  // per-step transition drafts
  const [stepDrafts, setStepDrafts] = useState<Record<string, StepDraft>>({});

  const [transitionBusy, setTransitionBusy] = useState<
    null | 'closeout' | 'self-assign' | string
  >(null);
  const [denial, setDenial] = useState<{
    code: string | null;
    message: string;
    scope: string;
  } | null>(null);
  const [transitionMessage, setTransitionMessage] = useState<{
    scope: string;
    text: string;
  } | null>(null);

  const loadList = useCallback(() => {
    setListLoading(true);
    setListError(null);
    platformService
      .listIncidentCloseouts(50, 0, appliedFilters)
      .then((res) => {
        const body = unwrap<IncidentCloseoutList>(res);
        const items = body?.closeouts ?? [];
        setCloseouts(items);
        setListMeta({
          total: body?.total ?? items.length,
          active_count: body?.active_count ?? items.length,
          limit: body?.limit ?? 50,
          offset: body?.offset ?? 0,
        });
      })
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : 'Failed to load incident closeouts';
        setListError(msg);
        setCloseouts(null);
        setListMeta(null);
      })
      .finally(() => setListLoading(false));
  }, [appliedFilters]);

  useEffect(() => {
    if (canOperate) loadList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canOperate, loadList]);

  const loadDetail = useCallback((closeoutId: string) => {
    setDetailLoading(true);
    platformService
      .getIncidentCloseout(closeoutId)
      .then((res) => setDetail(unwrap<IncidentCloseoutDetail>(res)))
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : 'Failed to load closeout detail';
        setListError(msg);
        setDetail(null);
      })
      .finally(() => setDetailLoading(false));
  }, []);

  const selectCloseout = (closeoutId: string | null) => {
    setDenial(null);
    setTransitionMessage(null);
    setCloseoutTarget('');
    setCloseoutReason('');
    setCloseoutConfirm(false);
    setStepDrafts({});
    if (!closeoutId) {
      setDetail(null);
      return;
    }
    loadDetail(closeoutId);
  };

  const applyFilters = () => {
    setAppliedFilters({ ...draftFilters });
    // loadList fires via the appliedFilters effect dependency.
  };

  const resetFilters = () => {
    setDraftFilters(DEFAULT_FILTERS);
    setAppliedFilters(DEFAULT_FILTERS);
  };

  // -- transition plumbing ---------------------------------------------------

  const allowedCloseoutTargets: readonly CloseoutState[] = detail
    ? ALLOWED_CLOSEOUT_TRANSITIONS[detail.state]
    : [];

  const closeGateOpen = useMemo(() => {
    if (!detail) return false;
    // Mirror of the backend honest close gate (P24-A 3.3). The backend is the
    // authority; these flags are surfaced to set operator expectation and to
    // pre-disable a close that would be denied. They flip no flag and execute
    // nothing.
    return (
      detail.flag_ever_set === true ||
      detail.followup_owed === true ||
      detail.source_status === 'unknown' ||
      detail.linked_execution_warning === true
    );
  }, [detail]);

  const canTargetClosed =
    !!detail && allowedCloseoutTargets.includes('closed');
  const closeoutSubmitDisabled =
    closeoutTarget === '' ||
    transitionBusy !== null ||
    !canOperate ||
    (closeoutTarget === 'closed' && (!closeoutConfirm || closeGateOpen));

  const recordCloseoutTransition = () => {
    if (!detail || closeoutTarget === '' || closeoutSubmitDisabled) return;
    setTransitionBusy('closeout');
    setDenial(null);
    setTransitionMessage(null);
    const payload: CloseoutTransitionRequest = {
      target_state: closeoutTarget as CloseoutState,
    };
    const reason = closeoutReason.trim();
    if (reason) payload.reason = reason;
    platformService
      .transitionCloseout(detail.closeout_id, payload)
      .then((res) => {
        const result = unwrap<{ closeout: IncidentCloseout; accepted: boolean }>(res);
        setTransitionMessage({
          scope: 'closeout',
          text: `Recorded closeout judgment (${result.accepted ? 'accepted' : 'denied'}).`,
        });
        setCloseoutTarget('');
        setCloseoutReason('');
        setCloseoutConfirm(false);
        // Re-read the authoritative record (closed / display_status come from
        // the backend, never from local optimism).
        loadDetail(detail.closeout_id);
        loadList();
      })
      .catch((err: unknown) => {
        const d = extractDenial(err);
        setDenial({ ...d, scope: 'closeout' });
      })
      .finally(() => setTransitionBusy(null));
  };

  const runSelfAssign = () => {
    if (!detail || transitionBusy !== null || !canOperate) return;
    setTransitionBusy('self-assign');
    setDenial(null);
    setTransitionMessage(null);
    platformService
      .selfAssignCloseout(detail.closeout_id)
      .then((res) => {
        const result = unwrap<{ accepted: boolean }>(res);
        setTransitionMessage({
          scope: 'self-assign',
          text: `Self-assigned (presentation only; ${result.accepted ? 'recorded' : 'no change'}).`,
        });
        loadDetail(detail.closeout_id);
        loadList();
      })
      .catch((err: unknown) => {
        const d = extractDenial(err);
        setDenial({ ...d, scope: 'self-assign' });
      })
      .finally(() => setTransitionBusy(null));
  };

  const stepDraftFor = (stepId: string): StepDraft =>
    stepDrafts[stepId] ?? EMPTY_STEP_DRAFT;

  const patchStepDraft = (stepId: string, patch: Partial<StepDraft>) => {
    setStepDrafts((prev) => ({
      ...prev,
      [stepId]: { ...stepDraftFor(stepId), ...patch },
    }));
  };

  const recordStepTransition = (step: RunbookStep) => {
    if (!detail || transitionBusy !== null || !canOperate) return;
    const draft = stepDraftFor(step.step_id);
    if (draft.target === '') return;
    // The backend requires an evidence note for an observation `done`; pre-disable
    // would-be-denied submits so the operator sees the hint, but the backend
    // remains the authority.
    const needsEvidence =
      draft.target === 'done' && step.step_kind === 'observation';
    if (needsEvidence && draft.evidence.trim() === '') return;
    setTransitionBusy(step.step_id);
    setDenial(null);
    setTransitionMessage(null);
    const payload: StepTransitionRequest = {
      target_state: draft.target as StepState,
    };
    const evidence = draft.evidence.trim();
    if (evidence) payload.evidence = evidence;
    const reason = draft.reason.trim();
    if (reason) payload.reason = reason;
    platformService
      .transitionRunbookStep(detail.closeout_id, step.step_id, payload)
      .then((res) => {
        const result = unwrap<{ step: RunbookStep; accepted: boolean }>(res);
        setTransitionMessage({
          scope: step.step_id,
          text: `Recorded step judgment (${result.accepted ? 'accepted' : 'denied'}).`,
        });
        setStepDrafts((prev) => {
          const next = { ...prev };
          delete next[step.step_id];
          return next;
        });
        loadDetail(detail.closeout_id);
        loadList();
      })
      .catch((err: unknown) => {
        const d = extractDenial(err);
        setDenial({ ...d, scope: step.step_id });
      })
      .finally(() => setTransitionBusy(null));
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900" data-testid="ic-title">
          Incident Closeouts
        </h1>
        <p className="mt-1 text-sm text-gray-500" data-testid="ic-subtitle">
          A closeout is a view, not an executor. A runbook step is a pointer, not an execution. A
          follow-up task is a record, not a repair. Closeouts are listed, read, and triaged here;
          recording a transition records operator judgment only and never runs a controlled action,
          never approves an approval, never sets or clears the incident_active flag, and never
          delivers a notification. No execution, approval decision, flag mutation, or notification
          delivery happens on this page.
        </p>
      </div>

      {/* Persistent invariants */}
      <section
        className="rounded-lg border border-gray-200 bg-gray-50 p-4"
        data-testid="ic-invariants"
      >
        <h2 className="text-sm font-semibold text-gray-700">Console invariants</h2>
        <ul className="mt-2 grid gap-1 text-xs text-gray-600 sm:grid-cols-2">
          <li>a closeout is a view, not an executor</li>
          <li>a runbook step is a pointer, not an execution</li>
          <li>a follow-up task is a record, not a repair</li>
          <li>the flag is mirrored (read-only), never owned</li>
          <li>redaction_applied = true (every free-text field)</li>
          <li>source_unknown is never healthy</li>
          <li>backup_check_warning / degraded is never success</li>
          <li>a blocked runbook step is never healthy</li>
          <li>closed comes from the backend, never frontend optimism</li>
          <li>no execute / approve / send / clear-flag control</li>
        </ul>
      </section>

      {listError && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4">
          <p className="text-sm text-red-700" data-testid="ic-error">
            {listError}
          </p>
        </div>
      )}

      {!canOperate ? (
        <div
          className="rounded-lg border border-gray-200 bg-white p-4"
          data-testid="ic-no-access"
        >
          <p className="text-sm text-gray-700">
            Incident closeout controls are hidden for tenant-contextual identities. The platform
            incident closeout surface is identity-only.
          </p>
        </div>
      ) : (
        <>
          {/* Filters */}
          <section
            className="rounded-lg border border-gray-200 bg-white p-4"
            data-testid="ic-filters"
          >
            <h2 className="text-lg font-semibold text-gray-900 mb-2">Filters</h2>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <label className="block text-sm text-gray-700">
                State
                <select
                  className="mt-1 block w-full rounded border border-gray-300 p-2"
                  value={draftFilters.state ?? ''}
                  onChange={(e) =>
                    setDraftFilters({
                      ...draftFilters,
                      state: (e.target.value || undefined) as CloseoutState | undefined,
                    })
                  }
                  data-testid="ic-filter-state"
                >
                  <option value="">(any)</option>
                  {CLOSEOUT_STATES.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-sm text-gray-700">
                Severity
                <select
                  className="mt-1 block w-full rounded border border-gray-300 p-2"
                  value={draftFilters.severity ?? ''}
                  onChange={(e) =>
                    setDraftFilters({
                      ...draftFilters,
                      severity: (e.target.value || undefined) as Severity | undefined,
                    })
                  }
                  data-testid="ic-filter-severity"
                >
                  <option value="">(any)</option>
                  {SEVERITIES.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-sm text-gray-700">
                Classification
                <select
                  className="mt-1 block w-full rounded border border-gray-300 p-2"
                  value={draftFilters.classification ?? ''}
                  onChange={(e) =>
                    setDraftFilters({
                      ...draftFilters,
                      classification: (e.target.value || undefined) as
                        | Classification
                        | undefined,
                    })
                  }
                  data-testid="ic-filter-classification"
                >
                  <option value="">(any)</option>
                  {CLASSIFICATIONS.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-sm text-gray-700">
                Flag observed
                <select
                  className="mt-1 block w-full rounded border border-gray-300 p-2"
                  value={draftFilters.flag_observed ?? ''}
                  onChange={(e) =>
                    setDraftFilters({
                      ...draftFilters,
                      flag_observed: (e.target.value || undefined) as FlagObserved | undefined,
                    })
                  }
                  data-testid="ic-filter-flag"
                >
                  <option value="">(any)</option>
                  {FLAG_OBSERVED_VALUES.map((f) => (
                    <option key={f} value={f}>
                      {f}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="mt-3 flex gap-2">
              <button
                type="button"
                onClick={applyFilters}
                className="rounded bg-gray-200 px-3 py-2 text-sm font-medium text-gray-800"
                data-testid="ic-filter-apply"
              >
                Apply filters
              </button>
              <button
                type="button"
                onClick={resetFilters}
                className="rounded bg-gray-100 px-3 py-2 text-sm font-medium text-gray-700"
                data-testid="ic-filter-reset"
              >
                Reset filters
              </button>
            </div>
          </section>

          {/* Queue */}
          <section
            className="rounded-lg border border-gray-200 bg-white p-4"
            data-testid="ic-queue"
          >
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-gray-900">Incident closeout queue</h2>
              <button
                type="button"
                onClick={loadList}
                className="rounded bg-gray-200 px-3 py-2 text-sm font-medium text-gray-800"
                data-testid="ic-refresh-btn"
              >
                Refresh
              </button>
            </div>
            {listLoading && !closeouts ? (
              <div className="mt-3">
                <Skeleton className="h-16 w-full rounded-lg" />
              </div>
            ) : closeouts ? (
              <div className="mt-3">
                <p className="text-xs text-gray-500" data-testid="ic-queue-summary">
                  {listMeta
                    ? `${listMeta.total} closeouts (${listMeta.active_count} active)`
                    : ''}
                  ; redaction_applied=true
                </p>
                {closeouts.length === 0 ? (
                  <p className="mt-2 text-xs text-gray-400" data-testid="ic-queue-empty">
                    No incident closeouts match the current filters.
                  </p>
                ) : (
                  <ul className="mt-2 divide-y divide-gray-100">
                    {closeouts.map((item) => (
                      <li key={item.closeout_id} className="py-2" data-testid="ic-queue-item">
                        <div className="flex flex-wrap items-center gap-2 text-sm">
                          <CloseoutDisplayBadge
                            displayStatus={item.display_status}
                            sourceStatus={item.source_status}
                            linkedExecutionWarning={item.linked_execution_warning}
                          />
                          <span
                            className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${SEVERITY_TONE[item.severity]}`}
                            data-testid="ic-severity-badge"
                          >
                            severity: {item.severity}
                          </span>
                          <span
                            className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${CLOSEOUT_STATE_TONE[item.state]}`}
                            data-testid="ic-state-badge"
                          >
                            {item.state}
                          </span>
                          {item.classification ? (
                            <span className="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-700">
                              {item.classification}
                            </span>
                          ) : null}
                          <span
                            className="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-700"
                            data-testid="ic-flag-badge"
                          >
                            flag: {item.flag_observed}
                          </span>
                          <span className="text-xs text-gray-400">
                            redaction_applied={String(item.redaction_applied)}
                          </span>
                          <button
                            type="button"
                            onClick={() => selectCloseout(item.closeout_id)}
                            className={`rounded px-2 py-1 text-xs font-medium ${
                              detail?.closeout_id === item.closeout_id
                                ? 'bg-primary-600 text-white'
                                : 'bg-gray-200 text-gray-800'
                            }`}
                            data-testid="ic-view-btn"
                          >
                            View
                          </button>
                        </div>
                        <p
                          className="mt-1 truncate text-xs text-gray-600"
                          data-testid="ic-queue-summary-text"
                        >
                          {item.summary_redacted}
                        </p>
                        {item.owner_actor_id ? (
                          <p className="text-xs text-gray-400">
                            owner: {item.owner_actor_id}
                            {item.owner_role ? ` (${OWNER_ROLE_LABEL[item.owner_role]})` : ''}
                          </p>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ) : (
              <p className="mt-3 text-xs text-gray-400">Refresh to load the closeout queue.</p>
            )}
          </section>

          {/* Detail + runbook + transition panel */}
          {detail ? (
            <section
              className="space-y-4 rounded-lg border border-gray-200 bg-white p-4"
              data-testid="ic-detail"
            >
              <div>
                <h2 className="text-lg font-semibold text-gray-900">Closeout detail</h2>
                <p className="text-xs text-gray-500">
                  Read-only. Only redacted fields and echo-safe ids are shown; no raw reason, secret,
                  DSN, host, port, token, or tenant-business payload is displayed. The flag is
                  mirrored (P24 never writes it).
                </p>
              </div>
              {detailLoading ? (
                <Skeleton className="h-20 w-full rounded-lg" />
              ) : (
                <DetailGrid record={detail} />
              )}

              {/* Audit history */}
              <div data-testid="ic-audit-list">
                <h3 className="mb-1 text-sm font-semibold text-gray-800">
                  Audit history ({detail.audit_events.length}; append-only)
                </h3>
                {detail.audit_events.length === 0 ? (
                  <p className="text-xs text-gray-400">No audit events recorded.</p>
                ) : (
                  <ul className="divide-y divide-gray-100">
                    {detail.audit_events.map((ev) => (
                      <CloseoutAuditRow key={ev.event_id} event={ev} />
                    ))}
                  </ul>
                )}
              </div>

              {/* Runbook checklist */}
              <div data-testid="ic-runbook">
                <h3 className="mb-1 text-sm font-semibold text-gray-800">
                  Runbook ({detail.steps.length}; pointers, not executions)
                </h3>
                <p className="mb-1 text-xs text-gray-500">
                  Each step is a pointer and a record. An action_pointer step is done only when its
                  linked execution is observed terminal; an approval_pointer step is done only when
                  its linked approval is observed resolved; an observation step is done only with a
                  redacted evidence note. Marking a step done executes nothing.
                </p>
                {detail.steps.length === 0 ? (
                  <p className="text-xs text-gray-400" data-testid="ic-runbook-empty">
                    No runbook steps recorded for this closeout.
                  </p>
                ) : (
                  <ul className="divide-y divide-gray-100">
                    {detail.steps.map((step) => (
                      <RunbookStepRow
                        key={step.step_id}
                        step={step}
                        draft={stepDraftFor(step.step_id)}
                        busy={transitionBusy !== null}
                        canOperate={canOperate}
                        onPatch={(patch) => patchStepDraft(step.step_id, patch)}
                        onSubmit={() => recordStepTransition(step)}
                      />
                    ))}
                  </ul>
                )}
              </div>

              {/* Closeout transition controls (presentation only) */}
              {isTerminalCloseoutState(detail.state) ? (
                <p className="text-xs text-gray-500" data-testid="ic-terminal-note">
                  This closeout is in a terminal state ({detail.state}); no closeout transition is
                  available. The audit history and runbook are retained. Nothing is executed.
                </p>
              ) : (
                <div
                  className="rounded-lg border border-gray-200 p-3"
                  data-testid="ic-transitions"
                >
                  <h3 className="mb-2 text-sm font-semibold text-gray-800">
                    Closeout judgment (state management only; not executed)
                  </h3>

                  {closeGateOpen && canTargetClosed ? (
                    <div
                      className="mb-3 rounded bg-yellow-50 p-3 text-xs text-yellow-800"
                      data-testid="ic-close-gate-warning"
                    >
                      The honest close gate is still open (flag ever set, follow-up owed, source
                      unknown, or linked execution at backup_check_warning). Closing will be denied
                      until the gate closes; recording `closed` is disabled. Nothing is executed and
                      no flag is cleared here.
                    </div>
                  ) : null}

                  <div className="grid gap-3">
                    <label className="block text-sm text-gray-700">
                      Target state
                      <select
                        className="mt-1 block w-full rounded border border-gray-300 p-2"
                        value={closeoutTarget}
                        onChange={(e) =>
                          setCloseoutTarget(e.target.value as CloseoutState | '')
                        }
                        data-testid="ic-closeout-target"
                      >
                        <option value="">(select target)</option>
                        {allowedCloseoutTargets.map((s) => (
                          <option key={s} value={s}>
                            {s}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="block text-sm text-gray-700">
                      Judgment reason (optional; redacted)
                      <textarea
                        className="mt-1 block w-full rounded border border-gray-300 p-2"
                        rows={2}
                        value={closeoutReason}
                        onChange={(e) => setCloseoutReason(e.target.value)}
                        data-testid="ic-closeout-reason"
                      />
                    </label>
                    {closeoutTarget === 'closed' ? (
                      <label className="inline-flex items-center gap-2 text-sm text-gray-700">
                        <input
                          type="checkbox"
                          checked={closeoutConfirm}
                          onChange={(e) => setCloseoutConfirm(e.target.checked)}
                          data-testid="ic-close-confirm"
                        />
                        Confirm close judgment (records judgment; the backend enforces the close gate;
                        not executed)
                      </label>
                    ) : null}
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        disabled={closeoutSubmitDisabled}
                        onClick={recordCloseoutTransition}
                        className="rounded bg-primary-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                        data-testid="ic-closeout-submit"
                      >
                        Record transition
                      </button>
                      <button
                        type="button"
                        disabled={transitionBusy !== null}
                        onClick={runSelfAssign}
                        className="rounded bg-gray-200 px-3 py-2 text-sm font-medium text-gray-800 disabled:opacity-50"
                        data-testid="ic-self-assign-btn"
                      >
                        Self-assign
                      </button>
                    </div>
                    {closeoutTarget === 'closed' && closeGateOpen ? (
                      <p className="text-xs text-gray-400" data-testid="ic-close-hint">
                        The close gate is open; recording `closed` is disabled until the gate closes.
                      </p>
                    ) : null}
                  </div>

                  {denial ? (
                    <div
                      className="mt-3 rounded bg-red-50 p-3 text-xs text-red-800"
                      data-testid="ic-denial"
                    >
                      <span className="font-mono">{denial.code ?? 'DENIED'}</span>: {denial.message}{' '}
                      The state was not changed; the denial is recorded in the audit history.
                    </div>
                  ) : null}

                  {transitionMessage ? (
                    <div
                      className="mt-3 rounded bg-blue-50 p-3 text-xs text-blue-800"
                      data-testid="ic-transition-ok"
                    >
                      {transitionMessage.text}
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

function CloseoutDisplayBadge({
  displayStatus,
  sourceStatus,
  linkedExecutionWarning,
}: {
  displayStatus: DisplayStatus;
  sourceStatus: SourceStatus | null;
  linkedExecutionWarning: boolean;
}) {
  const tone = resolveCloseoutDisplayTone(
    displayStatus,
    sourceStatus,
    linkedExecutionWarning,
  );
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${DISPLAY_TONE_CLASS[tone]}`}
      data-testid="ic-display-badge"
      data-tone={tone}
    >
      display: {displayStatus}
    </span>
  );
}

function StepDisplayBadge({ step }: { step: RunbookStep }) {
  const tone = resolveStepDisplayTone(
    step.display_status,
    step.source_status,
    step.linked_execution_warning,
    step.step_state,
  );
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${DISPLAY_TONE_CLASS[tone]}`}
      data-testid="ic-step-display-badge"
      data-tone={tone}
    >
      display: {step.display_status}
    </span>
  );
}

function DetailGrid({ record }: { record: IncidentCloseoutDetail }) {
  return (
    <dl
      className="grid gap-x-4 gap-y-1 text-xs text-gray-700 sm:grid-cols-2"
      data-testid="ic-detail-grid"
    >
      <DetailRow label="closeout_id" value={record.closeout_id} />
      <DetailRow label="state" value={record.state} />
      <DetailRow label="display_status" value={record.display_status} />
      <DetailRow label="severity" value={record.severity} />
      <DetailRow label="classification" value={record.classification} />
      <DetailRow label="source_status" value={record.source_status} />
      <DetailRow label="tenant_id" value={record.tenant_id} />
      <DetailRow label="actor_scope" value={record.actor_scope} />
      <DetailRow label="owner_role" value={record.owner_role ? OWNER_ROLE_LABEL[record.owner_role] : null} />
      <DetailRow label="owner_actor_id" value={record.owner_actor_id} />
      <DetailRow label="flag_observed" value={record.flag_observed} />
      <DetailRow label="flag_ever_set" value={String(record.flag_ever_set)} />
      <DetailRow label="followup_owed" value={String(record.followup_owed)} />
      <DetailRow label="linked_execution_warning" value={String(record.linked_execution_warning)} />
      <DetailRow label="linked_followup_task_id" value={record.linked_followup_task_id} />
      <DetailRow label="linked_incident_id" value={record.linked_incident_id} />
      <DetailRow label="linked_triage_snapshot_ref" value={record.linked_triage_snapshot_ref} />
      <DetailRow label="linked_handoff_ref" value={record.linked_handoff_ref} />
      <DetailRow label="summary (redacted)" value={record.summary_redacted} />
      <DetailRow label="reason (redacted)" value={record.reason_redacted} />
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

function CloseoutAuditRow({ event }: { event: IncidentCloseoutAuditEvent }) {
  return (
    <li className="py-2 text-xs text-gray-700" data-testid="ic-audit-item">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-gray-900">{event.transition}</span>
        <span className="text-gray-500">
          {event.previous_state} -&gt; {event.next_state}
        </span>
        <span className="text-gray-400">
          {event.actor_id ?? 'system'} ({event.actor_role})
        </span>
        <span className="text-gray-400">flag: {event.flag_observed}</span>
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

function RunbookStepRow({
  step,
  draft,
  busy,
  canOperate,
  onPatch,
  onSubmit,
}: {
  step: RunbookStep;
  draft: StepDraft;
  busy: boolean;
  canOperate: boolean;
  onPatch: (patch: Partial<StepDraft>) => void;
  onSubmit: () => void;
}) {
  const allowed = ALLOWED_STEP_TRANSITIONS[step.step_state];
  const terminal = isTerminalStepState(step.step_state);
  const needsEvidence =
    draft.target === 'done' && step.step_kind === 'observation';
  const submitDisabled =
    !canOperate ||
    busy ||
    draft.target === '' ||
    (needsEvidence && draft.evidence.trim() === '');
  return (
    <li className="py-2 text-xs text-gray-700" data-testid="ic-step-item">
      <div className="flex flex-wrap items-center gap-2">
        <StepDisplayBadge step={step} />
        <span
          className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${STEP_STATE_TONE[step.step_state]}`}
        >
          {step.step_state}
        </span>
        <span className="font-mono text-gray-900">{STEP_KIND_LABEL[step.step_kind]}</span>
        <span className="text-gray-400">#{step.sequence_no}</span>
        <span className="text-gray-400">
          redaction_applied={String(step.redaction_applied)}
        </span>
      </div>
      <p className="mt-1 text-gray-600" data-testid="ic-step-summary">
        summary (redacted): {step.summary_redacted}
      </p>
      <ul className="mt-1 grid gap-x-4 gap-y-0.5 text-gray-500 sm:grid-cols-2">
        <li>linked_action_id: {step.linked_action_id ?? '(none)'}</li>
        <li>linked_approval_id: {step.linked_approval_id ?? '(none)'}</li>
        <li>linked_execution_id: {step.linked_execution_id ?? '(none)'}</li>
        <li>linked_source_ref: {step.linked_source_ref ?? '(none)'}</li>
        <li>evidence_ref: {step.evidence_ref ?? '(none)'}</li>
        <li>linked_task_id: {step.linked_task_id ?? '(none)'}</li>
        <li>linked_execution_terminal: {String(step.linked_execution_terminal)}</li>
        <li>linked_approval_resolved: {String(step.linked_approval_resolved)}</li>
        <li>linked_execution_warning: {String(step.linked_execution_warning)}</li>
        <li>source_status: {step.source_status ?? '(none)'}</li>
      </ul>
      {step.reason_redacted ? (
        <p className="mt-1 text-gray-600">reason (redacted): {step.reason_redacted}</p>
      ) : null}

      {terminal ? (
        <p className="mt-1 text-gray-400" data-testid="ic-step-terminal">
          This step is terminal ({step.step_state}); no step transition is available.
        </p>
      ) : (
        <div className="mt-2 rounded border border-gray-200 p-2" data-testid="ic-step-transition">
          <div className="grid gap-2 sm:grid-cols-2">
            <label className="block text-gray-700">
              Target step state
              <select
                className="mt-1 block w-full rounded border border-gray-300 p-2"
                value={draft.target}
                onChange={(e) =>
                  onPatch({ target: e.target.value as StepState | '' })
                }
                data-testid="ic-step-target"
              >
                <option value="">(select target)</option>
                {allowed.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-gray-700">
              Step reason (optional; redacted)
              <input
                className="mt-1 block w-full rounded border border-gray-300 p-2"
                value={draft.reason}
                onChange={(e) => onPatch({ reason: e.target.value })}
                data-testid="ic-step-reason"
              />
            </label>
          </div>
          {needsEvidence ? (
            <label className="mt-2 block text-gray-700">
              Evidence note (required for an observation done; redacted)
              <textarea
                className="mt-1 block w-full rounded border border-gray-300 p-2"
                rows={2}
                value={draft.evidence}
                onChange={(e) => onPatch({ evidence: e.target.value })}
                data-testid="ic-step-evidence"
              />
            </label>
          ) : null}
          <div className="mt-2 flex gap-2">
            <button
              type="button"
              disabled={submitDisabled}
              onClick={onSubmit}
              className="rounded bg-primary-600 px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
              data-testid="ic-step-submit"
            >
              Record step transition
            </button>
          </div>
          {needsEvidence && draft.evidence.trim() === '' ? (
            <p className="mt-1 text-gray-400" data-testid="ic-step-hint">
              An observation `done` requires a redacted evidence note before it can be recorded.
            </p>
          ) : null}
        </div>
      )}
    </li>
  );
}
