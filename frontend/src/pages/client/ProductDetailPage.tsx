import { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeftIcon, ShoppingBagIcon } from '@heroicons/react/24/outline';
import { clientProductService } from '@/services/clientProductService';
import type { ClientProductDetail, ClientSellableUnit } from '@/types/client';

const STOCK_BADGE: Record<string, { label: string; className: string }> = {
  HIGH: { label: 'In Stock', className: 'bg-green-100 text-green-700' },
  MEDIUM: { label: 'Limited Stock', className: 'bg-yellow-100 text-yellow-700' },
  LOW: { label: 'Low Stock', className: 'bg-orange-100 text-orange-700' },
  OUT_OF_STOCK: { label: 'Out of Stock', className: 'bg-red-100 text-red-700' },
};

function formatKES(amount: number): string {
  return amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

/**
 * DC-12R1-MVP-L1-SKU-R0-M1-R1-R1: the detail page IS the product container.
 * Packaging choices are selected through an accessible radio group; stock,
 * price and availability always reflect the SELECTED sellable unit; any
 * submission carries the selected stable sellable_unit_id (exposed as
 * data-selected-sellable-unit-id for observability).
 */
export function ProductDetailPage() {
  const { productId } = useParams<{ productId: string }>();
  const navigate = useNavigate();
  const [product, setProduct] = useState<ClientProductDetail | null>(null);
  const [selectedUnit, setSelectedUnit] = useState<ClientSellableUnit | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [quantity, setQuantity] = useState(1);

  const load = useCallback(async () => {
    if (!productId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await clientProductService.getById(productId);
      const detail: ClientProductDetail = res.data.data;
      setProduct(detail);
      // Deterministic default: first unit in the backend's stable order.
      setSelectedUnit(detail.units[0] ?? null);
    } catch {
      setError('Product not found or unavailable.');
    } finally {
      setLoading(false);
    }
  }, [productId]);

  useEffect(() => {
    load();
  }, [load]);

  const handleAddToOrder = () => {
    if (!product || !selectedUnit) return;
    navigate('/client/orders/new', {
      state: {
        items: [{
          sellable_unit_id: selectedUnit.sellable_unit_id,
          sku_code: selectedUnit.sku_code,
          name: product.name,
          quantity,
          price: selectedUnit.price
        }],
      },
    });
  };

  if (loading) {
    return (
      <div className="space-y-4 animate-pulse">
        <div className="h-8 w-1/3 rounded bg-gray-200" />
        <div className="h-48 rounded-xl bg-gray-200" />
        <div className="h-4 w-2/3 rounded bg-gray-200" />
        <div className="h-4 w-1/2 rounded bg-gray-200" />
        <div className="h-12 rounded-xl bg-gray-200" />
      </div>
    );
  }

  if (error || !product) {
    return (
      <div className="space-y-4">
        <button
          onClick={() => navigate('/client')}
          className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700"
        >
          <ArrowLeftIcon className="h-4 w-4" />
          Back to products
        </button>
        <div className="rounded-lg bg-red-50 p-4 text-sm text-red-700">
          {error || 'Product not found'}
        </div>
      </div>
    );
  }

  const unitBadge = STOCK_BADGE[selectedUnit?.stock_level ?? 'OUT_OF_STOCK'] ?? STOCK_BADGE.OUT_OF_STOCK;

  return (
    <div className="space-y-4">
      {/* Back Button */}
      <button
        onClick={() => navigate('/client')}
        className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700"
      >
        <ArrowLeftIcon className="h-4 w-4" />
        Back to products
      </button>

      {/* Product Image Placeholder */}
      <div className="flex h-48 items-center justify-center rounded-xl bg-gray-100 text-gray-300">
        <ShoppingBagIcon className="h-16 w-16" />
      </div>

      {/* Product Info — the selected unit drives price/stock display */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-gray-900">{product.name}</h1>
          {selectedUnit && (
            <p className="mt-0.5 text-sm font-mono text-gray-400">{selectedUnit.sku_code}</p>
          )}
        </div>
        <div className="text-right">
          {selectedUnit?.price !== null && selectedUnit !== null ? (
            <div className="text-2xl font-bold text-gray-900">
              KES {formatKES(selectedUnit.price as number)}
            </div>
          ) : (
            <div className="text-sm font-medium text-gray-500 italic mt-1.5">
              Contact Supplier for Price
            </div>
          )}
        </div>
      </div>

      {/* Packaging selector — one accessible radio group per product */}
      {product.units.length > 0 && (
        <div
          role="radiogroup"
          aria-label="Packaging"
          data-testid="packaging-selector"
          className="grid grid-cols-2 gap-2"
        >
          {product.units.map((unit) => (
            <button
              key={unit.sellable_unit_id}
              type="button"
              role="radio"
              aria-checked={selectedUnit?.sellable_unit_id === unit.sellable_unit_id}
              data-sellable-unit-id={unit.sellable_unit_id}
              onClick={() => {
                setSelectedUnit(unit);
                setQuantity(1);
              }}
              className={`rounded-xl border p-3 text-left transition focus:outline-none focus:ring-2 focus:ring-primary-500 ${
                selectedUnit?.sellable_unit_id === unit.sellable_unit_id
                  ? 'border-primary-500 bg-primary-50 ring-1 ring-primary-500'
                  : 'border-gray-200 bg-white hover:border-primary-200'
              }`}
            >
              <span className="block font-mono text-xs text-gray-500 truncate">{unit.sku_code}</span>
              <span className="block text-sm font-semibold text-gray-900">
                {unit.package_quantity} × {unit.unit}
              </span>
              <span className="block text-xs text-gray-500">
                {unit.price !== null ? `KES ${formatKES(unit.price)}` : 'Contact Supplier'}
              </span>
            </button>
          ))}
        </div>
      )}

      {/* Stock & Category — reflects the SELECTED unit */}
      <div className="flex items-center gap-2">
        <span
          data-testid="selected-unit-stock"
          className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ${unitBadge.className}`}
        >
          {unitBadge.label}
        </span>
        {product.category && (
          <span className="inline-flex items-center rounded-full bg-gray-100 px-2.5 py-1 text-xs font-medium text-gray-600">
            {product.category}
          </span>
        )}
        {selectedUnit && (
          <span className="text-xs text-gray-400">
            Per {selectedUnit.unit} ({selectedUnit.package_quantity})
          </span>
        )}
      </div>

      {/* Description */}
      {product.description && (
        <p className="text-sm text-gray-600 leading-relaxed">{product.description}</p>
      )}

      {/* Order Section — carries ONLY the selected stable sellable_unit_id */}
      <div
        data-testid="order-section"
        data-selected-sellable-unit-id={selectedUnit?.sellable_unit_id ?? ''}
      >
        {product.can_order && selectedUnit?.can_order ? (
          <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm space-y-3">
            <div className="flex items-center justify-between">
              <label className="text-sm font-medium text-gray-700">Quantity</label>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setQuantity((q) => Math.max(1, q - 1))}
                  className="flex h-8 w-8 items-center justify-center rounded-lg border border-gray-300 text-gray-600 hover:bg-gray-50 transition"
                >
                  -
                </button>
                <input
                  type="number"
                  min={1}
                  value={quantity}
                  onChange={(e) => setQuantity(Math.max(1, parseInt(e.target.value) || 1))}
                  className="w-16 rounded-lg border border-gray-300 px-2 py-1.5 text-center text-sm"
                />
                <button
                  onClick={() => setQuantity((q) => q + 1)}
                  className="flex h-8 w-8 items-center justify-center rounded-lg border border-gray-300 text-gray-600 hover:bg-gray-50 transition"
                >
                  +
                </button>
              </div>
            </div>

            {selectedUnit.price !== null && (
              <div className="flex justify-between items-center py-2 border-t border-gray-100">
                <span className="text-sm text-gray-600">Subtotal</span>
                <span className="text-base font-bold text-gray-900">
                  KES {formatKES(selectedUnit.price * quantity)}
                </span>
              </div>
            )}

            <button
              onClick={handleAddToOrder}
              className="w-full rounded-xl bg-primary-600 px-4 py-3 text-sm font-semibold text-white shadow-sm hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 transition"
            >
              Add to Order
            </button>
          </div>
        ) : (
          <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-center">
            <p className="text-sm font-medium text-red-700">
              {selectedUnit?.price === null
                ? "Cannot order: No price configured. Please contact your supplier."
                : "This product is currently out of stock"}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
