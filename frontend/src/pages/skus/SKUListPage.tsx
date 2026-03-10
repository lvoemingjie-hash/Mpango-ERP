import { useEffect, useState, useCallback } from 'react';
import { skuService, type SKU } from '@/services/skuService';
import { PageHeader } from '@/components/layout/PageHeader';
import { TableSkeleton } from '@/components/skeletons/TableSkeleton';
import { useAuthStore } from '@/stores/authStore';
import { PlusIcon, CubeIcon } from '@heroicons/react/24/outline';
import { EmptyState } from '@/components/ui/EmptyState';
import { SKUFormModal } from './SKUFormModal';

export function SKUListPage() {
  const [skus, setSkus] = useState<SKU[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Modal state
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedSku, setSelectedSku] = useState<SKU | null>(null);

  const user = useAuthStore((s) => s.user);
  const canWrite = user?.permissions.includes('inventory:write') || user?.roles.includes('admin');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await skuService.getAll(1, 100);
      setSkus(res.data.data.items);
    } catch {
      setError('Failed to load products. Please try again.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleEdit = (sku: SKU) => {
    setSelectedSku(sku);
    setIsModalOpen(true);
  };

  const handleCreate = () => {
    setSelectedSku(null);
    setIsModalOpen(true);
  };

  return (
    <div>
      <PageHeader
        title="Products (SKUs)"
        description="Manage your product catalog and SKU codes."
        action={
          canWrite && (
            <button onClick={handleCreate} className="btn-primary flex items-center gap-2">
              <PlusIcon className="h-5 w-5" />
              Add Product
            </button>
          )
        }
      />

      {loading && <TableSkeleton />}

      {error && (
        <div className="mt-6 rounded-md bg-red-50 p-4">
          <div className="text-sm text-red-700">{error}</div>
        </div>
      )}

      {!loading && !error && skus.length === 0 && (
        <EmptyState
          icon={CubeIcon}
          title="No products found"
          description="Get started by creating your first product SKU."
          action={
            canWrite ? (
              <button onClick={handleCreate} className="btn-primary mt-4">
                Add Product
              </button>
            ) : undefined
          }
        />
      )}

      {!loading && !error && skus.length > 0 && (
        <div className="mt-6 overflow-hidden rounded-lg border border-gray-200 bg-white">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  SKU Code
                </th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Product Name
                </th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Category
                </th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Unit
                </th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Status
                </th>
                {canWrite && (
                  <th scope="col" className="px-6 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
                    Actions
                  </th>
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 bg-white">
              {skus.map((sku) => (
                <tr key={sku.id} className="hover:bg-gray-50">
                  <td className="whitespace-nowrap px-6 py-4 text-sm font-medium text-gray-900">
                    {sku.sku_code}
                  </td>
                  <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-900">
                    {sku.name}
                  </td>
                  <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-500">
                    {sku.category || '—'}
                  </td>
                  <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-500">
                    {sku.unit}
                  </td>
                  <td className="whitespace-nowrap px-6 py-4 text-sm">
                    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
                      sku.is_active ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'
                    }`}>
                      {sku.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  {canWrite && (
                    <td className="whitespace-nowrap px-6 py-4 text-right text-sm font-medium">
                      <button
                        onClick={() => handleEdit(sku)}
                        className="text-primary-600 hover:text-primary-900"
                      >
                        Edit
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <SKUFormModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSuccess={load}
        sku={selectedSku}
      />
    </div>
  );
}
