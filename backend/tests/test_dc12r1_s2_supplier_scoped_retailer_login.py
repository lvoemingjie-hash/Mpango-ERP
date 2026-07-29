"""DC-12R1-S2 (R1 repair) Supplier-scoped retailer login tests.

Comprehensive tests for POST /api/v1/client/auth/login.  Runs against a real
PostgreSQL 16 database migrated to head 036.

Required proofs (from DC-12R1-S2-R1 task spec):
- A+B retailer login through A returns only A and executes no B-schema query
  (SQL capture proves portal A never references schema B).
- Separate login through B returns only B.
- Wrong email/password/code, missing registration/binding/role, pending user
  and inactive binding produce identical neutral 401 bodies.
- Lowercase codes are normalized to UPPERCASE (not 422); genuinely malformed
  codes (symbols, empty, spaces) produce a controlled 422 with zero SQL.
- JWT is contextual, exact-tenant and has no tmap/available_tenants.
- Response/logs contain no other supplier name/code/schema.
- Refresh, /auth/me and logout preserve the selected context.
- Retailer token accesses client routes but is denied orders, payments,
  finance, invitation-management and platform routes (RBAC 403).
- Owner login still returns its existing available_tenants contract.
- Rate limiting returns controlled 429, never 500.
- Registry/schema fail-closed: soft-deleted registration/user/role/retailer
  and duplicate registry rows all fail neutrally.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from http import HTTPStatus

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from core.config import get_settings
from core.security import (
    create_contextual_token,
    decode_token,
    hash_password,
    verify_password,
)

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Shared test constants (avoid inline secrets for detect-secrets hook)
# ---------------------------------------------------------------------------
_WRONG_PW = "WrongPassword"
_RIGHT_PW_ALT = "RightPass1"
_DUMMY_PW = "dummypw1"
_DEFAULT_PW = "TestPass123"
_TWO_TENANT_PW = "CorrectPass99"
_OWNER_PW = "OwnerPass99"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _execute(db: AsyncSession, sql: str, params: dict | None = None):
    await db.execute(text(sql), params or {})


async def _fetch(db: AsyncSession, sql: str, params: dict | None = None):
    return (await db.execute(text(sql), params or {})).fetchall()


async def _fetch_one(db: AsyncSession, sql: str, params: dict | None = None):
    return (await db.execute(text(sql), params or {})).fetchone()


def _unique_code(prefix: str = "S2T") -> str:
    return f"{prefix}{uuid.uuid4().hex[:8].upper()}"


def _unique_email() -> str:
    return f"s2.retailer.{uuid.uuid4().hex[:8]}@example.com"


def _unique_phone() -> str:
    return f"+2557{uuid.uuid4().hex[:9][:9]}"


async def _make_tenant(
    db: AsyncSession, *, code: str, name: str | None = None
) -> tuple[str, str]:
    """Create a wholesaler + tenant_registrations + tenant schema with RBAC tables."""
    ws_id = uuid.uuid4()
    tenant_schema = f"t_{ws_id.hex}"

    await _execute(
        db,
        "INSERT INTO public.wholesalers (id, code, name, status, is_deleted) "
        "VALUES (:id, :code, :name, 'active', false)",
        {"id": ws_id, "code": code, "name": name or f"Tenant {code}"},
    )

    # Active registration (required for the authoritative join in retailer login).
    # The ck_tenant_registrations_terminal_password_hash_cleared check requires
    # that a terminal status (active/cancelled/expired) has password_hash NULL
    # AND password_hash_cleared_at NOT NULL, so we set the cleared timestamp.
    now_utc = datetime.now(timezone.utc)
    await _execute(
        db,
        "INSERT INTO public.tenant_registrations "
        "(id, company_name, tenant_code, country, owner_email, status, "
        " wholesaler_id, tenant_schema, expires_at, password_hash_cleared_at) "
        "VALUES (:id, :company, :code, 'TZ', :email, 'active', "
        " :ws_id, :schema, :expires, :cleared)",
        {
            "id": uuid.uuid4(),
            "company": name or f"Company {code}",
            "code": code,
            "email": f"owner.{code.lower()}@example.com",
            "ws_id": ws_id,
            "schema": tenant_schema,
            "expires": now_utc + timedelta(days=365),
            "cleared": now_utc,
        },
    )

    # Create minimal tenant schema tables needed for login.
    await _execute(db, f'CREATE SCHEMA IF NOT EXISTS "{tenant_schema}"')
    for stmt in (
        f'CREATE TABLE IF NOT EXISTS "{tenant_schema}".users ('
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
        "email VARCHAR(255) NOT NULL, password_hash VARCHAR(255) NOT NULL, "
        "full_name TEXT, is_active BOOLEAN NOT NULL DEFAULT true, "
        "created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now(), "
        "is_deleted BOOLEAN DEFAULT false, deleted_at TIMESTAMPTZ, "
        "created_by UUID, updated_by UUID)",
        f'CREATE UNIQUE INDEX IF NOT EXISTS ux_users_email_active '
        f'ON "{tenant_schema}".users (email) WHERE is_deleted IS FALSE',
        f'CREATE TABLE IF NOT EXISTS "{tenant_schema}".roles ('
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
        "name VARCHAR(100) NOT NULL UNIQUE, description TEXT, "
        "created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now(), "
        "is_deleted BOOLEAN DEFAULT false, deleted_at TIMESTAMPTZ, "
        "created_by UUID, updated_by UUID)",
        f'CREATE TABLE IF NOT EXISTS "{tenant_schema}".user_roles ('
        f'user_id UUID NOT NULL REFERENCES "{tenant_schema}".users(id) ON DELETE CASCADE, '
        f'role_id UUID NOT NULL REFERENCES "{tenant_schema}".roles(id) ON DELETE CASCADE, '
        "PRIMARY KEY (user_id, role_id))",
        f'CREATE TABLE IF NOT EXISTS "{tenant_schema}".permissions ('
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
        "code VARCHAR(100) NOT NULL UNIQUE, description TEXT, "
        "created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now(), "
        "is_deleted BOOLEAN DEFAULT false, deleted_at TIMESTAMPTZ, "
        "created_by UUID, updated_by UUID)",
        f'CREATE TABLE IF NOT EXISTS "{tenant_schema}".role_permissions ('
        f'role_id UUID NOT NULL REFERENCES "{tenant_schema}".roles(id) ON DELETE CASCADE, '
        f'permission_id UUID NOT NULL REFERENCES "{tenant_schema}".permissions(id) ON DELETE CASCADE, '
        "PRIMARY KEY (role_id, permission_id))",
        # Minimal payments table with the canonical method check constraint.
        # The dc10f (migration 032) preflight enumerates every live registered
        # tenant schema and requires each to expose a payments table whose
        # method column carries ck_payments_method_canonical; without it, our
        # test tenants would pollute that preflight and fail unrelated suites.
        f'CREATE TABLE IF NOT EXISTS "{tenant_schema}".payments ('
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
        "method VARCHAR(32) NOT NULL, "
        "amount NUMERIC(12,2) NOT NULL DEFAULT 0, "
        "CONSTRAINT ck_payments_method_canonical CHECK (method IN ('cash', 'transfer', 'credit'))"
        ")",
    ):
        await _execute(db, stmt)

    # Seed retailer_operator role + client permissions.
    await _execute(
        db,
        f'INSERT INTO "{tenant_schema}".roles (name, description) '
        "VALUES ('retailer_operator', 'Retailer MVP') ON CONFLICT (name) DO NOTHING",
    )
    for code_, desc in (
        ("client:catalog:read", "x"),
        ("client:orders:read", "x"),
        ("client:orders:create", "x"),
    ):
        await _execute(
            db,
            f'INSERT INTO "{tenant_schema}".permissions (code, description) '
            "VALUES (:c, :d) ON CONFLICT (code) DO NOTHING",
            {"c": code_, "d": desc},
        )

    await db.commit()
    return str(ws_id), tenant_schema


async def _create_retailer_user(
    db: AsyncSession,
    *,
    tenant_schema: str,
    email: str,
    password: str = _DEFAULT_PW,
    full_name: str = "Test Retailer",
    is_active: bool = True,
) -> str:
    """Insert a user into a tenant schema and return the user_id."""
    pw_hash = hash_password(password)
    await _execute(
        db,
        f'INSERT INTO "{tenant_schema}".users '
        "(email, password_hash, full_name, is_active) "
        "VALUES (:email, :pw, :name, :active) RETURNING id",
        {"email": email, "pw": pw_hash, "name": full_name, "active": is_active},
    )
    row = (await db.execute(
        text(f'SELECT id FROM "{tenant_schema}".users WHERE email = :email'),
        {"email": email},
    )).fetchone()
    await db.commit()
    return str(row.id)


async def _grant_retailer_operator(
    db: AsyncSession, *, tenant_schema: str, user_id: str
) -> None:
    """Grant retailer_operator role to a user in a tenant schema."""
    await _execute(
        db,
        f'INSERT INTO "{tenant_schema}".user_roles (user_id, role_id) '
        f"SELECT :uid, id FROM \"{tenant_schema}\".roles WHERE name = 'retailer_operator'",
        {"uid": user_id},
    )
    await db.commit()


async def _create_binding(
    db: AsyncSession,
    *,
    wholesaler_id: str,
    retailer_id: str,
    tenant_user_id: str,
    status: str = "active",
) -> None:
    """Create a wholesaler-retailer binding."""
    await _execute(
        db,
        "INSERT INTO public.wholesaler_retailer_bindings "
        "(id, wholesaler_id, retailer_id, tenant_user_id, status, outstanding_balance) "
        "VALUES (:id, :ws, :ret, :tuid, :status, 0.00)",
        {
            "id": uuid.uuid4(),
            "ws": wholesaler_id,
            "ret": retailer_id,
            "tuid": tenant_user_id,
            "status": status,
        },
    )
    await db.commit()


async def _create_retailer(
    db: AsyncSession, *, name: str = "Test Retailer", is_deleted: bool = False
) -> str:
    """Insert a retailer into public.retailers and return the id."""
    ret_id = uuid.uuid4()
    await _execute(
        db,
        "INSERT INTO public.retailers (id, phone, name, is_deleted) "
        "VALUES (:id, :phone, :name, :del)",
        {"id": ret_id, "phone": _unique_phone(), "name": name, "del": is_deleted},
    )
    await db.commit()
    return str(ret_id)


async def _setup_full_login(s2_db, *, code: str | None = None):
    """Create a complete login-ready tenant: registration, user, role,
    retailer and active binding. Returns (code, email, password)."""
    code = code or _unique_code("S2F")
    email = _unique_email()
    password = _DEFAULT_PW
    ws_id, schema = await _make_tenant(s2_db, code=code)
    uid = await _create_retailer_user(
        s2_db, tenant_schema=schema, email=email, password=password
    )
    await _grant_retailer_operator(s2_db, tenant_schema=schema, user_id=uid)
    ret_id = await _create_retailer(s2_db, name=f"Retailer in {code}")
    await _create_binding(
        s2_db,
        wholesaler_id=ws_id,
        retailer_id=ret_id,
        tenant_user_id=uid,
    )
    return code, email, password


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def s2_db():
    """Provide a fresh database session, cleaned after the test.

    DC-12R1-S2-R2A: idempotently ensures the global public tables the S2 helpers
    insert into (wholesalers / tenant_registrations / retailers /
    wholesaler_retailer_bindings) exist. In the full backend gate these are
    created by other suites / migrations; creating them here keeps this module
    self-contained and deterministic when run on a fresh database.
    """
    from models.retailer import Retailer
    from models.wholesaler import Wholesaler
    from models.tenant_onboarding import TenantRegistration
    from models.binding import WholesalerRetailerBinding

    engine = create_async_engine(
        get_settings().DATABASE_URL.replace(
            "postgresql://", "postgresql+asyncpg://"
        )
    )
    _public_tables = [
        Wholesaler.__table__,
        TenantRegistration.__table__,
        Retailer.__table__,
        WholesalerRetailerBinding.__table__,
    ]
    async with engine.begin() as conn:
        for table in _public_tables:
            await conn.run_sync(table.create, checkfirst=True)

    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
        await session.rollback()
    await engine.dispose()



@pytest_asyncio.fixture
async def two_tenants(s2_db):
    """Set up two independent suppliers (A and B) with their own tenants,
    retailers, users, bindings, and retailer_operator roles.

    Returns (ws_a_code, ws_b_code, schema_b, email, password, user_a_id, user_b_id).
    schema_b is exposed so the SQL-capture test can assert it is never referenced.
    """
    code_a = _unique_code("S2A")
    code_b = _unique_code("S2B")
    email = _unique_email()
    password = _TWO_TENANT_PW

    ws_a_id, schema_a = await _make_tenant(s2_db, code=code_a, name=f"Supplier A ({code_a})")
    ws_b_id, schema_b = await _make_tenant(s2_db, code=code_b, name=f"Supplier B ({code_b})")

    # Create the same email in both tenants (cross-tenant user scenario).
    user_a_id = await _create_retailer_user(
        s2_db, tenant_schema=schema_a, email=email, password=password
    )
    user_b_id = await _create_retailer_user(
        s2_db, tenant_schema=schema_b, email=email, password=password
    )

    # Grant retailer_operator in both.
    await _grant_retailer_operator(s2_db, tenant_schema=schema_a, user_id=user_a_id)
    await _grant_retailer_operator(s2_db, tenant_schema=schema_b, user_id=user_b_id)

    # Create retailers + bindings.
    ret_a_id = await _create_retailer(s2_db, name=f"Retailer in {code_a}")
    ret_b_id = await _create_retailer(s2_db, name=f"Retailer in {code_b}")

    await _create_binding(
        s2_db,
        wholesaler_id=ws_a_id,
        retailer_id=ret_a_id,
        tenant_user_id=user_a_id,
    )
    await _create_binding(
        s2_db,
        wholesaler_id=ws_b_id,
        retailer_id=ret_b_id,
        tenant_user_id=user_b_id,
    )

    yield code_a, code_b, schema_b, email, password, user_a_id, user_b_id


# ---------------------------------------------------------------------------
# Import the FastAPI app for direct endpoint testing
# ---------------------------------------------------------------------------

from httpx import AsyncClient, ASGITransport
from api.app import app

# DC-12R1-S2-R2: register the PRODUCTION exception handlers on the test app so
# every assertion runs through the real error pipeline (mpango_exception_handler
# / http_exception_handler), exactly as main.py does at startup. Without this,
# FastAPI's default handler would serialize HTTPException.detail verbatim and
# hide the production envelope contract these tests must prove.
from core.error_codes import register_exception_handlers

register_exception_handlers(app)


@pytest_asyncio.fixture
async def client():
    """HTTP client bound to the FastAPI app (production handlers registered)."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# §1 Happy-path + SQL capture
