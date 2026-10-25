"""Finite real migrated-app HTTP/SQL journeys; no product permission overrides."""
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import sys
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from tests.audit_fixes.support import create_confirmed, economic_facts, full_world, retain

pytestmark = pytest.mark.asyncio(loop_scope='session')


def code(response):
    body = response.json()
    return body.get('code') or body.get('error', {}).get('code') or body.get('detail', {}).get('code')


async def views(w, oid, due):
    invoice = await w.client.get(f'/api/v1/orders/{oid}/invoice')
    assert invoice.status_code == 200, invoice.text
    assert Decimal(str(invoice.json()['data']['balance_due'])) == due, 'FINITE-INVOICE-DUE'
    summary = await w.client.get('/api/v1/finance/summary')
    assert summary.status_code == 200, summary.text
    assert Decimal(str(summary.json()['data']['outstanding_receivables'])) == due, 'FINITE-SUMMARY-DUE'
    today = (datetime.now(timezone.utc)+timedelta(hours=3)).date().isoformat()
    query = {'from': today, 'to': today}
    for route, headers, params in (
        ('/api/v1/statements/print', {}, {**query, 'retailer_id': str(w.retailer)}),
        ('/api/v1/client/statements/print', {'Authorization': 'Bearer '+w.client_token}, query)):
        response = await w.client.get(route, headers=headers, params=params)
        assert response.status_code == 200, response.text
        data = response.json()['data']
        opening, charges, collected, closing = (Decimal(str(data[k])) for k in
            ('opening_balance', 'charge_total', 'collection_total', 'closing_balance'))
        assert opening+charges-collected == closing == due, 'FINITE-STATEMENT-ACCOUNT-IDENTITY'
        assert charges == 100 and collected == 100-due, 'FINITE-REAL-CHARGE-AND-RECEIPTS'
        assert data['currency'] == w.currency
    rows = await w.sql('SELECT outstanding_balance FROM public.wholesaler_retailer_bindings WHERE wholesaler_id=:w AND retailer_id=:r',
                      {'w': w.a, 'r': w.retailer})
    assert rows[0]['outstanding_balance'] == due, 'FINITE-BINDING-CACHE'


@pytest.mark.parametrize('country', ['UG', 'KE'])
async def test_product_quote_confirm_receipts_and_statement(country):
    async with full_world(country) as w:
        oid = await create_confirmed(w)
        assert not (await w.sql('SELECT id FROM ledger_entries')), 'FINITE-CONFIRM-ZERO-LEDGER'
        await views(w, oid, Decimal('100'))
        for value, due in (('40', Decimal('60')), ('60', Decimal('0'))):
            key = str(uuid4())
            response = await w.client.post(f'/api/v1/orders/{oid}/pay',
                headers={'X-Idempotency-Key': key}, json={'amount': value, 'method': 'cash'})
            assert response.status_code == 200, response.text
            await views(w, oid, due)
            before = await economic_facts(w, 'cash-before-replay')
            replay = await w.client.post(f'/api/v1/orders/{oid}/pay',
                headers={'X-Idempotency-Key': key}, json={'amount': value, 'method': 'cash'})
            assert replay.status_code == 200, replay.text
            assert await economic_facts(w, 'cash-after-replay') == before, 'FINITE-REPLAY-ZERO-ECONOMIC-EFFECT'
        cash = await w.sql("SELECT amount,reference_id FROM ledger_entries WHERE account_type='cash' ORDER BY amount")
        assert [row['amount'] for row in cash] == [Decimal('40'), Decimal('60')]
        assert len({row['reference_id'] for row in cash}) == 2, 'FINITE-EACH-PAYMENT-POSTED-ONCE'


async def declare(w, oid, value, key=None):
    response = await w.client.post(f'/api/v1/client/orders/{oid}/declare',
        headers={'Authorization': 'Bearer '+w.client_token,
                 'X-Declaration-Idempotency-Key': key or str(uuid4())},
        json={'declared_amount': value, 'method': 'cash'})
    assert response.status_code == 201, response.text
    return response.json()['data']['id']


