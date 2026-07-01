"""U4-C internal-login-only intake workspace API contract tests."""
from __future__ import annotations

import hashlib
import importlib.util
import os
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

import httpx
import pytest
from alembic import op
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from fastapi import FastAPI, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test_db")  # pragma: allowlist secret
os.environ.setdefault(
    "SECRET_KEY",
    hashlib.sha256(b"mpango-test-runner-key-not-for-production").hexdigest(),  # pragma: allowlist secret
)
os.environ.setdefault("REPORTING_USER_PASSWORD", "test")  # pragma: allowlist secret
os.environ["MPANGO_ENV"] = "test"

BACKEND_DIR = Path(__file__).resolve().parents[1]
INTAKE_API = BACKEND_DIR / "api" / "v1" / "intake.py"
TEST_TENANT_SCHEMA = os.environ.get("TEST_TENANT_SCHEMA", "t_test")
TEST_TENANT_ID = os.environ.get("TEST_TENANT_ID", "11111111-1111-1111-1111-111111111111")
OTHER_TENANT_ID = "22222222-2222-2222-2222-222222222222"


class _Permission:
    def __init__(self, code: str):
        self.code = code


class _Role:
    def __init__(self, permissions: list[str]):
        self.permissions = [_Permission(code) for code in permissions]


class _RuntimeStrategy:
    def __init__(self, *, permissions: Optional[list[str]], tenant_id: str = TEST_TENANT_ID):
        self.permissions = permissions
        self.tenant_id = tenant_id

    async def authenticate(self, request: Request):
        if self.permissions is None:
            return None
        from api.context.auth import AuthContext
        from core.security import TokenPayload

        return AuthContext(
            token=TokenPayload(
                user_id="00000000-0000-0000-0000-0000000000aa",
                tenant_id=self.tenant_id,
                tenant_schema=TEST_TENANT_SCHEMA,
                roles=["runtime-test"],
            ),
            raw_token="runtime-test-token",
        )

    async def resolve_tenant_context(self, auth_ctx):
        from api.context.tenant import TenantContext, create_tenant_session

        session = await create_tenant_session(TEST_TENANT_SCHEMA)
        session.info["tenant_id"] = self.tenant_id
        return TenantContext(
            tenant_id=self.tenant_id,
            tenant_schema=TEST_TENANT_SCHEMA,
            session=session,
            user=SimpleNamespace(roles=[_Role(self.permissions or [])], is_active=True),
        )


def _build_runtime_app(*, permissions: Optional[list[str]], tenant_id: str = TEST_TENANT_ID) -> FastAPI:
    from api.middleware.auth import AuthenticationMiddleware
    from api.v1 import intake

    app = FastAPI()
    app.add_middleware(AuthenticationMiddleware, strategy=_RuntimeStrategy(permissions=permissions, tenant_id=tenant_id))
    app.include_router(intake.router, prefix="/api/v1/intake")
    return app


async def _ensure_intake_schema(session: AsyncSession) -> None:
    await _run_024_upgrade(session, TEST_TENANT_SCHEMA)
    await session.execute(text(f'TRUNCATE TABLE "{TEST_TENANT_SCHEMA}".intake_validation_issues CASCADE'))
    await session.execute(text(f'TRUNCATE TABLE "{TEST_TENANT_SCHEMA}".intake_product_rows CASCADE'))
    await session.execute(text(f'TRUNCATE TABLE "{TEST_TENANT_SCHEMA}".intake_uploads CASCADE'))
    await session.execute(text(f'TRUNCATE TABLE "{TEST_TENANT_SCHEMA}".intake_workspaces CASCADE'))
    await session.commit()


async def _run_024_upgrade(session: AsyncSession, schema: str) -> None:
    await session.execute(text(f'SET search_path TO "{schema}", public'))
    await session.commit()

    migration_file = BACKEND_DIR / "alembic" / "versions" / "024_intake_skeleton.py"
    spec = importlib.util.spec_from_file_location("migration_024_api", migration_file)
    migration_mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(migration_mod)

    def _run_upgrade_sync(sync_conn):
        migration_context = MigrationContext.configure(sync_conn)
        operations = Operations(migration_context)
        saved = {name: getattr(op, name, None) for name in ("create_table", "create_index", "drop_table", "get_bind")}
        op.get_bind = lambda: sync_conn
        op.create_table = operations.create_table
        op.create_index = operations.create_index
        op.drop_table = operations.drop_table
        try:
            migration_mod.upgrade()
        finally:
            for name, original in saved.items():
                if original is not None:
                    setattr(op, name, original)

    async_conn = await session.connection()
    await async_conn.run_sync(_run_upgrade_sync)
    await session.commit()


def _client_for(*, permissions: Optional[list[str]], tenant_id: str = TEST_TENANT_ID):
    app = _build_runtime_app(permissions=permissions, tenant_id=tenant_id)
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://u4c-runtime",
        headers={"Authorization": "Bearer runtime-test-token"},
    )


def _error_code(response: httpx.Response) -> str:
    payload = response.json()
    detail = payload.get("detail", payload)
    return detail["code"]


def test_intake_workspace_routes_are_registered():
    from api.app import app

    route_paths = {getattr(route, "path", None) for route in app.routes}

    assert "/api/v1/intake/workspaces" in route_paths
    assert "/api/v1/intake/workspaces/{workspace_id}" in route_paths
    assert "/api/v1/intake/workspaces/{workspace_id}/uploads" in route_paths
    assert "/api/v1/intake/workspaces/{workspace_id}/mapping" in route_paths
    assert "/api/v1/intake/workspaces/{workspace_id}/validate" in route_paths
    assert "/api/v1/intake/workspaces/{workspace_id}/rows" in route_paths
    assert "/api/v1/intake/workspaces/{workspace_id}/issues" in route_paths


