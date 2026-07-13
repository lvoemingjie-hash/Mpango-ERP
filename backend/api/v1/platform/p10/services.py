"""
Service layer for P10 Platform Product read-only APIs.

Data-source alignment per PLATFORM_PRODUCT_CONTRACTS.md:
  - available_now: Data that can be queried from existing tables.
  - proposed_public_metadata: Returns null until platform metadata tables exist.
  - tenant_aggregate_required: Returns null until cross-schema aggregation is built.
  - telemetry_required: Returns null until telemetry/metrics infrastructure is built.
  - manual_or_unknown: Returns "unknown" fallback.
  - deferred: Returns null until dependency is built.

All endpoints are READ-ONLY. No mutations, no writes, no side effects.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from models.wholesaler import Wholesaler
from models.platform_tenant import PlatformTenant

from .schemas import (
    TenantSummary,
    TenantSummaryList,
    TenantHealth,
    SystemHealth,
    PlatformAuditEvent,
    PlatformAuditEventList,
    ActivityCounters,
    DatabaseConnections,
    HealthStatus,
    TenantStatus,
    SchemaStatus,
    OverallStatus,
    ComponentStatus,
)


def _coerce_tenant_id(tenant_id: str) -> Optional[uuid.UUID]:
    """Parse a tenant_id path parameter into a UUID.

    Returns None when the value is not a valid UUID so that callers translate
    invalid/slug identifiers into a clean 404 instead of letting the raw string
    reach a UUID column and raise an asyncpg DataError (HTTP 500).
    """
    try:
        return uuid.UUID(str(tenant_id))
    except (ValueError, AttributeError, TypeError):
        return None


# ── Metadata Redaction (P10-R1-B) ──


# Keywords that indicate sensitive data — case-insensitive substring match.
_SENSITIVE_KEY_PATTERNS: tuple[str, ...] = (
    "password",
    "token",
    "secret",
    "authorization",
    "cookie",
    "raw_body",
    "request_body",
    "response_body",
    "payload",
    "stack_trace",
    "traceback",
    "card",
    "payment",
)


def _is_sensitive_key(key: str) -> bool:
    """Check if a key name suggests sensitive content (case-insensitive)."""
    key_lower = key.lower()
    return any(pattern in key_lower for pattern in _SENSITIVE_KEY_PATTERNS)


def redact_metadata(metadata: Optional[dict]) -> Optional[dict]:
    """
    Redact sensitive keys from audit metadata before exposing via the API.

    P10-R1-B: Do NOT map PlatformAuditLog.audit_metadata directly to
    metadata_redacted. This function implements an allowlist approach —
    any key whose name contains a sensitive pattern is removed.

    Handles nested dicts and lists of dicts recursively.
    Returns None if input is None. Returns empty dict if input is empty.

    Safe keys preserved include (but are not limited to):
      result, denial_code, reason_code, actor_assignment_status,
      requested_at, message, operator_assignments, context, entries.
    """
    if metadata is None:
        return None

    return _redact_value(metadata)


def _redact_value(value: Any) -> Any:
    """Recursively redact sensitive keys from dicts and lists."""
    if isinstance(value, dict):
        redacted: dict = {}
        for k, v in value.items():
            if _is_sensitive_key(k):
                continue  # drop the key entirely
            redacted[k] = _redact_value(v)
        return redacted
    elif isinstance(value, list):
        return [_redact_value(item) for item in value]
    else:
        return value


# ── Helpers ──


def _map_wholesaler_status(ws_status: Optional[str]) -> TenantStatus:
    """Map wholesaler status to P10-A TenantSummary status enum.

    Existing wholesaler statuses don't perfectly align with P10-A enums.
    We map known values and fall back to 'unknown'.
    """
    mapping: dict[str, TenantStatus] = {
        "active": "active",
        "suspended": "suspended",
        "draft": "draft",
        "paused": "paused",
        "archived": "archived",
    }
    if ws_status is None:
        return "unknown"
    return mapping.get(ws_status, "unknown")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Valid audit result values per P10-A AuditResult closed vocab (P25-EF).
_VALID_AUDIT_RESULTS: frozenset[str] = frozenset(
    {"allowed", "denied", "failed", "completed", "recorded"}
)


def _coerce_audit_result(raw: object) -> str:
    """Map an audit_metadata.result value to a valid AuditResult vocab term.

    P19/P20 handlers legitimately write result='recorded' for record-only
    audit events; that value is now part of the closed vocab. Any other
    unexpected value is fail-closed to 'completed' so the API never raises a
    Pydantic ValidationError -> HTTP 500. The raw metadata (before redaction)
    is preserved in audit_metadata_redacted so real data is not silently hidden.
    """
    if raw is None:
        return "completed"
    candidate = str(raw).strip().lower()
    if candidate in _VALID_AUDIT_RESULTS:
        return candidate
    return "completed"


# ── TenantSummary ──


async def list_tenant_summaries(
    db: AsyncSession,
    limit: int = 50,
    offset: int = 0,
) -> TenantSummaryList:
    """
    List all tenants with P10-A contract-compliant summaries.

    Data sources available now:
      - wholesaler name, code, status, plan_type, created_at (from wholesalers table)
      - tenant_schema (via wholesaler.get_tenant_schema())

    Data sources returning null (not yet built):
      - last_activity_at (tenant_aggregate_required)
      - user_count (tenant_aggregate_required)
      - recent_error_count (telemetry_required)
      - tier mapping (proposed_public_metadata — plan_type exists but is not tier)

    Non-nullable with fallback:
      - status: mapped from wholesaler, 'unknown' if unmappable
      - health_status: 'unknown' (manual_or_unknown — no health signals yet)
      - support_mode_active: False (not yet implemented)
    """
    count_q = await db.execute(
        select(func.count()).select_from(
            select(Wholesaler.id)
            .where(Wholesaler.is_deleted == False)
            .subquery()
        )
    )
    total = count_q.scalar() or 0

    result = await db.execute(
        select(Wholesaler)
        .where(Wholesaler.is_deleted == False)
        .order_by(Wholesaler.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    wholesalers = result.scalars().all()

    items: list[TenantSummary] = []
    for w in wholesalers:
        items.append(
            TenantSummary(
                tenant_id=str(w.id) if w.id else None,
                tenant_name=w.name,
                tenant_schema=w.get_tenant_schema() if hasattr(w, "get_tenant_schema") else None,
                status=_map_wholesaler_status(w.status),
                tier=None,  # proposed_public_metadata — subscription model not yet built
                created_at=w.created_at,
                last_activity_at=None,  # tenant_aggregate_required
                user_count=None,  # tenant_aggregate_required
                health_status="unknown",  # manual_or_unknown — no health signals yet
                recent_error_count=None,  # telemetry_required
                support_mode_active=False,  # not yet implemented
            )
        )

    return TenantSummaryList(items=items, total=total, limit=limit, offset=offset)


async def get_tenant_summary(
    db: AsyncSession,
    tenant_id: str,
) -> Optional[TenantSummary]:
    """Get a single tenant's contract-compliant summary."""
    parsed = _coerce_tenant_id(tenant_id)
    if parsed is None:
        return None
    result = await db.execute(
        select(Wholesaler).where(Wholesaler.id == parsed)
    )
    w = result.scalar_one_or_none()
    if w is None:
        return None

    return TenantSummary(
        tenant_id=str(w.id),
        tenant_name=w.name,
        tenant_schema=w.get_tenant_schema() if hasattr(w, "get_tenant_schema") else None,
        status=_map_wholesaler_status(w.status),
        tier=None,
        created_at=w.created_at,
        last_activity_at=None,
        user_count=None,
        health_status="unknown",
        recent_error_count=None,
        support_mode_active=False,
    )


