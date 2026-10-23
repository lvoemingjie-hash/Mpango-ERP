"""Four-gap controls on native task tenants, real JWT middleware and PG rows."""
from contextlib import asynccontextmanager
import asyncio
import csv
import gc
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import io
import warnings
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, text

from tests.audit_fixes.support import create_confirmed, economic_facts, full_world, retain

pytestmark = pytest.mark.asyncio(loop_scope='session')


@pytest.fixture
def inventory_pool_lifecycle():
    from database.session import async_engine
    from sqlalchemy.exc import SAWarning

    resets, invalidations = [], []

    def record_reset(_connection, _record, state):
        resets.append({'asyncio_safe': state.asyncio_safe, 'terminate_only': state.terminate_only})

    def record_invalidate(_connection, _record, error):
        invalidations.append(type(error).__name__)

    event.listen(async_engine.sync_engine, 'reset', record_reset)
    event.listen(async_engine.sync_engine, 'invalidate', record_invalidate)
    try:
        with warnings.catch_warnings(record=True) as observed:
            warnings.simplefilter('always', SAWarning)
            # Requested before monkeypatch so its references are released first.
            yield
            gc.collect()
    finally:
        event.remove(async_engine.sync_engine, 'reset', record_reset)
        event.remove(async_engine.sync_engine, 'invalidate', record_invalidate)
    leaked = [item for item in observed if 'non-checked-in connection' in str(item.message)]
    for item in observed:
        if item not in leaked:
            warnings.warn_explicit(item.message, item.category, item.filename, item.lineno)
    retain('B02-pool-return', {'resets': resets, 'invalidations': invalidations,
                             'unreturned_connection_warnings': len(leaked)})
    assert not leaked and not invalidations and all(row['asyncio_safe'] for row in resets), 'B02-NO-GC-OF-UNRETURNED-CONNECTION'


def error_code(response):
    body = response.json()
    return body.get('code') or body.get('detail', {}).get('code') or body.get('error', {}).get('code')


async def vectors(w, label):
    result = {'economic': await economic_facts(w, label + '-economic')}
    for table, columns in (
        ('users', 'id,is_active,is_deleted'),
        ('roles', 'id,name,is_deleted'),
        ('user_roles', 'user_id,role_id'),
        ('payment_declarations', '*'),
    ):
        result[table] = [r['raw'] for r in await w.sql(
            f'SELECT row_to_json(r)::text AS raw FROM (SELECT {columns} FROM {table} ORDER BY 1,2) r')]
    retain(label + '-identity-and-economic', result)
    return result


async def cached_refresh(w):
    login = await w.client.post('/api/v1/auth/login', headers={'Authorization': ''},
        json={'email': w.email, 'password': w.password})
    assert login.status_code == 200, login.text
    body = {'refresh_token': login.json()['data']['refresh_token']}
    headers = {'Authorization': '', 'X-Idempotency-Key': str(uuid4())}
    first = await w.client.post('/api/v1/auth/refresh', headers=headers, json=body)
    assert first.status_code == 200, first.text
    replay = await w.client.post('/api/v1/auth/refresh', headers=headers, json=body)
    assert replay.status_code == 200 and replay.headers.get('X-Idempotency-Replayed') == 'true'
    assert replay.json() == first.json(), 'B01-POSITIVE-MUST-REALLY-REPLAY-CACHED-TOKENS'
    return body, headers


@pytest.mark.parametrize('change', ['inactive', 'deleted', 'platform_role_removed'])
async def test_cached_body_refresh_rechecks_current_identity(change):
    async with full_world() as w:
        await w.sql("UPDATE roles SET name='super_admin' WHERE id=:r", {'r': w.rid})
        body, headers = await cached_refresh(w)
        if change == 'inactive':
            await w.sql('UPDATE users SET is_active=false WHERE id=:u', {'u': w.uid})
        elif change == 'deleted':
            await w.sql('UPDATE users SET is_deleted=true WHERE id=:u', {'u': w.uid})
        else:
            await w.sql('DELETE FROM user_roles WHERE user_id=:u', {'u': w.uid})
        before = await vectors(w, 'B01-before-revoked-replay-' + change)
        denied = await w.client.post('/api/v1/auth/refresh', headers=headers, json=body)
        assert denied.status_code == 401, 'B01-REVOKED-IDENTITY-MUST-NOT-RETURN-CACHED-TOKEN-PACKAGE'
        assert error_code(denied) in ('IDENTITY_REVOKED', 'PLATFORM_ROLE_REVOKED')
        assert denied.headers.get('X-Idempotency-Replayed') != 'true'
        assert 'access_token' not in denied.text and 'refresh_token' not in denied.text
        assert await vectors(w, 'B01-after-revoked-replay-' + change) == before


