"""Regression contracts for the independent frozen-candidate audit.

These are token, routing and filesystem controls, not database/V3 evidence.
"""
from pathlib import Path
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4
import hashlib
import json
import secrets

import pytest
from fastapi import FastAPI, HTTPException
from starlette.routing import Match


@pytest.mark.parametrize("kind", ["refresh", "unknown", None])
def test_business_auth_rejects_non_access_token(monkeypatch, kind):
    from core import security
    from api.context.auth import resolve_auth_context

    monkeypatch.setattr(security, "get_settings", lambda: SimpleNamespace(
        SECRET_KEY=secrets.token_hex(32), ALGORITHM="HS256"))
    # One stable synthetic key for both encode and decode.
    settings = security.get_settings()
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    from jose import jwt
    tenant_id = uuid4()
    claims = {
        "user_id": str(uuid4()),
        "tenant_id": str(tenant_id),
        "tenant_schema": f"t_{tenant_id.hex}",
        "sv": security.SESSION_VERSION,
        "credential_epoch": 7,
    }
    if kind is not None:
        claims['type'] = kind
    token = jwt.encode(claims,
                       settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    with pytest.raises(HTTPException) as raised:
        resolve_auth_context(token)
    assert raised.value.status_code == 401, "AUDIT-F06-NON-ACCESS-REJECTED"
    assert raised.value.detail["code"] == (
        "INVALID_TOKEN_TYPE" if kind == "refresh" else "INVALID_TOKEN"
    )


def test_business_auth_keeps_access_token(monkeypatch):
    from core import security
    from api.context.auth import resolve_auth_context
    settings = SimpleNamespace(SECRET_KEY=secrets.token_hex(32), ALGORITHM="HS256")
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    from jose import jwt
    uid = str(uuid4())
    legacy = jwt.encode({"user_id": uid, "type": "access"},
                        settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    with pytest.raises(HTTPException) as refused:
        resolve_auth_context(legacy)
    assert refused.value.status_code == 401
    assert refused.value.detail["code"] == "INVALID_TOKEN"

    tenant_id = uuid4()
    token = security.create_contextual_token(uid, [], str(tenant_id), f"t_{tenant_id.hex}",
                                             credential_epoch=7, expires_delta=timedelta(minutes=5))
    assert resolve_auth_context(token).token.user_id == uid


def test_full_app_orders_export_resolves_static_handler():
    from api.app import configure_app
    from api.v1.data_export import export_orders_csv
    from core.config import get_settings
    app = FastAPI()
    configure_app(app, get_settings())
    scope = {"type": "http", "path": "/api/v1/orders/export", "method": "GET",
             "root_path": ""}
    first = next(route for route in app.routes if route.matches(scope)[0] == Match.FULL)
    assert first.endpoint is export_orders_csv, "AUDIT-F07-STATIC-EXPORT-ROUTE"


def _sidecar(root: Path, *, payload: dict, content: str):
    path = root / f"{payload['file_id']}.csv"
    raw = f"label\n{content}\n".encode("utf-8-sig")
    path.write_bytes(raw)
    meta = {
        **payload,
        "metadata_version": 1,
        "file_path": str(path),
        "file_name": path.name,
        "row_count": 1,
        "file_size_bytes": len(raw),
        "content_sha256": hashlib.sha256(raw).hexdigest(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    (root / f"{payload['file_id']}.meta.json").write_text(json.dumps(meta))
    return meta


def test_export_jobs_use_persisted_file_identity(tmp_path, monkeypatch):
    import jobs.export_jobs as jobs
    from api.v1.exports import _find_job_metadata
    monkeypatch.setattr(jobs, "EXPORT_DIR", tmp_path)
    identity = {"tenant_id": str(uuid4()), "user_id": str(uuid4()), "format": "csv"}
    first, second = str(uuid4()), str(uuid4())
    _sidecar(tmp_path, payload={**identity, "file_id": first}, content="first")
    _sidecar(tmp_path, payload={**identity, "file_id": second}, content="second")
    for file_id in (first, second):
        meta = _find_job_metadata(str(uuid4()), {**identity, "file_id": file_id})
        assert meta["file_id"] == file_id, "AUDIT-F08-EXACT-JOB-FILE"
        content = "first" if file_id == first else "second"
        assert Path(meta["file_path"]).read_text(encoding="utf-8-sig") == f"label\n{content}\n"


@pytest.mark.parametrize("case", ["missing", "wrong_tenant", "missing_file", "traversal"])
def test_export_job_never_falls_back_to_other_file(tmp_path, monkeypatch, case):
    import jobs.export_jobs as jobs
    from api.v1.exports import _find_job_metadata
    monkeypatch.setattr(jobs, "EXPORT_DIR", tmp_path)
    payload = {
        "tenant_id": str(uuid4()), "user_id": str(uuid4()), "format": "csv", "file_id": str(uuid4()),
    }
    unrelated = {**payload, "file_id": str(uuid4())}
    _sidecar(tmp_path, payload=unrelated, content="unrelated")
    assert _find_job_metadata(str(uuid4()), unrelated) is not None
    if case == "wrong_tenant":
        _sidecar(tmp_path, payload={**payload, "tenant_id": str(uuid4())}, content="wrong")
    elif case == "missing_file":
        meta = _sidecar(tmp_path, payload=payload, content="gone")
        Path(meta["file_path"]).unlink()
    elif case == "traversal":
        payload["file_id"] = "../unrelated"
    assert _find_job_metadata(str(uuid4()), payload) is None, "AUDIT-F08-NO-FALLBACK"


def test_export_file_identity_is_created_before_enqueue_and_survives_serialization():
    from api.schemas.jobs import ExportJobPayload, ExportRequest
    tenant = str(uuid4())
    request = ExportRequest(view='sales_daily', metrics=['revenue'])
    first, second = [ExportJobPayload.from_request(request, tenant, 't_' + tenant.replace('-', ''), str(uuid4())) for _ in range(2)]
    assert first.file_id and second.file_id and first.file_id != second.file_id, 'AUDIT-F08-PERSISTED-UNIQUE-RESULT'
    assert ExportJobPayload(**first.model_dump()).file_id == first.file_id


@pytest.mark.asyncio
async def test_legacy_unmapped_worker_refuses_instead_of_creating_orphan_file(monkeypatch):
    import jobs.export_jobs as jobs
    def forbidden_connection():
        raise AssertionError('A missing file binding must be refused before database work')
    monkeypatch.setattr(jobs, 'ReportingSessionLocal', forbidden_connection)
    with pytest.raises(ValueError, match='persisted file identity'):
        await jobs.export_report_worker({'tenant_id': str(uuid4()), 'tenant_schema': 't_fixture',
            'user_id': str(uuid4()), 'view': 'sales_daily', 'metrics': ['revenue'], 'format': 'csv'})
