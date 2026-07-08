/**
 * PlatformTenantCard — displays a single tenant summary in the directory.
 *
 * Shows tenant name, status, health badge, user count, and last activity.
 * Unknown states displayed distinctly from healthy. Null fields show N/A.
 */
import { Link } from 'react-router-dom';
import { PlatformStatusBadge } from './PlatformStatusBadge';
import { displayCount, displayTimestamp } from '@/types/platform';
import type { PlatformTenantSummary } from '@/types/platform';

interface PlatformTenantCardProps {
  tenant: PlatformTenantSummary;
}

export function PlatformTenantCard({ tenant }: PlatformTenantCardProps) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm transition-shadow hover:shadow-md">
      <div className="flex items-start justify-between">
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-sm font-semibold text-gray-900">
            {tenant.tenant_name ?? 'Unknown Tenant'}
          </h3>
          <p className="mt-0.5 text-xs text-gray-500">
            {tenant.tenant_schema ?? 'N/A'}
          </p>
        </div>
        <PlatformStatusBadge status={tenant.health_status} />
      </div>

      <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-gray-600">
        <div>
          <span className="text-gray-400">Status:</span>{' '}
          <span className="font-medium">{tenant.status}</span>
        </div>
        <div>
          <span className="text-gray-400">Tier:</span>{' '}
          <span className="font-medium">{tenant.tier ?? 'N/A'}</span>
        </div>
        <div>
          <span className="text-gray-400">Users:</span>{' '}
          <span
            className="font-medium"
            title={tenant.user_count === null ? 'Data unavailable' : undefined}
          >
            {displayCount(tenant.user_count)}
          </span>
        </div>
        <div>
          <span className="text-gray-400">Errors:</span>{' '}
          <span className="font-medium">{displayCount(tenant.recent_error_count)}</span>
        </div>
        <div className="col-span-2">
          <span className="text-gray-400">Last activity:</span>{' '}
          <span className="font-medium">{displayTimestamp(tenant.last_activity_at)}</span>
        </div>
      </div>

      <div className="mt-3 border-t border-gray-100 pt-2">
        <Link
          to={`/platform/tenants/${tenant.tenant_id ?? ''}/health`}
          className="text-xs font-medium text-primary-600 hover:text-primary-700"
        >
          View health details →
        </Link>
      </div>
    </div>
  );
}
