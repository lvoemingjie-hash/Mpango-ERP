import { useEffect, useState, useCallback } from 'react';
import { inventoryService, type MovementLogEntry } from '@/services/inventoryService';
import { PageHeader } from '@/components/layout/PageHeader';
import { TableSkeleton } from '@/components/skeletons/TableSkeleton';
import { EmptyState } from '@/components/ui/EmptyState';
import { Pagination } from '@/components/ui/Pagination';
import { ClipboardDocumentListIcon } from '@heroicons/react/24/outline';

export function InventoryLogPage() {
  const [logs, setLogs] = useState<MovementLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [page, setPage] = useState(1);
  const [size] = useState(20);
  const [total, setTotal] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await inventoryService.getLogs(page, size);
      setLogs(res.data.data.items);
      setTotal(res.data.data.pagination.total);
    } catch {
      setError('Failed to load inventory logs.');
    } finally {
      setLoading(false);
    }
  }, [page, size]);

  useEffect(() => {
    load();
  }, [load]);

  const getMovementColor = (type: string, quantity: number) => {
    if (type === 'deduction' || quantity < 0) return 'text-red-600';
    if (type === 'restock' || quantity > 0) return 'text-green-600';
    return 'text-gray-900';
  };

  return (
    <div>
      <PageHeader
        title="Inventory Logs"
        description="View all stock movements and adjustments."
        action={
          <button onClick={load} disabled={loading} className="btn-secondary text-sm">
            Refresh
          </button>
        }
      />

      {loading && <TableSkeleton />}
      {error && <p className="mt-6 text-sm text-red-600">{error}</p>}

      {!loading && !error && logs.length === 0 && (
        <EmptyState
          icon={ClipboardDocumentListIcon}
          title="No movements yet"
          description="Stock movements will appear here when inventory is adjusted or orders are fulfilled."
        />
      )}

      {!loading && !error && logs.length > 0 && (
        <div className="mt-6 flex flex-col gap-4">
          <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                    Date
                  </th>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                    SKU
                  </th>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                    Type
                  </th>
                  <th scope="col" className="px-6 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
                    Quantity
                  </th>
                  <th scope="col" className="px-6 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
                    Before → After
                  </th>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                    Reason / Ref
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 bg-white">
                {logs.map((log) => (
                  <tr key={log.id} className="hover:bg-gray-50">
                    <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-500">
                      {new Date(log.created_at).toLocaleString()}
                    </td>
                    <td className="whitespace-nowrap px-6 py-4 text-sm font-medium text-gray-900">
                      {log.sku_code || '—'}
                    </td>
                    <td className="whitespace-nowrap px-6 py-4 text-sm">
                      <span className="capitalize text-gray-600">{log.movement_type}</span>
                    </td>
                    <td className={`whitespace-nowrap px-6 py-4 text-sm font-bold text-right ${getMovementColor(log.movement_type, log.quantity)}`}>
                      {log.quantity > 0 ? '+' : ''}{log.quantity}
                    </td>
                    <td className="whitespace-nowrap px-6 py-4 text-sm text-right text-gray-500">
                      {log.quantity_before} → {log.quantity_after}
                    </td>
                    <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-500 truncate max-w-xs">
                      {log.reason || (log.reference_type ? `${log.reference_type}: ${log.reference_id?.slice(0, 8)}` : '—')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <Pagination
            page={page}
            totalPages={Math.ceil(total / size)}
            onPageChange={setPage}
          />
        </div>
      )}
    </div>
  );
}
