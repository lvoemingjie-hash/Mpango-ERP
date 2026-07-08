/**
 * P17 Platform Registry types.
 *
 * TypeScript mirrors of the backend P17 schemas in
 * backend/api/v1/platform/p17/schemas.py, aligned to
 * docs/ai/PLATFORM_PRODUCT_P17_REGISTRY_LIFECYCLE_CONTRACT.md.
 *
 * Contract display rules (from the P17-A contract):
 *   - unknown != healthy / active / success. Render 'unknown' as gray, never green.
 *   - null != 0 / false. Render null counts as "N/A", never "0".
 *   - unavailable_reason / flags_unavailable_reason are always surfaced.
 *   - failure_reason_redacted is an allowlisted reason code only (no secrets).
 */

// -- Enums --

export type RegistrySourceStatus = 'available' | 'unavailable' | 'unknown';

export type LifecycleState =
  | 'draft'
  | 'provisioning'
  | 'active'
  | 'under_review'
  | 'paused'
  | 'suspended'
  | 'archived'
  | 'failed_provisioning'
  | 'unknown';

export type ActorRole = 'super_admin' | 'support_operator' | 'engineering_operator';
export type AuditResult = 'allowed' | 'denied' | 'failed' | 'completed';

export type SchemaStatus =
  | 'exists' | 'missing' | 'unreachable' | 'migration_misaligned' | 'unknown';
export type SeedStatus = 'seeded' | 'partial' | 'missing' | 'unknown';
export type AdminUserStatus = 'created' | 'missing' | 'unknown';
export type FeatureConfigStatus = 'applied' | 'partial' | 'missing' | 'unknown';
export type LastBackupStatus =
  | 'success' | 'partial' | 'failed' | 'in_progress' | 'stale' | 'unknown';
export type RestoreTestStatus = 'passed' | 'failed' | 'stale' | 'unknown';

// -- 4.2 TenantLifecycleState --

export interface TenantLifecycleState {
  state: LifecycleState;
  previous_state: LifecycleState | null;
  entered_at: string | null;
  last_actor_id: string | null;
  last_actor_role: ActorRole | null;
  transition_reason: string | null;
  last_audit_event_id: string | null;
  state_source_status: RegistrySourceStatus;
}

// -- 4.3 TenantOperationalFlags --

export interface TenantOperationalFlags {
  support_mode_active: boolean;
  incident_active: boolean;
  login_paused: boolean;
  writes_paused: boolean;
  billing_hold: boolean;
  backup_attention_required: boolean;
  migration_attention_required: boolean;
  quota_attention_required: boolean;
  flags_source_status: RegistrySourceStatus;
  flags_updated_at: string | null;
  flags_unavailable_reason: string | null;
}

// -- 4.4 TenantProvisioningStatus --

export interface TenantProvisioningStatus {
  schema_status: SchemaStatus | null;
  seed_status: SeedStatus | null;
  admin_user_status: AdminUserStatus | null;
  feature_config_status: FeatureConfigStatus | null;
  last_provisioning_check_at: string | null;
  failure_reason_redacted: string | null;
  provisioning_source_status: RegistrySourceStatus;
}

// -- 4.5 TenantBackupStatus --

export interface TenantBackupStatus {
  last_backup_at: string | null;
  last_backup_status: LastBackupStatus | null;
  last_restore_test_at: string | null;
  restore_test_status: RestoreTestStatus | null;
  export_available: boolean | null;
  retention_policy: string | null;
  failure_reason_redacted: string | null;
  backup_source_status: RegistrySourceStatus;
  last_status_check_at: string | null;
}

// -- 4.1 PlatformTenantRegistry (root) --

export interface PlatformTenantRegistry {
  tenant_id: string;
  tenant_name: string | null;
  tenant_schema: string | null;
  tier: string | null;
  created_at: string | null;
  lifecycle_state: TenantLifecycleState;
  operational_flags: TenantOperationalFlags;
  provisioning_status: TenantProvisioningStatus | null;
  backup_status: TenantBackupStatus | null;
  last_registry_update_at: string | null;
  registry_source_status: RegistrySourceStatus;
  unavailable_reason: string | null;
}

export interface PlatformTenantRegistryList {
  items: PlatformTenantRegistry[];
  total: number;
  limit: number;
  offset: number;
  registry_source_status: RegistrySourceStatus;
  unavailable_reason: string | null;
}

// -- Display helpers (unknown != healthy; null != 0) --

/**
 * Display a nullable count. null -> "N/A", number -> string.
 * Never displays "0" for null (null != 0).
 */
export function displayRegistryCount(value: number | null): string {
  return value === null ? 'N/A' : String(value);
}

/**
 * Human-readable label for a lifecycle state.
 * 'unknown' is labeled "Unknown" and is never treated as active/healthy.
 */
export function lifecycleStateLabel(state: LifecycleState | null | undefined): string {
  switch (state) {
    case 'draft': return 'Draft';
    case 'provisioning': return 'Provisioning';
    case 'active': return 'Active';
    case 'under_review': return 'Under review';
    case 'paused': return 'Paused';
    case 'suspended': return 'Suspended';
    case 'archived': return 'Archived';
    case 'failed_provisioning': return 'Failed provisioning';
    case 'unknown': return 'Unknown';
    default: return 'Unknown';
  }
}

/** True when a state is unknown / cannot be confirmed as operational. */
export function isLifecycleUnknown(state: LifecycleState | null | undefined): boolean {
  return state == null || state === 'unknown';
}

/**
 * Visual tone for a lifecycle state badge. 'active' is green ONLY;
 * failed/suspended/paused/under_review are amber/red; unknown is gray.
 * Never green for an unknown or degraded state.
 */
export function lifecycleStateTone(
  state: LifecycleState | null | undefined
): 'green' | 'amber' | 'red' | 'gray' {
  switch (state) {
    case 'active': return 'green';
    case 'under_review':
    case 'paused':
      return 'amber';
    case 'suspended':
    case 'failed_provisioning':
      return 'red';
    case 'draft':
    case 'provisioning':
    case 'archived':
      return 'gray';
    case 'unknown':
    default:
      return 'gray';
  }
}

/**
 * Visual tone for a source_status. 'available' is green;
 * 'unavailable'/'unknown' are gray (never green).
 */
export function sourceStatusTone(
  status: RegistrySourceStatus | null | undefined
): 'green' | 'gray' {
  return status === 'available' ? 'green' : 'gray';
}

/** Render a nullable summary field: null -> "N/A", present -> the value. */
export function displayNullable(value: string | null | undefined): string {
  return value == null || value === '' ? 'N/A' : value;
}

/** Render a nullable boolean flag (e.g. export_available): null -> "N/A". */
export function displayNullableBool(value: boolean | null | undefined): string {
  return value == null ? 'N/A' : value ? 'Yes' : 'No';
}
