import { useEffect, useState, useCallback } from 'react';
import { orderService } from '@/services/orderService';
import { financeService } from '@/services/financeService';
import { useAuthStore } from '@/stores/authStore';
import { useToastStore } from '@/stores/toastStore';
import { PageHeader } from '@/components/layout/PageHeader';
import type { Order, OrderStatus } from '@/types/order';
import {
  ORDER_STATUS_LABELS,
  ALLOWED_TRANSITIONS,
} from '@/types/order';
import { EmptyState } from '@/components/ui/EmptyState';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { TableSkeleton } from '@/components/skeletons/TableSkeleton';
import { ClipboardDocumentListIcon } from '@heroicons/react/24/outline';

export function OrderListPage() {
  const user = useAuthStore((s) => s.user);
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const canWrite = user?.permissions.includes('orders:write') ||
    user?.permissions.includes('orders:update') ||
    user?.roles.includes('admin');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await orderService.getAll(1, 50);
      setOrders(res.data.data.items);
    } catch {
      setError('Failed to load orders.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleConfirm = async (id: string) => {
    setActionLoading(id);
    try {
      await orderService.confirm(id);
      useToastStore.getState().addToast({
        type: 'success',
        title: 'Order Confirmed',
        message: `Order ${id.slice(0, 8)}… has been confirmed.`,
      });
      await load();
    } catch {
      // Error toast handled by global interceptor
    } finally {
      setActionLoading(null);
    }
  };

  const handleCancel = async (id: string) => {
    if (!window.confirm(`Are you sure you want to cancel Order #${id.slice(0, 8)}? This cannot be undone.`)) return;

    setActionLoading(id);
    try {
      await orderService.cancel(id);
      useToastStore.getState().addToast({
        type: 'success',
        title: 'Order Cancelled',
        message: `Order #${id.slice(0, 8)} has been cancelled.`,
      });
      await load();
    } catch {
      // Error toast handled by global interceptor
    } finally {
      setActionLoading(null);
    }
  };

  const handleReturn = async (id: string) => {
    if (!window.confirm('Are you sure you want to process a full return for this order? This will reverse ledger entries.')) return;
    setActionLoading(id);
    try {
      await orderService.returnOrder(id);
      useToastStore.getState().addToast({
        type: 'success',
        title: 'Order Returned',
        message: `Order ${id.slice(0, 8)}… has been returned. Refund entries posted.`,
      });
      await load();
    } catch {
      // Error toast handled by global interceptor
    } finally {
      setActionLoading(null);
    }
  };

  const canConfirm = (status: OrderStatus) =>
    ALLOWED_TRANSITIONS[status]?.includes('confirmed');

  const canCancelOrder = (status: OrderStatus) =>
    ALLOWED_TRANSITIONS[status]?.includes('cancelled');

  const canReturn = (status: OrderStatus) =>
    ALLOWED_TRANSITIONS[status]?.includes('returned');

  const canInvoice = (status: OrderStatus) => {
    const noInvoice: OrderStatus[] = ['draft', 'cancelled', 'voided'];
    return !noInvoice.includes(status);
  };

  const handleDownloadInvoice = async (orderId: string) => {
    try {
      const res = await financeService.getInvoice(orderId);
      const invoice = res.data.data;
      const blob = new Blob([JSON.stringify(invoice, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${invoice.invoice_number}.json`;
      a.click();
      URL.revokeObjectURL(url);
      useToastStore.getState().addToast({
        type: 'success',
        title: 'Invoice Downloaded',
        message: `Downloaded ${invoice.invoice_number}`,
      });
    } catch {
      // Error toast handled by global interceptor
    }
  };

  return (
    <div>
      <PageHeader
        title="Sales"
        description={loading ? 'Loading orders...' : `${orders.length} order${orders.length !== 1 ? 's' : ''} found`}
        action={
          <button onClick={load} disabled={loading} className="btn-secondary text-sm">
            Refresh
          </button>
        }
      />

      {loading && <TableSkeleton />}
      {error && <p className="mt-6 text-sm text-red-600">{error}</p>}

      {!loading && !error && orders.length === 0 && (
        <EmptyState
          icon={ClipboardDocumentListIcon}
          title="Ready to make your first sale?"
          description="Share your catalog link to get orders."
          action={
            <button className="btn-primary text-sm" disabled title="Manual order creation coming soon">
              Create Order
            </button>
          }
        />
      )}

      {!loading && !error && orders.length > 0 && (
        <div className="mt-6 overflow-hidden rounded-lg border border-gray-200 bg-white">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Order ID
                </th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Customer
                </th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Date
                </th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Status
                </th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Total
                </th>
                <th scope="col" className="px-6 py-3 text-right text-xs font-medium uppercase tracking-wider text-gray-500">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {orders.map((o) => (
                <tr key={o.id} className="hover:bg-gray-50">
                  <td className="whitespace-nowrap px-6 py-4 text-sm font-medium text-gray-900">
                    {o.code}
                  </td>
                  <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-500">
                    {o.customer_name}
                  </td>
                  <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-500">
                    {new Date(o.created_at).toLocaleDateString()}
                  </td>
                  <td className="whitespace-nowrap px-6 py-4">
                    <StatusBadge status={o.status} />
                  </td>
                  <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-500">
                    {o.currency} {o.total_amount.toLocaleString()}
                  </td>
                  <td className="whitespace-nowrap px-6 py-4 text-right text-sm font-medium">
                    <div className="flex justify-end gap-2">
                      {canWrite && canConfirm(o.status) && (
                        <button
                          onClick={() => handleConfirm(o.id)}
                          disabled={!!actionLoading}
                          className="text-blue-600 hover:text-blue-900 disabled:opacity-50"
                        >
                          Confirm
                        </button>
                      )}
                      {canWrite && canCancelOrder(o.status) && (
                        <button
                          onClick={() => handleCancel(o.id)}
                          disabled={!!actionLoading}
                          className="text-red-600 hover:text-red-900 disabled:opacity-50"
                        >
                          Cancel
                        </button>
                      )}
                      {canWrite && canReturn(o.status) && (
                        <button
                          onClick={() => handleReturn(o.id)}
                          disabled={!!actionLoading}
                          className="text-amber-600 hover:text-amber-900 disabled:opacity-50"
                        >
                          Return
                        </button>
                      )}
                      {canInvoice(o.status) && (
                        <button
                          onClick={() => handleDownloadInvoice(o.id)}
                          className="text-gray-600 hover:text-gray-900"
                          title="Download Invoice"
                        >
                          Invoice
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )
      }
    </div >
  );
}
