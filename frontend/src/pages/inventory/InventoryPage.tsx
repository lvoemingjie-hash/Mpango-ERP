import { useEffect, useState, useCallback } from 'react';
import { inventoryService } from '@/services/inventoryService';
import { Badge } from '@/components/ui/Badge';
import type { StockView } from '@/types/inventory';

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
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Inventory</h1>
          <p className="mt-1 text-sm text-gray-500">
            {stocks.length} SKU{stocks.length !== 1 ? 's' : ''} in stock
          </p>
        </div>
        <button onClick={load} disabled={loading} className="btn-secondary text-sm">
          Refresh
        </button>
      </div>

      {loading && <p className="mt-6 text-sm text-gray-400">Loading inventory…</p>}
      {error && <p className="mt-6 text-sm text-red-600">{error}</p>}

      {!loading && !error && (
        <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {stocks.map((s) => (
            <div
              key={s.sku_id}
              className="rounded-lg border border-gray-200 bg-white p-4"
            >
              <div className="flex items-start justify-between">
                <div>
                  <p className="font-semibold text-gray-900">{s.sku_name}</p>
                  <p className="text-xs font-mono text-gray-500">{s.sku_code}</p>
                </div>
                <Badge variant={s.quantity_available > 0 ? 'green' : 'red'}>
                  {s.quantity_available > 0 ? 'In Stock' : 'Out of Stock'}
                </Badge>
              </div>
              <dl className="mt-3 grid grid-cols-3 gap-2 text-sm">
                <div>
                  <dt className="text-xs text-gray-400">On Hand</dt>
                  <dd className="font-medium text-gray-900">{s.quantity_on_hand}</dd>
                </div>
                <div>
                  <dt className="text-xs text-gray-400">Reserved</dt>
                  <dd className="font-medium text-gray-900">{s.quantity_reserved}</dd>
                </div>
                <div>
                  <dt className="text-xs text-gray-400">Available</dt>
                  <dd className="font-bold text-primary-700">{s.quantity_available}</dd>
                </div>
              </dl>
            </div>
          ))}
          {stocks.length === 0 && (
            <p className="col-span-full text-center text-gray-400 py-8">
              No inventory data found. Run the seed script first.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
