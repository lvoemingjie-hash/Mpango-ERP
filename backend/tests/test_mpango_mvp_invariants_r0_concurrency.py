"""MPANGO-MVP-INVARIANTS-R0/R1 — concurrency regression tests.

R1 fix round (branch zcode/mpango-mvp-invariants-r1-auth-stock-fix-2026-09-08),
on the accepted R0-R2 known-RED baseline (1485c3f5). Fix state of the two
product counterexample nodes in this file:

- test_r0_red_concurrent_stock_adjustments_no_lost_update: FIXED in R1 —
  InventoryService.adjust_stock's locked re-select now refreshes the
  identity-map object (populate_existing), so the post-lock row state is
  what the adjustment computes from. The node keeps its R0 name (historical
  identifier) and its exact assertions; expected verdict is now PASS.
- test_r0_red_concurrent_full_return_single_economic_effect: NOT fixed and
  STILL EXPECTED RED (named known-unfixed) — the return route's unlocked
  pre-read + OrderService.transition/restock_on_return re-select without
  populate_existing remain, by R1 directive the duplicate-return economics
  is out of scope. It must stay listed as a known RED, never silently
  skipped or re-expected.

R1 addition: test_r1_control_adjustment_read_helper_preserves_duplicate_rows —
the DB-level proof that adjustment_movements returns RAW rows (a synthetic
duplicate-reason journal row survives the read helper and is rejected by the
shared assert_adjustment_chain), closing CTO O1's row-count-preservation
requirement end-to-end.

Never edit an expectation to make a test pass — fix the product instead.

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
    assert_adjustment_chain,
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

    R2 (CTO F1): the transaction decision mirrors the real HTTP middleware
    (api/middleware/auth.py finalize_tenant_context(success=status<400)) —
    a successful request COMMITS inside this helper, a rejected one ROLLS
    BACK before the exception is classified OUTSIDE the transaction. The
    outer tenant_session context therefore never commits partial state from
    a failed request: a legitimate implementation that stages writes and
    then rejects the duplicate with 409 is not misjudged as a double
    economic effect.

    Returns ("success", response) or ("http_rejected", HTTPException).
    Anything else propagates — unknown failures must fail the test, never be
    swallowed into a "pass".
    """
    try:
        response = await order_routes.return_order(order_id=order_id, token=token, db=db)
        await db.commit()
        return ("success", response)
    except HTTPException as exc:
        await db.rollback()
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
            movement_row = movements[0]
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
# 2b. CONTROL (R2, CTO F1): a rejected request must roll back, never commit
# ---------------------------------------------------------------------------

_PROBE_REFERENCE = "r0-harness-probe"
_PROBE_REASON = "r0-staging-write"


async def _probe_movement_count(db, *, schema: str) -> int:
    return int(
        (
            await db.execute(
                text(
                    'SELECT count(*) FROM inventory_movements '
                    'WHERE reference_type = :ref'
                ),
                {"ref": _PROBE_REFERENCE},
            )
        ).scalar_one()
    )


async def _insert_probe_write(db, *, sku_id, order_id) -> None:
    """Stage a harmless probe row INSIDE the request's transaction.

    If the failing request's transaction is committed (the F1 harness bug)
    this row survives and is detected; when the transaction is rolled back
    like the real HTTP middleware would, the row never exists.
    """
    await db.execute(
        text(
            "INSERT INTO inventory_movements "
            "(sku_id, movement_type, quantity, quantity_before, quantity_after, "
            "reason, reference_type, reference_id) "
            "VALUES (:sku, 'r0_probe', 0, 0, 0, :reason, :ref, :oid)"
        ),
        {"sku": sku_id, "reason": _PROBE_REASON, "ref": _PROBE_REFERENCE, "oid": order_id},
    )


