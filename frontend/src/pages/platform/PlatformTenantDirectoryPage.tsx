/**
 * PlatformTenantDirectoryPage — read-only tenant directory view.
 *
 * Lists all tenants with health badges, status, user count.
 * Uses P10 contracts. Unknown != healthy; null != zero.
 * No write actions. No business data display.
 */
import { useEffect } from 'react';
import { BuildingOfficeIcon } from '@heroicons/react/24/outline';
import { usePlatformStore } from '@/stores/platformStore';
import { platformService } from '@/services/platformApi';
import { PlatformTenantCard } from '@/components/platform/PlatformTenantCard';
import { PlatformErrorState } from '@/components/platform/PlatformErrorState';
import { EmptyState } from '@/components/ui/EmptyState';
import { Skeleton } from '@/components/ui/Skeleton';

export function PlatformTenantDirectoryPage() {
  const {
    tenants,
    tenantsTotal,
    tenantsLoading,
    tenantsError,
    setTenants,
    setTenantsLoading,
    setTenantsError,
  } = usePlatformStore();

  const fetchTenants = () => {
    setTenantsLoading(true);
    setTenantsError(null);
    platformService
      .listTenants(200, 0)
      .then((res) => {
        const data = res.data?.data ?? res.data;
        setTenants(data.items ?? [], data.total ?? 0);
      })
      .catch((err) => setTenantsError(err.message ?? 'Failed to load tenants'));
  };

  useEffect(() => {
    fetchTenants();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Tenant Directory</h1>
        <p className="mt-1 text-sm text-gray-500">
          Read-only tenant overview. No tenant business data is displayed.
        </p>
      </div>

      {tenantsError ? (
        <PlatformErrorState message={tenantsError} onRetry={fetchTenants} />
      ) : tenantsLoading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="rounded-lg border border-gray-200 bg-white p-4">
              <Skeleton className="mb-2 h-4 w-32" />
              <Skeleton className="mb-1 h-3 w-24" />
              <Skeleton className="h-3 w-20" />
            </div>
          ))}
        </div>
      ) : tenants.length === 0 ? (
        <EmptyState
          icon={BuildingOfficeIcon}
          title="No tenants found"
          description="No tenants are registered in the platform yet."
        />
      ) : (
        <>
          <p className="text-sm text-gray-500">
            Showing {tenants.length} of {tenantsTotal} tenants
          </p>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {tenants.map((tenant) => (
              <PlatformTenantCard
                key={tenant.tenant_id ?? tenant.tenant_schema ?? Math.random()}
                tenant={tenant}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
