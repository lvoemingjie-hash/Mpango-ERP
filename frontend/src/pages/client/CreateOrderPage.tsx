import { useState, useEffect, useRef } from 'react';
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeftIcon, TrashIcon, PlusIcon, ShoppingBagIcon } from '@heroicons/react/24/outline';
import { ProductImage } from '@/components/catalog/ProductImage';
import { OrderProductPicker } from '@/components/catalog/OrderProductPicker';
import { clientOrderService } from '@/services/clientOrderService';
import { QuoteConsent } from '@/components/pricing/QuoteConsent';
import { formatMoney } from '@/utils/printFormat';
import { useAuthStore } from '@/stores/authStore';
import { operationScope, ownsOperation, readPending, savePending, clearPending } from '@/utils/pendingClientOperation';
import type { PendingOperation } from '@/utils/pendingClientOperation';
import type { ClientProduct, ClientSellableUnit, CreateOrderItem } from '@/types/client';

interface OrderLineItem {
  sellable_unit_id: string;
  sku_code: string;
  name: string;
  quantity: number;
  price?: string | null;
  currency?: string | null;
  image?: ClientProduct['image'];
  package_quantity?: number;
  unit?: string;
}

export function CreateOrderPage() {
  const auth = useAuthStore();
  const [params] = useSearchParams();
  const replacing = params.get('replace');
  const scope = operationScope(replacing ? 'replace' : 'create', replacing || 'new');
  return <OrderEditor key={`${scope}:${auth.sessionGeneration}`} scope={scope} generation={auth.sessionGeneration} />;
}