async def test_credit_fulfill_customer_declaration_cashier_receipt():
    async with full_world() as w:
        oid = await create_confirmed(w)
        response = await w.client.post(f'/api/v1/orders/{oid}/pay', headers={'X-Idempotency-Key': str(uuid4())},
            json={'amount': '100', 'method': 'credit'})
        assert response.status_code == 200, response.text
        response = await w.client.post(f'/api/v1/orders/{oid}/fulfill')
        assert response.status_code == 200, response.text
        await views(w, oid, Decimal('100'))
        stock = (await economic_facts(w, 'fulfilled-stock'))['inventory_stocks']
        for value, due in (('40', Decimal('60')), ('60', Decimal('0'))):
            before = await economic_facts(w, 'before-declare')
            did = await declare(w, oid, value)
            assert await economic_facts(w, 'after-declare') == before, 'FINITE-DECLARATION-NOT-A-RECEIPT'
            response = await w.client.post(f'/api/v1/declarations/{did}/confirm')
            assert response.status_code == 200, response.text
            first = response.json()['data']
            assert first['order_status'] == 'fulfilled', 'FINITE-COLLECTION-PRESERVES-FULFILLED'
            facts = await economic_facts(w, 'before-confirm-replay')
            replay = await w.client.post(f'/api/v1/declarations/{did}/confirm')
            assert replay.status_code == 200 and replay.json()['data']['receipt_number'] == first['receipt_number']
            assert await economic_facts(w, 'after-confirm-replay') == facts
            receipt = await w.client.get(f'/api/v1/client/declarations/{did}/receipt',
                headers={'Authorization': 'Bearer '+w.client_token})
            assert receipt.status_code == 200, receipt.text
            assert Decimal(receipt.json()['data']['confirmed_amount']) == Decimal(value)
            assert facts['inventory_stocks'] == stock, 'FINITE-COLLECTION-NEVER-CHANGES-STOCK'
            await views(w, oid, due)
            if due == Decimal('60'):
                excessive = await declare(w, oid, '61')
                before_excessive = await economic_facts(w, 'before-positive-exposure-overpayment')
                refused = await w.client.post(f'/api/v1/declarations/{excessive}/confirm')
                assert refused.status_code == 400 and code(refused) == 'PAYMENT_EXCEEDS_REMAINING', refused.text
                assert await economic_facts(w, 'after-positive-exposure-overpayment') == before_excessive
        did = await declare(w, oid, '1')
        before = await economic_facts(w, 'before-overpayment-confirm')
        denied = await w.client.post(f'/api/v1/declarations/{did}/confirm')
        assert denied.status_code == 409 and code(denied) == 'ORDER_ALREADY_PAID', denied.text
        assert await economic_facts(w, 'after-overpayment-confirm') == before


@pytest.mark.parametrize('fault', ['ledger_entries', 'binding'])
async def test_payment_failure_has_exact_full_rollback(fault):
    async with full_world() as w:
        oid = await create_confirmed(w)
        before = await economic_facts(w, 'fault-before')
        # DB fault injection is confined to tables owned by this provisioned tenant.
        # Binding uses a conditional trigger in public and therefore is not installed
        # with the runtime role: a test engine listener raises at its actual UPDATE.
        from database.session import async_engine
        from sqlalchemy import event
        def fail(_conn, _cursor, statement, parameters, _context, _many):
            normalized = statement.lower().lstrip()
            target = ('insert into ledger_entries' in normalized if fault == 'ledger_entries'
                      else normalized.startswith('update public.wholesaler_retailer_bindings'))
            if target:
                retain('injected-actual-sql-boundary', {'fault': fault, 'statement': statement})
                raise RuntimeError('FINITE_SYNTHETIC_WRITE_BOUNDARY_FAILURE')
        event.listen(async_engine.sync_engine, 'before_cursor_execute', fail)
        try:
            response = await w.client.post(f'/api/v1/orders/{oid}/pay',
                headers={'X-Idempotency-Key': str(uuid4())}, json={'amount': '40', 'method': 'cash'})
            assert response.status_code == 500, response.text
        finally:
            event.remove(async_engine.sync_engine, 'before_cursor_execute', fail)
        assert await economic_facts(w, 'fault-after') == before, 'FINITE-ROLLBACK-ALL-RAW-ROWS'


async def test_same_key_different_body_and_overpay_zero_writes():
    async with full_world() as w:
        oid = await create_confirmed(w)
        key = str(uuid4())
        response = await w.client.post(f'/api/v1/orders/{oid}/pay', headers={'X-Idempotency-Key': key},
            json={'amount': '40', 'method': 'cash'})
        assert response.status_code == 200, response.text
        for amount, expected in (('41', 'IDEMPOTENCY_KEY_CONFLICT'), ('61', 'PAYMENT_EXCEEDS_REMAINING')):
            before = await economic_facts(w, 'denied-before')
            response = await w.client.post(f'/api/v1/orders/{oid}/pay',
                headers={'X-Idempotency-Key': key if amount=='41' else str(uuid4())},
                json={'amount': amount, 'method': 'cash'})
            assert response.status_code in (400, 409) and code(response) == expected, response.text
            assert await economic_facts(w, 'denied-after') == before


