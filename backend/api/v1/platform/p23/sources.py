"""P23-C operator-task source materialization bridge (READ-ONLY, NON-EXECUTING).

This module is the P23-C PULL bridge that begins to populate the P23 operator-task
queue with REAL platform follow-up items read from existing, already-audited
READ-ONLY platform source surfaces. It turns those reads into typed, redacted
``OperatorTaskIntakeEvent`` objects and feeds them -- and only them -- through the
P23 service layer's ``upsert_task_from_event``.

The single invariant, carried verbatim from P23-A / P23-B:

    A task is a view, not an executor. A notification is a record, not a delivery.

What this module IS:
  - A READ-ONLY materialization pass. It reads two proven safe surfaces and maps
    them into the closed P23 task vocabulary (P23-A section 3.1):
      * P19 in-memory approval workflow (``p19.services.list_approvals``) ->
        ``approval_pending`` for an open approval (requested / pending_review),
        and ``approval_decision_required`` when such an approval is past its
        expiry (an honest "decide now" signal). P19 is in-memory; no session.
      * P22-E3 read-only ``backup.check`` source probe
        (``p22.source_probe.read_backup_check_source``) -> ``backup_check_warning``
        for a degraded backup (stale / failed / partial / in_progress) or
        ``source_unknown`` for an unknown / unavailable source. A fresh success is
        the only healthy read and it produces NO task (a healthy backup needs no
        follow-up). This reuses the PROVEN P22-E3 / P17-D-C read-only path.
  - HONEST. An unknown / unavailable source is never displayed healthy and never
    success; null is never zero. The mapping never fabricates a healthy state.

What this module NEVER does:
  - execute a P22 action, approve a P19/P20/P21 approval, mutate a P17 registry
    field, deliver a notification, dispatch a worker / scheduler / drain loop, or
    run shell / SQL / script / subprocess / pg_dump / restore;
  - read or write any tenant business / payment / billing / product / order /
    invoice / customer / inventory / ledger record;
  - import the P22 EXECUTION surface (``p22.services`` / ``p22.adapters`` /
    ``p22.governed_execution``) or sqlalchemy / alembic / psycopg. A static AST
    guard in the test suite asserts this for every P23 source file.

Why some task types are NOT materialized by this PULL bridge:
  - ``action_request_created`` / ``execution_ready`` / ``execution_completed`` /
    ``execution_failed`` derive from the P22 execution surface, which P23 is
    deliberately decoupled from (the AST guard forbids the import). Those
    follow-ups arrive via the P23 INTAKE endpoint (a PUSH from the execution
    layer), not via this PULL bridge. Omitting them here is the honest, safe
    choice -- it is not a fabrication and never claims success from unknown data.
  - ``incident_followup_required`` / ``runbook_step_required`` need a P15 /
    runbook source not wired through this pass; deferred to a later P23 phase.

This module adds NO HTTP route. The guarded manual trigger lives in ``routes.py``
(``POST .../internal/materialize``); it is a manual read/materialize operation,
NOT a scheduler and NOT a worker.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

# Read-only, already-audited source surfaces. These imports add no execution
# surface: P19 is an in-memory approval read; p22.source_probe is the P22-E3
# read-only backup.check source probe (a read, never an execution). The P22
# execution surface (p22.services / p22.adapters / p22.governed_execution) and
# sqlalchemy / alembic / psycopg are deliberately NOT imported -- a static AST
# guard in the test suite enforces this for every P23 source file.
from api.v1.platform.p19 import services as p19_services
from api.v1.platform.p22.source_probe import read_backup_check_source
from api.v1.platform.p23.schemas import OperatorTaskIntakeEvent
from api.v1.platform.p23.services import upsert_task_from_event


# -- Constants (echo-safe labels only) ----------------------------------------

#: The P23-C phase implemented by this module.
SOURCE_MATERIALIZE_PHASE: str = "P23-C-operator-task-source-materialization-bridge"

#: Read-only marker. This bridge realizes no execution and approves nothing.
SOURCE_MATERIALIZE_REALIZES_EXECUTION: bool = False

#: P19 in-memory approval states that are an active review follow-up.
_PENDING_P19_STATES: frozenset = frozenset({"requested", "pending_review"})

#: P17/P22 backup source summaries that are degraded (never healthy, never
#: success) -> backup_check_warning (P23-A 3.1).
_DEGRADED_BACKUP_SUMMARIES: frozenset = frozenset(
    {"stale", "failed", "partial", "in_progress"}
)

#: P19 registry source status -> P23 source status. Unknown is never healthy.
_P19_SOURCE_STATUS_MAP: dict = {
    "available": "known",
    "unavailable": "degraded",
    "unknown": "unknown",
}

_BACKUP_CHECK_SOURCE_REF: str = "backup.check"
_BACKUP_CORRELATION: str = "p23c:backup.check:platform-wide"
_P19_CORRELATION_PREFIX: str = "p23c:p19:approval:"


# -- Materialization summary models (echo-safe; extra="forbid") ---------------


class SourceMaterializationCounts(BaseModel):
    """Per-source counts for one materialization pass. Read-only summary."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(..., description="Source label, e.g. p19_approvals.")
    read: int = Field(..., description="Source items read this pass.")
    created: int = Field(..., description="Brand-new tasks materialized.")
    deduped: int = Field(
        ..., description="Events absorbed into an existing ACTIVE task (idempotent replay)."
    )
    skipped: int = Field(
        ...,
        description="Source items that needed no follow-up (healthy / non-pending).",
    )
    unavailable: int = Field(
        ...,
        description="Source reads that were unavailable / failed (still surfaced as source_unknown).",
    )
    task_ids: list[str] = Field(
        default_factory=list, description="Tasks touched (created or deduped) this pass."
    )