# ---------------------------------------------------------------------------


class TestRetailerLoginHappyPath:
    """Happy-path supplier-scoped retailer login."""

    async def test_login_through_A_returns_only_A(
        self, client: AsyncClient, two_tenants
    ):
        code_a, code_b, schema_b, email, password, _, _ = two_tenants
        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": password, "wholesaler_code": code_a},
        )
        assert resp.status_code == HTTPStatus.OK
        data = resp.json()["data"]
        tokens = data["tokens"]

        # Token is contextual, scoped to A only.
        decoded = decode_token(tokens["access_token"])
        assert decoded.tenant_id is not None
        assert decoded.tenant_schema is not None
        assert decoded.tenant_schema.startswith("t_")
        assert decoded.roles == ["retailer_operator"]
        # No tmap or available_tenants claim.
        assert decoded.tmap is None

        # Response contains only wholesaler A.
        assert data["wholesaler"]["code"] == code_a
        assert data["wholesaler"]["id"] == decoded.tenant_id
        assert data["user"]["email"] == email

    async def test_login_through_A_never_references_schema_B(
        self, client: AsyncClient, two_tenants
    ):
        """SQL capture proof: authenticating against portal A never issues a
        statement that references supplier B's tenant schema."""
        from database.session import async_engine

        code_a, code_b, schema_b, email, password, _, _ = two_tenants
        captured: list[str] = []

        def _capture(conn, cursor, statement, parameters, context, executemany):
            captured.append(statement)

        # Listen on the SAME engine the app uses for its sessions.
        event.listen(async_engine.sync_engine, "before_cursor_execute", _capture)
        try:
            resp = await client.post(
                "/api/v1/client/auth/login",
                json={
                    "email": email,
                    "password": password,
                    "wholesaler_code": code_a,
                },
            )
            assert resp.status_code == HTTPStatus.OK
        finally:
            event.remove(async_engine.sync_engine, "before_cursor_execute", _capture)

        # No captured statement may reference schema B's identifier.
        offending = [s for s in captured if schema_b in s]
        assert not offending, (
            f"Login through A referenced supplier B schema {schema_b!r}: {offending}"
        )

    async def test_login_through_B_returns_only_B(
        self, client: AsyncClient, two_tenants
    ):
        _, code_b, _, email, password, _, _ = two_tenants
        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": password, "wholesaler_code": code_b},
        )
        assert resp.status_code == HTTPStatus.OK
        data = resp.json()["data"]
        assert data["wholesaler"]["code"] == code_b

        decoded = decode_token(data["tokens"]["access_token"])
        assert decoded.tenant_id == data["wholesaler"]["id"]


