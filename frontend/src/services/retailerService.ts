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
  /** R1 dual-entry: 'invite' (entry A) | 'code' (entry B) — server-derived. */
  join_source: string;
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
 * Backend RetailerRegisterRequest (dual-entry, DC-12R1-MVP-L1-J1-H2-A-R1).
 * Exactly ONE of invitation_code (entry A) or join_intent (entry B) — the
 * backend rejects both/neither. Email is REQUIRED. Credentials travel ONLY
 * in the JSON body — never in a URL; there is no wholesaler_id field (the
 * bound supplier is resolved server-side from the verified credential).
 */
export interface RetailerRegisterPayload {
  invitation_code?: string;
  join_intent?: string;
  phone: string;
  name?: string;
  email: string;
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
  /** Server-verified supplier portal code for /retail/login?w=<code>. */
  wholesaler_code: string;
}

export const retailerService = {
  // New unified CRM list endpoint
  getAll: (page = 1, size = 20) =>
    api.get<ApiResponse<RetailerListData>>(`/retailers?page=${page}&size=${size}`),

  getById: (id: string) =>
    api.get<ApiResponse<RetailerWithBinding>>(`/retailers/${id}`),

  /**
   * R1 dual-entry: wholesaler-side post-hoc control — deactivate a retailer
   * relationship. Requires the retailers:deactivate permission server-side.
   */
  deactivate: (retailerId: string) =>
    api.post<ApiResponse<{ id: string; status: string }>>(
      `/retailers/${retailerId}/deactivate`,
    ),

  /**
   * Public invitation acceptance (POST /retailers/register). Atomic backend
   * transaction: binding + tenant user + setup-credential email.
   *
   * R1 hardening: explicitly EMPTY Authorization + full interceptor opt-out
   * (no global error toasts, no 401 refresh hijack) — the invitation code
   * travels only in the JSON body and the page keeps its fixed neutral copy.
   */
  registerWithInvitation: (payload: RetailerRegisterPayload) =>
    api.post<ApiResponse<RetailerRegisterResult>>('/retailers/register', payload, {
      headers: { Authorization: '' },
      skipAuthInterceptors: true,
    }),

  // Keep old endpoint if still needed anywhere, though the UI will now use getAll
  getBindings: () =>
    api.get<ApiResponse<{ items: { binding: { status: string, created_at: string }, retailer: Retailer | null }[] }>>('/retailers/bindings'),
};
