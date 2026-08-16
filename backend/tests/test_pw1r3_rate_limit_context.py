"""
PW1-R3 (R1) — Authenticated rate-limit context integration tests.

REAL middleware stack: FastAPI() + configure_app(...) wired with the production
JwtAuthStrategy (same pattern as the DC-12R1-S2 suite), exercised end-to-end
through httpx ASGITransport. The rate limiter runs its REAL code path against a
REAL Redis instance.

Deterministic-start design (PW1-R3-R1):
- Task-exclusive Redis DB (PW1R3_TEST_REDIS_URL, default .../15).
- Exact task-owned keys only:
  * tenant bucket: `rate_limit:tenant:{tenant_id}:{user_id}` with fresh UUID
    per test (function-scoped fixture) — every test starts at count 0.
  * anonymous IP bucket: each test obtains a FRESH ASGI client peer address
    (transport client=("<test-ip>", port)) — per-test IP keys start at 0.
    This is the transport-level connection peer, NOT a spoofed
    X-Forwarded-For/X-Real-IP header, so the product's header-reading code is
    never exercised with forged values.
- No FLUSHDB, no wildcard SCAN/delete, no retry-until-green, no window
  alignment sleeps (no longer needed with deterministic per-test keys).
- The tenant schema/user is SYNTHETIC but real-PG: direct DDL + INSERT (not
  the formal owner/retailer lifecycle) — sufficient and exact for exercising
  resolve_tenant_context()'s real DB lookup.
"""
import os
import uuid

import pytest
import pytest_asyncio
from unittest import mock
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import text

import core.rate_limiter as rate_limiter_module
from api.app import configure_app
from auth.strategies.jwt import JwtAuthStrategy
from core.config import get_settings
from core.error_codes import register_exception_handlers
from core.rate_limiter import RateLimiter
from core.security import create_contextual_token, create_identity_token, hash_password
from database.session import AsyncSessionLocal

pytestmark = pytest.mark.asyncio

# Task-exclusive Redis DB for this suite.
TEST_REDIS_URL = os.environ.get("PW1R3_TEST_REDIS_URL", "redis://127.0.0.1:26379/15")

RL_SCHEMA = f"t_pw1r3_rl_{uuid.uuid4().hex[:8]}"

# Per-RUN anonymous-peer seed: every run gets a fresh 10.x.y.* network, so the
# task-owned IP buckets start at zero even across rapid consecutive runs
# within the same fixed window (no FLUSHDB, no residue accounting).
_RUN_IP_SEED = uuid.uuid4().hex


def _make_test_ip(suffix: int) -> str:
    octet = lambda i: (int(_RUN_IP_SEED[i:i + 4], 16) % 200) + 20
    return f"10.{octet(0)}.{octet(4)}.{suffix}"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture(scope="module")
