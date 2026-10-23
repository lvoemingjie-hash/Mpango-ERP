"""Actual app/JWT/SQL regression on a task-only PG16 database.

Minimal model DDL is deliberately NOT a migration or production-role proof.
"""
import os
import secrets
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.schema import CreateTable, CreateIndex

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture(loop_scope="session")
async def world():
    if os.environ.get('AUDIT_FINITE_APP_URL'):
        from tests.audit_fixes.support import full_world
        async with full_world() as value:
            yield value
        return
    assert os.environ.get('AUDIT_REPAIR_DATABASE') == 'audit_repair', 'Explicit disposable database guard required'
    from database.session import async_engine
    from models.wholesaler import Wholesaler
    from models.platform_tenant import PlatformTenant
    from models.retailer import Retailer
    from models.user import User, Role, Permission
    from models.associations import user_roles, role_permissions
    from models.ledger import LedgerEntry
    from models.order import Order, OrderItem
    from models.order_credit_hold import OrderCreditHold
    from core.permission_registry import ADMIN_PERMISSION_CODES
    from core.security import hash_password, create_contextual_token
    from api.app import configure_app
    from core.config import get_settings
    from core.error_codes import register_exception_handlers

    a, b, uid, rid = uuid4(), uuid4(), uuid4(), uuid4()
    schema = 't_' + a.hex
    password = secrets.token_urlsafe(32)
    email = uid.hex + '@example.com'
    async with async_engine.begin() as c:
        assert await c.scalar(text('SELECT current_database()')) == 'audit_repair'
        for table in (Wholesaler.__table__, PlatformTenant.__table__, Retailer.__table__):
            await c.run_sync(lambda conn, t=table: t.create(conn, checkfirst=True))
        await c.execute(text('CREATE TABLE IF NOT EXISTS public.wholesaler_retailer_bindings(wholesaler_id uuid,retailer_id uuid,outstanding_balance numeric,is_deleted bool default false,updated_at timestamp default now())'))
        await c.execute(text(f'CREATE SCHEMA "{schema}"'))
        await c.execute(text(f'SET LOCAL search_path TO "{schema}",public'))
        for table in (User.__table__, Role.__table__, Permission.__table__, user_roles, role_permissions, LedgerEntry.__table__, Order.__table__):
            for column in table.columns:
                if hasattr(column.type, 'create'):
                    await c.run_sync(lambda conn, typ=column.type: typ.create(conn, checkfirst=True))
            await c.execute(CreateTable(table))
            seen = set()
            for index in table.indexes:
                if index.name not in seen:
                    await c.execute(CreateIndex(index))
                    seen.add(index.name)
        await c.execute(text('INSERT INTO public.wholesalers(id,code,name) VALUES (:a,:ac,\'Tenant A\'),(:b,:bc,\'Tenant B\')'), {'a': a, 'b': b, 'ac': a.hex, 'bc': b.hex})
        await c.execute(text('INSERT INTO users(id,email,password_hash,is_active) VALUES (:u,:email,:p,true)'), {'u': uid, 'email': email, 'p': hash_password(password)})
        await c.execute(text("INSERT INTO roles(id,name) VALUES (:r,'admin')"), {'r': rid})
        await c.execute(text('INSERT INTO user_roles(user_id,role_id) VALUES (:u,:r)'), {'u': uid, 'r': rid})
        for code in set(ADMIN_PERMISSION_CODES) | {'exports:create'}:
            pid = uuid4()
            await c.execute(text('INSERT INTO permissions(id,code) VALUES (:p,:c)'), {'p': pid, 'c': code})
            await c.execute(text('INSERT INTO role_permissions(role_id,permission_id) VALUES (:r,:p)'), {'r': rid, 'p': pid})
        await c.execute(text('CREATE TABLE staff_authority(singleton int,state text,owner_user_id uuid,authz_revision int)'))
        await c.execute(text("INSERT INTO staff_authority VALUES(1,'unmapped',NULL,1)"))
        await c.execute(text('CREATE TABLE staff_memberships(user_id uuid)'))
        await c.execute(text('CREATE TABLE skus(id uuid primary key)'))
        await c.execute(CreateTable(OrderItem.__table__))
        await c.execute(text('CREATE TABLE payments(id uuid PRIMARY KEY default gen_random_uuid(),order_id uuid,retailer_id uuid,amount numeric,method text,status text,transaction_id text,idempotency_key text UNIQUE,receipt_number text,created_at timestamp default now(),updated_at timestamp default now(),is_deleted bool default false,created_by uuid,updated_by uuid)'))
        await c.run_sync(OrderCreditHold.__table__.create)

    async def sql(statement, parameters=None):
        async with async_engine.begin() as c:
            await c.execute(text(f'SET LOCAL search_path TO "{schema}",public'))
            result = await c.execute(text(statement), parameters or {})
            return result.mappings().all() if result.returns_rows else []

    async def order(*, credit=False, currency='KES'):
        oid, retailer = uuid4(), uuid4()
        await sql('INSERT INTO public.retailers(id,phone,name) VALUES (:r,:phone,\'Fixture retailer\')', {'r': retailer, 'phone': retailer.hex[:16]})
        await sql('INSERT INTO orders(id,wholesaler_id,retailer_id,status,total_amount,currency_snapshot) VALUES (:o,:w,:r,:s,100,:currency)',
                  {'o': oid, 'w': a, 'r': retailer, 's': 'fulfilled' if credit else 'confirmed', 'currency': currency})
        await sql('INSERT INTO order_credit_holds(order_id,amount,remaining_amount,status,created_by) VALUES (:o,100,:remaining,:s,:u)',
                  {'o': oid, 'remaining': 0 if credit else 100, 's': 'converted' if credit else 'active', 'u': uid})
        await sql('INSERT INTO public.wholesaler_retailer_bindings(wholesaler_id,retailer_id,outstanding_balance) VALUES (:w,:r,100)', {'w': a, 'r': retailer})
        if credit:
            await sql("INSERT INTO payments(order_id,retailer_id,amount,method,status) VALUES (:o,:r,100,'credit','completed')", {'o': oid, 'r': retailer})
        return str(oid), str(retailer)

    app = FastAPI()
    register_exception_handlers(app)
    configure_app(app, get_settings())
    token = create_contextual_token(str(uid), ['admin'], str(a), schema)
    async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url='http://audit', headers={'Authorization': 'Bearer ' + token}) as client:
        yield SimpleNamespace(client=client, sql=sql, order=order, a=a, b=b, uid=uid, rid=rid, email=email, password=password, schema=schema)


