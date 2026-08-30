import { useCallback, useEffect, useState } from 'react';
import {
  ArrowUpTrayIcon,
  CameraIcon,
  ClipboardDocumentListIcon,
  CubeIcon,
  PlusIcon,
} from '@heroicons/react/24/outline';

import { PageHeader } from '@/components/layout/PageHeader';
import { TableSkeleton } from '@/components/skeletons/TableSkeleton';
import { EmptyState } from '@/components/ui/EmptyState';
import {
  catalogProductService,
  type CatalogProduct,
  type SellableUnit,
} from '@/services/catalogProductService';
import { useAuthStore } from '@/stores/authStore';
import { can, canAny, INTAKE_PERMISSIONS, SKU_PERMISSIONS } from '@/utils/permissions';

import { AddSellableUnitModal } from './AddSellableUnitModal';
import { SKUFormModal } from './SKUFormModal';
import { SKUImportModal } from './SKUImportModal';

export function SKUListPage() {
  const [products, setProducts] = useState<CatalogProduct[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isProductModalOpen, setIsProductModalOpen] = useState(false);
  const [isImportOpen, setIsImportOpen] = useState(false);
  const [isPackagingOpen, setIsPackagingOpen] = useState(false);
  const [selectedProduct, setSelectedProduct] = useState<CatalogProduct | null>(null);
  const [selectedUnit, setSelectedUnit] = useState<SellableUnit | null>(null);

  const user = useAuthStore((state) => state.user);
  const canCreate = can(user, SKU_PERMISSIONS.CREATE);
  const canUpdate = can(user, SKU_PERMISSIONS.UPDATE);
  const canImport = can(user, SKU_PERMISSIONS.IMPORT);
  const canUseIntake = canAny(user, [INTAKE_PERMISSIONS.CREATE, INTAKE_PERMISSIONS.UPDATE]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await catalogProductService.getAll(1, 100);
      setProducts(response.data.data.items);
    } catch {
      setError('Could not load your product catalog. Check your connection and try again. If the problem persists, contact support.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const createProduct = () => {
    setSelectedProduct(null);
    setIsProductModalOpen(true);
  };

  const editProduct = (product: CatalogProduct) => {
    setSelectedProduct(product);
    setIsProductModalOpen(true);
  };

  const addPackaging = (product: CatalogProduct) => {
    setSelectedProduct(product);
    setSelectedUnit(null);
    setIsPackagingOpen(true);
  };

  const editPackaging = (product: CatalogProduct, unit: SellableUnit) => {
    setSelectedProduct(product);
    setSelectedUnit(unit);
    setIsPackagingOpen(true);
  };

  return (
    <div className="min-w-0">
      <PageHeader
        title="Products (SKUs)"
        description="Manage customer-facing products and their independently stocked packaging options."
        action={
          (canCreate || canImport || canUseIntake) && (
            <div className="flex flex-wrap items-center gap-2">
              {canCreate && (
                <button onClick={createProduct} className="btn-primary flex items-center gap-2">
                  <PlusIcon className="h-5 w-5" />
                  Add Product
                </button>
              )}
              {canImport && (
                <button onClick={() => setIsImportOpen(true)} className="btn-secondary flex items-center gap-2">
                  <ArrowUpTrayIcon className="h-5 w-5" />
                  Import Catalog SKUs
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
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="text-sm text-red-700">{error}</div>
            <button onClick={load} className="rounded-md bg-red-100 px-3 py-1 text-xs font-medium text-red-800 hover:bg-red-200">
              Retry
            </button>
          </div>
        </div>
      )}

      {!loading && !error && products.length === 0 && (
        <EmptyState
          icon={CubeIcon}
          title="No products yet"
          description="Add a product with at least one packaging option, or import catalog records from a spreadsheet."
        />
      )}

      {!loading && !error && products.length > 0 && (
        <div className="mt-6 space-y-4" data-testid="catalog-product-list">
          {products.map((product) => (
            <article key={product.id} className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
              <div className="flex flex-col gap-4 border-b border-gray-100 bg-gray-50/70 p-4 sm:flex-row sm:items-start sm:justify-between sm:p-5">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="break-words text-base font-semibold text-gray-900">{product.name}</h2>
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${product.is_active ? 'bg-green-100 text-green-800' : 'bg-gray-200 text-gray-700'}`}>
                      {product.is_active ? 'Active product' : 'Inactive product'}
                    </span>
                  </div>
                  <p className="mt-1 text-sm text-gray-500">{product.category || 'Uncategorized'}</p>
                  {product.description && <p className="mt-2 break-words text-sm text-gray-600">{product.description}</p>}
                </div>
                <div className="flex flex-wrap gap-3 text-sm font-medium">
                  {canUpdate && <button onClick={() => editProduct(product)} className="text-primary-700">Edit product</button>}
                  {canCreate && <button onClick={() => addPackaging(product)} className="text-primary-700">Add packaging</button>}
                </div>
              </div>

              <div className="p-4 sm:p-5">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500">Packaging options</h3>
                <div className="mt-3 divide-y divide-gray-100 rounded-lg border border-gray-200">
                  {(product.sellable_units ?? []).map((unit) => (
                    <div key={unit.id} className="flex flex-col gap-3 p-3 sm:flex-row sm:items-center sm:justify-between sm:p-4">
                      <div className="grid min-w-0 flex-1 gap-2 sm:grid-cols-3 sm:gap-6">
                        <div className="min-w-0">
                          <p className="text-xs text-gray-500">SKU code</p>
                          <p className="break-all font-mono text-sm font-medium text-gray-900">{unit.sku_code}</p>
                        </div>
                        <div>
                          <p className="text-xs text-gray-500">Pack size</p>
                          <p className="text-sm text-gray-900">{unit.package_quantity} {unit.unit}</p>
                        </div>
                        <div>
                          <p className="text-xs text-gray-500">Availability</p>
                          <p className="text-sm text-gray-900">{unit.is_active ? 'Active' : 'Inactive'}</p>
                        </div>
                      </div>
                      {canUpdate && (
                        <button onClick={() => editPackaging(product, unit)} className="self-start text-sm font-medium text-primary-700 sm:self-center">
                          Edit packaging
                        </button>
                      )}
                    </div>
                  ))}
                  {(product.sellable_units ?? []).length === 0 && (
                    <p className="p-4 text-sm text-gray-500">No packaging options are available for this product.</p>
                  )}
                </div>
              </div>
            </article>
          ))}
        </div>
      )}

      <SKUFormModal
        isOpen={isProductModalOpen}
        onClose={() => setIsProductModalOpen(false)}
        onSuccess={load}
        product={selectedProduct}
      />
      <SKUImportModal isOpen={isImportOpen} onClose={() => setIsImportOpen(false)} onSuccess={load} />
      <AddSellableUnitModal
        isOpen={isPackagingOpen}
        product={selectedProduct}
        sellableUnit={selectedUnit}
        onClose={() => setIsPackagingOpen(false)}
        onSuccess={load}
      />
    </div>
  );
}
