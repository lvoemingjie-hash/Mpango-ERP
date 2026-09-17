"""C6 lock order and concurrency — real production paths, two concurrent
requests per scenario, start-gated by an asyncio event (no sleeps, no
service monkeypatching). Final-state assertions are deterministic under BOTH
interleavings so the parent commit REDs deterministically wherever the hold
gap changes the money.

Counterexamples (product-RED on the parent commit):
  - C6-RED-1  confirm(Y) racing cancel(X) on the same binding: product nets
              +10 -10 = binding stays 10; parent nets +20 (cancel releases
              nothing).
  - C6-RED-2  pay(cash full) racing cancel on the SAME order: product ends at
              binding 0 under either interleaving; the parent strands 60.
  - C6-RED-3  declaration-confirm racing direct pay on the same order:
              exactly one settlement effect; product binding 0; parent 100.
Guards (green on parent and product, protect the lock-order rework):
  - double declaration confirmation yields exactly one payment+receipt.
  - two orders confirming concurrently keep the binding sum exact.
"""
from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

import pytest

from tests.order_state_r2.support import (
    binding_balance,
    errcode,
    http_action,
    inventory_vector,
    http_create_order,
    make_bound_retailer,
    order_vector,
    osd1_cashier_token,
    payments_vector,
    receipt_numbers,
    reservation_vector,
    seed_sku_with_stock,
)

pytestmark = pytest.mark.asyncio


class _StartGate:
    def __init__(self, n: int):
        self._event = asyncio.Event()
        self._n = n

    async def wait(self):
        await self._event.wait()

    def open(self):
        self._event.set()


async def _race(coro_a, coro_b, timeout: float = 30.0):
    gate = _StartGate(2)

    async def run(coro):
        await gate.wait()
        return await asyncio.wait_for(coro, timeout)

    task_a = asyncio.create_task(run(coro_a))
    task_b = asyncio.create_task(run(coro_b))
    await asyncio.sleep(0)  # let both tasks reach the gate
    gate.open()
    return await asyncio.gather(task_a, task_b, return_exceptions=True)


