import { api } from '@/services/api';
import type { ApiResponse, PaginatedData } from '@/types/api';
import type { StockView } from '@/types/inventory';

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
  getStocks: (page = 1, size = 50) =>
    api.get<ApiResponse<PaginatedData<StockView>>>('/inventory/stocks', {
      params: { page, size },
    }),

  adjustStock: (data: InventoryAdjustRequest) =>
    api.post<ApiResponse<InventoryAdjustResponse>>('/inventory/adjust', data),

  getLogs: (page = 1, size = 20) =>
    api.get<ApiResponse<MovementLogListData>>(`/inventory/logs?page=${page}&size=${size}`),
};
