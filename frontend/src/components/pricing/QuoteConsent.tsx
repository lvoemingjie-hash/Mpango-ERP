import { useEffect, useRef, useState } from 'react';
import type { ServerQuote } from '@/types/pricing';
import { formatMoney } from '@/utils/printFormat';
import { normalizeApiError } from '@/utils/errorHandling';

interface Props {
  intent: string;
  disabled?: boolean;
  replacing?: boolean;
  preview: () => Promise<ServerQuote>;
  submit: (quote: ServerQuote, key: string) => Promise<void>;
}

/** The retained pending closure owns the original accepted intent on an unknown result. */
export function QuoteConsent({ intent, disabled, replacing, preview, submit }: Props) {
  const [quote, setQuote] = useState<ServerQuote | null>(null);
  const [busy, setBusy] = useState(false);
  const [unknown, setUnknown] = useState(false);
  const [message, setMessage] = useState('');
  const sending = useRef(false);
  const liveIntent = useRef(intent);
  liveIntent.current = intent;
  const pending = useRef<{ quote: ServerQuote; key: string; send: Props['submit'] } | null>(null);

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
    if (!pending.current) pending.current = { quote: quote!, key: crypto.randomUUID(), send: submit };
    const accepted = pending.current;
    setBusy(true);
    try {
      await accepted.send(accepted.quote, accepted.key);
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
        pending.current = null; setUnknown(false);
        const detail = response.data?.details;
        if (response.data?.code === 'PRICE_PREVIEW_STALE' && detail?.quote) {
          setQuote(detail.quote);
          setMessage(`Price changed: ${detail.old_total} → ${detail.new_total}; difference ${detail.delta}. ` +
            (detail.changes || []).map(line => `${line.sku_id}: ${line.old_price} → ${line.new_price}`).join('; '));
        } else { setQuote(null); setMessage(response.data?.message || normalizeApiError(error)); }
      }
    } finally { sending.current = false; setBusy(false); }
  };

  return <section className="rounded-xl border border-gray-200 bg-white p-4 space-y-3" aria-label="Server quote">
    {message && <p role="alert" className="text-sm text-amber-800">{message}</p>}
    {replacing && <p className="text-sm text-amber-800">Accepting cancels the old draft and creates a new draft atomically. Its original amounts remain unchanged.</p>}
    {quote && <div className="space-y-2">
      {quote.lines.map(line => <p key={line.sku_id} className="text-sm">
        {line.product_name}: {line.quantity} × {line.display_label} ({line.unit}, package {line.package_quantity}):
        {' '}{formatMoney(line.unit_price, quote.currency)} = {formatMoney(line.subtotal, quote.currency)}
      </p>)}
      <p className="font-semibold">Server total: {formatMoney(quote.total, quote.currency)}</p>
    </div>}
    {!unknown && <button type="button" disabled={busy || disabled} onClick={refresh} className="btn-secondary">
      {busy ? 'Working...' : 'Review server quote'}
    </button>}
    {(quote || unknown) && <button type="button" disabled={busy || (!unknown && disabled)}
      onClick={accept} className="btn-primary ml-2">
      {unknown ? 'Retry same accepted submission' : replacing ? 'Accept and replace old draft' : 'Accept these prices and create draft'}
    </button>}
  </section>;
}