async def test_admin_registry_is_self_only_and_foreign_writes_zero(world):
    w = world
    response = await w.client.get('/api/v1/wholesalers')
    assert response.status_code == 200
    assert [row['id'] for row in response.json()['data']['items']] == [str(w.a)], 'AUDIT-F01-SELF-ONLY'
    for method, body in (('get', None), ('put', {'name': 'unauthorized'}), ('delete', None)):
        response = await w.client.request(method, f'/api/v1/wholesalers/{w.b}', json=body)
        assert response.status_code in (403, 404), 'AUDIT-F01-FOREIGN-REGISTRY-DENIED'
    rows = await w.sql('SELECT name,is_deleted FROM public.wholesalers WHERE id=:b', {'b': w.b})
    assert rows == [{'name': 'Tenant B', 'is_deleted': False}], 'AUDIT-F01-ZERO-WRITES'
    response = await w.client.post('/api/v1/wholesalers', json={'code': 'DENIED', 'name': 'Unauthorized'})
    assert response.status_code == 403, 'AUDIT-F01-REGISTRY-CREATE-DENIED'


async def test_live_platform_registry_operations_still_work(world):
    w = world
    await w.sql("UPDATE roles SET name='super_admin' WHERE id=:r", {'r': w.rid})
    login = await w.client.post('/api/v1/auth/login', headers={'Authorization': ''}, json={'email': w.email, 'password': w.password})
    assert login.status_code == 200
    headers = {'Authorization': 'Bearer ' + login.json()['data']['access_token']}
    response = await w.client.put(f'/api/v1/wholesalers/{w.b}', headers=headers, json={'name': 'Platform authorized'})
    assert response.status_code == 200, 'AUDIT-F01-PLATFORM-POSITIVE'
    response = await w.client.get(f'/api/v1/wholesalers/{w.b}', headers=headers)
    assert response.json()['data']['name'] == 'Platform authorized'


