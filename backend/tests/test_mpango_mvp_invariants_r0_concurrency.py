"""MPANGO-MVP-INVARIANTS-R0-R1 — concurrency regression candidates (known-RED).

R1 revision of the R0 candidate (same product invariants on frozen baseline
bd2373cbfeafde07f1771aba2089f0d1b5f0cd3f). Changes in R1:

- Every run proves the database belongs to this task BEFORE any write
  (session fixture `r0_task_database`: declared container + owner label +
  image/port/db/user match + engine/live-probe agreement + explicit-URL
  migration to the baseline head). Loopback alone is not authorization.
- Concurrent-return test collects BOTH request outcomes. A duplicate return
  may be rejected by the documented contract (409 INVALID_STATE_TRANSITION)
  — acceptance of that explicit rejection is asserted — but the economic
  assertions (refund, restock, final quantity exactly once) ALWAYS run and
  are never skipped because of an expected 409. Unknown exceptions propagate.
- Concurrent-adjustment movements are identified by the unique journal reason
  each adjustment was written with (never by timestamp order). The algebra is
  order-free: per-row before+delta=after, deltas {5,7}, exactly one row
  starting from the initial value and one from the other's committed result,
  total delta and final stock must agree.
- Background work is supervised (timeout -> cancel -> await); transactions
  roll back and sessions close before test data is dropped; partial tenant
  creation is cleaned up; dedicated harness-safety tests cover the
  barrier-timeout and task-exception paths.

THIS FILE IS A REGRESSION CANDIDATE, NOT A GREEN MERGE CANDIDATE:
tests marked [TARGET-DEFECT RED] assert the business invariant that the
external review showed the baseline violates. They are expected to FAIL
(named RED) until the product is fixed. Never edit the expectation to make
them pass — fix the product instead.

External evidence (AI_REPORT_INBOX/external-architecture-2026-09-06):
- counterexamples.json: concurrent_stock_adjustment actual=15 (expected 22)
- supplementary-probes.json: two_return_requests_for_one_100_order
  refund cash=-200, 2 positive inventory movements (expected 1 each)

Execution entry points per test are stated in each docstring, including what
the direct route-function call path does NOT cover (HTTP dependency layer).
"""
from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from api.v1 import orders as order_routes
from crud.order import get_order_by_id
from repositories.inventory_repository import InventoryRepository
from schemas.order import PayOrderRequest, WholesalerOrderCreateRequest
from services.inventory_service import InventoryService

from tests.mpango_invariants_r0_support import (
    R0Token,
    TenantIdentity,
    adjustment_movements,
    cancel_and_wait,
    r0_task_database,  # noqa: F401 - session fixture via usefixtures (ownership proof)
    seed_sku_with_stock,
    stock_on_hand,
    supervise,
    tenant_session,
)

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("r0_task_database")]

REASON_A = "r0-race-A-delta-5"
REASON_B = "r0-race-B-delta-7"
TIMEOUT_S = 30.0


# ---------------------------------------------------------------------------
# Lifecycle helpers (real order entry points)
# ---------------------------------------------------------------------------

async def _create_confirmed_order(
    *,
    identity: TenantIdentity,
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
    schema, wholesaler_id, retailer_id = (
        identity.schema,
        identity.wholesaler_id,
        identity.retailer_id,
    )
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
    *, identity: TenantIdentity, user_id: uuid.UUID, order_id: str,
    total: Decimal = Decimal("100.00"),
) -> None:
    schema = identity.schema
    async with tenant_session(schema, identity.wholesaler_id) as db:
        token = R0Token(
            tenant_id=identity.wholesaler_id, tenant_schema=schema, user_id=user_id
        )
        await order_routes.pay_order(
            order_id=order_id,
            token=token,
            db=db,
            payment_input=PayOrderRequest(amount=total, method="cash"),
            x_idempotency_key=f"r0-pay-{uuid.uuid4().hex[:24]}",
        )


async def _fulfill(
    *, identity: TenantIdentity, user_id: uuid.UUID, order_id: str,
) -> None:
    async with tenant_session(identity.schema, identity.wholesaler_id) as db:
        token = R0Token(
            tenant_id=identity.wholesaler_id, tenant_schema=identity.schema, user_id=user_id
        )
        await order_routes.fulfill_order(order_id=order_id, token=token, db=db)


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
        "refund_revenue": Decimal(refund.get("revenue", "0")),
        "restock_movement_count": int(restock_count),
        "order_status": status,
    }


