import { api } from '@/services/api';
import type { ApiResponse, PaginatedData } from '@/types/api';
import type {
  Tenant,
  CreateTenantRequest,
  UpdateTenantRequest,
} from '@/types/tenant';

/**
 * Tenant (Wholesaler) CRUD service.
 * Backend entity is "wholesalers" — frontend uses "tenants" terminology.
 */
export const tenantService = {
  getAll: (page = 1, size = 20) =>
    api.get<ApiResponse<PaginatedData<Tenant>>>('/wholesalers', {
      params: { page, size },
    }),

  getById: (id: string) =>
    api.get<ApiResponse<Tenant>>(`/wholesalers/${id}`),

  create: (data: CreateTenantRequest) =>
    api.post<ApiResponse<Tenant>>('/wholesalers', data),

  update: (id: string, data: UpdateTenantRequest) =>
    api.put<ApiResponse<Tenant>>(`/wholesalers/${id}`, data),

  delete: (id: string) =>
    api.delete(`/wholesalers/${id}`),
};