async def test_cached_refresh_keeps_ordinary_multitenant_identity_positive():
    from core.security import hash_password
    from jose import jwt
    async with full_world() as w:
        async with w.foreign.session() as db:
            await db.execute(text('INSERT INTO users(id,email,password_hash,is_active) VALUES (:u,:e,:p,true)'),
                {'u': uuid4(), 'e': w.email, 'p': hash_password(w.password)})
            await db.execute(text("INSERT INTO user_roles(user_id,role_id) SELECT u.id,r.id FROM users u CROSS JOIN roles r WHERE u.email=:e AND r.name='admin'"), {'e': w.email})
        body, headers = await cached_refresh(w)
        response = await w.client.post('/api/v1/auth/refresh', headers=headers, json=body)
        claims = jwt.get_unverified_claims(response.json()['data']['access_token'])
        assert set(claims['tmap']) == {str(w.a), str(w.b)}
        assert 'super_admin' not in claims['roles'], 'B01-ORDINARY-IDENTITY-MUST-NOT-REQUIRE-PLATFORM-ROLE'


async def seed_many_stocks(w):
    product = (await w.sql('SELECT catalog_product_id FROM skus WHERE id=:s',
                          {'s': w.stock_world.sku}))[0]['catalog_product_id']
    await w.sql("INSERT INTO skus(sku_code,name,unit,is_active,is_deleted,catalog_product_id,package_quantity,base_price) "
        "SELECT :prefix || n::text,'Stream item','piece',true,false,:product,1,1 FROM generate_series(1,501) n",
        {'prefix': 'B02-' + w.a.hex + '-', 'product': product})
    await w.sql("INSERT INTO inventory_stocks(sku_id,quantity_on_hand,quantity_reserved,is_deleted) "
        "SELECT id,10,0,false FROM skus WHERE sku_code LIKE :pattern",
        {'pattern': 'B02-' + w.a.hex + '-%'})


async def test_inventory_csv_full_app_two_batches_and_foreign_sentinel(inventory_pool_lifecycle):
    async with full_world() as w:
        await seed_many_stocks(w)
        async with w.foreign.session() as db:
            foreign_stock = (await db.execute(text('SELECT id FROM inventory_stocks WHERE sku_id=:s'),
                {'s': w.foreign.sku})).scalar_one()
        expected_ids = {str(r['id']) for r in await w.sql('SELECT id FROM inventory_stocks')}
        before = await vectors(w, 'B02-before-native-inventory-export')
        response = await w.client.get('/api/v1/inventory/export')
        assert response.status_code == 200, response.text
        rows = list(csv.reader(io.StringIO(response.text)))
        assert len(rows) == 503, 'B02-CSV-MUST-CONSUME-MORE-THAN-ONE-500-ROW-BATCH'
        assert rows[0][0] == 'Stock ID'
        assert {r[0] for r in rows[1:]} == expected_ids, 'B02-CSV-MUST-CONTAIN-EXACTLY-THIS-TENANTS-STOCK-IDS'
        assert str(foreign_stock) not in {r[0] for r in rows[1:]}, 'B02-FOREIGN-STOCK-MUST-NOT-LEAK'
        assert await vectors(w, 'B02-after-native-inventory-export') == before


