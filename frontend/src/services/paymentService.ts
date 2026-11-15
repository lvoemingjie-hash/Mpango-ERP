import { api } from '@/services/api';
import type { ApiResponse } from '@/types/api';

export interface PaymentData {
  id: string;
  order_id: string;
  retailer_id: string;
  transaction_id: string | null;
  amount: number;
  method: 'cash' | 'transfer' | 'credit';
  status: 'pending' | 'completed';
  created_at: string;
  updated_at: string;
}

export type PaymentCurrencyStatus = 'KNOWN' | 'LEGACY_CURRENCY_UNVERIFIED';

/** List-GET only: PaymentData plus the paying order's currency snapshot.
 *  Detail GET and POST responses do not carry these fields. */
export interface PaymentListItem extends PaymentData {
  currency: string | null;
  currency_status: PaymentCurrencyStatus;
}

export interface PaymentListData {
  items: PaymentListItem[];
  pagination: {
    page: number;
    size: number;
    total: number;
    pages: number;
  };
}

export const paymentService = {
  getAll: (page = 1, size = 20) =>
    api.get<ApiResponse<PaymentListData>>(`/payments?page=${page}&size=${size}`),

  getById: (id: string) =>
    api.get<ApiResponse<PaymentData>>(`/payments/${id}`),

  getByOrder: (orderId: string, page = 1, size = 100) =>
    api.get<ApiResponse<PaymentListData>>(`/payments?order_id=${orderId}&page=${page}&size=${size}`),
};
