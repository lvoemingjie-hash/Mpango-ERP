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

export interface PaymentListData {
  items: PaymentData[];
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
};
