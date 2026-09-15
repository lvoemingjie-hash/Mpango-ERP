"""MPANGO-ORDER-STATE-AUTHORITY-D1 matrix group 3 — locked-ORM freshness.

R1 claim correction (Codex-L review): the stale-state test below proves that
``OrderService.transition`` ACCEPTS the CONFIRMED→PAID transition and at
minimum FLUSHES it while validating stale identity-map state. The test
fails at ``DID NOT RAISE`` and its finally closes the session WITHOUT
committing, so it does NOT by itself prove a committed PAID overwrite of a
concurrent CANCELLED. The committed-persistence claim is proven separately
by ``test_preloaded_transition_committed_overwrite_DIAGNOSTIC``, a
fixture-only diagnostic that commits in a dedicated session, reads the
persisted row from a fresh independent session, and cleans up. Do not
change the original rejection expectation just to make it pass.

PROOF BOUNDARY (direct service, real sessions): this group proves the
service-layer serialization semantics of ``OrderService.transition`` — what
the HTTP pay/fulfill/return paths rely on. HTTP wrapper behaviors are
covered in groups 1/2/4/6.

Finding under test: ``transition`` locks the order row with SELECT FOR UPDATE
but WITHOUT ``populate_existing``/``expire`` — when the CALLING session has
already loaded the order (unexpired identity-map object), the locked SELECT
does not refresh the in-memory attributes, so the matrix check validates the
STALE pre-lock state.

- Fresh session (no preload): transition correctly 409s against the
  committed concurrent change (positive control — the lock works when the
  object is not stale).
- Preloaded session WITHOUT expire: transition accepts CONFIRMED→PAID even
  though the committed row is CANCELLED -> RED (stale-state acceptance).
- Committed diagnostic: the flushed stale write, when committed, lands as
  PAID over CANCELLED (fixture-only; labelled; cleanup verified).
"""
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
from models.order import Order
from services.order_service import OrderService

from tests.order_state_d1.support import (
    bound_retailer,
    http_action,
    http_create_wholesaler_order,
    osd1_cashier_token,
    seed_sku_with_stock,
)

pytestmark = pytest.mark.asyncio


async def _bound_session(schema: str, tenant_id: str):
    session = AsyncSessionLocal()
    session.info["tenant_schema"] = schema
    session.info["tenant_id"] = tenant_id
    await session.execute(text(f'SET search_path TO "{schema}", public'))
    return session


async def _seed_confirmed_order(osd1_client, token, db, pool, reg):
    async with bound_retailer(db, pool, reg) as (ret_id, schema, _ws):
        sku, _sid = await seed_sku_with_stock(db, schema, ret_id, quantity=100)
        order = await http_create_wholesaler_order(osd1_client, token, ret_id, sku, 2)
        oid = order["id"]
        assert (await http_action(osd1_client, token, oid, "confirm")).status_code == 200
        return oid, schema


async def _externally_cancel(db, schema: str, tenant_id: str, oid) -> None:
    """A second actor commits CANCELLED while our session holds the old object."""
    other = await _bound_session(schema, tenant_id)
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
    ws_id = provisioned_pool.tenants["a"]["ws_id"]
    oid, schema = await _seed_confirmed_order(osd1_client, token, db, provisioned_pool, reg)
    await _externally_cancel(db, schema, ws_id, oid)

    service_session = await _bound_session(schema, ws_id)
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
    ACCEPTS + FLUSHES CONFIRMED→PAID although the committed row is CANCELLED.

    CLAIM SCOPE (R1): this test proves stale-state acceptance + flush. It
    does NOT commit, and the post-block persistence query is unreachable on
    the expected-failure path; committed persistence is proven by the
    separately labelled diagnostic below."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(osd1_client, osd1_cashier)
    ws_id = provisioned_pool.tenants["a"]["ws_id"]
    oid, schema = await _seed_confirmed_order(osd1_client, token, db, provisioned_pool, reg)

    service_session = await _bound_session(schema, ws_id)
    try:
        result = await service_session.execute(
            text(f'SELECT * FROM "{schema}".orders WHERE id = :oid'), {"oid": oid}
        )
        assert result.fetchone() is not None  # plain read, no ORM preload yet

        # ORM preload (identity map now holds an unexpired CONFIRMED object)
        preloaded = (await service_session.execute(
            select(Order).where(Order.id == uuid.UUID(oid))
        )).scalar_one()
        assert preloaded.status.value == "confirmed"

        await _externally_cancel(db, schema, ws_id, oid)

        # CONTRACT: the locked transition must reject CONFIRMED→PAID because
        # the locked-fresh row is CANCELLED. Current product accepts it.
        with pytest.raises((InvalidStateTransitionError, OrderInvariantViolation)):
            await OrderService(service_session).transition(
                order_id=uuid.UUID(oid), target_state=OrderState.PAID
            )
    finally:
        await service_session.rollback()
        await service_session.close()

    row = (await db.execute(text(
        f'SELECT status FROM "{schema}".orders WHERE id = :oid'), {"oid": oid}
    )).fetchone()
    assert row.status == "cancelled", (
        f"order status changed without any committed write in this test: {row.status}")


async def test_preloaded_transition_committed_overwrite_DIAGNOSTIC(
    osd1_client, s2_clean_db, provisioned_pool, osd1_cashier
):
    """FIXTURE-ONLY CURRENT-BEHAVIOR DIAGNOSTIC (R1, separately labelled).

    Not a contract assertion about desired behavior: this commits the
    stale-validated transition in a dedicated session and reads the
    persisted row from a fresh independent session, proving (or refuting)
    that the stale acceptance lands as a COMMITTED PAID overwrite of a
    concurrently cancelled order. The owning schema is torn down by the
    pool fixture; no product row outside this fixture is touched. If the
    product is later fixed, this diagnostic fails and must be updated to
    assert the rejection (never silently deleted)."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(osd1_client, osd1_cashier)
    ws_id = provisioned_pool.tenants["a"]["ws_id"]
    oid, schema = await _seed_confirmed_order(osd1_client, token, db, provisioned_pool, reg)

    service_session = await _bound_session(schema, ws_id)
    try:
        preloaded = (await service_session.execute(
            select(Order).where(Order.id == uuid.UUID(oid))
        )).scalar_one()
        assert preloaded.status.value == "confirmed"

        await _externally_cancel(db, schema, ws_id, oid)

        # current behavior: no rejection; flush + commit the stale write
        updated = await OrderService(service_session).transition(
            order_id=uuid.UUID(oid), target_state=OrderState.PAID
        )
        assert updated.status.value == "paid"
        await service_session.commit()
    finally:
        await service_session.rollback()
        await service_session.close()

    # fresh independent session reads the persisted row
    reader = await _bound_session(schema, ws_id)
    try:
        row = (await reader.execute(text(
            f'SELECT status FROM "{schema}".orders WHERE id = :oid'), {"oid": oid}
        )).fetchone()
    finally:
        await reader.close()
    assert row is not None
    assert row.status == "paid", (
        "CURRENT-BEHAVIOR-CHANGED: the committed stale transition no longer "
        f"persists PAID over CANCELLED (persisted={row.status}); if the "
        "product now rejects stale transitions, update this diagnostic and "
        "the group's stale-state test together")