class MaterializeSummary(BaseModel):
    """Aggregate result of one manual materialize pass. Read-only summary."""

    model_config = ConfigDict(extra="forbid")

    sources: list[SourceMaterializationCounts]
    total_created: int
    total_deduped: int
    total_skipped: int
    total_unavailable: int
    materialized_at: datetime = Field(..., description="UTC ISO-8601.")


# -- Pure source -> event mapping (the honesty rules live here) ---------------
#
# These helpers take a single typed source item and return ONE redacted
# OperatorTaskIntakeEvent (or None when the item needs no follow-up). They
# execute nothing, read no store, and are independently unit-testable. The
# P23 service layer re-redacts every free-text field, so the output is safe even
# if a source identifier were ever hostile.


def _actor_scope_for_tenant(tenant_id: Optional[str]) -> str:
    return "tenant_contextual" if tenant_id else "platform"


def _source_status_for_approval(rec: Any) -> str:
    """P19 registry source status -> P23 source status. Unknown is never healthy."""
    raw = getattr(rec, "source_status", None) or "unknown"
    return _P19_SOURCE_STATUS_MAP.get(raw, "unknown")


def approval_event_from_record(
    rec: Any, *, now: datetime
) -> Optional[OperatorTaskIntakeEvent]:
    """Map a P19 approval record to an intake event, or None if no follow-up.

    An open approval (requested / pending_review) is an ``approval_pending``
    follow-up; one past its expiry is an ``approval_decision_required`` follow-up
    (an honest "decide now" signal). Any other (terminal / decided) state needs
    no operator follow-up and returns None. The linked approval gate is mirrored
    as still open while the approval is pending (completing the task is honestly
    blocked until the approval is decided through P19 / P20 / P21, never here).
    """
    state = getattr(rec, "state", None)
    if state not in _PENDING_P19_STATES:
        return None

    approval_id = getattr(rec, "approval_id", None) or ""
    tenant_id = getattr(rec, "tenant_id", None)
    action_type = getattr(rec, "action_type", None) or "unknown_action"
    action_id = getattr(rec, "action_id", None)
    expires_at = getattr(rec, "expires_at", None)
    overdue = expires_at is not None and expires_at <= now
    task_type = "approval_decision_required" if overdue else "approval_pending"

    correlation_id = getattr(rec, "correlation_id", None) or (
        _P19_CORRELATION_PREFIX + approval_id
    )
    summary = "P19 approval " + approval_id + " for " + action_type + " is " + state + "."
    if overdue:
        summary += " It is past expiry; a checker decision is required."

    return OperatorTaskIntakeEvent(
        task_type=task_type,
        tenant_id=tenant_id,
        actor_scope=_actor_scope_for_tenant(tenant_id),
        owner_role="super_admin",
        correlation_id=correlation_id,
        linked_action_id=action_id,
        linked_approval_id=approval_id or None,
        linked_source_ref=None,
        summary=summary,
        reason="Materialized from P19 approval state=" + state + ".",
        source_status=_source_status_for_approval(rec),
        linked_gate_open=True,
        followup_variant=task_type,
        ttl_expires_at=expires_at,
        channel=None,
    )


