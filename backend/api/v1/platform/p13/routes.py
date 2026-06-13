"""
FastAPI routes for P13 Operations Observability Cockpit API.

All endpoints are GET-only (read-only). No mutations.
Responses match PLATFORM_PRODUCT_P13_OPERATIONS_COCKPIT_CONTRACT.md exactly.

Endpoints:
  GET /api/v1/platform/p13/ops/health          -- System health with P13 extensions
  GET /api/v1/platform/p13/ops/errors           -- Error rate analysis
  GET /api/v1/platform/p13/ops/slow-routes      -- Slow route analysis
  GET /api/v1/platform/p13/ops/resources         -- Resource health summary
  GET /api/v1/platform/p13/ops/noisy-neighbors   -- Noisy-neighbor detection

All endpoints require identity-only super_admin (P10 guard).
Tenant-contextual super_admin and non-super_admin roles are denied.
Every view writes an ops audit event.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from api.v1.platform.p10.guard import require_platform_operator
from api.v1.platform.p10.schemas import SystemHealth

from . import services
from .schemas import (
    ErrorRateSummary,
    NoisyNeighborSummary,
    ResourceHealthSummary,
    SlowRouteSummary,
)

router = APIRouter(prefix="/api/v1/platform/p13", tags=["platform-p13"])


# -- Access-denied audit helper --


async def _write_access_denied_audit(
    db: AsyncSession,
    request: Request,
    exc: HTTPException,
) -> None:
    """Write ops_access_denied audit event. Best-effort."""
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
                "scope": "operations",
            },
        )
        await db.commit()
    except Exception:
        pass


async def require_platform_operator_with_ops_audit(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_platform_operator: Optional[str] = Header(
        None,
        alias="X-Platform-Operator",
        description="Platform operator shared secret",
    ),
    x_platform_test_override: Optional[str] = Header(
        None,
        alias="X-Platform-Test-Override",
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


# -- GET /ops/health --


@router.get("/ops/health", response_model=SystemHealth)
async def get_ops_health(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _platform_auth: None = Depends(require_platform_operator_with_ops_audit),
):
    """System health with P13 extensions (read-only).

    Reuses P10 system health endpoint data.
    P13 extensions (error rate, slow requests) come from separate endpoints.
    """
    await services._write_ops_audit(db, request, action="ops_health_view", view_type="health")
    from api.v1.platform.p10 import services as p10_services
    return await p10_services.get_system_health(db)


# -- GET /ops/errors --


@router.get("/ops/errors", response_model=ErrorRateSummary)
async def get_ops_errors(
    request: Request,
    window: int = Query(15, ge=1, le=1440, description="Aggregation window in minutes"),
    db: AsyncSession = Depends(get_db),
    _platform_auth: None = Depends(require_platform_operator_with_ops_audit),
):
    """Error rate analysis (read-only).

    Returns aggregated error counts by class, route, and tenant.
    Telemetry not yet instrumented -- source_status is 'unavailable'.
    """
    await services._write_ops_audit(
        db, request, action="ops_error_analysis_view",
        view_type="errors", window_minutes=window,
    )
    return await services.get_error_rate_summary(db, window_minutes=window)


# -- GET /ops/slow-routes --


@router.get("/ops/slow-routes", response_model=SlowRouteSummary)
async def get_ops_slow_routes(
    request: Request,
    window: int = Query(15, ge=1, le=1440, description="Aggregation window in minutes"),
    threshold: int = Query(1000, ge=1, le=60000, description="Slow threshold in ms"),
    db: AsyncSession = Depends(get_db),
    _platform_auth: None = Depends(require_platform_operator_with_ops_audit),
):
    """Slow route analysis (read-only).

    Returns routes exceeding latency thresholds.
    Telemetry not yet instrumented -- source_status is 'unavailable'.
    """
    await services._write_ops_audit(
        db, request, action="ops_slow_route_view",
        view_type="slow_routes", window_minutes=window,
    )
    return await services.get_slow_route_summary(
        db, window_minutes=window, threshold_ms=threshold,
    )


# -- GET /ops/resources --


@router.get("/ops/resources", response_model=ResourceHealthSummary)
async def get_ops_resources(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _platform_auth: None = Depends(require_platform_operator_with_ops_audit),
):
    """Resource health summary (read-only).

    Returns DB, queue, CPU, memory, disk health summaries.
    Only DB pool stats are partially available (from P10).
    """
    await services._write_ops_audit(
        db, request, action="ops_resource_view", view_type="resources",
    )
    return await services.get_resource_health_summary(db)


# -- GET /ops/noisy-neighbors --


@router.get("/ops/noisy-neighbors", response_model=NoisyNeighborSummary)
async def get_ops_noisy_neighbors(
    request: Request,
    window: int = Query(15, ge=1, le=1440, description="Aggregation window in minutes"),
    db: AsyncSession = Depends(get_db),
    _platform_auth: None = Depends(require_platform_operator_with_ops_audit),
):
    """Noisy-neighbor detection (read-only).

    Returns tenants with disproportionate error rates or slow routes.
    Cross-tenant telemetry not yet instrumented -- returns empty list.
    """
    await services._write_ops_audit(
        db, request, action="ops_noisy_neighbor_view",
        view_type="noisy_neighbors", window_minutes=window,
    )
    return await services.get_noisy_neighbor_summary(db, window_minutes=window)
