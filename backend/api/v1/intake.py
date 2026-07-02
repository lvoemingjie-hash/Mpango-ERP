"""U4 internal intake workspace and staging API."""
from __future__ import annotations

import uuid
from datetime import datetime
from math import ceil
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.context import get_auth_context, get_tenant_context
from api.dependencies import get_tenant_db_session
from api.middleware.rbac import RequirePermission
from core.security import TokenPayload
from models.intake import IntakeProductRow, IntakeUpload, IntakeValidationIssue, IntakeWorkspace
from schemas.common import DataResponse, Pagination
from schemas.intake import (
    IntakeMappingRead,
    IntakeMappingRequest,
    IntakeProductRowRead,
    IntakeUploadRead,
    IntakeValidationIssueRead,
    IntakeValidationRead,
    IntakeWorkspaceCreateRequest,
    IntakeWorkspaceRead,
    IntakeWorkspaceStatus,
)
from services.intake_service import IntakeService


router = APIRouter()
intake_service = IntakeService()


class RequireAnyIntakePermission:
    """Require any one of the supplied intake permissions."""

    def __init__(self, *permissions: str):
        self.permissions = set(permissions)

    async def __call__(self, request: Request) -> TokenPayload:
        auth_ctx = get_auth_context(request)
        token = auth_ctx.token
        if token.is_identity_only and token.is_super_admin:
            return token

        try:
            tenant_ctx = get_tenant_context(request)
        except HTTPException:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "TENANT_CONTEXT_REQUIRED",
                    "message": "Please select a tenant first (POST /auth/select-tenant)",
                },
            )

        if token.is_super_admin:
            return token

        user_permissions = {
            permission.code
            for role in tenant_ctx.user.roles
            for permission in role.permissions
        }
        if self.permissions.isdisjoint(user_permissions):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "PERMISSION_DENIED",
                    "message": f"One of {sorted(self.permissions)} required",
                },
            )
        return token


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


