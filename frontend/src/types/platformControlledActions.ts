/**
 * P18 Controlled Platform Actions types (request skeleton, P18-C).
 *
 * Aligned to docs/ai/PLATFORM_PRODUCT_P18_CONTROLLED_ACTIONS_CONTRACT.md (P18-A)
 * and the backend P18 schemas. These describe a REQUEST skeleton only: nothing
 * is executed, and every response carries executed === false.
 */

export type ActionClassification = 'read' | 'write' | 'write_request';

export type ControlledRequestResult =
  | 'accepted'
  | 'denied'
  | 'degraded'
  | 'duplicate'
  | 'conflict';

export type RegistrySourceStatus = 'available' | 'unavailable' | 'unknown';

export interface ControlledActionCatalogItem {
  action_type: string;
  classification: ActionClassification;
  allowed_actors: string[];
  confirmation_required: boolean;
  degraded_allowed: boolean;
  description: string;
}

export interface ControlledActionCatalog {
  items: ControlledActionCatalogItem[];
  total: number;
  contract: string;
  executed: boolean;
}

export interface ControlledActionRequestPayload {
  action_type: string;
  tenant_id?: string | null;
  reason: string;
  idempotency_key: string;
  requested_state?: string | null;
  confirm: boolean;
  correlation_id?: string | null;
  metadata?: Record<string, unknown> | null;
}

export interface ControlledActionRequestResponse {
  action_id: string | null;
  action_type: string;
  result: ControlledRequestResult;
  executed: boolean;
  dry_run: boolean;
  message: string;
  reason: string;
  idempotency_key: string;
  requested_state: string | null;
  previous_state: string | null;
  source_status: RegistrySourceStatus;
  degraded_reason: string | null;
  metadata_redacted: Record<string, unknown> | null;
  correlation_id: string | null;
  created_at: string;
}