async def test_unsupported_historical_statement_is_explicit():
    async with full_world() as w:
        await create_confirmed(w)
        yesterday = (datetime.now(timezone.utc)-timedelta(days=1)).date().isoformat()
        response = await w.client.get('/api/v1/statements/print', params={
            'retailer_id': str(w.retailer), 'from': yesterday, 'to': yesterday})
        assert response.status_code == 409 and code(response) == 'STATEMENT_HISTORY_UNSUPPORTED', response.text
        await w.sql('UPDATE order_credit_holds SET created_by=NULL')
        today = (datetime.now(timezone.utc)+timedelta(hours=3)).date().isoformat()
        response = await w.client.get('/api/v1/statements/print', params={
            'retailer_id': str(w.retailer), 'from': today, 'to': today})
        assert response.status_code == 409 and code(response) == 'STATEMENT_HISTORY_UNSUPPORTED', response.text


async def test_multitenant_identity_login_select_and_refresh_positive():
    from core.security import hash_password
    async with full_world() as w:
        await w.foreign.engine.dispose()
        async with w.foreign.session() as db:
            await db.execute(text('INSERT INTO users(id,email,password_hash,is_active) VALUES (:u,:e,:p,true)'),
                {'u': uuid4(), 'e': w.email, 'p': hash_password(w.password)})
            await db.execute(text("INSERT INTO user_roles(user_id,role_id) SELECT u.id,r.id FROM users u CROSS JOIN roles r WHERE u.email=:e AND r.name='admin'"), {'e': w.email})
        login = await w.client.post('/api/v1/auth/login', headers={'Authorization': ''},
            json={'email': w.email, 'password': w.password})
        assert login.status_code == 200, login.text
        token = login.json()['data']['access_token']
        refresh = await w.client.post('/api/v1/auth/refresh', headers={'Authorization': ''},
            json={'refresh_token': login.json()['data']['refresh_token']})
        assert refresh.status_code == 200, refresh.text
        for tenant in (w.a, w.b):
            selected = await w.client.post('/api/v1/auth/select-tenant', headers={'Authorization': 'Bearer '+token},
                json={'tenant_id': str(tenant)})
            assert selected.status_code == 200, selected.text
            response = await w.client.get('/api/v1/wholesalers', headers={
                'Authorization': 'Bearer '+selected.json()['data']['access_token']})
            assert response.status_code == 200 and [x['id'] for x in response.json()['data']['items']] == [str(tenant)]


@pytest.mark.parametrize('change', ['inactive', 'deleted', 'role_removed'])
async def test_identity_revocation_reaches_auth_boundary_without_platform_catalog(change):
    """Additional auth proof; does NOT replace the blocked platform-list controls."""
    async with full_world() as w:
        await w.sql("UPDATE roles SET name='super_admin' WHERE id=:r", {'r': w.rid})
        login = await w.client.post('/api/v1/auth/login', headers={'Authorization': ''},
            json={'email': w.email, 'password': w.password})
        assert login.status_code == 200, login.text
        tokens = login.json()['data']
        headers = {'Authorization': 'Bearer '+tokens['access_token']}
        positive = await w.client.get('/api/v1/wholesalers', headers=headers)
        assert positive.status_code == 200, positive.text
        if change == 'inactive':
            await w.sql('UPDATE users SET is_active=false WHERE id=:u', {'u': w.uid})
        elif change == 'deleted':
            await w.sql('UPDATE users SET is_deleted=true WHERE id=:u', {'u': w.uid})
        else:
            await w.sql('DELETE FROM user_roles WHERE user_id=:u', {'u': w.uid})
        before = await economic_facts(w, 'revocation-before-refusal')
        denied = await w.client.get('/api/v1/wholesalers', headers=headers)
        assert denied.status_code == 401, denied.text
        denied = await w.client.post('/api/v1/auth/refresh', headers={'Authorization': ''},
            json={'refresh_token': tokens['refresh_token']})
        assert denied.status_code == 401, denied.text
        assert await economic_facts(w, 'revocation-after-refusal') == before


