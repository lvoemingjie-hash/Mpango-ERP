"""MPANGO-MVP-INVARIANTS-R0 — concurrency regression candidates (known-RED).

Converts the external architecture review's reproduced counterexamples into
formal pytest cases on the frozen baseline bd2373cbfeafde07f1771aba2089f0d1b5f0cd3f.

THIS FILE IS A REGRESSION CANDIDATE, NOT A GREEN MERGE CANDIDATE:
tests marked [TARGET-DEFECT RED] assert the business invariant that the
external review showed the baseline violates. They are expected to FAIL
(named RED) until the product is fixed. Never edit the expectation to make
them pass — fix the product instead.

External evidence (AI_REPORT_INBOX/external-architecture-2026-09-06):
- counterexamples.json: concurrent_stock_adjustment actual=15 (expected 22)
- supplementary-probes.json: two_return_requests_for_one_100_order
  refund cash=-200, 2 positive inventory movements (expected 1 each)

Environment premises (checked by guards, see mpango_invariants_r0_support):
- Task-exclusive disposable loopback PostgreSQL (TEST_DATABASE_URL).
- Public schema migrated to the baseline head (037_payment_declarations_schema).
- Real product services and route functions; no SQL mocking; deterministic
  asyncio-event barriers across two real sessions/connections.

Execution entry points per test are stated in each docstring, including what
the direct route-function call path does NOT cover (HTTP dependency layer).
"""
from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from api.v1 import orders as order_routes
from crud.order import get_order_by_id
from fastapi import HTTPException
from repositories.inventory_repository import InventoryRepository
from schemas.order import PayOrderRequest, WholesalerOrderCreateRequest
from services.inventory_service import InventoryService

from tests.mpango_invariants_r0_support import (
    R0Token,
    adjustment_movements,
    assert_loopback_test_database,
    bootstrap_tenant,
    drop_tenant,
    new_tenant_identity,
    require_jwt_auth_strategy,
    seed_public_tenant_rows,
    seed_sku_with_stock,
    stock_on_hand,
    tenant_session,
)


def setup_module(module) -> None:  # noqa: ANN001
    assert_loopback_test_database()


async def _make_tenant(fixtures_registry: list):
    wholesaler_id, retailer_id, schema = new_tenant_identity()
    await bootstrap_tenant(schema)
    await seed_public_tenant_rows(wholesaler_id=wholesaler_id, retailer_id=retailer_id)
    fixtures_registry.append((schema, wholesaler_id, retailer_id))
    return wholesaler_id, retailer_id, schema


async def _drop_tenant(schema, wholesaler_id, retailer_id) -> None:
    await drop_tenant(schema, wholesaler_id=wholesaler_id, retailer_id=retailer_id)


# ---------------------------------------------------------------------------
# Lifecycle helpers (real order entry points)
# ---------------------------------------------------------------------------

async def _create_confirmed_order(
    *,
    schema: str,
    wholesaler_id: uuid.UUID,
    retailer_id: uuid.UUID,
    user_id: uuid.UUID,
    sku_code: str = "R0-BOX",
    quantity: int = 1,
    unit_price: Decimal = Decimal("100.00"),
) -> str:
    """Create + confirm an order through the real route functions.

    create_order route: binding check, server-side price resolution from
    retailer_prices, crud create. confirm_order route: crud confirm +
    InventoryService.reserve_on_confirm. Both commit at the end of the helper
    (route functions only flush; the HTTP transaction owner is the auth
    middleware, which direct calls bypass — the helper commits instead).
    """
    async with tenant_session(schema, wholesaler_id) as db:
        token = R0Token(tenant_id=wholesaler_id, tenant_schema=schema, user_id=user_id)
        request = WholesalerOrderCreateRequest(
            retailer_id=str(retailer_id),
            items=[{"sku_code": sku_code, "quantity": quantity}],
        )
        response = await order_routes.create_order(request=request, token=token, db=db)
        order_id = response.data.id
    async with tenant_session(schema, wholesaler_id) as db:
        token = R0Token(tenant_id=wholesaler_id, tenant_schema=schema, user_id=user_id)
        await order_routes.confirm_order(order_id=order_id, token=token, db=db)
    return order_id


