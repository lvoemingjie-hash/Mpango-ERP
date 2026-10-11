"""
Public-create commit-boundary controls (R1, 2026-10-10).

Task: CTO-AUTH-MPANGO-PUBLIC-CREATE-COMMIT-BOUNDARY-R1-20261010.
Closes CTO finding F-01: POST /invitations and POST /retailers/register
(both entry modes) previously returned success after flush only; the sole
commit ran in request-scope dependency teardown AFTER FastAPI had already
emitted the response, so a client could receive 201 before the business
transaction was committed (and a later commit failure could not retract
the sent success).

Timing mechanism (real stack, no service/auth/DB replacement):
- ``TimingASGI`` wraps the real ``main.app`` and records the monotonic
  time of the ``http.response.start`` ASGI message (the moment a real
  server begins sending the response). It is deliberately NOT the moment
  the test client's ``await`` resolves, which may include app teardown.
- The session factory is wrapped so every REAL session keeps its true
  engine/connection while its ``commit()`` is observed: a session that
  flushed pending object writes since its last commit is
  "write-carrying". Read-only sessions (auth/permission lookups) are
  never touched. Write-carrying commits are recorded
  (begin/end) and can be held on a barrier or made to raise a distinctive
  injected exception — the only test-side instrumentation allowed by the
  directive.

Discriminative contract (must hold after the R1 fix):
- With the barrier HELD over write-carrying commits, no
  http.response.start / 2xx may be produced (BASE bytes and
  commit-removed mutants emit the response anyway -> RED).
- After the barrier is released the request succeeds, and a NEW
  independent connection immediately reads the committed rows.
- With a distinctive exception injected at the write-carrying commit,
  the request must fail closed: no 2xx and zero partial business rows.
- Permanent ordering control (no barrier): every write-carrying commit
  must END before http.response.start.

Cache-revocation controls (separate accounting, CTO F-06) live at the
bottom and are reported separately; they do not gate the two API
boundary fixes.
"""
from __future__ import annotations

import asyncio
import os
import secrets
import time
import uuid

import asyncpg
import httpx
import pytest
import pytest_asyncio
from sqlalchemy import event

os.environ.setdefault("MPANGO_ENV", "staging")

from fastapi import FastAPI  # noqa: E402

TENANT_ID = "550e8400-e29b-41d4-a716-446655440000"
TENANT_SCHEMA = "t_550e8400e29b41d4a716446655440000"
ADMIN_EMAIL = "admin@test.com"
ADMIN_PASSWORD = os.environ.get("MPANGO_TEST_ADMIN_PASSWORD", "")

INJECTED = "PCB_INJECTED_COMMIT_FAILURE_MARKER_7f3a"


class CommitProbe:
    """Records ordering of write-carrying commits vs response start."""

    def __init__(self) -> None:
        self.events: list[tuple[str, float]] = []
        self.response_started_at: float | None = None
        self.release = asyncio.Event()
        self.release.set()  # default: no barrier
        self.fail_first_write_commit = False
        self._failed_one = False

    def barrier_on(self) -> None:
        self.release.clear()

    def barrier_off(self) -> None:
        self.release.set()

    def mark_response_start(self) -> None:
        if self.response_started_at is None:
            self.response_started_at = time.monotonic()
            self.events.append(("response_start", self.response_started_at))

    def write_commit_ends_after_response_start(self) -> list[float]:
        if self.response_started_at is None:
            return []
        return [
            ts
            for kind, ts in self.events
            if kind == "write_commit_end" and ts > self.response_started_at
        ]


class TimingASGI:
    def __init__(self, app, probe: CommitProbe):
        self.app = app
        self.probe = probe

    async def __call__(self, scope, receive, send):
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                self.probe.mark_response_start()
            await send(message)

        await self.app(scope, receive, send_wrapper)


@pytest.fixture(scope="module")
def probe():
    return CommitProbe()