async def test_c6_confirm_vs_cancel_different_orders_same_binding(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity,
):
    """C6-RED-1: order X confirmed (hold 10) then cancel(X) races confirm(Y):
    the binding must end at 10 (X released, Y reserved) regardless of the
    winner. The parent cannot release X, so it ends at 20."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, ws_id = await make_bound_retailer(db, provisioned_pool, reg)
    sku, _sid = await seed_sku_with_stock(db, schema, ret_id, price="10.00")
    oid_x = await http_create_order(r1_client, token, ret_id,
                                    [{"sku_code": sku, "quantity": 1}])
    assert (await http_action(r1_client, token, oid_x, "confirm")).status_code == 200
    assert await binding_balance(db, ws_id, ret_id) == Decimal("10.00")
    oid_y = await http_create_order(r1_client, token, ret_id,
                                    [{"sku_code": sku, "quantity": 1}])

    (cancel_resp, confirm_resp) = await _race(
        http_action(r1_client, token, oid_x, "cancel"),
        http_action(r1_client, token, oid_y, "confirm"),
    )
    assert not isinstance(cancel_resp, BaseException), cancel_resp
    assert not isinstance(confirm_resp, BaseException), confirm_resp
    assert cancel_resp.status_code == 200, cancel_resp.text
    assert confirm_resp.status_code == 200, confirm_resp.text

    balance = await binding_balance(db, ws_id, ret_id)
    assert balance == Decimal("10.00"), (
        f"C6-RED-1 binding after confirm(Y) racing cancel(X) = {balance}, "
        "expected 10.00 (X released, Y reserved) — parent strands X's hold")
    assert (await order_vector(db, schema, oid_x))["status"] == "cancelled"
    assert (await order_vector(db, schema, oid_y))["status"] == "confirmed"


async def test_c6_pay_vs_cancel_same_order_both_interleavings(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity,
):
    """C6-RED-2: pay(cash, full 60) races cancel on the same CONFIRMED order.
    Either the payment wins (order PAID, cancel 409, binding 0) or the cancel
    wins (order CANCELLED, pay 409, binding 0). The parent ends at 60 in BOTH
    branches (stranded hold / refund-gate keeps it)."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, ws_id = await make_bound_retailer(db, provisioned_pool, reg)
    sku, sid = await seed_sku_with_stock(db, schema, ret_id, price="30.00")
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 2}])
    assert (await http_action(r1_client, token, oid, "confirm")).status_code == 200

    (pay_resp, cancel_resp) = await _race(
        http_action(r1_client, token, oid, "pay",
                    {"amount": 60.0, "method": "cash"}),
        http_action(r1_client, token, oid, "cancel"),
    )
    assert not isinstance(pay_resp, BaseException), pay_resp
    assert not isinstance(cancel_resp, BaseException), cancel_resp
    status = (await order_vector(db, schema, oid))["status"]

    if status == "paid":
        assert pay_resp.status_code == 200, pay_resp.text
        assert cancel_resp.status_code == 409, cancel_resp.text
        assert errcode(cancel_resp) == "REFUND_WORKFLOW_NOT_IMPLEMENTED"
    elif status == "cancelled":
        assert cancel_resp.status_code == 200, cancel_resp.text
        assert pay_resp.status_code == 409, pay_resp.text
    else:  # pragma: no cover - serialization bug
        raise AssertionError(f"neither writer won: status={status} "
                             f"pay={pay_resp} cancel={cancel_resp}")

    balance = await binding_balance(db, ws_id, ret_id)
    assert balance == Decimal("0.00"), (
        f"C6-RED-2 binding after pay/cancel race (status={status}) = "
        f"{balance}, expected 0.00 under both interleavings — parent "
        "strands the hold in both")

    # inventory shape per branch: PAID keeps its reservations reserved
    # (fulfill consumes them); CANCELLED releases them.
    inv = await inventory_vector(db, schema, [sid])
    resv = await reservation_vector(db, schema, oid)
    if status == "paid":
        assert all(r["status"] == "reserved" for r in resv), (inv, resv)
        assert inv[sid].endswith("/2"), (inv, resv)
    else:
        assert all(r["status"] == "released" for r in resv), (inv, resv)
        assert inv[sid].endswith("/0"), (inv, resv)


async def test_c6_declaration_confirm_vs_direct_pay_same_order(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity,
):
    """C6-RED-3: a pending cash declaration and a direct cash pay race on the
    same confirmed order. Exactly one settlement wins, the other is refused,
    and the binding ends at 0 (one total held, then one total settled). The
    parent ends at 100 (hold stranded, declaration adds nothing)."""
    from services.payment_declaration_service import PaymentDeclarationService
    from tests.order_state_r1.support import rebind_search_path

    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, ws_id = await make_bound_retailer(db, provisioned_pool, reg)
    sku, _sid = await seed_sku_with_stock(db, schema, ret_id, price="50.00")
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 2}])
    assert (await http_action(r1_client, token, oid, "confirm")).status_code == 200
    await rebind_search_path(db, schema)

    record, replayed = await PaymentDeclarationService().submit_declaration(
        db=db,
        order_id=oid,
        retailer_id=uuid.UUID(ret_id),
        wholesaler_id=uuid.UUID(ws_id),
        submitted_by=uuid.UUID(str(cashier_identity["user_id"])),
        declared_amount=Decimal("100.00"),
        method="cash",
        transfer_reference=None,
        idempotency_key=f"r2-c6-{uuid.uuid4().hex}",
    )
    await db.commit()
    assert not replayed
    decl_id = str(record["id"])

    (decl_resp, pay_resp) = await _race(
        r1_client.post(f"/api/v1/declarations/{decl_id}/confirm",
                       headers={"Authorization": f"Bearer {token}"}),
        http_action(r1_client, token, oid, "pay",
                    {"amount": 100.0, "method": "cash"}),
    )
    for r in (decl_resp, pay_resp):
        assert not isinstance(r, BaseException), r

    status = (await order_vector(db, schema, oid))["status"]
    assert status in {"paid", "cancelled"}, status
    if status == "paid":
        settled = [r for r in (decl_resp, pay_resp) if r.status_code == 200]
        assert len(settled) == 1, (
            f"exactly one settlement may win: decl={decl_resp} pay={pay_resp}")
    else:
        assert all(r.status_code in {200, 409} for r in (decl_resp, pay_resp))

    rows = await payments_vector(db, schema, oid)
    effective = [r for r in rows if not r["is_deleted"]]
    assert len(effective) <= 2, rows  # credit is not among them; cash only
    balance = await binding_balance(db, ws_id, ret_id)
    assert balance == Decimal("0.00"), (
        f"C6-RED-3 binding after declaration/direct-pay race (status="
        f"{status}) = {balance}, expected 0.00 — parent strands the hold")


