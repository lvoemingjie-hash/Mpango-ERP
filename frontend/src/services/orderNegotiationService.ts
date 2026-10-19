import { api } from '@/services/api';
import type { ApiResponse } from '@/types/api';

export interface NegotiationPriceLine {
  sku_id: string;
  sku_code: string;
  product_name: string;
  quantity: number;
  unit: string;
  package_quantity: string;
  display_label: string | null;
  unit_price: string;
  subtotal: string;
}

export interface OrderNegotiation {
  id: string;
  source_order_id: string;
  version: number;
  digest: string;
  status: 'pending' | 'accepted' | 'rejected' | 'withdrawn';
  expires_at: string;
  expired: boolean;
  accepted_order_id: string | null;
  currency: 'UGX' | 'KES';
  country: 'UG' | 'KE';
  lines: NegotiationPriceLine[];
  original_lines: NegotiationPriceLine[];
  total: string;
  original_total: string;
  replayed?: boolean;
}

const base = (id: string, client: boolean) => `${client ? '/client' : ''}/orders/${encodeURIComponent(id)}/negotiations`;
const identity = (proposal: OrderNegotiation) => ({ version: proposal.version, digest: proposal.digest });

export const orderNegotiationService = {
  list: (id: string, client: boolean) => api.get<ApiResponse<{ items: OrderNegotiation[] }>>(base(id, client)),
  propose: (id: string, lines: { sku_id: string; unit_price: string }[], expires_at: string) =>
    api.post<ApiResponse<OrderNegotiation>>(base(id, false), { lines, expires_at }),
  withdraw: (id: string, proposal: OrderNegotiation) =>
    api.post<ApiResponse<OrderNegotiation>>(`${base(id, false)}/${proposal.id}/withdraw`, identity(proposal)),
  reject: (id: string, proposal: OrderNegotiation) =>
    api.post<ApiResponse<OrderNegotiation>>(`${base(id, true)}/${proposal.id}/reject`, identity(proposal)),
  accept: (id: string, proposal: OrderNegotiation, key: string) =>
    api.post<ApiResponse<OrderNegotiation>>(`${base(id, true)}/${proposal.id}/accept`, identity(proposal),
      { headers: { 'X-Idempotency-Key': key } }),
};
