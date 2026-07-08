/**
 * SupportDiagnosticsPanel -- P12-C1 read-only diagnostics panel.
 *
 * Displays diagnostic items fetched from the support session, grouped by
 * category, with source status badges and a refresh button.
 *
 * Boundaries:
 *   - Read-only display only -- no mutation/edit/delete controls.
 *   - No impersonation, no business data editing.
 *   - No download/export functionality.
 */
import { useState, useEffect, useCallback } from 'react';
import { supportService } from '@/services/supportApi';
import { displayTimestamp } from '@/types/platform';
import { PlatformErrorState } from '@/components/platform/PlatformErrorState';
import { Skeleton } from '@/components/ui/Skeleton';
import type { SupportDiagnosticItem, DiagnosticSourceStatus } from '@/types/support';

// Canonical category ordering
const CATEGORY_ORDER = [
  'tenant_metadata',
  'health_summary',
  'activity_counters',
  'recent_errors',
  'slow_routes',
  'failed_jobs',
  'system_snapshot',
  'correlation_ids',
  'schema_status',
] as const;

/** Inline status badge for DiagnosticSourceStatus.
 *  Not reusing PlatformStatusBadge because its type union does not cover
 *  available/unavailable -- only healthy/degraded/unhealthy/down/unknown. */
function DiagnosticStatusBadge({ status }: { status: DiagnosticSourceStatus }) {
  const colors: Record<DiagnosticSourceStatus, string> = {
    available: 'bg-green-100 text-green-800',
    degraded: 'bg-yellow-100 text-yellow-800',
    unavailable: 'bg-gray-100 text-gray-600',
    unknown: 'bg-gray-100 text-gray-600',
  };
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${colors[status]}`}
      data-testid={`status-badge-${status}`}
    >
      {status}
    </span>
  );
}

/** Format a category key into a human-readable heading. */
function categoryLabel(category: string): string {
  return category
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

/** Render a diagnostic value safely. */
function renderValue(value: unknown): string {
  if (value === null || value === undefined) return 'N/A';
  if (typeof value === 'object') {
    const s = JSON.stringify(value);
    return s.length > 200 ? s.slice(0, 200) + '...' : s;
  }
  return String(value);
}

interface SupportDiagnosticsPanelProps {
  sessionId: string;
}

export function SupportDiagnosticsPanel({ sessionId }: SupportDiagnosticsPanelProps) {
  const [diagnostics, setDiagnostics] = useState<SupportDiagnosticItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDiagnostics = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await supportService.getDiagnostics(sessionId);
      setDiagnostics(response.data);
    } catch {
      setError('Failed to load diagnostics.');
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    fetchDiagnostics();
  }, [fetchDiagnostics]);

  // Group by category in canonical order
  const grouped = new Map<string, SupportDiagnosticItem[]>();
  for (const cat of CATEGORY_ORDER) {
    grouped.set(cat, []);
  }
  for (const item of diagnostics) {
    const list = grouped.get(item.category);
    if (list) {
      list.push(item);
    } else {
      grouped.set(item.category, [item]);
    }
  }
  // Filter to only categories with items
  const activeCategories = CATEGORY_ORDER.filter(
    (cat) => (grouped.get(cat)?.length ?? 0) > 0,
  );

  if (loading) {
    return (
      <div data-testid="diagnostics-loading" className="space-y-3">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  if (error) {
    return (
      <div data-testid="diagnostics-error">
        <PlatformErrorState message={error} onRetry={fetchDiagnostics} />
      </div>
    );
  }

  return (
    <div data-testid="diagnostics-panel" className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500" data-testid="diagnostics-count">
          {diagnostics.length} diagnostic item{diagnostics.length !== 1 ? 's' : ''}
        </p>
        <button
          type="button"
          onClick={fetchDiagnostics}
          className="rounded-md bg-white px-3 py-1.5 text-sm font-medium text-gray-700 shadow-sm ring-1 ring-inset ring-gray-300 hover:bg-gray-50"
          data-testid="diagnostics-refresh-btn"
        >
          Refresh
        </button>
      </div>

      {diagnostics.length === 0 && (
        <p className="text-sm text-gray-500">No diagnostics available for this session.</p>
      )}

      {activeCategories.map((cat) => {
        const items = grouped.get(cat) ?? [];
        return (
          <section key={cat} data-testid={`diagnostics-category-${cat}`}>
            <h3 className="mb-2 text-base font-semibold text-gray-900">
              {categoryLabel(cat)}
            </h3>
            <div className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-2 text-left text-xs font-medium uppercase text-gray-500">
                      Label
                    </th>
                    <th className="px-4 py-2 text-left text-xs font-medium uppercase text-gray-500">
                      Value
                    </th>
                    <th className="px-4 py-2 text-left text-xs font-medium uppercase text-gray-500">
                      Status
                    </th>
                    <th className="px-4 py-2 text-left text-xs font-medium uppercase text-gray-500">
                      Collected
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {items.map((item) => (
                    <tr key={item.item_id}>
                      <td className="whitespace-nowrap px-4 py-2 text-sm font-medium text-gray-900">
                        {item.label}
                      </td>
                      <td className="max-w-xs truncate px-4 py-2 text-sm text-gray-700">
                        {renderValue(item.value)}
                      </td>
                      <td className="px-4 py-2 text-sm">
                        <DiagnosticStatusBadge status={item.source_status} />
                      </td>
                      <td className="whitespace-nowrap px-4 py-2 text-sm text-gray-500">
                        {displayTimestamp(item.collected_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        );
      })}
    </div>
  );
}