async def test_c6_double_declaration_confirm_one_receipt(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity,
):
    """Guard: two concurrent confirmations of the SAME declaration produce
    exactly one payment and one receipt; the second observes the confirmed
    declaration (replay or 409) with zero extra writes."""
    from services.payment_declaration_service import PaymentDeclarationService
    from tests.order_state_r1.support import rebind_search_path

    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, ws_id = await make_bound_retailer(db, provisioned_pool, reg)
    sku, _sid = await seed_sku_with_stock(db, schema, ret_id, price="50.00")
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 2}])
    assert (await http_action(r1_client, token, oid, "confirm")).status_code == 200
    await rebind_search_path(db, schema)

    record, _ = await PaymentDeclarationService().submit_declaration(
        db=db,
        order_id=oid,
        retailer_id=uuid.UUID(ret_id),
        wholesaler_id=uuid.UUID(ws_id),
        submitted_by=uuid.UUID(str(cashier_identity["user_id"])),
        declared_amount=Decimal("100.00"),
        method="cash",
        transfer_reference=None,
        idempotency_key=f"r2-c6d-{uuid.uuid4().hex}",
    )
    await db.commit()
    decl_id = str(record["id"])

    (r1, r2) = await _race(
        r1_client.post(f"/api/v1/declarations/{decl_id}/confirm",
                       headers={"Authorization": f"Bearer {token}"}),
        r1_client.post(f"/api/v1/declarations/{decl_id}/confirm",
                       headers={"Authorization": f"Bearer {token}"}),
    )
    for r in (r1, r2):
        assert not isinstance(r, BaseException), r
    codes = sorted([r1.status_code, r2.status_code])
    assert codes in ([200, 200], [200, 409]), (r1.text, r2.text)

    receipts = await receipt_numbers(db, schema, oid)
    assert len(receipts) == 1, f"exactly one receipt expected: {receipts}"
    assert await binding_balance(db, ws_id, ret_id) == Decimal("0.00")
    effective = [p for p in await payments_vector(db, schema, oid)
                 if not p["is_deleted"]]
    assert len(effective) == 1, effective


async def test_c6_two_orders_concurrent_confirm_binding_sum(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity,
):
    """Guard: two different orders confirming concurrently on the same
    binding keep the cache exact (atomic conditional updates, no lost
    update), zero deadlock."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, ws_id = await make_bound_retailer(db, provisioned_pool, reg)
    sku, _sid = await seed_sku_with_stock(db, schema, ret_id, price="10.00")
    oid_a = await http_create_order(r1_client, token, ret_id,
                                    [{"sku_code": sku, "quantity": 1}])
    oid_b = await http_create_order(r1_client, token, ret_id,
                                    [{"sku_code": sku, "quantity": 2}])

    (resp_a, resp_b) = await _race(
        http_action(r1_client, token, oid_a, "confirm"),
        http_action(r1_client, token, oid_b, "confirm"),
    )
    for r in (resp_a, resp_b):
        assert not isinstance(r, BaseException), r
        assert r.status_code == 200, r.text

    assert await binding_balance(db, ws_id, ret_id) == Decimal("30.00"), (
        "concurrent confirms must sum their holds exactly (1x10 + 1x20)")
