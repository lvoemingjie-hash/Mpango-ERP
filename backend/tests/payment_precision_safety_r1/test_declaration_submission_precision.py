from decimal import Decimal
import json
import os
from pathlib import Path
import uuid

import psycopg2
from psycopg2 import sql
import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

from tests.test_dc12r1_s3_s2b_i2b_payment_declarations import (
    cashier_identity,provisioned_pool,s2_clean_db,two_tenants,_errcode,
    _h5_flush_stmt_cache,_cleanup_rate_limiter,test_client_ip,
)
from tests.payment_precision_safety_r1.support import financial_case

pytestmark=pytest.mark.asyncio

def economic(vector):return {key:value for key,value in vector.items() if key!='payment_declarations'}

@pytest.mark.parametrize('currency,amount',[('KES','1.005'),('UGX','1.001')])
async def test_raw_submission_precision_before_first_insert(financial_case,two_tenants,currency,amount):
    c=financial_case;oid=await c.seed(currency);token=await c.retailer_auth(two_tenants)
    read=await c.client.get(f'/api/v1/client/orders/{oid}',headers={'Authorization':'Bearer '+token})
    assert read.status_code==200,'R2_RETAILER_ORDER_REACHABLE'
    before=await c.vector(oid)
    response=await c.declare(oid,amount,token,uuid.uuid4().hex)
    after=await c.vector(oid)
    assert (response.status_code,_errcode(response))==(400,'DECLARATION_AMOUNT_PRECISION'),'R2_RAW_DECLARATION_PRECISION_REFUSED'
    assert after==before,'R2_RAW_INPUT_ZERO_DECLARATION_AND_ECONOMIC_WRITES'

@pytest.mark.parametrize('currency,amount,method',[('KES','1.25','cash'),('KES','1.25','transfer'),('UGX','2','cash'),('UGX','2','transfer')])
async def test_real_submit_confirm_replay_single_economic_effect(financial_case,two_tenants,currency,amount,method):
    c=financial_case;oid=await c.seed(currency);token=await c.retailer_auth(two_tenants);key=uuid.uuid4().hex
    before=await c.vector(oid);response=await c.declare(oid,amount,token,key,method)
    assert response.status_code==201,response.text
    data=response.json()['data'];middle=await c.vector(oid)
    assert data['status']=='pending' and Decimal(data['declared_amount'])==Decimal(amount)
    assert len(middle['payment_declarations'])==1 and economic(middle)==economic(before),'R2_SUBMISSION_IS_NOT_RECEIPT'
    replay=await c.declare(oid,amount,token,key,method)
    assert replay.status_code==200 and replay.json()['data']['id']==data['id']
    assert await c.vector(oid)==middle
    confirmed=await c.confirm(data['id']);assert confirmed.status_code==200,confirmed.text
    after=await c.vector(oid)
    assert len(after['payments'])==1 and after['payments'][0]['amount']==Decimal(amount)
    assert after['payments'][0]['receipt_number'] and after['payment_declarations'][0]['status']=='confirmed'
    assert len(after['ledger_entries'])==2 and sorted(e['amount'] for e in after['ledger_entries'])==[-Decimal(amount),Decimal(amount)]
    assert after['order_credit_holds'][0]['remaining_amount']==100-Decimal(amount)
    assert after['binding'][0]['outstanding_balance']==before['binding'][0]['outstanding_balance']-Decimal(amount)
    repeated=await c.confirm(data['id']);assert repeated.status_code==200,repeated.text
    assert await c.vector(oid)==after,'R2_CONFIRM_REPLAY_ZERO_SECOND_EFFECT'

async def test_trailing_zeros_and_raw_invalid_same_key_are_not_rounded_replay(financial_case,two_tenants):
    c=financial_case;oid=await c.seed('UGX');token=await c.retailer_auth(two_tenants);key=uuid.uuid4().hex
    first=await c.declare(oid,'1.000',token,key);assert first.status_code==201,first.text
    before=await c.vector(oid)
    same=await c.declare(oid,'1',token,key);assert same.status_code==200,same.text
    assert await c.vector(oid)==before
    invalid=await c.declare(oid,'1.001',token,key)
    assert (invalid.status_code,_errcode(invalid))==(400,'DECLARATION_AMOUNT_PRECISION'),'R2_INVALID_RAW_NOT_ROUNDED_REPLAY'
    assert await c.vector(oid)==before
    conflict=await c.declare(oid,'2',token,key)
    assert (conflict.status_code,_errcode(conflict))==(409,'DECLARATION_IDEMPOTENCY_KEY_CONFLICT')
    assert await c.vector(oid)==before