@pytest.mark.integration
async def test_r0_control_rejected_return_rolls_back_staging_write():
    """[CONTROL — expected PASS] (R2, CTO F1 regression) 409 means rollback.

    正常对照: harness/transaction behaviour — a request that stages a write
    and is then rejected with the documented 409 must leave NO surviving
    write (the helper rolls back before classifying, mirroring
    finalize_tenant_context(success=False)); the following real request
    commits and yields exactly one economic effect; an UNKNOWN (non-HTTP)
    exception is never swallowed, propagates, rolls back and cleans up.
    目标缺陷: none (control for the R1 harness gap where the outer context
    committed a rejected request's staged writes).
    环境前提: task-owned database; the rejecting route is a fixture wrapper
    (staged write + documented 409) run through the SAME _return_outcome
    helper the real concurrent test uses.
    执行入口: _return_outcome + real return_order route (phase 2), fixture
    wrapper (phases 1/3).
    未覆盖范围: product 409 paths (the baseline currently double-executes
    instead of rejecting; rejection acceptance is proven at assertion level
    in the guards controls and structurally here).
    """
    identity = await TenantIdentity().create()
    user_id = uuid.uuid4()
    try:
        async with tenant_session(identity.schema, identity.wholesaler_id) as db:
            sku_id = await seed_sku_with_stock(
                db,
                sku_code="R0-BOX",
                quantity_on_hand=Decimal("10"),
                price=Decimal("100.00"),
                retailer_id=identity.retailer_id,
            )
        token = R0Token(
            tenant_id=identity.wholesaler_id, tenant_schema=identity.schema, user_id=user_id
        )

        # ---- Phase 1: documented 409 with a staged write -> no survival ----
        order_id = await _create_confirmed_order(identity=identity, user_id=user_id)
        await _pay_full_cash(identity=identity, user_id=user_id, order_id=order_id)
        await _fulfill(identity=identity, user_id=user_id, order_id=order_id)

        original_return = order_routes.return_order

        async def staging_then_reject(order_id, token, db):  # noqa: ANN001
            await _insert_probe_write(db, sku_id=sku_id, order_id=order_id)
            raise HTTPException(
                status_code=409,
                detail={"code": "INVALID_STATE_TRANSITION", "message": "duplicate return"},
            )

        order_routes.return_order = staging_then_reject
        try:
            async with tenant_session(identity.schema, identity.wholesaler_id) as db:
                kind, payload = await _return_outcome(order_id, token, db)
        finally:
            order_routes.return_order = original_return
        assert kind == "http_rejected"
        assert payload.status_code == 409
        assert payload.detail["code"] == "INVALID_STATE_TRANSITION"

        async with tenant_session(identity.schema, identity.wholesaler_id) as db:
            assert await _probe_movement_count(db, schema=identity.schema) == 0, (
                "INVARIANT_R0_REJECTED_REQUEST_WROTE: a request rejected with "
                "the documented 409 must roll back its staged writes (the real "
                "HTTP middleware commits only <400 responses); a surviving "
                "probe row means the harness committed a failed transaction."
            )

        # ---- Phase 2: the other request commits; single economic effect ----
        async with tenant_session(identity.schema, identity.wholesaler_id) as db:
            kind2, payload2 = await _return_outcome(order_id, token, db)
        assert kind2 == "success"
        async with tenant_session(identity.schema, identity.wholesaler_id) as db:
            snap = await _refund_snapshot(db, order_id=order_id)
            final_stock = await stock_on_hand(db, sku_code="R0-BOX")
            probe_count = await _probe_movement_count(db, schema=identity.schema)
        assert snap["order_status"] == "returned"
        _assert_single_economic_effect(
            snap, final_stock=final_stock, context="R2 rejected-then-committed control"
        )
        assert probe_count == 0, (
            "INVARIANT_R0_REJECTED_REQUEST_WROTE: the rejected request's "
            "staged write must still be absent after the succeeding request "
            "commits."
        )

        # ---- Phase 3: UNKNOWN exception propagates, rolls back, cleans ----
        order2 = await _create_confirmed_order(identity=identity, user_id=user_id)
        await _pay_full_cash(identity=identity, user_id=user_id, order_id=order2)
        await _fulfill(identity=identity, user_id=user_id, order_id=order2)

        async def staging_then_boom(order_id, token, db):  # noqa: ANN001
            await _insert_probe_write(db, sku_id=sku_id, order_id=order_id)
            raise RuntimeError("r0 unknown harness failure")

        order_routes.return_order = staging_then_boom
        try:
            # The unknown exception must ESCAPE the transaction context (so
            # the session rolls back exactly like the middleware would) and
            # be caught OUTSIDE it — catching it inside the context would
            # turn the context's normal exit into a commit (the very F1 bug
            # this control exists to prevent).
            with pytest.raises(RuntimeError, match="r0 unknown harness failure"):
                async with tenant_session(identity.schema, identity.wholesaler_id) as db:
                    await _return_outcome(order2, token, db)
        finally:
            order_routes.return_order = original_return

        async with tenant_session(identity.schema, identity.wholesaler_id) as db:
            assert await _probe_movement_count(db, schema=identity.schema) == 0, (
                "INVARIANT_R0_REJECTED_REQUEST_WROTE: an unknown exception must "
                "propagate (never swallowed) and roll its staged writes back."
            )
            status2 = (
                await db.execute(
                    text("SELECT status::text FROM orders WHERE id = :oid"),
                    {"oid": order2},
                )
            ).scalar_one()
        assert status2 == "fulfilled", (
            "CONTROL: the order facing the unknown failure must remain "
            f"fulfilled after rollback, got {status2}."
        )
    finally:
        await identity.drop()


