"""P22-E3 backup.check read-only source probe -- NON-EXECUTING source binding.

This module is the P22-E3 read-only source binding for ``backup.check``: it binds
the now-PROVEN, MERGED, TESTED P17-D-C backup / status source (the durable read
path in ``backend/api/v1/platform/p17/services.py`` over migration 021's
``platform_backup_outcome`` + ``platform_backup_policy`` public-schema tables) to
the P22 ``backup.check`` action as a READ-ONLY governed adapter result.

History that gates this module:
  - P22-E2 (docs-only, base ``e87323f``) returned SOURCE_UNKNOWN: no real backup /
    status source existed, so ``backup.check`` stayed ``source_unknown`` /
    ``not_implemented`` and P22-E3 was explicitly NOT started.
  - P17-D-C landed that source on ``origin/platform-dev`` (the P17-D-C merge is
    the base of this branch): migration 021, the read ORM models, and the
    durable registry read path that reads the latest completed backup /
    restore-test outcome plus policy.
  - P22-E3 is therefore unblocked and binds ``backup.check`` to that proven
    source -- but ONLY as a read-only probe that never claims execution
    (P22-E0 / E1 contract; P22-E2 section 6 entry gate, option (b)).

What this probe IS:
  - A READ-ONLY source read. It reuses the P17-D-C durable read path
    (``_load_backup_status_map`` + ``_build_backup_status``) VERBATIM. It adds no
    new query, no new source, no new table, and changes no P17 semantics. It reads
    the latest completed backup / restore-test outcome plus policy and never
    mutates a row (mutations are writer-only; the P17-D-C G16 read-only
    invariant).
  - An HONEST source-status mapping into the P22 vocabulary (known | unknown |
    degraded):
      * a fresh successful backup reads ``known``;
      * a stale / failed / partial / in-progress backup reads ``degraded``;
      * no outcome reads ``unknown``;
      * a source read failure reads ``unknown`` (fail-closed) with the summary
        ``unavailable``.
    Unknown is never healthy; null is never zero; success is never stale.
  - NON-EXECUTING. It performs NO backup, NO restore, NO dump, NO shell / child
    process / SQL script, NO queue drain, NO harness job, and NO tenant mutation.
    ``realizes_execution`` / ``executed`` / ``execution_started`` /
    ``execution_allowed`` are ALWAYS False and ``result_state`` is ALWAYS
    ``blocked`` (never executed). Approval is not execution; a read is not
    execution; a source binding is not execution.

What this probe is NOT:
  - This module is a library-level read-only source reader; it defines no HTTP
    route itself. P22-E3-R1 exposes the probe through a guarded READ-ONLY route
    (``GET /api/v1/platform/p22/backup-check/source`` in ``routes.py``, behind the
    existing ``require_platform_operator_with_p22_audit`` guard) so operators can
    observe backup status. Neither the probe nor that route is a public EXECUTION
    entry point: both read status and return; neither executes, dispatches,
    drains, or mutates. A future real governed EXECUTION (e.g. a read-and-record
    action) would still have to route through the runtime governed action adapter
    seam (P22-E1) behind the full preflight / audit / idempotency gate, and even
    then it would be a read, never an execution.
  - It does NOT modify the static ``backup.check`` adapter descriptor in
    ``adapters.py``. That descriptor stays ``not_implemented`` / ``source_unknown``
    -- the G15 invariant recorded by P17-D-C
    (``test_p22_backup_check_still_not_implemented``). The ADAPTER (the execution
    realization) is still not implemented; this probe is a read-only source read,
    which is not execution.

The probe never raises: a source read failure degrades to an honest
``unavailable`` / ``unknown`` (fail-closed) result, never a 500 and never a
fabricated healthy status. ``failure_reason_redacted`` is the closed
``BACKUP_FAILURE_REASONS`` vocabulary only -- carried verbatim from P17, which
already collapses the raw reason via ``redact_failure_reason`` and re-asserted
here defensively; the raw exception / log / command line never appears.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# Minimal, READ-ONLY reuse of the PROVEN P17-D-C source read path. These symbols
# are the durable backup / status source readers; importing them adds no new
# source, runs no query at import time, and changes no P17 semantics. The read is
# a read of completed outcome rows + policy (read-only); mutations are
# writer-only.
from ..p17.schemas import BACKUP_FAILURE_REASONS
from ..p17.services import _build_backup_status, _load_backup_status_map


# -- Non-execution / phase markers --------------------------------------------

#: The P22-E3 phase implemented by this module.
SOURCE_PROBE_PHASE: str = "P22-E3-backup-check-read-only-source-binding"

#: Explicit non-execution marker. The probe realizes NO execution.
PROBE_REALIZES_EXECUTION: bool = False

#: What this binding is: a read-only source probe, not an executing adapter.
BACKUP_CHECK_BINDING: str = "read_only_source_probe"

#: The P22 source-status vocabulary the probe maps to (mirrors schemas.py).
BackupCheckSourceStatus = Literal["known", "unknown", "degraded"]

#: The closed, honest source-summary vocabulary the probe emits. Mirrors the
#: P17-derived backup verdict (fresh_success / stale / failed / partial /
#: in_progress) plus the two honest non-verdict cases (no outcome -> unknown;
#: read failure -> unavailable).
BackupCheckSummary = Literal[
    "fresh_success",
    "stale",
    "failed",
    "partial",
    "in_progress",
    "unknown",
    "unavailable",
]

#: Nil-UUID sentinel used to read the PLATFORM-WIDE backup outcome (the row whose
#: tenant is NULL) through the P17 loader's OWN platform-fallback resolution. No
#: real tenant carries the nil UUID, so the loader resolves this slot to the
#: platform-default outcome -- reusing the exact P17-D-C resolution rather than
#: duplicating it. Read-only (an IN-clause read query over outcome rows); never a
#: mutation.
_PLATFORM_WIDE_SENTINEL: str = "00000000-0000-4000-8000-000000000000"

#: Honest reason emitted when no backup outcome has been recorded.
_NO_OUTCOME_REASON: str = "No backup outcome has been recorded; status is unknown."

#: Honest reason emitted when the source read failed (fail-closed).
_READ_FAILED_REASON: str = "Backup source read failed; status is unavailable."


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# -- The honest P22-shaped read-only result -----------------------------------


class BackupCheckSourceRead(BaseModel):
    """The READ-ONLY, NON-EXECUTING P22 result of binding backup.check to P17.

    Carries the honest P22 source status, a one-line honest summary (P17-derived
    verdict), the freshness-routed backup / restore-test fields, the allowlisted
    failure reason (never raw), and the non-execution markers. Every execution
    flag is ALWAYS False and ``result_state`` is ALWAYS ``blocked``: this is a
    read, not an execution. Approval is not execution.

    ``adapter_result`` is ``not_implemented``: the backup.check ADAPTER (the
    execution realization) is still not implemented -- this probe is a read-only
    source read. ``binding`` names what this is (a read-only source probe).
    """

    model_config = ConfigDict(extra="forbid")

    action_type: Literal["backup.check"] = "backup.check"
    action_class: Literal["read"] = "read"
    binding: Literal["read_only_source_probe"] = BACKUP_CHECK_BINDING
    adapter_result: Literal["not_implemented"] = "not_implemented"

    source_status: BackupCheckSourceStatus = Field(
        ..., description="known | unknown | degraded. Unknown is never healthy."
    )
    source_summary: BackupCheckSummary = Field(
        ..., description="The honest one-line P17-derived verdict."
    )
    last_backup_status: Optional[str] = Field(
        None,
        description="Freshness-routed verdict: success | partial | failed | in_progress | stale.",
    )
    last_backup_at: Optional[datetime] = Field(None, description="UTC ISO-8601, or null.")
    restore_test_status: Optional[str] = Field(
        None, description="passed | failed | stale | unknown, or null."
    )
    last_restore_test_at: Optional[datetime] = Field(None, description="UTC ISO-8601, or null.")
    failure_reason_redacted: Optional[str] = Field(
        None,
        description="Allowlisted BACKUP_FAILURE_REASONS code only; never the raw reason.",
    )
    export_available: Optional[bool] = Field(None, description="A restorable dump exists.")
    retention_policy: Optional[str] = Field(None, description="Policy label, or null.")
    p17_backup_source_status: Optional[str] = Field(
        None,
        description="The P17 vocabulary mirror: available | unavailable | unknown.",
    )

    realizes_execution: bool = Field(False, description="Always False -- a read is not execution.")
    executed: bool = Field(False, description="Always False.")
    execution_started: bool = Field(False, description="Always False.")
    execution_allowed: bool = Field(False, description="Always False.")
    result_state: Literal["blocked"] = Field(
        "blocked", description="Always blocked (never executed)."
    )
    read_only: bool = Field(True, description="Always True.")
    redaction_applied: bool = Field(True, description="Always True.")
    reason: Optional[str] = Field(
        None, description="The honest reason when source_status is unknown / unavailable."
    )
    checked_at: datetime = Field(..., description="UTC ISO-8601.")


# -- P17 -> P22 honest mapping ------------------------------------------------


def _classify_backup_status(
    bs: Optional[Any],
) -> tuple[BackupCheckSummary, BackupCheckSourceStatus, Optional[str]]:
    """Map a P17 ``TenantBackupStatus`` (or its absence) to a P22 verdict.

    Returns ``(summary, source_status, reason)``. source_status mapping
    (P22-E0 / E1 / E2; P22-A 4.5 / 10.10):
      - fresh success -> ('fresh_success', 'known')   # the only healthy read
      - stale         -> ('stale',         'degraded') # success is never stale
      - failed        -> ('failed',        'degraded')
      - partial       -> ('partial',       'degraded')
      - in_progress   -> ('in_progress',   'degraded')
      - no outcome    -> ('unknown',       'unknown')  # never healthy
      - source available but no completed backup verdict (e.g. restore-test only)
                      -> ('unknown',       'degraded')  # readable, not healthy

    Never returns ``known`` except for a fresh success. Never raises.
    """
    if bs is None:
        return "unknown", "unknown", _NO_OUTCOME_REASON

    last = getattr(bs, "last_backup_status", None)
    if last == "success":
        return "fresh_success", "known", None
    if last == "stale":
        return "stale", "degraded", "Latest successful backup is outside the 24h freshness window."
    if last == "failed":
        return "failed", "degraded", "Latest backup failed; see failure_reason_redacted."
    if last == "partial":
        return "partial", "degraded", "Latest backup completed partially; see failure_reason_redacted."
    if last == "in_progress":
        return "in_progress", "degraded", "A backup is in progress; no completed verdict yet."
    # last is None (e.g. only a restore-test outcome recorded) or an unrecognized
    # value: the source was readable but there is no completed backup verdict, so
    # the backup status is honestly unknown. 'degraded' (not 'known') because a
    # readable-but-verdict-less source is not healthy; null is never zero.
    return "unknown", "degraded", "Source readable but no completed backup verdict; status unknown."


def _build_read(
    bs: Optional[Any],
    summary: BackupCheckSummary,
    source_status: BackupCheckSourceStatus,
    reason: Optional[str],
    now: datetime,
) -> BackupCheckSourceRead:
    """Assemble a ``BackupCheckSourceRead`` from a P17 status + classification.

    ``failure_reason_redacted`` is re-asserted against the closed allowlist: P17
    already collapses the raw reason via ``redact_failure_reason``, but an
    untrusted value is never carried -- it is forced to ``unknown``.
    """
    failure_reason: Optional[str] = None
    if bs is not None:
        raw_reason = getattr(bs, "failure_reason_redacted", None)
        if raw_reason:
            failure_reason = raw_reason if raw_reason in BACKUP_FAILURE_REASONS else "unknown"

    def _opt(name: str) -> Any:
        return getattr(bs, name, None) if bs is not None else None

    return BackupCheckSourceRead(
        source_status=source_status,
        source_summary=summary,
        last_backup_status=_opt("last_backup_status"),
        last_backup_at=_opt("last_backup_at"),
        restore_test_status=_opt("restore_test_status"),
        last_restore_test_at=_opt("last_restore_test_at"),
        failure_reason_redacted=failure_reason,
        export_available=_opt("export_available"),
        retention_policy=_opt("retention_policy"),
        p17_backup_source_status=_opt("backup_source_status"),
        reason=reason,
        checked_at=now,
    )


def _unavailable_read(now: datetime) -> BackupCheckSourceRead:
    """The honest fail-closed result when the source read failed."""
    return BackupCheckSourceRead(
        source_status="unknown",
        source_summary="unavailable",
        reason=_READ_FAILED_REASON,
        checked_at=now,
    )


# -- The read-only source probe -----------------------------------------------


async def read_backup_check_source(
    db: Any,
    tenant_id: Optional[str] = None,
    now: Optional[datetime] = None,
) -> BackupCheckSourceRead:
    """Read the PROVEN P17-D-C backup source for ``backup.check`` -- READ-ONLY.

    Reuses the P17-D-C durable read path verbatim (no new query, no new source,
    no mutation). ``tenant_id`` scopes the read to a tenant (with the P17
    platform-wide fallback); ``None`` reads the platform-wide outcome via the
    loader's own platform-fallback resolution.

    Never executes, never mutates, never raises: a read failure degrades to an
    honest ``unavailable`` / ``unknown`` fail-closed result, never a 500 and never
    a fabricated healthy status. ``db`` is the async session the P17 reader
    reads through; it is only read.
    """
    now = now or _utcnow()
    scope_id = tenant_id if tenant_id else _PLATFORM_WIDE_SENTINEL
    try:
        reads = await _load_backup_status_map(db, [scope_id], now)
    except Exception:
        return _unavailable_read(now)
    if reads is None:
        # The P17 loader returns None on a read failure -> unavailable for all.
        return _unavailable_read(now)
    read = reads.get(scope_id)
    bs = _build_backup_status(read, now)
    summary, source_status, reason = _classify_backup_status(bs)
    return _build_read(bs, summary, source_status, reason, now)


__all__ = [
    "SOURCE_PROBE_PHASE",
    "PROBE_REALIZES_EXECUTION",
    "BACKUP_CHECK_BINDING",
    "BackupCheckSourceRead",
    "BackupCheckSummary",
    "BackupCheckSourceStatus",
    "read_backup_check_source",
]
