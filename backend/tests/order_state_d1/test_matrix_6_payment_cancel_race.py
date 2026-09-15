"""MPANGO-ORDER-STATE-AUTHORITY-D1 matrix group 6 — payment vs cancel race.

Real HTTP surface, two concurrent requests, event barriers with bounded
waits (no sleeps for ordering logic).

Sequential positive controls (both legitimate orders, deterministic):
- pay-then-cancel: pay 200/paid; cancel 409 (paid not in crud allowed_from);
  final paid; one completed payment; settlement ledger present; reservations
  stay reserved awaiting fulfillment.
- cancel-then-pay: cancel 200; pay 409 INVALID_STATE_TRANSITION; final
  cancelled; zero payments.

Racing interleaving (pay commits first, cancel validated its pre-loaded
CONFIRMED object before that commit): cancel overwrites PAID with CANCELLED,
releases the reservations, and returns 200 — money recorded and settled on a
cancelled order with no refund/reversal path. Contract asserted: the final
facts must equal ONE of the two sequential histories; the paid+cancelled
combo must never exist. Current product violates both -> honest RED.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
from http import HTTPStatus

import pytest
from sqlalchemy import text

from tests.order_state_d1.support import (
    assert_no_orphan_reservations,
    assert_no_paid_cancelled_combo,
    bound_retailer,
    fetch_order_state,
    fetch_payment_ledger_facts,
    fetch_reservation_facts,
    http_action,
    http_create_wholesaler_order,
    linearizable_final,
    osd1_cashier_token,
    seed_sku_with_stock,
)

pytestmark = pytest.mark.asyncio

_BUDGET = 25.0


def _errcode(resp) -> str:
    body = resp.json()
    detail = body.get("detail") or body.get("error") or {}
    return (detail.get("code") or body.get("code") or "")


async def _race_facts(db, schema, oid):
    state = await fetch_order_state(db, schema, oid)
    money = await fetch_payment_ledger_facts(db, schema, oid)
    facts = await fetch_reservation_facts(db, schema, oid)
    return {
        "status": state["status"],
        "payments": len(money["payments"]),
        "ledger": len(money["ledger"]),
        "reserved_rows": facts["reserved_rows"],
    }


async def _seed(osd1_client, token, db, pool, reg):
    async with bound_retailer(db, pool, reg) as (ret_id, schema, _ws):
        sku, _sid = await seed_sku_with_stock(db, schema, ret_id, quantity=100, price="40.00")
        order = await http_create_wholesaler_order(osd1_client, token, ret_id, sku, 2)
        oid = order["id"]
        assert (await http_action(osd1_client, token, oid, "confirm")).status_code == 200
        return oid, schema


async def test_sequential_pay_then_cancel_control(
    osd1_client, s2_clean_db, provisioned_pool, osd1_cashier
):
    db, reg = s2_clean_db
    token = await osd1_cashier_token(osd1_client, osd1_cashier)
    oid, schema = await _seed(osd1_client, token, db, provisioned_pool, reg)

    pay = await http_action(osd1_client, token, oid, "pay",
                            {"amount": 80.00, "method": "cash"})
    assert pay.status_code == HTTPStatus.OK, pay.text
    cancel = await http_action(osd1_client, token, oid, "cancel")
    assert cancel.status_code == HTTPStatus.CONFLICT
    assert _errcode(cancel) == "INVALID_STATE_TRANSITION"

    facts = await _race_facts(db, schema, oid)
    assert facts == {"status": "paid", "payments": 1, "ledger": 2,
                     "reserved_rows": 1}, facts
    await assert_no_paid_cancelled_combo(db, schema, oid)


async def test_sequential_cancel_then_pay_control(
    osd1_client, s2_clean_db, provisioned_pool, osd1_cashier
):
    db, reg = s2_clean_db
    token = await osd1_cashier_token(osd1_client, osd1_cashier)
    oid, schema = await _seed(osd1_client, token, db, provisioned_pool, reg)

    cancel = await http_action(osd1_client, token, oid, "cancel")
    assert cancel.status_code == HTTPStatus.OK, cancel.text
    pay = await http_action(osd1_client, token, oid, "pay",
                            {"amount": 80.00, "method": "cash"})
    assert pay.status_code == HTTPStatus.CONFLICT
    assert _errcode(pay) == "INVALID_STATE_TRANSITION"

    facts = await _race_facts(db, schema, oid)
    assert facts == {"status": "cancelled", "payments": 0, "ledger": 0,
                     "reserved_rows": 0}, facts
    await assert_no_paid_cancelled_combo(db, schema, oid)


async def test_race_pay_committed_then_cancel_overwrites_current_defect(
    osd1_client, s2_clean_db, provisioned_pool, osd1_cashier, monkeypatch
):
    db, reg = s2_clean_db
    token = await osd1_cashier_token(osd1_client, osd1_cashier)
    oid, schema = await _seed(osd1_client, token, db, provisioned_pool, reg)

    import api.v1.orders as orders_api
    import services.canonical_payment_service as canonical_module

    real_confirm_payment = canonical_module.CanonicalPaymentService.confirm_payment
    real_cancel = orders_api.crud_cancel_order

    cancel_arrived = asyncio.Event()
    pay_started = asyncio.Event()
    pay_committed = asyncio.Event()

    async def gated_confirm_payment(self, **kwargs):
        await pay_started.wait()          # cancel has arrived first
        return await real_confirm_payment(self, **kwargs)

    async def gated_cancel(db, order, **kwargs):
        cancel_arrived.set()              # cancel's stale read happened HERE
        await pay_committed.wait()        # release only after pay committed
        return await real_cancel(db, order, **kwargs)

    monkeypatch.setattr(
        canonical_module.CanonicalPaymentService, "confirm_payment", gated_confirm_payment
    )
    monkeypatch.setattr(orders_api, "crud_cancel_order", gated_cancel)

    async def run(action, body=None):
        return await http_action(osd1_client, token, oid, action, body)

    pay_task = asyncio.create_task(run("pay", {"amount": 80.00, "method": "cash"}))
    cancel_task = asyncio.create_task(run("cancel"))

    async with asyncio.timeout(_BUDGET):
        await asyncio.wait_for(cancel_arrived.wait(), _BUDGET)
        pay_started.set()

        async def watch_commit():
            while True:
                state = await fetch_order_state(db, schema, oid)
                if state.get("status") == "paid":
                    pay_committed.set()
                    return
                await asyncio.sleep(0.02)

        await asyncio.gather(watch_commit())
        pay_resp, cancel_resp = await asyncio.gather(pay_task, cancel_task)

    assert pay_resp.status_code == HTTPStatus.OK, pay_resp.text

    # CONTRACT (linearizability): the racing final facts must equal exactly
    # one of the two legitimate sequential histories.
    sequential_histories = [
        {"status": "paid", "payments": 1, "ledger": 2, "reserved_rows": 1},
        {"status": "cancelled", "payments": 0, "ledger": 0, "reserved_rows": 0},
    ]
    final = await _race_facts(db, schema, oid)
    assert linearizable_final(final, sequential_histories), (
        f"racing outcome {final} matches no sequential history "
        f"{sequential_histories}; cancel={cancel_resp.status_code} {cancel_resp.text}")

    # CONTRACT: completed payment + settlement ledger must never sit on a
    # cancelled order (no refund path exists in the product).
    await assert_no_paid_cancelled_combo(db, schema, oid)
    await assert_no_orphan_reservations(db, schema, oid, expect_status="cancelled")
