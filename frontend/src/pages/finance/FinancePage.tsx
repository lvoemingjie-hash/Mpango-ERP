import { useState, useEffect, useCallback } from 'react';
import { financeService } from '@/services/financeService';
import type { FinancialSummary, ReceivableItem } from '@/services/financeService';
import { PageHeader } from '@/components/layout/PageHeader';
import { EmptyState } from '@/components/ui/EmptyState';
import { DashboardSkeleton } from '@/components/skeletons/DashboardSkeleton';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { BanknotesIcon } from '@heroicons/react/24/outline';

export function FinancePage() {
    const [summary, setSummary] = useState<FinancialSummary | null>(null);
    const [receivables, setReceivables] = useState<ReceivableItem[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const load = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const [summaryRes, receivablesRes] = await Promise.all([
                financeService.getSummary(),
                financeService.getReceivables(1, 100), // Fetch up to 100 for now
            ]);
            setSummary(summaryRes.data.data);
            // The API returns paginated data structure
            setReceivables(receivablesRes.data.data.items);
        } catch {
            setError('Failed to load financial data.');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { load(); }, [load]);

    const formatCurrency = (amount: number) => {
        return new Intl.NumberFormat('en-KE', {
            style: 'currency',
            currency: 'KES',
        }).format(amount);
    };

    if (loading && !summary) {
        return (
            <div>
                <PageHeader
                    title="Money"
                    description="Loading financial data..."
                />
                <DashboardSkeleton />
            </div>
        );
    }

    return (
        <div>
            <PageHeader
                title="Money"
                description={
                    summary?.generated_at
                        ? `Overview generated on ${new Date(summary.generated_at).toLocaleString()}`
                        : 'Financial overview'
                }
                action={
                    <button onClick={load} disabled={loading} className="btn-secondary text-sm">
                        Refresh
                    </button>
                }
            />

            {error && <p className="mt-6 text-sm text-red-600">{error}</p>}

            {summary && (
                <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
                    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
                        <p className="text-sm font-medium text-gray-500">Total Revenue</p>
                        <p className="mt-2 text-2xl font-bold text-gray-900">
                            {formatCurrency(summary.total_revenue)}
                        </p>
                    </div>
                    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
                        <p className="text-sm font-medium text-gray-500">Cash Received</p>
                        <p className="mt-2 text-2xl font-bold text-green-600">
                            {formatCurrency(summary.total_cash_received)}
                        </p>
                    </div>
                    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
                        <p className="text-sm font-medium text-gray-500">Outstanding AR</p>
                        <p className="mt-2 text-2xl font-bold text-amber-600">
                            {formatCurrency(summary.outstanding_receivables)}
                        </p>
                    </div>
                    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
                        <p className="text-sm font-medium text-gray-500">Total Orders</p>
                        <p className="mt-2 text-2xl font-bold text-gray-900">
                            {summary.total_orders}
                        </p>
                    </div>
                </div>
            )}

            {!loading && receivables.length === 0 ? (
                <div className="mt-8">
                    <EmptyState
                        icon={BanknotesIcon}
                        title="No transactions recorded yet"
                        description="Financial records will appear here once orders are processed."
                    />
                </div>
            ) : (
                <div className="mt-8 overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
                    <div className="border-b border-gray-200 bg-gray-50 px-6 py-4">
                        <h3 className="text-base font-semibold text-gray-900">Outstanding Invoices</h3>
                    </div>
                    <table className="min-w-full divide-y divide-gray-200 text-sm">
                        <thead className="bg-gray-50">
                            <tr>
                                <th className="px-6 py-3 text-left font-medium text-gray-500">Order ID</th>
                                <th className="px-6 py-3 text-left font-medium text-gray-500">Status</th>
                                <th className="px-6 py-3 text-right font-medium text-gray-500">Total</th>
                                <th className="px-6 py-3 text-right font-medium text-gray-500">Paid</th>
                                <th className="px-6 py-3 text-right font-medium text-gray-500">Balance</th>
                                <th className="px-6 py-3 text-right font-medium text-gray-500">Age</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-200">
                            {receivables.map((r) => (
                                <tr key={r.order_id} className="hover:bg-gray-50">
                                    <td className="px-6 py-4 font-mono text-xs text-gray-600">
                                        {r.order_id.slice(0, 8)}...
                                    </td>
                                    <td className="px-6 py-4">
                                        <StatusBadge status={r.status} />
                                    </td>
                                    <td className="px-6 py-4 text-right text-gray-900">
                                        {formatCurrency(r.total_amount)}
                                    </td>
                                    <td className="px-6 py-4 text-right text-green-600">
                                        {formatCurrency(r.total_paid)}
                                    </td>
                                    <td className="px-6 py-4 text-right font-medium text-red-600">
                                        {formatCurrency(r.balance_due)}
                                    </td>
                                    <td className="px-6 py-4 text-right text-gray-500">
                                        {r.age_days}d
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}
