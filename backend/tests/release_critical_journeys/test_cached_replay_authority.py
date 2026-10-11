"""
Cached-replay real-time authority controls (R1, 2026-10-10).

Task: CTO-AUTH-MPANGO-CACHED-REPLAY-AUTHORITY-R1-20261010.
Closes CTO finding F-06 on the R1 commit-boundary candidate: a deactivated
user with an unexpired token could previously retrieve a hot cached success
response by replaying the same key/body/path, because the idempotency
middleware sat OUTSIDE authentication and its hit path never reached the
live account/tenant/route-permission checks.

Fix under test (product bytes, not test doubles):
- IdempotencyMiddleware remains outside AuthenticationMiddleware for
  post-commit publication. Hits use that app's configured real strategy
  to recheck current account/tenant state and JWT validity.
- On a cache hit the middleware re-executes the MATCHED ROUTE'S OWN declared
  authority dependencies (RequirePermission / RequirePlatformAdmin instances)
  against the freshly loaded tenant user before serving the old body. A
  refusal withholds the cache and falls through to the real stack, where the
  identical refusal happens in FastAPI's dependency pipeline BEFORE the
  handler — zero business writes on any refused replay.

Node inventory (10): B.1 legal replay single effect with full vectors;
B.2 account soft-delete revocation; B.3 permission withdrawal (kills
auth-outer-only partial fixes); B.4a tenant suspension (registered task-SQL
construction, restored in finally); B.4b other-subject same-key isolation;
B.4c cross-tenant key isolation (real second tenant via the product
TenantProvisioningService — registered construction: the provisioned owner
cannot log in, so isolation is proven on the middleware's own key function
with both real resolved identities); B.6 concurrent same-key single
economic effect; B.7a-public and B.7a-pay commit-barrier cache visibility;
B.7b commit failure leaves no replayable cache and no stuck marker.

Post-state evidence for every rejection control is captured BEFORE the final
assertions (or in finally), per CTO E-02.
"""
from __future__ import annotations

import asyncio
import os
import secrets
import time
import uuid
from decimal import Decimal

import asyncpg
import httpx
import pytest
import pytest_asyncio
from sqlalchemy import event

os.environ.setdefault("MPANGO_ENV", "staging")

TENANT_ID = "550e8400-e29b-41d4-a716-446655440000"
TENANT_SCHEMA = "t_550e8400e29b41d4a716446655440000"
ADMIN_EMAIL = "admin@test.com"
ADMIN_PASSWORD = os.environ.get("MPANGO_TEST_ADMIN_PASSWORD", "")
BASE_URL = os.environ.get("PCB_RUNTIME_BASE_URL", "http://127.0.0.1:58410")
DB_URL = os.environ.get("TEST_DATABASE_URL", "")

INJECTED = "CRA_INJECTED_COMMIT_FAILURE_MARKER_3d9"

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not (ADMIN_PASSWORD and BASE_URL and DB_URL),
        reason="cached-replay authority evidence requires "
        "MPANGO_TEST_ADMIN_PASSWORD, PCB_RUNTIME_BASE_URL, TEST_DATABASE_URL",
    ),
]


# ---------------------------------------------------------------------------
# Shared native-HTTP helpers (real server, real JWT, no token forgery)
# ---------------------------------------------------------------------------

async def _login(client: httpx.AsyncClient, email: str, password: str) -> dict:
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert resp.status_code == 200, f"login failed: {resp.status_code} {resp.text[:200]}"
    identity = resp.json()["data"]["access_token"]
    select = await client.post(
        "/api/v1/auth/select-tenant",
        json={"tenant_id": TENANT_ID},
        headers={"Authorization": f"Bearer {identity}"},
    )
    assert select.status_code == 200, f"select-tenant failed: {select.status_code}"
    return {"Authorization": f"Bearer {select.json()['data']['access_token']}"}


async def _admin(client: httpx.AsyncClient) -> dict:
    return await _login(client, ADMIN_EMAIL, ADMIN_PASSWORD)


async def _s1_prices(client, headers, retailer_id, sku_id, price):
    """Prepare the current S1 base/revision contract through real HTTP."""
    base = await client.put(
        f"/api/v1/pricing/base-prices/{sku_id}",
        json={"price": price, "expected_revision": 0}, headers=headers,
    )
    assert base.status_code == 200, "INTEGRATION_S1_BASE_PRICE_PREPARATION"
    revision = base.json()["data"]["pricing_revision"]
    override = await client.put(
        "/api/v1/pricing/prices",
        json={"retailer_id": retailer_id, "sku_id": sku_id,
              "price": price, "expected_revision": revision}, headers=headers,
    )
    assert override.status_code == 200, "INTEGRATION_S1_VERSIONED_PRICE_PREPARATION"


async def _s1_order_body(client, headers, retailer_id, items):
    body = {"retailer_id": retailer_id, "items": items}
    quote = await client.post("/api/v1/orders/quote", json=body, headers=headers)
    assert quote.status_code == 200, "INTEGRATION_S1_QUOTE_PREPARATION"
    return {**body, "quote_token": quote.json()["data"]["quote_token"]}


async def _create_user_with_role(
    client: httpx.AsyncClient, admin: dict, db: asyncpg.Connection, role: str
) -> tuple[str, str, str]:
    """Product path: create user, assign role, login. Returns (id, email, password)."""
    email = f"cra-user-{uuid.uuid4().hex[:8]}@example.com"
    password = secrets.token_urlsafe(32)
    created = await client.post(
        "/api/v1/users",
        json={"email": email, "password": password, "full_name": "CRA Operator"},
        headers=admin,
    )
    assert created.status_code == 201, created.text[:300]
    user_id = created.json()["data"]["id"]
    role_id = await db.fetchval(
        f"SELECT id FROM {TENANT_SCHEMA}.roles WHERE name = $1 LIMIT 1", role
    )
    assert role_id is not None
    assigned = await client.put(
        f"/api/v1/users/{user_id}/roles",
        json={"role_ids": [str(role_id)]},
        headers=admin,
    )
    assert assigned.status_code == 200, assigned.text[:300]
    return user_id, email, password


