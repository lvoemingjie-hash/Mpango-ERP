import { api } from '@/services/api';
import type { ApiResponse, PaginatedData } from '@/types/api';
import type { ClientOrder, CreateOrderRequest } from '@/types/client';

export const clientOrderService = {
  create: (data: CreateOrderRequest) =>
    api.post<ApiResponse<ClientOrder>>('/client/orders', data),

  getAll: (page = 1, size = 20, status?: string) =>
    api.get<ApiResponse<PaginatedData<ClientOrder>>>('/client/orders', {
      params: { page, size, ...(status ? { status } : {}) },
    }),

  getById: (id: string) =>
    api.get<ApiResponse<ClientOrder>>(`/client/orders/${id}`),

  cancel: (id: string) =>
    api.post<ApiResponse<ClientOrder>>(`/client/orders/${id}/cancel`),
};
