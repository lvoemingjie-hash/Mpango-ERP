import { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeftIcon, ShoppingBagIcon } from '@heroicons/react/24/outline';
import { clientProductService } from '@/services/clientProductService';
import type { ClientProductDetail } from '@/types/client';

const STOCK_BADGE: Record<string, { label: string; className: string }> = {
  HIGH: { label: 'In Stock', className: 'bg-green-100 text-green-700' },
  MEDIUM: { label: 'Limited Stock', className: 'bg-yellow-100 text-yellow-700' },
  LOW: { label: 'Low Stock', className: 'bg-orange-100 text-orange-700' },
  OUT_OF_STOCK: { label: 'Out of Stock', className: 'bg-red-100 text-red-700' },
};

export function ProductDetailPage() {
  const { productId } = useParams<{ productId: string }>();
  const navigate = useNavigate();
  const [product, setProduct] = useState<ClientProductDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [quantity, setQuantity] = useState(1);

  const load = useCallback(async () => {
    if (!productId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await clientProductService.getById(productId);
      setProduct(res.data.data);
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
    if (!product) return;
    navigate('/client/orders/new', {
      state: {
        items: [{ sku_code: product.sku_code, name: product.name, quantity }],
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

  const badge = STOCK_BADGE[product.stock_level] ?? STOCK_BADGE.OUT_OF_STOCK;

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

      {/* Product Info */}
      <div>
        <h1 className="text-xl font-bold text-gray-900">{product.name}</h1>
        <p className="mt-0.5 text-sm font-mono text-gray-400">{product.sku_code}</p>
      </div>

      {/* Stock & Category */}
      <div className="flex items-center gap-2">
        <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ${badge.className}`}>
          {badge.label}
        </span>
        {product.category && (
          <span className="inline-flex items-center rounded-full bg-gray-100 px-2.5 py-1 text-xs font-medium text-gray-600">
            {product.category}
          </span>
        )}
        <span className="text-xs text-gray-400">Per {product.unit}</span>
      </div>

      {/* Description */}
      {product.description && (
        <p className="text-sm text-gray-600 leading-relaxed">{product.description}</p>
      )}

      {/* Order Section */}
      {product.can_order ? (
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
            This product is currently unavailable for ordering
          </p>
        </div>
      )}
    </div>
  );
}
