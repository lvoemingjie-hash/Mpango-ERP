/**
 * PlatformControlledActionsPage -- P18 controlled-action REQUEST skeleton (P18-C).
 *
 * Read-only / request-only UX:
 *   - shows the closed action catalog (read-only)
 *   - validate (dry-run) and submit a controlled-action request skeleton
 *   - renders accepted / denied / duplicate / conflict / degraded results
 *   - always states the request was recorded and NOT executed
 *
 * No destructive execution controls. Button copy is "Validate request" and
 * "Submit request" -- never "execute" / "pause" / "resume" / "trigger". UI copy
 * explicitly distinguishes a request from an execution.
 *
 * Route is platform-only (/platform/controlled-actions) behind the identity-only
 * PlatformRoute guard. Reuses the existing platformService API client.
 */
import { useEffect, useState } from 'react';
import { platformService } from '@/services/platformApi';
import { Skeleton } from '@/components/ui/Skeleton';
import type {
  ControlledActionCatalog,
  ControlledActionRequestPayload,
  ControlledActionRequestQueue,
  ControlledActionRequestResponse,
} from '@/types/platformControlledActions';

const RESULT_TONE: Record<string, string> = {
  accepted: 'bg-green-100 text-green-800',
  denied: 'bg-red-100 text-red-800',
  degraded: 'bg-yellow-100 text-yellow-800',
  duplicate: 'bg-blue-100 text-blue-800',
  conflict: 'bg-orange-100 text-orange-800',
};

function unwrap<T>(res: { data?: unknown }): T {
  const data = res.data as { data?: T } | T | undefined;
  if (data && typeof data === 'object' && 'data' in (data as Record<string, unknown>)) {
    return (data as { data: T }).data;
  }
  return data as T;
}