@pytest.fixture(scope="module")
def instrumented_app(probe):
    import database.session as ds
    import main

    real_factory = ds.AsyncSessionLocal
    sid_counter = [0]

    def factory():
        session = real_factory()
        sid_counter[0] += 1
        sid = sid_counter[0]
        state = {"flushed_since_commit": False}

        @event.listens_for(session.sync_session, "after_flush")
        def _mark_flushed(sess, flush_context):
            state["flushed_since_commit"] = True

        real_commit = session.commit

        async def observed_commit():
            if not state["flushed_since_commit"]:
                return await real_commit()
            probe.events.append(("write_commit_begin", time.monotonic()))
            if probe.fail_first_write_commit and not probe._failed_one:
                probe._failed_one = True
                raise RuntimeError(INJECTED)
            await probe.release.wait()
            try:
                await real_commit()
            finally:
                state["flushed_since_commit"] = False
            probe.events.append(("write_commit_end", time.monotonic()))

        session.commit = observed_commit  # type: ignore[method-assign]
        return session

    ds.AsyncSessionLocal = factory
    try:
        yield main.app
    finally:
        ds.AsyncSessionLocal = real_factory


@pytest_asyncio.fixture(scope="module")
async def asgi_client(instrumented_app, probe):
    wrapped = TimingASGI(instrumented_app, probe)
    transport = httpx.ASGITransport(app=wrapped)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://pcb-asgi.test", timeout=30.0
    ) as client:
        yield client


