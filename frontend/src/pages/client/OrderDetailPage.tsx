import { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { ArrowLeftIcon, PrinterIcon } from '@heroicons/react/24/outline';
import { clientOrderService } from '@/services/clientOrderService';
import { normalizeApiError } from '@/utils/errorHandling';
import { formatMoney } from '@/utils/printFormat';
import { useAuthStore } from '@/stores/authStore';
import { can, CLIENT_PERMISSIONS } from '@/utils/permissions';
import type { ClientOrder } from '@/types/client';
import { OrderNegotiationPanel } from '@/components/orders/OrderNegotiationPanel';

const STATUS_BADGE: Record<string, { label: string; className: string }> = {
  CREATED: { label: 'Created', className: 'bg-blue-100 text-blue-700' },
  CONFIRMED: { label: 'Confirmed', className: 'bg-indigo-100 text-indigo-700' },
  DELIVERED: { label: 'Delivered', className: 'bg-green-100 text-green-700' },
  CANCELLED: { label: 'Cancelled', className: 'bg-red-100 text-red-700' },
  RETURNED: { label: 'Returned', className: 'bg-gray-100 text-gray-700' },
};

export function OrderDetailPage() {
  const { orderId } = useParams<{ orderId: string }>();
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const [order, setOrder] = useState<ClientOrder | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);

  const load = useCallback(async () => {
    if (!orderId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await clientOrderService.getById(orderId);
      setOrder(res.data.data);
    } catch {
      setError('Order not found.');
    } finally {
      setLoading(false);
    }
  }, [orderId]);

  useEffect(() => {
    load();
  }, [load]);

  const handleCancel = async () => {
    if (!orderId || !order || cancelling) return;
    const isReorderDraft = order.status === 'CREATED' && Boolean(order.source_order_id);
    const confirmation = isReorderDraft
      ? 'Cancel this draft before ordering again? Only this draft will be cancelled; the historical order will remain unchanged.'
      : 'Are you sure you want to cancel this order?';
    if (!window.confirm(confirmation)) return;

    setCancelling(true);
    setError(null);
    try {
      const res = await clientOrderService.cancel(orderId);
      const cancelledOrder = res.data?.data;
      if (isReorderDraft && (res.data?.success !== true || !cancelledOrder || cancelledOrder.id !== order.id || cancelledOrder.status !== 'CANCELLED')) {
        setError('Cancellation could not be confirmed. Check this draft\'s status before ordering again.');
        return;
      }
      setOrder(isReorderDraft ? { ...cancelledOrder, source_order_id: order.source_order_id } : cancelledOrder);
    } catch (err) {
      setError(normalizeApiError(err));
    } finally {
      setCancelling(false);
    }
  };

  const formatCurrency = (amount: string) => formatMoney(amount, order?.currency);

  const formatDate = (iso: string) => {
    return new Date(iso).toLocaleString('en-KE', {
      dateStyle: 'medium',
      timeStyle: 'short',
    });
  };

  const canCancel = order && (order.status === 'CREATED' || order.status === 'CONFIRMED');
  // Navigation discoverability only: the declare route and its
  // client:payments:declare admission stay the permission boundary; the
  // backend remains the final arbiter of whether a declaration is accepted.
  const canDeclare = can(user, CLIENT_PERMISSIONS.PAYMENTS_DECLARE);

  if (loading) {
    return (
      <div className="space-y-4 animate-pulse">
        <div className="h-6 w-1/4 rounded bg-gray-200" />
        <div className="h-32 rounded-xl bg-gray-200" />
        <div className="h-24 rounded-xl bg-gray-200" />
      </div>
    );
  }

  if (error && !order) {
    return (
      <div className="space-y-4">
        <button
          onClick={() => navigate('/client/orders')}
          className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700"
        >
          <ArrowLeftIcon className="h-4 w-4" />
          Back to orders
        </button>
        <div className="rounded-lg bg-red-50 p-4 text-sm text-red-700">{error}</div>
      </div>
    );
  }

  if (!order) return null;

  const badge = STATUS_BADGE[order.status] ?? STATUS_BADGE.CREATED;
  const isReorderDraft = order.status === 'CREATED' && Boolean(order.source_order_id);
  const isCancelledReorderDraft = order.status === 'CANCELLED' && Boolean(order.source_order_id);

  return (
    <div className="space-y-4">
      {/* Back */}
      <button
        onClick={() => navigate('/client/orders')}
        className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700"
      >
        <ArrowLeftIcon className="h-4 w-4" />
        Back to orders
      </button>

      {/* Error Banner */}
      {error && (
        <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</div>
      )}

      {/* Order Header Card */}
      <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs text-gray-400 font-mono">Order #{order.id.slice(0, 8)}</p>
            <p className="mt-1 text-xl font-bold text-gray-900">
              {formatCurrency(order.total_amount)}
            </p>
          </div>
          <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ${badge.className}`}>
            {badge.label}
          </span>
        </div>

        {/* DC-12R1-S3-S2B-I2C-I2: printable order (Contract A, retailer). */}
        <div className="no-print mt-3 flex flex-wrap gap-2">
          {!isReorderDraft && !isCancelledReorderDraft && <Link to={`/client/orders/${order.id}/reorder`}
            className="inline-flex items-center rounded-lg bg-primary-600 px-3 py-2 text-sm font-medium text-white hover:bg-primary-700">
            Order again
          </Link>}
          {canDeclare && <Link to={`/client/orders/${order.id}/declare`}
            className="inline-flex items-center rounded-lg border border-primary-300 bg-white px-3 py-2 text-sm font-medium text-primary-700 hover:bg-primary-50">
            Declare Payment
          </Link>}
          <Link
            to={`/client/orders/${order.id}/print`}
            className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 transition"
          >
            <PrinterIcon className="h-4 w-4" />
            Print order
          </Link>
        </div>
        {canDeclare && <p className="no-print mt-2 text-xs text-gray-500">
          Declare Payment only submits a declaration. The supplier books it only
          after confirming receipt offline — never record the same payment twice.
        </p>}

        <div className="mt-3 flex flex-wrap items-center gap-4 text-xs text-gray-500">
          <span>{order.item_count} item{order.item_count !== 1 ? 's' : ''}</span>
          <span>{formatDate(order.created_at)}</span>
        </div>

        {order.source_order_id && <p className="mt-3 text-sm text-gray-600">
          New draft from <Link to={`/client/orders/${order.source_order_id}`} className="text-primary-700 underline">historical order #{order.source_order_id.slice(0, 8)}</Link>.
        </p>}

        {order.notes && (
          <div className="mt-3 rounded-lg bg-gray-50 p-2.5">
            <p className="text-xs text-gray-500">Notes</p>
            <p className="mt-0.5 text-sm text-gray-700">{order.notes}</p>
          </div>
        )}
      </div>

      {/* Order Items */}
      {can(user, CLIENT_PERMISSIONS.ORDERS_READ) && <OrderNegotiationPanel key={order.id} client orderId={order.id} items={order.items}
        currency={order.currency} draft={order.status === 'CREATED'} onAccepted={(id) => navigate(`/client/orders/${id}`)} />}
      <div className="rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden">
        <div className="border-b border-gray-200 bg-gray-50 px-4 py-2.5">
          <h2 className="text-sm font-semibold text-gray-900">Items</h2>
        </div>
        <div className="divide-y divide-gray-100">
          {order.items.map((item, idx) => (
            <div key={idx} className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-gray-900 break-words">
                  {item.product_name}
                </p>
                <p className="text-xs text-gray-400 font-mono break-all">{item.sku_code}</p>
              </div>
              <div className="min-w-0 break-words sm:ml-4 sm:text-right">
                <p className="text-sm text-gray-900">
                  {item.quantity} {item.display_label_snapshot || item.unit_snapshot || "UNIT_UNVERIFIED"} (package {item.package_quantity_snapshot || "unknown"}) &times; {formatCurrency(item.unit_price)}
                </p>
                <p className="text-xs font-medium text-gray-500">
                  {formatCurrency(item.subtotal)}
                </p>
              </div>
            </div>
          ))}
        </div>
        {/* Total */}
        <div className="border-t border-gray-200 bg-gray-50 px-4 py-3 flex justify-between">
          <span className="text-sm font-semibold text-gray-900">Total</span>
          <span className="text-sm font-bold text-gray-900">
            {formatCurrency(order.total_amount)}
          </span>
        </div>
      </div>

      {/* Status Timeline (simplified) */}
      <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
        <h2 className="mb-3 text-sm font-semibold text-gray-900">Order Status</h2>
        <div className="space-y-2">
          {(['CREATED', 'CONFIRMED', 'DELIVERED'] as const).map((step) => {
            const stepOrder = { CREATED: 0, CONFIRMED: 1, DELIVERED: 2 };
            const currentStep = stepOrder[order.status as keyof typeof stepOrder] ?? -1;
            const thisStep = stepOrder[step];
            const isCompleted = thisStep <= currentStep && order.status !== 'CANCELLED';
            const isCurrent = step === order.status || (order.status === 'CONFIRMED' && step === 'CONFIRMED');

            return (
              <div key={step} className="flex items-center gap-3">
                <div className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold ${
                  isCompleted
                    ? 'bg-primary-600 text-white'
                    : 'bg-gray-200 text-gray-400'
                }`}>
                  {isCompleted ? '✓' : thisStep + 1}
                </div>
                <span className={`text-sm ${
                  isCurrent ? 'font-semibold text-gray-900' : 'text-gray-500'
                }`}>
                  {step === 'CREATED' ? 'Order Placed' :
                   step === 'CONFIRMED' ? 'Confirmed by Supplier' :
                   'Delivered'}
                </span>
              </div>
            );
          })}
          {order.status === 'CANCELLED' && (
            <div className="flex items-center gap-3">
              <div className="flex h-6 w-6 items-center justify-center rounded-full bg-red-500 text-xs font-bold text-white">
                ✕
              </div>
              <span className="text-sm font-semibold text-red-600">Cancelled</span>
            </div>
          )}
        </div>
      </div>

      {order.status === 'CREATED' && !order.source_order_id && <Link to={`/client/orders/new?replace=${order.id}`}
        className="btn-secondary block text-center">Review new quote and replace this draft</Link>}
      {isReorderDraft && <section aria-label="Reorder draft actions" className="rounded-xl border border-gray-200 bg-white p-4 text-sm text-gray-700">
        To review a new quote, cancel this draft first. After cancellation succeeds, order again from the historical order. The historical order will remain unchanged.
      </section>}
      {isCancelledReorderDraft && <section aria-label="Reorder draft actions" className="rounded-xl border border-gray-200 bg-white p-4 text-sm text-gray-700">
        <p role="status">This draft is cancelled. You can now review a new quote from the historical order.</p>
        <Link to={`/client/orders/${order.source_order_id}/reorder`}
          className="btn-secondary mt-3 block text-center">Order again from historical order</Link>
      </section>}
      {/* Cancel Button */}
      {canCancel && (
        <button
          onClick={handleCancel}
          disabled={cancelling}
          className="w-full rounded-xl border border-red-300 bg-white px-4 py-3 text-sm font-medium text-red-600 hover:bg-red-50 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition"
        >
          {cancelling ? 'Cancelling...' : isReorderDraft ? 'Cancel this draft to order again' : 'Cancel Order'}
        </button>
      )}
    </div>
  );
}
