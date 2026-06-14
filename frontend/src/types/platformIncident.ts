/**
 * P15 Incident Triage types.
 *
 * TypeScript mirrors of backend P15 schemas in
 * backend/api/v1/platform/p15/schemas.py.
 *
 * Contract rules (from PLATFORM_PRODUCT_P15_INCIDENT_TRIAGE_CONTRACT.md):
 *   - unknown != healthy. Display unknown as gray, never green.
 *   - null != 0. Display null counts as "N/A", never "0".
 *   - unavailable_reason / degraded_reason are always surfaced to the operator.
 */

// -- Enums --

export type IncidentCategory =
  | 'database'
  | 'system'
  | 'api'
  | 'tenant_health'
  | 'support_issue';

export type IncidentSeverity =
  | 'info'
  | 'warning'
  | 'degraded'
  | 'unhealthy'
  | 'unknown';

export type IncidentOwner = 'support' | 'engineering' | 'dba' | 'platform';
export type IncidentConfidence = 'low' | 'medium' | 'high';

export type OpsSourceStatus = 'available' | 'unavailable' | 'unknown';
export type HealthStatus = 'healthy' | 'degraded' | 'unhealthy' | 'unknown';

// -- DatabaseHealth (mirror of P13/P14 DatabaseHealth used by the snapshot) --

export interface DatabaseHealth {
  status: HealthStatus;
  connection_pool_active: number | null;
  connection_pool_max: number | null;
  connection_pool_idle: number | null;
  latency_ms: number | null;
}

// -- 4.1 IncidentSignal --

export interface IncidentSignal {
  signal_id: string;
  kind: IncidentCategory;
  severity: IncidentSeverity;
  source_ref: string;
  observed_value: string | number | null;
  source_status: OpsSourceStatus;
  unavailable_reason: string | null;
  degraded_reason: string | null;
  observed_at: string;
}

// -- 4.2 IncidentClassification --

export interface IncidentClassification {
  category: IncidentCategory;
  confidence: IncidentConfidence;
  suggested_owner: IncidentOwner;
  notes: string | null;
}

// -- 4.3 IncidentRunbookHint --

export interface IncidentRunbookHint {
  category: IncidentCategory;
  checklist: string[];
  do_not: string[];
  handoff_to: IncidentOwner;
}

// -- 4.4 IncidentTriageSnapshot --

export interface IncidentTriageSnapshot {
  snapshot_id: string;
  generated_at: string;
  overall_status: HealthStatus;
  signals: IncidentSignal[];
  database_probe: DatabaseHealth | null;
  system_health_overall: HealthStatus | null;
  tenant_health_sample_count: number | null;
  tenant_health_unhealthy_count: number | null;
  degraded_reason: string | null;
  unavailable_reason: string | null;
  graceful_degraded: boolean;
}

// -- 4.5 IncidentHandoffSummary --

export interface IncidentHandoffSummary {
  summary_id: string;
  created_at: string;
  classification: IncidentClassification;
  signals: IncidentSignal[];
  runbook_hint: IncidentRunbookHint | null;
  redacted: boolean;
  sensitive_keys_dropped: number;
}

// -- Helpers (reuse P13/P14 semantics) --

/**
 * Display a nullable ops count. null -> "N/A", number -> string.
 * Never displays "0" for null.
 */
export function displayIncidentCount(value: number | null): string {
  return value === null ? 'N/A' : String(value);
}

/**
 * Human-readable label for a health status.
 * unknown -> "Unknown" (gray, never green).
 */
export function healthStatusLabel(status: HealthStatus | null | undefined): string {
  switch (status) {
    case 'healthy': return 'Healthy';
    case 'degraded': return 'Degraded';
    case 'unhealthy': return 'Unhealthy';
    case 'unknown': return 'Unknown';
    default: return 'Unknown';
  }
}

/** True when a status indicates no real/measured data. */
export function isStatusUnknown(status: HealthStatus | null | undefined): boolean {
  return status === 'unknown' || status === null || status === undefined;
}
