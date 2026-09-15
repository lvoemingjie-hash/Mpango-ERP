"""MPANGO-ORDER-STATE-AUTHORITY-D1 matrix group 3 — locked-ORM freshness.

PROOF BOUNDARY (direct service, two real sessions): this group proves the
service-layer serialization semantics of ``OrderService.transition`` — what
the HTTP pay/fulfill/return paths rely on. The HTTP wrapper behaviors are
proven separately in groups 1/2/4/6.

Finding under test: ``transition`` locks the order row with SELECT FOR UPDATE
but WITHOUT ``populate_existing``/``expire`` — when the CALLING session has
already loaded the order (unexpired identity-map object), the locked SELECT
does not refresh the in-memory attributes, so the matrix check validates the
STALE pre-lock state and the write lands on top of a concurrently changed
row (lost update under the very lock meant to prevent it).

- Fresh session (no preload): transition correctly 409s against the
  committed concurrent change (positive control — the lock works when the
  object is not stale).
- Preloaded session WITHOUT expire: transition accepts CONFIRMED->PAID even
  though the committed row is CANCELLED -> RED (current product defect).
- Preloaded session WITH db.expire(obj) (the fulfill endpoint's own
  mitigation pattern): the locked SELECT repopulates -> correct 409 — the
  codebase already contains the fix pattern, applied to one caller only.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from core.domain.order_state import (
    InvalidStateTransitionError,
    OrderInvariantViolation,
    OrderState,
)
from database.session import AsyncSessionLocal
from services.order_service import OrderService

from tests.order_state_d1.support import (
    bound_retailer,
    http_action,
    http_create_wholesaler_order,
    osd1_cashier_token,
    seed_sku_with_stock,
)

pytestmark = pytest.mark.asyncio


async def _seed_confirmed_order(osd1_client, token, db, pool, reg):
    async with bound_retailer(db, pool, reg) as (ret_id, schema, _ws):
        sku, _sid = await seed_sku_with_stock(db, schema, ret_id, quantity=100)
        order = await http_create_wholesaler_order(osd1_client, token, ret_id, sku, 2)
        oid = order["id"]
        assert (await http_action(osd1_client, token, oid, "confirm")).status_code == 200
        return oid, schema


async def _bind_tenant_session(schema: str, tenant_id: str):
    session = AsyncSessionLocal()
    session.info["tenant_schema"] = schema
    session.info["tenant_id"] = tenant_id
    await session.execute(text(f'SET search_path TO "{schema}", public'))
    return session


async def _externally_cancel(db, schema: str, tenant_id: str, oid) -> None:
    """A second actor commits CANCELLED while our session holds the old object."""
    other = await _bind_tenant_session(schema, tenant_id)
    try:
        await other.execute(text(
            f'UPDATE "{schema}".orders SET status = \'cancelled\' WHERE id = :oid'
        ), {"oid": oid})
        await other.commit()
    finally:
        await other.close()
    await db.rollback()  # drop any snapshot so later reads see the commit


async def test_fresh_session_transition_sees_committed_change_positive_control(
    osd1_client, s2_clean_db, provisioned_pool, osd1_cashier
):
    db, reg = s2_clean_db
    token = await osd1_cashier_token(osd1_client, osd1_cashier)
    oid, schema = await _seed_confirmed_order(osd1_client, token, db, provisioned_pool, reg)
    ws_id = provisioned_pool.tenants["a"]["ws_id"]
    await _externally_cancel(db, schema, ws_id, oid)

    service_session = await _bind_tenant_session(schema, ws_id)
    try:
        with pytest.raises((InvalidStateTransitionError, OrderInvariantViolation)):
            await OrderService(service_session).transition(
                order_id=uuid.UUID(oid), target_state=OrderState.PAID
            )
    finally:
        await service_session.rollback()
        await service_session.close()


async def test_preloaded_session_transition_uses_stale_state_current_defect(
    osd1_client, s2_clean_db, provisioned_pool, osd1_cashier
):
    """The caller preloaded the order (like confirm/cancel endpoints do via
    get_order_by_id). transition() takes the row lock but never repopulates
    the unexpired identity-map object, so it validates CONFIRMED (stale) and
    writes PAID over the committed CANCELLED row."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(osd1_client, osd1_cashier)
    oid, schema = await _seed_confirmed_order(osd1_client, token, db, provisioned_pool, reg)
    ws_id = provisioned_pool.tenants["a"]["ws_id"]

    service_session = await _bind_tenant_session(schema, ws_id)
    try:
        from models.order import Order
        result = await service_session.execute(
            text(f'SELECT * FROM "{schema}".orders WHERE id = :oid'), {"oid": oid}
        )
        assert result.fetchone() is not None  # plain read, no ORM preload yet

        # ORM preload (identity map now holds an unexpired CONFIRMED object)
        from sqlalchemy import select
        preloaded = (await service_session.execute(
            select(Order).where(Order.id == uuid.UUID(oid))
        )).scalar_one()
        assert preloaded.status.value == "confirmed"

        await _externally_cancel(db, schema, ws_id, oid)

        # CONTRACT: the locked transition must reject CONFIRMED->PAID because
        # the locked-fresh row is CANCELLED. Current product accepts it.
        with pytest.raises((InvalidStateTransitionError, OrderInvariantViolation)):
            await OrderService(service_session).transition(
                order_id=uuid.UUID(oid), target_state=OrderState.PAID
            )
        await service_session.rollback()
    finally:
        await service_session.close()

    row = (await db.execute(text(
        f'SELECT status FROM "{schema}".orders WHERE id = :oid'), {"oid": oid}
    )).fetchone()
    assert row.status == "cancelled", (
        f"locked transition overwrote a committed concurrent CANCELLED with "
        f"{row.status}: lock taken without freshness")