async def _pay_full_cash(
    *,
    schema: str,
    wholesaler_id: uuid.UUID,
    retailer_id: uuid.UUID,
    user_id: uuid.UUID,
    order_id: str,
    total: Decimal = Decimal("100.00"),
) -> None:
    async with tenant_session(schema, wholesaler_id) as db:
        token = R0Token(tenant_id=wholesaler_id, tenant_schema=schema, user_id=user_id)
        await order_routes.pay_order(
            order_id=order_id,
            token=token,
            db=db,
            payment_input=PayOrderRequest(amount=total, method="cash"),
            x_idempotency_key=f"r0-pay-{uuid.uuid4().hex[:24]}",
        )


async def _fulfill(
    *,
    schema: str,
    wholesaler_id: uuid.UUID,
    user_id: uuid.UUID,
    order_id: str,
) -> None:
    async with tenant_session(schema, wholesaler_id) as db:
        token = R0Token(tenant_id=wholesaler_id, tenant_schema=schema, user_id=user_id)
        await order_routes.fulfill_order(order_id=order_id, token=token, db=db)


# ---------------------------------------------------------------------------
# Snapshot helpers
# ---------------------------------------------------------------------------

async def _refund_snapshot(db, *, order_id: str) -> dict:
    refund = dict(
    (
        await db.execute(
            text(
                "SELECT account_type::text AS t, COALESCE(sum(amount), 0)::text AS s "
                "FROM ledger_entries WHERE reference_type = 'refund' "
                "AND reference_id = :oid GROUP BY account_type"
            ),
            {"oid": uuid.UUID(order_id)},
        )
    ).all()
    )
    restock_count = (
        await db.execute(
            text(
                "SELECT count(*) FROM inventory_movements "
                "WHERE reference_type = 'order' AND reference_id = :oid AND quantity > 0"
            ),
            {"oid": uuid.UUID(order_id)},
        )
    ).scalar_one()
    status = (
        await db.execute(
            text("SELECT status::text FROM orders WHERE id = :oid"),
            {"oid": uuid.UUID(order_id)},
        )
    ).scalar_one()
    return {
        "refund_by_account": refund,
        "refund_cash": Decimal(refund.get("cash", "0")),
        "restock_movement_count": int(restock_count),
        "order_status": status,
    }


# ---------------------------------------------------------------------------
# 1. Focused control: single adjustment applies and failed adjustment rolls back
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_r0_control_single_adjustment_and_failed_adjustment_rollback():
    """[CONTROL — expected PASS] Plain inventory adjustment semantics.

    正常对照: one +7 adjustment through the real adjustment service applies
    exactly once and journals one movement; a failing (negative-result)
    adjustment leaves neither value nor movement behind.
    目标缺陷: none — this pins the semantics the RED tests rely on.
    环境前提: task-exclusive loopback PostgreSQL, tenant schema built by the
    product's own bootstrap DDL.
    执行入口: InventoryService.adjust_stock — the exact function
    POST /api/v1/inventory/adjust calls (route adds permission + logging only).
    未覆盖范围: HTTP layer of /inventory/adjust and RBAC.
    """
    registry: list = []
    wholesaler_id, retailer_id, schema = await _make_tenant(registry)
    try:
        async with tenant_session(schema, wholesaler_id) as db:
            await seed_sku_with_stock(db, sku_code="R0-CTL", quantity_on_hand=Decimal("10"))

        async with tenant_session(schema, wholesaler_id) as db:
            stock, movement = await InventoryService().adjust_stock(
                db, sku_code="R0-CTL", quantity=Decimal("7"), reason="r0 control +7"
            )
            assert Decimal(str(movement.quantity_before)) == Decimal("10")
            assert Decimal(str(movement.quantity_after)) == Decimal("17")
        async with tenant_session(schema, wholesaler_id) as db:
            assert await stock_on_hand(db, sku_code="R0-CTL") == Decimal("17.00")
            movements = await adjustment_movements(db, sku_code="R0-CTL")
            assert len(movements) == 1
            assert Decimal(movements[0]["qty"]) == Decimal("7")

        # Failing adjustment: full rollback of value and journal entry.
        async with tenant_session(schema, wholesaler_id) as db:
            with pytest.raises(HTTPException) as excinfo:
                await InventoryService().adjust_stock(
                    db, sku_code="R0-CTL", quantity=Decimal("-50"), reason="r0 control -50"
                )
            assert excinfo.value.status_code == 409
            assert excinfo.value.detail["code"] == "NEGATIVE_STOCK"
        async with tenant_session(schema, wholesaler_id) as db:
            assert await stock_on_hand(db, sku_code="R0-CTL") == Decimal("17.00")
            assert len(await adjustment_movements(db, sku_code="R0-CTL")) == 1
    finally:
        await _drop_tenant(schema, wholesaler_id, retailer_id)


