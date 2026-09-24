"""R1 concurrency matrix: two confirms, two cancels, confirm vs cancel,
pay vs cancel — two independent HTTP connections, event barriers, bounded
cleanup, facts captured before assertions. Includes the two-order /
two-SKU / reverse-item-order matrix."""
from __future__ import annotations

import asyncio
from decimal import Decimal
from http import HTTPStatus

import pytest
from sqlalchemy import text

from tests.order_state_r1.support import (
    RaceOrchestrator,
    SharedGate,
    errcode,
    http_action,
    http_create_order,
    inventory_vector,
    make_bound_retailer,
    order_vector,
    osd1_cashier_token,
    reservation_vector,
    seed_sku_with_stock,
)

pytestmark = pytest.mark.asyncio

_BUDGET = 30.0


async def _await_committed_status(db, schema, oid, status_value) -> bool:
    async with asyncio.timeout(10.0):
        while True:
            state = await order_vector(db, schema, oid)
            if state.get("status") == status_value:
                return True
            await asyncio.sleep(0.02)


async def _seed(r1_client, token, db, pool, reg, skus: list[tuple[str, int]]):
    """Create a DRAFT order over (sku_code, quantity) pairs; confirms it if
    requested by the caller afterwards."""
    ret_id, schema, _ws = await make_bound_retailer(db, pool, reg)
    items = [{"sku_code": c, "quantity": q} for c, q in skus]
    oid = await http_create_order(r1_client, token, ret_id, items)
    return oid, schema, ret_id


