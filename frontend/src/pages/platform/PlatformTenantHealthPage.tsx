/**
 * PlatformTenantHealthPage — read-only tenant health detail view.
 *
 * Shows tenant health profile with activity counters, errors, slow routes,
 * failed jobs. Uses fixtures and degraded/unknown states from P10 contracts.
 * Unknown != healthy; null != zero; display N/A where needed.
 * No mutation paths.
 */
import { useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { usePlatformStore } from '@/stores/platformStore';
import { platformService, unwrapApiResponse } from '@/services/platformApi';
import { PlatformStatusBadge } from '@/components/platform/PlatformStatusBadge';
import { PlatformMetricCard } from '@/components/platform/PlatformMetricCard';
import { PlatformErrorState } from '@/components/platform/PlatformErrorState';
import { PlatformUnknownState } from '@/components/platform/PlatformUnknownState';
import { displayTimestamp, type PlatformTenantHealth } from '@/types/platform';
import { Skeleton } from '@/components/ui/Skeleton';

export function PlatformTenantHealthPage() {
  const { tenantId } = useParams<{ tenantId: string }>();
  const {
    selectedTenantHealth,
    tenantHealthLoading,
    tenantHealthError,
    setTenantHealth,
    setTenantHealthLoading,
    setTenantHealthError,
  } = usePlatformStore();

  const fetchHealth = () => {
    if (!tenantId) return;
    setTenantHealthLoading(true);
    setTenantHealthError(null);
    platformService
      .getTenantHealth(tenantId)
      .then((res) => {
        const data = unwrapApiResponse<PlatformTenantHealth>(res);
        setTenantHealth(data);
      })
      .catch((err) => setTenantHealthError(err.message ?? 'Failed to load tenant health'));
  };

  useEffect(() => {
    fetchHealth();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId]);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link to="/platform/tenants" className="text-sm text-gray-500 hover:text-gray-700">
          ← Tenants
        </Link>
      </div>

      {tenantHealthError ? (
        <PlatformErrorState message={tenantHealthError} onRetry={fetchHealth} />
      ) : tenantHealthLoading ? (
        <div className="space-y-4">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-4 w-32" />
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="rounded-lg border border-gray-200 bg-white p-4">
                <Skeleton className="mb-2 h-4 w-20" />
                <Skeleton className="h-8 w-16" />
              </div>
            ))}
          </div>
        </div>
      ) : selectedTenantHealth ? (
        <>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Tenant Health</h1>
            <div className="mt-2 flex items-center gap-3">
              <span className="text-sm text-gray-500">
                Schema: {selectedTenantHealth.tenant_schema ?? 'N/A'}
              </span>
              <PlatformStatusBadge status={selectedTenantHealth.health_status} />
            </div>
          </div>

          {/* Schema Status */}
          {selectedTenantHealth.schema_status && (
            <div className="flex items-center gap-2 text-sm">
              <span className="text-gray-500">Schema status:</span>
              <span className="font-medium">{selectedTenantHealth.schema_status}</span>
            </div>
          )}

          {/* Metrics */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <PlatformMetricCard
              label="Last Login"
              value={null}
            >
              <p className="mt-1 text-sm text-gray-600">
                {displayTimestamp(selectedTenantHealth.last_login_at)}
              </p>
            </PlatformMetricCard>
            <PlatformMetricCard
              label="Last Health Check"
              value={null}
            >
              <p className="mt-1 text-sm text-gray-600">
                {displayTimestamp(selectedTenantHealth.last_health_check_at)}
              </p>
            </PlatformMetricCard>
          </div>

          {/* Activity Counters */}
          <section>
            <h2 className="text-lg font-semibold text-gray-900 mb-3">Activity Counters</h2>
            {selectedTenantHealth.activity_counters ? (
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
                {Object.entries(selectedTenantHealth.activity_counters).map(([key, value]) => (
                  <PlatformMetricCard key={key} label={key.replace(/_/g, ' ')} value={value} />
                ))}
              </div>
            ) : (
              <PlatformUnknownState message="Activity counters unavailable" />
            )}
          </section>

          {/* Recent Errors */}
          <section>
            <h2 className="text-lg font-semibold text-gray-900 mb-3">Recent Errors</h2>
            {selectedTenantHealth.recent_errors === null ? (
              <PlatformUnknownState message="Error telemetry unavailable" />
            ) : selectedTenantHealth.recent_errors.length === 0 ? (
              <p className="text-sm text-gray-500">No recent errors.</p>
            ) : (
              <div className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-2 text-left text-xs font-medium uppercase text-gray-500">Error Class</th>
                      <th className="px-4 py-2 text-left text-xs font-medium uppercase text-gray-500">Count</th>
                      <th className="px-4 py-2 text-left text-xs font-medium uppercase text-gray-500">Correlation IDs</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedTenantHealth.recent_errors.map((err, i) => (
                      <tr key={i} className="border-t border-gray-100">
                        <td className="px-4 py-2 text-sm text-gray-900">{err.error_class}</td>
                        <td className="px-4 py-2 text-sm text-gray-600">{err.count}</td>
                        <td className="px-4 py-2 text-sm text-gray-500 font-mono text-xs">
                          {err.correlation_ids.join(', ')}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {/* Slow Routes */}
          <section>
            <h2 className="text-lg font-semibold text-gray-900 mb-3">Slow Routes</h2>
            {selectedTenantHealth.slow_routes === null ? (
              <PlatformUnknownState message="Route telemetry unavailable" />
            ) : selectedTenantHealth.slow_routes.length === 0 ? (
              <p className="text-sm text-gray-500">No slow routes detected.</p>
            ) : (
              <div className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-2 text-left text-xs font-medium uppercase text-gray-500">Route</th>
                      <th className="px-4 py-2 text-left text-xs font-medium uppercase text-gray-500">Latency (ms)</th>
                      <th className="px-4 py-2 text-left text-xs font-medium uppercase text-gray-500">Count</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedTenantHealth.slow_routes.map((route, i) => (
                      <tr key={i} className="border-t border-gray-100">
                        <td className="px-4 py-2 text-sm text-gray-900">{route.route}</td>
                        <td className="px-4 py-2 text-sm text-gray-600">{route.latency_bucket_ms}</td>
                        <td className="px-4 py-2 text-sm text-gray-600">{route.count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {/* Failed Jobs */}
          <section>
            <h2 className="text-lg font-semibold text-gray-900 mb-3">Failed Jobs</h2>
            {selectedTenantHealth.failed_jobs === null ? (
              <PlatformUnknownState message="Job telemetry unavailable" />
            ) : selectedTenantHealth.failed_jobs.length === 0 ? (
              <p className="text-sm text-gray-500">No failed jobs.</p>
            ) : (
              <div className="space-y-2">
                {selectedTenantHealth.failed_jobs.map((job, i) => (
                  <div key={i} className="flex items-center justify-between rounded-lg border border-gray-200 bg-white p-3">
                    <span className="text-sm text-gray-900">{job.job_class}</span>
                    <span className="text-sm font-medium text-red-600">{job.count} failures</span>
                  </div>
                ))}
              </div>
            )}
          </section>
        </>
      ) : null}
    </div>
  );
}
