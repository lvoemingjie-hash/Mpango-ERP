/**
 * PlatformControlledExecutionConsolePage -- P22 controlled-execution v0
 * NON-EXECUTING operator console (P22-C).
 *
 * This console lets an identity-only platform operator:
 *   - view the closed v0 execution catalog (read-only)
 *   - inspect the explicitly excluded actions and the safety boundaries
 *   - run a NO-MUTATION dry-run (precondition validator)
 *   - record a NON-EXECUTING execution request, only after a passed dry-run
 *     AND an explicit typed acknowledgement
 *   - list / read recorded execution requests
 *
 * Hard invariant: this page NEVER executes anything. There is no execute
 * button, no worker, no queue drain, no harness, no shell / SQL / script, and
 * no tenant / payment / product mutation. Approval is not execution and
 * request recording is not execution. Every response is rendered with
 * executed === false, execution_allowed === false, execution_started === false,
 * and a result_state of only dry_run_passed | blocked.
 *
 * The raw idempotency_key the operator types is sent to the boundary only; it
 * is hashed there and NEVER stored / logged / echoed. Only its one-way digest
 * (idempotency_key_digest) and the canonical payload_digest are ever rendered.
 *
 * Route: /platform/controlled-execution (identity-only PlatformRoute guard).
 */
import { useEffect, useState } from 'react';
import { platformService } from '@/services/platformApi';
import { Skeleton } from '@/components/ui/Skeleton';
import type {
  ExecutionCatalogResponse,
  ExecutionDryRunResponse,
  ExecutionRequestQueue,
  ExecutionRequestResponse,
} from '@/types/platformControlledExecution';

// -- tone maps for badges ----------------------------------------------------

const VERDICT_TONE: Record<string, string> = {
  passed: 'bg-green-100 text-green-800',
  blocked: 'bg-red-100 text-red-800',
};

const RESULT_TONE: Record<string, string> = {
  recorded: 'bg-green-100 text-green-800',
  blocked: 'bg-red-100 text-red-800',
  denied: 'bg-red-100 text-red-800',
  conflict: 'bg-orange-100 text-orange-800',
  duplicate: 'bg-blue-100 text-blue-800',
};

const SOURCE_TONE: Record<string, string> = {
  known: 'bg-green-100 text-green-800',
  degraded: 'bg-yellow-100 text-yellow-800',
  unknown: 'bg-red-100 text-red-800',
};

// -- helpers -----------------------------------------------------------------

/**
 * Unwrap an axios response that may carry a `{ data: { data: T } }` envelope or
 * a raw `{ data: T }` body. Mirrors the platformApi consumer convention.
 */
function unwrap<T>(res: { data?: unknown }): T {
  const data = res.data as { data?: T } | T | undefined;
  if (data && typeof data === 'object' && 'data' in (data as Record<string, unknown>)) {
    return (data as { data: T }).data;
  }
  return data as T;
}

/** Parse the optional metadata textarea as JSON. Returns null when empty. */
function parseMetadata(
  text: string,
): { ok: true; value: Record<string, unknown> | null } | { ok: false; error: string } {
  const trimmed = text.trim();
  if (!trimmed) return { ok: true, value: null };
  try {
    const parsed = JSON.parse(trimmed);
    if (parsed === null) return { ok: true, value: null };
    if (typeof parsed !== 'object' || Array.isArray(parsed)) {
      return { ok: false, error: 'Metadata must be a JSON object (or empty).' };
    }
    return { ok: true, value: parsed as Record<string, unknown> };
  } catch {
    return { ok: false, error: 'Metadata is not valid JSON. Leave empty or use a JSON object.' };
  }
}

const NON_EXECUTING_BANNER =
  'Approval is not execution. A passed dry-run is a precondition, not an execution. ' +
  'Recording a request is not execution. This console never dispatches a worker, never ' +
  'drains a queue, never invokes the governed harness, and never changes tenant, payment, ' +
  'billing, or product state.';

