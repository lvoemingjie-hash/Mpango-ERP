"""F1 fix-round RED faces (real HTTP / real service on task PG16).

Faces 1-3 document the credit-hold persistence gap as KNOWN REDs
(CREDIT_HOLD_PERSISTENCE_DECISION_REQUIRED): per-order credit-hold
attribution does not exist — only the aggregate
bindings.outstanding_balance — so cancel cannot release what it cannot
attribute, and confirm->credit-payment double-counts the same exposure in
both the binding aggregate and the receivables summary. These REDs are
evidence for the CTO decision; they are NOT fixed in this round.
Faces 4-6 are fixed this round and must be GREEN.
"""
from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal
from http import HTTPStatus

import pytest
from sqlalchemy import text

from core.domain.order_state import (
    InvalidStateTransitionError,
    OrderInvariantViolation,
    OrderState,
)
from database.session import AsyncSessionLocal
from services.order_command_service import OrderCommandService

from tests.order_state_r1.support import (
    RaceOrchestrator,
    _second_session,
    binding_balance,
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


# ---------------------------------------------------------------------------
# Face 1 (KNOWN RED — credit release on cancel; STOP clause)
# ---------------------------------------------------------------------------


async def test_cancel_after_confirm_releases_credit_hold_KNOWN_RED(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity
):
    """Confirm reserves credit (binding += total); cancelling the confirmed
    order MUST release that hold (binding back to before). Current product
    cannot: no per-order credit-hold attribution exists to release —
    aggregate-only. KNOWN RED pending CREDIT_HOLD_PERSISTENCE_DECISION."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, ws_id = await make_bound_retailer(db, provisioned_pool, reg)
    sku, _sid = await seed_sku_with_stock(db, schema, ret_id, price="30.00")
    before = await binding_balance(db, ws_id, ret_id)
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 2}])  # 60
    assert (await http_action(r1_client, token, oid, "confirm")).status_code == 200
    held = await binding_balance(db, ws_id, ret_id)
    assert held - before == Decimal("60.00")

    resp = await http_action(r1_client, token, oid, "cancel")
    assert resp.status_code == HTTPStatus.OK, resp.text

    after = await binding_balance(db, ws_id, ret_id)
    assert after == before, (
        f"CREDIT_HOLD_PERSISTENCE_DECISION_REQUIRED: cancel did not release "
        f"the confirm-time credit hold (before={before} held={held} "
        f"after_cancel={after}); per-order attribution is missing, the "
        f"aggregate cannot be decremented without guessing")


# ---------------------------------------------------------------------------
# Face 2 (KNOWN RED — confirm + credit payment must not double count)
# ---------------------------------------------------------------------------


async def test_confirm_then_credit_payment_does_not_double_count_KNOWN_RED(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity
):
    """Confirm reserves credit (binding += total); a later full CREDIT
    payment must CONVERT that hold into actual credit exposure — the total
    binding movement across both events must be exactly one total, not
    two. Current product adds the total twice (hold + credit payment
    delta) with no linkage. KNOWN RED pending the same decision."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, ws_id = await make_bound_retailer(db, provisioned_pool, reg)
    sku, _sid = await seed_sku_with_stock(db, schema, ret_id, price="40.00")
    before = await binding_balance(db, ws_id, ret_id)
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 2}])  # 80
    assert (await http_action(r1_client, token, oid, "confirm")).status_code == 200
    held = await binding_balance(db, ws_id, ret_id)
    assert held - before == Decimal("80.00")
    pay = await http_action(r1_client, token, oid, "pay",
                            {"amount": 80.00, "method": "credit"})
    assert pay.status_code == HTTPStatus.OK, pay.text

    # control with cash/transfer on an identical second order: exactly one
    # hold movement (no credit delta on the binding for cash tenders)
    oid2 = await http_create_order(r1_client, token, ret_id,
                                   [{"sku_code": sku, "quantity": 2}])
    assert (await http_action(r1_client, token, oid2, "confirm")).status_code == 200
    mid = await binding_balance(db, ws_id, ret_id)
    pay2 = await http_action(r1_client, token, oid2, "pay",
                             {"amount": 80.00, "method": "transfer"})
    assert pay2.status_code == HTTPStatus.OK, pay2.text
    after = await binding_balance(db, ws_id, ret_id)
    # control: cash/transfer payment must NOT move the binding at all
    # (the mid value itself embeds the known-RED double count and is not
    # asserted absolutely here)
    assert after == mid, (
        "control face: cash/transfer payment must not move the binding "
        f"(mid={mid} after={after})")

    credit_order_after = after - Decimal("80.00")  # strip the control hold
    assert credit_order_after - before == Decimal("80.00"), (
        f"CREDIT_HOLD_PERSISTENCE_DECISION_REQUIRED: confirm-time hold + "
        f"credit payment double-counted the exposure "
        f"(movement={credit_order_after - before}, expected one total of 80.00)")


