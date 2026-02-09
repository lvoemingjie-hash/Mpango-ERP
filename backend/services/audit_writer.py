"""
S7-3: Audit Writer Service — Fire and Forget.

This module provides the async write function that persists PolicyResult
to the sys_audit_logs table. It is designed to be called from FastAPI's
BackgroundTasks, ensuring zero impact on request latency.

🔒 Constraint S7-3-C3 (CTO Mandate, Frozen):
    - Audit failure MUST NOT affect the original request result.
    - Audit failure MUST be observable (structured error log).
    - The policy decision is already final before this function runs.

Design:
    write_audit_log(result, metadata=None)
        → Opens its own AsyncSession (public schema)
        → INSERT INTO sys_audit_logs
        → Commit
        → On failure: log error, do NOT raise

    This function is the ONLY legal way to write to sys_audit_logs.
    Direct ORM inserts from business code are forbidden.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from core.governance.policy import PolicyResult
from database.session import AsyncSessionLocal
from models.audit import SysAuditLog

logger = logging.getLogger("mpango.audit")


async def write_audit_log(
    result: PolicyResult,
    tenant_id: str,
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    """
    Persist a PolicyResult to the sys_audit_logs table.

    This function is designed to be called from BackgroundTasks.
    It manages its own database session and NEVER raises exceptions
    to the caller (🔒 S7-3-C3: audit failure must not affect business).

    Args:
        result: The PolicyResult from evaluate_policy().
        tenant_id: The tenant_id from PolicySubject (passed by enforcement layer).
        metadata: Optional JSONB context (request_id, IP, user_agent, etc.).
    """
    try:
        async with AsyncSessionLocal() as session:
            session.info["tenant_schema"] = "public"

            log_entry = SysAuditLog(
                actor_id=result.subject_id,
                tenant_id=tenant_id,
                action=result.action,
                asset_urn=result.asset_urn,
                allowed=result.allowed,
                policy_name=result.policy_name,
                reason=result.reason,
                metadata_=metadata,
            )

            session.add(log_entry)
            await session.commit()

            logger.debug(
                "audit_log_written",
                extra={
                    "audit_id": str(log_entry.id),
                    "actor_id": result.subject_id,
                    "tenant_id": tenant_id,
                    "action": result.action,
                    "asset_urn": result.asset_urn,
                    "allowed": result.allowed,
                },
            )

    except Exception as exc:
        # 🔒 S7-3-C3: Audit failure must be observable but NOT propagated
        logger.error(
            "audit_log_write_failed",
            exc_info=exc,
            extra={
                "actor_id": result.subject_id,
                "tenant_id": tenant_id,
                "action": result.action,
                "asset_urn": result.asset_urn,
                "allowed": result.allowed,
                "error": str(exc),
            },
        )
        # Explicitly swallow — do NOT re-raise
