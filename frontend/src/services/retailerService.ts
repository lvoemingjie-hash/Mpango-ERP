import { api } from '@/services/api';
import type { ApiResponse } from '@/types/api';

export interface Retailer {
  id: string;
  phone: string;
  name: string;
  email: string | null;
  address: string | null;
}

export interface RetailerBinding {
  id: string;
  wholesaler_id: string;
  retailer_id: string;
  status: string;
  created_at: string;
}

export interface RetailerBindingItem {
  binding: RetailerBinding;
  retailer: Retailer | null;
}

export interface BindingListData {
  items: RetailerBindingItem[];
}

export const retailerService = {
  getBindings: () =>
    api.get<ApiResponse<BindingListData>>('/retailers/bindings'),
};