async def test_unknown_saved_currency_new_submission_zero_writes(financial_case,two_tenants):
    c=financial_case;oid=await c.seed(None);token=await c.retailer_auth(two_tenants);before=await c.vector(oid)
    response=await c.declare(oid,'1',token,uuid.uuid4().hex)
    assert (response.status_code,_errcode(response))==(409,'DECLARATION_CURRENCY_UNVERIFIED')
    assert await c.vector(oid)==before

async def test_other_tenant_retailer_submission_remains_hidden(financial_case,two_tenants):
    c=financial_case;oid=await c.seed();token=await c.retailer_auth(two_tenants,portal_index=1)
    before=await c.vector(oid);response=await c.declare(oid,'1.005',token,uuid.uuid4().hex)
    assert response.status_code==404
    assert await c.vector(oid)==before


async def _legacy_declaration_fixture(c, two_tenants, method='cash', second_order=False):
    oid = await c.seed('KES')
    other = await c.seed('KES') if second_order else None
    token = await c.retailer_auth(two_tenants)
    key = uuid.uuid4().hex
    created = await c.declare(oid, '23.50', token, key, method)
    assert created.status_code == 201, 'LEGACY_FIXTURE_NORMAL_CREATION_REQUIRED'
    declaration = created.json()['data']
    assert declaration['status'] == 'pending'
    order_ids = [oid] + ([other] if other else [])

    # Historical compatibility fixture only: all writes precede measurement.
    for target in order_ids:
        await c.db.execute(text(f'UPDATE "{c.schema}".orders SET currency_snapshot=NULL WHERE id=:oid'), {'oid': target})
    await c.db.commit()
    url = make_url(os.environ['DATABASE_URL'])
    with psycopg2.connect(host=url.host, port=url.port, dbname=url.database,
                          user=url.username, password=url.password) as connection:
        connection.set_session(readonly=True)
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_user, current_setting('transaction_read_only'), pg_backend_pid()")
            identity = cursor.fetchone()
            assert identity[:2] == ('mpango_app', 'on'), 'LEGACY_FIXTURE_INDEPENDENT_READ_ONLY_APP_REQUIRED'
            rows = []
            for target in order_ids:
                cursor.execute(sql.SQL('SELECT id, currency_snapshot FROM {}.orders WHERE id=%s').format(sql.Identifier(c.schema)), (str(target),))
                row = cursor.fetchone()
                assert row is not None and str(row[0]) == str(target) and row[1] is None
                rows.append(row)
            cursor.execute(sql.SQL('SELECT id, order_id, retailer_id, wholesaler_id, idempotency_key, declared_amount, method, transfer_reference, status FROM {}.payment_declarations WHERE id=%s').format(sql.Identifier(c.schema)), (declaration['id'],))
            stored = cursor.fetchone()
            assert stored is not None
            assert tuple(map(str, stored[:4])) == (declaration['id'], str(oid), str(c.retailer), str(c.ws))
            assert stored[4:] == (key, Decimal('23.50'), method, 'r2-' + key if method == 'transfer' else None, 'pending')
    if os.environ.get('PAYMENT_SAFETY_FACTS'):
        proof_root = Path(os.environ['PAYMENT_SAFETY_FACTS']) / 'fixture-proofs'
        proof_root.mkdir(mode=0o700, exist_ok=True)
        proof = proof_root / (uuid.uuid4().hex + '.json')
        with proof.open('x') as stream:
            json.dump({'nodeid': c.nodeid, 'invocation': os.environ['P1_INVOCATION_ID'],
                       'fixture_committed_before_measurement': True, 'read_only_identity': identity,
                       'orders': rows, 'declaration': stored}, stream, default=str)
        proof.chmod(0o600)
    body = {'declared_amount': '23.50', 'method': method}
    if method == 'transfer':
        body['transfer_reference'] = 'r2-' + key
    return oid, other, token, key, declaration, body


async def _legacy_request(c, oid, token, key, body):
    return await c.client.post(f'/api/v1/client/orders/{oid}/declare', json=body,
        headers={'Authorization': 'Bearer ' + token, 'X-Declaration-Idempotency-Key': key})


