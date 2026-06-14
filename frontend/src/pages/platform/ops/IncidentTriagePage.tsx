/**
 * IncidentTriagePage -- read-only P15 incident triage snapshot.
 *
 * Shows IncidentTriageSnapshot from P15 /incidents/triage/snapshot.
 * unknown != healthy (gray, never green); null != 0 (N/A, never 0).
 * unavailable_reason / degraded_reason always visible. graceful_degraded stated.
 * No mutation controls; no tenant business fields; no credentials/DSN/host/port.
 */
import { useEffect, useState } from 'react';
import { platformService } from '@/services/platformApi';
import { PlatformStatusBadge } from '@/components/platform/PlatformStatusBadge';
import { PlatformErrorState } from '@/components/platform/PlatformErrorState';
import { Skeleton } from '@/components/ui/Skeleton';
import type { IncidentTriageSnapshot } from '@/types/platformIncident';
import { displayIncidentCount, healthStatusLabel } from '@/types/platformIncident';

export function IncidentTriagePage() {
  const [data, setData] = useState<IncidentTriageSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSnapshot = () => {
    setLoading(true);
    setError(null);
    platformService
      .getIncidentTriageSnapshot()
      .then((res) => setData(res.data?.data ?? res.data))
      .catch((err) => setError(err.message ?? 'Failed to load incident triage snapshot'))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchSnapshot();
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Incident Triage</h1>
        <p className="mt-1 text-sm text-gray-500">
          Read-only triage snapshot. No mutation paths.
        </p>
      </div>

      {error ? (
        <PlatformErrorState message={error} onRetry={fetchSnapshot} />
      ) : loading ? (
        <div className="space-y-4">
          <Skeleton className="h-10 w-48" />
          <Skeleton className="h-40 w-full rounded-lg" />
        </div>
      ) : data ? (
        <>
          {/* Overall status + freshness */}
          <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
            <div className="flex flex-wrap items-center gap-3">
              <PlatformStatusBadge status={data.overall_status} />
              <span className="text-sm text-gray-600">
                {healthStatusLabel(data.overall_status)}
              </span>
              {data.graceful_degraded && (
                <span
                  className="inline-flex items-center rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-800"
                  data-testid="graceful-degraded"
                >
                  Graceful degraded
                </span>
              )}
            </div>
            {data.graceful_degraded ? (
              <p className="mt-2 text-sm text-amber-700">
                Snapshot assembled despite one or more source failures; see reasons below.
              </p>
            ) : null}
            <p className="mt-2 text-sm text-gray-500">
              Generated at: {new Date(data.generated_at).toLocaleString()}
            </p>
            {data.degraded_reason ? (
              <p className="mt-1 text-sm text-gray-600" data-testid="degraded-reason">
                Degraded reason: {data.degraded_reason}
              </p>
            ) : null}
            {data.unavailable_reason ? (
              <p className="mt-1 text-sm text-gray-600" data-testid="unavailable-reason">
                Unavailable reason: {data.unavailable_reason}
              </p>
            ) : null}
          </div>

          {/* Database probe (P14 live signal) */}
          <section>
            <h2 className="text-lg font-semibold text-gray-900 mb-3">Database Probe</h2>
            {data.database_probe ? (
              <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
                <div className="flex items-center gap-3 mb-3">
                  <PlatformStatusBadge status={data.database_probe.status} />
                </div>
                <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                  <div>
                    <p className="text-sm font-medium text-gray-500">Latency</p>
                    <p className={`mt-1 text-lg font-semibold ${data.database_probe.latency_ms === null ? 'text-gray-400' : 'text-gray-900'}`}>
                      {data.database_probe.latency_ms !== null ? `${data.database_probe.latency_ms}ms` : 'N/A'}
                    </p>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-gray-500">Active</p>
                    <p className={`mt-1 text-lg font-semibold ${data.database_probe.connection_pool_active === null ? 'text-gray-400' : 'text-gray-900'}`}>
                      {displayIncidentCount(data.database_probe.connection_pool_active)}
                    </p>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-gray-500">Idle</p>
                    <p className={`mt-1 text-lg font-semibold ${data.database_probe.connection_pool_idle === null ? 'text-gray-400' : 'text-gray-900'}`}>
                      {displayIncidentCount(data.database_probe.connection_pool_idle)}
                    </p>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-gray-500">Max Pool</p>
                    <p className={`mt-1 text-lg font-semibold ${data.database_probe.connection_pool_max === null ? 'text-gray-400' : 'text-gray-900'}`}>
                      {displayIncidentCount(data.database_probe.connection_pool_max)}
                    </p>
                  </div>
                </div>
              </div>
            ) : (
              <div className="rounded-lg border border-gray-200 bg-gray-50 p-6 text-center">
                <p className="text-sm text-gray-400">Database probe unavailable</p>
              </div>
            )}
          </section>

          {/* Tenant health sample counts (no business records) */}
          <section>
            <h2 className="text-lg font-semibold text-gray-900 mb-3">Tenant Health Sample</h2>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
                <p className="text-sm font-medium text-gray-500">Tenants (sample)</p>
                <p className={`mt-1 text-2xl font-semibold ${data.tenant_health_sample_count === null ? 'text-gray-400' : 'text-gray-900'}`}>
                  {displayIncidentCount(data.tenant_health_sample_count)}
                </p>
              </div>
              <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
                <p className="text-sm font-medium text-gray-500">Non-healthy (sample)</p>
                <p className={`mt-1 text-2xl font-semibold ${data.tenant_health_unhealthy_count === null ? 'text-gray-400' : 'text-gray-900'}`}>
                  {displayIncidentCount(data.tenant_health_unhealthy_count)}
                </p>
              </div>
            </div>
          </section>

          {/* Signals */}
          <section>
            <h2 className="text-lg font-semibold text-gray-900 mb-3">Signals</h2>
            {data.signals.length === 0 ? (
              <div className="rounded-lg border border-gray-200 bg-gray-50 p-6 text-center">
                <p className="text-sm text-gray-400">No signals</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Kind</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Severity</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Source</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Reason</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200 bg-white">
                    {data.signals.map((s) => (
                      <tr key={s.signal_id}>
                        <td className="px-4 py-3 text-sm text-gray-900">{s.kind}</td>
                        <td className="px-4 py-3 text-sm text-gray-900">{s.severity}</td>
                        <td className="px-4 py-3 text-sm text-gray-900 font-mono">{s.source_ref}</td>
                        <td className="px-4 py-3 text-sm text-gray-900">{s.source_status}</td>
                        <td className="px-4 py-3 text-sm text-gray-500">
                          {s.degraded_reason ?? s.unavailable_reason ?? 'N/A'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      ) : null}
    </div>
  );
}
