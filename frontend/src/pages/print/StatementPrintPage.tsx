/**
 * DC-12R1-S3-S2B-I2C-I2B — Contract D: printable relationship account
 * statement (read-only).
 *
 * Renders ONLY server-authoritative fields from GET /client/statements/print
 * (retailer) or GET /statements/print (cashier). No money is recomputed,
 * summed, or rounded — every balance/total/movement/payment amount is a server
 * decimal string rendered via string-only grouping (utils/printFormat).
 *
 * The document structure is FIXED by the backend view:
 *   - opening_balance (receivable sum strictly before the period),
 *   - movements[] (inclusive EAT period) with charge_total / collection_total /
 *     net_movement derived server-side ONLY from those movements,
 *   - closing_balance = opening + net_movement (computed server-side),
 *   - settled_payments[] as an INDEPENDENT list (never cross-associated with a
 *     movement), and
 *   - pending_declarations[] rendered ONLY when explicitly requested
 *     (?include_pending=true); they are non-accounting and never affect
 *     balances.
 *
 * `mode` is fixed by the static route config (never a query param). Query
 * params (from/to/retailer_id/include_pending) are read-only inputs for the
 * GET; they never switch mode, never carry money, and are encoded by the
 * service. Failures (401/403/404/409/5xx) collapse to fixed neutral copy via
 * sanitizePrintError — never internal codes, schema names, or another party's
 * data. Browser print is window.print() + print CSS.
 *
 * R1 (truth closure):
 *  - Default/monthly ranges use Africa/Nairobi (EAT) calendar dates, never
 *    browser-local dates (utils/printFormat eat* helpers).
 *  - A 400 (INVALID_DATE_RANGE / STATEMENT_RANGE_TOO_LARGE) shows the fixed
 *    neutral "Choose a shorter date range." — status-only, no body echo.
 *  - The printable DOM never shows a full UUID: order/declaration references
 *    are truncated to short 8-char references. receipt_number (RCT-…) is a
 *    canonical identifier, not a UUID, and is rendered verbatim.
 *  - Movements render the server-classified kind (charge/collection) and
 *    display_amount=abs(signed_amount) verbatim; settled_total is rendered
 *    server-side-only. No client financial arithmetic anywhere.
 */
import { useCallback, useEffect, useState } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { PrinterIcon, ArrowLeftIcon } from '@heroicons/react/24/outline';
import { getRetailerStatementPrint, getSupplierStatementPrint } from '@/services/statementService';
import { sanitizePrintError } from '@/utils/printError';
import { formatKes, formatPrintDate, eatDefaultRange } from '@/utils/printFormat';
import type { StatementPrintView } from '@/types/statement';

interface StatementPrintPageProps {
  /** Fixed by static route config: 'client' (retailer) or 'cashier' (wholesaler). */
  mode: 'client' | 'cashier';
}

/** Short display reference (R1): never expose a full UUID in the DOM. */
function shortRef(id: string | null | undefined): string {
  if (!id) return '—';
  return id.length > 8 ? id.slice(0, 8) : id;
}

/** Fixed neutral copy for a 400 (INVALID_DATE_RANGE / STATEMENT_RANGE_TOO_LARGE). */
const SHORTER_RANGE_COPY = 'Choose a shorter date range.';

