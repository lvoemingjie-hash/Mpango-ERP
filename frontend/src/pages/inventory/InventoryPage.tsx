import { useEffect, useState, useCallback } from 'react';
import { inventoryService } from '@/services/inventoryService';
import { Badge } from '@/components/ui/Badge';
import type { StockView } from '@/types/inventory';

import { PageHeader } from '@/components/layout/PageHeader';
import { EmptyState } from '@/components/ui/EmptyState';
import { InventoryAdjustModal, type AdjustFormData } from './InventoryAdjustModal';
import { useAuthStore } from '@/stores/authStore';
import { useToastStore } from '@/stores/toastStore';
import { Link } from 'react-router-dom';
import { CardGridSkeleton } from '@/components/skeletons/CardGridSkeleton';
import { CubeIcon, ExclamationTriangleIcon } from '@heroicons/react/24/outline';

export function InventoryPage() {
  const user = useAuthStore((s) => s.user);
  const [stocks, setStocks] = useState<StockView[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Modal state
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedSkuCode, setSelectedSkuCode] = useState<string>('');

  const hasUpdatePermission = user?.permissions.includes('inventory:update') || user?.roles.includes('admin');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await inventoryService.getStocks(1, 50);
      setStocks(res.data.data.items);
    } catch {
      setError('Could not load stock levels. Check your connection and try again. If the problem persists, contact support.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleAdjustSubmit = async (data: AdjustFormData) => {
    await inventoryService.adjustStock(data);
    useToastStore.getState().addToast({
      type: 'success',
      title: 'Stock Adjusted',
      message: `Successfully adjusted stock for ${data.sku_code}.`,
    });
    await load();
  };

  const openAdjustModal = (skuCode: string) => {
    setSelectedSkuCode(skuCode);
    setIsModalOpen(true);
  };

  return (
    <div>
      <PageHeader
        title="Stock"
        description={loading ? 'Loading stock...' : `${stocks.length} SKU${stocks.length !== 1 ? 's' : ''} in stock`}
        action={
          <div className="flex gap-2">
            <Link to="/inventory/logs" className="btn-secondary text-sm">
              View Logs
            </Link>
            <button onClick={load} disabled={loading} className="btn-secondary text-sm">
              Refresh
            </button>
          </div>
        }
      />

      {loading && <CardGridSkeleton />}
      {error && (
        <div className="mt-6 flex items-center gap-3 rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">
          <span>{error}</span>
          <button
            onClick={load}
            className="inline-flex items-center gap-1 rounded-md bg-red-100 px-2 py-1 text-xs font-medium text-red-800 hover:bg-red-200"
          >
            Retry
          </button>
        </div>
      )}

      {!loading && !error && stocks.length === 0 && (
        <EmptyState
          icon={CubeIcon}
          title="No stock yet"
          description="Your warehouse is empty. Add products first, then stock levels will appear here as you create orders or adjust inventory."
          action={
            <Link to="/skus" className="btn-primary text-sm">
              Go to Products
            </Link>
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

              {hasUpdatePermission && (
                <div className="mt-4 border-t border-gray-100 pt-3 flex justify-end">
                  <button
                    onClick={() => openAdjustModal(s.sku_code)}
                    className="text-sm font-medium text-primary-600 hover:text-primary-800"
                  >
                    Adjust Stock
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <InventoryAdjustModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSubmit={handleAdjustSubmit}
        initialSkuCode={selectedSkuCode}
      />
    </div>
  );
}
