import { useEffect, useState, useCallback } from 'react';
import { skuService, type SKU } from '@/services/skuService';
import { PageHeader } from '@/components/layout/PageHeader';
import { TableSkeleton } from '@/components/skeletons/TableSkeleton';
import { useAuthStore } from '@/stores/authStore';
import { PlusIcon, CubeIcon, ArrowUpTrayIcon, ClipboardDocumentListIcon, CameraIcon } from '@heroicons/react/24/outline';
import { EmptyState } from '@/components/ui/EmptyState';
import { SKUFormModal } from './SKUFormModal';
import { SKUImportModal } from './SKUImportModal';
import { can, canAny, INTAKE_PERMISSIONS } from '@/utils/permissions';
import { SKU_PERMISSIONS } from '@/utils/permissions';

export function SKUListPage() {
  const [skus, setSkus] = useState<SKU[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Modal state
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isImportOpen, setIsImportOpen] = useState(false);
  const [selectedSku, setSelectedSku] = useState<SKU | null>(null);

  const user = useAuthStore((s) => s.user);

  // U4-A: Fixed product gates -- previously checked 'inventory:write' (wrong
  // domain). Products require 'skus:create' (Add) and 'skus:update' (Edit).
  // Import requires 'skus:import'. Admin role bypasses all checks via can().
  const canCreate = can(user, SKU_PERMISSIONS.CREATE);
  const canUpdate = can(user, SKU_PERMISSIONS.UPDATE);
  const canImport = can(user, SKU_PERMISSIONS.IMPORT);
  const canUseIntake = canAny(user, [INTAKE_PERMISSIONS.CREATE, INTAKE_PERMISSIONS.UPDATE]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await skuService.getAll(1, 100);
      setSkus(res.data.data.items);
    } catch {
      setError('Could not load your product catalog. Check your connection and try again. If the problem persists, contact support.');
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
          (canCreate || canImport || canUseIntake) && (
            <div className="flex items-center gap-2">
              {canCreate && (
                <button onClick={handleCreate} className="btn-primary flex items-center gap-2">
                  <PlusIcon className="h-5 w-5" />
                  Add Product
                </button>
              )}
              {canImport && (
                <button
                  onClick={() => setIsImportOpen(true)}
                  className="btn-secondary flex items-center gap-2"
                >
                  <ArrowUpTrayIcon className="h-5 w-5" />
                  Import Products
                </button>
              )}
              {canUseIntake && (
                <a href="/skus/intake" className="btn-secondary flex items-center gap-2">
                  <ClipboardDocumentListIcon className="h-5 w-5" />
                  Data Intake
                </a>
              )}
              {canUseIntake && (
                <a href="/skus/scan" className="btn-secondary flex items-center gap-2">
                  <CameraIcon className="h-5 w-5" />
                  Mobile Scan
                </a>
              )}
            </div>
          )
        }
      />

      {loading && <TableSkeleton />}

      {error && (
        <div className="mt-6 rounded-md bg-red-50 p-4">
          <div className="flex items-center justify-between">
            <div className="text-sm text-red-700">{error}</div>
            <button
              onClick={load}
              className="rounded-md bg-red-100 px-3 py-1 text-xs font-medium text-red-800 hover:bg-red-200"
            >
              Retry
            </button>
          </div>
        </div>
      )}

      {!loading && !error && skus.length === 0 && (
        <EmptyState
          icon={CubeIcon}
          title="No products yet"
          description="Your product catalog is empty. Add your first product to start selling, or import products from a spreadsheet."
          action={
            <div className="mt-4 flex flex-col items-center gap-3 sm:flex-row">
              {canCreate && (
                <button onClick={handleCreate} className="btn-primary">
                  Add Product
                </button>
              )}
              {canImport && (
                <button
                  onClick={() => setIsImportOpen(true)}
                  className="btn-secondary flex items-center gap-2"
                >
                  <ArrowUpTrayIcon className="h-4 w-4" />
                  Import Products
                </button>
              )}
              {canUseIntake && (
                <a href="/skus/intake" className="btn-secondary flex items-center gap-2">
                  <ClipboardDocumentListIcon className="h-4 w-4" />
                  Data Intake
                </a>
              )}
            </div>
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
                {canUpdate && (
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
                    {sku.category || '--'}
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
                  {canUpdate && (
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

      <SKUImportModal
        isOpen={isImportOpen}
        onClose={() => setIsImportOpen(false)}
        onSuccess={load}
      />
    </div>
  );
}
