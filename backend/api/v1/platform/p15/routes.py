"""
FastAPI routes for P15 Incident Triage (read-only snapshot API).

All endpoints are GET-only (read-only). No mutations.
Responses match PLATFORM_PRODUCT_P15_INCIDENT_TRIAGE_CONTRACT.md (P15-A).

Endpoints:
  GET /api/v1/platform/p15/incidents/triage/snapshot   -- read-only triage snapshot

All endpoints require identity-only super_admin (P10 guard). Tenant-contextual
super_admin and non-super_admin roles are denied. The snapshot aggregates only
existing P10/P13/P14 read-only sources; it performs no writes and no tenant
business-data reads.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_platform_db
from api.v1.platform.p10.guard import require_platform_operator

from . import services
from .schemas import IncidentTriageSnapshot

router = APIRouter(prefix="/api/v1/platform/p15", tags=["platform-p15"])


# -- Access-denied audit helper (best-effort, mirrors P13) --


async def _write_access_denied_audit(
    db: AsyncSession,
    request: Request,
    exc: HTTPException,
) -> None:
    """Write an ops_access_denied audit event. Best-effort."""
    try:
        from uuid import UUID as PyUUID

        actor_id = None
        actor_role = None
        has_tenant_context = False
        try:
            from api.context.auth import get_auth_context
            auth_ctx = get_auth_context(request)
            token = auth_ctx.token
            actor_id = token.user_id
            has_tenant_context = not getattr(token, "is_identity_only", True)
            if getattr(token, "is_super_admin", False):
                actor_role = "super_admin"
        except Exception:
            pass

        detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}

        from services.platform_audit_service import append_audit_entry

        await append_audit_entry(
            db,
            actor_type="api",
            action="ops_access_denied",
            resource=f"ops{request.url.path}",
            actor_id=PyUUID(actor_id) if actor_id else None,
            wholesaler_id=None,
            audit_metadata={
                "code": detail.get("code", "UNKNOWN"),
                "reason": detail.get("message", ""),
                "path": str(request.url.path),
                "actor_id": actor_id,
                "actor_role": actor_role,
                "has_tenant_context": has_tenant_context,
                "scope": "incident_triage",
            },
        )
        await db.commit()
    except Exception:
        pass


async def require_platform_operator_with_triage_audit(
    request: Request,
    db: AsyncSession = Depends(get_platform_db),
    x_platform_operator: Optional[str] = Header(
        None, alias="X-Platform-Operator",
        description="Platform operator shared secret",
    ),
    x_platform_test_override: Optional[str] = Header(
        None, alias="X-Platform-Test-Override",
        description="Test override (MPANGO_ENV=test|testing only)",
    ),
) -> None:
    """Platform operator guard with ops_access_denied audit on denial."""
    try:
        require_platform_operator(request, x_platform_operator, x_platform_test_override)
    except HTTPException as exc:
        if exc.status_code in (401, 403):
            await _write_access_denied_audit(db, request, exc)
        raise


# -- GET /incidents/triage/snapshot --


async def _write_triage_view_audit(db: AsyncSession, request: Request) -> None:
    """Best-effort audit for a successful triage snapshot view. Never blocks."""
    try:
        from uuid import UUID as PyUUID

        actor_id = None
        actor_role = None
        try:
            from api.context.auth import get_auth_context
            auth_ctx = get_auth_context(request)
            token = auth_ctx.token
            actor_id = token.user_id
            if getattr(token, "is_super_admin", False):
                actor_role = "super_admin"
        except Exception:
            pass

        from services.platform_audit_service import append_audit_entry

        await append_audit_entry(
            db,
            actor_type="api",
            action="ops_incident_triage_view",
            resource="ops/incidents/triage/snapshot",
            actor_id=PyUUID(actor_id) if actor_id else None,
            wholesaler_id=None,
            audit_metadata={
                "view_type": "incident_triage",
                "actor_role": actor_role,
                "scope": "incident_triage",
            },
        )
        await db.commit()
    except Exception:
        pass  # Audit failure must not prevent the read-only response


@router.get("/incidents/triage/snapshot", response_model=IncidentTriageSnapshot)
async def get_incident_triage_snapshot(
    request: Request,
    db: AsyncSession = Depends(get_platform_db),
    _platform_auth: None = Depends(require_platform_operator_with_triage_audit),
) -> IncidentTriageSnapshot:
    """Read-only incident triage snapshot (P15-B).

    Aggregates existing P10/P13/P14 read-only sources into a single triage view.
    graceful_degraded=true when assembled despite a source failure. No writes, no
    tenant business records, no credentials/DSN/host/port.
    """
    await _write_triage_view_audit(db, request)
    return await services.build_triage_snapshot(db)