def _assert_single_economic_effect(snap: dict, *, final_stock: Decimal, context: str) -> None:
    """The R0 economics invariant, shared by control and race tests.

    Exactly one full-return effect: refund cash −100 / revenue +100 once,
    one positive restock movement, stock back to its pre-order value.
    """
    assert snap["refund_cash"] == Decimal("-100.0000"), (
        f"{context}: one 100.00 full return must refund exactly 100.00 once, "
        f"got refund cash {snap['refund_cash']} (accounts: {snap['refund_by_account']})."
    )
    assert snap["refund_revenue"] == Decimal("100.0000"), (
        f"{context}: one full return must reverse revenue exactly once, "
        f"got {snap['refund_revenue']}."
    )
    assert snap["restock_movement_count"] == 1, (
        f"{context}: exactly one positive restock movement expected, "
        f"got {snap['restock_movement_count']}."
    )
    assert final_stock == Decimal("10.00"), (
        f"{context}: stock must return to its pre-order 10.00 exactly once, "
        f"got {final_stock}."
    )


async def _return_outcome(order_id: str, token, db):
    """Run one real return request and classify its outcome.

    Returns ("success", response) or ("http_rejected", HTTPException).
    Anything else propagates — unknown failures must fail the test, never be
    swallowed into a "pass".
    """
    try:
        return ("success", await order_routes.return_order(order_id=order_id, token=token, db=db))
    except HTTPException as exc:
        return ("http_rejected", exc)


