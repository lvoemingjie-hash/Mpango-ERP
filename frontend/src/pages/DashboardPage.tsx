import { useEffect, useState } from 'react';
import { useAuthStore } from '@/stores/authStore';
import { orderService } from '@/services/orderService';
import { inventoryService } from '@/services/inventoryService';
import { Badge } from '@/components/ui/Badge';
import type { Order, OrderStatus } from '@/types/order';
import { ORDER_STATUS_LABELS, ORDER_STATUS_COLORS } from '@/types/order';
import type { StockView } from '@/types/inventory';

export function DashboardPage() {
  const user = useAuthStore((s) => s.user);
  const tenantCode = useAuthStore((s) => s.tenantCode);
  const [orders, setOrders] = useState<Order[]>([]);
  const [stocks, setStocks] = useState<StockView[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [ordersRes, stocksRes] = await Promise.all([
          orderService.getAll(1, 50),
          inventoryService.getStocks(1, 50),
        ]);
        setOrders(ordersRes.data.data.items);
        setStocks(stocksRes.data.data.items);
      } catch (err) {
        setError('Failed to load dashboard data. Is the backend running?');
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  // Count orders by status
  const statusCounts = orders.reduce<Record<string, number>>((acc, o) => {
    acc[o.status] = (acc[o.status] || 0) + 1;
    return acc;
  }, {});

  const totalRevenue = orders
    .filter((o) => ['paid', 'fulfilled'].includes(o.status))
    .reduce((sum, o) => sum + o.total_amount, 0);

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
      <p className="mt-1 text-sm text-gray-500">
        Welcome back{user?.full_name ? `, ${user.full_name}` : ''}.
        {tenantCode && <span className="ml-1 font-medium text-primary-600">({tenantCode})</span>}
      </p>

      {loading && <p className="mt-6 text-sm text-gray-400">Loading dashboard…</p>}
      {error && <p className="mt-6 text-sm text-red-600">{error}</p>}

      {!loading && !error && (
        <>
          {/* Summary Cards */}
          <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <SummaryCard label="Total Orders" value={orders.length} />
            <SummaryCard label="Active SKUs" value={stocks.length} />
            <SummaryCard
              label="Revenue (Paid+Fulfilled)"
              value={`KES ${totalRevenue.toLocaleString()}`}
            />
            <SummaryCard label="Pending Confirmation" value={statusCounts['draft'] || 0} />
          </div>

          {/* Order Status Breakdown */}
          <div className="mt-8">
            <h2 className="text-lg font-semibold text-gray-900">Order Status Breakdown</h2>
            <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
              {(Object.keys(ORDER_STATUS_LABELS) as OrderStatus[]).map((s) => (
                <div
                  key={s}
                  className="rounded-lg border border-gray-200 bg-white p-3 text-center"
                >
                  <p className="text-2xl font-bold text-gray-900">{statusCounts[s] || 0}</p>
                  <Badge variant={ORDER_STATUS_COLORS[s] as 'green' | 'gray' | 'red' | 'blue' | 'yellow'}>
                    {ORDER_STATUS_LABELS[s]}
                  </Badge>
                </div>
              ))}
            </div>
          </div>

          {/* Recent Orders Table */}
          <div className="mt-8">
            <h2 className="text-lg font-semibold text-gray-900">Recent Orders</h2>
            <div className="mt-3 overflow-x-auto rounded-lg border border-gray-200 bg-white">
              <table className="min-w-full divide-y divide-gray-200 text-sm">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-2 text-left font-medium text-gray-500">ID</th>
                    <th className="px-4 py-2 text-left font-medium text-gray-500">Status</th>
                    <th className="px-4 py-2 text-left font-medium text-gray-500">Items</th>
                    <th className="px-4 py-2 text-right font-medium text-gray-500">Total</th>
                    <th className="px-4 py-2 text-left font-medium text-gray-500">Notes</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {orders.map((o) => (
                    <tr key={o.id}>
                      <td className="px-4 py-2 font-mono text-xs text-gray-600">
                        {o.id.slice(0, 8)}…
                      </td>
                      <td className="px-4 py-2">
                        <Badge variant={ORDER_STATUS_COLORS[o.status] as 'green' | 'gray' | 'red' | 'blue' | 'yellow'}>
                          {ORDER_STATUS_LABELS[o.status]}
                        </Badge>
                      </td>
                      <td className="px-4 py-2 text-gray-700">{o.items.length}</td>
                      <td className="px-4 py-2 text-right font-medium text-gray-900">
                        KES {o.total_amount.toLocaleString()}
                      </td>
                      <td className="px-4 py-2 text-gray-500 truncate max-w-[200px]">
                        {o.notes || '—'}
                      </td>
                    </tr>
                  ))}
                  {orders.length === 0 && (
                    <tr>
                      <td colSpan={5} className="px-4 py-6 text-center text-gray-400">
                        No orders found. Run the seed script first.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function SummaryCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <p className="text-xs font-medium uppercase tracking-wider text-gray-400">{label}</p>
      <p className="mt-1 text-2xl font-bold text-gray-900">{value}</p>
    </div>
  );
}
