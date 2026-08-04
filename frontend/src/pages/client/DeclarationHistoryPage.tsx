/** Retailer declaration history (DC-12R1-S3-S2B-I2B). */
import { useCallback, useEffect, useState } from 'react';
import { BanknotesIcon } from '@heroicons/react/24/outline';
import { EmptyState } from '@/components/ui/EmptyState';
import { Pagination } from '@/components/ui/Pagination';
import { listClientDeclarations } from '@/services/declarationService';
import type { PaymentDeclaration } from '@/types/declaration';

const STATUS_LABEL: Record<string, string> = {
  pending: 'Pending — Not Received',
  confirmed: 'Payment Received',
  rejected: 'Rejected',
};

function formatMoney(amount: string) {
  return `KES ${Number(amount).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

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
      setError((err as Error).message || 'Failed to load declarations');
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
      {declarations.length === 0 ? (
        <EmptyState icon={BanknotesIcon} title="No declarations" description="You haven't submitted any payment declarations yet." />
      ) : (
        <div className="space-y-3">
          {declarations.map((d) => (
            <div key={d.id} className="bg-white rounded-xl shadow p-4">
              <p className="text-sm font-semibold text-gray-900">{declarationLabel(d)}</p>
              <p className="mt-1 text-xs text-gray-500">
                {formatDate(d.submitted_at)} · {STATUS_LABEL[d.status] ?? d.status} · {formatMoney(d.declared_amount)} ({d.method})
              </p>
              {d.reason && d.status === 'rejected' && (
                <p className="mt-1 text-xs text-red-600">Reason: {d.reason}</p>
              )}
            </div>
          ))}
          {totalPages > 1 && <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />}
        </div>
      )}
    </div>
  );
}
