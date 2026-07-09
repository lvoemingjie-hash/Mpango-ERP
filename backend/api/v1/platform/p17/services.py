"""
Service layer for P17 Platform Registry (read-only tenant registry adapter).

Assembles EXISTING read-only sources only (contract section 7 field source map):
  - P10 ``list_tenant_summaries`` / tenant identity (public platform metadata):
    tenant_id, tenant_name, tenant_schema, status, created_at,
    support_mode_active. This is the registry "public platform metadata" row.
  - ``PlatformTenant`` provisioning journal (public.platform_tenants): the
    coarse provisioning lifecycle signal used to enrich the lifecycle state
    (e.g. ``failed_provisioning``) and to surface a provisioning sub-status
    where the journal is authoritative.
  - Runtime telemetry, fine provisioning diagnostics, and the backup system are
    NOT yet instrumented. Per the contract those fields read their documented
    fallback (null / unknown / false) with a visible reason -- never a
    fabricated healthy / active / success / exists value.

Design rules (from PLATFORM_PRODUCT_P17_REGISTRY_LIFECYCLE_CONTRACT.md):
  - unknown != healthy / active / success / exists. null != 0 / false.
  - Every unavailable field carries a visible reason.
  - Freshness is enforced: a stale ``success`` backup reads ``stale``, never
    ``success`` (counterexample C4).
  - ``failure_reason_redacted`` is an allowlisted reason code only (C2/C6).
  - No writes, no mutation, no tenant business records (orders / payments /
    invoices / customers), no credentials / DSN / host / port.

P17-B is read-only. It adds no new data sources and no new infrastructure.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.platform.p10.services import list_tenant_summaries
from models.platform_tenant import PlatformTenant

from .models import PlatformBackupOutcome, PlatformBackupPolicy
from .schemas import (
    BACKUP_FAILURE_REASONS,
    PlatformTenantRegistry,
    PlatformTenantRegistryList,
    RegistrySourceStatus,
    TenantBackupStatus,
    TenantLifecycleState,
    TenantOperationalFlags,
    TenantProvisioningStatus,
    enforce_backup_freshness,
    redact_failure_reason,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# -- Source loaders (best-effort; degrade to empty/None on any failure) --


async def _load_provisioning_map(
    db: AsyncSession, wholesaler_ids: list[str]
) -> dict[str, PlatformTenant]:
    """Load the platform provisioning journal for the given tenant ids.

    Returns a {wholesaler_id_str: PlatformTenant} map. On any error returns an
    empty map so the adapter degrades gracefully (provisioning reads null +
    reason), never raises to the caller, and never fabricates.

    P25-EJ: The query runs inside a SAVEPOINT (``db.begin_nested()``). If the
    query fails (e.g. table absent), the SAVEPOINT is rolled back -- only the
    nested scope, not the outer request transaction -- so the swallowed error
    does NOT poison the AsyncSession for the subsequent audit-log commit.
    """
    if not wholesaler_ids:
        return {}
    try:
        async with db.begin_nested():
            result = await db.execute(
                select(PlatformTenant).where(
                    PlatformTenant.wholesaler_id.in_(wholesaler_ids)
                )
            )
            rows = result.scalars().all()
        return {str(r.wholesaler_id): r for r in rows}
    except Exception:
        return {}


# -- Lifecycle derivation --

# P10 TenantSummary.status -> P17 lifecycle state. The P10 enum is a subset of
# the P17 enum; states P17 adds (provisioning / under_review /
# failed_provisioning) are derived from the provisioning journal when present.
_P10_STATUS_TO_LIFECYCLE: dict[str, str] = {
    "draft": "draft",
    "active": "active",
    "paused": "paused",
    "suspended": "suspended",
    "archived": "archived",
    "unknown": "unknown",
}


def _derive_lifecycle_state(
    p10_status: Optional[str],
    provisioning: Optional[PlatformTenant],
) -> TenantLifecycleState:
    """Derive the read-only lifecycle state from existing sources.

    Priority:
      1. A provisioning-journal failure -> ``failed_provisioning`` (real signal).
      2. A draft tenant with provisioning in progress -> ``provisioning``.
      3. The mapped P10 status (draft/active/paused/suspended/archived).
      4. ``unknown`` fallback (never 'active').

    state_source_status is 'available' when a real (non-unknown) position is
    derived, else 'unknown'. Transition audit fields read null -- they are
    deferred to a future controlled-action phase.
    """
    state = "unknown"
    if provisioning is not None and provisioning.provisioning_status == "failed":
        state = "failed_provisioning"
    elif (
        p10_status == "draft"
        and provisioning is not None
        and provisioning.provisioning_status
        in ("pending", "schema_created", "seed_complete")
    ):
        state = "provisioning"
    elif p10_status is not None:
        state = _P10_STATUS_TO_LIFECYCLE.get(p10_status, "unknown")

    source_status: RegistrySourceStatus = "unknown" if state == "unknown" else "available"

    entered_at = None
    if state == "active" and provisioning is not None and provisioning.activated_at is not None:
        entered_at = provisioning.activated_at

    return TenantLifecycleState(
        state=state,  # type: ignore[arg-type]
        previous_state=None,
        entered_at=entered_at,
        last_actor_id=None,  # deferred until platform auth
        last_actor_role=None,  # deferred until platform auth
        transition_reason=None,  # no transition log source yet
        last_audit_event_id=None,  # no audit-event source yet
        state_source_status=source_status,
    )


# -- Operational flags --

_FLAGS_UNAVAILABLE_REASON = (
    "Operational flag telemetry is not yet instrumented; all flags read false."
)


def _build_operational_flags(
    support_mode_active: bool,
) -> TenantOperationalFlags:
    """Build the operational-flags block.

    Runtime telemetry for the operational flags (incident_active, login_paused,
    writes_paused, billing_hold, backup/migration/quota attention) is not yet
    instrumented, so the block reads flags_source_status='unavailable' with a
    visible reason and every flag false -- an operator can tell a real false
    from an unknown one (unknown != false).
    """
    return TenantOperationalFlags(
        support_mode_active=support_mode_active,
        incident_active=False,
        login_paused=False,
        writes_paused=False,
        billing_hold=False,
        backup_attention_required=False,
        migration_attention_required=False,
        quota_attention_required=False,
        flags_source_status="unavailable",
        flags_updated_at=None,
        flags_unavailable_reason=_FLAGS_UNAVAILABLE_REASON,
    )


# -- Provisioning status --

_PROVISIONING_UNAVAILABLE_REASON = (
    "Provisioning diagnostics (seed / admin_user / feature_config) are not yet "
    "instrumented; only the coarse provisioning journal is readable."
)


def _build_provisioning_status(
    provisioning: Optional[PlatformTenant],
) -> Optional[TenantProvisioningStatus]:
    """Build provisioning diagnostics from the provisioning journal.

    Only fields the journal is authoritative for are populated:
      - schema_status: 'exists' when the journal records schema creation.
      - failure_reason_redacted: an allowlisted code on a failed provisioning.
    Fine diagnostics (seed / admin_user / feature_config) have no source yet and
    read null. When the journal itself is absent, returns None so the caller
    surfaces the source gap at the registry level (null + reason).
    """
    if provisioning is None:
        return None
    ps = provisioning.provisioning_status
    schema_status = "exists" if ps in ("schema_created", "seed_complete") else None

    failure_reason = None
    if ps == "failed":
        # Collapse any journal detail to an allowlisted code; never raw.
        failure_reason = "provisioning_incomplete"

    return TenantProvisioningStatus(
        schema_status=schema_status,  # type: ignore[arg-type]
        seed_status=None,  # tenant schema aggregate not available
        admin_user_status=None,  # tenant schema aggregate not available
        feature_config_status=None,  # tenant schema aggregate not available
        last_provisioning_check_at=None,  # telemetry not available
        failure_reason_redacted=failure_reason,
        provisioning_source_status="available",
    )


# -- Backup status (P17-D-C: durable source read path) --
#
# The backup sub-contract is now sourced from the durable public-schema tables
# created by migration 021 (platform_backup_outcome append-only outcomes +
# platform_backup_policy config). The read path is READ-ONLY: it SELECTs the
# latest COMPLETED outcome rows and never mutates them (mutations are
# writer-only). The mapping, freshness, redaction, and visibility rules are the
# P17-D-A contract / P17-D-B plan (sections 4-9); a summary of the binding
# invariants:
#   - unknown is never healthy, null is never zero, success is never stale.
#   - success requires a fresh timestamp (within BACKUP_FRESHNESS_WINDOW, 24h)
#     AND backup_source_status == 'available'.
#   - restore-test verdicts go stale past the restore-test cadence.
#   - failure_reason_redacted is the closed BACKUP_FAILURE_REASONS vocabulary
#     only (never raw); collapsed by redact_failure_reason.
#   - a source read failure degrades to backup_status=None + reason, never a
#     500 and never a fabricated success.
#   - read-only, no P22: backup.check stays source_unknown / not_implemented.

_BACKUP_UNAVAILABLE_REASON = (
    "Backup source read failed; backup status is unavailable."
)
_BACKUP_UNKNOWN_REASON = (
    "No backup outcome has been recorded; backup status is unknown."
)

# Restore-test cadence window (P17-D-B section 6 pins this value). A
# passed/failed restore-test older than this reads 'stale' (never a fresh
# verdict). Overridable per-policy via platform_backup_policy.restore_test_cadence_hours.
RESTORE_TEST_CADENCE_WINDOW = timedelta(hours=168)  # 7 days


@dataclass
class _BackupSourceRead:
    """One tenant's resolved backup / status source read (best-effort).

    ``source_status`` is the honest hinge: 'available' only when the source was
    readable AND an outcome applicable to this tenant exists (tenant-specific or
    platform-wide fallback); 'unknown' when readable but no applicable outcome;
    'unavailable' is never set here (a read failure returns ``None`` from the
    loader for the whole map).
    """

    source_status: RegistrySourceStatus
    backup_row: Optional[PlatformBackupOutcome] = None
    restore_row: Optional[PlatformBackupOutcome] = None
    policy_row: Optional[PlatformBackupPolicy] = None
    reason: Optional[str] = None


def _to_uuid(value: Optional[str]) -> Optional[UUID]:
    """Best-effort UUID parse; None on a missing/malformed id (never raises)."""
    if value is None:
        return None
    try:
        return UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


def _restore_test_cadence(policy_row: Optional[PlatformBackupPolicy]) -> timedelta:
    """Per-policy restore-test cadence override, else the platform default."""
    if (
        policy_row is not None
        and policy_row.restore_test_cadence_hours is not None
    ):
        return timedelta(hours=policy_row.restore_test_cadence_hours)
    return RESTORE_TEST_CADENCE_WINDOW


def _enforce_restore_test_freshness(
    base_status: Optional[str],
    at: Optional[datetime],
    policy_row: Optional[PlatformBackupPolicy],
    now: datetime,
) -> Optional[str]:
    """Downgrade a stale restore-test verdict to 'stale'; never a fresh verdict.

    A 'passed'/'failed' restore test older than the (policy-or-default) cadence
    reads 'stale'. A verdict without a confirmable timestamp reads 'unknown'.
    Other values pass through unchanged.
    """
    if base_status not in ("passed", "failed"):
        return base_status
    if at is None:
        return "unknown"
    if now - at > _restore_test_cadence(policy_row):
        return "stale"
    return base_status


async def _load_backup_status_map(
    db: AsyncSession, tenant_ids: list[str], now: datetime
) -> Optional[dict[str, _BackupSourceRead]]:
    """Load the latest completed backup / restore-test outcomes + policy per tenant.

    Returns a ``{tenant_id_str: _BackupSourceRead}`` map. For each tenant, prefers
    a tenant-specific outcome (``tenant_id = X``) and falls back to the
    platform-wide outcome (``tenant_id IS NULL``), applied independently per
    ``job_kind`` (backup_job vs restore_test_job) -- today's only writer is a
    whole-database pg_dump whose freshness applies to every tenant. Policy is
    resolved the same way (tenant row, else platform default).

    On ANY error returns ``None`` so the adapter degrades to
    ``backup_status=None`` + the unavailable reason for every tenant (never
    raises, never fabricates) -- mirroring ``_load_provisioning_map``'s
    degrade-on-failure discipline but distinguishing a read failure (``None``)
    from a successful empty read (a dict of 'unknown' reads). Returns ``{}`` for
    an empty tenant-id list (nothing to resolve).
    """
    if not tenant_ids:
        return {}

    tenant_uuids = [u for u in (_to_uuid(t) for t in tenant_ids) if u is not None]

    try:
        async with db.begin_nested():
            outcomes_result = await db.execute(
                select(PlatformBackupOutcome).where(
                    or_(
                        PlatformBackupOutcome.tenant_id.in_(tenant_uuids),
                        PlatformBackupOutcome.tenant_id.is_(None),
                    ),
                    PlatformBackupOutcome.completed_at.is_not(None),
                )
            )
            outcomes = outcomes_result.scalars().all()

            policies_result = await db.execute(
                select(PlatformBackupPolicy).where(
                    or_(
                        PlatformBackupPolicy.tenant_id.in_(tenant_uuids),
                        PlatformBackupPolicy.tenant_id.is_(None),
                    )
                )
            )
            policies = policies_result.scalars().all()
    except Exception:
        # Read failure -> SAVEPOINT rolled back, outer session is clean.
        # Unavailable for every tenant (caller surfaces reason).
        return None

    def _latest(rows: list[PlatformBackupOutcome]) -> Optional[PlatformBackupOutcome]:
        return max(rows, key=lambda r: r.completed_at) if rows else None

    plat_backup = _latest(
        [o for o in outcomes if o.tenant_id is None and o.job_kind == "backup_job"]
    )
    plat_restore = _latest(
        [o for o in outcomes if o.tenant_id is None and o.job_kind == "restore_test_job"]
    )
    plat_policy = next((p for p in policies if p.tenant_id is None), None)

    resolved: dict[str, _BackupSourceRead] = {}
    for tid in tenant_ids:
        tid_uuid = _to_uuid(tid)
        tenant_backup = _latest(
            [
                o
                for o in outcomes
                if o.tenant_id == tid_uuid and o.job_kind == "backup_job"
            ]
        )
        tenant_restore = _latest(
            [
                o
                for o in outcomes
                if o.tenant_id == tid_uuid and o.job_kind == "restore_test_job"
            ]
        )
        backup_row = tenant_backup or plat_backup
        restore_row = tenant_restore or plat_restore

        tenant_policy = (
            next((p for p in policies if p.tenant_id == tid_uuid), None)
            if tid_uuid is not None
            else None
        )
        policy_row = tenant_policy or plat_policy

        if backup_row is not None or restore_row is not None:
            resolved[tid] = _BackupSourceRead(
                source_status="available",
                backup_row=backup_row,
                restore_row=restore_row,
                policy_row=policy_row,
                reason=None,
            )
        else:
            resolved[tid] = _BackupSourceRead(
                source_status="unknown",
                reason=_BACKUP_UNKNOWN_REASON,
            )
    return resolved


def _build_backup_status(
    read: Optional[_BackupSourceRead], now: datetime
) -> Optional[TenantBackupStatus]:
    """Build a TenantBackupStatus from the durable source read.

    Returns ``None`` when the source is not 'available' (read failed -> None from
    the loader, or 'unknown' read with no applicable outcome) so the registry
    keeps ``backup_status`` nullable and surfaces the reason -- the existing
    degrade path. When the source is 'available', routes every populated status
    through ``enforce_backup_freshness`` (24h window) and the restore-test
    cadence, applies ``redact_failure_reason``, and asserts
    ``backup_source_status='available'`` so the schema backstop
    (``success_requires_fresh_timestamp``) holds. Never raises.
    """
    if read is None or read.source_status != "available":
        return None

    backup_row = read.backup_row
    restore_row = read.restore_row
    policy_row = read.policy_row

    # last_backup_at / last_backup_status (freshness-routed; success is never stale).
    last_backup_at = backup_row.completed_at if backup_row is not None else None
    raw_backup_status = backup_row.status if backup_row is not None else None
    last_backup_status = (
        enforce_backup_freshness(raw_backup_status, last_backup_at, now=now)
        if raw_backup_status is not None
        else None
    )

    # failure_reason_redacted: allowlisted code of the latest failed/partial backup.
    failure_reason: Optional[str] = None
    if backup_row is not None and backup_row.status in ("failed", "partial"):
        failure_reason = redact_failure_reason(
            backup_row.failure_reason_code, BACKUP_FAILURE_REASONS
        )

    # restore_test_status: success -> passed; failed -> failed; else unknown; then cadence.
    last_restore_test_at = restore_row.completed_at if restore_row is not None else None
    if restore_row is not None:
        if restore_row.status == "success":
            rt_base = "passed"
        elif restore_row.status == "failed":
            rt_base = "failed"
        else:
            # partial / unexpected: indeterminate, never a pass.
            rt_base = "unknown"
        restore_test_status = _enforce_restore_test_freshness(
            rt_base, last_restore_test_at, policy_row, now
        )
    else:
        restore_test_status = None  # no restore-test outcome recorded -> null

    # export_available: a restorable non-empty dump exists and latest backup is
    # not failed -> True; else False. The durable outcome carries no per-dump
    # retention timestamp, so 'within retention' is approximated by 'the latest
    # backup succeeded with bytes_written > 0' (the CHECK constraint guarantees a
    # success row carries bytes_written > 0).
    if (
        backup_row is not None
        and backup_row.status == "success"
        and (backup_row.bytes_written or 0) > 0
    ):
        export_available = True
    else:
        export_available = False

    retention_policy = policy_row.retention_policy if policy_row is not None else None

    return TenantBackupStatus(
        last_backup_at=last_backup_at,
        last_backup_status=last_backup_status,  # type: ignore[arg-type]
        last_restore_test_at=last_restore_test_at,
        restore_test_status=restore_test_status,  # type: ignore[arg-type]
        export_available=export_available,
        retention_policy=retention_policy,
        failure_reason_redacted=failure_reason,
        backup_source_status="available",
        last_status_check_at=now,
    )


def _backup_unavailable_reason(read: Optional[_BackupSourceRead]) -> str:
    """The honest registry-level reason when backup_status is null."""
    if read is None or read.source_status == "unavailable":
        return _BACKUP_UNAVAILABLE_REASON
    if read.source_status == "unknown":
        return _BACKUP_UNKNOWN_REASON
    return _BACKUP_UNKNOWN_REASON  # defensive: a null build is treated as unknown


# -- Registry assembly --


def _build_registry(
    tenant_id: str,
    tenant_name: Optional[str],
    tenant_schema: Optional[str],
    tier: Optional[str],
    created_at: Optional[datetime],
    support_mode_active: bool,
    p10_status: Optional[str],
    provisioning: Optional[PlatformTenant],
    now: datetime,
    backup_read: Optional[_BackupSourceRead] = None,
) -> PlatformTenantRegistry:
    """Assemble one PlatformTenantRegistry from existing sources.

    Never raises: every sub-source degrades to its documented fallback with a
    reason. ``unknown`` is never 'active' and ``null`` is never '0'. The backup
    sub-source is built from the durable read (P17-D-C): when the source reads
    'available' a real TenantBackupStatus is attached and no backup reason is
    surfaced; otherwise ``backup_status`` stays null with the honest reason.
    """
    lifecycle = _derive_lifecycle_state(p10_status, provisioning)
    flags = _build_operational_flags(support_mode_active)
    provisioning_status = _build_provisioning_status(provisioning)
    backup_status = _build_backup_status(backup_read, now)

    reasons: list[str] = [_FLAGS_UNAVAILABLE_REASON]
    if provisioning_status is None:
        reasons.append(_PROVISIONING_UNAVAILABLE_REASON)
    if backup_status is None:
        # Source not available (read failed -> unavailable, or no outcome ->
        # unknown). Never a fabricated success; the reason is surfaced.
        reasons.append(_backup_unavailable_reason(backup_read))

    # The core record (identity + lifecycle + flags) availability drives the
    # registry-level status; degraded sub-sources are enumerated in the reason.
    registry_source_status: RegistrySourceStatus = (
        "unknown" if lifecycle.state == "unknown" else "available"
    )

    return PlatformTenantRegistry(
        tenant_id=tenant_id,
        tenant_name=tenant_name,
        tenant_schema=tenant_schema,
        tier=tier,
        created_at=created_at,
        lifecycle_state=lifecycle,
        operational_flags=flags,
        provisioning_status=provisioning_status,
        backup_status=backup_status,
        last_registry_update_at=None,  # no registry-update timestamp source yet
        registry_source_status=registry_source_status,
        unavailable_reason=" ".join(reasons),
    )


async def list_tenant_registries(
    db: AsyncSession, limit: int = 50, offset: int = 0
) -> PlatformTenantRegistryList:
    """List all tenant registries (read-only).

    Aggregates the P10 tenant summaries + the provisioning journal. Any source
    failure is swallowed: the list returns with registry_source_status set to
    'unavailable'/'unknown' and an unavailable_reason, never a 500 and never a
    fabricated healthy record.
    """
    now = _utcnow()
    reasons: list[str] = []

    try:
        summaries = await list_tenant_summaries(db, limit=limit, offset=offset)
    except Exception:
        return PlatformTenantRegistryList(
            items=[],
            total=0,
            limit=limit,
            offset=offset,
            registry_source_status="unavailable",
            unavailable_reason="Tenant identity source unavailable during registry assembly.",
        )

    wholesaler_ids = [s.tenant_id for s in summaries.items if s.tenant_id]
    provisioning_map = await _load_provisioning_map(db, wholesaler_ids)
    if provisioning_map == {} and wholesaler_ids:
        # Distinguish "no provisioning rows" from "source query failed": a failed
        # query returns {} too, so we cannot be certain; treat empty conservatively
        # as a degraded sub-source (provisioning reads null + reason per-tenant).
        reasons.append(_PROVISIONING_UNAVAILABLE_REASON)

    backup_map = await _load_backup_status_map(db, wholesaler_ids, now)
    if backup_map is None and wholesaler_ids:
        # A None map means the backup source read FAILED (unavailable for all);
        # each tenant's backup_status is null with the unavailable reason.
        reasons.append(_BACKUP_UNAVAILABLE_REASON)

    items: list[PlatformTenantRegistry] = []
    any_unknown = False
    for s in summaries.items:
        tenant_id = s.tenant_id or "00000000-0000-4000-8000-000000000000"
        provisioning = provisioning_map.get(tenant_id) if tenant_id else None
        backup_read = backup_map.get(tenant_id) if backup_map else None
        try:
            reg = _build_registry(
                tenant_id=tenant_id,
                tenant_name=s.tenant_name,
                tenant_schema=s.tenant_schema,
                tier=s.tier,
                created_at=s.created_at,
                support_mode_active=s.support_mode_active,
                p10_status=s.status,
                provisioning=provisioning,
                now=now,
                backup_read=backup_read,
            )
        except Exception:
            # A single tenant build failure must not break the list; emit an
            # explicit unknown record rather than a fabricated healthy one.
            any_unknown = True
            reg = PlatformTenantRegistry(
                tenant_id=tenant_id,
                tenant_name=s.tenant_name,
                tenant_schema=s.tenant_schema,
                tier=s.tier,
                created_at=s.created_at,
                lifecycle_state=TenantLifecycleState(
                    state="unknown", state_source_status="unknown"
                ),
                operational_flags=_build_operational_flags(False),
                provisioning_status=None,
                backup_status=None,
                last_registry_update_at=None,
                registry_source_status="unknown",
                unavailable_reason="Registry assembly failed for this tenant; data is unknown.",
            )
        if reg.lifecycle_state.state == "unknown":
            any_unknown = True
        items.append(reg)

    if any_unknown:
        reasons.append("One or more tenant lifecycle states could not be determined.")

    source_status: RegistrySourceStatus = (
        "unknown" if any_unknown else "available"
    ) if items else "unavailable"

    return PlatformTenantRegistryList(
        items=items,
        total=summaries.total,
        limit=summaries.limit,
        offset=summaries.offset,
        registry_source_status=source_status,
        unavailable_reason=" ".join(reasons) if reasons else None,
    )


async def get_tenant_registry(
    db: AsyncSession, tenant_id: str
) -> Optional[PlatformTenantRegistry]:
    """Get a single tenant registry (read-only).

    Returns None when the tenant identity does not exist at all (caller returns
    404). When the tenant exists but sub-sources are unavailable, returns a
    record with unknown / null fields + reasons, never a fabricated healthy one.
    """
    now = _utcnow()

    # Reuse P10's tenant summary source (single-tenant).
    from api.v1.platform.p10.services import get_tenant_summary

    try:
        summary = await get_tenant_summary(db, tenant_id)
    except Exception:
        return None
    if summary is None or summary.tenant_id is None:
        return None

    provisioning_map = await _load_provisioning_map(db, [summary.tenant_id])
    provisioning = provisioning_map.get(summary.tenant_id)

    backup_map = await _load_backup_status_map(db, [summary.tenant_id], now)
    backup_read = backup_map.get(summary.tenant_id) if backup_map else None

    return _build_registry(
        tenant_id=summary.tenant_id,
        tenant_name=summary.tenant_name,
        tenant_schema=summary.tenant_schema,
        tier=summary.tier,
        created_at=summary.created_at,
        support_mode_active=summary.support_mode_active,
        p10_status=summary.status,
        provisioning=provisioning,
        now=now,
        backup_read=backup_read,
    )
