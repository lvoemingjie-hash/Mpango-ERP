/**
 * PlatformRegistryPage -- read-only P17 platform tenant registry.
 *
 * Renders the P17 PlatformTenantRegistryList from /platform/p17/registry.
 *
 * Display contract (P17-A):
 *   - unknown != healthy / active: lifecycle 'unknown' and source_status
 *     'unavailable'/'unknown' render gray, never green.
 *   - null != 0 / false: nullable counts/statuses render "N/A", never "0".
 *   - unavailable_reason / flags_unavailable_reason always surfaced.
 *   - No mutation controls (no pause/resume/suspend/re-provision/retry/backup).
 *   - No tenant business fields; no credentials/DSN/host/port.
 */
import { useEffect, useState } from 'react';
import { platformService, unwrapApiResponse } from '@/services/platformApi';
import { Skeleton } from '@/components/ui/Skeleton';
import type {
  LifecycleState,
  PlatformTenantRegistry,
  PlatformTenantRegistryList,
  RegistrySourceStatus,
} from '@/types/platformRegistry';
import {
  displayNullableBool,
  displayRegistryCount,
  lifecycleStateLabel,
  lifecycleStateTone,
  sourceStatusTone,
} from '@/types/platformRegistry';

const TONE_CLASS: Record<'green' | 'amber' | 'red' | 'gray', string> = {
  green: 'bg-green-100 text-green-800',
  amber: 'bg-yellow-100 text-yellow-800',
  red: 'bg-red-100 text-red-800',
  gray: 'bg-gray-100 text-gray-600',
};

function LifecycleBadge({ state }: { state: LifecycleState | null | undefined }) {
  const tone = lifecycleStateTone(state);
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${TONE_CLASS[tone]}`}
      data-testid="lifecycle-badge"
      title={state === 'unknown' || state == null ? 'Lifecycle state could not be determined' : undefined}
    >
      {lifecycleStateLabel(state)}
    </span>
  );
}

function SourceBadge({ status }: { status: RegistrySourceStatus | null | undefined }) {
  const tone = sourceStatusTone(status);
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${TONE_CLASS[tone]}`}
      data-testid="source-badge"
      title={tone === 'gray' ? 'Source unavailable or unknown' : undefined}
    >
      {status ?? 'unknown'}
    </span>
  );
}

function activeFlags(flags: PlatformTenantRegistry['operational_flags']): string[] {
  const active: string[] = [];
  if (flags.support_mode_active) active.push('support_mode');
  if (flags.incident_active) active.push('incident');
  if (flags.login_paused) active.push('login_paused');
  if (flags.writes_paused) active.push('writes_paused');
  if (flags.billing_hold) active.push('billing_hold');
  if (flags.backup_attention_required) active.push('backup_attention');
  if (flags.migration_attention_required) active.push('migration_attention');
  if (flags.quota_attention_required) active.push('quota_attention');
  return active;
}

export function PlatformRegistryPage() {
  const [data, setData] = useState<PlatformTenantRegistryList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchRegistry = () => {
    setLoading(true);
    setError(null);
    platformService
      .listTenantRegistry()
      .then((res) => setData(unwrapApiResponse<PlatformTenantRegistryList>(res)))
      .catch((err) => setError(err.message ?? 'Failed to load platform registry'))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchRegistry();
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Platform Registry</h1>
        <p className="mt-1 text-sm text-gray-500">
          Read-only tenant registry. No mutation controls.
        </p>
      </div>

      {error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4">
          <p className="text-sm text-red-700" data-testid="registry-error">
            {error}
          </p>
          <p className="mt-1 text-xs text-red-500">
            Registry reads are read-only; reload the page to retry.
          </p>
        </div>
      ) : loading ? (
        <div className="space-y-4">
          <Skeleton className="h-10 w-48" />
          <Skeleton className="h-40 w-full rounded-lg" />
        </div>
      ) : data ? (
        <>
          {/* Registry-level availability */}
          <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
            <div className="flex flex-wrap items-center gap-3">
              <SourceBadge status={data.registry_source_status} />
              <span className="text-sm text-gray-600" data-testid="registry-source-status">
                {data.registry_source_status ?? 'unknown'}
              </span>
              <span className="text-sm text-gray-500">
                {displayRegistryCount(data.total)} tenant(s)
              </span>
            </div>
            {data.unavailable_reason ? (
              <p className="mt-2 text-sm text-amber-700" data-testid="unavailable-reason">
                Unavailable reason: {data.unavailable_reason}
              </p>
            ) : null}
          </div>

          {/* Tenant registry table */}
          <section>
            <h2 className="text-lg font-semibold text-gray-900 mb-3">Tenants</h2>
            {data.items.length === 0 ? (
              <div className="rounded-lg border border-gray-200 bg-gray-50 p-6 text-center">
                <p className="text-sm text-gray-400">No tenants in the registry</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Tenant</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Lifecycle</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Operational flags</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Provisioning</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Backup</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Source</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200 bg-white">
                    {data.items.map((t) => {
                      const flags = t.operational_flags;
                      const af = activeFlags(flags);
                      const prov = t.provisioning_status;
                      const backup = t.backup_status;
                      return (
                        <tr key={t.tenant_id} data-testid="registry-row">
                          <td className="px-4 py-3 text-sm text-gray-900">
                            <div className="font-medium">{t.tenant_name ?? 'Unnamed'}</div>
                            <div className="font-mono text-xs text-gray-400">{t.tenant_id}</div>
                          </td>
                          <td className="px-4 py-3 text-sm">
                            <LifecycleBadge state={t.lifecycle_state.state} />
                            {t.lifecycle_state.state_source_status !== 'available' ? (
                              <div className="mt-1 text-xs text-gray-400">source: {t.lifecycle_state.state_source_status}</div>
                            ) : null}
                          </td>
                          <td className="px-4 py-3 text-sm text-gray-900">
                            {af.length === 0 ? (
                              <span className="text-gray-500">No active flags</span>
                            ) : (
                              <span className="text-gray-900">{af.join(', ')}</span>
                            )}
                            {flags.flags_source_status !== 'available' ? (
                              <div className="mt-1 text-xs text-gray-400">
                                flags source: {flags.flags_source_status}
                                {flags.flags_unavailable_reason ? ` - ${flags.flags_unavailable_reason}` : ''}
                              </div>
                            ) : null}
                          </td>
                          <td className="px-4 py-3 text-sm text-gray-900">
                            {prov == null ? (
                              <span className="text-gray-400">N/A</span>
                            ) : (
                              <span>schema: {prov.schema_status ?? 'N/A'}</span>
                            )}
                          </td>
                          <td className="px-4 py-3 text-sm text-gray-900">
                            {backup == null ? (
                              <span className="text-gray-400">N/A</span>
                            ) : (
                              <span>
                                {backup.last_backup_status ?? 'N/A'}
                                {backup.export_available != null
                                  ? ` - export: ${displayNullableBool(backup.export_available)}`
                                  : ''}
                              </span>
                            )}
                          </td>
                          <td className="px-4 py-3 text-sm">
                            <SourceBadge status={t.registry_source_status} />
                          </td>
                        </tr>
                      );
                    })}
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
