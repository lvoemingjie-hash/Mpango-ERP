import { formatMoney } from '@/utils/printFormat';
import { useEffect, useState, useRef } from 'react';
import { Link } from 'react-router-dom';
import { MagnifyingGlassIcon, ShoppingBagIcon } from '@heroicons/react/24/outline';
import { ProductImage } from '@/components/catalog/ProductImage';
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

/**
 * DC-12R1-MVP-L1-SKU-R0-M1-R1-R1: exactly ONE card per CatalogProduct.
 * Packaging choices (bottle/case/...) are rendered INSIDE the same product
 * container — never as independent SKU cards.
 */
export function ProductListPage() {
  const [products, setProducts] = useState<ClientProduct[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [{ search, page }, setQuery] = useState({ search: '', page: 1 });
  const [retry, setRetry] = useState(0);
  const request = useRef(0);
  const [totalPages, setTotalPages] = useState(1);

  useEffect(() => {
    const attempt = ++request.current;
    let active = true;
    setLoading(true); setError(null);
    clientProductService.getAll(page, 20, { search: search || undefined }).then(res => {
      if (!active || attempt !== request.current) return;
      setProducts(res.data.data.items); setTotalPages(res.data.data.pagination.pages);
    }).catch(error => {
      if (active && attempt === request.current) setError(error?.response?.status === 403
        ? 'Your account cannot view this supplier catalog. Check your access with the supplier.'
        : 'Failed to load products. Please try again.');
    }).finally(() => { if (active && attempt === request.current) setLoading(false); });
    return () => { active = false; };
  }, [page, search, retry]);
  const changeSearch = (value: string) => {
    if (value === search && page === 1) return;
    request.current++; // invalidate an old response immediately, before effects run
    setQuery({ search: value, page: 1 });
  };

  return (
    <div className="space-y-4">
      {/* Search Bar */}
      <form onSubmit={e => e.preventDefault()} className="relative">
        <MagnifyingGlassIcon className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-gray-400" />
        <input
          type="text"
          aria-label="Search products" placeholder="Search products..."
          value={search}
          onChange={(e) => changeSearch(e.target.value)}
          className="w-full rounded-xl border border-gray-200 bg-white py-3 pl-10 pr-4 text-sm shadow-sm focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none transition"
        />
      </form>
      {search && <button type="button" onClick={() => changeSearch('')} className="text-sm text-primary-700 underline">Clear search</button>}

      {/* Error */}
      {error && (
        <div role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error} <button onClick={() => setRetry(n => n + 1)} className="underline">Retry products</button></div>
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
          title={search ? "No matching products" : "No products available"}
          description={search ? "Try another product name or clear your search." : "Products from your supplier will appear here."}
        />
      )}

      {/* Product Cards Grid — one container per CatalogProduct */}
      {!loading && !error && products.length > 0 && (
        <>
          <div className="grid grid-cols-2 gap-3">
            {products.map((product) => {
              const badge = STOCK_BADGE[product.stock_level] ?? STOCK_BADGE.OUT_OF_STOCK;
              const pricedUnit = product.units.find(unit => unit.can_order && unit.price != null);

              return (
                <Link
                  key={product.id}
                  to={`/client/products/${product.id}`}
                  data-testid="client-product-card"
                  aria-label={`View product ${product.name}`}
                  className="group rounded-xl border border-gray-200 bg-white p-4 shadow-sm transition hover:shadow-md hover:border-primary-200"
                >
                  {/* Product Icon Placeholder */}
                  <div className="mb-3 flex h-20 items-center justify-center rounded-lg bg-gray-50 text-gray-300">
                    <ProductImage image={product.image} name={product.name} className="h-full w-full" />
                  </div>

                  {/* Name & Price */}
                  <div className="flex flex-col items-start gap-2 sm:flex-row sm:justify-between">
                    <h3 className="text-sm font-semibold text-gray-900 line-clamp-2 group-hover:text-primary-600 transition-colors">
                      {product.name}
                    </h3>
                    {pricedUnit ? (
                      <span className="text-sm font-bold text-gray-900 whitespace-nowrap">
                        {formatMoney(pricedUnit.price, pricedUnit.currency)}
                        <span className="block text-xs font-normal text-gray-500 whitespace-normal">per {pricedUnit.display_label || `${pricedUnit.package_quantity} × ${pricedUnit.unit}`}</span>
                      </span>
                    ) : (
                      <span className="text-xs font-medium text-gray-500 italic whitespace-nowrap mt-0.5">
                        Contact Supplier
                      </span>
                    )}
                  </div>

                  {/* Packaging choices — inside this same product container */}
                  <ul data-testid="client-product-units" className="mt-2 space-y-1">
                    {product.units.map((unit) => (
                      <li
                        key={unit.sellable_unit_id}
                        className="flex flex-wrap items-start justify-between gap-1 border-t border-gray-100 py-1 text-xs text-gray-500"
                      >
                        <span className="break-words">{unit.package_quantity} × {unit.unit}<span className="block break-all text-gray-400">{unit.sku_code}</span></span>
                        <span className="break-words">{unit.price != null ? formatMoney(unit.price, unit.currency) : 'Price unavailable'} · {unit.can_order ? 'Available to order' : 'Unavailable'}</span>
                      </li>
                    ))}
                  </ul>

                  {/* Category */}
                  {product.category && (
                    <p className="mt-1 text-xs text-gray-500">{product.category}</p>
                  )}

                  {/* Stock Badge */}
                  <div className="mt-2 flex items-center gap-1.5">
                    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${badge.className}`}>
                      {badge.label}
                    </span>
                    {product.unit_count > 0 && (
                      <span className="text-xs text-gray-400">
                        {product.unit_count} {product.unit_count === 1 ? 'packaging' : 'packagings'}
                      </span>
                    )}
                  </div>
                </Link>
              );
            })}
          </div>

          <Pagination page={page} totalPages={totalPages} onPageChange={nextPage => { if (nextPage !== page) { request.current++; setQuery(current => ({ ...current, page: nextPage })); } }} />
        </>
      )}
    </div>
  );
}