# ---------------------------------------------------------------------------
# Face 3 (KNOWN RED — receivables summary must not duplicate the exposure)
# ---------------------------------------------------------------------------


async def test_receivables_summary_counts_exposure_once_KNOWN_RED(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity
):
    """Two ISOLATED retailers: (a) confirm-only control — the summary
    reports its hold exactly once (GREEN control face); (b) credit flow —
    the same credit exposure must be counted ONCE in the summary. The
    summary reads the binding aggregate, which double-counts hold+credit
    for the same exposure -> KNOWN RED pending the CTO credit decision."""
    from tests.test_dc12r1_s2_supplier_scoped_retailer_login import (
        _create_binding,
        _create_retailer,
    )
    from services.receivables_service import ReceivablesService

    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_ctrl, schema, ws_id = await make_bound_retailer(db, provisioned_pool, reg)
    # second, isolated retailer for the credit flow
    ret_cred = await _create_retailer(db, name="F2 Credit Retailer", registry=reg)
    await _create_binding(db, wholesaler_id=ws_id, retailer_id=ret_cred,
                          tenant_user_id=str(uuid.uuid4()), registry=reg)
    sku, _sid = await seed_sku_with_stock(db, schema, ret_ctrl, price="25.00")
    sku2, _sid2 = await seed_sku_with_stock(db, schema, ret_cred, price="25.00")

    # (a) confirm-only control: hold 50.00, no payment
    oid_ctrl = await http_create_order(r1_client, token, ret_ctrl,
                                       [{"sku_code": sku, "quantity": 2}])
    assert (await http_action(r1_client, token, oid_ctrl, "confirm")).status_code == 200

    # (b) credit flow: hold 100 then full credit payment
    oid = await http_create_order(r1_client, token, ret_cred,
                                  [{"sku_code": sku2, "quantity": 4}])
    assert (await http_action(r1_client, token, oid, "confirm")).status_code == 200
    pay = await http_action(r1_client, token, oid, "pay",
                            {"amount": 100.00, "method": "credit"})
    assert pay.status_code == HTTPStatus.OK, pay.text

    reader = await _second_session(schema, ws_id)
    try:
        summary = await ReceivablesService().get_receivables_summary(
            tenant_db=reader, wholesaler_id=ws_id)
        rows = summary.get("by_retailer") or []
        by_ret = {str(r.get("retailer_id", "")): r for r in rows}

        ctrl_row = by_ret.get(ret_ctrl)
        assert ctrl_row is not None, f"summary lacks control retailer: {rows}"
        ctrl_out = Decimal(str(ctrl_row.get("outstanding_balance", 0)))
        # control face (current aggregation semantics): the confirm-only
        # order contributes binding hold 50.00 + unpaid_order_balance 50.00
        # = 100.00 — both tracks visible, the hold counted once
        assert ctrl_out == Decimal("100.00"), (
            f"confirm-only control face failed: summary={ctrl_out}, "
            f"expected binding-hold(50)+unpaid(50)=100")

        cred_row = by_ret.get(str(ret_cred))
        assert cred_row is not None, f"summary lacks credit retailer: {rows}"
        cred_out = Decimal(str(cred_row.get("outstanding_balance", 0)))
    finally:
        await reader.close()

    assert cred_out == Decimal("100.00"), (
        f"CREDIT_HOLD_PERSISTENCE_DECISION_REQUIRED: receivables summary "
        f"double-counts the same exposure (got {cred_out}, expected "
        f"100.00 exactly once for the credit order)")


