from decimal import Decimal
import uuid
import pytest

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
