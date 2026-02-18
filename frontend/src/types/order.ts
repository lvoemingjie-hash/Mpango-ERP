export type OrderStatus = 'draft' | 'confirmed' | 'partially_paid' | 'paid' | 'fulfilled' | 'cancelled' | 'voided' | 'returned';

export interface OrderItem {
  id: string;
  product_name: string;
  sku_code: string;
  quantity: number;
  unit_price: number;
  subtotal: number;
}

export interface Order {
  id: string;
  wholesaler_id: string;
  retailer_id: string;
  retailer_name: string | null;
  status: OrderStatus;
  total_amount: number;
  items: OrderItem[];
  notes: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export const ORDER_STATUS_LABELS: Record<OrderStatus, string> = {
  draft: 'Draft',
  confirmed: 'Confirmed',
  partially_paid: 'Partially Paid',
  paid: 'Paid',
  fulfilled: 'Fulfilled',
  cancelled: 'Cancelled',
  voided: 'Voided',
  returned: 'Returned',
};

export const ORDER_STATUS_COLORS: Record<OrderStatus, string> = {
  draft: 'gray',
  confirmed: 'blue',
  partially_paid: 'yellow',
  paid: 'green',
  fulfilled: 'green',
  cancelled: 'red',
  voided: 'red',
  returned: 'yellow',
};

/** Legal transitions from the backend state machine */
export const ALLOWED_TRANSITIONS: Record<OrderStatus, OrderStatus[]> = {
  draft: ['confirmed', 'cancelled'],
  confirmed: ['paid', 'cancelled'],
  partially_paid: ['paid', 'cancelled'],
  paid: ['fulfilled'],
  fulfilled: ['returned'],
  cancelled: [],
  voided: [],
  returned: [],
};
