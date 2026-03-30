import { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { MagnifyingGlassIcon, ShoppingBagIcon } from '@heroicons/react/24/outline';
import { clientProductService } from '@/services/clientProductService';
import { EmptyState } from '@/components/ui/EmptyState';
import { Pagination } from '@/components/ui/Pagination';
import type { ClientProduct } from '@/types/client';

const STOCK_BADGE: Record<string, { label: string; className: string }> = {
  HIGH: { label: 'In Stock', className: 'bg-green-100 text-green-700' },
  MEDIUM: { label: 'Limited', className: 'bg-yellow-100 text-yellow-700' },
  LOW: { label: 'Low Stock', className: 'bg-orange-100 text-orange-700' },
  OUT_OF_STOCK: { label: 'Out of Stock', className: 'bg-red-100 text-red-700' },
};

export function ProductListPage() {
  const [products, setProducts] = useState<ClientProduct[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await clientProductService.getAll(page, 20, {
        search: search || undefined,
      });
      setProducts(res.data.data.items);
      setTotalPages(res.data.data.pagination.pages);
    } catch {
      setError('Failed to load products. Please try again.');
    } finally {
      setLoading(false);
    }
  }, [page, search]);

  useEffect(() => {
    load();
  }, [load]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    load();
  };

  return (
    <div className="space-y-4">
      {/* Search Bar */}
      <form onSubmit={handleSearch} className="relative">
        <MagnifyingGlassIcon className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-gray-400" />
        <input
          type="text"
          placeholder="Search products..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full rounded-xl border border-gray-200 bg-white py-3 pl-10 pr-4 text-sm shadow-sm focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none transition"
        />
      </form>

      {/* Error */}
      {error && (
        <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</div>
      )}

      {/* Loading */}
      {loading && (
        <div className="grid grid-cols-2 gap-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="animate-pulse rounded-xl border border-gray-200 bg-white p-4">
              <div className="mb-3 h-4 w-3/4 rounded bg-gray-200" />
              <div className="mb-2 h-3 w-1/2 rounded bg-gray-200" />
              <div className="h-8 w-full rounded bg-gray-200" />
            </div>
          ))}
        </div>
      )}

      {/* Empty State */}
      {!loading && !error && products.length === 0 && (
        <EmptyState
          icon={ShoppingBagIcon}
          title="No products available"
          description="Products from your supplier will appear here."
        />
      )}

      {/* Product Cards Grid */}
      {!loading && !error && products.length > 0 && (
        <>
          <div className="grid grid-cols-2 gap-3">
            {products.map((product) => {
              const badge = STOCK_BADGE[product.stock_level] ?? STOCK_BADGE.OUT_OF_STOCK;

              return (
                <Link
                  key={product.id}
                  to={`/client/products/${product.id}`}
                  className="group rounded-xl border border-gray-200 bg-white p-4 shadow-sm transition hover:shadow-md hover:border-primary-200"
                >
                  {/* Product Icon Placeholder */}
                  <div className="mb-3 flex h-20 items-center justify-center rounded-lg bg-gray-50 text-gray-300">
                    <ShoppingBagIcon className="h-8 w-8" />
                  </div>

                  {/* Name */}
                  <h3 className="text-sm font-semibold text-gray-900 line-clamp-2 group-hover:text-primary-600 transition-colors">
                    {product.name}
                  </h3>

                  {/* SKU */}
                  <p className="mt-0.5 text-xs text-gray-400 font-mono">
                    {product.sku_code}
                  </p>

                  {/* Category */}
                  {product.category && (
                    <p className="mt-1 text-xs text-gray-500">{product.category}</p>
                  )}

                  {/* Stock Badge */}
                  <div className="mt-2">
                    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${badge.className}`}>
                      {badge.label}
                    </span>
                  </div>

                  {/* Unit */}
                  <p className="mt-1 text-xs text-gray-400">
                    Per {product.unit}
                  </p>
                </Link>
              );
            })}
          </div>

          <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />
        </>
      )}
    </div>
  );
}
