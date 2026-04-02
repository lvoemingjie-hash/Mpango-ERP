import { useState, useEffect, useCallback } from 'react';
import { retailerService, type RetailerWithBinding } from '@/services/retailerService';
import { pricingService } from '@/services/pricingService';
import { skuService, type SKU } from '@/services/skuService';
import { useAuthStore } from '@/stores/authStore';
import { normalizeApiError } from '@/utils/errorHandling';
import { useToastStore } from '@/stores/toastStore';
import { PageHeader } from '@/components/layout/PageHeader';
import { TableSkeleton } from '@/components/skeletons/TableSkeleton';
import { CurrencyDollarIcon, PlusIcon, PencilIcon } from '@heroicons/react/24/outline';
import { EmptyState } from '@/components/ui/EmptyState';
import { Pagination } from '@/components/ui/Pagination';
import type { RetailerPriceView } from '@/types/pricing';

export function RetailerPricingPage() {
  const user = useAuthStore((s) => s.user);

  // Data state
  const [retailers, setRetailers] = useState<RetailerWithBinding[]>([]);
  const [prices, setPrices] = useState<RetailerPriceView[]>([]);
  const [loading, setLoading] = useState(true);
  const [pricesLoading, setPricesLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Selection state
  const [retailerId, setRetailerId] = useState<string>('');

  // Pagination
  const [page, setPage] = useState(1);
  const [size] = useState(20);
  const [total, setTotal] = useState(0);

  // Edit/Create Modal State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [skus, setSkus] = useState<SKU[]>([]);
  const [editingPrice, setEditingPrice] = useState<{sku_id: string, sku_code: string, name: string, price: number | ''} | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const hasWritePermission = user?.permissions.includes('pricing:write') || user?.roles.includes('admin');

  // Load Retailers on mount
  useEffect(() => {
    async function loadInitial() {
      setLoading(true);
      try {
        const res = await retailerService.getAll(1, 100);
        setRetailers(res.data.data.items);
      } catch {
        setError('Failed to load customers.');
      } finally {
        setLoading(false);
      }
    }
    loadInitial();
  }, []);

  // Load Prices when retailer or page changes
  const loadPrices = useCallback(async () => {
    if (!retailerId) {
      setPrices([]);
      return;
    }
    setPricesLoading(true);
    setError(null);
    try {
      const res = await pricingService.getPrices(retailerId, page, size);
      setPrices(res.data.data.items);
      setTotal(res.data.data.total);
    } catch {
      setError('Failed to load prices for this customer.');
    } finally {
      setPricesLoading(false);
    }
  }, [retailerId, page, size]);

  useEffect(() => {
    loadPrices();
  }, [loadPrices]);

  const handleOpenAddModal = async () => {
    setIsModalOpen(true);
    setEditingPrice(null);
    if (skus.length === 0) {
      try {
        const res = await skuService.getAll(1, 100, undefined, true);
        setSkus(res.data.data.items);
      } catch {
        // Handle silently
      }
    }
  };

  const handleOpenEditModal = (p: RetailerPriceView) => {
    setIsModalOpen(true);
    setEditingPrice({
      sku_id: p.sku_id,
      sku_code: p.sku_code,
      name: p.sku_name,
      price: p.price
    });
  };

  const handleSavePrice = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingPrice || !editingPrice.sku_id || !editingPrice.price || !retailerId) return;

    setIsSaving(true);
    try {
      await pricingService.setPrice({
        retailer_id: retailerId,
        sku_id: editingPrice.sku_id,
        price: Number(editingPrice.price)
      });

      useToastStore.getState().addToast({
        type: 'success',
        title: 'Price Saved',
        message: 'The customer price has been updated successfully.'
      });

      setIsModalOpen(false);
      loadPrices();
    } catch (err) {
      useToastStore.getState().addToast({
        type: 'error',
        title: 'Failed to save',
        message: normalizeApiError(err)
      });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="Customer Pricing"
        description="Manage specific product prices for each customer."
        action={
          <button
            onClick={handleOpenAddModal}
            disabled={!retailerId || !hasWritePermission}
            className="btn-primary text-sm flex items-center gap-2"
          >
            <PlusIcon className="h-4 w-4" />
            Set New Price
          </button>
        }
      />

      <div className="mt-6 flex flex-col gap-6">
        {/* Retailer Selector */}
        <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
          <label htmlFor="retailer" className="block text-sm font-medium text-gray-700">
            Select Customer
          </label>
          <select
            id="retailer"
            value={retailerId}
            onChange={(e) => {
              setRetailerId(e.target.value);
              setPage(1);
            }}
            className="mt-1 block w-full max-w-md rounded-md border-gray-300 py-2 pl-3 pr-10 text-base focus:border-primary-500 focus:outline-none focus:ring-primary-500 sm:text-sm"
            disabled={loading}
          >
            <option value="">Select a customer to view prices...</option>
            {retailers.map((r) => (
              <option key={r.retailer.id} value={r.retailer.id}>
                {r.retailer.name} {r.retailer.phone ? `(${r.retailer.phone})` : ''}
              </option>
            ))}
          </select>
        </div>

        {/* Error State */}
        {error && (
          <div className="rounded-md bg-red-50 p-4">
            <div className="text-sm text-red-700">{error}</div>
          </div>
        )}

        {/* Main Content Area */}
        {!retailerId ? (
          <EmptyState
            icon={CurrencyDollarIcon}
            title="No customer selected"
            description="Please select a customer from the dropdown above to manage their pricing."
          />
        ) : pricesLoading ? (
          <TableSkeleton />
        ) : prices.length === 0 ? (
          <EmptyState
            icon={CurrencyDollarIcon}
            title="No prices configured"
            description="This customer does not have any custom prices set. They cannot order items without prices."
            action={
              <button
                onClick={handleOpenAddModal}
                disabled={!hasWritePermission}
                className="btn-primary text-sm mt-4"
              >
                Set First Price
              </button>
            }
          />
        ) : (
          <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                    Product
                  </th>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                    SKU Code
                  </th>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                    Price (KES)
                  </th>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                    Last Updated
                  </th>
                  <th scope="col" className="relative px-6 py-3">
                    <span className="sr-only">Edit</span>
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 bg-white">
                {prices.map((p) => (
                  <tr key={p.sku_id} className="hover:bg-gray-50">
                    <td className="whitespace-nowrap px-6 py-4 text-sm font-medium text-gray-900">
                      {p.sku_name}
                    </td>
                    <td className="whitespace-nowrap px-6 py-4 text-sm font-mono text-gray-500">
                      {p.sku_code}
                    </td>
                    <td className="whitespace-nowrap px-6 py-4 text-sm font-medium text-gray-900">
                      {new Intl.NumberFormat('en-KE', { style: 'currency', currency: 'KES' }).format(p.price)}
                    </td>
                    <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-500">
                      {p.updated_at ? new Date(p.updated_at).toLocaleDateString() : '-'}
                    </td>
                    <td className="whitespace-nowrap px-6 py-4 text-right text-sm font-medium">
                      <button
                        onClick={() => handleOpenEditModal(p)}
                        disabled={!hasWritePermission}
                        className="text-primary-600 hover:text-primary-900 flex items-center justify-end gap-1 ml-auto disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        <PencilIcon className="h-4 w-4" />
                        Edit
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {total > size && (
              <Pagination
                page={page}
                totalPages={Math.ceil(total / size)}
                onPageChange={setPage}
              />
            )}
          </div>
        )}
      </div>

      {/* Set/Edit Price Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-md rounded-xl bg-white shadow-xl">
            <div className="border-b border-gray-200 px-6 py-4">
              <h3 className="text-lg font-medium text-gray-900">
                {editingPrice?.sku_id && editingPrice?.name ? `Edit Price: ${editingPrice.name}` : 'Set New Price'}
              </h3>
            </div>

            <form onSubmit={handleSavePrice} className="p-6 space-y-4">
              {/* If creating new, show SKU selector */}
              {!editingPrice?.name && (
                <div>
                  <label htmlFor="sku" className="block text-sm font-medium text-gray-700">
                    Product
                  </label>
                  <select
                    id="sku"
                    required
                    value={editingPrice?.sku_id || ''}
                    onChange={(e) => {
                      const selected = skus.find(s => s.id === e.target.value);
                      if (selected) {
                        setEditingPrice({
                          sku_id: selected.id,
                          sku_code: selected.sku_code,
                          name: selected.name,
                          price: ''
                        });
                      }
                    }}
                    className="mt-1 block w-full rounded-md border-gray-300 py-2 pl-3 pr-10 text-base focus:border-primary-500 focus:outline-none focus:ring-primary-500 sm:text-sm"
                  >
                    <option value="">Select a product...</option>
                    {skus.map(s => (
                      <option key={s.id} value={s.id}>{s.name} ({s.sku_code})</option>
                    ))}
                  </select>
                </div>
              )}

              <div>
                <label htmlFor="price" className="block text-sm font-medium text-gray-700">
                  Price (KES)
                </label>
                <div className="relative mt-1 rounded-md shadow-sm">
                  <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
                    <span className="text-gray-500 sm:text-sm">KES</span>
                  </div>
                  <input
                    type="number"
                    name="price"
                    id="price"
                    required
                    min="0.01"
                    step="0.01"
                    className="block w-full rounded-md border-gray-300 pl-12 focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
                    placeholder="0.00"
                    value={editingPrice?.price || ''}
                    onChange={(e) => setEditingPrice(prev => prev ? { ...prev, price: e.target.value === '' ? '' : Number(e.target.value) } : null)}
                  />
                </div>
              </div>

              <div className="mt-6 flex justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="rounded-md border border-gray-300 bg-white py-2 px-4 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSaving || !editingPrice?.sku_id || !editingPrice?.price}
                  className="inline-flex justify-center rounded-md border border-transparent bg-primary-600 py-2 px-4 text-sm font-medium text-white shadow-sm hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 disabled:opacity-50"
                >
                  {isSaving ? 'Saving...' : 'Save Price'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
