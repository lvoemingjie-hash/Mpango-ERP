"""R1 notification pipeline: zero sends before commit, zero sends on
rollback, post-commit best-effort dispatch with recipients resolved from
REAL retailer contact data (no placeholder addresses or phone numbers)."""
from __future__ import annotations

import asyncio
import uuid
from http import HTTPStatus

import pytest
from sqlalchemy import text

from tests.order_state_r1.support import (
    _second_session,
    http_action,
    http_create_order,
    make_bound_retailer,
    notification_spy,
    osd1_cashier_token,
    seed_sku_with_stock,
)

pytestmark = pytest.mark.asyncio

PLACEHOLDER_MARKERS = ("placeholder", "example.com", "@local", "+254000000000")


async def test_confirm_dispatches_after_commit_to_real_recipient(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity, monkeypatch
):
    """Seeded retailer has a REAL email; after the confirm response the
    post-commit dispatcher sends to that address. No placeholder values."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, _ws = await make_bound_retailer(db, provisioned_pool, reg)
    # give the retailer a REAL (test-scoped) email
    real_email = f"retailer-{uuid.uuid4().hex[:8]}@retailer.test"
    await db.execute(text(
        "UPDATE public.retailers SET email = :e WHERE id = :r"),
        {"e": real_email, "r": ret_id})
    await db.commit()
    await db.rollback()

    sku, _sid = await seed_sku_with_stock(db, schema, ret_id)
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 1}])

    spy_ctx = notification_spy()
    with spy_ctx as spy:
        resp = await http_action(r1_client, token, oid, "confirm")
        assert resp.status_code == HTTPStatus.OK, resp.text

    assert spy.total == 1, (spy.emails, spy.sms)
    assert spy.emails[0]["to"] == real_email
    for recipient in spy.recipients():
        for marker in PLACEHOLDER_MARKERS:
            assert marker not in recipient, recipient


async def test_no_send_before_commit(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity, monkeypatch
):
    """The confirm transaction is parked BEFORE commit (barrier inside the
    command service): zero notification sends may have happened at that
    point."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, _ws = await make_bound_retailer(db, provisioned_pool, reg)
    sku, _sid = await seed_sku_with_stock(db, schema, ret_id)
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 1}])

    import api.v1.orders as orders_api
    real_service = orders_api.OrderCommandService
    inside_tx = asyncio.Event()
    release = asyncio.Event()

    class GatedService(real_service):
        async def confirm_order(self, *args, **kwargs):
            result = await super().confirm_order(*args, **kwargs)
            inside_tx.set()          # state write flushed, commit NOT yet
            await asyncio.wait_for(release.wait(), 30.0)
            return result

    orders_api.OrderCommandService = GatedService
    spy_ctx = notification_spy()
    try:
        with spy_ctx as spy:
            task = asyncio.create_task(
                http_action(r1_client, token, oid, "confirm"))
            await asyncio.wait_for(inside_tx.wait(), 30.0)
            # transaction is open (post-write, pre-commit): nothing sent
            assert spy.total == 0, (
                f"send observed before commit: {spy.emails} {spy.sms}")
            release.set()
            resp = await task
            assert resp.status_code == HTTPStatus.OK, resp.text
    finally:
        orders_api.OrderCommandService = real_service


async def test_rollback_produces_zero_sends(
    r1_client, s2_clean_db, provisioned_pool, cashier_identity, monkeypatch
):
    """A fault AFTER the state write (during inventory reservation) rolls
    the request back: zero sends, including the intent that was already
    created inside the transaction."""
    db, reg = s2_clean_db
    token = await osd1_cashier_token(r1_client, cashier_identity)
    ret_id, schema, _ws = await make_bound_retailer(db, provisioned_pool, reg)
    real_email = f"retailer-{uuid.uuid4().hex[:8]}@retailer.test"
    await db.execute(text(
        "UPDATE public.retailers SET email = :e WHERE id = :r"),
        {"e": real_email, "r": ret_id})
    await db.commit()
    await db.rollback()
    sku, _sid = await seed_sku_with_stock(db, schema, ret_id)
    oid = await http_create_order(r1_client, token, ret_id,
                                  [{"sku_code": sku, "quantity": 5}])

    # shrink stock so reservation fails AFTER the (stale) state write would
    # have happened in the legacy flow; here the command reserves first, so
    # inject the fault INSIDE the command after the status assignment via
    # the credit-reservation seam.
    from services import order_command_service as ocs_mod

    real_reserve_credit = ocs_mod.OrderCommandService._reserve_credit

    async def exploding_credit(self, order):
        raise RuntimeError("R1 fault after state write, before commit")

    monkeypatch.setattr(ocs_mod.OrderCommandService, "_open_credit_hold",
                        exploding_credit)

    with notification_spy() as spy:
        with pytest.raises(RuntimeError, match="fault after state write"):
            await http_action(r1_client, token, oid, "confirm")
        await asyncio.sleep(0.05)
        assert spy.total == 0, (
            f"sends observed for a rolled-back request: {spy.emails} {spy.sms}")
