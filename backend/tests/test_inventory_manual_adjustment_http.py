"""Native JWT login/select-tenant HTTP controls for manual stock adjustment."""
from __future__ import annotations

from decimal import Decimal
import json
import os
import secrets
import time
import uuid

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from models.inventory_movement import InventoryMovement
from tests.test_inventory_manual_adjustment_safety import (
    StockWorld, assert_non_stock_unchanged, retain, stock_world,
)

pytestmark = pytest.mark.integration


def error_code(response):
    def find(value):
        if not isinstance(value, dict):
            return None
        if 'code' in value:
            return value['code']
        for key in ('detail', 'error', 'data'):
            result = find(value.get(key))
            if result:
                return result
        return None
    return find(response.json())


async def login(client, world, *, email=None, password=None):
    response = await client.post('/api/v1/auth/login', json={
        'email': email or world.email, 'password': password or world.password,
    })
    assert response.status_code == 200, 'INV_NATIVE_LOGIN_FAILED'
    identity = response.json()['data']['access_token']
    response = await client.post('/api/v1/auth/select-tenant',
                                 json={'tenant_id': str(world.wid)},
                                 headers={'Authorization': 'Bearer ' + identity})
    assert response.status_code == 200, 'INV_NATIVE_SELECT_TENANT_FAILED'
    return {'Authorization': 'Bearer ' + response.json()['data']['access_token']}


@pytest_asyncio.fixture
async def inventory_http(stock_world, monkeypatch):
    from api.app import configure_app
    from auth.strategies.jwt import JwtAuthStrategy
    from core.config import get_settings
    from core.error_codes import register_exception_handlers
    from fastapi import FastAPI

    assert os.environ['MPANGO_ENV'] == 'staging', 'INV_HTTP_REQUIRES_NATIVE_STAGING_PROFILE'
    app = FastAPI()
    configure_app(app, get_settings())
    register_exception_handlers(app)
    strategies = [item.kwargs['strategy'] for item in app.user_middleware
                  if item.cls.__name__ == 'AuthenticationMiddleware']
    assert len(strategies) == 1 and isinstance(strategies[0], JwtAuthStrategy)
    probe = {'events': [], 'fail_commit': False, 'fail_movement': False}
    real_flush, real_commit, real_execute = AsyncSession.flush, AsyncSession.commit, AsyncSession.execute

    async def observed_execute(session, statement, *args, **kwargs):
        result=await real_execute(session,statement,*args,**kwargs)
        sql=str(statement)
        if 'INSERT INTO' in sql and '.inventory_movements ' in sql and 'manual_adjustment_id' in sql:
            session.info['inventory_safety_manual_write']=True
            probe['events'].append(('manual_flush_end',time.monotonic()))
            if probe['fail_movement']:
                probe['events'].append(('manual_movement_injected_failure',time.monotonic()))
                raise RuntimeError('INV_HTTP_MOVEMENT_AFTER_FLUSH')
        return result

    async def observed_flush(session, *args, **kwargs):
        manual = any(isinstance(obj, InventoryMovement) and obj.reference_type == 'manual'
                     for obj in session.new)
        result = await real_flush(session, *args, **kwargs)
        if manual:
            session.info['inventory_safety_manual_write'] = True
            probe['events'].append(('manual_flush_end', time.monotonic()))
            if probe['fail_movement']:
                probe['events'].append(('manual_movement_injected_failure', time.monotonic()))
                raise RuntimeError('INV_HTTP_MOVEMENT_AFTER_FLUSH')
        return result

    async def observed_commit(session):
        manual = session.info.get('inventory_safety_manual_write', False)
        if manual:
            probe['events'].append(('manual_commit_begin', time.monotonic()))
            if probe['fail_commit']:
                probe['events'].append(('manual_commit_injected_failure', time.monotonic()))
                raise RuntimeError('INV_HTTP_COMMIT_FAILURE')
        result = await real_commit(session)
        if manual:
            probe['events'].append(('manual_commit_end', time.monotonic()))
        return result

    monkeypatch.setattr(AsyncSession, 'flush', observed_flush)
    monkeypatch.setattr(AsyncSession, 'commit', observed_commit)
    monkeypatch.setattr(AsyncSession, 'execute', observed_execute)

    async def timing(scope, receive, send):
        async def observed_send(message):
            if message['type'] == 'http.response.start':
                probe['events'].append(('response_' + str(message['status']), time.monotonic()))
            await send(message)
        await app(scope, receive, observed_send)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=timing, raise_app_exceptions=False),
                                base_url='http://inventory-safety.invalid', timeout=30) as client:
        headers = await login(client, stock_world)
        client._inventory_world=stock_world
        probe['events'].clear()
        yield client, headers, probe
    from database.session import async_engine
    await async_engine.dispose()


