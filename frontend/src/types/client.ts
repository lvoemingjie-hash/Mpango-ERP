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
  price: string | null;
  currency?: 'KES' | 'UGX' | null;
  display_label?: string | null;
  unorderable_reason?: string | null;
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
  package_quantity_snapshot?: string | null;
  display_label_snapshot?: string | null;
  quantity: number;
  unit_price: string;
  subtotal: string;
}

export type ClientOrderStatus = 'CREATED' | 'CONFIRMED' | 'DELIVERED' | 'CANCELLED' | 'RETURNED';

export interface ClientOrder {
  id: string;
  status: ClientOrderStatus;
  total_amount: string;
  currency?: string | null;
  currency_status?: string;
  replaces_order_id?: string | null;
  source_order_id?: string | null;
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
  quote_token: string;
  items: CreateOrderItem[];
  notes?: string;
}

/** Every historical row has an explicit decision; the server owns identity and money. */
export type ReorderSelection =
  | { source_item_id: string; action: 'keep' | 'remove' }
  | { source_item_id: string; action: 'replace'; sellable_unit_id: string; quantity: number };

export interface ReorderRow {
  source_item_id: string;
  original: {
    product_name: string;
    sku_code: string;
    sellable_unit_id: string | null;
    identity_status: ClientOrderItem['identity_status'];
    unit: string | null;
    package_quantity: string | null;
    display_label: string | null;
    quantity: number;
    unit_price: string;
    subtotal: string;
  };
  selection: ReorderSelection;
  status: 'READY' | 'UNAVAILABLE' | 'REMOVED';
  reason: string | null;
  current: import('@/types/pricing').ServerQuote['lines'][number] | null;
  stock_warning: 'INSUFFICIENT_STOCK' | null;
}

export interface ReorderPreview {
  source_order_id: string;
  order_basis: 'HISTORICAL_ITEM_ID';
  historical_total: string;
  historical_currency: string | null;
  historical_currency_status: 'KNOWN' | 'LEGACY_CURRENCY_UNVERIFIED';
  rows: ReorderRow[];
  ready: boolean;
  quote: import('@/types/pricing').ServerQuote | null;
  current_total: string | null;
  current_currency: string;
  delta: string | null;
}

export interface ReorderRequest {
  selections: ReorderSelection[];
  quote_token: string;
  notes?: string;
}

export type ClientPaymentMethod = 'cash' | 'transfer' | 'credit';
export type ClientPaymentStatus = 'pending' | 'completed';

export interface ClientPayment {
  currency?: string | null;
  currency_status?: string;
  id: string;
  order_id: string;
  amount: string;
  method: ClientPaymentMethod;
  status: ClientPaymentStatus;
  created_at: string;
}

export interface ClientFinanceBalance {
  currency?: string | null;
  currency_status?: string;
  outstanding_balance: string;
  has_outstanding_balance: boolean;
  updated_at: string;
}
