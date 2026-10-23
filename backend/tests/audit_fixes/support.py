"""Finite regression support: native provisioning on migrated task app identity."""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import secrets
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text


def retain(label, value):
    root = Path(os.environ['AUDIT_FINITE_PRIVATE']) / 'facts'
    root.mkdir(mode=0o700, exist_ok=True)
    path = root / (label + '-' + uuid4().hex + '.json')
    with path.open('x') as out:
        os.fchmod(out.fileno(), 0o600)
        json.dump(value, out, default=str, indent=2)
        out.write('\n')


@asynccontextmanager
async def full_world(country='KE'):
    from tests.test_inventory_manual_adjustment_safety import StockWorld
    from core.security import create_contextual_token, hash_password
    from api.app import configure_app
    from core.config import get_settings
    from core.error_codes import register_exception_handlers
    from database.session import async_engine

    sw, foreign = StockWorld(), StockWorld()
    try:
        await sw.initialize(country=country)
        await foreign.initialize(country=country)

        async def sql(statement, parameters=None):
            async with sw.session() as db:
                result = await db.execute(text(statement), parameters or {})
                return result.mappings().all() if result.returns_rows else []

        await sql('UPDATE public.wholesalers SET name=:name WHERE id=:id',
                  {'id': foreign.wid, 'name': 'Tenant B'})
        customer, password = uuid4(), secrets.token_urlsafe(32)
        await sql('INSERT INTO users(id,email,password_hash,is_active) VALUES (:id,:e,:p,true)',
                  {'id': customer, 'e': customer.hex+'@example.com', 'p': hash_password(password)})
        await sql("INSERT INTO user_roles(user_id,role_id) SELECT :id,id FROM roles WHERE name='retailer_operator'",
                  {'id': customer})
        await sql('UPDATE public.wholesaler_retailer_bindings SET tenant_user_id=:u WHERE wholesaler_id=:w AND retailer_id=:r',
                  {'u': customer, 'w': sw.wid, 'r': sw.retailer})
        admin_role = (await sql("SELECT id FROM roles WHERE name='admin'"))[0]['id']

        async def seed_order(*, credit=False, currency='KES'):
            oid, retailer = uuid4(), uuid4()
            await sql("INSERT INTO public.retailers(id,phone,name) VALUES (:r,:p,'Fixture retailer')",
                      {'r': retailer, 'p': retailer.hex[:16]})
            await sql('INSERT INTO orders(id,wholesaler_id,retailer_id,status,total_amount,currency_snapshot) VALUES (:o,:w,:r,:s,100,:currency)',
                      {'o': oid, 'w': sw.wid, 'r': retailer, 's': 'fulfilled' if credit else 'confirmed', 'currency': currency})
            await sql('INSERT INTO order_credit_holds(order_id,amount,remaining_amount,status,created_by) VALUES (:o,100,:remaining,:s,:u)',
                      {'o': oid, 'remaining': 0 if credit else 100, 's': 'converted' if credit else 'active', 'u': sw.actor})
            await sql("INSERT INTO public.wholesaler_retailer_bindings(wholesaler_id,retailer_id,status,outstanding_balance) VALUES (:w,:r,'active',100)",
                      {'w': sw.wid, 'r': retailer})
            if credit:
                await sql("INSERT INTO payments(order_id,retailer_id,amount,method,status) VALUES (:o,:r,100,'credit','completed')", {'o': oid, 'r': retailer})
            return str(oid), str(retailer)

        async def response_record(response):
            await response.aread()
            request = response.request
            retain('http', {'method': request.method, 'path': request.url.path,
                'query': request.url.query.decode(), 'status': response.status_code,
                'authorization_sha256': hashlib.sha256(request.headers.get('Authorization','').encode()).hexdigest(),
                'key_sha256': hashlib.sha256(request.headers.get('X-Idempotency-Key',
                    request.headers.get('X-Declaration-Idempotency-Key','')).encode()).hexdigest(),
                'body_sha256': hashlib.sha256(request.content).hexdigest(),
                'response': response.text, 'at_utc': datetime.now(timezone.utc)})

        app = FastAPI()
        register_exception_handlers(app)
        configure_app(app, get_settings())
        assert not app.dependency_overrides
        assert type(app.state.auth_strategy).__name__ == 'JwtAuthStrategy'
        token = create_contextual_token(str(sw.actor), ['admin'], str(sw.wid), sw.schema)
        client_token = create_contextual_token(str(customer), ['retailer_operator'], str(sw.wid), sw.schema)
        async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False),
                base_url='http://audit', headers={'Authorization': 'Bearer '+token,
                    'X-Forwarded-For': '10.'+'.'.join(str(x) for x in secrets.token_bytes(3))},
                event_hooks={'response': [response_record]}) as client:
            w = SimpleNamespace(client=client, app=app, sql=sql, order=seed_order,
                a=sw.wid, b=foreign.wid, uid=sw.actor, rid=admin_role, schema=sw.schema,
                email=sw.email, password=sw.password, stock_world=sw, foreign=foreign,
                customer=customer, customer_password=password,
                customer_email=customer.hex+'@example.com', client_token=client_token,
                retailer=sw.retailer, currency='UGX' if country=='UG' else 'KES')
            yield w
    finally:
        await async_engine.dispose()
        if hasattr(sw, 'engine'): await sw.engine.dispose()
        if hasattr(foreign, 'engine'): await foreign.engine.dispose()


async def economic_facts(w, label):
    result = {}
    for table in ('orders', 'order_items', 'inventory_stocks', 'inventory_movements',
                  'inventory_reservations', 'payments', 'ledger_entries', 'order_credit_holds'):
        result[table] = [row['raw'] for row in await w.sql(
            f'SELECT row_to_json(t)::text AS raw FROM "{w.schema}"."{table}" t ORDER BY id')]
    result['binding'] = [row['raw'] for row in await w.sql(
        'SELECT row_to_json(b)::text AS raw FROM public.wholesaler_retailer_bindings b '
        'WHERE wholesaler_id=:w ORDER BY retailer_id', {'w': w.a})]
    retain(label, result)
    return result


async def create_confirmed(w):
    items = [{'sellable_unit_id': str(w.stock_world.sku), 'quantity': 100}]
    quote = await w.client.post('/api/v1/orders/quote', json={'items': items, 'retailer_id': str(w.retailer)})
    assert quote.status_code == 200, quote.text
    result = await w.client.post('/api/v1/orders', headers={'X-Idempotency-Key': str(uuid4())},
        json={'items': items, 'retailer_id': str(w.retailer), 'quote_token': quote.json()['data']['quote_token']})
    assert result.status_code == 201, result.text
    oid = result.json()['data']['id']
    result = await w.client.post(f'/api/v1/orders/{oid}/confirm')
    assert result.status_code == 200, result.text
    assert (await w.sql('SELECT total_amount FROM orders WHERE id=:o', {'o': UUID(oid)}))[0]['total_amount'] == Decimal('100')
    return oid
