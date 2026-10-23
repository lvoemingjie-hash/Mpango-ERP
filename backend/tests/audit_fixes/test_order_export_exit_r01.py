"""R01: real ASGI exits, PG lifecycle, and a subsequent foreign tenant request."""
import asyncio
from contextlib import asynccontextmanager
import csv
import gc
import io
import os
import warnings
from uuid import uuid4

import anyio
import asyncpg
import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import SAWarning

from tests.audit_fixes.support import economic_facts, full_world, retain

pytestmark = pytest.mark.asyncio(loop_scope='session')


def leaves(exc):
    if isinstance(exc, BaseExceptionGroup):
        return [leaf for child in exc.exceptions for leaf in leaves(child)]
    return [exc]


async def activity():
    db = await asyncpg.connect(os.environ['AUDIT_FINITE_APP_URL'])
    try:
        return [dict(row) for row in await db.fetch(
            'SELECT pid,state,xact_start IS NOT NULL AS transaction_open FROM pg_stat_activity '
            'WHERE usename=current_user AND datname=current_database() AND pid<>pg_backend_pid() ORDER BY pid')]
    finally:
        await db.close()


async def seed(w, endpoint):
    if endpoint == 'orders':
        await w.sql("INSERT INTO orders(wholesaler_id,retailer_id,status,total_amount,currency_snapshot,created_at) "
            "SELECT :w,:r,'draft',0,'KES',now()+n*interval '1 microsecond' FROM generate_series(1,501) n", {'w': w.a, 'r': w.retailer})
        expected = {str(r['id']) for r in await w.sql('SELECT id FROM orders')}
        async with w.foreign.session() as db:
            foreign = (await db.execute(text("INSERT INTO orders(wholesaler_id,retailer_id,status,total_amount,currency_snapshot) "
                "VALUES (:w,:r,'draft',0,'KES') RETURNING id"),
                {'w': w.b, 'r': w.foreign.retailer})).scalar_one()
    else:
        product = (await w.sql('SELECT catalog_product_id FROM skus WHERE id=:s', {'s': w.stock_world.sku}))[0]['catalog_product_id']
        prefix = 'R01-' + uuid4().hex + '-'
        await w.sql("INSERT INTO skus(sku_code,name,unit,is_active,is_deleted,catalog_product_id,package_quantity,base_price) "
            "SELECT :prefix || n::text,'R01 stock','piece',true,false,:p,1,1 FROM generate_series(1,501) n",
            {'prefix': prefix, 'p': product})
        await w.sql("INSERT INTO inventory_stocks(sku_id,quantity_on_hand,quantity_reserved,is_deleted,created_at) "
            "SELECT id,10,0,false,now()+row_number() OVER (ORDER BY id)*interval '1 microsecond' "
            "FROM skus WHERE sku_code LIKE :pattern", {'pattern': prefix + '%'})
        expected = {str(r['id']) for r in await w.sql('SELECT id FROM inventory_stocks')}
        async with w.foreign.session() as db:
            foreign = (await db.execute(text('SELECT id FROM inventory_stocks WHERE sku_id=:s'),
                {'s': w.foreign.sku})).scalar_one()
    assert len(expected) > 500
    return expected, str(foreign)


@pytest.mark.parametrize('endpoint,finish', [
    ('orders', 'eof'), ('orders', 'sql_error'), ('orders', 'header_cancel'), ('orders', 'data_cancel'),
    ('inventory', 'eof'), ('inventory', 'sql_error'), ('inventory', 'header_cancel'), ('inventory', 'data_cancel'),
], ids=['orders-eof', 'orders-sql-error', 'orders-header-cancel', 'orders-data-cancel',
        'inventory-eof', 'inventory-sql-error', 'inventory-header-cancel', 'inventory-data-cancel'])