async def _get_workspace_or_404(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> IntakeWorkspace:
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
    return workspace


def _upload_to_read(upload: IntakeUpload) -> IntakeUploadRead:
    return IntakeUploadRead(
        upload_id=str(upload.id),
        workspace_id=str(upload.workspace_id),
        filename=upload.filename,
        file_ext=upload.file_ext,
        status=upload.status,
        row_count=upload.row_count,
        column_count=upload.column_count,
        headers_raw=upload.headers_raw or [],
        headers_normalized=upload.headers_normalized or {},
        parse_summary=upload.parse_summary or {},
        created_at=upload.created_at,
    )


def _row_to_read(row: IntakeProductRow) -> IntakeProductRowRead:
    return IntakeProductRowRead(
        row_id=str(row.id),
        upload_id=str(row.upload_id),
        source_row_number=row.source_row_number,
        row_index=row.row_index,
        raw_values=row.raw_values or {},
        normalized_values=row.normalized_values or {},
        mapping_version=row.mapping_version,
        sku_code=row.sku_code,
        name=row.name,
        unit=row.unit,
        category=row.category,
        unit_price=str(row.unit_price) if row.unit_price is not None else None,
        barcode=row.barcode,
        review_status=row.review_status,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _issue_to_read(issue: IntakeValidationIssue) -> IntakeValidationIssueRead:
    return IntakeValidationIssueRead(
        issue_id=str(issue.id),
        upload_id=str(issue.upload_id) if issue.upload_id else None,
        row_id=str(issue.row_id) if issue.row_id else None,
        source_row_number=issue.source_row_number,
        severity=issue.severity,
        code=issue.code,
        field=issue.field,
        source_header=issue.source_header,
        message=issue.message,
        is_blocking=issue.is_blocking,
        created_at=issue.created_at,
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
    await db.flush()

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


@router.post(
    "/workspaces/{workspace_id}/uploads",
    response_model=DataResponse[IntakeUploadRead],
    status_code=status.HTTP_201_CREATED,
)
async def upload_intake_file(
    workspace_id: uuid.UUID,
    file: UploadFile = File(...),
    principal: TokenPayload = Depends(RequireAnyIntakePermission("intake:create", "intake:update")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """Parse a CSV/XLSX file and store staged raw product rows."""
    tenant_id = _uuid_or_403(
        principal.tenant_id,
        "TENANT_CONTEXT_REQUIRED",
        "Tenant context is required for intake upload operations",
    )
    user_id = _optional_uuid(principal.user_id)
    workspace = await _get_workspace_or_404(db, tenant_id=tenant_id, workspace_id=workspace_id)

    file_bytes = await file.read()
    parsed = intake_service.parse_upload(
        filename=file.filename or "upload",
        content_type=file.content_type,
        file_bytes=file_bytes,
    )
    upload, _ = await intake_service.create_upload_rows(
        db,
        tenant_id=tenant_id,
        workspace=workspace,
        parsed=parsed,
        user_id=user_id,
    )

    return DataResponse(success=True, data=_upload_to_read(upload), timestamp=datetime.utcnow())


@router.put(
    "/workspaces/{workspace_id}/mapping",
    response_model=DataResponse[IntakeMappingRead],
    status_code=status.HTTP_200_OK,
)
async def update_intake_mapping(
    workspace_id: uuid.UUID,
    body: IntakeMappingRequest,
    principal: TokenPayload = Depends(RequirePermission("intake:update")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """Apply column mapping to staged rows without touching SKU tables."""
    tenant_id = _uuid_or_403(
        principal.tenant_id,
        "TENANT_CONTEXT_REQUIRED",
        "Tenant context is required for intake mapping operations",
    )
    user_id = _optional_uuid(principal.user_id)
    workspace = await _get_workspace_or_404(db, tenant_id=tenant_id, workspace_id=workspace_id)

    mapped_rows = await intake_service.apply_mapping(
        db,
        tenant_id=tenant_id,
        workspace=workspace,
        mapping=body.mapping,
        user_id=user_id,
    )
    metadata = workspace.metadata_json or {}

    return DataResponse(
        success=True,
        data=IntakeMappingRead(
            workspace_id=str(workspace.id),
            mapped_rows=mapped_rows,
            mapping=metadata.get("column_mapping") or {},
            status=workspace.status,
            unit_default_note=metadata.get("unit_default_note") or "",
        ),
        timestamp=datetime.utcnow(),
    )


@router.post(
    "/workspaces/{workspace_id}/validate",
    response_model=DataResponse[IntakeValidationRead],
    status_code=status.HTTP_200_OK,
)
async def validate_intake_workspace(
    workspace_id: uuid.UUID,
    principal: TokenPayload = Depends(RequirePermission("intake:update")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """Validate staged rows and write row/file-level issues."""
    tenant_id = _uuid_or_403(
        principal.tenant_id,
        "TENANT_CONTEXT_REQUIRED",
        "Tenant context is required for intake validation operations",
    )
    user_id = _optional_uuid(principal.user_id)
    workspace = await _get_workspace_or_404(db, tenant_id=tenant_id, workspace_id=workspace_id)

    summary = await intake_service.validate_workspace(
        db,
        tenant_id=tenant_id,
        workspace=workspace,
        user_id=user_id,
    )

    return DataResponse(
        success=True,
        data=IntakeValidationRead(
            workspace_id=str(workspace.id),
            status=workspace.status,
            row_count=int(summary["row_count"]),
            error_count=int(summary["error_count"]),
            warning_count=int(summary["warning_count"]),
        ),
        timestamp=datetime.utcnow(),
    )


@router.get(
    "/workspaces/{workspace_id}/rows",
    response_model=DataResponse[dict],
    status_code=status.HTTP_200_OK,
)
async def list_intake_rows(
    workspace_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    principal: TokenPayload = Depends(RequirePermission("intake:read")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """List staged rows for a tenant-scoped intake workspace."""
    tenant_id = _uuid_or_403(
        principal.tenant_id,
        "TENANT_CONTEXT_REQUIRED",
        "Tenant context is required for intake row operations",
    )
    await _get_workspace_or_404(db, tenant_id=tenant_id, workspace_id=workspace_id)

    filters = [
        IntakeProductRow.tenant_id == tenant_id,
        IntakeProductRow.workspace_id == workspace_id,
        IntakeProductRow.is_deleted.is_(False),
    ]
    total = (await db.execute(select(func.count()).select_from(IntakeProductRow).where(*filters))).scalar_one()
    result = await db.execute(
        select(IntakeProductRow)
        .where(*filters)
        .order_by(IntakeProductRow.upload_id, IntakeProductRow.row_index)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    pages = ceil(total / page_size) if total else 0

    return DataResponse(
        success=True,
        data={
            "items": [_row_to_read(row) for row in result.scalars().all()],
            "pagination": Pagination(page=page, size=page_size, total=total, pages=pages).model_dump(),
        },
        timestamp=datetime.utcnow(),
    )


@router.get(
    "/workspaces/{workspace_id}/issues",
    response_model=DataResponse[dict],
    status_code=status.HTTP_200_OK,
)
async def list_intake_issues(
    workspace_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    severity: Optional[str] = Query(None),
    principal: TokenPayload = Depends(RequirePermission("intake:read")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """List validation issues for a tenant-scoped intake workspace."""
    tenant_id = _uuid_or_403(
        principal.tenant_id,
        "TENANT_CONTEXT_REQUIRED",
        "Tenant context is required for intake issue operations",
    )
    await _get_workspace_or_404(db, tenant_id=tenant_id, workspace_id=workspace_id)

    filters = [
        IntakeValidationIssue.tenant_id == tenant_id,
        IntakeValidationIssue.workspace_id == workspace_id,
        IntakeValidationIssue.is_deleted.is_(False),
    ]
    if severity:
        filters.append(IntakeValidationIssue.severity == severity.upper())

    total = (await db.execute(select(func.count()).select_from(IntakeValidationIssue).where(*filters))).scalar_one()
    result = await db.execute(
        select(IntakeValidationIssue)
        .where(*filters)
        .order_by(IntakeValidationIssue.created_at, IntakeValidationIssue.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    pages = ceil(total / page_size) if total else 0

    return DataResponse(
        success=True,
        data={
            "items": [_issue_to_read(issue) for issue in result.scalars().all()],
            "pagination": Pagination(page=page, size=page_size, total=total, pages=pages).model_dump(),
        },
        timestamp=datetime.utcnow(),
    )
