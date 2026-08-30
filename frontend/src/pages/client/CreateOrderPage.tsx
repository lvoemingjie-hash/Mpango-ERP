import { useState, useEffect, useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { ArrowLeftIcon, TrashIcon, PlusIcon, ShoppingBagIcon } from '@heroicons/react/24/outline';
import { clientProductService } from '@/services/clientProductService';
import { clientOrderService } from '@/services/clientOrderService';
import { normalizeApiError } from '@/utils/errorHandling';
import type { ClientProduct, CreateOrderItem } from '@/types/client';

interface OrderLineItem {
  sellable_unit_id: string;
  sku_code: string;
  name: string;
  quantity: number;
  price?: number | null;
}

export function CreateOrderPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const [items, setItems] = useState<OrderLineItem[]>([]);
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Product picker state
  const [showPicker, setShowPicker] = useState(false);
  const [products, setProducts] = useState<ClientProduct[]>([]);
  const [loadingProducts, setLoadingProducts] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  // Initialize from navigation state (from ProductDetailPage)
  useEffect(() => {
    const state = location.state as { items?: OrderLineItem[] } | null;
    if (state?.items) {
      setItems(state.items);
    }
  }, [location.state]);

  const loadProducts = useCallback(async () => {
    setLoadingProducts(true);
    try {
      const res = await clientProductService.getAll(1, 50, {
        search: searchQuery || undefined,
      });
      setProducts(res.data.data.items.filter((p) => p.can_order));
    } catch {
      // Silently fail — picker just shows empty
    } finally {
      setLoadingProducts(false);
    }
  }, [searchQuery]);

  useEffect(() => {
    if (showPicker) {
      loadProducts();
    }
  }, [showPicker, loadProducts]);

  const addProduct = (product: ClientProduct) => {
    const existing = items.find((i) => i.sellable_unit_id === product.sellable_unit_id);
    if (existing) {
      setItems(items.map((i) =>
        i.sellable_unit_id === product.sellable_unit_id
          ? { ...i, quantity: i.quantity + 1 }
          : i
      ));
    } else {
      setItems([...items, {
        sellable_unit_id: product.sellable_unit_id,
        sku_code: product.sku_code,
        name: product.name,
        quantity: 1,
        price: product.price
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

  const handleSubmit = async () => {
    if (items.length === 0) return;
    setSubmitting(true);
    setError(null);
    try {
      const orderItems: CreateOrderItem[] = items.map((i) => ({
        sellable_unit_id: i.sellable_unit_id,
        sku_code: i.sku_code,
        quantity: i.quantity,
      }));
      const res = await clientOrderService.create({ items: orderItems, notes: notes || undefined });
      navigate(`/client/orders/${res.data.data.id}`, { replace: true });
    } catch (err) {
      setError(normalizeApiError(err));
    } finally {
      setSubmitting(false);
    }
  };

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('en-KE', {
      style: 'currency',
      currency: 'KES',
    }).format(amount);
  };

  const calculateTotal = () => {
    return items.reduce((total, item) => {
      return total + ((item.price || 0) * item.quantity);
    }, 0);
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => navigate('/client')}
          className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600 transition"
        >
          <ArrowLeftIcon className="h-5 w-5" />
        </button>
        <h1 className="text-lg font-bold text-gray-900">New Order</h1>
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</div>
      )}

      {/* Line Items */}
      {items.length === 0 ? (
        <div className="rounded-xl border-2 border-dashed border-gray-300 bg-gray-50 p-8 text-center">
          <ShoppingBagIcon className="mx-auto h-10 w-10 text-gray-300" />
          <p className="mt-2 text-sm font-medium text-gray-500">No items yet</p>
          <p className="text-xs text-gray-400">Add products to your order</p>
        </div>
      ) : (
        <div className="space-y-2">
          {items.map((item) => (
            <div
              key={item.sellable_unit_id}
              className="flex items-center gap-3 rounded-xl border border-gray-200 bg-white p-3 shadow-sm"
            >
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900 truncate">{item.name}</p>
                <div className="flex items-center gap-2 mt-0.5">
                  <p className="text-xs text-gray-400 font-mono">{item.sku_code}</p>
                  {item.price !== undefined && item.price !== null && (
                    <span className="text-xs font-medium text-gray-600">
                      {formatCurrency(item.price)}
                    </span>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-1.5">
                <button
                  onClick={() => updateQuantity(item.sellable_unit_id, item.quantity - 1)}
                  className="flex h-7 w-7 items-center justify-center rounded-md border border-gray-300 text-xs text-gray-600 hover:bg-gray-50"
                >
                  -
                </button>
                <span className="w-8 text-center text-sm font-medium">{item.quantity}</span>
                <button
                  onClick={() => updateQuantity(item.sellable_unit_id, item.quantity + 1)}
                  className="flex h-7 w-7 items-center justify-center rounded-md border border-gray-300 text-xs text-gray-600 hover:bg-gray-50"
                >
                  +
                </button>
              </div>

              <button
                onClick={() => removeItem(item.sellable_unit_id)}
                className="rounded-md p-1 text-gray-400 hover:bg-red-50 hover:text-red-500 transition"
              >
                <TrashIcon className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Add Product Button */}
      <button
        onClick={() => setShowPicker(true)}
        className="flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-gray-300 bg-white px-4 py-3 text-sm font-medium text-gray-500 hover:border-primary-300 hover:text-primary-600 transition"
      >
        <PlusIcon className="h-5 w-5" />
        Add Product
      </button>

      {/* Product Picker Modal */}
      {showPicker && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 sm:items-center">
          <div className="w-full max-w-lg rounded-t-2xl bg-white p-4 shadow-xl sm:rounded-2xl sm:m-4 max-h-[70vh] flex flex-col">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-base font-semibold text-gray-900">Add Product</h2>
              <button
                onClick={() => setShowPicker(false)}
                className="rounded-md p-1 text-gray-400 hover:text-gray-600"
              >
                &times;
              </button>
            </div>

            <input
              type="text"
              placeholder="Search..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="mb-3 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none"
            />

            <div className="flex-1 overflow-y-auto space-y-1">
              {loadingProducts && (
                <p className="py-4 text-center text-sm text-gray-400">Loading...</p>
              )}
              {!loadingProducts && products.length === 0 && (
                <p className="py-4 text-center text-sm text-gray-400">No products available</p>
              )}
              {products.map((p) => (
                <button
                  key={p.id}
                  onClick={() => addProduct(p)}
                  className="flex w-full items-center gap-3 rounded-lg p-2.5 text-left hover:bg-gray-50 transition"
                >
                  <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-gray-100">
                    <ShoppingBagIcon className="h-5 w-5 text-gray-400" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-900 truncate">{p.name}</p>
                    <p className="text-xs text-gray-400">{p.sku_code} - {p.package_quantity} {p.unit}</p>
                  </div>
                  <span className={`text-xs font-medium ${
                    p.stock_level === 'HIGH' ? 'text-green-600' :
                    p.stock_level === 'MEDIUM' ? 'text-yellow-600' :
                    'text-orange-600'
                  }`}>
                    {p.stock_level === 'HIGH' ? 'In Stock' :
                     p.stock_level === 'MEDIUM' ? 'Limited' : 'Low'}
                  </span>
                  {p.price !== null && (
                    <span className="text-sm font-medium text-gray-900">
                      {formatCurrency(p.price)}
                    </span>
                  )}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Notes */}
      <div>
        <label className="mb-1 block text-sm font-medium text-gray-700">
          Notes (optional)
        </label>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Any special instructions..."
          rows={2}
          className="w-full rounded-xl border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none transition resize-none"
        />
      </div>

      {/* Order Total */}
      {items.length > 0 && (
        <div className="rounded-xl bg-gray-50 p-4 flex items-center justify-between">
          <span className="text-sm font-medium text-gray-700">Estimated Total</span>
          <span className="text-lg font-bold text-gray-900">
            {formatCurrency(calculateTotal())}
          </span>
        </div>
      )}

      {/* Submit */}
      <button
        onClick={handleSubmit}
        disabled={items.length === 0 || submitting}
        className="w-full rounded-xl bg-primary-600 px-4 py-3.5 text-sm font-semibold text-white shadow-sm hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition"
      >
        {submitting
          ? 'Submitting...'
          : `Submit Order (${items.reduce((sum, i) => sum + i.quantity, 0)} items)`}
      </button>
    </div>
  );
}
