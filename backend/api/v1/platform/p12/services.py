"""
Service layer for P12 Support Console API.

In-memory session management, diagnostic gathering (reusing P10),
bundle generation, and audit event creation.

Key design decisions:
  - Sessions are in-memory only (no migrations, no persistent storage).
  - Lazy expiry on access (no background timer).
  - Diagnostics gathered from P10 services with redaction applied.
  - Audit events persisted via platform_audit_service (the only allowed write).
  - Unknown/unavailable metrics stay unknown/null -- never fabricated.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.v1.platform.p10.services import (
    get_tenant_health,
    get_system_health,
    get_tenant_summary,
    redact_metadata,
)
from services.platform_audit_service import append_audit_entry

from .schemas import (
    BundleType,
    DiagnosticSourceStatus,
    SupportBundle,
    SupportCategory,
    SupportDiagnosticItem,
    SupportSession,
    SupportSessionStatus,
)


# ── Constants ──

SESSION_TTL_MINUTES = 60

# Diagnostic categories included per bundle type
_FULL_CATEGORIES = frozenset({
    "tenant_metadata",
    "health_summary",
    "activity_counters",
    "recent_errors",
    "slow_routes",
    "failed_jobs",
    "system_snapshot",
    "correlation_ids",
    "schema_status",
})

_TECHNICAL_CATEGORIES = frozenset({
    "health_summary",
    "recent_errors",
    "slow_routes",
    "failed_jobs",
    "system_snapshot",
    "schema_status",
})

_SUMMARY_CATEGORIES = frozenset({
    "tenant_metadata",
    "health_summary",
})


# ── In-Memory Session Store ──


class SupportSessionStore:
    """In-memory store for support sessions. No persistence, no migrations."""

    def __init__(self, ttl_minutes: int = SESSION_TTL_MINUTES):
        self._sessions: dict[str, SupportSession] = {}
        self._ttl_minutes = ttl_minutes

    def create(
        self,
        *,
        actor_id: Optional[str],
        actor_role: Optional[str],
        tenant_id: Optional[str],
        reason: str,
        category: SupportCategory,
        correlation_id: Optional[str],
    ) -> SupportSession:
        now = _utcnow()
        session = SupportSession(
            session_id=str(uuid.uuid4()),
            actor_id=actor_id,
            actor_role=actor_role,
            tenant_id=tenant_id,
            reason=reason,
            category=category,
            correlation_id=correlation_id or str(uuid.uuid4()),
            status="active",
            started_at=now,
            closed_at=None,
            expires_at=now + timedelta(minutes=self._ttl_minutes),
            bundle_count=0,
        )
        self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> Optional[SupportSession]:
        self._cleanup_expired()
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if session.expires_at and _utcnow() > session.expires_at:
            session.status = "expired"
            del self._sessions[session_id]
            return None
        return session

    def close(self, session_id: str) -> Optional[SupportSession]:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        now = _utcnow()
        session.status = "closed"
        session.closed_at = now
        return session

    def increment_bundle_count(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if session is not None:
            session.bundle_count += 1

    def _cleanup_expired(self) -> None:
        now = _utcnow()
        expired_ids = [
            sid
            for sid, s in self._sessions.items()
            if s.expires_at and now > s.expires_at
        ]
        for sid in expired_ids:
            self._sessions[sid].status = "expired"
            del self._sessions[sid]

    def clear_all(self) -> None:
        """For testing only -- clear all sessions."""
        self._sessions.clear()


# Module-level singleton
_session_store = SupportSessionStore()


# ── Helpers ──


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def extract_support_actor(request: Request) -> tuple[Optional[str], Optional[str]]:
    """
    Extract actor_id and actor_role from request auth context.

    Returns (actor_id, actor_role) or (None, None) if no auth context.
    """
    try:
        from api.context.auth import get_auth_context
        auth_ctx = get_auth_context(request)
        token = auth_ctx.token
        actor_id = token.user_id
        if token.is_super_admin:
            actor_role = "super_admin"
        else:
            actor_role = None
        return actor_id, actor_role
    except Exception:
        return None, None


# ── Service functions ──


async def create_support_session(
    db: AsyncSession,
    request: Request,
    *,
    reason: str,
    category: SupportCategory,
    tenant_id: Optional[str],
) -> SupportSession:
    """
    Create a new in-memory support session and write audit event.

    The session is request-scoped -- it exists only in process memory.
    The audit event is the only persistent write.
    """
    actor_id, actor_role = extract_support_actor(request)

    correlation_id = str(uuid.uuid4())

    session = _session_store.create(
        actor_id=actor_id,
        actor_role=actor_role,
        tenant_id=tenant_id,
        reason=reason,
        category=category,
        correlation_id=correlation_id,
    )

    # Write audit event (the only allowed persistent write)
    from uuid import UUID as PyUUID

    wholesaler_id = None
    if tenant_id:
        try:
            wholesaler_id = PyUUID(tenant_id)
        except (ValueError, AttributeError):
            pass

    await append_audit_entry(
        db,
        actor_type="api",
        action="support_session_start",
        resource=f"support/sessions/{session.session_id}",
        actor_id=PyUUID(actor_id) if actor_id else None,
        wholesaler_id=wholesaler_id,
        audit_metadata={
            "session_id": session.session_id,
            "category": category,
            "reason": reason,
            "correlation_id": correlation_id,
            "actor_role": actor_role,
            "tenant_id": tenant_id,
        },
    )
    await db.commit()

    return session


async def get_diagnostics(
    db: AsyncSession,
    session_id: str,
) -> list[SupportDiagnosticItem]:
    """
    Gather redacted diagnostics for an active support session.

    Reuses P10 services for data gathering.
    Applies redaction at the data gathering layer.
    Unknown/unavailable metrics stay unknown/null.
    """
    session = _session_store.get(session_id)
    if session is None:
        raise ValueError("Session not found or expired")
    if session.status != "active":
        raise ValueError(f"Session is {session.status}, not active")

    tenant_id = session.tenant_id
    now = _utcnow()
    items: list[SupportDiagnosticItem] = []

    # Tenant metadata
    if tenant_id:
        summary = await get_tenant_summary(db, tenant_id)
        if summary is not None:
            summary_dict = summary.model_dump()
            redacted = redact_metadata(summary_dict) or {}
            items.append(
                SupportDiagnosticItem(
                    item_id=str(uuid.uuid4()),
                    bundle_id=None,
                    category="tenant_metadata",
                    label="Tenant Summary",
                    value=redacted,
                    source_status="available",
                    collected_at=now,
                )
            )
        else:
            items.append(
                SupportDiagnosticItem(
                    item_id=str(uuid.uuid4()),
                    bundle_id=None,
                    category="tenant_metadata",
                    label="Tenant Summary",
                    value=None,
                    source_status="unavailable",
                    collected_at=now,
                )
            )

        # Health summary
        health = await get_tenant_health(db, tenant_id)
        if health is not None:
            health_dict = health.model_dump()
            redacted_health = redact_metadata(health_dict) or {}
            items.append(
                SupportDiagnosticItem(
                    item_id=str(uuid.uuid4()),
                    bundle_id=None,
                    category="health_summary",
                    label="Tenant Health",
                    value=redacted_health,
                    source_status="available",
                    collected_at=now,
                )
            )
        else:
            items.append(
                SupportDiagnosticItem(
                    item_id=str(uuid.uuid4()),
                    bundle_id=None,
                    category="health_summary",
                    label="Tenant Health",
                    value=None,
                    source_status="unavailable",
                    collected_at=now,
                )
            )
    else:
        # No tenant selected -- return minimal unknown diagnostics
        for cat, label in [
            ("tenant_metadata", "Tenant Summary"),
            ("health_summary", "Tenant Health"),
        ]:
            items.append(
                SupportDiagnosticItem(
                    item_id=str(uuid.uuid4()),
                    bundle_id=None,
                    category=cat,
                    label=label,
                    value=None,
                    source_status="unavailable",
                    collected_at=now,
                )
            )

    # System snapshot (always available)
    system_health = await get_system_health(db)
    system_dict = system_health.model_dump()
    redacted_system = redact_metadata(system_dict) or {}
    items.append(
        SupportDiagnosticItem(
            item_id=str(uuid.uuid4()),
            bundle_id=None,
            category="system_snapshot",
            label="System Health",
            value=redacted_system,
            source_status="available",
            collected_at=now,
        )
    )

    # Telemetry-required items (unavailable until instrumented)
    for cat, label in [
        ("activity_counters", "Activity Counters"),
        ("recent_errors", "Recent Errors"),
        ("slow_routes", "Slow Routes"),
        ("failed_jobs", "Failed Jobs"),
        ("correlation_ids", "Correlation IDs"),
        ("schema_status", "Schema Status"),
    ]:
        items.append(
            SupportDiagnosticItem(
                item_id=str(uuid.uuid4()),
                bundle_id=None,
                category=cat,
                label=label,
                value=None,
                source_status="unavailable",
                collected_at=now,
            )
        )

    return items


async def generate_bundle(
    db: AsyncSession,
    request: Request,
    session_id: str,
    bundle_type: BundleType,
) -> SupportBundle:
    """
    Generate a support bundle from an active session's diagnostics.

    Filters diagnostics by bundle type.
    Always applies redaction.
    Writes audit event for bundle generation.
    """
    session = _session_store.get(session_id)
    if session is None:
        raise ValueError("Session not found or expired")
    if session.status != "active":
        raise ValueError(f"Session is {session.status}, cannot generate bundle")

    # Gather all diagnostics
    all_diagnostics = await get_diagnostics(db, session_id)

    # Filter by bundle type
    if bundle_type == "full":
        allowed = _FULL_CATEGORIES
    elif bundle_type == "technical":
        allowed = _TECHNICAL_CATEGORIES
    else:
        allowed = _SUMMARY_CATEGORIES

    filtered = [d for d in all_diagnostics if d.category in allowed]

    if not filtered:
        # Ensure at least 1 item (contract requirement)
        now = _utcnow()
        filtered = [
            SupportDiagnosticItem(
                item_id=str(uuid.uuid4()),
                bundle_id=None,
                category="health_summary",
                label="Health Summary (no data available)",
                value=None,
                source_status="unavailable",
                collected_at=now,
            )
        ]

    bundle_id = str(uuid.uuid4())
    correlation_id = f"{session.correlation_id}-b-{bundle_id[:8]}"

    # Set bundle_id on each item
    for d in filtered:
        d.bundle_id = bundle_id

    bundle = SupportBundle(
        bundle_id=bundle_id,
        session_id=session_id,
        actor_id=session.actor_id,
        tenant_id=session.tenant_id,
        correlation_id=correlation_id,
        generated_at=_utcnow(),
        diagnostics=filtered,
        redaction_applied=True,
        bundle_type=bundle_type,
    )

    _session_store.increment_bundle_count(session_id)

    # Write audit event
    from uuid import UUID as PyUUID

    wholesaler_id = None
    if session.tenant_id:
        try:
            wholesaler_id = PyUUID(session.tenant_id)
        except (ValueError, AttributeError):
            pass

    actor_id = session.actor_id

    await append_audit_entry(
        db,
        actor_type="api",
        action="support_bundle_generated",
        resource=f"support/sessions/{session_id}/bundles/{bundle_id}",
        actor_id=PyUUID(actor_id) if actor_id else None,
        wholesaler_id=wholesaler_id,
        audit_metadata={
            "session_id": session_id,
            "bundle_id": bundle_id,
            "bundle_type": bundle_type,
            "correlation_id": correlation_id,
            "diagnostic_count": len(filtered),
            "actor_role": session.actor_role,
        },
    )
    await db.commit()

    return bundle


async def close_support_session(
    db: AsyncSession,
    session_id: str,
) -> SupportSession:
    """
    Close an active support session and write audit event.
    """
    session = _session_store.get(session_id)
    if session is None:
        raise ValueError("Session not found or expired")

    if session.status != "active":
        raise ValueError(f"Session is already {session.status}")

    closed = _session_store.close(session_id)
    if closed is None:
        raise ValueError("Session not found during close")

    # Write audit event
    from uuid import UUID as PyUUID

    wholesaler_id = None
    if closed.tenant_id:
        try:
            wholesaler_id = PyUUID(closed.tenant_id)
        except (ValueError, AttributeError):
            pass

    await append_audit_entry(
        db,
        actor_type="api",
        action="support_session_end",
        resource=f"support/sessions/{session_id}",
        actor_id=PyUUID(closed.actor_id) if closed.actor_id else None,
        wholesaler_id=wholesaler_id,
        audit_metadata={
            "session_id": session_id,
            "correlation_id": closed.correlation_id,
            "bundle_count": closed.bundle_count,
            "actor_role": closed.actor_role,
        },
    )
    await db.commit()

    return closed
