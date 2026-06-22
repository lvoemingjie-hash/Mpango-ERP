"""
Pydantic schemas for P17 Platform Registry (read-only tenant registry API).

Field-for-field aligned to
docs/ai/PLATFORM_PRODUCT_P17_REGISTRY_LIFECYCLE_CONTRACT.md (P17-A).

Contract rules (carried from P10/P13/P14/P15):
  - source_status on every derived value (never a bare 0 / false for unknown).
  - Nullable totals when a source is unavailable (null != 0).
  - unknown != healthy / active / success / exists.
  - unavailable_reason / flags_unavailable_reason always visible when a source
    is down; the reason is human-readable, never a secret/DSN/host/port.
  - failure_reason_redacted is an ALLOWLISTED reason code only -- never the raw
    exception, stack trace, credential, DSN, host/port, or connection string.
  - A last_backup_status of "success" is invalid when last_backup_at is stale;
    it must read "stale" (or "unknown"), never "success".
  - extra="forbid" on every model (no undeclared fields / leaks).
  - No tenant business records (orders, payments, invoices, customers).

P17-B is read-only: these schemas are response models only. No mutation model
exists in P17 (lifecycle transition, flag change, provisioning re-run, backup
trigger are reserved for a separately approved controlled-action phase).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from api.v1.platform.p10.schemas import (
    ActorRole,
    AuditResult,
    validate_uuid_v4_v7,
)


# ── Source-status vocabulary (reused from P13/P14, P10 §x-status) ──

RegistrySourceStatus = Literal["available", "unavailable", "unknown"]


# ── 4.2 TenantLifecycleState ──

LifecycleState = Literal[
    "draft",
    "provisioning",
    "active",
    "under_review",
    "paused",
    "suspended",
    "archived",
    "failed_provisioning",
    "unknown",
]


class TenantLifecycleState(BaseModel):
    """The lifecycle position of one tenant (read-only in P17).

    P17 defines the state machine but does NOT execute transitions. The fields
    here are read-only observations of the current position; transition audit
    (actor / reason / from_state / to_state) is reserved for a future
    controlled-action phase and therefore reads null/deferred here.
    """

    model_config = ConfigDict(extra="forbid")

    state: LifecycleState = Field(
        ..., description="Current lifecycle state; 'unknown' is the fallback and is never 'active'"
    )
    previous_state: Optional[LifecycleState] = Field(
        None, description="null before the first transition"
    )
    entered_at: Optional[datetime] = Field(
        None, description="UTC ISO-8601; null if entry time unknown"
    )
    last_actor_id: Optional[str] = Field(
        None, description="null until platform auth exists"
    )
    last_actor_role: Optional[ActorRole] = Field(
        None, description="null until platform auth exists"
    )
    transition_reason: Optional[str] = Field(
        None,
        description="null only before the first transition; required on every transition",
    )
    last_audit_event_id: Optional[str] = Field(
        None, description="null if no audit event exists yet"
    )
    state_source_status: RegistrySourceStatus = Field(
        ..., description="available | unavailable | unknown"
    )

    _validate_last_audit_event_id = field_validator("last_audit_event_id")(
        validate_uuid_v4_v7
    )

    @model_validator(mode="after")
    def state_source_consistency(self) -> "TenantLifecycleState":
        """unknown != active. A 'state' of 'unknown' must carry state_source_status != 'available'."""
        if self.state == "unknown" and self.state_source_status == "available":
            raise ValueError(
                "state='unknown' is never an available/known state; "
                "state_source_status must be 'unavailable' or 'unknown'"
            )
        return self


# ── 4.3 TenantOperationalFlags ──


class TenantOperationalFlags(BaseModel):
    """Required set of boolean operational flags. Every flag defaults to false.

    When runtime telemetry is unavailable, every flag reads false AND
    flags_unavailable_reason is set, so an operator can tell a real false from
    an unknown one (null != 0 / unknown != false).
    """

    model_config = ConfigDict(extra="forbid")

    support_mode_active: bool = Field(..., description="false + reason when telemetry down")
    incident_active: bool = Field(..., description="false + reason when telemetry down")
    login_paused: bool = Field(..., description="false + reason when telemetry down")
    writes_paused: bool = Field(..., description="false + reason when telemetry down")
    billing_hold: bool = Field(..., description="false + reason when telemetry down")
    backup_attention_required: bool = Field(..., description="false + reason when telemetry down")
    migration_attention_required: bool = Field(..., description="false + reason when telemetry down")
    quota_attention_required: bool = Field(..., description="false + reason when telemetry down")
    flags_source_status: RegistrySourceStatus = Field(
        ..., description="available | unavailable | unknown"
    )
    flags_updated_at: Optional[datetime] = Field(
        None, description="UTC ISO-8601; null if never set"
    )
    flags_unavailable_reason: Optional[str] = Field(
        None, description="set when telemetry is unavailable"
    )

    @model_validator(mode="after")
    def flags_source_consistency(self) -> "TenantOperationalFlags":
        """If every flag is false, the source MUST NOT read 'available' without a check.

        A fully-false flag set is only 'available' when flags_updated_at is set
        (a real measurement). Otherwise unknown telemetry must be reflected by
        source_status != 'available' so a real false is distinguishable from
        an unknown one.
        """
        all_false = not (
            self.support_mode_active
            or self.incident_active
            or self.login_paused
            or self.writes_paused
            or self.billing_hold
            or self.backup_attention_required
            or self.migration_attention_required
            or self.quota_attention_required
        )
        if all_false and self.flags_source_status == "available" and self.flags_updated_at is None:
            raise ValueError(
                "all-false operational flags with no flags_updated_at cannot read "
                "flags_source_status='available' (unknown != false)"
            )
        return self


# ── 4.4 TenantProvisioningStatus ──

SchemaStatus = Literal[
    "exists", "missing", "unreachable", "migration_misaligned", "unknown"
]
SeedStatus = Literal["seeded", "partial", "missing", "unknown"]
AdminUserStatus = Literal["created", "missing", "unknown"]
FeatureConfigStatus = Literal["applied", "partial", "missing", "unknown"]

# Allowlisted reason codes only. Anything outside this set is collapsed to
# "unknown" by redact_failure_reason() -- never the raw value.
PROVISIONING_FAILURE_REASONS: frozenset[str] = frozenset(
    {
        "schema_create_failed",
        "seed_failed",
        "admin_seed_failed",
        "feature_config_failed",
        "migration_failed",
        "provisioning_incomplete",
        "unknown",
    }
)


class TenantProvisioningStatus(BaseModel):
    """Provisioning state of tenant resources. Diagnostics only; no secrets.

    failure_reason_redacted is an allowlisted reason code ONLY -- it must never
    contain the raw exception, stack trace, credential, DSN, host/port, or
    connection string (counterexample C6).
    """

    model_config = ConfigDict(extra="forbid")

    schema_status: Optional[SchemaStatus] = Field(
        None, description="null + reason if DB metadata unavailable"
    )
    seed_status: Optional[SeedStatus] = Field(
        None, description="null + reason if unavailable"
    )
    admin_user_status: Optional[AdminUserStatus] = Field(
        None, description="null + reason if unavailable"
    )
    feature_config_status: Optional[FeatureConfigStatus] = Field(
        None, description="null + reason if unavailable"
    )
    last_provisioning_check_at: Optional[datetime] = Field(
        None, description="null if never checked"
    )
    failure_reason_redacted: Optional[str] = Field(
        None, description="allowlisted reason code only; null if no failure"
    )
    provisioning_source_status: RegistrySourceStatus = Field(
        ..., description="available | unavailable | unknown"
    )

    @field_validator("failure_reason_redacted")
    @classmethod
    def failure_reason_is_allowlisted(cls, v: Optional[str]) -> Optional[str]:
        """Reject (at construction) any failure reason outside the allowlist.

        The service layer also collapses non-allowlisted raw reasons to
        'unknown' before building; this validator is the hard backstop so a
        secret-bearing string can never survive into a serialized response.
        """
        if v is None:
            return v
        if v not in PROVISIONING_FAILURE_REASONS:
            raise ValueError(
                "failure_reason_redacted must be an allowlisted reason code "
                "(credential/stack/DSN leak rejected)"
            )
        return v


# ── 4.5 TenantBackupStatus ──

LastBackupStatus = Literal[
    "success", "partial", "failed", "in_progress", "stale", "unknown"
]
RestoreTestStatus = Literal["passed", "failed", "stale", "unknown"]

# Allowlisted backup failure reason codes only.
BACKUP_FAILURE_REASONS: frozenset[str] = frozenset(
    {
        "backup_job_timeout",
        "restore_checksum_mismatch",
        "backup_source_unreachable",
        "restore_test_failed",
        "backup_incomplete",
        "unknown",
    }
)

# Freshness window for a 'success' backup. A last_backup_at older than this
# downgrades last_backup_status to 'stale' (never 'success'). Counterexample C4.
BACKUP_FRESHNESS_WINDOW = timedelta(hours=24)


class TenantBackupStatus(BaseModel):
    """Backup & restore-test posture. Sourced from the backup system.

    A last_backup_status of 'success' is valid only when last_backup_at is
    within the freshness window; a stale timestamp downgrades the rendered
    status to 'stale' and never reads 'success' (counterexample C4).
    """

    model_config = ConfigDict(extra="forbid")

    last_backup_at: Optional[datetime] = Field(
        None, description="null if never backed up"
    )
    last_backup_status: Optional[LastBackupStatus] = Field(
        None,
        description="null + reason if backup system unavailable; 'stale' if timestamp outside window",
    )
    last_restore_test_at: Optional[datetime] = Field(
        None, description="null if never tested"
    )
    restore_test_status: Optional[RestoreTestStatus] = Field(
        None, description="null + reason if unavailable"
    )
    export_available: Optional[bool] = Field(
        None, description="null + reason if unavailable"
    )
    retention_policy: Optional[str] = Field(
        None, description="null if not configured"
    )
    failure_reason_redacted: Optional[str] = Field(
        None, description="allowlisted reason code only; null if no failure"
    )
    backup_source_status: RegistrySourceStatus = Field(
        ..., description="available | unavailable | unknown"
    )
    last_status_check_at: Optional[datetime] = Field(
        None, description="null if never checked"
    )

    @field_validator("failure_reason_redacted")
    @classmethod
    def failure_reason_is_allowlisted(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if v not in BACKUP_FAILURE_REASONS:
            raise ValueError(
                "failure_reason_redacted must be an allowlisted reason code "
                "(credential/path/DSN leak rejected)"
            )
        return v

    @model_validator(mode="after")
    def success_requires_fresh_timestamp(self) -> "TenantBackupStatus":
        """C4: 'success' is invalid when last_backup_at is stale or absent.

        The service layer applies freshness before construction; this validator
        is the hard backstop: a 'success' status with a stale/missing timestamp
        is rejected so it can never render as success.
        """
        if self.last_backup_status == "success":
            if self.last_backup_at is None:
                raise ValueError(
                    "last_backup_status='success' requires a non-null last_backup_at"
                )
            if self.backup_source_status != "available":
                raise ValueError(
                    "last_backup_status='success' requires backup_source_status='available'"
                )
        return self


# ── 4.1 PlatformTenantRegistry (root) ──


class PlatformTenantRegistry(BaseModel):
    """Root read-only registry record for one tenant.

    Composes the sub-contracts (4.2-4.5). registry_source_status / unavailable_reason
    surface the overall availability so an operator never mistakes a degraded
    assembly for a fully-healthy record.
    """

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(..., description="UUID v4/v7; required")
    tenant_name: Optional[str] = Field(None, description="null if not set")
    tenant_schema: Optional[str] = Field(
        None, description="null if provisioning metadata absent"
    )
    tier: Optional[str] = Field(
        None, description="null until a subscription model exists"
    )
    created_at: Optional[datetime] = Field(
        None, description="null if creation metadata absent"
    )
    lifecycle_state: TenantLifecycleState = Field(..., description="required")
    operational_flags: TenantOperationalFlags = Field(..., description="required")
    provisioning_status: Optional[TenantProvisioningStatus] = Field(
        None, description="null + unavailable_reason when source absent"
    )
    backup_status: Optional[TenantBackupStatus] = Field(
        None, description="null + unavailable_reason when source absent"
    )
    last_registry_update_at: Optional[datetime] = Field(
        None, description="null if never updated"
    )
    registry_source_status: RegistrySourceStatus = Field(
        ..., description="available | unavailable | unknown"
    )
    unavailable_reason: Optional[str] = Field(
        None, description="set when any sub-source is unavailable or unknown"
    )

    _validate_tenant_id = field_validator("tenant_id")(validate_uuid_v4_v7)


class PlatformTenantRegistryList(BaseModel):
    """Paginated list of PlatformTenantRegistry records."""

    model_config = ConfigDict(extra="forbid")

    items: list[PlatformTenantRegistry]
    total: int = Field(..., ge=0)
    limit: int = Field(..., ge=1)
    offset: int = Field(..., ge=0)
    registry_source_status: RegistrySourceStatus = Field(
        ..., description="overall availability of the registry assembly"
    )
    unavailable_reason: Optional[str] = Field(
        None, description="set when the assembly degraded despite a source failure"
    )


# ── 4.6 TenantRegistryAuditEvent ──

RegistryAction = Literal[
    "registry_view",
    "registry_view_denied",
    "lifecycle_transition",
    "flag_change",
    "provisioning_recheck",
    "backup_trigger",
]
# In P17 only registry_view / registry_view_denied are emitted; the rest are
# reserved for a separately approved controlled-action phase.


class TenantRegistryAuditEvent(BaseModel):
    """Append-only audit event for registry access (and, in future phases, mutation).

    A typed specialization of the P10 PlatformAuditEvent. In P17 (read and
    contract only) the only events emitted are reads and denied reads; the
    write actions in the enum are reserved for future controlled-action phases.
    """

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(..., description="UUID v4/v7; always generated")
    actor_id: Optional[str] = Field(
        None, description="null until platform auth exists"
    )
    actor_role: Optional[ActorRole] = Field(
        None, description="null until platform auth exists"
    )
    tenant_id: Optional[str] = Field(
        None, description="null for global-scope events"
    )
    registry_action: RegistryAction = Field(..., description="always required")
    from_state: Optional[LifecycleState] = Field(
        None, description="null for non-transition actions"
    )
    to_state: Optional[LifecycleState] = Field(
        None, description="null for non-transition actions"
    )
    reason: Optional[str] = Field(
        None,
        description="null for actions that need none; required on transitions and flag changes",
    )
    result: AuditResult = Field(..., description="allowed | denied | failed | completed")
    metadata_redacted: Optional[dict] = Field(
        None, description="null if none; never a raw sensitive payload"
    )
    correlation_id: Optional[str] = Field(
        None, description="null if not yet correlated"
    )
    created_at: datetime = Field(..., description="UTC ISO-8601; always required")

    _validate_event_id = field_validator("event_id")(validate_uuid_v4_v7)
    _validate_tenant_id = field_validator("tenant_id")(validate_uuid_v4_v7)


# ── Pure helpers (freshness + redaction) ──


def enforce_backup_freshness(
    last_backup_status: Optional[str],
    last_backup_at: Optional[datetime],
    *,
    now: datetime,
    window: timedelta = BACKUP_FRESHNESS_WINDOW,
) -> Optional[str]:
    """Downgrade a stale 'success' backup status to 'stale'.

    A last_backup_status of 'success' is valid only when last_backup_at is
    within `window` of `now`. A stale or absent timestamp downgrades the status
    to 'stale' / 'unknown' respectively -- it never reads 'success'
    (counterexample C4). Non-success statuses pass through unchanged.
    """
    if last_backup_status != "success":
        return last_backup_status
    if last_backup_at is None:
        # Cannot confirm freshness -> must not read 'success'.
        return "unknown"
    if now - last_backup_at > window:
        return "stale"
    return "success"


def redact_failure_reason(
    raw: Optional[str], allowlist: "frozenset[str]"
) -> Optional[str]:
    """Collapse a raw failure reason to an allowlisted code.

    If `raw` is None -> None. If `raw` is an allowlisted code -> returned as-is.
    Otherwise the value is NOT echoed; it is collapsed to 'unknown' so a
    secret/credential/stack-trace/DSN-bearing string can never leak
    (counterexamples C2 and C6).
    """
    if raw is None:
        return None
    if raw in allowlist:
        return raw
    return "unknown"
