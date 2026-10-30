/** Retailer payment declaration submission (DC-12R1-S3-S2B-I2B). */
import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { clientOrderService } from '@/services/clientOrderService';
import { submitDeclaration } from '@/services/declarationService';
import { useAuthStore } from '@/stores/authStore';
import { operationScope, ownsOperation, readPending, savePending, clearPending, retentionError } from '@/utils/pendingClientOperation';
import type { PendingOperation } from '@/utils/pendingClientOperation';

/**
 * Fixed, status-derived public copy for a declaration submission failure
 * (DC-12R1-MVP-R0-R1 / WPR-003).
 *
 * Deliberately consults ONLY the coarse HTTP status (and a no-response /
 * network signal) — never the response body, ``data.message``, ``data.code``,
 * headers, schema names, internal ids, or the raw ``Error.message``. This
 * mirrors the established ``sanitizePrintError`` contract and guarantees a
 * malicious or verbose backend payload can never reach the declaration UI.
 */
function neutralDeclarationError(err: unknown): string {
  const status = (err as { response?: { status?: number } })?.response?.status;
  if (status === 401) return 'Your session has expired. Please sign in and try again.';
  if (status === 403) return 'You are not allowed to declare payments for this order.';
  if (status === 404) return 'This order is not available for declaration.';
  if (status === 409) return 'This declaration could not be processed. Please review and try again.';
  if (status !== undefined && status >= 400 && status < 500) {
    return 'We could not process your declaration. Please check your input and try again.';
  }
  // 5xx, network, timeout, or fully unknown — uniform neutral fallback.
  return 'We could not submit your declaration right now. Please try again later.';
}

export default function DeclarePaymentPage() {
  const { orderId = '' } = useParams<{ orderId: string }>();
  const auth = useAuthStore();
  const scope = operationScope('declare', orderId);
  return <DeclarationForm key={`${scope}:${auth.sessionGeneration}`} orderId={orderId} scope={scope} generation={auth.sessionGeneration} />;
}

