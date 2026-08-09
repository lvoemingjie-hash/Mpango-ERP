/**
 * DC-12R1-S3-S2B-I2C-I2 — Contract A: printable order document (read-only).
 *
 * Renders ONLY server-authoritative fields from GET /client/orders/{id}/print
 * (retailer) or GET /orders/{id}/print (cashier). No money is recomputed,
 * summed, or rounded — server decimal strings are rendered via string-only
 * grouping (utils/printFormat). Browser print is window.print() + print CSS.
 *
 * `mode` is fixed by the static route config (never a query param). Error
 * states are status-only neutral copy (utils/printError) — no internal IDs,
 * schema names, raw server text, or another party's data are ever surfaced.
 */
import { useCallback, useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { PrinterIcon, ArrowLeftIcon } from '@heroicons/react/24/outline';
import { clientOrderService } from '@/services/clientOrderService';
import { orderService } from '@/services/orderService';
import { sanitizePrintError } from '@/utils/printError';
import { formatKes, formatPrintDate } from '@/utils/printFormat';
import type { OrderPrintView } from '@/types/print';

interface OrderPrintPageProps {
  /** Fixed by static route config: 'client' (retailer) or 'cashier' (wholesaler). */
  mode: 'client' | 'cashier';
}

export function OrderPrintPage({ mode }: OrderPrintPageProps) {
  const { orderId } = useParams<{ orderId: string }>();
  const [doc, setDoc] = useState<OrderPrintView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!orderId) {
      setError('This document is not available.');
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res =
        mode === 'client'
          ? await clientOrderService.getPrint(orderId)
          : await orderService.getPrint(orderId);
      setDoc(res.data.data);
    } catch (err) {
      setDoc(null);
      setError(sanitizePrintError(err, 'order'));
    } finally {
      setLoading(false);
    }
  }, [orderId, mode]);

  useEffect(() => {
    load();
  }, [load]);

  const handlePrint = () => {
    window.print();
  };

  const backHref = mode === 'client' ? '/client/orders' : '/orders';

  return (
    <div className="mx-auto w-full max-w-2xl px-4 py-6 print:max-w-none print:px-0 print:py-0">
      {/* Chrome (hidden in print) */}
      <div className="no-print mb-4 flex items-center justify-between">
        <Link
          to={backHref}
          className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700"
        >
          <ArrowLeftIcon className="h-4 w-4" />
          Back to orders
        </Link>
        <button
          type="button"
          onClick={handlePrint}
          disabled={loading || !!error || !doc}
          className="inline-flex items-center gap-1.5 rounded-lg bg-primary-600 px-3 py-2 text-sm font-medium text-white shadow-sm hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition"
          data-testid="order-print-button"
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
          data-testid="order-print-error"
        >
          {error}
        </div>
      )}

      {!loading && !error && doc && (
        <article
          className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm print:border-0 print:shadow-none print:p-0"
          data-testid="order-print-document"
        >
          <header className="border-b border-gray-200 pb-4">
            <h1 className="text-xl font-bold text-gray-900">Order</h1>
            <p className="mt-1 text-xs text-gray-500">
              Placed {formatPrintDate(doc.created_at_eat || doc.created_at)}
            </p>
          </header>

          <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
            <dt className="text-gray-500">Supplier</dt>
            <dd className="text-gray-900">{doc.supplier_name}</dd>
            <dt className="text-gray-500">Retailer</dt>
            <dd className="text-gray-900">{doc.retailer_name}</dd>
            <dt className="text-gray-500">Status</dt>
            <dd className="text-gray-900">{doc.status}</dd>
            <dt className="text-gray-500">Items</dt>
            <dd className="text-gray-900">{doc.item_count}</dd>
          </dl>

          <table className="mt-6 w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 text-left text-xs text-gray-500">
                <th className="py-2 pr-2 font-medium">Item</th>
                <th className="py-2 px-2 font-medium">SKU</th>
                <th className="py-2 px-2 text-right font-medium">Qty</th>
                <th className="py-2 px-2 text-right font-medium">Unit price</th>
                <th className="py-2 pl-2 text-right font-medium">Subtotal</th>
              </tr>
            </thead>
            <tbody>
              {doc.items.map((item, idx) => (
                <tr key={idx} className="border-b border-gray-100 align-top">
                  <td className="py-2 pr-2 text-gray-900">{item.product_name}</td>
                  <td className="py-2 px-2 font-mono text-xs text-gray-500">{item.sku_code}</td>
                  <td className="py-2 px-2 text-right text-gray-900">{item.quantity}</td>
                  <td className="py-2 px-2 text-right text-gray-900">{formatKes(item.unit_price)}</td>
                  <td className="py-2 pl-2 text-right text-gray-900">{formatKes(item.subtotal)}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="mt-4 flex justify-between border-t border-gray-200 pt-3">
            <span className="text-sm font-semibold text-gray-900">Total</span>
            <span
              className="text-base font-bold text-gray-900"
              data-testid="order-print-total"
            >
              {formatKes(doc.total_amount)}
            </span>
          </div>

          {doc.notes && (
            <div className="mt-4 rounded-lg bg-gray-50 p-3">
              <p className="text-xs text-gray-500">Notes</p>
              <p className="mt-0.5 text-sm text-gray-700">{doc.notes}</p>
            </div>
          )}
        </article>
      )}
    </div>
  );
}