async def _journey_to_confirmed_order(
    client: httpx.AsyncClient, admin: dict, tag: str, price: str = "1000.00", qty: int = 10
) -> tuple[str, str]:
    """SKU -> stock -> invitation -> register -> price -> order -> confirm."""
    sku_code = f"CRA-{tag}-{uuid.uuid4().hex[:8].upper()}"
    r = await client.post(
        "/api/v1/skus",
        json={"sku_code": sku_code, "name": f"CRA product {tag}", "unit": "piece"},
        headers=admin,
    )
    assert r.status_code == 201, r.text[:300]
    sku_id = (await client.get(f"/api/v1/skus/{sku_code}", headers=admin)).json()["data"]["id"]
    stock = await client.post(
        "/api/v1/inventory/adjust",
        json={"sku_code": sku_code, "quantity": 100, "reason": "stocktake"},
        headers=admin,
    )
    assert stock.status_code == 200, stock.text[:300]
    phone = f"+256733{uuid.uuid4().hex[:6]}"
    invite = await client.post(
        "/api/v1/invitations", json={"retailer_phone": phone}, headers=admin
    )
    assert invite.status_code == 201, invite.text[:300]
    reg = await client.post(
        "/api/v1/retailers/register",
        json={
            "invitation_code": invite.json()["data"]["code"],
            "phone": phone,
            "email": f"cra-{tag}-{uuid.uuid4().hex[:8]}@example.com",
            "name": f"CRA Retailer {tag}",
        },
    )
    assert reg.status_code == 201, reg.text[:300]
    retailer_id = reg.json()["data"]["retailer"]["id"]
    await _s1_prices(client, admin, retailer_id, sku_id, price)
    order_body = await _s1_order_body(client, admin, retailer_id,
                                    [{"sku_code": sku_code, "quantity": qty}])
    order = await client.post(
        "/api/v1/orders",
        json=order_body,
        headers={**admin, "X-Idempotency-Key": "cra-create-" + uuid.uuid4().hex},
    )
    assert order.status_code == 201, order.text[:300]
    order_id = order.json()["data"]["id"]
    confirm = await client.post(f"/api/v1/orders/{order_id}/confirm", headers=admin)
    assert confirm.status_code == 200, confirm.text[:300]
    return order_id, retailer_id


async def _pay_vectors(db: asyncpg.Connection, order_id: str) -> dict:
    """Full persisted write-set vectors for a cash payment on the order."""
    oid = uuid.UUID(order_id)
    payments = await db.fetch(
        "SELECT id, amount::text, method, status, idempotency_key, receipt_number "
        f"FROM {TENANT_SCHEMA}.payments WHERE order_id = $1 ORDER BY id", oid)
    ledger = await db.fetch(
        "SELECT id, amount::text, entry_version FROM ledger_entries "
        f"WHERE reference_id = $1 ORDER BY id", oid)
    order = await db.fetchrow(
        f"SELECT status, total_amount::text FROM {TENANT_SCHEMA}.orders WHERE id = $1", oid)
    holds = await db.fetch(
        f"SELECT id, status::text, amount::text, remaining_amount::text "
        f"FROM {TENANT_SCHEMA}.order_credit_holds WHERE order_id = $1 ORDER BY id", oid)
    return {
        "payments": [tuple(r) for r in payments],
        "ledger": [tuple(r) for r in ledger],
        "order": (order["status"], order["total_amount"]) if order else None,
        "holds": [tuple(r) for r in holds],
    }


async def _db() -> asyncpg.Connection:
    """App-role connection with the tenant schema first on search_path."""
    conn = await asyncpg.connect(DB_URL)
    await conn.execute(f"SET search_path TO {TENANT_SCHEMA}, public")
    return conn


async def _post_tolerant(client: httpx.AsyncClient, url: str, **kw):
    """POST that captures both a returned response and a propagated
    in-progress conflict. The product's idempotency middleware signals a
    concurrent same-key request by RAISING HTTPException(409) (pre-existing
    behaviour, unchanged here); through BaseHTTPMiddleware that surfaces as a
    server error rather than a 409 response. Either shape is 'no success
    visible'; only a 2xx/replay would violate the control."""
    try:
        resp = await client.post(url, **kw)
        return resp.status_code, dict(resp.headers), resp.text
    except Exception as exc:
        return None, {}, f"{type(exc).__name__}: {exc}"


async def _pay(client: httpx.AsyncClient, headers: dict, order_id: str, amount: str, key: str):
    return await client.post(
        f"/api/v1/orders/{order_id}/pay",
        json={"method": "cash", "amount": amount},
        headers={**headers, "X-Idempotency-Key": key},
    )


# ---------------------------------------------------------------------------
# B.1 — active subject legal cache replay: one economic effect, full vectors
# ---------------------------------------------------------------------------

async def test_active_subject_legal_replay_single_effect_full_vectors():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        admin = await _admin(client)
        order_id, _retailer = await _journey_to_confirmed_order(client, admin, "b1")
        key = "cra-b1-" + uuid.uuid4().hex[:12]
        conn = await _db()
        try:
            first = await _pay(client, admin, order_id, "10000.00", key)
            assert first.status_code == 200, first.text[:300]
            assert first.headers.get("X-Idempotency-Replayed") is None
            before = await _pay_vectors(conn, order_id)
            assert len(before["payments"]) == 1 and before["order"][0] == "paid"
            payment_id = first.json()["data"]["payment_id"]

            replay = await _pay(client, admin, order_id, "10000.00", key)
            after = await _pay_vectors(conn, order_id)
            # Post-state evidence captured BEFORE the final assertions.
            assert replay.status_code == 200, replay.text[:300]
            assert replay.headers.get("X-Idempotency-Replayed") == "true", dict(replay.headers)
            assert replay.json()["data"]["payment_id"] == payment_id
            assert after == before, f"replay changed vectors: {before} -> {after}"
        finally:
            await conn.close()


# ---------------------------------------------------------------------------
# B.2 — account soft-delete: old token + hot key must be live-denied
# ---------------------------------------------------------------------------

async def test_replay_after_user_deactivation_denied():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        admin = await _admin(client)
        conn = await _db()
        try:
            user_id, email, password = await _create_user_with_role(
                client, admin, conn, "admin"
            )
            user = await _login(client, email, password)
            body = {"sku_code": f"CRADEL{uuid.uuid4().hex[:8].upper()}",
                    "name": "cra del target", "unit": "piece"}
            key = "cra-del-" + uuid.uuid4().hex[:12]
            kh = {**user, "X-Idempotency-Key": key}
            first = await client.post("/api/v1/skus", json=body, headers=kh)
            assert first.status_code == 201, first.text[:300]
            hot = await client.post("/api/v1/skus", json=body, headers=kh)
            assert hot.headers.get("X-Idempotency-Replayed") == "true", (
                "premise failed: cache not hot"
            )

            # Product path deactivation (DELETE /users/{id}), committed check.
            deactivated = await client.delete(f"/api/v1/users/{user_id}", headers=admin)
            assert deactivated.status_code in (200, 204), deactivated.text[:300]
            row = None
            for _ in range(20):
                row = await conn.fetchrow(
                    f"SELECT is_deleted, is_active FROM {TENANT_SCHEMA}.users WHERE id = $1",
                    uuid.UUID(user_id))
                if row and bool(row["is_deleted"]):
                    break
                await asyncio.sleep(0.5)
            post_user_state = dict(row) if row else None
            replay = await client.post("/api/v1/skus", json=body, headers=kh)
            dupes = await conn.fetch(
                f"SELECT id FROM {TENANT_SCHEMA}.skus WHERE sku_code = $1", body["sku_code"])
            # Post-state evidence (E-02) captured BEFORE the final assertions.
            assert post_user_state is not None and bool(post_user_state["is_deleted"]), (
                f"deactivation not committed: {post_user_state}"
            )
            assert replay.status_code in (401, 403), (
                f"deactivated replay served: {replay.status_code} "
                f"replayed={replay.headers.get('X-Idempotency-Replayed')} {replay.text[:150]}"
            )
            assert len(dupes) == 1, f"economic projection changed: {dupes}"
        finally:
            await conn.close()


