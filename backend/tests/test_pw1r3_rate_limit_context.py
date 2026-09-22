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

Deterministic boundary (V3, 2026-09-23): the exact-boundary node
test_101st_anonymous_is_429_and_contextually_independently_admitted no longer
relies on 101 real HTTP requests completing inside one real 60s window (the
wall-clock assumption that failed a fresh Kilo 84-run at 307.482s with no
product regression). It now pins a controlled time source (see FixedLogicalClock
below), performs the first 100 anonymous increments directly through the REAL
RateLimiter against the task-owned real Redis, and lets the 101st request —
the FIRST real HTTP one — hit the REAL middleware and return exactly 429.
The product rate limiter, its limits (100/1000), WINDOW_SIZE=60 and the Redis
fixed-window algorithm are untouched.
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
from starlette.requests import Request

import core.rate_limiter as rate_limiter_module
from api.app import configure_app
from auth.strategies.jwt import JwtAuthStrategy
from core.config import get_settings
from core.error_codes import register_exception_handlers
from core.rate_limiter import WINDOW_SIZE, RateLimiter
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

    R1 auth-stock fix alignment (2026-09-08): resolve_tenant_context now also
    requires an existing, non-deleted, ACTIVE public.wholesalers row for the
    token's tenant (platform-registry liveness — a tenant outside the registry
    must fail closed). This fixture therefore also provisions one exact,
    task-owned wholesalers row (status='active') and removes it by exact id on
    teardown; the rate-limit contract under test is otherwise unchanged.
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
        await session.execute(
            text(
                "INSERT INTO public.wholesalers (id, code, name, status, is_deleted) "
                "VALUES (:wid, :code, :name, 'active', FALSE)"
            ),
            {
                "wid": tenant_id,
                "code": f"PW1R3RL{uuid.uuid4().hex[:10].upper()}",
                "name": "PW1-R3 synthetic rate-limit tenant",
            },
        )
        await session.commit()
    try:
        yield {"schema": RL_SCHEMA, "tenant_id": tenant_id, "user_id": user_id}
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(
                text("DELETE FROM public.wholesalers WHERE id = :wid"),
                {"wid": tenant_id},
            )
            await session.commit()


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
# Test-injected controlled time source (PW1-R3 deterministic boundary,
# CTO-AUTH-REVOCATION-STOCK-R1-PW1R3-DETERMINISTIC-BOUNDARY-20260923).
#
# The product's fixed-window math — core/rate_limiter.py
# `int(time.time() / WINDOW_SIZE)` — resolves `time` from ITS OWN module
# namespace at call time. A function-scoped monkeypatch of that ONE module
# attribute pins the window selection for the REAL product code path: every
# increment then lands in ONE deterministic window regardless of host speed
# or real minute boundaries. The injection is scoped to the test and the
# rate-limit module only (never a global, never a permanent replacement of
# Python time.time) and monkeypatch restores the original automatically.
# ---------------------------------------------------------------------------
# A fixed instant 30 seconds INSIDE its window (mid-window, maximally far
# from both boundaries; 1234590.0 = 60*20576 + 30).
LOGICAL_NOW = 1_234_590.0


class FixedLogicalClock:
    """Object with a fixed ``time()`` — the controlled time source."""

    def __init__(self, instant: float):
        self._instant = instant

    def time(self) -> float:
        return self._instant


@pytest.fixture
def fixed_window(monkeypatch):
    """Pin core.rate_limiter's clock to LOGICAL_NOW for this test only.

    Both the direct RateLimiter calls and the REAL HTTP middleware path (the
    inner RateLimitingMiddleware and the auth-rejection hook call the same
    limiter code, which reads ``time`` from core.rate_limiter's namespace)
    then share ONE fixed logical window, so every key and count is exact and
    independent of wall-clock speed.
    """
    clock = FixedLogicalClock(LOGICAL_NOW)
    monkeypatch.setattr(rate_limiter_module, "time", clock)
    return clock


def fixed_window_index(instant: float = LOGICAL_NOW) -> int:
    """The window index the pinned product clock selects for ``instant``."""
    return int(instant // WINDOW_SIZE)


def direct_request(client_ip: str) -> Request:
    """A REAL starlette Request for direct RateLimiter.check_rate_limit calls.

    The scope mirrors what ASGITransport produces: the peer address is the
    transport-level client (NOT a forged X-Forwarded-For/X-Real-IP header),
    so `_get_client_ip` falls back to the exact peer this test owns. No
    tenant/user state is attached — the anonymous bucket is exercised."""
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "server": ("testserver", 80),
        "path": "/api/v1/auth/me",
        "raw_path": b"/api/v1/auth/me",
        "query_string": b"",
        "headers": [],
        "client": (client_ip, 12345),
    }
    return Request(scope)


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


