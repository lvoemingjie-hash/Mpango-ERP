"""
Service layer for P13 Operations Observability Cockpit API.

Read-only services returning operational data from existing P10/P12 sources.
No new observability infrastructure, no migrations, no persistent writes
except audit events.

Key design decisions:
  - source_status: "unavailable" when telemetry not instrumented.
  - Nullable totals (null, not 0) when source is unavailable.
  - Reuses P10 services for system health and tenant data.
  - All data is read-only. Only audit event writes.
  - Identity-only super_admin required (P10 guard).
"""
from __future__ import annotations

import re
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.platform_audit_service import append_audit_entry

from .schemas import (
    DatabaseHealth,
    ErrorRateSummary,
    NoisyNeighborEntry,
    NoisyNeighborSummary,
    QueueHealth,
    ResourceHealthSummary,
    SlowRouteSummary,
)


# -- P14-B documented unavailable reasons (see P14-A source contract) --

_ERROR_RATE_UNAVAILABLE_REASON = (
    "Request error telemetry is not instrumented; correlation IDs are required "
    "for class/route breakdown."
)
_SLOW_ROUTE_UNAVAILABLE_REASON = (
    "Per-request latency telemetry is not instrumented."
)
_NOISY_NEIGHBOR_UNAVAILABLE_REASON = (
    "Cross-tenant activity telemetry is not available; requires business-scope "
    "instrumentation outside platform-runtime scope."
)


# -- DB latency thresholds (P14-B) --
_DB_HEALTHY_LATENCY_MS = 200
_DB_DEGRADED_LATENCY_MS = 1000


# -- Helpers --


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _extract_ops_actor(request: Request) -> tuple[Optional[str], Optional[str]]:
    """Extract actor_id and actor_role from request auth context."""
    try:
        from api.context.auth import get_auth_context
        auth_ctx = get_auth_context(request)
        token = auth_ctx.token
        actor_id = token.user_id
        actor_role = "super_admin" if token.is_super_admin else None
        return actor_id, actor_role
    except Exception:
        return None, None


async def _write_ops_audit(
    db: AsyncSession,
    request: Request,
    *,
    action: str,
    view_type: str,
    window_minutes: int = 0,
    tenant_id: Optional[str] = None,
) -> None:
    """Write an ops audit event. Best-effort -- failure must not prevent response."""
    try:
        from uuid import UUID as PyUUID

        actor_id, actor_role = await _extract_ops_actor(request)

        wholesaler_id = None
        if tenant_id:
            try:
                wholesaler_id = PyUUID(tenant_id)
            except (ValueError, AttributeError):
                pass

        await append_audit_entry(
            db,
            actor_type="api",
            action=action,
            resource=f"ops/{view_type}",
            actor_id=PyUUID(actor_id) if actor_id else None,
            wholesaler_id=wholesaler_id,
            audit_metadata={
                "view_type": view_type,
                "window_minutes": window_minutes,
                "actor_role": actor_role,
                "scope": "operations",
                "target_tenant_id": tenant_id,
            },
        )
        await db.commit()
    except Exception:
        pass  # Audit failure must not prevent response


# -- Service functions --


def _parse_pool_status(status_text: Optional[str]) -> tuple[Optional[int], Optional[int], Optional[int]]:
    """Parse a SQLAlchemy pool.status() string into (active, idle, max).

    Typical QueuePool output:
      "Pool size: 5 Connections in pool: 2 Current Overflow: 0 Current Checked out connections: 1"

    - active = checked-out connections
    - idle   = connections in pool
    - max    = pool size + overflow (capacity)

    Returns (None, None, None) for any non-string / unparseable input so callers
    can fall back to honest nulls (null != 0). The raw string is never serialized.
    """
    if not isinstance(status_text, str) or not status_text:
        return None, None, None

    def _grab(label: str) -> Optional[int]:
        m = re.search(rf"{re.escape(label)}\s*:\s*(\d+)", status_text)
        return int(m.group(1)) if m else None

    size = _grab("Pool size")
    in_pool = _grab("Connections in pool")
    overflow = _grab("Current Overflow")
    checked_out = _grab("Checked out connections")

    idle = in_pool
    active = checked_out
    mx: Optional[int] = None
    if size is not None and overflow is not None:
        mx = size + overflow
    elif size is not None:
        mx = size
    return active, idle, mx


