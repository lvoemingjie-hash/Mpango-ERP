import { api } from '@/services/api';
import type { ApiResponse, PaginatedData } from '@/types/api';
import type {
  Tenant,
  CreateTenantRequest,
  UpdateTenantRequest,
} from '@/types/tenant';

type TenantRegistryResponse = ApiResponse<Tenant> & { message?: string };

/**
 * Tenant (Wholesaler) CRUD service.
 * Backend entity is "wholesalers"; frontend uses "tenants" terminology.
 * Create is registry-only; it does not provision schema, login, admin user, or RBAC.
 */
export const tenantService = {
  getAll: (page = 1, size = 20) =>
    api.get<ApiResponse<PaginatedData<Tenant>>>('/wholesalers', {
      params: { page, size },
    }),

  getById: (id: string) =>
    api.get<ApiResponse<Tenant>>(`/wholesalers/${id}`),

  create: (data: CreateTenantRequest) =>
    api.post<TenantRegistryResponse>('/wholesalers', data),

  update: (id: string, data: UpdateTenantRequest) =>
    api.put<ApiResponse<Tenant>>(`/wholesalers/${id}`, data),

  delete: (id: string) =>
    api.delete(`/wholesalers/${id}`),
};
