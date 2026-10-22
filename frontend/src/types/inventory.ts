export interface StockView {
  sku_id: string;
  sku_code: string;
  sku_name: string;
  quantity_on_hand: number;
  quantity_reserved: number;
  quantity_available: number;
  updated_at: string;
}

export interface AdjustmentPolicy {
  policy_version: number; owner_direct_enabled: boolean; approver_ids: string[];
}
export interface AdjustmentSnapshot {
  sku_id: string; sku_code: string; unit: string; package_quantity: string;
  stock_revision: number; policy_version: number; quantity_on_hand: string; quantity_reserved: string;
}
export interface StockAdjustment {
  id: string; requester_id: string; sellable_unit_id: string; delta: string;
  payload: AdjustmentSnapshot & {reason: string; reason_kind: string};
  version: number; status: 'pending'|'approved_applied'|'rejected'|'withdrawn'|'applied_direct';
  result: null|{movement_id?:string; quantity_before?:string; quantity_after?:string; reason?:string};
  replayed: boolean;
}
export interface AdjustmentInput {
  sellable_unit_id: string; quantity_delta: string; reason_kind: string; reason: string;
  expected_stock_revision: number; expected_policy_version: number;
}
