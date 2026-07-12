"""
S6-4: Async Export Engine - Test Suite.

Tests cover:
1. ExportJobPayload validation (tenant_id propagation, empty rejection)
2. ExportRequest Pydantic validation (enum whitelist enforcement)
3. Export worker logic (streaming, file generation, metadata)
4. Context propagation chain (HTTP -> payload -> worker)
5. Security: tenant ownership verification
"""
import json
import os
import uuid
import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import HTTPException
from starlette.requests import Request as StarletteRequest

from api.context.auth import AuthContext, attach_auth_context
from api.context.tenant import TenantContext, attach_tenant_context
from api.middleware.rbac import RequirePermission
from api.schemas.jobs import (
    ExportRequest,
    ExportJobPayload,
    ExportFormat,
    ExportStatusData,
)
from core.security import TokenPayload
from services.reporting.semantic_layer import (
    ViewScope,
    ReportMetric,
    ReportDimension,
)


TEST_TENANT_ID = "550e8400-e29b-41d4-a716-446655440000"
OTHER_TENANT_ID = "660e8400-e29b-41d4-a716-446655440000"
TEST_TENANT_SCHEMA = "t_550e8400e29b41d4a716446655440000"


def _response_json(response):
    return json.loads(response.body.decode("utf-8"))


def _request_with_context() -> StarletteRequest:
    request = StarletteRequest({"type": "http", "headers": []})
    permission = SimpleNamespace(code="exports:create")
    role = SimpleNamespace(permissions=[permission])
    user = SimpleNamespace(id="user-123", roles=[role])
    token = TokenPayload(
        user_id="user-123",
        tenant_id=TEST_TENANT_ID,
        tenant_schema=TEST_TENANT_SCHEMA,
        roles=["admin"],
    )
    attach_auth_context(request, AuthContext(token=token, raw_token="redacted-test-token"))
    attach_tenant_context(
        request,
        TenantContext(
            tenant_id=TEST_TENANT_ID,
            tenant_schema=TEST_TENANT_SCHEMA,
            session=SimpleNamespace(),
            user=user,
        ),
    )
    return request


async def _exports_create_token(request: StarletteRequest) -> TokenPayload:
    return await RequirePermission("exports:create")(request)


class _FakeResult:
    def __init__(self, job):
        self.job = job

    def scalar_one_or_none(self):
        return self.job


class _FakeSession:
    def __init__(self, job):
        self.job = job
        self.info = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement):
        return _FakeResult(self.job)


def _patch_job_lookup(monkeypatch, job) -> None:
    monkeypatch.setattr(
        "database.session.AsyncSessionLocal",
        lambda: _FakeSession(job),
    )


def _job(*, tenant_id: str = TEST_TENANT_ID, status: str = "pending"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        status=status,
        payload={"tenant_id": tenant_id, "format": "csv"},
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        started_at=None,
        completed_at=None,
        last_error=None,
    )


# ============================================================================
# 1. ExportJobPayload Validation Tests
# ============================================================================

