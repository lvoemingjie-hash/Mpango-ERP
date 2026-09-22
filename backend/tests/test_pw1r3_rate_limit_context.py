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

Fixed-window determinism closure (PW1-R3-FIXED-WINDOW-DETERMINISM-R1,
CTO-AUTH-...-2026-09-22, BASE 46ba2b1cc): the former proofs of the
exact-boundary contracts issued 101+ (105+) REAL HTTP requests and implicitly
required them all to complete inside ONE 60s fixed window. A fresh Kilo 84-run
observed the 101st node at 307.482s wall time: the requests spread across
multiple windows, the per-window count never reached 101, and the node FAILED
without any product regression (a real-clock assumption defect in the TEST).
This round removes that dependence WITHOUT touching product code:

- The window math of the REAL product path (`core/rate_limiter.py`
  `int(time.time() / WINDOW_SIZE)`) reads `time` from ITS OWN module
  namespace at call time, so the tests pin a FIXED LOGICAL CLOCK by
  monkeypatching `core.rate_limiter.time` — every increment then lands in
  ONE deterministic window no matter how slow the machine is (no sleeps,
  no retries; the verdict becomes a pure function of the request index).
- Split proof (CTO recommendation): the bulk 100-allowed/101st-rejected
  counting runs DIRECTLY through the real RateLimiter against the real
  Redis (fast, exact count sequence asserted), and a FEW real HTTP
  requests prove the boundary envelope (429 + exact headers) and the
  bucket mapping (anonymous / invalid-auth / contextual).
- A dedicated semantic-counterexample node replays the OLD wall-clock
  assumption with an advancing logical clock and demonstrates BOTH false
  verdicts it could produce (false red: expecting 429 at #101; vacuous
  green: "burst admitted well past the limit" with no window ever past
  it), then proves the pinned-clock design immune (same 101st rejection
  at two different fixed instants).
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
from core.error_codes import ErrorCode, MpangoAPIException, register_exception_handlers
from core.rate_limiter import WINDOW_SIZE, RateLimiter
from core.security import create_contextual_token, create_identity_token, hash_password
from database.session import AsyncSessionLocal
from starlette.requests import Request

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
# Fixed-window determinism apparatus (PW1-R3-FIXED-WINDOW-DETERMINISM-R1)
# ---------------------------------------------------------------------------
# The product's fixed-window math is `int(time.time() / WINDOW_SIZE)` inside
# core/rate_limiter.py, where `time` resolves from THAT module's namespace at
# call time. Pinning a logical clock there makes the REAL product path put
# every increment into ONE deterministic window regardless of wall-clock
# speed — no sleeps, no window alignment, no retry-until-green.

# A fixed, deliberately NON-window-aligned instant (its window index is
# int(LOGICAL_NOW // 60); not a multiple of 60, so no alignment assumption).
LOGICAL_NOW = 1_234_567.7


class FixedLogicalClock:
    """Clock whose time() always returns the same logical instant."""

    def __init__(self, instant: float):
        self._instant = instant

    def time(self) -> float:
        return self._instant


class AdvancingLogicalClock:
    """Clock that advances `step` seconds per time() read.

    Replays, deterministically, what slow wall-clock execution does to the
    OLD test design: a request sequence spread across a 60s window boundary."""

    def __init__(self, start: float, step: float):
        self._next = start
        self._step = step

    def time(self) -> float:
        now = self._next
        self._next += self._step
        return now


@pytest.fixture
def fixed_window(monkeypatch):
    """Pin core.rate_limiter's clock to LOGICAL_NOW for the whole test.

    Both the direct RateLimiter calls and the REAL HTTP middleware path (the
    middleware and the auth-rejection hook call the same limiter code, which
    reads `time` from core.rate_limiter's namespace) then share ONE fixed
    logical window, so bucket keys are exact and count math is deterministic.
    """
    clock = FixedLogicalClock(LOGICAL_NOW)
    monkeypatch.setattr(rate_limiter_module, "time", clock)
    return clock