# ── TenantHealth ──


async def get_tenant_health(
    db: AsyncSession,
    tenant_id: str,
) -> Optional[TenantHealth]:
    """
    Get contract-compliant health assessment for a single tenant.

    Most fields return null/unknown because health signals are not yet built:
      - health_status: 'unknown' (manual_or_unknown)
      - schema_status: null (telemetry_required)
      - last_login_at: null (tenant_aggregate_required)
      - activity_counters: null (tenant_aggregate_required)
      - recent_errors: null (telemetry_required)
      - slow_routes: null (telemetry_required)
      - failed_jobs: null (telemetry_required)
      - last_health_check_at: null (proposed_public_metadata)

    Available now:
      - tenant_id from wholesalers
      - tenant_schema from wholesaler
    """
    parsed = _coerce_tenant_id(tenant_id)
    if parsed is None:
        return None
    result = await db.execute(
        select(Wholesaler).where(Wholesaler.id == parsed)
    )
    w = result.scalar_one_or_none()
    if w is None:
        return None

    return TenantHealth(
        tenant_id=str(w.id),
        tenant_schema=w.get_tenant_schema() if hasattr(w, "get_tenant_schema") else None,
        health_status="unknown",
        schema_status=None,
        last_login_at=None,
        activity_counters=None,
        recent_errors=None,
        slow_routes=None,
        failed_jobs=None,
        last_health_check_at=None,
    )


