from dataclasses import dataclass, field
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
import uuid

from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport
import pytest_asyncio
from sqlalchemy import text

from api.app import configure_app
from auth.strategies.jwt import JwtAuthStrategy
from core.config import get_settings
from core.error_codes import register_exception_handlers
from services.canonical_payment_service import CanonicalPaymentService
from tests.test_dc12r1_s3_s2b_i2b_payment_declarations import _cashier_token, _resolve_binding_retailer


@dataclass
class Case:
    db: object
    client: AsyncClient
    schema: str
    ws: str
    retailer: str
    token: str
    actor: str
    orders: list = field(default_factory=list)
    nodeid: str = ''
    sample_phase: str = 'business'
    sample_ordinal: int = 0

    async def seed(self, currency='KES', total='100.00'):
        oid=uuid.uuid4();self.orders.append(oid)
        await self.db.execute(text(f'INSERT INTO "{self.schema}".orders '
            '(id,wholesaler_id,retailer_id,status,total_amount,currency_snapshot) '
            "VALUES (:o,:w,:r,'confirmed',:a,:c)"),
            {'o':oid,'w':self.ws,'r':self.retailer,'a':Decimal(total),'c':currency})
        await self.db.execute(text(f'INSERT INTO "{self.schema}".order_credit_holds '
            "(order_id,amount,remaining_amount,status) VALUES (:o,:a,:a,'active')"),{'o':oid,'a':Decimal(total)})
        await self.db.execute(text('UPDATE public.wholesaler_retailer_bindings '
            'SET outstanding_balance=outstanding_balance+:a WHERE wholesaler_id=:w AND retailer_id=:r'),
            {'a':Decimal(total),'w':self.ws,'r':self.retailer})
        await self.db.commit();return oid

    async def vector(self, oid):
        await self.db.rollback()
        out={}
        for table in ('orders','payments','order_credit_holds','payment_declarations'):
            column='id' if table=='orders' else 'order_id'
            rows=(await self.db.execute(text(f'SELECT * FROM "{self.schema}".{table} WHERE {column}=:o ORDER BY id'),{'o':oid})).mappings().all()
            out[table]=[dict(r) for r in rows]
        out['ledger_entries']=[dict(r) for r in (await self.db.execute(text(
            f'SELECT * FROM "{self.schema}".ledger_entries WHERE '
            "(reference_type='order' AND reference_id=:o) OR "
            f"(reference_type='payment' AND reference_id IN (SELECT id FROM \"{self.schema}\".payments WHERE order_id=:o)) ORDER BY id"),{'o':oid})).mappings().all()]
        out['binding']=[dict(r) for r in (await self.db.execute(text(
            'SELECT * FROM public.wholesaler_retailer_bindings WHERE wholesaler_id=:w AND retailer_id=:r ORDER BY id'),
            {'w':self.ws,'r':self.retailer})).mappings().all()]
        out['receipt_sequences']=[dict(r) for r in (await self.db.execute(text(
            f'SELECT * FROM "{self.schema}".receipt_sequences ORDER BY 1'))).mappings().all()]
        root=os.environ.get('PAYMENT_SAFETY_FACTS')
        if root:
            p=Path(root)/(uuid.uuid4().hex+'.json')
            with p.open('x') as stream:json.dump(out,stream,default=str)
            p.chmod(0o600)
            self.sample_ordinal += 1
            sidecar = Path(root) / 'vector-index.jsonl'
            record = {'nodeid': self.nodeid,
                'invocation': os.environ['P1_INVOCATION_ID'],
                'phase': self.sample_phase, 'ordinal': self.sample_ordinal,
                'raw_path': str(p), 'sha256': sha256(p.read_bytes()).hexdigest()}
            assert record['nodeid'], 'FINANCIAL_VECTOR_NODE_ATTRIBUTION_NOT_ESTABLISHED'
            with sidecar.open('a') as stream:stream.write(json.dumps(record) + '\n')
            sidecar.chmod(0o600)
        await self.db.rollback()
        return out

    async def http_pay(self, oid, amount, key=None, method='cash'):
        body={'amount':str(amount),'method':method}
        if method=='transfer':body['transaction_id']='r01-'+(key or uuid.uuid4().hex)
        return await self.client.post(f'/api/v1/orders/{oid}/pay',json=body,
            headers={'Authorization':'Bearer '+self.token,'X-Idempotency-Key':key or uuid.uuid4().hex})

    async def retailer_auth(self, two_tenants, portal_index=0):
        response=await self.client.post('/api/v1/client/auth/login',json={
            'email':two_tenants[3],'password':two_tenants[4],
            'wholesaler_code':two_tenants[portal_index]})
        assert response.status_code==200,'R2_REAL_RETAILER_LOGIN_PRECONDITION'
        return response.json()['data']['tokens']['access_token']

    async def declare(self, oid, amount, retailer_token, key, method='cash'):
        body={'declared_amount':str(amount),'method':method}
        if method=='transfer':body['transfer_reference']='r2-'+key
        return await self.client.post(f'/api/v1/client/orders/{oid}/declare',json=body,
            headers={'Authorization':'Bearer '+retailer_token,'X-Declaration-Idempotency-Key':key})

    async def confirm(self, declaration_id):
        return await self.client.post(f'/api/v1/declarations/{declaration_id}/confirm',
            headers={'Authorization':'Bearer '+self.token})

    async def service_pay(self, oid, amount, key=None, method='cash', locked=False, receipt=False):
        await self.db.execute(text(f'SET LOCAL search_path TO "{self.schema}", public'))
        svc=CanonicalPaymentService()
        kwargs=dict(db=self.db,amount=Decimal(amount),method=method,transaction_id=None,
            idempotency_key=key or uuid.uuid4().hex,created_by=self.actor,allocate_receipt=receipt)
        try:
            if locked:
                order=await svc._get_order_by_id_for_update(self.db,str(oid))
                result=await svc._confirm_payment_for_locked_order(order=order,**kwargs)
            else:result=await svc.confirm_payment(order_id=str(oid),**kwargs)
            await self.db.commit();return result
        except BaseException:
            await self.db.rollback();raise


@pytest_asyncio.fixture
async def financial_case(s2_clean_db, provisioned_pool, two_tenants, cashier_identity, test_client_ip, monkeypatch, request):
    db,_=s2_clean_db;tenant=provisioned_pool.tenants['a']
    retailer=await _resolve_binding_retailer(db,tenant['ws_id'],two_tenants[5])
    # Only this request app switches profile. Existing test-preparation roles
    # retain their normal test contract; real authentication is never mocked.
    monkeypatch.setenv('MPANGO_ENV','staging')
    settings=get_settings();app=FastAPI();configure_app(app,settings)
    register_exception_handlers(app)
    assert isinstance(app.state.auth_strategy,JwtAuthStrategy)
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://testserver',
        headers={'X-Forwarded-For':test_client_ip}) as client:
        token=await _cashier_token(client,cashier_identity)
        case=Case(db,client,tenant['schema'],tenant['ws_id'],retailer,token,str(cashier_identity['user_id']), nodeid=request.node.nodeid)
        try:yield case
        finally:
            await db.rollback()
            case.sample_phase = 'fixture-teardown'
            for oid in case.orders:
                await case.vector(oid)
            # Only this module's freshly provisioned target schema; immutable
            # ledger DELETE is never disabled and no external schema is touched.
            await db.execute(text(f'TRUNCATE TABLE "{case.schema}".order_items, '
                f'"{case.schema}".payments, "{case.schema}".ledger_entries, '
                f'"{case.schema}".orders RESTART IDENTITY CASCADE'))
            await db.commit()
