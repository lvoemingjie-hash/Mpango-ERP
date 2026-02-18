import { useEffect, useState } from 'react';
import { useAuthStore } from '@/stores/authStore';
import { orderService } from '@/services/orderService';
import { inventoryService } from '@/services/inventoryService';
import { dashboardService } from '@/services/dashboardService';
import { Badge } from '@/components/ui/Badge';
import type { Order, OrderStatus } from '@/types/order';
import { ORDER_STATUS_LABELS, ORDER_STATUS_COLORS } from '@/types/order';
import type { StockView } from '@/types/inventory';
import type { KpiCard as KpiCardType, ChartDataPoint } from '@/services/dashboardService';

export function DashboardPage() {
  const user = useAuthStore((s) => s.user);
  const tenantCode = useAuthStore((s) => s.tenantCode);

  // Legacy data (orders table + status breakdown)
  const [orders, setOrders] = useState<Order[]>([]);
  const [stocks, setStocks] = useState<StockView[]>([]);

  // BI data (from S6-3 Dashboard API)
  const [kpiCards, setKpiCards] = useState<KpiCardType[]>([]);
  const [salesTrend, setSalesTrend] = useState<ChartDataPoint[]>([]);
  const [currency, setCurrency] = useState('KES');

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        // Parallel fetch: BI endpoints + legacy lists
        const [kpiRes, trendRes, ordersRes, stocksRes] = await Promise.allSettled([
          dashboardService.getKpiSummary(),
          dashboardService.getSalesTrend(),
          orderService.getAll(1, 50),
          inventoryService.getStocks(1, 50),
        ]);

        // BI endpoints — graceful fallback if not available
        if (kpiRes.status === 'fulfilled') {
          setKpiCards(kpiRes.value.data.data.cards);
          setCurrency(kpiRes.value.data.data.currency);
        }
        if (trendRes.status === 'fulfilled') {
          setSalesTrend(trendRes.value.data.data.data);
        }

        // Legacy lists — always needed for orders table
        if (ordersRes.status === 'fulfilled') {
          setOrders(ordersRes.value.data.data.items);
        }
        if (stocksRes.status === 'fulfilled') {
          setStocks(stocksRes.value.data.data.items);
        }
      } catch {
        setError('Failed to load dashboard data. Is the backend running?');
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  // Count orders by status (for breakdown section)
  const statusCounts = orders.reduce<Record<string, number>>((acc, o) => {
    acc[o.status] = (acc[o.status] || 0) + 1;
    return acc;
  }, {});

  // Compute max for simple bar chart scale
  const trendMax = Math.max(...salesTrend.map((p) => p.value), 1);

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
          {/* ── KPI Cards (from BI API or fallback) ── */}
          <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {kpiCards.length > 0 ? (
              kpiCards.map((card, i) => (
                <KpiSummaryCard key={i} label={card.label} value={card.value} currency={card.currency} />
              ))
            ) : (
              /* Fallback: compute from order list */
              <>
                <SummaryCard label="Total Orders" value={orders.length} />
                <SummaryCard label="Active SKUs" value={stocks.length} />
                <SummaryCard
                  label="Revenue (Paid+Fulfilled)"
                  value={`${currency} ${orders
                    .filter((o) => ['paid', 'fulfilled'].includes(o.status))
                    .reduce((sum, o) => sum + o.total_amount, 0)
                    .toLocaleString()}`}
                />
                <SummaryCard label="Pending Confirmation" value={statusCounts['draft'] || 0} />
              </>
            )}
            {/* Always show operational counts alongside BI cards */}
            {kpiCards.length > 0 && (
              <SummaryCard
                label="Pending Orders"
                value={statusCounts['draft'] || 0}
                accent={statusCounts['draft'] > 0 ? 'amber' : undefined}
              />
            )}
          </div>

          {/* ── Sales Trend Chart ── */}
          {salesTrend.length > 0 && (
            <div className="mt-8">
              <h2 className="text-lg font-semibold text-gray-900">Sales Trend (Last 7 Days)</h2>
              <div className="mt-3 rounded-lg border border-gray-200 bg-white p-4">
                <div className="flex items-end gap-1" style={{ height: 160 }}>
                  {salesTrend.map((point, i) => {
                    const pct = trendMax > 0 ? (point.value / trendMax) * 100 : 0;
                    return (
                      <div key={i} className="flex flex-1 flex-col items-center gap-1">
                        <span className="text-[10px] font-medium text-gray-500">
                          {point.value > 0 ? `${(point.value / 1000).toFixed(0)}k` : '0'}
                        </span>
                        <div
                          className="w-full rounded-t bg-gradient-to-t from-blue-600 to-blue-400 transition-all duration-300"
                          style={{ height: `${Math.max(pct, 2)}%` }}
                          title={`${currency} ${point.value.toLocaleString()}`}
                        />
                        <span className="text-[10px] text-gray-400">
                          {new Date(point.date).toLocaleDateString(undefined, { weekday: 'short' })}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}

          {/* ── Order Status Breakdown ── */}
          <div className="mt-8">
            <h2 className="text-lg font-semibold text-gray-900">Order Status Breakdown</h2>
            <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-7">
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

          {/* ── Recent Orders Table ── */}
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
                  {orders.slice(0, 10).map((o) => (
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
                        {currency} {o.total_amount.toLocaleString()}
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

/* ── Sub-components ── */

function KpiSummaryCard({ label, value, currency }: { label: string; value: number; currency: string }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wider text-gray-400">{label}</p>
      <p className="mt-1 text-2xl font-bold text-gray-900">
        {currency} {value.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
      </p>
    </div>
  );
}

function SummaryCard({
  label,
  value,
  accent,
}: {
  label: string;
  value: string | number;
  accent?: 'amber' | 'red';
}) {
  const borderColor =
    accent === 'amber' ? 'border-amber-300' : accent === 'red' ? 'border-red-300' : 'border-gray-200';
  return (
    <div className={`rounded-lg border ${borderColor} bg-white p-4`}>
      <p className="text-xs font-medium uppercase tracking-wider text-gray-400">{label}</p>
      <p className="mt-1 text-2xl font-bold text-gray-900">{value}</p>
    </div>
  );
}
