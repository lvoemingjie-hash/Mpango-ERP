/**
 * Client-facing View Model types for Retailer App.
 *
 * These types mirror backend schemas/client.py View Models.
 * They NEVER expose wholesaler-internal fields like cost_price.
 */

export type StockLevel = 'OUT_OF_STOCK' | 'LOW' | 'MEDIUM' | 'HIGH';

export interface ClientProduct {
  id: string;
  name: string;
  sku_code: string;
  category: string | null;
  unit: string;
  price: number | null;
  in_stock: boolean;
  stock_level: StockLevel;
  can_order: boolean;
}

export interface ClientProductDetail extends ClientProduct {
  description: string | null;
}

export interface ClientOrderItem {
  product_name: string;
  sku_code: string;
  quantity: number;
  unit_price: number;
  subtotal: number;
}

export type ClientOrderStatus = 'CREATED' | 'CONFIRMED' | 'DELIVERED' | 'CANCELLED' | 'RETURNED';

export interface ClientOrder {
  id: string;
  status: ClientOrderStatus;
  total_amount: number;
  item_count: number;
  notes: string | null;
  items: ClientOrderItem[];
  created_at: string;
}

export interface CreateOrderItem {
  sku_code: string;
  quantity: number;
}

export interface CreateOrderRequest {
  items: CreateOrderItem[];
  notes?: string;
}

export type ClientPaymentMethod = 'cash' | 'transfer' | 'credit';
export type ClientPaymentStatus = 'pending' | 'completed';

export interface ClientPayment {
  id: string;
  order_id: string;
  amount: string;
  method: ClientPaymentMethod;
  status: ClientPaymentStatus;
  created_at: string;
}

export interface ClientFinanceBalance {
  outstanding_balance: string;
  has_outstanding_balance: boolean;
  updated_at: string;
}
