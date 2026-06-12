/**
 * SupportConsolePage -- P12-C0 route shell with reason-required form.
 *
 * This is a wiring/contract slice, NOT the full support workflow UI.
 * Provides:
 *   - Reason textarea (required, min 10 chars, client-side validation)
 *   - Category select
 *   - Optional tenant ID input
 *   - Start/Close session buttons
 *
 * Contract note: Backend CreateSessionRequest.reason is Optional only to
 * allow route-layer 400 + support_access_denied audit (P12-B-R3).
 * Frontend MUST require reason before API call. This is enforced by
 * isReasonValid() client-side and the disabled button state.
 *
 * Boundaries:
 *   - No mutation controls, no impersonation, no business data editing.
 *   - No bundle download UI (future P12-C slice).
 *   - No full diagnostics dashboard (future P12-C slice).
 *   - Read-only display of session state only.
 */
import { useState, useCallback } from 'react';
import { supportService } from '@/services/supportApi';
import {
  isReasonValid,
  getReasonValidationError,
  REASON_MIN_LENGTH,
} from '@/types/support';
import type {
  SupportCategory,
  SupportSession,
  SupportErrorDetail,
} from '@/types/support';

const SUPPORT_CATEGORIES: { value: SupportCategory; label: string }[] = [
  { value: 'login_issue', label: 'Login Issue' },
  { value: 'activity_anomaly', label: 'Activity Anomaly' },
  { value: 'performance', label: 'Performance' },
  { value: 'data_integrity', label: 'Data Integrity' },
  { value: 'integration', label: 'Integration' },
  { value: 'general', label: 'General' },
  { value: 'incident', label: 'Incident' },
  { value: 'other', label: 'Other' },
];

export function SupportConsolePage() {
  // Form state
  const [reason, setReason] = useState('');
  const [category, setCategory] = useState<SupportCategory>('general');
  const [tenantId, setTenantId] = useState('');

  // Session state
  const [session, setSession] = useState<SupportSession | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Client-side validation
  const reasonError = getReasonValidationError(reason || null);
  const isFormValid = reasonError === null;

  const handleStartSession = useCallback(async () => {
    // Client-side guard: reason MUST be valid before API call
    if (!isReasonValid(reason)) return;

    setLoading(true);
    setError(null);

    try {
      const response = await supportService.createSession({
        reason,
        category,
        tenant_id: tenantId.trim() || null,
      });
      setSession(response.data);
    } catch (err: unknown) {
      // Handle backend 400 error codes (P12-B-R3 belt-and-suspenders)
      const axiosErr = err as { response?: { data?: { detail?: SupportErrorDetail } } };
      const detail = axiosErr?.response?.data?.detail;
      if (detail?.code === 'MISSING_REASON') {
        setError('Support reason is required.');
      } else if (detail?.code === 'REASON_TOO_SHORT') {
        setError(`Support reason must be at least ${REASON_MIN_LENGTH} characters.`);
      } else {
        setError(detail?.message ?? 'Failed to create support session.');
      }
    } finally {
      setLoading(false);
    }
  }, [reason, category, tenantId]);

  const handleCloseSession = useCallback(async () => {
    if (!session) return;
    setLoading(true);
    setError(null);
    try {
      const response = await supportService.closeSession(session.session_id);
      setSession(response.data);
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: SupportErrorDetail } } };
      const detail = axiosErr?.response?.data?.detail;
      setError(detail?.message ?? 'Failed to close support session.');
    } finally {
      setLoading(false);
    }
  }, [session]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Support Console</h1>
        <p className="mt-1 text-sm text-gray-500">
          Create request-scoped diagnostic sessions for tenant support.
          Sessions are in-memory only and expire after 60 minutes.
        </p>
      </div>

      {/* Session Active Display */}
      {session && session.status === 'active' && (
        <div className="rounded-md bg-blue-50 p-4">
          <h3 className="text-sm font-medium text-blue-800">Active Session</h3>
          <p className="mt-1 text-sm text-blue-700">
            Session {session.session_id.slice(0, 8)}... started for {session.category}
          </p>
          <p className="mt-1 text-xs text-blue-600">
            Expires: {session.expires_at ?? 'N/A'}
          </p>
          {/* P12-C0: No mutation controls, no impersonation, no business data editing */}
          <button
            type="button"
            onClick={handleCloseSession}
            disabled={loading}
            className="mt-3 rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            data-testid="close-session-btn"
          >
            Close Session
          </button>
        </div>
      )}

      {/* Session Closed Display */}
      {session && session.status === 'closed' && (
        <div className="rounded-md bg-gray-50 p-4">
          <h3 className="text-sm font-medium text-gray-800">Session Closed</h3>
          <p className="mt-1 text-sm text-gray-600">
            Session {session.session_id.slice(0, 8)}... closed.
            Bundles generated: {session.bundle_count}.
          </p>
        </div>
      )}

      {/* Error Display */}
      {error && (
        <div className="rounded-md bg-red-50 p-4" data-testid="error-display">
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {/* Create Session Form */}
      {(!session || session.status !== 'active') && (
        <div className="space-y-4 rounded-md border border-gray-200 p-4">
          <div>
            <label htmlFor="support-reason" className="block text-sm font-medium text-gray-700">
              Reason (required, minimum {REASON_MIN_LENGTH} characters)
            </label>
            <textarea
              id="support-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={3}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:ring-blue-500"
              placeholder="Describe the support reason..."
              data-testid="reason-input"
            />
            {reason && reasonError && (
              <p className="mt-1 text-sm text-red-600" data-testid="reason-validation-error">
                {reasonError}
              </p>
            )}
          </div>

          <div>
            <label htmlFor="support-category" className="block text-sm font-medium text-gray-700">
              Category
            </label>
            <select
              id="support-category"
              value={category}
              onChange={(e) => setCategory(e.target.value as SupportCategory)}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:ring-blue-500"
              data-testid="category-select"
            >
              {SUPPORT_CATEGORIES.map((cat) => (
                <option key={cat.value} value={cat.value}>
                  {cat.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="support-tenant-id" className="block text-sm font-medium text-gray-700">
              Tenant ID (optional)
            </label>
            <input
              id="support-tenant-id"
              type="text"
              value={tenantId}
              onChange={(e) => setTenantId(e.target.value)}
              className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:ring-blue-500"
              placeholder="UUID of target tenant..."
              data-testid="tenant-id-input"
            />
          </div>

          <button
            type="button"
            onClick={handleStartSession}
            disabled={!isFormValid || loading}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
            data-testid="start-session-btn"
          >
            {loading ? 'Starting...' : 'Start Session'}
          </button>
        </div>
      )}

      {/* P12-C0 limitation notice */}
      <p className="text-xs text-gray-400">
        P12-C0 wiring/form shell only. Full diagnostics dashboard and bundle
        download UI will be implemented in a future P12-C slice.
      </p>
    </div>
  );
}