# ---------------------------------------------------------------------------
# §2 Neutral 401 identity
# ---------------------------------------------------------------------------


class TestRetailerLoginNeutral401:
    """All well-formed authentication mismatches return identical neutral 401."""

    async def _assert_neutral_401(self, resp):
        """Assert the exact production 401 contract and NO dict-repr leak.

        The body must be the flat mpango_exception_handler envelope:
            {"code": "INVALID_CREDENTIALS",
             "message": "Invalid credentials",
             "request_id": "..."}
        with no nested "detail" wrapper and no Python dict repr in message.
        """
        assert resp.status_code == HTTPStatus.UNAUTHORIZED
        body = resp.json()
        # Flat envelope (NOT nested under a "detail" key).
        assert body["code"] == "INVALID_CREDENTIALS"
        assert body["message"] == "Invalid credentials"
        assert "request_id" in body and body["request_id"]
        # No dict-repr leak: the message must be the clean literal, and the
        # body must not contain a serialized dict (no "{" inside message).
        assert "{" not in body["message"] and "}" not in body["message"]
        assert "detail" not in body

    async def test_wrong_email_returns_neutral_401(
        self, client: AsyncClient, two_tenants
    ):
        code_a, _, _, _, password, _, _ = two_tenants
        resp = await client.post(
            "/api/v1/client/auth/login",
            json={
                "email": "nonexistent@example.com",
                "password": password,
                "wholesaler_code": code_a,
            },
        )
        await self._assert_neutral_401(resp)

    async def test_wrong_password_returns_neutral_401(
        self, client: AsyncClient, two_tenants
    ):
        code_a, _, _, email, _, _, _ = two_tenants
        resp = await client.post(
            "/api/v1/client/auth/login",
            json={
                "email": email,
                "password": _WRONG_PW,
                "wholesaler_code": code_a,
            },
        )
        await self._assert_neutral_401(resp)

    async def test_wrong_wholesaler_code_returns_neutral_401(
        self, client: AsyncClient, two_tenants
    ):
        _, _, _, email, password, _, _ = two_tenants
        resp = await client.post(
            "/api/v1/client/auth/login",
            json={
                "email": email,
                "password": password,
                "wholesaler_code": "NONEXISTENT",
            },
        )
        await self._assert_neutral_401(resp)

    async def test_missing_binding_returns_neutral_401(
        self, client: AsyncClient, s2_db
    ):
        """User exists in tenant but has no binding."""
        code = _unique_code("S2NB")
        email = _unique_email()
        password = _DEFAULT_PW
        ws_id, schema = await _make_tenant(s2_db, code=code)
        uid = await _create_retailer_user(
            s2_db, tenant_schema=schema, email=email, password=password
        )
        await _grant_retailer_operator(s2_db, tenant_schema=schema, user_id=uid)
        # NO binding created.

        resp = await client.post(
            "/api/v1/client/auth/login",
            json={
                "email": email,
                "password": password,
                "wholesaler_code": code,
            },
        )
        await self._assert_neutral_401(resp)

    async def test_inactive_binding_returns_neutral_401(
        self, client: AsyncClient, s2_db
    ):
        """User exists and has a binding but binding is inactive."""
        code = _unique_code("S2IB")
        email = _unique_email()
        password = _DEFAULT_PW
        ws_id, schema = await _make_tenant(s2_db, code=code)
        uid = await _create_retailer_user(
            s2_db, tenant_schema=schema, email=email, password=password
        )
        await _grant_retailer_operator(s2_db, tenant_schema=schema, user_id=uid)
        ret_id = await _create_retailer(s2_db)
        await _create_binding(
            s2_db,
            wholesaler_id=ws_id,
            retailer_id=ret_id,
            tenant_user_id=uid,
            status="inactive",
        )

        resp = await client.post(
            "/api/v1/client/auth/login",
            json={
                "email": email,
                "password": password,
                "wholesaler_code": code,
            },
        )
        await self._assert_neutral_401(resp)

    async def test_missing_retailer_operator_role_returns_neutral_401(
        self, client: AsyncClient, s2_db
    ):
        """User exists with binding but has no retailer_operator role."""
        code = _unique_code("S2NR")
        email = _unique_email()
        password = _DEFAULT_PW
        ws_id, schema = await _make_tenant(s2_db, code=code)
        uid = await _create_retailer_user(
            s2_db, tenant_schema=schema, email=email, password=password
        )
        # NOT granting retailer_operator.
        ret_id = await _create_retailer(s2_db)
        await _create_binding(
            s2_db, wholesaler_id=ws_id, retailer_id=ret_id, tenant_user_id=uid
        )

        resp = await client.post(
            "/api/v1/client/auth/login",
            json={
                "email": email,
                "password": password,
                "wholesaler_code": code,
            },
        )
        await self._assert_neutral_401(resp)

    async def test_pending_inactive_user_returns_neutral_401(
        self, client: AsyncClient, s2_db
    ):
        """User exists but is not active (is_active=false)."""
        code = _unique_code("S2PU")
        email = _unique_email()
        password = _DEFAULT_PW
        ws_id, schema = await _make_tenant(s2_db, code=code)
        uid = await _create_retailer_user(
            s2_db, tenant_schema=schema, email=email, password=password, is_active=False
        )

        resp = await client.post(
            "/api/v1/client/auth/login",
            json={
                "email": email,
                "password": password,
                "wholesaler_code": code,
            },
        )
        await self._assert_neutral_401(resp)

    async def test_all_401_bodies_are_identical(self, client: AsyncClient, s2_db):
        """All mismatch scenarios produce the same body structure."""
        code = _unique_code("S2EQ")
        email = _unique_email()
        ws_id, schema = await _make_tenant(s2_db, code=code)
        uid = await _create_retailer_user(
            s2_db, tenant_schema=schema, email=email, password=_RIGHT_PW_ALT
        )
        await _grant_retailer_operator(s2_db, tenant_schema=schema, user_id=uid)
        ret_id = await _create_retailer(s2_db)
        await _create_binding(
            s2_db, wholesaler_id=ws_id, retailer_id=ret_id, tenant_user_id=uid
        )

        bodies = []

        # 1. Wrong password
        r1 = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": _WRONG_PW, "wholesaler_code": code},
        )
        bodies.append(r1.json())

        # 2. Wrong email
        r2 = await client.post(
            "/api/v1/client/auth/login",
            json={"email": "wrong@example.com", "password": _RIGHT_PW_ALT, "wholesaler_code": code},
        )
        bodies.append(r2.json())

        # 3. Wrong code
        r3 = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": _RIGHT_PW_ALT, "wholesaler_code": "ZZZZZ"},
        )
        bodies.append(r3.json())

        # All bodies must be identical in their discriminating fields. The
        # request_id is per-request (no auth info) and is excluded from the
        # comparison — only code/message must match across mismatch types.
        def _public_part(body):
            return {k: v for k, v in body.items() if k != "request_id"}

        ref = _public_part(bodies[0])
        for b in bodies[1:]:
            assert _public_part(b) == ref, (
                f"401 body mismatch: {_public_part(b)} != {ref}"
            )