async def rl_auth_schema():
    """Synthetic real-PG auth schema: direct DDL + one active user.

    resolve_tenant_context() performs a real DB lookup (get_user_with_permissions),
    so the contextual-JWT path is exercised end-to-end: verification, tenant
    resolution, request.state attachment, and rate-limit keying. This is NOT a
    formal-lifecycle provisioned tenant — it is a synthetic schema created by
    the test itself for the precise purpose of the middleware contract.

    Tables are created with explicit DDL (NOT Base.metadata.create_all): the
    User/Role/Permission models each declare their unique email/name/code index
    TWICE (column index=True + an explicit same-named Index in __table_args__),
    which makes create_all fail with DuplicateTableError. The DDL below mirrors
    the model columns exactly.
    """
    audit = (
        "created_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
        "updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
        "is_deleted BOOLEAN NOT NULL DEFAULT false, "
        "deleted_at TIMESTAMPTZ, "
        "created_by UUID, "
        "updated_by UUID"
    )
    ddl = [
        f'CREATE TABLE "{RL_SCHEMA}".users ('
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
        "email VARCHAR(255) NOT NULL UNIQUE, "
        "password_hash VARCHAR(255) NOT NULL, "
        "full_name TEXT, "
        f"is_active BOOLEAN NOT NULL DEFAULT true, {audit})",
        f'CREATE TABLE "{RL_SCHEMA}".roles ('
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
        "name VARCHAR(100) NOT NULL UNIQUE, "
        f"description VARCHAR(255), {audit})",
        f'CREATE TABLE "{RL_SCHEMA}".permissions ('
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
        "code VARCHAR(100) NOT NULL UNIQUE, "
        f"description VARCHAR(255), {audit})",
        f'CREATE TABLE "{RL_SCHEMA}".user_roles ('
        "user_id UUID NOT NULL REFERENCES \"" + RL_SCHEMA + "\".users(id) ON DELETE CASCADE, "
        "role_id UUID NOT NULL REFERENCES \"" + RL_SCHEMA + "\".roles(id) ON DELETE CASCADE, "
        "PRIMARY KEY (user_id, role_id))",
        f'CREATE TABLE "{RL_SCHEMA}".role_permissions ('
        "role_id UUID NOT NULL REFERENCES \"" + RL_SCHEMA + "\".roles(id) ON DELETE CASCADE, "
        "permission_id UUID NOT NULL REFERENCES \"" + RL_SCHEMA + "\".permissions(id) ON DELETE CASCADE, "
        "PRIMARY KEY (role_id, permission_id))",
    ]

    async with AsyncSessionLocal() as session:
        await session.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{RL_SCHEMA}"'))
        for stmt in ddl:
            await session.execute(text(stmt))
        await session.commit()

    yield RL_SCHEMA

    # Cleanup of THIS test's own schema only (explicit name, no wildcards).
    async with AsyncSessionLocal() as session:
        await session.execute(text(f'DROP SCHEMA IF EXISTS "{RL_SCHEMA}" CASCADE'))
        await session.commit()


@pytest_asyncio.fixture
async def rl_tenant(rl_auth_schema):
    """Function-scoped synthetic tenant identity: fresh task-owned UUIDs.

    Every test starts with a deterministic, untouched tenant bucket
    (`rate_limit:tenant:{tenant_id}:{user_id}`) and a fresh active user row.
    """
    tenant_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    async with AsyncSessionLocal() as session:
        await session.execute(
            text(
                f'INSERT INTO "{RL_SCHEMA}".users (id, email, password_hash, full_name, is_active) '
                "VALUES (:id, :email, :pw, :name, true)"
            ),
            {"id": user_id, "email": f"pw1r3-rl-{uuid.uuid4().hex[:6]}@test.dev",
             "pw": hash_password("pw1r3-not-a-real-credential"), "name": "PW1R3 RL User"},
        )
        await session.commit()
    return {"schema": RL_SCHEMA, "tenant_id": tenant_id, "user_id": user_id}


@pytest_asyncio.fixture(autouse=True)
async def real_rate_limiter():
    """Real RateLimiter against the task-exclusive real Redis DB.

    The singleton is swapped so the REAL middleware path get_rate_limiter()
    serves this instance; the original global is restored afterwards.
    """
    redis_client = Redis.from_url(TEST_REDIS_URL, encoding="utf-8", decode_responses=True)
    limiter = RateLimiter(redis_client=redis_client)
    prev = rate_limiter_module._rate_limiter
    rate_limiter_module._rate_limiter = limiter
    yield limiter
    rate_limiter_module._rate_limiter = prev
    await redis_client.aclose()


def build_app() -> FastAPI:
    app = FastAPI()
    with mock.patch("auth.factory.get_auth_strategy", return_value=JwtAuthStrategy()):
        configure_app(app, get_settings())
    register_exception_handlers(app)
    return app


def make_client(client_ip: str):
    """AsyncClient over the real app with a fresh ASGI client peer address.

    The per-test peer IP yields a deterministic, task-owned anonymous bucket
    (`rate_limit:ip:{client_ip}:{window}`). This is the transport-level peer,
    not a forged X-Forwarded-For/X-Real-IP header.
    """
    return AsyncClient(
        transport=ASGITransport(app=build_app(), client=(client_ip, 12345)),
        base_url="http://testserver",
    )