async def test_101st_anonymous_is_429_and_contextual_independently_admitted(
    rl_tenant, real_rate_limiter, fixed_window
):
    """Mandatory #9, deterministic under the test-injected controlled clock.

    This test owns a fresh IP bucket (a fresh peer IP) and a fresh tenant
    bucket (function-scoped rl_tenant), and deletes EXACTLY those two keys
    before and after. The controlled time source pins the product's window
    selection (core.rate_limiter reads ``time`` from its own module
    namespace) to one fixed mid-window instant, so all anonymous increments —
    the 100 direct ones below AND the HTTP ones — land in ONE fixed window
    deterministically, independent of host speed or real minute boundaries.

    Split proof: increments 1..100 run directly through the REAL
    RateLimiter.check_rate_limit against the task-owned real Redis; the
    101st request is the FIRST real HTTP one, so the exact boundary — 429
    with limit 100, X-RateLimit-Remaining 0, Retry-After > 0 and code
    RATE_LIMIT_EXCEEDED — is proven through the REAL middleware stack.
    Garbage Authorization then shares the SAME anonymous bucket (rejection
    path — no bypass) and a valid contextual request is independently
    admitted at limit 1000."""
    ip = _make_test_ip(15)
    limiter = real_rate_limiter
    redis = await limiter._get_redis()
    window = fixed_window_index()
    own_keys = [
        f"rate_limit:ip:{ip}:{window}",
        f"rate_limit:tenant:{rl_tenant['tenant_id']}:{rl_tenant['user_id']}:{window}",
    ]
    # Pre-delete ONLY this test's own two exact keys (fresh run-unique IP and
    # fresh tenant UUIDs make this a defensive zero; asserted as such).
    assert await redis.delete(*own_keys) == 0, (
        "task-owned buckets must start empty in the fixed window"
    )
    try:
        # Increments 1..100 — direct, real limiter, real Redis, fixed window.
        counts = []
        for _ in range(100):
            allowed, count, limit = await limiter.check_rate_limit(direct_request(ip))
            assert allowed is True and limit == 100
            counts.append(count)

        # THE 101st anonymous request — through the REAL HTTP stack — must be
        # exactly the one refused: precise boundary, not "some 429".
        async with make_client(ip) as client:
            resp = await client.get("/api/v1/auth/me")
            assert resp.status_code == 429, (
                f"the 101st anonymous request must be 429, got {resp.status_code}"
            )
            assert resp.headers.get("X-RateLimit-Limit") == "100"
            assert resp.headers.get("X-RateLimit-Remaining") == "0"
            assert int(resp.headers.get("Retry-After", "0")) > 0
            assert resp.json().get("code") == "RATE_LIMIT_EXCEEDED"

            # Malformed/invalid Authorization shares the SAME anonymous bucket:
            # the auth-rejection path is rate-limited — no unlimited bypass.
            garbage = await client.get(
                "/api/v1/auth/me", headers={"Authorization": "Bearer not-a-jwt"}
            )
            assert garbage.status_code == 429
            assert garbage.headers.get("X-RateLimit-Limit") == "100"

            # A valid contextual request is independently admitted.
            token = contextual_token(rl_tenant)
            ctx = await client.get(
                "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
            )
            assert ctx.status_code == 200
            assert ctx.headers.get("X-RateLimit-Limit") == "1000"

        # Post-conditions (asserted AFTER the boundary so the exact-101st
        # assertion is the first one a window-breaking regression can trip):
        # the 100 direct increments formed ONE unbroken in-window sequence,
        # the two anonymous-path HTTP requests landed in the SAME IP bucket,
        # and the contextual request in its OWN tenant bucket only.
        assert counts == list(range(1, 101)), (
            "all 100 direct increments must land in ONE fixed window "
            f"(sequence broken: {counts[:3]}...{counts[-3:]})"
        )
        assert await redis.get(own_keys[0]) == "102"
        assert await redis.get(own_keys[1]) == "1"
    finally:
        # Post-delete ONLY this test's own two exact keys.
        await redis.delete(*own_keys)


async def test_health_endpoints_are_exempt_from_rate_limiting():
    async with make_client(_make_test_ip(16)) as client:
        resp = await client.get("/health/live")
        assert resp.status_code == 200
        assert "X-RateLimit-Limit" not in resp.headers
        assert "X-RateLimit-Remaining" not in resp.headers
