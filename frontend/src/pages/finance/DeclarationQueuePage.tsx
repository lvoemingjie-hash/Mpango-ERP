/** Wholesaler cashier declaration queue (DC-12R1-S3-S2B-I2B). */
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { BanknotesIcon, PrinterIcon } from '@heroicons/react/24/outline';
import { EmptyState } from '@/components/ui/EmptyState';
import { Pagination } from '@/components/ui/Pagination';
import { listDeclarations, confirmDeclaration, rejectDeclaration } from '@/services/declarationService';
import { getCashierReviewContext } from '@/services/partyContextService';
import { useAuthStore } from '@/stores/authStore';
import { can } from '@/utils/permissions';
import { isCashierReviewContext, type CashierReviewContext } from '@/types/partyContext';
import type { PaymentDeclaration } from '@/types/declaration';
import { formatMoney } from '@/utils/printFormat';

const STATUS_BADGE: Record<string, string> = {
  pending: 'bg-yellow-100 text-yellow-800',
  confirmed: 'bg-green-100 text-green-800',
  rejected: 'bg-red-100 text-red-800',
};

function formatDate(value: string) {
  return new Date(value).toLocaleDateString('en-KE', { month: 'short', day: 'numeric', year: 'numeric' });
}

export default function DeclarationQueuePage() {
  const auth = useAuthStore();
  const context = reviewScope(auth);
  return <DeclarationQueue key={context} context={context} />;
}