# ---------------------------------------------------------------------------
# Face 4 (FIXED this round): generic transition dispatch-or-reject
# ---------------------------------------------------------------------------


async def test_generic_transition_refuses_command_owned_targets(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity
):
    """apply_transition must refuse CONFIRMED/CANCELLED/PAID/FULFILLED/
    RETURNED; only the explicit commands (and the canonical payment path)
    write those states. VOIDED remains service-internal."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, ws_id = await make_bound_retailer(db, provisioned_pool, reg)
    sku, _sid = await seed_sku_with_stock(db, schema, ret_id)
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 1}])

    session = await _second_session(schema, ws_id)
    try:
        for target in (OrderState.CONFIRMED, OrderState.CANCELLED,
                       OrderState.PAID, OrderState.PARTIALLY_PAID,
                       OrderState.FULFILLED, OrderState.RETURNED):
            try:
                await OrderCommandService(session).apply_transition(
                    uuid.UUID(oid), target)
            except InvalidStateTransitionError:
                pass
            else:
                raise AssertionError(
                    f"OSR1-M8-ORACLE generic transition accepted "
                    f"command-owned target {target.value}")
            await session.rollback()
            from tests.order_state_r1.support import rebind_search_path
            await rebind_search_path(session, schema)
        # the state was never touched by the refusals
        assert (await order_vector(session, schema, oid))["status"] == "draft"
    finally:
        await session.rollback()
        await session.close()


async def test_adapter_transition_refuses_confirm_and_cancel(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity
):
    from services.order_service import OrderService

    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, ws_id = await make_bound_retailer(db, provisioned_pool, reg)
    sku, _sid = await seed_sku_with_stock(db, schema, ret_id)
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 1}])

    session = await _second_session(schema, ws_id)
    try:
        for target in (OrderState.CONFIRMED, OrderState.CANCELLED,
                       OrderState.FULFILLED, OrderState.RETURNED):
            with pytest.raises(InvalidStateTransitionError):
                await OrderService(session).transition(uuid.UUID(oid), target)
            await session.rollback()
            from tests.order_state_r1.support import rebind_search_path
            await rebind_search_path(session, schema)
        assert (await order_vector(session, schema, oid))["status"] == "draft"
    finally:
        await session.rollback()
        await session.close()


# ---------------------------------------------------------------------------
# Face 5 (FIXED this round): client repeated / paid cancel stable 409
# ---------------------------------------------------------------------------


async def test_client_repeated_and_paid_cancel_return_stable_409(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity, two_tenants
):
    from tests.test_dc12r1_s3_s2b_i2b_payment_declarations import (
        _resolve_binding_retailer,
    )

    db, reg = s2_clean_db
    admin = await osd1_cashier_token(r1_client, cashier_identity)
    code_a, _b, _sb, email, password, uid_a, _ub = two_tenants
    a = provisioned_pool.tenants["a"]
    schema, ws_id = a["schema"], a["ws_id"]

    resp = await r1_client.post(
        "/api/v1/client/auth/login",
        json={"email": email, "password": password,
              "wholesaler_code": code_a})
    assert resp.status_code == 200, resp.text
    token_c = resp.json()["data"]["tokens"]["access_token"]

    # retailer owned by this client user (binding tenant_user_id = uid_a)
    ret_id = await _resolve_binding_retailer(db, ws_id, uid_a)
    sku, _sid = await seed_sku_with_stock(db, schema, ret_id, price="10.00")
    # create via admin on the bound retailer; the client user owns it via
    # the binding created in make_bound_retailer (tenant_user random) —
    # instead create through the CLIENT API itself for correct ownership
    resp = await r1_client.post(
        "/api/v1/client/orders",
        json={"items": [{"sku_code": sku, "quantity": 2}]},
        headers={"Authorization": f"Bearer {token_c}"})
    assert resp.status_code == 201, resp.text
    oid = resp.json()["data"]["id"]

    first = await r1_client.post(f"/api/v1/client/orders/{oid}/cancel",
                                 headers={"Authorization": f"Bearer {token_c}"})
    assert first.status_code == HTTPStatus.OK, first.text
    second = await r1_client.post(f"/api/v1/client/orders/{oid}/cancel",
                                  headers={"Authorization": f"Bearer {token_c}"})
    assert second.status_code == HTTPStatus.CONFLICT, second.text
    assert errcode(second) == "CANCEL_NOT_ALLOWED", second.text

    # paid cancel: same stable 409 (workflow code surfaces)
    resp2 = await r1_client.post(
        "/api/v1/client/orders",
        json={"items": [{"sku_code": sku, "quantity": 2}]},
        headers={"Authorization": f"Bearer {token_c}"})
    oid2 = resp2.json()["data"]["id"]
    assert (await http_action(r1_client, admin, oid2, "confirm")).status_code == 200
    pay = await http_action(r1_client, admin, oid2, "pay",
                            {"amount": 20.00, "method": "cash"})
    assert pay.status_code == 200, pay.text
    paid_cancel = await r1_client.post(
        f"/api/v1/client/orders/{oid2}/cancel",
        headers={"Authorization": f"Bearer {token_c}"})
    assert paid_cancel.status_code == HTTPStatus.CONFLICT, paid_cancel.text
    code = errcode(paid_cancel)
    assert code in {"REFUND_WORKFLOW_NOT_IMPLEMENTED", "CANCEL_NOT_ALLOWED"}, code
    # stable on repeat
    again = await r1_client.post(
        f"/api/v1/client/orders/{oid2}/cancel",
        headers={"Authorization": f"Bearer {token_c}"})
    assert again.status_code == HTTPStatus.CONFLICT
    assert errcode(again) == code


# ---------------------------------------------------------------------------
# Face 6 (FIXED this round): two orders / two SKUs / reverse item order —
# fulfill and return racing under an arrival barrier
# ---------------------------------------------------------------------------


async def test_fulfill_and_return_concurrent_two_orders_two_skus(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity
):
    """Order A (reverse items B,A) pays then FULFILLS while order B (items
    A,B) is fulfilled then RETURNS, concurrently under a barrier: both
    succeed; per-SKU on-hand returns to its pre-fulfillment value for the
    returned order and decreases for the fulfilled one; zero orphans."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, _ws = await make_bound_retailer(db, provisioned_pool, reg)
    sku_a, sid_a = await seed_sku_with_stock(db, schema, ret_id, quantity=100, price="10.00")
    sku_b, sid_b = await seed_sku_with_stock(db, schema, ret_id, quantity=100, price="20.00")

    # order A: reverse item order (B then A)
    oid_a = await http_create_order(r1_client, token, ret_id,
                                    [{"sku_code": sku_b, "quantity": 2},
                                     {"sku_code": sku_a, "quantity": 3}])
    # order B: (A then B)
    oid_b = await http_create_order(r1_client, token, ret_id,
                                    [{"sku_code": sku_a, "quantity": 4},
                                     {"sku_code": sku_b, "quantity": 5}])
    for oid, total in ((oid_a, "70.00"), (oid_b, "140.00")):
        assert (await http_action(r1_client, token, oid, "confirm")).status_code == 200
        pay = await http_action(r1_client, token, oid, "pay",
                                {"amount": total, "method": "cash"})
        assert pay.status_code == 200, pay.text
    assert (await http_action(r1_client, token, oid_b, "fulfill")).status_code == 200

    import api.v1.orders as orders_api
    real_service = orders_api.OrderCommandService

    gate_arrived = asyncio.Event()
    gate_release = asyncio.Event()
    counts = {"fulfill": 0, "return": 0}

    class GatedService(real_service):
        async def fulfill_order(self, *args, **kwargs):
            counts["fulfill"] += 1
            if counts["fulfill"] == 1:
                gate_arrived.set()
                await asyncio.wait_for(gate_release.wait(), 30.0)
            return await super().fulfill_order(*args, **kwargs)

        async def return_order(self, *args, **kwargs):
            counts["return"] += 1
            if counts["return"] == 1:
                gate_arrived.set()
                await asyncio.wait_for(gate_release.wait(), 30.0)
            return await super().return_order(*args, **kwargs)

    orders_api.OrderCommandService = GatedService
    orch = RaceOrchestrator(30.0)
    try:
        t_fulfill = orch.spawn(http_action(r1_client, token, oid_a, "fulfill"))
        t_return = orch.spawn(http_action(r1_client, token, oid_b, "return"))
        async with asyncio.timeout(30.0):
            await asyncio.wait_for(gate_arrived.wait(), 30.0)
            gate_release.set()
            results = await asyncio.gather(t_fulfill, t_return,
                                           return_exceptions=True)
    except TimeoutError:
        orch.timed_out = True
        raise AssertionError("ORCHESTRATION_TIMEOUT — not a product verdict")
    finally:
        await orch.drain()
        orders_api.OrderCommandService = real_service

    assert not any(isinstance(r, BaseException) for r in results), results
    for r in results:
        assert r.status_code == HTTPStatus.OK, r.text

    inv = await inventory_vector(db, schema, [sid_a, sid_b])
    # B was fulfilled in the pre-step (a-4, b-5); the race then fulfills A
    # (a-3, b-2) and returns B (a+4, b+5 restored). Net: a=97, b=98,
    # zero reserved.
    assert inv[sid_a] == "97/0", inv
    assert inv[sid_b] == "98/0", inv
    for oid in (oid_a, oid_b):
        resv = await reservation_vector(db, schema, oid)
        assert all(r["status"] in {"consumed", "released"} for r in resv), resv
    assert (await order_vector(db, schema, oid_a))["status"] == "fulfilled"
    assert (await order_vector(db, schema, oid_b))["status"] == "returned"


