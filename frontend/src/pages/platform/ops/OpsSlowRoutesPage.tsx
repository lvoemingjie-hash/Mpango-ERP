/**
 * OpsSlowRoutesPage -- read-only P13 slow route analysis.
 *
 * Shows SlowRouteSummary from P13 /ops/slow-routes endpoint.
 * source_status unavailable = gray "Data unavailable", null total = N/A.
 * null != 0; no mutation paths; no sensitive data.
 */
import { useEffect, useState } from 'react';
import { platformService } from '@/services/platformApi';
import { PlatformErrorState } from '@/components/platform/PlatformErrorState';
import { Skeleton } from '@/components/ui/Skeleton';
import type { SlowRouteSummary } from '@/types/platformOps';
import { displayOpsCount, isSourceUnavailable, sourceStatusLabel } from '@/types/platformOps';

export function OpsSlowRoutesPage() {
  const [data, setData] = useState<SlowRouteSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSlowRoutes = () => {
    setLoading(true);
    setError(null);
    platformService
      .getOpsSlowRoutes()
      .then((res) => setData(res.data?.data ?? res.data))
      .catch((err) => setError(err.message ?? 'Failed to load slow route data'))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchSlowRoutes();
  }, []);

  const unavailable = data ? isSourceUnavailable(data.source_status) : false;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Slow Routes</h1>
        <p className="mt-1 text-sm text-gray-500">
          Read-only slow route analysis. No mutation paths.
        </p>
      </div>

      {error ? (
        <PlatformErrorState message={error} onRetry={fetchSlowRoutes} />
      ) : loading ? (
        <div className="space-y-4">
          <Skeleton className="h-10 w-48" />
          <Skeleton className="h-40 w-full rounded-lg" />
        </div>
      ) : data ? (
        <>
          {/* Source status banner */}
          <div className={`rounded-lg border p-4 ${unavailable ? 'border-gray-200 bg-gray-50' : 'border-green-200 bg-green-50'}`}>
            <div className="flex items-center gap-3">
              <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${unavailable ? 'bg-gray-200 text-gray-600' : 'bg-green-100 text-green-800'}`}>
                {data.source_status}
              </span>
              <span className="text-sm text-gray-600">{sourceStatusLabel(data.source_status)}</span>
            </div>
            {unavailable && data.unavailable_reason ? (
              <p className="mt-2 text-sm text-gray-500" data-testid="unavailable-reason">
                {data.unavailable_reason}
              </p>
            ) : null}
          </div>

          {/* Summary cards */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-4">
            <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
              <p className="text-sm font-medium text-gray-500">Total Slow Requests</p>
              <p className={`mt-1 text-2xl font-semibold ${data.total_slow_requests === null ? 'text-gray-400' : 'text-gray-900'}`} title={data.total_slow_requests === null ? 'Data unavailable' : undefined}>
                {displayOpsCount(data.total_slow_requests)}
              </p>
            </div>
            <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
              <p className="text-sm font-medium text-gray-500">Threshold</p>
              <p className="mt-1 text-2xl font-semibold text-gray-900">{data.threshold_ms}ms</p>
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

          {/* Routes table */}
          <section>
            <h2 className="text-lg font-semibold text-gray-900 mb-3">Slow Routes</h2>
            {data.routes.length === 0 ? (
              <div className="rounded-lg border border-gray-200 bg-gray-50 p-6 text-center">
                <p className="text-sm text-gray-400">{unavailable ? 'Data unavailable' : 'No slow routes detected'}</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Route</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Requests</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">P50</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">P95</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">P99</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200 bg-white">
                    {data.routes.map((r) => (
                      <tr key={r.route}>
                        <td className="px-4 py-3 text-sm text-gray-900 font-mono">{r.route}</td>
                        <td className="px-4 py-3 text-sm text-gray-900">{r.request_count}</td>
                        <td className="px-4 py-3 text-sm text-gray-900">{r.p50_ms !== null ? `${r.p50_ms}ms` : 'N/A'}</td>
                        <td className="px-4 py-3 text-sm text-gray-900">{r.p95_ms !== null ? `${r.p95_ms}ms` : 'N/A'}</td>
                        <td className="px-4 py-3 text-sm text-gray-900">{r.p99_ms !== null ? `${r.p99_ms}ms` : 'N/A'}</td>
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
