import { useEffect, useRef, useState } from 'react';
import { Dialog } from '@headlessui/react';
import { CheckIcon, MagnifyingGlassIcon, PlusIcon, XMarkIcon } from '@heroicons/react/24/outline';
import { ProductImage } from '@/components/catalog/ProductImage';
import { clientProductService } from '@/services/clientProductService';
import { formatMoney } from '@/utils/printFormat';
import type { ClientProduct, ClientSellableUnit } from '@/types/client';

interface Props {
  selected: { sellable_unit_id: string; quantity: number }[];
  onAdd: (product: ClientProduct, unit: ClientSellableUnit) => void;
  onClose: () => void;
}

export function OrderProductPicker({ selected, onAdd, onClose }: Props) {
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(1);
  const [products, setProducts] = useState<ClientProduct[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(false);
    setProducts([]);
    const timer = window.setTimeout(async () => {
      try {
        const response = await clientProductService.getAll(page, 20, { search: query.trim() || undefined });
        if (!active) return;
        setProducts(response.data.data.items.filter(product => product.units.some(unit => unit.can_order)));
        setPages(Math.max(1, response.data.data.pagination.pages));
      } catch {
        if (active) setError(true);
      } finally {
        if (active) setLoading(false);
      }
    }, query.trim() ? 300 : 0);
    // In-flight responses lose ownership on search, paging, retry or dismissal.
    return () => { active = false; window.clearTimeout(timer); };
  }, [query, page, attempt]);

  return <Dialog open onClose={onClose} initialFocus={heading} className="relative z-50">
    <div className="fixed inset-0 bg-gray-900/40" aria-hidden="true" />
    <div className="fixed inset-0 flex items-end justify-center sm:items-center sm:p-4">
      <Dialog.Panel className="flex max-h-[90dvh] w-full max-w-lg flex-col overflow-hidden rounded-t-2xl bg-gray-50 shadow-xl sm:rounded-2xl">
        <div className="shrink-0 border-b border-gray-200 bg-white p-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <Dialog.Title ref={heading} tabIndex={-1} as="h2" className="text-lg font-bold text-gray-900 outline-none">Add products</Dialog.Title>
              <Dialog.Description className="mt-1 text-sm text-gray-500">Choose a pack. Keep adding, then review your order.</Dialog.Description>
            </div>
            <button type="button" aria-label="Close product picker" onClick={onClose}
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-gray-500 hover:bg-gray-100 focus-visible:outline-primary-600">
              <XMarkIcon className="h-5 w-5" aria-hidden="true" />
            </button>
          </div>
          <label className="relative mt-4 block">
            <span className="sr-only">Search products</span>
            <MagnifyingGlassIcon className="pointer-events-none absolute left-3 top-3 h-5 w-5 text-gray-400" aria-hidden="true" />
            <input type="search" value={query} placeholder="Search products..." autoComplete="off"
              onChange={event => { setQuery(event.target.value); setPage(1); }}
              className="min-h-[44px] w-full rounded-xl border border-gray-300 bg-white py-2 pl-10 pr-3 text-base outline-none focus:border-primary-500 focus:ring-1 focus:ring-primary-500" />
          </label>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-4" aria-busy={loading}>
          {loading && <p role="status" className="py-8 text-center text-sm text-gray-500">Loading products...</p>}
          {!loading && error && <div role="alert" className="rounded-xl border border-red-200 bg-white p-4 text-sm text-red-700">
            <p>Products could not be loaded. Your selection is still here.</p>
            <button type="button" onClick={() => setAttempt(value => value + 1)} className="mt-2 min-h-[44px] rounded-lg border border-red-200 px-4 font-medium">Retry loading products</button>
          </div>}
          {!loading && !error && products.length === 0 && <p className="py-8 text-center text-sm text-gray-500">No orderable products on this page. Try another page or search.</p>}
          <div className="space-y-3">
            {products.map(product => <article key={product.id} aria-label={product.name} className="rounded-xl border border-gray-200 bg-white p-3">
              <div className="flex items-center gap-3">
                <div className="h-16 w-16 shrink-0 overflow-hidden rounded-lg bg-gray-50">
                  <ProductImage image={product.image} name={product.name} className="h-full w-full" />
                </div>
                <h3 className="min-w-0 break-words text-sm font-semibold text-gray-900">{product.name}</h3>
              </div>
              <div className="mt-3 space-y-2">
                {product.units.filter(unit => unit.can_order).map(unit => {
                  const quantity = selected.find(item => item.sellable_unit_id === unit.sellable_unit_id)?.quantity || 0;
                  return <button key={unit.sellable_unit_id} type="button" data-testid={`picker-unit-${unit.sku_code}`}
                    aria-label={`Add ${unit.sku_code}, ${unit.package_quantity} ${unit.unit}; ${quantity} selected`}
                    onClick={() => onAdd(product, unit)}
                    className={`flex min-h-[60px] w-full items-center gap-3 rounded-lg border p-3 text-left transition focus-visible:outline-primary-600 ${quantity ? 'border-primary-300 bg-primary-50' : 'border-gray-200 hover:bg-gray-50'}`}>
                    <div className="min-w-0 flex-1">
                      <p className="break-words text-sm font-medium text-gray-900">{unit.package_quantity} &times; {unit.unit}</p>
                      <p className="break-all text-xs text-gray-500">{unit.sku_code}</p>
                      <p className={`mt-1 text-xs ${unit.stock_level === 'HIGH' ? 'text-green-700' : 'text-amber-700'}`}>
                        {unit.stock_level === 'HIGH' ? 'In Stock' : unit.stock_level === 'MEDIUM' ? 'Limited Stock' : 'Low Stock'}
                      </p>
                    </div>
                    <div className="min-w-0 text-right">
                      {unit.price !== null && <p className="break-words text-sm font-semibold text-gray-900">{formatMoney(unit.price, unit.currency)}</p>}
                      {quantity > 0 && <p className="mt-1 text-xs font-medium text-primary-700">{quantity} selected</p>}
                    </div>
                    <PlusIcon className="h-5 w-5 shrink-0 text-primary-600" aria-hidden="true" />
                  </button>;
                })}
              </div>
            </article>)}
          </div>
        </div>

        <div className="shrink-0 space-y-3 border-t border-gray-200 bg-white p-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
          <nav aria-label="Product pages" className="flex items-center justify-between gap-2 text-sm">
            <button type="button" disabled={loading || page === 1} onClick={() => setPage(value => value - 1)} className="min-h-[44px] rounded-lg border border-gray-200 px-3 disabled:opacity-40">Previous page</button>
            <span aria-live="polite">Page {page} of {pages}</span>
            <button type="button" disabled={loading || error || page >= pages} onClick={() => setPage(value => value + 1)} className="min-h-[44px] rounded-lg border border-gray-200 px-3 disabled:opacity-40">Next page</button>
          </nav>
          <div className="flex items-center justify-between gap-3">
            <p role="status" className="text-sm text-gray-600">{selected.length} pack {selected.length === 1 ? 'choice' : 'choices'} selected</p>
            <button type="button" onClick={onClose} className="flex min-h-[44px] items-center gap-2 rounded-xl bg-primary-600 px-5 py-3 text-sm font-semibold text-white hover:bg-primary-700">
              <CheckIcon className="h-5 w-5" aria-hidden="true" /> Done
            </button>
          </div>
        </div>
      </Dialog.Panel>
    </div>
  </Dialog>;
}
