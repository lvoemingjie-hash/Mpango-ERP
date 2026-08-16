"""PW1-R4-B4 — Retailer permission context hydration closure.

Product contract under test (POST /api/v1/client/auth/login):
  1. The login response carries SERVER-DERIVED effective permissions of the
     verified tenant-local user (``RetailerLoginUser.permissions``).
  2. Permissions come ONLY from live roles held by the user joined to
     non-deleted permissions rows.
  3. Deduplicated and stably sorted.
  4. The frontend must consume the list verbatim — no role-name inference,
     no hardcoded six-permission list (frontend suite covers that).
  5. JWT semantics and backend RequirePermission behavior are unchanged.
  6. Missing permissions still fail closed (empty-permission user logs in
     but is denied by permission-gated routes).

All artifacts are REAL: the FORMAL tenant bootstrap
(scripts.bootstrap_tenant_schema.bootstrap — including the S1 RBAC
reconcile that seeds retailer_operator with exactly the six client:*
permissions), real public registry rows, and a real FastAPI app wired with
configure_app + the production JwtAuthStrategy (same pattern as the
DC-12R1 PW1 suites), exercised through httpx ASGITransport.

Public rows (wholesalers / tenant_registrations / retailers / bindings)
and tenant users are synthetic direct inserts, documented as synthetic;
the six-permission seeding itself comes from the FORMAL bootstrap, never
from this suite.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import uuid
from unittest import mock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from core.config import get_settings
from core.security import hash_password
from database.session import AsyncSessionLocal

pytestmark = pytest.mark.asyncio

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# The canonical six retailer_operator client:* permissions
# (core.permission_registry.RETAILER_OPERATOR_PERMISSIONS), in the STABLE
# SORTED order the endpoint must return.
SIX_PERMISSIONS = sorted([
    "client:catalog:read",
    "client:orders:read",
    "client:orders:create",
    "client:payments:read",
    "client:payments:declare",
    "client:finance:read",
])


def _async_db_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql+asyncpg://"):
        return url
    raise RuntimeError("TEST_DATABASE_URL/DATABASE_URL must be a PostgreSQL URL")


def _load_formal_bootstrap():
    spec = importlib.util.spec_from_file_location(
        "pw1r4b4_bootstrap", os.path.join(BACKEND_DIR, "scripts", "bootstrap_tenant_schema.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.bootstrap


async def _drop_schema(schema: str) -> None:
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(_async_db_url(), pool_size=1)
    try:
        async with engine.connect() as c:
            await c.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            await c.commit()
    finally:
        await engine.dispose()


async def _namespace_count(schema: str) -> int:
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(_async_db_url(), pool_size=1)
    try:
        async with engine.connect() as c:
            return (
                await c.execute(
                    text(
                        "SELECT count(*) FROM pg_catalog.pg_namespace WHERE nspname = :n"
                    ),
                    {"n": schema},
                )
            ).scalar()
    finally:
        await engine.dispose()


async def _seed_login_environment(
    *, user_email: str, password: str
) -> dict:
    """Bootstrap a formal tenant + the public registry rows login requires.

    Synthetic direct inserts (documented as synthetic; no lifecycle claim):
    an active wholesaler, an ACTIVE tenant_registration whose tenant_schema
    equals ``t_<wholesaler id hex>`` (the registry contract steps 3/6 of
    the login flow — the schema is DERIVED from the wholesaler id here
    exactly as the endpoint requires), a retailer, an active binding, and
    one tenant-local user holding the bootstrap-seeded retailer_operator
    role.
    """
    wholesaler_id = uuid.uuid4()
    # Login step 6: tenant_schema MUST equal Wholesaler.derive_schema_from_id.
    schema = f"t_{wholesaler_id.hex}"
    retailer_id = uuid.uuid4()
    user_id = uuid.uuid4()
    code = f"B4{uuid.uuid4().hex[:6].upper()}"
    await _load_formal_bootstrap()(schema, _async_db_url())
    async with AsyncSessionLocal() as s:
        await s.execute(
            text("INSERT INTO public.wholesalers (id, code, name, status) "
                 "VALUES (:i, :c, :n, 'active')"),
            {"i": wholesaler_id, "c": code, "n": f"B4 WS {code}"},
        )
        await s.execute(
            text(
                "INSERT INTO public.tenant_registrations "
                "(wholesaler_id, company_name, country, owner_email, tenant_schema, "
                " status, password_hash_cleared_at, expires_at) "
                "VALUES (:w, :comp, 'KE', :email, :ts, 'active', now(), "
                " now() + interval '30 days')"
            ),
            {
                "w": wholesaler_id,
                "comp": f"B4 Company {code}",
                "email": f"owner-{code.lower()}@b4.dev",
                "ts": schema,
            },
        )
        await s.execute(
            text("INSERT INTO public.retailers (id, phone, name) VALUES (:i, :ph, :n)"),
            {"i": retailer_id, "ph": f"+2547{uuid.uuid4().int % 10**7:07d}", "n": f"B4 Retailer {code}"},
        )
        await s.execute(
            text(
                "INSERT INTO public.wholesaler_retailer_bindings "
                "(wholesaler_id, retailer_id, status, tenant_user_id, outstanding_balance) "
                "VALUES (:w, :r, 'active', :u, 0)"
            ),
            {"w": wholesaler_id, "r": retailer_id, "u": user_id},
        )
        await s.execute(
            text(f'SET LOCAL search_path TO "{schema}", public')
        )
        await s.execute(
            text(
                f'INSERT INTO "{schema}".users (id, email, password_hash, full_name, is_active) '
                "VALUES (:id, :email, :pw, :name, true)"
            ),
            {"id": user_id, "email": user_email, "pw": hash_password(password),
             "name": "PW1-R4-B4 User"},
        )
        role_id = (await s.execute(
            text(f'SELECT id FROM "{schema}".roles WHERE name = \'retailer_operator\'')
        )).scalar()
        await s.execute(
            text(f'INSERT INTO "{schema}".user_roles (user_id, role_id) '
                 "VALUES (:u, :r) ON CONFLICT DO NOTHING"),
            {"u": user_id, "r": role_id},
        )
        await s.commit()
    return {
        "schema": schema,
        "wholesaler_code": code,
        "wholesaler_id": str(wholesaler_id),
        "user_id": str(user_id),
        "user_email": user_email,
        "password": password,
    }


async def _cleanup_login_environment(env: dict) -> None:
    """Exact-name cleanup: tenant schema + this run's synthetic public rows."""
    async with AsyncSessionLocal() as s:
        await s.execute(
            text("DELETE FROM public.wholesaler_retailer_bindings WHERE wholesaler_id = :w"),
            {"w": env["wholesaler_id"]},
        )
        await s.execute(
            text("DELETE FROM public.tenant_registrations WHERE wholesaler_id = :w"),
            {"w": env["wholesaler_id"]},
        )
        await s.execute(
            text("DELETE FROM public.wholesalers WHERE id = :w"),
            {"w": env["wholesaler_id"]},
        )
        await s.commit()
    await _drop_schema(env["schema"])
    assert await _namespace_count(env["schema"]) == 0