# ---------------------------------------------------------------------------
# 2. TARGET-DEFECT RED: concurrent adjustments must not lose an update
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_r0_red_concurrent_stock_adjustments_no_lost_update():
    """[TARGET-DEFECT RED] Inventory 10 + concurrent +7 and +5 must be 22.

    Invariant (REVIEW §2.1 fix goal): every adjustment computes from the
    post-lock latest value; two successful adjustments both survive; the two
    movement rows, the current value and failure rollback stay consistent.

    正常对照: control test above proves single adjustments are correct.
    目标缺陷: inventory_service.adjust_stock re-selects the stock row with
    FOR UPDATE but without populate_existing, so the ORM identity map keeps
    the stale pre-lock quantity and the second committer's increment is
    silently overwritten (external counterexample: 10 +7 +5 → 15).
    环境前提: two real sessions/connections on the task-exclusive database;
    barrier = asyncio.Event set inside a repository read wrapper (timing
    control only — the wrapper never alters SQL results).
    执行入口: InventoryService.adjust_stock (the POST /inventory/adjust
    service), two interleaved transactions, each committing on its own
    connection. HTTP dependency layer not covered (documented probe boundary).
    未覆盖范围: POST /inventory/adjust HTTP/RBAC layer; multi-worker timing.

    Expected RED failure names:
      INVARIANT_R0_STOCK_LOST_UPDATE — final on-hand must be 22.00
      INVARIANT_R0_STOCK_MOVEMENT_CHAIN — movements must chain
          before→after ending at the final on-hand value.
    """
    registry: list = []
    wholesaler_id, retailer_id, schema = await _make_tenant(registry)
    try:
        async with tenant_session(schema, wholesaler_id) as db:
            await seed_sku_with_stock(db, sku_code="R0-RACE", quantity_on_hand=Decimal("10"))

        first_read = asyncio.Event()
        resume = asyncio.Event()

        class PausingRepository(InventoryRepository):
            async def get_stock_by_sku_code(self, db, *, sku_code):  # noqa: ANN001
                row = await super().get_stock_by_sku_code(db, sku_code=sku_code)
                if sku_code == "R0-RACE":
                    first_read.set()
                    await resume.wait()
                return row

        async def adjustment_a():
            async with tenant_session(schema, wholesaler_id) as db_a:
                await InventoryService(PausingRepository()).adjust_stock(
                    db_a, sku_code="R0-RACE", quantity=Decimal("5"), reason="r0 race A(+5)"
                )

        task_a = asyncio.create_task(adjustment_a())
        await asyncio.wait_for(first_read.wait(), timeout=30)
        async with tenant_session(schema, wholesaler_id) as db_b:
            await InventoryService().adjust_stock(
                db_b, sku_code="R0-RACE", quantity=Decimal("7"), reason="r0 race B(+7)"
            )
        resume.set()
        await asyncio.wait_for(task_a, timeout=30)

        async with tenant_session(schema, wholesaler_id) as db:
            final = await stock_on_hand(db, sku_code="R0-RACE")
            movements = await adjustment_movements(db, sku_code="R0-RACE")

        assert final == Decimal("22.00"), (
            "INVARIANT_R0_STOCK_LOST_UPDATE: initial 10 with successful "
            f"+7 and +5 adjustments must end at 22.00, got {final}. The "
            "adjustment path recomputes from a stale identity-map object "
            "instead of the post-lock row (inventory_service.py:388)."
        )
        assert len(movements) == 2, (
            "INVARIANT_R0_STOCK_MOVEMENT_CHAIN: expected exactly 2 "
            f"successful adjustment movements, got {len(movements)}"
        )
        chain = [Decimal(m["q_before"]) for m in movements] + [Decimal(movements[-1]["q_after"])]
        expected_chain = [Decimal("10"), Decimal("17"), Decimal("22")]
        assert chain == expected_chain, (
            "INVARIANT_R0_STOCK_MOVEMENT_CHAIN: movement journal must chain "
            f"10 → 17 → 22 (each adjustment from the latest committed "
            f"value), got {chain}. Current value and journal contradict "
            "each other, so stocktake interpretation is impossible."
        )
    finally:
        await _drop_tenant(schema, wholesaler_id, retailer_id)


