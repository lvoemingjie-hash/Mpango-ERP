"""U4-C internal intake workspace API."""
from __future__ import annotations

import uuid
from datetime import datetime
from math import ceil
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_tenant_db_session
from api.middleware.rbac import RequirePermission
from core.security import TokenPayload
from models.intake import IntakeWorkspace
from schemas.common import DataResponse, Pagination
from schemas.intake import IntakeWorkspaceCreateRequest, IntakeWorkspaceRead, IntakeWorkspaceStatus


router = APIRouter()


def _uuid_or_403(value: Optional[str], code: str, message: str) -> uuid.UUID:
    if not value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": code, "message": message},
        )
    try:
        return uuid.UUID(str(value))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_TENANT_ID", "message": "Could not parse tenant_id from context"},
        )


def _optional_uuid(value: str) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def _workspace_to_read(workspace: IntakeWorkspace) -> IntakeWorkspaceRead:
    return IntakeWorkspaceRead(
        workspace_id=str(workspace.id),
        tenant_id=str(workspace.tenant_id),
        name=workspace.name,
        description=workspace.description,
        source_type=workspace.source_type,
        status=workspace.status,
        metadata=workspace.metadata_json or {},
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
    )


@router.post(
    "/workspaces",
    response_model=DataResponse[IntakeWorkspaceRead],
    status_code=status.HTTP_201_CREATED,
)
async def create_workspace(
    body: IntakeWorkspaceCreateRequest,
    principal: TokenPayload = Depends(RequirePermission("intake:create")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """Create a tenant-scoped intake workspace for internal users."""
    tenant_id = _uuid_or_403(
        principal.tenant_id,
        "TENANT_CONTEXT_REQUIRED",
        "Tenant context is required for intake workspace operations",
    )
    user_id = _optional_uuid(principal.user_id)

    workspace = IntakeWorkspace(
        tenant_id=tenant_id,
        name=body.name,
        description=body.description,
        source_type=body.source_type,
        status="OPEN",
        metadata_json=body.metadata,
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(workspace)
    await db.commit()
    await db.refresh(workspace)

    return DataResponse(
        success=True,
        data=_workspace_to_read(workspace),
        timestamp=datetime.utcnow(),
    )


@router.get(
    "/workspaces",
    response_model=DataResponse[dict],
    status_code=status.HTTP_200_OK,
)
async def list_workspaces(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    workspace_status: Optional[IntakeWorkspaceStatus] = Query(None, alias="status"),
    principal: TokenPayload = Depends(RequirePermission("intake:read")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """List tenant-scoped intake workspaces."""
    tenant_id = _uuid_or_403(
        principal.tenant_id,
        "TENANT_CONTEXT_REQUIRED",
        "Tenant context is required for intake workspace operations",
    )

    filters = [IntakeWorkspace.tenant_id == tenant_id, IntakeWorkspace.is_deleted.is_(False)]
    if workspace_status:
        filters.append(IntakeWorkspace.status == workspace_status)

    total = (
        await db.execute(select(func.count()).select_from(IntakeWorkspace).where(*filters))
    ).scalar_one()
    result = await db.execute(
        select(IntakeWorkspace)
        .where(*filters)
        .order_by(IntakeWorkspace.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [_workspace_to_read(workspace) for workspace in result.scalars().all()]
    pages = ceil(total / page_size) if total else 0

    return DataResponse(
        success=True,
        data={
            "items": items,
            "pagination": Pagination(page=page, size=page_size, total=total, pages=pages).model_dump(),
        },
        timestamp=datetime.utcnow(),
    )


@router.get(
    "/workspaces/{workspace_id}",
    response_model=DataResponse[IntakeWorkspaceRead],
    status_code=status.HTTP_200_OK,
)
async def get_workspace(
    workspace_id: uuid.UUID,
    principal: TokenPayload = Depends(RequirePermission("intake:read")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """Read one tenant-scoped intake workspace."""
    tenant_id = _uuid_or_403(
        principal.tenant_id,
        "TENANT_CONTEXT_REQUIRED",
        "Tenant context is required for intake workspace operations",
    )

    result = await db.execute(
        select(IntakeWorkspace).where(
            IntakeWorkspace.id == workspace_id,
            IntakeWorkspace.tenant_id == tenant_id,
            IntakeWorkspace.is_deleted.is_(False),
        )
    )
    workspace = result.scalar_one_or_none()
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "WORKSPACE_NOT_FOUND", "message": "Intake workspace not found"},
        )

    return DataResponse(
        success=True,
        data=_workspace_to_read(workspace),
        timestamp=datetime.utcnow(),
    )
