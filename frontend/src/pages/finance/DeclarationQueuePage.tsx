/** Wholesaler cashier declaration queue (DC-12R1-S3-S2B-I2B). */
import { useCallback, useEffect, useState } from 'react';
import { BanknotesIcon } from '@heroicons/react/24/outline';
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
  const [rejectReason, setRejectReason] = useState('');

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
    try {
      await confirmDeclaration(id);
      load();
    } catch (err: unknown) {
      setError((err as Error).message || 'Confirm failed');
    } finally {
      setActionId(null);
    }
  };

  const handleReject = async (id: string) => {
    if (!rejectReason.trim()) return;
    setActionId(id);
    try {
      await rejectDeclaration(id, rejectReason.trim());
      setRejectReason('');
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
      {declarations.length === 0 ? (
        <EmptyState icon={BanknotesIcon} title="No pending declarations" message="All declarations have been processed." />
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
                </div>
                {d.status === 'pending' && (
                  <div className="flex gap-2">
                    <button onClick={() => handleConfirm(d.id)} disabled={actionId === d.id}
                      className="bg-green-600 text-white text-xs px-3 py-1 rounded hover:bg-green-700 disabled:opacity-50">
                      Confirm
                    </button>
                    <div className="flex flex-col gap-1">
                      <input type="text" placeholder="Reason" maxLength={256}
                        value={(actionId === d.id || !actionId) ? rejectReason : ''}
                        onChange={e => { setRejectReason(e.target.value); setActionId(d.id); }}
                        className="text-xs border rounded px-1 py-0.5 w-28" />
                      <button onClick={() => handleReject(d.id)} disabled={actionId === d.id}
                        className="bg-red-600 text-white text-xs px-3 py-1 rounded hover:bg-red-700 disabled:opacity-50">
                        Reject
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