async def adjust(client, headers, quantity, *, sku_code='INV-BOX'):
    world=client._inventory_world
    # Read-only observer supplies the new explicit input contract; the real
    # request still authenticates and validates every identity/version itself.
    async with world.session() as db:
        row=(await db.execute(text('SELECT s.id,coalesce(st.stock_revision,1) AS revision '
            'FROM skus s LEFT JOIN inventory_stocks st ON st.sku_id=s.id WHERE s.sku_code=:c'),{'c':sku_code})).one_or_none()
        policy=await db.scalar(text('SELECT policy_version FROM staff_authority'))
    return await client.post('/api/v1/inventory/owner-adjustments', headers={**headers,'Idempotency-Key':uuid.uuid4().hex},
        json={'sellable_unit_id':str(row.id if row else uuid.uuid4()),'quantity_delta':quantity,'reason_kind':'correction',
              'reason':'native inventory safety','expected_stock_revision':row.revision if row else 1,'expected_policy_version':policy})


async def test_reserved_lower_bound_http(stock_world, inventory_http):
    client, headers, probe = inventory_http
    await stock_world.reserve(80)
    before = await stock_world.snapshot()
    assert len(before['orders']) == len(before['inventory_reservations']) == 1
    response = await adjust(client, headers, '-30')
    after = await stock_world.snapshot()
    retain('http-reserved', {'status': response.status_code, 'code': error_code(response),
                           'before': before, 'after': after, 'events': probe['events']})
    assert response.status_code == 409, 'INV_RESERVED_HTTP_MISSING_REJECTION'
    assert error_code(response) == 'STOCK_RESERVED_CONFLICT', 'INV_RESERVED_HTTP_WRONG_CATEGORY'
    assert before == after, 'INV_RESERVED_HTTP_PERSISTED_WRITE'


async def test_reserved_boundary_http_commits_before_response(stock_world, inventory_http):
    client, headers, probe = inventory_http
    await stock_world.reserve(80)
    before = await stock_world.snapshot()
    probe['events'].clear()
    response = await adjust(client, headers, '-20')
    after = await stock_world.snapshot()
    retain('http-boundary', {'status': response.status_code, 'before': before,
                            'after': after, 'events': probe['events']})
    assert response.status_code == 201
    assert await stock_world.stock() == (Decimal('80'), Decimal('80'))
    assert len(after['inventory_movements']) == len(before['inventory_movements']) + 1
    added = [json.loads(row, parse_float=Decimal) for row in after['inventory_movements']
             if row not in before['inventory_movements']]
    assert len(added) == 1 and added[0]['created_by'] == str(stock_world.actor)
    assert (added[0]['quantity'], added[0]['quantity_before'], added[0]['quantity_after']) == (-20, 100, 80)
    events = probe['events']
    commit_end = [timestamp for name, timestamp in events if name == 'manual_commit_end']
    response_start = [timestamp for name, timestamp in events if name == 'response_201']
    assert len(commit_end) == len(response_start) == 1
    assert commit_end[0] < response_start[0], 'INV_HTTP_SUCCESS_BEFORE_COMMIT'
    assert_non_stock_unchanged(before, after)


async def test_http_invalid_quantities_and_equivalent_tail_zero(stock_world, inventory_http):
    client, headers, _probe = inventory_http
    before = await stock_world.snapshot()
    observed = []
    for quantity in (0, '0.001', 'NaN', 'Infinity', '-Infinity', '10000000000', True, False,
                     '1e-1000000', '1.0000000000000000000000000000000000000001'):
        response = await adjust(client, headers, quantity)
        observed.append({'input': quantity, 'status': response.status_code, 'body': response.json()})
        assert response.status_code == 422, 'INV_HTTP_INVALID_QUANTITY_ACCEPTED'
        assert await stock_world.snapshot() == before
    retain('http-invalid-categories', observed)
    response = await adjust(client, headers, '1.2300')
    assert response.status_code == 201
    assert await stock_world.stock() == (Decimal('101.23'), Decimal('0'))