# ---------------------------------------------------------------------------
# B.3 — permission withdrawal: account+tenant still active, role removed
# ---------------------------------------------------------------------------

async def test_permission_withdrawal_denied_with_account_and_tenant_active():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        admin = await _admin(client)
        conn = await _db()
        try:
            user_id, email, password = await _create_user_with_role(
                client, admin, conn, "admin"
            )
            user = await _login(client, email, password)
            body = {"sku_code": f"CRAPERM{uuid.uuid4().hex[:8].upper()}",
                    "name": "cra perm target", "unit": "piece"}
            key = "cra-perm-" + uuid.uuid4().hex[:12]
            kh = {**user, "X-Idempotency-Key": key}
            first = await client.post("/api/v1/skus", json=body, headers=kh)
            assert first.status_code == 201, first.text[:300]
            hot = await client.post("/api/v1/skus", json=body, headers=kh)
            assert hot.headers.get("X-Idempotency-Replayed") == "true", "cache not hot"

            # Product path permission withdrawal via the roles entry point:
            # swap the user's role from the permission-granting role to a real
            # product role that does NOT carry ``skus:create`` — the account
            # and tenant stay active, only the current permission is withdrawn.
            operator_role_id = await conn.fetchval(
                f"SELECT id FROM {TENANT_SCHEMA}.roles WHERE name = 'retailer_operator' LIMIT 1")
            assert operator_role_id is not None
            stripped = await client.put(
                f"/api/v1/users/{user_id}/roles",
                json={"role_ids": [str(operator_role_id)]}, headers=admin)
            assert stripped.status_code == 200, stripped.text[:300]
            roles_now = None
            for _ in range(20):
                roles_now = await conn.fetch(
                    "SELECT ro.name FROM user_roles ur JOIN roles ro ON ro.id = ur.role_id "
                    "WHERE ur.user_id = $1", uuid.UUID(user_id))
                if roles_now and all(r["name"] != "admin" for r in roles_now):
                    break
                await asyncio.sleep(0.5)
            account_state = await conn.fetchrow(
                f"SELECT is_deleted, is_active FROM {TENANT_SCHEMA}.users WHERE id = $1",
                uuid.UUID(user_id))
            tenant_state = await conn.fetchrow(
                "SELECT status, is_deleted FROM public.wholesalers WHERE id = $1",
                uuid.UUID(TENANT_ID))
            skus_before_replay = await conn.fetchval(
                f"SELECT count(*) FROM {TENANT_SCHEMA}.skus WHERE sku_code = $1",
                body["sku_code"])
            replay = await client.post("/api/v1/skus", json=body, headers=kh)
            skus_after_replay = await conn.fetchval(
                f"SELECT count(*) FROM {TENANT_SCHEMA}.skus WHERE sku_code = $1",
                body["sku_code"])
            # Post-state evidence BEFORE final assertions (E-02).
            assert roles_now and all(r["name"] != "admin" for r in roles_now), (
                f"role withdrawal not committed: {roles_now}"
            )
            assert account_state["is_deleted"] is False and account_state["is_active"] is True, (
                f"account must remain active: {dict(account_state)}"
            )
            assert tenant_state["status"] == "active", f"tenant must remain active: {dict(tenant_state)}"
            assert replay.status_code == 403, (
                f"permission-stripped replay served: {replay.status_code} "
                f"replayed={replay.headers.get('X-Idempotency-Replayed')} {replay.text[:150]}"
            )
            assert skus_before_replay == skus_after_replay == 1, (
                f"write on refused replay: {skus_before_replay} -> {skus_after_replay}"
            )
        finally:
            await conn.close()


# ---------------------------------------------------------------------------
# B.4a — tenant suspension: registered task-SQL construction, restored in finally
# ---------------------------------------------------------------------------

async def test_tenant_suspension_denied_registered_construction():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        admin = await _admin(client)
        conn = await _db()
        suspended = False
        try:
            body = {"sku_code": f"CRATEN{uuid.uuid4().hex[:8].upper()}",
                    "name": "cra tenant target", "unit": "piece"}
            key = "cra-ten-" + uuid.uuid4().hex[:12]
            kh = {**admin, "X-Idempotency-Key": key}
            first = await client.post("/api/v1/skus", json=body, headers=kh)
            assert first.status_code == 201, first.text[:300]
            hot = await client.post("/api/v1/skus", json=body, headers=kh)
            assert hot.headers.get("X-Idempotency-Replayed") == "true", "cache not hot"

            # REGISTERED CONSTRUCTION: no product endpoint suspends a
            # wholesaler tenant; the precise task-SQL pre-state is the
            # lifecycle value the product's assert_tenant_active consumes.
            await conn.execute(
                "UPDATE public.wholesalers SET status = 'suspended' WHERE id = $1",
                uuid.UUID(TENANT_ID))
            suspended = True
            state = await conn.fetchrow(
                "SELECT status, is_deleted FROM public.wholesalers WHERE id = $1",
                uuid.UUID(TENANT_ID))
            replay = await client.post("/api/v1/skus", json=body, headers=kh)
            skus_after = await conn.fetchval(
                f"SELECT count(*) FROM {TENANT_SCHEMA}.skus WHERE sku_code = $1",
                body["sku_code"])
            # Post-state evidence BEFORE final assertions.
            assert state["status"] == "suspended", f"suspension not committed: {dict(state)}"
            assert replay.status_code in (401, 403), (
                f"suspended-tenant replay served: {replay.status_code} "
                f"replayed={replay.headers.get('X-Idempotency-Replayed')}"
            )
            assert skus_after == 1, f"write on refused replay: {skus_after}"
        finally:
            if suspended:
                await conn.execute(
                    "UPDATE public.wholesalers SET status = 'active' WHERE id = $1",
                    uuid.UUID(TENANT_ID))
                restored = await conn.fetchval(
                    "SELECT status FROM public.wholesalers WHERE id = $1", uuid.UUID(TENANT_ID))
                assert restored == "active"
            await conn.close()