# ---------------------------------------------------------------------------
# F2 faces: confirm‖fulfill and cancel‖fulfill — two orders, two SKUs,
# reverse item order, real PG, arrival barriers
# ---------------------------------------------------------------------------


async def _seed_two_sku_paid_pair(r1_client, token, db, pool, reg):
    """Return (schema, sku pair, draft order A reverse, paid order B)."""
    ret_id, schema, _ws = await make_bound_retailer(db, pool, reg)
    sku_a, sid_a = await seed_sku_with_stock(db, schema, ret_id, quantity=100, price="10.00")
    sku_b, sid_b = await seed_sku_with_stock(db, schema, ret_id, quantity=100, price="20.00")
    # order A: REVERSE item order (B then A), left DRAFT
    oid_a = await http_create_order(r1_client, token, ret_id,
                                    [{"sku_code": sku_b, "quantity": 2},
                                     {"sku_code": sku_a, "quantity": 3}])
    # order B: (A then B), confirmed + paid, ready to fulfill
    oid_b = await http_create_order(r1_client, token, ret_id,
                                    [{"sku_code": sku_a, "quantity": 4},
                                     {"sku_code": sku_b, "quantity": 5}])
    assert (await http_action(r1_client, token, oid_b, "confirm")).status_code == 200
    pay = await http_action(r1_client, token, oid_b, "pay",
                            {"amount": 140.00, "method": "cash"})
    assert pay.status_code == 200, pay.text
    return schema, (sid_a, sid_b), oid_a, oid_b


