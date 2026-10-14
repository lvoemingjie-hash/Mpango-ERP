import { api } from '@/services/api';
import type { ApiResponse, PaginatedData } from '@/types/api';
import type { ClientOrder, CreateOrderRequest, ReorderPreview, ReorderRequest, ReorderSelection } from '@/types/client';
import type { OrderPrintView } from '@/types/print';
import type { ServerQuote } from '@/types/pricing';

export const clientOrderService = {
  preview: (data: Omit<CreateOrderRequest, 'quote_token' | 'notes'>) =>
    api.post<ApiResponse<ServerQuote>>('/client/orders/quote', data),

  create: (data: CreateOrderRequest, key: string) =>
    api.post<ApiResponse<ClientOrder>>('/client/orders', data, { headers: { 'X-Idempotency-Key': key } }),

  replaceDraft: (id: string, data: CreateOrderRequest, key: string) =>
    api.post<ApiResponse<ClientOrder>>(`/client/orders/${id}/replace-draft`, data, { headers: { 'X-Idempotency-Key': key } }),

  previewReorder: (sourceId: string, selections?: ReorderSelection[]) =>
    api.post<ApiResponse<ReorderPreview>>(`/client/orders/${encodeURIComponent(sourceId)}/reorder/quote`,
      selections ? { selections } : {}),

  submitReorder: (sourceId: string, data: ReorderRequest, key: string) =>
    api.post<ApiResponse<ClientOrder>>('/client/orders', { ...data, source_order_id: sourceId },
      { headers: { 'X-Idempotency-Key': key } }),

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
