import { useEffect, useState, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { paymentService, type PaymentListItem } from '@/services/paymentService';
import { formatMoney } from '@/utils/printFormat';
import { PageHeader } from '@/components/layout/PageHeader';
import { TableSkeleton } from '@/components/skeletons/TableSkeleton';
import { BanknotesIcon } from '@heroicons/react/24/outline';
import { EmptyState } from '@/components/ui/EmptyState';
import { Pagination } from '@/components/ui/Pagination';

/** Sum exact decimal amounts digit-for-digit via BigInt; no float
 * arithmetic anywhere, so the page total equals the received values exactly.
 * Returns '' for any malformed input (caller then shows no total). */
function sumExactAmounts(values: Array<string | number>): string {
  type Part = { negative: boolean; digits: bigint; fracLen: number };
  const parts: Part[] = [];
  let scale = 0;
  for (const value of values) {
    const match = /^([+-]?)(\d*)(?:\.(\d*))?$/.exec(String(value ?? '').trim());
    if (!match || (match[2] === '' && !match[3])) return '';
    const negative = match[1] === '-';
    const intPart = match[2] || '0';
    const frac = match[3] ?? '';
    parts.push({ negative, digits: BigInt(intPart + frac || '0'), fracLen: frac.length });
    scale = Math.max(scale, frac.length);
  }
  let total = 0n;
  for (const part of parts) {
    const scaled = part.digits * 10n ** BigInt(scale - part.fracLen);
    total += part.negative ? -scaled : scaled;
  }
  const negative = total < 0n;
  if (negative) total = -total;
  const digits = total.toString().padStart(scale + 1, '0');
  const plain = scale === 0 ? digits : `${digits.slice(0, -scale)}.${digits.slice(-scale)}`;
  return negative ? `-${plain}` : plain;
}

/** Parse and clamp the `page` query param. Invalid/missing -> 1. */
function parsePage(value: string | null): number {
  if (!value) return 1;
  const n = Number(value);
  return Number.isInteger(n) && n > 0 ? n : 1;
}

export function PaymentListPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const page = parsePage(searchParams.get('page'));
  const searchKey = searchParams.toString();

  const [payments, setPayments] = useState<PaymentListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [size] = useState(20);
  const [total, setTotal] = useState(0);
  const totalPages = Math.ceil(total / size) || 1;

  // Canonicalize: strip noisy/invalid params via replace navigation.
  useEffect(() => {
    const next = new URLSearchParams();
    if (page !== 1) next.set('page', String(page));
    if (next.toString() !== searchKey) {
      setSearchParams(next, { replace: true });
    }
  }, [page, searchKey, setSearchParams]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await paymentService.getAll(page, size);
      const { items, pagination } = res.data.data;

      // Page-recovery: a bookmarked or shared URL may request a page beyond
      // the available data. Redirect to the last valid page so the user sees
      // content instead of a misleading "No payments found" empty state.
      if (page > pagination.pages && pagination.pages > 0) {
        const recovered = new URLSearchParams();
        if (pagination.pages !== 1) recovered.set('page', String(pagination.pages));
        setSearchParams(recovered, { replace: true });
        return; // keep loading skeleton; the URL change triggers a fresh fetch
      }

      setPayments(items);
      setTotal(pagination.total);
      setLoading(false);
    } catch {
      setError('Could not load payment records. Check your connection and try again. If the problem persists, contact support.');
      setLoading(false);
    }
  }, [page, size, setSearchParams]);

  useEffect(() => {
    load();
  }, [load]);

  const changePage = (nextPage: number) => {
    const next = new URLSearchParams();
    if (nextPage !== 1) next.set('page', String(nextPage));
    setSearchParams(next);
  };

  // Currency comes only from each payment's order snapshot. A page total is
  // shown only when every row is a verified KES/UGX snapshot AND exactly one
  // currency is present; any unverified or mixed page shows no total rather
  // than a misleading single-currency sum.
  const allCurrenciesVerified = payments.length > 0 && payments.every(
    (p) => p.currency_status === 'KNOWN' && (p.currency === 'KES' || p.currency === 'UGX'),
  );
  const distinctCurrencies = new Set(payments.map((p) => p.currency));
  const exactTotal = allCurrenciesVerified && distinctCurrencies.size === 1
    ? sumExactAmounts(payments.map((p) => p.amount))
    : '';
  const pageTotal = exactTotal !== '' ? formatMoney(exactTotal, payments[0].currency) : null;

  return (
    <div>
      <PageHeader
        title="Payments"
        description="View all payment records."
        action={
          <button onClick={load} disabled={loading} className="btn-secondary text-sm">
            {loading ? 'Refreshing...' : 'Refresh'}
          </button>
        }
      />

      {loading && <TableSkeleton />}

      {error && (
        <div className="mt-6 flex items-center gap-3 rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">
          <span>{error}</span>
          <button
            onClick={load}
            className="inline-flex items-center gap-1 rounded-md bg-red-100 px-2 py-1 text-xs font-medium text-red-800 hover:bg-red-200"
          >
            Retry
          </button>
        </div>
      )}

      {!loading && !error && payments.length === 0 && (
        <EmptyState
          icon={BanknotesIcon}
          title="No payments yet"
          description="Payment records will appear here once you start collecting payments against orders."
        />
      )}

      {!loading && !error && payments.length > 0 && (
        <div className="mt-6 flex flex-col gap-4">
          <div className="flex flex-wrap items-center gap-4 rounded-lg border border-gray-200 bg-gray-50 px-4 py-2 text-sm text-gray-600">
            <span>Page {page} of {totalPages}</span>
            <span className="text-gray-300">|</span>
            <span>{total} records</span>
            <span className="text-gray-300">|</span>
            {pageTotal
              ? <span>Page total: {pageTotal}</span>
              : <span>Page total: not shown (unverified or mixed-currency page)</span>}
            <span className="text-gray-300">|</span>
            <span className="text-green-700">{payments.filter(p => p.status === 'completed').length} completed</span>
            <span className="text-yellow-700">{payments.filter(p => p.status === 'pending').length} pending</span>
          </div>
          <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                    Date
                  </th>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                    Order ID
                  </th>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                    Method
                  </th>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                    Transaction ID
                  </th>
                  <th scope="col" className="px-6 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
                    Amount
                  </th>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 bg-white">
                {payments.map((p) => (
                  <tr key={p.id} className="hover:bg-gray-50">
                    <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-500">
                      {new Date(p.created_at).toLocaleString()}
                    </td>
                    <td className="whitespace-nowrap px-6 py-4 text-sm font-mono text-gray-600">
                      {p.order_id.slice(0, 8)}...
                    </td>
                    <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-900 capitalize">
                      {p.method}
                    </td>
                    <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-500">
                      {p.transaction_id || '-'}
                    </td>
                    <td className="whitespace-nowrap px-6 py-4 text-sm font-medium text-right text-gray-900">
                      {formatMoney(p.amount, p.currency)}
                    </td>
                    <td className="whitespace-nowrap px-6 py-4 text-sm">
                      <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
                        p.status === 'completed' ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'
                      }`}>
                        {p.status.charAt(0).toUpperCase() + p.status.slice(1)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <Pagination
            page={page}
            totalPages={totalPages}
            onPageChange={changePage}
          />
        </div>
      )}
    </div>
  );
}
