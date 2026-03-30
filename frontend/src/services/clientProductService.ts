import { api } from '@/services/api';
import type { ApiResponse, PaginatedData } from '@/types/api';
import type { ClientProduct, ClientProductDetail } from '@/types/client';

export const clientProductService = {
  getAll: (page = 1, size = 20, params?: { category?: string; search?: string }) =>
    api.get<ApiResponse<PaginatedData<ClientProduct>>>('/client/products', {
      params: { page, size, ...params },
    }),

  getById: (id: string) =>
    api.get<ApiResponse<ClientProductDetail>>(`/client/products/${id}`),
};
