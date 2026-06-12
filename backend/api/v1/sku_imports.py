"""U3-B2 SKU Import Router -- preview + validate endpoints.

Phase 1: POST /api/v1/skus/import/preview
    Accept CSV file, parse structure, return import_id.  No SKU writes.

Phase 2: POST /api/v1/skus/import/{import_id}/validate
    Accept field mapping, validate rows against rules, update import_runs.
    No SKU/inventory writes.

Both endpoints use RequirePermission("skus:import") per U3-B1 contract.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_tenant_db_session
from api.middleware.rbac import RequirePermission
from core.logging_config import get_request_logger
from core.security import TokenPayload
from schemas.common import DataResponse
from schemas.import_schemas import ImportValidateRequest, ImportValidateResponse
from services.import_service import ImportService

router = APIRouter()

# Max upload size: 10 MB
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


@router.post(
    "/preview",
    response_model=DataResponse[dict],
    status_code=status.HTTP_200_OK,
    summary="Phase 1: Parse CSV and preview import structure",
)
async def preview_import(
    request: Request,
    file: UploadFile = File(..., description="CSV file to import"),
    token: TokenPayload = Depends(RequirePermission("skus:import")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """Parse uploaded CSV, detect columns, create ImportRun, return preview.

    Does NOT write to SKU or inventory tables.
    """
    request_id = getattr(request.state, "request_id", "N/A")
    tenant_id_str = getattr(request.state, "tenant_id", None)
    logger = get_request_logger(request_id, tenant_id_str)

    # -- Validate content type --
    if file.content_type and file.content_type not in (
        "text/csv",
        "text/plain",
        "application/vnd.ms-excel",
        "application/octet-stream",
    ):
        logger.warning(
            "preview_invalid_content_type",
            extra={"action": "preview_import", "content_type": file.content_type},
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_CONTENT_TYPE",
                "message": f"Expected CSV file, got '{file.content_type}'",
            },
        )

    # -- Read file bytes --
    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "EMPTY_FILE",
                "message": "Uploaded file is empty",
            },
        )
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "FILE_TOO_LARGE",
                "message": (
                    f"File size {len(file_bytes)} bytes exceeds "
                    f"limit of {MAX_UPLOAD_BYTES} bytes"
                ),
            },
        )

    # -- Determine tenant --
    if not tenant_id_str:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "TENANT_CONTEXT_REQUIRED",
                "message": "Tenant context is required for import operations",
            },
        )

    import uuid as _uuid
    try:
        tenant_uuid = _uuid.UUID(str(tenant_id_str))
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_TENANT_ID",
                "message": "Could not parse tenant_id from context",
            },
        )

    logger.info(
        "preview_import_started",
        extra={
            "action": "preview_import",
            "user_id": token.user_id,
            "filename": file.filename,
            "file_size": len(file_bytes),
        },
    )

    try:
        service = ImportService()
        result = await service.preview(
            db,
            tenant_id=tenant_uuid,
            filename=file.filename or "upload.csv",
            file_bytes=file_bytes,
        )

        response = DataResponse(
            success=True,
            data=result.model_dump(),
            timestamp=datetime.utcnow(),
        )

        logger.info(
            "preview_import_completed",
            extra={
                "action": "preview_import",
                "import_id": result.import_id,
                "row_count": result.source.row_count,
                "success": True,
            },
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "preview_import_failed",
            extra={
                "action": "preview_import",
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        raise


@router.post(
    "/{import_id}/validate",
    response_model=DataResponse[dict],
    status_code=status.HTTP_200_OK,
    summary="Phase 2: Validate import with field mapping",
)
async def validate_import(
    import_id: str,
    body: ImportValidateRequest,
    request: Request,
    token: TokenPayload = Depends(RequirePermission("skus:import")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
    """Apply field mapping, validate rows against business rules.

    Does NOT write to SKU or inventory tables.
    Returns row-level errors/warnings and updated import status.
    """
    request_id = getattr(request.state, "request_id", "N/A")
    tenant_id_str = getattr(request.state, "tenant_id", None)
    logger = get_request_logger(request_id, tenant_id_str)

    logger.info(
        "validate_import_started",
        extra={
            "action": "validate_import",
            "user_id": token.user_id,
            "import_id": import_id,
        },
    )

    try:
        service = ImportService()
        result = await service.validate(
            db,
            import_id=import_id,
            mapping=body.mapping,
        )

        response = DataResponse(
            success=True,
            data=result.model_dump(),
            timestamp=datetime.utcnow(),
        )

        logger.info(
            "validate_import_completed",
            extra={
                "action": "validate_import",
                "import_id": import_id,
                "status": result.status,
                "valid_rows": result.valid_rows,
                "error_rows": result.error_rows,
                "success": True,
            },
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "validate_import_failed",
            extra={
                "action": "validate_import",
                "import_id": import_id,
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        raise
