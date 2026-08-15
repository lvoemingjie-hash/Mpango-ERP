"""
PW1-R3 — Authenticated rate-limit context integration tests.

REAL middleware stack: FastAPI() + configure_app(...) wired with the production
JwtAuthStrategy (same pattern as the DC-12R1-S2 suite), exercised end-to-end
through httpx ASGITransport. The rate limiter runs its REAL code path against a
REAL Redis instance (dedicated DB; tenant keys unique per run via UUIDs; the
shared anonymous IP key is read explicitly for exact-boundary accounting).

Isolation rules honored: no FLUSHDB, no wildcard SCAN/delete, no
retry-until-green, no spoofed X-Forwarded-For.
"""
import os
import time
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
from core.rate_limiter import RateLimiter, WINDOW_SIZE
from core.security import create_contextual_token, create_identity_token, hash_password
from database.session import AsyncSessionLocal

pytestmark = pytest.mark.asyncio

# Dedicated Redis DB for this suite (default: the task-owned test Redis).
TEST_REDIS_URL = os.environ.get("PW1R3_TEST_REDIS_URL", "redis://127.0.0.1:26379/15")

RL_SCHEMA = f"t_pw1r3_rl_{uuid.uuid4().hex[:8]}"
RL_TENANT_ID = str(uuid.uuid4())
RL_USER_ID = str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture(scope="module")
async def rl_tenant():
    """Create a real tenant schema with auth tables and one active user.

    resolve_tenant_context() performs a real DB lookup (get_user_with_permissions),
    so the contextual-JWT path is exercised end-to-end: verification, tenant
    resolution, request.state attachment, and rate-limit keying.

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
        await session.execute(
            text(
                f'INSERT INTO "{RL_SCHEMA}".users (id, email, password_hash, full_name, is_active) '
                "VALUES (:id, :email, :pw, :name, true)"
            ),
            {"id": RL_USER_ID, "email": f"pw1r3-rl-{uuid.uuid4().hex[:6]}@test.dev",
             "pw": hash_password("pw1r3-not-a-real-credential"), "name": "PW1R3 RL User"},
        )
        await session.commit()

    yield {"schema": RL_SCHEMA, "tenant_id": RL_TENANT_ID, "user_id": RL_USER_ID}

    # Cleanup of THIS test's own schema only (explicit name, no wildcards).
    async with AsyncSessionLocal() as session:
        await session.execute(text(f'DROP SCHEMA IF EXISTS "{RL_SCHEMA}" CASCADE'))
        await session.commit()


@pytest_asyncio.fixture(autouse=True)
async def real_rate_limiter():
    """Real RateLimiter against real Redis (client wiring only — no state mocks).

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


@pytest_asyncio.fixture
async def client():
    app = build_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as ac:
        yield ac


def contextual_token(rl):
    return create_contextual_token(
        user_id=RL_USER_ID,
        roles=["admin"],
        tenant_id=RL_TENANT_ID,
        tenant_schema=rl["schema"],
        token_type="access",
    )


async def redis_of():
    return Redis.from_url(TEST_REDIS_URL, encoding="utf-8", decode_responses=True)


async def current_ip_count(redis_client) -> int:
    """Read the CURRENT anonymous IP-window count (explicit keys, no SCAN)."""
    window = int(time.time() / WINDOW_SIZE)
    total = 0
    for ip in ("127.0.0.1", "testserver", "unknown"):
        v = await redis_client.get(f"rate_limit:ip:{ip}:{window}")
        if v:
            total += int(v)
    return total


async def align_to_fresh_window():
    """If the fixed window is about to rotate, wait for the next one so the
    exact-boundary (101st) math is deterministic."""
    remaining = WINDOW_SIZE - (time.time() % WINDOW_SIZE)
    if remaining < 15:
        time.sleep(remaining + 0.5)


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


async def test_anonymous_request_uses_ip_bucket_limit_100(client):
    # The anonymous IP key is shared across the suite (and may carry counts
    # from earlier tests in this window); the bucket CLASS is what is under
    # test here — any status is fine as long as it is limited at 100.
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code in (401, 429)
    assert resp.headers.get("X-RateLimit-Limit") == "100"


async def test_contextual_jwt_uses_tenant_bucket_limit_1000(client, rl_tenant):
    token = contextual_token(rl_tenant)
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.headers.get("X-RateLimit-Limit") == "1000"
    assert resp.json()["data"]["tenant_id"] == RL_TENANT_ID


async def test_contextual_burst_stays_admitted_well_past_ip_limit(client, rl_tenant):
    """105 contextual requests (unique tenant/user bucket) — none may be 429,
    even though the same count would exhaust the anonymous IP bucket."""
    token = contextual_token(rl_tenant)
    statuses = set()
    for _ in range(105):
        resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        statuses.add(resp.status_code)
        assert resp.headers.get("X-RateLimit-Limit") == "1000"
    assert statuses == {200}


async def test_identity_only_jwt_uses_ip_limit_100(client):
    token = create_identity_token(user_id=str(uuid.uuid4()), roles=["admin"], token_type="access")
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    # Identity-only me is handled (H-Fix-01); it must stay on the IP limit
    # (status may be 429 if the shared anonymous bucket is already hot).
    assert resp.status_code in (200, 429)
    assert resp.headers.get("X-RateLimit-Limit") == "100"


async def test_101st_anonymous_is_429_and_contextual_independently_admitted(client, rl_tenant):
    """Mandatory #9: the 101st anonymous request is 429 with exact headers,
    garbage Authorization shares the same IP bucket (no bypass), and a valid
    contextual request remains independently admitted at limit 1000."""
    redis_client = await redis_of()
    try:
        await align_to_fresh_window()
        prior = await current_ip_count(redis_client)

        first_429_index = None
        for i in range(1, 151):
            resp = await client.get("/api/v1/auth/me")
            if resp.status_code == 429:
                first_429_index = i
                break
        assert first_429_index is not None, "anonymous IP bucket never limited within 150 requests"
        assert first_429_index + prior == 101, (
            f"429 arrived at cumulative {first_429_index + prior} (limit boundary must be exactly 101)"
        )
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
    finally:
        await redis_client.aclose()


async def test_health_endpoints_are_exempt_from_rate_limiting(client):
    resp = await client.get("/health/live")
    assert resp.status_code == 200
    assert "X-RateLimit-Limit" not in resp.headers
    assert "X-RateLimit-Remaining" not in resp.headers
