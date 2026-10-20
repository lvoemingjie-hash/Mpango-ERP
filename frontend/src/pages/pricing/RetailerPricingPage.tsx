import { useEffect, useState } from 'react';
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
  const user = useAuthStore(s => s.user);
  const writable = Boolean(user?.permissions.includes('pricing:write') || user?.roles.includes('admin'));
  const [retailers, setRetailers] = useState<RetailerWithBinding[]>([]);
  const [retailerId, setRetailerId] = useState('');
  const [rows, setRows] = useState<RetailerPriceView[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const reload = async () => {
    if (!retailerId) return;
    setLoaded(false);
    const response = await pricingService.getPrices(retailerId, page, 20);
    setRows(response.data.data.items); setTotal(response.data.data.total); setLoaded(true);
  };
  useEffect(() => { void retailerService.getAll(1, 100).then(r => setRetailers(r.data.data.items)).catch(e => setError(normalizeApiError(e))); }, []);
  useEffect(() => { setRows([]); void reload().catch(e => setError(normalizeApiError(e))); }, [retailerId, page]);
  const write = async (operation: () => Promise<unknown>) => {
    setBusy(true); setError('');
    try { await operation(); await reload(); }
    catch (e) { setError(normalizeApiError(e)); }
    finally { setBusy(false); }
  };
  return <div className="space-y-6">
    <PageHeader title="Base and Customer Pricing" description="Complete a positive base price first. An active customer price overrides it; retirement restores the base." />
    <label className="block">Customer
      <select aria-label="Customer" value={retailerId} onChange={e => { setRetailerId(e.target.value); setPage(1); }} className="input-field max-w-md">
        <option value="">Select customer</option>
        {retailers.map(r => <option key={r.retailer.id} value={r.retailer.id}>{r.retailer.name}</option>)}
      </select>
    </label>
    {error && <p role="alert" className="text-red-700">{error}</p>}
    {!retailerId && <p role="status">Select a customer above to view and maintain base prices and customer-specific prices.</p>}
    {retailerId && loaded && !error && rows.length === 0 && <p role="status">No sellable units found for the selected customer.</p>}
    {retailerId && (!loaded || rows.length > 0 || error) && <div className="overflow-x-auto rounded-xl border bg-white">
      <table className="min-w-full text-left text-sm">
        <thead><tr><th className="p-4">Sellable unit</th><th>Base price</th><th>Customer override</th><th>Effective price / source</th></tr></thead>
        <tbody>{rows.map(row => <tr key={row.sku_id + ':' + row.pricing_revision} className="border-t">
          <td className="p-4">{row.sku_name}<br />{row.sku_code}</td>
          <td className="p-4"><p>{formatMoney(row.base_price, row.currency)}</p>
            <PriceEditor initial={row.base_price || ''} disabled={busy || !writable} saveLabel="Save base price" valueLabel="Base price value"
              save={value => write(() => pricingService.setBasePrice(row.sku_id, value, row.pricing_revision))} /></td>
          <td className="p-4"><p>{row.override_retired ? 'Retired: ' : ''}{formatMoney(row.override_price, row.currency)}</p>
            <PriceEditor initial={row.override_price || ''} disabled={busy || !writable} saveLabel="Save customer price" valueLabel="Customer price value"
              save={value => write(() => pricingService.setPrice({ sku_id: row.sku_id, retailer_id: retailerId, price: value, expected_revision: row.pricing_revision }))} />
            {row.override_price && <button className="btn-secondary mt-2" disabled={busy || !writable}
              onClick={() => void write(() => pricingService.setPrice({ sku_id: row.sku_id, retailer_id: retailerId, price: row.override_price!, expected_revision: row.pricing_revision, retire: !row.override_retired }))}>
              {row.override_retired ? 'Restore override' : 'Retire override'}
            </button>}</td>
          <td className="p-4">{row.unorderable_reason || formatMoney(row.price, row.currency)}<br />{row.price_source}</td>
        </tr>)}</tbody>
      </table>
    </div>}
    <div className="flex gap-3"><button disabled={page <= 1} onClick={() => setPage(p => p - 1)}>Previous</button>
      <span>{page}</span><button disabled={page * 20 >= total} onClick={() => setPage(p => p + 1)}>Next</button></div>
  </div>;
}
