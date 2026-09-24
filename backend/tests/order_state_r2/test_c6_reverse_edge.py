"""C6 lock-order regression: the declaration-confirmation path must NEVER
take a binding row lock before the order row lock.

Mechanism (fully deterministic, real PG locks, no sleeps-as-serialization):
the test holds the ORDER row FOR UPDATE from a separate session, starts a
real declaration confirmation, and polls pg_locks. A RowShareLock on
public.wholesaler_retailer_bindings (the signature of SELECT ... FOR UPDATE
taken by the reverse-edge implementation) appearing while the confirmation
is still waiting on the order lock proves the reverse edge. The corrected
path reads the binding without a row lock, so no such lock can appear.
"""
from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from tests.order_state_r2.support import (
    binding_balance,
    http_action,
    http_create_order,
    make_bound_retailer,
    osd1_cashier_token,
    seed_sku_with_stock,
)

pytestmark = pytest.mark.asyncio

# (contention window) how long the probe waits for a reverse-edge signature
# before concluding the path is clean; bounded so a deadlock can never hang
# the suite.
POLL_SECONDS = 8.0


async def test_c6_no_binding_lock_before_order_lock(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity, monkeypatch
):
    from services.payment_declaration_service import PaymentDeclarationService
    from tests.order_state_r1.support import _second_session

    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, ws_id = await make_bound_retailer(db, provisioned_pool, reg)
    sku, _sid = await seed_sku_with_stock(db, schema, ret_id, price="50.00")
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 2}])
    assert (await http_action(r1_client, token, oid, "confirm")).status_code == 200
    from tests.order_state_r1.support import rebind_search_path
    await rebind_search_path(db, schema)

    record, _ = await PaymentDeclarationService().submit_declaration(
        db=db,
        order_id=oid,
        retailer_id=uuid.UUID(ret_id),
        wholesaler_id=uuid.UUID(ws_id),
        submitted_by=uuid.UUID(str(cashier_identity["user_id"])),
        declared_amount=Decimal("100.00"),
        method="cash",
        transfer_reference=None,
        idempotency_key=f"r2-m6-{uuid.uuid4().hex}",
    )
    await db.commit()
    decl_id = str(record["id"])

    from tests.order_state_r1.support import rebind_search_path
    holder = await _second_session(schema, ws_id)
    await rebind_search_path(holder, schema)
    runner = await _second_session(schema, ws_id)
    await rebind_search_path(runner, schema)
    confirm_task = None
    try:
        # Hold the ORDER row in the HOLDER session: the confirmation (RUNNER
        # session) must block on the ORDER (its first lock) and must NOT have
        # touched the binding row by then.
        await holder.execute(text(
            f'SELECT id FROM "{schema}".orders WHERE id = :oid FOR UPDATE'),
            {"oid": oid})
        # keep this transaction OPEN: the order row lock must stay held

        async def run_confirm():
            return await PaymentDeclarationService().confirm_declaration(
                db=runner,
                declaration_id=uuid.UUID(decl_id),
                wholesaler_id=uuid.UUID(ws_id),
                confirmed_by=uuid.UUID(str(cashier_identity["user_id"])),
            )

        confirm_task = asyncio.create_task(run_confirm())
        await asyncio.sleep(0.2)  # let the runner reach the order lock wait

        reverse_edge_seen = False
        deadline = asyncio.get_event_loop().time() + POLL_SECONDS
        while asyncio.get_event_loop().time() < deadline:
            if confirm_task.done():
                break
            row = (await db.execute(text(
                "SELECT 1 "
                "FROM pg_locks l "
                "JOIN pg_class c ON c.oid = l.relation "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE c.relname = 'wholesaler_retailer_bindings' "
                "AND n.nspname = 'public' "
                "AND l.mode = 'RowShareLock' AND l.granted "
                "LIMIT 1"))).first()
            if row is not None:
                reverse_edge_seen = True
                break
            await asyncio.sleep(0.05)

        assert not reverse_edge_seen, (
            "C6 reverse edge: declaration confirmation took a binding row "
            "lock (RowShareLock) BEFORE acquiring the order lock — the "
            "binding must be locked LAST on this path")

        # release the order row; the confirmation completes normally
        await holder.rollback()  # releases the order row lock
        result = await asyncio.wait_for(confirm_task, 30.0)
        _declaration, payment_result = result
        assert payment_result.replayed is False
        await runner.commit()  # persist the confirmation
        reader = await _second_session(schema, ws_id)
        try:
            assert (await binding_balance(reader, ws_id, ret_id)) == Decimal("0.00")
        finally:
            await reader.close()
    finally:
        if confirm_task is not None and not confirm_task.done():
            confirm_task.cancel()
            try:
                await confirm_task
            except (asyncio.CancelledError, Exception):
                pass
        for session in (runner, holder):
            try:
                await session.rollback()
                await session.close()
            except Exception:
                pass
