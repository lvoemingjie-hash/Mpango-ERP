import { api } from '@/services/api';
import type { ApiResponse, PaginatedData } from '@/types/api';
import type { ClientFinanceBalance, ClientPayment } from '@/types/client';

export interface ClientPaymentFilters {
  method?: string;
  status?: string;
  order_id?: string;
}

export const clientFinanceService = {
  getPayments: (page = 1, size = 20, filters?: ClientPaymentFilters) =>
    api.get<ApiResponse<PaginatedData<ClientPayment>>>('/client/payments', {
      params: { page, size, ...filters },
    }),

  getBalance: () =>
    api.get<ApiResponse<ClientFinanceBalance>>('/client/finance/balance'),
};
