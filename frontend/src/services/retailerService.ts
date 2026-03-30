import { api } from '@/services/api';
import type { ApiResponse } from '@/types/api';

export interface Retailer {
  id: string;
  phone: string;
  name: string;
  email: string | null;
  address: string | null;
}

export interface RetailerWithBinding {
  retailer: Retailer;
  binding_status: string;
  bound_at: string;
}

export interface RetailerListData {
  items: RetailerWithBinding[];
  pagination: {
    page: number;
    size: number;
    total: number;
    pages: number;
  };
}

export const retailerService = {
  // New unified CRM list endpoint
  getAll: (page = 1, size = 20) =>
    api.get<ApiResponse<RetailerListData>>(`/retailers?page=${page}&size=${size}`),
    
  getById: (id: string) =>
    api.get<ApiResponse<RetailerWithBinding>>(`/retailers/${id}`),

  // Keep old endpoint if still needed anywhere, though the UI will now use getAll
  getBindings: () =>
    api.get<ApiResponse<{ items: { binding: { status: string, created_at: string }, retailer: Retailer | null }[] }>>('/retailers/bindings'),
};
