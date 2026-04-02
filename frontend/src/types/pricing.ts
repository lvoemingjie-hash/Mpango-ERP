export interface RetailerPriceView {
  sku_id: string;
  sku_code: string;
  sku_name: string;
  retailer_id: string;
  price: number;
  updated_at: string | null;
}

export interface RetailerPriceListData {
  items: RetailerPriceView[];
  total: number;
}

export interface SetPriceRequest {
  retailer_id: string;
  sku_id: string;
  price: number;
}

export interface SetPriceResponse {
  sku_id: string;
  retailer_id: string;
  price: number;
  action: 'created' | 'updated';
}
