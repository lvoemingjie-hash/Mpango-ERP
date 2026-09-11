import { api } from '@/services/api';
import type { ApiResponse, PaginatedData } from '@/types/api';

export interface SellableUnit {
  id: string;
  catalog_product_id: string;
  sku_code: string;
  unit: string;
  package_quantity: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CatalogProduct {
  id: string;
  name: string;
  description: string | null;
  category: string | null;
  is_active: boolean;
  sellable_units: SellableUnit[];
  created_at: string;
  updated_at: string;
}

export interface SellableUnitInput {
  sku_code: string;
  unit: string;
  package_quantity: number;
  is_active?: boolean;
}

export interface CatalogProductCreateRequest {
  name: string;
  description?: string;
  category?: string;
  is_active?: boolean;
  sellable_units: SellableUnitInput[];
}

export interface CatalogProductUpdateRequest {
  name?: string;
  description?: string;
  category?: string;
  is_active?: boolean;
}

export interface SellableUnitUpdateRequest {
  unit?: string;
  package_quantity?: number;
  is_active?: boolean;
}

export const catalogProductService = {
  getAll: (page = 1, size = 50, q?: string, is_active?: boolean) =>
    api.get<ApiResponse<PaginatedData<CatalogProduct>>>('/catalog-products', {
      params: { page, size, ...(q ? { q } : {}), ...(is_active !== undefined ? { is_active } : {}) },
    }),
  create: (data: CatalogProductCreateRequest) =>
    api.post<ApiResponse<CatalogProduct>>('/catalog-products', data),
  update: (productId: string, data: CatalogProductUpdateRequest) =>
    api.put<ApiResponse<CatalogProduct>>(`/catalog-products/${productId}`, data),
  addSellableUnit: (productId: string, data: SellableUnitInput) =>
    api.post<ApiResponse<CatalogProduct>>(`/catalog-products/${productId}/sellable-units`, data),
  updateSellableUnit: (
    productId: string,
    sellableUnitId: string,
    data: SellableUnitUpdateRequest,
  ) => api.put<ApiResponse<CatalogProduct>>(
    `/catalog-products/${productId}/sellable-units/${sellableUnitId}`,
    data,
  ),
};