function reviewScope(s: ReturnType<typeof useAuthStore.getState>) {
  return JSON.stringify([s.user?.id, s.user?.tenant_id, s.user?.tenant_schema, s.sessionGeneration,
    s.user?.permissions, s.user?.roles, s.user?.staff_state, s.user?.is_owner, s.user?.authz_revision]);
}
function sameDecimal(a: string, b: string) {
  const normalize = (v: string) => v.replace(/^0+(?=\d)/, '').replace(/(\.\d*?)0+$/, '$1').replace(/\.$/, '');
  return /^\d+(?:\.\d+)?$/.test(a) && /^\d+(?:\.\d+)?$/.test(b) && normalize(a) === normalize(b);
}
function readyContext(data: CashierReviewContext) {
  return data.review_state === 'READY' && data.reason_codes.length === 0
    && data.declaration.status === 'pending' && ['confirmed', 'partially_paid', 'paid', 'fulfilled'].includes(data.order.status)
    && data.supplier.name_resolution === 'RESOLVED' && data.retailer.name_resolution === 'RESOLVED'
    && data.money.currency_status === 'KNOWN' && data.money.balance_status === 'VERIFIED'
    && data.money.balance_due !== null && !/^0(?:\.0+)?$/.test(data.money.balance_due)
    && (data.declaration.method !== 'transfer' || Boolean(data.declaration.transfer_reference?.trim()));
}
function DeclarationQueue({ context }: { context: string }) {
  const mounted = useRef(true);
  const listAttempt = useRef(0);
  const reviewAttempt = useRef(0);
  const reviewRequest = useRef<AbortController | null>(null);
  const actionBusy = useRef(false);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; reviewRequest.current?.abort(); }; }, []);
  const current = () => {
    const s = useAuthStore.getState();
    return mounted.current && Boolean(s.accessToken) && context === reviewScope(s);
  };
  const mayReview = () => current() && can(useAuthStore.getState().user, 'payments:read');
  const mayConfirm = () => mayReview() && can(useAuthStore.getState().user, 'payments:confirm_declaration');
  const ownsReview = (attempt: number) => mayReview() && attempt === reviewAttempt.current;
  const [review, setReview] = useState<{ id: string; attempt: number; loading?: boolean; error?: string; data?: CashierReviewContext } | null>(null);
  const [verified, setVerified] = useState(false);
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
    reviewRequest.current?.abort();
    ++reviewAttempt.current;
    setReview(null); setVerified(false);
    const attempt = ++listAttempt.current;
    setLoading(true);
    setError('');
    try {
      const res = await listDeclarations(page, 20, 'pending');
      if (!mounted.current || attempt !== listAttempt.current) return;
      setDeclarations((res.data as { items: PaymentDeclaration[] }).items);
      setTotalPages((res.data as { pagination: { pages: number } }).pagination.pages);
    } catch (err: unknown) {
      if (mounted.current && attempt === listAttempt.current) setError((err as { response?: { status?: number } }).response?.status === 403 ? 'You do not have permission to view declarations.' : 'Could not load declarations. Please retry.');
    } finally {
      if (mounted.current && attempt === listAttempt.current) setLoading(false);
    }
  }, [page]);

  useEffect(() => { load(); }, [load]);

  const openReview = async (d: PaymentDeclaration) => {
    reviewRequest.current?.abort();
    const request = new AbortController();
    reviewRequest.current = request;
    const attempt = ++reviewAttempt.current;
    setVerified(false);
    setError(''); setConfirmedReceiptId(null); setReceiptLinkUnavailable(false);
    setReview({ id: d.id, attempt, loading: true });
    if (!mayReview()) { setReview({ id: d.id, attempt, error: 'Payment review permission is required. Ask an authorized colleague to review this payment.' }); return; }
    try {
      const response = await getCashierReviewContext(d.id, request.signal);
      if (!ownsReview(attempt) || request.signal.aborted) return;
      if (response.success !== true) throw new Error('Unverified response');
      const data: unknown = response.data;
      const user = useAuthStore.getState().user;
      const expectedRetailer = (d as PaymentDeclaration & { retailer_id?: string }).retailer_id;
      if (!isCashierReviewContext(data) || data.context.user_id !== user?.id || data.context.tenant_id !== user?.tenant_id
        || data.supplier.id !== user?.tenant_id || data.declaration.id !== d.id
        || data.order.id !== d.order_id || data.declaration.order_id !== d.order_id
        || (expectedRetailer && data.retailer.id !== expectedRetailer)
        || !sameDecimal(data.declaration.declared_amount, d.declared_amount) || data.declaration.method !== d.method
        || (data.declaration.transfer_reference || '') !== (d.transfer_reference || '')
        || (data.money.currency_status === 'KNOWN' && d.currency_status === 'KNOWN' && data.money.currency !== d.currency)) throw new Error('Incomplete review');
      setReview({ id: d.id, attempt, data });
    } catch {
      if (ownsReview(attempt) && !request.signal.aborted) {
        setVerified(false);
        setReview({ id: d.id, attempt, error: 'The payment context is incomplete or could not be verified. Refresh the review or contact support; do not confirm blindly.' });
      }
    }
  };
  const handleConfirm = async (id: string) => {
    if (actionBusy.current || !mayConfirm() || !verified || review?.id !== id || !review.data
      || !ownsReview(review.attempt) || !readyContext(review.data)) return;
    const attempt = review.attempt;
    const selected = declarations.find(d => d.id === id);
    actionBusy.current = true;
    setActionId(id);
    // Reset prior receipt-link state before each confirmation.
    setConfirmedReceiptId(null);
    setReceiptLinkUnavailable(false);
    try {
      // Confirmation transaction is unchanged: exactly one POST with the
      // request declaration id. We only READ the returned id afterwards.
      const resp = await confirmDeclaration(id);
      if (!mayConfirm() || !ownsReview(attempt)) return;
      setReview(null); setVerified(false);
      // R2 Correction 1: derive the receipt id ONLY from the real
      // ApiResponse<DeclarationConfirmResponse> envelope, i.e. resp.data.id.
      // confirmDeclaration's declared contract is
      // Promise<ApiResponse<DeclarationConfirmResponse>> where ApiResponse is
      // { success, data: { id, ... }, timestamp }. No request/row/cached/fixed
      // id fallback (no `?? id`, no `|| id`); no shape guessing beyond the
      // declared envelope.
      const dataObj = resp && typeof resp === 'object' ? (resp as { data?: unknown }).data : undefined;
      const responseId =
        dataObj && typeof dataObj === 'object' ? (dataObj as { id?: unknown }).id : undefined;
      if (typeof responseId === 'string' && responseId.length > 0) {
        setConfirmedReceiptId(responseId);
      } else {
        // Malformed/missing response id: fail closed for the receipt link only.
        setConfirmedReceiptId(null);
        setReceiptLinkUnavailable(true);
      }
      load();
    } catch (err: unknown) {
      if (ownsReview(attempt)) {
        setVerified(false);
        setReview(null);
        if (selected) await openReview(selected);
        if (current()) setError('The confirmation result could not be verified. Recheck this declaration before trying again; no payment was automatically resent.');
      }
    } finally {
      actionBusy.current = false;
      if (mounted.current) setActionId(null);
    }
  };

  const handleReject = async (id: string) => {
    const reason = (rejectReasons[id] || '').trim();
    if (!reason || actionBusy.current || !current() || !can(useAuthStore.getState().user, 'payments:confirm_declaration')) return;
    actionBusy.current = true;
    reviewRequest.current?.abort(); ++reviewAttempt.current;
    setReview(null); setVerified(false);
    setActionId(id);
    try {
      await rejectDeclaration(id, reason);
      if (!current()) return;
      setReview(null); setVerified(false);
      setRejectReasons(prev => { const n = { ...prev }; delete n[id]; return n; });
      setEditingReasonId(null);
      load();
    } catch (err: unknown) {
      if (current()) setError('The rejection could not be verified. Refresh and check the declaration.');
    } finally {
      actionBusy.current = false;
      if (mounted.current) setActionId(null);
    }
  };

  if (loading) return <div className="flex justify-center p-8"><p className="text-gray-500">Loading pending declarations...</p></div>;

  return (
    <div className="min-h-screen bg-gray-50 p-4">
      <h1 className="text-lg font-semibold text-gray-900 mb-4">Payment Declarations — Pending</h1>
      {error && <div role="alert" className="bg-red-50 text-red-700 text-sm p-3 rounded mb-3">{error} <button onClick={load} className="underline">Retry</button></div>}
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
            <article key={d.id} aria-label={`Declaration ${d.id}`} className="bg-white rounded-xl shadow p-4">
              <div className="flex flex-wrap justify-between items-start gap-3">
                <div>
                  <p className="text-sm font-semibold text-gray-900">
                    {formatMoney(d.declared_amount, d.currency_status === 'KNOWN' ? d.currency : undefined)} · {d.method}
                  </p>
                  <p className="text-xs text-gray-500 mt-1">Order: {d.order_id} · {formatDate(d.submitted_at)}</p>
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
                    <button onClick={() => openReview(d)} disabled={Boolean(actionId)}
                      className="bg-green-600 text-white text-xs px-3 py-1 rounded hover:bg-green-700 disabled:opacity-50">
                      Review payment
                    </button>
                    <div className="flex flex-col gap-1">
                      <input aria-label={`Rejection reason for ${d.id}`} type="text" placeholder="Reason" maxLength={256}
                        value={rejectReasons[d.id] || ''}
                        onFocus={() => { setEditingReasonId(d.id); }}
                        onChange={e => setRejectReasons(prev => ({ ...prev, [d.id]: e.target.value }))}
                        className={`text-xs border rounded px-1 py-0.5 w-28 ${editingReasonId === d.id ? 'ring-1 ring-indigo-500' : ''}`} />
                      <button onClick={() => handleReject(d.id)} disabled={Boolean(actionId) || !can(useAuthStore.getState().user, 'payments:confirm_declaration') || !(rejectReasons[d.id] || '').trim()}
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
              {review?.id === d.id && <section aria-label="Payment review" className="mt-4 border-t pt-4 space-y-3 text-sm">
                {review.loading && <p role="status">Loading customer and order context…</p>}
                {review.error && <p role="alert" className="text-amber-800">{review.error}</p>}
                {!mayReview() && !review.error && <p role="alert">Your access changed. Reopen the review after signing in with the required permissions.</p>}
                <button onClick={() => openReview(d)} disabled={Boolean(actionId)} className="underline">Refresh review</button>
                {mayReview() && review.data && <>
                  <dl className="grid gap-2 sm:grid-cols-2 break-words">
                    <div><dt className="text-gray-500">Customer</dt><dd>{review.data.retailer.name_resolution === 'RESOLVED' ? review.data.retailer.name : 'Customer name not verified'}</dd><dd className="text-xs break-all">{review.data.retailer.id}</dd></div>
                    <div><dt className="text-gray-500">Supplier</dt><dd>{review.data.supplier.name_resolution === 'RESOLVED' ? review.data.supplier.name : 'Supplier name not verified'}</dd><dd className="text-xs break-all">{review.data.supplier.code} · {review.data.supplier.id}</dd></div>
                    <div><dt className="text-gray-500">Order</dt><dd className="break-all">{review.data.order.id}</dd></div>
                    <div><dt className="text-gray-500">Active binding</dt><dd className="break-all">{review.data.binding.id}</dd></div>
                    <div><dt className="text-gray-500">Declared amount</dt><dd>{review.data.money.currency || 'Currency not verified'} {review.data.declaration.declared_amount}</dd></div>
                    <div><dt className="text-gray-500">Method / reference</dt><dd>{review.data.declaration.method} / {review.data.declaration.transfer_reference || 'No transfer reference (cash)'}</dd></div>
                    <div><dt className="text-gray-500">Remaining receivable at review</dt><dd>{review.data.money.balance_due === null ? 'Balance not verified' : `${review.data.money.currency} ${review.data.money.balance_due}`}</dd></div>
                    <div><dt className="text-gray-500">Observed at</dt><dd>{review.data.observed_at}</dd></div>
                  </dl>
                  <p className="text-xs text-gray-500">This is an observed order balance, not an amount lock or proof of receipt. The server validates every confirmation.</p>
                  {!readyContext(review.data) && <p role="alert">Review {review.data.review_state}: {review.data.reason_codes.join(', ') || 'Context not ready'}. Do not confirm blindly.</p>}
                  {!mayConfirm() && <p>You can review this payment, but cannot confirm it.</p>}
                  {readyContext(review.data) && mayConfirm() && <>
                    <label className="flex gap-2 items-start"><input type="checkbox" checked={verified} onChange={e => setVerified(e.target.checked)} disabled={Boolean(actionId)} />I have verified that this money was received for this customer and order.</label>
                    <button onClick={() => handleConfirm(d.id)} disabled={!verified || Boolean(actionId)} className="btn-primary">Confirm</button>
                  </>}
                </>}
              </section>}
            </article>
          ))}
          {totalPages > 1 && <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />}
        </div>
      )}
    </div>
  );
}
