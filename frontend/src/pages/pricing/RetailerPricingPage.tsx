import { useEffect, useRef, useState } from 'react';
import { retailerService, type RetailerWithBinding } from '@/services/retailerService';
import { pricingService } from '@/services/pricingService';
import { useAuthStore } from '@/stores/authStore';
import { normalizeApiError } from '@/utils/errorHandling';
import { PageHeader } from '@/components/layout/PageHeader';
import { formatMoney } from '@/utils/printFormat';
import type { RetailerPriceView } from '@/types/pricing';

function PriceEditor({ initial, disabled, save, saveLabel, valueLabel }: {
  initial: string; disabled: boolean; save: (value: string) => Promise<void>;
  saveLabel: 'Save base price' | 'Save customer price'; valueLabel: 'Base price value' | 'Customer price value';
}) {
  const [value, setValue] = useState(initial);
  return <form onSubmit={event => { event.preventDefault(); void save(value); }} className="flex gap-2">
    <input aria-label={valueLabel} inputMode="decimal" value={value} onChange={event => setValue(event.target.value)}
      className="input-field w-28" disabled={disabled} required maxLength={40} />
    <button className="btn-secondary" aria-label={saveLabel} disabled={disabled}>{saveLabel}</button>
  </form>;
}

export function RetailerPricingPage() {
  const [retailers, setRetailers] = useState<RetailerWithBinding[]>([]);
  const [customer, setCustomer] = useState<{ id: string; name: string } | null>(null);
  const [customerPage, setCustomerPage] = useState(1);
  const [customerPages, setCustomerPages] = useState(1);
  const [customersLoaded, setCustomersLoaded] = useState(false);
  const [customerError, setCustomerError] = useState('');
  const [page, setPage] = useState(1);
  useEffect(() => {
    let current = true;
    setCustomersLoaded(false); setCustomerError(''); setRetailers([]);
    void retailerService.getAll(customerPage, 100).then(response => {
      if (!current) return;
      setRetailers(response.data.data.items);
      setCustomerPages(response.data.data.pagination.pages);
      setCustomersLoaded(true);
    }).catch(e => { if (current) setCustomerError(normalizeApiError(e)); });
    return () => { current = false; };
  }, [customerPage]);

  return <div className="space-y-6">
    <PageHeader title="Base and Customer Pricing" description="Complete a positive base price first. An active customer price overrides it; retirement restores the base." />
    <label className="block">Customer
      <select aria-label="Customer" value={customer?.id || ''} disabled={!customersLoaded} onChange={e => {
        const selected = retailers.find(r => r.retailer.id === e.target.value)?.retailer;
        if (selected || !e.target.value) {
          setCustomer(selected ? { id: selected.id, name: selected.name } : null); setPage(1);
        }
      }} className="input-field max-w-md">
        <option value="">Select customer</option>
        {customer && !retailers.some(r => r.retailer.id === customer.id) &&
          <option value={customer.id}>{customer.name} (selected)</option>}
        {retailers.map(r => <option key={r.retailer.id} value={r.retailer.id}>{r.retailer.name}</option>)}
      </select>
    </label>
    {customer && <p>Current customer: {customer.name}</p>}
    <nav aria-label="Customer pagination" className="flex gap-3">
      <button aria-label="Previous customer page" disabled={customerPage <= 1} onClick={() => setCustomerPage(p => p - 1)}>Previous customers</button>
      <span>Customer page {customerPage} of {Math.max(customerPages, 1)}</span>
      <button aria-label="Next customer page" disabled={customerPage >= customerPages} onClick={() => setCustomerPage(p => p + 1)}>Next customers</button>
    </nav>
    {customerError && <p role="alert" className="text-red-700">{customerError}</p>}
    {!customerError && !customersLoaded && <p aria-live="polite">Loading customers...</p>}
    {customersLoaded && retailers.length === 0 && <p>No customers found.</p>}
    {!customer && <p role="status">Select a customer above to view and maintain base prices and customer-specific prices.</p>}
    {customer && <CustomerPrices key={customer.id + ':' + page} retailerId={customer.id} page={page} changePage={setPage} />}
  </div>;
}

