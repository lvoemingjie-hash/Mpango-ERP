import { useEffect, useState } from 'react';
import { financeService } from '@/services/financeService';
import type { FinancialSummary, ReceivableItem } from '@/services/financeService';
import { useToastStore } from '@/stores/toastStore';

/**
 * FinancePage — GAP 2 Finance Dashboard
 *
 * Shows:
 *  - Financial Summary KPIs (revenue, cash, receivables)
 *  - Accounts Receivable table with aging
 *
 * Permission: finance:read
 * Uses existing UI patterns from DashboardPage and OrderListPage.
 */

function formatCurrency(n: number): string {
    return new Intl.NumberFormat('en-KE', {
        style: 'currency',
        currency: 'KES',
        minimumFractionDigits: 0,
        maximumFractionDigits: 0,
    }).format(n);
}

export function FinancePage() {
    const [summary, setSummary] = useState<FinancialSummary | null>(null);
    const [receivables, setReceivables] = useState<ReceivableItem[]>([]);
    const [loading, setLoading] = useState(true);
    const [page, setPage] = useState(1);
    const [totalPages, setTotalPages] = useState(0);

    useEffect(() => {
        loadData();
    }, [page]);

    async function loadData() {
        setLoading(true);
        try {
            const [summaryRes, arRes] = await Promise.all([
                financeService.getSummary(),
                financeService.getReceivables(page, 10),
            ]);

            setSummary(summaryRes.data.data);
            setReceivables(arRes.data.data.items);
            setTotalPages(arRes.data.data.pagination.pages);
        } catch {
            useToastStore.getState().addToast({
                type: 'error',
                title: 'Failed to load finance data',
                message: 'Could not fetch financial summary. Please try again.',
            });
        } finally {
            setLoading(false);
        }
    }

    if (loading && !summary) {
        return (
            <div className="flex items-center justify-center py-20">
                <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary-600 border-t-transparent" />
            </div>
        );
    }

    const kpiCards = summary
        ? [
            { label: 'Total Revenue', value: formatCurrency(summary.total_revenue), color: 'bg-emerald-50 text-emerald-700' },
            { label: 'Cash Received', value: formatCurrency(summary.total_cash_received), color: 'bg-blue-50 text-blue-700' },
            { label: 'Outstanding AR', value: formatCurrency(summary.outstanding_receivables), color: 'bg-amber-50 text-amber-700' },
            { label: 'Overdue (>30d)', value: String(summary.overdue_receivables_count), color: summary.overdue_receivables_count > 0 ? 'bg-red-50 text-red-700' : 'bg-gray-50 text-gray-600' },
            { label: 'Total Orders', value: String(summary.total_orders), color: 'bg-indigo-50 text-indigo-700' },
        ]
        : [];

    return (
        <div>
            <div className="flex items-center justify-between">
                <h1 className="text-2xl font-bold text-gray-900">Finance</h1>
                <span className="text-xs text-gray-400">
                    {summary ? `Generated: ${new Date(summary.generated_at).toLocaleString()}` : ''}
                </span>
            </div>

            {/* KPI Cards */}
            <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
                {kpiCards.map((card, i) => (
                    <div
                        key={i}
                        className={`rounded-xl border border-gray-200 p-5 ${card.color}`}
                    >
                        <p className="text-xs font-medium uppercase tracking-wide opacity-70">{card.label}</p>
                        <p className="mt-1 text-2xl font-bold">{card.value}</p>
                    </div>
                ))}
            </div>

            {/* Order Status Breakdown */}
            {summary && Object.keys(summary.order_counts).length > 0 && (
                <div className="mt-6 rounded-xl border border-gray-200 bg-white p-5">
                    <h2 className="text-sm font-semibold text-gray-700">Order Status Breakdown</h2>
                    <div className="mt-3 flex flex-wrap gap-3">
                        {Object.entries(summary.order_counts).map(([status, count]) => (
                            <span
                                key={status}
                                className="inline-flex items-center gap-1.5 rounded-full bg-gray-100 px-3 py-1 text-xs font-medium text-gray-700"
                            >
                                {status}: <strong>{count}</strong>
                            </span>
                        ))}
                    </div>
                </div>
            )}

            {/* Accounts Receivable Table */}
            <div className="mt-8">
                <h2 className="text-lg font-semibold text-gray-900">Accounts Receivable</h2>
                <p className="text-sm text-gray-500">
                    Orders with outstanding balances (confirmed, partially paid, or paid).
                </p>

                <div className="mt-4 overflow-hidden rounded-xl border border-gray-200 bg-white">
                    <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-gray-50">
                            <tr>
                                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Order ID</th>
                                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-500">Status</th>
                                <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">Total</th>
                                <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">Paid</th>
                                <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">Balance Due</th>
                                <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-gray-500">Age (days)</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100">
                            {receivables.length === 0 ? (
                                <tr>
                                    <td colSpan={6} className="px-4 py-8 text-center text-sm text-gray-400">
                                        No outstanding receivables 🎉
                                    </td>
                                </tr>
                            ) : (
                                receivables.map((r) => (
                                    <tr key={r.order_id} className="hover:bg-gray-50 transition-colors">
                                        <td className="px-4 py-3 text-sm font-mono text-gray-700">
                                            {r.order_id.slice(0, 8)}…
                                        </td>
                                        <td className="px-4 py-3">
                                            <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${r.status === 'confirmed' ? 'bg-blue-100 text-blue-700' :
                                                    r.status === 'partially_paid' ? 'bg-yellow-100 text-yellow-700' :
                                                        'bg-green-100 text-green-700'
                                                }`}>
                                                {r.status}
                                            </span>
                                        </td>
                                        <td className="px-4 py-3 text-right text-sm text-gray-700">{formatCurrency(r.total_amount)}</td>
                                        <td className="px-4 py-3 text-right text-sm text-gray-700">{formatCurrency(r.total_paid)}</td>
                                        <td className="px-4 py-3 text-right text-sm font-semibold text-amber-700">{formatCurrency(r.balance_due)}</td>
                                        <td className="px-4 py-3 text-right text-sm">
                                            <span className={r.age_days > 30 ? 'text-red-600 font-semibold' : 'text-gray-500'}>
                                                {r.age_days}d
                                            </span>
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>

                {/* Pagination */}
                {totalPages > 1 && (
                    <div className="mt-4 flex items-center justify-between">
                        <button
                            onClick={() => setPage((p) => Math.max(1, p - 1))}
                            disabled={page <= 1}
                            className="rounded bg-gray-200 px-3 py-1 text-sm font-medium text-gray-700 hover:bg-gray-300 disabled:opacity-50"
                        >
                            Previous
                        </button>
                        <span className="text-sm text-gray-500">
                            Page {page} of {totalPages}
                        </span>
                        <button
                            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                            disabled={page >= totalPages}
                            className="rounded bg-gray-200 px-3 py-1 text-sm font-medium text-gray-700 hover:bg-gray-300 disabled:opacity-50"
                        >
                            Next
                        </button>
                    </div>
                )}
            </div>
        </div>
    );
}