# ---------------------------------------------------------------------------
# 3. Lifecycle control: one full return has exactly one economic effect
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_r0_control_single_full_return_single_economic_effect():
    """[CONTROL — expected PASS] Full lifecycle then one full return.

    正常对照: create → confirm → pay 100 cash → fulfill → single return,
    all through the real route functions. Pins the economics the RED race
    test relies on: one refund set (-100 cash), one restock movement, stock
    back to its pre-order level.
    目标缺陷: none (control).
    环境前提: task-exclusive database; retailer price seeded server-side.
    执行入口: POST /orders create/confirm/pay/fulfill/return route functions
    (CanonicalPaymentService under pay_order; OrderService.transition +
    restock_on_return under return_order). HTTP auth/RBAC layer not covered.
    未覆盖范围: business-contract-disputed semantics (confirm-time ledger,
    partial-payment timing, credit-sale refund treatment) are deliberately
    NOT asserted here — see the report's pending-decisions section.
    """
    registry: list = []
    wholesaler_id, retailer_id, schema = await _make_tenant(registry)
    user_id = uuid.uuid4()
    try:
        async with tenant_session(schema, wholesaler_id) as db:
            await seed_sku_with_stock(
                db,
                sku_code="R0-BOX",
                quantity_on_hand=Decimal("10"),
                price=Decimal("100.00"),
                retailer_id=retailer_id,
            )
        order_id = await _create_confirmed_order(
            schema=schema,
            wholesaler_id=wholesaler_id,
            retailer_id=retailer_id,
            user_id=user_id,
        )
        await _pay_full_cash(
            schema=schema,
            wholesaler_id=wholesaler_id,
            retailer_id=retailer_id,
            user_id=user_id,
            order_id=order_id,
        )
        await _fulfill(schema=schema, wholesaler_id=wholesaler_id, user_id=user_id, order_id=order_id)

        async with tenant_session(schema, wholesaler_id) as db:
            assert await stock_on_hand(db, sku_code="R0-BOX") == Decimal("9.00")
            token = R0Token(tenant_id=wholesaler_id, tenant_schema=schema, user_id=user_id)
            await order_routes.return_order(order_id=order_id, token=token, db=db)

        async with tenant_session(schema, wholesaler_id) as db:
            snap = await _refund_snapshot(db, order_id=order_id)
            assert snap["order_status"] == "returned"
            assert snap["refund_cash"] == Decimal("-100.0000"), (
                "CONTROL: one full cash return must refund exactly 100.00"
            )
            assert snap["restock_movement_count"] == 1, (
                "CONTROL: one full return must restock exactly once"
            )
            assert await stock_on_hand(db, sku_code="R0-BOX") == Decimal("10.00")
    finally:
        await _drop_tenant(schema, wholesaler_id, retailer_id)


