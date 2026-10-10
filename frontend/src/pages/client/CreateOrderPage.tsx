import { useState, useEffect, useCallback } from 'react';
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeftIcon, TrashIcon, PlusIcon, ShoppingBagIcon } from '@heroicons/react/24/outline';
import { clientProductService } from '@/services/clientProductService';
import { clientOrderService } from '@/services/clientOrderService';
import { QuoteConsent } from '@/components/pricing/QuoteConsent';
import { formatMoney } from '@/utils/printFormat';
import type { ClientProduct, ClientSellableUnit, CreateOrderItem } from '@/types/client';

interface OrderLineItem {
  sellable_unit_id: string;
  sku_code: string;
  name: string;
  quantity: number;
  price?: string | null;
  currency?: string | null;
}

export function CreateOrderPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const replacing = params.get('replace');
  const [items, setItems] = useState<OrderLineItem[]>([]);
  const [notes, setNotes] = useState('');
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
      // Product-level contract: keep products that have at least one orderable unit.
      setProducts(res.data.data.items.filter((p) => p.units.some((u) => u.can_order)));
    } catch {
      setError('Failed to load products. Please retry the product selection.');
    } finally {
      setLoadingProducts(false);
    }
  }, [searchQuery]);

  useEffect(() => {
    if (showPicker) {
      loadProducts();
    }
  }, [showPicker, loadProducts]);

  const addUnit = (product: ClientProduct, unit: ClientSellableUnit) => {
    const existing = items.find((i) => i.sellable_unit_id === unit.sellable_unit_id);
    if (existing) {
      setItems(items.map((i) =>
        i.sellable_unit_id === unit.sellable_unit_id
          ? { ...i, quantity: i.quantity + 1 }
          : i
      ));
    } else {
      setItems([...items, {
        sellable_unit_id: unit.sellable_unit_id,
        sku_code: unit.sku_code,
        name: product.name,
        quantity: 1,
        price: unit.price,
        currency: unit.currency
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

  const formatCurrency = (amount: string, currency?: string | null) => formatMoney(amount, currency);
  const orderItems: CreateOrderItem[] = items.map(i => ({
    sellable_unit_id: i.sellable_unit_id, sku_code: i.sku_code, quantity: i.quantity,
  }));

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
                      {formatCurrency(item.price, item.currency)}
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
              {/* One row per product; each orderable packaging choice is its own button */}
              {products.map((p) => (
                <div key={p.id} className="rounded-lg border border-gray-100 p-2">
                  <p className="text-sm font-medium text-gray-900 truncate">{p.name}</p>
                  {p.units.filter((u) => u.can_order).map((u) => (
                    <button
                      key={u.sellable_unit_id}
                      data-testid={`picker-unit-${u.sku_code}`}
                      onClick={() => addUnit(p, u)}
                      className="mt-1 flex w-full items-center gap-3 rounded-lg p-2 text-left hover:bg-gray-50 transition"
                    >
                      <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-gray-100">
                        <ShoppingBagIcon className="h-5 w-5 text-gray-400" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-xs text-gray-500 font-mono truncate">{u.sku_code}</p>
                        <p className="text-xs text-gray-400">{u.package_quantity} × {u.unit}</p>
                      </div>
                      <span className={`text-xs font-medium ${
                        u.stock_level === 'HIGH' ? 'text-green-600' :
                        u.stock_level === 'MEDIUM' ? 'text-yellow-600' :
                        'text-orange-600'
                      }`}>
                        {u.stock_level === 'HIGH' ? 'In Stock' :
                         u.stock_level === 'MEDIUM' ? 'Limited' : 'Low'}
                      </span>
                      {u.price !== null && (
                        <span className="text-sm font-medium text-gray-900">
                          {formatCurrency(u.price, u.currency)}
                        </span>
                      )}
                    </button>
                  ))}
                </div>
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

      <QuoteConsent
        intent={JSON.stringify({ orderItems, notes })}
        disabled={!items.length}
        replacing={Boolean(replacing)}
        preview={async () => (await clientOrderService.preview({ items: orderItems })).data.data}
        submit={async (quote, key) => {
          const data = { items: orderItems, notes: notes || undefined, quote_token: quote.quote_token };
          const result = replacing
            ? await clientOrderService.replaceDraft(replacing, data, key)
            : await clientOrderService.create(data, key);
          navigate(`/client/orders/${result.data.data.id}`, { replace: true });
        }}
      />
    </div>
  );
}