def backup_check_event_from_read(read: Any) -> Optional[OperatorTaskIntakeEvent]:
    """Map a P22-E3 backup.check source read to an intake event, or None.

    A fresh success is the only healthy read -> None (no follow-up). A degraded
    backup (stale / failed / partial / in_progress) -> ``backup_check_warning``
    (source_status degraded; a warning is never a success). An unknown or
    unavailable source -> ``source_unknown`` (source_status unknown; unknown is
    never healthy). The mapping is defensive: the P23 source_status is derived
    from the task type, so a hostile read value can never become healthy.
    """
    summary = getattr(read, "source_summary", None)
    if summary == "fresh_success":
        return None
    if summary in _DEGRADED_BACKUP_SUMMARIES:
        task_type = "backup_check_warning"
        source_status = "degraded"
    else:
        # "unknown" (no outcome) or "unavailable" (read failure) -> source_unknown.
        task_type = "source_unknown"
        source_status = "unknown"
    reason_text = getattr(read, "reason", None) or (
        "backup.check source_summary=" + summary + "."
    )
    return OperatorTaskIntakeEvent(
        task_type=task_type,
        tenant_id=None,
        actor_scope="platform",
        owner_role="engineering_operator",
        correlation_id=_BACKUP_CORRELATION,
        linked_source_ref=_BACKUP_CHECK_SOURCE_REF,
        summary="Platform backup.check source is " + summary + ".",
        reason=reason_text,
        source_status=source_status,
        linked_gate_open=False,
        followup_variant=task_type,
        channel=None,
    )


# -- Source readers -> materializers (call only upsert_task_from_event) --------


def materialize_approvals(*, now: Optional[datetime] = None) -> SourceMaterializationCounts:
    """Read P19 in-memory approvals and materialize a task per open follow-up.

    Read-only and in-memory (no session). Executes nothing. Idempotent: a second
    pass dedups against ACTIVE tasks already materialized this process.
    """
    now = now or datetime.now(timezone.utc)
    queue = p19_services.list_approvals(limit=100, offset=0)
    created = 0
    deduped = 0
    skipped = 0
    task_ids: list[str] = []
    for rec in queue.items:
        event = approval_event_from_record(rec, now=now)
        if event is None:
            skipped += 1
            continue
        result = upsert_task_from_event(event)
        if result.created:
            created += 1
        else:
            deduped += 1
        task_ids.append(result.task.task_id)
    return SourceMaterializationCounts(
        source="p19_approvals",
        read=len(queue.items),
        created=created,
        deduped=deduped,
        skipped=skipped,
        unavailable=0,
        task_ids=task_ids,
    )


async def materialize_backup_check(
    db: Any, *, now: Optional[datetime] = None
) -> SourceMaterializationCounts:
    """Read the P22-E3 backup.check source probe and materialize one task.

    Reuses the PROVEN read-only P22-E3 / P17-D-C path verbatim. ``db`` is the
    async session the probe reads through; it is only read. A read failure
    degrades honestly to ``source_unknown`` (fail-closed); a fresh success
    produces no task. Executes nothing.
    """
    now = now or datetime.now(timezone.utc)
    read = await read_backup_check_source(db, tenant_id=None, now=now)
    unavailable = 1 if getattr(read, "source_summary", None) == "unavailable" else 0
    event = backup_check_event_from_read(read)
    if event is None:
        # Healthy fresh success -> no follow-up. Honest, never a fake task.
        return SourceMaterializationCounts(
            source="p22_backup_check",
            read=1,
            created=0,
            deduped=0,
            skipped=1,
            unavailable=0,
            task_ids=[],
        )
    result = upsert_task_from_event(event)
    return SourceMaterializationCounts(
        source="p22_backup_check",
        read=1,
        created=1 if result.created else 0,
        deduped=0 if result.created else 1,
        skipped=0,
        unavailable=unavailable,
        task_ids=[result.task.task_id],
    )


async def materialize_all(
    db: Any, *, now: Optional[datetime] = None
) -> MaterializeSummary:
    """Run every safe source materializer for one manual pass. Read-only.

    Orchestrates the per-source readers, each of which maps its reads to typed
    intake events and calls only ``upsert_task_from_event``. Executes nothing,
    approves nothing, delivers nothing, and mutates no product / tenant data.
    """
    now = now or datetime.now(timezone.utc)
    approvals = materialize_approvals(now=now)
    backup = await materialize_backup_check(db, now=now)
    sources = [approvals, backup]
    return MaterializeSummary(
        sources=sources,
        total_created=sum(s.created for s in sources),
        total_deduped=sum(s.deduped for s in sources),
        total_skipped=sum(s.skipped for s in sources),
        total_unavailable=sum(s.unavailable for s in sources),
        materialized_at=now,
    )


__all__ = [
    "SOURCE_MATERIALIZE_PHASE",
    "SOURCE_MATERIALIZE_REALIZES_EXECUTION",
    "SourceMaterializationCounts",
    "MaterializeSummary",
    "approval_event_from_record",
    "backup_check_event_from_read",
    "materialize_approvals",
    "materialize_backup_check",
    "materialize_all",
]


# Static import-time marker: keep the non-execution invariant discoverable.
assert SOURCE_MATERIALIZE_REALIZES_EXECUTION is False
