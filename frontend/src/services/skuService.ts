import { api } from '@/services/api';
import type { ApiResponse, PaginatedData } from '@/types/api';

export interface SKU {
  id: string;
  catalog_product_id: string;
  sku_code: string;
  name: string;
  description: string | null;
  unit: string;
  package_quantity: number;
  category: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface SKUCreateRequest {
  catalog_product_id?: string;
  sku_code: string;
  name: string;
  description?: string;
  unit?: string;
  package_quantity?: number;
  category?: string;
  is_active?: boolean;
}

export interface SKUUpdateRequest {
  name?: string;
  description?: string;
  unit?: string;
  package_quantity?: number;
  category?: string;
  is_active?: boolean;
}

export const skuService = {
  getAll: (page = 1, size = 50, q?: string, is_active?: boolean) =>
    api.get<ApiResponse<PaginatedData<SKU>>>('/skus', {
      params: {
        page,
        size,
        ...(q ? { q } : {}),
        ...(is_active !== undefined ? { is_active } : {}),
      },
    }),

  getByCode: (skuCode: string) =>
    api.get<ApiResponse<SKU>>(`/skus/${skuCode}`),

  create: (data: SKUCreateRequest) =>
    api.post<ApiResponse<SKU>>('/skus', data),

  update: (skuCode: string, data: SKUUpdateRequest) =>
    api.put<ApiResponse<SKU>>(`/skus/${skuCode}`, data),
};
