"""MPANGO-ORDER-STATE-AUTHORITY-D1 matrix group 2 — double-connection races.

R1 (Codex-L review round): every spawned task is owned by a
RaceOrchestrator that drains it on every exit path; response bodies and DB
fact vectors are captured BEFORE any failing assertion (a race outcome is
never reported without its inventory facts); timeout is surfaced as
ORCHESTRATION_TIMEOUT and never equated with a product defect. Arrival
synchronization uses explicit events inside the barrier wrappers (no
sleep-based ordering); commit observation is a bounded fresh-DB read.

Three race families over the REAL HTTP surface (two concurrent ASGI
requests, each with its own tenant session and its own middleware commit),
synchronized by event barriers around the module-level CRUD names the
endpoints call. The wrappers delegate to the REAL functions unchanged.

- confirm || confirm: expected deterministic good case — the reservation
  duplicate guard or the matrix check turns exactly one request into 409.
- cancel || cancel: current product accepts BOTH (both validated a stale
  CONFIRMED object). No sequential history accepts two cancels -> RED.
- confirm || cancel (cancel commits last): final cancelled order keeps
  ``reserved`` rows -> orphaned inventory -> RED.
"""
from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal
from http import HTTPStatus

import pytest
from sqlalchemy import text

from tests.order_state_d1.support import (
    RaceOrchestrator,
    assert_no_orphan_reservations,
    bound_retailer,
    fetch_order_state,
    fetch_reservation_facts,
    http_action,
    http_create_wholesaler_order,
    linearizable_final,
    osd1_cashier_token,
    seed_sku_with_stock,
)

pytestmark = pytest.mark.asyncio

_BUDGET = 30.0  # bounded waits; never a sleep-ordering mechanism


class _SharedGate:
    """Arrival barrier for N wrappers; the last arrival releases all."""

    def __init__(self, expected: int):
        self.expected = expected
        self.arrived = asyncio.Event()

    async def wait_turn(self) -> None:
        self._count = getattr(self, "_count", 0) + 1
        if self._count >= self.expected:
            self.arrived.set()
        else:
            await asyncio.wait_for(self.arrived.wait(), _BUDGET)


async def _seed_confirmed_ready(osd1_client, token, db, pool, reg, qty: int):
    async with bound_retailer(db, pool, reg) as (ret_id, schema, _ws):
        sku, _sid = await seed_sku_with_stock(db, schema, ret_id, quantity=100)
        order = await http_create_wholesaler_order(osd1_client, token, ret_id, sku, qty)
        return order["id"], schema


async def _race_facts(db, schema, oid):
    state = await fetch_order_state(db, schema, oid)
    facts = await fetch_reservation_facts(db, schema, oid)
    return {"status": state["status"], "reserved_rows": facts["reserved_rows"],
            "reserved_total": facts["reserved_total"],
            "row_statuses": sorted(r["status"] for r in facts["rows"])}


async def _await_committed_status(db, schema, order_id, status: str) -> bool:
    """Fresh-DB observation with a bounded loop; returns observed flag."""
    async with asyncio.timeout(10.0):
        while True:
            state = await fetch_order_state(db, schema, order_id)
            if state.get("status") == status:
                return True
            await asyncio.sleep(0.02)
    return False


async def test_race_confirm_confirm_exactly_one_success(
    osd1_client, s2_clean_db, provisioned_pool, osd1_cashier, monkeypatch
):
    db, reg = s2_clean_db
    token = await osd1_cashier_token(osd1_client, osd1_cashier)
    oid, schema = await _seed_confirmed_ready(osd1_client, token, db, provisioned_pool, reg, 4)

    gate = _SharedGate(2)
    import api.v1.orders as orders_api

    real_confirm = orders_api.crud_confirm_order

    async def gated_confirm(db_, order, **kwargs):
        await gate.wait_turn()
        return await real_confirm(db_, order, **kwargs)

    monkeypatch.setattr(orders_api, "crud_confirm_order", gated_confirm)

    orch = RaceOrchestrator(_BUDGET)
    try:
        orch.spawn(http_action(osd1_client, token, oid, "confirm"))
        orch.spawn(http_action(osd1_client, token, oid, "confirm"))
        results = await orch.gather_all()
    finally:
        await orch.drain()

    responses = [r for r in results if not isinstance(r, BaseException)]
    errors = [r for r in results if isinstance(r, BaseException)]
    assert not errors, f"transport failures are orchestration errors, not REDs: {errors}"
    # facts BEFORE assertions: capture final DB state regardless of outcomes
    facts = await _race_facts(db, schema, oid)
    statuses = sorted(r.status_code for r in responses)

    assert statuses == [HTTPStatus.OK, HTTPStatus.CONFLICT], (
        f"race outcomes {statuses}: {[r.text for r in responses]}")
    assert facts["reserved_rows"] == 1, f"double reservation leaked: {facts}"
    assert Decimal(facts["reserved_total"]) == Decimal("4")
    assert facts["status"] == "confirmed"
    assert linearizable_final(
        {"status": facts["status"], "reserved_rows": facts["reserved_rows"]},
        [{"status": "confirmed", "reserved_rows": 1}],
    )