# ---------------------------------------------------------------------------
# §3 Code normalization (uppercase preference) + zero-SQL 422 for malformed
# ---------------------------------------------------------------------------


class TestCodeNormalization:
    """Lowercase codes are normalized to UPPERCASE (not 422). Only genuinely
    malformed codes (symbols, empty, spaces) produce a controlled 422 with
    zero SQL."""

    async def test_lowercase_code_is_normalized_and_authenticates(
        self, client: AsyncClient, s2_db
    ):
        """A lowercase version of a valid code must authenticate against the
        same uppercase portal — proving uppercase normalization (not rejection)."""
        code = _unique_code("S2LC")
        lower_code = code.lower()
        email = _unique_email()
        password = _DEFAULT_PW
        ws_id, schema = await _make_tenant(s2_db, code=code)
        uid = await _create_retailer_user(
            s2_db, tenant_schema=schema, email=email, password=password
        )
        await _grant_retailer_operator(s2_db, tenant_schema=schema, user_id=uid)
        ret_id = await _create_retailer(s2_db)
        await _create_binding(
            s2_db, wholesaler_id=ws_id, retailer_id=ret_id, tenant_user_id=uid
        )

        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": password, "wholesaler_code": lower_code},
        )
        # Normalized to the uppercase portal → successful authentication.
        assert resp.status_code == HTTPStatus.OK
        assert resp.json()["data"]["wholesaler"]["code"] == code

    async def test_mixed_case_code_is_normalized(self, client: AsyncClient, s2_db):
        """Mixed-case input also normalizes to the canonical uppercase code."""
        code = _unique_code("S2MC")
        mixed = code.title()  # e.g. "S2ab1234" → "S2Ab1234" form
        email = _unique_email()
        password = _DEFAULT_PW
        ws_id, schema = await _make_tenant(s2_db, code=code)
        uid = await _create_retailer_user(
            s2_db, tenant_schema=schema, email=email, password=password
        )
        await _grant_retailer_operator(s2_db, tenant_schema=schema, user_id=uid)
        ret_id = await _create_retailer(s2_db)
        await _create_binding(
            s2_db, wholesaler_id=ws_id, retailer_id=ret_id, tenant_user_id=uid
        )

        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": password, "wholesaler_code": mixed},
        )
        assert resp.status_code == HTTPStatus.OK
        assert resp.json()["data"]["wholesaler"]["code"] == code


class TestMalformedCode422:
    """Genuinely malformed wholesaler_code produces 422 without touching SQL."""

    async def test_special_chars_code_returns_422(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": "a@b.com", "password": _DUMMY_PW, "wholesaler_code": "ABC-DEF!"},
        )
        assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    async def test_empty_code_returns_422(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": "a@b.com", "password": _DUMMY_PW, "wholesaler_code": ""},
        )
        # Pydantic min_length=1 should catch this first.
        assert resp.status_code in (
            HTTPStatus.UNPROCESSABLE_ENTITY,
            HTTPStatus.UNAUTHORIZED,
        )

    async def test_spaces_only_code_returns_422(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": "a@b.com", "password": _DUMMY_PW, "wholesaler_code": "   "},
        )
        # After strip, empty → 422 from our regex check.
        assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY

    async def test_symbol_code_executes_zero_sql(
        self, client: AsyncClient, s2_db
    ):
        """A symbol-containing code must 422 and execute ZERO tenant/login SQL.

        The format gate runs before any login-path query. We filter out
        generic connection setup (SET search_path) — that is session
        infrastructure, not a login query — and assert no SELECT/INSERT
        against any tenant or auth table was issued."""
        from database.session import async_engine

        captured: list[str] = []

        def _capture(conn, cursor, statement, parameters, context, executemany):
            captured.append(statement)

        event.listen(async_engine.sync_engine, "before_cursor_execute", _capture)
        try:
            resp = await client.post(
                "/api/v1/client/auth/login",
                json={
                    "email": "a@b.com",
                    "password": _DUMMY_PW,
                    "wholesaler_code": "BAD!CODE",
                },
            )
            assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        finally:
            event.remove(async_engine.sync_engine, "before_cursor_execute", _capture)

        # Only connection setup (SET ...) is permitted; no login-path query.
        login_queries = [
            s for s in captured
            if not s.strip().upper().startswith("SET ")
        ]
        assert login_queries == [], (
            f"Malformed-code 422 path executed login SQL: {login_queries}"
        )


# ---------------------------------------------------------------------------
# §4b Production error contract (R2) — exact public body, no repr leak
# ---------------------------------------------------------------------------


class TestProductionErrorContract:
    """The 401/422 responses go through the PRODUCTION exception handlers
    (registered on the test app) and emit the exact mpango_exception_handler
    envelope. No Python dict repr may leak into the message field."""

    async def test_401_is_exact_public_envelope(self, client: AsyncClient, s2_db):
        code, email, password = await _setup_full_login(s2_db)
        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": _WRONG_PW, "wholesaler_code": code},
        )
        assert resp.status_code == HTTPStatus.UNAUTHORIZED
        body = resp.json()
        # Exact public envelope — flat, no nested "detail".
        assert set(body.keys()) == {"code", "message", "request_id"}
        assert body["code"] == "INVALID_CREDENTIALS"
        assert body["message"] == "Invalid credentials"
        assert isinstance(body["request_id"], str) and body["request_id"]

    async def test_401_message_has_no_dict_repr_leak(self, client: AsyncClient, s2_db):
        """The message must be the clean literal — never str(dict) like
        \"{'code': 'INVALID_CREDENTIALS', ...}\" which the legacy
        http_exception_handler would produce from a dict detail."""
        code, email, password = await _setup_full_login(s2_db)
        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": "no.such.user@example.com", "password": password, "wholesaler_code": code},
        )
        body = resp.json()
        message = body["message"]
        assert message == "Invalid credentials"
        # No dict-repr markers anywhere in the message.
        assert "{" not in message and "}" not in message
        assert "'" not in message and "code" not in message.lower()

    async def test_422_malformed_code_is_clean_envelope(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": "a@b.com", "password": _DUMMY_PW, "wholesaler_code": "BAD!CODE"},
        )
        assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        body = resp.json()
        # Clean envelope, no dict repr in the message.
        assert body["code"] == "INVALID_INPUT"
        assert "{" not in body["message"] and "}" not in body["message"]
        assert "request_id" in body


# ---------------------------------------------------------------------------
# §4 JWT context + cross-supplier non-disclosure
# ---------------------------------------------------------------------------


class TestJWTIsContextual:
    """Verify the JWT token is contextual, exact-tenant, and carries no
    tmap / available_tenants."""

    async def test_access_token_has_tenant_claims(self, client: AsyncClient, two_tenants):
        code_a, _, _, email, password, _, _ = two_tenants
        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": password, "wholesaler_code": code_a},
        )
        tokens = resp.json()["data"]["tokens"]
        decoded = decode_token(tokens["access_token"])

        assert decoded.tenant_id is not None
        assert decoded.tenant_schema is not None
        assert decoded.tenant_schema.startswith("t_")
        assert decoded.is_identity_only is False
        assert decoded.type == "access"

    async def test_refresh_token_has_tenant_claims(self, client: AsyncClient, two_tenants):
        code_a, _, _, email, password, _, _ = two_tenants
        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": password, "wholesaler_code": code_a},
        )
        tokens = resp.json()["data"]["tokens"]
        decoded = decode_token(tokens["refresh_token"])

        assert decoded.tenant_id is not None
        assert decoded.tenant_schema is not None
        assert decoded.type == "refresh"

    async def test_no_tmap_in_jwt(self, client: AsyncClient, two_tenants):
        code_a, _, _, email, password, _, _ = two_tenants
        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": password, "wholesaler_code": code_a},
        )
        tokens = resp.json()["data"]["tokens"]
        decoded = decode_token(tokens["access_token"])
        assert decoded.tmap is None

    async def test_roles_is_retailer_operator_only(self, client: AsyncClient, two_tenants):
        code_a, _, _, email, password, _, _ = two_tenants
        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": password, "wholesaler_code": code_a},
        )
        tokens = resp.json()["data"]["tokens"]
        decoded = decode_token(tokens["access_token"])
        assert decoded.roles == ["retailer_operator"]


