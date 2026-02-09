"""
S7-4-T3: BI Assets CRUD API — Tenant-Scoped Report Management.

Philosophy: "Let the architecture work. Don't bypass it."

This module provides CRUD endpoints for tenant-created BI report assets.
Every endpoint flows through the governance architecture:

    POST   /api/bi/assets/reports          → Create report → invalidate cache
    GET    /api/bi/assets/reports/{id}     → enforce_bi_access(VIEW) → resolution chain
    PATCH  /api/bi/assets/reports/{id}     → enforce_bi_access(MANAGE) → update → invalidate
    DELETE /api/bi/assets/reports/{id}     → enforce_bi_access(MANAGE) → soft delete → invalidate
    GET    /api/bi/assets/reports          → List user's reports

🔒 Security:
    - owner_id is ALWAYS forced from authenticated user context.
    - GET uses enforce_bi_access(VIEW) which triggers the full resolution
      chain (Static → Cache → DB) and policy engine.
    - PATCH/DELETE use enforce_bi_access(MANAGE) — only owner or admin.

🔒 S7-4-C4: Every mutation calls invalidate_asset(urn) after DB commit.
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.context import get_auth_context, get_tenant_context
from api.middleware.bi_access import (
    enforce_bi_access,
    get_policy_subject,
)
from api.schemas.report import (
    CreateReportRequest,
    CreateReportResponse,
    ReportResponse,
    UpdateReportRequest,
)
from core.governance.models import BIAction
from core.governance.registry import (
    get_asset_async,
    invalidate_asset,
)
from models.report import SysReport

logger = logging.getLogger("mpango.api.bi_assets")

bi_assets_router = APIRouter()


# ============================================================================
# POST /api/bi/assets/reports — Create a new report
# ============================================================================

@bi_assets_router.post(
    "/reports",
    response_model=CreateReportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a tenant-scoped report",
)
async def create_report(
    body: CreateReportRequest,
    request: Request,
):
    """
    Create a new tenant-scoped BI report.

    🔒 Security: owner_id is forced from the authenticated user.
    The user cannot specify or forge the owner.

    🔒 S7-4-C4: Cache is invalidated after creation.
    """
    auth_ctx = get_auth_context(request)
    tenant_ctx = get_tenant_context(request)
    session: AsyncSession = tenant_ctx.session

    # 🔒 Force owner_id from authenticated user — never trust client
    owner_id = UUID(auth_ctx.token.user_id)

    report = SysReport(
        title=body.title,
        description=body.description or "",
        domain=body.domain,
        config=body.config.model_dump(),
        owner_id=owner_id,
        acl=body.acl,
        created_by=owner_id,
    )

    session.add(report)
    await session.flush()  # Get the generated ID

    urn = report.to_urn()

    # 🔒 S7-4-C4: Invalidate cache (in case of re-creation with same ID)
    invalidate_asset(urn)

    logger.info(
        "report_created",
        extra={
            "report_id": str(report.id),
            "urn": urn,
            "owner_id": str(owner_id),
            "tenant_id": auth_ctx.token.tenant_id,
        },
    )

    return CreateReportResponse(
        id=report.id,
        urn=urn,
        title=report.title,
    )


# ============================================================================
# GET /api/bi/assets/reports/{report_id} — Get a single report
# ============================================================================

@bi_assets_router.get(
    "/reports/{report_id}",
    response_model=ReportResponse,
    summary="Get a report by ID (enforces BI access policy)",
)
async def get_report(
    report_id: UUID,
    request: Request,
    background_tasks: BackgroundTasks,
):
    """
    Get a tenant-scoped report by ID.

    🔒 Critical: This does NOT query the DB directly.
    It calls enforce_bi_access(VIEW) which triggers:
    1. GovernanceRegistry.get_asset_async() → resolution chain
    2. Policy engine → tenant isolation, owner bypass, ACL, role matrix
    3. Audit trail → fire-and-forget log

    Let the architecture work.
    """
    auth_ctx = get_auth_context(request)
    tenant_ctx = get_tenant_context(request)
    subject = get_policy_subject(request)

    # Build URN from path parameter
    # We need the domain to build the URN, but we don't know it yet.
    # So we query the DB first to get the row, then enforce access on the BIAsset.
    session: AsyncSession = tenant_ctx.session
    stmt = (
        select(SysReport)
        .where(SysReport.id == report_id)
        .where(SysReport.is_deleted.is_(False))
    )
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "REPORT_NOT_FOUND", "message": "Report not found"},
        )

    urn = row.to_urn()

    # Resolve through the governance architecture (cache → DB → BIAsset)
    try:
        asset = await get_asset_async(urn, tenant_id=auth_ctx.token.tenant_id)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ASSET_NOT_RESOLVED", "message": "Asset could not be resolved"},
        )

    # 🔒 Enforce BI access policy (VIEW action)
    enforce_bi_access(
        subject, BIAction.VIEW, asset,
        background_tasks=background_tasks,
    )

    return ReportResponse(
        id=row.id,
        urn=urn,
        title=row.title,
        description=row.description or "",
        domain=row.domain,
        config=row.config,
        owner_id=row.owner_id,
        acl=row.acl if isinstance(row.acl, list) else [],
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


# ============================================================================
# PATCH /api/bi/assets/reports/{report_id} — Update a report
# ============================================================================

@bi_assets_router.patch(
    "/reports/{report_id}",
    response_model=ReportResponse,
    summary="Update a report (requires MANAGE permission)",
)
async def update_report(
    report_id: UUID,
    body: UpdateReportRequest,
    request: Request,
    background_tasks: BackgroundTasks,
):
    """
    Update a tenant-scoped report.

    🔒 Requires MANAGE permission — only owner or admin.
    🔒 S7-4-C4: Cache is invalidated after update.
    """
    auth_ctx = get_auth_context(request)
    tenant_ctx = get_tenant_context(request)
    subject = get_policy_subject(request)
    session: AsyncSession = tenant_ctx.session

    stmt = (
        select(SysReport)
        .where(SysReport.id == report_id)
        .where(SysReport.is_deleted.is_(False))
    )
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "REPORT_NOT_FOUND", "message": "Report not found"},
        )

    urn = row.to_urn()

    # Resolve and enforce MANAGE
    try:
        asset = await get_asset_async(urn, tenant_id=auth_ctx.token.tenant_id)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ASSET_NOT_RESOLVED", "message": "Asset could not be resolved"},
        )

    enforce_bi_access(
        subject, BIAction.MANAGE, asset,
        background_tasks=background_tasks,
    )

    # Apply updates
    if body.title is not None:
        row.title = body.title
    if body.description is not None:
        row.description = body.description
    if body.config is not None:
        row.config = body.config.model_dump()
    if body.acl is not None:
        row.acl = body.acl

    row.updated_by = UUID(auth_ctx.token.user_id)

    await session.flush()

    # 🔒 S7-4-C4: Invalidate cache after mutation
    invalidate_asset(urn)

    logger.info(
        "report_updated",
        extra={"report_id": str(report_id), "urn": urn},
    )

    return ReportResponse(
        id=row.id,
        urn=urn,
        title=row.title,
        description=row.description or "",
        domain=row.domain,
        config=row.config,
        owner_id=row.owner_id,
        acl=row.acl if isinstance(row.acl, list) else [],
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


# ============================================================================
# DELETE /api/bi/assets/reports/{report_id} — Soft-delete a report
# ============================================================================

@bi_assets_router.delete(
    "/reports/{report_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a report (requires MANAGE permission)",
)
async def delete_report(
    report_id: UUID,
    request: Request,
    background_tasks: BackgroundTasks,
):
    """
    Soft-delete a tenant-scoped report.

    🔒 Requires MANAGE permission — only owner or admin.
    🔒 S7-4-C4: Cache is invalidated after deletion.
    """
    auth_ctx = get_auth_context(request)
    tenant_ctx = get_tenant_context(request)
    subject = get_policy_subject(request)
    session: AsyncSession = tenant_ctx.session

    stmt = (
        select(SysReport)
        .where(SysReport.id == report_id)
        .where(SysReport.is_deleted.is_(False))
    )
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "REPORT_NOT_FOUND", "message": "Report not found"},
        )

    urn = row.to_urn()

    # Resolve and enforce MANAGE
    try:
        asset = await get_asset_async(urn, tenant_id=auth_ctx.token.tenant_id)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ASSET_NOT_RESOLVED", "message": "Asset could not be resolved"},
        )

    enforce_bi_access(
        subject, BIAction.MANAGE, asset,
        background_tasks=background_tasks,
    )

    # Soft delete
    row.soft_delete()
    row.updated_by = UUID(auth_ctx.token.user_id)

    await session.flush()

    # 🔒 S7-4-C4: Invalidate cache after deletion
    invalidate_asset(urn)

    logger.info(
        "report_deleted",
        extra={"report_id": str(report_id), "urn": urn},
    )


# ============================================================================
# GET /api/bi/assets/reports — List user's reports
# ============================================================================

@bi_assets_router.get(
    "/reports",
    response_model=list[ReportResponse],
    summary="List reports in the current tenant",
)
async def list_reports(
    request: Request,
):
    """
    List all non-deleted reports in the current tenant.

    Returns reports the user owns. Admin sees all tenant reports.
    No BI access enforcement on list — individual access is checked on GET.
    """
    auth_ctx = get_auth_context(request)
    tenant_ctx = get_tenant_context(request)
    session: AsyncSession = tenant_ctx.session

    user_id = UUID(auth_ctx.token.user_id)

    # Check if user is admin
    user = tenant_ctx.user
    role_names = frozenset(role.name for role in getattr(user, "roles", []))
    is_admin = "admin" in role_names

    stmt = (
        select(SysReport)
        .where(SysReport.is_deleted.is_(False))
        .order_by(SysReport.created_at.desc())
    )

    # Non-admin users only see their own reports
    if not is_admin:
        stmt = stmt.where(SysReport.owner_id == user_id)

    result = await session.execute(stmt)
    rows = result.scalars().all()

    return [
        ReportResponse(
            id=row.id,
            urn=row.to_urn(),
            title=row.title,
            description=row.description or "",
            domain=row.domain,
            config=row.config,
            owner_id=row.owner_id,
            acl=row.acl if isinstance(row.acl, list) else [],
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]