@pytest.mark.parametrize('method', ['cash', 'transfer'])
async def test_legacy_null_currency_strict_replay_zero_writes(financial_case, two_tenants, method):
    c = financial_case
    oid, _, token, key, declaration, body = await _legacy_declaration_fixture(c, two_tenants, method)
    if method == 'transfer':
        body['transfer_reference'] = '  ' + body['transfer_reference'] + '  '
    before = await c.vector(oid)
    response = await _legacy_request(c, oid, token, key, body)
    after = await c.vector(oid)
    assert response.status_code == 200, (
        f'LEGACY_DECLARATION_STRICT_REPLAY_REQUIRED status={response.status_code} code={_errcode(response)}')
    payload = response.json()
    assert payload['message'] == 'Payment declaration replayed'
    assert payload['data']['id'] == declaration['id'] and payload['data']['status'] == declaration['status']
    assert payload['data']['transfer_reference'] == declaration['transfer_reference']
    assert len(after['payment_declarations']) == 1 and after == before, 'LEGACY_REPLAY_ALL_SEVEN_PROJECTIONS_UNCHANGED'


async def test_legacy_null_currency_new_key_refused_zero_writes(financial_case, two_tenants):
    c = financial_case
    oid, _, token, _, _, body = await _legacy_declaration_fixture(c, two_tenants)
    before = await c.vector(oid)
    response = await _legacy_request(c, oid, token, uuid.uuid4().hex, body)
    after = await c.vector(oid)
    assert (response.status_code, _errcode(response)) == (409, 'DECLARATION_CURRENCY_UNVERIFIED')
    assert after == before, 'LEGACY_NEW_KEY_ALL_SEVEN_PROJECTIONS_UNCHANGED'


async def _legacy_changed_request_conflict(c, two_tenants, field):
    method = 'transfer' if field == 'reference' else 'cash'
    oid, other, token, key, _, body = await _legacy_declaration_fixture(c, two_tenants, method, field == 'order')
    order_ids = [oid] + ([other] if other else [])
    target = oid
    if field == 'amount':
        body['declared_amount'] = '24.50'
    elif field == 'order':
        target = other
    elif field == 'method':
        body.update(method='transfer', transfer_reference='changed-method-reference')
    else:
        body['transfer_reference'] = 'changed-transfer-reference'
    before = {str(order_id): await c.vector(order_id) for order_id in order_ids}
    response = await _legacy_request(c, target, token, key, body)
    after = {str(order_id): await c.vector(order_id) for order_id in order_ids}
    assert (response.status_code, _errcode(response)) == (409, 'DECLARATION_IDEMPOTENCY_KEY_CONFLICT')
    assert after == before, 'LEGACY_CONFLICT_ALL_DECLARED_ORDERS_SEVEN_PROJECTIONS_UNCHANGED'


async def test_legacy_null_currency_same_key_changed_amount_conflict(financial_case, two_tenants):
    await _legacy_changed_request_conflict(financial_case, two_tenants, 'amount')


async def test_legacy_null_currency_same_key_changed_order_conflict(financial_case, two_tenants):
    await _legacy_changed_request_conflict(financial_case, two_tenants, 'order')


async def test_legacy_null_currency_same_key_changed_method_conflict(financial_case, two_tenants):
    await _legacy_changed_request_conflict(financial_case, two_tenants, 'method')


async def test_legacy_null_currency_same_key_changed_reference_conflict(financial_case, two_tenants):
    await _legacy_changed_request_conflict(financial_case, two_tenants, 'reference')


async def test_legacy_null_currency_other_tenant_cannot_replay(financial_case, two_tenants):
    c = financial_case
    oid, _, _, key, declaration, body = await _legacy_declaration_fixture(c, two_tenants)
    other_token = await c.retailer_auth(two_tenants, portal_index=1)
    before = await c.vector(oid)
    response = await _legacy_request(c, oid, other_token, key, body)
    after = await c.vector(oid)
    assert (response.status_code, _errcode(response)) == (404, 'ORDER_NOT_FOUND')
    assert declaration['id'] not in response.text and not response.json().get('data'), 'LEGACY_DECLARATION_NOT_DISCLOSED'
    assert after == before, 'LEGACY_OTHER_TENANT_ALL_SEVEN_PROJECTIONS_UNCHANGED'