@pytest_asyncio.fixture(scope="module")
async def admin_headers(asgi_client):
    login = await asgi_client.post(
        "/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert login.status_code == 200, login.text[:300]
    identity = login.json()["data"]["access_token"]
    select = await asgi_client.post(
        "/api/v1/auth/select-tenant",
        json={"tenant_id": TENANT_ID},
        headers={"Authorization": f"Bearer {identity}"},
    )
    assert select.status_code == 200, select.text[:300]
    return {"Authorization": f"Bearer {select.json()['data']['access_token']}"}


@pytest_asyncio.fixture(scope="module")
async def independent_db():
    conn = await asyncpg.connect(os.environ["TEST_DATABASE_URL"])
    try:
        yield conn
    finally:
        await conn.close()


def _reset_probe(probe: CommitProbe) -> None:
    probe.events.clear()
    probe.response_started_at = None
    probe._failed_one = False
    probe.fail_first_write_commit = False
    probe.barrier_off()


async def _unique_phone_email(tag: str) -> tuple[str, str]:
    tail = uuid.uuid4().hex[:8]
    return f"+256711{tail[:6]}", f"pcb-{tag}-{tail}@example.com"


async def _create_invitation(asgi_client, admin_headers, phone: str) -> str:
    resp = await asgi_client.post(
        "/api/v1/invitations",
        json={"retailer_phone": phone},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text[:300]
    return resp.json()["data"]["code"]


async def _register(asgi_client, *, phone: str, email: str, code: str | None = None, join_intent: str | None = None):
    body: dict = {"phone": phone, "email": email, "name": "PCB Retailer"}
    if code is not None:
        body["invitation_code"] = code
    else:
        body["join_intent"] = join_intent
    return await asgi_client.post("/api/v1/retailers/register", json=body)


def _cause_chain_has(exc: BaseException, marker: str) -> bool:
    """E-02: the failure reason must be traceable to the dedicated injection,
    never an arbitrary RuntimeError that happens to satisfy the control."""
    seen = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if marker in str(cur):
            return True
        cur = cur.__cause__ or cur.__context__
    return False


async def _registration_rows(independent_db, email: str) -> dict:
    """E-02 strengthening: the register controls now match the PRECISE
    provisioning vectors — the binding's tenant_user_id, that tenant user's
    row and role, and the retailer credential setup token — not just
    'a retailer and some role exist'."""
    public = await independent_db.fetchrow(
        "SELECT r.id AS retailer_id, b.id AS binding_id, b.status AS binding_status, "
        "b.tenant_user_id AS bound_tenant_user_id "
        "FROM retailers r LEFT JOIN wholesaler_retailer_bindings b ON b.retailer_id = r.id "
        "WHERE r.email = $1",
        email,
    )
    tenant_user = await independent_db.fetchrow(
        f"SELECT u.id, u.is_active, u.is_deleted, "
        f"(SELECT ro.name FROM {TENANT_SCHEMA}.user_roles ur "
        f" JOIN {TENANT_SCHEMA}.roles ro ON ro.id = ur.role_id "
        f" WHERE ur.user_id = u.id ORDER BY ro.name LIMIT 1) AS role_name "
        f"FROM {TENANT_SCHEMA}.users u WHERE u.email = $1",
        email,
    )
    setup_tokens = await independent_db.fetch(
        "SELECT t.id, t.used_at, t.revoked_at "
        "FROM public.retailer_credential_setup_tokens t "
        "JOIN retailers r ON r.id = t.retailer_id WHERE r.email = $1 ORDER BY t.id",
        email,
    )
    return {
        "public": public,
        "tenant_user": tenant_user,
        "setup_tokens": [tuple(t) for t in setup_tokens],
    }


# ---------------------------------------------------------------------------
# 1. Barrier controls: no success response before the real commit
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_invitation_no_success_response_before_real_commit(
    probe, asgi_client, admin_headers, independent_db
):
    _reset_probe(probe)
    phone, _ = await _unique_phone_email("bar-inv")
    probe.barrier_on()
    task = asyncio.create_task(_create_invitation(asgi_client, admin_headers, phone))
    await asyncio.sleep(2.0)
    # While the write-carrying commit is held: no response may have started.
    assert probe.response_started_at is None, (
        "http.response.start emitted while the business commit was still held "
        f"(events={probe.events})"
    )
    assert any(k == "write_commit_begin" for k, _ in probe.events), probe.events
    probe.barrier_off()
    resp = await asyncio.wait_for(task, timeout=10)
    ends = [ts for k, ts in probe.events if k == "write_commit_end"]
    assert ends and max(ends) < probe.response_started_at, probe.events
    row = await independent_db.fetchrow(
        "SELECT status FROM invitations WHERE retailer_phone = $1", phone
    )
    assert row is not None and row["status"] == "active"


@pytest.mark.asyncio
async def test_register_invitation_entry_no_success_before_commit(
    probe, asgi_client, admin_headers, independent_db
):
    _reset_probe(probe)
    phone, email = await _unique_phone_email("bar-reg")
    code = await _create_invitation(asgi_client, admin_headers, phone)
    _reset_probe(probe)
    task = None
    probe.barrier_on()  # E-02: release the barrier in finally on any failure
    try:
        task = asyncio.create_task(_register(asgi_client, phone=phone, email=email, code=code))
        await asyncio.sleep(2.5)
        assert probe.response_started_at is None, (
            f"register emitted http.response.start before its commit (events={probe.events})"
        )
        assert any(k == "write_commit_begin" for k, _ in probe.events), probe.events
        probe.barrier_off()
        resp = await asyncio.wait_for(task, timeout=15)
        assert resp.status_code == 201, resp.text[:300]
        rows = await _registration_rows(independent_db, email)
        # E-02: precise provisioning vectors, not a coarse existence check.
        assert rows["public"] is not None and rows["public"]["binding_status"] == "active"
        tu = rows["tenant_user"]
        assert tu is not None and tu["is_deleted"] is False, f"tenant user: {dict(tu) if tu else None}"
        assert tu["is_active"] is False, (
            "a freshly registered retailer user is inactive until credential setup"
        )
        assert tu["role_name"] == "retailer_operator", f"role: {tu['role_name']}"
        assert rows["public"]["bound_tenant_user_id"] == tu["id"], (
            "binding.tenant_user_id does not match the tenant user row"
        )
        assert len(rows["setup_tokens"]) == 1, rows["setup_tokens"]
        assert rows["setup_tokens"][0][1] is None and rows["setup_tokens"][0][2] is None, (
            "a freshly issued setup token must be unused and unrevoked"
        )
    finally:
        probe.barrier_off()
        if task is not None and not task.done():
            task.cancel()


@pytest.mark.asyncio
async def test_register_join_intent_entry_no_success_before_commit(
    probe, asgi_client, admin_headers, independent_db
):
    _reset_probe(probe)
    lookup = await asgi_client.post(
        "/api/v1/wholesalers/lookup-code", json={"code": "TEST001"}
    )
    assert lookup.status_code == 200, lookup.text[:300]
    join_intent = lookup.json()["data"]["join_intent"]
    assert join_intent, lookup.text[:300]
    phone, email = await _unique_phone_email("bar-ji")
    _reset_probe(probe)
    task = None
    probe.barrier_on()
    try:
        task = asyncio.create_task(
            _register(asgi_client, phone=phone, email=email, join_intent=join_intent)
        )
        await asyncio.sleep(2.5)
        assert probe.response_started_at is None, (
            f"join_intent register emitted response before commit (events={probe.events})"
        )
        assert any(k == "write_commit_begin" for k, _ in probe.events), probe.events
        probe.barrier_off()
        resp = await asyncio.wait_for(task, timeout=15)
        assert resp.status_code == 201, resp.text[:300]
        rows = await _registration_rows(independent_db, email)
        assert rows["public"] is not None and rows["public"]["binding_status"] == "active"
        tu = rows["tenant_user"]
        assert tu is not None and tu["is_deleted"] is False, f"tenant user: {dict(tu) if tu else None}"
        assert tu["is_active"] is False, (
            "a freshly registered retailer user is inactive until credential setup"
        )
        assert tu["role_name"] == "retailer_operator", f"role: {tu['role_name']}"
        assert rows["public"]["bound_tenant_user_id"] == tu["id"]
    finally:
        probe.barrier_off()
        if task is not None and not task.done():
            task.cancel()


# ---------------------------------------------------------------------------
# 2. Commit-failure negative controls: fail closed, zero partial writes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_invitation_commit_failure_fail_closed_no_writes(
    probe, asgi_client, admin_headers, independent_db
):
    _reset_probe(probe)
    phone, _ = await _unique_phone_email("fail-inv")
    probe.fail_first_write_commit = True
    # Fail-closed contract: the client must NEVER receive a success
    # response. In-process an unhandled commit failure propagates out of
    # the ASGI app (a real uvicorn turns that into a 500 / reset
    # connection); either shape — propagated exception or >=500 response —
    # is acceptable, a 2xx is not.
    try:
        resp = await asgi_client.post(
            "/api/v1/invitations",
            json={"retailer_phone": phone},
            headers=admin_headers,
        )
        assert resp.status_code >= 500, (
            f"commit failure produced {resp.status_code}: {resp.text[:200]}"
        )
        assert INJECTED not in resp.text and "postgresql://" not in resp.text
    except Exception as exc:
        assert _cause_chain_has(exc, INJECTED), (
            "failure reason is not traceable to the dedicated injection: "
            f"{type(exc).__name__}: {exc}"
        )
        assert "postgresql://" not in str(exc)
    row = await independent_db.fetchrow(
        "SELECT 1 FROM invitations WHERE retailer_phone = $1", phone
    )
    assert row is None


@pytest.mark.asyncio
async def test_register_commit_failure_fail_closed_zero_partial_writes(
    probe, asgi_client, admin_headers, independent_db
):
    _reset_probe(probe)
    phone, email = await _unique_phone_email("fail-reg")
    code = await _create_invitation(asgi_client, admin_headers, phone)
    _reset_probe(probe)
    probe.fail_first_write_commit = True
    try:
        resp = await _register(asgi_client, phone=phone, email=email, code=code)
        assert resp.status_code >= 500, (
            f"commit failure produced {resp.status_code}: {resp.text[:200]}"
        )
        assert INJECTED not in resp.text and "postgresql://" not in resp.text
    except Exception as exc:
        assert _cause_chain_has(exc, INJECTED), (
            "failure reason is not traceable to the dedicated injection: "
            f"{type(exc).__name__}: {exc}"
        )
        assert "postgresql://" not in str(exc)
    rows = await _registration_rows(independent_db, email)
    # E-02: zero-partial across the full provisioning vector set.
    assert rows["public"] is None, f"partial public rows after failed commit: {rows}"
    assert rows["tenant_user"] is None, f"partial tenant rows after failed commit: {rows}"
    assert rows["setup_tokens"] == [], (
        f"setup token left after failed commit: {rows['setup_tokens']}"
    )
    # The invitation must remain consumable (its own transaction untouched).
    left = await independent_db.fetchval(
        "SELECT status FROM invitations WHERE code = $1", code
    )
    assert left == "active"


# ---------------------------------------------------------------------------
# 3. Permanent ordering control (no barrier)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_write_carrying_commit_after_response_start(
    probe, asgi_client, admin_headers, independent_db
):
    _reset_probe(probe)
    phone, email = await _unique_phone_email("ord")
    code = await _create_invitation(asgi_client, admin_headers, phone)
    _reset_probe(probe)
    resp = await _register(asgi_client, phone=phone, email=email, code=code)
    assert resp.status_code == 201, resp.text[:300]
    late = probe.write_commit_ends_after_response_start()
    assert not late, (
        f"write-carrying commits ended AFTER the response started: {late}; "
        f"events={probe.events}"
    )
    rows = await _registration_rows(independent_db, email)
    assert rows["public"] is not None and rows["tenant_user"] is not None


