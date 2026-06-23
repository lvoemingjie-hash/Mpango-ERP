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

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.platform.p10.services import list_tenant_summaries
from models.platform_tenant import PlatformTenant

from .schemas import (
    PlatformTenantRegistry,
    PlatformTenantRegistryList,
    RegistrySourceStatus,
    TenantLifecycleState,
    TenantOperationalFlags,
    TenantProvisioningStatus,
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
    """
    if not wholesaler_ids:
        return {}
    try:
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


# -- Backup status --

_BACKUP_UNAVAILABLE_REASON = (
    "Backup system source is not yet wired; backup status is unavailable."
)

# Freshness enforcement (stale != success, counterexample C4) is implemented in
# schemas.enforce_backup_freshness and applied by the schema backstop; a live
# backup source will route through it when wired. No backup source exists in
# P17-B, so the backup sub-contract is null at the registry level with the
# reason surfaced on the registry record.


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
) -> PlatformTenantRegistry:
    """Assemble one PlatformTenantRegistry from existing sources.

    Never raises: every sub-source degrades to its documented fallback with a
    reason. ``unknown`` is never 'active' and ``null`` is never '0'.
    """
    lifecycle = _derive_lifecycle_state(p10_status, provisioning)
    flags = _build_operational_flags(support_mode_active)
    provisioning_status = _build_provisioning_status(provisioning)

    reasons: list[str] = [_FLAGS_UNAVAILABLE_REASON]
    if provisioning_status is None:
        reasons.append(_PROVISIONING_UNAVAILABLE_REASON)
    reasons.append(_BACKUP_UNAVAILABLE_REASON)

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
        backup_status=None,  # no backup source -> null + reason (never success)
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

    items: list[PlatformTenantRegistry] = []
    any_unknown = False
    for s in summaries.items:
        tenant_id = s.tenant_id or "00000000-0000-4000-8000-000000000000"
        provisioning = provisioning_map.get(tenant_id) if tenant_id else None
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
    )