class TestExportJobPayload:
    """Test the serializable job payload with tenant context propagation."""

    def test_valid_payload_creates_successfully(self):
        """A well-formed payload with tenant_id should be accepted."""
        payload = ExportJobPayload(
            tenant_id="550e8400-e29b-41d4-a716-446655440000",
            tenant_schema="t_550e8400e29b41d4a716446655440000",
            user_id="user-123",
            view="sales_daily",
            metrics=["revenue", "transaction_count"],
            dimensions=["date"],
            format="csv",
            limit=1000,
        )
        assert payload.tenant_id == "550e8400-e29b-41d4-a716-446655440000"
        assert payload.tenant_schema == "t_550e8400e29b41d4a716446655440000"
        assert payload.view == "sales_daily"
        assert payload.metrics == ["revenue", "transaction_count"]

    def test_empty_tenant_id_rejected(self):
        """
        #[Constraint Check] Rule #1: Empty tenant_id MUST be rejected.
        If the worker runs without tenant_id, it queries the wrong schema.
        """
        with pytest.raises(ValueError, match="MUST NOT be empty"):
            ExportJobPayload(
                tenant_id="",
                tenant_schema="t_abc",
                user_id="user-123",
                view="sales_daily",
                metrics=["revenue"],
            )

    def test_whitespace_tenant_id_rejected(self):
        """Whitespace-only tenant_id should also be rejected."""
        with pytest.raises(ValueError, match="MUST NOT be empty"):
            ExportJobPayload(
                tenant_id="   ",
                tenant_schema="t_abc",
                user_id="user-123",
                view="sales_daily",
                metrics=["revenue"],
            )

    def test_invalid_tenant_schema_prefix_rejected(self):
        """tenant_schema must start with 't_'."""
        with pytest.raises(ValueError, match="must start with 't_'"):
            ExportJobPayload(
                tenant_id="valid-uuid",
                tenant_schema="public",
                user_id="user-123",
                view="sales_daily",
                metrics=["revenue"],
            )

    def test_from_request_factory(self):
        """ExportJobPayload.from_request() correctly serializes context."""
        request = ExportRequest(
            view=ViewScope.SALES_DAILY,
            metrics=[ReportMetric.REVENUE, ReportMetric.TRANSACTION_COUNT],
            dimensions=[ReportDimension.DATE],
            date_from=date(2026, 1, 1),
            date_to=date(2026, 1, 31),
            format=ExportFormat.CSV,
            limit=5000,
        )
        payload = ExportJobPayload.from_request(
            request=request,
            tenant_id="tid-123",
            tenant_schema="t_tid123",
            user_id="uid-456",
        )
        assert payload.tenant_id == "tid-123"
        assert payload.tenant_schema == "t_tid123"
        assert payload.user_id == "uid-456"
        assert payload.view == "sales_daily"
        assert payload.metrics == ["revenue", "transaction_count"]
        assert payload.dimensions == ["date"]
        assert payload.date_from == "2026-01-01"
        assert payload.date_to == "2026-01-31"
        assert payload.format == "csv"
        assert payload.limit == 5000

    def test_payload_is_json_serializable(self):
        """Payload must survive JSON round-trip (stored in sys_jobs.payload)."""
        payload = ExportJobPayload(
            tenant_id="tid-abc",
            tenant_schema="t_tidabc",
            user_id="uid-def",
            view="sales_daily",
            metrics=["revenue"],
            format="xlsx",
        )
        dumped = payload.model_dump()
        assert isinstance(dumped, dict)
        # Simulate JSON round-trip (what the Job Queue does)
        json_str = json.dumps(dumped)
        restored = ExportJobPayload(**json.loads(json_str))
        assert restored.tenant_id == payload.tenant_id
        assert restored.view == payload.view
        assert restored.format == "xlsx"


# ============================================================================
# 2. ExportRequest Pydantic Validation Tests
# ============================================================================

class TestExportRequest:
    """Test the API-facing request schema with enum whitelist enforcement."""

    def test_valid_request_parses(self):
        """A well-formed request with valid enums should parse."""
        req = ExportRequest(
            view=ViewScope.SALES_DAILY,
            metrics=[ReportMetric.REVENUE],
            format=ExportFormat.CSV,
        )
        assert req.view == ViewScope.SALES_DAILY
        assert req.metrics == [ReportMetric.REVENUE]
        assert req.format == ExportFormat.CSV
        assert req.limit == 50000  # default

    def test_invalid_view_rejected(self):
        """Invalid view enum value should be rejected by Pydantic."""
        with pytest.raises(Exception):
            ExportRequest(
                view="users_table",
                metrics=["revenue"],
            )

    def test_invalid_metric_rejected(self):
        """Invalid metric enum value should be rejected by Pydantic."""
        with pytest.raises(Exception):
            ExportRequest(
                view="sales_daily",
                metrics=["daily_revenue"],  # raw column name, not enum
            )

    def test_invalid_format_rejected(self):
        """Invalid export format should be rejected."""
        with pytest.raises(Exception):
            ExportRequest(
                view="sales_daily",
                metrics=["revenue"],
                format="pdf",  # not supported
            )

    def test_empty_metrics_rejected(self):
        """At least one metric is required."""
        with pytest.raises(Exception):
            ExportRequest(
                view="sales_daily",
                metrics=[],
            )

    def test_limit_bounds(self):
        """Limit must be between 1 and 500000."""
        # Too high
        with pytest.raises(Exception):
            ExportRequest(
                view="sales_daily",
                metrics=["revenue"],
                limit=1_000_000,
            )
        # Zero
        with pytest.raises(Exception):
            ExportRequest(
                view="sales_daily",
                metrics=["revenue"],
                limit=0,
            )

    def test_xlsx_format_accepted(self):
        """XLSX format should be accepted."""
        req = ExportRequest(
            view=ViewScope.CASH_FLOW_DAILY,
            metrics=[ReportMetric.NET_CASH_CHANGE],
            format=ExportFormat.XLSX,
        )
        assert req.format == ExportFormat.XLSX


