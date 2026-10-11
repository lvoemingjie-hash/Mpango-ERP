"""Six predeclared S1/live-cache combination nodes over real JWT and PG."""
import asyncio
import hashlib
import json
import uuid

import pytest
from sqlalchemy import event, text

from tests.s1_pricing_quote.test_http import headers, preview, selection, submit

pytestmark = pytest.mark.asyncio
COMMIT_FAILURE = "INTEGRATION_S1_OWNED_COMMIT_FAILURE_9ac2"


def cache_for(http):
    from api.middleware.auth import AuthenticationMiddleware
    from api.middleware.idempotency import IdempotencyMiddleware
    from auth.strategies.jwt import JwtAuthStrategy

    app = http._transport.app
    assert isinstance(app.state.auth_strategy, JwtAuthStrategy), "INTEGRATION_REAL_JWT_STRATEGY"
    current, cache, auth = app.middleware_stack, None, None
    visited = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        if isinstance(current, IdempotencyMiddleware):
            cache = current
        if isinstance(current, AuthenticationMiddleware):
            auth = current
        current = getattr(current, "app", None)
    assert cache is not None and auth is not None, "INTEGRATION_REAL_MIDDLEWARE_STACK"
    assert auth._strategy is app.state.auth_strategy, "INTEGRATION_SINGLE_CONFIGURED_AUTHORITY"
    return cache


async def vector(world):
    """Persisted economics and S1's retained snapshot/intent audit fields."""
    result = {}
    async with world["session"]() as db:
        for table in ("orders", "order_items", "inventory_stocks", "inventory_reservations",
                      "inventory_movements", "order_credit_holds", "payments", "ledger_entries"):
            rows = (await db.execute(text(
                f"SELECT to_jsonb(row) FROM {table} row ORDER BY row.id"
            ))).scalars().all()
            result[table] = rows
        result["binding"] = (await db.execute(text(
            "SELECT outstanding_balance::text "
            "FROM public.wholesaler_retailer_bindings WHERE wholesaler_id=:wid AND retailer_id=:rid"
        ), {"wid": uuid.UUID(world["wid"]), "rid": uuid.UUID(world["rid"])})).all()
    return result


@pytest.mark.parametrize("client", [False, True], ids=["merchant", "client"])
async def test_create_cache_and_binding_revocation(r1_client, world, client):
    quote = await preview(r1_client, world, client=client)
    key = "integration-create-" + uuid.uuid4().hex
    before = await vector(world)
    first = await submit(r1_client, world, quote, client=client, key=key)
    assert first.status_code == 201, "INTEGRATION_FIRST_S1_CREATE"
    assert first.headers.get("X-Idempotency-Replayed") is None
    cache_for(r1_client)
    committed = await vector(world)
    assert len(committed["orders"]) == len(committed["order_items"]) == 1
    for field in ("inventory_stocks", "inventory_reservations", "inventory_movements",
                  "order_credit_holds", "payments", "ledger_entries", "binding"):
        assert committed[field] == before[field], "INTEGRATION_DRAFT_ZERO_ECONOMIC_WRITE"
    hot = await submit(r1_client, world, quote, client=client, key=key)
    after_hot = await vector(world)
    assert hot.status_code == 201 and hot.json() == first.json()
    assert hot.headers.get("X-Idempotency-Replayed") == "true", "INTEGRATION_REAL_CREATE_CACHE_HIT"
    assert after_hot == committed, "INTEGRATION_REPLAY_ZERO_EFFECT_INCLUDING_SNAPSHOT_AUDIT"
    async with world["session"]() as db:
        await db.execute(text(
            "UPDATE public.wholesaler_retailer_bindings SET status='inactive' "
            "WHERE wholesaler_id=:wid AND retailer_id=:rid"
        ), {"wid": uuid.UUID(world["wid"]), "rid": uuid.UUID(world["rid"])})
        await db.commit()
    revoked = await submit(r1_client, world, quote, client=client, key=key)
    after_revoke = await vector(world)
    assert revoked.status_code == 403, "INTEGRATION_REVOKED_BINDING_NEVER_CACHED_SUCCESS"
    assert revoked.headers.get("X-Idempotency-Replayed") is None
    assert after_revoke == committed, "INTEGRATION_REVOKED_CREATE_ZERO_EFFECT"


async def test_cached_create_rechecks_live_subject(r1_client, world):
    quote = await preview(r1_client, world)
    key = "integration-subject-" + uuid.uuid4().hex
    first = await submit(r1_client, world, quote, key=key)
    assert first.status_code == 201
    hot = await submit(r1_client, world, quote, key=key)
    assert hot.headers.get("X-Idempotency-Replayed") == "true", "INTEGRATION_SUBJECT_CACHE_PREMISE"
    before = await vector(world)
    async with world["session"]() as db:
        await db.execute(text("UPDATE users SET is_deleted=true WHERE id=:id"),
                         {"id": uuid.UUID(world["actor"])})
        await db.commit()
    denied = await submit(r1_client, world, quote, key=key)
    after = await vector(world)
    assert denied.status_code == 401, "INTEGRATION_DELETED_SUBJECT_NEVER_CACHED_SUCCESS"
    assert denied.json()["code"] == "USER_DELETED"
    assert denied.headers.get("X-Idempotency-Replayed") is None
    assert after == before, "INTEGRATION_SUBJECT_REJECTION_ZERO_EFFECT"


