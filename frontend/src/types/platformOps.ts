/**
 * P13 Operations Observability Cockpit types.
 *
 * TypeScript mirrors of backend P13 schemas in
 * backend/api/v1/platform/p13/schemas.py.
 *
 * Key contract rules:
 *   - source_status "available": total fields are integer >= 0, never null.
 *   - source_status "unavailable"/"unknown": total fields are null, never 0.
 *   - null != 0.  Display null as "N/A" or "Data unavailable", never "0".
 *   - Unknown != healthy.  Unknown is gray, distinct from green.
 */

// -- Enums --

export type OpsSourceStatus = 'available' | 'unavailable' | 'unknown';

// -- ErrorRateSummary sub-types --

export interface ErrorClassBreakdown {
  error_class: string;
  count: number;
  percentage: number;
  sample_correlation_ids: string[];
}

export interface RouteErrorBreakdown {
  route: string;
  error_count: number;
  latency_bucket_ms: number | null;
  sample_correlation_ids: string[];
}

export interface TenantErrorBreakdown {
  tenant_id: string;
  tenant_name: string | null;
  error_count: number;
  top_error_class: string | null;
}

export interface ErrorRateSummary {
  source_status: OpsSourceStatus;
  window_minutes: number;
  total_errors: number | null;
  error_classes: ErrorClassBreakdown[];
  top_routes: RouteErrorBreakdown[];
  top_tenants: TenantErrorBreakdown[] | null;
  /**
   * P14: human-readable reason when source_status is unavailable/unknown.
   * null/undefined when the source is available. Lets the UI state *why*.
   */
  unavailable_reason?: string | null;
  generated_at: string;
}

// -- SlowRouteSummary sub-types --

export interface SlowRouteEntry {
  route: string;
  request_count: number;
  p50_ms: number | null;
  p95_ms: number | null;
  p99_ms: number | null;
  sample_correlation_ids: string[];
}

export interface SlowRouteSummary {
  source_status: OpsSourceStatus;
  window_minutes: number;
  threshold_ms: number;
  total_slow_requests: number | null;
  routes: SlowRouteEntry[];
  /** P14: reason when source_status is unavailable/unknown. null/undefined when available. */
  unavailable_reason?: string | null;
  generated_at: string;
}

// -- ResourceHealthSummary sub-types --

export interface DatabaseHealth {
  status: 'healthy' | 'degraded' | 'unhealthy' | 'unknown';
  connection_pool_active: number | null;
  connection_pool_max: number | null;
  connection_pool_idle: number | null;
  latency_ms: number | null;
}

export interface QueueHealth {
  status: 'healthy' | 'degraded' | 'unhealthy' | 'unknown';
  depth: number | null;
  worker_count: number | null;
  oldest_pending_age_s: number | null;
}

export interface ComponentHealth {
  status: 'healthy' | 'degraded' | 'unhealthy' | 'unknown';
  usage_percent: number | null;
  detail: string | null;
}

export interface ResourceHealthSummary {
  database: DatabaseHealth;
  queue: QueueHealth | null;
  memory: ComponentHealth | null;
  cpu: ComponentHealth | null;
  disk: ComponentHealth | null;
  generated_at: string;
}

// -- NoisyNeighborSummary sub-types --

export interface NoisyNeighborEntry {
  tenant_id: string;
  tenant_name: string | null;
  error_count: number;
  slow_route_count: number;
  impact_score: number;
  top_error_class: string | null;
  top_slow_route: string | null;
}

export interface NoisyNeighborSummary {
  window_minutes: number;
  tenants: NoisyNeighborEntry[];
  /** P14: reason when the source is unavailable. null/undefined when populated. */
  unavailable_reason?: string | null;
  generated_at: string;
}

// -- Helpers --

/**
 * Display a nullable ops count.  null -> "N/A", number -> string.
 * Never displays "0" for null.
 */
export function displayOpsCount(value: number | null): string {
  return value === null ? 'N/A' : String(value);
}

/**
 * Human-readable label for source_status.
 * unavailable -> "Data unavailable"
 * unknown -> "Not instrumented"
 * available -> "Live data"
 */
export function sourceStatusLabel(status: OpsSourceStatus): string {
  switch (status) {
    case 'available': return 'Live data';
    case 'unavailable': return 'Data unavailable';
    case 'unknown': return 'Not instrumented';
  }
}

/**
 * True when source_status indicates no real data.
 */
export function isSourceUnavailable(status: OpsSourceStatus): boolean {
  return status === 'unavailable' || status === 'unknown';
}
