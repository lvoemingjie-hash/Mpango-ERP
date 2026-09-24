import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { PlusIcon, ShoppingBagIcon, TrashIcon } from '@heroicons/react/24/outline';
import { orderService } from '@/services/orderService';
import { retailerService, type RetailerWithBinding } from '@/services/retailerService';
import { skuService, type SKU } from '@/services/skuService';
import { pricingService } from '@/services/pricingService';
import { inventoryService } from '@/services/inventoryService';
import { useAuthStore } from '@/stores/authStore';
import { normalizeApiError } from '@/utils/errorHandling';
import { PageHeader } from '@/components/layout/PageHeader';
import type { WholesalerOrderItemCreate } from '@/types/order';
import type { RetailerPriceView } from '@/types/pricing';

interface OrderLineItem {
  sellable_unit_id: string;
  sku_code: string;
  name: string;
  quantity: number;
  price?: number | null;
  stock?: number;
}

interface OrderValidationError {
  response?: {
    data?: {
      detail?: {
        errors?: string[];
      };
    };
  };
}

export function CreateOrderPage() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const hasCreatePermission = user?.permissions.includes('orders:create') || user?.roles.includes('admin');

  // Form State
  const [retailerId, setRetailerId] = useState<string>('');
  const [items, setItems] = useState<OrderLineItem[]>([]);
  const [notes, setNotes] = useState('');

  // UI State
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Data State
  const [retailers, setRetailers] = useState<RetailerWithBinding[]>([]);
  const [loadingRetailers, setLoadingRetailers] = useState(true);

  // Picker State
  const [showPicker, setShowPicker] = useState(false);
  const [skus, setSkus] = useState<SKU[]>([]);
  const [prices, setPrices] = useState<Record<string, number>>({});
  const [stocks, setStocks] = useState<Record<string, number>>({});
  const [loadingProducts, setLoadingProducts] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  // 1. Load retailers on mount
  useEffect(() => {
    async function loadRetailers() {
      try {
        const res = await retailerService.getAll(1, 100);
        setRetailers(res.data.data.items);
      } catch (err) {
        setError('Failed to load customers.');
      } finally {
        setLoadingRetailers(false);
      }
    }
    loadRetailers();
  }, []);

  // 2. Load product details when picker opens (dependent on selected retailer)
  const loadProducts = useCallback(async () => {
    if (!retailerId) return;

    setLoadingProducts(true);
    try {
      // Parallel fetch: SKUs, Prices (for this retailer), Stocks
      const [skusRes, pricesRes, stocksRes] = await Promise.all([
        skuService.getAll(1, 50, searchQuery, true), // Only active SKUs
        pricingService.getPrices(retailerId, 1, 100), // Get all prices
        inventoryService.getStocks(1, 100) // Get all stocks
      ]);

      setSkus(skusRes.data.data.items);

      const priceMap: Record<string, number> = {};
      pricesRes.data.data.items.forEach((p: RetailerPriceView) => {
        priceMap[p.sku_code] = p.price;
      });
      setPrices(priceMap);

      const stockMap: Record<string, number> = {};
      stocksRes.data.data.items.forEach((s) => {
        stockMap[s.sku_code] = s.quantity_on_hand;
      });
      setStocks(stockMap);

    } catch {
      // Handle error implicitly
    } finally {
      setLoadingProducts(false);
    }
  }, [retailerId, searchQuery]);

  useEffect(() => {
    if (showPicker && retailerId) {
      loadProducts();
    }
  }, [showPicker, loadProducts, retailerId]);

  // If retailer changes, clear items (prices might be different)
  useEffect(() => {
    setItems([]);
  }, [retailerId]);

  const addProduct = (sku: SKU) => {
    const existing = items.find((i) => i.sellable_unit_id === sku.id);
    if (existing) {
      setItems(items.map((i) =>
        i.sellable_unit_id === sku.id
          ? { ...i, quantity: i.quantity + 1 }
          : i
      ));
    } else {
      setItems([...items, {
        sellable_unit_id: sku.id,
        sku_code: sku.sku_code,
        name: sku.name,
        quantity: 1,
        price: prices[sku.sku_code] || null,
        stock: stocks[sku.sku_code] || 0
      }]);
    }
    setShowPicker(false);
  };

  const updateQuantity = (sellableUnitId: string, quantity: number) => {
    if (quantity <= 0) {
      setItems(items.filter((i) => i.sellable_unit_id !== sellableUnitId));
    } else {
      setItems(items.map((i) =>
        i.sellable_unit_id === sellableUnitId ? { ...i, quantity } : i
      ));
    }
  };

  const removeItem = (sellableUnitId: string) => {
    setItems(items.filter((i) => i.sellable_unit_id !== sellableUnitId));
  };

  const calculateTotal = () => {
    return items.reduce((total, item) => {
      return total + ((item.price || 0) * item.quantity);
    }, 0);
  };

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('en-KE', {
      style: 'currency',
      currency: 'KES',
    }).format(amount);
  };

  const handleSubmit = async () => {
    if (!retailerId || items.length === 0) return;
    setSubmitting(true);
    setError(null);

    try {
      const orderItems: WholesalerOrderItemCreate[] = items.map((i) => ({
        sellable_unit_id: i.sellable_unit_id,
        sku_code: i.sku_code,
        quantity: i.quantity,
      }));

      await orderService.create({
        retailer_id: retailerId,
        items: orderItems,
        notes: notes || null,
      });

      navigate('/orders');
    } catch (err: unknown) {
      // Backend returns accumulated errors in detail.errors
      const validationError = err as OrderValidationError;
      if (validationError.response?.data?.detail?.errors) {
        setError(validationError.response.data.detail.errors.join(' | '));
      } else {
        setError(normalizeApiError(err));
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="Create Order"
        description="Create an order manually on behalf of a customer."
      />

      <div className="mt-6 max-w-3xl space-y-6">
        {error && (
          <div className="rounded-md bg-red-50 p-4">
            <div className="flex">
              <div className="ml-3">
                <h3 className="text-sm font-medium text-red-800">Order Validation Failed</h3>
                <div className="mt-2 text-sm text-red-700">
                  <p>{error}</p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* 1. Retailer Selection */}
        <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
          <h3 className="text-lg font-medium text-gray-900 mb-4">Customer</h3>
          <div>
            <label htmlFor="retailer" className="block text-sm font-medium text-gray-700">
              Select Customer
            </label>
            <select
              id="retailer"
              value={retailerId}
              onChange={(e) => setRetailerId(e.target.value)}
              className="mt-1 block w-full rounded-md border-gray-300 py-2 pl-3 pr-10 text-base focus:border-primary-500 focus:outline-none focus:ring-primary-500 sm:text-sm"
              disabled={loadingRetailers}
            >
              <option value="">Select a customer...</option>
              {retailers.map((r) => (
                <option key={r.retailer.id} value={r.retailer.id}>
                  {r.retailer.name} {r.retailer.phone ? `(${r.retailer.phone})` : ''}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* 2. Order Items */}
        <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-medium text-gray-900">Order Items</h3>
            <button
              type="button"
              onClick={() => setShowPicker(true)}
              disabled={!retailerId}
              className="inline-flex items-center gap-x-1.5 rounded-md bg-primary-50 px-3 py-2 text-sm font-semibold text-primary-600 shadow-sm hover:bg-primary-100 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <PlusIcon className="-ml-0.5 h-5 w-5" aria-hidden="true" />
              Add Product
            </button>
          </div>

          {items.length === 0 ? (
            <p className="text-sm text-gray-500 text-center py-4 border-2 border-dashed border-gray-200 rounded-lg">
              {retailerId ? 'Click "Add Product" to start building the order.' : 'Select a customer first to add products.'}
            </p>
          ) : (
            <ul className="divide-y divide-gray-200">
              {items.map((item) => (
                <li key={item.sellable_unit_id} className="flex py-4">
                  <div className="ml-3 flex flex-1 flex-col">
                    <div>
                      <div className="flex justify-between text-base font-medium text-gray-900">
                        <h3>{item.name}</h3>
                        <p className="ml-4">
                          {item.price ? formatCurrency(item.price * item.quantity) : <span className="text-red-500 text-sm">No Price</span>}
                        </p>
                      </div>
                      <p className="mt-1 text-sm text-gray-500 font-mono">{item.sku_code}</p>
                    </div>
                    <div className="flex flex-1 items-end justify-between text-sm">
                      <div className="flex items-center gap-3">
                        <div className="flex items-center rounded-md border border-gray-300">
                          <button
                            type="button"
                            className="px-2 py-1 text-gray-600 hover:bg-gray-50 rounded-l-md"
                            onClick={() => updateQuantity(item.sellable_unit_id, item.quantity - 1)}
                          >-</button>
                          <span className="px-2 py-1 text-center min-w-[2.5rem] font-medium border-x border-gray-300">
                            {item.quantity}
                          </span>
                          <button
                            type="button"
                            className="px-2 py-1 text-gray-600 hover:bg-gray-50 rounded-r-md"
                            onClick={() => updateQuantity(item.sellable_unit_id, item.quantity + 1)}
                          >+</button>
                        </div>
                        <span className={`text-xs ${item.quantity > (item.stock || 0) ? 'text-red-600 font-medium' : 'text-gray-500'}`}>
                          {item.stock} in stock
                        </span>
                      </div>

                      <div className="flex">
                        <button
                          type="button"
                          onClick={() => removeItem(item.sellable_unit_id)}
                          className="font-medium text-red-600 hover:text-red-500 flex items-center"
                        >
                          <TrashIcon className="h-4 w-4 mr-1" />
                          Remove
                        </button>
                      </div>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* 3. Notes & Summary */}
        <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm space-y-4">
          <div>
            <label htmlFor="notes" className="block text-sm font-medium text-gray-700">
              Order Notes
            </label>
            <div className="mt-1">
              <textarea
                id="notes"
                rows={3}
                className="block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Optional notes for this order"
              />
            </div>
          </div>

          <div className="border-t border-gray-200 pt-4">
            <div className="flex justify-between text-base font-medium text-gray-900">
              <p>Estimated Total</p>
              <p>{formatCurrency(calculateTotal())}</p>
            </div>
            <p className="mt-0.5 text-sm text-gray-500">
              Pricing is validated server-side. Errors will be shown if prices are missing or stock is insufficient.
            </p>
          </div>

          <div className="pt-4 flex justify-end gap-3">
            <button
              type="button"
              onClick={() => navigate('/orders')}
              className="rounded-md border border-gray-300 bg-white py-2 px-4 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSubmit}
              disabled={submitting || items.length === 0 || !retailerId || !hasCreatePermission}
              title={!hasCreatePermission ? "Permission Denied" : undefined}
              className="inline-flex justify-center rounded-md border border-transparent bg-primary-600 py-2 px-4 text-sm font-medium text-white shadow-sm hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {submitting ? 'Creating Order...' : 'Create Order'}
            </button>
          </div>
        </div>
      </div>

      {/* Product Picker Modal */}
      {showPicker && (
        <div className="fixed inset-0 z-10 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-2xl rounded-lg bg-white p-6 shadow-xl max-h-[80vh] flex flex-col">
            <div className="mb-4 flex items-center justify-between border-b pb-4">
              <h2 className="text-lg font-medium text-gray-900">Select Product</h2>
              <button onClick={() => setShowPicker(false)} className="text-gray-400 hover:text-gray-500">
                <span className="sr-only">Close</span>
                &times;
              </button>
            </div>

            <div className="mb-4">
              <input
                type="text"
                placeholder="Search SKUs..."
                className="w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>

            <div className="flex-1 overflow-y-auto">
              {loadingProducts ? (
                <div className="text-center py-4 text-gray-500">Loading products...</div>
              ) : skus.length === 0 ? (
                <div className="text-center py-4 text-gray-500">No products found.</div>
              ) : (
                <ul className="divide-y divide-gray-200">
                  {skus.map((sku) => {
                    const price = prices[sku.sku_code];
                    const stock = stocks[sku.sku_code] || 0;

                    return (
                      <li key={sku.id} className="py-4 flex justify-between items-center hover:bg-gray-50 px-2 rounded-md">
                        <div className="flex items-center gap-3">
                          <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-gray-100">
                            <ShoppingBagIcon className="h-5 w-5 text-gray-400" />
                          </div>
                          <div>
                            <p className="text-sm font-medium text-gray-900">{sku.name}</p>
                            <div className="flex items-center gap-2 mt-0.5 text-xs">
                              <span className="text-gray-500 font-mono">{sku.sku_code}</span>
                              <span className="text-gray-500">{sku.package_quantity} {sku.unit}</span>
                              <span className="text-gray-300">&bull;</span>
                              <span className={stock > 0 ? 'text-green-600' : 'text-red-600'}>
                                {stock} in stock
                              </span>
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center gap-4">
                          <div className="text-right">
                            {price ? (
                              <span className="text-sm font-medium text-gray-900">{formatCurrency(price)}</span>
                            ) : (
                              <span className="text-sm font-medium text-red-600">No price set</span>
                            )}
                          </div>
                          <button
                            type="button"
                            onClick={() => addProduct(sku)}
                            className="rounded border border-gray-300 bg-white px-2.5 py-1.5 text-xs font-medium text-gray-700 shadow-sm hover:bg-gray-50 focus:outline-none"
                          >
                            Add
                          </button>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
