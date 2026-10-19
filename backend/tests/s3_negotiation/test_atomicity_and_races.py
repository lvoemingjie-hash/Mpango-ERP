"""Independent PG sessions and actual blocked-lock observations, not timing guesses."""
import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text

from models.order import Order
from schemas.order_negotiation import ProposalDecision
from services import order_negotiation_service as service
from tests.s1_pricing_quote.test_http import headers
from tests.s3_negotiation.test_contract import decide, economics, offer, original

pytestmark = pytest.mark.asyncio


async def blocked(world, holder, count=1):
    async with asyncio.timeout(15):
        while True:
            async with world['session']() as observer:
                graph = (await observer.execute(text(
                    'SELECT pid,pg_blocking_pids(pid) FROM pg_stat_activity WHERE datname=current_database()'
                ))).all()
            # PG tuple-lock queues may name the preceding waiter, not just
            # the row owner. Prove the whole actual blocking chain.
            reached = {holder}
            while True:
                expanded = reached | {pid for pid, owners in graph if reached.intersection(owners)}
                if expanded == reached:
                    break
                reached = expanded
            if len(reached) - 1 >= count:
                return
            await asyncio.sleep(0.01)


async def until_deadline(world, deadline):
    async with asyncio.timeout(15):
        while True:
            async with world['session']() as observer:
                now = (await observer.execute(text('SELECT clock_timestamp()'))).scalar_one()
            if now >= datetime.fromisoformat(deadline):
                return
            await asyncio.sleep(0.02)


async def decisions(world):
    async with world['session']() as db:
        return [tuple(row) for row in (await db.execute(text(
            'SELECT status,accepted_order_id FROM order_negotiation_proposals ORDER BY version'))).all()]


@pytest.mark.parametrize('failure', ['save', 'cancel'])
async def test_accept_save_or_close_failure_is_atomic_even_if_caller_commits(r1_client, world, monkeypatch, failure):
    source = await original(r1_client, world)
    proposal = (await offer(r1_client, world, source)).json()['data']
    before = await economics(world)
    from services.order_command_service import OrderCommandService
    real_save, real_cancel = service.create_order, OrderCommandService.cancel_order

    async def fail_save(*args, **kwargs):
        await real_save(*args, **kwargs)
        raise RuntimeError('S3_INJECT_AFTER_REAL_SAVE')

    async def fail_cancel(self, *args, **kwargs):
        await real_cancel(self, *args, **kwargs)
        raise RuntimeError('S3_INJECT_AFTER_REAL_CANCEL')

    monkeypatch.setattr(service, 'create_order', fail_save if failure == 'save' else real_save)
    monkeypatch.setattr(OrderCommandService, 'cancel_order', fail_cancel if failure == 'cancel' else real_cancel)
    async with world['session']() as db:
        with pytest.raises(RuntimeError, match='S3_INJECT_AFTER_REAL_'):
            await service.accept_proposal(db, order_id=source['id'], proposal_id=proposal['id'],
                wholesaler_id=world['wid'], retailer_id=world['rid'], actor_id=world['customer'],
                decision=ProposalDecision(version=proposal['version'], digest=proposal['digest']),
                idempotency_key=str(uuid4()))
        await db.commit()
    async with world['session']() as db:
        assert (await db.execute(text('SELECT count(*) FROM orders'))).scalar_one() == 1, 'S3_ATOMIC_REPLACEMENT_NO_PARTIAL_SAVE'
        assert (await db.execute(text('SELECT status::text FROM orders'))).scalar_one() == 'draft', 'S3_ATOMIC_REPLACEMENT_NO_PARTIAL_CLOSE'
    assert await decisions(world) == [('pending', None)], 'S3_ATOMIC_CONSENT_NO_PARTIAL_DECISION'
    assert await economics(world) == before