# ---------------------------------------------------------------------------
# 4. TARGET-DEFECT RED: concurrent identical full returns
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_r0_red_concurrent_full_return_single_economic_effect():
    """[TARGET-DEFECT RED] One full return executed twice concurrently.

    Invariant (REVIEW §2.3 fix goal): at most one economic effect per real
    return — no duplicate refund posting, no duplicate stock restoration —
    regardless of request interleaving.

    正常对照: single-return control test above proves fixture + expectations.
    目标缺陷: the return route pre-reads the order WITHOUT a lock and
    OrderService.transition re-selects with FOR UPDATE but without
    populate_existing, so the loser of the race keeps its stale
    identity-map status ('fulfilled'), passes validation, and posts a second
    refund + restock (external counterexample: cash -200, 2 restocks).
    环境前提: two real sessions; barrier patched into routes.get_order_by_id
    (the route's actual pre-read), pausing request A after its read while B
    commits a complete return; A then resumes on the same stale object.
    执行入口: real return_order route function (OrderService.transition →
    post_order_return ledger + restock_on_return), exactly as the cancel
    HTTP route invokes it. Full HTTP auth layer not covered.
    未覆盖范围: partial returns (no product support yet); refund payout
    outside the ledger; business-contract-disputed credit-sale semantics.

    Expected RED failure names:
      INVARIANT_R0_DOUBLE_RETURN_CASH — refund cash must total -100 once
      INVARIANT_R0_DOUBLE_RETURN_RESTOCK — exactly one positive movement
      INVARIANT_R0_DOUBLE_RETURN_STOCK — on-hand must return to 10.00
    """
    registry: list = []
    wholesaler_id, retailer_id, schema = await _make_tenant(registry)
    user_id = uuid.uuid4()
    try:
        async with tenant_session(schema, wholesaler_id) as db:
            await seed_sku_with_stock(
                db,
                sku_code="R0-BOX",
                quantity_on_hand=Decimal("10"),
                price=Decimal("100.00"),
                retailer_id=retailer_id,
            )
        order_id = await _create_confirmed_order(
            schema=schema,
            wholesaler_id=wholesaler_id,
            retailer_id=retailer_id,
            user_id=user_id,
        )
        await _pay_full_cash(
            schema=schema,
            wholesaler_id=wholesaler_id,
            retailer_id=retailer_id,
            user_id=user_id,
            order_id=order_id,
        )
        await _fulfill(schema=schema, wholesaler_id=wholesaler_id, user_id=user_id, order_id=order_id)

        before_read = asyncio.Event()
        resume = asyncio.Event()
        original_get = order_routes.get_order_by_id
        token = R0Token(tenant_id=wholesaler_id, tenant_schema=schema, user_id=user_id)

        async with tenant_session(schema, wholesaler_id) as db_a:

            async def pausing_get(db, order_id_arg):  # noqa: ANN001
                result = await original_get(db, order_id_arg)
                if db is db_a:
                    before_read.set()
                    await resume.wait()
                return result

            order_routes.get_order_by_id = pausing_get
            try:
                task_a = asyncio.create_task(
                    order_routes.return_order(order_id=order_id, token=token, db=db_a)
                )
                await asyncio.wait_for(before_read.wait(), timeout=30)
                async with tenant_session(schema, wholesaler_id) as db_b:
                    await order_routes.return_order(order_id=order_id, token=token, db=db_b)
                resume.set()
                await asyncio.wait_for(task_a, timeout=30)
            finally:
                order_routes.get_order_by_id = original_get

        async with tenant_session(schema, wholesaler_id) as db:
            snap = await _refund_snapshot(db, order_id=order_id)
            final_stock = await stock_on_hand(db, sku_code="R0-BOX")

        assert snap["order_status"] == "returned"
        assert snap["refund_cash"] == Decimal("-100.0000"), (
            "INVARIANT_R0_DOUBLE_RETURN_CASH: one 100.00 fulfilled order "
            f"returned twice concurrently must refund exactly 100.00 once, "
            f"got refund cash {snap['refund_cash']} "
            f"(accounts: {snap['refund_by_account']})."
        )
        assert snap["restock_movement_count"] == 1, (
            "INVARIANT_R0_DOUBLE_RETURN_RESTOCK: exactly one positive "
            f"restock movement expected, got {snap['restock_movement_count']}."
        )
        assert final_stock == Decimal("10.00"), (
            "INVARIANT_R0_DOUBLE_RETURN_STOCK: stock must return to its "
            f"pre-order 10.00 exactly once, got {final_stock}."
        )
    finally:
        await _drop_tenant(schema, wholesaler_id, retailer_id)
