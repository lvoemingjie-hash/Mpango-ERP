"""MPANGO-ORDER-STATE-AUTHORITY-D1 matrix group 5 — identity snapshots and
packaging protection (R1 de-confounded).

Identity contract under test: ``order_items.sellable_unit_id -> skus.id`` is
THE identity field. State operations must never reprice an order item,
overwrite its snapshots, or rewrite a legacy item's identity. The first SKU
reference (order creation) freezes package identity (BC-06 history lock).

R1 corrections (Codex-L review): every packaging-guard rejection below is
attributed to the ORDER REFERENCE alone — each scenario independently
verifies its history preconditions (order_reference / movement /
nonzero_stock / any_reservation) via ``identity_history_causes``, and the
positive controls exercise the all-zero placeholder exemption explicitly.
The first-reference vs packaging-change boundary runs REAL HTTP order
creation against the REAL SKU guard concurrently (barriered wrappers around
``crud_create_order``; the guard path is the real
``lock_sku_row`` + ``ensure_package_quantity_change_allowed`` chain).
Source fact recorded in R1-ADDENDUM: both HTTP create paths read the SKU
row (joined with stocks/prices) WITHOUT FOR UPDATE; the first-reference
INSERT is not serialized against the shared skus lock — proven below.
"""
from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

import pytest
from fastapi import HTTPException
from http import HTTPStatus
from sqlalchemy import text

from tests.order_state_d1.support import (
    RaceOrchestrator,
    bound_retailer,
    http_action,
    http_create_wholesaler_order,
    identity_history_causes,
    osd1_cashier_token,
    seed_bare_sku,
    seed_sku_with_stock,
    snapshot_order_items,
    strip_price_and_zero_stock,
)

pytestmark = pytest.mark.asyncio

_BUDGET = 30.0


def _errcode(resp) -> str:
    body = resp.json()
    detail = body.get("detail") or body.get("error") or {}
    return (detail.get("code") or body.get("code") or "")


async def _guard_session(schema: str, tenant_id: str):
    from database.session import AsyncSessionLocal

    session = AsyncSessionLocal()
    session.info["tenant_schema"] = schema
    session.info["tenant_id"] = tenant_id
    # NO commit here: the open implicit transaction pins the pooled
    # connection (a commit would return it to the pool where the asyncpg
    # reset runs RESET ALL and silently drops the search_path)
    await session.execute(text(f'SET search_path TO "{schema}", public'))
    got = (await session.execute(text("SHOW search_path"))).scalar()
    assert schema in str(got), (
        f"guard session search_path not applied: got {got!r} want {schema!r}")
    return session


async def _guard_verdict_fresh(schema: str, ws_id: str, sku_id: str, new_quantity: Decimal):
    """Run the real guard chain in a FRESH session per call.

    Rationale (proven by probe): a rollback/commit returns the pooled
    connection and the asyncpg reset issues RESET ALL, silently dropping the
    pinned search_path; reusing the session across verdicts then fails with
    ``relation "skus" does not exist``. One session per verdict avoids it.
    """
    session = await _guard_session(schema, ws_id)
    try:
        return await _guard_verdict(session, sku_id, new_quantity)
    finally:
        await session.close()


async def _guard_verdict(session, sku_id: str, new_quantity: Decimal):
    """Run the REAL guard chain: shared row lock then the shared gate."""
    from services.package_identity import (
        ensure_package_quantity_change_allowed,
        lock_sku_row,
    )

    guard_result_ = None
    locked = await lock_sku_row(session, sku_id=uuid.UUID(sku_id))
    try:
        sp = (await session.execute(text("SHOW search_path"))).scalar()
        cnt = (await session.execute(text(
            'SELECT count(*) FROM skus WHERE id = :i'), {"i": uuid.UUID(sku_id)}
        )).scalar()
        print(f"GUARD_PROBE search_path={sp!r} skus_count={cnt}")
    except Exception as probe_exc:
        print(f"GUARD_PROBE_FAILED {type(probe_exc).__name__}: {probe_exc}")
    assert locked is not None, "guard precondition: SKU must exist and be live"
    try:
        await ensure_package_quantity_change_allowed(
            session, sku=locked, new_package_quantity=new_quantity
        )
        return None
    except HTTPException as exc:
        return exc.detail["code"] if isinstance(exc.detail, dict) else str(exc.detail)


