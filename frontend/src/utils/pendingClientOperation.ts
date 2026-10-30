import { useAuthStore } from '@/stores/authStore';
import { can, CLIENT_PERMISSIONS } from '@/utils/permissions';
import type { CreateOrderRequest } from '@/types/client';
import type { ServerQuote } from '@/types/pricing';

// Browser retention is a recovery aid, never an authorization or replay verdict.
// The existing authenticated service and backend still own both decisions.
export type OperationKind = 'create' | 'replace' | 'declare';
export type DeclarationBody = { declared_amount: string; method: 'cash' | 'transfer'; transfer_reference?: string | null };
export type PendingOperation =
  | { version: 1; scope: string; kind: 'create' | 'replace'; key: string; body: CreateOrderRequest; quote: ServerQuote }
  | { version: 1; scope: string; kind: 'declare'; key: string; body: DeclarationBody; currency: 'KES' | 'UGX' | null };

export function operationScope(kind: OperationKind, target: string): string | null {
  const { accessToken, user, retailerPortalCode, tenantCode } = useAuthStore.getState();
  const portal = retailerPortalCode || tenantCode;
  if (!accessToken || !user?.id || !user.tenant_id || !user.tenant_schema || !portal || !target) return null;
  // The current DTO has no retailer binding id. Account + tenant + supplier
  // portal is the available context; the backend resolves its live binding.
  return JSON.stringify([user.id, user.tenant_id, user.tenant_schema, portal, kind, target]);
}
export function ownsOperation(kind: OperationKind, target: string, scope: string | null, generation: number): boolean {
  const state = useAuthStore.getState();
  return scope !== null && scope === operationScope(kind, target) && generation === state.sessionGeneration
    && can(state.user, kind === 'declare' ? CLIENT_PERMISSIONS.PAYMENTS_DECLARE : CLIENT_PERMISSIONS.ORDERS_CREATE);
}
export const pendingStorageKey = (scope: string) => `mpango-pending:v1:${scope}`;
const object = (v: unknown): v is Record<string, unknown> => Boolean(v) && typeof v === 'object' && !Array.isArray(v);
const text = (v: unknown): v is string => typeof v === 'string' && v.trim().length > 0;
const keys = (v: Record<string, unknown>, allowed: string[]) => Object.keys(v).every(k => allowed.includes(k));
const decimal = (v: unknown): v is string => typeof v === 'string' && /^\d+(\.\d+)?$/.test(v);
const uuid = (v: unknown): v is string => typeof v === 'string' && /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(v);
const currency = (v: unknown) => v === 'KES' || v === 'UGX';
function validQuote(v: unknown): v is ServerQuote {
  return object(v) && keys(v, ['quote_token','currency','country','total','expires_at','lines'])
    && text(v.quote_token) && ((v.currency === 'KES' && v.country === 'KE') || (v.currency === 'UGX' && v.country === 'UG'))
    && decimal(v.total) && typeof v.expires_at === 'number' && Number.isFinite(v.expires_at)
    && Array.isArray(v.lines) && v.lines.length > 0 && v.lines.every(l => object(l)
      && keys(l, ['sku_id','sku_code','product_name','quantity','unit','package_quantity','display_label','unit_price','subtotal','revision','source'])
      && ['sku_id','sku_code','product_name','unit','display_label','source'].every(k => text(l[k]))
      && typeof l.quantity === 'number' && Number.isSafeInteger(l.quantity) && l.quantity > 0
      && decimal(l.package_quantity) && decimal(l.unit_price) && decimal(l.subtotal)
      && typeof l.revision === 'number' && Number.isSafeInteger(l.revision) && l.revision >= 0);
}
function valid(v: unknown, scope: string, kind: OperationKind): v is PendingOperation {
  if (!object(v) || v.version !== 1 || v.scope !== scope || v.kind !== kind || !uuid(v.key) || !object(v.body)) return false;
  const b = v.body;
  if (kind === 'declare') return keys(v, ['version','scope','kind','key','body','currency'])
    && (currency(v.currency) || v.currency === null)
    && keys(b, ['declared_amount','method','transfer_reference']) && decimal(b.declared_amount)
    && (b.method === 'cash' || b.method === 'transfer')
    && (b.transfer_reference === undefined || b.transfer_reference === null || typeof b.transfer_reference === 'string');
  return keys(v, ['version','scope','kind','key','body','quote']) && validQuote(v.quote)
    && keys(b, ['items','notes','quote_token']) && b.quote_token === v.quote.quote_token
    && (b.notes === undefined || typeof b.notes === 'string') && Array.isArray(b.items) && b.items.length > 0
    && b.items.every(i => object(i) && keys(i, ['sellable_unit_id','sku_code','quantity'])
      && text(i.sellable_unit_id) && (i.sku_code === undefined || text(i.sku_code))
      && typeof i.quantity === 'number' && Number.isSafeInteger(i.quantity) && i.quantity > 0);
}
export const retentionError = 'The original request cannot be safely retained or read in this browser. Do not submit another copy. Reopen this tab or contact support to check the result.';
export function readPending(scope: string | null, kind: OperationKind): { value: PendingOperation | null; error: string } {
  if (!scope) return { value: null, error: 'Sign in to the correct supplier portal before continuing.' };
  try {
    const raw = sessionStorage.getItem(pendingStorageKey(scope));
    if (raw === null) return { value: null, error: '' };
    const value: unknown = JSON.parse(raw);
    if (!valid(value, scope, kind)) throw new Error('Invalid retained request');
    return { value, error: '' };
  } catch { return { value: null, error: retentionError }; }
}
export function savePending(value: PendingOperation): void {
  // Serialize a snapshot so subsequent editor changes cannot mutate the body.
  const raw = JSON.stringify(value);
  if (!valid(JSON.parse(raw), value.scope, value.kind)) throw new Error('Invalid request');
  const key = pendingStorageKey(value.scope);
  const existing = sessionStorage.getItem(key);
  if (existing !== null && existing !== raw) throw new Error('An original request already exists');
  sessionStorage.setItem(key, raw);
  if (sessionStorage.getItem(key) !== raw) throw new Error('Request was not retained');
}
export function clearPending(value: PendingOperation): void {
  const key = pendingStorageKey(value.scope);
  // Never erase a different operation that acquired this slot.
  const raw = sessionStorage.getItem(key);
  if (raw !== null && raw !== JSON.stringify(value)) throw new Error('Request changed');
  sessionStorage.removeItem(key);
  if (sessionStorage.getItem(key) !== null) throw new Error('Request was not cleared');
}
