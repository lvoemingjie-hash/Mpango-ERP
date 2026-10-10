export interface RetailerPriceView {
  sku_id: string;
  sku_code: string;
  sku_name: string;
  retailer_id: string;
  price: string | null;
  base_price: string | null;
  override_price: string | null;
  override_retired: boolean;
  currency: 'KES' | 'UGX';
  pricing_revision: number;
  price_source: string | null;
  unorderable_reason: string | null;
  updated_at: string | null;
}

export interface RetailerPriceListData {
  items: RetailerPriceView[];
  total: number;
}

export interface SetPriceRequest {
  retailer_id: string;
  sku_id: string;
  price: string;
  expected_revision: number;
  retire?: boolean;
}

export interface SetPriceResponse {
  sku_id: string;
  retailer_id: string;
  price: string;
  action: 'saved' | 'retired';
}

export interface ServerQuote {
  quote_token: string;
  currency: 'KES' | 'UGX';
  country: 'KE' | 'UG';
  total: string;
  expires_at: number;
  lines: {
    sku_id: string; sku_code: string; product_name: string; quantity: number;
    unit: string; package_quantity: string; display_label: string;
    unit_price: string; subtotal: string; revision: number; source: string;
  }[];
}