def build_app() -> FastAPI:
    """Real middleware/app wiring with the production JwtAuthStrategy."""
    from api.app import configure_app
    from auth.strategies.jwt import JwtAuthStrategy
    from core.error_codes import register_exception_handlers

    app = FastAPI()
    with mock.patch("auth.factory.get_auth_strategy", return_value=JwtAuthStrategy()):
        configure_app(app, get_settings())
    register_exception_handlers(app)
    return app


async def login(client: AsyncClient, env: dict, *, password: str | None = None):
    return await client.post(
        "/api/v1/client/auth/login",
        json={
            "email": env["user_email"],
            "password": password if password is not None else env["password"],
            "wholesaler_code": env["wholesaler_code"],
        },
    )


# ---------------------------------------------------------------------------
# Shared module environment (tests 1-3 are mutually order-independent:
# test 3's custom permission is soft-deleted and therefore invisible to
# tests 1-2 regardless of execution order; the admin role's grants are
# never held by the login user).
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture(scope="module")
async def b4_env():
    env = await _seed_login_environment(
        user_email=f"b4-full-{uuid.uuid4().hex[:8]}@b4.dev",
        password="pw1r4b4-full",  # pragma: allowlist secret
    )
    try:
        yield env
    finally:
        await _cleanup_login_environment(env)


@pytest_asyncio.fixture(scope="module")
async def api(b4_env):
    app = build_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        yield client


# ---------------------------------------------------------------------------
# 1. Formal-bootstrap retailer_operator login returns the exact six
#    client:* permissions, deduplicated and stably sorted.
# ---------------------------------------------------------------------------
async def test_login_returns_exact_six_sorted_permissions(b4_env, api):
    r = await login(api, b4_env)
    assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:300]}"
    perms = r.json()["data"]["user"]["permissions"]
    assert perms == SIX_PERMISSIONS, (
        f"expected exactly the six client:* permissions in stable sorted "
        f"order, got: {perms}"
    )


# ---------------------------------------------------------------------------
# 2. Foreign permissions do not leak: the admin role's management
#    permissions (granted by the SAME formal bootstrap to a role this user
#    does NOT hold) must never appear in this user's login response.
# ---------------------------------------------------------------------------
async def test_foreign_role_and_user_permissions_do_not_leak(b4_env, api):
    r = await login(api, b4_env)
    assert r.status_code == 200
    perms = r.json()["data"]["user"]["permissions"]
    assert perms == SIX_PERMISSIONS
    # Admin-only codes exist in the same tenant (seeded by the formal
    # bootstrap) but belong to a role this user does not hold.
    assert "payments:confirm_declaration" not in perms
    assert not [p for p in perms if not p.startswith("client:")], (
        f"non-client permission leaked: {perms}"
    )


