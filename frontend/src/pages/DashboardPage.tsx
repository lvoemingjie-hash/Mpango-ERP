import { useEffect, useState } from 'react';
import { useAuthStore } from '@/stores/authStore';
import { dashboardService } from '@/services/dashboardService';
import { orderService } from '@/services/orderService';
import { inventoryService } from '@/services/inventoryService';
import { ORDER_STATUS_LABELS, ORDER_STATUS_COLORS } from '@/types/order';
import type { Order } from '@/types/order';
import type { StockView } from '@/types/inventory';
import type { KpiCard as KpiCardType, ChartDataPoint } from '@/services/dashboardService';

import { PageHeader } from '@/components/layout/PageHeader';
import { DashboardSkeleton } from '@/components/skeletons/DashboardSkeleton';

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

  if (loading) {
    return (
      <div>
        <PageHeader
          title="Home"
          description={`Welcome back${user?.full_name ? `, ${user.full_name}` : ''}.${tenantCode ? ` (${tenantCode})` : ''}`}
        />
        <DashboardSkeleton />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title="Home"
        description={`Welcome back${user?.full_name ? `, ${user.full_name}` : ''}.${tenantCode ? ` (${tenantCode})` : ''}`}
      />

      {error && <p className="mt-6 text-sm text-red-600">{error}</p>}

      {!error && (
        <div className="space-y-6">
          {/* KPI Cards */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {kpiCards.map((card, i) => (
              <div key={i} className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
                <p className="text-sm font-medium text-gray-500">{card.label}</p>
                <p className="mt-2 text-2xl font-bold text-gray-900">
                  {currency} {card.value.toLocaleString()}
                </p>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            {/* Sales Trend Chart (Simple CSS Bar Chart) */}
            <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm lg:col-span-2">
              <h3 className="mb-6 text-base font-semibold text-gray-900">Sales Trend</h3>
              <div className="flex h-64 items-end gap-2">
                {salesTrend.map((point, i) => (
                  <div key={i} className="group relative flex-1">
                    <div
                      className="w-full rounded-t bg-primary-100 transition-all group-hover:bg-primary-600"
                      style={{ height: `${(point.value / trendMax) * 100}%` }}
                    />
                    <div className="absolute bottom-full left-1/2 mb-2 hidden -translate-x-1/2 rounded bg-gray-900 px-2 py-1 text-xs text-white group-hover:block">
                      {currency} {point.value.toLocaleString()}
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-2 flex justify-between text-xs text-gray-400">
                {salesTrend.map((p, i) => (
                  <span key={i}>{p.label}</span>
                ))}
              </div>
            </div>

            {/* Order Status Breakdown */}
            <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
              <h3 className="mb-6 text-base font-semibold text-gray-900">Order Status</h3>
              <div className="space-y-4">
                {Object.entries(statusCounts).map(([status, count]) => (
                  <div key={status} className="flex items-center justify-between">
                    <span
                      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${ORDER_STATUS_COLORS[status as keyof typeof ORDER_STATUS_COLORS] ||
                        'bg-gray-100 text-gray-800'
                        }`}
                    >
                      {ORDER_STATUS_LABELS[status as keyof typeof ORDER_STATUS_LABELS] || status}
                    </span>
                    <span className="font-medium text-gray-900">{count}</span>
                  </div>
                ))}
                {orders.length === 0 && (
                  <p className="text-sm text-gray-400">No orders yet.</p>
                )}
              </div>
            </div>
          </div>

          {/* Recent Orders Table (Preview) */}
          <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
            <div className="border-b border-gray-200 bg-gray-50 px-6 py-4">
              <h3 className="text-base font-semibold text-gray-900">Recent Orders</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200 text-sm">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left font-medium text-gray-500">Order ID</th>
                    <th className="px-6 py-3 text-left font-medium text-gray-500">Customer</th>
                    <th className="px-6 py-3 text-left font-medium text-gray-500">Total</th>
                    <th className="px-6 py-3 text-right font-medium text-gray-500">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {orders.slice(0, 5).map((o) => (
                    <tr key={o.id}>
                      <td className="px-6 py-4 font-medium text-gray-900">{o.code}</td>
                      <td className="px-6 py-4 text-gray-500">{o.customer_name}</td>
                      <td className="px-6 py-4 text-gray-500">
                        {o.currency} {o.total_amount.toLocaleString()}
                      </td>
                      <td className="px-6 py-4 text-right">
                        <span
                          className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${ORDER_STATUS_COLORS[o.status] || 'bg-gray-100 text-gray-800'
                            }`}
                        >
                          {ORDER_STATUS_LABELS[o.status] || o.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                  {orders.length === 0 && (
                    <tr>
                      <td colSpan={4} className="px-6 py-8 text-center text-gray-400">
                        No recent orders found.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