# ============================================================================
# 3. Export Worker Tests
# ============================================================================

class TestExportWorker:
    """Test the export worker logic with mocked database."""

    @pytest.mark.asyncio
    async def test_worker_rejects_empty_tenant_id(self):
        """Worker must reject payloads with empty tenant_id."""
        from jobs.export_jobs import export_report_worker

        payload = {
            "tenant_id": "",
            "tenant_schema": "t_abc",
            "user_id": "uid",
            "view": "sales_daily",
            "metrics": ["revenue"],
            "format": "csv",
            "limit": 100,
        }
        with pytest.raises(ValueError, match="MUST NOT be empty"):
            await export_report_worker(payload)

    @pytest.mark.asyncio
    async def test_worker_rejects_invalid_view(self):
        """Worker must reject payloads with invalid ViewScope."""
        from jobs.export_jobs import export_report_worker

        payload = {
            "tenant_id": "tid-123",
            "tenant_schema": "t_tid123",
            "user_id": "uid",
            "view": "users_table",
            "metrics": ["revenue"],
            "format": "csv",
            "limit": 100,
        }
        with pytest.raises(ValueError, match="Invalid ViewScope"):
            await export_report_worker(payload)

    @pytest.mark.asyncio
    async def test_worker_rejects_invalid_metric(self):
        """Worker must reject payloads with invalid ReportMetric."""
        from jobs.export_jobs import export_report_worker

        payload = {
            "tenant_id": "tid-123",
            "tenant_schema": "t_tid123",
            "user_id": "uid",
            "view": "sales_daily",
            "metrics": ["daily_revenue"],  # raw column name
            "format": "csv",
            "limit": 100,
        }
        with pytest.raises(ValueError, match="Invalid ReportMetric"):
            await export_report_worker(payload)


# ============================================================================
# 4. CSV Streaming Writer Tests
# ============================================================================

class TestCsvStreaming:
    """Test the CSV streaming writer with mock data."""

    @pytest.mark.asyncio
    async def test_csv_writer_produces_valid_file(self, tmp_path):
        """CSV writer should produce a valid file with header and rows."""
        from jobs.export_jobs import _write_csv_streaming

        # Mock a result proxy with fetchmany
        mock_result = MagicMock()
        mock_result.fetchmany.side_effect = [
            [
                (date(2026, 1, 1), Decimal("1234.5678"), 5),
                (date(2026, 1, 2), Decimal("2345.6789"), 10),
            ],
            [],  # End of results
        ]

        columns = ["transaction_date", "daily_revenue", "transaction_count"]
        file_path = tmp_path / "test_export.csv"

        row_count = await _write_csv_streaming(mock_result, columns, file_path)

        assert row_count == 2
        assert file_path.exists()

        # Verify CSV content
        with open(file_path, "r") as f:
            lines = f.readlines()
        assert len(lines) == 3  # header + 2 data rows
        assert "transaction_date" in lines[0]
        assert "2026-01-01" in lines[1]

    @pytest.mark.asyncio
    async def test_csv_writer_handles_empty_result(self, tmp_path):
        """CSV writer should produce header-only file on empty result."""
        from jobs.export_jobs import _write_csv_streaming

        mock_result = MagicMock()
        mock_result.fetchmany.return_value = []

        columns = ["date", "value"]
        file_path = tmp_path / "empty_export.csv"

        row_count = await _write_csv_streaming(mock_result, columns, file_path)

        assert row_count == 0
        assert file_path.exists()
        with open(file_path, "r") as f:
            lines = f.readlines()
        assert len(lines) == 1  # header only

    @pytest.mark.asyncio
    async def test_csv_writer_streams_in_batches(self, tmp_path):
        """CSV writer should call fetchmany multiple times for large results."""
        from jobs.export_jobs import _write_csv_streaming, STREAM_BATCH_SIZE

        # Simulate 3 batches
        batch1 = [(i, f"val_{i}") for i in range(STREAM_BATCH_SIZE)]
        batch2 = [(i + STREAM_BATCH_SIZE, f"val_{i}") for i in range(STREAM_BATCH_SIZE)]
        batch3 = [(2 * STREAM_BATCH_SIZE + i, f"val_{i}") for i in range(50)]

        mock_result = MagicMock()
        mock_result.fetchmany.side_effect = [batch1, batch2, batch3, []]

        columns = ["id", "value"]
        file_path = tmp_path / "batched_export.csv"

        row_count = await _write_csv_streaming(mock_result, columns, file_path)

        assert row_count == 2 * STREAM_BATCH_SIZE + 50
        assert mock_result.fetchmany.call_count == 4  # 3 data + 1 empty


