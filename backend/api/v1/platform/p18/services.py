"""P18 Controlled Platform Actions -- request-skeleton service layer (P18-B).

SAFE skeleton: validates, deduplicates, redacts, audits, and records
controlled-action REQUESTS in process-local memory. It NEVER executes any
action and NEVER mutates the P17 registry, tenant lifecycle, operational flags,
provisioning, backup, or any tenant business data. Recorded requests are
ephemeral (in-process memory) -- there is intentionally no database table and
no migration.

The registry source-status resolver ``_resolve_registry_source_status`` is the
deferred seam: real wiring to the P17 registry read is deferred to a later
phase. The conservative default is "unknown", which denies write / write_request
actions and allows only the two degraded read actions, exactly as P18-A requires
(no action when the registry source is unknown unless the contract explicitly
allows a degraded request). Tests patch this function for determinism.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from .schemas import (
    ActionCatalogItem,
    ActionCatalogResponse,
    ActionClassification,
    ActionType,
    ActionRequestResponse,
    RegistrySourceStatus,
)


# -- Catalog (mirrors P18-A section 3) --------------------------------------

_CATALOG: list[ActionCatalogItem] = [
    ActionCatalogItem(
        action_type="support_mode.on",
        classification="write",
        allowed_actors=["super_admin", "support_operator"],
        confirmation_required=True,
        degraded_allowed=False,
        description="Request to enable support mode. Recorded only; not executed.",
    ),
    ActionCatalogItem(
        action_type="support_mode.off",
        classification="write",
        allowed_actors=["super_admin", "support_operator"],
        confirmation_required=True,
        degraded_allowed=False,
        description="Request to disable support mode. Recorded only; not executed.",
    ),
    ActionCatalogItem(
        action_type="tenant.pause",
        classification="write",
        allowed_actors=["super_admin"],
        confirmation_required=True,
        degraded_allowed=False,
        description="Request to pause a tenant. Recorded only; not executed.",
    ),
    ActionCatalogItem(
        action_type="tenant.resume",
        classification="write",
        allowed_actors=["super_admin"],
        confirmation_required=True,
        degraded_allowed=False,
        description="Request to resume a tenant. Recorded only; not executed.",
    ),
    ActionCatalogItem(
        action_type="incident.flag_set",
        classification="write",
        allowed_actors=["super_admin"],
        confirmation_required=True,
        degraded_allowed=False,
        description="Request to set the incident flag. Recorded only; not executed.",
    ),
    ActionCatalogItem(
        action_type="incident.flag_clear",
        classification="write",
        allowed_actors=["super_admin"],
        confirmation_required=True,
        degraded_allowed=False,
        description="Request to clear the incident flag. Recorded only; not executed.",
    ),
    ActionCatalogItem(
        action_type="provisioning.recheck",
        classification="read",
        allowed_actors=["super_admin", "engineering_operator"],
        confirmation_required=False,
        degraded_allowed=True,
        description="Request to recompute provisioning status. Degraded allowed; not executed.",
    ),
    ActionCatalogItem(
        action_type="backup.check",
        classification="read",
        allowed_actors=["super_admin", "engineering_operator"],
        confirmation_required=False,
        degraded_allowed=True,
        description="Request to refresh backup status. Degraded allowed; not executed.",
    ),
    ActionCatalogItem(
        action_type="backup.restore_test_request",
        classification="write_request",
        allowed_actors=["super_admin"],
        confirmation_required=True,
        degraded_allowed=False,
        description="Request to trigger an isolated restore test. Recorded only; not executed.",
    ),
    ActionCatalogItem(
        action_type="lifecycle.transition",
        classification="write",
        allowed_actors=["super_admin"],
        confirmation_required=True,
        degraded_allowed=False,
        description="Request a lifecycle transition validated against the P17 state machine. Recorded only; not executed.",
    ),
]

_CATALOG_BY_TYPE: dict[str, ActionCatalogItem] = {item.action_type: item for item in _CATALOG}


def get_catalog() -> ActionCatalogResponse:
    """Return the closed controlled-action catalog (read-only)."""
    return ActionCatalogResponse(
        items=list(_CATALOG),
        total=len(_CATALOG),
        contract="P18-A",
        executed=False,
    )


def known_action_type(action_type: str) -> bool:
    return action_type in _CATALOG_BY_TYPE


def _item_for(action_type: str) -> Optional[ActionCatalogItem]:
    return _CATALOG_BY_TYPE.get(action_type)


# -- Registry source-status resolution (deferred seam) ----------------------


async def _resolve_registry_source_status(
    tenant_id: Optional[str], db: AsyncSession
) -> RegistrySourceStatus:
    """Best-effort registry source status for the target tenant.

    Conservative default is "unknown": real wiring to the P17 registry read is
    deferred to a later phase. "unknown" denies write / write_request actions and
    allows only the two degraded read actions, matching P18-A (no action when the
    registry source is unknown unless the contract explicitly allows a degraded
    request). Tests patch this function for determinism.
    """
    return "unknown"


# -- In-memory request store (ephemeral, process-local) ---------------------


class _StoredRequest:
    """A recorded (accepted) controlled-action request. Ephemeral, in memory."""

    __slots__ = (
        "action_id",
        "action_type",
        "tenant_id",
        "reason",
        "idempotency_key",
        "requested_state",
        "result",
        "source_status",
        "created_at",
        "fingerprint",
        "correlation_id",
        "metadata_redacted",
    )

    def __init__(self, **kwargs: Any) -> None:
        for key in self.__slots__:
            setattr(self, key, kwargs.get(key))


_STORE: dict[str, _StoredRequest] = {}
_STORE_BY_ACTION_ID: dict[str, _StoredRequest] = {}


def reset_store() -> None:
    """Clear the in-memory request store. Used by tests for isolation."""
    _STORE.clear()
    _STORE_BY_ACTION_ID.clear()


def _fingerprint(
    action_type: str,
    tenant_id: Optional[str],
    requested_state: Optional[str],
    reason: str,
) -> str:
    raw = "|".join(
        [action_type or "", tenant_id or "", requested_state or "", reason or ""]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_stored_request(action_id: str) -> Optional[ActionRequestResponse]:
    """Rebuild the response for a recorded request by action_id, or None."""
    rec = _STORE_BY_ACTION_ID.get(action_id)
    if rec is None:
        return None
    return _make_response(
        action_type=rec.action_type,
        result=rec.result,  # type: ignore[arg-type]
        message=(
            "Recorded request (ephemeral in-memory store). The action was NOT "
            "executed; no registry / lifecycle / flag / provisioning / backup "
            "state was changed."
        ),
        reason=rec.reason,
        idempotency_key=rec.idempotency_key,
        requested_state=rec.requested_state,
        source_status=rec.source_status,  # type: ignore[arg-type]
        action_id=rec.action_id,
        dry_run=False,
        metadata_redacted=rec.metadata_redacted,
        correlation_id=rec.correlation_id,
        created_at=rec.created_at,
    )


# -- Redaction (allowlist-style; mirrors P10 redact_metadata intent) --------

_SENSITIVE_KEY = re.compile(
    r"(?i)(password|passwd|secret|token|api[_-]?key|access[_-]?key|credential|"
    r"dsn|host|port|url|uri|connection|string|private[_-]?key)"
)
_SENSITIVE_VAL = re.compile(
    r"(?i)(password|passwd|secret|token|api[_-]?key|access[_-]?key|credential|"
    r"dsn|postgres(ql)?://|mysql://|mongodb(\+srv)?://|redis://|amqp://|://|@)"
)
# Host / IP + optional :port. Used to catch a bare host or endpoint embedded in
# the free-text reason (a value the keyword regexes do not cover on their own).
_HOST_PORT = re.compile(
    r"(?i)(?:\b\d{1,3}(?:\.\d{1,3}){3}(?::\d{2,5})?\b"
    r"|\b[a-z][a-z0-9.-]*[a-z0-9]:\d{2,5}\b)"
)


def _redact_node(key: Optional[str], value: Any) -> Any:
    """Recursively redact a metadata node by key name and by value pattern."""
    # Key-based: a sensitive key name redacts the value at any depth.
    if isinstance(key, str) and _SENSITIVE_KEY.search(key):
        return "[redacted]"
    if isinstance(value, str):
        if _SENSITIVE_VAL.search(value):
            return "[redacted]"
        return value
    if isinstance(value, dict):
        return {k: _redact_node(k, v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_node(None, v) for v in value]
    return value


def redact_metadata(metadata: Optional[dict]) -> Optional[dict]:
    """Return a redacted copy of metadata. Sensitive keys/values become [redacted]."""
    if not metadata:
        return None
    return {key: _redact_node(key, value) for key, value in metadata.items()}


def _reason_is_sensitive(reason: str) -> bool:
    """True if the reason carries any secret keyword, scheme, or host:port pattern."""
    if not reason:
        return False
    if _SENSITIVE_VAL.search(reason):
        return True
    if _HOST_PORT.search(reason):
        return True
    return False


def _redact_reason(reason: str) -> str:
    """Return a safe reason for storage and echo.

    Conservative policy (P18-B/C-R1): if the reason contains ANY sensitive pattern
    -- a secret keyword (password / token / api_key / dsn / credential / ...), a
    connection scheme (postgres://, mysql://, redis://, ://), an '@' credential
    separator, or a host / IP : port pair -- the ENTIRE reason is replaced with
    "[redacted]" so that no secret VALUE can remain (the previous keyword-sub
    approach left the value, for example "abc123" in "password=abc123"). A clean
    reason is returned verbatim. The raw reason is never stored or echoed: only the
    idempotency fingerprint uses the raw payload, and that is a one-way hash that is
    never returned in any response.
    """
    if not reason:
        return ""
    if _reason_is_sensitive(reason):
        return "[redacted]"
    return reason


def _sanitize_text(value: Optional[str]) -> Optional[str]:
    """Return a safe value for any free-text client input echoed in responses/audit.

    P18-B/C-R2 generalizes the reason boundary to ALL client-supplied echo fields:
    idempotency_key, requested_state, and correlation_id. If the value carries any
    sensitive pattern it is replaced with "[redacted]"; None stays None; a clean
    value is returned verbatim. The RAW value is still used internally for the store
    key and the one-way idempotency fingerprint (a hash that is never echoed/audited).
    """
    if value is None:
        return None
    if _reason_is_sensitive(value):
        return "[redacted]"
    return value


def _sanitize_action_type(action_type: str) -> str:
    """Echo-safe action_type.

    Catalog values come from a fixed, safe enum and are returned verbatim. An
    unsupported value that contains a sensitive pattern is replaced with "[redacted]"
    (so a hostile action_type such as a DSN cannot be echoed); a benign unsupported
    value is echoed so the client can see what was rejected. The RAW action_type is
    still used internally for catalog lookup and the one-way fingerprint.
    """
    if known_action_type(action_type):
        return action_type
    if _reason_is_sensitive(action_type):
        return "[redacted]"
    return action_type


# -- Response builder --------------------------------------------------------


def _make_response(
    *,
    action_type: str,
    result: str,
    message: str,
    reason: str,
    idempotency_key: str,
    requested_state: Optional[str],
    source_status: RegistrySourceStatus,
    degraded_reason: Optional[str] = None,
    action_id: Optional[str] = None,
    dry_run: bool = False,
    metadata_redacted: Optional[dict] = None,
    correlation_id: Optional[str] = None,
    created_at: datetime,
) -> ActionRequestResponse:
    return ActionRequestResponse(
        action_id=action_id,
        action_type=action_type,
        result=result,  # type: ignore[arg-type]
        executed=False,
        dry_run=dry_run,
        message=message,
        reason=reason,
        idempotency_key=idempotency_key,
        requested_state=requested_state,
        previous_state=None,
        source_status=source_status,
        degraded_reason=degraded_reason,
        metadata_redacted=metadata_redacted,
        correlation_id=correlation_id,
        created_at=created_at,
    )


# -- Core evaluation (shared by validate and request) -----------------------


async def evaluate_request(
    *,
    action_type: str,
    tenant_id: Optional[str],
    reason: Optional[str],
    idempotency_key: Optional[str],
    requested_state: Optional[str],
    confirm: bool,
    correlation_id: Optional[str],
    metadata: Optional[dict],
    db: AsyncSession,
    persist: bool,
) -> ActionRequestResponse:
    """Validate and (optionally) record a controlled-action request.

    Never executes the action. When persist=True and the request is accepted,
    records it in the in-memory store. Returns a uniform ActionRequestResponse.

    Order of checks: reason -> idempotency_key -> known action_type ->
    confirmation -> registry source status -> (persist) idempotency store.
    """
    now = datetime.now(timezone.utc)
    raw_reason = (reason or "").strip()
    raw_key = (idempotency_key or "").strip()
    # Echo-safe values for every client-supplied field (P18-B/C-R2). RAW values are
    # still used internally: catalog lookup (action_type), the store key (raw_key),
    # and the one-way fingerprint (raw payload). Nothing raw is echoed or audited.
    safe_reason = _redact_reason(raw_reason)
    safe_action_type = _sanitize_action_type(action_type)
    safe_key = _sanitize_text(raw_key) or ""
    safe_requested_state = _sanitize_text(requested_state)
    safe_correlation_id = _sanitize_text(correlation_id)
    redacted_md = redact_metadata(metadata)

    def denied(message: str, source_status: RegistrySourceStatus = "unknown") -> ActionRequestResponse:
        return _make_response(
            action_type=safe_action_type,
            result="denied",
            message=message,
            reason=safe_reason,
            idempotency_key=safe_key,
            requested_state=safe_requested_state,
            source_status=source_status,
            dry_run=not persist,
            metadata_redacted=redacted_md,
            correlation_id=safe_correlation_id,
            created_at=now,
        )

    # 1) reason required (no action without a reason)
    if not raw_reason:
        return denied("Denied: a non-empty reason is required for every controlled action.")

    # 2) idempotency_key required (no action without an idempotency key)
    if not raw_key:
        return denied("Denied: an idempotency_key is required for every controlled action.")

    # 3) action_type must be in the closed catalog
    item = _item_for(action_type)
    if item is None:
        return denied("Denied: unsupported action_type; it is not in the P18-A catalog.")

    # 4) confirmation required for write / write_request actions
    if item.confirmation_required and not confirm:
        return denied("Denied: this action requires explicit confirmation (confirm=true).")

    # 5) resolve registry source status
    source_status = await _resolve_registry_source_status(tenant_id, db)
    is_write = item.classification in ("write", "write_request")

    # 6) unknown / unavailable source: writes denied; degraded read only when allowed
    if source_status != "available":
        if is_write:
            return denied(
                "Denied: registry source is unknown/unavailable; write and "
                "write_request actions are not accepted against an unreadable source.",
                source_status=source_status,
            )
        if item.degraded_allowed:
            return _make_response(
                action_type=safe_action_type,
                result="degraded",
                message=(
                    "Degraded: source unavailable; the request was accepted as a "
                    "degraded read. No state changed and no execution was performed."
                ),
                reason=safe_reason,
                idempotency_key=safe_key,
                requested_state=safe_requested_state,
                source_status=source_status,
                degraded_reason=f"Source status is '{source_status}'; degraded read only.",
                dry_run=not persist,
                metadata_redacted=redacted_md,
                correlation_id=safe_correlation_id,
                created_at=now,
            )
        return denied(
            "Denied: source unavailable for this action and degraded read is not permitted.",
            source_status=source_status,
        )

    # source available -> would be accepted
    projected = "accepted"

    # 7) idempotency: duplicate / conflict (only when persisting against the store)
    if persist:
        fp = _fingerprint(action_type, tenant_id, requested_state, raw_reason)
        existing = _STORE.get(raw_key)
        if existing is not None:
            if existing.fingerprint == fp:
                return _make_response(
                    action_type=existing.action_type,
                    result="duplicate",
                    message=(
                        "Duplicate: idempotency_key already recorded with an "
                        "identical request; the original result is returned and the "
                        "action was NOT re-executed."
                    ),
                    reason=existing.reason,
                    idempotency_key=safe_key,
                    requested_state=existing.requested_state,
                    source_status=existing.source_status,  # type: ignore[arg-type]
                    action_id=existing.action_id,
                    dry_run=False,
                    metadata_redacted=existing.metadata_redacted,
                    correlation_id=existing.correlation_id,
                    created_at=existing.created_at,
                )
            return _make_response(
                action_type=safe_action_type,
                result="conflict",
                message=(
                    "Conflict: idempotency_key already recorded with a different "
                    "request payload; the request is rejected and NOT executed."
                ),
                reason=safe_reason,
                idempotency_key=safe_key,
                requested_state=safe_requested_state,
                source_status=source_status,
                dry_run=False,
                metadata_redacted=redacted_md,
                correlation_id=safe_correlation_id,
                created_at=now,
            )

        action_id = str(uuid4())
        rec = _StoredRequest(
            action_id=action_id,
            action_type=safe_action_type,
            tenant_id=tenant_id,
            reason=safe_reason,
            idempotency_key=safe_key,
            requested_state=safe_requested_state,
            result=projected,
            source_status=source_status,
            created_at=now,
            fingerprint=fp,
            correlation_id=safe_correlation_id,
            metadata_redacted=redacted_md,
        )
        _STORE[raw_key] = rec
        _STORE_BY_ACTION_ID[action_id] = rec
        return _make_response(
            action_type=safe_action_type,
            result=projected,
            message=(
                "Accepted: the request was recorded and audited, NOT executed. No "
                "registry, lifecycle, flag, provisioning, or backup state was changed."
            ),
            reason=safe_reason,
            idempotency_key=safe_key,
            requested_state=safe_requested_state,
            source_status=source_status,
            action_id=action_id,
            dry_run=False,
            metadata_redacted=redacted_md,
            correlation_id=safe_correlation_id,
            created_at=now,
        )

    # validate (dry run) -- accepted projection, no persistence
    return _make_response(
        action_type=safe_action_type,
        result=projected,
        message=(
            "Accepted (dry run): the request is valid and would be recorded. Nothing "
            "was persisted and the action was NOT executed."
        ),
        reason=safe_reason,
        idempotency_key=safe_key,
        requested_state=safe_requested_state,
        source_status=source_status,
        dry_run=True,
        metadata_redacted=redacted_md,
        correlation_id=safe_correlation_id,
        created_at=now,
    )
