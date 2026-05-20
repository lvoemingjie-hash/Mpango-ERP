import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { financeService } from '@/services/financeService';
import type { FinancialSummary, CreditReceivableItem, ReceivablesSummary } from '@/services/financeService';
import { PageHeader } from '@/components/layout/PageHeader';
import { EmptyState } from '@/components/ui/EmptyState';
import { DashboardSkeleton } from '@/components/skeletons/DashboardSkeleton';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { Pagination } from '@/components/ui/Pagination';
import { BanknotesIcon, ArrowPathIcon } from '@heroicons/react/24/outline';

type ReceivableTab = 'all' | 'credit_receivable' | 'unpaid_order';

const ALLOWED_TABS: ReceivableTab[] = ['all', 'credit_receivable', 'unpaid_order'];
const PAGE_SIZE = 20;
const COLLECTION_RECORDED = 'recorded';

function parseTab(value: string | null): ReceivableTab {
    if (value && ALLOWED_TABS.includes(value as ReceivableTab)) return value as ReceivableTab;
    return 'all';
}

function parsePage(value: string | null): number {
    if (!value) return 1;
    const n = Number(value);
    return Number.isInteger(n) && n > 0 ? n : 1;
}

function parseCollectedOrderId(value: string | null): string | null {
    if (!value) return null;
    const trimmed = value.trim();
    return trimmed.length > 0 && trimmed.length <= 64 ? trimmed : null;
}

function buildFinanceSearchParams(
    tab: ReceivableTab,
    page: number,
    collectionNotice?: { recorded: boolean; orderId: string | null },
): URLSearchParams {
    const next = new URLSearchParams();
    if (tab !== 'all') next.set('tab', tab);
    if (page !== 1) next.set('page', String(page));
    if (collectionNotice?.recorded) {
        next.set('collection', COLLECTION_RECORDED);
        if (collectionNotice.orderId) next.set('collectedOrder', collectionNotice.orderId);
    }
    return next;
}

function agingStyle(days: number): string {
    if (days >= 30) return 'text-red-600';
    if (days >= 15) return 'text-orange-600';
    if (days >= 7) return 'text-amber-600';
    return 'text-gray-500';
}

function agingLabel(days: number): string {
    if (days >= 30) return `${days}d overdue`;
    if (days >= 15) return `${days}d aging`;
    return `${days}d`;
}

function PaymentBar({ paid, total }: { paid: number; total: number }) {
    if (total <= 0) return null;
    const pct = Math.min(100, Math.round((paid / total) * 100));
    const barColor = pct >= 100 ? 'bg-green-500' : pct >= 50 ? 'bg-blue-500' : 'bg-amber-500';
    return (
        <div className="mt-1 h-1 w-full rounded-full bg-gray-200">
            <div className={`h-1 rounded-full ${barColor}`} style={{ width: `${pct}%` }} />
        </div>
    );
}

