/** Retailer declaration history (DC-12R1-S3-S2B-I2B). */
import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { BanknotesIcon, PrinterIcon } from '@heroicons/react/24/outline';
import { EmptyState } from '@/components/ui/EmptyState';
import { Pagination } from '@/components/ui/Pagination';
import { listClientDeclarations } from '@/services/declarationService';
import type { PaymentDeclaration } from '@/types/declaration';
import { formatMoney } from '@/utils/printFormat';

const STATUS_LABEL: Record<string, string> = {
  pending: 'Pending — Not Received',
  confirmed: 'Payment Received',
  rejected: 'Rejected',
};

function formatDate(value: string) {
  return new Date(value).toLocaleDateString('en-KE', { month: 'short', day: 'numeric', year: 'numeric' });
}

function declarationLabel(d: PaymentDeclaration) {
  if (d.status === 'confirmed') return `Payment Received${d.receipt_number ? ` · ${d.receipt_number}` : ''}`;
  if (d.status === 'pending') return 'Payment Declaration — Not Received';
  return d.reason || 'Rejected';
}

export default function DeclarationHistoryPage() {
  const [declarations, setDeclarations] = useState<PaymentDeclaration[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await listClientDeclarations(page, 20);
      setDeclarations((res.data as { items: PaymentDeclaration[] }).items);
      setTotalPages((res.data as { pagination: { pages: number } }).pagination.pages);
    } catch (err: unknown) {
      setError((err as { response?: { status?: number } }).response?.status === 403 ? 'Your account cannot view these declarations.' : 'Could not load declarations. Please retry.');
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <div className="flex justify-center p-8"><p className="text-gray-500">Loading declarations...</p></div>;
  if (error) return (
    <div className="p-4">
      <div className="bg-red-50 text-red-700 p-3 rounded">{error}</div>
      <button onClick={load} className="mt-2 text-indigo-600 text-sm">Try again</button>
    </div>
  );

  return (
    <div className="min-h-screen bg-gray-50 p-4">
      <h1 className="text-lg font-semibold text-gray-900 mb-4">My Declarations</h1>
      <p className="mb-4 text-sm text-gray-600">If a submission result was unknown, reopen its order and use Declare Payment in the same browser tab to recover the original request. Do not record the payment twice.</p>
      <Link to="/client/orders" className="mb-4 inline-block text-sm text-primary-700 underline">Find the original order</Link>
      {declarations.length === 0 ? (
        <EmptyState icon={BanknotesIcon} title="No declarations" description="You haven't submitted any payment declarations yet." />
      ) : (
        <div className="space-y-3">
          {declarations.map((d) => (
            <div key={d.id} className="bg-white rounded-xl shadow p-4">
              <p className="text-sm font-semibold text-gray-900">{declarationLabel(d)}</p>
              <p className="mt-1 text-xs text-gray-500">
                {formatDate(d.submitted_at)} · {STATUS_LABEL[d.status] ?? d.status} · {formatMoney(d.declared_amount, d.currency_status === 'KNOWN' ? d.currency : undefined)} ({d.method})
              </p>
              {d.reason && d.status === 'rejected' && (
                <p className="mt-1 text-xs text-red-600">Reason: {d.reason}</p>
              )}
              {/* DC-12R1-S3-S2B-I2C-I2: printable declaration (Contract B).
                  Receipt link (Contract C) is shown ONLY when confirmed. */}
              <div className="no-print mt-2 flex flex-wrap gap-2">
                <Link to={`/client/orders/${encodeURIComponent(d.order_id)}`} className="text-xs text-primary-700 underline">View order</Link>
                <Link
                  to={`/client/declarations/${d.id}/print`}
                  className="inline-flex items-center gap-1 rounded border border-gray-300 bg-white px-2 py-0.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
                >
                  <PrinterIcon className="h-3.5 w-3.5" />
                  Print
                </Link>
                {d.status === 'confirmed' && (
                  <Link
                    to={`/client/declarations/${d.id}/receipt`}
                    className="inline-flex items-center gap-1 rounded border border-gray-300 bg-white px-2 py-0.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
                  >
                    <PrinterIcon className="h-3.5 w-3.5" />
                    Receipt
                  </Link>
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
