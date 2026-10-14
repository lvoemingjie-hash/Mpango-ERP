import { useEffect, useRef, useState } from 'react';
import type { ServerQuote } from '@/types/pricing';
import { formatMoney } from '@/utils/printFormat';
import { normalizeApiError } from '@/utils/errorHandling';

export interface PendingQuoteSubmission {
  quote: ServerQuote;
  key: string;
}

interface Props {
  intent: string;
  disabled?: boolean;
  replacing?: boolean;
  preview: () => Promise<ServerQuote>;
  submit: (quote: ServerQuote, key: string) => Promise<void>;
  /** S2 can restore a previously accepted request after checking source authorization. */
  initialPending?: PendingQuoteSubmission | null;
  onPendingChange?: (pending: PendingQuoteSubmission | null) => void;
  onLockChange?: (locked: boolean) => void;
  /** S2 must refresh row eligibility along with the changed economic quote. */
  onStale?: () => Promise<ServerQuote | null>;
}

/** The retained pending closure owns the original accepted intent on an unknown result. */
export function QuoteConsent({ intent, disabled, replacing, preview, submit,
  initialPending, onPendingChange, onLockChange, onStale }: Props) {
  const [quote, setQuote] = useState<ServerQuote | null>(initialPending?.quote || null);
  const [busy, setBusy] = useState(false);
  const [unknown, setUnknown] = useState(Boolean(initialPending));
  const [message, setMessage] = useState(initialPending
    ? 'Result unknown. Retry the SAME accepted order; do not create a second order.' : '');
  const sending = useRef(false);
  const liveIntent = useRef(intent);
  liveIntent.current = intent;
  const pending = useRef<(PendingQuoteSubmission & {
    send: Props['submit']; persist?: Props['onPendingChange'];
  }) | null>(initialPending ? { ...initialPending, send: submit, persist: onPendingChange } : null);

  useEffect(() => {
    if (!pending.current) { setQuote(null); setMessage(''); }
  }, [intent]);

  const refresh = async () => {
    const requestedIntent = intent;
    setBusy(true); setMessage('');
    try {
      const result = await preview();
      if (liveIntent.current === requestedIntent) setQuote(result);
    }
    catch (error) { setMessage(normalizeApiError(error)); }
    finally { setBusy(false); }
  };
  const accept = async () => {
    if (sending.current) return;
    if (!quote && !pending.current) return;
    sending.current = true;
    if (!pending.current) {
      const accepted = { quote: quote!, key: crypto.randomUUID(), send: submit, persist: onPendingChange };
      try { accepted.persist?.({ quote: accepted.quote, key: accepted.key }); }
      catch {
        sending.current = false;
        setMessage('Unable to retain this accepted request. Please retry before submitting.');
        return;
      }
      pending.current = accepted;
    }
    const accepted = pending.current;
    onLockChange?.(true);
    setBusy(true);
    try {
      await accepted.send(accepted.quote, accepted.key);
      accepted.persist?.(null);
      pending.current = null; setUnknown(false);
    } catch (error) {
      const response = (error as { response?: { status?: number; data?: { code?: string; message?: string; details?: {
        code?: string; old_total?: string; new_total?: string; delta?: string; quote?: ServerQuote;
        changes?: { sku_id: string; old_price: string; new_price: string }[];
      } } } }).response;
      if (!response || (response.status || 0) >= 500 || response.status === 408) {
        setUnknown(true);
        setMessage('Result unknown. Retry the SAME accepted order; do not create a second order.');
      } else {
        accepted.persist?.(null);
        pending.current = null; setUnknown(false);
        const detail = response.data?.details;
        if ((response.data?.code === 'PRICE_PREVIEW_STALE' || response.data?.code === 'REORDER_PREVIEW_STALE') && detail?.quote) {
          try { setQuote(onStale ? await onStale() : detail.quote); }
          catch (refreshError) { setQuote(null); setMessage(normalizeApiError(refreshError)); return; }
          setMessage(`Price changed: ${detail.old_total} → ${detail.new_total}; difference ${detail.delta}. ` +
            (detail.changes || []).map(line => `${line.sku_id}: ${line.old_price} → ${line.new_price}`).join('; '));
        } else if (response.data?.code === 'REORDER_SELECTION_UNAVAILABLE' && onStale) {
          try { setQuote(await onStale()); }
          catch (refreshError) { setQuote(null); setMessage(normalizeApiError(refreshError)); return; }
          setMessage(response.data?.message || 'A selected line is no longer available. Review its current reason.');
        } else { setQuote(null); setMessage(response.data?.message || normalizeApiError(error)); }
      }
    } finally { sending.current = false; setBusy(false); onLockChange?.(Boolean(pending.current)); }
  };

  return <section className="min-w-0 rounded-xl border border-gray-200 bg-white p-4 space-y-3 break-words" aria-label="Server quote">
    {message && <p role="alert" className="text-sm text-amber-800">{message}</p>}
    {replacing && <p className="text-sm text-amber-800">Accepting cancels the old draft and creates a new draft atomically. Its original amounts remain unchanged.</p>}
    {quote && <div className="space-y-2">
      {quote.lines.map(line => <p key={line.sku_id} className="text-sm">
        {line.product_name}: {line.quantity} × {line.display_label} ({line.unit}, package {line.package_quantity}):
        {' '}{formatMoney(line.unit_price, quote.currency)} = {formatMoney(line.subtotal, quote.currency)}
      </p>)}
      <p className="font-semibold">Server total: {formatMoney(quote.total, quote.currency)}</p>
    </div>}
    <div className="flex flex-wrap gap-2">
    {!unknown && <button type="button" disabled={busy || disabled} onClick={refresh} className="btn-secondary whitespace-normal">
      {busy ? 'Working...' : 'Review server quote'}
    </button>}
    {(quote || unknown) && <button type="button" disabled={busy || (!unknown && disabled)}
      onClick={accept} className="btn-primary whitespace-normal">
      {unknown ? 'Retry same accepted submission' : replacing ? 'Accept and replace old draft' : 'Accept these prices and create draft'}
    </button>}
    </div>
  </section>;
}
