import { api } from '@/services/api';
import type { ApiResponse, PaginatedData } from '@/types/api';
import type { StockView, AdjustmentPolicy, AdjustmentSnapshot, StockAdjustment, AdjustmentInput } from '@/types/inventory';

export interface MovementLogEntry {
  id: string;
  sku_id: string;
  sku_code: string | null;
  movement_type: string;
  quantity: number;
  quantity_before: number;
  quantity_after: number;
  reason: string | null;
  reference_type: string | null;
  reference_id: string | null;
  created_at: string;
  created_by: string | null;
}

export interface MovementLogListData {
  items: MovementLogEntry[];
  pagination: {
    page: number;
    size: number;
    total: number;
    pages: number;
  };
}

export interface InventoryAdjustRequest {
  sku_code: string;
  quantity: number;
  reason: string;
}

export interface InventoryAdjustResponse {
  sku_code: string;
  quantity_before: number;
  quantity_after: number;
  adjustment: number;
  reason: string;
}

export const inventoryService = {
  getAdjustmentPolicy: async () => (await api.get<{data:AdjustmentPolicy}>('/inventory/adjustment-policy')).data.data,
  saveAdjustmentPolicy: async (body: {approver_ids:string[];owner_direct_enabled:boolean;expected_policy_version:number}) =>
    (await api.put<{data:AdjustmentPolicy}>('/inventory/adjustment-policy',body)).data.data,
  getAdjustmentSnapshot: async (id:string) =>
    (await api.get<{data:AdjustmentSnapshot}>('/inventory/adjustment-snapshot/'+id)).data.data,
  getAdjustmentRequests: async () =>
    (await api.get<{data:{items:StockAdjustment[];can_approve:boolean}}>('/inventory/adjustment-requests')).data.data,
  submitAdjustment: async (body:AdjustmentInput,key:string,direct=false) =>
    (await api.post<{data:StockAdjustment}>(direct?'/inventory/owner-adjustments':'/inventory/adjustment-requests',body,
      {headers:{'Idempotency-Key':key}})).data.data,
  decideAdjustment: async (row:StockAdjustment,action:'approve'|'reject'|'withdraw',key:string,reason='') =>
    (await api.post<{data:StockAdjustment}>(`/inventory/adjustment-requests/${row.id}/${action}`,
      {expected_version:row.version,reason},{headers:{'Idempotency-Key':key}})).data.data,
  getStocks: (page = 1, size = 50) =>
    api.get<ApiResponse<PaginatedData<StockView>>>('/inventory/stocks', {
      params: { page, size },
    }),

  adjustStock: (data: InventoryAdjustRequest) =>
    api.post<ApiResponse<InventoryAdjustResponse>>('/inventory/adjust', data),

  getLogs: (page = 1, size = 20) =>
    api.get<ApiResponse<MovementLogListData>>(`/inventory/logs?page=${page}&size=${size}`),
};