// The keyed customer/page owns its editors; sequence checks also reject effect replays.
function CustomerPrices({ retailerId, page, changePage }: {
  retailerId: string; page: number; changePage: (page: number) => void;
}) {
  const user = useAuthStore(s => s.user);
  const writable = Boolean(user?.permissions.includes('pricing:write') || user?.roles.includes('admin'));
  const [rows, setRows] = useState<RetailerPriceView[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [total, setTotal] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const alive = useRef(false);
  const request = useRef(0);
  const writing = useRef(false);
  const ownsRequest = (sequence: number) => alive.current && sequence === request.current;
  const reload = async () => {
    const sequence = ++request.current;
    setLoaded(false); setError('');
    try {
      const response = await pricingService.getPrices(retailerId, page, 20);
      if (!ownsRequest(sequence)) return;
      setRows(response.data.data.items); setTotal(response.data.data.total); setLoaded(true);
    } catch (e) {
      if (ownsRequest(sequence)) setError(normalizeApiError(e));
    }
  };
  useEffect(() => {
    alive.current = true;
    void reload();
    return () => { alive.current = false; request.current += 1; };
  }, [retailerId, page]);
  const write = async (operation: () => Promise<unknown>) => {
    if (!alive.current || !loaded || !writable || writing.current) return;
    const sequence = request.current;
    writing.current = true;
    setBusy(true); setError('');
    try {
      await operation();
      if (ownsRequest(sequence)) await reload();
    } catch (e) {
      if (ownsRequest(sequence)) setError(normalizeApiError(e));
    } finally {
      writing.current = false;
      if (alive.current) setBusy(false);
    }
  };
  return <div className="space-y-6">
    {error && <p role="alert" className="text-red-700">{error}</p>}
    {!loaded && !error && <p aria-live="polite">Loading prices...</p>}
    {loaded && !error && rows.length === 0 && <p role="status">No sellable units found for the selected customer.</p>}
    {(rows.length > 0 || error) && <div className="overflow-x-auto rounded-xl border bg-white">
      <table className="min-w-full text-left text-sm">
        <thead><tr><th className="p-4">Sellable unit</th><th>Base price</th><th>Customer override</th><th>Effective price / source</th></tr></thead>
        <tbody>{rows.map(row => <tr key={row.sku_id + ':' + row.pricing_revision} className="border-t">
          <td className="p-4">{row.sku_name}<br />{row.sku_code}</td>
          <td className="p-4"><p>{formatMoney(row.base_price, row.currency)}</p>
            <PriceEditor initial={row.base_price || ''} disabled={busy || !loaded || !writable} saveLabel="Save base price" valueLabel="Base price value"
              save={value => write(() => pricingService.setBasePrice(row.sku_id, value, row.pricing_revision))} /></td>
          <td className="p-4"><p>{row.override_retired ? 'Retired: ' : ''}{formatMoney(row.override_price, row.currency)}</p>
            <PriceEditor initial={row.override_price || ''} disabled={busy || !loaded || !writable} saveLabel="Save customer price" valueLabel="Customer price value"
              save={value => write(() => pricingService.setPrice({ sku_id: row.sku_id, retailer_id: retailerId, price: value, expected_revision: row.pricing_revision }))} />
            {row.override_price && <button className="btn-secondary mt-2" disabled={busy || !loaded || !writable}
              onClick={() => void write(() => pricingService.setPrice({ sku_id: row.sku_id, retailer_id: retailerId, price: row.override_price!, expected_revision: row.pricing_revision, retire: !row.override_retired }))}>
              {row.override_retired ? 'Restore override' : 'Retire override'}
            </button>}</td>
          <td className="p-4">{row.unorderable_reason || formatMoney(row.price, row.currency)}<br />{row.price_source}</td>
        </tr>)}</tbody>
      </table>
    </div>}
    <nav aria-label="SKU pagination" className="flex gap-3"><button aria-label="Previous SKU page" disabled={page <= 1} onClick={() => changePage(page - 1)}>Previous</button>
      <span>SKU page {page}</span><button aria-label="Next SKU page" disabled={!loaded || page * 20 >= total} onClick={() => changePage(page + 1)}>Next</button></nav>
  </div>;
}
