"""DC-10G Platform UUID + Export Error Boundary Hardening tests (R1).

Corrections from R0:
- All env mutations use monkeypatch (auto-restored).
- Export enqueue test executes the actual create_export handler with a
  sentinel exception containing fake internal URL/credential text; asserts
  the sentinel text is absent from both response and logs.
- Malformed UUID tests assert db.execute.await_count == 0 (fail before SQL).
- Direct test for p10.services.get_audit_event (malformed -> None, no DB call).
- Platform tests call handlers directly (no FastAPI app construction) to
  avoid test-isolation issues with route-auth tests.
"""
from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.responses import JSONResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_db_returns_none():
    """Mock async DB session that returns None for all scalar queries."""
    db = MagicMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result)
    return db


# ---------------------------------------------------------------------------
# Platform tenant UUID hardening (direct handler calls)
# ---------------------------------------------------------------------------

class TestPlatformTenantUUIDHardening:
    """Malformed wholesaler_id must return 404 (not 500) and never reach SQL."""

    def test_malformed_wholesaler_id_returns_404_before_sql(self):
        from api.v1.platform.tenants import get_tenant
        mock_db = _mock_db_returns_none()

        result = asyncio.run(get_tenant("not-a-uuid", db=mock_db, _auth=None))
        assert isinstance(result, JSONResponse)
        assert result.status_code == 404
        assert mock_db.execute.await_count == 0

    def test_well_formed_missing_uuid_returns_404(self):
        from api.v1.platform.tenants import get_tenant
        mock_db = _mock_db_returns_none()

        result = asyncio.run(
            get_tenant("00000000-0000-0000-0000-000000000000", db=mock_db, _auth=None)
        )
        assert isinstance(result, JSONResponse)
        assert result.status_code == 404
        assert mock_db.execute.await_count >= 1


# ---------------------------------------------------------------------------
# Platform audit UUID hardening (direct handler calls)
# ---------------------------------------------------------------------------

class TestPlatformAuditUUIDHardening:
    """Malformed log_id must return 404 (not 500) and never reach SQL."""

    def test_malformed_log_id_returns_404_before_sql(self):
        from api.v1.platform.audit import get_audit_log
        mock_db = _mock_db_returns_none()

        with pytest.raises(Exception) as exc_info:
            asyncio.run(get_audit_log("not-a-uuid", db=mock_db, _auth=None))
        assert exc_info.value.status_code == 404
        assert mock_db.execute.await_count == 0

    def test_well_formed_missing_log_id_returns_404(self):
        from api.v1.platform.audit import get_audit_log
        mock_db = _mock_db_returns_none()

        with pytest.raises(Exception) as exc_info:
            asyncio.run(
                get_audit_log("00000000-0000-0000-0000-000000000000", db=mock_db, _auth=None)
            )
        assert exc_info.value.status_code == 404
        assert mock_db.execute.await_count >= 1


# ---------------------------------------------------------------------------
# p10.services.get_audit_event direct test
# ---------------------------------------------------------------------------

class TestP10GetAuditEventDirect:
    """Direct unit test for the get_audit_event service function."""

    def test_malformed_uuid_returns_none_without_db_call(self):
        from api.v1.platform.p10.services import get_audit_event
        mock_db = MagicMock()
        mock_db.execute = AsyncMock()

        result = asyncio.run(get_audit_event(mock_db, "not-a-uuid"))
        assert result is None
        assert mock_db.execute.await_count == 0

    def test_well_formed_missing_uuid_returns_none(self):
        from api.v1.platform.p10.services import get_audit_event
        mock_db = _mock_db_returns_none()

        result = asyncio.run(get_audit_event(mock_db, "00000000-0000-0000-0000-000000000000"))
        assert result is None
        assert mock_db.execute.await_count >= 1


# ---------------------------------------------------------------------------
# Export enqueue error boundary (executes real handler)
# ---------------------------------------------------------------------------

