"""
S6-4: Export API Router - Async File Export Endpoints.

Philosophy: "Request now, download later."

Architecture:
    POST /api/v1/exports          -> Enqueue export job (returns job_id)
    GET  /api/v1/exports/{job_id} -> Poll export status (returns progress/download URL)
    GET  /api/v1/exports/{job_id}/download -> Download the exported file

Context Propagation (Critical):
    The POST endpoint runs in authenticated HTTP context. It captures
    tenant_id from request.state (JWT claims) and serializes it into
    the ExportJobPayload. The S4 worker then reconstructs the tenant
    context from the payload - never from ambient state.

    JWT -> request.state -> TenantContext -> ExportJobPayload -> Job Queue -> Worker

Security:
    - tenant_id comes ONLY from request.state (Rule #1)
    - All view/metric/dimension inputs are whitelisted Enums (Rule #4)
    - Worker re-validates tenant_id and enums (defense in depth)
    - Download endpoint verifies tenant_id matches the export's tenant

API Contract Compliance (api_contract.md section 3):
    - Success: {"success": true, "data": {...}, "timestamp": "..."}
    - Error:   {"success": false, "error": {"code": ..., "message": ...}, "timestamp": "..."}
"""
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import FileResponse, JSONResponse

from api.context.tenant import TenantContext, get_tenant_context
from api.middleware.rbac import RequirePermission
from api.schemas.dashboard import make_success, make_error
from core.security import TokenPayload
from api.schemas.jobs import (
    ExportRequest,
    ExportJobPayload,
    ExportStatusData,
)
from services.reporting.semantic_layer import (
    get_view_registration,
)
from core.structured_logging import get_logger

logger = get_logger(__name__)

# ============================================================================
# Router
# ============================================================================

exports_router = APIRouter(tags=["exports"])


# ============================================================================
# Helper: Extract tenant context
# ============================================================================

def _extract_tenant(request: Request) -> TenantContext:
    """
    Extract validated TenantContext from request.state.

    #[Constraint Check] Rule #1: tenant_id comes ONLY from trusted context
    """
    return get_tenant_context(request)


def _parse_export_job_id(job_id: str) -> uuid.UUID | None:
    """Parse external job IDs before DB lookup so malformed IDs fail closed."""
    try:
        return uuid.UUID(job_id)
    except (TypeError, ValueError, AttributeError):
        return None


def _invalid_export_id_response() -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=make_error(
            "INVALID_EXPORT_ID",
            "Export job id must be a valid UUID",
        ),
    )


# ============================================================================
# POST /exports - Enqueue an export job
# ============================================================================