function OrderEditor({ scope, generation }: { scope: string | null; generation: number }) {
  const location = useLocation();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const replacing = params.get('replace');
  const kind = replacing ? 'replace' : 'create';
  const [retained] = useState(() => readPending(scope, kind));
  const original = useRef<PendingOperation | null>(retained.value);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const owns = () => mounted.current && ownsOperation(kind, replacing || 'new', scope, generation);
  const [items, setItems] = useState<OrderLineItem[]>(() => {
    const saved = retained.value;
    return saved && saved.kind !== 'declare' ? saved.body.items.map(item => ({ ...item, sku_code: item.sku_code || item.sellable_unit_id,
      name: saved.quote.lines.find(line => line.sku_id === item.sellable_unit_id)?.product_name || item.sku_code || 'Selected product' })) : [];
  });
  const [notes, setNotes] = useState(retained.value && retained.value.kind !== 'declare' ? retained.value.body.notes || '' : '');
  const [createdId, setCreatedId] = useState<string | null>(null);
  const confirmedId = useRef<string | null>(null);
  const [cleanupError, setCleanupError] = useState('');
  const [showPicker, setShowPicker] = useState(false);
  const [quantityDrafts, setQuantityDrafts] = useState<Record<string, string>>({});
  const [editorLocked, setEditorLocked] = useState(Boolean(retained.value));

  useEffect(() => {
    const state = location.state as { items?: OrderLineItem[] } | null;
    if (state?.items && !retained.value) {
      setItems(state.items);
      setQuantityDrafts({});
    }
  }, [location.state]);

  const validQuantity = (value: string) => /^\d+$/.test(value) && Number.isSafeInteger(Number(value)) && Number(value) > 0;
  const hasInvalidQuantity = items.some(item => !validQuantity(quantityDrafts[item.sellable_unit_id] ?? String(item.quantity)));

  const updateQuantity = (id: string, value: string) => {
    if (editorLocked) return;
    setQuantityDrafts(current => ({ ...current, [id]: value }));
    if (validQuantity(value)) {
      setItems(current => current.map(item => item.sellable_unit_id === id ? { ...item, quantity: Number(value) } : item));
    }
  };

  const addUnit = (product: ClientProduct, unit: ClientSellableUnit) => {
    if (editorLocked) return;
    setItems(current => {
      const existing = current.find(item => item.sellable_unit_id === unit.sellable_unit_id);
      if (existing) return current.map(item => item === existing
        ? { ...item, quantity: Math.min(Number.MAX_SAFE_INTEGER, item.quantity + 1) } : item);
      return [...current, { sellable_unit_id: unit.sellable_unit_id, sku_code: unit.sku_code,
        name: product.name, quantity: 1, price: unit.price, currency: unit.currency,
        image: product.image, package_quantity: unit.package_quantity, unit: unit.unit }];
    });
    setQuantityDrafts(current => {
      const next = { ...current };
      delete next[unit.sellable_unit_id];
      return next;
    });
  };

  const removeItem = (id: string) => {
    if (editorLocked) return;
    setItems(current => current.filter(item => item.sellable_unit_id !== id));
    setQuantityDrafts(current => {
      const next = { ...current };
      delete next[id];
      return next;
    });
  };

  const orderItems: CreateOrderItem[] = items.map(item => ({
    sellable_unit_id: item.sellable_unit_id, sku_code: item.sku_code, quantity: item.quantity,
  }));

  if (createdId) return <section className="rounded-xl border bg-white p-4 space-y-3">
    <h1 className="text-lg font-semibold">Draft created</h1>
    {cleanupError && <p role="alert" className="text-sm text-amber-800">{cleanupError}</p>}
    <Link to={`/client/orders/${encodeURIComponent(createdId)}`} className="btn-primary inline-block">View created draft</Link>
  </section>;
  return <div className="space-y-4">
    <div className="flex items-center gap-3">
      <button type="button" aria-label="Back to products" disabled={editorLocked} onClick={() => navigate('/client')}
        className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-gray-500 hover:bg-gray-100 disabled:opacity-40">
        <ArrowLeftIcon className="h-5 w-5" aria-hidden="true" />
      </button>
      <div>
        <h1 className="text-lg font-bold text-gray-900">New Order</h1>
        <p className="text-sm text-gray-500">Choose packs, then review current prices.</p>
      </div>
    </div>

    {items.length === 0 ? <div className="rounded-xl border-2 border-dashed border-gray-300 bg-gray-50 p-8 text-center">
      <ShoppingBagIcon className="mx-auto h-10 w-10 text-gray-300" aria-hidden="true" />
      <p className="mt-2 text-sm font-medium text-gray-600">Start your order</p>
      <p className="mt-1 text-sm text-gray-500">Choose products and the pack sizes you need.</p>
    </div> : <section aria-label="Selected products" className="space-y-3">
      <h2 className="text-sm font-semibold text-gray-700">Your selection <span className="text-gray-500">({items.length} pack choices)</span></h2>
      {items.map(item => {
        const value = quantityDrafts[item.sellable_unit_id] ?? String(item.quantity);
        const invalid = !validQuantity(value);
        const labelId = `quantity-${item.sellable_unit_id}`;
        return <article key={item.sellable_unit_id} aria-label={`Selected ${item.sku_code}`} className="rounded-xl border border-gray-200 bg-white p-3 shadow-sm">
          <div className="flex items-start gap-3">
            <div className="h-16 w-16 shrink-0 overflow-hidden rounded-lg bg-gray-50">
              <ProductImage image={item.image} name={item.name} className="h-full w-full" />
            </div>
            <div className="min-w-0 flex-1">
              <h3 className="break-words text-sm font-semibold text-gray-900">{item.name}</h3>
              {item.unit && <p className="mt-0.5 text-sm text-gray-700">{item.package_quantity} &times; {item.unit}</p>}
              <p className="mt-0.5 break-all text-xs text-gray-500">{item.sku_code}</p>
              {item.price != null && <p className="mt-1 text-sm font-medium text-gray-700">{formatMoney(item.price, item.currency)} <span className="text-xs font-normal text-gray-500">per pack, indicative</span></p>}
            </div>
            <button type="button" aria-label={`Remove ${item.sku_code}`} disabled={editorLocked} onClick={() => removeItem(item.sellable_unit_id)}
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-gray-400 hover:bg-red-50 hover:text-red-600 disabled:opacity-40">
              <TrashIcon className="h-5 w-5" aria-hidden="true" />
            </button>
          </div>
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-gray-100 pt-3">
            <label htmlFor={labelId} className="text-sm text-gray-600">Number of packs</label>
            <div className="flex items-center rounded-lg border border-gray-300">
              <button type="button" aria-label={`Decrease ${item.sku_code}`} disabled={editorLocked || item.quantity <= 1} onClick={() => updateQuantity(item.sellable_unit_id, String(item.quantity - 1))}
                className="h-11 w-11 rounded-l-lg text-lg text-gray-600 hover:bg-gray-50 disabled:opacity-40">-</button>
              <input id={labelId} aria-label={`Quantity for ${item.sku_code}`} aria-invalid={invalid} aria-describedby={invalid ? `${labelId}-error` : undefined}
                inputMode="numeric" pattern="[0-9]*" autoComplete="off" value={value} disabled={editorLocked}
                onChange={event => updateQuantity(item.sellable_unit_id, event.target.value)}
                className="h-11 w-16 min-w-0 border-x border-gray-200 text-center text-base font-semibold outline-none focus:ring-2 focus:ring-inset focus:ring-primary-500 disabled:bg-gray-50" />
              <button type="button" aria-label={`Increase ${item.sku_code}`} disabled={editorLocked || item.quantity === Number.MAX_SAFE_INTEGER} onClick={() => updateQuantity(item.sellable_unit_id, String(item.quantity + 1))}
                className="h-11 w-11 rounded-r-lg text-lg text-gray-600 hover:bg-gray-50 disabled:opacity-40">+</button>
            </div>
          </div>
          {invalid && <p id={`${labelId}-error`} role="alert" className="mt-2 text-sm text-red-700">Enter a whole number of packs, at least 1.</p>}
        </article>;
      })}
    </section>}

    <button type="button" disabled={editorLocked} onClick={() => setShowPicker(true)}
      className="flex min-h-[48px] w-full items-center justify-center gap-2 rounded-xl border border-dashed border-primary-300 bg-primary-50 px-4 py-3 text-sm font-semibold text-primary-700 hover:bg-primary-100 disabled:opacity-40">
      <PlusIcon className="h-5 w-5" aria-hidden="true" /> Add Product
    </button>
    {showPicker && <OrderProductPicker selected={items} onAdd={addUnit} onClose={() => setShowPicker(false)} />}

    <div>
      <label htmlFor="order-notes" className="mb-1 block text-sm font-medium text-gray-700">Notes (optional)</label>
      <textarea id="order-notes" value={notes} disabled={editorLocked} onChange={event => setNotes(event.target.value)}
        placeholder="Any special instructions..." rows={2}
        className="w-full resize-none rounded-xl border border-gray-300 px-3 py-2 text-base shadow-sm outline-none focus:border-primary-500 focus:ring-1 focus:ring-primary-500 disabled:bg-gray-50" />
    </div>
    <p className="text-sm text-gray-500">Catalog prices are indicative. Review the server quote before accepting this draft.</p>
    {retained.error && <p role="alert" className="text-sm text-red-700">{retained.error}</p>}
    {retained.value && <p className="text-sm text-amber-800">An accepted order is awaiting a verified result. The quote below is the original request; recovery keeps its quantities and notes unchanged.</p>}
    <QuoteConsent
      intent={JSON.stringify({ orderItems, notes, quantityDrafts })}
      disabled={!owns() || Boolean(retained.error) || !items.length || hasInvalidQuantity}
      canSubmit={owns}
      initialPending={retained.value && retained.value.kind !== 'declare' ? retained.value : null}
      onPendingChange={pending => {
        if (!owns()) throw new Error('Session changed');
        if (!pending) {
          if (confirmedId.current) return;
          if (original.current) clearPending(original.current);
          original.current = null;
          return;
        }
        if (!scope || retained.error) throw new Error('Retention unavailable');
        const value: PendingOperation = { version: 1, scope, kind, key: pending.key, quote: pending.quote,
          body: { items: orderItems, ...(notes ? { notes } : {}), quote_token: pending.quote.quote_token } };
        savePending(value);
        original.current = JSON.parse(JSON.stringify(value)) as PendingOperation;
      }}
      onLockChange={setEditorLocked}
      replacing={Boolean(replacing)}
      preview={async () => (await clientOrderService.preview({ items: orderItems })).data.data}
      submit={async (quote, key) => {
        if (!owns()) throw new Error('Session changed');
        const saved = original.current;
        if (!saved || saved.kind === 'declare' || saved.key !== key || saved.quote.quote_token !== quote.quote_token) throw new Error('Original request unavailable');
        // Re-check persistence immediately before every write, including recovery.
        savePending(saved);
        const data = saved.body;
        const result = replacing
          ? await clientOrderService.replaceDraft(replacing, data, key)
          : await clientOrderService.create(data, key);
        if (!owns()) throw new Error('Session changed');
        if (typeof result.data.data.id !== 'string' || !result.data.data.id.trim()) throw new Error('Result unavailable');
        confirmedId.current = result.data.data.id;
        setCreatedId(result.data.data.id);
        try { clearPending(saved); }
        catch { setCleanupError('The draft was created, but local recovery data could not be cleared. Open this draft to check its result before starting another order.'); return; }
        original.current = null;
        navigate(`/client/orders/${encodeURIComponent(result.data.data.id)}`, { replace: true });
      }}
    />
  </div>;
}
