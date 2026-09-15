"""MPANGO-ORDER-STATE-AUTHORITY-D1 matrix group 2 — double-connection races.

Three race families over the REAL HTTP surface (two concurrent ASGI requests,
each with its own tenant session and its own middleware commit), synchronized
by event barriers around the module-level CRUD names the endpoints call
(``api.v1.orders.crud_confirm_order`` / ``crud_cancel_order``). The barrier
wrappers delegate to the REAL functions unchanged; no sleeps, bounded waits
via ``asyncio.timeout``.

Linearizability oracle: the racing final facts must equal EXACTLY ONE of the
legitimate sequential histories' facts (positive controls in group 1 and
re-run here). A racing outcome matching no sequential history is a lost
update — reported as-is, never masked.

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

_BUDGET = 20.0  # bounded waits, never sleeps


class _ArrivalGate:
    """Barrier wrapper factory: N arrivals park, the last one releases all."""

    def __init__(self, expected: int):
        self.expected = expected
        self.arrived = 0
        self.gate = asyncio.Event()

    async def wait_turn(self) -> None:
        self.arrived += 1
        if self.arrived >= self.expected:
            self.gate.set()
        else:
            async with asyncio.timeout(_BUDGET):
                await self.gate.wait()


async def _seed_confirmed_ready(osd1_client, token, db, pool, reg, qty: int):
    async with bound_retailer(db, pool, reg) as (ret_id, schema, _ws):
        sku, _sid = await seed_sku_with_stock(db, schema, ret_id, quantity=100)
        order = await http_create_wholesaler_order(osd1_client, token, ret_id, sku, qty)
        return order["id"], schema


async def _race_two_actions(client, token, order_id, action_pair, monkeypatch):
    """Launch two HTTP actions concurrently behind arrival gates.

    ``action_pair`` is ``((action, gate), (action, gate))``. Both wrappers
    wait for both arrivals, then delegate to the real CRUD/service function
    the endpoint actually calls.
    """
    import api.v1.orders as orders_api
    from crud import order as crud_order_module_real

    real = {
        "confirm": orders_api.crud_confirm_order,
        "cancel": orders_api.crud_cancel_order,
    }
    names = {"confirm": "crud_confirm_order", "cancel": "crud_cancel_order"}

    def make_wrapper(action, gate):
        base = real[action]

        async def gated(db, order, **kwargs):
            await gate.wait_turn()
            return await base(db, order, **kwargs)

        return gated

    for action, gate in action_pair:
        monkeypatch.setattr(orders_api, names[action], make_wrapper(action, gate))

    async def run(action: str):
        return await http_action(client, token, order_id, action)

    a, b = await asyncio.gather(
        run(action_pair[0][0]), run(action_pair[1][0])
    )
    # keep a hard module reference so linters do not drop the import
    assert crud_order_module_real is not None
    return a, b


async def _await_status(db, schema, order_id, status: str) -> None:
    """Bounded poll (event-loop yield, not sleep-ordered logic) for a commit."""
    async with asyncio.timeout(_BUDGET):
        while True:
            state = await fetch_order_state(db, schema, order_id)
            if state.get("status") == status:
                return
            await asyncio.sleep(0.02)


# ---------------------------------------------------------------------------
# Race family 1: confirm || confirm
# ---------------------------------------------------------------------------


async def test_race_confirm_confirm_exactly_one_success(
    osd1_client, s2_clean_db, provisioned_pool, osd1_cashier, monkeypatch
):
    db, reg = s2_clean_db
    token = await osd1_cashier_token(osd1_client, osd1_cashier)
    oid, schema = await _seed_confirmed_ready(osd1_client, token, db, provisioned_pool, reg, 4)

    gates = (_ArrivalGate(2), _ArrivalGate(2))
    a, b = await _race_two_actions(
        osd1_client, token, oid, (("confirm", gates[0]), ("confirm", gates[1])), monkeypatch
    )
    statuses = sorted([a.status_code, b.status_code])
    assert statuses == [HTTPStatus.OK, HTTPStatus.CONFLICT], (
        f"race outcomes {statuses}: {a.text} | {b.text}")

    facts = await fetch_reservation_facts(db, schema, oid)
    assert facts["reserved_rows"] == 1, f"double reservation leaked: {facts}"
    assert Decimal(facts["reserved_total"]) == Decimal("4")
    state = await fetch_order_state(db, schema, oid)
    assert state["status"] == "confirmed"
    # matches the sequential history: one confirm commits, second 409s
    assert linearizable_final(
        {"status": state["status"], "reserved_rows": facts["reserved_rows"]},
        [{"status": "confirmed", "reserved_rows": 1}],
    )


# ---------------------------------------------------------------------------
# Race family 2: cancel || cancel
# ---------------------------------------------------------------------------


async def test_race_cancel_cancel_must_match_sequential_history(
    osd1_client, s2_clean_db, provisioned_pool, osd1_cashier, monkeypatch
):
    """Both requests validated a pre-loaded CONFIRMED object with no lock and
    no ORM refresh, so both write CANCELLED and both return 200. Sequentially
    the second cancel is a deterministic 409 — no serial history produces two
    successes. Assert the contract (one 200 + one 409); current product
    violates it -> honest RED, evidence preserved."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(osd1_client, osd1_cashier)
    oid, schema = await _seed_confirmed_ready(osd1_client, token, db, provisioned_pool, reg, 3)
    assert (await http_action(osd1_client, token, oid, "confirm")).status_code == HTTPStatus.OK

    gates = (_ArrivalGate(2), _ArrivalGate(2))
    a, b = await _race_two_actions(
        osd1_client, token, oid, (("cancel", gates[0]), ("cancel", gates[1])), monkeypatch
    )
    statuses = sorted([a.status_code, b.status_code])
    assert statuses == [HTTPStatus.OK, HTTPStatus.CONFLICT], (
        f"racing double-cancel accepted both: {statuses}: {a.text} | {b.text}; "
        "sequential control is 200 then 409")

    await assert_no_orphan_reservations(db, schema, oid, expect_status="cancelled")