export function FinancePage() {
    const navigate = useNavigate();
    const [searchParams, setSearchParams] = useSearchParams();
    const searchKey = searchParams.toString();
    const tab = parseTab(searchParams.get('tab'));
    const page = parsePage(searchParams.get('page'));
    const collectionRecorded = searchParams.get('collection') === COLLECTION_RECORDED;
    const collectedOrderId = collectionRecorded
        ? parseCollectedOrderId(searchParams.get('collectedOrder'))
        : null;
    const [summary, setSummary] = useState<FinancialSummary | null>(null);
    const [receivablesSummary, setReceivablesSummary] = useState<ReceivablesSummary | null>(null);
    const [receivables, setReceivables] = useState<CreditReceivableItem[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [totalItems, setTotalItems] = useState(0);
    const [totalPages, setTotalPages] = useState(0);

    // Canonicalize invalid/noisy query params while keeping the URL as the source of truth.
    useEffect(() => {
        const next = buildFinanceSearchParams(tab, page, {
            recorded: collectionRecorded,
            orderId: collectedOrderId,
        });
        if (next.toString() !== searchKey) {
            setSearchParams(next, { replace: true });
        }
    }, [tab, page, collectionRecorded, collectedOrderId, searchKey, setSearchParams]);

    const changeTab = (t: ReceivableTab) => {
        setSearchParams(buildFinanceSearchParams(t, 1), { replace: true });
    };

    const changePage = (nextPage: number) => {
        setSearchParams(buildFinanceSearchParams(tab, nextPage), { replace: true });
    };

    const dismissCollectionNotice = () => {
        setSearchParams(buildFinanceSearchParams(tab, page), { replace: true });
    };

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

    const formatCurrency = (amount: number) => {
        return new Intl.NumberFormat('en-KE', {
            style: 'currency',
            currency: 'KES',
        }).format(amount);
    };

    const overdueCount = summary?.overdue_receivables_count ?? 0;

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

    const goToCollect = (orderId?: string) => {
        if (!orderId) { navigate('/orders'); return; }
        const params = new URLSearchParams({ collect: orderId, returnTo: 'finance' });
        if (tab !== 'all') params.set('financeTab', tab);
        if (page !== 1) params.set('financePage', String(page));
        navigate(`/orders?${params.toString()}`);
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
                        <button onClick={() => goToCollect()} className="btn-secondary text-sm">
                            Record Repayment
                        </button>
                        <button onClick={load} disabled={loading} className="btn-secondary text-sm">
                            Refresh
                        </button>
                    </div>
                }
            />

            {collectionRecorded && (
                <div className="mt-6 rounded-md border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                        <div>
                            <p className="font-semibold">Payment recorded</p>
                            <p className="mt-1">
                                You are back in Accounts Receivable
                                {collectedOrderId ? ` after collecting payment for order ${collectedOrderId.slice(0, 8)}...` : ''}
                                . Refresh is available if you want to confirm the latest balance immediately.
                            </p>
                        </div>
                        <button
                            type="button"
                            onClick={dismissCollectionNotice}
                            className="self-start rounded-md bg-green-100 px-2 py-1 text-xs font-medium text-green-800 hover:bg-green-200"
                        >
                            Dismiss
                        </button>
                    </div>
                </div>
            )}

            {error && (
                <div className="mt-6 flex items-center gap-3 rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">
                    <span>{error}</span>
                    <button
                        onClick={load}
                        className="inline-flex items-center gap-1 rounded-md bg-red-100 px-2 py-1 text-xs font-medium text-red-800 hover:bg-red-200"
                    >
                        <ArrowPathIcon className="h-3 w-3" />
                        Retry
                    </button>
                </div>
            )}

            {loading && summary && (
                <div className="mt-4 flex items-center gap-2 text-sm text-gray-500">
                    <ArrowPathIcon className="h-4 w-4 animate-spin" />
                    Updating...
                </div>
            )}

            {summary && (
                <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
                    <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 shadow-sm">
                        <p className="text-sm font-medium text-amber-700">Outstanding Receivables</p>
                        <p className="mt-2 text-2xl font-bold text-amber-800">
                            {formatCurrency(receivablesSummary?.total_outstanding ?? summary.outstanding_receivables)}
                        </p>
                        <p className="mt-1 text-xs text-amber-600">
                            across {receivablesSummary?.retailer_count ?? 0} retailer{(receivablesSummary?.retailer_count ?? 0) !== 1 ? 's' : ''}
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
                    <div className={`rounded-lg border p-4 shadow-sm ${overdueCount > 0 ? 'border-red-200 bg-red-50' : 'border-gray-200 bg-white'}`}>
                        <p className={`text-sm font-medium ${overdueCount > 0 ? 'text-red-700' : 'text-gray-500'}`}>Overdue</p>
                        <p className={`mt-2 text-2xl font-bold ${overdueCount > 0 ? 'text-red-600' : 'text-gray-400'}`}>
                            {overdueCount}
                        </p>
                        <p className="mt-1 text-xs text-gray-500">
                            {overdueCount > 0 ? '30+ days outstanding' : 'No overdue accounts'}
                        </p>
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
                                    Click <strong>Collect</strong> to record a repayment against an order.
                                </p>
                            </div>
                            <div className="flex gap-1">
                                {(['all', 'credit_receivable', 'unpaid_order'] as const).map((t) => (
                                    <button
                                        key={t}
                                        onClick={() => changeTab(t)}
                                        className={`rounded-md px-3 py-1 text-sm font-medium transition-colors ${
                                            tab === t
                                                ? 'bg-primary-600 text-white'
                                                : 'text-gray-600 hover:bg-gray-100'
                                        }`}
                                    >
                                        {t === 'all'
                                            ? `All (${totalItems})`
                                            : t === 'credit_receivable'
                                                ? 'Credit'
                                                : 'Unpaid'}
                                    </button>
                                ))}
                            </div>
                        </div>
                    </div>
                    <div className="overflow-x-auto">
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
                                <th className="px-6 py-3 text-right font-medium text-gray-500">Next Action</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-200">
                            {receivables.map((r) => {
                                const hasBalance = r.balance_due > 0;
                                const isOverdue = r.age_days >= 30;
                                return (
                                    <tr key={r.order_id} className={`hover:bg-gray-50 ${isOverdue && hasBalance ? 'bg-red-50/40' : ''}`}>
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
                                            <PaymentBar paid={r.cash_paid} total={r.total_amount} />
                                        </td>
                                        <td className="px-6 py-4 text-right text-green-600">
                                            {formatCurrency(r.cash_paid)}
                                        </td>
                                        <td className={`px-6 py-4 text-right font-medium ${hasBalance ? 'text-red-600' : 'text-green-600'}`}>
                                            {hasBalance ? formatCurrency(r.balance_due) : 'Settled'}
                                        </td>
                                        <td className="px-6 py-4 text-right">
                                            <span className={`text-xs font-medium ${agingStyle(r.age_days)}`}>
                                                {agingLabel(r.age_days)}
                                            </span>
                                        </td>
                                        <td className="px-6 py-4 text-right">
                                            <div className="flex justify-end gap-2">
                                                <button
                                                    onClick={() => handleDownloadInvoice(r.order_id)}
                                                    className="text-gray-500 hover:text-gray-700 text-xs"
                                                >
                                                    Invoice
                                                </button>
                                                {hasBalance && (
                                                    <button
                                                        onClick={() => goToCollect(r.order_id)}
                                                        className={`inline-flex items-center rounded-md px-2 py-1 text-xs font-medium ${
                                                            isOverdue
                                                                ? 'bg-red-100 text-red-700 hover:bg-red-200'
                                                                : 'bg-green-100 text-green-700 hover:bg-green-200'
                                                        }`}
                                                    >
                                                        {isOverdue ? 'Collect Now' : 'Collect'}
                                                    </button>
                                                )}
                                            </div>
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                    </div>

                    {totalPages > 1 && (
                        <div className="px-6 py-3">
                            <Pagination
                                page={page}
                                totalPages={totalPages}
                                onPageChange={changePage}
                            />
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