# ---------------------------------------------------------------------------
# 3. TARGET-DEFECT RED: concurrent adjustments must not lose an update
# ---------------------------------------------------------------------------

@pytest.mark.integration
async def test_r0_red_concurrent_stock_adjustments_no_lost_update():
    """[R0 RED → expected PASS after the R1 fix] Inventory 10 + concurrent
    +7 and +5 must be 22.

    Invariant (REVIEW §2.1 fix goal): every adjustment computes from the
    post-lock latest value; two successful adjustments both survive; both
    movement rows and the current value stay mutually consistent.

    正常对照: single-adjustment control + the two harness-safety controls.
    目标缺陷(已修复): inventory_service.adjust_stock re-selected the stock row
    with FOR UPDATE but without populate_existing, so the ORM identity map
    kept the stale pre-lock quantity and the second committer's increment was
    silently overwritten (external counterexample: 10 +7 +5 → 15). R1 fix:
    the locked re-select now carries populate_existing (the module's own
    _locked_stock_by_sku_code pattern).
    环境前提: two real sessions/connections; barrier = asyncio.Event set
    inside a repository read wrapper (timing control only — the wrapper never
    alters SQL results).
    执行入口: InventoryService.adjust_stock (the POST /inventory/adjust
    service), two interleaved transactions, each committing on its own
    connection. HTTP dependency layer not covered (documented probe boundary).
    未覆盖范围: POST /inventory/adjust HTTP/RBAC layer; multi-worker timing.

    Movement verification (R2, CTO F2): the RAW movement rows are checked by
    the shared assert_adjustment_chain helper (support module) — raw row
    count and per-reason multiplicity first (duplicate journal rows are
    rejected, never deduplicated away), then per-row before+delta=after, the
    delta multiset, and order-free chain linkage that accepts BOTH legal
    serial orders (A→B: 10→15, 15→22; B→A: 10→17, 17→22) against the
    observed final stock. Timestamps are never used to infer order.

    Pre-fix RED failure names (kept verbatim as the regression contract):
      INVARIANT_R0_STOCK_LOST_UPDATE — final on-hand must be 22.00
      INVARIANT_R0_STOCK_MOVEMENT_SET — exactly two rows, each reason once
          (duplicates/missing/unknown rejected)
      INVARIANT_R0_STOCK_MOVEMENT_ALGEBRA — rows must chain
          initial→…→final (order-free form).
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
        # R2 (CTO F2): shared invariant helper over the RAW movement rows —
        # no reason-keyed dedup; row count, per-reason multiplicity, per-row
        # algebra and order-free chain linkage (accepts A→B and B→A) are all
        # checked against the observed final stock.
        assert_adjustment_chain(
            movements,
            initial=Decimal("10"),
            final_observed=final,
            expected=[(REASON_A, Decimal("5")), (REASON_B, Decimal("7"))],
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
    """[TARGET-DEFECT RED — STILL EXPECTED RED, known unfixed in R1] One full
    return executed twice concurrently.

    Invariant (REVIEW §2.3 fix goal): at most one economic effect per real
    return — no duplicate refund posting, no duplicate stock restoration —
    regardless of request interleaving.

    R1 directive scope: this node is NOT fixed in this round (duplicate-return
    economics is out of scope) and must keep failing as a named known-RED.
    If it ever passes without a deliberate product fix for the return path,
    that is a harness fault to investigate, not a win.

    正常对照: single-return control test above proves fixture + expectations;
    the outcome classifier accepts BOTH valid fix shapes (serialize the
    second request, or reject it with the documented 409).
    目标缺陷(未修复): the return route pre-reads the order WITHOUT a lock and
    OrderService.transition re-selects with FOR UPDATE but without
    populate_existing, so the loser of the race keeps its stale
    identity-map status ('fulfilled'), passes validation, and posts a second
    refund + restock (external counterexample: cash -200, 2 restocks);
    restock_on_return has the same re-lock shape.
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
      INVARIANT_R0_DOUBLE_RETURN — exactly one economic effect required;
      raised by the shared _assert_single_economic_effect helper (refund
      cash/revenue, restock count and final stock are each named in the
      message).
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