export function StatementPrintPage({ mode }: StatementPrintPageProps) {
  const [searchParams] = useSearchParams();
  const [doc, setDoc] = useState<StatementPrintView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const from = searchParams.get('from') ?? '';
  const to = searchParams.get('to') ?? '';
  const includePending = searchParams.get('include_pending') === 'true';
  // Supplier-side target selector (server derives the authority from the
  // active binding under the token tenant; see Contract D route rules).
  const retailerId = mode === 'cashier' ? searchParams.get('retailer_id') ?? '' : '';

  const load = useCallback(async () => {
    // R1 rule 6: the default range is Africa/Nairobi calendar dates (never
    // browser-local dates).
    const { from: f, to: t } = from && to ? { from, to } : eatDefaultRange();
    if (mode === 'cashier' && !retailerId) {
      setDoc(null);
      setError('This document is not available.');
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res =
        mode === 'client'
          ? await getRetailerStatementPrint(f, t, includePending)
          : await getSupplierStatementPrint(retailerId, f, t, includePending);
      setDoc(res.data);
    } catch (err) {
      setDoc(null);
      // 401/403/404/409/5xx all collapse to fixed neutral strings; a 409
      // (period/ledger/reconciliation) is deliberately indistinguishable
      // from any other not-available case in the UI. A 400 (invalid date
      // range / range too large) shows the fixed shorter-range copy —
      // status-only, never echoing the body.
      const status = (err as { response?: { status?: number } })?.response?.status;
      setError(status === 400 ? SHORTER_RANGE_COPY : sanitizePrintError(err));
    } finally {
      setLoading(false);
    }
  }, [mode, from, to, retailerId, includePending]);

  useEffect(() => {
    load();
  }, [load]);

  const handlePrint = () => {
    window.print();
  };

  const backHref = mode === 'client' ? '/client/finance' : '/finance';

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-6 print:max-w-none print:px-0 print:py-0">
      {/* Chrome (hidden in print) */}
      <div className="no-print mb-4 flex items-center justify-between">
        <Link
          to={backHref}
          className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700"
        >
          <ArrowLeftIcon className="h-4 w-4" />
          Back to finance
        </Link>
        <button
          type="button"
          onClick={handlePrint}
          disabled={loading || !!error || !doc}
          className="inline-flex items-center gap-1.5 rounded-lg bg-primary-600 px-3 py-2 text-sm font-medium text-white shadow-sm hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition"
          data-testid="statement-print-button"
        >
          <PrinterIcon className="h-4 w-4" />
          Print
        </button>
      </div>

      {loading && (
        <div className="space-y-3 animate-pulse" role="status" aria-live="polite">
          <div className="h-6 w-1/3 rounded bg-gray-200" />
          <div className="h-40 rounded-xl bg-gray-200" />
        </div>
      )}

      {!loading && error && (
        <div
          className="rounded-lg bg-gray-50 p-4 text-sm text-gray-700"
          role="alert"
          data-testid="statement-print-error"
        >
          {error}
        </div>
      )}

      {!loading && !error && doc && (
        <article
          className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm print:border-0 print:shadow-none print:p-0"
          data-testid="statement-print-document"
        >
          <header className="border-b border-gray-200 pb-4">
            <h1 className="text-xl font-bold text-gray-900">Relationship Account Statement</h1>
            <p className="mt-1 text-xs text-gray-500">
              Period {doc.period_from} to {doc.period_to}
            </p>
            <p className="mt-1 text-xs text-gray-500">
              Generated {formatPrintDate(doc.generated_at_eat || doc.generated_at)}
            </p>
          </header>

          <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
            <dt className="text-gray-500">Supplier</dt>
            <dd className="text-gray-900">{doc.supplier_name}</dd>
            <dt className="text-gray-500">Retailer</dt>
            <dd className="text-gray-900">{doc.retailer_name}</dd>
          </dl>

          {/* Server-derived balance summary — never recomputed client-side. */}
          <dl className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3">
            <div className="rounded-lg bg-gray-50 p-3">
              <dt className="text-xs text-gray-500">Opening balance</dt>
              <dd
                className="mt-1 text-base font-bold text-gray-900"
                data-testid="statement-opening-balance"
              >
                {formatKes(doc.opening_balance)}
              </dd>
            </div>
            <div className="rounded-lg bg-gray-50 p-3">
              <dt className="text-xs text-gray-500">Charges this period</dt>
              <dd
                className="mt-1 text-base font-bold text-gray-900"
                data-testid="statement-charge-total"
              >
                {formatKes(doc.charge_total)}
              </dd>
            </div>
            <div className="rounded-lg bg-gray-50 p-3">
              <dt className="text-xs text-gray-500">Collections this period</dt>
              <dd
                className="mt-1 text-base font-bold text-gray-900"
                data-testid="statement-collection-total"
              >
                {formatKes(doc.collection_total)}
              </dd>
            </div>
            <div className="rounded-lg bg-gray-50 p-3">
              <dt className="text-xs text-gray-500">Net movement</dt>
              <dd
                className="mt-1 text-base font-bold text-gray-900"
                data-testid="statement-net-movement"
              >
                {formatKes(doc.net_movement)}
              </dd>
            </div>
            <div className="rounded-lg bg-gray-50 p-3">
              <dt className="text-xs text-gray-500">Settled this period</dt>
              <dd
                className="mt-1 text-base font-bold text-gray-900"
                data-testid="statement-settled-total"
              >
                {formatKes(doc.settled_total)}
              </dd>
            </div>
            <div className="rounded-lg bg-primary-50 p-3">
              <dt className="text-xs text-primary-600">Closing balance</dt>
              <dd
                className="mt-1 text-base font-bold text-primary-900"
                data-testid="statement-closing-balance"
              >
                {formatKes(doc.closing_balance)}
              </dd>
            </div>
          </dl>

          {/* Movements — receivable ledger entries in the inclusive period.
              R1: server-classified kind + display_amount rendered verbatim;
              references are short (never a full UUID). */}
          <section className="mt-8" data-testid="statement-movements-section">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
              Movements
            </h2>
            {doc.movements.length === 0 ? (
              <p className="mt-2 text-sm text-gray-500">No movements in this period.</p>
            ) : (
              <table className="mt-2 w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 text-left text-xs text-gray-500">
                    <th className="py-2 pr-2 font-medium">Date</th>
                    <th className="py-2 px-2 font-medium">Kind</th>
                    <th className="py-2 px-2 font-medium">Description</th>
                    <th className="py-2 px-2 font-medium">Reference</th>
                    <th className="py-2 pl-2 text-right font-medium">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {doc.movements.map((m, idx) => (
                    <tr key={idx} className="border-b border-gray-100 align-top">
                      <td className="py-2 pr-2 text-gray-900">{m.date_eat}</td>
                      <td className="py-2 px-2">
                        <span
                          className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                            m.kind === 'charge'
                              ? 'bg-amber-100 text-amber-700'
                              : 'bg-green-100 text-green-700'
                          }`}
                        >
                          {m.kind}
                        </span>
                      </td>
                      <td className="py-2 px-2 text-gray-700">{m.description || '—'}</td>
                      <td className="py-2 px-2 font-mono text-xs text-gray-500">
                        {shortRef(m.reference_id)}
                      </td>
                      <td className="py-2 pl-2 text-right text-gray-900">
                        {formatKes(m.display_amount)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          {/* Settled payments — independent canonical list; never cross-linked
              to a movement row above. R1: settled_total derives ONLY from this
              list server-side; order references are short (never a full UUID). */}
          <section
            className="mt-8"
            data-testid="statement-settled-payments-section"
          >
            <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
              Settled Payments
            </h2>
            {doc.settled_payments.length === 0 ? (
              <p className="mt-2 text-sm text-gray-500">No settled payments in this period.</p>
            ) : (
              <table className="mt-2 w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 text-left text-xs text-gray-500">
                    <th className="py-2 pr-2 font-medium">Date</th>
                    <th className="py-2 px-2 font-medium">Order</th>
                    <th className="py-2 px-2 font-medium">Method</th>
                    <th className="py-2 px-2 font-medium">Receipt</th>
                    <th className="py-2 pl-2 text-right font-medium">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {doc.settled_payments.map((p, idx) => (
                    <tr key={idx} className="border-b border-gray-100 align-top">
                      <td className="py-2 pr-2 text-gray-900">{p.date_eat}</td>
                      <td className="py-2 px-2 font-mono text-xs text-gray-500">
                        {shortRef(p.order_id)}
                      </td>
                      <td className="py-2 px-2 text-gray-700">{p.method}</td>
                      <td className="py-2 px-2 text-gray-700">{p.receipt_number || '—'}</td>
                      <td className="py-2 pl-2 text-right text-gray-900">
                        {formatKes(p.amount)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          {/* Pending/rejected declarations — non-accounting context, rendered
              ONLY when explicitly requested; they never affect balances. */}
          {doc.pending_declarations.length > 0 && (
            <section
              className="mt-8"
              data-testid="statement-pending-declarations-section"
            >
              <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
                Pending Declarations
              </h2>
              <p className="mt-1 text-xs text-gray-400">
                These declarations have not been confirmed and do not affect the
                balances above.
              </p>
              <table className="mt-2 w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 text-left text-xs text-gray-500">
                    <th className="py-2 pr-2 font-medium">Date</th>
                    <th className="py-2 px-2 font-medium">Order</th>
                    <th className="py-2 px-2 font-medium">Method</th>
                    <th className="py-2 px-2 font-medium">Transfer</th>
                    <th className="py-2 px-2 font-medium">Status</th>
                    <th className="py-2 pl-2 text-right font-medium">Declared</th>
                  </tr>
                </thead>
                <tbody>
                  {doc.pending_declarations.map((d, idx) => (
                    <tr key={idx} className="border-b border-gray-100 align-top">
                      <td className="py-2 pr-2 text-gray-900">{d.submitted_at_eat}</td>
                      <td className="py-2 px-2 font-mono text-xs text-gray-500">
                        {shortRef(d.order_id)}
                      </td>
                      <td className="py-2 px-2 text-gray-700">{d.method}</td>
                      <td className="py-2 px-2 text-gray-700">{d.transfer_reference || '—'}</td>
                      <td className="py-2 px-2 text-gray-700">{d.status}</td>
                      <td className="py-2 pl-2 text-right text-gray-900">
                        {formatKes(d.declared_amount)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}
        </article>
      )}
    </div>
  );
}
