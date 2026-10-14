import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { QuoteConsent } from '@/components/pricing/QuoteConsent';
import type { PendingQuoteSubmission } from '@/components/pricing/QuoteConsent';
import { clientOrderService } from '@/services/clientOrderService';
import { clientProductService } from '@/services/clientProductService';
import { useAuthStore } from '@/stores/authStore';
import { formatMoney } from '@/utils/printFormat';
import type { ClientProduct, ClientSellableUnit, ReorderPreview, ReorderSelection } from '@/types/client';
import type { ServerQuote } from '@/types/pricing';

interface AcceptedReorder extends PendingQuoteSubmission {
  version: 1;
  source_order_id: string;
  selections: ReorderSelection[];
  notes: string;
}

function readAccepted(storageKey: string, sourceId: string): AcceptedReorder | null {
  try {
    const stored = sessionStorage.getItem(storageKey);
    if (!stored) return null;
    const value = JSON.parse(stored) as AcceptedReorder;
    if (value.version !== 1 || value.source_order_id !== sourceId || typeof value.key !== 'string' || !value.key ||
      typeof value.notes !== 'string' || !Array.isArray(value.selections) || !value.selections.length ||
      !value.selections.every(selection => typeof selection.source_item_id === 'string' &&
        (selection.action === 'keep' || selection.action === 'remove' ||
          (selection.action === 'replace' && typeof selection.sellable_unit_id === 'string' &&
            Number.isInteger(selection.quantity) && selection.quantity > 0))) ||
      !value.quote || typeof value.quote.quote_token !== 'string' || typeof value.quote.total !== 'string' ||
      !Array.isArray(value.quote.lines) || !['KES', 'UGX'].includes(value.quote.currency)) {
      sessionStorage.removeItem(storageKey);
      return null;
    }
    return value;
  } catch { return null; }
}

const REASONS: Record<string, string> = {
  LEGACY_IDENTITY_UNRESOLVED: 'The historical product identity or unit could not be verified.',
  PACKAGING_IDENTITY_CHANGED: 'The current unit or package differs from this historical line.',
  SELLABLE_UNIT_NOT_FOUND: 'This sales unit is no longer available.',
  SELLABLE_UNIT_UNAVAILABLE: 'This product or sales unit is inactive.',
  BASE_PRICE_REQUIRED: 'A current base price has not been configured.',
  QUOTE_DUPLICATE_LINE: 'Two decisions select the same sales unit. Choose a different replacement or remove one line.',
  INVALID_QUANTITY: 'The requested quantity is not valid.',
};

function differenceLabel(delta: string, currency: string) {
  const signed = delta.startsWith('-') || delta.startsWith('+') || /^0(?:\.0+)?$/.test(delta) ? delta : `+${delta}`;
  return formatMoney(signed, currency);
}

/** Null/omitted unused fields and object-key order do not change a decision. */
function sameReorderSelection(left: ReorderSelection, right: ReorderSelection) {
  if (left.source_item_id !== right.source_item_id || left.action !== right.action) return false;
  return left.action !== 'replace' || (right.action === 'replace' &&
    left.sellable_unit_id === right.sellable_unit_id && left.quantity === right.quantity);
}

export function ReorderPage() {
  const { orderId } = useParams<{ orderId: string }>();
  const user = useAuthStore(state => state.user);
  if (!orderId || !user?.id || !user.tenant_id) return <p role="alert">Order not found.</p>;
  const storageKey = `mpango-s2-reorder:${user.tenant_id}:${user.id}:${orderId}`;
  return <ReorderFlow key={storageKey} sourceId={orderId} storageKey={storageKey} />;
}