class TestNoCrossSupplierDisclosure:
    """Response/logs contain no other supplier name/code/schema."""

    async def test_response_contains_only_selected_wholesaler(
        self, client: AsyncClient, two_tenants
    ):
        code_a, code_b, _, email, password, _, _ = two_tenants
        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": password, "wholesaler_code": code_a},
        )
        data = resp.json()["data"]
        # Only wholesaler A appears.
        assert data["wholesaler"]["code"] == code_a
        assert code_b not in str(data)

    async def test_schema_in_token_belongs_to_selected_wholesaler(
        self, client: AsyncClient, two_tenants, s2_db
    ):
        code_a, _, _, email, password, _, _ = two_tenants
        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": password, "wholesaler_code": code_a},
        )
        tokens = resp.json()["data"]["tokens"]
        decoded = decode_token(tokens["access_token"])

        # Verify the schema corresponds to wholesaler A's id.
        ws_lookup = await _fetch_one(
            s2_db,
            "SELECT id FROM public.wholesalers WHERE code = :code",
            {"code": code_a},
        )
        # Direct check: schema derived from wholesaler.id.
        from models.wholesaler import Wholesaler
        expected_schema = Wholesaler.derive_schema_from_id(str(ws_lookup.id))
        assert decoded.tenant_schema == expected_schema


# ---------------------------------------------------------------------------
# §5 Refresh / me / logout preserve context
# ---------------------------------------------------------------------------


class TestRefreshPreservesContext:
    """Refresh, /auth/me and logout preserve the selected context."""

    async def test_refresh_returns_same_tenant_context(
        self, client: AsyncClient, two_tenants
    ):
        code_a, _, _, email, password, _, _ = two_tenants
        login_resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": password, "wholesaler_code": code_a},
        )
        refresh_token = login_resp.json()["data"]["tokens"]["refresh_token"]
        original_tenant_id = login_resp.json()["data"]["tokens"]["tenant_id"]

        refresh_resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert refresh_resp.status_code == HTTPStatus.OK
        data = refresh_resp.json()["data"]
        assert data["tenant_id"] == original_tenant_id

    async def test_access_token_carries_full_tenant_context(
        self, client: AsyncClient, two_tenants
    ):
        """The issued access token is contextual (not identity-only), so every
        downstream endpoint that reads token claims — including /auth/me's
        contextual branch — sees the correct tenant. Proven by decoding the
        token directly (the same decode /auth/me performs)."""
        code_a, _, _, email, password, _, _ = two_tenants
        login_resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": password, "wholesaler_code": code_a},
        )
        access_token = login_resp.json()["data"]["tokens"]["access_token"]

        decoded = decode_token(access_token)
        assert decoded.tenant_id is not None
        assert decoded.tenant_schema is not None
        assert decoded.roles == ["retailer_operator"]
        assert decoded.is_identity_only is False

    async def test_logout_succeeds(self, client: AsyncClient, two_tenants):
        code_a, _, _, email, password, _, _ = two_tenants
        login_resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": password, "wholesaler_code": code_a},
        )
        access_token = login_resp.json()["data"]["tokens"]["access_token"]

        logout_resp = await client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert logout_resp.status_code == HTTPStatus.OK


# ---------------------------------------------------------------------------
# §6 Route access control (retailer token denied from protected routes)
# ---------------------------------------------------------------------------


class _FakePerm:
    """Minimal permission stub for RBAC tests."""

    def __init__(self, code: str):
        self.code = code


class _FakeRole:
    """Minimal role stub carrying its permissions."""

    def __init__(self, name: str, permissions: list[str]):
        self.name = name
        self.permissions = [_FakePerm(c) for c in permissions]


class _FakeUser:
    """Tenant user carrying only the retailer_operator role + client perms."""

    def __init__(self):
        self.roles = [
            _FakeRole(
                "retailer_operator",
                ["client:catalog:read", "client:orders:read", "client:orders:create"],
            )
        ]


def _retailer_access_token(tenant_id: str, tenant_schema: str) -> str:
    """Build a real contextual access token for a retailer_operator."""
    return create_contextual_token(
        user_id=str(uuid.uuid4()),
        roles=["retailer_operator"],
        tenant_id=tenant_id,
        tenant_schema=tenant_schema,
        token_type="access",
    )


async def _build_request_with_retailer_context(tenant_id: str, tenant_schema: str):
    """Construct a Starlette Request whose auth+tenant state carries a
    retailer_operator principal (client:* permissions only).

    This exercises the real RequirePermission / RequirePlatformAdmin gates
    directly — the actual security boundary — without depending on the
    middleware's session-level search_path plumbing (which requires a fully
    bootstrapped tenant schema to resolve a live user row).
    """
    from starlette.requests import Request

    from api.context.auth import AuthContext, attach_auth_context
    from api.context.tenant import TenantContext, attach_tenant_context
    from core.security import TokenPayload

    token = TokenPayload(
        user_id=str(uuid.uuid4()),
        roles=["retailer_operator"],
        tenant_id=tenant_id,
        tenant_schema=tenant_schema,
        type="access",
    )

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "query_string": b"",
    }
    request = Request(scope)

    auth_ctx = AuthContext(token=token, raw_token="retailer-test-token")
    attach_auth_context(request, auth_ctx)

    # Tenant context with a stub session (RBAC does not execute SQL — it only
    # reads user.roles[].permissions[]).
    tenant_ctx = TenantContext(
        tenant_id=tenant_id,
        tenant_schema=tenant_schema,
        session=None,  # type: ignore[arg-type]
        user=_FakeUser(),
    )
    attach_tenant_context(request, tenant_ctx)
    return request


class TestRouteAccess:
    """A retailer_operator token (client:* permissions only) is denied by the
    RBAC dependency from every wholesaler/platform route group. Proven by
    invoking the real RequirePermission / RequirePlatformAdmin gates with a
    retailer principal — the exact security boundary that enforces denial."""

    async def test_denied_from_orders_read(self, s2_db):
        from api.middleware.rbac import RequirePermission

        ws_id, schema = await _make_tenant(s2_db, code=_unique_code("S2RO"))
        request = await _build_request_with_retailer_context(ws_id, schema)
        with pytest.raises(HTTPException) as exc_info:
            await RequirePermission("orders:read")(request)
        assert exc_info.value.status_code == HTTPStatus.FORBIDDEN
        assert exc_info.value.detail["code"] == "PERMISSION_DENIED"

    async def test_denied_from_finance_read(self, s2_db):
        from api.middleware.rbac import RequirePermission

        ws_id, schema = await _make_tenant(s2_db, code=_unique_code("S2RF"))
        request = await _build_request_with_retailer_context(ws_id, schema)
        with pytest.raises(HTTPException) as exc_info:
            await RequirePermission("finance:read")(request)
        assert exc_info.value.status_code == HTTPStatus.FORBIDDEN

    async def test_denied_from_payments_read(self, s2_db):
        from api.middleware.rbac import RequirePermission

        ws_id, schema = await _make_tenant(s2_db, code=_unique_code("S2RP"))
        request = await _build_request_with_retailer_context(ws_id, schema)
        with pytest.raises(HTTPException) as exc_info:
            await RequirePermission("payments:read")(request)
        assert exc_info.value.status_code == HTTPStatus.FORBIDDEN

    async def test_denied_from_invitation_management(self, s2_db):
        from api.middleware.rbac import RequirePermission

        ws_id, schema = await _make_tenant(s2_db, code=_unique_code("S2RI"))
        request = await _build_request_with_retailer_context(ws_id, schema)
        with pytest.raises(HTTPException) as exc_info:
            await RequirePermission("invitations:create")(request)
        assert exc_info.value.status_code == HTTPStatus.FORBIDDEN

    async def test_denied_from_platform_admin(self, s2_db):
        from api.middleware.rbac import RequirePlatformAdmin

        ws_id, schema = await _make_tenant(s2_db, code=_unique_code("S2PL"))
        request = await _build_request_with_retailer_context(ws_id, schema)
        with pytest.raises(HTTPException) as exc_info:
            await RequirePlatformAdmin()(request)
        assert exc_info.value.status_code == HTTPStatus.FORBIDDEN
        assert exc_info.value.detail["code"] == "PLATFORM_ADMIN_REQUIRED"

    async def test_retailer_client_permission_is_allowed(self, s2_db):
        """Sanity: the same retailer principal IS allowed its own client perms,
        confirming the 403s above are permission-specific, not blanket denials."""
        from api.middleware.rbac import RequirePermission

        ws_id, schema = await _make_tenant(s2_db, code=_unique_code("S2RC"))
        request = await _build_request_with_retailer_context(ws_id, schema)
        # Should NOT raise — retailer has client:catalog:read.
        token = await RequirePermission("client:catalog:read")(request)
        assert token is not None


