import { api } from '@/services/api';
import type { ApiResponse, PaginatedData } from '@/types/api';
import type { StockView } from '@/types/inventory';

export const inventoryService = {
  getStocks: (page = 1, size = 50) =>
    api.get<ApiResponse<PaginatedData<StockView>>>('/inventory/stocks', {
      params: { page, size },
    }),
};