class TestExportEnqueueErrorBoundary:
    """Execute the actual create_export handler; prove no str(exception) leak."""

    def test_enqueue_failure_sanitized_response_and_logs(self, capsys):
        """When enqueue raises a sentinel exception containing fake internal
        URL/credential text, the 500 response must use a fixed sanitized
        message and the sentinel text must not appear in response or logs."""
        from api.v1.exports import create_export
        from api.schemas.jobs import ExportRequest
        from services.reporting.semantic_layer import ViewScope, ReportMetric
        from api.schemas.jobs import ExportFormat
        from api.context.tenant import TenantContext

        # Sentinel exception text that must NEVER leak to the client or logs.
        SENTINEL_URL = "redis://super-secret:password@internal-host:6379/0"  # pragma: allowlist secret
        SENTINEL_TEXT = f"Connection refused: {SENTINEL_URL}"

        body = ExportRequest(
            view=ViewScope.SALES_DAILY,
            metrics=[ReportMetric.REVENUE],
            format=ExportFormat.CSV,
        )

        fake_user = MagicMock()
        fake_user.id = "00000000-0000-0000-0000-000000000001"
        fake_tenant_ctx = TenantContext(
            tenant_id="00000000-0000-0000-0000-000000000002",
            tenant_schema="t_test",
            session=MagicMock(),
            user=fake_user,
        )

        sentinel_exc = ConnectionError(SENTINEL_TEXT)

        with patch("api.v1.exports._extract_tenant", return_value=fake_tenant_ctx), \
             patch("main.get_job_queue") as mock_get_queue:
            mock_queue = MagicMock()
            mock_queue.enqueue = AsyncMock(side_effect=sentinel_exc)
            mock_get_queue.return_value = mock_queue

            mock_request = MagicMock()
            result = asyncio.run(create_export(request=mock_request, body=body))

        captured = capsys.readouterr()
        log_text = captured.out + captured.err

        # Assert HTTP 500
        assert isinstance(result, JSONResponse)
        assert result.status_code == 500

        # Assert response body
        body_bytes = result.body if hasattr(result, "body") else b""
        body_str = body_bytes.decode("utf-8", errors="replace") if isinstance(body_bytes, bytes) else str(body_bytes)
        assert "EXPORT_ENQUEUE_FAILED" in body_str
        assert "Unable to enqueue export job" in body_str

        # CRITICAL: sentinel text must NOT appear in the response body.
        assert SENTINEL_URL not in body_str
        assert SENTINEL_TEXT not in body_str
        assert "Connection refused" not in body_str
        assert "password" not in body_str.lower()

        # CRITICAL: sentinel text must NOT appear in logs.
        assert SENTINEL_URL not in log_text
        assert SENTINEL_TEXT not in log_text
        assert "Connection refused" not in log_text

        # Only the exception CLASS NAME may appear in logs.
        assert "ConnectionError" in log_text

    def test_malformed_export_id_returns_400(self):
        """Regression: DC-6B malformed export job_id still returns 400."""
        from api.v1.exports import _parse_export_job_id, _invalid_export_id_response

        assert _parse_export_job_id("not-a-uuid") is None
        assert _parse_export_job_id("00000000-0000-0000-0000-000000000000") is not None

        resp = _invalid_export_id_response()
        assert resp.status_code == 400
        body = resp.body.decode() if hasattr(resp, "body") else str(resp)
        assert "INVALID_EXPORT_ID" in body
        assert "badly formed" not in body.lower()
        assert "ValueError" not in body
        assert "traceback" not in body.lower()


    def test_malformed_export_id_returns_400(self):
        """Regression: DC-6B malformed export job_id still returns 400."""
        from api.v1.exports import _parse_export_job_id, _invalid_export_id_response

        assert _parse_export_job_id("not-a-uuid") is None
        assert _parse_export_job_id("00000000-0000-0000-0000-000000000000") is not None

        resp = _invalid_export_id_response()
        assert resp.status_code == 400
        body = resp.body.decode() if hasattr(resp, "body") else str(resp)
        assert "INVALID_EXPORT_ID" in body
        assert "badly formed" not in body.lower()
        assert "ValueError" not in body
        assert "traceback" not in body.lower()