# ---------------------------------------------------------------------------
# B.4b — another subject, same idempotency key: no cross-subject body, fresh
#        authoritative execution of that subject's own request
# ---------------------------------------------------------------------------

async def test_other_subject_same_key_isolated_fresh_authoritative():
    """Two different live subjects send the SAME X-Idempotency-Key on the same
    route with DIFFERENT bodies. The second subject must not receive the
    first subject's cached response body (middleware key includes the verified
    user/tenant identity), and their own request must execute authoritatively.
    Uses POST /skus (no canonical durable-idempotency authority, unlike
    payments): the subject-specific key is what isolates the two bodies."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        admin = await _admin(client)
        conn = await _db()
        try:
            operator_id, oemail, opassword = await _create_user_with_role(
                client, admin, conn, "admin")
            operator = await _login(client, oemail, opassword)
            shared_key = "cra-b4b-" + uuid.uuid4().hex[:12]
            sku_a = f"CRAB4BA{uuid.uuid4().hex[:6].upper()}"
            sku_b = f"CRAB4BB{uuid.uuid4().hex[:6].upper()}"

            first = await client.post(
                "/api/v1/skus",
                json={"sku_code": sku_a, "name": "b4b subject A", "unit": "piece"},
                headers={**admin, "X-Idempotency-Key": shared_key},
            )
            assert first.status_code == 201, first.text[:300]
            a_body = first.json()

            second = await client.post(
                "/api/v1/skus",
                json={"sku_code": sku_b, "name": "b4b subject B", "unit": "piece"},
                headers={**operator, "X-Idempotency-Key": shared_key},
            )
            rows_a = await conn.fetch(
                f"SELECT sku_code FROM {TENANT_SCHEMA}.skus WHERE sku_code = $1", sku_a)
            rows_b = await conn.fetch(
                f"SELECT sku_code FROM {TENANT_SCHEMA}.skus WHERE sku_code = $1", sku_b)
            # Post-state evidence BEFORE final assertions.
            assert second.status_code == 201, (
                f"subject B's own request was not executed fresh: "
                f"{second.status_code} {second.text[:150]}"
            )
            assert second.headers.get("X-Idempotency-Replayed") is None, (
                "subject B was served subject A's cached response"
            )
            assert second.json() != a_body
            assert second.json()["data"]["sku_code"] == sku_b
            assert len(rows_a) == 1 and len(rows_b) == 1, (
                f"persisted rows A={rows_a} B={rows_b}"
            )
        finally:
            await conn.close()


# ---------------------------------------------------------------------------
# B.4c — cross-tenant key isolation (real second tenant via the product
# TenantProvisioningService; registered construction)
# ---------------------------------------------------------------------------

async def test_cross_tenant_key_isolation_real_second_tenant():
    from datetime import datetime, timezone, timedelta
    import sqlalchemy
    from sqlalchemy import text as sa_text
    from models.tenant_onboarding import TenantRegistration
    from services.tenant_provisioning_service import TenantProvisioningService
    from database.session import AsyncSessionLocal
    from api.middleware.idempotency import IdempotencyMiddleware

    registration_id = None
    provisioned = None
    owner_email = None
    try:
        now = datetime.now(timezone.utc)
        owner_email = f"cra-xtenant-{uuid.uuid4().hex}@example.com"
        registration = TenantRegistration(
            company_name=f"CRA XTenant {uuid.uuid4().hex[:8]}",
            country="KE",
            owner_email=owner_email,
            password_hash="hashed-registration-password",  # pragma: allowlist secret
            status="provisioning",
            email_verified_at=now,
            provisioning_started_at=now,
            expires_at=now + timedelta(hours=1),
        )
        async with AsyncSessionLocal() as session:
            await session.execute(sa_text("SET search_path TO public"))
            session.add(registration)
            await session.commit()
            registration_id = registration.id
        async with AsyncSessionLocal() as session:
            await session.execute(sa_text("SET search_path TO public"))
            result = await TenantProvisioningService(session).provision_wholesaler_and_schema(
                registration_id)
            await session.commit()
        assert result.action == "provisioned" and result.tenant_schema
        provisioned = result

        mw = IdempotencyMiddleware(app=None)  # key function only; no dispatch
        body = b'{"method":"cash","amount":"10000.00"}'
        body_hash = __import__("hashlib").sha256(body).hexdigest()
        shared_key = "cra-xt-" + uuid.uuid4().hex[:10]
        key_a = mw._make_cache_key(
            idempotency_key=shared_key,
            tenant_schema=TENANT_SCHEMA,
            user_id=TENANT_ID,
            method="POST",
            path="/api/v1/orders/x/pay",
            body_hash=body_hash,
        )
        key_b = mw._make_cache_key(
            idempotency_key=shared_key,  # IDENTICAL visible key, other real tenant identity
            tenant_schema=result.tenant_schema,
            user_id=str(result.wholesaler_id),
            method="POST",
            path="/api/v1/orders/x/pay",
            body_hash=body_hash,
        )
        assert key_a != key_b, "cross-tenant cache key collision"
        # The tenant-B identity is resolvable through the product's own
        # tenant-context requirements (schema derives from the real
        # provisioned wholesaler UUID).
        assert result.tenant_schema == "t_" + uuid.UUID(str(result.wholesaler_id)).hex
    finally:
        # Registered construction cleanup: remove the provisioned tenant by
        # exact identities captured above (task-owned rows only).
        if registration_id is not None:
            try:
                async with AsyncSessionLocal() as session:
                    if provisioned is not None and getattr(provisioned, "tenant_schema", None):
                        await session.execute(sa_text(
                            f'DROP SCHEMA IF EXISTS "{provisioned.tenant_schema}" CASCADE'))
                    await session.execute(sa_text(
                        "DELETE FROM public.tenant_registrations WHERE id = :rid"),
                        {"rid": registration_id})
                    if provisioned is not None and getattr(provisioned, "wholesaler_id", None):
                        await session.execute(sa_text(
                            "DELETE FROM public.wholesalers WHERE id = :wid"),
                            {"wid": provisioned.wholesaler_id})
                    await session.commit()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# B.6 — concurrent same-key payments: single economic effect
# ---------------------------------------------------------------------------

async def test_concurrent_same_key_single_economic_effect():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=60.0) as client:
        admin = await _admin(client)
        order_id, _r = await _journey_to_confirmed_order(client, admin, "b6")
        key = "cra-b6-" + uuid.uuid4().hex[:12]
        results = await asyncio.gather(
            _pay(client, admin, order_id, "10000.00", key),
            _pay(client, admin, order_id, "10000.00", key),
            return_exceptions=True,
        )
        conn = await _db()
        try:
            payments = await conn.fetch(
                f"SELECT id, amount::text, status FROM {TENANT_SCHEMA}.payments "
                "WHERE order_id = $1", uuid.UUID(order_id))
            ledger = await conn.fetch(
                "SELECT id FROM ledger_entries WHERE reference_id = $1",
                uuid.UUID(order_id))
            order = await conn.fetchrow(
                f"SELECT status FROM {TENANT_SCHEMA}.orders WHERE id = $1",
                uuid.UUID(order_id))
            total = sum((Decimal(p[1]) for p in payments), Decimal("0"))
            # Post-state BEFORE final assertions.
            outcomes = []
            for r in results:
                if isinstance(r, Exception):
                    outcomes.append(type(r).__name__)
                else:
                    outcomes.append((r.status_code, r.headers.get("X-Idempotency-Replayed")))
            assert len(payments) == 1, f"concurrent same-key produced {len(payments)} payments"
            assert total == Decimal("10000.00"), f"double effect: {total}"
            assert len(ledger) == 2, f"ledger rows: {len(ledger)}"
            assert order["status"] == "paid"
            ok = [o for o in outcomes if not isinstance(o, str) and o[0] == 200]
            assert ok, f"no successful payment among {outcomes}"
            replayed_flags = [o[1] for o in outcomes if not isinstance(o, str)]
            assert any(f == "true" for f in replayed_flags) or len(ok) == 1, (
                f"unexpected outcome shape: {outcomes}"
            )
        finally:
            await conn.close()


# ---------------------------------------------------------------------------
# B.7 — commit barrier / commit failure vs cache publish (in-process probe)
# ---------------------------------------------------------------------------

class CommitProbe:
    def __init__(self):
        self.release = asyncio.Event()
        self.release.set()
        self.fail_next_write_commit = False
        self.failed_marker = None
        self.write_commit_pending = asyncio.Event()

    def arm_barrier(self):
        self.write_commit_pending.clear()  # ignore setup-phase commits
        self.release.clear()

    def release_barrier(self):
        self.release.set()


@pytest.fixture()
def probe_app():
    import database.session as ds
    import main

    probe = CommitProbe()
    real_factory = ds.AsyncSessionLocal
    state = {"dirty": False}

    def factory():
        session = real_factory()

        @event.listens_for(session.sync_session, "after_flush")
        def _mark(sess, ctx):
            state["dirty"] = True

        real_commit = session.commit

        async def observed_commit():
            if not state["dirty"]:
                return await real_commit()
            state["dirty"] = False
            if probe.fail_next_write_commit:
                probe.fail_next_write_commit = False
                probe.failed_marker = INJECTED
                raise RuntimeError(INJECTED)
            probe.write_commit_pending.set()
            await probe.release.wait()
            return await real_commit()

        session.commit = observed_commit  # type: ignore[method-assign]
        return session

    ds.AsyncSessionLocal = factory
    try:
        yield main.app, probe
    finally:
        ds.AsyncSessionLocal = real_factory


@pytest_asyncio.fixture()
async def asgi_with_probe(probe_app):
    app, probe = probe_app
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://cra-asgi.test", timeout=60.0
    ) as client:
        yield client, probe


async def _await_write_commit_or_report(probe, task, probe_label: str):
    """Wait for the first write-carrying commit; if the request finishes
    first, surface its outcome instead of hanging (diagnostic clarity)."""
    event_task = asyncio.create_task(probe.write_commit_pending.wait())
    done, _pending = await asyncio.wait(
        {task, event_task}, timeout=25, return_when=asyncio.FIRST_COMPLETED
    )
    if event_task in done:
        return
    if task in done:
        probe.release_barrier()
        try:
            resp = task.result()
            raise AssertionError(
                f"{probe_label}: first request finished before reaching the "
                f"held write commit: {resp.status_code} {resp.text[:200]}"
            )
        except AssertionError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise AssertionError(
                f"{probe_label}: first request raised before the held commit: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
    probe.release_barrier()
    raise AssertionError(f"{probe_label}: write commit never reached within 25s")


@pytest.mark.asyncio
async def test_commit_barrier_hides_cache_public_route(asgi_with_probe):
    """B.7a (public dimension): while the invitation create's in-route commit
    is held, the same-key request must NOT observe a cached 201; after
    release the cache exists and replays. Kills the publish-before-commit
    mutant (route commit removed => cache written while commit pending)."""
    client, probe = asgi_with_probe
    admin = await _admin(client)
    phone = f"+256744{uuid.uuid4().hex[:6]}"
    body = {"retailer_phone": phone}
    key = "cra-b7a-" + uuid.uuid4().hex[:12]
    kh = {**admin, "X-Idempotency-Key": key}

    probe.arm_barrier()
    task = asyncio.create_task(client.post("/api/v1/invitations", json=body, headers=kh))
    await _await_write_commit_or_report(probe, task, "B.7a-public")
    second_status, second_headers, second_text = await asyncio.wait_for(
        _post_tolerant(client, "/api/v1/invitations", json=body, headers=kh), timeout=20)
    probe.release_barrier()
    first = await asyncio.wait_for(task, timeout=15)
    replay = await client.post("/api/v1/invitations", json=body, headers=kh)
    # Post-state BEFORE final assertions.
    assert second_status is None or second_status == 409, (
        f"while commit pending, second request got {second_status}: {second_text[:150]}"
    )
    assert second_headers.get("X-Idempotency-Replayed") is None
    assert not (second_status is not None and 200 <= second_status < 300), (
        "success was visible while the business commit was still pending"
    )
    assert first.status_code == 201, first.text[:200]
    assert replay.status_code == 201
    assert replay.headers.get("X-Idempotency-Replayed") == "true"
    assert replay.json()["data"]["code"] == first.json()["data"]["code"]


async def test_commit_barrier_hides_cache_pay_route(asgi_with_probe):
    """B.7a (tenant dimension): while finalize's business commit for a payment
    is held, the same-key request must not observe the cached success."""
    client, probe = asgi_with_probe
    admin = await _admin(client)
    order_id, _r = await _journey_to_confirmed_order(client, admin, "b7p")
    key = "cra-b7p-" + uuid.uuid4().hex[:12]
    body = {"method": "cash", "amount": "10000.00"}
    kh = {**admin, "X-Idempotency-Key": key}

    probe.arm_barrier()
    task = asyncio.create_task(
        client.post(f"/api/v1/orders/{order_id}/pay", json=body, headers=kh))
    await _await_write_commit_or_report(probe, task, "B.7a-pay")
    second_status, second_headers, second_text = await asyncio.wait_for(
        _post_tolerant(client, f"/api/v1/orders/{order_id}/pay", json=body, headers=kh),
        timeout=20)
    probe.release_barrier()
    first = await asyncio.wait_for(task, timeout=20)
    assert second_status is None or second_status == 409, (
        f"while pay commit pending, second request got {second_status}: {second_text[:150]}"
    )
    assert second_headers.get("X-Idempotency-Replayed") is None
    assert not (second_status is not None and 200 <= second_status < 300), (
        "success was visible while the pay business commit was still pending"
    )
    assert first.status_code == 200, first.text[:200]
    replay = await client.post(
        f"/api/v1/orders/{order_id}/pay", json=body, headers=kh)
    assert replay.status_code == 200
    assert replay.headers.get("X-Idempotency-Replayed") == "true"


async def test_commit_failure_leaves_no_replayable_cache_and_no_stuck_marker(
    asgi_with_probe,
):
    """B.7b: an injected commit failure must not leave a replayable success
    cache, must not confirm success to the client, and must not leave the
    five-minute in-progress marker blocking a later legitimate request."""
    client, probe = asgi_with_probe
    admin = await _admin(client)
    order_id, _r = await _journey_to_confirmed_order(client, admin, "b7f")
    key = "cra-b7f-" + uuid.uuid4().hex[:12]
    body = {"method": "cash", "amount": "10000.00"}
    kh = {**admin, "X-Idempotency-Key": key}

    probe.fail_next_write_commit = True
    outcome_status = None
    outcome_text = ""
    try:
        resp = await client.post(f"/api/v1/orders/{order_id}/pay", json=body, headers=kh)
        outcome_status = resp.status_code
        outcome_text = resp.text or ""
    except Exception as exc:
        # A real server turns the injected commit failure into a 500 or a
        # reset connection; the in-process ASGI transport may surface it as
        # an exception. Either is fail-closed; a 2xx is not.
        outcome_text = str(exc)
    marker_seen = probe.failed_marker
    conn = await _db()
    try:
        payments_after_failure = await conn.fetch(
            f"SELECT id FROM {TENANT_SCHEMA}.payments WHERE order_id = $1",
            uuid.UUID(order_id))
        # Immediately retry the same key legitimately (failure un-injected).
        retry = await client.post(
            f"/api/v1/orders/{order_id}/pay", json=body, headers=kh)
        payments_after_retry = await conn.fetch(
            f"SELECT id, amount::text FROM {TENANT_SCHEMA}.payments WHERE order_id = $1",
            uuid.UUID(order_id))
        # Post-state BEFORE final assertions.
        assert marker_seen == INJECTED, f"injected reason not observed: {marker_seen}"
        assert outcome_status is None or outcome_status >= 500, (
            f"commit failure surfaced as success: {outcome_status} {outcome_text[:150]}"
        )
        assert "postgresql://" not in outcome_text
        assert len(payments_after_failure) == 0, (
            f"partial payment rows after failed commit: {payments_after_failure}"
        )
        assert retry.status_code == 200, (
            f"legitimate retry blocked by stale marker: {retry.status_code} "
            f"{retry.text[:150]}"
        )
        assert retry.headers.get("X-Idempotency-Replayed") != "true"
        assert len(payments_after_retry) == 1, (
            f"retry produced {len(payments_after_retry)} payments"
        )
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# R2 controls (CTO review F1/F2/F3, 2026-10-10): handler-level authority
# ---------------------------------------------------------------------------

async def _set_user_active(client: httpx.AsyncClient, admin: dict, conn, user_id: str, active: bool) -> None:
    resp = await client.put(
        f"/api/v1/users/{user_id}",
        json={"is_active": active},
        headers=admin,
    )
    assert resp.status_code == 200, resp.text[:300]
    for _ in range(20):
        row = await conn.fetchrow(
            f"SELECT is_active, is_deleted FROM {TENANT_SCHEMA}.users WHERE id = $1",
            uuid.UUID(user_id))
        if row and bool(row["is_active"]) == active:
            return
        await asyncio.sleep(0.5)
    raise AssertionError(f"is_active={active} not committed for {user_id}")


async def test_select_tenant_hot_cache_refused_after_soft_delete():
    """F1+F3 (select-tenant): the handler's authority (target-tenant user
    state) is re-validated at the seam. Warm cache -> replay served; soft-
    delete the user via the product path -> the cached success is NOT served
    AND the fresh handler itself now refuses with 401 USER_DELETED (R3
    unification of the select-tenant product authority with the replay gate
    and the tenant resolver): zero token issuance in any response, repeated
    requests keep the identical refusal (never 409), and a keyless fresh
    request behaves identically. Recovery-after-restore is covered by the
    dedicated skus control below, because the product has no un-delete path
    and PUT /users/{id} {"is_active": ...} currently fails with a
    pre-existing MissingGreenlet defect (registered separately)."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        admin = await _admin(client)
        conn = await _db()
        try:
            user_id, email, password = await _create_user_with_role(
                client, admin, conn, "admin")
            login = await client.post(
                "/api/v1/auth/login", json={"email": email, "password": password})
            assert login.status_code == 200, login.text[:200]
            identity = login.json()["data"]["access_token"]
            body = {"tenant_id": TENANT_ID}
            key = "cra-st-" + uuid.uuid4().hex[:12]
            ih = {"Authorization": f"Bearer {identity}", "X-Idempotency-Key": key}
            first = await client.post("/api/v1/auth/select-tenant", json=body, headers=ih)
            assert first.status_code == 200, first.text[:200]
            hot = await client.post("/api/v1/auth/select-tenant", json=body, headers=ih)
            assert hot.status_code == 200, f"hot probe: {hot.status_code} {hot.text[:150]}"
            assert hot.headers.get("X-Idempotency-Replayed") == "true", "cache not hot"

            deleted = await client.delete(f"/api/v1/users/{user_id}", headers=admin)
            assert deleted.status_code in (200, 204), deleted.text[:200]
            state = None
            for _ in range(20):
                state = await conn.fetchrow(
                    f"SELECT is_active, is_deleted FROM {TENANT_SCHEMA}.users WHERE id = $1",
                    uuid.UUID(user_id))
                if state and bool(state["is_deleted"]):
                    break
                await asyncio.sleep(0.5)
            replay = await client.post("/api/v1/auth/select-tenant", json=body, headers=ih)
            replay2 = await client.post("/api/v1/auth/select-tenant", json=body, headers=ih)
            fresh = await client.post(
                "/api/v1/auth/select-tenant", json=body,
                headers={"Authorization": f"Bearer {identity}"})
            # Post-state BEFORE final assertions.
            assert state is not None and bool(state["is_deleted"]), f"user state: {state}"
            # R3 unified refusal: real rejection (401 USER_DELETED), zero
            # token issuance in ANY response, no cached body, repeat-safe.
            for label, resp in (("replay", replay), ("replay2", replay2), ("fresh", fresh)):
                assert resp.status_code == 401, (
                    f"{label}: expected unified USER_DELETED refusal, got "
                    f"{resp.status_code} {resp.text[:150]}"
                )
                assert resp.headers.get("X-Idempotency-Replayed") is None, (
                    f"{label}: served the cached success body"
                )
                assert "access_token" not in (resp.text or ""), (
                    f"{label}: a token pair was issued for a deleted subject"
                )
                assert "refresh_token" not in (resp.text or "")
            assert '"code":"USER_DELETED"' in replay.text, replay.text[:150]
            assert '"code":"USER_DELETED"' in fresh.text, fresh.text[:150]
        finally:
            await conn.close()