@pytest.mark.parametrize('first,second', [
    ('accept', 'accept'), ('accept', 'reject'), ('reject', 'accept'),
    ('withdraw', 'accept'), ('accept', 'withdraw'), ('cancel', 'accept'),
    ('confirm', 'accept'), ('accept', 'confirm'), ('accept', 'cancel'),
])
async def test_real_source_lock_races_have_one_legal_serial_history(r1_client, world, first, second):
    source = await original(r1_client, world)
    proposal = (await offer(r1_client, world, source)).json()['data']
    tasks = []

    async def request(action):
        if action in {'accept', 'reject'}:
            return await decide(r1_client, world, source, proposal, action)
        if action == 'withdraw':
            return await r1_client.post(
                f"/api/v1/orders/{source['id']}/negotiations/{proposal['id']}/withdraw",
                json={'version': proposal['version'], 'digest': proposal['digest']}, headers=headers(world))
        return await r1_client.post(f"/api/v1/orders/{source['id']}/{action}", headers=headers(world))

    async with world['session']() as blocker:
        await blocker.execute(select(Order).where(Order.id == UUID(source['id'])).with_for_update())
        holder = (await blocker.execute(text('SELECT pg_backend_pid()'))).scalar_one()
        try:
            tasks.append(asyncio.create_task(request(first)))
            await blocked(world, holder)
            tasks.append(asyncio.create_task(request(second)))
            await blocked(world, holder, 2)
            await blocker.commit()
            a, b = await asyncio.wait_for(asyncio.gather(*tasks), timeout=25)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
    assert a.status_code == 200 and b.status_code == 409, 'S3_SERIAL_HISTORY_ONE_DECISION'
    async with world['session']() as db:
        count = (await db.execute(text('SELECT count(*) FROM orders WHERE replaces_order_id=:oid'),
                                 {'oid': UUID(source['id'])})).scalar_one()
        assert count == (1 if first == 'accept' else 0), 'S3_DIFFERENT_KEYS_NEVER_SECOND_REPLACEMENT'
        source_status = (await db.execute(text('SELECT status::text FROM orders WHERE id=:oid'),
                                         {'oid': UUID(source['id'])})).scalar_one()
        assert source_status == ('confirmed' if first == 'confirm' else 'draft' if first in {'reject', 'withdraw'} else 'cancelled')


async def test_accept_waiting_for_source_lock_past_deadline_refuses(r1_client, world):
    source = await original(r1_client, world)
    proposal = (await offer(r1_client, world, source,
        expires=(datetime.now(timezone.utc) + timedelta(seconds=5)).isoformat())).json()['data']
    before = await economics(world)
    async with world['session']() as blocker:
        await blocker.execute(select(Order).where(Order.id == UUID(source['id'])).with_for_update())
        holder = (await blocker.execute(text('SELECT pg_backend_pid()'))).scalar_one()
        task = asyncio.create_task(decide(r1_client, world, source, proposal))
        try:
            await blocked(world, holder)
            await until_deadline(world, proposal['expires_at'])
            await blocker.commit()
            response = await asyncio.wait_for(task, 15)
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    assert response.status_code == 409 and response.json()['code'] == 'NEGOTIATION_EXPIRED', 'S3_DEADLINE_LOCK_BOUNDARY'
    assert await decisions(world) == [('pending', None)]
    assert await economics(world) == before


async def test_confirmation_waiting_for_stock_lock_past_deadline_refuses(r1_client, world):
    source = await original(r1_client, world)
    proposal = (await offer(r1_client, world, source,
        expires=(datetime.now(timezone.utc) + timedelta(seconds=6)).isoformat())).json()['data']
    accepted = await decide(r1_client, world, source, proposal)
    assert accepted.status_code == 200
    new_id = accepted.json()['data']['accepted_order_id']
    before = await economics(world)
    async with world['session']() as blocker:
        await blocker.execute(text('SELECT sku_id FROM inventory_stocks WHERE sku_id=:sid FOR UPDATE'), {'sid': UUID(world['sku'])})
        holder = (await blocker.execute(text('SELECT pg_backend_pid()'))).scalar_one()
        task = asyncio.create_task(r1_client.post(f'/api/v1/orders/{new_id}/confirm', headers=headers(world)))
        try:
            await blocked(world, holder)
            await until_deadline(world, proposal['expires_at'])
            await blocker.commit()
            response = await asyncio.wait_for(task, 15)
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    assert response.status_code == 409 and response.json()['code'] == 'NEGOTIATION_EXPIRED', 'S3_CONFIRM_POST_STOCK_LOCK_DEADLINE'
    assert await economics(world) == before, 'S3_EXPIRED_CONFIRM_ZERO_EFFECTS'


async def test_committed_acceptance_replays_after_expiry_without_second_order(r1_client, world):
    source = await original(r1_client, world)
    proposal = (await offer(r1_client, world, source,
        expires=(datetime.now(timezone.utc) + timedelta(seconds=4)).isoformat())).json()['data']
    key = str(uuid4())
    accepted = await decide(r1_client, world, source, proposal, key=key)
    assert accepted.status_code == 200
    await until_deadline(world, proposal['expires_at'])
    replay = await decide(r1_client, world, source, proposal, key=key)
    assert replay.status_code == 200 and replay.json()['data']['replayed'] is True, 'S3_EXPIRED_COMMITTED_RESULT_RESTORED'
    assert replay.json()['data']['accepted_order_id'] == accepted.json()['data']['accepted_order_id']
    confirmed = await r1_client.post(f"/api/v1/orders/{accepted.json()['data']['accepted_order_id']}/confirm", headers=headers(world))
    assert confirmed.status_code == 409 and confirmed.json()['code'] == 'NEGOTIATION_EXPIRED'
