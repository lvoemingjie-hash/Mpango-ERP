import { api } from '@/services/api';
import type { ApiResponse } from '@/types/api';
import type { RetailerPriceListData, SetPriceRequest, SetPriceResponse } from '@/types/pricing';

export const pricingService = {
  getPrices: (retailerId: string, page = 1, size = 50) =>
    api.get<ApiResponse<RetailerPriceListData>>('/pricing/prices', {
      params: { retailer_id: retailerId, page, size },
    }),

  setPrice: (data: SetPriceRequest) =>
    api.put<ApiResponse<SetPriceResponse>>('/pricing/prices', data),
};