async def test_http_missing_sku_and_negative_compatibility(stock_world, inventory_http):
    client, headers, _probe = inventory_http
    before = await stock_world.snapshot()
    response = await adjust(client, headers, '-101')
    assert response.status_code == 409 and error_code(response) == 'NEGATIVE_STOCK'
    response = await adjust(client, headers, '1', sku_code='ABSENT')
    assert response.status_code == 404 and error_code(response) == 'SELLABLE_UNIT_NOT_FOUND'
    assert await stock_world.snapshot() == before


async def test_http_overflow_and_absent_stock_validation(stock_world, inventory_http):
    client, headers, _probe = inventory_http
    async with stock_world.session() as db:
        await db.execute(text('UPDATE inventory_stocks SET quantity_on_hand=9999999999.99'))
    before = await stock_world.snapshot()
    response = await adjust(client, headers, '0.01')
    assert response.status_code == 422 and error_code(response) == 'INVALID_ADJUSTMENT_QUANTITY'
    assert await stock_world.snapshot() == before
    async with stock_world.session() as db:
        await db.execute(text('DELETE FROM inventory_stocks WHERE sku_id=:id'), {'id': stock_world.sku})
    before = await stock_world.snapshot()
    assert before['inventory_stocks'] == []
    response = await adjust(client, headers, '0.001')
    assert response.status_code == 422
    assert await stock_world.snapshot() == before


async def test_native_permission_denial(stock_world, inventory_http):
    from crud.user import create_user
    client, _headers, _probe = inventory_http
    email = uuid.uuid4().hex + '@example.com'
    password = secrets.token_urlsafe(32)
    async with stock_world.session() as db:
        await create_user(db, email=email, password=password, full_name='No permission')
    denied = await login(client, stock_world, email=email, password=password)
    before = await stock_world.snapshot()
    response = await adjust(client, denied, '-1')
    assert response.status_code == 403, 'INV_NATIVE_PERMISSION_NOT_ENFORCED'
    assert await stock_world.snapshot() == before


async def test_http_tenant_same_and_different_sku_isolation(stock_world, inventory_http):
    client, headers, _probe = inventory_http
    other = StockWorld()
    try:
        await other.initialize()
        await other.reserve(80)
        before = await other.snapshot()
        response = await adjust(client, headers, '-1')
        assert response.status_code == 201
        assert await other.snapshot() == before
        async with other.session() as db:
            await db.execute(text("UPDATE skus SET sku_code='ONLY-IN-B' WHERE id=:id"), {'id': other.sku})
        before = await other.snapshot()
        response = await adjust(client, headers, '-1', sku_code='ONLY-IN-B')
        assert response.status_code == 404 and error_code(response) == 'SELLABLE_UNIT_NOT_FOUND'
        assert await other.snapshot() == before
    finally:
        if hasattr(other, 'engine'):
            await other.engine.dispose()


@pytest.mark.parametrize('fault', ['fail_movement', 'fail_commit'])
async def test_http_failures_never_send_success_and_roll_back(stock_world, inventory_http, fault):
    client, headers, probe = inventory_http
    await stock_world.reserve(80)
    before = await stock_world.snapshot()
    probe['events'].clear()
    probe[fault] = True
    response = await adjust(client, headers, '1')
    probe[fault] = False
    after = await stock_world.snapshot()
    retain('http-' + fault, {'status': response.status_code, 'events': probe['events'],
                            'before': before, 'after': after})
    assert response.status_code == 500
    assert any(name == 'manual_flush_end' for name, _ in probe['events'])
    if fault == 'fail_commit':
        assert any(name == 'manual_commit_injected_failure' for name, _ in probe['events'])
    else:
        assert any(name == 'manual_movement_injected_failure' for name, _ in probe['events'])
    assert not any(name.startswith('response_2') for name, _ in probe['events']), 'INV_FAILURE_SENT_2XX'
    assert before == after, 'INV_HTTP_FAILURE_PARTIAL_WRITE'
