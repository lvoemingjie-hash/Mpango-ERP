import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { orderNegotiationService, type OrderNegotiation } from '@/services/orderNegotiationService';
import { useAuthStore } from '@/stores/authStore';
import { formatMoney } from '@/utils/printFormat';
import { normalizeApiError } from '@/utils/errorHandling';

interface PriceItem {
  sellable_unit_id: string | null;
  product_name: string;
  quantity: number;
  unit_price: string;
  unit_snapshot: string | null;
  package_quantity_snapshot?: string | null;
}

interface Props {
  orderId: string;
  items: PriceItem[];
  currency?: string | null;
  draft: boolean;
  client?: boolean;
  onAccepted?: (id: string) => void;
}

function deadlineLabel(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium', timeStyle: 'long',
  }).format(new Date(value));
}

export function OrderNegotiationPanel({ orderId, items, currency, draft, client = false, onAccepted }: Props) {
  const user = useAuthStore((state) => state.user);
  const [proposals, setProposals] = useState<OrderNegotiation[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const sending = useRef(false);
  const [prices, setPrices] = useState<Record<string, string>>({});
  const [deadline, setDeadline] = useState('');
  const [reviewed, setReviewed] = useState<string | null>(null);
  const [unknown, setUnknown] = useState<string | null>(null);
  const canAct = client
    ? Boolean(user?.permissions.includes('client:orders:read') && user?.permissions.includes('client:orders:create'))
    : Boolean(user?.permissions.includes('pricing:write') && user?.permissions.includes('orders:update'));

  useEffect(() => {
    let current = true;
    setLoaded(false); setError(''); setReviewed(null); setUnknown(null);
    orderNegotiationService.list(orderId, client).then((response) => {
      if (current) { setProposals(response.data.data.items); setLoaded(true); }
    }).catch((reason) => { if (current) setError(normalizeApiError(reason)); });
    return () => { current = false; };
  }, [orderId, client]);

  const reload = async () => {
    const response = await orderNegotiationService.list(orderId, client);
    setProposals(response.data.data.items); setLoaded(true);
  };

  const act = async (task: () => Promise<void>) => {
    if (sending.current) return;
    sending.current = true; setBusy(true); setError('');
    try { await task(); }
    catch (reason) { setError(normalizeApiError(reason)); }
    finally { sending.current = false; setBusy(false); }
  };

  const accept = async (proposal: OrderNegotiation) => act(async () => {
    if (!user?.id || !user.tenant_id) throw new Error('A current customer session is required.');
    const storageKey = `s3-accept:${user.tenant_id}:${user.id}:${proposal.id}`;
    const prior = sessionStorage.getItem(storageKey);
    const retained = prior ? JSON.parse(prior) as { key: string; digest: string; version: number } : {
      key: crypto.randomUUID(), digest: proposal.digest, version: proposal.version,
    };
    if (retained.digest !== proposal.digest || retained.version !== proposal.version || typeof retained.key !== 'string') {
      throw new Error('The retained accepted intent does not match this proposal.');
    }
    sessionStorage.setItem(storageKey, JSON.stringify(retained));
    setUnknown(proposal.id);
    const response = await orderNegotiationService.accept(orderId, proposal, retained.key);
    const result = response.data.data;
    if (result.id !== proposal.id || result.digest !== proposal.digest || !result.accepted_order_id || result.status !== 'accepted') {
      throw new Error('Acceptance result could not be verified. Retry the same request.');
    }
    setUnknown(null);
    await reload();
    onAccepted?.(result.accepted_order_id);
  });

  const pending = proposals.some((proposal) => proposal.status === 'pending');
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  return <section aria-label="Negotiated prices" className="space-y-4 rounded-xl border border-amber-200 bg-amber-50/40 p-4">
    <div>
      <h2 className="text-base font-semibold text-gray-900">Negotiated prices</h2>
      <p className="mt-1 text-sm text-gray-600">Accepting creates a replacement draft. The merchant must confirm it before the deadline. Nothing is reserved or charged on acceptance.</p>
    </div>
    {error && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</p>}
    {!loaded && !error && <p role="status" className="text-sm text-gray-500">Loading proposals...</p>}
    {loaded && proposals.length === 0 && <p className="text-sm text-gray-500">No negotiated proposal for this order.</p>}
    {proposals.map((proposal) => <article key={proposal.id} className="space-y-3 rounded-lg border border-gray-200 bg-white p-3">
      <div className="flex flex-wrap justify-between gap-2 text-sm">
        <strong>Proposal {proposal.version}</strong>
        <span>{proposal.status}{proposal.expired ? ' - deadline passed' : ''}</span>
      </div>
      <p className="text-sm text-gray-700">Accept and confirm before <time dateTime={proposal.expires_at}>{deadlineLabel(proposal.expires_at)}</time></p>
      <ul className="divide-y divide-gray-100">
        {proposal.lines.map((line) => {
          const original = proposal.original_lines.find((item) => item.sku_id === line.sku_id);
          return <li key={line.sku_id} className="space-y-1 py-2 text-sm">
            <p className="font-medium break-words">{line.product_name}</p>
            <p className="text-gray-500">{line.quantity} {line.display_label || line.unit}, package {line.package_quantity}</p>
            <p>{formatMoney(original?.unit_price ?? '', proposal.currency)} → <strong>{formatMoney(line.unit_price, proposal.currency)}</strong> each</p>
            <p className="text-right">Line total: {formatMoney(line.subtotal, proposal.currency)}</p>
          </li>;
        })}
      </ul>
      <p className="flex flex-wrap justify-between gap-2 border-t pt-3 text-sm"><span>Original: {formatMoney(proposal.original_total, proposal.currency)}</span><strong>Agreed total: {formatMoney(proposal.total, proposal.currency)}</strong></p>
      {proposal.accepted_order_id && <Link className="inline-block py-2 text-sm font-semibold text-primary-700 underline" to={client ? `/client/orders/${proposal.accepted_order_id}` : '/orders'}>Open accepted replacement draft</Link>}
      {client && canAct && proposal.status === 'pending' && draft && <>
        <label className="flex items-start gap-3 py-2 text-sm">
          <input type="checkbox" className="mt-1 h-5 w-5" checked={reviewed === proposal.id} disabled={busy || Boolean(unknown)} onChange={(event) => setReviewed(event.target.checked ? proposal.id : null)} />
          I agree to these exact prices and the confirmation deadline.
        </label>
        {unknown === proposal.id && <p role="status" className="text-sm text-amber-800">Result unknown. Retry the SAME acceptance; do not create another order.</p>}
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <button className="min-h-11 rounded-lg bg-primary-600 px-4 py-3 text-sm font-semibold text-white disabled:opacity-50" disabled={busy || (unknown !== proposal.id && (reviewed !== proposal.id || proposal.expired))} onClick={() => accept(proposal)}>{unknown === proposal.id ? 'Retry same acceptance' : 'Accept agreed prices'}</button>
          <button className="min-h-11 rounded-lg border border-gray-300 px-4 py-3 text-sm disabled:opacity-50" disabled={busy || Boolean(unknown)} onClick={() => act(async () => { await orderNegotiationService.reject(orderId, proposal); await reload(); })}>Reject proposal</button>
        </div>
      </>}
      {!client && canAct && proposal.status === 'pending' && draft && <button className="min-h-11 rounded-lg border px-4 py-2 text-sm" disabled={busy} onClick={() => act(async () => { await orderNegotiationService.withdraw(orderId, proposal); await reload(); })}>Withdraw proposal</button>}
    </article>)}
    {!client && canAct && draft && loaded && !pending && <form className="space-y-3 border-t border-amber-200 pt-4" onSubmit={(event) => {
      event.preventDefault();
      void act(async () => {
        const expiry = new Date(deadline);
        if (!deadline || !Number.isFinite(expiry.getTime())) throw new Error('Enter an explicit deadline in your displayed timezone.');
        if (items.some((item) => !item.sellable_unit_id)) throw new Error('Replace this legacy draft with verified items first.');
        await orderNegotiationService.propose(orderId, items.map((item) => ({ sku_id: item.sellable_unit_id!, unit_price: prices[item.sellable_unit_id!] ?? item.unit_price })), expiry.toISOString());
        setDeadline(''); await reload();
      });
    }}>
      <h3 className="font-semibold text-sm">Offer new unit prices</h3>
      {items.map((item, index) => <label key={item.sellable_unit_id || index} className="block space-y-1 text-sm">
        <span>{item.product_name} - {item.quantity} {item.unit_snapshot}, package {item.package_quantity_snapshot}</span>
        <span className="block text-xs text-gray-500">Original: {formatMoney(item.unit_price, currency)}</span>
        <input aria-label={`Proposed unit price for ${item.product_name}`} className="min-h-11 w-full rounded-lg border border-gray-300 px-3 py-2" required inputMode="decimal" type="text" value={prices[item.sellable_unit_id || ''] ?? item.unit_price} onChange={(event) => setPrices({ ...prices, [item.sellable_unit_id || '']: event.target.value })} />
      </label>)}
      <label className="block space-y-1 text-sm"><span>Accept and confirm deadline ({timezone})</span><input className="min-h-11 w-full rounded-lg border border-gray-300 px-3 py-2" type="datetime-local" required value={deadline} onChange={(event) => setDeadline(event.target.value)} /></label>
      <button className="min-h-11 w-full rounded-lg bg-primary-600 px-4 py-3 text-sm font-semibold text-white disabled:opacity-50" disabled={busy || !deadline}>Send price proposal</button>
    </form>}
  </section>;
}