function DeclarationForm({ orderId, scope, generation }: { orderId: string; scope: string | null; generation: number }) {
  const navigate = useNavigate();
  const [retained] = useState(() => readPending(scope, 'declare'));
  const initial = retained.value?.kind === 'declare' ? retained.value : null;
  const [pending, setPending] = useState(initial);
  const original = useRef(initial);
  const mounted = useRef(true);
  const owns = () => mounted.current && ownsOperation('declare', orderId, scope, generation);
  const [currency, setCurrency] = useState<string | null>(null);
  const [currencyLoaded, setCurrencyLoaded] = useState(false);
  const [currencyAttempt, setCurrencyAttempt] = useState(0);
  useEffect(() => {
    mounted.current = true;
    let active = true;
    setCurrencyLoaded(false);
    if (owns()) clientOrderService.getById(orderId).then(res => {
      if (active && owns()) setCurrency(res.data.data.currency === 'KES' || res.data.data.currency === 'UGX' ? res.data.data.currency : null);
    }).catch(() => { if (active && owns()) setCurrency(null); })
      .finally(() => { if (active && owns()) setCurrencyLoaded(true); });
    return () => { active = false; mounted.current = false; };
  }, [orderId, currencyAttempt]);
  const [amount, setAmount] = useState(initial?.body.declared_amount || '');
  const [method, setMethod] = useState<'cash' | 'transfer'>(initial?.body.method || 'cash');
  const [transferRef, setTransferRef] = useState(initial?.body.transfer_reference || '');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [rejected, setRejected] = useState(false);
  const [completed, setCompleted] = useState(false);
  // Lazy initialization: a remount with a pending operation consumes no new key.
  const [initialKey] = useState(() => initial?.key || crypto.randomUUID());
  const idempotencyKeyRef = useRef(initialKey);
  const submittingRef = useRef(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (submittingRef.current || completed || !owns() || retained.error || !scope) return;
    if (!original.current && (!currencyLoaded || !currency)) {
      setError('The order currency must be verified before a new declaration.'); return;
    }
    if (!original.current && (!/^\d+(\.\d+)?$/.test(amount) || !/[1-9]/.test(amount))) {
      setError('Enter a positive payment amount.'); return;
    }
    if (!original.current && method === 'transfer' && !transferRef.trim()) {
      setError('Enter the transfer reference from your payment record.'); return;
    }
    const saved: Extract<PendingOperation, { kind: 'declare' }> = original.current || {
      version: 1, scope, kind: 'declare', key: idempotencyKeyRef.current,
      currency: currency === 'KES' || currency === 'UGX' ? currency : null,
      body: { declared_amount: amount, method, ...(method === 'transfer' ? { transfer_reference: transferRef.trim() } : {}) },
    };
    try { savePending(saved); }
    catch { setError(retentionError); return; }
    original.current = saved; setPending(saved);
    submittingRef.current = true; setLoading(true); setError(''); setRejected(false);
    try {
      // Even legacy-currency recovery must reach the existing authenticated
      // backend with the original exact body. Browser state cannot approve it.
      const response = await submitDeclaration(orderId, saved.body, saved.key);
      if (!owns()) return;
      if (typeof response?.data?.id !== 'string' || !response.data.id.trim() || response.data.order_id !== orderId) throw new Error('Unverified response');
      setCompleted(true);
      try { clearPending(saved); }
      catch { setError('Declaration submitted. Local recovery data could not be cleared; open the order to check it before declaring again.'); return; }
      original.current = null; setPending(null);
      idempotencyKeyRef.current = crypto.randomUUID();
      navigate(`/client/orders/${orderId}`);
    } catch (err: unknown) {
      if (!owns()) return;
      setError(neutralDeclarationError(err));
      const status = (err as { response?: { status?: number } })?.response?.status;
      // Only explicit input rejection permits a user-chosen fresh operation.
      // A conflict, access failure or lost response never silently rotates it.
      setRejected(status === 400 || status === 422);
    } finally {
      submittingRef.current = false;
      if (mounted.current) setLoading(false);
    }
  };
  const startNew = () => {
    if (!owns() || !original.current || !rejected) return;
    try { clearPending(original.current); }
    catch { setError(retentionError); return; }
    original.current = null; setPending(null); setRejected(false); setError('');
    idempotencyKeyRef.current = crypto.randomUUID();
  };
  const locked = Boolean(pending) || loading || completed;
  return (
    <div className="min-h-screen bg-gray-50 p-4">
      <h1 className="text-lg font-semibold text-gray-900 mb-4">Declare Payment</h1>
      <p className="text-sm text-gray-500 mb-4 break-all">Order: {orderId}</p>
      <p className="text-sm text-gray-600 mb-4">Record money you have already paid. Your supplier must verify receipt; a declaration is not a confirmed payment.</p>
      {pending && !completed && <p role="status" className="mb-4 text-sm text-amber-800">The original declaration is retained in this tab. Its result needs checking. Recover it below without changing the amount or submitting another copy.</p>}
      {!currency && !pending && <p className="mb-3 text-sm text-amber-800">{currencyLoaded ? 'Currency unavailable. Ask your supplier to verify this order.' : 'Checking order currency…'}
        <button type="button" onClick={() => setCurrencyAttempt(n => n + 1)} className="ml-2 underline">Retry currency check</button></p>}
      <form onSubmit={handleSubmit} className="bg-white rounded-xl shadow p-6 space-y-4">
        {(error || retained.error) && <div role="alert" className="bg-red-50 text-red-700 text-sm p-3 rounded">{error || retained.error}</div>}
        <div>
          <label htmlFor="amount" className="block text-sm font-medium text-gray-700 mb-1">Amount ({pending ? pending.currency || 'currency unverified' : currency || 'currency unverified'})</label>
          <input id="amount" type="text" inputMode="decimal" required disabled={locked} value={amount} onChange={e => setAmount(e.target.value)}
            className="w-full rounded-lg border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500" />
        </div>
        <div>
          <label htmlFor="declaration-method" className="block text-sm font-medium text-gray-700 mb-1">Method</label>
          <select id="declaration-method" disabled={locked} value={method} onChange={e => setMethod(e.target.value as 'cash' | 'transfer')}
            className="w-full rounded-lg border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500">
            <option value="cash">Cash</option><option value="transfer">Transfer</option>
          </select>
        </div>
        {method === 'transfer' && <div>
          <label htmlFor="transfer-reference" className="block text-sm font-medium text-gray-700 mb-1">Transfer Reference</label>
          <input id="transfer-reference" type="text" required={!pending} disabled={locked} maxLength={128} value={transferRef} onChange={e => setTransferRef(e.target.value)}
            aria-describedby="transfer-reference-help" className="w-full rounded-lg border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500" />
          <p id="transfer-reference-help" className="mt-1 text-xs text-gray-500">Use the reference on your bank or mobile transfer record.</p>
        </div>}
        {!completed && <button type="submit" disabled={loading || !owns() || Boolean(retained.error) || (!pending && !currency)}
          className="w-full bg-indigo-600 text-white py-2 px-4 rounded-lg hover:bg-indigo-700 disabled:opacity-50">
          {loading ? 'Submitting...' : pending ? 'Recover original declaration' : 'Submit Declaration'}
        </button>}
        {rejected && <button type="button" onClick={startNew} className="btn-secondary">Edit rejected input and start a new declaration</button>}
        {completed && <button type="button" onClick={() => navigate(`/client/orders/${orderId}`)} className="btn-primary">View order and declarations</button>}
      </form>
    </div>
  );
}