# ============================================================================
# 5. Metadata Sidecar Tests
# ============================================================================

class TestMetadata:
    """Test the metadata sidecar read/write."""

    def test_write_and_read_metadata(self, tmp_path):
        """Metadata should survive write -> read round-trip."""
        from jobs.export_jobs import _write_metadata, read_metadata, EXPORT_DIR

        # Temporarily override EXPORT_DIR
        import jobs.export_jobs as mod
        original_dir = mod.EXPORT_DIR
        mod.EXPORT_DIR = tmp_path

        try:
            file_id = "test-file-id"
            meta = {
                "file_path": str(tmp_path / "test.csv"),
                "row_count": 42,
                "file_size_bytes": 1024,
                "tenant_id": "tid-123",
            }
            _write_metadata(file_id, meta)

            restored = read_metadata(file_id)
            assert restored is not None
            assert restored["row_count"] == 42
            assert restored["tenant_id"] == "tid-123"
        finally:
            mod.EXPORT_DIR = original_dir

    def test_read_nonexistent_metadata_returns_none(self, tmp_path):
        """Reading metadata for a non-existent file should return None."""
        from jobs.export_jobs import read_metadata

        import jobs.export_jobs as mod
        original_dir = mod.EXPORT_DIR
        mod.EXPORT_DIR = tmp_path

        try:
            result = read_metadata("nonexistent-id")
            assert result is None
        finally:
            mod.EXPORT_DIR = original_dir


# ============================================================================
# 6. Context Propagation Chain Test
# ============================================================================

class TestContextPropagation:
    """
    Verify the full context propagation chain:
    HTTP request -> ExportRequest -> ExportJobPayload -> Worker validation
    """

    def test_full_chain_preserves_tenant_id(self):
        """
        Simulate: Frontend sends ExportRequest -> API builds payload -> Worker validates.
        tenant_id must survive the entire chain.
        """
        # Step 1: Frontend sends request (Pydantic validates enums)
        request = ExportRequest(
            view=ViewScope.SALES_DAILY,
            metrics=[ReportMetric.REVENUE],
            dimensions=[ReportDimension.DATE, ReportDimension.CURRENCY],
            date_from=date(2026, 1, 1),
            format=ExportFormat.CSV,
        )

        # Step 2: API layer captures tenant context and builds payload
        tenant_id = "550e8400-e29b-41d4-a716-446655440000"
        tenant_schema = "t_550e8400e29b41d4a716446655440000"
        payload = ExportJobPayload.from_request(
            request=request,
            tenant_id=tenant_id,
            tenant_schema=tenant_schema,
            user_id="user-789",
        )

        # Step 3: Simulate JSON serialization (what S4 Job Queue does)
        payload_dict = json.loads(json.dumps(payload.model_dump()))

        # Step 4: Worker deserializes and validates
        restored = ExportJobPayload(**payload_dict)
        assert restored.tenant_id == tenant_id
        assert restored.tenant_schema == tenant_schema
        assert restored.view == "sales_daily"
        assert restored.metrics == ["revenue"]
        assert restored.dimensions == ["date", "currency"]

    def test_chain_rejects_tampered_tenant_id(self):
        """
        If someone tampers with the payload to remove tenant_id,
        the worker MUST reject it.
        """
        payload_dict = {
            "tenant_id": "",  # tampered!
            "tenant_schema": "t_abc",
            "user_id": "uid",
            "view": "sales_daily",
            "metrics": ["revenue"],
        }
        with pytest.raises(ValueError, match="MUST NOT be empty"):
            ExportJobPayload(**payload_dict)


# ============================================================================
# 7. ExportStatusData Response Schema Tests
# ============================================================================