def _gated_command(r1_client_module_orders, gate_first, gate_second):
    """Build a GatedService releasing both after arrival, first-writer
    deterministic via gate_first/gate_second events."""
    import asyncio

    real_service = r1_client_module_orders.OrderCommandService
    arrive = {"a": False, "b": False}
    both = asyncio.Event()

    class GatedService(real_service):
        async def confirm_order(self, *args, **kwargs):
            arrive["a"] = True
            if arrive["b"]:
                both.set()
            await asyncio.wait_for(both.wait(), 30.0)
            await gate_first.wait()
            return await super().confirm_order(*args, **kwargs)

        async def cancel_order(self, *args, **kwargs):
            arrive["a"] = True
            if arrive["b"]:
                both.set()
            await asyncio.wait_for(both.wait(), 30.0)
            await gate_first.wait()
            return await super().cancel_order(*args, **kwargs)

        async def fulfill_order(self, *args, **kwargs):
            arrive["b"] = True
            if arrive["a"]:
                both.set()
            await asyncio.wait_for(both.wait(), 30.0)
            await gate_second.wait()
            return await super().fulfill_order(*args, **kwargs)

    return real_service, GatedService


async def test_confirm_vs_fulfill_two_orders_two_skus_reverse(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity
):
    """Order A (draft, reverse items) CONFIRMS while order B (paid, A-then-B
    items) FULFILLS concurrently under an arrival barrier with the shared
    prelock strategy: both succeed; aggregates exact; zero orphans."""
    import asyncio
    from http import HTTPStatus as HS

    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    schema, (sid_a, sid_b), oid_a, oid_b = await _seed_two_sku_paid_pair(
        r1_client, token, db, provisioned_pool, reg)

    import api.v1.orders as orders_api
    real_service = orders_api.OrderCommandService

    a_arrived = asyncio.Event()
    b_arrived = asyncio.Event()
    both = asyncio.Event()
    flags = {"a": False, "b": False}
    release = asyncio.Event()

    class GatedService(real_service):
        async def confirm_order(self, *args, **kwargs):
            flags["a"] = True; a_arrived.set()
            if flags["b"]: both.set()
            await asyncio.wait_for(both.wait(), 30.0)
            await asyncio.wait_for(release.wait(), 30.0)
            return await super().confirm_order(*args, **kwargs)

        async def fulfill_order(self, *args, **kwargs):
            flags["b"] = True; b_arrived.set()
            if flags["a"]: both.set()
            await asyncio.wait_for(both.wait(), 30.0)
            await asyncio.wait_for(release.wait(), 30.0)
            return await super().fulfill_order(*args, **kwargs)

    orders_api.OrderCommandService = GatedService
    orch = RaceOrchestrator(30.0)
    try:
        t_confirm = orch.spawn(http_action(r1_client, token, oid_a, "confirm"))
        t_fulfill = orch.spawn(http_action(r1_client, token, oid_b, "fulfill"))
        async with asyncio.timeout(30.0):
            await asyncio.wait_for(asyncio.gather(
                a_arrived.wait(), b_arrived.wait()), 30.0)
            release.set()
            results = await asyncio.gather(t_confirm, t_fulfill,
                                           return_exceptions=True)
    except TimeoutError:
        orch.timed_out = True
        raise AssertionError("ORCHESTRATION_TIMEOUT — not a product verdict")
    finally:
        await orch.drain()
        orders_api.OrderCommandService = real_service

    assert not any(isinstance(r, BaseException) for r in results), results
    for r in results:
        assert r.status_code == HS.OK, r.text

    inv = await inventory_vector(db, schema, [sid_a, sid_b])
    # A reserves a3/b2; B fulfillment consumes its reserved a4/b5 (deduct
    # on-hand only): a=96/7? no — deduct on_hand -4/-5, reserved -4/-5.
    assert inv[sid_a] == "96/3", inv
    assert inv[sid_b] == "95/2", inv
    assert (await order_vector(db, schema, oid_a))["status"] == "confirmed"
    assert (await order_vector(db, schema, oid_b))["status"] == "fulfilled"