def fixed_window_index(instant: float = LOGICAL_NOW) -> int:
    """The window index the pinned product clock selects for `instant`."""
    return int(instant // WINDOW_SIZE)


def direct_request(client_ip: str, *, tenant_id: str | None = None, user_id: str | None = None) -> Request:
    """A REAL starlette Request for direct RateLimiter.check_rate_limit calls.

    The scope mirrors what ASGITransport produces (peer address = the
    transport-level client, NOT a forged X-Forwarded-For/X-Real-IP header).
    tenant_id/user_id are attached to request.state exactly the way the REAL
    AuthenticationMiddleware attaches the verified server-side context."""
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
    request = Request(scope)
    if tenant_id is not None:
        request.state.tenant_id = tenant_id
    if user_id is not None:
        request.state.user_id = user_id
    return request


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


async def test_contextual_burst_stays_admitted_well_past_ip_limit(
    rl_tenant, real_rate_limiter, fixed_window
):
    """Contextual requests stay admitted (limit 1000) while the SAME client
    IP's anonymous bucket is exhausted FAR past its limit — deterministic
    under the pinned logical clock.

    Determinism closure: the former shape issued 105 REAL HTTP requests and
    implicitly required them to finish inside one 60s window; on a slow host
    the windows rolled over and the "well past the ip limit" premise silently
    evaporated (vacuous green). Now the exhaustion is proven DIRECTLY through
    the real limiter (120 increments in ONE fixed window — count sequence
    asserted), a handful of REAL HTTP contextual requests prove the envelope
    on the very same exhausted peer IP, and the tenant bucket's own 1000
    boundary is proven exactly (1000 allowed, 1001st rejected)."""
    ip = _make_test_ip(13)
    limiter = real_rate_limiter

    # Exhaust the anonymous IP bucket far past its limit in ONE fixed window.
    allowed_counts = []
    first_reject = None
    for i in range(1, 121):
        try:
            _, count, limit = await limiter.check_rate_limit(direct_request(ip))
            assert limit == 100
            allowed_counts.append(count)
        except MpangoAPIException as exc:
            assert exc.error_code == ErrorCode.RATE_LIMIT_EXCEEDED
            if first_reject is None:
                first_reject = i
    assert first_reject == 101, (
        f"anonymous bucket must reject at exactly the 101st request (got {first_reject})"
    )
    assert allowed_counts == list(range(1, 101)), (
        "all 100 allowed increments must land in ONE fixed window "
        f"(sequence broken: {allowed_counts[:3]}...{allowed_counts[-3:]})"
    )
    redis = await limiter._get_redis()
    window = fixed_window_index()
    assert await redis.get(f"rate_limit:ip:{ip}:{window}") == "120"

    # REAL HTTP contextual burst on the SAME (exhausted) peer IP: every
    # request is independently admitted at the tenant limit 1000.
    token = contextual_token(rl_tenant)
    async with make_client(ip) as client:
        statuses = set()
        for _ in range(12):
            resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
            statuses.add(resp.status_code)
            assert resp.headers.get("X-RateLimit-Limit") == "1000"
        assert statuses == {200}
    assert await redis.get(f"rate_limit:ip:{ip}:{window}") == "120", (
        "contextual requests must not touch the anonymous IP bucket"
    )
    assert await redis.get(
        f"rate_limit:tenant:{rl_tenant['tenant_id']}:{rl_tenant['user_id']}:{window}"
    ) == "12"

    # Exact tenant-bucket boundary (deterministic under the pinned clock):
    # 1000 allowed, the 1001st rejected with limit 1000.
    tenant = {
        "tenant_id": rl_tenant["tenant_id"],
        "user_id": rl_tenant["user_id"],
    }
    for expected_count in range(13, 1001):
        _, count, limit = await limiter.check_rate_limit(direct_request(ip, **tenant))
        assert (count, limit) == (expected_count, 1000)
    with pytest.raises(MpangoAPIException) as raised:
        await limiter.check_rate_limit(direct_request(ip, **tenant))
    assert raised.value.error_code == ErrorCode.RATE_LIMIT_EXCEEDED
    assert raised.value.status_code == 429
    assert raised.value.details["limit"] == 1000


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
    """Mandatory #9, deterministic under the pinned logical clock.

    Split proof (fixed-window determinism closure): the exact-boundary
    counting (100 allowed, 101st rejected) runs DIRECTLY through the real
    RateLimiter against the task-owned real Redis with the clock pinned to
    ONE fixed window — the count sequence is asserted to be exactly
    1..100, so the verdict is a pure function of the request index and
    cannot be affected by wall-clock speed. ONE real HTTP request then
    proves the boundary envelope through the REAL middleware (429 + exact
    headers + error code), a garbage-Authorization request proves the
    auth-rejection path cannot bypass the SAME anonymous bucket, and a
    valid contextual request is independently admitted at limit 1000 —
    with the real Redis keys asserted to prove the bucket mapping."""
    ip = _make_test_ip(15)
    limiter = real_rate_limiter
    redis = await limiter._get_redis()
    window = fixed_window_index()

    # Direct product-path proof: 100 allowed in ONE fixed window...
    counts = []
    for _ in range(100):
        allowed, count, limit = await limiter.check_rate_limit(direct_request(ip))
        assert allowed is True
        assert limit == 100
        counts.append(count)
    assert counts == list(range(1, 101)), (
        "all 100 increments must land in ONE fixed window "
        f"(sequence broken: {counts[:3]}...{counts[-3:]})"
    )
    # ...and the 101st is rejected by the REAL limiter with the exact contract.
    with pytest.raises(MpangoAPIException) as raised:
        await limiter.check_rate_limit(direct_request(ip))
    assert raised.value.error_code == ErrorCode.RATE_LIMIT_EXCEEDED
    assert raised.value.status_code == 429
    assert raised.value.details["limit"] == 100
    assert int(raised.value.details["retry_after"]) > 0
    assert await redis.get(f"rate_limit:ip:{ip}:{window}") == "101"

    # REAL HTTP boundary envelope: the 102nd overall increment (first through
    # the middleware) is a 429 carrying the exact S2-5 rate-limit headers.
    async with make_client(ip) as client:
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 429
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

    # Bucket mapping proof in the real Redis: the two anonymous-path HTTP
    # requests (429 + garbage) landed in the SAME IP bucket (101 -> 103) and
    # the contextual request in its OWN tenant bucket only.
    assert await redis.get(f"rate_limit:ip:{ip}:{window}") == "103"
    assert await redis.get(
        f"rate_limit:tenant:{rl_tenant['tenant_id']}:{rl_tenant['user_id']}:{window}"
    ) == "1"


async def test_health_endpoints_are_exempt_from_rate_limiting():
    async with make_client(_make_test_ip(16)) as client:
        resp = await client.get("/health/live")
        assert resp.status_code == 200
        assert "X-RateLimit-Limit" not in resp.headers
        assert "X-RateLimit-Remaining" not in resp.headers


async def test_semantic_counterexample_wallclock_spread_false_verdicts_fixed_clock_immune(
    real_rate_limiter, monkeypatch
):
    """[SEMANTIC COUNTEREXAMPLE — CTO §8] The OLD wall-clock-dependent proof
    design produces FALSE verdicts when execution is slow enough to cross a
    window boundary; the pinned-clock design is immune to wall-clock speed.

    Part 1 (old design replayed deterministically): an AdvancingLogicalClock
    moves the product's window index forward 1 second per request, which is
    exactly what slow wall-clock execution does to a "send 150 real HTTP
    requests and expect the 101st to be 429" test (the fresh Kilo 84-run
    observed the node at 307.482s). Against the REAL limiter and REAL Redis,
    the per-window count then NEVER reaches 101:
      - the old "first 429 must be request #101" expectation FAILS (false
        red — no product regression exists);
      - an old "burst stays admitted well past the ip limit" check would
        PASS VACUOUSLY (false green — no window was ever past the limit,
        so nothing about the 1000-limit contract was exercised).

    Part 2 (new design, twice): with the clock PINNED — at two DIFFERENT
    fixed, non-aligned instants — the same 150-request sequence rejects at
    EXACTLY #101 both times: the verdict is a pure function of the request
    index, independent of wall-clock speed and of WHICH window the fixed
    instant lands in."""
    limiter = real_rate_limiter

    # --- Part 1: advancing clock == slow execution crossing windows.
    spread_ip = _make_test_ip(21)
    spread_clock = AdvancingLogicalClock(start=LOGICAL_NOW, step=1.0)
    monkeypatch.setattr(rate_limiter_module, "time", spread_clock)
    first_reject = None
    max_window_count = 0
    for i in range(1, 151):
        try:
            _, count, _limit = await limiter.check_rate_limit(direct_request(spread_ip))
            max_window_count = max(max_window_count, count)
        except MpangoAPIException:
            if first_reject is None:
                first_reject = i
    assert first_reject is None, (
        "under window-crossing execution the old design's 101st-request 429 "
        "never arrives — replaying it deterministically must show NO rejection "
        f"(got first rejection at #{first_reject})"
    )
    assert max_window_count < 101, (
        "under window-crossing execution no single fixed window ever reaches "
        f"the limit (max per-window count {max_window_count}) — the OLD "
        "'burst admitted well past the ip limit' shape would pass VACUOUSLY"
    )

    # --- Part 2: pinned clock at two different fixed instants — identical,
    # index-deterministic verdicts regardless of wall-clock speed.
    for probe, instant in enumerate((LOGICAL_NOW, LOGICAL_NOW + 10_000.7)):
        pinned_ip = _make_test_ip(22 + probe)
        monkeypatch.setattr(rate_limiter_module, "time", FixedLogicalClock(instant))
        first_reject = None
        for i in range(1, 151):
            try:
                await limiter.check_rate_limit(direct_request(pinned_ip))
            except MpangoAPIException:
                if first_reject is None:
                    first_reject = i
        assert first_reject == 101, (
            f"with the clock pinned at instant {instant!r} the 101st request "
            f"must be rejected EXACTLY at index 101 (got {first_reject!r}); "
            "the pinned-clock verdict must not depend on wall-clock speed or "
            "on which window the fixed instant lands in"
        )
