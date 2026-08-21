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

/**
 * Backend RetailerRegisterRequest (DC-12R1-MVP-L1-J1-H2-A landing page).
 * invitation_code travels ONLY in the JSON body — never in a URL.
 */
export interface RetailerRegisterPayload {
  invitation_code: string;
  phone: string;
  name?: string;
  email?: string;
  address?: string;
}

export interface RetailerRegisterResult {
  retailer: Retailer;
  binding: {
    id: string;
    wholesaler_id: string;
    retailer_id: string;
    status: string;
    created_at: string;
  };
}

export const retailerService = {
  // New unified CRM list endpoint
  getAll: (page = 1, size = 20) =>
    api.get<ApiResponse<RetailerListData>>(`/retailers?page=${page}&size=${size}`),

  getById: (id: string) =>
    api.get<ApiResponse<RetailerWithBinding>>(`/retailers/${id}`),

  /**
   * Public invitation acceptance (POST /retailers/register). Atomic backend
   * transaction: binding + tenant user + setup-credential email.
   */
  registerWithInvitation: (payload: RetailerRegisterPayload) =>
    api.post<ApiResponse<RetailerRegisterResult>>('/retailers/register', payload),

  // Keep old endpoint if still needed anywhere, though the UI will now use getAll
  getBindings: () =>
    api.get<ApiResponse<{ items: { binding: { status: string, created_at: string }, retailer: Retailer | null }[] }>>('/retailers/bindings'),
};