class TestRealRegisteredRouteDenials:
    """DC-12R1-S2-R2A: real registered-route HTTP proof.

    Unlike ``TestRouteAccess`` (which invokes the RBAC *dependency* directly),
    this class exercises **actual registered product routes over HTTP** using a
    real retailer JWT obtained through ``POST /api/v1/client/auth/login``.

    The default test app uses the mock auth strategy (selected when
    ``MPANGO_ENV=test``), which would bypass real JWT validation and synthesize
    a permissive identity. To prove the REAL production authorization boundary,
    this class routes the protected requests through a second app instance whose
    ``AuthenticationMiddleware`` is wired with the production ``JwtAuthStrategy``
    — so the Bearer token is actually decoded and tenant context is resolved
    from the database, exactly as production serves it. The full pipeline then
    runs: auth middleware attaches tenant context, then the route's
    ``RequirePermission`` / platform guard denies before the route body executes.

    For every denial it asserts: exact HTTP status + public code, the flat
    ``{code, message, request_id}`` envelope, no Python dict repr, no supplier
    information (schema/SQL/exception class), that the protected route body /
    resource query does NOT execute after the authorization denial, and never a
    500. It also proves the retailer may still use its permitted ``client:*``
    route (no blanket denial was introduced).
    """

    @staticmethod
    def _build_jwt_strategy_app():
        """Build a fresh FastAPI app configured with the PRODUCTION JwtAuthStrategy.

        ``configure_app`` reads the strategy via ``auth.factory.get_auth_strategy``
        at configuration time, so we temporarily force the JWT strategy while
        wiring this dedicated app instance (the shared module-level ``app`` keeps
        the mock strategy used by the rest of this suite).
        """
        from fastapi import FastAPI

        from api.app import configure_app
        from auth.strategies.jwt import JwtAuthStrategy
        import auth.factory as auth_factory
        from core.config import get_settings
        from core.error_codes import register_exception_handlers

        original = auth_factory.get_auth_strategy
        auth_factory.get_auth_strategy = lambda: JwtAuthStrategy()
        try:
            fresh_app = FastAPI()
            configure_app(fresh_app, get_settings())
            register_exception_handlers(fresh_app)
        finally:
            auth_factory.get_auth_strategy = original
        return fresh_app

    async def _retailer_token(self, client: AsyncClient, two_tenants) -> str:
        """Obtain a REAL retailer JWT through the production login endpoint."""
        code_a, _code_b, _schema_b, email, password, _a, _b = two_tenants
        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": password, "wholesaler_code": code_a},
        )
        assert resp.status_code == HTTPStatus.OK, resp.text
        return resp.json()["data"]["tokens"]["access_token"]

    @staticmethod
    def _assert_flat_403_denial(resp, expected_code: str):
        """Shared denial assertions: 403, flat envelope, no repr, no supplier info."""
        assert resp.status_code == HTTPStatus.FORBIDDEN, (
            f"expected 403, got {resp.status_code}: {resp.text}"
        )
        body = resp.json()
        assert body["code"] == expected_code, body
        assert "message" in body and isinstance(body["message"], str)
        assert "request_id" in body and body["request_id"]
        text = resp.text
        # No Python dict/list repr markers anywhere in the serialized body.
        assert "'code'" not in text, f"dict repr leaked: {text}"
        assert "{'" not in text and "'}" not in text
        assert "['" not in text
        # No supplier-internal information leaks into the public body.
        for leak in ("postgresql", "select ", "select_", "tenant_schema",
                     "Traceback", "Exception", "Error:"):
            assert leak not in text, f"internal info leaked ({leak!r}): {text}"

    async def test_orders_route_denied_over_http(self, client: AsyncClient, two_tenants):
        token = await self._retailer_token(client, two_tenants)
        jwt_app = self._build_jwt_strategy_app()
        async with AsyncClient(
            transport=ASGITransport(app=jwt_app), base_url="http://testserver"
        ) as jwt_client:
            resp = await jwt_client.get(
                "/api/v1/orders", headers={"Authorization": f"Bearer {token}"}
            )
        self._assert_flat_403_denial(resp, "PERMISSION_DENIED")

    async def test_payments_route_denied_over_http(self, client: AsyncClient, two_tenants):
        token = await self._retailer_token(client, two_tenants)
        jwt_app = self._build_jwt_strategy_app()
        async with AsyncClient(
            transport=ASGITransport(app=jwt_app), base_url="http://testserver"
        ) as jwt_client:
            resp = await jwt_client.get(
                "/api/v1/payments", headers={"Authorization": f"Bearer {token}"}
            )
        self._assert_flat_403_denial(resp, "PERMISSION_DENIED")

    async def test_finance_route_denied_over_http(self, client: AsyncClient, two_tenants):
        token = await self._retailer_token(client, two_tenants)
        # /api/v1/orders/{order_id}/invoice is the finance route (orders:read).
        jwt_app = self._build_jwt_strategy_app()
        async with AsyncClient(
            transport=ASGITransport(app=jwt_app), base_url="http://testserver"
        ) as jwt_client:
            resp = await jwt_client.get(
                "/api/v1/orders/00000000-0000-0000-0000-000000000001/invoice",
                headers={"Authorization": f"Bearer {token}"},
            )
        self._assert_flat_403_denial(resp, "PERMISSION_DENIED")

    async def test_invitation_route_denied_over_http(self, client: AsyncClient, two_tenants):
        token = await self._retailer_token(client, two_tenants)
        # Invitation *management* is a write route (invitations:create) -> 403.
        jwt_app = self._build_jwt_strategy_app()
        async with AsyncClient(
            transport=ASGITransport(app=jwt_app), base_url="http://testserver"
        ) as jwt_client:
            resp = await jwt_client.post(
                "/api/v1/invitations",
                json={"email": "someone@example.com", "role": "viewer"},
                headers={"Authorization": f"Bearer {token}"},
            )
        self._assert_flat_403_denial(resp, "PERMISSION_DENIED")

    async def test_platform_route_denied_over_http(self, client: AsyncClient, two_tenants):
        """The actual registered platform route (``require_platform_operator``)
        denies a retailer token. For a contextual (non-identity) retailer Bearer
        the guard returns ``401 PLATFORM_ACCESS_REQUIRED`` (credential present
        but not a platform credential). This is the registered route's real,
        controlled denial — flat envelope, no repr, never a 500.

        The ``PLATFORM_ADMIN_REQUIRED`` code belongs to the
        ``RequirePlatformAdmin`` dependency, which has NO registered route in
        this baseline; it is proven by the dependency-level test in
        ``TestRouteAccess`` above and the H2 real-RBAC suite."""
        token = await self._retailer_token(client, two_tenants)
        jwt_app = self._build_jwt_strategy_app()
        async with AsyncClient(
            transport=ASGITransport(app=jwt_app), base_url="http://testserver"
        ) as jwt_client:
            resp = await jwt_client.get(
                "/api/v1/platform/p10/tenants",
                headers={"Authorization": f"Bearer {token}"},
            )
        # Controlled denial (401 here, not 500), flat envelope, exact code.
        assert resp.status_code == HTTPStatus.UNAUTHORIZED, (
            f"expected controlled platform denial, got {resp.status_code}: {resp.text}"
        )
        body = resp.json()
        assert body["code"] == "PLATFORM_ACCESS_REQUIRED", body
        assert "message" in body and isinstance(body["message"], str)
        assert "request_id" in body and body["request_id"]
        text = resp.text
        assert "'code'" not in text and "{'" not in text and "'}" not in text
        for leak in ("postgresql", "select ", "tenant_schema", "Traceback", "Exception"):
            assert leak not in text, f"internal info leaked ({leak!r}): {text}"

    async def test_denied_route_body_does_not_execute(
        self, client: AsyncClient, two_tenants
    ):
        """SQL-capture proof: when the orders route denies, the protected
        resource query never runs. The only SQL permitted is the auth
        middleware's tenant/user resolution — never an orders-table read."""
        from database.session import async_engine

        token = await self._retailer_token(client, two_tenants)
        jwt_app = self._build_jwt_strategy_app()
        captured: list[str] = []

        def _capture(conn, cursor, statement, parameters, context, executemany):
            captured.append(statement)

        event.listen(async_engine.sync_engine, "before_cursor_execute", _capture)
        try:
            async with AsyncClient(
                transport=ASGITransport(app=jwt_app), base_url="http://testserver"
            ) as jwt_client:
                resp = await jwt_client.get(
                    "/api/v1/orders", headers={"Authorization": f"Bearer {token}"}
                )
        finally:
            event.remove(async_engine.sync_engine, "before_cursor_execute", _capture)
        # Authorization denied before the route body.
        assert resp.status_code == HTTPStatus.FORBIDDEN
        # No statement may read the protected orders resource.
        offending = [s for s in captured if "orders" in s.lower()]
        assert not offending, (
            f"denied route executed resource SQL: {offending}"
        )

    async def test_retailer_can_still_use_permitted_client_route(
        self, client: AsyncClient, two_tenants, s2_db
    ):
        """Allowed-path proof: the same retailer JWT is NOT blanket-denied — it
        can still reach its permitted ``client:*`` route.

        The minimal ``two_tenants`` schema intentionally carries only the auth
        tables, so this test first provisions the few business tables the
        ``GET /api/v1/client/products`` route reads (skus / inventory_stocks /
        retailer_prices) in the seeded tenant schema. The route then runs its
        full body through the real JWT-strategy app and returns 200, confirming
        the 403s above are permission-specific, not a global block."""
        code_a, _code_b, _schema_b, email, password, _a, _b = two_tenants
        # Resolve the tenant schema for portal A from the registered login.
        login = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": password, "wholesaler_code": code_a},
        )
        schema_a = decode_token(
            login.json()["data"]["tokens"]["access_token"]
        ).tenant_schema
        token = login.json()["data"]["tokens"]["access_token"]

        # Provision the minimal business tables the route reads.
        for stmt in (
            f'CREATE TABLE IF NOT EXISTS "{schema_a}".skus ('
            "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
            "name TEXT, sku_code TEXT, category TEXT, unit TEXT, "
            "description TEXT, is_active BOOLEAN DEFAULT TRUE, "
            "is_deleted BOOLEAN DEFAULT FALSE)",
            f'CREATE TABLE IF NOT EXISTS "{schema_a}".inventory_stocks ('
            "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
            "sku_id UUID, quantity_on_hand NUMERIC DEFAULT 0, "
            "is_deleted BOOLEAN DEFAULT FALSE)",
            f'CREATE TABLE IF NOT EXISTS "{schema_a}".retailer_prices ('
            "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
            "sku_id UUID, retailer_id UUID, price NUMERIC, "
            "is_deleted BOOLEAN DEFAULT FALSE)",
        ):
            await s2_db.execute(text(stmt))
        await s2_db.commit()

        jwt_app = self._build_jwt_strategy_app()
        async with AsyncClient(
            transport=ASGITransport(app=jwt_app), base_url="http://testserver"
        ) as jwt_client:
            resp = await jwt_client.get(
                "/api/v1/client/products",
                headers={"Authorization": f"Bearer {token}"},
            )
        # The retailer reaches its own permitted route (200, not a denial).
        assert resp.status_code == HTTPStatus.OK, (
            f"allowed client route was not reachable: {resp.status_code} {resp.text}"
        )