async def test_two_orders_two_skus_reverse_order_confirm_matrix(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity
):
    """Two orders over the SAME two SKUs with REVERSE item order confirm
    concurrently under an arrival barrier: both succeed, aggregate reserved
    equals the sum, no partial or duplicate reservations."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, _ws = await make_bound_retailer(db, provisioned_pool, reg)
    sku_a, sid_a = await seed_sku_with_stock(db, schema, ret_id, quantity=50, price="10.00")
    sku_b, sid_b = await seed_sku_with_stock(db, schema, ret_id, quantity=50, price="20.00")

    # reverse item order across the two orders over the same SKUs
    oid1 = await http_create_order(r1_client, token, ret_id,
                                   [{"sku_code": sku_a, "quantity": 2},
                                    {"sku_code": sku_b, "quantity": 3}])
    oid2 = await http_create_order(r1_client, token, ret_id,
                                   [{"sku_code": sku_b, "quantity": 4},
                                    {"sku_code": sku_a, "quantity": 5}])

    gate = SharedGate(2)
    import api.v1.orders as orders_api

    real_service = orders_api.OrderCommandService

    class GatedService(real_service):
        async def confirm_order(self, *args, **kwargs):
            await gate.wait_turn()
            return await super().confirm_order(*args, **kwargs)

    monkey = getattr(r1_client, "_monkeypatch", None)
    # patch on the module attribute the endpoint resolves
    orders_api.OrderCommandService = GatedService
    try:
        orch = RaceOrchestrator(_BUDGET)
        try:
            orch.spawn(http_action(r1_client, token, oid1, "confirm"))
            orch.spawn(http_action(r1_client, token, oid2, "confirm"))
            results = await orch.gather_all()
        finally:
            await orch.drain()
    finally:
        orders_api.OrderCommandService = real_service

    assert not any(isinstance(r, BaseException) for r in results), results
    statuses = sorted(r.status_code for r in results)
    assert statuses == [HTTPStatus.OK, HTTPStatus.OK], (
        [r.text for r in results])

    inv = await inventory_vector(db, schema, [sid_a, sid_b])
    assert inv[sid_a] == "50/7", inv   # 2 + 5
    assert inv[sid_b] == "50/7", inv   # 3 + 4
    assert (await order_vector(db, schema, oid1))["status"] == "confirmed"
    assert (await order_vector(db, schema, oid2))["status"] == "confirmed"
    for oid in (oid1, oid2):
        resv = await reservation_vector(db, schema, oid)
        assert len(resv) == 2 and all(r["status"] == "reserved" for r in resv)


async def test_race_confirm_confirm_exactly_one_success(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity
):
    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, _ws = await make_bound_retailer(db, provisioned_pool, reg)
    sku, sid = await seed_sku_with_stock(db, schema, ret_id)
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 4}])

    gate = SharedGate(2)
    import api.v1.orders as orders_api
    real = orders_api.OrderCommandService

    class GatedService(real):
        async def confirm_order(self, *args, **kwargs):
            await gate.wait_turn()
            return await super().confirm_order(*args, **kwargs)

    orders_api.OrderCommandService = GatedService
    try:
        orch = RaceOrchestrator(_BUDGET)
        try:
            orch.spawn(http_action(r1_client, token, oid, "confirm"))
            orch.spawn(http_action(r1_client, token, oid, "confirm"))
            results = await orch.gather_all()
        finally:
            await orch.drain()
    finally:
        orders_api.OrderCommandService = real

    assert not any(isinstance(r, BaseException) for r in results), results
    facts_status = (await order_vector(db, schema, oid))["status"]
    facts = await reservation_vector(db, schema, oid)
    statuses = sorted(r.status_code for r in results)

    assert statuses == [HTTPStatus.OK, HTTPStatus.CONFLICT], (
        [r.text for r in results])
    assert facts_status == "confirmed"
    assert len([r for r in facts if r["status"] == "reserved"]) == 1
    assert Decimal(facts[0]["qty"]) == Decimal("4")


async def test_race_cancel_cancel_one_success_one_conflict(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity
):
    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, _ws = await make_bound_retailer(db, provisioned_pool, reg)
    sku, sid = await seed_sku_with_stock(db, schema, ret_id)
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 3}])
    assert (await http_action(r1_client, token, oid, "confirm")).status_code == 200

    gate = SharedGate(2)
    import api.v1.orders as orders_api
    real = orders_api.OrderCommandService

    class GatedService(real):
        async def cancel_order(self, *args, **kwargs):
            await gate.wait_turn()
            return await super().cancel_order(*args, **kwargs)

    orders_api.OrderCommandService = GatedService
    try:
        orch = RaceOrchestrator(_BUDGET)
        try:
            orch.spawn(http_action(r1_client, token, oid, "cancel"))
            orch.spawn(http_action(r1_client, token, oid, "cancel"))
            results = await orch.gather_all()
        finally:
            await orch.drain()
    finally:
        orders_api.OrderCommandService = real

    assert not any(isinstance(r, BaseException) for r in results), results
    facts = {
        "status": (await order_vector(db, schema, oid))["status"],
        "reservations": await reservation_vector(db, schema, oid),
        "inventory": await inventory_vector(db, schema, [sid]),
    }
    statuses = sorted(r.status_code for r in results)

    assert statuses == [HTTPStatus.OK, HTTPStatus.CONFLICT], (
        f"responses={[r.text for r in results]} facts={facts}")
    assert facts["status"] == "cancelled"
    assert all(r["status"] == "released" for r in facts["reservations"]), facts
    assert facts["inventory"][sid] == "100/0", facts


async def test_race_confirm_then_cancel_releases_reservations(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity
):
    """Deterministic interleaving: confirm commits first (fresh-DB observed),
    then the cancel — which validated a pre-loaded DRAFT object — runs. The
    locked-fresh command must release the committed reservations and leave
    zero orphan reserved rows (the D1 R2 defect is closed)."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, _ws = await make_bound_retailer(db, provisioned_pool, reg)
    sku, sid = await seed_sku_with_stock(db, schema, ret_id)
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 5}])

    import api.v1.orders as orders_api
    real_service = orders_api.OrderCommandService

    confirm_committed = asyncio.Event()
    cancel_arrived = asyncio.Event()

    class GatedService(real_service):
        async def cancel_order(self, *args, **kwargs):
            cancel_arrived.set()
            # proceed ONLY after the confirm transaction is observed
            # committed from a fresh DB read
            await asyncio.wait_for(confirm_committed.wait(), _BUDGET)
            return await super().cancel_order(*args, **kwargs)

    orders_api.OrderCommandService = GatedService
    orch = RaceOrchestrator(_BUDGET)
    try:
        confirm_task = orch.spawn(http_action(r1_client, token, oid, "confirm"))
        cancel_task = orch.spawn(http_action(r1_client, token, oid, "cancel"))
        async with asyncio.timeout(_BUDGET):
            await asyncio.wait_for(cancel_arrived.wait(), _BUDGET)
            committed = await _await_committed_status(db, schema, oid, "confirmed")
            assert committed, "confirm never committed — orchestration issue"
            confirm_committed.set()
            results = await asyncio.gather(confirm_task, cancel_task,
                                           return_exceptions=True)
    except TimeoutError:
        orch.timed_out = True
        raise AssertionError("ORCHESTRATION_TIMEOUT — not a product verdict")
    finally:
        await orch.drain()
        orders_api.OrderCommandService = real_service

    assert not any(isinstance(r, BaseException) for r in results), results
    facts = {
        "status": (await order_vector(db, schema, oid))["status"],
        "reservations": await reservation_vector(db, schema, oid),
        "inventory": await inventory_vector(db, schema, [sid]),
    }
    for r in results:
        assert r.status_code in (HTTPStatus.OK, HTTPStatus.CONFLICT), r.text

    # CONTRACT: whatever the final status, no reserved rows survive a
    # completed cancel, and aggregate reserved matches.
    if facts["status"] == "cancelled":
        assert all(r["status"] == "released" for r in facts["reservations"]), (
            f"OSR1-M3-ORACLE reservations not released after completed "
            f"cancel: {facts}")
        assert facts["inventory"][sid] == "100/0", (
            f"OSR1-M3-ORACLE inventory aggregate not restored after "
            f"cancel: {facts}")
    else:
        assert facts["status"] == "confirmed", facts
        assert facts["inventory"][sid] == "100/5", facts


