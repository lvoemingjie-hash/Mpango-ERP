"""
Release-critical journey cluster C1: real-path overpayment rejection and
single economic effect over REAL HTTP.

Evidence task: CTO-AUTH-MPANGO-BASELINE-FINITE-RELEASE-EVIDENCE-R1-20261010.
Task-owned evidence per directive section 5: this file (and its directory)
is the only backend addition; it changes no product code and no existing
test.

It closes the disposition gap of the xfailed node
tests/test_phase5_order_payment.py::TestRouteLevelOrderPaymentMonkeypatch::test_route_overpayment_rejected_with_400
whose unit-level "overpayment checks" are pure arithmetic assertions that
invoke no product code. Here the exact same business risk is driven through
the real stack: uvicorn + real JwtAuthStrategy (MPANGO_ENV=staging) + task
PG16/Redis7 provisioned by the product supply recipe (migrated to
039_order_credit_holds, product grants applied) + the product-seeded test
tenant.

Journey per test: login -> select-tenant -> create SKU -> stock adjust ->
invitation -> retailer registration (binding active) -> retailer price ->
order create (server-side pricing) -> confirm -> payments.

Economic correctness is asserted on the RAW persisted vectors (payments
rows, ledger entries, order row) read via the app-role DSN, not on HTTP
status codes alone. Rejections must prove ZERO business writes.

Required environment (no defaults; missing -> skip, same contract as the
runtime HTTP import proof):
  MPANGO_RUNTIME_BASE_URL
  MPANGO_RUNTIME_TEST_EMAIL
  MPANGO_RUNTIME_TEST_PASSWORD
  MPANGO_RUNTIME_TENANT_ID
  TEST_DATABASE_URL          (app-role DSN of the same task database)
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal

import asyncpg
import httpx
import pytest

pytestmark = pytest.mark.asyncio

_BASE_URL = os.environ.get("MPANGO_RUNTIME_BASE_URL")
_EMAIL = os.environ.get("MPANGO_RUNTIME_TEST_EMAIL")
_PASSWORD = os.environ.get("MPANGO_RUNTIME_TEST_PASSWORD")
_TENANT_ID = os.environ.get("MPANGO_RUNTIME_TENANT_ID")
_DB_URL = os.environ.get("TEST_DATABASE_URL")
_TENANT_SCHEMA = "t_" + _TENANT_ID.replace("-", "") if _TENANT_ID else None

_missing = [k for k, v in {
    "MPANGO_RUNTIME_BASE_URL": _BASE_URL,
    "MPANGO_RUNTIME_TEST_EMAIL": _EMAIL,
    "MPANGO_RUNTIME_TEST_PASSWORD": _PASSWORD,
    "MPANGO_RUNTIME_TENANT_ID": _TENANT_ID,
    "TEST_DATABASE_URL": _DB_URL,
}.items() if not v]

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        bool(_missing),
        reason="real-runtime journey evidence requires "
        + ", ".join(sorted(_missing)),
    ),
]

UNIT_PRICE = Decimal("1000.00")
QUANTITY = 10
ORDER_TOTAL = Decimal("10000.00")


async def _login_headers(client: httpx.AsyncClient) -> dict[str, str]:
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": _EMAIL, "password": _PASSWORD},
    )
    assert login.status_code == 200, f"real login failed: {login.status_code}"
    identity_token = login.json()["data"]["access_token"]
    select = await client.post(
        "/api/v1/auth/select-tenant",
        json={"tenant_id": _TENANT_ID},
        headers={"Authorization": f"Bearer {identity_token}"},
    )
    assert select.status_code == 200, f"select-tenant failed: {select.status_code}"
    return {"Authorization": f"Bearer {select.json()['data']['access_token']}"}


@pytest.fixture(scope="module")
async def auth_headers():
    async with httpx.AsyncClient(base_url=_BASE_URL, timeout=30.0) as client:
        yield await _login_headers(client)


@pytest.fixture(scope="module")
async def db():
    conn = await asyncpg.connect(_DB_URL)
    try:
        await conn.execute(f"SET search_path TO {_TENANT_SCHEMA}")
        yield conn
    finally:
        await conn.close()


async def _order_vectors(conn: asyncpg.Connection, order_id: str) -> dict:
    """Raw persisted economic vectors for one order (no API mediation)."""
    payments = await conn.fetch(
        "SELECT id, amount::text, method, status, idempotency_key "
        "FROM payments WHERE order_id = $1 ORDER BY created_at, id",
        uuid.UUID(order_id),
    )
    ledger = await conn.fetch(
        "SELECT id, amount::text, entry_version "
        "FROM ledger_entries WHERE reference_id = $1 ORDER BY id",
        uuid.UUID(order_id),
    )
    order = await conn.fetchrow(
        "SELECT status, total_amount::text FROM orders WHERE id = $1",
        uuid.UUID(order_id),
    )
    return {
        "payment_rows": [tuple(r) for r in payments],
        "payment_total": sum((Decimal(r[1]) for r in payments), Decimal("0")),
        "ledger_rows": [tuple(r) for r in ledger],
        "order_status": order["status"],
        "order_total": order["total_amount"],
    }


async def _provision_journey(
    client: httpx.AsyncClient, headers: dict[str, str,], tag: str
) -> dict:
    """Real merchant journey up to a CONFIRMED order with a known total."""
    sku_code = f"RCJ-{tag}-{uuid.uuid4().hex[:8].upper()}"

    sku_resp = await client.post(
        "/api/v1/skus",
        json={"sku_code": sku_code, "name": f"RCJ product {tag}", "unit": "piece"},
        headers=headers,
    )
    assert sku_resp.status_code == 201, f"SKU create failed: {sku_resp.status_code} {sku_resp.text[:300]}"
    sku_id = sku_resp.json()["data"]["id"]
    phone = f"+256700{abs(hash(tag)) % 1000000:06d}"

    stock_resp = await client.post(
        "/api/v1/inventory/adjust",
        json={"sku_code": sku_code, "quantity": 100, "reason": "stocktake"},
        headers=headers,
    )
    assert stock_resp.status_code == 200, f"stock adjust failed: {stock_resp.status_code}"

    invite_resp = await client.post(
        "/api/v1/invitations",
        json={"retailer_phone": phone},
        headers=headers,
    )
    assert invite_resp.status_code == 201, f"invitation failed: {invite_resp.status_code} {invite_resp.text[:300]}"
    invitation_code = invite_resp.json()["data"]["code"]

    # R1 (CTO-AUTH-MPANGO-PUBLIC-CREATE-COMMIT-BOUNDARY-R1-20261010): the
    # historical retry loops here were a workaround for the success-response-
    # before-commit defect (invitation create / retailer register returned 201
    # before their transaction was committed). With the R1 boundary fix the
    # chain is single-request, no retries and no waits — a failure here is a
    # real journey failure, never retried away.
    reg_resp = await client.post(
        "/api/v1/retailers/register",
        json={
            "invitation_code": invitation_code,
            "name": f"RCJ Retailer {tag}",
            "phone": phone,
            "email": f"rcj-{tag.lower()}-{uuid.uuid4().hex[:8]}@example.com",
            "address": "journey evidence",
        },
    )
    assert reg_resp.status_code == 201, f"retailer registration failed: {reg_resp.status_code} {reg_resp.text[:300]}"
    registration = reg_resp.json()["data"]
    retailer_id = registration["retailer"]["id"]

    from tests.release_critical_journeys.test_cached_replay_authority import (
        _s1_order_body, _s1_prices,
    )
    await _s1_prices(client, headers, retailer_id, sku_id, str(UNIT_PRICE))
    order_body = await _s1_order_body(
        client, headers, retailer_id, [{"sku_code": sku_code, "quantity": QUANTITY}],
    )

    order_resp = await client.post(
        "/api/v1/orders",
        json=order_body,
        headers={**headers, "X-Idempotency-Key": "rcj-create-" + uuid.uuid4().hex},
    )
    assert order_resp.status_code == 201, f"order create failed: {order_resp.status_code} {order_resp.text[:300]}"
    order = order_resp.json()["data"]
    assert Decimal(str(order["total_amount"])) == ORDER_TOTAL, (
        f"server-resolved total {order['total_amount']} != expected {ORDER_TOTAL}"
    )

    confirm_resp = await client.post(
        f"/api/v1/orders/{order['id']}/confirm", headers=headers
    )
    assert confirm_resp.status_code == 200, f"confirm failed: {confirm_resp.status_code}"
    return {"order_id": order["id"], "retailer_id": retailer_id}


async def _pay(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    order_id: str,
    amount: str,
    idem: str,
) -> httpx.Response:
    return await client.post(
        f"/api/v1/orders/{order_id}/pay",
        json={"method": "cash", "amount": amount},
        headers={**headers, "X-Idempotency-Key": idem},
    )


def _error_code(resp: httpx.Response) -> str | None:
    body = resp.json()
    if isinstance(body.get("code"), str):
        return body["code"]
    detail = body.get("detail")
    if isinstance(detail, dict):
        return detail.get("code")
    return None


async def test_real_journey_overpayment_rejected_with_zero_business_write(
    auth_headers, db
):
    """Partial payment then an overpaying request must be rejected by the
    real canonical payment path with ZERO change to any persisted vector."""
    async with httpx.AsyncClient(base_url=_BASE_URL, timeout=30.0) as client:
        journey = await _provision_journey(client, auth_headers, "c1a")
        order_id = journey["order_id"]

        partial = await _pay(client, auth_headers, order_id, "4000.00", "rcj-c1a-p1-" + uuid.uuid4().hex[:12])
        assert partial.status_code == 200, partial.text[:300]
        after_partial = await _order_vectors(db, order_id)
        assert after_partial["order_status"] == "partially_paid", after_partial["order_status"]
        assert after_partial["payment_total"] == Decimal("4000.00")

        overpay = await _pay(client, auth_headers, order_id, "7000.00", "rcj-c1a-o1-" + uuid.uuid4().hex[:12])
        assert overpay.status_code == 400, (
            f"overpayment must be rejected, got {overpay.status_code}: {overpay.text[:300]}"
        )
        assert _error_code(overpay) == "PAYMENT_EXCEEDS_REMAINING", overpay.text[:300]

        after_reject = await _order_vectors(db, order_id)
        assert after_reject == after_partial, (
            "overpayment rejection must leave ZERO business writes: "
            f"before={after_partial} after={after_reject}"
        )


async def test_paid_order_second_payment_rejected(auth_headers, db):
    """Completing to PAID then paying again must 409 with zero writes."""
    async with httpx.AsyncClient(base_url=_BASE_URL, timeout=30.0) as client:
        journey = await _provision_journey(client, auth_headers, "c1b")
        order_id = journey["order_id"]

        full = await _pay(client, auth_headers, order_id, "10000.00", "rcj-c1b-p1-" + uuid.uuid4().hex[:12])
        assert full.status_code == 200, full.text[:300]
        paid = await _order_vectors(db, order_id)
        assert paid["order_status"] == "paid", paid["order_status"]
        assert paid["payment_total"] == ORDER_TOTAL

        again = await _pay(client, auth_headers, order_id, "1.00", "rcj-c1b-p2-" + uuid.uuid4().hex[:12])
        assert again.status_code == 409, (
            f"second payment on a PAID order must be rejected, got {again.status_code}: {again.text[:300]}"
        )
        assert _error_code(again) in {"ORDER_ALREADY_PAID", "PAYMENT_EXCEEDS_REMAINING"}, again.text[:300]

        still_paid = await _order_vectors(db, order_id)
        assert still_paid == paid, (
            f"rejected second payment changed vectors: {paid} -> {still_paid}"
        )


async def test_full_payment_idempotent_replay_single_economic_effect(
    auth_headers, db
):
    """Replaying the identical payment request (same idempotency key) must
    not create a second payment, ledger effect, or state change."""
    async with httpx.AsyncClient(base_url=_BASE_URL, timeout=30.0) as client:
        journey = await _provision_journey(client, auth_headers, "c1c")
        order_id = journey["order_id"]
        idem = "rcj-c1c-idem-" + uuid.uuid4().hex[:12]

        first = await _pay(client, auth_headers, order_id, "10000.00", idem)
        assert first.status_code == 200, first.text[:300]
        once = await _order_vectors(db, order_id)
        assert once["order_status"] == "paid"
        assert len(once["payment_rows"]) == 1, once["payment_rows"]
        first_payment_id = first.json()["data"]["payment_id"]

        replay = await _pay(client, auth_headers, order_id, "10000.00", idem)
        assert replay.status_code == 200, replay.text[:300]
        # Economic contract: the replay must return the SAME payment (no
        # second record). NOTE observed on BASE bytes: the replay response
        # message says "Payment recorded and order updated" instead of
        # "Payment replayed" even though the same existing payment is
        # returned with zero new writes — a cosmetic label mismatch,
        # reported in the task report; the vectors are authoritative here.
        assert replay.json()["data"]["payment_id"] == first_payment_id, (
            f"replay must return the existing payment: {replay.text[:300]}"
        )

        twice = await _order_vectors(db, order_id)
        assert twice == once, (
            f"idempotent replay changed persisted vectors: {once} -> {twice}"
        )


async def test_unauthenticated_order_create_rejected_zero_write(auth_headers, db):
    """Order creation without a token must be refused with zero writes
    (real-path protection behind the 9 stale validation/RBAC xfails)."""
    orders_before = await db.fetchval("SELECT count(*) FROM orders")
    async with httpx.AsyncClient(base_url=_BASE_URL, timeout=30.0) as client:
        resp = await client.post(
            "/api/v1/orders",
            json={
                "retailer_id": str(uuid.uuid4()),
                "items": [{"sku_code": "X", "quantity": 1}],
            },
        )
    assert resp.status_code in {401, 403}, (
        f"unauthenticated order create must be refused, got {resp.status_code}"
    )
    orders_after = await db.fetchval("SELECT count(*) FROM orders")
    assert orders_after == orders_before, "refused request must not create orders"
