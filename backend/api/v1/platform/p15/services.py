"""
Service layer for P15 Incident Triage (read-only snapshot API).

Aggregates EXISTING read-only sources only:
  - P10 system/tenant health summaries (status/counts, no business records)
  - P13 ops helpers (error-rate, slow-route, noisy-neighbor, resource summaries)
  - P14 real DB live probe (_database_health: ping + pool)

Design rules (from PLATFORM_PRODUCT_P15_INCIDENT_TRIAGE_CONTRACT.md):
  - unknown != healthy. null != 0.
  - unavailable_reason / degraded_reason always visible.
  - graceful_degraded: a single source failure still yields a snapshot (with the
    failing component marked unknown/unavailable + reason), never a bare 500 or a
    fabricated healthy.
  - No write endpoints, no tenant business records, no credentials/DSN/host/port,
    no raw pool.status() string (P14 parses it to counts).

P15-B is read-only. It adds no new data sources and no new infrastructure.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.platform.p13.services import (
    _database_health,
    get_error_rate_summary,
    get_noisy_neighbor_summary,
    get_resource_health_summary,
    get_slow_route_summary,
)
from api.v1.platform.p10.services import (
    get_system_health,
    list_tenant_summaries,
)

from .schemas import (
    IncidentClassification,
    IncidentHandoffSummary,
    IncidentRunbookHint,
    IncidentSignal,
    IncidentTriageSnapshot,
)


# -- Static runbook hints (doc-driven, observation-only) --

_RUNBOOKS = {
    "database": IncidentRunbookHint(
        category="database",
        checklist=[
            "Check P14 DB live probe latency and pool utilisation.",
            "Confirm P13 /ops/resources database status.",
            "Review unavailable_reason / degraded_reason before concluding.",
        ],
        do_not=[
            "Do not run repair or restart actions (out of P15 scope).",
            "Do not read tenant business records.",
        ],
        handoff_to="dba",
    ),
    "system": IncidentRunbookHint(
        category="system",
        checklist=[
            "Review P10 system health overall status.",
            "Check P13 /ops/resources for uninstrumented components.",
        ],
        do_not=[
            "Do not scale or redeploy from this surface.",
            "Do not impersonate tenants.",
        ],
        handoff_to="platform",
    ),
    "api": IncidentRunbookHint(
        category="api",
        checklist=[
            "Review P13 /ops/errors and /ops/slow-routes source_status.",
            "Note unavailable_reason if telemetry not instrumented.",
        ],
        do_not=[
            "Do not read raw request/response payloads.",
            "Do not mutate API configuration.",
        ],
        handoff_to="engineering",
    ),
    "tenant_health": IncidentRunbookHint(
        category="tenant_health",
        checklist=[
            "Review P10 tenant summaries (status counts only).",
            "Confirm no business records are exposed.",
        ],
        do_not=[
            "Do not open tenant business data.",
            "Do not impersonate tenant admins.",
        ],
        handoff_to="support",
    ),
    "support_issue": IncidentRunbookHint(
        category="support_issue",
        checklist=[
            "Use P12 support console diagnostics/bundle concepts.",
            "Prepare a redacted handoff summary.",
        ],
        do_not=[
            "Do not include credentials or payloads.",
            "Do not execute support actions from this surface.",
        ],
        handoff_to="support",
    ),
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _short_id() -> str:
    return uuid.uuid4().hex[:12]


def _runbook_for(category: str) -> IncidentRunbookHint:
    """Return the doc-driven runbook for a category (defaults to system)."""
    return _RUNBOOKS.get(category, _RUNBOOKS["system"])


def _classify_overall(db_status: Optional[str]) -> tuple[str, Optional[str], Optional[str]]:
    """Derive overall_status + reasons from the strongest available signal.

    Returns (overall_status, degraded_reason, unavailable_reason).
    """
    if db_status is None:
        return "unknown", None, "Database probe unavailable; primary signal missing."
    if db_status == "unhealthy":
        return "unhealthy", "Database probe reported unhealthy latency or ping failure.", None
    if db_status == "degraded":
        return "degraded", "Database probe latency above healthy threshold.", None
    if db_status == "healthy":
        return "healthy", None, None
    return "unknown", None, "Database probe reported unknown status."


# -- Public service functions --


async def build_triage_snapshot(db: AsyncSession) -> IncidentTriageSnapshot:
    """Assemble a read-only incident triage snapshot.

    Aggregates P10/P13/P14 read-only sources. Any single source failure is
    swallowed: the snapshot returns with graceful_degraded=true and the failing
    piece marked unknown/unavailable with a reason. Never raises to the client,
    never fabricates healthy/0.
    """
    graceful = False
    unavailable_reasons: list[str] = []
    signals: list[IncidentSignal] = []
    now = _utcnow()

    # --- P14 real DB probe (strongest signal) ---
    db_health = None
    db_status: Optional[str] = None
    try:
        db_health = await _database_health(db)
        db_status = db_health.status
    except Exception:
        graceful = True
        unavailable_reasons.append("Database probe failed during snapshot assembly.")
        db_signal = IncidentSignal(
            signal_id=_short_id(),
            kind="database",
            severity="unknown",
            source_ref="p14.ops.resources.database",
            observed_value=None,
            source_status="unavailable",
            unavailable_reason="Database probe raised an error.",
            degraded_reason=None,
            observed_at=now,
        )
        signals.append(db_signal)
    else:
        sev = {
            "healthy": "info",
            "degraded": "degraded",
            "unhealthy": "unhealthy",
            "unknown": "unknown",
        }.get(db_status, "unknown")
        degraded_reason = None
        if db_status == "degraded":
            degraded_reason = "Database latency above healthy threshold."
        elif db_status == "unhealthy":
            degraded_reason = "Database ping failed or latency critical."
        elif db_status == "unknown":
            degraded_reason = "Database status could not be determined."
        signals.append(
            IncidentSignal(
                signal_id=_short_id(),
                kind="database",
                severity=sev,
                source_ref="p14.ops.resources.database",
                observed_value=db_status,
                source_status="unavailable" if db_status == "unknown" else "available",
                unavailable_reason=None if db_status != "unknown" else "Database status unknown.",
                degraded_reason=degraded_reason,
                observed_at=now,
            )
        )

    overall_status, degraded_reason, base_unavailable = _classify_overall(db_status)
    if base_unavailable:
        unavailable_reasons.append(base_unavailable)

    # --- P10 system health (counts/status only; no business records) ---
    system_overall: Optional[str] = None
    try:
        system_health = await get_system_health(db)
        system_overall = system_health.overall_status
    except Exception:
        graceful = True
        unavailable_reasons.append("P10 system health unavailable during snapshot.")
    signals.append(
        IncidentSignal(
            signal_id=_short_id(),
            kind="system",
            severity="info" if system_overall == "healthy" else (
                "unknown" if system_overall in (None, "unknown") else "degraded"
            ),
            source_ref="p10.system.health",
            observed_value=system_overall,
            source_status="unavailable" if system_overall is None else (
                "unknown" if system_overall == "unknown" else "available"
            ),
            unavailable_reason=None if system_overall else "P10 system health not available.",
            degraded_reason=None,
            observed_at=now,
        )
    )

    # --- P10 tenant health sample counts (no business records) ---
    tenant_count: Optional[int] = None
    unhealthy_count: Optional[int] = None
    try:
        tenant_list = await list_tenant_summaries(db, limit=50, offset=0)
        tenant_count = tenant_list.total
        unhealthy_count = sum(
            1 for t in tenant_list.items if t.status not in ("active",)
        )
    except Exception:
        graceful = True
        unavailable_reasons.append("P10 tenant summaries unavailable during snapshot.")
    signals.append(
        IncidentSignal(
            signal_id=_short_id(),
            kind="tenant_health",
            severity="info" if unhealthy_count == 0 else "warning",
            source_ref="p10.tenants.summary",
            observed_value=str(tenant_count) if tenant_count is not None else None,
            source_status="unavailable" if tenant_count is None else "available",
            unavailable_reason=None if tenant_count is not None else "Tenant summaries not available.",
            degraded_reason=None,
            observed_at=now,
        )
    )

    # --- P13 ops signals (error-rate / slow / noisy) -- source_status carries reasons ---
    for kind, fetch in (
        ("api", lambda: get_error_rate_summary(db, window_minutes=15)),
        ("api", lambda: get_slow_route_summary(db, window_minutes=15)),
    ):
        try:
            summary = await fetch()
            signals.append(
                IncidentSignal(
                    signal_id=_short_id(),
                    kind=kind,
                    severity="info" if summary.source_status == "available" else "unknown",
                    source_ref="p13.ops",
                    observed_value=summary.source_status,
                    source_status=summary.source_status,
                    unavailable_reason=getattr(summary, "unavailable_reason", None),
                    degraded_reason=None,
                    observed_at=now,
                )
            )
        except Exception:
            graceful = True
            unavailable_reasons.append("P13 ops signal unavailable during snapshot.")

    return IncidentTriageSnapshot(
        snapshot_id=_short_id(),
        generated_at=now,
        overall_status=overall_status,
        signals=signals,
        database_probe=db_health,
        system_health_overall=system_overall,
        tenant_health_sample_count=tenant_count,
        tenant_health_unhealthy_count=unhealthy_count,
        degraded_reason=degraded_reason,
        unavailable_reason=" ".join(unavailable_reasons) if unavailable_reasons else None,
        graceful_degraded=graceful or bool(unavailable_reasons),
    )


def build_handoff_summary(
    snapshot: IncidentTriageSnapshot,
    classification: IncidentClassification,
) -> IncidentHandoffSummary:
    """Build a redacted handoff summary from a snapshot + classification.

    Redaction is structural: the summary only carries the already-redacted signal
    list (counts/paths/statuses/reasons) and a doc-driven runbook. No raw
    payloads, credentials, DSN, host/port, or tenant business records are present
    in the source models, so none can leak. sensitive_keys_dropped is a
    diagnostic count (0 for P15 -- the upstream models are already allowlisted).
    """
    return IncidentHandoffSummary(
        summary_id=_short_id(),
        created_at=_utcnow(),
        classification=classification,
        signals=list(snapshot.signals),
        runbook_hint=_runbook_for(classification.category),
        redacted=True,
        sensitive_keys_dropped=0,
    )