# ---------------------------------------------------------------------------
# 4. Cache-revocation controls — SEPARATE ACCOUNTING (CTO F-06)
# ---------------------------------------------------------------------------

BASE_URL = os.environ.get("PCB_RUNTIME_BASE_URL", "http://127.0.0.1:58310")


@pytest.mark.asyncio
async def test_idempotency_cache_premise_positive_control__cache_accounting(
    probe, asgi_client
):
    """Prove the idempotency response cache is actually hot for a real
    mutation: same key+body replay must return the first body with
    X-Idempotency-Replayed: true (middleware cache path, NOT canonical
    payment replay)."""
    _reset_probe(probe)
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        headers = await _native_login(client)
        sku_code = f"PCB-{uuid.uuid4().hex[:8].upper()}"
        r = await client.post(
            "/api/v1/skus",
            json={"sku_code": sku_code, "name": "PCB cache product", "unit": "piece"},
            headers=headers,
        )
        assert r.status_code == 201, r.text[:300]
        await client.post(
            "/api/v1/inventory/adjust",
            json={"sku_code": sku_code, "quantity": 50, "reason": "stocktake"},
            headers=headers,
        )
        invite = await client.post(
            "/api/v1/invitations",
            json={"retailer_phone": "+256700pcbcache"},
            headers=headers,
        )
        assert invite.status_code == 201, invite.text[:300]
        reg = await client.post(
            "/api/v1/retailers/register",
            json={
                "invitation_code": invite.json()["data"]["code"],
                "phone": "+256700pcbcache",
                "email": "pcb-cache@example.com",
                "name": "PCB cache retailer",
            },
        )
        assert reg.status_code == 201, reg.text[:300]
        retailer_id = reg.json()["data"]["retailer"]["id"]
        sku_id = await _sku_id(client, headers, sku_code)
        from tests.release_critical_journeys.test_cached_replay_authority import (
            _s1_order_body, _s1_prices,
        )
        await _s1_prices(client, headers, retailer_id, sku_id, "1000.00")
        order_body = await _s1_order_body(
            client, headers, retailer_id, [{"sku_code": sku_code, "quantity": 5}],
        )
        order = await client.post(
            "/api/v1/orders",
            json=order_body,
            headers={**headers, "X-Idempotency-Key": "pcb-create-" + uuid.uuid4().hex},
        )
        assert order.status_code == 201, order.text[:300]
        order_id = order.json()["data"]["id"]
        await client.post(f"/api/v1/orders/{order_id}/confirm", headers=headers)

        key = "pcb-cache-" + uuid.uuid4().hex[:12]
        pay_headers = {**headers, "X-Idempotency-Key": key}
        first = await client.post(
            f"/api/v1/orders/{order_id}/pay",
            json={"method": "cash", "amount": "5000.00"},
            headers=pay_headers,
        )
        assert first.status_code == 200, first.text[:300]
        replay = await client.post(
            f"/api/v1/orders/{order_id}/pay",
            json={"method": "cash", "amount": "5000.00"},
            headers=pay_headers,
        )
        assert replay.status_code == 200, replay.text[:300]
        assert replay.headers.get("X-Idempotency-Replayed") == "true", (
            "cache premise NOT established: replay was not served by the "
            f"idempotency cache (headers={dict(replay.headers)})"
        )
        assert replay.json() == first.json(), "cached body must equal first body"


