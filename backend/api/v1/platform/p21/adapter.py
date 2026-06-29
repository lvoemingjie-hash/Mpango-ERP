"""P21-D Durable Approval Runtime Adapter -- NON-EXECUTING SKELETON (P21-D-B).

This module is the first runtime substrate of P21-D. It records the locked
adapter design (the exact surface a future P21-D-1 implementation must satisfy)
as importable, testable Python, WITHOUT becoming the live store and WITHOUT
executing anything.

What this skeleton IS:
  - The frozen operation -> durable-table mapping (P21-D design lock 4.1).
  - The new-column population rules (design lock 4.4): ``store_version``,
    ``sequence_no``, ``storage_class``, ``audit_result``, ``confirm``,
    ``metadata_redacted``.
  - The closed P20/P21 value mappings that bridge the in-memory P20-B store to
    the durable enum vocabularies (source-status map, audit-result derivation,
    the no-execution invariants).
  - The ``StoreError`` vocabulary and ``StoreResult`` shape (P21-B
    storage-adapter interface contract, schema plan section 7).
  - The planned ``DurableApprovalStore`` method signatures (create / list / get
    / decide / audit / idempotency-lookup / expire / purge / export).

What this skeleton is NOT:
  - It performs NO database I/O and mutates NO state. Every ``DurableApprovalStore``
    method raises :class:`StoreNotImplementedError`.
  - It is NOT imported by ``api.v1.platform.p20`` (services / routes) or by
    ``api.app``. The running durable approval store stays the in-memory P20-B
    skeleton (``storage == "memory"``). Runtime storage cutover is a separately
    CTO-gated P21-D-2 slice.
  - It adds NO migration, NO alembic change, NO table alteration, NO auth/RBAC/
    session/tenancy/payment change, and NO frontend.

Approval is not execution, and durability is not execution. The adapter
preserves ``execution_allowed == False``, ``executed == False``, and
``execution_gate == "blocked"``, and never runs any P18 action.

Frozen against docs/ai/PLATFORM_PRODUCT_P21_D_DURABLE_APPROVAL_RUNTIME_ADAPTER_DESIGN_LOCK.md
(section 4). Operation surface mirrors the P21-B storage-adapter interface
contract in docs/ai/PLATFORM_PRODUCT_P21_DURABLE_APPROVAL_SCHEMA_PLAN.md
(section 7).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import and_, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

# Re-export the durable value vocabularies so the adapter surface is
# self-contained and the closed-set guarantees are testable from one place.
from api.v1.platform.p21.models import (
    AUDIT_RESULT_VALUES,
    EVENT_TYPE_VALUES,
    SCOPE_KEY_VALUES,
    SOURCE_STATUS_VALUES,
    STATE_VALUES,
    STORAGE_CLASS_VALUES,
    DurableApprovalAuditEvent,
    DurableApprovalDecision,
    DurableApprovalIdempotencyKey,
    DurableApprovalRequest,
)

# P21-D-C concrete adapter consumes the P18 redaction helpers unchanged and
# preserves the P20 response shapes (design lock 4.5 / 4.7). These imports are
# one-way (p21 -> p18 / p20); the P20 routes / services never import p21 (the
# no-cutover source-scan contract in test_platform_p21_durable_approval_adapter
# _skeleton.py guards the reverse direction), so this adds no live coupling.
from api.v1.platform.p18 import services as _p18
from api.v1.platform.p20.schemas import (
    CheckerDecisionSummary,
    DurableApprovalQueue,
    DurableApprovalRecord,
)


# ---------------------------------------------------------------------------
# Phase / liveness markers
# ---------------------------------------------------------------------------

#: The storage_class value the adapter writes for every durable row.
STORAGE_CLASS_DURABLE: str = "durable"

#: Explicit flag: this skeleton is NOT the live running store. The running
#: P20-B store stays in-memory until a separately approved P21-D-2 cutover.
IS_LIVE_STORE: bool = False

#: The P21-D slice this skeleton belongs to (relationship to the design-lock
#: slice map: this is the non-executing definitions + skeleton portion of
#: P21-D-1; the executing implementation and the P21-D-2 cutover remain
#: not-started and CTO-gated).
ADAPTER_PHASE: str = "P21-D-B-skeleton"


# ---------------------------------------------------------------------------
# No-execution invariants (design lock 1.1 / 4.5; P21-A acceptance criterion 1)
# ---------------------------------------------------------------------------

#: A durable approval never permits execution.
EXECUTION_ALLOWED: bool = False
#: A durable approval never executes.
EXECUTED: bool = False
#: The only execution-gate value reachable in P21.
EXECUTION_GATE: str = "blocked"


# ---------------------------------------------------------------------------
# Operation -> durable-table mapping (design lock 4.1 / 4.2)
# ---------------------------------------------------------------------------

#: Each P20-B public operation maps to a single atomic transaction against the
#: listed durable tables (all committed together or not at all).
OPERATION_TABLE_MAP: dict[str, tuple[str, ...]] = {
    "create": (
        "durable_approval_requests",
        "durable_approval_audit_events",
        "durable_approval_idempotency_keys",
    ),
    "decide": (
        "durable_approval_requests",
        "durable_approval_decisions",
        "durable_approval_audit_events",
        "durable_approval_idempotency_keys",
    ),
    "read": (
        "durable_approval_requests",
        "durable_approval_decisions",
        "durable_approval_audit_events",
    ),
    "list": (
        "durable_approval_requests",
    ),
}

#: The in-memory P20-B global that each durable table replaces (design lock 4.1).
INMEMORY_GLOBAL_MAP: dict[str, str] = {
    "_STORE[approval_id]": "durable_approval_requests (+ durable_approval_decisions)",
    "_STORE_BY_CREATE_KEY": "durable_approval_idempotency_keys (scope_key=open)",
    "decision_digest dedup": (
        "durable_approval_idempotency_keys (scope_key=decide) "
        "+ durable_approval_decisions uniqueness"
    ),
    "_AUDIT_LOG": "durable_approval_audit_events",
}

#: The set of all durable tables the adapter targets (T1-T5 from migration 020).
DURABLE_TABLES: frozenset[str] = frozenset(
    (
        "durable_approval_requests",
        "durable_approval_decisions",
        "durable_approval_audit_events",
        "durable_approval_idempotency_keys",
        "durable_approval_retention_jobs",
    )
)


# ---------------------------------------------------------------------------
# New-column population rules (design lock 4.4)
# ---------------------------------------------------------------------------

#: Columns that have no direct in-memory P20-B counterpart and that the adapter
#: must populate. Values are the locked population rules.
NEW_COLUMN_RULES: dict[str, str] = {
    "store_version": "1 at create; bumped by exactly 1 on every state transition.",
    "sequence_no": (
        "per-approval_id monotonic audit sequence; computed inside the "
        "transaction from the current max sequence_no for that approval."
    ),
    "storage_class": "durable (STORAGE_CLASS_DURABLE) for every row the adapter writes.",
    "audit_result": (
        "derived from the transition outcome without information loss "
        "(see AUDIT_RESULT_BY_EVENT_TYPE and derive_audit_result)."
    ),
    "confirm": (
        "the explicit decision confirmation token, persisted verbatim "
        "(already a caller-supplied boolean; not a secret)."
    ),
    "metadata_redacted": (
        "the P10/P18-redacted metadata, persisted; the raw metadata is never persisted."
    ),
}


# ---------------------------------------------------------------------------
# Closed value mappings (P20/P21 compatibility)
# ---------------------------------------------------------------------------

#: P20/P18 registry source status -> durable ``durable_approval_source_status``.
#:
#: The durable vocabulary generalizes P20's three-value ``RegistrySourceStatus``
#: (available / unavailable / unknown): "available" becomes "valid", and the
#: durable set adds "degraded" (a durable-only, never-fabricated-healthy state
#: with no P20 source counterpart). The map is total over the P20 vocabulary and
#: every target is a member of SOURCE_STATUS_VALUES. The adapter never upgrades
#: an unknown / unavailable / degraded source to "valid".
SOURCE_STATUS_MAP: dict[str, str] = {
    "available": "valid",
    "unknown": "unknown",
    "unavailable": "unavailable",
}

#: The durable source-status value the adapter writes when the P18 source cannot
#: be confirmed healthy after a restart / partial outage (unknown is never
#: healthy; design lock 4.6 / P21-A 3.6).
DEGRADED_SOURCE_STATUS: str = "degraded"

#: Proposed default ``audit_result`` derivation keyed by ``event_type``
#: (design lock 4.4). Closed: keyed by exactly EVENT_TYPE_VALUES and every value
#: is a member of AUDIT_RESULT_VALUES. The disambiguation between denied /
#: idempotent / conflict for an ``approval_denied`` event depends on the
#: operation outcome, so the runtime derivation refines this default via
#: :func:`derive_audit_result(event_type, outcome)`. The exact final mapping is
#: fixed in the P21-D-1 runtime slice and must lose no information relative to
#: the in-memory event.
AUDIT_RESULT_BY_EVENT_TYPE: dict[str, str] = {
    "approval_opened": "success",
    "approval_decision_recorded": "success",
    "approval_quorum_met": "success",
    "approval_rejected": "success",
    "approval_expired": "expired",
    "approval_cancelled": "success",
    "approval_superseded": "success",
    "approval_failed_validation": "error",
    "approval_read": "success",
    "approval_exported": "success",
    "approval_denied": "denied",
    "approval_purged": "success",
}


def derive_audit_result(event_type: str, outcome: Optional[str] = None) -> str:
    """Derive the durable ``audit_result`` for an event.

    NON-EXECUTING helper (pure): it only reads the closed maps above. It returns
    the closed-vocabulary audit_result for an event type, refining the
    ``approval_denied`` default when an explicit outcome (``idempotent`` /
    ``conflict`` / ``denied``) is supplied by the future runtime caller.

    Raises ``ValueError`` for an unknown event_type or an outcome that is not a
    member of AUDIT_RESULT_VALUES, so the closed-set guarantee is enforced at
    the boundary rather than silently dropping information.
    """
    if event_type not in EVENT_TYPE_VALUES:
        raise ValueError(f"unknown durable event_type: {event_type!r}")
    if outcome is not None and outcome not in AUDIT_RESULT_VALUES:
        raise ValueError(f"unknown durable audit_result outcome: {outcome!r}")
    if outcome is not None:
        return outcome
    return AUDIT_RESULT_BY_EVENT_TYPE[event_type]


# ---------------------------------------------------------------------------
# StoreError vocabulary + StoreResult (schema plan section 7)
# ---------------------------------------------------------------------------

#: The closed ``StoreError`` code vocabulary (schema plan section 7). Every code
#: a future runtime adapter may return; the skeleton never returns any (every
#: method raises StoreNotImplementedError), but the closed set is exposed here so
#: it is testable and frozen.
STORE_ERROR_CODES: frozenset[str] = frozenset(
    (
        "not_authorized",
        "self_decision_denied",
        "decision_conflict",
        "idempotent_replay",
        "expired",
        "terminal",
        "unknown_source",
        "stale_write",
        "read_only",
        "not_found",
        "store_unknown",
    )
)


@dataclass(frozen=True)
class StoreError:
    """A durable-store error carrying a closed-vocabulary code.

    ``unavailable_reason`` reuses the P13/P14 vocabulary (the unknown / degraded
    / read-only fallback, design lock 4.6) when the store cannot confirm state.
    """

    code: str
    message: str = ""
    unavailable_reason: Optional[str] = None

    def __post_init__(self) -> None:
        if self.code not in STORE_ERROR_CODES:
            raise ValueError(
                f"StoreError.code {self.code!r} is not in the closed STORE_ERROR_CODES set"
            )


@dataclass(frozen=True)
class StoreResult:
    """Result[T, StoreError] convention (schema plan section 7).

    Exactly one of ``value`` / ``error`` is set. ``restart_safe`` is the additive
    durability badge (true once the durable adapter is live; the skeleton never
    produces a result because it does not execute). ``execution_allowed`` /
    ``executed`` are always false (no-execution invariant).
    """

    value: Any = None
    error: Optional[StoreError] = None
    restart_safe: bool = False
    execution_allowed: bool = EXECUTION_ALLOWED
    executed: bool = EXECUTED
    storage_class: str = STORAGE_CLASS_DURABLE

    @property
    def ok(self) -> bool:
        return self.error is None

    @classmethod
    def ok_value(cls, value: Any) -> "StoreResult":
        return cls(value=value, restart_safe=True)

    @classmethod
    def err(
        cls,
        code: str,
        message: str = "",
        unavailable_reason: Optional[str] = None,
    ) -> "StoreResult":
        return cls(error=StoreError(code=code, message=message,
                                    unavailable_reason=unavailable_reason))


class StoreNotImplementedError(NotImplementedError):
    """Raised by every adapter method in the P21-D-B skeleton.

    Signals that the planned surface exists and is typed but is deliberately
    non-executing: the running store is still the in-memory P20-B skeleton and
    the durable adapter implementation is deferred to the separately CTO-gated
    P21-D-1 runtime slice.
    """


# ---------------------------------------------------------------------------
# Planned store surface (schema plan section 7; design lock section 4.2)
# ---------------------------------------------------------------------------


class DurableApprovalStore:
    """NON-EXECUTING skeleton of the durable approval store adapter.

    Every method raises :class:`StoreNotImplementedError`. The signatures and
    docstrings freeze the surface a future P21-D-1 implementation must satisfy,
    preserving the P20 service-function contract (create / list / read / decide)
    while adding the durable idempotency, audit, retention, and export
    operations. Nothing here performs database I/O, mutates state, executes a
    controlled action, or mutates tenant / P17 registry data.

    The class is NOT instantiated or imported by the P20 routes / services: the
    running store is the P20-B in-memory skeleton until a P21-D-2 cutover.
    """

    __slots__ = ()

    #: Marks this implementation as the non-executing skeleton.
    is_live_store: bool = IS_LIVE_STORE

    def create_request(
        self,
        payload: Any,
        idempotency_key_digest: str,
        *,
        payload_digest: str,
        actor: Optional[str] = None,
        actor_role: str = "system",
        identity_context: str = "unknown",
    ) -> StoreResult:
        """Open a durable approval request at ``pending_review``.

        Lock: redacts reason/metadata; opens T1 with ``execution_allowed=false``,
        ``executed=false``, ``storage_class=durable``, ``store_version=1``; emits
        ``approval_opened`` (sequence_no=1); writes the ``open`` idempotency row.
        Idempotent on matching ``payload_digest``; conflicting ``payload_digest``
        -> ``decision_conflict``. Never executes.
        """
        raise StoreNotImplementedError(
            "DurableApprovalStore.create_request is a P21-D-B non-executing skeleton; "
            "the durable adapter implementation is deferred to the CTO-gated P21-D-1 "
            "slice. The running store is the in-memory P20-B skeleton."
        )

    def list_requests(
        self,
        filters: Optional[dict] = None,
        page: Optional[Any] = None,
    ) -> StoreResult:
        """Read-only filtered queue over T1 (state / action_type / tenant_id).

        Redacted and audited as ``approval_read``. Never writes; ``executed``
        stays false.
        """
        raise StoreNotImplementedError(
            "DurableApprovalStore.list_requests is a P21-D-B non-executing skeleton."
        )

    def get_request(self, approval_id: str) -> StoreResult:
        """Read-only fetch of one durable record (T1 + decisions + audit).

        Returns state, maker, checkers, quorum_*, decision, with
        ``execution_allowed=false`` / ``executed=false``. Audited as
        ``approval_read``.
        """
        raise StoreNotImplementedError(
            "DurableApprovalStore.get_request is a P21-D-B non-executing skeleton."
        )

    def submit_decision(
        self,
        approval_id: str,
        decision: str,
        approver_id: str,
        reason: str,
        idempotency_key_digest: str,
        *,
        confirm: bool,
        payload_digest: str,
        actor: Optional[str] = None,
    ) -> StoreResult:
        """Record one checker decision in a single transaction.

        Enforces maker-checker / distinct-checker / reject-final / source-honesty
        (design lock 4.2-4.3) with ``store_version`` optimistic locking on the
        quorum race. Rejects self-decision, conflict, terminal, non-identity-only,
        and unknown-source writes. Never sets ``execution_allowed=true`` or
        ``executed=true``. Duplicate with matching ``decision_digest`` is an
        idempotent replay; a mismatch is a ``decision_conflict``.
        """
        raise StoreNotImplementedError(
            "DurableApprovalStore.submit_decision is a P21-D-B non-executing skeleton."
        )

    def append_audit_event(self, event: Any) -> StoreResult:
        """INSERT-only into T3 (append-only, redacted).

        Used by the adapter internally and by SYSTEM jobs. Never UPDATE / DELETE
        (purge is whole-record via purge_eligible_records).
        """
        raise StoreNotImplementedError(
            "DurableApprovalStore.append_audit_event is a P21-D-B non-executing skeleton."
        )

    def find_by_idempotency_digest(
        self,
        scope_key: str,
        scope_id: str,
        idempotency_key_digest: str,
        payload_digest: str,
    ) -> StoreResult:
        """Idempotency lookup over T4.

        Returns the prior ``result_ref`` when the digest matches AND
        ``payload_digest`` matches (idempotent_replay); returns a conflict marker
        when the digest matches but the payload differs. The raw key is never
        passed in (the caller hashes first).
        """
        raise StoreNotImplementedError(
            "DurableApprovalStore.find_by_idempotency_digest is a P21-D-B "
            "non-executing skeleton."
        )

    def expire_due_requests(self, now: datetime) -> StoreResult:
        """SYSTEM sweep: expire pending rows past ``expires_at`` and approved
        rows past durable TTL to ``state=expired``; emit ``approval_expired`` per
        row. Idempotent. Never executes.
        """
        raise StoreNotImplementedError(
            "DurableApprovalStore.expire_due_requests is a P21-D-B non-executing skeleton."
        )

    def purge_eligible_records(self, now: datetime) -> StoreResult:
        """SYSTEM sweep: whole-record purge of terminal rows past
        ``durable_retain_until`` EXCLUDING ``retention_class=legal_hold``; emit
        ``approval_purged`` per bundle. Never an operator call; never skips the
        purge audit event.
        """
        raise StoreNotImplementedError(
            "DurableApprovalStore.purge_eligible_records is a P21-D-B non-executing skeleton."
        )

    def export_record(self, approval_id: str, window: Any) -> StoreResult:
        """Identity-only super_admin export of a REDACTED retention bundle.

        Returns ONLY export-safe fields (P21-A 7.4); never a raw key / secret /
        DSN / host:port / token / password / cookie / auth header / body /
        payload. Audited as ``approval_exported``. Deletes nothing.
        """
        raise StoreNotImplementedError(
            "DurableApprovalStore.export_record is a P21-D-B non-executing skeleton."
        )


#: The planned method surface of :class:`DurableApprovalStore` (frozen; cross
#: checked in tests). The base adapter (create/list/get/decide) is required for
#: the P20 service-function contract; the rest are durable-only operations.
PLANNED_METHODS: tuple[str, ...] = (
    "create_request",
    "list_requests",
    "get_request",
    "submit_decision",
    "append_audit_event",
    "find_by_idempotency_digest",
    "expire_due_requests",
    "purge_eligible_records",
    "export_record",
)


# ===========================================================================
# P21-D-C concrete durable approval store adapter (DB read/write implementation)
# ===========================================================================
#
# This section is the P21-D-C runtime implementation. It adds a CONCRETE adapter
# (:class:`DurableApprovalStoreAdapter`) that realizes the frozen surface above
# against the five merged P21-C1 public durable approval tables, through an
# injected async SQLAlchemy session. It mirrors the P20-B in-memory service
# logic EXACTLY (P20-B-R1 identity binding, maker-checker, distinct-checker,
# reject-final, quorum, source-honesty, redaction, digest-only idempotency) and
# persists every operation as a single atomic, restart-safe transaction.
#
# NO RUNTIME STORAGE CUTOVER (the directive's hard constraint). This class is
# never imported by ``api.v1.platform.p20`` (services / routes) or by
# ``api.app``; the running durable approval store stays the in-memory P20-B
# skeleton (``storage == "memory"``). The concrete adapter is exercised only by
# platform-only tests against an ephemeral DB. ``is_live_store`` is False.
#
# NO EXECUTION. ``execution_allowed`` stays False, ``executed`` stays False,
# ``execution_gate`` stays "blocked", and no P18 controlled action is ever run.
#
# The frozen non-executing :class:`DurableApprovalStore` skeleton and every
# constant / mapping above are unchanged; this section is purely additive.
# ===========================================================================


#: Implementation phase marker for the concrete adapter. The frozen skeleton
#: (:class:`DurableApprovalStore`, ``ADAPTER_PHASE``) remains the non-executing
#: P21-D-B surface; this marker identifies the P21-D-C concrete realization.
DURABLE_ADAPTER_IMPLEMENTATION_PHASE: str = "P21-D-C-implementation"

#: Reverse map: durable ``durable_approval_source_status`` -> P20
#: ``RegistrySourceStatus``, so adapter responses preserve the P20 source_status
#: vocabulary (design lock 4.5). ``degraded`` has no P20 counterpart and maps to
#: ``unknown`` (unknown is never healthy; design lock 4.6 / P21-A 3.6).
_DURABLE_TO_P20_SOURCE_STATUS: dict[str, str] = {
    "valid": "available",
    "unknown": "unknown",
    "unavailable": "unavailable",
    "degraded": "unknown",
}

#: Terminal P20-B states whose transitions are not implemented (mirrors P20-B
#: services): an approval in any of these states is terminal and cannot be
# decided.
_TERMINAL_UNIMPLEMENTED_STATES: frozenset[str] = frozenset(
    ("expired", "cancelled", "superseded", "failed_validation")
)


# -- Pure helpers (mirror P20-B services; self-contained, no global state) --


def _digest(value: Optional[str]) -> str:
    """One-way SHA-256 hex digest of an idempotency key (raw key never stored)."""
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(value: Optional[datetime]) -> Optional[datetime]:
    """Normalize a datetime to aware UTC; None stays None (mirrors P20-B)."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _to_uuid(value: Any) -> Optional[UUID]:
    """Coerce a str / UUID / None to a UUID (or None). Identity-safe (echo is
    handled by the redaction layer; this is only for ORM FK / PK columns)."""
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def _request_digest(
    action_id: Optional[str],
    action_type: Optional[str],
    tenant_id: Optional[str],
    maker: str,
) -> str:
    """SHA-256 of the canonical request envelope (P20-A 3.1). Echo-safe: built
    from action_id / action_type / tenant_id / maker only (never the reason)."""
    raw = "|".join([action_id or "", action_type or "", tenant_id or "", maker or ""])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _create_fingerprint(
    action_type: Optional[str],
    tenant_id: Optional[str],
    maker: str,
    reason_redacted: str,
) -> str:
    """SHA-256 of the REDACTED create envelope. Built from echo-safe (already
    redacted) values so the raw reason is never hashed or persisted; two creates
    with the same redacted payload collide (the dedup intent)."""
    raw = "|".join([action_type or "", tenant_id or "", maker or "", reason_redacted or ""])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _decision_digest(
    approval_id: str,
    checker_actor_id: str,
    decision: str,
    reason_redacted: str,
) -> str:
    """SHA-256 content fingerprint of one checker decision (echo-safe values)."""
    raw = "|".join([approval_id or "", checker_actor_id or "", decision or "", reason_redacted or ""])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class DurableApprovalStoreAdapter:
    """Concrete durable approval store adapter (P21-D-C DB read/write impl).

    Implements the create / read / list / decide operations against the five
    merged P21-C1 public durable approval tables through an injected async
    SQLAlchemy session, mirroring the P20-B in-memory service logic exactly
    while persisting each operation as a single atomic, restart-safe
    transaction (design lock 4.2 / 4.3).

    Identity binding (P20-B-R1), maker-checker, distinct-checker, reject-final,
    quorum, source-honesty, redaction, and digest-only idempotency are enforced
    exactly as in P20-B. ``store_version`` optimistic locking guards the quorum
    race; the P21-B / P21-C1 unique constraints backstop distinct-checker and
    per-key decide idempotency. New durable columns are populated per design
    lock 4.4 (``store_version``, ``sequence_no``, ``storage_class=durable``,
    ``audit_result`` via :func:`derive_audit_result`, ``confirm``,
    ``metadata_redacted``).

    NOT THE LIVE STORE. This class is never imported by P20 routes / services or
    ``api.app`` (no runtime storage cutover); the running store stays the
    in-memory P20-B skeleton. ``is_live_store`` is False. It is exercised only by
    platform-only tests against an ephemeral DB. Approval is not execution and
    durability is not execution: ``execution_allowed`` / ``executed`` stay False
    and ``execution_gate`` stays "blocked"; no P18 action is ever run.

    The retention / export operations (``expire_due_requests``,
    ``purge_eligible_records``, ``export_record``) remain deferred to the
    separately CTO-gated P21-D-future slice; they raise
    :class:`StoreNotImplementedError` here.
    """

    __slots__ = ("_session",)

    #: Explicit flag: this concrete adapter is NOT the live running store. The
    #: running P20-B store stays in-memory until a separately approved P21-D-2
    #: cutover (which this slice does not perform).
    is_live_store: bool = False

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        # The durable approval store is a public-schema platform facility: it is
        # system-scope, not tenant-scoped business data (design lock: tenant_id is
        # a scoped identifier only, never an FK into a business table). Mark the
        # session for the global tenant guardrail bypass (db.tenant_filter) so the
        # durable tables are read/written without a tenant context. This mirrors
        # how the adapter must run once a future P21-D-2 cutover wires it live.
        try:
            from db.tenant_filter import mark_session_as_system

            mark_session_as_system(session, reason="p21_durable_approval_store")
        except Exception:
            # If the tenant filter is absent in a reduced environment, the bypass
            # is unnecessary; never let it block adapter construction.
            pass

    # -- internal helpers ------------------------------------------------

    async def _next_sequence_no(self, approval_id: Optional[UUID]) -> int:
        """Monotonic per-approval audit sequence_no = current max + 1.

        Computed inside the transaction (design lock 4.4). A NULL approval_id
        (a create-time denial before any request row) uses the NULL bucket; the
        ``uq_audit_approval_seq`` partial uniqueness allows multiple NULL rows.
        """
        if approval_id is None:
            stmt = select(func.coalesce(func.max(DurableApprovalAuditEvent.sequence_no), 0)).where(
                DurableApprovalAuditEvent.approval_id.is_(None)
            )
        else:
            stmt = select(func.coalesce(func.max(DurableApprovalAuditEvent.sequence_no), 0)).where(
                DurableApprovalAuditEvent.approval_id == approval_id
            )
        cur = (await self._session.execute(stmt)).scalar_one()
        return int(cur) + 1

    async def _emit_audit(
        self,
        *,
        event_type: str,
        actor_id: Optional[str],
        actor_role: str,
        identity_context: str,
        tenant_id: Optional[str],
        action_id: Optional[str],
        approval_id: Optional[UUID],
        decision: Optional[str],
        previous_status: Optional[str],
        next_status: Optional[str],
        reason: str,
        request_digest: Optional[str],
        quorum_required: int,
        quorum_met: bool,
        correlation_id: Optional[str],
        outcome: Optional[str],
        now: datetime,
    ) -> UUID:
        """Build, add, and flush one durable audit event row; return its id.

        Applies P18 reason redaction internally so a raw reason can never reach
        the audit table. ``audit_result`` is derived via :func:`derive_audit_result`
        (design lock 4.4). Only the REDACTED reason / correlation are persisted.
        """
        seq = await self._next_sequence_no(approval_id)
        audit_result = derive_audit_result(event_type, outcome)
        event = DurableApprovalAuditEvent(
            event_id=uuid4(),
            approval_id=approval_id,
            action_id=_to_uuid(action_id),
            actor_id=actor_id or "",
            actor_role=actor_role,
            identity_context=identity_context,
            event_type=event_type,
            decision=decision,
            audit_result=audit_result,
            previous_status=previous_status,
            next_status=next_status,
            reason_redacted=_p18._redact_reason(reason),
            metadata_redacted=None,
            request_digest=request_digest,
            redaction_applied=True,
            tenant_id=_to_uuid(tenant_id),
            quorum_required=quorum_required,
            quorum_met=quorum_met,
            source_status=None,
            validation_status=None,
            correlation_id=correlation_id,
            sequence_no=seq,
            created_at=now,
        )
        self._session.add(event)
        await self._session.flush()
        return event.event_id

    async def _find_idempotency_row(
        self,
        scope_key: str,
        scope_id: str,
        idempotency_key_digest: str,
    ) -> Optional[DurableApprovalIdempotencyKey]:
        stmt = select(DurableApprovalIdempotencyKey).where(
            DurableApprovalIdempotencyKey.scope_key == scope_key,
            DurableApprovalIdempotencyKey.scope_id == scope_id,
            DurableApprovalIdempotencyKey.idempotency_key_digest == idempotency_key_digest,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    def _build_record(
        self,
        req: DurableApprovalRequest,
        decisions: list[DurableApprovalDecision],
        *,
        result: str,
        message: str,
        now: Optional[datetime],
    ) -> DurableApprovalRecord:
        """Build the uniform P20 response record from durable rows.

        Preserves the P20 DurableApprovalRecord shape exactly (design lock 4.5);
        only ``storage`` becomes ``"durable"`` (additive) and source_status is
        mapped back to the P20 vocabulary. ``execution_allowed`` / ``executed``
        are always False; ``execution_gate`` is always "blocked".
        """
        checkers = [
            CheckerDecisionSummary(
                checker_id=d.checker_actor_id,
                decided_at=d.created_at,
                decision=d.decision,  # type: ignore[arg-type]
                reason_redacted=d.reason_redacted,
                audit_event_id=str(d.audit_event_id),
            )
            for d in sorted(decisions, key=lambda x: x.created_at)
        ]
        return DurableApprovalRecord(
            approval_id=str(req.approval_id),
            action_id=str(req.action_id) if req.action_id else None,
            tenant_id=str(req.tenant_id) if req.tenant_id else None,
            action_type=req.action_type,
            action_class=req.action_class,  # type: ignore[arg-type]
            state=req.state,  # type: ignore[arg-type]
            maker=req.maker_actor_id,
            maker_at=req.maker_at,
            checkers=checkers,
            quorum_required=req.quorum_required,
            quorum_met=bool(req.quorum_met),
            decision=req.decision,  # type: ignore[arg-type]
            reason=req.reason_redacted,
            request_digest=req.request_digest,
            idempotency_key_digest=req.idempotency_key_digest,
            expires_at=req.expires_at,
            durable_retain_until=req.durable_retain_until,
            execution_allowed=False,
            execution_gate="blocked",
            redaction_applied=True,
            storage="durable",
            retention_class=req.retention_class,  # type: ignore[arg-type]
            validation_status=req.validation_status,  # type: ignore[arg-type]
            superseded_by=str(req.superseded_by) if req.superseded_by else None,
            previous_state=req.previous_state,  # type: ignore[arg-type]
            audit_event_id=str(req.last_audit_event_id) if req.last_audit_event_id else None,
            correlation_id=req.correlation_id,
            source_status=_DURABLE_TO_P20_SOURCE_STATUS.get(req.source_status, "unknown"),  # type: ignore[arg-type]
            result=result,  # type: ignore[arg-type]
            message=message,
            executed=False,
            created_at=req.created_at,
            updated_at=now or req.updated_at,
        )

    # -- public surface: create -----------------------------------------

    async def create_request(
        self,
        *,
        action_id: Optional[str],
        tenant_id: Optional[str],
        action_type: str,
        source_status: str,
        action_class: str,
        maker: Optional[str],
        reason: Optional[str],
        idempotency_key: Optional[str],
        expires_at: Optional[datetime],
        durable_retain_until: Optional[datetime],
        confirm: bool,
        correlation_id: Optional[str],
        metadata: Optional[dict],
        actor: Optional[str],
        actor_role: str,
        identity_context: str,
        retention_class: str = "standard",
    ) -> StoreResult:
        """Open a durable approval request at ``pending_review`` (restart-safe).

        Mirrors P20-B ``create_durable_approval`` exactly: P20-B-R1 identity
        binding, reason / key / confirm / future-expires validation, honest
        source-status storage, digest-only create idempotency, and the
        no-execution defaults. One atomic transaction inserts the request row
        (T1), the ``approval_opened`` audit event (T3, sequence_no = 1), and the
        ``open`` idempotency row (T4). Never executes; never mutates tenant /
        P17 data. Returns a :class:`StoreResult` whose value is the
        :class:`DurableApprovalRecord` on success or an error on denial.
        """
        now = _now()
        raw_reason = (reason or "").strip()
        raw_key = (idempotency_key or "").strip()
        raw_maker = (maker or "").strip()
        safe_reason = _p18._redact_reason(raw_reason)
        safe_correlation_id = _p18._sanitize_text(correlation_id)
        redacted_md = _p18.redact_metadata(metadata)
        bound_maker = _p18._sanitize_text(actor) if actor else None
        safe_action_type = _p18._sanitize_text(action_type) or action_type
        durable_source = SOURCE_STATUS_MAP.get(source_status, source_status)
        validation_status = "valid" if source_status == "available" else "source_unknown"
        quorum_required = 2 if action_class != "read" else 1

        async def denied(message: str, result_code: str, outcome: str) -> StoreResult:
            await self._emit_audit(
                event_type="approval_denied",
                actor_id=actor,
                actor_role=actor_role,
                identity_context=identity_context,
                tenant_id=tenant_id,
                action_id=action_id,
                approval_id=None,
                decision=None,
                previous_status=None,
                next_status=None,
                reason=safe_reason,
                request_digest=None,
                quorum_required=0,
                quorum_met=False,
                correlation_id=safe_correlation_id,
                outcome=outcome,
                now=now,
            )
            await self._session.commit()
            return StoreResult.err(result_code, message)

        # 1) authenticated actor required (maker binds to the authenticated actor)
        if not bound_maker:
            return await denied(
                "Denied: an authenticated identity-only super_admin actor is required to open a durable approval.",
                "not_authorized", "denied",
            )
        # 2) client-supplied maker must match the authenticated actor (spoof denied)
        if raw_maker and raw_maker != actor:
            return await denied(
                "Denied: the payload maker must match the authenticated actor; identity spoofing is denied.",
                "not_authorized", "denied",
            )
        # 3) reason required
        if not raw_reason:
            return await denied(
                "Denied: a non-empty reason is required to open a durable approval.",
                "not_authorized", "denied",
            )
        # 4) idempotency_key required
        if not raw_key:
            return await denied(
                "Denied: an idempotency_key is required to open a durable approval.",
                "not_authorized", "denied",
            )
        # 5) explicit confirmation required
        if not confirm:
            return await denied(
                "Denied: explicit confirmation (confirm=true) is required to open a durable approval.",
                "not_authorized", "denied",
            )
        # 6) expires_at required and in the future
        exp = _utc(expires_at)
        if exp is None:
            return await denied(
                "Denied: expires_at is required (a durable approval must expire).",
                "not_authorized", "denied",
            )
        if exp <= now:
            return await denied(
                "Denied: expires_at must be in the future.",
                "not_authorized", "denied",
            )
        retain = _utc(durable_retain_until) or exp
        # 7) action_type must be resolvable (honest P18 reference)
        if not action_type:
            return await denied(
                "Denied: the P18 action reference could not be resolved (unknown action_id / action_type); durable approval not recorded.",
                "not_found", "denied",
            )

        # 8) create idempotency: duplicate / conflict (keyed by the key DIGEST)
        create_digest = _digest(raw_key)
        payload_digest = _create_fingerprint(safe_action_type, tenant_id, bound_maker, safe_reason)
        existing = await self._find_idempotency_row("open", "open", create_digest)
        if existing is not None:
            if existing.payload_digest == payload_digest:
                # idempotent replay: return the original record, emit a reopen audit
                existing_req = await self._fetch_request(existing.result_ref)
                if existing_req is None:
                    return StoreResult.err(
                        "store_unknown",
                        "Idempotency replay references a missing approval record (store unknown).",
                    )
                existing_decs = await self._fetch_decisions(existing_req.approval_id)
                await self._emit_audit(
                    event_type="approval_opened",
                    actor_id=actor,
                    actor_role=actor_role,
                    identity_context=identity_context,
                    tenant_id=tenant_id,
                    action_id=existing_req.action_id and str(existing_req.action_id),
                    approval_id=existing_req.approval_id,
                    decision=None,
                    previous_status=None,
                    next_status=existing_req.state,
                    reason=existing_req.reason_redacted,
                    request_digest=existing_req.request_digest,
                    quorum_required=existing_req.quorum_required,
                    quorum_met=bool(existing_req.quorum_met),
                    correlation_id=existing_req.correlation_id,
                    outcome="idempotent",
                    now=now,
                )
                await self._session.commit()
                rec = self._build_record(
                    existing_req,
                    existing_decs,
                    result="duplicate",
                    message=(
                        "Duplicate: idempotency_key already recorded with an identical durable "
                        "approval request; the original record is returned and nothing was executed."
                    ),
                    now=now,
                )
                return StoreResult.ok_value(rec)
            return await denied(
                "Conflict: idempotency_key already recorded with a different durable approval request; rejected and not recorded.",
                "decision_conflict", "conflict",
            )

        # 9) record the durable approval at pending_review; execution_allowed stays False
        approval_id = uuid4()
        stored_action_id = _to_uuid(action_id) if action_id else uuid4()
        req_digest = _request_digest(
            action_id and str(action_id), safe_action_type, tenant_id, bound_maker
        )
        opened_audit_id = await self._emit_audit(
            event_type="approval_opened",
            actor_id=actor,
            actor_role=actor_role,
            identity_context=identity_context,
            tenant_id=tenant_id,
            action_id=action_id,
            approval_id=approval_id,
            decision=None,
            previous_status=None,
            next_status="pending_review",
            reason=safe_reason,
            request_digest=req_digest,
            quorum_required=quorum_required,
            quorum_met=False,
            correlation_id=safe_correlation_id,
            outcome=None,
            now=now,
        )
        request_row = DurableApprovalRequest(
            approval_id=approval_id,
            action_id=stored_action_id,
            tenant_id=_to_uuid(tenant_id),
            action_type=safe_action_type,
            action_class=action_class,
            state="pending_review",
            maker_actor_id=bound_maker,
            maker_at=now,
            quorum_required=quorum_required,
            quorum_met=False,
            decision=None,
            reason_redacted=safe_reason,
            metadata_redacted=redacted_md,
            request_digest=req_digest,
            idempotency_key_digest=create_digest,
            source_status=durable_source,
            validation_status=validation_status,
            execution_allowed=False,
            execution_gate="blocked",
            executed=False,
            redaction_applied=True,
            storage_class=STORAGE_CLASS_DURABLE,
            retention_class=retention_class,
            expires_at=exp,
            durable_retain_until=retain,
            superseded_by=None,
            previous_state=None,
            last_audit_event_id=opened_audit_id,
            correlation_id=safe_correlation_id,
            store_version=1,
            created_at=now,
            updated_at=now,
        )
        self._session.add(request_row)
        idem_row = DurableApprovalIdempotencyKey(
            idempotency_id=uuid4(),
            scope_key="open",
            scope_id="open",
            idempotency_key_digest=create_digest,
            payload_digest=payload_digest,
            result_ref=approval_id,
            first_seen_at=now,
            last_seen_at=now,
        )
        self._session.add(idem_row)
        try:
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            return StoreResult.err("decision_conflict", "Conflict: concurrent create collision; rejected.")
        rec = self._build_record(
            request_row, [], result="recorded",
            message=(
                "Recorded: the durable approval request was recorded at pending_review and audited. "
                "No action was executed and no tenant state was changed."
            ),
            now=now,
        )
        return StoreResult.ok_value(rec)

    # -- public surface: decide -----------------------------------------

    async def submit_decision(
        self,
        approval_id: str,
        *,
        decision: Optional[str],
        approver_id: Optional[str],
        reason: Optional[str],
        idempotency_key: Optional[str],
        confirm: bool,
        correlation_id: Optional[str],
        metadata: Optional[dict],
        actor: Optional[str],
        actor_role: str,
        identity_context: str,
    ) -> StoreResult:
        """Record one checker's approve / reject decision (single transaction).

        Mirrors P20-B ``submit_decision`` exactly: P20-B-R1 identity binding,
        decision / reason / key / confirm validation, unimplemented-terminal
        rejection, maker-checker separation, reject-final, distinct-checker
        idempotency / conflict, source-honesty for approve, and quorum with
        ``store_version`` optimistic locking. Never sets ``execution_allowed`` /
        ``executed`` true. Returns a :class:`StoreResult`.
        """
        now = _now()
        raw_reason = (reason or "").strip()
        raw_key = (idempotency_key or "").strip()
        raw_approver = (approver_id or "").strip()
        safe_reason = _p18._redact_reason(raw_reason)
        safe_correlation_id = _p18._sanitize_text(correlation_id)
        _p18.redact_metadata(metadata)  # redact in place (defense in depth)
        key_digest = _digest(raw_key)
        bound_approver = _p18._sanitize_text(actor) if actor else None

        req = await self._fetch_request(_to_uuid(approval_id))
        decisions = await self._fetch_decisions(_to_uuid(approval_id)) if req is not None else []

        async def denied(message: str, result_code: str, outcome: str) -> StoreResult:
            await self._emit_audit(
                event_type="approval_denied",
                actor_id=actor,
                actor_role=actor_role,
                identity_context=identity_context,
                tenant_id=str(req.tenant_id) if req and req.tenant_id else None,
                action_id=str(req.action_id) if req and req.action_id else None,
                approval_id=req.approval_id if req else None,
                decision=None,
                previous_status=req.state if req else None,
                next_status=req.state if req else None,
                reason=safe_reason,
                request_digest=req.request_digest if req else None,
                quorum_required=req.quorum_required if req else 0,
                quorum_met=bool(req.quorum_met) if req else False,
                correlation_id=safe_correlation_id,
                outcome=outcome,
                now=now,
            )
            await self._session.commit()
            return StoreResult.err(result_code, message)

        if req is None:
            return await denied("Denied: approval_id not found.", "not_found", "denied")
        # 1) authenticated actor required
        if not bound_approver:
            return await denied(
                "Denied: an authenticated identity-only super_admin actor is required to record a decision.",
                "not_authorized", "denied",
            )
        # 2) client-supplied approver_id must match the authenticated actor
        if raw_approver and raw_approver != actor:
            return await denied(
                "Denied: the payload approver_id must match the authenticated actor; identity spoofing is denied.",
                "not_authorized", "denied",
            )
        # 3) decision must be approve | reject
        if decision not in ("approve", "reject"):
            return await denied("Denied: decision must be 'approve' or 'reject'.", "not_authorized", "denied")
        # 4) reason / idempotency_key / confirmation required
        if not raw_reason:
            return await denied("Denied: a non-empty reason is required for a decision.", "not_authorized", "denied")
        if not raw_key:
            return await denied("Denied: an idempotency_key is required for a decision.", "not_authorized", "denied")
        if not confirm:
            return await denied("Denied: explicit confirmation (confirm=true) is required for a decision.", "not_authorized", "denied")
        # 5) unimplemented terminal transitions are explicitly rejected
        if req.state in _TERMINAL_UNIMPLEMENTED_STATES:
            return await denied(
                "Denied: the '%s' state transition is not implemented in P20-B; the approval is terminal and cannot be decided." % req.state,
                "terminal", "denied",
            )
        # 6) maker-checker separation
        if bound_approver == req.maker_actor_id:
            return await denied(
                "Denied: maker-checker separation forbids the maker from approving / rejecting their own durable approval.",
                "self_decision_denied", "denied",
            )

        existing = next((d for d in decisions if d.checker_actor_id == bound_approver), None)

        # 7) already-rejected approval: reject is final
        if req.state == "rejected":
            if existing is not None and existing.decision == decision:
                await self._emit_audit(
                    event_type="approval_rejected",
                    actor_id=actor, actor_role=actor_role, identity_context=identity_context,
                    tenant_id=str(req.tenant_id) if req.tenant_id else None,
                    action_id=str(req.action_id) if req.action_id else None,
                    approval_id=req.approval_id, decision="reject",
                    previous_status="rejected", next_status="rejected",
                    reason=safe_reason, request_digest=req.request_digest,
                    quorum_required=req.quorum_required, quorum_met=False,
                    correlation_id=safe_correlation_id, outcome="idempotent", now=now,
                )
                await self._session.commit()
                rec = self._build_record(req, decisions, result="duplicate",
                    message="Duplicate: this checker already recorded this decision; reject is final. Nothing was executed.", now=now)
                return StoreResult.ok_value(rec)
            return await denied(
                "Conflict: the durable approval is already rejected; reject is final and no further decision is accepted.",
                "decision_conflict", "conflict",
            )

        # 8) quorum-met approval (approved_execution_blocked): no further state change
        if req.state == "approved_execution_blocked":
            if decision == "approve" and (existing is None or existing.decision == "approve"):
                rec = self._build_record(req, decisions, result="duplicate",
                    message="Duplicate: the durable approval already reached quorum (approved_execution_blocked); the approve is idempotent. Nothing was executed.", now=now)
                return StoreResult.ok_value(rec)
            return await denied(
                "Conflict: the durable approval already reached quorum (approved_execution_blocked); a reject after quorum is rejected.",
                "decision_conflict", "conflict",
            )

        # 9) pending_review -> apply the decision
        if existing is not None:
            if existing.decision == decision:
                rec = self._build_record(req, decisions, result="duplicate",
                    message="Duplicate: this checker already recorded this decision; nothing changed and nothing was executed.", now=now)
                return StoreResult.ok_value(rec)
            return await denied(
                "Conflict: this checker already recorded a different decision on this durable approval; a checker cannot flip.",
                "decision_conflict", "conflict",
            )

        # source-honesty: approve requires a verified-available P18 source
        if decision == "approve" and req.validation_status != "valid":
            return await denied(
                "Denied: the underlying P18 source status is '%s'; an approve requires an available source. Nothing was executed." % req.source_status,
                "unknown_source", "denied",
            )

        content_digest = _decision_digest(approval_id, bound_approver, decision, safe_reason)
        redacted_md = _p18.redact_metadata(metadata)

        if decision == "reject":
            recorded_id = await self._emit_audit(
                event_type="approval_decision_recorded",
                actor_id=actor, actor_role=actor_role, identity_context=identity_context,
                tenant_id=str(req.tenant_id) if req.tenant_id else None,
                action_id=str(req.action_id) if req.action_id else None,
                approval_id=req.approval_id, decision="reject",
                previous_status=req.state, next_status="rejected",
                reason=safe_reason, request_digest=req.request_digest,
                quorum_required=req.quorum_required, quorum_met=False,
                correlation_id=safe_correlation_id, outcome=None, now=now,
            )
            self._session.add(DurableApprovalDecision(
                decision_id=uuid4(), approval_id=req.approval_id,
                checker_actor_id=bound_approver, decision="reject",
                reason_redacted=safe_reason, metadata_redacted=redacted_md,
                idempotency_key_digest=key_digest, decision_digest=content_digest,
                confirm=confirm, audit_event_id=recorded_id,
                correlation_id=safe_correlation_id, created_at=now,
            ))
            self._session.add(DurableApprovalIdempotencyKey(
                idempotency_id=uuid4(), scope_key="decide", scope_id=str(req.approval_id),
                idempotency_key_digest=key_digest, payload_digest=content_digest,
                result_ref=req.approval_id, first_seen_at=now, last_seen_at=now,
            ))
            rejected_id = await self._emit_audit(
                event_type="approval_rejected",
                actor_id=actor, actor_role=actor_role, identity_context=identity_context,
                tenant_id=str(req.tenant_id) if req.tenant_id else None,
                action_id=str(req.action_id) if req.action_id else None,
                approval_id=req.approval_id, decision="reject",
                previous_status=req.state, next_status="rejected",
                reason=safe_reason, request_digest=req.request_digest,
                quorum_required=req.quorum_required, quorum_met=False,
                correlation_id=safe_correlation_id, outcome=None, now=now,
            )
            bumped = await self._optimistic_update(
                req, new_state="rejected", new_decision="reject",
                quorum_met=False, last_audit_event_id=rejected_id, now=now,
            )
            if not bumped:
                return StoreResult.err("stale_write", "Conflict: a concurrent decision committed first; this write was rolled back.")
            await self._session.commit()
            refreshed = await self._fetch_request(req.approval_id)
            refreshed_decs = await self._fetch_decisions(req.approval_id)
            rec = self._build_record(refreshed,  # type: ignore[arg-type]
                refreshed_decs, result="rejected",
                message="Rejected: a checker rejected the durable approval; reject is final for this approval_id. Nothing was executed.", now=now)
            return StoreResult.ok_value(rec)

        # decision == "approve"
        recorded_id = await self._emit_audit(
            event_type="approval_decision_recorded",
            actor_id=actor, actor_role=actor_role, identity_context=identity_context,
            tenant_id=str(req.tenant_id) if req.tenant_id else None,
            action_id=str(req.action_id) if req.action_id else None,
            approval_id=req.approval_id, decision="approve",
            previous_status=req.state, next_status="pending_review",
            reason=safe_reason, request_digest=req.request_digest,
            quorum_required=req.quorum_required, quorum_met=False,
            correlation_id=safe_correlation_id, outcome=None, now=now,
        )
        self._session.add(DurableApprovalDecision(
            decision_id=uuid4(), approval_id=req.approval_id,
            checker_actor_id=bound_approver, decision="approve",
            reason_redacted=safe_reason, metadata_redacted=redacted_md,
            idempotency_key_digest=key_digest, decision_digest=content_digest,
            confirm=confirm, audit_event_id=recorded_id,
            correlation_id=safe_correlation_id, created_at=now,
        ))
        self._session.add(DurableApprovalIdempotencyKey(
            idempotency_id=uuid4(), scope_key="decide", scope_id=str(req.approval_id),
            idempotency_key_digest=key_digest, payload_digest=content_digest,
            result_ref=req.approval_id, first_seen_at=now, last_seen_at=now,
        ))
        try:
            approve_count = 1 + sum(1 for d in decisions if d.decision == "approve")
            if approve_count >= req.quorum_required:
                quorum_id = await self._emit_audit(
                    event_type="approval_quorum_met",
                    actor_id=actor, actor_role=actor_role, identity_context=identity_context,
                    tenant_id=str(req.tenant_id) if req.tenant_id else None,
                    action_id=str(req.action_id) if req.action_id else None,
                    approval_id=req.approval_id, decision="approve",
                    previous_status=req.state, next_status="approved_execution_blocked",
                    reason=safe_reason, request_digest=req.request_digest,
                    quorum_required=req.quorum_required, quorum_met=True,
                    correlation_id=safe_correlation_id, outcome=None, now=now,
                )
                bumped = await self._optimistic_update(
                    req, new_state="approved_execution_blocked", new_decision="approve",
                    quorum_met=True, last_audit_event_id=quorum_id, now=now,
                )
                if not bumped:
                    return StoreResult.err("stale_write", "Conflict: a concurrent decision committed first; this write was rolled back.")
                await self._session.commit()
                refreshed = await self._fetch_request(req.approval_id)
                refreshed_decs = await self._fetch_decisions(req.approval_id)
                rec = self._build_record(refreshed,  # type: ignore[arg-type]
                    refreshed_decs, result="approved",
                    message="Approved: durable approval quorum was met and the approval resolved to approved_execution_blocked. The action was NOT executed; execution_allowed is false and no tenant state changed.", now=now)
                return StoreResult.ok_value(rec)
            # quorum not yet met -> stays pending_review (no state transition, no version bump)
            await self._session.commit()
            refreshed = await self._fetch_request(req.approval_id)
            refreshed_decs = await self._fetch_decisions(req.approval_id)
            rec = self._build_record(refreshed,  # type: ignore[arg-type]
                refreshed_decs, result="quorum_pending",
                message="Quorum pending: the checker approve was recorded; the durable approval stays pending_review until the quorum of distinct checkers is met. Nothing was executed.", now=now)
            return StoreResult.ok_value(rec)
        except IntegrityError:
            await self._session.rollback()
            return StoreResult.err("decision_conflict", "Conflict: a duplicate checker / idempotency collision was rejected.")

    async def _optimistic_update(
        self,
        req: DurableApprovalRequest,
        *,
        new_state: str,
        new_decision: str,
        quorum_met: bool,
        last_audit_event_id: UUID,
        now: datetime,
    ) -> bool:
        """Advance the request with store_version optimistic locking.

        ``UPDATE ... WHERE approval_id = ? AND store_version = ?``; returns False
        (and rolls back) when zero rows match (a concurrent conflicting decision
        committed first). Exactly one transition commits (design lock 4.3 / C8).
        """
        stmt = update(DurableApprovalRequest).where(
            DurableApprovalRequest.approval_id == req.approval_id,
            DurableApprovalRequest.store_version == req.store_version,
        ).values(
            state=new_state,
            decision=new_decision,
            quorum_met=quorum_met,
            previous_state=req.state,
            store_version=req.store_version + 1,
            last_audit_event_id=last_audit_event_id,
            updated_at=now,
        )
        res = await self._session.execute(stmt)
        if res.rowcount == 0:
            await self._session.rollback()
            return False
        return True

    # -- public surface: read / list ------------------------------------

    async def get_request(self, approval_id: str) -> StoreResult:
        """Read-only fetch of one durable record; emits ``approval_read`` audit.

        Returns state, maker, checkers, quorum_*, decision with
        ``execution_allowed=false`` / ``executed=false``. The read is audited as
        ``approval_read`` (design lock 4.2). Not found -> ``not_found`` error.
        """
        now = _now()
        req = await self._fetch_request(_to_uuid(approval_id))
        if req is None:
            return StoreResult.err("not_found", "Denied: approval_id not found.")
        decisions = await self._fetch_decisions(req.approval_id)
        await self._emit_audit(
            event_type="approval_read",
            actor_id=req.maker_actor_id,
            actor_role="system",
            identity_context="system",
            tenant_id=str(req.tenant_id) if req.tenant_id else None,
            action_id=str(req.action_id) if req.action_id else None,
            approval_id=req.approval_id,
            decision=None,
            previous_status=req.state,
            next_status=req.state,
            reason=req.reason_redacted,
            request_digest=req.request_digest,
            quorum_required=req.quorum_required,
            quorum_met=bool(req.quorum_met),
            correlation_id=req.correlation_id,
            outcome=None,
            now=now,
        )
        await self._session.commit()
        rec = self._build_record(req, decisions, result="recorded",
            message="Read: durable approval record (durable store). Nothing was executed.", now=now)
        return StoreResult.ok_value(rec)

    async def list_requests(
        self,
        filters: Optional[dict] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> StoreResult:
        """Read-only filtered queue over T1 (state / action_type / tenant_id).

        Mirrors P20-B ``list_durable_approvals``. No audit write (design lock
        4.2 list is read-only); ``executed`` stays False.
        """
        safe_limit = max(1, min(int(limit), 100))
        safe_offset = max(0, int(offset))
        filters = filters or {}
        stmt = select(DurableApprovalRequest).order_by(
            DurableApprovalRequest.created_at.desc()
        )
        if filters.get("status"):
            stmt = stmt.where(DurableApprovalRequest.state == filters["status"])
        if filters.get("action_type"):
            stmt = stmt.where(DurableApprovalRequest.action_type == filters["action_type"])
        if filters.get("tenant_id"):
            stmt = stmt.where(DurableApprovalRequest.tenant_id == _to_uuid(filters["tenant_id"]))
        page_ids_stmt = stmt.offset(safe_offset).limit(safe_limit)
        page_rows = list((await self._session.execute(page_ids_stmt)).scalars().all())
        total_stmt = select(func.count()).select_from(DurableApprovalRequest)
        if filters.get("status"):
            total_stmt = total_stmt.where(DurableApprovalRequest.state == filters["status"])
        if filters.get("action_type"):
            total_stmt = total_stmt.where(DurableApprovalRequest.action_type == filters["action_type"])
        if filters.get("tenant_id"):
            total_stmt = total_stmt.where(DurableApprovalRequest.tenant_id == _to_uuid(filters["tenant_id"]))
        total = int((await self._session.execute(total_stmt)).scalar_one())
        items: list[DurableApprovalRecord] = []
        if page_rows:
            ids = [r.approval_id for r in page_rows]
            dec_rows = list(
                (await self._session.execute(
                    select(DurableApprovalDecision).where(DurableApprovalDecision.approval_id.in_(ids))
                )).scalars().all()
            )
            by_req: dict[UUID, list[DurableApprovalDecision]] = {}
            for d in dec_rows:
                by_req.setdefault(d.approval_id, []).append(d)
            for r in page_rows:
                items.append(self._build_record(
                    r, by_req.get(r.approval_id, []),
                    result="recorded",
                    message="Queued: durable approval record (durable queue). Nothing was executed.",
                    now=r.updated_at,
                ))
        queue = DurableApprovalQueue(
            items=items, total=total, limit=safe_limit, offset=safe_offset,
            storage="durable", executed=False,
        )
        return StoreResult.ok_value(queue)

    # -- public surface: idempotency lookup + audit append --------------

    async def find_by_idempotency_digest(
        self,
        scope_key: str,
        scope_id: str,
        idempotency_key_digest: str,
        payload_digest: str,
    ) -> StoreResult:
        """Idempotency lookup over T4.

        Returns ``{"matched": True, "idempotent": bool, "result_ref": ...}``:
        when the digest matches AND ``payload_digest`` matches it is an
        idempotent replay (``idempotent=True``); when the digest matches but the
        payload differs it is a conflict (``idempotent=False``). No match ->
        ``matched=False``. The raw key is never passed in.
        """
        row = await self._find_idempotency_row(scope_key, scope_id, idempotency_key_digest)
        if row is None:
            return StoreResult.ok_value({"matched": False, "idempotent": False, "result_ref": None})
        return StoreResult.ok_value({
            "matched": True,
            "idempotent": row.payload_digest == payload_digest,
            "result_ref": str(row.result_ref) if row.result_ref else None,
        })

    async def append_audit_event(self, event: dict) -> StoreResult:
        """INSERT-only into T3 (append-only, redacted). Used internally and by
        SYSTEM jobs. Never UPDATE / DELETE. ``audit_result`` is derived from the
        supplied ``event_type`` / optional ``outcome``.
        """
        now = _now()
        audit_id = await self._emit_audit(
            event_type=event.get("event_type", "approval_read"),
            actor_id=event.get("actor_id"),
            actor_role=event.get("actor_role", "system"),
            identity_context=event.get("identity_context", "system"),
            tenant_id=event.get("tenant_id"),
            action_id=event.get("action_id"),
            approval_id=_to_uuid(event.get("approval_id")),
            decision=event.get("decision"),
            previous_status=event.get("previous_status"),
            next_status=event.get("next_status"),
            reason=event.get("reason", ""),
            request_digest=event.get("request_digest"),
            quorum_required=int(event.get("quorum_required", 0) or 0),
            quorum_met=bool(event.get("quorum_met", False)),
            correlation_id=event.get("correlation_id"),
            outcome=event.get("outcome"),
            now=now,
        )
        await self._session.commit()
        return StoreResult.ok_value({"event_id": str(audit_id)})

    # -- deferred durable-only operations (P21-D-future, CTO-gated) -----

    async def expire_due_requests(self, now: datetime) -> StoreResult:
        raise StoreNotImplementedError(
            "DurableApprovalStoreAdapter.expire_due_requests is deferred to the "
            "separately CTO-gated P21-D-future retention slice."
        )

    async def purge_eligible_records(self, now: datetime) -> StoreResult:
        raise StoreNotImplementedError(
            "DurableApprovalStoreAdapter.purge_eligible_records is deferred to the "
            "separately CTO-gated P21-D-future retention slice."
        )

    async def export_record(self, approval_id: str, window: Any) -> StoreResult:
        raise StoreNotImplementedError(
            "DurableApprovalStoreAdapter.export_record is deferred to the "
            "separately CTO-gated P21-D-future export slice."
        )

    # -- fetch helpers (read-only) --------------------------------------

    async def _fetch_request(self, approval_id: Optional[UUID]) -> Optional[DurableApprovalRequest]:
        if approval_id is None:
            return None
        # populate_existing bypasses the identity map so a re-fetch after a Core
        # store_version UPDATE + commit returns the fresh DB state (the session
        # uses expire_on_commit=False so create can read post-commit attributes).
        stmt = select(DurableApprovalRequest).execution_options(populate_existing=True).where(
            DurableApprovalRequest.approval_id == approval_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def _fetch_decisions(self, approval_id: Optional[UUID]) -> list[DurableApprovalDecision]:
        if approval_id is None:
            return []
        stmt = select(DurableApprovalDecision).execution_options(populate_existing=True).where(
            DurableApprovalDecision.approval_id == approval_id
        ).order_by(DurableApprovalDecision.created_at)
        return list((await self._session.execute(stmt)).scalars().all())


#: The concrete adapter operations implemented in P21-D-C (the create / read /
#: list / decide base surface plus the idempotency lookup and audit append).
#: Retention / export remain deferred (P21-D-future).
IMPLEMENTED_METHODS: tuple[str, ...] = (
    "create_request",
    "get_request",
    "list_requests",
    "submit_decision",
    "find_by_idempotency_digest",
    "append_audit_event",
)


__all__ = [
    # phase / liveness
    "STORAGE_CLASS_DURABLE",
    "IS_LIVE_STORE",
    "ADAPTER_PHASE",
    # no-execution invariants
    "EXECUTION_ALLOWED",
    "EXECUTED",
    "EXECUTION_GATE",
    # mappings
    "OPERATION_TABLE_MAP",
    "INMEMORY_GLOBAL_MAP",
    "DURABLE_TABLES",
    "NEW_COLUMN_RULES",
    "SOURCE_STATUS_MAP",
    "DEGRADED_SOURCE_STATUS",
    "AUDIT_RESULT_BY_EVENT_TYPE",
    "derive_audit_result",
    # vocabularies (re-exported)
    "STATE_VALUES",
    "SOURCE_STATUS_VALUES",
    "STORAGE_CLASS_VALUES",
    "EVENT_TYPE_VALUES",
    "AUDIT_RESULT_VALUES",
    "SCOPE_KEY_VALUES",
    # errors / results
    "STORE_ERROR_CODES",
    "StoreError",
    "StoreResult",
    "StoreNotImplementedError",
    # surface
    "DurableApprovalStore",
    "PLANNED_METHODS",
    # P21-D-C concrete implementation
    "DurableApprovalStoreAdapter",
    "IMPLEMENTED_METHODS",
    "DURABLE_ADAPTER_IMPLEMENTATION_PHASE",
]
