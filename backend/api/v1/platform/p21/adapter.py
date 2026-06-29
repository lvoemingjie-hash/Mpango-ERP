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

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

# Re-export the durable value vocabularies so the adapter surface is
# self-contained and the closed-set guarantees are testable from one place.
from api.v1.platform.p21.models import (
    AUDIT_RESULT_VALUES,
    EVENT_TYPE_VALUES,
    SCOPE_KEY_VALUES,
    SOURCE_STATUS_VALUES,
    STATE_VALUES,
    STORAGE_CLASS_VALUES,
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
]