def _engine_pool_status(db: AsyncSession) -> Optional[str]:
    """Best-effort read of the bound engine's pool.status() string.

    Returns None if the session has no introspectable pool (NullPool, mock, etc.).
    Never raises -- pool introspection is best-effort, not load-bearing.
    """
    try:
        bind = getattr(db, "bind", None)
        pool = getattr(bind, "pool", None)
        status_fn = getattr(pool, "status", None)
        if status_fn is None:
            return None
        result = status_fn()
        return result if isinstance(result, str) else None
    except Exception:
        return None


async def _database_health(db: AsyncSession) -> DatabaseHealth:
    """Measure real database health (P14-B).

    - latency_ms: wall-clock of a `SELECT 1` ping on the request session.
    - status: threshold-derived from latency (healthy/degraded/unhealthy).
    - pool stats: parsed from the engine pool, best-effort (null if unavailable).

    On ping failure the database is reported unhealthy with latency null --
    never fabricated healthy. On pool-introspection failure the pool stats are
    null while latency/status remain real. No host/port/DSN/credentials leak.
    """
    active: Optional[int] = None
    idle: Optional[int] = None
    mx: Optional[int] = None
    latency_ms: Optional[int] = None

    # Real pool stats (best-effort, independent of the ping).
    active, idle, mx = _parse_pool_status(_engine_pool_status(db))

    # Real DB connectivity ping.
    try:
        start = time.perf_counter()
        await db.execute(text("SELECT 1"))
        latency_ms = int((time.perf_counter() - start) * 1000)
        if latency_ms < _DB_HEALTHY_LATENCY_MS:
            status = "healthy"
        elif latency_ms < _DB_DEGRADED_LATENCY_MS:
            status = "degraded"
        else:
            status = "unhealthy"
    except Exception:
        # Ping failed: real unhealthy, not fabricated healthy. Latency unknown.
        status = "unhealthy"
        latency_ms = None

    return DatabaseHealth(
        status=status,
        connection_pool_active=active,
        connection_pool_max=mx,
        connection_pool_idle=idle,
        latency_ms=latency_ms,
    )


async def get_error_rate_summary(
    db: AsyncSession,
    window_minutes: int = 15,
) -> ErrorRateSummary:
    """
    Return error rate summary.

    Telemetry is not yet instrumented, so source_status is "unavailable"
    and total_errors is null. This is the honest state -- not fabricated 0.
    The unavailable_reason (P14) explains why for the UI.
    """
    return ErrorRateSummary(
        source_status="unavailable",
        window_minutes=window_minutes,
        total_errors=None,
        error_classes=[],
        top_routes=[],
        top_tenants=None,
        unavailable_reason=_ERROR_RATE_UNAVAILABLE_REASON,
        generated_at=_utcnow(),
    )


async def get_slow_route_summary(
    db: AsyncSession,
    window_minutes: int = 15,
    threshold_ms: int = 1000,
) -> SlowRouteSummary:
    """
    Return slow route summary.

    Telemetry is not yet instrumented, so source_status is "unavailable"
    and total_slow_requests is null. The unavailable_reason (P14) explains why.
    """
    return SlowRouteSummary(
        source_status="unavailable",
        window_minutes=window_minutes,
        threshold_ms=threshold_ms,
        total_slow_requests=None,
        routes=[],
        unavailable_reason=_SLOW_ROUTE_UNAVAILABLE_REASON,
        generated_at=_utcnow(),
    )


async def get_resource_health_summary(
    db: AsyncSession,
) -> ResourceHealthSummary:
    """
    Return resource health summary.

    Database health is a REAL signal (P14-B): measured ping latency + engine
    pool stats, with a threshold-derived status (no fabricated 'unknown').
    Queue, CPU, memory, disk are not instrumented -- returned as null.
    """
    db_health = await _database_health(db)

    return ResourceHealthSummary(
        database=db_health,
        queue=None,
        memory=None,
        cpu=None,
        disk=None,
        generated_at=_utcnow(),
    )


async def get_noisy_neighbor_summary(
    db: AsyncSession,
    window_minutes: int = 15,
) -> NoisyNeighborSummary:
    """
    Return noisy-neighbor summary.

    Requires cross-tenant telemetry which is not yet instrumented.
    Returns empty tenants list. The unavailable_reason (P14) explains why.
    """
    return NoisyNeighborSummary(
        window_minutes=window_minutes,
        tenants=[],
        unavailable_reason=_NOISY_NEIGHBOR_UNAVAILABLE_REASON,
        generated_at=_utcnow(),
    )
