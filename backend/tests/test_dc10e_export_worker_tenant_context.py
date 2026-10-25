import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import text
from starlette.requests import Request as StarletteRequest

from api.context.auth import AuthContext, attach_auth_context
from api.context.tenant import TenantContext, attach_tenant_context
from api.middleware.rbac import RequirePermission
from core.security import TokenPayload
from database.session import AsyncSessionLocal


TENANT_A_ID = "550e8400-e29b-41d4-a716-446655440000"
TENANT_A_SCHEMA = "t_550e8400e29b41d4a716446655440000"
TENANT_B_ID = "660e8400-e29b-41d4-a716-446655440000"
TENANT_B_SCHEMA = "t_660e8400e29b41d4a716446655440000"


def _payload(*, tenant_id: str = TENANT_A_ID, tenant_schema: str = TENANT_A_SCHEMA):
    return {
        "tenant_id": tenant_id,
        "tenant_schema": tenant_schema,
        "user_id": "770e8400-e29b-41d4-a716-446655440000",
        "view": "sales_daily",
        "metrics": ["revenue", "transaction_count"],
        "dimensions": ["date"],
        "format": "csv",
        "limit": 100,
    }


async def _create_reporting_table(schema: str, revenue: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await session.execute(text(f'CREATE SCHEMA "{schema}"'))
        await session.execute(text(f'GRANT USAGE ON SCHEMA "{schema}" TO reporting_role'))
        await session.execute(text(f'''
            CREATE TABLE "{schema}".mv_sales_daily (
                transaction_date DATE NOT NULL,
                reporting_currency_code VARCHAR(3) NOT NULL,
                daily_revenue NUMERIC(20, 4) NOT NULL,
                transaction_count INTEGER NOT NULL,
                PRIMARY KEY (transaction_date, reporting_currency_code)
            )
        '''))
        await session.execute(
            text(f'''
                INSERT INTO "{schema}".mv_sales_daily (
                    transaction_date,
                    reporting_currency_code,
                    daily_revenue,
                    transaction_count
                ) VALUES ('2026-01-01', 'USD', :revenue, 1)
            '''),
            {"revenue": revenue},
        )
        await session.execute(text(f'GRANT SELECT ON "{schema}".mv_sales_daily TO reporting_role'))
        await session.commit()


async def _drop_reporting_schema(schema: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await session.commit()


def _request_with_context(tenant_id: str = TENANT_A_ID) -> StarletteRequest:
    request = StarletteRequest({"type": "http", "headers": []})
    permission = SimpleNamespace(code="exports:create")
    role = SimpleNamespace(permissions=[permission])
    user = SimpleNamespace(id="770e8400-e29b-41d4-a716-446655440000", roles=[role])
    token = TokenPayload(
        user_id="770e8400-e29b-41d4-a716-446655440000",
        tenant_id=tenant_id,
        tenant_schema=TENANT_A_SCHEMA if tenant_id == TENANT_A_ID else TENANT_B_SCHEMA,
        roles=["admin"],
    )
    attach_auth_context(request, AuthContext(token=token, raw_token="redacted-test-token"))
    from tests.rc2_current_contract_support import current_rbac_sql
    async def execute(statement, params=None):
        answer = current_rbac_sql(statement, params, schema=token.tenant_schema,
            user_id=token.user_id, permissions={"exports:create"}, roles=["admin"])
        assert answer is not None, "UNMODELED_EXPORT_RBAC_SQL"
        return answer
    attach_tenant_context(
        request,
        TenantContext(
            tenant_id=tenant_id,
            tenant_schema=token.tenant_schema or TENANT_A_SCHEMA,
            session=SimpleNamespace(execute=execute),
            user=user,
        ),
    )
    return request


async def _submitted_payload(monkeypatch, *, tenant_id=TENANT_A_ID):
    from api.schemas.jobs import ExportRequest
    from api.v1.exports import create_export
    from core.jobs.local_queue import LocalJobQueue
    from models.job import Job
    from sqlalchemy import select
    queue = LocalJobQueue(max_workers=1)
    monkeypatch.setattr("main.get_job_queue", lambda: queue)
    request = _request_with_context(tenant_id)
    token = await _exports_create_token(request)
    response = await create_export(request, ExportRequest(view="sales_daily",
        metrics=["revenue", "transaction_count"], dimensions=["date"], format="csv", limit=100), token)
    assert response.status_code == 202
    job_id = uuid.UUID(json.loads(response.body)["data"]["job_id"])
    async with AsyncSessionLocal() as db:
        db.info["tenant_schema"] = "public"
        row = (await db.execute(select(Job).where(Job.id == job_id))).scalar_one()
        payload = dict(row.payload)
    assert payload["file_id"] and payload["tenant_id"] == tenant_id
    assert payload == queue.jobs[str(job_id)]["payload"]
    return job_id, payload, queue


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


class _AssertingResult:
    def keys(self):
        return ["transaction_date", "daily_revenue"]

    def fetchmany(self, size):
        return []


class _AssertingReportingSession:
    def __init__(self, expected_tenant_id: str, expected_tenant_schema: str):
        self.info = {}
        self.expected_tenant_id = expected_tenant_id
        self.expected_tenant_schema = expected_tenant_schema
        self.execute_count = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement):
        self.execute_count += 1
        assert self.info["tenant_id"] == self.expected_tenant_id
        assert self.info["tenant_schema"] == self.expected_tenant_schema
        return _AssertingResult()


@pytest.mark.asyncio
async def test_worker_real_reporting_session_has_required_tenant_context(
    tmp_path, monkeypatch, ensure_reporting_user_password
):
    from jobs import export_jobs
    from jobs.export_jobs import export_report_worker

    await _create_reporting_table(TENANT_A_SCHEMA, "123.4500")
    monkeypatch.setattr(export_jobs, "EXPORT_DIR", tmp_path)

    try:
        job_id, payload, queue = await _submitted_payload(monkeypatch)
        await export_report_worker(payload)
    finally:
        await _drop_reporting_schema(TENANT_A_SCHEMA)


@pytest.mark.asyncio
async def test_worker_sets_tenant_context_before_first_sql(tmp_path, monkeypatch):
    from jobs import export_jobs
    from jobs.export_jobs import export_report_worker

    session = _AssertingReportingSession(TENANT_A_ID, TENANT_A_SCHEMA)
    monkeypatch.setattr(export_jobs, "ReportingSessionLocal", lambda: session)
    monkeypatch.setattr(export_jobs, "EXPORT_DIR", tmp_path)

    job_id, payload, queue = await _submitted_payload(monkeypatch)
    await export_report_worker(payload)

    assert session.execute_count >= 1


@pytest.mark.asyncio
async def test_valid_tenant_export_creates_metadata_and_downloads(
    tmp_path, monkeypatch, ensure_reporting_user_password
):
    from api.v1.exports import download_export, get_export_status
    from jobs import export_jobs
    from jobs.export_jobs import export_report_worker

    await _create_reporting_table(TENANT_A_SCHEMA, "123.4500")
    monkeypatch.setattr(export_jobs, "EXPORT_DIR", tmp_path)

    try:
        job_id, payload, queue = await _submitted_payload(monkeypatch)
        await export_report_worker(payload)
        metadata_files = list(Path(tmp_path).glob("*.meta.json"))
        assert len(metadata_files) == 1
        metadata = json.loads(metadata_files[0].read_text(encoding="utf-8"))
        assert metadata["tenant_id"] == TENANT_A_ID
        assert metadata["row_count"] == 1

        # The actual queue completion writes the same persisted job row.
        await queue._execute_job(queue.jobs[str(job_id)])
        assert queue.jobs[str(job_id)]["status"].value == "completed"
        request = _request_with_context(TENANT_A_ID)
        token = await _exports_create_token(request)
        status_response = await get_export_status(request, str(job_id), token)
        status_body = json.loads(status_response.body.decode("utf-8"))
        assert status_response.status_code == 200
        assert status_body["data"]["download_url"] == f"/api/v1/exports/{job_id}/download"

        download_response = await download_export(request, str(job_id), token)
        assert getattr(download_response, "status_code", 200) == 200
        from api.v1.exports import _find_job_metadata
        assert _find_job_metadata(str(job_id), {"tenant_id": TENANT_A_ID}) is None
        assert _find_job_metadata(str(job_id), {**payload, "file_id": "missing"}) is None
        other = _request_with_context(TENANT_B_ID)
        other_token = await _exports_create_token(other)
        assert (await get_export_status(other, str(job_id), other_token)).status_code == 404
        assert (await download_export(other, str(job_id), other_token)).status_code == 404
        export_jobs._write_metadata(payload["file_id"], {**metadata, "tenant_id": TENANT_B_ID})
        assert _find_job_metadata(str(job_id), payload) is None
        export_jobs._write_metadata(payload["file_id"], metadata)
    finally:
        await _drop_reporting_schema(TENANT_A_SCHEMA)


@pytest.mark.asyncio
async def test_tenant_a_export_does_not_include_tenant_b_rows(
    tmp_path, monkeypatch, ensure_reporting_user_password
):
    from jobs import export_jobs
    from jobs.export_jobs import export_report_worker

    await _create_reporting_table(TENANT_A_SCHEMA, "111.0000")
    await _create_reporting_table(TENANT_B_SCHEMA, "999.0000")
    monkeypatch.setattr(export_jobs, "EXPORT_DIR", tmp_path)

    try:
        job_id, payload, queue = await _submitted_payload(monkeypatch)
        await export_report_worker(payload)
        csv_files = list(Path(tmp_path).glob("*.csv"))
        assert len(csv_files) == 1
        csv_text = csv_files[0].read_text(encoding="utf-8")
        assert "111" in csv_text
        assert "999" not in csv_text
    finally:
        await _drop_reporting_schema(TENANT_A_SCHEMA)
        await _drop_reporting_schema(TENANT_B_SCHEMA)


@pytest.mark.asyncio
async def test_missing_or_invalid_tenant_context_fails_closed(tmp_path, monkeypatch):
    from jobs import export_jobs
    from jobs.export_jobs import export_report_worker

    monkeypatch.setattr(export_jobs, "EXPORT_DIR", tmp_path)

    with pytest.raises(ValueError, match="MUST NOT be empty"):
        await export_report_worker(_payload(tenant_id="", tenant_schema=TENANT_A_SCHEMA))

    with pytest.raises(ValueError, match="must start with 't_'"):
        await export_report_worker(_payload(tenant_id=TENANT_A_ID, tenant_schema="public"))


@pytest.mark.asyncio
async def test_retry_does_not_lose_tenant_context(
    tmp_path, monkeypatch, ensure_reporting_user_password
):
    from jobs import export_jobs
    from jobs.export_jobs import export_report_worker

    await _create_reporting_table(TENANT_A_SCHEMA, "123.4500")
    monkeypatch.setattr(export_jobs, "EXPORT_DIR", tmp_path)

    try:
        job_id, payload, queue = await _submitted_payload(monkeypatch)
        await export_report_worker(payload)
        before = (tmp_path / (payload["file_id"] + ".csv")).read_bytes()
        await export_report_worker(payload)
        assert len(list(Path(tmp_path).glob("*.meta.json"))) == 1
        assert (tmp_path / (payload["file_id"] + ".csv")).read_bytes() == before
        assert export_jobs.read_metadata(payload["file_id"])["tenant_id"] == TENANT_A_ID
    finally:
        await _drop_reporting_schema(TENANT_A_SCHEMA)


def test_export_worker_uses_no_tenant_filter_bypass():
    source = Path("jobs/export_jobs.py").read_text(encoding="utf-8")
    forbidden = ["run_as_system", "ignore_tenant", "mark_session_as_system"]
    for token in forbidden:
        assert token not in source


def test_export_metadata_exposes_no_sensitive_runtime_values(tmp_path, monkeypatch):
    from jobs import export_jobs
    from jobs.export_jobs import _write_metadata

    monkeypatch.setattr(export_jobs, "EXPORT_DIR", tmp_path)
    _write_metadata(
        "safe-file",
        {
            "file_path": str(tmp_path / "safe-file.csv"),
            "tenant_id": TENANT_A_ID,
            "row_count": 1,
            "format": "csv",
        },
    )

    body = (tmp_path / "safe-file.meta.json").read_text(encoding="utf-8")
    assert "postgresql://" not in body
    assert "Authorization" not in body
    assert "Bearer" not in body
    assert "SELECT" not in body.upper()