@pytest.mark.parametrize('revocation', ['inactive', 'deleted', 'role_removed'])
async def test_current_platform_subject_revokes_access_and_refresh(world, revocation):
    w = world
    await w.sql("UPDATE roles SET name='super_admin' WHERE id=:r", {'r': w.rid})
    login = await w.client.post('/api/v1/auth/login', headers={'Authorization': ''}, json={'email': w.email, 'password': w.password})
    assert login.status_code == 200
    tokens = login.json()['data']
    headers = {'Authorization': 'Bearer ' + tokens['access_token']}
    assert (await w.client.get('/api/v1/platform/tenants/', headers=headers)).status_code == 200, 'AUDIT-F02-LIVE-CONTROL'
    if revocation == 'inactive':
        await w.sql('UPDATE users SET is_active=false WHERE id=:u', {'u': w.uid})
    elif revocation == 'deleted':
        await w.sql('UPDATE users SET is_deleted=true WHERE id=:u', {'u': w.uid})
    else:
        await w.sql('DELETE FROM user_roles WHERE user_id=:u', {'u': w.uid})
    assert (await w.client.get('/api/v1/platform/tenants/', headers=headers)).status_code == 401, 'AUDIT-F02-OLD-ACCESS-REVOKED'
    refresh = await w.client.post('/api/v1/auth/refresh', headers={'Authorization': ''}, json={'refresh_token': tokens['refresh_token']})
    assert refresh.status_code == 401, 'AUDIT-F02-OLD-REFRESH-REVOKED'


async def test_real_csv_export_and_order_detail_are_distinct(world):
    oid, _ = await world.order(currency='UGX')
    response = await world.client.get('/api/v1/orders/export')
    assert response.status_code == 200 and response.headers['content-type'].startswith('text/csv'), 'AUDIT-F07-CSV'
    assert oid in response.text, 'AUDIT-F07-EXPORTED-ORDER'
    assert 'Currency' in response.text and 'UGX' in response.text and 'Total Amount (KES)' not in response.text
    assert (await world.client.get('/api/v1/orders/' + oid)).status_code == 200


async def test_partial_receipts_invoice_cash_and_replay(world):
    w = world
    oid, retailer = await w.order()
    key = str(uuid4())
    response = await w.client.post(f'/api/v1/orders/{oid}/pay', headers={'X-Idempotency-Key': key}, json={'amount': '40', 'method': 'cash'})
    assert response.status_code == 200, response.text
    invoice = (await w.client.get(f'/api/v1/orders/{oid}/invoice')).json()['data']
    assert (invoice['total_paid'], invoice['balance_due']) == (40, 60), 'AUDIT-F04-PARTIAL-INVOICE'
    rows = await w.sql("SELECT SUM(amount) AS cash FROM ledger_entries WHERE account_type='cash'")
    assert rows[0]['cash'] == 40, 'AUDIT-F04-PARTIAL-CASH-LEDGER'
    legacy = (await w.client.get('/api/v1/finance/receivables')).json()['data']['items']
    assert (legacy[0]['total_paid'], legacy[0]['balance_due']) == (40, 60), 'AUDIT-F04-LEGACY-PROJECTION'
    from database.session import AsyncSessionLocal
    from repositories.statement_repository import StatementRepository
    from datetime import datetime, timedelta, timezone
    async with AsyncSessionLocal() as db:
        repo = StatementRepository()
        now = datetime.now(timezone.utc)
        movements, total = await repo.list_movements(db, schema=w.schema, wholesaler_id=w.a,
            retailer_id=UUID(retailer), start_utc=now-timedelta(days=1), next_day_utc=now+timedelta(days=1))
        assert len(movements) == 1
        assert total == -40, 'AUDIT-F04-STATEMENT-PAYMENT-REFERENCE-NOT-DROPPED'
    response = await w.client.post(f'/api/v1/orders/{oid}/pay', headers={'X-Idempotency-Key': key}, json={'amount': '40', 'method': 'cash'})
    assert response.status_code == 200
    response = await w.client.post(f'/api/v1/orders/{oid}/pay', headers={'X-Idempotency-Key': str(uuid4())}, json={'amount': '60', 'method': 'cash'})
    assert response.status_code == 200, response.text
    rows = await w.sql("SELECT SUM(amount) AS cash,COUNT(*) AS n FROM ledger_entries WHERE account_type='cash'")
    assert (rows[0]['cash'], rows[0]['n']) == (100, 2), 'AUDIT-F04-NO-DUPLICATE-FULL-POSTING'
    summary = (await w.client.get('/api/v1/finance/summary')).json()['data']
    assert summary['outstanding_receivables'] == 0, 'AUDIT-F05-SETTLED-IS-ZERO-NOT-NEGATIVE'