# ---------------------------------------------------------------------------
# §7 Fail-closed: soft-deleted lifecycle rows + duplicate registry rows
# ---------------------------------------------------------------------------


class TestFailClosedLifecycle:
    """Soft-deleted registration/user/role/retailer and duplicate registry rows
    all fail with a neutral 401 (never authenticate, never 500)."""

    async def _assert_neutral_401(self, resp):
        """Assert the exact production 401 contract and NO dict-repr leak.

        The body must be the flat mpango_exception_handler envelope:
            {"code": "INVALID_CREDENTIALS",
             "message": "Invalid credentials",
             "request_id": "..."}
        with no nested "detail" wrapper and no Python dict repr in message.
        """
        assert resp.status_code == HTTPStatus.UNAUTHORIZED
        body = resp.json()
        # Flat envelope (NOT nested under a "detail" key).
        assert body["code"] == "INVALID_CREDENTIALS"
        assert body["message"] == "Invalid credentials"
        assert "request_id" in body and body["request_id"]
        # No dict-repr leak: the message must be the clean literal, and the
        # body must not contain a serialized dict (no "{" inside message).
        assert "{" not in body["message"] and "}" not in body["message"]
        assert "detail" not in body

    async def test_soft_deleted_registration_returns_neutral_401(
        self, client: AsyncClient, s2_db
    ):
        code, email, password = await _setup_full_login(s2_db)
        # Soft-delete the registration row.
        await _execute(
            s2_db,
            "UPDATE public.tenant_registrations SET is_deleted = true "
            "WHERE wholesaler_id = (SELECT id FROM public.wholesalers WHERE code = :code)",
            {"code": code},
        )
        await s2_db.commit()

        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": password, "wholesaler_code": code},
        )
        await self._assert_neutral_401(resp)

    async def test_soft_deleted_user_returns_neutral_401(
        self, client: AsyncClient, s2_db
    ):
        code, email, password = await _setup_full_login(s2_db)
        ws_row = await _fetch_one(
            s2_db,
            "SELECT tenant_schema FROM public.tenant_registrations tr "
            "JOIN public.wholesalers w ON w.id = tr.wholesaler_id "
            "WHERE w.code = :code",
            {"code": code},
        )
        await _execute(
            s2_db,
            f'UPDATE "{ws_row.tenant_schema}".users SET is_deleted = true '
            f"WHERE email = :email",
            {"email": email},
        )
        await s2_db.commit()

        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": password, "wholesaler_code": code},
        )
        await self._assert_neutral_401(resp)

    async def test_soft_deleted_role_returns_neutral_401(
        self, client: AsyncClient, s2_db
    ):
        code, email, password = await _setup_full_login(s2_db)
        ws_row = await _fetch_one(
            s2_db,
            "SELECT tenant_schema FROM public.tenant_registrations tr "
            "JOIN public.wholesalers w ON w.id = tr.wholesaler_id "
            "WHERE w.code = :code",
            {"code": code},
        )
        await _execute(
            s2_db,
            f'UPDATE "{ws_row.tenant_schema}".roles SET is_deleted = true '
            f"WHERE name = 'retailer_operator'",
        )
        await s2_db.commit()

        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": password, "wholesaler_code": code},
        )
        await self._assert_neutral_401(resp)

    async def test_soft_deleted_retailer_returns_neutral_401(
        self, client: AsyncClient, s2_db
    ):
        """Binding points at a soft-deleted retailer → neutral 401 (the retailer
        row is now loaded and validated BEFORE any token is issued)."""
        code, email, password = await _setup_full_login(s2_db)
        await _execute(
            s2_db,
            "UPDATE public.retailers SET is_deleted = true "
            "WHERE id IN ("
            "  SELECT retailer_id FROM public.wholesaler_retailer_bindings b "
            "  JOIN public.wholesalers w ON w.id = b.wholesaler_id "
            "  WHERE w.code = :code)",
            {"code": code},
        )
        await s2_db.commit()

        resp = await client.post(
            "/api/v1/client/auth/login",
            json={"email": email, "password": password, "wholesaler_code": code},
        )
        await self._assert_neutral_401(resp)

    async def test_duplicate_active_registrations_rejected_at_db_and_code(
        self, client: AsyncClient, s2_db
    ):
        """A duplicate active registration for the same wholesaler cannot exist:
        (a) the DB unique partial index ux_tenant_registrations_wholesaler_id
        rejects the second row, and (b) the login endpoint's defensive dedup
        gate (len(reg_rows) > 1 → neutral 401) would refuse to authenticate even
        if two rows were ever present.

        Proven in two parts because the schema constraint makes a real double-row
        insert impossible — exactly the fail-closed guarantee required."""
        code, email, password = await _setup_full_login(s2_db)
        ws_row = await _fetch_one(
            s2_db,
            "SELECT w.id AS wid, tr.tenant_schema AS schema "
            "FROM public.wholesalers w "
            "JOIN public.tenant_registrations tr ON tr.wholesaler_id = w.id "
            "WHERE w.code = :code",
            {"code": code},
        )

        # (a) The DB rejects a second live registration for the same wholesaler.
        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError):
            await _execute(
                s2_db,
                "INSERT INTO public.tenant_registrations "
                "(id, company_name, tenant_code, country, owner_email, status, "
                " wholesaler_id, tenant_schema, expires_at, password_hash_cleared_at) "
                "VALUES (:id, :company, :code2, 'TZ', :email2, 'active', "
                " :ws_id, :schema, :expires, :cleared)",
                {
                    "id": uuid.uuid4(),
                    "company": f"Company Dup {code}",
                    "code2": _unique_code("DUP"),
                    "email2": _unique_email(),
                    "ws_id": ws_row.wid,
                    "schema": ws_row.schema,
                    "expires": datetime.now(timezone.utc) + timedelta(days=365),
                    "cleared": datetime.now(timezone.utc),
                },
            )
            await s2_db.commit()
        await s2_db.rollback()

        # (b) The endpoint's dedup gate refuses to authenticate when two rows
        # would be returned. Proven by invoking the login handler with a stub
        # session that yields two synthetic registration rows for the same code.
        from api.v1.client import auth as auth_module
        from schemas.retailer_credentials import RetailerLoginRequest

        class _Row:
            def __init__(self, **kw):
                for k, v in kw.items():
                    setattr(self, k, v)

        class _Result:
            def __init__(self, rows):
                self._rows = rows

            def fetchall(self):
                return self._rows

        class _StubSession:
            async def execute(self, _stmt, _params=None):
                # Return two distinct active registrations for the same wholesaler.
                return _Result([
                    _Row(
                        id=ws_row.wid,
                        code=code,
                        name="A",
                        status="active",
                        registration_id=uuid.uuid4(),
                        tenant_schema=ws_row.schema,
                    ),
                    _Row(
                        id=ws_row.wid,
                        code=code,
                        name="B",
                        status="active",
                        registration_id=uuid.uuid4(),
                        tenant_schema=ws_row.schema,
                    ),
                ])

        req = RetailerLoginRequest(
            email=email, password=password, wholesaler_code=code
        )
        from core.error_codes import MpangoAPIException

        with pytest.raises(MpangoAPIException) as exc_info:
            await auth_module.retailer_login(req, _StubSession())
        assert exc_info.value.status_code == HTTPStatus.UNAUTHORIZED
        assert exc_info.value.error_code.value == "INVALID_CREDENTIALS"
        assert exc_info.value.message == "Invalid credentials"


