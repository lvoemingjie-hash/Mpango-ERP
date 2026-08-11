import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ScaleIcon, PrinterIcon } from '@heroicons/react/24/outline';
import { clientFinanceService } from '@/services/clientFinanceService';
import { eatMonthRange } from '@/utils/printFormat';
import type { ClientFinanceBalance } from '@/types/client';

function formatMoney(amount: string) {
  return `KES ${Number(amount).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatDate(value: string) {
  return new Date(value).toLocaleString('en-KE', { month: 'short', day: 'numeric', year: 'numeric' });
}

/** Current calendar month in Africa/Nairobi (EAT) — R1 rule 6: never
 *  browser-local dates for statement ranges. */
function monthRangeHref(): string {
  const { from, to } = eatMonthRange();
  return `/client/statements/print?from=${from}&to=${to}`;
}

export function ClientFinanceBalancePage() {
  const [balance, setBalance] = useState<ClientFinanceBalance | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await clientFinanceService.getBalance();
      setBalance(res.data.data);
    } catch {
      setError('Failed to load balance. Please try again.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-4">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-primary-600">Authoritative</p>
        <h1 className="text-lg font-bold text-gray-900">Outstanding Balance</h1>
      </div>

      {loading && <div className="rounded-xl border border-gray-200 bg-white p-4 text-sm text-gray-500">Loading balance...</div>}

      {!loading && error && (
        <div className="rounded-xl border border-red-100 bg-red-50 p-4 text-sm text-red-700">
          <p>{error}</p>
          <button type="button" onClick={load} className="mt-3 rounded-lg bg-red-600 px-3 py-2 text-sm font-medium text-white">
            Try again
          </button>
        </div>
      )}

      {!loading && !error && balance && (
        <section className="rounded-2xl border border-primary-100 bg-white p-5 shadow-sm">
          <div className="flex items-center gap-3">
            <div className="rounded-full bg-primary-50 p-3 text-primary-600">
              <ScaleIcon className="h-6 w-6" />
            </div>
            <div>
              <p className="text-sm text-gray-500">Outstanding Balance</p>
              <p className="text-2xl font-bold text-gray-900">{formatMoney(balance.outstanding_balance)}</p>
            </div>
          </div>
          <p className="mt-4 text-sm text-gray-600">
            This value is from your supplier relationship and is not recalculated on this device.
          </p>
          <p className="mt-2 text-xs text-gray-400">Updated {formatDate(balance.updated_at)}</p>
          <div className="mt-4 border-t border-gray-100 pt-3">
            <Link
              to={monthRangeHref()}
              className="inline-flex items-center gap-1.5 rounded-lg bg-primary-600 px-3 py-2 text-sm font-medium text-white shadow-sm hover:bg-primary-700"
              data-testid="retailer-statement-print-link"
            >
              <PrinterIcon className="h-4 w-4" />
              Print monthly statement
            </Link>
          </div>
        </section>
      )}
    </div>
  );
}