@pytest.mark.parametrize('finish', ['complete', 'sql_error', 'disconnect'])
async def test_inventory_stream_owns_session_after_request_closes(inventory_pool_lifecycle, monkeypatch, finish):
    import database.session as sessions
    from api.v1.data_export import export_inventory_csv
    from core.security import decode_token
    from db.tenant_filter import set_current_tenant, reset_current_tenant
    async with full_world() as w:
        opened, closed = [], []
        stock_id = (await w.sql('SELECT id FROM inventory_stocks WHERE sku_id=:s',
                               {'s': w.stock_world.sku}))[0]['id']
        original = sessions.get_tenant_db

        async def observed(schema):
            async with asynccontextmanager(original)(schema) as real_db:
                opened.append(id(real_db))
                close = real_db.close

                async def record_completed_close():
                    await close()
                    if id(real_db) not in closed:
                        closed.append(id(real_db))

                monkeypatch.setattr(real_db, 'close', record_completed_close)
                yield real_db

        monkeypatch.setattr(sessions, 'get_tenant_db', observed)
        token = decode_token(w.client.headers['Authorization'].split(' ', 1)[1])
        scope = set_current_tenant(tenant_id=str(w.a), tenant_schema=w.schema)
        try:
            async with asynccontextmanager(original)(w.schema) as request_db:
                response = await export_inventory_csv(format='csv', token=token, db=request_db)
        finally:
            reset_current_tenant(*scope)
        iterator = response.body_iterator
        assert 'Stock ID' in await anext(iterator)

        def inject(_conn, _cursor, statement, _params, _context, _many):
            if 'FROM inventory_stocks' in statement:
                raise RuntimeError('B02-TASK-OWNED-STREAM-SQL-FAULT')

        try:
            if finish == 'sql_error':
                event.listen(sessions.async_engine.sync_engine, 'before_cursor_execute', inject)
                with pytest.raises(RuntimeError, match='B02-TASK-OWNED-STREAM-SQL-FAULT'):
                    await anext(iterator)
            elif finish == 'disconnect':
                assert str(stock_id) in await anext(iterator)
                await iterator.aclose()
            else:
                body = ''.join([chunk async for chunk in iterator])
                assert str(stock_id) in body
        finally:
            if finish == 'sql_error':
                event.remove(sessions.async_engine.sync_engine, 'before_cursor_execute', inject)
            await iterator.aclose()
            await request_db.close()
        retain('B02-real-session-lifecycle-' + finish, {'opened': opened, 'closed': closed})
        assert len(opened) == 1 and closed == opened, 'B02-STREAM-MUST-OWN-AND-CLOSE-ITS-REAL-TENANT-SESSION'


async def test_inventory_full_asgi_disconnect_completes_owned_session_close(inventory_pool_lifecycle, monkeypatch):
    import database.session as sessions
    async with full_world() as w:
        opened, closed, chunks, statuses = [], [], [], []
        disconnected = asyncio.Event()
        original = sessions.get_tenant_db
        stock_id = str((await w.sql('SELECT id FROM inventory_stocks WHERE sku_id=:s',
                                   {'s': w.stock_world.sku}))[0]['id'])

        async def observed(schema):
            async with asynccontextmanager(original)(schema) as real_db:
                opened.append(id(real_db))
                close = real_db.close

                async def record_completed_close():
                    await close()
                    if id(real_db) not in closed:
                        closed.append(id(real_db))

                monkeypatch.setattr(real_db, 'close', record_completed_close)
                yield real_db

        monkeypatch.setattr(sessions, 'get_tenant_db', observed)
        request_sent = False

        async def receive():
            nonlocal request_sent
            if not request_sent:
                request_sent = True
                return {'type': 'http.request', 'body': b'', 'more_body': False}
            await disconnected.wait()
            return {'type': 'http.disconnect'}

        async def send(message):
            if message['type'] == 'http.response.start':
                statuses.append(message['status'])
            elif message['type'] == 'http.response.body':
                chunks.append(message.get('body', b''))
                if stock_id.encode() in message.get('body', b''):
                    disconnected.set()
                    # A closed server transport raises on send. Waiting for
                    # receive alone cannot release BaseHTTPMiddleware's outer
                    # proxy send, which has no disconnect listener itself.
                    raise OSError('B02-SYNTHETIC-DISCONNECTED-TRANSPORT')

        scope = {'type': 'http', 'asgi': {'version': '3.0', 'spec_version': '2.0'},
            'http_version': '1.1', 'method': 'GET', 'scheme': 'http',
            'path': '/api/v1/inventory/export', 'raw_path': b'/api/v1/inventory/export',
            'query_string': b'', 'root_path': '', 'client': ('127.0.0.1', 10001),
            'server': ('audit', 80), 'headers': [(b'host', b'audit'),
                (b'authorization', w.client.headers['Authorization'].encode())]}
        with pytest.raises(OSError, match='B02-SYNTHETIC-DISCONNECTED-TRANSPORT'):
            await asyncio.wait_for(w.app(scope, receive, send), timeout=15)
        retain('B02-full-asgi-disconnect', {'statuses': statuses, 'opened': opened,
            'completed_close': closed, 'disconnect_observed': disconnected.is_set(),
            'received_stock_id': stock_id})
        assert statuses == [200] and disconnected.is_set()
        assert len(opened) == 1 and closed == opened, 'B02-ASGI-DISCONNECT-MUST-COMPLETE-REAL-SESSION-CLOSE'