async def _native_login(client) -> dict:
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert login.status_code == 200, login.text[:300]
    identity = login.json()["data"]["access_token"]
    select = await client.post(
        "/api/v1/auth/select-tenant",
        json={"tenant_id": TENANT_ID},
        headers={"Authorization": f"Bearer {identity}"},
    )
    assert select.status_code == 200, select.text[:300]
    return {"Authorization": f"Bearer {select.json()['data']['access_token']}"}


async def _sku_id(client, headers, sku_code: str) -> str:
    resp = await client.get(f"/api/v1/skus/{sku_code}", headers=headers)
    assert resp.status_code == 200, resp.text[:300]
    return resp.json()["data"]["id"]


@pytest.mark.asyncio
async def test_cached_mutation_replay_after_user_deactivation__cache_accounting(
    probe, asgi_client, independent_db
):
    """CTO F-06 targeted negative control. Premise is proven by the
    positive-control node above (same middleware, same cache). Here:
    create a second admin-capable user, warm a cached 2xx mutation under
    that user's token, deactivate the user through the product path
    (DELETE /users/{id}), verify the deactivation is committed via direct
    DB, then replay the SAME unexpired token/key/body. Expected: current
    authentication denial (401/403), never the cached old 2xx; the
    persisted economic projection must be unchanged."""
    _reset_probe(probe)
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        admin = await _native_login(client)
        email = f"pcb-revoked-{uuid.uuid4().hex[:8]}@example.com"
        password = secrets.token_urlsafe(32)
        created = await client.post(
            "/api/v1/users",
            json={
                "email": email,
                "password": password,
                "full_name": "PCB Revoked User",
            },
            headers=admin,
        )
        assert created.status_code == 201, created.text[:300]
        user_id = created.json()["data"]["id"]
        admin_role_id = await independent_db.fetchval(
            f"SELECT id FROM {TENANT_SCHEMA}.roles WHERE name = 'admin' LIMIT 1"
        )
        assert admin_role_id is not None
        assigned = await client.put(
            f"/api/v1/users/{user_id}/roles",
            json={"role_ids": [str(admin_role_id)]},
            headers=admin,
        )
        assert assigned.status_code == 200, assigned.text[:300]

        login = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": password}
        )
        assert login.status_code == 200, login.text[:300]
        identity = login.json()["data"]["access_token"]
        select = await client.post(
            "/api/v1/auth/select-tenant",
            json={"tenant_id": TENANT_ID},
            headers={"Authorization": f"Bearer {identity}"},
        )
        assert select.status_code == 200, select.text[:300]
        user_headers = {"Authorization": f"Bearer {select.json()['data']['access_token']}"}

        body = {"sku_code": f"PCBREV{uuid.uuid4().hex[:8].upper()}", "name": "rev target", "unit": "piece"}
        key = "pcb-rev-target-" + uuid.uuid4().hex[:10]
        kh = {**user_headers, "X-Idempotency-Key": key}
        first = await client.post("/api/v1/skus", json=body, headers=kh)
        assert first.status_code == 201, first.text[:300]
        cached = await client.post("/api/v1/skus", json=body, headers=kh)
        assert cached.headers.get("X-Idempotency-Replayed") == "true", (
            "premise failed: cache not hot for this key"
        )

        deactivated = await client.delete(f"/api/v1/users/{user_id}", headers=admin)
        assert deactivated.status_code in (200, 204), deactivated.text[:300]
        for _ in range(20):
            row = await independent_db.fetchrow(
                f"SELECT is_deleted, is_active FROM {TENANT_SCHEMA}.users WHERE id = $1",
                uuid.UUID(user_id),
            )
            if row and bool(row["is_deleted"]):
                break
            await asyncio.sleep(0.5)
        assert row is not None and bool(row["is_deleted"]), (
            "deactivation not committed before replay — precondition unmet"
        )

        replayed = await client.post("/api/v1/skus", json=body, headers=kh)
        assert replayed.status_code in (401, 403), (
            "REVOKED user's cached mutation replayed a success response: "
            f"{replayed.status_code} {replayed.text[:200]} "
            "(X-Idempotency-Replayed="
            f"{replayed.headers.get('X-Idempotency-Replayed')})"
        )
        dupes = await independent_db.fetch(
            f"SELECT id FROM {TENANT_SCHEMA}.skus WHERE sku_code = $1",
            body["sku_code"],
        )
        assert len(dupes) == 1, f"economic projection changed on replay: {dupes}"