export function PlatformControlledActionsPage() {
  const [catalog, setCatalog] = useState<ControlledActionCatalog | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [actionType, setActionType] = useState('');
  const [tenantId, setTenantId] = useState('');
  const [reason, setReason] = useState('');
  const [idempotencyKey, setIdempotencyKey] = useState('');
  const [requestedState, setRequestedState] = useState('');
  const [confirm, setConfirm] = useState(true);

  const [result, setResult] = useState<ControlledActionRequestResponse | null>(null);
  const [queue, setQueue] = useState<ControlledActionRequestQueue | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    platformService
      .getControlledActionCatalog()
      .then((res) => {
        const payload = unwrap<ControlledActionCatalog>(res);
        if (!alive) return;
        setCatalog(payload);
        if (payload?.items?.length) {
          setActionType((prev) => prev || payload.items[0].action_type);
        }
      })
      .catch((err) => alive && setError(err.message ?? 'Failed to load controlled-action catalog'))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, []);

  const formValid = reason.trim().length > 0 && idempotencyKey.trim().length > 0;

  const buildPayload = (): ControlledActionRequestPayload => ({
    action_type: actionType,
    tenant_id: tenantId.trim() ? tenantId.trim() : null,
    reason: reason.trim(),
    idempotency_key: idempotencyKey.trim(),
    requested_state: requestedState.trim() ? requestedState.trim() : null,
    confirm,
  });

  const callEndpoint = (
    fn: (p: ControlledActionRequestPayload) => Promise<{ data?: unknown }>,
  ) => {
    setBusy(true);
    setResult(null);
    fn(buildPayload())
      .then((res) => setResult(unwrap<ControlledActionRequestResponse>(res)))
      .catch((err) => setError(err.message ?? 'Controlled-action request failed'))
      .finally(() => setBusy(false));
  };

  const refreshQueue = () => {
    platformService
      .listControlledActionRequests(20, 0)
      .then((res) => setQueue(unwrap<ControlledActionRequestQueue>(res)))
      .catch((err) => setError(err.message ?? 'Controlled-action queue failed'));
  };

  const sourceWarning = !!result && result.source_status !== 'available';

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900" data-testid="ca-title">
          Controlled Action Requests
        </h1>
        <p className="mt-1 text-sm text-gray-500" data-testid="ca-subtitle">
          Request skeleton: requests are recorded and audited, not executed. No registry,
          lifecycle, flag, provisioning, or backup state is changed.
        </p>
      </div>

      {error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4">
          <p className="text-sm text-red-700" data-testid="ca-error">
            {error}
          </p>
        </div>
      ) : loading ? (
        <Skeleton className="h-40 w-full rounded-lg" />
      ) : catalog ? (
        <>
          {/* Action catalog (read-only) */}
          <section data-testid="ca-catalog">
            <h2 className="text-lg font-semibold text-gray-900 mb-1">Action catalog (read-only)</h2>
            <p className="mb-3 text-xs text-gray-500">
              {catalog.total} actions; contract {catalog.contract}; executed={String(catalog.executed)}
            </p>
            <ul className="grid gap-2 sm:grid-cols-2">
              {catalog.items.map((item) => (
                <li
                  key={item.action_type}
                  className="rounded-lg border border-gray-200 bg-white p-3"
                  data-testid="ca-catalog-item"
                >
                  <div className="font-mono text-sm text-gray-900">{item.action_type}</div>
                  <div className="text-xs text-gray-500">
                    {item.classification} - confirmation{' '}
                    {item.confirmation_required ? 'required' : 'not required'}
                    {item.degraded_allowed ? ' - degraded allowed' : ''}
                  </div>
                  <div className="mt-1 text-xs text-gray-400">{item.description}</div>
                </li>
              ))}
            </ul>
          </section>

          {/* Request form (not executed) */}
          <section className="rounded-lg border border-gray-200 bg-white p-4">
            <h2 className="text-lg font-semibold text-gray-900 mb-3">
              Submit a request (not executed)
            </h2>
            <div className="grid gap-3">
              <label className="block text-sm text-gray-700">
                Action type
                <select
                  className="mt-1 block w-full rounded border border-gray-300 p-2"
                  value={actionType}
                  onChange={(e) => setActionType(e.target.value)}
                  data-testid="ca-action-select"
                >
                  {catalog.items.map((item) => (
                    <option key={item.action_type} value={item.action_type}>
                      {item.action_type}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-sm text-gray-700">
                Tenant id (optional)
                <input
                  className="mt-1 block w-full rounded border border-gray-300 p-2"
                  value={tenantId}
                  onChange={(e) => setTenantId(e.target.value)}
                  data-testid="ca-tenant-input"
                />
              </label>
              <label className="block text-sm text-gray-700">
                Reason (required)
                <textarea
                  className="mt-1 block w-full rounded border border-gray-300 p-2"
                  rows={2}
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  data-testid="ca-reason-input"
                />
              </label>
              <label className="block text-sm text-gray-700">
                Idempotency key (required)
                <input
                  className="mt-1 block w-full rounded border border-gray-300 p-2"
                  value={idempotencyKey}
                  onChange={(e) => setIdempotencyKey(e.target.value)}
                  data-testid="ca-idempotency-input"
                />
              </label>
              <label className="block text-sm text-gray-700">
                Requested state (optional)
                <input
                  className="mt-1 block w-full rounded border border-gray-300 p-2"
                  value={requestedState}
                  onChange={(e) => setRequestedState(e.target.value)}
                  data-testid="ca-state-input"
                />
              </label>
              <label className="inline-flex items-center gap-2 text-sm text-gray-700">
                <input
                  type="checkbox"
                  checked={confirm}
                  onChange={(e) => setConfirm(e.target.checked)}
                  data-testid="ca-confirm-input"
                />
                Confirm acknowledgement (required for write / write_request actions)
              </label>
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={!formValid || busy}
                  onClick={() => callEndpoint(platformService.validateControlledAction)}
                  className="rounded bg-gray-200 px-4 py-2 text-sm font-medium text-gray-800 disabled:opacity-50"
                  data-testid="ca-validate-btn"
                >
                  Validate request
                </button>
                <button
                  type="button"
                  disabled={!formValid || busy}
                  onClick={() => callEndpoint(platformService.submitControlledAction)}
                  className="rounded bg-primary-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                  data-testid="ca-submit-btn"
                >
                  Submit request
                </button>
              </div>
              {!formValid ? (
                <p className="text-xs text-gray-400" data-testid="ca-form-hint">
                  A reason and an idempotency key are required before a request can be validated or submitted.
                </p>
              ) : null}
            </div>
          </section>

          {/* Result (always not executed) */}
          {result ? (
            <section className="rounded-lg border border-gray-200 bg-white p-4" data-testid="ca-result">
              <div className="flex flex-wrap items-center gap-3">
                <span
                  className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${RESULT_TONE[result.result] ?? 'bg-gray-100 text-gray-600'}`}
                  data-testid="ca-result-badge"
                >
                  {result.result}
                </span>
                <span className="text-sm text-gray-600" data-testid="ca-result-source">
                  source: {result.source_status}
                </span>
                <span className="text-xs text-gray-400">
                  dry run: {String(result.dry_run)}
                </span>
              </div>
              <p
                className="mt-2 text-sm font-semibold text-gray-900"
                data-testid="ca-not-executed"
              >
                Request recorded: not executed (executed=false).
              </p>
              <p className="mt-1 text-sm text-gray-700">{result.message}</p>
              {result.action_id ? (
                <p className="mt-1 text-xs text-gray-500">action id: {result.action_id}</p>
              ) : null}
              {sourceWarning ? (
                <div
                  className="mt-2 rounded bg-yellow-50 p-2 text-xs text-yellow-800 space-y-1"
                  data-testid="ca-source-warning"
                >
                  <p>
                    {result.result === "degraded"
                      ? "Degraded request: registry source is " + result.source_status + "."
                      : "Not requestable: registry source is " + result.source_status + "."}{" "}
                    No safe execution is possible against an unknown or unavailable source; this
                    request was not executed.
                  </p>
                  {result.degraded_reason ? (
                    <p data-testid="ca-degraded-reason">{result.degraded_reason}</p>
                  ) : null}
                </div>
              ) : null}
            </section>
          ) : null}

          <section className="rounded-lg border border-gray-200 bg-white p-4" data-testid="ca-queue">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">Operator queue</h2>
                <p className="text-xs text-gray-500">
                  Ephemeral memory queue; requests are listed for review and are not executed.
                </p>
              </div>
              <button
                type="button"
                onClick={refreshQueue}
                className="rounded bg-gray-200 px-3 py-2 text-sm font-medium text-gray-800"
                data-testid="ca-refresh-queue-btn"
              >
                Refresh queue
              </button>
            </div>
            {queue ? (
              <div className="mt-3">
                <p className="text-xs text-gray-500" data-testid="ca-queue-summary">
                  {queue.total} recorded requests; storage={queue.storage}; executed={String(queue.executed)}
                </p>
                <ul className="mt-2 divide-y divide-gray-100">
                  {queue.items.map((item) => (
                    <li
                      key={item.action_id ?? `${item.action_type}-${item.created_at}`}
                      className="py-2"
                      data-testid="ca-queue-item"
                    >
                      <div className="flex flex-wrap items-center gap-2 text-sm">
                        <span className="font-mono text-gray-900">{item.action_type}</span>
                        <span
                          className={`rounded-full px-2 py-0.5 text-xs ${RESULT_TONE[item.result] ?? 'bg-gray-100 text-gray-600'}`}
                        >
                          {item.result}
                        </span>
                        <span className="text-xs text-gray-500">source: {item.source_status}</span>
                        <span className="text-xs text-gray-400">executed={String(item.executed)}</span>
                      </div>
                      {item.action_id ? (
                        <p className="mt-1 text-xs text-gray-500">action id: {item.action_id}</p>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <p className="mt-3 text-xs text-gray-400">Refresh to load the current request queue.</p>
            )}
          </section>
        </>
      ) : null}
    </div>
  );
}
