import { useEffect, useState, useCallback } from 'react';
import { inventoryService } from '@/services/inventoryService';
import { Badge } from '@/components/ui/Badge';
import type { StockView } from '@/types/inventory';

import { PageHeader } from '@/components/layout/PageHeader';
import { EmptyState } from '@/components/ui/EmptyState';
import { CardGridSkeleton } from '@/components/skeletons/CardGridSkeleton';
import { CubeIcon, ExclamationTriangleIcon } from '@heroicons/react/24/outline';

export function InventoryPage() {
  const [stocks, setStocks] = useState<StockView[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await inventoryService.getStocks(1, 50);
      setStocks(res.data.data.items);
    } catch {
      setError('Failed to load inventory.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <div>
      <PageHeader
        title="Stock"
        description={loading ? 'Loading stock...' : `${stocks.length} SKU${stocks.length !== 1 ? 's' : ''} in stock`}
        action={
          <button onClick={load} disabled={loading} className="btn-secondary text-sm">
            Refresh
          </button>
        }
      />

      {loading && <CardGridSkeleton />}
      {error && <p className="mt-6 text-sm text-red-600">{error}</p>}

      {!loading && !error && stocks.length === 0 && (
        <EmptyState
          icon={CubeIcon}
          title="Your warehouse is empty."
          description="Add your first product to start tracking inventory."
          action={
            <button className="btn-primary text-sm" disabled title="Coming soon">
              Add First Product
            </button>
          }
        />
      )}

      {!loading && !error && stocks.length > 0 && (
        <div className="mt-6 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {stocks.map((s) => (
            <div
              key={s.sku_id}
              className="relative flex flex-col justify-between rounded-xl border border-gray-200 bg-white p-6 shadow-sm transition-shadow hover:shadow-md"
            >
              <div>
                <div className="mb-4 flex items-start justify-between">
                  <div>
                    <p className="font-semibold text-gray-900">{s.sku_name}</p>
                    <p className="text-xs font-mono text-gray-500">{s.sku_code}</p>
                  </div>
                  <Badge
                    variant={
                      s.quantity_available > 0
                        ? s.quantity_available < 10
                          ? 'yellow'
                          : 'green'
                        : 'red'
                    }
                  >
                    {s.quantity_available > 0
                      ? (s.quantity_available < 10 ? 'Low Stock' : 'In Stock')
                      : 'Out of Stock'}
                  </Badge>
                </div>
              </div>

              <div className="mt-4 flex items-center justify-between border-t border-gray-100 pt-4">
                <div>
                  <p className="text-xs text-gray-500">On Hand</p>
                  <p className="font-medium text-gray-900">{s.quantity_on_hand}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-500">Reserved</p>
                  <p className="font-medium text-gray-900">{s.quantity_reserved}</p>
                </div>
                <div className="text-right">
                  <p className="text-xs text-gray-500">Available</p>
                  <div className="flex items-center justify-end gap-1">
                    <p className={`font-medium ${s.quantity_available < 10 ? 'text-red-600 font-bold' : 'text-gray-900'}`}>
                      {s.quantity_available}
                    </p>
                    {s.quantity_available < 10 && (
                      <ExclamationTriangleIcon className="h-4 w-4 text-red-500" title="Low Stock" />
                    )}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