# ---------------------------------------------------------------------------
# Race family 3: confirm || cancel with cancel committing last
# ---------------------------------------------------------------------------


async def test_race_confirm_then_cancel_last_writer_orphans_reservation(
    osd1_client, s2_clean_db, provisioned_pool, osd1_cashier, monkeypatch
):
    """Deterministic interleaving: both arrive before either writes; confirm
    is released first and COMMITTED (status observed 'confirmed'); cancel —
    validated against its pre-loaded DRAFT object — then overwrites to
    CANCELLED while the committed reservations stay ``reserved``."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(osd1_client, osd1_cashier)
    oid, schema = await _seed_confirmed_ready(osd1_client, token, db, provisioned_pool, reg, 5)

    confirm_arrival, cancel_arrival = _ArrivalGate(1), _ArrivalGate(1)
    shared_gate = _ArrivalGate(2)  # ONE gate both wrappers park on
    import api.v1.orders as orders_api

    real_confirm, real_cancel = orders_api.crud_confirm_order, orders_api.crud_cancel_order

    release_confirm = asyncio.Event()
    confirm_committed = asyncio.Event()

    async def gated_confirm(db, order, **kwargs):
        confirm_arrival.arrived += 1
        await shared_gate.wait_turn()    # both actions arrived
        await release_confirm.wait()     # scheduler releases confirm first
        return await real_confirm(db, order, **kwargs)

    async def gated_cancel(db, order, **kwargs):
        cancel_arrival.arrived += 1
        await shared_gate.wait_turn()    # both actions arrived
        await confirm_committed.wait()   # cancel only proceeds post-commit
        return await real_cancel(db, order, **kwargs)

    monkeypatch.setattr(orders_api, "crud_confirm_order", gated_confirm)
    monkeypatch.setattr(orders_api, "crud_cancel_order", gated_cancel)

    async def run(action):
        return await http_action(osd1_client, token, oid, action)

    confirm_task = asyncio.create_task(run("confirm"))
    cancel_task = asyncio.create_task(run("cancel"))

    async with asyncio.timeout(_BUDGET):
        while confirm_arrival.arrived < 1 or cancel_arrival.arrived < 1:
            await asyncio.sleep(0.01)
        release_confirm.set()

        async def watch_commit():
            while True:
                state = await fetch_order_state(db, schema, oid)
                if state.get("status") == "confirmed":
                    confirm_committed.set()
                    return
                await asyncio.sleep(0.02)

        await asyncio.gather(watch_commit())
        a, b = await asyncio.gather(confirm_task, cancel_task)

    assert a.status_code == HTTPStatus.OK, a.text
    # CONTRACT: after any completed cancel the order owns zero reserved rows.
    # Current product leaves the committed reservation reserved -> RED here.
    await assert_no_orphan_reservations(db, schema, oid, expect_status="cancelled")

    state = await fetch_order_state(db, schema, oid)
    assert state["status"] in {"cancelled", "confirmed"}, state
    assert b.status_code in (HTTPStatus.OK, HTTPStatus.CONFLICT), b.text