async def test_cached_create_preserves_intent_and_quote_ownership(r1_client, world):
    quote = await preview(r1_client, world)
    key = "integration-intent-" + uuid.uuid4().hex
    first = await submit(r1_client, world, quote, key=key)
    assert first.status_code == 201
    hot = await submit(r1_client, world, quote, key=key)
    assert hot.headers.get("X-Idempotency-Replayed") == "true"
    before = await vector(world)
    changed = await submit(r1_client, world, quote, key=key, notes="different accepted intent")
    assert changed.status_code == 409
    assert changed.json()["code"] == "ORDER_CREATE_IDEMPOTENCY_CONFLICT"
    assert changed.headers.get("X-Idempotency-Replayed") is None
    other = uuid.uuid4()
    async with world["session"]() as db:
        await db.execute(text("INSERT INTO public.retailers(id,phone,name) VALUES(:id,:phone,'Integration other')"),
                         {"id": other, "phone": "+256" + str(other.int)[:12]})
        await db.execute(text(
            "INSERT INTO public.wholesaler_retailer_bindings(wholesaler_id,retailer_id,status,outstanding_balance) "
            "VALUES(:wid,:rid,'active',0)"
        ), {"wid": uuid.UUID(world["wid"]), "rid": other})
        await db.commit()
    wrong_owner = await r1_client.post("/api/v1/orders", json={
        "retailer_id": str(other), "items": selection(world), "quote_token": quote["quote_token"],
        "notes": "S1",
    }, headers=headers(world, key=key))
    after = await vector(world)
    assert wrong_owner.status_code == 409 and wrong_owner.json()["code"] == "QUOTE_CONTEXT_CHANGED"
    assert wrong_owner.headers.get("X-Idempotency-Replayed") is None
    assert after == before, "INTEGRATION_INTENT_AND_QUOTE_REJECTION_ZERO_EFFECT"


@pytest.mark.parametrize("mode", ["barrier", "failure"])
async def test_s1_commit_publication(r1_client, world, monkeypatch, mode):
    import database.session as ds
    from models.order import Order

    quote = await preview(r1_client, world)
    body = {"retailer_id": world["rid"], "items": selection(world),
            "quote_token": quote["quote_token"], "notes": "commit boundary"}
    key = "integration-commit-" + uuid.uuid4().hex
    cache = cache_for(r1_client)
    # Match HTTPX's native JSON bytes, rather than substituting a cache key.
    raw = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode()
    cache_key = cache._make_cache_key(
        idempotency_key=key, tenant_schema=world["schema"], user_id=world["actor"],
        method="POST", path="/api/v1/orders", body_hash=hashlib.sha256(raw).hexdigest(),
    )
    before = await vector(world)
    entered, release = asyncio.Event(), asyncio.Event()
    trace, failed = [], []
    real_factory = ds.AsyncSessionLocal

    def instrumented_factory():
        session = real_factory()
        state = {"writes_order": False}

        @event.listens_for(session.sync_session, "after_flush")
        def flushed(sync, _context):
            state["writes_order"] = state["writes_order"] or any(
                isinstance(obj, Order) for obj in sync.new
            )

        real_commit = session.commit

        async def commit():
            if not state["writes_order"]:
                return await real_commit()
            trace.append("write_commit_begin")
            entered.set()
            if mode == "failure" and not failed:
                failed.append(COMMIT_FAILURE)
                raise RuntimeError(COMMIT_FAILURE)
            await release.wait()
            result = await real_commit()
            trace.append("write_commit_end")
            return result

        session.commit = commit
        return session

    monkeypatch.setattr(ds, "AsyncSessionLocal", instrumented_factory)
    task = asyncio.create_task(r1_client.post(
        "/api/v1/orders", content=raw, headers=headers(world, key=key),
    ))
    try:
        await asyncio.wait_for(entered.wait(), 30)
        if mode == "barrier":
            assert not task.done(), "INTEGRATION_NO_SUCCESS_BEFORE_REAL_COMMIT"
            pending = await cache._store.get(cache_key)
            assert pending is not None and pending["in_progress"] is True
            assert "body" not in pending, "INTEGRATION_NO_COMPLETED_CACHE_BEFORE_COMMIT"
            assert await vector(world) == before, "INTEGRATION_UNCOMMITTED_WRITE_NOT_VISIBLE"
            release.set()
            first = await asyncio.wait_for(task, 30)
            assert first.status_code == 201 and trace == ["write_commit_begin", "write_commit_end"]
            committed = await vector(world)
            assert len(committed["orders"]) == 1, "INTEGRATION_COMMIT_INDEPENDENT_VISIBILITY"
        else:
            with pytest.raises(RuntimeError, match="^" + COMMIT_FAILURE + "$"):
                await asyncio.wait_for(task, 30)
            assert failed == [COMMIT_FAILURE] and trace == ["write_commit_begin"]
            assert await cache._store.get(cache_key) is None, "INTEGRATION_FAILED_COMMIT_NO_CACHE_OR_MARKER"
            assert await vector(world) == before, "INTEGRATION_FAILED_COMMIT_ZERO_COMMITTED_EFFECT"
            release.set()
            first = await r1_client.post("/api/v1/orders", content=raw, headers=headers(world, key=key))
            assert first.status_code == 201, "INTEGRATION_FAILED_COMMIT_SAME_INTENT_REMAINS_AVAILABLE"
            committed = await vector(world)
        hot = await r1_client.post("/api/v1/orders", content=raw, headers=headers(world, key=key))
        assert hot.status_code == 201 and hot.json() == first.json()
        assert hot.headers.get("X-Idempotency-Replayed") == "true", "INTEGRATION_POST_COMMIT_REAL_CACHE"
        assert await vector(world) == committed, "INTEGRATION_POST_COMMIT_REPLAY_ZERO_EFFECT"
    finally:
        release.set()
        if not task.done():
            try:
                await asyncio.wait_for(asyncio.shield(task), 5)
            except asyncio.TimeoutError:
                task.cancel()
        await asyncio.gather(task, return_exceptions=True)
