"""Real independent processes and fault boundaries, never a cached response mock."""
import asyncio
import json
import os
from pathlib import Path
import sys
import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import event, text

from tests.s1_pricing_quote.test_http import facts, headers, preview, selection, submit

pytestmark = pytest.mark.asyncio


async def start():
    process = await asyncio.create_subprocess_exec(
        sys.executable, '-B', str(Path(__file__).with_name('process_create.py')),
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE, env=os.environ.copy())
    try:
        async with asyncio.timeout(30):
            while True:
                line = await process.stdout.readline()
                if line == b'S1_PROCESS_READY\n':
                    return process
                if not line:
                    raise AssertionError('S1_PROCESS_FAILED_BEFORE_READY')
    except BaseException:
        if process.returncode is None:
            process.kill()
        await process.communicate()
        raise


async def finish(process, payload):
    async with asyncio.timeout(30):
        output, _private_stderr = await process.communicate(json.dumps(payload).encode() + b'\n')
    assert process.returncode == 0, 'S1_PROCESS_REQUEST_EXIT'
    rows = [json.loads(line.removeprefix('S1_RESULT ')) for line in output.decode().splitlines()
            if line.startswith('S1_RESULT ')]
    assert len(rows) == 1, 'S1_PROCESS_SINGLE_RESULT'
    return rows[0]


async def test_two_processes_same_key_and_fresh_process_replay(r1_client, world):
    quote = await preview(r1_client, world)
    payload = {'token': world['token'], 'key': str(uuid.uuid4()), 'body': {
        'items': selection(world), 'retailer_id': world['rid'], 'quote_token': quote['quote_token'], 'notes': 'process'}}
    children = []
    try:
        children.extend(await asyncio.gather(start(), start()))
        assert children[0].pid != children[1].pid, 'S1_INDEPENDENT_OS_PROCESSES'
        first, second = await asyncio.gather(*(finish(child, payload) for child in children))
        assert first['status'] == second['status'] == 201, 'S1_BOTH_AUTHORIZED_PROCESS_REQUESTS'
        assert first['id'] == second['id'], 'S1_DURABLE_SAME_KEY_ONE_ORDER'
        assert (await facts(world))['orders'] == 1, 'S1_DURABLE_SAME_KEY_ONE_ORDER'
        async with world['session']() as db:
            await db.execute(text('UPDATE skus SET base_price=120 WHERE id=:id'), {'id': uuid.UUID(world['sku'])})
            await db.commit()
        restarted = await start()
        children.append(restarted)
        replay = await finish(restarted, payload)
        assert replay['status'] == 201 and replay['id'] == first['id'], 'S1_RESTART_DURABLE_REPLAY'
        conflicted = await start()
        children.append(conflicted)
        conflict = await finish(conflicted, {**payload, 'body': {**payload['body'], 'notes': 'different'}})
        assert conflict['status'] == 409 and conflict['code'] == 'ORDER_CREATE_IDEMPOTENCY_CONFLICT'
        assert (await facts(world))['orders'] == 1
    finally:
        for child in children:
            if child.returncode is None:
                child.kill()
                await child.communicate()


@pytest.mark.parametrize('fault_at', ['second-item', 'commit'])
async def test_create_fault_rolls_back_all_effects(r1_client, world, fault_at):
    from models.order import OrderItem
    from sqlalchemy.orm import Session
    async with world['session']() as db:
        sid = (await db.execute(text(
            "INSERT INTO skus(sku_code,name,unit,package_quantity,catalog_product_id,base_price) "
            "VALUES('BOX2','Second box','Box',12,:pid,90) RETURNING id"), {'pid': uuid.UUID(world['product'])})).scalar_one()
        await db.execute(text('INSERT INTO inventory_stocks(sku_id,quantity_on_hand) VALUES(:id,100)'), {'id': sid})
        await db.commit()
    body = {'retailer_id': world['rid'], 'items': selection(world) + [
        {'sellable_unit_id': str(sid), 'quantity': 1}]}
    quote = await r1_client.post('/api/v1/orders/quote', json=body, headers=headers(world))
    assert quote.status_code == 200
    before = await facts(world)
    seen = []
    def item_fault(_mapper, connection, _item):
        seen.append('inserted-item')
        if len(seen) == 2:
            assert connection.scalar(text('SELECT count(*) FROM order_items')) == 2, 'S1_SECOND_ITEM_WAS_WRITTEN'
            raise RuntimeError('S1_INJECTED_ITEM_WRITE_FAILURE')
    def commit_fault(session):
        if not session.in_nested_transaction() and any(
                getattr(obj, 'creation_operation', None) == 'merchant-create' for obj in session.identity_map.values()):
            seen.append('commit')
            raise RuntimeError('S1_INJECTED_COMMIT_FAILURE')
    target, name, handler = ((OrderItem, 'after_insert', item_fault)
                            if fault_at == 'second-item' else (Session, 'before_commit', commit_fault))
    event.listen(target, name, handler)
    try:
        with pytest.raises(RuntimeError, match='S1_INJECTED_'):
            await r1_client.post('/api/v1/orders', json={**body, 'quote_token': quote.json()['data']['quote_token']},
                                headers=headers(world, key=str(uuid.uuid4())))
    finally:
        event.remove(target, name, handler)
    assert seen, 'S1_FAULT_BOUNDARY_ACTUALLY_REACHED'
    assert await facts(world) == before, 'S1_CREATE_FAILURE_ZERO_PARTIAL_RESULT'


async def test_replacement_cancel_failure_restores_old_draft(r1_client, world):
    quote = await preview(r1_client, world, client=True)
    first = await submit(r1_client, world, quote, client=True)
    oid = first.json()['data']['id']
    before = await facts(world)
    from services.order_command_service import OrderCommandService
    original = OrderCommandService.cancel_order
    async def fail_after_cancel(self, *args, **kwargs):
        await original(self, *args, **kwargs)
        raise RuntimeError('S1_INJECTED_CANCEL_FAILURE')
    with patch.object(OrderCommandService, 'cancel_order', fail_after_cancel):
        with pytest.raises(RuntimeError, match='S1_INJECTED_CANCEL_FAILURE'):
            await submit(r1_client, world, quote, client=True, replace=oid)
    assert await facts(world) == before, 'S1_REPLACE_FAILURE_ZERO_PARTIAL_RESULT'
    async with world['session']() as db:
        assert (await db.execute(text('SELECT status FROM orders WHERE id=:id'),
                                {'id': uuid.UUID(oid)})).scalar_one() == 'draft'
