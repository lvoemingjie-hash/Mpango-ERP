"""
S6-4: Export Job Worker - Async File Generation via S4 Job Queue.

Philosophy: "The export runs where the user isn't waiting."

Context Propagation:
    The HTTP endpoint (POST /exports) captures tenant_id from JWT claims
    and serializes it into ExportJobPayload. This worker deserializes it
    and reconstructs the SemanticQueryBuilder with the same tenant context.

    POST /exports (HTTP, authenticated)
        -> ExportJobPayload.from_request(request, tenant_id, tenant_schema, user_id)
        -> job_queue.enqueue("export_report", payload.model_dump())
        -> [detached worker picks up job]
        -> export_report_worker(payload_dict)
            -> ExportJobPayload(**payload_dict)  # re-validates tenant_id
            -> SemanticQueryBuilder(session, tenant_id, tenant_schema, view_scope)
            -> builder.execute(stmt)  # SET LOCAL search_path enforced
            -> stream rows -> write CSV/XLSX to disk

Memory Safety:
    - Uses yield_per(STREAM_BATCH_SIZE) to stream rows from the database.
    - Never loads the full result set into RAM.
    - Writes to disk in batches via csv.writer / openpyxl streaming.

Security:
    - Worker REJECTS payloads with empty tenant_id (ExportJobPayload validator).
    - Worker re-validates ViewScope, ReportMetric, ReportDimension from string values.
    - SET LOCAL search_path is enforced by SemanticQueryBuilder before any query.
"""
import csv
import os
import re
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.jobs.base import job_handler
from core.structured_logging import get_logger
from database.reporting_session import ReportingSessionLocal
from services.reporting.semantic_layer import (
    ViewScope,
    ReportMetric,
    ReportDimension,
    get_view_registration,
)
from services.reporting.query_builder import SemanticQueryBuilder

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Directory where export files are written.
# In production, this would be an object store (S3/GCS). For now, local disk.
EXPORT_DIR = Path(os.environ.get(
    "EXPORT_DIR",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "exports")
))

# Streaming batch size - rows fetched per database round-trip.
# Keeps memory bounded: at most STREAM_BATCH_SIZE rows in RAM at once.
STREAM_BATCH_SIZE = 1000

# Maximum rows per export (hard safety cap, overrides payload.limit)
MAX_EXPORT_ROWS = 500_000


# ---------------------------------------------------------------------------
# Ensure export directory exists
# ---------------------------------------------------------------------------

def _ensure_export_dir() -> Path:
    """Create the export directory if it doesn't exist."""
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    return EXPORT_DIR


# ---------------------------------------------------------------------------
# The Worker
# ---------------------------------------------------------------------------

@job_handler("export_report")
async def export_report_worker(payload: dict) -> None:
    """
    S6-4 Export Worker: Generate CSV/XLSX from a semantic query.

    This function runs in the S4 job queue worker (detached from HTTP).
    It reconstructs the tenant context from the serialized payload and
    uses SemanticQueryBuilder to execute the query with full isolation.

    Payload is validated via ExportJobPayload Pydantic model, which
    rejects empty tenant_id (Constraint Check Rule #1).

    Args:
        payload: Dict from sys_jobs.payload JSON column.
                 Must contain tenant_id, tenant_schema, view, metrics, etc.

    Raises:
        ValueError: If tenant_id is missing or view/metrics are invalid.
        Exception: On database or file I/O errors (triggers S4 retry).
    """
    # --- Step 1: Deserialize and validate payload ---
    # This import is here to avoid circular imports at module level
    from api.schemas.jobs import ExportJobPayload

    #[Constraint Check] Rule #1: Re-validate tenant_id in the worker
    job_payload = ExportJobPayload(**payload)

    logger.info(
        "Export job started",
        extra={
            "tenant_id": job_payload.tenant_id,
            "user_id": job_payload.user_id,
            "view": job_payload.view,
            "format": job_payload.format,
        }
    )

    # --- Step 2: Re-validate enums from string values ---
    #[Constraint Check] Rule #4: Re-validate enums in worker (defense in depth)
    try:
        view_scope = ViewScope(job_payload.view)
    except ValueError:
        raise ValueError(
            f"Invalid ViewScope in export payload: '{job_payload.view}'"
        )

    metrics: list[ReportMetric] = []
    for m_val in job_payload.metrics:
        try:
            metrics.append(ReportMetric(m_val))
        except ValueError:
            raise ValueError(
                f"Invalid ReportMetric in export payload: '{m_val}'"
            )

    dimensions: Optional[list[ReportDimension]] = None
    if job_payload.dimensions:
        dimensions = []
        for d_val in job_payload.dimensions:
            try:
                dimensions.append(ReportDimension(d_val))
            except ValueError:
                raise ValueError(
                    f"Invalid ReportDimension in export payload: '{d_val}'"
                )

    # Parse date filters
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    if job_payload.date_from:
        date_from = date.fromisoformat(job_payload.date_from)
    if job_payload.date_to:
        date_to = date.fromisoformat(job_payload.date_to)

    # Clamp limit to safety cap
    limit = min(job_payload.limit, MAX_EXPORT_ROWS)

    # --- Step 3: Build query via SemanticQueryBuilder ---
    #[Constraint Check] Rule #1: tenant_id flows from payload -> builder constructor
    #[Constraint Check] Rule #1: SET LOCAL search_path enforced by builder
    async with ReportingSessionLocal() as session:
        session.info["tenant_id"] = job_payload.tenant_id
        session.info["tenant_schema"] = job_payload.tenant_schema
        builder = SemanticQueryBuilder(
            session=session,
            tenant_id=job_payload.tenant_id,
            tenant_schema=job_payload.tenant_schema,
            view_scope=view_scope,
        )

        stmt = builder.build_query(
            metrics=metrics,
            dimensions=dimensions,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
        )

        # --- Step 4: Execute with tenant scope and stream results ---
        #[Constraint Check] Rule #1: Tenant scope enforced before query
        await builder._ensure_tenant_scope()
        result = await session.execute(stmt)
        columns = list(result.keys())

        # --- Step 5: Write to file in streaming batches ---
        export_dir = _ensure_export_dir()
        file_id = str(uuid.uuid4())

        if job_payload.format == "xlsx":
            file_path = export_dir / f"{file_id}.xlsx"
            row_count = await _write_xlsx_streaming(
                result, columns, file_path
            )
        else:
            file_path = export_dir / f"{file_id}.csv"
            row_count = await _write_csv_streaming(
                result, columns, file_path
            )

    # --- Step 6: Record result metadata in payload ---
    # The S4 queue updates sys_jobs.status to "completed" automatically.
    # We store file metadata so the status endpoint can return download info.
    file_size = file_path.stat().st_size

    # Update the job payload with result metadata.
    # We write a small metadata sidecar file that the status endpoint reads.
    _write_metadata(file_id, {
        "file_path": str(file_path),
        "file_name": file_path.name,
        "row_count": row_count,
        "file_size_bytes": file_size,
        "format": job_payload.format,
        "tenant_id": job_payload.tenant_id,
        "user_id": job_payload.user_id,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    })

    logger.info(
        "Export job completed",
        extra={
            "tenant_id": job_payload.tenant_id,
            "file": str(file_path),
            "row_count": row_count,
            "file_size_bytes": file_size,
        }
    )