async def test_state_operations_never_touch_item_snapshots(
    osd1_client, s2_clean_db, provisioned_pool, osd1_cashier
):
    db, reg = s2_clean_db
    token = await osd1_cashier_token(osd1_client, osd1_cashier)
    async with bound_retailer(db, provisioned_pool, reg) as (ret_id, schema, _ws):
        sku, sid = await seed_sku_with_stock(db, schema, ret_id, quantity=50, price="12.50")
        order = await http_create_wholesaler_order(osd1_client, token, ret_id, sku, 3)
        oid = order["id"]

        before = await snapshot_order_items(db, schema, oid)
        assert len(before) == 1
        assert before[0]["identity_status"] == "stable"
        assert before[0]["sellable_unit_id"] == sid
        assert before[0]["unit_snapshot"] == "piece"
        assert Decimal(before[0]["unit_price"]) == Decimal("12.50")

        assert (await http_action(osd1_client, token, oid, "confirm")).status_code == 200
        pay = await http_action(osd1_client, token, oid, "pay",
                                {"amount": 37.50, "method": "cash"})
        assert pay.status_code == 200, pay.text

        # Even a retailer-price change must not reprice the confirmed item.
        await db.execute(text(
            f'UPDATE "{schema}".retailer_prices SET price = 99.00 '
            "WHERE sku_id = :s AND retailer_id = :r"),
            {"s": sid, "r": ret_id})
        await db.commit()

        cancel = await http_action(osd1_client, token, oid, "cancel")
        # paid cancel is (correctly) unreachable over HTTP; the snapshot
        # invariant is checked regardless of the transition outcome
        assert cancel.status_code in (HTTPStatus.CONFLICT,), cancel.text

        after = await snapshot_order_items(db, schema, oid)
        assert after == before, (
            "state operations mutated item identity/pricing snapshots: "
            f"{before} -> {after}")


# ---------------------------------------------------------------------------
# De-confounded packaging-freeze proofs (order reference is the ONLY cause)
# ---------------------------------------------------------------------------


async def test_first_order_reference_alone_freezes_package_identity(
    osd1_client, s2_clean_db, provisioned_pool, osd1_cashier
):
    """REAL HTTP creation is the first SKU reference; after isolating every
    other history cause (zero stock aggregate, retired price, no movements,
    no reservations), the guard must still reject with IMMUTABLE_AFTER_USE."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(osd1_client, osd1_cashier)
    async with bound_retailer(db, provisioned_pool, reg) as (ret_id, schema, ws_id):
        sku, sid = await seed_sku_with_stock(db, schema, ret_id, quantity=10, price="5.00")
        order = await http_create_wholesaler_order(osd1_client, token, ret_id, sku, 1)
        assert order["id"]

        # isolate: only the order reference may remain as a history cause
        await strip_price_and_zero_stock(db, schema, sid)
        causes = await identity_history_causes(db, schema, sid, sku)
        assert causes == {"order_reference": True, "movement": False,
                          "nonzero_stock": False, "any_reservation": False}, causes

        session = await _guard_session(schema, ws_id)
        try:
            verdict = await _guard_verdict(session, sid, Decimal("12"))
            await session.rollback()
        finally:
            await session.close()
        assert verdict == "SKU_PACKAGE_QUANTITY_IMMUTABLE_AFTER_USE", verdict


async def test_all_zero_placeholder_stock_is_not_history_positive_control(
    osd1_client, s2_clean_db, provisioned_pool, osd1_cashier
):
    """Positive control proving the all-zero placeholder exemption: a bare
    SKU whose ONLY stock row is an all-zero placeholder (on_hand=0,
    reserved=0) accepts repackaging."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(osd1_client, osd1_cashier)
    async with bound_retailer(db, provisioned_pool, reg) as (ret_id, schema, ws_id):
        sku, sid = await seed_bare_sku(db, schema)
        await db.execute(text(
            f'INSERT INTO "{schema}".inventory_stocks (sku_id, quantity_on_hand, '
            "quantity_reserved, is_deleted) VALUES (:s, 0, 0, false)"), {"s": sid})
        await db.commit()

        causes = await identity_history_causes(db, schema, sid, sku)
        assert causes == {"order_reference": False, "movement": False,
                          "nonzero_stock": False, "any_reservation": False}, causes

        session = await _guard_session(schema, ws_id)
        try:
            verdict = await _guard_verdict(session, sid, Decimal("12"))
            await session.rollback()
        finally:
            await session.close()
        assert verdict is None, (
            f"all-zero placeholder blocked repackaging (exemption broken): {verdict}")


