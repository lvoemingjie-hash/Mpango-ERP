export type StaffTemplateKey = 'warehouse' | 'sales' | 'finance';
export interface StaffMember {
  id: string; email: string; full_name: string | null; is_active: boolean;
  template_key: StaffTemplateKey; credential_state: 'pending' | 'ready';
  employment_state: 'invited' | 'active' | 'disabled'; version: number;
}
export interface StaffTemplate {
  key: StaffTemplateKey; permission_codes: string[]; version: number; affected_count: number;
}
export const STAFF_CAPABILITIES = [
  'orders:read','orders:create','orders:confirm','orders:ship','orders:cancel','orders:return',
  'skus:read','inventory:read','retailers:read','pricing:read','pricing:write',
  'payments:read','payments:create','payments:confirm_declaration','finance:read','dashboards:read',
] as const;