class TestExportStatusData:
    """Test the response schema for export status."""

    def test_pending_status(self):
        """Pending export should have no download_url."""
        data = ExportStatusData(
            job_id="job-123",
            status="pending",
            format="csv",
        )
        assert data.download_url is None
        assert data.row_count is None

    def test_completed_status_with_metadata(self):
        """Completed export should include download info."""
        data = ExportStatusData(
            job_id="job-123",
            status="completed",
            format="csv",
            download_url="/api/v1/exports/job-123/download",
            row_count=1500,
            file_size_bytes=45000,
        )
        assert data.download_url is not None
        assert data.row_count == 1500

    def test_failed_status_with_error(self):
        """Failed export should include error message."""
        data = ExportStatusData(
            job_id="job-123",
            status="failed",
            format="xlsx",
            error="Database connection timeout",
        )
        assert data.error == "Database connection timeout"
        assert data.download_url is None


# ============================================================================
# 8. Export API Fail-Closed Security Tests
# ============================================================================

class TestExportApiFailClosed:
    """Test export API security behavior at handler boundaries."""

    @pytest.mark.asyncio
    async def test_status_malformed_job_id_returns_controlled_error(self):
        from api.v1.exports import get_export_status

        request = _request_with_context()
        token = await _exports_create_token(request)

        response = await get_export_status(request, "not-a-uuid", token)
        body = _response_json(response)

        assert response.status_code in (400, 404)
        assert response.status_code != 500
        assert body["error"]["code"] in {"INVALID_EXPORT_ID", "EXPORT_NOT_FOUND"}
        assert "badly formed hexadecimal UUID string" not in json.dumps(body)
        assert "ValueError" not in json.dumps(body)

    @pytest.mark.asyncio
    async def test_download_malformed_job_id_returns_controlled_error(self):
        from api.v1.exports import download_export

        request = _request_with_context()
        token = await _exports_create_token(request)

        response = await download_export(request, "not-a-uuid", token)
        body = _response_json(response)

        assert response.status_code in (400, 404)
        assert response.status_code != 500
        assert body["error"]["code"] in {"INVALID_EXPORT_ID", "EXPORT_NOT_FOUND"}
        assert "badly formed hexadecimal UUID string" not in json.dumps(body)
        assert "ValueError" not in json.dumps(body)

    @pytest.mark.asyncio
    async def test_export_permission_rejects_no_auth(self):
        request = StarletteRequest({"type": "http", "headers": []})

        with pytest.raises(HTTPException) as exc:
            await RequirePermission("exports:create")(request)

        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_wrong_tenant_status_job_id_remains_hidden(self, monkeypatch):
        from api.v1.exports import get_export_status

        request = _request_with_context()
        token = await _exports_create_token(request)
        _patch_job_lookup(monkeypatch, _job(tenant_id=OTHER_TENANT_ID))

        response = await get_export_status(request, str(uuid.uuid4()), token)
        body = _response_json(response)

        assert response.status_code == 404
        assert body["error"]["code"] == "EXPORT_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_pending_job_download_remains_conflict(self, monkeypatch):
        from api.v1.exports import download_export

        request = _request_with_context()
        token = await _exports_create_token(request)
        _patch_job_lookup(monkeypatch, _job(status="pending"))

        response = await download_export(request, str(uuid.uuid4()), token)
        body = _response_json(response)

        assert response.status_code == 409
        assert body["error"]["code"] == "EXPORT_NOT_READY"


# ============================================================================
# 9. Value Serialization Tests
# ============================================================================

class TestValueSerialization:
    """Test the _serialize_value helper used by streaming writers."""

    def test_serialize_decimal(self):
        from jobs.export_jobs import _serialize_value
        assert _serialize_value(Decimal("1234.5678")) == 1234.5678

    def test_serialize_date(self):
        from jobs.export_jobs import _serialize_value
        assert _serialize_value(date(2026, 1, 15)) == "2026-01-15"

    def test_serialize_datetime(self):
        from jobs.export_jobs import _serialize_value
        dt = datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        assert "2026-01-15" in _serialize_value(dt)

    def test_serialize_none(self):
        from jobs.export_jobs import _serialize_value
        assert _serialize_value(None) == ""

    def test_serialize_uuid(self):
        from jobs.export_jobs import _serialize_value
        u = uuid.uuid4()
        assert _serialize_value(u) == str(u)

    def test_serialize_string_passthrough(self):
        from jobs.export_jobs import _serialize_value
        assert _serialize_value("hello") == "hello"

    def test_serialize_int_passthrough(self):
        from jobs.export_jobs import _serialize_value
        assert _serialize_value(42) == 42