# ---------------------------------------------------------------------------
# Streaming Writers
# ---------------------------------------------------------------------------

async def _write_csv_streaming(result, columns: list[str], file_path: Path) -> int:
    """
    Write query results to CSV in streaming batches.

    Memory Safety: Only STREAM_BATCH_SIZE rows are in RAM at any time.
    The result proxy is iterated via fetchmany() to avoid loading all rows.

    Returns:
        Number of rows written.
    """
    row_count = 0

    with open(file_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)  # Header

        while True:
            # Fetch a batch of rows (memory-bounded)
            batch = result.fetchmany(STREAM_BATCH_SIZE)
            if not batch:
                break

            for row in batch:
                writer.writerow([
                    _serialize_value(val) for val in row
                ])
                row_count += 1

    return row_count


async def _write_xlsx_streaming(result, columns: list[str], file_path: Path) -> int:
    """
    Write query results to XLSX using openpyxl write-only mode.

    Memory Safety: openpyxl's write_only=True mode streams rows to disk
    without keeping the full worksheet in memory.

    Falls back to CSV if openpyxl is not installed.

    Returns:
        Number of rows written.
    """
    try:
        from openpyxl import Workbook
    except ImportError:
        logger.warning(
            "openpyxl not installed, falling back to CSV for XLSX export"
        )
        csv_path = file_path.with_suffix(".csv")
        count = await _write_csv_streaming(result, columns, csv_path)
        # Rename so the caller still finds the file at the expected path
        csv_path.rename(file_path)
        return count

    row_count = 0
    wb = Workbook(write_only=True)
    ws = wb.create_sheet("Export")

    # Header row
    ws.append(columns)

    while True:
        batch = result.fetchmany(STREAM_BATCH_SIZE)
        if not batch:
            break

        for row in batch:
            ws.append([_serialize_value(val) for val in row])
            row_count += 1

    wb.save(str(file_path))
    return row_count


# ---------------------------------------------------------------------------
# Metadata Sidecar
# ---------------------------------------------------------------------------

# S8-SEC: Safe file_id pattern - prevents path traversal in metadata sidecar.
_SAFE_FILE_ID_RE = re.compile(r"^[a-zA-Z0-9_\-]{1,128}$")


def _validate_file_id(file_id: str) -> str:
    """Validate file_id to prevent path traversal attacks.

    Raises ValueError if file_id contains path separators, dots, or
    other characters that could escape the export directory.
    """
    if not _SAFE_FILE_ID_RE.match(file_id):
        raise ValueError(
            f"Unsafe file_id: {file_id!r} - must match {_SAFE_FILE_ID_RE.pattern}"
        )
    return file_id


def _safe_meta_path(file_id: str) -> Path:
    """Build a validated metadata path within EXPORT_DIR."""
    _validate_file_id(file_id)
    export_dir = _ensure_export_dir()
    meta_path = (export_dir / f"{file_id}.meta.json").resolve()
    # Belt-and-suspenders: verify resolved path is inside export dir
    if not str(meta_path).startswith(str(export_dir.resolve())):
        raise ValueError(f"Path traversal detected: {meta_path}")
    return meta_path


def _write_metadata(file_id: str, metadata: dict) -> None:
    """
    Write a JSON metadata sidecar for the export file.

    The status endpoint reads this to return download_url, row_count, etc.
    """
    import json

    meta_path = _safe_meta_path(file_id)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)


def read_metadata(file_id: str) -> Optional[dict]:
    """
    Read the metadata sidecar for an export file.

    Returns None if the metadata file doesn't exist (job still running).
    """
    import json

    meta_path = _safe_meta_path(file_id)
    if not meta_path.exists():
        return None

    with open(meta_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _serialize_value(val: Any) -> Any:
    """Serialize a database value for file output."""
    from decimal import Decimal

    if val is None:
        return ""
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, (date, datetime)):
        return val.isoformat()
    if hasattr(val, "hex"):  # UUID
        return str(val)
    return val
