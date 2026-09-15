"""R1 freshness: lock-after-preload uses the refreshed object; a stale
identity-map object can no longer drive the matrix decision. Includes the
fresh-session committed-state read proving the fix end to end."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text

from core.domain.order_state import (
    InvalidStateTransitionError,
    OrderInvariantViolation,
    OrderState,
)
from database.session import AsyncSessionLocal
from services.order_command_service import OrderCommandService

from tests.order_state_r1.support import (
    _second_session,
    rebind_search_path,
    http_action,
    http_create_order,
    make_bound_retailer,
    order_vector,
    osd1_cashier_token,
    seed_sku_with_stock,
)

pytestmark = pytest.mark.asyncio


async def test_preloaded_session_transition_uses_locked_fresh_state(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity
):
    """A preloaded CONFIRMED object plus a concurrent committed CANCELLED:
    the locked transition must reject (old product accepted the stale
    state). After rejection, an independent fresh session still reads the
    committed CANCELLED — nothing was overwritten."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, ws_id = await make_bound_retailer(db, provisioned_pool, reg)
    sku, _sid = await seed_sku_with_stock(db, schema, ret_id)
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 2}])
    assert (await http_action(r1_client, token, oid, "confirm")).status_code == 200

    service_session = await _second_session(schema, ws_id)
    try:
        preloaded = (await service_session.execute(
            select(Order := __import__("models.order", fromlist=["Order"]).Order)
            .where(Order.id == uuid.UUID(oid))
        )).scalar_one()
        assert preloaded.status.value == "confirmed"

        # a second actor commits CANCELLED while we hold the old object
        other = await _second_session(schema, ws_id)
        try:
            await other.execute(text(
                f'UPDATE "{schema}".orders SET status = \'cancelled\' '
                "WHERE id = :oid"), {"oid": oid})
            await other.commit()
        finally:
            await other.close()
        # NO rollback here: the identity map must still hold the stale
        # CONFIRMED object when the locked transition runs — only
        # populate_existing forces the refresh that sees CANCELLED.
        with pytest.raises((InvalidStateTransitionError, OrderInvariantViolation)):
            await OrderCommandService(service_session).apply_transition(
                uuid.UUID(oid), OrderState.PAID)
    finally:
        await service_session.rollback()
        await service_session.close()

    reader = await _second_session(schema, ws_id)
    try:
        state = await order_vector(reader, schema, oid)
    finally:
        await reader.close()
    assert state["status"] == "cancelled", state


async def test_committed_stale_write_is_rejected_fresh_session_read(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity
):
    """FIXTURE-ONLY CURRENT-BEHAVIOR PROOF (fixed product): the stale
    acceptance no longer exists — the transition raises and, after a
    rollback, an independent fresh session still reads the concurrent
    CANCELLED. (The D1-era diagnostic proved the OLD behavior persisted
    PAID; this is its fixed-product counterpart.)"""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, ws_id = await make_bound_retailer(db, provisioned_pool, reg)
    sku, _sid = await seed_sku_with_stock(db, schema, ret_id)
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 2}])
    assert (await http_action(r1_client, token, oid, "confirm")).status_code == 200

    service_session = await _second_session(schema, ws_id)
    try:
        preloaded = (await service_session.execute(
            select(__import__("models.order", fromlist=["Order"]).Order)
            .where(__import__("models.order", fromlist=["Order"]).Order.id == uuid.UUID(oid))
        )).scalar_one()
        assert preloaded.status.value == "confirmed"

        other = await _second_session(schema, ws_id)
        try:
            await other.execute(text(
                f'UPDATE "{schema}".orders SET status = \'cancelled\' '
                "WHERE id = :oid"), {"oid": oid})
            await other.commit()
        finally:
            await other.close()
        await service_session.rollback()
        await rebind_search_path(service_session, schema)

        with pytest.raises((InvalidStateTransitionError, OrderInvariantViolation)):
            await OrderCommandService(service_session).apply_transition(
                uuid.UUID(oid), OrderState.PAID)
        await rebind_search_path(service_session, schema)
        await service_session.commit()  # nothing to commit; proves no write
    finally:
        await service_session.rollback()
        await service_session.close()

    reader = await _second_session(schema, ws_id)
    try:
        state = await order_vector(reader, schema, oid)
    finally:
        await reader.close()
    assert state["status"] == "cancelled", (
        f"stale write persisted despite the rejection: {state}")


async def test_confirm_after_external_cancel_uses_locked_fresh_state(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity
):
    """M2 oracle: a preloaded DRAFT object plus a concurrent committed
    CANCELLED — the confirm COMMAND must decide on the locked-fresh row
    (terminal CANCELLED) and reject; without populate_existing the stale
    DRAFT passes and the confirmation succeeds (mutation RED)."""
    from services.order_command_service import (
        InvalidStateTransitionError as _Iste,
        OrderCommandService as _Ocs,
    )
    from core.domain.order_state import OrderInvariantViolation as _Oiv

    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, ws_id = await make_bound_retailer(db, provisioned_pool, reg)
    sku, _sid = await seed_sku_with_stock(db, schema, ret_id)
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 2}])

    session = await _second_session(schema, ws_id)
    try:
        preloaded = (await session.execute(
            select(Order).where(Order.id == uuid.UUID(oid))
        )).scalar_one()
        assert preloaded.status.value == "draft"

        other = await _second_session(schema, ws_id)
        try:
            await other.execute(text(
                f'UPDATE "{schema}".orders SET status = \'cancelled\' '
                "WHERE id = :oid"), {"oid": oid})
            await other.commit()
        finally:
            await other.close()

        # no rollback: the stale DRAFT stays in the identity map
        with pytest.raises((_Iste, _Oiv)):
            await _Ocs(session).confirm_order(uuid.UUID(oid))
    finally:
        await session.rollback()
        await session.close()
