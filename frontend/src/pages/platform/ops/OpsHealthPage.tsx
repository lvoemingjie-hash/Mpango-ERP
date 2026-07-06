/**
 * OpsHealthPage -- read-only P13 ops system health.
 *
 * Shows overall system health via P13 /ops/health endpoint.
 * Reuses P10 SystemHealth shape. Null components show N/A.
 * Unknown != healthy; no mutation paths.
 */
import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import {
  ExclamationTriangleIcon,
  ClockIcon,
  CpuChipIcon,
  SignalIcon,
} from '@heroicons/react/24/outline';
import { usePlatformStore } from '@/stores/platformStore';
import { platformService } from '@/services/platformApi';
import { PlatformStatusBadge } from '@/components/platform/PlatformStatusBadge';
import { PlatformMetricCard } from '@/components/platform/PlatformMetricCard';
import { PlatformErrorState } from '@/components/platform/PlatformErrorState';
import { Skeleton } from '@/components/ui/Skeleton';
import { displayCount } from '@/types/platform';

/**
 * Read-only operations drill-downs not surfaced in the Sidebar. The Ops
 * Cockpit is the operator hub for these views; each link targets an existing
 * as-built ops route (no new capability). Navigation only -- no mutation path.
 */
const OPS_VIEW_LINKS = [
  { to: '/platform/ops/errors', label: 'Ops Errors', icon: ExclamationTriangleIcon, description: 'Recent error classes and counts' },
  { to: '/platform/ops/slow-routes', label: 'Slow Routes', icon: ClockIcon, description: 'Routes exceeding the latency threshold' },
  { to: '/platform/ops/resources', label: 'Resources', icon: CpuChipIcon, description: 'Database, queue, and runtime resources' },
  { to: '/platform/ops/noisy-neighbors', label: 'Noisy Neighbors', icon: SignalIcon, description: 'Tenants disproportionately using capacity' },
] as const;

export function OpsHealthPage() {
  const {
    systemHealth,
    systemHealthLoading,
    systemHealthError,
    setSystemHealth,
    setSystemHealthLoading,
    setSystemHealthError,
  } = usePlatformStore();

  const fetchHealth = () => {
    setSystemHealthLoading(true);
    setSystemHealthError(null);
    platformService
      .getOpsHealth()
      .then((res) => {
        const data = res.data?.data ?? res.data;
        setSystemHealth(data);
      })
      .catch((err) => setSystemHealthError(err.message ?? 'Failed to load ops health'));
  };

  useEffect(() => {
    fetchHealth();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const components: [string, string | null][] = systemHealth
    ? [
        ['API', systemHealth.api_status],
        ['Database', systemHealth.database_status],
        ['Queue', systemHealth.queue_status],
        ['CPU', systemHealth.cpu_status],
        ['Memory', systemHealth.memory_status],
        ['Disk', systemHealth.disk_status],
      ]
    : [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Ops Health</h1>
        <p className="mt-1 text-sm text-gray-500">
          Read-only operations health dashboard. No mutation paths.
        </p>
      </div>

      {systemHealthError ? (
        <PlatformErrorState message={systemHealthError} onRetry={fetchHealth} />
      ) : systemHealthLoading ? (
        <div className="space-y-4">
          <Skeleton className="h-10 w-48" />
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
            {[1, 2, 3, 4, 5, 6].map((i) => (
              <Skeleton key={i} className="h-20 w-full rounded-lg" />
            ))}
          </div>
        </div>
      ) : systemHealth ? (
        <>
          {/* Overall Status */}
          <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
            <div className="flex items-center gap-4">
              <h2 className="text-lg font-semibold text-gray-900">Overall Status</h2>
              <PlatformStatusBadge status={systemHealth.overall_status} />
            </div>
            <p className="mt-1 text-sm text-gray-500">
              Generated at: {new Date(systemHealth.generated_at).toLocaleString()}
            </p>
          </div>

          {/* Component Grid */}
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
            {components.map(([label, status]) => (
              <div key={label} className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm text-center">
                <p className="text-xs font-medium text-gray-500">{label}</p>
                <div className="mt-2">
                  {status ? (
                    <PlatformStatusBadge status={status as 'healthy' | 'degraded' | 'unhealthy' | 'down' | 'unknown'} />
                  ) : (
                    <span className="inline-flex items-center rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-gray-400" title="Not instrumented">
                      N/A
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>

          {/* Database Connections */}
          {systemHealth.database_connections && (
            <section>
              <h2 className="text-lg font-semibold text-gray-900 mb-3">Database Connections</h2>
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                <PlatformMetricCard label="Active" value={systemHealth.database_connections.active} />
                <PlatformMetricCard label="Idle" value={systemHealth.database_connections.idle} />
                <PlatformMetricCard label="Max" value={systemHealth.database_connections.max} />
                <PlatformMetricCard label="Saturation" value={null}>
                  <p className="mt-1 text-lg font-semibold text-gray-900">
                    {systemHealth.database_connections.saturation_pct.toFixed(1)}%
                  </p>
                </PlatformMetricCard>
              </div>
            </section>
          )}

          {/* Error Rate & Slow Requests */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
              <p className="text-sm font-medium text-gray-500">Error Rate</p>
              <p className="mt-1 text-2xl font-semibold text-gray-900">
                {systemHealth.error_rate !== null
                  ? `${(systemHealth.error_rate * 100).toFixed(1)}%`
                  : 'N/A'}
              </p>
            </div>
            <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
              <p className="text-sm font-medium text-gray-500">Slow Requests</p>
              <p className="mt-1 text-2xl font-semibold text-gray-900">
                {displayCount(systemHealth.slow_request_count)}
              </p>
            </div>
          </div>
        </>
      ) : null}

      {/* Operations views -- hub links to read-only ops routes not in the Sidebar */}
      <section>
        <h2 className="text-lg font-semibold text-gray-900 mb-3">Operations Views</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {OPS_VIEW_LINKS.map((item) => (
            <Link
              key={item.to}
              to={item.to}
              className="group flex items-start gap-3 rounded-lg border border-gray-200 bg-white p-4 shadow-sm transition-colors hover:bg-gray-50"
            >
              <item.icon className="h-6 w-6 shrink-0 text-gray-400 group-hover:text-gray-500" aria-hidden="true" />
              <div>
                <p className="text-sm font-medium text-gray-900 group-hover:text-gray-700">{item.label}</p>
                <p className="mt-0.5 text-xs text-gray-500">{item.description}</p>
              </div>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