async def test_cancel_vs_fulfill_two_orders_two_skus_reverse(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity
):
    """Order A (confirmed earlier, reverse items) CANCELS while order B
    (paid, A-then-B) FULFILLS concurrently: both succeed; released and
    consumed aggregates exact; zero reserved rows remain."""
    import asyncio
    from http import HTTPStatus as HS

    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    schema, (sid_a, sid_b), oid_a, oid_b = await _seed_two_sku_paid_pair(
        r1_client, token, db, provisioned_pool, reg)
    # order A must be CONFIRMED to have reservations to release
    assert (await http_action(r1_client, token, oid_a, "confirm")).status_code == 200

    import api.v1.orders as orders_api
    real_service = orders_api.OrderCommandService

    a_arrived = asyncio.Event()
    b_arrived = asyncio.Event()
    both = asyncio.Event()
    flags = {"a": False, "b": False}
    release = asyncio.Event()

    class GatedService(real_service):
        async def cancel_order(self, *args, **kwargs):
            flags["a"] = True; a_arrived.set()
            if flags["b"]: both.set()
            await asyncio.wait_for(both.wait(), 30.0)
            await asyncio.wait_for(release.wait(), 30.0)
            return await super().cancel_order(*args, **kwargs)

        async def fulfill_order(self, *args, **kwargs):
            flags["b"] = True; b_arrived.set()
            if flags["a"]: both.set()
            await asyncio.wait_for(both.wait(), 30.0)
            await asyncio.wait_for(release.wait(), 30.0)
            return await super().fulfill_order(*args, **kwargs)

    orders_api.OrderCommandService = GatedService
    orch = RaceOrchestrator(30.0)
    try:
        t_cancel = orch.spawn(http_action(r1_client, token, oid_a, "cancel"))
        t_fulfill = orch.spawn(http_action(r1_client, token, oid_b, "fulfill"))
        async with asyncio.timeout(30.0):
            await asyncio.wait_for(asyncio.gather(
                a_arrived.wait(), b_arrived.wait()), 30.0)
            release.set()
            results = await asyncio.gather(t_cancel, t_fulfill,
                                           return_exceptions=True)
    except TimeoutError:
        orch.timed_out = True
        raise AssertionError("ORCHESTRATION_TIMEOUT — not a product verdict")
    finally:
        await orch.drain()
        orders_api.OrderCommandService = real_service

    assert not any(isinstance(r, BaseException) for r in results), results
    for r in results:
        assert r.status_code == HS.OK, r.text

    inv = await inventory_vector(db, schema, [sid_a, sid_b])
    # A released its a3/b2; B consumed its a4/b5: net a=96/0, b=95/0
    assert inv[sid_a] == "96/0", inv
    assert inv[sid_b] == "95/0", inv
    for oid, want in ((oid_a, "cancelled"), (oid_b, "fulfilled")):
        assert (await order_vector(db, schema, oid))["status"] == want
    for oid in (oid_a, oid_b):
        resv = await reservation_vector(db, schema, oid)
        assert all(r["status"] in {"released", "consumed"} for r in resv), resv


