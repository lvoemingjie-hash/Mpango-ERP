"""P22-E1 runtime governed action adapter registry -- NON-EXECUTING skeleton.

This module is the adapter-registry half of the runtime governed action adapter
seam defined by P22-E0 (docs/ai/PLATFORM_PRODUCT_P22_RUNTIME_GOVERNED_ADAPTER_
CONTRACT.md, section 4 / section 9). It carries ONE named, bounded, NON-EXECUTING
adapter descriptor per allowlisted v0 action and nothing else:

  - It holds NO real adapter body for any action. Every descriptor is
    not_implemented and realizes_execution is always False.
  - It accepts NO arbitrary action string. The registry is built from the closed
    v0 allowlist (P22-A section 3.1) only; resolution of any other value returns
    None. There is no generic dispatcher and no fallback adapter.
  - It reads, writes, spawns, and calls nothing. It performs NO execution,
    dispatches NO worker, drains NO queue, invokes NO development-time worktree
    harness, and runs no shell, SQL, script, or external process.
  - backup.check is an honest source_unknown slot: the P17 backup system source
    is not yet wired, so the slot never fabricates a healthy / known read.

This module is import-tested in P22-E1; it is not wired into any HTTP route and
adds no public execution entry point. A separately CTO-approved real-execution
phase will, per P22-E0 section 9.6, realize adapter bodies behind the seam.

Approval is not execution, a passed dry-run is not execution, and a recorded
request is not execution. The registry is a name table, not an executor.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .schemas import (
    ACTION_CLASS_MAP,
    ALLOWED_ACTION_TYPES,
    P22ActionClass,
    P22ActionType,
    REVERSAL_MAP,
)


# -- Non-execution markers ----------------------------------------------------

#: Explicit non-execution marker. No adapter in this registry realizes execution
#: in P22-E1. A future real-execution phase flips a per-adapter marker only after
#: its source is proven and behind the full seam gate (P22-E0 9.2 / 9.6).
ADAPTER_REALIZES_EXECUTION: bool = False

#: The honest reason backup.check carries. Mirrors the P17 as-built state: the
#: backup system source is not yet wired, so backup status is unavailable. The
#: slot never synthesizes a fresh / healthy status.
_BACKUP_SOURCE_NOT_WIRED: str = (
    "Backup system source is not yet wired; backup status is unavailable."
)

#: The not-implemented reason every P22-E1 adapter descriptor carries. No adapter
#: in this skeleton has a real body; none reads a real source.
_NOT_IMPLEMENTED: str = (
    "P22-E1 non-executing skeleton: this adapter has no real body. A separately "
    "CTO-approved real-execution phase must realize it behind the seam gate."
)


# -- Adapter descriptor -------------------------------------------------------


class AdapterDescriptor(BaseModel):
    """One named, bounded, NON-EXECUTING adapter for an allowlisted v0 action.

    Carries the adapter NAME and an honest source_status only. There is no real
    adapter body: realizes_execution is always False and adapter_result is always
    not_implemented. backup.check is source_unknown (the P17 source is not wired);
    every other action is source_unknown too in P22-E1, because no adapter has a
    proven source yet. A future phase upgrades a slot to known only when its
    source is proven -- unknown is never healthy and null is never zero.
    """

    model_config = ConfigDict(extra="forbid")

    action_type: P22ActionType
    action_class: P22ActionClass
    realizes_execution: bool = Field(
        False, description="Always False in P22-E1; no adapter has a real body."
    )
    adapter_result: str = Field(
        "not_implemented", description="Always not_implemented in P22-E1."
    )
    source_status: str = Field(
        ..., description="known | unknown | degraded. Honest per action; never fabricated."
    )
    source_reason: Optional[str] = Field(
        None, description="Why the source is unknown / degraded; None only when known."
    )
    reversible: bool = Field(False, description="Whether a paired reversal action exists.")
    reversibility_via: Optional[P22ActionType] = Field(
        None, description="The paired reversal action, if any."
    )
    reads_business_data: bool = Field(
        False, description="Always False -- no tenant business record is ever read."
    )


def _source_status_for(action_type: str) -> tuple[str, Optional[str]]:
    """Honest (source_status, reason) for an allowlisted action.

    backup.check is source_unknown: the P17 backup source is not wired. Every
    other action is source_unknown too in P22-E1: no adapter has a proven source,
    so none fabricates a known / healthy status. A future real-execution phase
    upgrades a slot to known only when its source is proven.
    """
    if action_type == "backup.check":
        return "unknown", _BACKUP_SOURCE_NOT_WIRED
    return "unknown", _NOT_IMPLEMENTED


def _build_descriptor(action_type: str) -> AdapterDescriptor:
    source_status, source_reason = _source_status_for(action_type)
    return AdapterDescriptor(
        action_type=action_type,  # type: ignore[arg-type]
        action_class=ACTION_CLASS_MAP[action_type],  # type: ignore[arg-type]
        realizes_execution=ADAPTER_REALIZES_EXECUTION,
        adapter_result="not_implemented",
        source_status=source_status,
        source_reason=source_reason,
        reversible=bool(REVERSAL_MAP.get(action_type)),
        reversibility_via=REVERSAL_MAP.get(action_type),  # type: ignore[arg-type]
        reads_business_data=False,
    )


# -- The closed adapter registry (allowlist only) -----------------------------

#: ONE NON-EXECUTING descriptor per allowlisted v0 action, keyed by action_type.
#: Built from ALLOWED_ACTION_TYPES only; an arbitrary action string is never
#: accepted and never has a descriptor. There is no generic dispatcher.
_ADAPTER_REGISTRY: dict[str, AdapterDescriptor] = {
    str(at): _build_descriptor(str(at)) for at in ALLOWED_ACTION_TYPES
}


def resolve_adapter_descriptor(action_type: Optional[str]) -> Optional[AdapterDescriptor]:
    """Resolve an action_type to its ONE adapter descriptor, or None.

    Allowlist-only resolution (P22-E0 4.2.1): a value in ALLOWED_ACTION_TYPES
    resolves to its single descriptor; every other value -- an excluded action, an
    unknown string, or None -- resolves to None. There is no generic dispatcher
    that takes an arbitrary action string, and no fallback adapter.
    """
    if action_type in ALLOWED_ACTION_TYPES:
        return _ADAPTER_REGISTRY[str(action_type)]
    return None


def adapter_registry_inventory() -> list[AdapterDescriptor]:
    """Return every registered adapter descriptor (allowlist only, in order).

    Read-only. The count is always the v0 allowlist size (seven). No arbitrary
    action is ever present.
    """
    return [_ADAPTER_REGISTRY[str(at)] for at in ALLOWED_ACTION_TYPES]


def is_registered_action(action_type: Optional[str]) -> bool:
    """True only for an allowlisted v0 action that has a registered adapter."""
    return action_type in ALLOWED_ACTION_TYPES


def non_executing_adapter_result(action_type: Optional[str]) -> dict:
    """The honest NON-EXECUTING result shape for an adapter.

    For a registered adapter: registered True, realizes_execution False,
    result_state 'blocked' (never executed), adapter_result 'not_implemented',
    source_status honest, executed False. For an unregistered / arbitrary action:
    registered False, adapter_result 'not_registered' (the seam refuses it).

    Never claims execution and never fabricates a healthy / known source. This is
    a descriptive shape only; it does not run the adapter and writes nothing.
    """
    descriptor = resolve_adapter_descriptor(action_type)
    if descriptor is None:
        return {
            "action_type": action_type,
            "registered": False,
            "realizes_execution": False,
            "result_state": "blocked",
            "adapter_result": "not_registered",
            "source_status": "unknown",
            "executed": False,
            "reason": "Action is not in the v0 allowlist; no adapter is registered.",
        }
    return {
        "action_type": descriptor.action_type,
        "registered": True,
        "realizes_execution": descriptor.realizes_execution,
        "result_state": "blocked",
        "adapter_result": descriptor.adapter_result,
        "source_status": descriptor.source_status,
        "source_reason": descriptor.source_reason,
        "executed": False,
        "reason": _NOT_IMPLEMENTED,
    }


__all__ = [
    "ADAPTER_REALIZES_EXECUTION",
    "AdapterDescriptor",
    "resolve_adapter_descriptor",
    "adapter_registry_inventory",
    "is_registered_action",
    "non_executing_adapter_result",
]
