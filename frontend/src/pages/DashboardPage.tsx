import { useEffect, useState, useCallback, useRef } from 'react';
import { useAuthStore } from '@/stores/authStore';
import { dashboardService } from '@/services/dashboardService';
import { orderService } from '@/services/orderService';
import { inventoryService } from '@/services/inventoryService';
import { ORDER_STATUS_LABELS, ORDER_STATUS_COLORS } from '@/types/order';
import type { Order } from '@/types/order';
import { Link } from 'react-router-dom';
import { can } from '@/utils/permissions';
import type { KpiCard as KpiCardType, ChartDataPoint } from '@/services/dashboardService';

import { PageHeader } from '@/components/layout/PageHeader';
import { EmptyState } from '@/components/ui/EmptyState';
import { HomeIcon } from '@heroicons/react/24/outline';

type Section = 'summary' | 'trend' | 'orders' | 'stock';
const sectionLabels: Record<Section, string> = { summary: 'Business summary', trend: 'Sales trend', orders: 'Orders', stock: 'Stock' };

export function DashboardPage() {
  const user = useAuthStore((s) => s.user);
  const tenantCode = useAuthStore((s) => s.tenantCode);

  // Legacy data (orders table + status breakdown)
  const [orders, setOrders] = useState<Order[]>([]);

  // BI data (from S6-3 Dashboard API)
  const [kpiCards, setKpiCards] = useState<KpiCardType[]>([]);
  const [salesTrend, setSalesTrend] = useState<ChartDataPoint[]>([]);
  const [status, setStatus] = useState<Record<Section, 'loading' | 'success' | 'error'>>({ summary: 'loading', trend: 'loading', orders: 'loading', stock: 'loading' });
  const [errors, setErrors] = useState<Partial<Record<Section, string>>>({});
  const attempts = useRef<Record<Section, number>>({ summary: 0, trend: 0, orders: 0, stock: 0 });
  const load = useCallback(async (section: Section) => {
    const attempt = ++attempts.current[section];
    const current = () => attempts.current[section] === attempt;
    setStatus(s => ({ ...s, [section]: 'loading' }));
    setErrors(s => ({ ...s, [section]: undefined }));
    try {
      if (section === 'summary') {
        const response = await dashboardService.getKpiSummary();
        if (current()) setKpiCards(response.data.data.cards);
      } else if (section === 'trend') {
        const response = await dashboardService.getSalesTrend();
        if (current()) setSalesTrend(response.data.data.data);
      } else if (section === 'orders') {
        const response = await orderService.getAll(1, 50);
        if (current()) setOrders(response.data.data.items);
      } else { await inventoryService.getStocks(1, 50); }
      if (current()) setStatus(s => ({ ...s, [section]: 'success' }));
    } catch (error) {
      if (!current()) return;
      const httpStatus = (error as { response?: { status?: number } }).response?.status;
      setErrors(s => ({ ...s, [section]: httpStatus === 403
        ? 'Your role does not have access to this section. Ask your administrator if you need it.'
        : httpStatus === 401 ? 'Your session has expired. Sign in again to load this section.'
        : 'This section could not be loaded. Please retry.' }));
      setStatus(s => ({ ...s, [section]: 'error' }));
    }
  }, []);
  useEffect(() => {
    void Promise.allSettled((Object.keys(sectionLabels) as Section[]).map(load));
    return () => { for (const section of Object.keys(sectionLabels) as Section[]) attempts.current[section]++; };
  }, [load]);
  const sectionState = (section: Section) => status[section] === 'loading'
    ? <p role="status" className="text-sm text-gray-500">Loading {sectionLabels[section]}…</p>
    : errors[section] ? <div role="alert" className="my-3 rounded-md bg-amber-50 px-4 py-3 text-sm text-amber-900">
      <p>{sectionLabels[section]}: {errors[section]}</p>
      <button onClick={() => void load(section)} className="mt-2 underline">Retry {sectionLabels[section]}</button>
    </div> : null;

  // Count orders by status (for breakdown section)
  const statusCounts = orders.reduce<Record<string, number>>((acc, o) => {
    acc[o.status] = (acc[o.status] || 0) + 1;
    return acc;
  }, {});

  // Compute max for simple bar chart scale
  const trendMax = Math.max(...salesTrend.map((p) => p.value), 1);

  return (
    <div>
      <PageHeader
        title="Home"
        description={`Welcome back${user?.full_name ? `, ${user.full_name}` : ''}.${tenantCode ? ` (${tenantCode})` : ''}`}
      />

      <section aria-label="Getting started" className="my-5 rounded-xl border bg-white p-4">
        <h2 className="font-semibold">Set up your business</h2>
        <p className="mt-1 text-sm text-gray-600">Add products and pack sizes, check opening stock and prices, invite customers, then review your first order.</p>
        <div className="mt-3 flex flex-wrap gap-3 text-sm text-primary-700">
          {can(user, 'skus:read') && <Link to="/skus" className="underline">1. Products and packaging</Link>}
          {can(user, 'inventory:read') && <Link to="/inventory" className="underline">2. Check stock</Link>}
          {can(user, 'pricing:read') && <Link to="/pricing" className="underline">3. Review prices</Link>}
          {can(user, 'invitations:create') && <Link to="/retailers/invite" className="underline">4. Invite a customer</Link>}
          {can(user, 'orders:read') && <Link to="/orders" className="underline">5. Review orders</Link>}
        </div>
      </section>
      <section aria-label="Your work shortcuts" className="mb-5 flex flex-wrap gap-3 text-sm text-primary-700">
        {can(user, 'orders:read') && <Link to="/orders" className="underline">Sales: review orders</Link>}
        {can(user, 'payments:read') && <Link to="/declarations" className="underline">Declarations: verify incoming payments</Link>}
        {can(user, 'inventory:adjustments:read') && <Link to="/inventory/adjustments" className="underline">Stock requests: review adjustments</Link>}
        {can(user, 'pricing:read') && <Link to="/pricing" className="underline">Pricing: check product prices</Link>}
      </section>
      {sectionState('stock')}
        <div className="space-y-6">
          {/* First-use state: show guidance when there is no data at all */}
          {Object.values(status).every(s => s === 'success') && orders.length === 0 && kpiCards.length === 0 && salesTrend.length === 0 && (
            <EmptyState
              icon={HomeIcon}
              title="Welcome to your dashboard"
              description="Your business overview will appear here as you get started. Add products, create orders, and onboard customers to see your metrics come to life."
            />
          )}

          {/* KPI Cards */}
          {sectionState('summary')}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {status.summary === 'success' && kpiCards.map((card, i) => (
              <div key={i} className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
                <p className="text-sm font-medium text-gray-500">{card.label}</p>
                <p className="mt-2 text-2xl font-bold text-gray-900">
                  {card.currency || 'Currency unavailable'} {card.value.toLocaleString()}
                </p>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            {/* Sales Trend Chart (Simple CSS Bar Chart) */}
            <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm lg:col-span-2">
              <h3 className="mb-6 text-base font-semibold text-gray-900">Sales Trend</h3>
              {sectionState('trend')}
              <div className="flex h-64 items-end gap-2">
                {status.trend === 'success' && salesTrend.map((point, i) => (
                  <div key={i} className="group relative flex-1">
                    <div
                      className="w-full rounded-t bg-primary-100 transition-all group-hover:bg-primary-600"
                      style={{ height: `${(point.value / trendMax) * 100}%` }}
                    />
                    <div className="absolute bottom-full left-1/2 mb-2 hidden -translate-x-1/2 rounded bg-gray-900 px-2 py-1 text-xs text-white group-hover:block">
                      {point.currency || 'Currency unavailable'} {point.value.toLocaleString()}
                    </div>
                  </div>
                ))}
              </div>
              <div className="mt-2 flex justify-between text-xs text-gray-400">
                {status.trend === 'success' && salesTrend.map((p, i) => (
                  <span key={i}>{p.date}</span>
                ))}
              </div>
            </div>

            {/* Order Status Breakdown */}
            <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
              <h3 className="mb-6 text-base font-semibold text-gray-900">Order Status</h3>
              {sectionState('orders')}
              <div className="space-y-4">
                {status.orders === 'success' && Object.entries(statusCounts).map(([status, count]) => (
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
                {status.orders === 'success' && orders.length === 0 && (
                  <p className="text-sm text-gray-400">No orders yet. Create your first order to see status breakdown here.</p>
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
                  {status.orders === 'success' && orders.slice(0, 5).map((o) => (
                    <tr key={o.id}>
                      <td className="px-6 py-4 font-medium text-gray-900">{o.id.slice(0, 8)}</td>
                      <td className="px-6 py-4 text-gray-500">{o.retailer_name ?? '—'}</td>
                      <td className="px-6 py-4 text-gray-500">
                        {o.currency || 'Currency unavailable'} {o.total_amount.toLocaleString()}
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
                  {status.orders === 'success' && orders.length === 0 && (
                    <tr>
                      <td colSpan={4} className="px-6 py-8 text-center text-gray-400">
                        No orders yet. Go to Sales to create your first order.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
    </div>
  );
}