async def test_generic_refuses_partially_paid_on_confirmed(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity
):
    """M11 oracle: even a matrix-legal CONFIRMED->PARTIALLY_PAID edge must
    be refused by the GENERIC transition (PARTIALLY_PAID is command-owned;
    only the canonical payment command may write it)."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, ws_id = await make_bound_retailer(db, provisioned_pool, reg)
    sku, _sid = await seed_sku_with_stock(db, schema, ret_id)
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 2}])
    assert (await http_action(r1_client, token, oid, "confirm")).status_code == 200

    session = await _second_session(schema, ws_id)
    try:
        rejected = False
        try:
            await OrderCommandService(session).apply_transition(
                uuid.UUID(oid), OrderState.PARTIALLY_PAID)
        except InvalidStateTransitionError:
            rejected = True
        assert rejected, (
            "OSR1-M11-ORACLE generic transition accepted command-owned "
            "PARTIALLY_PAID on a CONFIRMED order")
    finally:
        await session.rollback()
        await session.close()


async def test_client_domain_errors_map_to_409_clean(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity, two_tenants
):
    """M10 oracle (clean, no pytest-error propagation): cancelling a
    terminal/duplicate order through the CLIENT route must surface as an
    HTTP 409 — if the domain error escapes unmapped, this captures it and
    fails with the named marker instead of erroring the test."""
    from tests.test_dc12r1_s3_s2b_i2b_payment_declarations import (
        _resolve_binding_retailer,
    )

    db, reg = s2_clean_db
    code_a, _b, _sb, email, password, uid_a, _ub = two_tenants
    a = provisioned_pool.tenants["a"]
    schema = a["schema"]

    resp = await r1_client.post(
        "/api/v1/client/auth/login",
        json={"email": email, "password": password, "wholesaler_code": code_a})
    assert resp.status_code == 200, resp.text
    token_c = resp.json()["data"]["tokens"]["access_token"]
    ret_id = await _resolve_binding_retailer(db, a["ws_id"], uid_a)
    sku, _sid = await seed_sku_with_stock(db, schema, ret_id, price="10.00")

    created = await r1_client.post(
        "/api/v1/client/orders",
        json={"items": [{"sku_code": sku, "quantity": 1}]},
        headers={"Authorization": f"Bearer {token_c}"})
    assert created.status_code == 201, created.text
    oid = created.json()["data"]["id"]
    first = await r1_client.post(f"/api/v1/client/orders/{oid}/cancel",
                                 headers={"Authorization": f"Bearer {token_c}"})
    assert first.status_code == 200, first.text

    try:
        second = await r1_client.post(
            f"/api/v1/client/orders/{oid}/cancel",
            headers={"Authorization": f"Bearer {token_c}"})
        assert second.status_code == 409, (
            f"expected stable 409, got {second.status_code}: {second.text}")
    except Exception as exc:  # unmapped domain exception escaped the route
        raise AssertionError(
            f"unmapped domain exception propagated to the client: "
            f"{type(exc).__name__}: {exc}") from exc


async def test_client_cancel_route_maps_domain_errors_409_direct(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity, two_tenants
):
    """M10 oracle (direct route call — no ASGI propagation, zero teardown
    pollution): the client cancel ROUTE maps domain transition errors to
    HTTP 409 CANCEL_NOT_ALLOWED. Under the M10 mutation the domain error
    escapes unmapped and this fails cleanly with the named marker."""
    from fastapi import HTTPException as _HttpExc
    from tests.test_dc12r1_s3_s2b_i2b_payment_declarations import (
        _resolve_binding_retailer,
    )
    from api.v1.client.orders import cancel_order as _client_cancel_route
    from api.v1.client.dependencies import ClientIdentity

    db, reg = s2_clean_db
    code_a, _b, _sb, email, password, uid_a, _ub = two_tenants
    a = provisioned_pool.tenants["a"]
    schema, ws_id = a["schema"], a["ws_id"]
    admin = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id = await _resolve_binding_retailer(db, ws_id, uid_a)
    sku, _sid = await seed_sku_with_stock(db, schema, ret_id, price="10.00")
    oid = await http_create_order(r1_client, admin, ret_id,
                                  [{"sku_code": sku, "quantity": 1}])
    assert (await http_action(r1_client, admin, oid, "confirm")).status_code == 200
    # make the order TERMINAL so the route must map a domain error to 409
    assert (await http_action(r1_client, admin, oid, "cancel")).status_code == 200

    from tests.order_state_r1.support import rebind_search_path
    await rebind_search_path(db, schema)
    identity = ClientIdentity(
        user_id=uid_a, retailer_id=ret_id, tenant_id=ws_id, token=None)
    try:
        # terminal-state cancel through the route: must surface HTTP 409
        await _client_cancel_route(order_id=oid, client=identity, db=db)
        raise AssertionError("unmapped: route returned without the 409 mapping")
    except _HttpExc as exc:
        assert exc.status_code == 409, (
            f"unmapped domain exception escaped as {exc.status_code}")
        assert exc.detail["code"] in {
            "REFUND_WORKFLOW_NOT_IMPLEMENTED", "CANCEL_NOT_ALLOWED"}, exc.detail
    finally:
        await db.rollback()
