export interface StockView {
  sku_id: string;
  sku_code: string;
  sku_name: string;
  quantity_on_hand: number;
  quantity_reserved: number;
  quantity_available: number;
  updated_at: string;
}
