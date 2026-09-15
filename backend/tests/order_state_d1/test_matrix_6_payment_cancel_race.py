"""MPANGO-ORDER-STATE-AUTHORITY-D1 matrix group 6 — payment vs cancel race.

R1 lifecycle: all tasks owned by a RaceOrchestrator (drained on every exit);
responses + DB fact vectors captured before failing assertions; commit
observation is a bounded fresh-DB read; timeout is surfaced as
ORCHESTRATION_TIMEOUT, never as a product defect.

Sequential positive controls (both legitimate orders, deterministic):
- pay-then-cancel: pay 200/paid; cancel 409 (paid not in crud allowed_from);
  final paid; one completed payment; settlement ledger present.
- cancel-then-pay: cancel 200; pay 409 INVALID_STATE_TRANSITION; final
  cancelled; zero payments.

Racing interleaving (pay commits first, cancel validated its pre-loaded
CONFIRMED object before that commit): cancel overwrites PAID with CANCELLED
and returns 200 — money recorded and settled on a cancelled order with no
refund/reversal path. Contract: the final facts must equal ONE of the two
sequential histories; the paid+cancelled combo must never exist. Current
product violates both -> honest RED.
"""
from __future__ import annotations

import asyncio
from http import HTTPStatus

import pytest

from tests.order_state_d1.support import (
    RaceOrchestrator,
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

_BUDGET = 30.0


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
        "completed_payments": sum(1 for p in money["payments"] if p["status"] == "completed"),
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


async def _await_committed_status(db, schema, order_id, status: str) -> bool:
    async with asyncio.timeout(10.0):
        while True:
            state = await fetch_order_state(db, schema, order_id)
            if state.get("status") == status:
                return True
            await asyncio.sleep(0.02)
    return False


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
    assert facts == {"status": "paid", "payments": 1, "completed_payments": 1,
                     "ledger": 2, "reserved_rows": 1}, facts
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
    assert facts == {"status": "cancelled", "payments": 0, "completed_payments": 0,
                     "ledger": 0, "reserved_rows": 0}, facts
    await assert_no_paid_cancelled_combo(db, schema, oid)


async def test_race_pay_committed_then_cancel_overwrites_current_defect(
    osd1_client, s2_clean_db, provisioned_pool, osd1_cashier, monkeypatch
):
    db, reg = s2_clean_db
    token = await osd1_cashier_token(osd1_client, osd1_cashier)
    oid, schema = await _seed(osd1_client, token, db, provisioned_pool, reg)

    import services.canonical_payment_service as canonical_module

    real_confirm_payment = canonical_module.CanonicalPaymentService.confirm_payment
    real_cancel = None
    import api.v1.orders as orders_api
    real_cancel = orders_api.crud_cancel_order

    cancel_arrived = asyncio.Event()
    pay_started = asyncio.Event()
    pay_committed = asyncio.Event()

    async def gated_confirm_payment(self, **kwargs):
        await asyncio.wait_for(pay_started.wait(), _BUDGET)
        return await real_confirm_payment(self, **kwargs)

    async def gated_cancel(db_, order, **kwargs):
        cancel_arrived.set()              # cancel's stale read happened HERE
        await asyncio.wait_for(pay_committed.wait(), _BUDGET)
        return await real_cancel(db_, order, **kwargs)

    monkeypatch.setattr(
        canonical_module.CanonicalPaymentService, "confirm_payment", gated_confirm_payment
    )
    monkeypatch.setattr(orders_api, "crud_cancel_order", gated_cancel)

    orch = RaceOrchestrator(_BUDGET)
    try:
        pay_task = orch.spawn(http_action(osd1_client, token, oid, "pay",
                                          {"amount": 80.00, "method": "cash"}))
        cancel_task = orch.spawn(http_action(osd1_client, token, oid, "cancel"))

        async with asyncio.timeout(_BUDGET):
            # explicit handshake: cancel's stale read has happened
            await asyncio.wait_for(cancel_arrived.wait(), _BUDGET)
            pay_started.set()
            # commit handshake: fresh-DB observation of the committed PAID
            committed = await _await_committed_status(db, schema, oid, "paid")
            assert committed, "pay never committed within budget — orchestration issue"
            pay_committed.set()
            results = await asyncio.gather(pay_task, cancel_task,
                                           return_exceptions=True)
    except TimeoutError:
        orch.timed_out = True
        raise AssertionError(
            "ORCHESTRATION_TIMEOUT: pay/cancel interleaving never completed "
            f"within {_BUDGET}s — not interpretable as a product race defect")
    finally:
        await orch.drain()

    responses = [r for r in results if not isinstance(r, BaseException)]
    errors = [r for r in results if isinstance(r, BaseException)]
    assert not errors, f"transport failures are orchestration errors: {errors}"

    facts = await _race_facts(db, schema, oid)
    pay_resp = next(r for r in responses if r.request.url.path.endswith("/pay"))
    cancel_resp = next(r for r in responses if r.request.url.path.endswith("/cancel"))
    assert pay_resp.status_code == HTTPStatus.OK, (
        f"pay must commit first for this interleaving: {pay_resp.text}; facts={facts}")

    # CONTRACT (linearizability): the racing final facts must equal exactly
    # one of the two legitimate sequential histories. Facts captured BEFORE
    # this assertion so a failure carries full evidence.
    sequential_histories = [
        {"status": "paid", "payments": 1, "completed_payments": 1,
         "ledger": 2, "reserved_rows": 1},
        {"status": "cancelled", "payments": 0, "completed_payments": 0,
         "ledger": 0, "reserved_rows": 0},
    ]
    assert linearizable_final(facts, sequential_histories), (
        f"RED_EVIDENCE racing outcome {facts} matches no sequential history "
        f"{sequential_histories}; cancel={cancel_resp.status_code} {cancel_resp.text}")

    # CONTRACT: completed payment + settlement ledger must never sit on a
    # cancelled order (no refund path exists in the product).
    await assert_no_paid_cancelled_combo(db, schema, oid)
    await assert_no_orphan_reservations(db, schema, oid, expect_status="cancelled")
