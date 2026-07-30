import { useCallback, useEffect, useState } from 'react';
import { BanknotesIcon, ReceiptRefundIcon } from '@heroicons/react/24/outline';
import { EmptyState } from '@/components/ui/EmptyState';
import { Pagination } from '@/components/ui/Pagination';
import { clientFinanceService } from '@/services/clientFinanceService';
import type { ClientPayment } from '@/types/client';

const METHOD_LABEL: Record<string, string> = {
  cash: 'Cash payment',
  transfer: 'Transfer payment',
  credit: 'Credit sale',
};

const STATUS_LABEL: Record<string, string> = {
  pending: 'Pending',
  completed: 'Completed',
};

function formatMoney(amount: string) {
  return `KES ${Number(amount).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatDate(value: string) {
  return new Date(value).toLocaleDateString('en-KE', { month: 'short', day: 'numeric', year: 'numeric' });
}

function paymentMethodLabel(payment: ClientPayment) {
  if (payment.status === 'completed' && payment.method === 'cash') {
    return 'Cash received';
  }
  if (payment.status === 'completed' && payment.method === 'transfer') {
    return 'Transfer received';
  }
  return METHOD_LABEL[payment.method] ?? payment.method;
}

export function ClientPaymentHistoryPage() {
  const [payments, setPayments] = useState<ClientPayment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await clientFinanceService.getPayments(page, 20);
      setPayments(res.data.data.items);
      setTotalPages(res.data.data.pagination.pages || 1);
    } catch {
      setError('Failed to load payments. Please try again.');
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-4">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-primary-600">Read only</p>
        <h1 className="text-lg font-bold text-gray-900">Payment History</h1>
      </div>

      {loading && <div className="rounded-xl border border-gray-200 bg-white p-4 text-sm text-gray-500">Loading payments...</div>}

      {!loading && error && (
        <div className="rounded-xl border border-red-100 bg-red-50 p-4 text-sm text-red-700">
          <p>{error}</p>
          <button type="button" onClick={load} className="mt-3 rounded-lg bg-red-600 px-3 py-2 text-sm font-medium text-white">
            Try again
          </button>
        </div>
      )}

      {!loading && !error && payments.length === 0 && (
        <EmptyState icon={ReceiptRefundIcon} title="No payments yet" description="Your supplier payment history will appear here." />
      )}

      {!loading && !error && payments.length > 0 && (
        <>
          <div className="space-y-2">
            {payments.map((payment) => (
              <article key={payment.id} className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-xs text-gray-400">Order #{payment.order_id.slice(0, 8)}</p>
                    <p className="mt-1 text-sm font-semibold text-gray-900">{paymentMethodLabel(payment)}</p>
                    <p className="mt-1 text-xs text-gray-500">{formatDate(payment.created_at)} · {STATUS_LABEL[payment.status] ?? payment.status}</p>
                  </div>
                  <div className="flex items-center gap-2 text-right">
                    <BanknotesIcon className="h-5 w-5 text-primary-500" />
                    <span className="text-sm font-bold text-gray-900">{formatMoney(payment.amount)}</span>
                  </div>
                </div>
              </article>
            ))}
          </div>
          <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />
        </>
      )}
    </div>
  );
}