export function PlatformControlledExecutionConsolePage() {
  // -- catalog (read-only) --
  const [catalog, setCatalog] = useState<ExecutionCatalogResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // -- shared execution-input form (drives both dry-run and record) --
  const [durableApprovalId, setDurableApprovalId] = useState('');
  const [actionType, setActionType] = useState('');
  const [tenantId, setTenantId] = useState('');
  const [requestedState, setRequestedState] = useState('');
  const [reason, setReason] = useState('');
  const [idempotencyKey, setIdempotencyKey] = useState('');
  const [executionMode, setExecutionMode] = useState<'sync' | 'queued'>('sync');
  const [correlationId, setCorrelationId] = useState('');
  const [metadataText, setMetadataText] = useState('');

  // -- dry-run --
  const [dryRunResult, setDryRunResult] = useState<ExecutionDryRunResponse | null>(null);
  const [dryRunBusy, setDryRunBusy] = useState(false);

  // -- record request --
  const [executionAck, setExecutionAck] = useState(false);
  const [recordResult, setRecordResult] = useState<ExecutionRequestResponse | null>(null);
  const [recordBusy, setRecordBusy] = useState(false);

  // -- queue / read --
  const [queue, setQueue] = useState<ExecutionRequestQueue | null>(null);
  const [readId, setReadId] = useState('');
  const [readResult, setReadResult] = useState<ExecutionRequestResponse | null>(null);
  const [readBusy, setReadBusy] = useState(false);

  // Load the catalog on mount.
  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    platformService
      .getExecutionCatalog()
      .then((res) => {
        const payload = unwrap<ExecutionCatalogResponse>(res);
        if (!alive) return;
        setCatalog(payload);
        if (payload?.items?.length) {
          setActionType((prev) => prev || payload.items[0].action_type);
        }
      })
      .catch((err: unknown) => {
        if (alive) setError(errMessage(err, 'Failed to load the execution catalog.'));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  // -- derived form state ---------------------------------------------------

  const metadataParse = parseMetadata(metadataText);
  const metadataValid = metadataParse.ok;

  const dryRunFormValid =
    durableApprovalId.trim().length > 0 &&
    actionType.length > 0 &&
    reason.trim().length > 0 &&
    idempotencyKey.trim().length > 0 &&
    (executionMode === 'sync' || executionMode === 'queued') &&
    metadataValid;

  const dryRunPassed =
    !!dryRunResult && dryRunResult.verdict === 'passed' && !!dryRunResult.dry_run_id;

  // Recording is allowed only after a passed dry-run AND the typed ack.
  const recordEnabled = dryRunPassed && executionAck && dryRunFormValid && !recordBusy;

  // -- mutations of bound inputs invalidate a prior passed dry-run ----------
  /** Clear a passed dry-run (and any recorded result) when a bound input changes. */
  function invalidateDryRun() {
    setDryRunResult(null);
    setRecordResult(null);
    setExecutionAck(false);
  }

  // -- build the shared payload --------------------------------------------

  function buildPayload() {
    return {
      durable_approval_id: durableApprovalId.trim(),
      action_type: actionType,
      tenant_id: tenantId.trim() ? tenantId.trim() : null,
      requested_state: requestedState.trim() ? requestedState.trim() : null,
      reason: reason.trim(),
      idempotency_key: idempotencyKey.trim(),
      execution_mode: executionMode,
      correlation_id: correlationId.trim() ? correlationId.trim() : null,
      metadata: metadataParse.ok ? metadataParse.value : null,
    };
  }

  // -- actions --------------------------------------------------------------

  function runDryRun() {
    if (!dryRunFormValid) return;
    setDryRunBusy(true);
    setError(null);
    setDryRunResult(null);
    setRecordResult(null);
    platformService
      .dryRunExecution(buildPayload())
      .then((res) => setDryRunResult(unwrap<ExecutionDryRunResponse>(res)))
      .catch((err: unknown) => setError(errMessage(err, 'Dry-run failed.')))
      .finally(() => setDryRunBusy(false));
  }

  function recordRequest() {
    if (!recordEnabled || !dryRunResult?.dry_run_id) return;
    setRecordBusy(true);
    setError(null);
    setRecordResult(null);
    platformService
      .recordExecutionRequest({
        ...buildPayload(),
        dry_run_ref: dryRunResult.dry_run_id,
        execution_ack: true,
      })
      .then((res) => {
        setRecordResult(unwrap<ExecutionRequestResponse>(res));
        // The queue now has one more recorded request; offer a refresh.
      })
      .catch((err: unknown) => setError(errMessage(err, 'Recording the request failed.')))
      .finally(() => setRecordBusy(false));
  }

  function refreshQueue() {
    platformService
      .listExecutionRequests(50, 0)
      .then((res) => setQueue(unwrap<ExecutionRequestQueue>(res)))
      .catch((err: unknown) => setError(errMessage(err, 'Loading the request queue failed.')));
  }

  function readRequest() {
    const id = readId.trim();
    if (!id) return;
    setReadBusy(true);
    setError(null);
    setReadResult(null);
    platformService
      .getExecutionRequest(id)
      .then((res) => setReadResult(unwrap<ExecutionRequestResponse>(res)))
      .catch((err: unknown) => {
        setReadResult(null);
        setError(errMessage(err, 'Execution request not found or could not be read.'));
      })
      .finally(() => setReadBusy(false));
  }

  // -- render ---------------------------------------------------------------

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900" data-testid="p22-title">
          Controlled Execution Console
        </h1>
        <p className="mt-1 text-sm text-gray-500" data-testid="p22-subtitle">
          Non-executing operator console: dry-run preconditions, then record a request. Requests are
          recorded only and are never executed.
        </p>
      </div>

      {/* Persistent non-execution banner */}
      <div
        className="rounded-lg border border-gray-300 bg-gray-50 p-3"
        data-testid="p22-non-executing-banner"
      >
        <p className="text-xs text-gray-700">{NON_EXECUTING_BANNER}</p>
      </div>

      {/* Error */}
      {error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4">
          <p className="text-sm text-red-700" data-testid="p22-error">
            {error}
          </p>
        </div>
      ) : null}

      {loading ? (
        <Skeleton className="h-40 w-full rounded-lg" />
      ) : catalog ? (
        <>
          {/* Catalog (read-only) */}
          <section data-testid="p22-catalog">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="text-lg font-semibold text-gray-900">Execution catalog (read-only)</h2>
              <p className="text-xs text-gray-500" data-testid="p22-catalog-summary">
                {catalog.total} allowlisted actions; contract {catalog.contract}; storage=
                {catalog.storage}; executed={String(catalog.executed)}
              </p>
            </div>
            <ul className="mt-3 grid gap-2 sm:grid-cols-2">
              {catalog.items.map((item) => (
                <li
                  key={item.action_type}
                  className="rounded-lg border border-gray-200 bg-white p-3"
                  data-testid="p22-catalog-item"
                >
                  <div className="font-mono text-sm text-gray-900" data-testid="p22-catalog-action">
                    {item.action_type}
                  </div>
                  <div className="text-xs text-gray-600">
                    class: <span data-testid="p22-catalog-class">{item.action_class}</span>
                    {' '}-- reversible:{' '}
                    <span data-testid="p22-catalog-reversible">{String(item.reversible)}</span>
                    {item.reversibility_via
                      ? ` via ${item.reversibility_via}`
                      : ''}
                  </div>
                  <div className="text-xs text-gray-500">
                    executor: {item.executor}; tenant business mutation:{' '}
                    <span data-testid="p22-catalog-mutation">{item.tenant_business_mutation}</span>
                  </div>
                </li>
              ))}
            </ul>
          </section>

          {/* Excluded actions (separated, read-only, never selectable) */}
          <section
            className="rounded-lg border border-gray-200 bg-white p-4"
            data-testid="p22-excluded"
          >
            <h2 className="text-lg font-semibold text-gray-900">
              Excluded actions (never executable in v0)
            </h2>
            <p className="mt-1 text-xs text-gray-500" data-testid="p22-excluded-summary">
              These actions have no v0 execution path. They appear here for safety visibility only
              and are not selectable in the dry-run form.
            </p>
            <ul className="mt-3 divide-y divide-gray-100">
              {catalog.exclusions.map((ex) => (
                <li key={ex.action_type} className="py-2" data-testid="p22-excluded-item">
                  <div className="font-mono text-sm text-gray-700">{ex.action_type}</div>
                  <div className="text-xs text-gray-500" data-testid="p22-excluded-reason">
                    {ex.reason}
                  </div>
                </li>
              ))}
            </ul>
          </section>

          {/* Dry-run form (no mutation) */}
          <section
            className="rounded-lg border border-gray-200 bg-white p-4"
            data-testid="p22-dry-run-form"
          >
            <h2 className="text-lg font-semibold text-gray-900">
              Dry-run validator (no mutation; never executes)
            </h2>
            <p className="mb-3 text-xs text-gray-500">
              Validate the execution preconditions. A passed dry-run is a precondition, not an
              execution.
            </p>
            <div className="grid gap-3">
              <label className="block text-sm text-gray-700">
                Durable approval id (required)
                <input
                  className="mt-1 block w-full rounded border border-gray-300 p-2"
                  value={durableApprovalId}
                  onChange={(e) => {
                    setDurableApprovalId(e.target.value);
                    invalidateDryRun();
                  }}
                  data-testid="p22-approval-input"
                />
              </label>
              <label className="block text-sm text-gray-700">
                Action type (required; allowlist only)
                <select
                  className="mt-1 block w-full rounded border border-gray-300 p-2"
                  value={actionType}
                  onChange={(e) => {
                    setActionType(e.target.value);
                    invalidateDryRun();
                  }}
                  data-testid="p22-action-select"
                >
                  {catalog.items.map((item) => (
                    <option key={item.action_type} value={item.action_type}>
                      {item.action_type}
                    </option>
                  ))}
                </select>
              </label>
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="block text-sm text-gray-700">
                  Tenant id (optional; scoped id only)
                  <input
                    className="mt-1 block w-full rounded border border-gray-300 p-2"
                    value={tenantId}
                    onChange={(e) => {
                      setTenantId(e.target.value);
                      invalidateDryRun();
                    }}
                    data-testid="p22-tenant-input"
                  />
                </label>
                <label className="block text-sm text-gray-700">
                  Requested state (optional)
                  <input
                    className="mt-1 block w-full rounded border border-gray-300 p-2"
                    value={requestedState}
                    onChange={(e) => {
                      setRequestedState(e.target.value);
                      invalidateDryRun();
                    }}
                    data-testid="p22-state-input"
                  />
                </label>
              </div>
              <label className="block text-sm text-gray-700">
                Reason (required; redacted before any record or response)
                <textarea
                  className="mt-1 block w-full rounded border border-gray-300 p-2"
                  rows={2}
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  data-testid="p22-reason-input"
                />
              </label>
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="block text-sm text-gray-700">
                  Idempotency key (required; hashed to a digest; raw key never returned)
                  <input
                    className="mt-1 block w-full rounded border border-gray-300 p-2 font-mono"
                    value={idempotencyKey}
                    onChange={(e) => setIdempotencyKey(e.target.value)}
                    data-testid="p22-idempotency-input"
                  />
                </label>
                <label className="block text-sm text-gray-700">
                  Execution mode (required; accepted, never executed)
                  <select
                    className="mt-1 block w-full rounded border border-gray-300 p-2"
                    value={executionMode}
                    onChange={(e) => {
                      setExecutionMode(e.target.value as 'sync' | 'queued');
                      invalidateDryRun();
                    }}
                    data-testid="p22-mode-select"
                  >
                    <option value="sync">sync</option>
                    <option value="queued">queued</option>
                  </select>
                </label>
              </div>
              <label className="block text-sm text-gray-700">
                Correlation id (optional)
                <input
                  className="mt-1 block w-full rounded border border-gray-300 p-2"
                  value={correlationId}
                  onChange={(e) => setCorrelationId(e.target.value)}
                  data-testid="p22-correlation-input"
                />
              </label>
              <label className="block text-sm text-gray-700">
                Metadata (optional; JSON object; redacted before audit)
                <textarea
                  className="mt-1 block w-full rounded border border-gray-300 p-2 font-mono text-xs"
                  rows={2}
                  value={metadataText}
                  onChange={(e) => setMetadataText(e.target.value)}
                  data-testid="p22-metadata-input"
                />
              </label>
              {!metadataValid ? (
                <p className="text-xs text-red-600" data-testid="p22-metadata-error">
                  {metadataParse.ok ? '' : metadataParse.error}
                </p>
              ) : null}
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  disabled={!dryRunFormValid || dryRunBusy}
                  onClick={runDryRun}
                  className="rounded bg-gray-200 px-4 py-2 text-sm font-medium text-gray-800 disabled:opacity-50"
                  data-testid="p22-dry-run-btn"
                >
                  Run dry-run (no mutation)
                </button>
                {!dryRunFormValid ? (
                  <span className="text-xs text-gray-400" data-testid="p22-form-hint">
                    A durable approval id, an allowlisted action, a reason, and an idempotency key
                    are required before a dry-run can run.
                  </span>
                ) : null}
              </div>
            </div>
          </section>

          {/* Dry-run result (always non-executing) */}
          {dryRunResult ? (
            <section
              className="rounded-lg border border-gray-200 bg-white p-4"
              data-testid="p22-dry-run-result"
            >
              <div className="flex flex-wrap items-center gap-3">
                <span
                  className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${VERDICT_TONE[dryRunResult.verdict] ?? 'bg-gray-100 text-gray-600'}`}
                  data-testid="p22-verdict-badge"
                >
                  verdict: {dryRunResult.verdict}
                </span>
                <span className="text-xs text-gray-600" data-testid="p22-executable">
                  executable: {String(dryRunResult.executable)}
                </span>
                <span
                  className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs ${SOURCE_TONE[dryRunResult.source_status] ?? 'bg-gray-100 text-gray-600'}`}
                  data-testid="p22-source-status"
                >
                  source: {dryRunResult.source_status}
                </span>
                <span className="text-xs text-gray-500">
                  reversible: {String(dryRunResult.reversible)}
                </span>
              </div>
              <p
                className="mt-2 text-sm font-semibold text-gray-900"
                data-testid="p22-dry-run-not-executed"
              >
                Dry-run complete: not executed (executed=false, execution_allowed=false,
                execution_started=false).
              </p>
              {dryRunResult.block_reasons.length > 0 ? (
                <div
                  className="mt-2 rounded bg-red-50 p-2 text-xs text-red-800"
                  data-testid="p22-block-reasons"
                >
                  <span className="font-semibold">Block reasons: </span>
                  <span data-testid="p22-block-reasons-text">
                    {dryRunResult.block_reasons.join(', ')}
                  </span>
                </div>
              ) : null}
              {dryRunResult.dry_run_id ? (
                <p className="mt-2 text-xs text-gray-500" data-testid="p22-dry-run-id">
                  dry_run_id: {dryRunResult.dry_run_id}
                </p>
              ) : null}
              {dryRunResult.idempotency_key_digest ? (
                <p className="mt-1 text-xs text-gray-500" data-testid="p22-dry-run-digest">
                  idempotency_key_digest: {dryRunResult.idempotency_key_digest}
                </p>
              ) : null}
              {Object.keys(dryRunResult.expected_audit_shape).length > 0 ? (
                <p className="mt-1 text-xs text-gray-500" data-testid="p22-expected-audit">
                  Expected audit events (field names only, no values):{' '}
                  {Object.keys(dryRunResult.expected_audit_shape).join(', ')}
                </p>
              ) : null}
            </section>
          ) : null}

          {/* Record request (only after a passed dry-run + explicit ack) */}
          {dryRunPassed ? (
            <section
              className="rounded-lg border border-gray-300 bg-white p-4"
              data-testid="p22-record-section"
            >
              <h2 className="text-lg font-semibold text-gray-900">
                Record non-executing request
              </h2>
              <p className="mt-1 mb-3 text-xs text-gray-500">
                Recording a request is not execution. The request will be recorded at
                dry_run_passed and will not be executed, queued for execution, or dispatched to a
                worker. Bound to dry_run_ref:{' '}
                <span className="font-mono" data-testid="p22-dry-run-ref">
                  {dryRunResult?.dry_run_id}
                </span>
              </p>
              <label className="flex items-start gap-2 text-sm text-gray-700">
                <input
                  type="checkbox"
                  checked={executionAck}
                  onChange={(e) => setExecutionAck(e.target.checked)}
                  className="mt-1"
                  data-testid="p22-ack-input"
                />
                <span data-testid="p22-ack-label">
                  I acknowledge that recording this request does NOT execute the action, does NOT
                  dispatch a worker, and does NOT change any tenant, payment, billing, or product
                  state. (Required.)
                </span>
              </label>
              <div className="mt-3 flex items-center gap-3">
                <button
                  type="button"
                  disabled={!recordEnabled}
                  onClick={recordRequest}
                  className="rounded bg-primary-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                  data-testid="p22-record-btn"
                >
                  Record non-executing request
                </button>
                {!executionAck ? (
                  <span className="text-xs text-gray-400" data-testid="p22-record-hint">
                    The acknowledgement is required before a request can be recorded.
                  </span>
                ) : null}
              </div>
            </section>
          ) : (
            <section
              className="rounded-lg border border-dashed border-gray-300 bg-gray-50 p-4"
              data-testid="p22-record-disabled"
            >
              <p className="text-xs text-gray-500">
                Recording is unavailable until a dry-run passes. A passed dry-run is a precondition,
                not an execution.
              </p>
            </section>
          )}

          {/* Record result (always non-executing) */}
          {recordResult ? (
            <section
              className="rounded-lg border border-gray-200 bg-white p-4"
              data-testid="p22-record-result"
            >
              <div className="flex flex-wrap items-center gap-3">
                <span
                  className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${RESULT_TONE[recordResult.result] ?? 'bg-gray-100 text-gray-600'}`}
                  data-testid="p22-result-badge"
                >
                  {recordResult.result}
                </span>
                <span
                  className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-gray-100 text-gray-700"
                  data-testid="p22-result-state"
                >
                  result_state: {recordResult.result_state}
                </span>
                <span className="text-xs text-gray-500">
                  redaction_applied: {String(recordResult.redaction_applied)}
                </span>
              </div>
              <p
                className="mt-2 text-sm font-semibold text-gray-900"
                data-testid="p22-not-executed"
              >
                Request recorded: not executed (executed=false, execution_allowed=false,
                execution_started=false).
              </p>
              <p className="mt-1 text-sm text-gray-700">{recordResult.message}</p>
              <ul className="mt-2 space-y-0.5 text-xs text-gray-500">
                <li>
                  action_type: <span className="font-mono">{recordResult.action_type}</span>
                </li>
                <li>
                  durable_approval_id:{' '}
                  <span className="font-mono">{recordResult.durable_approval_id}</span>
                </li>
                <li>
                  actor: {recordResult.actor_role} / {recordResult.identity_context}
                  {recordResult.actor_id ? ` (${recordResult.actor_id})` : ''}
                </li>
                <li>
                  execution_request_id:{' '}
                  <span className="font-mono">{recordResult.execution_request_id}</span>
                </li>
                <li data-testid="p22-idempotency-digest">
                  idempotency_key_digest: {recordResult.idempotency_key_digest}
                </li>
                <li>payload_digest: {recordResult.payload_digest}</li>
                <li>reason_redacted: {recordResult.reason_redacted}</li>
                <li>created_at: {recordResult.created_at}</li>
              </ul>
            </section>
          ) : null}

          {/* Queue + read (read-only) */}
          <section
            className="rounded-lg border border-gray-200 bg-white p-4"
            data-testid="p22-queue-section"
          >
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">Recorded requests (queue)</h2>
                <p className="text-xs text-gray-500">
                  Ephemeral in-memory queue; recorded requests are listed for review and are not
                  executed.
                </p>
              </div>
              <button
                type="button"
                onClick={refreshQueue}
                className="rounded bg-gray-200 px-3 py-2 text-sm font-medium text-gray-800"
                data-testid="p22-refresh-queue-btn"
              >
                Refresh queue
              </button>
            </div>
            {queue ? (
              <div className="mt-3" data-testid="p22-queue">
                <p className="text-xs text-gray-500" data-testid="p22-queue-summary">
                  {queue.total} recorded requests; storage={queue.storage}; executed=
                  {String(queue.executed)}
                </p>
                {queue.items.length === 0 ? (
                  <p className="mt-2 text-xs text-gray-400" data-testid="p22-queue-empty">
                    No recorded requests. The queue is empty (and still not executed).
                  </p>
                ) : (
                  <ul className="mt-2 divide-y divide-gray-100">
                    {queue.items.map((item) => (
                      <li
                        key={item.execution_request_id ?? `${item.action_type}-${item.created_at}`}
                        className="py-2"
                        data-testid="p22-queue-item"
                      >
                        <div className="flex flex-wrap items-center gap-2 text-sm">
                          <span className="font-mono text-gray-900">{item.action_type}</span>
                          <span
                            className={`rounded-full px-2 py-0.5 text-xs ${RESULT_TONE[item.result] ?? 'bg-gray-100 text-gray-600'}`}
                            data-testid="p22-queue-item-result"
                          >
                            {item.result}
                          </span>
                          <span
                            className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-700"
                            data-testid="p22-queue-item-state"
                          >
                            {item.result_state}
                          </span>
                          <span className="text-xs text-gray-500">
                            actor: {item.actor_role}/{item.identity_context}
                          </span>
                          <span className="text-xs text-gray-400">
                            executed={String(item.executed)}
                          </span>
                        </div>
                        <div className="mt-0.5 text-xs text-gray-500">
                          approval: {item.durable_approval_id}; redaction_applied=
                          {String(item.redaction_applied)}; digest={item.idempotency_key_digest};
                          created_at={item.created_at}
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ) : (
              <p className="mt-3 text-xs text-gray-400">Refresh to load the recorded request queue.</p>
            )}

            {/* Read one by id */}
            <div className="mt-4 border-t border-gray-100 pt-3" data-testid="p22-read-section">
              <label className="block text-sm text-gray-700">
                Read a recorded request by id (read-only)
                <div className="mt-1 flex gap-2">
                  <input
                    className="block flex-1 rounded border border-gray-300 p-2 font-mono text-sm"
                    value={readId}
                    onChange={(e) => setReadId(e.target.value)}
                    placeholder="execution_request_id"
                    data-testid="p22-read-input"
                  />
                  <button
                    type="button"
                    disabled={!readId.trim() || readBusy}
                    onClick={readRequest}
                    className="rounded bg-gray-200 px-3 py-2 text-sm font-medium text-gray-800 disabled:opacity-50"
                    data-testid="p22-read-btn"
                  >
                    Read request
                  </button>
                </div>
              </label>
              {readResult ? (
                <div
                  className="mt-2 rounded border border-gray-200 bg-gray-50 p-3 text-xs text-gray-700"
                  data-testid="p22-read-result"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-gray-900">{readResult.action_type}</span>
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs ${RESULT_TONE[readResult.result] ?? 'bg-gray-100 text-gray-600'}`}
                    >
                      {readResult.result}
                    </span>
                    <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs">
                      {readResult.result_state}
                    </span>
                    <span className="text-gray-400">
                      executed={String(readResult.executed)}
                    </span>
                  </div>
                  <p className="mt-1">
                    approval: {readResult.durable_approval_id}; actor:{' '}
                    {readResult.actor_role}/{readResult.identity_context}; redaction_applied=
                    {String(readResult.redaction_applied)}
                  </p>
                  <p className="mt-0.5">
                    idempotency_key_digest: {readResult.idempotency_key_digest}; payload_digest:{' '}
                    {readResult.payload_digest}
                  </p>
                  <p className="mt-0.5 text-gray-500">{readResult.message}</p>
                </div>
              ) : null}
            </div>
          </section>
        </>
      ) : null}
    </div>
  );
}

/** Best-effort operator-facing error message from an axios failure. */
function errMessage(err: unknown, fallback: string): string {
  if (err && typeof err === 'object') {
    const e = err as { message?: string; response?: { data?: unknown } };
    const detail = e.response?.data;
    if (detail && typeof detail === 'object') {
      const d = detail as { detail?: { message?: string }; message?: string };
      if (d.detail && typeof d.detail === 'object' && d.detail.message) {
        return `${fallback} (${d.detail.message})`;
      }
      if (typeof d.message === 'string') {
        return `${fallback} (${d.message})`;
      }
    }
    if (typeof e.message === 'string' && e.message.length > 0) {
      return `${fallback} (${e.message})`;
    }
  }
  return fallback;
}