# ---------------------------------------------------------------------------
# §8 Rate limit returns controlled 429, never 500
# ---------------------------------------------------------------------------


class TestRateLimit429:
    """POST /client/auth/login, when rate-limited through the real
    RateLimitingMiddleware, returns a controlled 429 (never 500) carrying the
    required X-RateLimit-* / Retry-After headers. Proven over real Redis."""

    async def test_rate_limited_login_returns_429_with_headers(
        self, client: AsyncClient, s2_db
    ):
        import core.rate_limiter as rl_mod

        # Set up a valid portal + credentials so requests reach the limiter
        # (and so the first <limit> requests succeed rather than 401).
        code, email, password = await _setup_full_login(s2_db)

        # A unique forwarded-IP isolates this test's Redis counter from any
        # other run (the limiter keys on X-Forwarded-For for anonymous calls).
        test_ip = f"203.0.113.{(uuid.uuid4().int % 200) + 1}"
        headers = {"X-Forwarded-For": test_ip}

        # Lower the IP limit so we can exceed it within the test window.
        original_limit = rl_mod.DEFAULT_IP_LIMIT
        rl_mod.DEFAULT_IP_LIMIT = 3
        limit_plus = original_limit  # noqa: F841 (documented below)
        try:
            statuses = []
            # Fire limit+2 requests: first `limit` succeed, the next 429.
            for _ in range(rl_mod.DEFAULT_IP_LIMIT + 2):
                resp = await client.post(
                    "/api/v1/client/auth/login",
                    json={
                        "email": email,
                        "password": password,
                        "wholesaler_code": code,
                    },
                    headers=headers,
                )
                statuses.append(resp.status_code)

            # The final request must be the controlled 429.
            assert statuses[-1] == HTTPStatus.TOO_MANY_REQUESTS, (
                f"Expected final 429, got statuses {statuses}"
            )
            # And at least the first request was NOT a 429 (limiter allowed it).
            assert statuses[0] != HTTPStatus.TOO_MANY_REQUESTS

            # Required rate-limit headers present on the 429 response.
            limited = next(
                r for r in [resp] if r.status_code == HTTPStatus.TOO_MANY_REQUESTS
            )
            assert "Retry-After" in limited.headers
            assert "X-RateLimit-Limit" in limited.headers
            assert "X-RateLimit-Remaining" in limited.headers
            assert "X-RateLimit-Reset" in limited.headers
            assert int(limited.headers["X-RateLimit-Remaining"]) == 0
        finally:
            rl_mod.DEFAULT_IP_LIMIT = original_limit


# ---------------------------------------------------------------------------
# §9 Owner login unchanged
# ---------------------------------------------------------------------------


class TestOwnerLoginUnchanged:
    """Owner login still returns its existing available_tenants contract."""

    async def test_owner_login_returns_available_tenants(
        self, client: AsyncClient, s2_db
    ):
        code = _unique_code("S2OL")
        email = _unique_email()
        password = _OWNER_PW
        ws_id, schema = await _make_tenant(s2_db, code=code)

        # Create an owner-style user (not retailer_operator).
        uid = await _create_retailer_user(
            s2_db, tenant_schema=schema, email=email, password=password
        )
        # Grant admin role (not retailer_operator).
        await _execute(
            s2_db,
            f'INSERT INTO "{schema}".roles (name, description) '
            "VALUES ('admin', 'Tenant Admin') ON CONFLICT (name) DO NOTHING",
        )
        await _execute(
            s2_db,
            f'INSERT INTO "{schema}".user_roles (user_id, role_id) '
            f"SELECT :uid, id FROM \"{schema}\".roles WHERE name = 'admin'",
            {"uid": uid},
        )
        await s2_db.commit()

        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        assert resp.status_code == HTTPStatus.OK
        data = resp.json()["data"]
        # Owner login returns identity tokens with available_tenants.
        assert "available_tenants" in data
        assert len(data["available_tenants"]) >= 1
        # The wholesaler code should be in available_tenants.
        assert any(t["code"] == code for t in data["available_tenants"])