# ---------------------------------------------------------------------------
# 6. R1 CONTROL (CTO O1): the movement read helper preserves duplicate rows
# ---------------------------------------------------------------------------

_R1_PRESERVE_REASON = "r1-preserve-delta-5"


@pytest.mark.integration
async def test_r1_control_adjustment_read_helper_preserves_duplicate_rows():
    """[CONTROL — expected PASS] adjustment_movements never collapses rows.

    正常对照: one real adjustment writes one journal row; the read helper
    returns exactly it. A synthetic second row with the SAME reason is then
    inserted directly (labelled fixture data, not a product write): the read
    helper must return BOTH raw rows (row-count preservation — the invariant
    depends on duplicates surviving the read), and the shared
    assert_adjustment_chain must reject the duplicated journal on the
    movement-set check. This is the DB-level end-to-end closure of CTO O1
    (2026-09-08 review): the guards-file synthetic controls prove the
    assertion logic; this control proves the real read path feeds it raw rows.
    目标缺陷: none (control for the read-helper/journal boundary).
    环境前提: task-owned database; synthetic duplicate row clearly labelled
    by its reason and reference_type, removed with the tenant schema.
    执行入口: InventoryService.adjust_stock (one real adjustment) +
    adjustment_movements + assert_adjustment_chain (the same shared helpers
    the concurrent RED test uses).
    未覆盖范围: no product write path can produce a duplicate-reason pair
    today (that is the duplicate-return shape, still known-RED) — the row is
    fixture-injected precisely because the read side must be provably
    duplicate-preserving regardless of how such rows arise.
    """
    identity = await TenantIdentity().create()
    try:
        async with tenant_session(identity.schema, identity.wholesaler_id) as db:
            sku_id = await seed_sku_with_stock(
                db, sku_code="R1-PRESERVE", quantity_on_hand=Decimal("10")
            )

        async with tenant_session(identity.schema, identity.wholesaler_id) as db:
            await InventoryService().adjust_stock(
                db, sku_code="R1-PRESERVE", quantity=Decimal("5"),
                reason=_R1_PRESERVE_REASON,
            )

        async with tenant_session(identity.schema, identity.wholesaler_id) as db:
            movements = await adjustment_movements(db, sku_code="R1-PRESERVE")
        assert len(movements) == 1, (
            "CONTROL_R1_ROW_PRESERVATION: one real adjustment must read back "
            f"as exactly one movement row, got {len(movements)}."
        )

        # Fixture-injected duplicate-reason journal row (clearly labelled).
        async with tenant_session(identity.schema, identity.wholesaler_id) as db:
            await db.execute(
                text(
                    "INSERT INTO inventory_movements "
                    "(sku_id, movement_type, quantity, quantity_before, quantity_after, "
                    "reason, reference_type) "
                    "VALUES (:sku, 'adjustment', 5, 10, 15, :reason, 'r1-fixture-duplicate')"
                ),
                {"sku": sku_id, "reason": _R1_PRESERVE_REASON},
            )

        async with tenant_session(identity.schema, identity.wholesaler_id) as db:
            duplicated = await adjustment_movements(db, sku_code="R1-PRESERVE")
        assert len(duplicated) == 2, (
            "CONTROL_R1_ROW_PRESERVATION: adjustment_movements must return the "
            f"RAW row count (2 after a duplicate insert), got {len(duplicated)} "
            "— any deduplication in the read helper would hide double economic "
            "effects from the invariant (the CTO O1 blind-spot shape)."
        )
        with pytest.raises(AssertionError, match="INVARIANT_R0_STOCK_MOVEMENT_SET"):
            assert_adjustment_chain(
                duplicated,
                initial=Decimal("10"),
                final_observed=Decimal("15"),
                expected=[(_R1_PRESERVE_REASON, Decimal("5"))],
            )
    finally:
        await identity.drop()
