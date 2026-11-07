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

File Safety:
    - Writes batches from the result proxy; this does not promise server-side streaming.
    - Publishes only closed files and then an identity/digest sidecar.
    - File work is serial, tracked and cooperatively stopped; no cross-host fencing.

Security:
    - Worker REJECTS payloads with empty tenant_id (ExportJobPayload validator).
    - Worker re-validates ViewScope, ReportMetric, ReportDimension from string values.
    - SET LOCAL search_path is enforced by SemanticQueryBuilder before any query.
"""
import csv
import asyncio
import codecs
import contextvars
import hashlib
import math
import os
import re
import tempfile
import threading
import uuid
import zipfile
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional
from xml.etree import ElementTree

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

_FORMULA_PREFIX = re.compile(r"^[\s\ufeff\x00-\x1f]*[=+\-@]")
_FORMULA_SIGNS = str.maketrans("＝＋－＠", "=+-@")
_INVALID_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")


class ExportFileError(ValueError):
    """Fixed public error category, without source values or runtime credentials."""


_IO_OWNER = contextvars.ContextVar("export_io_owner", default=None)
_FILE_WORK = set()


@contextmanager
def export_io_scope(owner):
    token = _IO_OWNER.set(owner)
    try:
        yield
    finally:
        _IO_OWNER.reset(token)


def export_io_pending(owners):
    for work in list(_FILE_WORK):
        if work.closed():
            _FILE_WORK.discard(work)
    return [work for work in _FILE_WORK if work.owner in owners]


def request_export_io_stop(owners):
    for work in export_io_pending(owners):
        work.cancel.set()


async def wait_export_io(owners, timeout):
    deadline = asyncio.get_running_loop().time() + max(0, timeout)
    while export_io_pending(owners):
        if asyncio.get_running_loop().time() >= deadline:
            return False
        await asyncio.sleep(0.005)
    return True


class _ExportFileWork:
    """One serial file worker, not an executor for the database handler.

    Every future, cleanup task and actual thread remains owned until closed.
    Cancelling an await never means that a thread has stopped.
    """
    def __init__(self):
        self.owner = _IO_OWNER.get()
        self.cancel = threading.Event()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mpango-export-file")
        self.futures = set()
        self.close_task = None
        self.context = self.handle = self.book = self.sheet = None
        self.temporary = None
        self.fmt = None
        _FILE_WORK.add(self)

    def _check(self):
        if self.cancel.is_set():
            raise ExportFileError("EXPORT_WRITE_CANCELLED")

    async def call(self, function, *args):
        future = asyncio.get_running_loop().run_in_executor(self.executor, function, *args)
        self.futures.add(future)
        def finished(done):
            self.futures.discard(done)
            if not done.cancelled():
                done.exception()
        future.add_done_callback(finished)
        try:
            return await asyncio.shield(future)
        except BaseException:
            self.cancel.set()
            raise

    def begin(self, file_path, fmt, columns):
        self._check()
        self.context = _atomic_export_path(file_path)
        self.temporary = self.context.__enter__()
        self.fmt = fmt
        if fmt == "csv":
            self.handle = self.temporary.open("w", newline="", encoding="utf-8-sig")
            self.csv = csv.writer(self.handle)
            self.csv.writerow([_csv_value(str(column)) for column in columns])
        else:
            self.book = require_xlsx_dependency()(write_only=True)
            self.sheet = self.book.create_sheet("Export")
            self.append([list(str(column) for column in columns)])

    def append(self, batch):
        for row in batch:
            self._check()
            if self.fmt == "csv":
                self.csv.writerow([_csv_value(value) for value in row])
            else:
                from openpyxl.cell import WriteOnlyCell
                cells = []
                for value in row:
                    value = _serialize_value(value)
                    if isinstance(value, str) and (_INVALID_XML.search(value) or len(value) > 32767):
                        raise ExportFileError("EXPORT_XLSX_TEXT_INVALID")
                    cell = WriteOnlyCell(self.sheet, value=value)
                    if isinstance(value, str):
                        cell.data_type = "s"
                    cells.append(cell)
                self.sheet.append(cells)

    def finish(self):
        self._check()
        if self.handle is not None:
            self.handle.close(); self.handle = None
        if self.book is not None:
            self.book.save(str(self.temporary))
        validate_export_file(self.temporary, self.fmt)
        self._check()
        self.context.__exit__(None, None, None)
        self.context = None

    def _cleanup(self):
        try:
            if self.handle is not None:
                self.handle.close(); self.handle = None
            if self.sheet is not None and self.sheet._writer is not None:
                if not self.sheet.closed:
                    self.sheet.close()
                if os.path.exists(self.sheet._writer.out):
                    self.sheet._writer.cleanup()
            if self.book is not None:
                self.book.close()
        finally:
            if self.context is not None:
                error = ExportFileError("EXPORT_WRITE_CANCELLED")
                self.context.__exit__(ExportFileError, error, None)
                self.context = None

    async def _close(self):
        try:
            await self.call(self._cleanup)
        finally:
            self.executor.shutdown(wait=False)
        while any(thread.is_alive() for thread in self.executor._threads):
            await asyncio.sleep(0.005)
        _FILE_WORK.discard(self)

    async def close(self):
        if self.close_task is None:
            self.close_task = asyncio.create_task(self._close())
        await asyncio.shield(self.close_task)

    def closed(self):
        return (self.close_task is not None and self.close_task.done() and not self.close_task.cancelled()
                and self.close_task.exception() is None and not self.futures
                and not any(thread.is_alive() for thread in self.executor._threads))


async def run_export_file_operation(function, *args):
    work = _ExportFileWork()
    try:
        return await work.call(function, work.cancel, *args)
    finally:
        await work.close()


def require_xlsx_dependency():
    """Both admission and execution must refuse, never substitute another format."""
    try:
        from openpyxl import Workbook
    except ImportError:
        raise ExportFileError("EXPORT_XLSX_DEPENDENCY_UNAVAILABLE") from None
    return Workbook


def _csv_value(value: Any) -> Any:
    # Detect on a copy, preserving original glyphs and leading data characters.
    if isinstance(value, str):
        if (_FORMULA_PREFIX.match(value.translate(_FORMULA_SIGNS))
                or value.startswith(("\t", "\r", "\n"))):
            return "'" + value
        return value
    return _serialize_value(value)


@contextmanager
def _atomic_export_path(file_path: Path):
    """The only cleanup target is the unique part allocated by this invocation."""
    fd, name = tempfile.mkstemp(prefix=file_path.name + ".part.", dir=file_path.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        yield temporary
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, file_path)
    finally:
        temporary.unlink(missing_ok=True)


def _file_digest(file_path: Path) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_export_file(file_path: Path, fmt: str) -> None:
    """Check actual bytes, not just an extension; never execute spreadsheet content."""
    try:
        if fmt == "csv":
            with file_path.open("rb") as handle:
                if handle.read(3) != codecs.BOM_UTF8:
                    raise ExportFileError("EXPORT_CSV_ENCODING_INVALID")
                decoder = codecs.getincrementaldecoder("utf-8")()
                for chunk in iter(lambda: handle.read(65536), b""):
                    decoder.decode(chunk)
                decoder.decode(b"", final=True)
            return
        if fmt != "xlsx":
            raise ExportFileError("EXPORT_FORMAT_INVALID")
        with zipfile.ZipFile(file_path) as archive:
            names = archive.namelist()
            required = {"[Content_Types].xml", "xl/workbook.xml", "xl/worksheets/sheet1.xml"}
            if not required.issubset(names) or len(names) != len(set(names)):
                raise ExportFileError("EXPORT_XLSX_FORMAT_INVALID")
            if len(names) > 1024 or sum(i.file_size for i in archive.infolist()) > 128 * 1024 * 1024:
                raise ExportFileError("EXPORT_XLSX_FORMAT_INVALID")
            main_content_type = False
            expected_roots = {
                "[Content_Types].xml": "{http://schemas.openxmlformats.org/package/2006/content-types}Types",
                "xl/workbook.xml": "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}workbook",
                "xl/worksheets/sheet1.xml": "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}worksheet",
            }
            for item in archive.infolist():
                name = item.filename
                if (item.flag_bits & 1 or item.file_size > 64 * 1024 * 1024
                        or name.startswith("/") or ".." in Path(name).parts
                        or "vbaproject" in name.lower() or "externallinks/" in name.lower()):
                    raise ExportFileError("EXPORT_XLSX_FORMAT_INVALID")
                if name.endswith((".xml", ".rels")):
                    with archive.open(item) as handle:
                        first = True
                        for event, element in ElementTree.iterparse(handle, events=("start", "end")):
                            if first:
                                first = False
                                if name in expected_roots and element.tag != expected_roots[name]:
                                    raise ExportFileError("EXPORT_XLSX_FORMAT_INVALID")
                            if event != "end":
                                continue
                            tag = element.tag.rsplit("}", 1)[-1]
                            if tag == "f" or element.attrib.get("TargetMode", "").lower() == "external":
                                raise ExportFileError("EXPORT_XLSX_UNSAFE_CONTENT")
                            if "macroenabled" in element.attrib.get("ContentType", "").lower():
                                raise ExportFileError("EXPORT_XLSX_UNSAFE_CONTENT")
                            if (name == "[Content_Types].xml"
                                    and element.attrib.get("PartName") == "/xl/workbook.xml"
                                    and element.attrib.get("ContentType") ==
                                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"):
                                main_content_type = True
                            element.clear()
            if not main_content_type:
                raise ExportFileError("EXPORT_XLSX_FORMAT_INVALID")
    except ExportFileError:
        raise
    except (OSError, UnicodeError, zipfile.BadZipFile, ElementTree.ParseError, RuntimeError):
        raise ExportFileError("EXPORT_FILE_FORMAT_INVALID") from None


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
    if not job_payload.file_id:
        raise ValueError("Export job has no persisted file identity; submit a new export")
    file_id = _validate_file_id(job_payload.file_id)
    if job_payload.format not in ("csv", "xlsx"):
        raise ExportFileError("EXPORT_FORMAT_INVALID")
    if job_payload.format == "xlsx":
        require_xlsx_dependency()

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
    def publish_metadata(cancel):
        file_size = file_path.stat().st_size
        validate_export_file(file_path, job_payload.format)
        content_digest = _file_digest(file_path)

        # Update the job payload with result metadata.
        # We write a small metadata sidecar file that the status endpoint reads.
        if cancel.is_set():
            raise ExportFileError("EXPORT_WRITE_CANCELLED")
        _write_metadata(file_id, {
            "metadata_version": 1,
            "file_id": file_id,
            "file_path": str(file_path),
            "file_name": file_path.name,
            "row_count": row_count,
            "file_size_bytes": file_size,
            "content_sha256": content_digest,
            "format": job_payload.format,
            "tenant_id": job_payload.tenant_id,
            "user_id": job_payload.user_id,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        })
        return file_path.stat().st_size

    file_size = await run_export_file_operation(publish_metadata)

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

async def _write_rows(result, columns, file_path, fmt):
    if fmt == "xlsx":
        require_xlsx_dependency()
    work = _ExportFileWork()
    count = 0
    try:
        await work.call(work.begin, file_path, fmt, columns)
        while True:
            # The result proxy and async database session stay on their owner loop.
            batch = result.fetchmany(STREAM_BATCH_SIZE)
            if not batch:
                break
            await work.call(work.append, batch)
            count += len(batch)
        await work.call(work.finish)
        return count
    finally:
        await work.close()


async def _write_csv_streaming(result, columns: list[str], file_path: Path) -> int:
    return await _write_rows(result, columns, file_path, "csv")


async def _write_xlsx_streaming(result, columns: list[str], file_path: Path) -> int:
    return await _write_rows(result, columns, file_path, "xlsx")


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
    temporary = meta_path.with_name(meta_path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, meta_path)
    finally:
        if temporary.exists():
            temporary.unlink()


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
        if not val.is_finite():
            raise ExportFileError("EXPORT_NONFINITE_VALUE")
        return format(val, "f")
    if isinstance(val, float) and not math.isfinite(val):
        raise ExportFileError("EXPORT_NONFINITE_VALUE")
    if isinstance(val, (date, datetime)):
        return val.isoformat()
    if isinstance(val, uuid.UUID):
        return str(val)
    return val
