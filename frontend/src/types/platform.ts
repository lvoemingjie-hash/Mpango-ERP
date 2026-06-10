/**
 * Platform Admin Cockpit types — matches PLATFORM_PRODUCT_CONTRACTS.md P10-A-R1 exactly.
 *
 * These types are the TypeScript mirror of the backend P10 data contracts.
 * Every field, nullable behavior, and enum value must match the contract.
 */

// -- Enums --

export type TenantStatus = 'draft' | 'active' | 'paused' | 'suspended' | 'archived' | 'unknown';
export type HealthStatus = 'healthy' | 'degraded' | 'unhealthy' | 'unknown';
export type AuditScope = 'global' | 'tenant' | 'system' | 'support';
export type AuditResult = 'allowed' | 'denied' | 'failed' | 'completed';
export type ActorRole = 'super_admin' | 'support_operator' | 'engineering_operator';
export type SchemaStatus = 'exists' | 'unreachable' | 'migration_misaligned' | 'missing' | 'unknown';
export type ComponentStatus = 'healthy' | 'degraded' | 'down' | 'unknown';

// -- Contracts --

export interface PlatformTenantSummary {
  tenant_id: string | null;
  tenant_name: string | null;
  tenant_schema: string | null;
  status: TenantStatus;
  tier: string | null;
  created_at: string | null;
  last_activity_at: string | null;
  user_count: number | null;
  health_status: HealthStatus;
  recent_error_count: number | null;
  support_mode_active: boolean;
}

export interface PlatformTenantSummaryList {
  items: PlatformTenantSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface ErrorSummary {
  error_class: string;
  count: number;
  correlation_ids: string[];
}

export interface SlowRoute {
  route: string;
  latency_bucket_ms: number;
  count: number;
}

export interface FailedJob {
  job_class: string;
  count: number;
}

export interface ActivityCounters {
  orders: number;
  inventory_changes: number;
  invoices: number;
  payments: number;
  sync_jobs: number;
}

export interface PlatformTenantHealth {
  tenant_id: string | null;
  tenant_schema: string | null;
  health_status: HealthStatus;
  schema_status: SchemaStatus | null;
  last_login_at: string | null;
  activity_counters: ActivityCounters | null;
  recent_errors: ErrorSummary[] | null;
  slow_routes: SlowRoute[] | null;
  failed_jobs: FailedJob[] | null;
  last_health_check_at: string | null;
}

export interface DatabaseConnections {
  active: number;
  idle: number;
  max: number;
  saturation_pct: number;
}

export interface PlatformSystemHealth {
  overall_status: HealthStatus;
  api_status: ComponentStatus | null;
  database_status: ComponentStatus | null;
  database_connections: DatabaseConnections | null;
  queue_status: ComponentStatus | null;
  cpu_status: ComponentStatus | null;
  memory_status: ComponentStatus | null;
  disk_status: ComponentStatus | null;
  error_rate: number | null;
  slow_request_count: number | null;
  generated_at: string;
}

export interface PlatformAuditEvent {
  event_id: string;
  actor_id: string | null;
  actor_role: ActorRole | null;
  tenant_id: string | null;
  scope: AuditScope;
  action: string;
  reason: string | null;
  result: AuditResult;
  metadata_redacted: Record<string, unknown> | null;
  correlation_id: string | null;
  created_at: string;
}

export interface PlatformAuditEventList {
  items: PlatformAuditEvent[];
  total: number;
  limit: number;
  offset: number;
}

// -- Helpers --

/**
 * Display a nullable count field as a human-readable string.
 * null → "N/A", number → string representation.
 */
export function displayCount(value: number | null): string {
  return value === null ? 'N/A' : String(value);
}

/**
 * Display a nullable timestamp as a human-readable string.
 * null → "N/A", string → localized date/time.
 */
export function displayTimestamp(value: string | null): string {
  if (value === null) return 'N/A';
  try {
    const d = new Date(value);
    if (isNaN(d.getTime())) return 'N/A';
    return d.toLocaleString();
  } catch {
    return 'N/A';
  }
}