# ---------------------------------------------------------------------------
# 3. Soft-deleted permissions are never returned, even when still linked
#    to the user's live role.
# ---------------------------------------------------------------------------
async def test_soft_deleted_permission_not_returned(b4_env, api):
    schema = b4_env["schema"]
    stale_code = f"client:stale:{uuid.uuid4().hex[:6]}"
    async with AsyncSessionLocal() as s:
        await s.execute(
            text(f'INSERT INTO "{schema}".permissions (code, description) '
                 "VALUES (:c, 'B4 stale perm') ON CONFLICT (code) DO NOTHING"),
            {"c": stale_code},
        )
        await s.execute(
            text(
                f'INSERT INTO "{schema}".role_permissions (role_id, permission_id) '
                f'SELECT r.id, p.id FROM "{schema}".roles r, "{schema}".permissions p '
                "WHERE r.name = 'retailer_operator' AND p.code = :c "
                "AND NOT EXISTS (SELECT 1 FROM "
                f'"{schema}".role_permissions rp WHERE rp.role_id = r.id '
                "AND rp.permission_id = p.id)"
            ),
            {"c": stale_code},
        )
        await s.commit()
    try:
        r = await login(api, b4_env)
        assert r.status_code == 200
        assert stale_code in r.json()["data"]["user"]["permissions"], (
            "precondition: live grant IS returned before soft-delete"
        )
        # Soft-delete the permission row (the exact lifecycle the contract
        # excludes). is_deleted=true must remove it from the response.
        async with AsyncSessionLocal() as s:
            await s.execute(
                text(f'UPDATE "{schema}".permissions SET is_deleted = true '
                     "WHERE code = :c"),
                {"c": stale_code},
            )
            await s.commit()
        r2 = await login(api, b4_env)
        assert r2.status_code == 200
        assert stale_code not in r2.json()["data"]["user"]["permissions"], (
            "soft-deleted permission leaked into the login response"
        )
        assert r2.json()["data"]["user"]["permissions"] == SIX_PERMISSIONS
    finally:
        async with AsyncSessionLocal() as s:
            await s.execute(
                text(f'DELETE FROM "{schema}".role_permissions WHERE permission_id '
                     f'IN (SELECT id FROM "{schema}".permissions WHERE code = :c)'),
                {"c": stale_code},
            )
            await s.execute(
                text(f'DELETE FROM "{schema}".permissions WHERE code = :c'),
                {"c": stale_code},
            )
            await s.commit()


# ---------------------------------------------------------------------------
# 4. Empty-permission user: login still succeeds (role membership is the
#    login gate, not permissions), the response carries an EMPTY list, and
#    the permission-gated route FAILS CLOSED (403). Fully self-contained
#    tenant (this test removes the role's grants, so it must not share a
#    tenant with the other tests).
# ---------------------------------------------------------------------------
async def test_empty_permission_user_login_ok_but_route_denied():
    env = await _seed_login_environment(
        user_email=f"b4-empty-{uuid.uuid4().hex[:8]}@b4.dev",
        password="pw1r4b4-empty",  # pragma: allowlist secret
    )
    schema = env["schema"]
    # Remove EVERY grant from this tenant's retailer_operator role: the user
    # still HOLDS the role (login gate) but derives ZERO permissions.
    async with AsyncSessionLocal() as s:
        await s.execute(
            text(
                f'DELETE FROM "{schema}".role_permissions '
                f'WHERE role_id IN (SELECT id FROM "{schema}".roles '
                "WHERE name = 'retailer_operator')"
            )
        )
        await s.commit()
    try:
        app = build_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            r = await login(client, env)
            assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:300]}"
            body = r.json()
            assert body["data"]["user"]["permissions"] == [], (
                "expected EMPTY permission list after grants removed"
            )
            token = body["data"]["tokens"]["access_token"]

            # The permission-gated route must fail closed with the SAME
            # contextual JWT (RequirePermission semantics unchanged).
            denied = await client.get(
                "/api/v1/client/orders?page=1&size=100",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert denied.status_code == 403, (
                f"expected 403 for permission-empty user, got {denied.status_code}: "
                f"{denied.text[:200]}"
            )
    finally:
        await _cleanup_login_environment(env)


# ---------------------------------------------------------------------------
# 5. Neutral 401 body never carries permission data (no disclosure in
#    error messages), and permissions live ONLY in the 200 login body.
# ---------------------------------------------------------------------------
async def test_no_permission_disclosure_in_errors(b4_env, api):
    r = await login(api, b4_env, password="definitely-wrong-input")  # pragma: allowlist secret
    assert r.status_code == 401
    body_text = r.text
    assert "client:" not in body_text, (
        f"permission string disclosed in error body: {body_text[:200]}"
    )
    assert "permissions" not in body_text
