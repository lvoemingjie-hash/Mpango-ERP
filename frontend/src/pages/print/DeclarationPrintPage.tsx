/**
 * DC-12R1-S3-S2B-I2C-I2 — Contract B: printable payment declaration document.
 *
 * Renders ONLY server-authoritative fields from GET /client/declarations/{id}/print
 * (retailer) or GET /declarations/{id}/print (cashier). No money is recomputed
 * or rounded — server decimal strings are rendered via string-only grouping.
 *
 * BINDING CORRECTION #2: a pending/rejected declaration is NEVER a receipt.
 * The server-provided `non_receipt_notice` (which legitimately contains the
 * text "NOT A RECEIPT") is rendered verbatim and prominently. Pending/rejected
 * documents never show a receipt number and never use "Payment Received" as
 * their status label. The dedicated receipt content is only ever fetched from
 * the Contract C endpoint (ReceiptPrintPage), never here.
 *
 * `mode` is fixed by the static route config (never a query param). Error
 * states are status-only neutral copy — no internal IDs / schema / raw server
 * text / eligibility state are surfaced.
 */
import { useCallback, useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { PrinterIcon, ArrowLeftIcon } from '@heroicons/react/24/outline';
import {
  getClientDeclarationPrint,
  getCashierDeclarationPrint,
} from '@/services/declarationService';
import { sanitizePrintError } from '@/utils/printError';
import { formatKes, formatPrintDate } from '@/utils/printFormat';
import type { DeclarationPrintView } from '@/types/print';

interface DeclarationPrintPageProps {
  /** Fixed by static route config: 'client' (retailer) or 'cashier' (wholesaler). */
  mode: 'client' | 'cashier';
}

/** Plain, non-receipt status labels. Never "received"/"receipt" for pending/rejected. */
const STATUS_LABEL: Record<string, string> = {
  pending: 'Pending — awaiting confirmation',
  confirmed: 'Confirmed',
  rejected: 'Rejected',
};

export function DeclarationPrintPage({ mode }: DeclarationPrintPageProps) {
  const { declarationId } = useParams<{ declarationId: string }>();
  const [doc, setDoc] = useState<DeclarationPrintView | null>(null);
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
          ? await getClientDeclarationPrint(declarationId)
          : await getCashierDeclarationPrint(declarationId);
      setDoc(res.data);
    } catch (err) {
      setDoc(null);
      setError(sanitizePrintError(err, 'declaration'));
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
          data-testid="declaration-print-button"
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
          data-testid="declaration-print-error"
        >
          {error}
        </div>
      )}

      {!loading && !error && doc && (
        <article
          className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm print:border-0 print:shadow-none print:p-0"
          data-testid="declaration-print-document"
        >
          <header className="border-b border-gray-200 pb-4">
            <h1 className="text-xl font-bold text-gray-900">Payment Declaration</h1>
            <p className="mt-1 text-xs text-gray-500">
              Submitted {formatPrintDate(doc.submitted_at_eat || doc.submitted_at)}
            </p>
          </header>

          {/* Prominent non-receipt notice for pending/rejected (server-authoritative text). */}
          {doc.is_receipt === false && doc.non_receipt_notice && (
            <div
              className="mt-4 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm font-semibold text-amber-900"
              role="note"
              data-testid="declaration-non-receipt-notice"
            >
              {doc.non_receipt_notice}
            </div>
          )}

          <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
            <dt className="text-gray-500">Supplier</dt>
            <dd className="text-gray-900">{doc.supplier_name}</dd>
            <dt className="text-gray-500">Retailer</dt>
            <dd className="text-gray-900">{doc.retailer_name}</dd>
            <dt className="text-gray-500">Status</dt>
            <dd className="text-gray-900" data-testid="declaration-status">
              {STATUS_LABEL[doc.status] ?? doc.status}
            </dd>
            <dt className="text-gray-500">Declared amount</dt>
            <dd className="text-gray-900">{formatKes(doc.declared_amount)}</dd>
            <dt className="text-gray-500">Method</dt>
            <dd className="text-gray-900">{doc.method}</dd>
            {doc.transfer_reference && (
              <>
                <dt className="text-gray-500">Transfer reference</dt>
                <dd className="font-mono text-xs text-gray-900">{doc.transfer_reference}</dd>
              </>
            )}
            {doc.confirmed_at && (
              <>
                <dt className="text-gray-500">Confirmed</dt>
                <dd className="text-gray-900">
                  {formatPrintDate(doc.confirmed_at_eat || doc.confirmed_at)}
                </dd>
              </>
            )}
            {doc.rejected_at && (
              <>
                <dt className="text-gray-500">Rejected</dt>
                <dd className="text-gray-900">
                  {formatPrintDate(doc.rejected_at_eat || doc.rejected_at)}
                </dd>
              </>
            )}
          </dl>

          {doc.rejection_reason && (
            <div className="mt-4 rounded-lg bg-gray-50 p-3">
              <p className="text-xs text-gray-500">Reason</p>
              <p className="mt-0.5 text-sm text-gray-700">{doc.rejection_reason}</p>
            </div>
          )}
        </article>
      )}
    </div>
  );
}