async def test_denied_key_recovery_after_role_restore():
    """F3 recovery on a working product path: warm a cached success under an
    operator identity, strip the role (authentic 403 refusals, repeated, no
    409 marker leak), restore the role through the product entry point, then
    replay the SAME key — the cached success is served again."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        admin = await _admin(client)
        conn = await _db()
        try:
            user_id, email, password = await _create_user_with_role(
                client, admin, conn, "admin")
            operator = await _login(client, email, password)
            body = {"sku_code": f"CRAREC{uuid.uuid4().hex[:8].upper()}",
                    "name": "cra recovery target", "unit": "piece"}
            key = "cra-rec-" + uuid.uuid4().hex[:12]
            kh = {**operator, "X-Idempotency-Key": key}
            first = await client.post("/api/v1/skus", json=body, headers=kh)
            assert first.status_code == 201, first.text[:200]
            hot = await client.post("/api/v1/skus", json=body, headers=kh)
            # A replay returns the ORIGINAL status code (201) with the marker.
            assert hot.status_code == 201, f"hot probe: {hot.status_code} {hot.text[:150]}"
            assert hot.headers.get("X-Idempotency-Replayed") == "true"

            operator_role_id = await conn.fetchval(
                f"SELECT id FROM {TENANT_SCHEMA}.roles WHERE name = 'retailer_operator' LIMIT 1")
            stripped = await client.put(
                f"/api/v1/users/{user_id}/roles",
                json={"role_ids": [str(operator_role_id)]}, headers=admin)
            assert stripped.status_code == 200, stripped.text[:200]
            refused1 = await client.post("/api/v1/skus", json=body, headers=kh)
            refused2 = await client.post("/api/v1/skus", json=body, headers=kh)
            # Post-state BEFORE final assertions.
            assert refused1.status_code == 403, (
                f"stripped replay: {refused1.status_code} "
                f"replayed={refused1.headers.get('X-Idempotency-Replayed')}"
            )
            assert refused1.headers.get("X-Idempotency-Replayed") is None
            assert refused2.status_code == 403, (
                f"repeated refusal degraded to {refused2.status_code} (F3 marker leak)"
            )
            assert refused2.headers.get("X-Idempotency-Replayed") is None

            admin_role_id = await conn.fetchval(
                f"SELECT id FROM {TENANT_SCHEMA}.roles WHERE name = 'admin' LIMIT 1")
            restored = await client.put(
                f"/api/v1/users/{user_id}/roles",
                json={"role_ids": [str(admin_role_id)]}, headers=admin)
            assert restored.status_code == 200, restored.text[:200]
            recovered = await client.post("/api/v1/skus", json=body, headers=kh)
            dupes = await conn.fetch(
                f"SELECT id FROM {TENANT_SCHEMA}.skus WHERE sku_code = $1", body["sku_code"])
            # Post-state BEFORE final assertions. A replay returns the
            # ORIGINAL status code (201) with the marker.
            assert recovered.status_code == 201, (
                f"restored-subject replay blocked: {recovered.status_code} {recovered.text[:150]}"
            )
            assert recovered.headers.get("X-Idempotency-Replayed") == "true", (
                "restored replay must be served from the retained cache entry"
            )
            assert len(dupes) == 1, f"economic projection changed: {dupes}"
        finally:
            await conn.close()


async def test_contextual_refresh_hot_cache_refused_after_soft_delete():
    """F1: the refresh credential travels in the body; the contextual subject
    validator is the live authority. Warm cache -> replay served; soft-delete
    the subject via the product path -> replay returns the authentic 401
    (PRINCIPAL_DELETED family), never the cached token pair."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        admin = await _admin(client)
        conn = await _db()
        try:
            user_id, email, password = await _create_user_with_role(
                client, admin, conn, "admin")
            login = await client.post(
                "/api/v1/auth/login", json={"email": email, "password": password})
            identity = login.json()["data"]["access_token"]
            select = await client.post(
                "/api/v1/auth/select-tenant", json={"tenant_id": TENANT_ID},
                headers={"Authorization": f"Bearer {identity}"})
            assert select.status_code == 200, select.text[:200]
            contextual_refresh = select.json()["data"]["refresh_token"]
            body = {"refresh_token": contextual_refresh}
            key = "cra-rf-" + uuid.uuid4().hex[:12]
            kh = {"X-Idempotency-Key": key}  # no Authorization header by design
            first = await client.post("/api/v1/auth/refresh", json=body, headers=kh)
            assert first.status_code == 200, first.text[:200]
            hot = await client.post("/api/v1/auth/refresh", json=body, headers=kh)
            assert hot.headers.get("X-Idempotency-Replayed") == "true", "cache not hot"

            deleted = await client.delete(f"/api/v1/users/{user_id}", headers=admin)
            assert deleted.status_code in (200, 204), deleted.text[:200]
            state = None
            for _ in range(20):
                state = await conn.fetchrow(
                    f"SELECT is_deleted, is_active FROM {TENANT_SCHEMA}.users WHERE id = $1",
                    uuid.UUID(user_id))
                if state and bool(state["is_deleted"]):
                    break
                await asyncio.sleep(0.5)
            replay = await client.post("/api/v1/auth/refresh", json=body, headers=kh)
            fresh = await client.post("/api/v1/auth/refresh", json=body)
            # Post-state BEFORE final assertions.
            assert state is not None and bool(state["is_deleted"])
            assert replay.status_code == 401, (
                f"deleted-subject refresh replay: {replay.status_code} "
                f"replayed={replay.headers.get('X-Idempotency-Replayed')} {replay.text[:150]}"
            )
            assert replay.headers.get("X-Idempotency-Replayed") is None
            assert fresh.status_code == 401 and fresh.headers.get("X-Idempotency-Replayed") is None
        finally:
            await conn.close()


