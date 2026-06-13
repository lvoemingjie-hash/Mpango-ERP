/**
 * OpsNoisyNeighborsPage -- read-only P13 noisy-neighbor analysis.
 *
 * Shows NoisyNeighborSummary from P13 /ops/noisy-neighbors endpoint.
 * Empty tenants list when unavailable. No mutation paths.
 * No sensitive data -- tenant IDs only, no business records.
 */
import { useEffect, useState } from 'react';
import { platformService } from '@/services/platformApi';
import { PlatformErrorState } from '@/components/platform/PlatformErrorState';
import { Skeleton } from '@/components/ui/Skeleton';
import type { NoisyNeighborSummary } from '@/types/platformOps';

export function OpsNoisyNeighborsPage() {
  const [data, setData] = useState<NoisyNeighborSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchNoisyNeighbors = () => {
    setLoading(true);
    setError(null);
    platformService
      .getOpsNoisyNeighbors()
      .then((res) => setData(res.data?.data ?? res.data))
      .catch((err) => setError(err.message ?? 'Failed to load noisy neighbor data'))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchNoisyNeighbors();
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Noisy Neighbors</h1>
        <p className="mt-1 text-sm text-gray-500">
          Read-only noisy-neighbor analysis. No mutation paths.
        </p>
      </div>

      {error ? (
        <PlatformErrorState message={error} onRetry={fetchNoisyNeighbors} />
      ) : loading ? (
        <div className="space-y-4">
          <Skeleton className="h-10 w-48" />
          <Skeleton className="h-40 w-full rounded-lg" />
        </div>
      ) : data ? (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
              <p className="text-sm font-medium text-gray-500">Flagged Tenants</p>
              <p className="mt-1 text-2xl font-semibold text-gray-900">{data.tenants.length}</p>
            </div>
            <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
              <p className="text-sm font-medium text-gray-500">Window</p>
              <p className="mt-1 text-2xl font-semibold text-gray-900">{data.window_minutes} min</p>
            </div>
            <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
              <p className="text-sm font-medium text-gray-500">Generated At</p>
              <p className="mt-1 text-sm font-semibold text-gray-900">{new Date(data.generated_at).toLocaleString()}</p>
            </div>
          </div>

          {/* Tenants table */}
          <section>
            <h2 className="text-lg font-semibold text-gray-900 mb-3">Tenant Impact Analysis</h2>
            {data.tenants.length === 0 ? (
              <div className="rounded-lg border border-gray-200 bg-gray-50 p-6 text-center">
                <p className="text-sm text-gray-400">No noisy-neighbor data available.</p>
                {data.unavailable_reason ? (
                  <p className="mt-2 text-sm text-gray-500" data-testid="unavailable-reason">
                    {data.unavailable_reason}
                  </p>
                ) : (
                  <p className="mt-2 text-sm text-gray-400">Cross-tenant telemetry is not yet instrumented.</p>
                )}
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Tenant</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Error Count</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Slow Route Count</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Impact Score</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Top Error</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Top Slow Route</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200 bg-white">
                    {data.tenants.map((t) => (
                      <tr key={t.tenant_id}>
                        <td className="px-4 py-3 text-sm text-gray-900">
                          {t.tenant_name ?? t.tenant_id}
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-900">{t.error_count}</td>
                        <td className="px-4 py-3 text-sm text-gray-900">{t.slow_route_count}</td>
                        <td className="px-4 py-3 text-sm text-gray-900">{t.impact_score.toFixed(2)}</td>
                        <td className="px-4 py-3 text-sm text-gray-900">{t.top_error_class ?? 'N/A'}</td>
                        <td className="px-4 py-3 text-sm text-gray-900 font-mono">{t.top_slow_route ?? 'N/A'}</td>
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