function ReorderFlow({ sourceId, storageKey }: { sourceId: string; storageKey: string }) {
  const navigate = useNavigate();
  const [recovered] = useState(() => readAccepted(storageKey, sourceId));
  const [preview, setPreview] = useState<ReorderPreview | null>(null);
  const [selections, setSelections] = useState<ReorderSelection[]>(recovered?.selections || []);
  const [notes, setNotes] = useState(recovered?.notes || '');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [locked, setLocked] = useState(Boolean(recovered));
  const [reviewedIntent, setReviewedIntent] = useState('');
  const [pickerRow, setPickerRow] = useState<string | null>(null);
  const [products, setProducts] = useState<ClientProduct[]>([]);
  const [loadingProducts, setLoadingProducts] = useState(false);
  const [search, setSearch] = useState('');
  const [replacementLabels, setReplacementLabels] = useState<Record<string, string>>({});
  const liveIntent = useRef('');
  const intent = JSON.stringify({ sourceId, selections, notes });
  liveIntent.current = intent;
  const currentReview = reviewedIntent === intent;

  const clearAccepted = () => { try { sessionStorage.removeItem(storageKey); } catch { /* Memory retry still owns the key. */ } };

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        // Cached acceptance is shown only after a fresh authorized source preview.
        const result = (await clientOrderService.previewReorder(sourceId, recovered?.selections)).data.data;
        if (!active) return;
        const choices = recovered?.selections || result.rows.map(row => row.selection);
        setSelections(choices);
        setPreview(result);
        setReviewedIntent(JSON.stringify({ sourceId, selections: choices, notes: recovered?.notes || '' }));
      } catch (failure) {
        if (!active) return;
        const status = (failure as { response?: { status?: number } }).response?.status;
        if (status === 401 || status === 403 || status === 404) {
          clearAccepted();
          setError('Order not found or no longer available.');
        } else setError('Unable to load this order. Reload to retry.');
      } finally { if (active) setLoading(false); }
    };
    void load();
    return () => { active = false; };
    // The keyed flow owns one actor, tenant and source throughout its lifetime.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sourceId, storageKey, recovered]);

  useEffect(() => {
    if (!pickerRow) return;
    let active = true;
    setLoadingProducts(true);
    clientProductService.getAll(1, 50, { search: search || undefined })
      .then(result => { if (active) setProducts(result.data.data.items.filter(product => product.units.some(unit => unit.can_order))); })
      .catch(() => { if (active) setError('Failed to load replacement products. Please retry.'); })
      .finally(() => { if (active) setLoadingProducts(false); });
    return () => { active = false; };
  }, [pickerRow, search]);

  const review = async (): Promise<ServerQuote | null> => {
    const requestedIntent = intent;
    const result = (await clientOrderService.previewReorder(sourceId, selections)).data.data;
    if (liveIntent.current !== requestedIntent) return null;
    setPreview(result);
    setReviewedIntent(requestedIntent);
    return result.ready ? result.quote : null;
  };

  const decide = (selection: ReorderSelection) => {
    if (locked) return;
    setSelections(current => current.map(value => value.source_item_id === selection.source_item_id ? selection : value));
    setError('');
  };

  const replace = (product: ClientProduct, unit: ClientSellableUnit) => {
    if (!pickerRow || !preview || locked) return;
    const original = preview.rows.find(row => row.source_item_id === pickerRow);
    if (!original || original.original.sellable_unit_id === unit.sellable_unit_id) return;
    decide({ source_item_id: pickerRow, action: 'replace', sellable_unit_id: unit.sellable_unit_id,
      quantity: original.original.quantity });
    setReplacementLabels(current => ({ ...current,
      [pickerRow]: `${product.name} · ${unit.sku_code} · ${unit.package_quantity} × ${unit.unit}` }));
    setPickerRow(null);
  };

  if (loading) return <p className="py-6 text-sm text-gray-500">Loading historical order…</p>;
  if (!preview) return <div className="space-y-4">
    <Link to={`/client/orders/${sourceId}`} className="text-sm text-primary-700">Back to order</Link>
    <p role="alert" className="rounded-lg bg-red-50 p-4 text-sm text-red-700">{error || 'Order not found.'}</p>
  </div>;

  return <div className="min-w-0 space-y-4 break-words">
    <Link to={`/client/orders/${sourceId}`} className="text-sm text-primary-700">Back to historical order</Link>
    <h1 className="text-lg font-bold text-gray-900">Order again</h1>
    <p className="text-sm text-gray-600">Review every historical line and accept the complete current quote to create a new draft.
      Your historical order and payments remain unchanged. This draft does not reserve stock or confirm availability.</p>
    {error && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}
    {locked && <p role="status" className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
      An accepted request is awaiting a result. Its choices are retained; retry the same submission to find your draft.
    </p>}

    <section className="min-w-0 rounded-xl border border-gray-200 bg-white p-4 space-y-2" aria-label="Historical and current totals">
      <p className="text-sm">Historical total: <strong>{formatMoney(preview.historical_total, preview.historical_currency)}</strong></p>
      <p className="text-xs text-gray-500">Historical display order uses stable historical line IDs.</p>
      {currentReview && preview.ready && preview.current_total !== null ? <>
        <p className="text-sm">Current total: <strong>{formatMoney(preview.current_total, preview.current_currency)}</strong></p>
        {preview.delta !== null ? <p className="text-sm">Change from historical total: <strong>{differenceLabel(preview.delta, preview.current_currency)}</strong></p>
          : <p className="text-sm text-amber-800">Historical and current currencies cannot be compared. No price difference is calculated.</p>}
      </> : <p className="text-sm text-amber-800">A complete current total requires reviewing all selected lines. Handle unavailable lines explicitly.</p>}
    </section>

    <section className="space-y-3" aria-label="All historical lines">
      {preview.rows.map((row, index) => {
        const selection = selections.find(value => value.source_item_id === row.source_item_id) || row.selection;
        const reviewedSelection = sameReorderSelection(selection, row.selection);
        const reason = row.reason;
        const current = reviewedSelection ? row.current : null;
        return <article key={row.source_item_id} data-testid={`reorder-row-${row.source_item_id}`}
          className="min-w-0 rounded-xl border border-gray-200 bg-white p-4 space-y-2 break-words">
          <h2 className="text-sm font-semibold text-gray-900">Historical line {index + 1}: {row.original.product_name}</h2>
          <p className="text-xs font-mono text-gray-600">{row.original.sku_code}</p>
          <p className="text-sm text-gray-700">Historical: {row.original.quantity} × {row.original.display_label || row.original.unit || 'UNIT_UNVERIFIED'}
            {' '}(unit {row.original.unit || 'unverified'}, package {row.original.package_quantity || 'unverified'})
            {' '}at {formatMoney(row.original.unit_price, preview.historical_currency)} = {formatMoney(row.original.subtotal, preview.historical_currency)}</p>
          {reason && <p className="text-sm text-amber-900">{REASONS[reason] || 'This line cannot currently be included.'} <span className="font-mono text-xs">{reason}</span></p>}
          {selection.action === 'remove' ? <p className="text-sm font-medium text-red-700">Decision: explicitly removed from the new draft. The historical line remains visible.</p>
            : selection.action === 'replace' ? <div className="space-y-1 text-sm text-gray-700">
              <p>Decision: explicit replacement — {replacementLabels[row.source_item_id] || current?.product_name || selection.sellable_unit_id}</p>
              <p className="break-all text-xs">Selected sales unit: {selection.sellable_unit_id}</p>
              <label className="flex flex-wrap items-center gap-2">Requested replacement quantity
                <input type="number" min={1} max={10000} step={1} value={selection.quantity} disabled={locked}
                  onChange={event => { const quantity = Number(event.target.value); if (Number.isInteger(quantity) && quantity > 0)
                    decide({ ...selection, quantity }); }}
                  className="w-24 rounded-lg border border-gray-300 px-2 py-1" />
              </label>
            </div> : reason ? <p className="text-sm text-amber-900">Decision pending: this original line is selected. Explicitly remove it or choose a replacement before accepting a complete quote.</p>
              : <p className="text-sm text-gray-700">Decision: keep the verified original sales unit and requested quantity {row.original.quantity}.</p>}
          {current && selection.action !== 'remove' && <p className="text-sm text-gray-900">
            Current: {current.quantity} × {current.display_label} (unit {current.unit}, package {current.package_quantity})
            {' '}at {formatMoney(current.unit_price, preview.current_currency)} = {formatMoney(current.subtotal, preview.current_currency)}
          </p>}
          {row.stock_warning && reviewedSelection && selection.action !== 'remove' && <p className="text-sm text-amber-900">
            Stock is insufficient for the requested quantity. The draft keeps your full request and awaits supplier confirmation.
          </p>}
          {!reviewedSelection && <p className="text-xs text-amber-800">Selection changed. Review the complete current quote.</p>}
          <div className="flex flex-wrap gap-2">
            {selection.action !== 'keep' && <button type="button" disabled={locked}
              onClick={() => decide({ source_item_id: row.source_item_id, action: 'keep' })}
              className="btn-secondary whitespace-normal">Restore original line {index + 1}</button>}
            {selection.action !== 'remove' && <button type="button" disabled={locked}
              onClick={() => decide({ source_item_id: row.source_item_id, action: 'remove' })}
              className="btn-secondary whitespace-normal">Remove line {index + 1}</button>}
            <button type="button" disabled={locked} onClick={() => { setSearch(''); setPickerRow(row.source_item_id); }}
              className="btn-secondary whitespace-normal">Choose replacement for line {index + 1}</button>
          </div>
        </article>;
      })}
    </section>

    {pickerRow && <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 sm:items-center" role="dialog" aria-modal="true" aria-label="Choose replacement product">
      <div className="flex max-h-[75vh] w-full min-w-0 max-w-lg flex-col rounded-t-2xl bg-white p-4 sm:m-4 sm:rounded-2xl">
        <div className="mb-3 flex items-start justify-between gap-3">
          <h2 className="text-base font-semibold">Choose an explicit replacement</h2>
          <button type="button" onClick={() => setPickerRow(null)} aria-label="Close replacement picker">×</button>
        </div>
        <input aria-label="Search replacement products" value={search} onChange={event => setSearch(event.target.value)}
          className="mb-3 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm" placeholder="Search products…" />
        <div className="min-w-0 flex-1 space-y-2 overflow-y-auto">
          {loadingProducts && <p className="text-sm text-gray-500">Loading products…</p>}
          {!loadingProducts && products.length === 0 && <p className="text-sm text-gray-500">No available replacements found.</p>}
          {products.map(product => <div key={product.id} className="min-w-0 rounded-lg border border-gray-200 p-3">
            <p className="text-sm font-medium break-words">{product.name}</p>
            {product.units.filter(unit => unit.can_order &&
              unit.sellable_unit_id !== preview.rows.find(row => row.source_item_id === pickerRow)?.original.sellable_unit_id)
              .map(unit => <button key={unit.sellable_unit_id} type="button" disabled={locked}
                data-testid={`replacement-unit-${unit.sku_code}`} onClick={() => replace(product, unit)}
                className="mt-2 w-full rounded-lg bg-gray-50 p-3 text-left text-sm break-words">
                <span className="block">{unit.sku_code} · {unit.package_quantity} × {unit.unit}</span>
                <span className="block">{unit.price === null ? 'Current price unavailable' : formatMoney(unit.price, unit.currency)}</span>
              </button>)}
          </div>)}
        </div>
      </div>
    </div>}

    <label className="block text-sm font-medium text-gray-700">Notes for the new draft (optional)
      <textarea value={notes} disabled={locked} onChange={event => setNotes(event.target.value)} rows={2}
        className="mt-1 w-full rounded-xl border border-gray-300 p-3 text-sm" />
    </label>
    <QuoteConsent intent={intent} disabled={!selections.some(selection => selection.action !== 'remove')}
      initialPending={recovered} onLockChange={setLocked}
      onPendingChange={pending => {
        if (!pending) { clearAccepted(); return; }
        const accepted: AcceptedReorder = { ...pending, version: 1, source_order_id: sourceId, selections, notes };
        sessionStorage.setItem(storageKey, JSON.stringify(accepted));
      }}
      preview={async () => {
        const quote = await review();
        if (!quote) throw new Error('Review the unavailable lines and choose a replacement or explicitly remove them.');
        return quote;
      }}
      onStale={review}
      submit={async (quote, key) => {
        const result = await clientOrderService.submitReorder(sourceId,
          { selections, notes: notes || undefined, quote_token: quote.quote_token }, key);
        navigate(`/client/orders/${result.data.data.id}`, { replace: true });
      }} />
  </div>;
}