async def _journey_to_retailer_and_price(
    client: httpx.AsyncClient, admin: dict, tag: str, price: str = "1000.00"
) -> tuple[str, str, str]:
    """SKU -> stock -> invitation -> register -> price (no order).
    Returns (retailer_id, sku_id, sku_code)."""
    sku_code = f"CRA-{tag}-{uuid.uuid4().hex[:8].upper()}"
    r = await client.post(
        "/api/v1/skus",
        json={"sku_code": sku_code, "name": f"CRA product {tag}", "unit": "piece"},
        headers=admin,
    )
    assert r.status_code == 201, r.text[:300]
    sku_id = (await client.get(f"/api/v1/skus/{sku_code}", headers=admin)).json()["data"]["id"]
    stock = await client.post(
        "/api/v1/inventory/adjust",
        json={"sku_code": sku_code, "quantity": 100, "reason": "stocktake"},
        headers=admin,
    )
    assert stock.status_code == 200, stock.text[:300]
    phone = f"+256777{uuid.uuid4().hex[:6]}"
    invite = await client.post(
        "/api/v1/invitations", json={"retailer_phone": phone}, headers=admin)
    assert invite.status_code == 201, invite.text[:300]
    reg = await client.post(
        "/api/v1/retailers/register",
        json={
            "invitation_code": invite.json()["data"]["code"],
            "phone": phone,
            "email": f"cra-{tag}-{uuid.uuid4().hex[:8]}@example.com",
            "name": f"CRA Retailer {tag}",
        },
    )
    assert reg.status_code == 201, reg.text[:300]
    retailer_id = reg.json()["data"]["retailer"]["id"]
    await _s1_prices(client, admin, retailer_id, sku_id, price)
    return retailer_id, sku_id, sku_code


