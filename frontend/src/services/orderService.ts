import { api } from '@/services/api';
import type { ApiResponse, PaginatedData } from '@/types/api';
import type { Order } from '@/types/order';

export const orderService = {
  getAll: (page = 1, size = 50, status?: string) =>
    api.get<ApiResponse<PaginatedData<Order>>>('/orders', {
      params: { page, size, ...(status ? { status } : {}) },
    }),

  getById: (id: string) =>
    api.get<ApiResponse<Order>>(`/orders/${id}`),

  confirm: (id: string) =>
    api.post<ApiResponse<{ order_id: string; status: string }>>(`/orders/${id}/confirm`),

  cancel: (id: string) =>
    api.post<ApiResponse<{ order_id: string; status: string }>>(`/orders/${id}/cancel`),

  returnOrder: (id: string) =>
    api.post<ApiResponse<{ order_id: string; status: string }>>(`/orders/${id}/return`),
};