async def test_fulfilled_credit_remains_collectible_and_fulfilled(world):
    w = world
    oid, retailer = await w.order(credit=True)
    for remaining, amount in ((100, '40'), (60, '60')):
        response = await w.client.get('/api/v1/finance/receivables/orders', params={'retailer_id': retailer})
        assert response.status_code == 200, response.text
        assert len(response.json()['data']['items']) == 1, 'AUDIT-F03-FULFILLED-DEBT-VISIBLE'
        assert response.json()['data']['items'][0]['balance_due'] == remaining, 'AUDIT-F03-FULFILLED-DEBT-VISIBLE'
        key = str(uuid4())
        for _ in range(2):
            response = await w.client.post(f'/api/v1/orders/{oid}/pay', headers={'X-Idempotency-Key': key}, json={'amount': amount, 'method': 'cash'})
            assert response.status_code == 200, 'AUDIT-F03-FULFILLED-COLLECTION:' + response.text
    rows = await w.sql('SELECT status FROM orders WHERE id=:o', {'o': oid})
    assert rows[0]['status'] == 'fulfilled', 'AUDIT-F03-NO-LOGISTICS-REWRITE'
    rows = await w.sql("SELECT SUM(amount) AS cash FROM payments WHERE method='cash'")
    assert rows[0]['cash'] == 100, 'AUDIT-F03-IDEMPOTENT-COLLECTION'


async def test_settled_summary_does_not_use_negative_legacy_receivable(world):
    oid, _ = await world.order()
    response = await world.client.post(f'/api/v1/orders/{oid}/pay', headers={'X-Idempotency-Key': str(uuid4())}, json={'amount': '100', 'method': 'cash'})
    assert response.status_code == 200, response.text
    data = (await world.client.get('/api/v1/finance/summary')).json()['data']
    assert data['outstanding_receivables'] == 0, 'AUDIT-F05-ZERO-SETTLED-RECEIVABLE'


async def test_receipt_ledger_failure_rolls_back_entire_payment(world):
    w = world
    oid, retailer = await w.order()
    await w.sql("CREATE FUNCTION reject_receipt() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'synthetic ledger fault'; END $$")
    await w.sql('CREATE TRIGGER reject_receipt BEFORE INSERT ON ledger_entries FOR EACH ROW EXECUTE FUNCTION reject_receipt()')
    response = await w.client.post(f'/api/v1/orders/{oid}/pay', headers={'X-Idempotency-Key': str(uuid4())}, json={'amount': '40', 'method': 'cash'})
    assert response.status_code == 500, 'AUDIT-F04-FAULT-MUST-FAIL'
    rows = await w.sql('SELECT status FROM orders WHERE id=:o', {'o': oid})
    assert rows[0]['status'] == 'confirmed', 'AUDIT-F04-ROLLBACK-STATE'
    rows = await w.sql('SELECT status,remaining_amount FROM order_credit_holds WHERE order_id=:o', {'o': oid})
    assert rows[0]['status'] == 'active' and rows[0]['remaining_amount'] == 100, 'AUDIT-F04-ROLLBACK-HOLD'
    rows = await w.sql('SELECT outstanding_balance FROM public.wholesaler_retailer_bindings WHERE wholesaler_id=:w AND retailer_id=:r', {'w': w.a, 'r': retailer})
    assert rows[0]['outstanding_balance'] == 100, 'AUDIT-F04-ROLLBACK-CACHE'
    assert (await w.sql('SELECT COUNT(*) AS n FROM payments'))[0]['n'] == 0, 'AUDIT-F04-ROLLBACK-PAYMENT'
    assert (await w.sql('SELECT COUNT(*) AS n FROM ledger_entries'))[0]['n'] == 0, 'AUDIT-F04-ROLLBACK-LEDGER'


@pytest.mark.parametrize('kind', ['refresh', 'unknown'])
async def test_real_business_http_refuses_non_access_token(world, kind):
    from core.security import create_contextual_token
    token = create_contextual_token(str(world.uid), ['admin'], str(world.a), world.schema, token_type=kind)
    response = await world.client.get('/api/v1/wholesalers', headers={'Authorization': 'Bearer ' + token})
    assert response.status_code == 401, 'AUDIT-F06-REAL-HTTP-REJECT'


@pytest.mark.parametrize('currency', ['KES', 'UGX', None])
async def test_finance_currency_is_snapshot_not_default_kes(world, currency):
    await world.order(currency=currency)
    response = await world.client.get('/api/v1/finance/summary')
    assert response.status_code == 200, response.text
    data = response.json()['data']
    assert 'currency' in data and data['currency'] == currency, 'AUDIT-F09-SNAPSHOT-CURRENCY'


async def test_mixed_currency_summary_is_not_summed(world):
    await world.order(currency='KES')
    await world.order(currency='UGX')
    response = await world.client.get('/api/v1/finance/summary')
    assert response.status_code == 200, response.text
    data = response.json()['data']
    assert data.get('currency_status') == 'mixed' and data['outstanding_receivables'] is None, 'AUDIT-F09-NO-MIXED-SUM'
    assert data['outstanding_by_currency'] == {'KES': 100, 'UGX': 100}