@exports_router.post(
    "",
    summary="Request Data Export",
    description=(
        "Enqueue an async export job. Returns a job_id immediately. "
        "Poll GET /exports/{job_id} for status and download URL. "
        "All view/metric/dimension fields must be valid enum values."
    ),
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_export(
    request: Request,
    body: ExportRequest,
    token: TokenPayload = Depends(RequirePermission("exports:create")),
) -> JSONResponse:
    """
    Enqueue an export job via the S4 Job Queue.

    Steps:
    1. Extract tenant context from JWT (request.state)
    2. Validate cross-view metric/dimension availability
    3. Build ExportJobPayload with tenant context serialized
    4. Enqueue "export_report" job
    5. Return 202 Accepted with job_id

    The actual file generation happens in the detached worker
    (jobs/export_jobs.py::export_report_worker).
    """
    #[Constraint Check] Rule #1: tenant_id from trusted HTTP context only
    tenant_ctx: TenantContext = _extract_tenant(request)

    # --- Cross-view validation (same as S6-3 analyze endpoint) ---
    registration = get_view_registration(body.view)
    for metric in body.metrics:
        if metric not in registration.metrics:
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                content=make_error(
                    code="METRIC_NOT_AVAILABLE",
                    message=(
                        f"Metric '{metric.value}' is not available on "
                        f"view '{body.view.value}'"
                    ),
                    available_values=[m.value for m in registration.metrics],
                ),
            )

    if body.dimensions:
        for dim in body.dimensions:
            if dim not in registration.dimensions:
                return JSONResponse(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    content=make_error(
                        code="DIMENSION_NOT_AVAILABLE",
                        message=(
                            f"Dimension '{dim.value}' is not available on "
                            f"view '{body.view.value}'"
                        ),
                        available_values=[d.value for d in registration.dimensions],
                    ),
                )

    # --- Build serializable payload with tenant context ---
    #[Constraint Check] Rule #1: tenant_id serialized from request.state into payload
    job_payload = ExportJobPayload.from_request(
        request=body,
        tenant_id=tenant_ctx.tenant_id,
        tenant_schema=tenant_ctx.tenant_schema,
        user_id=str(getattr(tenant_ctx.user, "id", "unknown")),
    )

    # --- Enqueue via S4 Job Queue ---
    try:
        from main import get_job_queue

        queue = get_job_queue()
        job_id = await queue.enqueue(
            job_name="export_report",
            payload=job_payload.model_dump(),
            max_retries=2,
        )
    except Exception as e:
        logger.error(
            f"Failed to enqueue export job: {type(e).__name__}",
            extra={"tenant_id": tenant_ctx.tenant_id, "error_class": type(e).__name__}
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=make_error(
                "EXPORT_ENQUEUE_FAILED",
                "Unable to enqueue export job. Please try again later.",
            ),
        )

    logger.info(
        "Export job enqueued",
        extra={
            "job_id": job_id,
            "tenant_id": tenant_ctx.tenant_id,
            "view": body.view.value,
            "format": body.format.value,
        }
    )

    data = ExportStatusData(
        job_id=job_id,
        status="pending",
        format=body.format.value,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=make_success(data, message="Export job enqueued"),
    )


# ============================================================================
# GET /exports/{job_id} - Poll export status
# ============================================================================

@exports_router.get(
    "/{job_id}",
    summary="Get Export Status",
    description=(
        "Poll the status of an export job. When completed, includes "
        "download_url, row_count, and file_size_bytes."
    ),
)
async def get_export_status(
    request: Request,
    job_id: str,
    token: TokenPayload = Depends(RequirePermission("exports:create")),
) -> JSONResponse:
    """
    Return the current status of an export job.

    Reads from:
    1. sys_jobs table (status, timestamps, errors)
    2. Metadata sidecar file (row_count, file_size, download_url)

    Security: Verifies the requesting tenant owns this export.
    """
    tenant_ctx: TenantContext = _extract_tenant(request)
    parsed_job_id = _parse_export_job_id(job_id)
    if parsed_job_id is None:
        return _invalid_export_id_response()

    # --- Look up job in database ---
    try:
        from database.session import AsyncSessionLocal
        from models.job import Job
        from sqlalchemy import select

        async with AsyncSessionLocal() as session:
            session.info["tenant_schema"] = "public"
            result = await session.execute(
                select(Job).where(Job.id == parsed_job_id)
            )
            job = result.scalar_one_or_none()

        if job is None:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=make_error("EXPORT_NOT_FOUND", f"Export job '{job_id}' not found"),
            )

        # --- Security: Verify tenant ownership ---
        #[Constraint Check] Rule #1: Only the owning tenant can see their export
        job_tenant = (job.payload or {}).get("tenant_id")
        if job_tenant != tenant_ctx.tenant_id:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=make_error("EXPORT_NOT_FOUND", f"Export job '{job_id}' not found"),
            )

        # --- Build response ---
        data = ExportStatusData(
            job_id=str(job.id),
            status=job.status,
            format=(job.payload or {}).get("format", "csv"),
            created_at=job.created_at.isoformat() if job.created_at else None,
            started_at=job.started_at.isoformat() if job.started_at else None,
            completed_at=job.completed_at.isoformat() if job.completed_at else None,
            error=job.last_error,
        )

        # If completed, read metadata sidecar for file info
        if job.status == "completed":
            from jobs.export_jobs import read_metadata

            # The metadata file_id is derived from the job's output
            # We search for any .meta.json that matches this job's tenant
            meta = _find_job_metadata(job_id, job.payload)
            if meta:
                data.download_url = f"/api/v1/exports/{job_id}/download"
                data.row_count = meta.get("row_count")
                data.file_size_bytes = meta.get("file_size_bytes")

        return JSONResponse(content=make_success(data))

    except Exception as e:
        logger.error(
            f"Failed to get export status: {e}",
            extra={"job_id": job_id, "error": str(e)}
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=make_error(
                "EXPORT_STATUS_FAILED",
                "Unable to retrieve export status",
            ),
        )