async def test_missing_token_type_business_http_is_rejected():
    from core.config import get_settings
    from core.security import create_contextual_token
    from jose import jwt
    async with full_world() as w:
        settings = get_settings()
        raw = create_contextual_token(str(w.uid), ['admin'], str(w.a), w.schema)
        payload = jwt.decode(raw, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        payload.pop('type')
        token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        response = await w.client.get('/api/v1/wholesalers', headers={'Authorization': 'Bearer '+token})
        assert response.status_code == 401, response.text


async def test_csv_client_permission_negative_and_closed_session():
    async with full_world('UG') as w:
        await create_confirmed(w)
        response = await w.client.get('/api/v1/orders/export',
            headers={'Authorization': 'Bearer '+w.client_token})
        assert response.status_code == 403
        from database.session import async_engine
        checked = async_engine.sync_engine.pool.checkedout()
        response = await w.client.get('/api/v1/orders/export')
        assert response.status_code == 200 and 'Currency' in response.text and 'UGX' in response.text
        assert async_engine.sync_engine.pool.checkedout() == checked, 'FINITE-CSV-SESSION-CLOSED'


async def test_persisted_jobs_distinct_worker_processes_and_restart():
    import main
    from core.jobs.local_queue import LocalJobQueue
    from database.reporting_session import reporting_engine
    async with full_world() as w:
        oid = await create_confirmed(w)
        response = await w.client.post(f'/api/v1/orders/{oid}/pay', headers={'X-Idempotency-Key': str(uuid4())},
            json={'amount': '40', 'method': 'cash'})
        assert response.status_code == 200, response.text
        import jobs.export_jobs  # registers the actual production handler
        main._job_queue = LocalJobQueue(max_workers=2)
        today = datetime.now(timezone.utc).date()
        ids = []
        for day in (today, today-timedelta(days=2)):
            response = await w.client.post('/api/v1/exports', json={'view': 'cash_flow_daily',
                'metrics': ['net_cash_change'], 'format': 'csv',
                'date_from': day.isoformat(), 'date_to': day.isoformat()})
            assert response.status_code == 202, response.text
            ids.append(response.json()['data']['job_id'])
        private = Path(os.environ['AUDIT_FINITE_PRIVATE'])
        async def execute(jid):
            stdout = (private / ('worker-'+jid+'.stdout')).open('xb')
            stderr = (private / ('worker-'+jid+'.stderr')).open('xb')
            try:
                process = await asyncio.create_subprocess_exec(sys.executable, '-B', '-m',
                    'tests.audit_fixes.worker_once', jid, stdout=stdout, stderr=stderr)
                try:
                    rc = await asyncio.wait_for(process.wait(), 40)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
                    raise
                assert rc == 0, 'FINITE-WORKER-PROCESS-FAILED'
                retain('worker-process', {'pid': process.pid, 'rc': rc, 'job_id': jid})
            finally:
                stdout.close()
                stderr.close()
        try:
            await asyncio.gather(*(execute(jid) for jid in ids))
            # Fresh queue has no old in-memory job map: downloads must use sys_jobs.
            main._job_queue = LocalJobQueue(max_workers=1)
            contents = []
            for jid in ids:
                status = await w.client.get('/api/v1/exports/'+jid)
                assert status.status_code == 200 and status.json()['data']['status'] == 'completed', status.text
                download = await w.client.get('/api/v1/exports/'+jid+'/download')
                assert download.status_code == 200, download.text
                contents.append(download.content)
                foreign_token = __import__('core.security', fromlist=['create_contextual_token']).create_contextual_token(
                    str(w.foreign.actor), ['admin'], str(w.b), w.foreign.schema)
                denied = await w.client.get('/api/v1/exports/'+jid+'/download',
                    headers={'Authorization': 'Bearer '+foreign_token})
                assert denied.status_code == 404, denied.text
            assert contents[0] != contents[1], 'FINITE-DIFFERENT-JOBS-NOT-SAME-FILE'
            from database.session import AsyncSessionLocal
            async with AsyncSessionLocal() as db:
                jobs = (await db.execute(text('SELECT id,payload FROM public.sys_jobs WHERE id=ANY(:ids)'),
                    {'ids': [UUID(jid) for jid in ids]})).mappings().all()
                assert len({row['payload']['file_id'] for row in jobs}) == 2
                payload = dict(jobs[0]['payload'])
                file_id = payload.pop('file_id')
                await db.execute(text('UPDATE public.sys_jobs SET payload=CAST(:p AS json) WHERE id=:i'),
                    {'p': json.dumps(payload), 'i': jobs[0]['id']})
                await db.commit()
            denied = await w.client.get('/api/v1/exports/'+str(jobs[0]['id'])+'/download')
            assert denied.status_code == 404, 'FINITE-LEGACY-JOB-NO-FALLBACK'
            other = jobs[1]['payload']['file_id']
            from jobs.export_jobs import EXPORT_DIR
            export_root = EXPORT_DIR.resolve()
            missing_file = export_root / (other+'.csv')
            assert missing_file.parent == export_root and missing_file.is_file()
            missing_file.unlink()
            denied = await w.client.get('/api/v1/exports/'+str(jobs[1]['id'])+'/download')
            assert denied.status_code == 404, 'FINITE-MISSING-FILE-NO-FALLBACK'
        finally:
            main._job_queue = None
            await reporting_engine.dispose()
