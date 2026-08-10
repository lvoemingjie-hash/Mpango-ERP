import { api } from '@/services/api';
import type { ApiResponse, PaginatedData } from '@/types/api';
import type { ClientOrder, CreateOrderRequest } from '@/types/client';
import type { OrderPrintView } from '@/types/print';

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

  /**
   * DC-12R1-S3-S2B-I2C-I2 (Contract A, retailer side): read-only printable
   * order document. Server-authoritative; no client recomputation.
   */
  getPrint: (id: string) =>
    api.get<ApiResponse<OrderPrintView>>(`/client/orders/${encodeURIComponent(id)}/print`),
};