@pytest.mark.parametrize('window', ['today', 'past', 'future', 'before_midnight', 'after_midnight_old', 'after_midnight_spanning'])
async def test_statement_period_contains_controlled_eat_today(monkeypatch, window):
    import services.print_service as printing
    real_today = (datetime.now(timezone.utc) + timedelta(hours=3)).date()
    moment = datetime.now(timezone.utc)
    start = end = real_today
    expected = 200
    if window == 'past':
        start = end = real_today - timedelta(days=1)
        expected = 409
    elif window == 'future':
        start = end = real_today + timedelta(days=1)
        expected = 409
    elif window == 'before_midnight':
        moment = datetime.combine(real_today, datetime.min.time(), timezone.utc) + timedelta(hours=20, minutes=59, seconds=59)
    elif window.startswith('after_midnight'):
        moment = datetime.combine(real_today, datetime.min.time(), timezone.utc) + timedelta(hours=21)
        if window == 'after_midnight_old':
            expected = 409
        else:
            end += timedelta(days=1)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return moment.astimezone(tz) if tz else moment.replace(tzinfo=None)

    async with full_world() as w:
        await create_confirmed(w)
        before = await vectors(w, 'B04-before-' + window)
        monkeypatch.setattr(printing, 'datetime', Clock)
        response = await w.client.get('/api/v1/statements/print', params={
            'retailer_id': str(w.retailer), 'from': start.isoformat(), 'to': end.isoformat()})
        assert response.status_code == expected, 'B04-PERIOD-MUST-CONTAIN-CURRENT-EAT-DATE'
        if expected == 409:
            assert error_code(response) == 'STATEMENT_HISTORY_UNSUPPORTED'
        else:
            data = response.json()['data']
            assert Decimal(str(data['opening_balance'])) + Decimal(str(data['charge_total'])) - Decimal(str(data['collection_total'])) == Decimal(str(data['closing_balance'])) == 100
        assert await vectors(w, 'B04-after-' + window) == before


async def test_two_real_orders_conflicting_key_and_raw_vectors():
    async with full_world() as w:
        await w.sql('UPDATE inventory_stocks SET quantity_on_hand=300 WHERE sku_id=:s',
                    {'s': w.stock_world.sku})
        first, second = await create_confirmed(w), await create_confirmed(w)
        key = str(uuid4())
        accepted = await w.client.post(f'/api/v1/orders/{first}/pay',
            headers={'X-Idempotency-Key': key}, json={'amount': '40', 'method': 'cash'})
        assert accepted.status_code == 200, accepted.text
        before = await vectors(w, 'two-order-before-conflict')
        for oid, amount in ((first, '41'), (second, '40')):
            refused = await w.client.post(f'/api/v1/orders/{oid}/pay',
                headers={'X-Idempotency-Key': key}, json={'amount': amount, 'method': 'cash'})
            assert refused.status_code == 409 and error_code(refused) == 'IDEMPOTENCY_KEY_CONFLICT'
            assert await vectors(w, 'two-order-after-' + oid) == before
        rows = await w.sql('SELECT order_id,remaining_amount FROM order_credit_holds ORDER BY order_id')
        assert {str(r['order_id']): r['remaining_amount'] for r in rows} == {first: Decimal('60'), second: Decimal('100')}
