import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { financeService } from '@/services/financeService';
import type { FinancialSummary, CreditReceivableItem, ReceivablesSummary } from '@/services/financeService';
import { PageHeader } from '@/components/layout/PageHeader';
import { EmptyState } from '@/components/ui/EmptyState';
import { DashboardSkeleton } from '@/components/skeletons/DashboardSkeleton';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { Pagination } from '@/components/ui/Pagination';
import { BanknotesIcon } from '@heroicons/react/24/outline';

type ReceivableTab = 'all' | 'credit_receivable' | 'unpaid_order';

const PAGE_SIZE = 20;

export function FinancePage() {
    const navigate = useNavigate();
    const [summary, setSummary] = useState<FinancialSummary | null>(null);
    const [receivablesSummary, setReceivablesSummary] = useState<ReceivablesSummary | null>(null);
    const [receivables, setReceivables] = useState<CreditReceivableItem[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [tab, setTab] = useState<ReceivableTab>('all');
    const [page, setPage] = useState(1);
    const [totalItems, setTotalItems] = useState(0);
    const [totalPages, setTotalPages] = useState(0);

    const load = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const classification = tab === 'all' ? undefined : tab;
            const [summaryRes, receivablesSummaryRes, receivablesRes] = await Promise.all([
                financeService.getSummary(),
                financeService.getReceivablesSummary(),
                financeService.getReceivablesOrders(page, PAGE_SIZE, classification),
            ]);

            setSummary(summaryRes.data.data);
            setReceivablesSummary(receivablesSummaryRes.data.data);
            setReceivables(receivablesRes.data.data.items);
            setTotalItems(receivablesRes.data.data.pagination.total);
            setTotalPages(receivablesRes.data.data.pagination.pages);
        } catch {
            setError('Failed to load accounts receivable data.');
        } finally {
            setLoading(false);
        }
    }, [page, tab]);

    useEffect(() => { load(); }, [load]);

    useEffect(() => { setPage(1); }, [tab]);

    const formatCurrency = (amount: number) => {
        return new Intl.NumberFormat('en-KE', {
            style: 'currency',
            currency: 'KES',
        }).format(amount);
    };

    const overdueCount = receivables.filter((r) => r.balance_due > 0 && r.age_days >= 30).length;
    const creditCount = receivables.filter((r) => r.classification === 'credit_receivable').length;
    const unpaidCount = receivables.filter((r) => r.classification === 'unpaid_order').length;

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
        } catch {
            setError('Failed to download invoice for the selected order.');
        }
    };

    const goToOrdersForRepayment = () => {
        navigate('/orders');
    };

    if (loading && !summary) {
        return (
            <div>
                <PageHeader
                    title="Accounts Receivable"
                    description="Loading credit sales and outstanding balances..."
                />
                <DashboardSkeleton />
            </div>
        );
    }

    return (
        <div>
            <PageHeader
                title="Accounts Receivable"
                description={
                    summary?.generated_at
                        ? `Credit sales and outstanding balances generated on ${new Date(summary.generated_at).toLocaleString()}`
                        : 'Track credit sales, unpaid orders, and repayment follow-up'
                }
                action={
                    <div className="flex items-center gap-3">
                        <button onClick={goToOrdersForRepayment} className="btn-secondary text-sm">
                            Record Repayment
                        </button>
                        <button onClick={load} disabled={loading} className="btn-secondary text-sm">
                            Refresh
                        </button>
                    </div>
                }
            />

            {error && <p className="mt-6 text-sm text-red-600">{error}</p>}

            {summary && (
                <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
                    <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 shadow-sm">
                        <p className="text-sm font-medium text-amber-700">Outstanding Receivables</p>
                        <p className="mt-2 text-2xl font-bold text-amber-800">
                            {formatCurrency(receivablesSummary?.total_outstanding ?? summary.outstanding_receivables)}
                        </p>
                    </div>
                    <div className="rounded-lg border border-blue-200 bg-blue-50 p-4 shadow-sm">
                        <p className="text-sm font-medium text-blue-700">Credit Exposure</p>
                        <p className="mt-2 text-2xl font-bold text-blue-800">
                            {formatCurrency(receivablesSummary?.credit_receivables ?? 0)}
                        </p>
                        <p className="mt-1 text-xs text-blue-600">
                            {receivablesSummary?.order_count ?? 0} receivable order{receivablesSummary?.order_count !== 1 ? 's' : ''}
                        </p>
                    </div>
                    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
                        <p className="text-sm font-medium text-gray-500">Overdue Accounts</p>
                        <p className="mt-2 text-2xl font-bold text-red-600">
                            {overdueCount}
                        </p>
                        <p className="mt-1 text-xs text-gray-500">30+ days on this page</p>
                    </div>
                    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
                        <p className="text-sm font-medium text-gray-500">Cash Received</p>
                        <p className="mt-2 text-2xl font-bold text-green-600">
                            {formatCurrency(summary.total_cash_received)}
                        </p>
                    </div>
                    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
                        <p className="text-sm font-medium text-gray-500">Revenue</p>
                        <p className="mt-2 text-2xl font-bold text-gray-900">
                            {formatCurrency(summary.total_revenue)}
                        </p>
                    </div>
                </div>
            )}

            {!loading && receivables.length === 0 ? (
                <div className="mt-8">
                    <EmptyState
                        icon={BanknotesIcon}
                        title="No outstanding receivables"
                        description="All visible credit accounts are settled. New credit sales and unpaid orders will appear here for follow-up."
                    />
                </div>
            ) : (
                <div className="mt-8 overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
                    <div className="border-b border-gray-200 bg-gray-50 px-6 py-4">
                        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                            <div>
                                <h3 className="text-base font-semibold text-gray-900">Receivable Orders</h3>
                                <p className="mt-1 text-sm text-gray-500">
                                    Use Orders to record repayments; invoices are available from each row.
                                </p>
                            </div>
                            <div className="flex gap-1">
                                {(['all', 'credit_receivable', 'unpaid_order'] as const).map((t) => (
                                    <button
                                        key={t}
                                        onClick={() => setTab(t)}
                                        className={`rounded-md px-3 py-1 text-sm font-medium transition-colors ${
                                            tab === t
                                                ? 'bg-primary-600 text-white'
                                                : 'text-gray-600 hover:bg-gray-100'
                                        }`}
                                    >
                                        {t === 'all'
                                            ? `All (${totalItems})`
                                            : t === 'credit_receivable'
                                                ? `Credit (${creditCount})`
                                                : `Unpaid (${unpaidCount})`}
                                    </button>
                                ))}
                            </div>
                        </div>
                    </div>
                    <table className="min-w-full divide-y divide-gray-200 text-sm">
                        <thead className="bg-gray-50">
                            <tr>
                                <th className="px-6 py-3 text-left font-medium text-gray-500">Order</th>
                                <th className="px-6 py-3 text-left font-medium text-gray-500">Retailer</th>
                                <th className="px-6 py-3 text-left font-medium text-gray-500">Type</th>
                                <th className="px-6 py-3 text-left font-medium text-gray-500">Status</th>
                                <th className="px-6 py-3 text-right font-medium text-gray-500">Total</th>
                                <th className="px-6 py-3 text-right font-medium text-gray-500">Paid</th>
                                <th className="px-6 py-3 text-right font-medium text-gray-500">Balance</th>
                                <th className="px-6 py-3 text-right font-medium text-gray-500">Age</th>
                                <th className="px-6 py-3 text-right font-medium text-gray-500">Actions</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-200">
                            {receivables.map((r) => (
                                <tr key={r.order_id} className="hover:bg-gray-50">
                                    <td className="px-6 py-4 font-mono text-xs text-gray-600">
                                        {r.order_id.slice(0, 8)}...
                                    </td>
                                    <td className="px-6 py-4 text-gray-700">
                                        <div className="font-medium">{r.retailer_name || 'Unknown retailer'}</div>
                                        <div className="font-mono text-xs text-gray-400">{r.retailer_id?.slice(0, 8) ?? '--'}...</div>
                                    </td>
                                    <td className="px-6 py-4">
                                        <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                                            r.classification === 'credit_receivable'
                                                ? 'bg-blue-100 text-blue-700'
                                                : 'bg-gray-100 text-gray-600'
                                        }`}>
                                            {r.classification === 'credit_receivable' ? 'Credit' : 'Unpaid'}
                                        </span>
                                    </td>
                                    <td className="px-6 py-4">
                                        <StatusBadge status={r.status} />
                                    </td>
                                    <td className="px-6 py-4 text-right text-gray-900">
                                        {formatCurrency(r.total_amount)}
                                    </td>
                                    <td className="px-6 py-4 text-right text-green-600">
                                        {formatCurrency(r.cash_paid)}
                                    </td>
                                    <td className="px-6 py-4 text-right font-medium text-red-600">
                                        {formatCurrency(r.balance_due)}
                                    </td>
                                    <td className="px-6 py-4 text-right">
                                        <span className={r.age_days >= 30 ? 'font-semibold text-red-600' : 'text-gray-500'}>
                                            {r.age_days}d{r.age_days >= 30 ? ' overdue' : ''}
                                        </span>
                                    </td>
                                    <td className="px-6 py-4 text-right">
                                        <div className="flex justify-end gap-3">
                                            <button
                                                onClick={() => handleDownloadInvoice(r.order_id)}
                                                className="text-gray-600 hover:text-gray-900"
                                            >
                                                Invoice
                                            </button>
                                            <button
                                                onClick={goToOrdersForRepayment}
                                                className="text-green-600 hover:text-green-900"
                                            >
                                                Record
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>

                    {totalPages > 1 && (
                        <div className="px-6 py-3">
                            <Pagination
                                page={page}
                                totalPages={totalPages}
                                onPageChange={setPage}
                            />
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