async def test_cancelled_order_history_alone_blocks_repackaging(
    osd1_client, s2_clean_db, provisioned_pool, osd1_cashier
):
    """A CANCELLED order's reference still freezes identity: cancellation is
    not the release of the right to modify package identity. Compared against
    an otherwise-identical bare SKU with no order (must accept)."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(osd1_client, osd1_cashier)
    async with bound_retailer(db, provisioned_pool, reg) as (ret_id, schema, ws_id):
        ws_uuid = str(uuid.UUID(ws_id))
        ret_uuid = str(uuid.UUID(ret_id))
        # control SKU: identical bare seed, no order reference
        control_code, control_sid = await seed_bare_sku(db, schema)
        # referenced SKU: bare seed referenced ONLY by a CANCELLED order
        ref_code, ref_sid = await seed_bare_sku(db, schema)
        order_id = uuid.uuid4()
        await db.execute(text(
            f'INSERT INTO "{schema}".orders (id, wholesaler_id, retailer_id, status, '
            "total_amount, is_deleted) "
            "VALUES (:o, :w, :r, 'cancelled', 10, false)"),
            {"o": order_id, "w": ws_uuid, "r": ret_uuid})
        await db.execute(text(
            f'INSERT INTO "{schema}".order_items (order_id, sellable_unit_id, '
            "identity_status, product_name, sku_code, unit_snapshot, quantity, "
            "unit_price, subtotal) "
            "VALUES (:o, :s, 'stable', 'OSD1Bare', :c, 'piece', 1, 10, 10)"),
            {"o": order_id, "s": uuid.UUID(ref_sid), "c": ref_code})
        await db.commit()

        ref_causes = await identity_history_causes(db, schema, ref_sid, ref_code)
        assert ref_causes["order_reference"] is True, ref_causes
        for key in ("movement", "nonzero_stock", "any_reservation"):
            assert ref_causes[key] is False, ref_causes
        control_causes = await identity_history_causes(db, schema, control_sid, control_code)
        assert control_causes["order_reference"] is False, control_causes

        ref_verdict = await _guard_verdict_fresh(schema, ws_id, ref_sid, Decimal("9"))
        control_verdict = await _guard_verdict_fresh(schema, ws_id, control_sid, Decimal("9"))

        assert ref_verdict == "SKU_PACKAGE_QUANTITY_IMMUTABLE_AFTER_USE", ref_verdict
        assert control_verdict is None, control_verdict


async def test_legacy_item_cancel_keeps_identity_snapshot(
    osd1_client, s2_clean_db, provisioned_pool, osd1_cashier
):
    """A legacy-shaped item (sellable_unit_id NULL) survives a legitimate
    HTTP cancel with its identity shape and snapshots byte-identical —
    cancellation must not silently backfill or clear identity."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(osd1_client, osd1_cashier)
    async with bound_retailer(db, provisioned_pool, reg) as (ret_id, schema, ws_id):
        sku, sid = await seed_sku_with_stock(db, schema, ret_id)
        order = await http_create_wholesaler_order(osd1_client, token, ret_id, sku, 1)
        oid = order["id"]

        session = await _guard_session(schema, ws_id)
        try:
            await session.execute(text(
                f'UPDATE "{schema}".order_items SET sellable_unit_id = NULL, '
                "identity_status = 'legacy', unit_snapshot = NULL "
                "WHERE order_id = :oid"), {"oid": oid})
            await session.commit()
        finally:
            await session.close()
        await db.rollback()

        before = await snapshot_order_items(db, schema, oid)
        cancel = await http_action(osd1_client, token, oid, "cancel")
        assert cancel.status_code == HTTPStatus.OK, cancel.text

        after = await snapshot_order_items(db, schema, oid)
        assert before[0]["identity_status"] == "legacy"
        assert before[0]["sellable_unit_id"] is None
        assert after == before, (
            "cancel rewrote legacy identity shape: "
            f"{before} -> {after}")


