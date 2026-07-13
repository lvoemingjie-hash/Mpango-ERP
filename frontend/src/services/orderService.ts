import { api } from '@/services/api';
import type { ApiResponse, PaginatedData } from '@/types/api';
import type { Order, WholesalerOrderCreateRequest } from '@/types/order';

export type PaymentMethod = 'cash' | 'transfer' | 'credit';

export interface PayOrderData {
  method: PaymentMethod;
  amount: number;
  transaction_id?: string;
  notes?: string;
}

export interface PayOrderResponse {
  order_id: string;
  status: string;
  payment_id?: string;
  payment_amount?: string;
  payment_method?: string;
}

export const orderService = {
  getAll: (page = 1, size = 50, status?: string) =>
    api.get<ApiResponse<PaginatedData<Order>>>('/orders', {
      params: { page, size, ...(status ? { status } : {}) },
    }),

  getById: (id: string) =>
    api.get<ApiResponse<Order>>(`/orders/${id}`),

  create: (data: WholesalerOrderCreateRequest) =>
    api.post<ApiResponse<Order>>('/orders', data),

  confirm: (id: string) =>
    api.post<ApiResponse<{ order_id: string; status: string }>>(`/orders/${id}/confirm`),

  cancel: (id: string) =>
    api.post<ApiResponse<{ order_id: string; status: string }>>(`/orders/${id}/cancel`),

  /** Phase 5: pay with optional structured payment data */
  pay: (id: string, paymentData?: PayOrderData) =>
    api.post<ApiResponse<PayOrderResponse>>(
      `/orders/${id}/pay`,
      paymentData ?? {}
    ),

  fulfill: (id: string) =>
    api.post<ApiResponse<{ order_id: string; status: string }>>(`/orders/${id}/fulfill`),

  returnOrder: (id: string) =>
    api.post<ApiResponse<{ order_id: string; status: string }>>(`/orders/${id}/return`),
};
