/**
 * SupportBundleCard -- P12-C2 bundle generation and read-only preview.
 *
 * Provides:
 *   - Bundle type selector (full / technical / summary)
 *   - Generate Bundle button
 *   - Read-only bundle metadata display
 *   - Diagnostics list from generated bundle
 *
 * Boundaries:
 *   - Read-only display only -- no download/export controls.
 *   - No impersonation, no business data editing.
 */
import { useState, useCallback } from 'react';
import { supportService } from '@/services/supportApi';
import { displayTimestamp } from '@/types/platform';
import type { SupportBundle, BundleType, SupportDiagnosticItem, DiagnosticSourceStatus } from '@/types/support';

const BUNDLE_TYPES: { value: BundleType; label: string }[] = [
  { value: 'full', label: 'Full' },
  { value: 'technical', label: 'Technical' },
  { value: 'summary', label: 'Summary' },
];

/** Inline status badge matching SupportDiagnosticsPanel pattern. */
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
    >
      {status}
    </span>
  );
}

function categoryLabel(category: string): string {
  return category
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

function renderValue(value: unknown): string {
  if (value === null || value === undefined) return 'N/A';
  if (typeof value === 'object') {
    const s = JSON.stringify(value);
    return s.length > 200 ? s.slice(0, 200) + '...' : s;
  }
  return String(value);
}

interface SupportBundleCardProps {
  sessionId: string;
}

export function SupportBundleCard({ sessionId }: SupportBundleCardProps) {
  const [bundle, setBundle] = useState<SupportBundle | null>(null);
  const [bundleType, setBundleType] = useState<BundleType>('full');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleGenerate = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await supportService.createBundle(sessionId, { bundle_type: bundleType });
      setBundle(response.data);
    } catch {
      setError('Failed to generate support bundle.');
    } finally {
      setLoading(false);
    }
  }, [sessionId, bundleType]);

  // Group bundle diagnostics by category
  const grouped = bundle
    ? bundle.diagnostics.reduce<Record<string, SupportDiagnosticItem[]>>((acc, item) => {
        const cat = item.category;
        if (!acc[cat]) acc[cat] = [];
        acc[cat].push(item);
        return acc;
      }, {})
    : {};

  return (
    <div data-testid="bundle-card" className="space-y-4">
      {/* Bundle type selector + generate button */}
      <div className="flex items-end gap-3">
        <div>
          <label htmlFor="bundle-type" className="block text-sm font-medium text-gray-700">
            Bundle Type
          </label>
          <select
            id="bundle-type"
            value={bundleType}
            onChange={(e) => setBundleType(e.target.value as BundleType)}
            className="mt-1 block rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:ring-blue-500"
            data-testid="bundle-type-select"
          >
            {BUNDLE_TYPES.map((bt) => (
              <option key={bt.value} value={bt.value}>
                {bt.label}
              </option>
            ))}
          </select>
        </div>
        <button
          type="button"
          onClick={handleGenerate}
          disabled={loading}
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
          data-testid="generate-bundle-btn"
        >
          {loading ? 'Generating...' : 'Generate Bundle'}
        </button>
      </div>

      {/* Error display */}
      {error && (
        <div className="rounded-md bg-red-50 p-3" data-testid="bundle-error">
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {/* Bundle metadata */}
      {bundle && (
        <div data-testid="bundle-metadata" className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
          <h3 className="mb-3 text-base font-semibold text-gray-900">Support Bundle</h3>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
            <dt className="text-gray-500">Bundle ID</dt>
            <dd className="text-gray-900">{bundle.bundle_id.slice(0, 8)}...</dd>
            <dt className="text-gray-500">Type</dt>
            <dd className="text-gray-900">{bundle.bundle_type}</dd>
            <dt className="text-gray-500">Generated</dt>
            <dd className="text-gray-900">{displayTimestamp(bundle.generated_at)}</dd>
            <dt className="text-gray-500">Redacted</dt>
            <dd className="text-gray-900">{bundle.redaction_applied ? 'Yes' : 'No'}</dd>
            <dt className="text-gray-500">Diagnostics</dt>
            <dd className="text-gray-900" data-testid="bundle-diagnostics-count">
              {bundle.diagnostics.length} item{bundle.diagnostics.length !== 1 ? 's' : ''}
            </dd>
          </dl>
        </div>
      )}

      {/* Bundle diagnostics */}
      {bundle && bundle.diagnostics.length > 0 && (
        <div data-testid="bundle-diagnostics" className="space-y-4">
          {Object.entries(grouped).map(([cat, items]) => (
            <section key={cat}>
              <h4 className="mb-2 text-sm font-semibold text-gray-800">{categoryLabel(cat)}</h4>
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
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