async def test_race_cancel_cancel_must_match_sequential_history(
    osd1_client, s2_clean_db, provisioned_pool, osd1_cashier, monkeypatch
):
    """Both requests validated a pre-loaded CONFIRMED object with no lock and
    no ORM refresh, so both write CANCELLED and both return 200. Sequentially
    the second cancel is a deterministic 409 — no serial history produces two
    successes. Facts captured before assertions; assertion kept intact."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(osd1_client, osd1_cashier)
    oid, schema = await _seed_confirmed_ready(osd1_client, token, db, provisioned_pool, reg, 3)
    assert (await http_action(osd1_client, token, oid, "confirm")).status_code == HTTPStatus.OK

    gate = _SharedGate(2)
    import api.v1.orders as orders_api

    real_cancel = orders_api.crud_cancel_order

    async def gated_cancel(db_, order, **kwargs):
        await gate.wait_turn()
        return await real_cancel(db_, order, **kwargs)

    monkeypatch.setattr(orders_api, "crud_cancel_order", gated_cancel)

    orch = RaceOrchestrator(_BUDGET)
    try:
        orch.spawn(http_action(osd1_client, token, oid, "cancel"))
        orch.spawn(http_action(osd1_client, token, oid, "cancel"))
        results = await orch.gather_all()
    finally:
        await orch.drain()

    responses = [r for r in results if not isinstance(r, BaseException)]
    errors = [r for r in results if isinstance(r, BaseException)]
    assert not errors, f"transport failures are orchestration errors: {errors}"
    facts = await _race_facts(db, schema, oid)
    statuses = sorted(r.status_code for r in responses)

    # CONTRACT first (may fail) — but facts are already captured for the record
    assert statuses == [HTTPStatus.OK, HTTPStatus.CONFLICT], (
        f"RED_EVIDENCE racing double-cancel accepted both: statuses={statuses} "
        f"responses={[r.text for r in responses]} final_facts={facts}; "
        "sequential control is 200 then 409")
    assert facts["reserved_rows"] == 0, facts
    await assert_no_orphan_reservations(db, schema, oid, expect_status="cancelled")


async def test_race_confirm_then_cancel_last_writer_orphans_reservation(
    osd1_client, s2_clean_db, provisioned_pool, osd1_cashier, monkeypatch
):
    """Deterministic interleaving: both arrive before either writes; confirm
    is released first and COMMITTED (observed via fresh DB read); cancel —
    validated against its pre-loaded DRAFT object — then overwrites to
    CANCELLED while the committed reservations stay ``reserved``."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(osd1_client, osd1_cashier)
    oid, schema = await _seed_confirmed_ready(osd1_client, token, db, provisioned_pool, reg, 5)

    import api.v1.orders as orders_api

    real_confirm, real_cancel = orders_api.crud_confirm_order, orders_api.crud_cancel_order

    both_arrived = asyncio.Event()
    arrival = {"confirm": False, "cancel": False}
    release_confirm = asyncio.Event()
    confirm_committed = asyncio.Event()

    def _mark(which: str):
        arrival[which] = True
        if all(arrival.values()):
            both_arrived.set()

    async def gated_confirm(db_, order, **kwargs):
        _mark("confirm")
        await asyncio.wait_for(both_arrived.wait(), _BUDGET)
        await asyncio.wait_for(release_confirm.wait(), _BUDGET)
        return await real_confirm(db_, order, **kwargs)

    async def gated_cancel(db_, order, **kwargs):
        _mark("cancel")
        await asyncio.wait_for(both_arrived.wait(), _BUDGET)
        await asyncio.wait_for(confirm_committed.wait(), _BUDGET)
        return await real_cancel(db_, order, **kwargs)

    monkeypatch.setattr(orders_api, "crud_confirm_order", gated_confirm)
    monkeypatch.setattr(orders_api, "crud_cancel_order", gated_cancel)

    orch = RaceOrchestrator(_BUDGET)
    try:
        confirm_task = orch.spawn(http_action(osd1_client, token, oid, "confirm"))
        cancel_task = orch.spawn(http_action(osd1_client, token, oid, "cancel"))

        async with asyncio.timeout(_BUDGET):
            # explicit event handshake for arrival (no polling sleep)
            await asyncio.wait_for(both_arrived.wait(), _BUDGET)
            release_confirm.set()
            # commit observation: bounded fresh-DB read as the handshake for
            # "confirm transaction committed" (HTTP response alone does not
            # prove the middleware commit has landed)
            committed = await _await_committed_status(db, schema, oid, "confirmed")
            assert committed, "confirm never committed within budget — orchestration issue"
            confirm_committed.set()
            results = await asyncio.gather(confirm_task, cancel_task,
                                           return_exceptions=True)
    except TimeoutError:
        orch.timed_out = True
        raise AssertionError(
            "ORCHESTRATION_TIMEOUT: interleaving never completed within "
            f"{_BUDGET}s — not interpretable as a product race defect")
    finally:
        await orch.drain()

    responses = [r for r in results if not isinstance(r, BaseException)]
    errors = [r for r in results if isinstance(r, BaseException)]
    assert not errors, f"transport failures are orchestration errors: {errors}"
    facts = await _race_facts(db, schema, oid)
    confirm_resp = next(r for r in responses if r.request.url.path.endswith("/confirm"))
    assert confirm_resp.status_code == HTTPStatus.OK, confirm_resp.text

    # CONTRACT: after any completed cancel the order owns zero reserved rows.
    # Current product leaves the committed reservation reserved -> RED here;
    # facts were captured before this assertion.
    assert facts["status"] in {"cancelled", "confirmed"}, facts
    if facts["status"] == "cancelled":
        assert facts["reserved_rows"] == 0, (
            f"RED_EVIDENCE orphan reservations on cancelled order: {facts}")
    else:
        pytest.fail(
            f"cancel did not land as last writer (facts={facts}); "
            "interleaving guarantee broken — orchestration issue")