async def _deactivate_binding(client: httpx.AsyncClient, admin: dict, conn, retailer_id: str) -> None:
    resp = await client.post(
        f"/api/v1/retailers/{retailer_id}/deactivate", headers=admin)
    assert resp.status_code == 200, resp.text[:300]
    for _ in range(20):
        row = await conn.fetchrow(
            "SELECT status FROM public.wholesaler_retailer_bindings WHERE retailer_id = $1 "
            "AND is_deleted IS FALSE",
            uuid.UUID(retailer_id))
        if row and row["status"] == "inactive":
            return
        await asyncio.sleep(0.5)
    raise AssertionError(f"binding deactivation not committed for {retailer_id}")


async def test_order_create_binding_revocation_refuses_replay():
    """F2: POST /orders enforces the active binding inside its handler; the
    extracted shared guard now also gates the replay. Valid binding: cached
    replay serves the SAME order (retry contract, single effect). Revoked
    binding: replay and keyless fresh request both get S1's authentic 403 with
    zero new orders."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        admin = await _admin(client)
        conn = await _db()
        try:
            retailer_id, sku_id, sku_code = await _journey_to_retailer_and_price(
                client, admin, "f2o")
            body = await _s1_order_body(client, admin, retailer_id,
                                        [{"sku_code": sku_code, "quantity": 1}])
            key = "cra-ord-" + uuid.uuid4().hex[:12]
            kh = {**admin, "X-Idempotency-Key": key}
            first = await client.post("/api/v1/orders", json=body, headers=kh)
            assert first.status_code == 201, first.text[:300]
            replay = await client.post("/api/v1/orders", json=body, headers=kh)
            orders_now = await conn.fetchval(
                f"SELECT count(*) FROM {TENANT_SCHEMA}.orders WHERE retailer_id = $1",
                uuid.UUID(retailer_id))
            assert replay.status_code == 201
            assert replay.headers.get("X-Idempotency-Replayed") == "true"
            assert replay.json()["data"]["id"] == first.json()["data"]["id"]
            assert orders_now == 1, f"replay created a second order: {orders_now}"

            await _deactivate_binding(client, admin, conn, retailer_id)
            revoked = await client.post("/api/v1/orders", json=body, headers=kh)
            fresh = await client.post("/api/v1/orders", json=body, headers=admin)
            orders_after = await conn.fetchval(
                f"SELECT count(*) FROM {TENANT_SCHEMA}.orders WHERE retailer_id = $1",
                uuid.UUID(retailer_id))
            # Post-state BEFORE final assertions.
            assert revoked.status_code == 403, (
                f"revoked-binding order replay: {revoked.status_code} "
                f"replayed={revoked.headers.get('X-Idempotency-Replayed')} {revoked.text[:150]}"
            )
            assert revoked.headers.get("X-Idempotency-Replayed") is None
            assert fresh.status_code == 403 and fresh.headers.get("X-Idempotency-Replayed") is None
            assert orders_after == 1, f"write on refused replay: {orders_after}"
        finally:
            await conn.close()


async def test_pricing_binding_revocation_refuses_replay():
    """F2: PUT /pricing/prices enforces the binding inside its handler; the
    seam imports the same current S1 guard as the live pricing handler.
    Revoked binding: replay and keyless fresh request are refused; zero price
    writes occur after revocation."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        admin = await _admin(client)
        conn = await _db()
        try:
            retailer_id, sku_id, _sku_code = await _journey_to_retailer_and_price(
                client, admin, "f2p")
            body = {"retailer_id": retailer_id, "sku_id": sku_id,
                    "price": "1000.00", "expected_revision": 2}
            key = "cra-prc-" + uuid.uuid4().hex[:12]
            kh = {**admin, "X-Idempotency-Key": key}
            warm = await client.put("/api/v1/pricing/prices", json=body, headers=kh)
            assert warm.status_code == 200, warm.text[:300]
            hot = await client.put("/api/v1/pricing/prices", json=body, headers=kh)
            assert hot.status_code == 200, (
                f"hot probe hit {hot.status_code} (rate limit?) before the cache "
                f"premise could be established: {hot.text[:150]}"
            )
            assert hot.headers.get("X-Idempotency-Replayed") == "true", "cache not hot"

            await _deactivate_binding(client, admin, conn, retailer_id)
            revoked = await client.put("/api/v1/pricing/prices", json=body, headers=kh)
            fresh = await client.put("/api/v1/pricing/prices", json=body, headers=admin)
            prices = await conn.fetch(
                "SELECT id, price::text, updated_at FROM retailer_prices "
                "WHERE retailer_id = $1 AND sku_id = $2",
                uuid.UUID(retailer_id), uuid.UUID(sku_id))
            # Post-state BEFORE final assertions.
            assert revoked.status_code == 403, (
                f"revoked-binding pricing replay: {revoked.status_code} "
                f"replayed={revoked.headers.get('X-Idempotency-Replayed')} {revoked.text[:150]}"
            )
            assert revoked.headers.get("X-Idempotency-Replayed") is None
            assert fresh.status_code == 403
            assert fresh.headers.get("X-Idempotency-Replayed") is None
            assert len(prices) == 1, f"price rows after revocation: {prices}"
        finally:
            await conn.close()
