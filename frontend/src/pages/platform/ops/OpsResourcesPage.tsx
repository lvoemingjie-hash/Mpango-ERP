/**
 * OpsResourcesPage -- read-only P13 resource health summary.
 *
 * Shows ResourceHealthSummary from P13 /ops/resources endpoint.
 * Database, queue, CPU, memory, disk health.
 * Unknown != healthy; null components show N/A.
 * No mutation paths; no sensitive data.
 */
import { useEffect, useState } from 'react';
import { platformService } from '@/services/platformApi';
import { PlatformStatusBadge } from '@/components/platform/PlatformStatusBadge';
import { PlatformErrorState } from '@/components/platform/PlatformErrorState';
import { Skeleton } from '@/components/ui/Skeleton';
import type { ResourceHealthSummary } from '@/types/platformOps';
import { displayOpsCount } from '@/types/platformOps';

export function OpsResourcesPage() {
  const [data, setData] = useState<ResourceHealthSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchResources = () => {
    setLoading(true);
    setError(null);
    platformService
      .getOpsResources()
      .then((res) => setData(res.data?.data ?? res.data))
      .catch((err) => setError(err.message ?? 'Failed to load resource data'));
  };

  useEffect(() => {
    fetchResources();
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Resources</h1>
        <p className="mt-1 text-sm text-gray-500">
          Read-only resource health summary. No mutation paths.
        </p>
      </div>

      {error ? (
        <PlatformErrorState message={error} onRetry={fetchResources} />
      ) : loading ? (
        <div className="space-y-4">
          <Skeleton className="h-10 w-48" />
          <div className="grid grid-cols-2 gap-4">
            <Skeleton className="h-32 w-full rounded-lg" />
            <Skeleton className="h-32 w-full rounded-lg" />
          </div>
        </div>
      ) : data ? (
        <>
          <p className="text-sm text-gray-500">
            Generated at: {new Date(data.generated_at).toLocaleString()}
          </p>

          {/* Database */}
          <section>
            <h2 className="text-lg font-semibold text-gray-900 mb-3">Database</h2>
            <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
              <div className="flex items-center gap-3 mb-4">
                <PlatformStatusBadge status={data.database.status} />
              </div>
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                <div>
                  <p className="text-sm font-medium text-gray-500">Active Connections</p>
                  <p className={`mt-1 text-lg font-semibold ${data.database.connection_pool_active === null ? 'text-gray-400' : 'text-gray-900'}`}>
                    {displayOpsCount(data.database.connection_pool_active)}
                  </p>
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-500">Idle Connections</p>
                  <p className={`mt-1 text-lg font-semibold ${data.database.connection_pool_idle === null ? 'text-gray-400' : 'text-gray-900'}`}>
                    {displayOpsCount(data.database.connection_pool_idle)}
                  </p>
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-500">Max Pool</p>
                  <p className={`mt-1 text-lg font-semibold ${data.database.connection_pool_max === null ? 'text-gray-400' : 'text-gray-900'}`}>
                    {displayOpsCount(data.database.connection_pool_max)}
                  </p>
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-500">Query Latency</p>
                  <p className={`mt-1 text-lg font-semibold ${data.database.latency_ms === null ? 'text-gray-400' : 'text-gray-900'}`}>
                    {data.database.latency_ms !== null ? `${data.database.latency_ms}ms` : 'N/A'}
                  </p>
                </div>
              </div>
            </div>
          </section>

          {/* Queue */}
          <section>
            <h2 className="text-lg font-semibold text-gray-900 mb-3">Queue</h2>
            {data.queue ? (
              <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
                <div className="flex items-center gap-3 mb-4">
                  <PlatformStatusBadge status={data.queue.status} />
                </div>
                <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
                  <div>
                    <p className="text-sm font-medium text-gray-500">Depth</p>
                    <p className={`mt-1 text-lg font-semibold ${data.queue.depth === null ? 'text-gray-400' : 'text-gray-900'}`}>
                      {displayOpsCount(data.queue.depth)}
                    </p>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-gray-500">Workers</p>
                    <p className={`mt-1 text-lg font-semibold ${data.queue.worker_count === null ? 'text-gray-400' : 'text-gray-900'}`}>
                      {displayOpsCount(data.queue.worker_count)}
                    </p>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-gray-500">Oldest Pending</p>
                    <p className={`mt-1 text-lg font-semibold ${data.queue.oldest_pending_age_s === null ? 'text-gray-400' : 'text-gray-900'}`}>
                      {data.queue.oldest_pending_age_s !== null ? `${data.queue.oldest_pending_age_s}s` : 'N/A'}
                    </p>
                  </div>
                </div>
              </div>
            ) : (
              <div className="rounded-lg border border-gray-200 bg-gray-50 p-6 text-center">
                <p className="text-sm text-gray-400">Not instrumented</p>
              </div>
            )}
          </section>

          {/* CPU, Memory, Disk */}
          {(['cpu', 'memory', 'disk'] as const).map((component) => {
            const c = data[component];
            const label = component.toUpperCase();
            return (
              <section key={component}>
                <h2 className="text-lg font-semibold text-gray-900 mb-3">{label}</h2>
                {c ? (
                  <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
                    <div className="flex items-center gap-3 mb-2">
                      <PlatformStatusBadge status={c.status} />
                      {c.usage_percent !== null && (
                        <span className="text-sm text-gray-600">{c.usage_percent.toFixed(1)}%</span>
                      )}
                    </div>
                    {c.detail && <p className="text-sm text-gray-500">{c.detail}</p>}
                  </div>
                ) : (
                  <div className="rounded-lg border border-gray-200 bg-gray-50 p-6 text-center">
                    <p className="text-sm text-gray-400">Not instrumented</p>
                  </div>
                )}
              </section>
            );
          })}
        </>
      ) : null}
    </div>
  );
}
