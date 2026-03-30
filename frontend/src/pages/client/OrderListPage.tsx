import { useEffect, useState, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ClipboardDocumentListIcon, PlusIcon } from '@heroicons/react/24/outline';
import { clientOrderService } from '@/services/clientOrderService';
import { EmptyState } from '@/components/ui/EmptyState';
import { Pagination } from '@/components/ui/Pagination';
import type { ClientOrder } from '@/types/client';

const STATUS_BADGE: Record<string, { label: string; className: string }> = {
  CREATED: { label: 'Created', className: 'bg-blue-100 text-blue-700' },
  CONFIRMED: { label: 'Confirmed', className: 'bg-indigo-100 text-indigo-700' },
  DELIVERED: { label: 'Delivered', className: 'bg-green-100 text-green-700' },
  CANCELLED: { label: 'Cancelled', className: 'bg-red-100 text-red-700' },
  RETURNED: { label: 'Returned', className: 'bg-gray-100 text-gray-700' },
};

const STATUS_FILTERS: { value: string; label: string }[] = [
  { value: '', label: 'All' },
  { value: 'CREATED', label: 'Created' },
  { value: 'CONFIRMED', label: 'Confirmed' },
  { value: 'DELIVERED', label: 'Delivered' },
  { value: 'CANCELLED', label: 'Cancelled' },
];

export function ClientOrderListPage() {
  const navigate = useNavigate();
  const [orders, setOrders] = useState<ClientOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [statusFilter, setStatusFilter] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await clientOrderService.getAll(page, 20, statusFilter || undefined);
      setOrders(res.data.data.items);
      setTotalPages(res.data.data.pagination.pages);
    } catch {
      setError('Failed to load orders. Please try again.');
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter]);

  useEffect(() => {
    load();
  }, [load]);

  const formatDate = (iso: string) => {
    return new Date(iso).toLocaleDateString('en-KE', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('en-KE', {
      style: 'currency',
      currency: 'KES',
    }).format(amount);
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-gray-900">My Orders</h1>
        <button
          onClick={() => navigate('/client/orders/new')}
          className="inline-flex items-center gap-1.5 rounded-lg bg-primary-600 px-3 py-2 text-sm font-medium text-white shadow-sm hover:bg-primary-700 transition"
        >
          <PlusIcon className="h-4 w-4" />
          New Order
        </button>
      </div>

      {/* Status Filter Tabs */}
      <div className="flex gap-1 overflow-x-auto rounded-lg bg-gray-100 p-1">
        {STATUS_FILTERS.map((f) => (
          <button
            key={f.value}
            onClick={() => { setStatusFilter(f.value); setPage(1); }}
            className={`flex-shrink-0 rounded-md px-3 py-1.5 text-xs font-medium transition ${
              statusFilter === f.value
                ? 'bg-white text-gray-900 shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</div>
      )}

      {/* Loading */}
      {loading && (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="animate-pulse rounded-xl border border-gray-200 bg-white p-4">
              <div className="mb-2 h-4 w-1/3 rounded bg-gray-200" />
              <div className="h-3 w-2/3 rounded bg-gray-200" />
            </div>
          ))}
        </div>
      )}

      {/* Empty State */}
      {!loading && !error && orders.length === 0 && (
        <EmptyState
          icon={ClipboardDocumentListIcon}
          title="No orders yet"
          description="Your order history will appear here."
          action={
            <button
              onClick={() => navigate('/client/orders/new')}
              className="inline-flex items-center gap-1.5 rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-primary-700 transition"
            >
              <PlusIcon className="h-4 w-4" />
              Place your first order
            </button>
          }
        />
      )}

      {/* Order List */}
      {!loading && !error && orders.length > 0 && (
        <>
          <div className="space-y-2">
            {orders.map((order) => {
              const badge = STATUS_BADGE[order.status] ?? STATUS_BADGE.CREATED;

              return (
                <Link
                  key={order.id}
                  to={`/client/orders/${order.id}`}
                  className="block rounded-xl border border-gray-200 bg-white p-4 shadow-sm hover:shadow-md hover:border-primary-200 transition"
                >
                  <div className="flex items-start justify-between">
                    <div>
                      <p className="text-xs text-gray-400 font-mono">
                        #{order.id.slice(0, 8)}
                      </p>
                      <p className="mt-0.5 text-sm font-medium text-gray-900">
                        {order.item_count} item{order.item_count !== 1 ? 's' : ''}
                      </p>
                    </div>
                    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${badge.className}`}>
                      {badge.label}
                    </span>
                  </div>

                  <div className="mt-2 flex items-center justify-between">
                    <span className="text-sm font-semibold text-gray-900">
                      {formatCurrency(order.total_amount)}
                    </span>
                    <span className="text-xs text-gray-400">
                      {formatDate(order.created_at)}
                    </span>
                  </div>
                </Link>
              );
            })}
          </div>

          <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />
        </>
      )}
    </div>
  );
}