async def test_legacy_item_failed_confirm_keeps_identity_snapshot(
    osd1_client, s2_clean_db, provisioned_pool, osd1_cashier
):
    """A legacy-shaped item fails confirm closed
    (ORDER_ITEM_SELLABLE_ID_REQUIRED) and — the whole request rolling back —
    its legacy identity is NOT rewritten."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(osd1_client, osd1_cashier)
    async with bound_retailer(db, provisioned_pool, reg) as (ret_id, schema, ws_id):
        sku, sid = await seed_sku_with_stock(db, schema, ret_id)
        order = await http_create_wholesaler_order(osd1_client, token, ret_id, sku, 1)
        oid = order["id"]

        session = await _guard_session(schema, ws_id)
        try:
            await session.execute(text(
                f'UPDATE "{schema}".order_items SET sellable_unit_id = NULL, '
                "identity_status = 'legacy', unit_snapshot = NULL "
                "WHERE order_id = :oid"), {"oid": oid})
            await session.commit()
        finally:
            await session.close()
        await db.rollback()

        before = await snapshot_order_items(db, schema, oid)
        resp = await http_action(osd1_client, token, oid, "confirm")
        assert resp.status_code == HTTPStatus.CONFLICT, resp.text
        assert _errcode(resp) == "ORDER_ITEM_SELLABLE_ID_REQUIRED", resp.text

        after = await snapshot_order_items(db, schema, oid)
        assert after == before, (
            "the failed confirm rewrote legacy identity shape: "
            f"{before} -> {after}")


# ---------------------------------------------------------------------------
# First-reference vs packaging-change concurrency boundary (real surfaces)
# ---------------------------------------------------------------------------


async def test_first_reference_insert_vs_guard_history_race(
    osd1_client, s2_clean_db, provisioned_pool, osd1_cashier, monkeypatch
):
    """CONTRACT: a packaging change and the FIRST order reference must be
    mutually exclusive — 'immutable after use' is meaningless if the change
    can land inside the creating request's read-to-INSERT window.

    Deterministic interleaving with REAL surfaces and a DE-CONFOUNDED guard:
    the HTTP create request has already read the SKU row (no FOR UPDATE —
    source fact) and is parked immediately before the real
    ``crud_create_order``. While it is parked, an independent session zeroes
    the stock aggregate and retires the retailer price (the create snapshot
    was already read, so its own INSERT is unaffected). The real guard chain
    (lock_sku_row + ensure_package_quantity_change_allowed) then runs and —
    with order_reference/nonzero_stock/movement/reservation all false — has
    NOTHING to reject it except a lock serialization with the parked create;
    it writes the new package quantity and commits. The parked create
    resumes and commits the first reference.

    Current product: BOTH succeed (create's SKU read takes no skus lock and
    the INSERT is not serialized against the guard) -> RED (boundary gap).
    An orchestration timeout is recorded, never read as a product defect."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(osd1_client, osd1_cashier)
    async with bound_retailer(db, provisioned_pool, reg) as (ret_id, schema, ws_id):
        sku, sid = await seed_sku_with_stock(db, schema, ret_id, quantity=100, price="7.00")

        import api.v1.orders as orders_api

        real_create = orders_api.crud_create_order
        create_in_flight = asyncio.Event()
        guard_checked = asyncio.Event()

        async def gated_create(*args, **kwargs):
            # the endpoint calls crud_create_order(db=db, ...) keyword-style,
            # so transparently forward everything
            create_in_flight.set()     # SKU row already read (unlocked) above
            await asyncio.wait_for(guard_checked.wait(), _BUDGET)
            return await real_create(*args, **kwargs)

        monkeypatch.setattr(orders_api, "crud_create_order", gated_create)

        guard_result: dict = {}

        async def run_guard():
            session = None
            try:
                guard_result["stage"] = "verdict-enter"
                verdict = await _guard_verdict_fresh(schema, ws_id, sid, Decimal("12"))
                guard_result["stage"] = "verdict-done"
                session = await _guard_session(schema, ws_id)
                if verdict is None:
                    # real write of the accepted change, as update_sku would
                    from services.package_identity import lock_sku_row
                    locked = await lock_sku_row(session, sku_id=uuid.UUID(sid))
                    locked.package_quantity = Decimal("12")
                    guard_result["stage"] = "commit-enter"
                    await session.commit()
                    guard_result["stage"] = "commit-done"
                else:
                    await session.rollback()
                guard_result["verdict"] = verdict
            except BaseException as exc:  # surface into the result, never swallow
                guard_result["error"] = f"{type(exc).__name__}: {exc}"
                try:
                    if session is not None:
                        await session.rollback()
                except Exception:
                    pass
            finally:
                if session is not None:
                    await session.close()

        orch = RaceOrchestrator(_BUDGET)
        try:
            create_task = orch.spawn(
                http_create_wholesaler_order(osd1_client, token, ret_id, sku, 2))
            async with asyncio.timeout(_BUDGET):
                await asyncio.wait_for(create_in_flight.wait(), _BUDGET)
                # de-confound while the create transaction holds its read
                # snapshot and is parked before INSERT: only the order
                # reference can (or should) decide the guard
                await strip_price_and_zero_stock(db, schema, sid)
                guard_task = orch.spawn(run_guard())
                # release create once the guard has produced its verdict
                while "verdict" not in guard_result and not guard_task.done():
                    await asyncio.sleep(0.01)
                guard_checked.set()
                await asyncio.wait_for(asyncio.shield(create_task), _BUDGET)
        except TimeoutError:
            orch.timed_out = True
            raise AssertionError(
                "ORCHESTRATION_TIMEOUT: first-reference/guard interleaving "
                f"never completed within {_BUDGET}s — not a product-defect "
                f"verdict; guard diagnostics: {guard_result!r}")
        finally:
            await orch.drain()

        assert "verdict" in guard_result, f"guard never produced a verdict: {guard_result}"

        count = int((await db.execute(text(
            f'SELECT count(*) FROM "{schema}".order_items '
            "WHERE sellable_unit_id = :s"), {"s": sid})).scalar_one())

        # CONTRACT: if the order reference exists, the guard must have failed
        if count > 0:
            assert guard_result["verdict"] is not None, (
                f"RED_EVIDENCE boundary gap: first reference committed "
                f"(order_items={count}) while the packaging change ALSO "
                f"succeeded (verdict={guard_result['verdict']}); create's SKU "
                "read holds no skus lock and the INSERT is not serialized "
                "against the shared guard lock")
        else:
            # guard's window swallowed the whole create: create must have failed
            assert guard_result["verdict"] is None, (
                f"neither reference nor change landed: items={count} "
                f"verdict={guard_result['verdict']}")
