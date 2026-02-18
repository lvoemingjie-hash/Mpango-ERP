import { useEffect, useState, useCallback } from 'react';
import { orderService } from '@/services/orderService';
import { financeService } from '@/services/financeService';
import { useAuthStore } from '@/stores/authStore';
import { Badge } from '@/components/ui/Badge';
import { useToastStore } from '@/stores/toastStore';
import type { Order, OrderStatus } from '@/types/order';
import {
  ORDER_STATUS_LABELS,
  ORDER_STATUS_COLORS,
  ALLOWED_TRANSITIONS,
} from '@/types/order';

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
    setActionLoading(id);
    try {
      await orderService.cancel(id);
      useToastStore.getState().addToast({
        type: 'success',
        title: 'Order Cancelled',
        message: `Order ${id.slice(0, 8)}… has been cancelled.`,
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
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Orders</h1>
          <p className="mt-1 text-sm text-gray-500">
            {orders.length} order{orders.length !== 1 ? 's' : ''} found
          </p>
        </div>
        <button onClick={load} disabled={loading} className="btn-secondary text-sm">
          Refresh
        </button>
      </div>

      {loading && <p className="mt-6 text-sm text-gray-400">Loading orders…</p>}
      {error && <p className="mt-6 text-sm text-red-600">{error}</p>}

      {!loading && !error && (
        <div className="mt-4 overflow-x-auto rounded-lg border border-gray-200 bg-white">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left font-medium text-gray-500">Order ID</th>
                <th className="px-4 py-3 text-left font-medium text-gray-500">Status</th>
                <th className="px-4 py-3 text-left font-medium text-gray-500">Items</th>
                <th className="px-4 py-3 text-right font-medium text-gray-500">Total</th>
                <th className="px-4 py-3 text-left font-medium text-gray-500">Notes</th>
                <th className="px-4 py-3 text-left font-medium text-gray-500">Created</th>
                <th className="px-4 py-3 text-right font-medium text-gray-500">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {orders.map((o) => (
                <tr key={o.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-mono text-xs text-gray-600">
                    {o.id.slice(0, 8)}…
                  </td>
                  <td className="px-4 py-3">
                    <Badge
                      variant={
                        ORDER_STATUS_COLORS[o.status] as
                        | 'green'
                        | 'gray'
                        | 'red'
                        | 'blue'
                        | 'yellow'
                      }
                    >
                      {ORDER_STATUS_LABELS[o.status]}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 text-gray-700">{o.items.length}</td>
                  <td className="px-4 py-3 text-right font-medium text-gray-900">
                    KES {o.total_amount.toLocaleString()}
                  </td>
                  <td className="px-4 py-3 text-gray-500 truncate max-w-[180px]">
                    {o.notes || '—'}
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-500">
                    {new Date(o.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-2">
                      {canWrite && canConfirm(o.status) && (
                        <button
                          onClick={() => handleConfirm(o.id)}
                          disabled={actionLoading === o.id}
                          className="rounded bg-blue-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50"
                        >
                          {actionLoading === o.id ? '…' : 'Confirm'}
                        </button>
                      )}
                      {canWrite && canCancelOrder(o.status) && (
                        <button
                          onClick={() => handleCancel(o.id)}
                          disabled={actionLoading === o.id}
                          className="rounded bg-red-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-50"
                        >
                          {actionLoading === o.id ? '…' : 'Cancel'}
                        </button>
                      )}
                      {canWrite && canReturn(o.status) && (
                        <button
                          onClick={() => handleReturn(o.id)}
                          disabled={actionLoading === o.id}
                          className="rounded bg-amber-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-amber-700 disabled:opacity-50"
                        >
                          {actionLoading === o.id ? '…' : 'Return'}
                        </button>
                      )}
                      {!canConfirm(o.status) && !canCancelOrder(o.status) && !canReturn(o.status) && (
                        <span className="text-xs text-gray-400">No actions</span>
                      )}
                      {canInvoice(o.status) && (
                        <button
                          onClick={() => handleDownloadInvoice(o.id)}
                          className="rounded bg-emerald-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-emerald-700"
                        >
                          Invoice
                        </button>
                      )}
                      {!canWrite && (canConfirm(o.status) || canCancelOrder(o.status) || canReturn(o.status)) && (
                        <span className="text-xs text-gray-400" title="Missing orders:write permission">
                          Read-only
                        </span>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {orders.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-gray-400">
                    No orders found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