def contextual_token(rl):
    return create_contextual_token(
        user_id=rl["user_id"],
        roles=["admin"],
        tenant_id=rl["tenant_id"],
        tenant_schema=rl["schema"],
        token_type="access",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
async def test_middleware_order_auth_runs_before_rate_limiting():
    """Structural canary: Starlette keeps user_middleware NEWEST-FIRST — the
    list index 0 element is the OUTERMOST (runs first on each request).
    AuthenticationMiddleware must sit BEFORE (outer than) RateLimitingMiddleware
    so the verified context exists when limiting runs."""
    app = build_app()
    names = [m.cls.__name__ for m in app.user_middleware]
    assert names.index("AuthenticationMiddleware") < names.index("RateLimitingMiddleware"), (
        f"execution order inverted (auth must be outer): {names}"
    )


async def test_anonymous_request_uses_ip_bucket_limit_100():
    async with make_client(_make_test_ip(11)) as client:
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 401
        assert resp.headers.get("X-RateLimit-Limit") == "100"


async def test_contextual_jwt_uses_tenant_bucket_limit_1000(rl_tenant):
    token = contextual_token(rl_tenant)
    async with make_client(_make_test_ip(12)) as client:
        resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.headers.get("X-RateLimit-Limit") == "1000"
        assert resp.json()["data"]["tenant_id"] == rl_tenant["tenant_id"]


async def test_contextual_burst_stays_admitted_well_past_ip_limit(rl_tenant):
    """105 contextual requests (task-owned tenant/user bucket) — none may be
    429, even though the same count would exhaust the anonymous IP bucket."""
    token = contextual_token(rl_tenant)
    async with make_client(_make_test_ip(13)) as client:
        statuses = set()
        for _ in range(105):
            resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
            statuses.add(resp.status_code)
            assert resp.headers.get("X-RateLimit-Limit") == "1000"
        assert statuses == {200}


async def test_identity_only_jwt_uses_ip_limit_100():
    token = create_identity_token(user_id=str(uuid.uuid4()), roles=["admin"], token_type="access")
    async with make_client(_make_test_ip(14)) as client:
        resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        # Identity-only me is handled (H-Fix-01); it must stay on the IP limit.
        assert resp.status_code == 200
        assert resp.headers.get("X-RateLimit-Limit") == "100"


async def test_101st_anonymous_is_429_and_contextual_independently_admitted(rl_tenant):
    """Mandatory #9, deterministic: this test owns a fresh IP bucket
    (a fresh peer IP) and a fresh tenant bucket (function-scoped rl_tenant), so the
    exact-boundary math holds without residue accounting: the 101st anonymous
    request is 429 at limit 100; garbage Authorization shares the SAME IP
    bucket (rejection path — no bypass); a valid contextual request is
    independently admitted at limit 1000."""
    async with make_client(_make_test_ip(15)) as client:
        first_429 = None
        for i in range(1, 151):
            resp = await client.get("/api/v1/auth/me")
            if resp.status_code == 429:
                first_429 = i
                break
        assert first_429 == 101, f"429 must arrive at exactly the 101st request (got {first_429})"
        assert resp.headers.get("X-RateLimit-Limit") == "100"
        assert resp.headers.get("X-RateLimit-Remaining") == "0"
        assert int(resp.headers.get("Retry-After", "0")) > 0
        assert resp.json().get("code") == "RATE_LIMIT_EXCEEDED"

        # Malformed/invalid Authorization shares the SAME anonymous bucket:
        # the auth-rejection path is rate-limited — no unlimited bypass.
        garbage = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
        assert garbage.status_code == 429
        assert garbage.headers.get("X-RateLimit-Limit") == "100"

        # A valid contextual request is independently admitted.
        token = contextual_token(rl_tenant)
        ctx = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert ctx.status_code == 200
        assert ctx.headers.get("X-RateLimit-Limit") == "1000"


async def test_health_endpoints_are_exempt_from_rate_limiting():
    async with make_client(_make_test_ip(16)) as client:
        resp = await client.get("/health/live")
        assert resp.status_code == 200
        assert "X-RateLimit-Limit" not in resp.headers
        assert "X-RateLimit-Remaining" not in resp.headers