async def test_race_pay_committed_then_cancel_is_409_workflow_code(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity
):
    """Pay commits first; the racing cancel must fail closed on the
    locked-fresh PAID state with the temporary workflow code — never
    overwrite to cancelled (D1 R4 closed)."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, _ws = await make_bound_retailer(db, provisioned_pool, reg)
    sku, sid = await seed_sku_with_stock(db, schema, ret_id, price="40.00")
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 2}])
    assert (await http_action(r1_client, token, oid, "confirm")).status_code == 200

    import api.v1.orders as orders_api
    real_service = orders_api.OrderCommandService
    pay_started = asyncio.Event()
    pay_committed = asyncio.Event()

    class GatedService(real_service):
        async def cancel_order(self, *args, **kwargs):
            await asyncio.wait_for(pay_committed.wait(), _BUDGET)
            return await super().cancel_order(*args, **kwargs)

    orders_api.OrderCommandService = GatedService
    orch = RaceOrchestrator(_BUDGET)
    try:
        pay_task = orch.spawn(http_action(r1_client, token, oid, "pay",
                                          {"amount": 80.00, "method": "cash"}))
        cancel_task = orch.spawn(http_action(r1_client, token, oid, "cancel"))
        async with asyncio.timeout(_BUDGET):
            pay_started.set()
            committed = await _await_committed_status(db, schema, oid, "paid")
            assert committed, "pay never committed — orchestration issue"
            pay_committed.set()
            results = await asyncio.gather(pay_task, cancel_task,
                                           return_exceptions=True)
    except TimeoutError:
        orch.timed_out = True
        raise AssertionError("ORCHESTRATION_TIMEOUT — not a product verdict")
    finally:
        await orch.drain()
        orders_api.OrderCommandService = real_service

    assert not any(isinstance(r, BaseException) for r in results), results
    pay_resp = next(r for r in results if r.request.url.path.endswith("/pay"))
    cancel_resp = next(r for r in results if r.request.url.path.endswith("/cancel"))
    assert pay_resp.status_code == HTTPStatus.OK, pay_resp.text
    assert cancel_resp.status_code == HTTPStatus.CONFLICT, cancel_resp.text
    assert errcode(cancel_resp) == "REFUND_WORKFLOW_NOT_IMPLEMENTED"
    facts = {
        "status": (await order_vector(db, schema, oid))["status"],
        "inventory": await inventory_vector(db, schema, [sid]),
    }
    assert facts["status"] == "paid", facts
    assert facts["inventory"][sid] == "100/2", facts
