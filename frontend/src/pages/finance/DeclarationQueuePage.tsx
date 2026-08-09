/** Wholesaler cashier declaration queue (DC-12R1-S3-S2B-I2B). */
import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { BanknotesIcon, PrinterIcon } from '@heroicons/react/24/outline';
import { EmptyState } from '@/components/ui/EmptyState';
import { Pagination } from '@/components/ui/Pagination';
import { listDeclarations, confirmDeclaration, rejectDeclaration } from '@/services/declarationService';
import type { PaymentDeclaration } from '@/types/declaration';

const STATUS_BADGE: Record<string, string> = {
  pending: 'bg-yellow-100 text-yellow-800',
  confirmed: 'bg-green-100 text-green-800',
  rejected: 'bg-red-100 text-red-800',
};

function formatMoney(amount: string) {
  return `KES ${Number(amount).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatDate(value: string) {
  return new Date(value).toLocaleDateString('en-KE', { month: 'short', day: 'numeric', year: 'numeric' });
}

export default function DeclarationQueuePage() {
  const [declarations, setDeclarations] = useState<PaymentDeclaration[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(0);
  const [actionId, setActionId] = useState<string | null>(null);
  const [editingReasonId, setEditingReasonId] = useState<string | null>(null);
  const [rejectReasons, setRejectReasons] = useState<Record<string, string>>({});
  // DC-12R1-S3-S2B-I2C-I2-R1: the confirmed declaration id, taken ONLY from the
  // successful confirmation response. There is NO fallback to the request/row
  // declaration id (no `?? id`, no `|| id`, no cached/stale id). The receipt
  // link is rendered only when this value is a non-empty string. Used solely to
  // surface a "View/Print receipt" link that reads Contract C; the confirm
  // transaction itself is unchanged (still a single POST /declarations/{id}/confirm).
  const [confirmedReceiptId, setConfirmedReceiptId] = useState<string | null>(null);
  // Set true only when confirmation succeeded but the response carried no valid
  // receipt id. We then show controlled neutral copy and expose NO receipt link.
  // We do NOT claim the payment failed; confirmation itself succeeded.
  const [receiptLinkUnavailable, setReceiptLinkUnavailable] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await listDeclarations(page, 20, 'pending');
      setDeclarations((res.data as { items: PaymentDeclaration[] }).items);
      setTotalPages((res.data as { pagination: { pages: number } }).pagination.pages);
    } catch (err: unknown) {
      setError((err as Error).message || 'Failed to load declarations');
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => { load(); }, [load]);

  const handleConfirm = async (id: string) => {
    setActionId(id);
    // Reset prior receipt-link state before each confirmation.
    setConfirmedReceiptId(null);
    setReceiptLinkUnavailable(false);
    try {
      // Confirmation transaction is unchanged: exactly one POST with the
      // request declaration id. We only READ the returned id afterwards.
      const resp = await confirmDeclaration(id);
      // R1 Correction 1: derive the receipt id ONLY from the response. No
      // fallback to the request id (no `?? id`). A non-empty string is the
      // sole authority for rendering the Contract C receipt link.
      const responseId =
        resp && typeof resp === 'object' && 'id' in resp
          ? (resp as { id?: unknown }).id
          : undefined;
      if (typeof responseId === 'string' && responseId.length > 0) {
        setConfirmedReceiptId(responseId);
      } else {
        // Malformed/missing response id: fail closed for the receipt link only.
        setConfirmedReceiptId(null);
        setReceiptLinkUnavailable(true);
      }
      load();
    } catch (err: unknown) {
      setError((err as Error).message || 'Confirm failed');
    } finally {
      setActionId(null);
    }
  };

  const handleReject = async (id: string) => {
    const reason = (rejectReasons[id] || '').trim();
    if (!reason) return;
    setActionId(id);
    try {
      await rejectDeclaration(id, reason);
      setRejectReasons(prev => { const n = { ...prev }; delete n[id]; return n; });
      setEditingReasonId(null);
      load();
    } catch (err: unknown) {
      setError((err as { response?: { data?: { message?: string } } }).response?.data?.message || (err as Error).message || 'Reject failed');
    } finally {
      setActionId(null);
    }
  };

  if (loading) return <div className="flex justify-center p-8"><p className="text-gray-500">Loading pending declarations...</p></div>;

  return (
    <div className="min-h-screen bg-gray-50 p-4">
      <h1 className="text-lg font-semibold text-gray-900 mb-4">Payment Declarations — Pending</h1>
      {error && <div className="bg-red-50 text-red-700 text-sm p-3 rounded mb-3">{error}</div>}
      {/* DC-12R1-S3-S2B-I2C-I2-R1: after a successful confirm, surface a receipt
          link that navigates ONLY to Contract C using the confirmed id taken
          ONLY from the confirmation response (no request/row id fallback). The
          link is rendered only when that id is a non-empty string; it is encoded
          before being placed in the URL. The confirm transaction itself is
          unchanged (single POST). */}
      {confirmedReceiptId && (
        <div
          className="bg-green-50 border border-green-200 text-green-800 text-sm p-3 rounded mb-3 flex items-center justify-between"
          data-testid="confirmed-receipt-banner"
        >
          <span>Declaration confirmed. A receipt is available.</span>
          <Link
            to={`/declarations/${encodeURIComponent(confirmedReceiptId)}/receipt`}
            data-testid="confirmed-receipt-link"
            className="inline-flex items-center gap-1 bg-green-600 text-white text-xs px-3 py-1 rounded hover:bg-green-700"
          >
            <PrinterIcon className="h-3.5 w-3.5" />
            View / Print receipt
          </Link>
        </div>
      )}
      {/* R1 Correction 1: confirmation succeeded but the response carried no
          valid receipt id. Fail closed for the receipt link only — show
          controlled neutral copy and expose NO receipt link. This is NOT a
          payment-failure message (confirmation itself succeeded); it is only a
          receipt-link rendering fail-closed. */}
      {receiptLinkUnavailable && !confirmedReceiptId && (
        <div
          className="bg-gray-100 border border-gray-200 text-gray-700 text-sm p-3 rounded mb-3"
          data-testid="receipt-link-unavailable"
        >
          Declaration confirmed. The receipt link is unavailable.
        </div>
      )}
      {declarations.length === 0 ? (
        <EmptyState icon={BanknotesIcon} title="No pending declarations" description="All declarations have been processed." />
      ) : (
        <div className="space-y-3">
          {declarations.map((d) => (
            <div key={d.id} className="bg-white rounded-xl shadow p-4">
              <div className="flex justify-between items-start">
                <div>
                  <p className="text-sm font-semibold text-gray-900">
                    {formatMoney(d.declared_amount)} · {d.method}
                  </p>
                  <p className="text-xs text-gray-500 mt-1">Order: {d.order_id?.slice(0, 8)}... · {formatDate(d.submitted_at)}</p>
                  <span className={`inline-block mt-1 text-xs font-medium px-2 py-0.5 rounded ${STATUS_BADGE[d.status] ?? 'bg-gray-100'}`}>
                    {d.status}
                  </span>
                  {/* DC-12R1-S3-S2B-I2C-I2: printable declaration (Contract B, cashier). */}
                  <div className="no-print mt-2">
                    <Link
                      to={`/declarations/${d.id}/print`}
                      className="inline-flex items-center gap-1 text-xs text-gray-600 hover:text-gray-900"
                    >
                      <PrinterIcon className="h-3.5 w-3.5" />
                      Print declaration
                    </Link>
                  </div>
                </div>
                {d.status === 'pending' && (
                  <div className="flex gap-2">
                    <button onClick={() => handleConfirm(d.id)} disabled={actionId === d.id}
                      className="bg-green-600 text-white text-xs px-3 py-1 rounded hover:bg-green-700 disabled:opacity-50">
                      {actionId === d.id ? '...' : 'Confirm'}
                    </button>
                    <div className="flex flex-col gap-1">
                      <input type="text" placeholder="Reason" maxLength={256}
                        value={rejectReasons[d.id] || ''}
                        onFocus={() => { setEditingReasonId(d.id); }}
                        onChange={e => setRejectReasons(prev => ({ ...prev, [d.id]: e.target.value }))}
                        className={`text-xs border rounded px-1 py-0.5 w-28 ${editingReasonId === d.id ? 'ring-1 ring-indigo-500' : ''}`} />
                      <button onClick={() => handleReject(d.id)} disabled={actionId === d.id || !(rejectReasons[d.id] || '').trim()}
                        className="bg-red-600 text-white text-xs px-3 py-1 rounded hover:bg-red-700 disabled:opacity-50">
                        {actionId === d.id ? '...' : 'Reject'}
                      </button>
                    </div>
                  </div>
                )}
                {d.status === 'confirmed' && (
                  <p className="text-xs text-green-700 font-medium">{d.receipt_number}</p>
                )}
                {d.status === 'rejected' && (
                  <p className="text-xs text-red-600">{d.reason}</p>
                )}
              </div>
            </div>
          ))}
          {totalPages > 1 && <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />}
        </div>
      )}
    </div>
  );
}
