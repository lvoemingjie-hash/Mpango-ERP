import { useEffect, useRef, useState, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { orderService } from '@/services/orderService';
import type { PayOrderData } from '@/services/orderService';
import { financeService } from '@/services/financeService';
import { useAuthStore } from '@/stores/authStore';
import { useToastStore } from '@/stores/toastStore';
import { PageHeader } from '@/components/layout/PageHeader';
import { PaymentRecordModal } from '@/components/ui/PaymentRecordModal';
import { paymentService } from '@/services/paymentService';
import type { Order, OrderStatus } from '@/types/order';
import {
  ALLOWED_TRANSITIONS,
} from '@/types/order';
import { EmptyState } from '@/components/ui/EmptyState';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { TableSkeleton } from '@/components/skeletons/TableSkeleton';
import { ClipboardDocumentListIcon } from '@heroicons/react/24/outline';

function buildFinanceCollectionReturnPath(returnPath: string, orderId: string): string {
  const [path, query = ''] = returnPath.split('?');
  const params = new URLSearchParams(query);
  params.set('collection', 'recorded');
  params.set('collectedOrder', orderId);
  const search = params.toString();
  return search ? `${path}?${search}` : path;
}

export function OrderListPage() {
  const user = useAuthStore((s) => s.user);
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const handledCollectIdRef = useRef<string | null>(null);
  const collectReturnPathRef = useRef<string | null>(null);
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  // Phase 5: payment modal state
  const [payModalOrder, setPayModalOrder] = useState<Order | null>(null);

  const hasUpdatePermission = user?.permissions.includes('orders:update') || user?.roles.includes('admin');
  const hasCreatePermission = user?.permissions.includes('orders:create') || user?.roles.includes('admin');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await orderService.getAll(1, 50);
      setOrders(res.data.data.items);
    } catch {
      setError('Could not load orders. Check your connection and try refreshing. If the problem persists, contact support.');
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
        message: `Order ${id.slice(0, 8)}... has been confirmed.`,
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

  // Phase 5: structured payment recording via modal
  const handlePaySubmit = async (data: PayOrderData, idempotencyKey: string) => {
    if (!payModalOrder) return;
    const orderId = payModalOrder.id;
    setActionLoading(orderId);
    try {
      const res = await orderService.pay(orderId, data, idempotencyKey);
      const resp = res.data.data;
      useToastStore.getState().addToast({
        type: 'success',
        title: 'Payment Recorded',
        message: resp.payment_id
          ? `KES ${Number(resp.payment_amount).toLocaleString()} via ${resp.payment_method}. Order ${orderId.slice(0, 8)}... -> ${resp.status}.`
          : `Order ${orderId.slice(0, 8)}... marked as ${resp.status}.`,
      });
      setPayModalOrder(null);
      const returnPath = collectReturnPathRef.current;
      collectReturnPathRef.current = null;
      if (returnPath) {
        navigate(buildFinanceCollectionReturnPath(returnPath, orderId));
      } else {
        await load();
      }
    } catch {
      // Error toast handled by global interceptor -- leave modal open so user can retry
    } finally {
      setActionLoading(null);
    }
  };

  const handleFulfill = async (id: string) => {
    if (!window.confirm(`Fulfill Order #${id.slice(0, 8)}? This will deduct inventory.`)) return;
    setActionLoading(id);
    try {
      await orderService.fulfill(id);
      useToastStore.getState().addToast({
        type: 'success',
        title: 'Order Fulfilled',
        message: `Order ${id.slice(0, 8)}... fulfilled. Inventory deducted.`,
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
        message: `Order ${id.slice(0, 8)}... has been returned. Refund entries posted.`,
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

  /** Phase 5: can pay from confirmed or partially_paid */
  const canPay = (status: OrderStatus) =>
    ALLOWED_TRANSITIONS[status]?.includes('paid') || status === 'partially_paid';

  const canFulfill = (status: OrderStatus) =>
    ALLOWED_TRANSITIONS[status]?.includes('fulfilled');

  const canReturn = (status: OrderStatus) =>
    ALLOWED_TRANSITIONS[status]?.includes('returned');

  const [payRemaining, setPayRemaining] = useState<number | null>(null);

  const handleOpenPayModal = async (order: Order) => {
    setPayModalOrder(order);
    // Fetch prior payments to compute true remaining balance
    try {
      const res = await paymentService.getByOrder(order.id);
      const items = res.data.data.items;
      const totalPaid = items.reduce((sum, p) => sum + Number(p.amount), 0);
      setPayRemaining(order.total_amount - totalPaid);
    } catch {
      // Fallback to full order total if payments can't be fetched
      setPayRemaining(order.total_amount);
    }
  };

  useEffect(() => {
    const collectOrderId = searchParams.get('collect');
    const returnTo = searchParams.get('returnTo');
    if (!collectOrderId || loading || payModalOrder || handledCollectIdRef.current === collectOrderId) return;

    // Consume the param exactly once before opening the existing payment flow.
    handledCollectIdRef.current = collectOrderId;

    if (returnTo === 'finance') {
      const ALLOWED_TABS = ['all', 'credit_receivable', 'unpaid_order'] as const;
      const rawTab = searchParams.get('financeTab');
      const rawPage = searchParams.get('financePage');
      const financeTab = rawTab && (ALLOWED_TABS as readonly string[]).includes(rawTab) ? rawTab : null;
      const financePage = rawPage && Number.isInteger(Number(rawPage)) && Number(rawPage) > 0 ? Number(rawPage) : null;
      const params = new URLSearchParams();
      if (financeTab && financeTab !== 'all') params.set('tab', financeTab);
      if (financePage && financePage !== 1) params.set('page', String(financePage));
      collectReturnPathRef.current = params.toString() ? `/finance?${params.toString()}` : '/finance';
    } else {
      collectReturnPathRef.current = null;
    }

    setSearchParams({}, { replace: true });

    // Fast path: order already in loaded rows
    const order = orders.find((o) => o.id === collectOrderId);
    if (order) {
      if (hasUpdatePermission && canPay(order.status)) {
        void handleOpenPayModal(order);
      } else {
        useToastStore.getState().addToast({
          type: 'error',
          title: 'Cannot Record Payment',
          message: !hasUpdatePermission
            ? 'You do not have permission to record payments.'
            : `Order ${collectOrderId.slice(0, 8)}... is not payable (status: ${order.status}).`,
        });
      }
      return;
    }

    // Fallback: fetch the specific order when it is outside the current page.
    (async () => {
      try {
        const res = await orderService.getById(collectOrderId);
        const fetched = res.data.data;
        if (hasUpdatePermission && canPay(fetched.status)) {
          void handleOpenPayModal(fetched);
        } else {
          useToastStore.getState().addToast({
            type: 'error',
            title: 'Cannot Record Payment',
            message: !hasUpdatePermission
              ? 'You do not have permission to record payments.'
              : `Order ${collectOrderId.slice(0, 8)}... is not payable (status: ${fetched.status}).`,
          });
        }
      } catch {
        useToastStore.getState().addToast({
          type: 'error',
          title: 'Order Not Found',
          message: `Could not load order ${collectOrderId.slice(0, 8)}... for collection.`,
        });
      }
    })();
  }, [searchParams, loading, payModalOrder, orders, hasUpdatePermission, setSearchParams]);

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
          <div className="flex items-center gap-3">
            <button onClick={load} disabled={loading} className="btn-secondary text-sm">
              Refresh
            </button>
            <button
              onClick={() => navigate('/orders/new')}
              className="btn-primary text-sm"
              disabled={!hasCreatePermission}
              title={!hasCreatePermission ? "Permission Denied" : undefined}
            >
              Create Order
            </button>
          </div>
        }
      />

      {loading && <TableSkeleton />}
      {error && (
        <div className="mt-6 flex items-center gap-3 rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">
          <span>{error}</span>
          <button
            onClick={load}
            disabled={loading}
            className="inline-flex items-center gap-1 rounded-md bg-red-100 px-2 py-1 text-xs font-medium text-red-800 hover:bg-red-200"
          >
            Retry
          </button>
        </div>
      )}

      {!loading && !error && orders.length === 0 && (
        <EmptyState
          icon={ClipboardDocumentListIcon}
          title="Ready to make your first sale?"
          description="Create an order to get started. Add products and customers first, then come back here to record sales."
          action={
            <button
              onClick={() => navigate('/orders/new')}
              className="btn-primary text-sm"
              disabled={!hasCreatePermission}
              title={!hasCreatePermission ? "Permission Denied" : undefined}
            >
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
                    {o.id.slice(0, 8)}
                  </td>
                  <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-500">
                    {o.retailer_name ?? '--'}
                  </td>
                  <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-500">
                    {new Date(o.created_at).toLocaleDateString()}
                  </td>
                  <td className="whitespace-nowrap px-6 py-4">
                    <StatusBadge status={o.status} />
                  </td>
                  <td className="whitespace-nowrap px-6 py-4 text-sm text-gray-500">
                    KES {o.total_amount.toLocaleString()}
                  </td>
                  <td className="whitespace-nowrap px-6 py-4 text-right text-sm font-medium">
                    <div className="flex justify-end gap-2">
                      {canConfirm(o.status) && (
                        <button
                          onClick={() => handleConfirm(o.id)}
                          disabled={!!actionLoading || !hasUpdatePermission}
                          title={!hasUpdatePermission ? "Permission Denied" : undefined}
                          className="text-blue-600 hover:text-blue-900 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          Confirm
                        </button>
                      )}
                      {canPay(o.status) && (
                        <button
                          onClick={() => handleOpenPayModal(o)}
                          disabled={!hasUpdatePermission}
                          title={!hasUpdatePermission ? "Permission Denied" : "Record Payment"}
                          className="text-green-600 hover:text-green-900 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          Record Payment
                        </button>
                      )}
                      {canFulfill(o.status) && (
                        <button
                          onClick={() => handleFulfill(o.id)}
                          disabled={!!actionLoading || !hasUpdatePermission}
                          title={!hasUpdatePermission ? "Permission Denied" : undefined}
                          className="text-emerald-600 hover:text-emerald-900 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          Fulfill
                        </button>
                      )}
                      {canCancelOrder(o.status) && (
                        <button
                          onClick={() => handleCancel(o.id)}
                          disabled={!!actionLoading || !hasUpdatePermission}
                          title={!hasUpdatePermission ? "Permission Denied" : undefined}
                          className="text-red-600 hover:text-red-900 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          Cancel
                        </button>
                      )}
                      {canReturn(o.status) && (
                        <button
                          onClick={() => handleReturn(o.id)}
                          disabled={!!actionLoading || !hasUpdatePermission}
                          title={!hasUpdatePermission ? "Permission Denied" : undefined}
                          className="text-amber-600 hover:text-amber-900 disabled:opacity-50 disabled:cursor-not-allowed"
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
      )}

      {/* Phase 5: Payment recording modal */}
      {payModalOrder && (
        <PaymentRecordModal
          open={!!payModalOrder}
          onClose={() => setPayModalOrder(null)}
          onSubmit={handlePaySubmit}
          orderId={payModalOrder.id}
          orderTotal={payModalOrder.total_amount}
          remainingAmount={payRemaining ?? payModalOrder.total_amount}
          loading={actionLoading === payModalOrder.id}
        />
      )}
    </div>
  );
}