def _assert_outcomes_contractual(outcomes: list) -> None:
    """Both request outcomes must fit the existing contract.

    At least one request must succeed (the return must be processable), and
    every rejection must be the documented duplicate-return rejection
    (409 INVALID_STATE_TRANSITION) — not an arbitrary error.
    """
    kinds = [kind for kind, _ in outcomes]
    assert "success" in kinds, (
        "OUTCOME_CONTRACT: at least one full-return request must succeed; "
        f"got {kinds}."
    )
    for kind, payload in outcomes:
        if kind == "http_rejected":
            detail = payload.detail if isinstance(payload.detail, dict) else {}
            assert payload.status_code == 409 and detail.get("code") == "INVALID_STATE_TRANSITION", (
                "OUTCOME_CONTRACT: a rejected duplicate return must be the "
                f"documented 409 INVALID_STATE_TRANSITION, got {payload.status_code} "
                f"{detail!r}."
            )


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
    环境前提: task-owned database proven by the r0_task_database fixture.
    执行入口: InventoryService.adjust_stock — the exact function
    POST /api/v1/inventory/adjust calls (route adds permission + logging only).
    未覆盖范围: HTTP layer of /inventory/adjust and RBAC.
    """
    identity = await TenantIdentity().create()
    try:
        async with tenant_session(identity.schema, identity.wholesaler_id) as db:
            await seed_sku_with_stock(db, sku_code="R0-CTL", quantity_on_hand=Decimal("10"))

        async with tenant_session(identity.schema, identity.wholesaler_id) as db:
            stock, movement = await InventoryService().adjust_stock(
                db, sku_code="R0-CTL", quantity=Decimal("7"), reason="r0 control +7"
            )
            assert Decimal(str(movement.quantity_before)) == Decimal("10")
            assert Decimal(str(movement.quantity_after)) == Decimal("17")
        async with tenant_session(identity.schema, identity.wholesaler_id) as db:
            assert await stock_on_hand(db, sku_code="R0-CTL") == Decimal("17.00")
            movements = await adjustment_movements(db, sku_code="R0-CTL")
            assert len(movements) == 1
            (movement_row,) = movements.values()
            assert Decimal(movement_row["qty"]) == Decimal("7")

        # Failing adjustment: full rollback of value and journal entry.
        async with tenant_session(identity.schema, identity.wholesaler_id) as db:
            with pytest.raises(HTTPException) as excinfo:
                await InventoryService().adjust_stock(
                    db, sku_code="R0-CTL", quantity=Decimal("-50"), reason="r0 control -50"
                )
            assert excinfo.value.status_code == 409
            assert excinfo.value.detail["code"] == "NEGATIVE_STOCK"
        async with tenant_session(identity.schema, identity.wholesaler_id) as db:
            assert await stock_on_hand(db, sku_code="R0-CTL") == Decimal("17.00")
            assert len(await adjustment_movements(db, sku_code="R0-CTL")) == 1
    finally:
        await identity.drop()


# ---------------------------------------------------------------------------
# 2. Harness-safety controls: timeout and task-exception cleanup paths
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_r0_harness_control_barrier_timeout_cancels_and_rolls_back():
    """[CONTROL — expected PASS] A wedged barrier must fail fast and clean up.

    正常对照: harness behaviour, not product behaviour — a stuck barrier must
    produce GUARD_HARNESS_TIMEOUT (never a silent hang), the parked task must
    be cancelled and awaited, its uncommitted transaction rolled back (no
    movement, value unchanged), and teardown must still succeed.
    目标缺陷: none.
    环境前提: task-owned database; two real connections.
    执行入口: InventoryService.adjust_stock behind a repository read barrier
    that is deliberately never released.
    未覆盖范围: product code paths beyond adjust_stock's first read.
    """
    identity = await TenantIdentity().create()
    try:
        async with tenant_session(identity.schema, identity.wholesaler_id) as db:
            await seed_sku_with_stock(db, sku_code="R0-WEDGE", quantity_on_hand=Decimal("10"))

        never = asyncio.Event()

        class WedgedRepository(InventoryRepository):
            async def get_stock_by_sku_code(self, db, *, sku_code):  # noqa: ANN001
                row = await super().get_stock_by_sku_code(db, sku_code=sku_code)
                await never.wait()  # never set within the test
                return row

        async def wedged_adjustment():
            async with tenant_session(identity.schema, identity.wholesaler_id) as db_w:
                await InventoryService(WedgedRepository()).adjust_stock(
                    db_w, sku_code="R0-WEDGE", quantity=Decimal("5"), reason="r0 wedged"
                )

        with pytest.raises(AssertionError, match="GUARD_HARNESS_TIMEOUT"):
            await supervise(
                wedged_adjustment(), timeout=3.0, label="wedged adjustment"
            )

        # The parked transaction must have been rolled back, not committed.
        async with tenant_session(identity.schema, identity.wholesaler_id) as db:
            assert await stock_on_hand(db, sku_code="R0-WEDGE") == Decimal("10.00")
            assert len(await adjustment_movements(db, sku_code="R0-WEDGE")) == 0

        # No lingering locks: a normal adjustment still works afterwards.
        async with tenant_session(identity.schema, identity.wholesaler_id) as db:
            await InventoryService().adjust_stock(
                db, sku_code="R0-WEDGE", quantity=Decimal("1"), reason="r0 after-wedge"
            )
        async with tenant_session(identity.schema, identity.wholesaler_id) as db:
            assert await stock_on_hand(db, sku_code="R0-WEDGE") == Decimal("11.00")
    finally:
        await identity.drop()


@pytest.mark.integration
async def test_r0_harness_control_task_exception_rolls_back_and_cleans():
    """[CONTROL — expected PASS] A raising background task cleans up.

    正常对照: after the barrier releases, the adjustment itself fails
    (negative result → 409). The supervised task propagates the typed error,
    its session rolls back (value and journal untouched), and teardown drops
    the tenant cleanly.
    目标缺陷: none.
    环境前提: task-owned database; two real connections.
    执行入口: InventoryService.adjust_stock behind a released read barrier.
    未覆盖范围: non-HTTP exception classes inside product code.
    """
    identity = await TenantIdentity().create()
    try:
        async with tenant_session(identity.schema, identity.wholesaler_id) as db:
            await seed_sku_with_stock(db, sku_code="R0-RAISE", quantity_on_hand=Decimal("10"))

        first_read = asyncio.Event()
        resume = asyncio.Event()

        class PausingRepository(InventoryRepository):
            async def get_stock_by_sku_code(self, db, *, sku_code):  # noqa: ANN001
                row = await super().get_stock_by_sku_code(db, sku_code=sku_code)
                first_read.set()
                await resume.wait()
                return row

        async def failing_adjustment():
            async with tenant_session(identity.schema, identity.wholesaler_id) as db_f:
                await InventoryService(PausingRepository()).adjust_stock(
                    db_f, sku_code="R0-RAISE", quantity=Decimal("-50"), reason="r0 raises"
                )

        task = asyncio.ensure_future(failing_adjustment())
        try:
            await asyncio.wait_for(first_read.wait(), timeout=TIMEOUT_S)
            resume.set()
            with pytest.raises(HTTPException) as excinfo:
                await asyncio.wait_for(task, timeout=TIMEOUT_S)
            assert excinfo.value.status_code == 409
            assert excinfo.value.detail["code"] == "NEGATIVE_STOCK"
        except BaseException:
            await cancel_and_wait(task)
            raise

        async with tenant_session(identity.schema, identity.wholesaler_id) as db:
            assert await stock_on_hand(db, sku_code="R0-RAISE") == Decimal("10.00")
            assert len(await adjustment_movements(db, sku_code="R0-RAISE")) == 0
    finally:
        await identity.drop()


# ---------------------------------------------------------------------------
# 3. TARGET-DEFECT RED: concurrent adjustments must not lose an update
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_r0_red_concurrent_stock_adjustments_no_lost_update():
    """[TARGET-DEFECT RED] Inventory 10 + concurrent +7 and +5 must be 22.

    Invariant (REVIEW §2.1 fix goal): every adjustment computes from the
    post-lock latest value; two successful adjustments both survive; both
    movement rows and the current value stay mutually consistent.

    正常对照: single-adjustment control + the two harness-safety controls.
    目标缺陷: inventory_service.adjust_stock re-selects the stock row with
    FOR UPDATE but without populate_existing, so the ORM identity map keeps
    the stale pre-lock quantity and the second committer's increment is
    silently overwritten (external counterexample: 10 +7 +5 → 15).
    环境前提: two real sessions/connections; barrier = asyncio.Event set
    inside a repository read wrapper (timing control only — the wrapper never
    alters SQL results).
    执行入口: InventoryService.adjust_stock (the POST /inventory/adjust
    service), two interleaved transactions, each committing on its own
    connection. HTTP dependency layer not covered (documented probe boundary).
    未覆盖范围: POST /inventory/adjust HTTP/RBAC layer; multi-worker timing.

    Movement verification is order-free (R1): each movement is identified by
    the unique reason it was written with; per-row before+delta=after must
    hold, the delta multiset must be {5,7}, exactly one movement may start
    from the initial value and one from the other adjustment's committed
    result, and initial + total delta must equal the final stock. Timestamps
    are never used to infer execution order.

    Expected RED failure names:
      INVARIANT_R0_STOCK_LOST_UPDATE — final on-hand must be 22.00
      INVARIANT_R0_STOCK_MOVEMENT_ALGEBRA — movements must be mutually
          consistent with the final value (order-free form).
    """
    identity = await TenantIdentity().create()
    try:
        async with tenant_session(identity.schema, identity.wholesaler_id) as db:
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
            async with tenant_session(identity.schema, identity.wholesaler_id) as db_a:
                await InventoryService(PausingRepository()).adjust_stock(
                    db_a, sku_code="R0-RACE", quantity=Decimal("5"), reason=REASON_A
                )

        task_a = asyncio.ensure_future(adjustment_a())
        try:
            await asyncio.wait_for(first_read.wait(), timeout=TIMEOUT_S)
            # B runs to completion on its own connection while A is parked.
            async def adjustment_b():
                async with tenant_session(identity.schema, identity.wholesaler_id) as db_b:
                    await InventoryService().adjust_stock(
                        db_b, sku_code="R0-RACE", quantity=Decimal("7"), reason=REASON_B
                    )

            await supervise(adjustment_b(), label="adjustment B", timeout=TIMEOUT_S)
            resume.set()
            await supervise(asyncio.shield(task_a), label="adjustment A resume", timeout=TIMEOUT_S)
        except BaseException:
            resume.set()  # unblock A so its session can close before teardown
            await cancel_and_wait(task_a)
            raise

        async with tenant_session(identity.schema, identity.wholesaler_id) as db:
            final = await stock_on_hand(db, sku_code="R0-RACE")
            movements = await adjustment_movements(db, sku_code="R0-RACE")

        assert final == Decimal("22.00"), (
            "INVARIANT_R0_STOCK_LOST_UPDATE: initial 10 with successful "
            f"+7 and +5 adjustments must end at 22.00, got {final}. The "
            "adjustment path recomputes from a stale identity-map object "
            "instead of the post-lock row (inventory_service.py:388)."
        )
        assert set(movements) == {REASON_A, REASON_B}, (
            f"INVARIANT_R0_STOCK_MOVEMENT_ALGEBRA: expected exactly two "
            f"identifiable adjustments {REASON_A!r} and {REASON_B!r}, got "
            f"{sorted(movements)!r}"
        )
        row_a = movements[REASON_A]
        row_b = movements[REASON_B]
        rows = {"A(+5)": row_a, "B(+7)": row_b}
        for label, row in rows.items():
            qty, before, after = (
                Decimal(row["qty"]),
                Decimal(row["q_before"]),
                Decimal(row["q_after"]),
            )
            assert qty == (Decimal("5") if label.startswith("A") else Decimal("7")), (
                f"INVARIANT_R0_STOCK_MOVEMENT_ALGEBRA: {label} journaled {qty}"
            )
            assert before + qty == after, (
                f"INVARIANT_R0_STOCK_MOVEMENT_ALGEBRA: {label} row violates "
                f"before+delta=after ({before} + {qty} != {after})"
            )
        deltas = sorted(
            Decimal(row["qty"]) for row in rows.values()
        )
        assert deltas == [Decimal("5"), Decimal("7")], (
            f"INVARIANT_R0_STOCK_MOVEMENT_ALGEBRA: delta multiset must be "
            f"[5, 7], got {deltas}"
        )
        # Order-free chain: exactly one movement starts from the initial 10
        # and one starts from the other adjustment's committed result 17;
        # endings must be the complementary values.
        starts = sorted(Decimal(row["q_before"]) for row in rows.values())
        ends = sorted(Decimal(row["q_after"]) for row in rows.values())
        assert starts == [Decimal("10"), Decimal("17")], (
            "INVARIANT_R0_STOCK_MOVEMENT_ALGEBRA: one adjustment must compute "
            f"from the initial 10 and one from the other's committed 17, got "
            f"starts {starts}."
        )
        assert ends == [Decimal("17"), Decimal("22")], (
            "INVARIANT_R0_STOCK_MOVEMENT_ALGEBRA: adjustment endings must be "
            f"17 and 22, got {ends}."
        )
        assert Decimal("10") + sum(deltas) == final, (
            "INVARIANT_R0_STOCK_MOVEMENT_ALGEBRA: initial + total journal "
            f"delta must equal the final stock (10 + {sum(deltas)} != {final})."
        )
    finally:
        await identity.drop()


# ---------------------------------------------------------------------------
# 4. Lifecycle control: one full return has exactly one economic effect
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_r0_control_single_full_return_single_economic_effect():
    """[CONTROL — expected PASS] Full lifecycle then one full return.

    正常对照: create → confirm → pay 100 cash → fulfill → single return,
    all through the real route functions. Pins the economics the RED race
    test relies on: one refund set (−100 cash / +100 revenue), one restock
    movement, stock back to its pre-order level.
    目标缺陷: none (control).
    环境前提: task-owned database; retailer price seeded server-side.
    执行入口: POST /orders create/confirm/pay/fulfill/return route functions
    (CanonicalPaymentService under pay_order; OrderService.transition +
    restock_on_return under return_order). HTTP auth/RBAC layer not covered.
    未覆盖范围: business-contract-disputed semantics (confirm-time ledger,
    partial-payment timing, credit-sale refund treatment) are deliberately
    NOT asserted here — see the report's pending-decisions section. No
    assertion is made about ledger state after confirm (source observation
    only).
    """
    identity = await TenantIdentity().create()
    user_id = uuid.uuid4()
    try:
        async with tenant_session(identity.schema, identity.wholesaler_id) as db:
            await seed_sku_with_stock(
                db,
                sku_code="R0-BOX",
                quantity_on_hand=Decimal("10"),
                price=Decimal("100.00"),
                retailer_id=identity.retailer_id,
            )
        order_id = await _create_confirmed_order(identity=identity, user_id=user_id)
        await _pay_full_cash(identity=identity, user_id=user_id, order_id=order_id)
        await _fulfill(identity=identity, user_id=user_id, order_id=order_id)

        async with tenant_session(identity.schema, identity.wholesaler_id) as db:
            assert await stock_on_hand(db, sku_code="R0-BOX") == Decimal("9.00")
            token = R0Token(
                tenant_id=identity.wholesaler_id, tenant_schema=identity.schema, user_id=user_id
            )
            await order_routes.return_order(order_id=order_id, token=token, db=db)

        async with tenant_session(identity.schema, identity.wholesaler_id) as db:
            snap = await _refund_snapshot(db, order_id=order_id)
            final_stock = await stock_on_hand(db, sku_code="R0-BOX")
            assert snap["order_status"] == "returned"
        _assert_single_economic_effect(
            snap, final_stock=final_stock, context="CONTROL single return"
        )
    finally:
        await identity.drop()


# ---------------------------------------------------------------------------
# 5. TARGET-DEFECT RED: concurrent identical full returns
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_r0_red_concurrent_full_return_single_economic_effect():
    """[TARGET-DEFECT RED] One full return executed twice concurrently.

    Invariant (REVIEW §2.3 fix goal): at most one economic effect per real
    return — no duplicate refund posting, no duplicate stock restoration —
    regardless of request interleaving.

    正常对照: single-return control test above proves fixture + expectations;
    the outcome classifier accepts BOTH valid fix shapes (serialize the
    second request, or reject it with the documented 409).
    目标缺陷: the return route pre-reads the order WITHOUT a lock and
    OrderService.transition re-selects with FOR UPDATE but without
    populate_existing, so the loser of the race keeps its stale
    identity-map status ('fulfilled'), passes validation, and posts a second
    refund + restock (external counterexample: cash -200, 2 restocks).
    环境前提: two real sessions; barrier patched into routes.get_order_by_id
    (the route's actual pre-read), pausing request A after its read while B
    completes; A then resumes on the same stale object. Both outcomes are
    collected and classified.
    执行入口: real return_order route function (OrderService.transition →
    post_order_return ledger + restock_on_return), exactly as the cancel
    HTTP route invokes it. Full HTTP auth layer not covered.
    未覆盖范围: partial returns (no product support yet); refund payout
    outside the ledger; business-contract-disputed credit-sale semantics.
    This test does NOT decide future partial-return or refund policy.

    Expected RED failure names (baseline double-executes, so the economic
    assertions fire):
      INVARIANT_R0_DOUBLE_RETURN_CASH — refund cash must total −100 once
      INVARIANT_R0_DOUBLE_RETURN_RESTOCK — exactly one positive movement
      INVARIANT_R0_DOUBLE_RETURN_STOCK — on-hand must return to 10.00
    """
    identity = await TenantIdentity().create()
    user_id = uuid.uuid4()
    try:
        async with tenant_session(identity.schema, identity.wholesaler_id) as db:
            await seed_sku_with_stock(
                db,
                sku_code="R0-BOX",
                quantity_on_hand=Decimal("10"),
                price=Decimal("100.00"),
                retailer_id=identity.retailer_id,
            )
        order_id = await _create_confirmed_order(identity=identity, user_id=user_id)
        await _pay_full_cash(identity=identity, user_id=user_id, order_id=order_id)
        await _fulfill(identity=identity, user_id=user_id, order_id=order_id)

        before_read = asyncio.Event()
        resume = asyncio.Event()
        original_get = order_routes.get_order_by_id
        token = R0Token(
            tenant_id=identity.wholesaler_id, tenant_schema=identity.schema, user_id=user_id
        )

        async with tenant_session(identity.schema, identity.wholesaler_id) as db_a:

            async def pausing_get(db, order_id_arg):  # noqa: ANN001
                result = await original_get(db, order_id_arg)
                if db is db_a:
                    before_read.set()
                    await resume.wait()
                return result

            order_routes.get_order_by_id = pausing_get
            task_a = asyncio.ensure_future(
                _return_outcome(order_id, token, db_a)
            )
            try:
                await asyncio.wait_for(before_read.wait(), timeout=TIMEOUT_S)

                async def request_b():
                    async with tenant_session(
                        identity.schema, identity.wholesaler_id
                    ) as db_b:
                        return await _return_outcome(order_id, token, db_b)

                outcome_b = await supervise(
                    request_b(), label="return request B", timeout=TIMEOUT_S
                )
                resume.set()
                outcome_a = await supervise(
                    asyncio.shield(task_a), label="return request A resume", timeout=TIMEOUT_S
                )
            except BaseException:
                resume.set()  # unblock A so its session can close before teardown
                await cancel_and_wait(task_a)
                raise
            finally:
                order_routes.get_order_by_id = original_get

        outcomes = [outcome_a, outcome_b]
        _assert_outcomes_contractual(outcomes)

        # Economic assertions ALWAYS run — an expected 409 must not skip them.
        async with tenant_session(identity.schema, identity.wholesaler_id) as db:
            snap = await _refund_snapshot(db, order_id=order_id)
            final_stock = await stock_on_hand(db, sku_code="R0-BOX")

        assert snap["order_status"] == "returned"
        _assert_single_economic_effect(
            snap,
            final_stock=final_stock,
            context=(
                "INVARIANT_R0_DOUBLE_RETURN: one 100.00 fulfilled order "
                "returned twice concurrently must produce exactly one economic "
                "effect (a documented 409 rejection of the duplicate is "
                "acceptable; a second economic effect is not)"
            ),
        )
    finally:
        await identity.drop()