# ── SystemHealth ──


async def get_system_health(
    db: AsyncSession,
) -> SystemHealth:
    """
    Get contract-compliant platform-wide health snapshot.

    Most component statuses return null because telemetry is not yet built:
      - api_status: null (telemetry_required)
      - database_status: null (telemetry_required)
      - database_connections: null (telemetry_required)
      - queue_status: null (telemetry_required)
      - cpu_status: null (telemetry_required, not instrumented in local/dev)
      - memory_status: null (telemetry_required, not instrumented in local/dev)
      - disk_status: null (telemetry_required, not instrumented in local/dev)
      - error_rate: null (telemetry_required)
      - slow_request_count: null (telemetry_required)

    Available now:
      - overall_status: 'unknown' (manual_or_unknown — no health signals yet)
      - generated_at: always available
    """
    return SystemHealth(
        overall_status="unknown",
        api_status=None,
        database_status=None,
        database_connections=None,
        queue_status=None,
        cpu_status=None,
        memory_status=None,
        disk_status=None,
        error_rate=None,
        slow_request_count=None,
        generated_at=_utcnow(),
    )


# ── PlatformAuditEvent ──


async def list_audit_events(
    db: AsyncSession,
    limit: int = 50,
    offset: int = 0,
) -> PlatformAuditEventList:
    """
    List platform audit events in P10-A contract shape.

    PLACEHOLDER: This maps existing platform_audit_logs entries to the P10-A
    PlatformAuditEvent contract shape. Some fields cannot be populated because
    the P10-A contract expects different field semantics than P0:

      - event_id: mapped from id
      - actor_id: mapped from actor_id (string)
      - actor_role: null (deferred — P0 has actor_type which uses different enum)
      - tenant_id: mapped from wholesaler_id
      - scope: inferred from wholesaler_id presence ('tenant' vs 'global')
      - action: mapped from action
      - reason: null (proposed_public_metadata — not captured in P0 schema)
      - result: mapped from audit_metadata.result or 'completed'
      - metadata_redacted: mapped from audit_metadata
      - correlation_id: null (telemetry_required)
      - created_at: mapped from created_at

    IMPORTANT: This is a placeholder mapping. When platform auth and audit
    infrastructure are built (P11+), these will be replaced with proper sources.
    """
    from models.platform_audit_log import PlatformAuditLog

    count_q = await db.execute(
        select(func.count(PlatformAuditLog.id))
    )
    total = count_q.scalar() or 0

    result = await db.execute(
        select(PlatformAuditLog)
        .order_by(PlatformAuditLog.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    entries = result.scalars().all()

    items: list[PlatformAuditEvent] = []
    for e in entries:
        meta = e.audit_metadata or {}
        items.append(
            PlatformAuditEvent(
                event_id=str(e.id),
                actor_id=str(e.actor_id) if e.actor_id else None,
                actor_role=None,  # deferred — P0 actor_type uses different enum
                tenant_id=str(e.wholesaler_id) if e.wholesaler_id else None,
                scope="tenant" if e.wholesaler_id else "global",
                action=e.action or "unknown",
                reason=None,  # proposed_public_metadata
                result=_coerce_audit_result(meta.get("result")),
                metadata_redacted=redact_metadata(meta) if meta else None,
                correlation_id=None,  # telemetry_required
                created_at=e.created_at,
            )
        )

    return PlatformAuditEventList(items=items, total=total, limit=limit, offset=offset)


async def get_audit_event(
    db: AsyncSession,
    event_id: str,
) -> Optional[PlatformAuditEvent]:
    """Get a single audit event in P10-A contract shape (placeholder)."""
    from models.platform_audit_log import PlatformAuditLog

    parsed_id = _coerce_tenant_id(event_id)
    if parsed_id is None:
        return None

    result = await db.execute(
        select(PlatformAuditLog).where(PlatformAuditLog.id == parsed_id)
    )
    e = result.scalar_one_or_none()
    if e is None:
        return None

    meta = e.audit_metadata or {}
    return PlatformAuditEvent(
        event_id=str(e.id),
        actor_id=str(e.actor_id) if e.actor_id else None,
        actor_role=None,
        tenant_id=str(e.wholesaler_id) if e.wholesaler_id else None,
        scope="tenant" if e.wholesaler_id else "global",
        action=e.action or "unknown",
        reason=None,
        result=_coerce_audit_result(meta.get("result")),
        metadata_redacted=redact_metadata(meta) if meta else None,
        correlation_id=None,
        created_at=e.created_at,
    )
