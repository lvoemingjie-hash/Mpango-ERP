/**
 * DC-12R1-S3-S2B-I2C-I2 — Contract C: confirmed receipt (read-only).
 *
 * Renders ONLY server-authoritative fields from GET /client/declarations/{id}/receipt
 * (retailer) or GET /declarations/{id}/receipt (cashier). This endpoint returns
 * 200 only for a receipt-eligible confirmed declaration; every other case
 * (pending/rejected/ineligible/wrong-party/missing) fails closed with a neutral
 * 404 RECEIPT_NOT_AVAILABLE. No money is recomputed or rounded — server decimal
 * strings are rendered via string-only grouping.
 *
 * BINDING CORRECTION #6: a /receipt failure shows ONLY neutral status copy
 * ("This document is not available.") via sanitizePrintError — never eligibility,
 * payment, binding, or supplier state.
 *
 * `mode` is fixed by the static route config (never a query param).
 */
import { useCallback, useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { PrinterIcon, ArrowLeftIcon } from '@heroicons/react/24/outline';
import { getClientReceipt, getCashierReceipt } from '@/services/declarationService';
import { sanitizePrintError } from '@/utils/printError';
import { formatKes, formatPrintDate } from '@/utils/printFormat';
import type { ReceiptPrintView } from '@/types/print';

interface ReceiptPrintPageProps {
  /** Fixed by static route config: 'client' (retailer) or 'cashier' (wholesaler). */
  mode: 'client' | 'cashier';
}

export function ReceiptPrintPage({ mode }: ReceiptPrintPageProps) {
  const { declarationId } = useParams<{ declarationId: string }>();
  const [doc, setDoc] = useState<ReceiptPrintView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!declarationId) {
      setError('This document is not available.');
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res =
        mode === 'client'
          ? await getClientReceipt(declarationId)
          : await getCashierReceipt(declarationId);
      setDoc(res.data);
    } catch (err) {
      setDoc(null);
      setError(sanitizePrintError(err, 'receipt'));
    } finally {
      setLoading(false);
    }
  }, [declarationId, mode]);

  useEffect(() => {
    load();
  }, [load]);

  const handlePrint = () => {
    window.print();
  };

  const backHref = mode === 'client' ? '/client/declarations' : '/declarations';

  return (
    <div className="mx-auto w-full max-w-2xl px-4 py-6 print:max-w-none print:px-0 print:py-0">
      {/* Chrome (hidden in print) */}
      <div className="no-print mb-4 flex items-center justify-between">
        <Link
          to={backHref}
          className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700"
        >
          <ArrowLeftIcon className="h-4 w-4" />
          Back to declarations
        </Link>
        <button
          type="button"
          onClick={handlePrint}
          disabled={loading || !!error || !doc}
          className="inline-flex items-center gap-1.5 rounded-lg bg-primary-600 px-3 py-2 text-sm font-medium text-white shadow-sm hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition"
          data-testid="receipt-print-button"
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
          data-testid="receipt-print-error"
        >
          {error}
        </div>
      )}

      {!loading && !error && doc && (
        <article
          className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm print:border-0 print:shadow-none print:p-0"
          data-testid="receipt-print-document"
        >
          <header className="border-b border-gray-200 pb-4">
            <h1 className="text-xl font-bold text-gray-900">Payment Received — Receipt</h1>
            <p
              className="mt-1 font-mono text-sm font-semibold text-gray-900"
              data-testid="receipt-number"
            >
              {doc.receipt_number}
            </p>
            <p className="mt-1 text-xs text-gray-500">
              Issued {formatPrintDate(doc.confirmed_at_eat || doc.confirmed_at)}
            </p>
          </header>

          <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
            <dt className="text-gray-500">Supplier</dt>
            <dd className="text-gray-900">{doc.supplier_name}</dd>
            <dt className="text-gray-500">Retailer</dt>
            <dd className="text-gray-900">{doc.retailer_name}</dd>
            <dt className="text-gray-500">Method</dt>
            <dd className="text-gray-900">{doc.method}</dd>
            <dt className="text-gray-500">Amount received</dt>
            <dd className="text-gray-900" data-testid="receipt-confirmed-amount">
              {formatKes(doc.confirmed_amount)}
            </dd>
            <dt className="text-gray-500">Declared amount</dt>
            <dd className="text-gray-900">{formatKes(doc.declared_amount)}</dd>
            {doc.order_status && (
              <>
                <dt className="text-gray-500">Order status</dt>
                <dd className="text-gray-900">{doc.order_status}</dd>
              </>
            )}
            {doc.order_total_amount && (
              <>
                <dt className="text-gray-500">Order total</dt>
                <dd className="text-gray-900">{formatKes(doc.order_total_amount)}</dd>
              </>
            )}
          </dl>
        </article>
      )}
    </div>
  );
}
