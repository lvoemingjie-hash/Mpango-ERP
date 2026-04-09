"""
Platform audit appender service — internal use only.

This module provides the single entry point for writing platform audit entries.
It is NOT exposed as a public API endpoint.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from models.platform_audit_log import PlatformAuditLog


async def append_audit_entry(
    db: AsyncSession,
    *,
    actor_type: str,
    action: str,
    resource: str,
    actor_id: Optional[UUID] = None,
    wholesaler_id: Optional[UUID] = None,
    audit_metadata: Optional[dict] = None,
) -> PlatformAuditLog:
    """
    Append a single audit log entry. Returns the created record.

    actor_type and actor_id are set server-side, never from client request body.
    created_at is set by database default, never passed explicitly.
    """
    entry = PlatformAuditLog(
        actor_type=actor_type,
        actor_id=actor_id,
        wholesaler_id=wholesaler_id,
        action=action,
        resource=resource,
        audit_metadata=audit_metadata or {},
    )
    db.add(entry)
    await db.flush()
    return entry
