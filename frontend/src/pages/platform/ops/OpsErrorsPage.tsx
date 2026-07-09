/**
 * OpsErrorsPage -- read-only P13 error rate analysis.
 *
 * Shows ErrorRateSummary from P13 /ops/errors endpoint.
 * source_status unavailable = gray "Data unavailable", null total = N/A.
 * null != 0; no mutation paths; no sensitive data.
 */
import { useEffect, useState } from 'react';
import { platformService, unwrapApiResponse } from '@/services/platformApi';
import { PlatformErrorState } from '@/components/platform/PlatformErrorState';
import { Skeleton } from '@/components/ui/Skeleton';
import type { ErrorRateSummary } from '@/types/platformOps';
import { displayOpsCount, isSourceUnavailable, sourceStatusLabel } from '@/types/platformOps';

export function OpsErrorsPage() {
  const [data, setData] = useState<ErrorRateSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchErrors = () => {
    setLoading(true);
    setError(null);
    platformService
      .getOpsErrors()
      .then((res) => setData(unwrapApiResponse<ErrorRateSummary>(res)))
      .catch((err) => setError(err.message ?? 'Failed to load error data'))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchErrors();
  }, []);

  const unavailable = data ? isSourceUnavailable(data.source_status) : false;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Error Analysis</h1>
        <p className="mt-1 text-sm text-gray-500">
          Read-only error rate analysis. No mutation paths.
        </p>
      </div>

      {error ? (
        <PlatformErrorState message={error} onRetry={fetchErrors} />
      ) : loading ? (
        <div className="space-y-4">
          <Skeleton className="h-10 w-48" />
          <div className="grid grid-cols-2 gap-4">
            <Skeleton className="h-20 w-full rounded-lg" />
            <Skeleton className="h-20 w-full rounded-lg" />
          </div>
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

          {/* Total errors */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
              <p className="text-sm font-medium text-gray-500">Total Errors</p>
              <p className={`mt-1 text-2xl font-semibold ${data.total_errors === null ? 'text-gray-400' : 'text-gray-900'}`} title={data.total_errors === null ? 'Data unavailable' : undefined}>
                {displayOpsCount(data.total_errors)}
              </p>
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

          {/* Error classes */}
          <section>
            <h2 className="text-lg font-semibold text-gray-900 mb-3">Error Classes</h2>
            {data.error_classes.length === 0 ? (
              <div className="rounded-lg border border-gray-200 bg-gray-50 p-6 text-center">
                <p className="text-sm text-gray-400">{unavailable ? 'Data unavailable' : 'No errors recorded'}</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Class</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Count</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Percentage</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200 bg-white">
                    {data.error_classes.map((ec) => (
                      <tr key={ec.error_class}>
                        <td className="px-4 py-3 text-sm text-gray-900">{ec.error_class}</td>
                        <td className="px-4 py-3 text-sm text-gray-900">{ec.count}</td>
                        <td className="px-4 py-3 text-sm text-gray-900">{ec.percentage.toFixed(1)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {/* Top routes */}
          <section>
            <h2 className="text-lg font-semibold text-gray-900 mb-3">Top Error Routes</h2>
            {data.top_routes.length === 0 ? (
              <div className="rounded-lg border border-gray-200 bg-gray-50 p-6 text-center">
                <p className="text-sm text-gray-400">{unavailable ? 'Data unavailable' : 'No route errors'}</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Route</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Errors</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">P95 Latency</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200 bg-white">
                    {data.top_routes.map((r) => (
                      <tr key={r.route}>
                        <td className="px-4 py-3 text-sm text-gray-900 font-mono">{r.route}</td>
                        <td className="px-4 py-3 text-sm text-gray-900">{r.error_count}</td>
                        <td className="px-4 py-3 text-sm text-gray-900">{r.latency_bucket_ms !== null ? `${r.latency_bucket_ms}ms` : 'N/A'}</td>
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
