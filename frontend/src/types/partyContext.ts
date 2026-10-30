/** Exact snake_case read DTOs; neither is a write permission or a balance lock. */
export interface ContextSubject { tenant_id: string; user_id: string }
export interface BusinessIdentity {
  id: string;
  name: string | null;
  name_resolution: 'RESOLVED' | 'MISSING';
}
export interface SupplierIdentity extends BusinessIdentity { code: string }
export interface ActiveBinding { id: string; status: 'active' }

export interface ClientPortalContext {
  context: ContextSubject;
  supplier: SupplierIdentity;
  retailer: BusinessIdentity;
  binding: ActiveBinding;
  observed_at: string;
}
export interface CashierReviewContext {
  context: ContextSubject;
  supplier: SupplierIdentity;
  retailer: BusinessIdentity;
  binding: ActiveBinding;
  declaration: {
    id: string; order_id: string; status: 'pending' | 'confirmed' | 'rejected';
    declared_amount: string; method: 'cash' | 'transfer'; transfer_reference: string | null;
  };
  order: { id: string; status: string };
  money: {
    currency: 'KES' | 'UGX' | null;
    currency_status: 'KNOWN' | 'LEGACY_CURRENCY_UNVERIFIED' | 'UNSUPPORTED';
    balance_due: string | null;
    balance_status: 'VERIFIED' | 'UNVERIFIED';
  };
  review_state: 'READY' | 'UNRESOLVED' | 'NOT_ACTIONABLE';
  reason_codes: string[];
  observed_at: string;
}

const object = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null;
const text = (v: unknown): v is string => typeof v === 'string' && v.trim().length > 0;
const decimal = (v: unknown): v is string => typeof v === 'string' && /^\d+(?:\.\d+)?$/.test(v);
function identity(v: unknown): v is BusinessIdentity {
  return object(v) && text(v.id) && (v.name_resolution === 'MISSING' ? v.name === null
    : v.name_resolution === 'RESOLVED' && text(v.name));
}
function parties(v: Record<string, unknown>): boolean {
  return object(v.context) && text(v.context.user_id) && text(v.context.tenant_id)
    && identity(v.supplier) && object(v.supplier) && text(v.supplier.code)
    && identity(v.retailer) && object(v.binding) && text(v.binding.id) && v.binding.status === 'active'
    && text(v.observed_at) && /^\d{4}-\d{2}-\d{2}T/.test(v.observed_at);
}
export function isClientPortalContext(v: unknown): v is ClientPortalContext {
  return object(v) && parties(v) && !('money' in v) && !('declaration' in v);
}
export function isCashierReviewContext(v: unknown): v is CashierReviewContext {
  if (!object(v) || !parties(v) || !object(v.declaration) || !object(v.order) || !object(v.money)) return false;
  const d = v.declaration; const m = v.money;
  if (!text(d.id) || !text(d.order_id) || !['pending', 'confirmed', 'rejected'].includes(d.status as string)
    || !decimal(d.declared_amount) || /^0+(?:\.0+)?$/.test(d.declared_amount) || !['cash', 'transfer'].includes(d.method as string)
    || !(d.transfer_reference === null || typeof d.transfer_reference === 'string')
    || !text(v.order.id) || !text(v.order.status)
    || !['READY', 'UNRESOLVED', 'NOT_ACTIONABLE'].includes(v.review_state as string)
    || !Array.isArray(v.reason_codes) || !v.reason_codes.every(text)) return false;
  if (m.currency_status === 'KNOWN') {
    if (!['KES', 'UGX'].includes(m.currency as string)) return false;
    if (!(m.currency === 'KES' ? /^\d+\.\d{2}$/ : /^\d+$/).test(d.declared_amount)) return false;
    if (m.balance_status === 'VERIFIED') return typeof m.balance_due === 'string'
      && (m.currency === 'KES' ? /^\d+\.\d{2}$/ : /^\d+$/).test(m.balance_due);
    return m.balance_status === 'UNVERIFIED' && m.balance_due === null;
  }
  return ['LEGACY_CURRENCY_UNVERIFIED', 'UNSUPPORTED'].includes(m.currency_status as string)
    && m.currency === null && m.balance_due === null && m.balance_status === 'UNVERIFIED';
}