async def test_real_asgi_export_exit(endpoint, finish, monkeypatch, request):
    import database.session as sessions
    from core.security import create_contextual_token
    from db.tenant_filter import get_current_tenant_id, get_current_tenant_schema

    async with full_world() as w:
        expected, foreign_id = await seed(w, endpoint)
        before = await economic_facts(w, 'R01-before-' + endpoint + '-' + finish)
        foreign_before = await w.foreign.snapshot()
        before_activity = await activity()
        original = sessions.get_tenant_db
        primary, operations, pool, batches = [], [], [], []
        phase = {'name': 'primary'}
        injected = []

        async def observed(schema):
            async with asynccontextmanager(original)(schema) as db:
                row = {'session_id': id(db), 'schema': schema, 'close_completed': False, 'operations': []}
                if phase['name'] == 'primary':
                    primary.append(row)
                for operation in ('commit', 'rollback', 'close'):
                    bound = getattr(db, operation)

                    async def instrumented(bound=bound, operation=operation, row=row):
                        row['operations'].append({'operation': operation, 'stage': 'started'})
                        try:
                            result = await bound()
                        except BaseException as exc:
                            row['operations'].append({'operation': operation, 'stage': 'interrupted', 'type': type(exc).__name__})
                            raise
                        row['operations'].append({'operation': operation, 'stage': 'completed'})
                        if operation == 'close':
                            row['close_completed'] = True
                        return result

                    monkeypatch.setattr(db, operation, instrumented)
                yield db

        def checkout(connection, record, _proxy):
            driver = getattr(connection, 'driver_connection', None)
            pool.append({'phase': phase['name'], 'event': 'checkout', 'record': id(record),
                'pid': driver.get_server_pid() if driver else None})

        def checkin(_connection, record):
            pool.append({'phase': phase['name'], 'event': 'checkin', 'record': id(record)})

        def reset(_connection, record, state):
            pool.append({'phase': phase['name'], 'event': 'reset', 'record': id(record),
                'asyncio_safe': state.asyncio_safe, 'terminate_only': state.terminate_only})

        def invalidate(_connection, record, error):
            pool.append({'phase': phase['name'], 'event': 'invalidate', 'record': id(record), 'type': type(error).__name__})

        def before_cursor(_connection, cursor, statement, parameters, _context, _many):
            target = 'FROM orders' if endpoint == 'orders' else 'FROM inventory_stocks'
            if phase['name'] == 'primary' and target in statement:
                batches.append({'parameters': repr(parameters), 'sql_sha256': __import__('hashlib').sha256(statement.encode()).hexdigest()})
                if finish == 'sql_error' and not injected:
                    try:
                        # Fault is raised by the real PG cursor on this same transaction.
                        cursor.execute('SELECT 1/0')
                    except BaseException as exc:
                        injected.append(exc)
                        raise

        def after_cursor(_connection, _cursor, statement, _parameters, _context, _many):
            if statement.strip() == 'SET search_path TO public':
                operations.append({'phase': phase['name'], 'event': 'reset_search_path_sql_completed'})

        listeners = [('checkout', checkout), ('checkin', checkin), ('reset', reset),
            ('invalidate', invalidate), ('before_cursor_execute', before_cursor), ('after_cursor_execute', after_cursor)]
        monkeypatch.setattr(sessions, 'get_tenant_db', observed)
        for name, callback in listeners:
            event.listen(sessions.async_engine.sync_engine, name, callback)

        statuses, chunks = [], []
        disconnected = asyncio.Event()
        transport_error = OSError('R01-TASK-DISCONNECTED-TRANSPORT')
        sent = False
        completed = False
        observed_error = None
        context_before = (get_current_tenant_id(), get_current_tenant_schema())
        receipt = {'nodeid': request.node.nodeid, 'batch': os.environ.get('R01_BATCH'),
            'endpoint': endpoint, 'finish': finish, 'seed_count': len(expected), 'statuses': statuses,
            'owned_sessions': primary, 'pool': pool, 'batches': batches, 'operations': operations,
            'before_activity': before_activity}

        async def receive():
            nonlocal sent
            if not sent:
                sent = True
                return {'type': 'http.request', 'body': b'', 'more_body': False}
            await disconnected.wait()
            return {'type': 'http.disconnect'}

        async def send(message):
            nonlocal completed
            if message['type'] == 'http.response.start':
                statuses.append(message['status'])
            elif message['type'] == 'http.response.body':
                body = message.get('body', b'')
                chunks.append(body)
                if not message.get('more_body', False):
                    completed = True
                received = b''.join(chunks)
                trigger = (finish == 'header_cancel' and b'\n' in received) or (
                    finish == 'data_cancel' and received.count(b'\n') >= 2)
                if trigger:
                    disconnected.set()
                    raise transport_error

        path = '/api/v1/' + endpoint + '/export'
        scope = {'type': 'http', 'asgi': {'version': '3.0', 'spec_version': '2.0'}, 'http_version': '1.1',
            'method': 'GET', 'scheme': 'http', 'path': path, 'raw_path': path.encode(), 'query_string': b'',
            'root_path': '', 'client': ('127.0.0.1', 10002), 'server': ('audit', 80),
            'headers': [(b'host', b'audit'), (b'authorization', w.client.headers['Authorization'].encode())]}
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter('always', SAWarning)
                try:
                    await asyncio.wait_for(w.app(scope, receive, send), timeout=30)
                except BaseException as exc:
                    observed_error = exc
                receipt['context_after_primary'] = [get_current_tenant_id(), get_current_tenant_schema()]
                gc.collect()
                await anyio.lowlevel.checkpoint()
                await anyio.lowlevel.checkpoint()
                receipt['leak_warning_count'] = sum('non-checked-in connection' in str(item.message) for item in caught)
            for item in caught:
                if 'non-checked-in connection' not in str(item.message):
                    warnings.warn_explicit(item.message, item.category, item.filename, item.lineno)

            receipt.update(complete_body=completed, disconnected=disconnected.is_set(),
                received_lines=b''.join(chunks).count(b'\n'), error_types=[type(e).__name__ for e in leaves(observed_error)] if observed_error else [])
            phase['name'] = 'followup'
            token = create_contextual_token(str(w.foreign.actor), ['admin'], str(w.b), w.foreign.schema)
            foreign_stock_ids = set()
            async with w.foreign.session() as db:
                foreign_stock_ids = {str(x) for x in (await db.execute(text('SELECT id FROM inventory_stocks'))).scalars()}
            followups = []
            for _ in range(2):
                response = await w.client.get('/api/v1/inventory/export', headers={'Authorization': 'Bearer ' + token})
                body = list(csv.reader(io.StringIO(response.text))) if response.status_code == 200 else []
                ids = {row[0] for row in body[1:]}
                followups.append({'status': response.status_code, 'exact_foreign_ids': ids == foreign_stock_ids})
            receipt['followups'] = followups
            receipt['after_activity'] = await activity()
            receipt['checkedout_after'] = sessions.async_engine.sync_engine.pool.checkedout()
            receipt['economic_unchanged'] = await economic_facts(w, 'R01-after-' + endpoint + '-' + finish) == before
            receipt['foreign_economic_unchanged'] = await w.foreign.snapshot() == foreign_before
            assert statuses == [200], 'R01-REAL-AUTHENTICATED-ROUTE-MUST-BE-REACHED'
            if finish == 'eof':
                rows = list(csv.reader(io.StringIO(b''.join(chunks).decode())))
                assert observed_error is None and completed
                assert {row[0] for row in rows[1:]} == expected and foreign_id not in {row[0] for row in rows[1:]}
                assert len(batches) >= 2, 'R01-NORMAL-EOF-MUST-READ-TWO-BATCHES'
            elif finish == 'sql_error':
                # BaseHTTPMiddleware can terminate its proxy body before raising
                # the original upstream error. A final frame is not data success.
                assert len(injected) == 1 and observed_error is not None
                assert getattr(injected[0], 'sqlstate', None) == '22012'
                assert any(e is injected[0] or getattr(e, 'orig', None) is injected[0] for e in leaves(observed_error)), 'R01-ORIGINAL-SQL-ERROR-MUST-PROPAGATE'
                assert receipt['received_lines'] == 1, 'R01-SQL-FAULT-MUST-NOT-RETURN-FULL-DATA'
            else:
                assert disconnected.is_set() and not completed
                assert observed_error is not None and any(e is transport_error for e in leaves(observed_error)), 'R01-DISCONNECT-MUST-NOT-LOOK-LIKE-COMPLETE-SUCCESS'
                if finish == 'header_cancel':
                    assert receipt['received_lines'] == 1, 'R01-HEADER-CANCEL-MUST-PRECEDE-DATA'
                else:
                    assert 2 <= receipt['received_lines'] < len(expected) + 1, 'R01-DATA-CANCEL-MUST-PRECEDE-EOF'
            assert len(primary) == 1 and primary[0]['close_completed'], 'R01-OWNED-SESSION-CLOSE-MUST-COMPLETE'
            assert not receipt['leak_warning_count'], 'R01-NO-GC-OF-UNRETURNED-CONNECTION'
            assert all(r.get('asyncio_safe', True) for r in pool), 'R01-POOL-RETURN-MUST-BE-ASYNCIO-SAFE'
            assert receipt['checkedout_after'] == 0, 'R01-NO-CHECKED-OUT-CONNECTION-LEFT'
            assert not any(r['transaction_open'] for r in receipt['after_activity']), 'R01-NO-LINGERING-TRANSACTION'
            assert tuple(receipt['context_after_primary']) == context_before, 'R01-TENANT-CONTEXT-MUST-BE-RESTORED'
            assert all(r['status'] == 200 and r['exact_foreign_ids'] for r in followups), 'R01-NEXT-TENANT-MUST-REMAIN-ISOLATED-AND-AVAILABLE'
            assert receipt['economic_unchanged'] and receipt['foreign_economic_unchanged'], 'R01-EXPORT-MUST-HAVE-ZERO-ECONOMIC-WRITES'
        finally:
            retain('R01-' + endpoint + '-' + finish, receipt)
            for name, callback in listeners:
                event.remove(sessions.async_engine.sync_engine, name, callback)
