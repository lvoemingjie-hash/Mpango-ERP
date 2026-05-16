/**
 * Finance service - mirrors backend api/v1/finance.py endpoints.
 *
 * Provides frontend access to invoices, receivables, and financial summary.
 */
import { api } from '@/services/api';
import type { ApiResponse, PaginatedData } from '@/types/api';

export interface InvoiceLineItem {
    product_name: string;
    sku_code: string;
    quantity: number;
    unit_price: number;
    subtotal: number;
}

export interface InvoiceLedgerEntry {
    date: string;
    account: string;
    amount: number;
    description: string | null;
}

export interface InvoiceData {
    invoice_number: string;
    order_id: string;
    status: string;
    created_at: string | null;
    updated_at: string | null;
    retailer_id: string | null;
    wholesaler_id: string | null;
    line_items: InvoiceLineItem[];
    subtotal: number;
    total_amount: number;
    total_paid: number;
    balance_due: number;
    ledger_entries: InvoiceLedgerEntry[];
}

export interface ReceivableItem {
    order_id: string;
    retailer_id: string | null;
    status: string;
    total_amount: number;
    total_paid: number;
    balance_due: number;
    created_at: string | null;
    age_days: number;
}

export interface RetailerReceivablesSummary {
    retailer_id: string;
    retailer_name: string;
    outstanding_balance: number;
    credit_receivables: number;
    unpaid_order_balance: number;
    order_count: number;
}

export interface CreditReceivableItem {
    order_id: string;
    retailer_id: string;
    retailer_name: string;
    status: string;
    classification: 'credit_receivable' | 'unpaid_order' | null;
    payment_method: 'credit' | 'cash' | 'unknown';
    total_amount: number;
    cash_paid: number;
    credit_amount: number;
    balance_due: number;
    created_at: string | null;
    age_days: number;
}

export interface ReceivablesSummary {
    total_outstanding: number;
    retailer_count: number;
    order_count: number;
    credit_receivables: number;
    unpaid_order_balance: number;
    by_retailer: RetailerReceivablesSummary[];
}

export interface FinancialSummary {
    total_revenue: number;
    total_cash_received: number;
    outstanding_receivables: number;
    overdue_receivables_count: number;
    order_counts: Record<string, number>;
    total_orders: number;
    generated_at: string;
}

export const financeService = {
    /** Generate an invoice for a specific order */
    getInvoice: (orderId: string) =>
        api.get<ApiResponse<InvoiceData>>(`/orders/${orderId}/invoice`),

    /** Legacy receivables list */
    getReceivables: (page = 1, size = 20) =>
        api.get<ApiResponse<PaginatedData<ReceivableItem>>>('/finance/receivables', {
            params: { page, size },
        }),

    /** Get aggregated financial summary */
    getSummary: () =>
        api.get<ApiResponse<FinancialSummary>>('/finance/summary'),

    /** Get classified receivable orders (credit exposure vs unpaid order balance) */
    getReceivablesOrders: (
        page = 1,
        size = 20,
        classification?: 'credit_receivable' | 'unpaid_order'
    ) =>
        api.get<ApiResponse<PaginatedData<CreditReceivableItem>>>('/finance/receivables/orders', {
            params: { page, size, ...(classification ? { classification } : {}) },
        }),

    /** Get receivables summary grouped by retailer */
    getReceivablesSummary: () =>
        api.get<ApiResponse<ReceivablesSummary>>('/finance/receivables/summary'),
};