def test_intake_routes_use_required_permissions():
    source = INTAKE_API.read_text(encoding="utf-8")

    assert source.count('RequirePermission("intake:create")') == 1
    assert source.count('RequirePermission("intake:update")') == 2
    assert source.count('RequirePermission("intake:read")') == 4
    assert 'RequireAnyIntakePermission("intake:create", "intake:update")' in source


def test_intake_routes_require_tenant_db_session():
    source = INTAKE_API.read_text(encoding="utf-8")

    assert "get_tenant_db_session" in source
    assert "get_db_session" not in source


def test_intake_u4_has_no_public_or_sku_import_surface():
    source = INTAKE_API.read_text(encoding="utf-8")

    forbidden = [
        "intake_public",
        "ImportService",
        "sku_import",
        "skus/import",
        "SKU(",
    ]
    for value in forbidden:
        assert value not in source, f"Forbidden U4-C API surface found: {value}"


@pytest.mark.asyncio
async def test_unauthenticated_request_to_workspaces_is_rejected(async_session):
    await _ensure_intake_schema(async_session)

    async with _client_for(permissions=None) as client:
        response = await client.get("/api/v1/intake/workspaces")

    assert response.status_code == 401
    assert _error_code(response) == "UNAUTHENTICATED"


@pytest.mark.asyncio
async def test_authenticated_user_without_intake_create_cannot_post(async_session):
    await _ensure_intake_schema(async_session)

    async with _client_for(permissions=["intake:read"]) as client:
        response = await client.post(
            "/api/v1/intake/workspaces",
            json={"name": "No create", "source_type": "CUSTOMER_ONBOARDING"},
        )

    assert response.status_code == 403
    assert _error_code(response) == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_authenticated_user_without_intake_read_cannot_list_or_detail(async_session):
    await _ensure_intake_schema(async_session)
    workspace_id = uuid.uuid4()
    await async_session.execute(
        text(
            f'INSERT INTO "{TEST_TENANT_SCHEMA}".intake_workspaces '
            "(id, tenant_id, name, source_type, status) "
            "VALUES (:id, :tenant_id, 'Readable only with permission', 'CUSTOMER_ONBOARDING', 'OPEN')"
        ),
        {"id": workspace_id, "tenant_id": TEST_TENANT_ID},
    )
    await async_session.commit()

    async with _client_for(permissions=["intake:create"]) as client:
        list_response = await client.get("/api/v1/intake/workspaces")
        detail_response = await client.get(f"/api/v1/intake/workspaces/{workspace_id}")

    assert list_response.status_code == 403
    assert _error_code(list_response) == "PERMISSION_DENIED"
    assert detail_response.status_code == 403
    assert _error_code(detail_response) == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_contextual_tenant_user_with_intake_create_can_create_workspace(async_session):
    await _ensure_intake_schema(async_session)

    async with _client_for(permissions=["intake:create"]) as client:
        response = await client.post(
            "/api/v1/intake/workspaces",
            json={
                "name": "Runtime create proof",
                "description": "Created through the real route",
                "source_type": "CUSTOMER_ONBOARDING",
                "metadata": {"customer_code": "RUNTIME"},
            },
        )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["tenant_id"] == TEST_TENANT_ID
    assert data["name"] == "Runtime create proof"
    assert data["status"] == "OPEN"
    assert data["metadata"] == {"customer_code": "RUNTIME"}


@pytest.mark.asyncio
async def test_contextual_tenant_user_with_intake_read_can_list_and_detail_created_workspace(async_session):
    await _ensure_intake_schema(async_session)

    async with _client_for(permissions=["intake:create"]) as create_client:
        create_response = await create_client.post(
            "/api/v1/intake/workspaces",
            json={"name": "Runtime read proof", "source_type": "CATALOG_REFRESH"},
        )
    assert create_response.status_code == 201
    workspace_id = create_response.json()["data"]["workspace_id"]

    async with _client_for(permissions=["intake:read"]) as read_client:
        list_response = await read_client.get("/api/v1/intake/workspaces")
        detail_response = await read_client.get(f"/api/v1/intake/workspaces/{workspace_id}")

    assert list_response.status_code == 200
    items = list_response.json()["data"]["items"]
    assert [item["workspace_id"] for item in items] == [workspace_id]
    assert detail_response.status_code == 200
    assert detail_response.json()["data"]["workspace_id"] == workspace_id


@pytest.mark.asyncio
async def test_detail_endpoint_does_not_return_another_tenant_workspace(async_session):
    await _ensure_intake_schema(async_session)
    other_workspace_id = uuid.uuid4()
    await async_session.execute(
        text(
            f'INSERT INTO "{TEST_TENANT_SCHEMA}".intake_workspaces '
            "(id, tenant_id, name, source_type, status) "
            "VALUES (:id, :tenant_id, 'Other tenant workspace', 'CUSTOMER_ONBOARDING', 'OPEN')"
        ),
        {"id": other_workspace_id, "tenant_id": OTHER_TENANT_ID},
    )
    await async_session.commit()

    async with _client_for(permissions=["intake:read"], tenant_id=TEST_TENANT_ID) as client:
        response = await client.get(f"/api/v1/intake/workspaces/{other_workspace_id}")

    assert response.status_code == 404
    assert _error_code(response) == "WORKSPACE_NOT_FOUND"
