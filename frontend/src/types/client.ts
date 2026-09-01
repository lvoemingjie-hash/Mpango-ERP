/**
 * Client-facing View Model types for Retailer App.
 *
 * These types mirror backend schemas/client.py View Models.
 * They NEVER expose wholesaler-internal fields like cost_price.
 */

export type StockLevel = 'OUT_OF_STOCK' | 'LOW' | 'MEDIUM' | 'HIGH';

/**
 * DC-12R1-MVP-L1-SKU-R0-M1-R1-R1 product-level catalog contract.
 * One ClientProduct per CatalogProduct; packaging choices are nested units,
 * each carrying its own stable sellable_unit_id, price and stock.
 */
export interface ClientSellableUnit {
  sellable_unit_id: string;
  sku_code: string;
  unit: string;
  package_quantity: number;
  price: number | null;
  in_stock: boolean;
  stock_level: StockLevel;
  can_order: boolean;
}

export interface ClientProduct {
  id: string; // CatalogProduct.id — the customer product identity
  name: string;
  category: string | null;
  in_stock: boolean;
  stock_level: StockLevel;
  can_order: boolean;
  unit_count: number;
  units: ClientSellableUnit[];
}

export interface ClientProductDetail extends ClientProduct {
  description: string | null;
}

export interface ClientOrderItem {
  sellable_unit_id: string | null;
  identity_status: 'legacy' | 'linked_legacy' | 'stable';
  product_name: string;
  sku_code: string;
  unit_snapshot: string | null;
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
  sellable_unit_id: string;
  sku_code?: string;
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