# ============================================================================
# GET /exports/{job_id}/download - Download the exported file
# ============================================================================

@exports_router.get(
    "/{job_id}/download",
    summary="Download Export File",
    description="Download the generated CSV/XLSX file for a completed export.",
)
async def download_export(
    request: Request,
    job_id: str,
    token: TokenPayload = Depends(RequirePermission("exports:create")),
) -> Any:
    """
    Serve the exported file for download.

    Security:
    - Verifies tenant ownership (same as status endpoint)
    - Only serves completed exports
    - File path is derived from metadata, never from user input
    """
    tenant_ctx: TenantContext = _extract_tenant(request)
    parsed_job_id = _parse_export_job_id(job_id)
    if parsed_job_id is None:
        return _invalid_export_id_response()

    try:
        from database.session import AsyncSessionLocal
        from models.job import Job
        from sqlalchemy import select

        async with AsyncSessionLocal() as session:
            session.info["tenant_schema"] = "public"
            result = await session.execute(
                select(Job).where(Job.id == parsed_job_id)
            )
            job = result.scalar_one_or_none()

        if job is None:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=make_error("EXPORT_NOT_FOUND", f"Export job '{job_id}' not found"),
            )

        # Security: Verify tenant ownership
        job_tenant = (job.payload or {}).get("tenant_id")
        if job_tenant != tenant_ctx.tenant_id:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=make_error("EXPORT_NOT_FOUND", f"Export job '{job_id}' not found"),
            )

        if job.status != "completed":
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content=make_error(
                    "EXPORT_NOT_READY",
                    f"Export job is '{job.status}', not yet completed"
                ),
            )

        # Find the file via metadata
        meta = _find_job_metadata(job_id, job.payload)
        if not meta or not meta.get("file_path"):
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=make_error("EXPORT_FILE_MISSING", "Export file not found on disk"),
            )

        file_path = Path(meta["file_path"])
        if not file_path.exists():
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=make_error("EXPORT_FILE_MISSING", "Export file not found on disk"),
            )

        # Determine content type
        fmt = meta.get("format", "csv")
        if fmt == "xlsx":
            media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        else:
            media_type = "text/csv"

        return FileResponse(
            path=str(file_path),
            media_type=media_type,
            filename=meta.get("file_name", f"export.{fmt}"),
        )

    except Exception as e:
        logger.error(
            f"Failed to download export: {e}",
            extra={"job_id": job_id, "error": str(e)}
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=make_error(
                "EXPORT_DOWNLOAD_FAILED",
                "Unable to download export",
            ),
        )


# ============================================================================
# Helpers
# ============================================================================

def _find_job_metadata(job_id: str, payload: Optional[dict]) -> Optional[dict]:
    """
    Find the metadata sidecar for a completed export job.

    The worker writes a {file_id}.meta.json file. We scan the export
    directory for metadata files that match this job's tenant_id.
    For efficiency, we also check if the job payload contains a hint.
    """
    from jobs.export_jobs import EXPORT_DIR, read_metadata
    import json

    if not EXPORT_DIR.exists():
        return None

    # Scan metadata files for one matching this job's tenant
    tenant_id = (payload or {}).get("tenant_id")
    for meta_file in EXPORT_DIR.glob("*.meta.json"):
        try:
            with open(meta_file, "r") as f:
                meta = json.load(f)
            if meta.get("tenant_id") == tenant_id:
                # Verify the file still exists
                if Path(meta.get("file_path", "")).exists():
                    return meta
        except (json.JSONDecodeError, OSError):
            continue

    return None
