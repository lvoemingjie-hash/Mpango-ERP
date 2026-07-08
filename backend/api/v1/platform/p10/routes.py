"""
FastAPI routes for P10 Platform Product read-only API.

All endpoints are GET-only. Mutation methods are rejected (405).
Responses match PLATFORM_PRODUCT_CONTRACTS.md exactly.

Endpoints:
  GET /api/v1/platform/p10/tenants                    — TenantSummary list
  GET /api/v1/platform/p10/tenants/{tenant_id}        — TenantSummary detail
  GET /api/v1/platform/p10/tenants/{tenant_id}/health  — TenantHealth detail
  GET /api/v1/platform/p10/system/health              — SystemHealth snapshot
  GET /api/v1/platform/p10/audit/events               — PlatformAuditEvent list (placeholder)
  GET /api/v1/platform/p10/audit/events/{event_id}    — PlatformAuditEvent detail (placeholder)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_platform_db

from . import services
from .guard import require_platform_operator
from .schemas import (
    TenantSummary,
    TenantSummaryList,
    TenantHealth,
    SystemHealth,
    PlatformAuditEvent,
    PlatformAuditEventList,
)

router = APIRouter(prefix="/api/v1/platform/p10", tags=["platform-p10"])


# ── TenantSummary ──


@router.get("/tenants", response_model=TenantSummaryList)
async def list_tenants(
    request: Request,
    limit: int = Query(50, ge=1, le=200, description="Max results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: AsyncSession = Depends(get_platform_db),
    _platform_auth: None = Depends(require_platform_operator),
):
    """List all tenants with P10-A contract-compliant summaries (read-only)."""
    return await services.list_tenant_summaries(db, limit=limit, offset=offset)


@router.get("/tenants/{tenant_id}", response_model=TenantSummary)
async def get_tenant(
    request: Request,
    tenant_id: str,
    db: AsyncSession = Depends(get_platform_db),
    _platform_auth: None = Depends(require_platform_operator),
):
    """Get a single tenant's P10-A contract-compliant summary (read-only)."""
    summary = await services.get_tenant_summary(db, tenant_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return summary


# ── TenantHealth ──


@router.get("/tenants/{tenant_id}/health", response_model=TenantHealth)
async def get_tenant_health(
    request: Request,
    tenant_id: str,
    db: AsyncSession = Depends(get_platform_db),
    _platform_auth: None = Depends(require_platform_operator),
):
    """Get P10-A contract-compliant health assessment for a single tenant (read-only)."""
    health = await services.get_tenant_health(db, tenant_id)
    if health is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return health


# ── SystemHealth ──


@router.get("/system/health", response_model=SystemHealth)
async def get_system_health(
    request: Request,
    db: AsyncSession = Depends(get_platform_db),
    _platform_auth: None = Depends(require_platform_operator),
):
    """Get P10-A contract-compliant platform-wide health snapshot (read-only)."""
    return await services.get_system_health(db)


# ── PlatformAuditEvent (placeholder) ──


@router.get("/audit/events", response_model=PlatformAuditEventList)
async def list_audit_events(
    request: Request,
    limit: int = Query(50, ge=1, le=200, description="Max results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: AsyncSession = Depends(get_platform_db),
    _platform_auth: None = Depends(require_platform_operator),
):
    """
    List platform audit events in P10-A contract shape (read-only, placeholder).

    This endpoint maps existing P0 audit log entries to the P10-A contract shape.
    Full fidelity requires P11+ platform auth and audit infrastructure.
    """
    return await services.list_audit_events(db, limit=limit, offset=offset)


@router.get("/audit/events/{event_id}", response_model=PlatformAuditEvent)
async def get_audit_event(
    request: Request,
    event_id: str,
    db: AsyncSession = Depends(get_platform_db),
    _platform_auth: None = Depends(require_platform_operator),
):
    """
    Get a single audit event in P10-A contract shape (read-only, placeholder).
    """
    event = await services.get_audit_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Audit event not found")
    return event
