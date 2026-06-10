/**
 * PlatformOverviewPage — read-only platform admin dashboard.
 *
 * Shows system health overview and tenant count summary.
 * All data is read-only. No write/destructive buttons.
 * Unknown states are displayed distinctly from healthy.
 */
import { useEffect } from 'react';
import { usePlatformStore } from '@/stores/platformStore';
import { platformService } from '@/services/platformApi';
import { PlatformMetricCard } from '@/components/platform/PlatformMetricCard';
import { PlatformStatusBadge } from '@/components/platform/PlatformStatusBadge';
import { PlatformErrorState } from '@/components/platform/PlatformErrorState';
import { Skeleton } from '@/components/ui/Skeleton';

export function PlatformOverviewPage() {
  const {
    tenants,
    tenantsTotal,
    tenantsLoading,
    tenantsError,
    systemHealth,
    systemHealthLoading,
    systemHealthError,
    setTenants,
    setTenantsLoading,
    setTenantsError,
    setSystemHealth,
    setSystemHealthLoading,
    setSystemHealthError,
  } = usePlatformStore();

  const fetchTenants = () => {
    setTenantsLoading(true);
    setTenantsError(null);
    platformService
      .listTenants(10, 0)
      .then((res) => {
        const data = res.data?.data ?? res.data;
        setTenants(data.items ?? [], data.total ?? 0);
      })
      .catch((err) => setTenantsError(err.message ?? 'Failed to load tenants'));
  };

  const fetchSystemHealth = () => {
    setSystemHealthLoading(true);
    setSystemHealthError(null);
    platformService
      .getSystemHealth()
      .then((res) => {
        const data = res.data?.data ?? res.data;
        setSystemHealth(data);
      })
      .catch((err) => setSystemHealthError(err.message ?? 'Failed to load system health'));
  };

  useEffect(() => {
    fetchTenants();
    fetchSystemHealth();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Count tenants by health status
  const healthyCount = tenants.filter((t) => t.health_status === 'healthy').length;
  const degradedCount = tenants.filter((t) => t.health_status === 'degraded').length;
  const unhealthyCount = tenants.filter((t) => t.health_status === 'unhealthy').length;
  const unknownCount = tenants.filter((t) => t.health_status === 'unknown').length;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Platform Overview</h1>
        <p className="mt-1 text-sm text-gray-500">
          Read-only platform admin cockpit. All data is view-only.
        </p>
      </div>

      {/* Tenant Summary Cards */}
      <section>
        <h2 className="text-lg font-semibold text-gray-900 mb-3">Tenants</h2>
        {tenantsError ? (
          <PlatformErrorState message={tenantsError} onRetry={fetchTenants} />
        ) : tenantsLoading ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="rounded-lg border border-gray-200 bg-white p-4">
                <Skeleton className="mb-2 h-4 w-20" />
                <Skeleton className="h-8 w-16" />
              </div>
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <PlatformMetricCard label="Total Tenants" value={tenantsTotal} />
            <PlatformMetricCard label="Healthy" value={healthyCount} />
            <PlatformMetricCard label="Degraded" value={degradedCount} />
            <PlatformMetricCard label="Unhealthy / Unknown" value={unhealthyCount + unknownCount} />
          </div>
        )}
      </section>

      {/* System Health */}
      <section>
        <h2 className="text-lg font-semibold text-gray-900 mb-3">System Health</h2>
        {systemHealthError ? (
          <PlatformErrorState message={systemHealthError} onRetry={fetchSystemHealth} />
        ) : systemHealthLoading ? (
          <div className="rounded-lg border border-gray-200 bg-white p-4">
            <Skeleton className="mb-2 h-4 w-24" />
            <Skeleton className="h-8 w-20" />
          </div>
        ) : systemHealth ? (
          <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
            <div className="flex items-center gap-3">
              <span className="text-sm font-medium text-gray-500">Overall Status</span>
              <PlatformStatusBadge status={systemHealth.overall_status} />
            </div>
            <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
              {([
                ['API', systemHealth.api_status],
                ['Database', systemHealth.database_status],
                ['Queue', systemHealth.queue_status],
                ['CPU', systemHealth.cpu_status],
                ['Memory', systemHealth.memory_status],
                ['Disk', systemHealth.disk_status],
              ] as const).map(([label, status]) => (
                <div key={label} className="text-center">
                  <p className="text-xs text-gray-500">{label}</p>
                  {status ? (
                    <PlatformStatusBadge status={status} />
                  ) : (
                    <span className="inline-flex items-center rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-gray-400">
                      N/A
                    </span>
                  )}
                </div>
              ))}
            </div>
            {systemHealth.error_rate !== null && (
              <p className="mt-3 text-xs text-gray-500">
                Error rate: {(systemHealth.error_rate * 100).toFixed(1)}% ·
                Slow requests: {systemHealth.slow_request_count ?? 'N/A'}
              </p>
            )}
          </div>
        ) : null}
      </section>
    </div>
  );
}
