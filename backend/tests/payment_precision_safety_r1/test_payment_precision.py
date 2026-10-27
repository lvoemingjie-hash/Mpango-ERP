from decimal import Decimal
import uuid
from unittest.mock import patch

from fastapi import HTTPException
import pytest
from sqlalchemy import text

from services.payment_service import PaymentService
from tests.test_dc12r1_s3_s2b_i2b_payment_declarations import (
    cashier_identity, provisioned_pool, s2_clean_db, two_tenants, _errcode,
    _h5_flush_stmt_cache, _cleanup_rate_limiter, test_client_ip,
)
from tests.payment_precision_safety_r1.support import financial_case

pytestmark=pytest.mark.asyncio


@pytest.mark.parametrize('currency,amount',[('KES','1.005'),('UGX','1.50')])
async def test_http_precision_refusal_and_full_vector(financial_case,currency,amount):
    c=financial_case;oid=await c.seed(currency)
    # Positive: real JWT login/select-tenant and this order's current read.
    got=await c.client.get(f'/api/v1/orders/{oid}',headers={'Authorization':'Bearer '+c.token})
    assert got.status_code==200,'R01_AUTHENTICATED_ORDER_PRECONDITION'
    before=await c.vector(oid)
    result=await c.http_pay(oid,amount)
    assert (result.status_code,_errcode(result))==(400,'PAYMENT_AMOUNT_PRECISION'),'R01_HTTP_PRECISION_REFUSAL'
    assert await c.vector(oid)==before,'R01_ZERO_FINANCIAL_EFFECT'


async def test_locked_entry_precision_refusal_preserves_receipt(financial_case):
    c=financial_case;oid=await c.seed();before=await c.vector(oid)
    with pytest.raises(HTTPException) as exc:await c.service_pay(oid,'1.005',locked=True,receipt=True)
    assert exc.value.detail['code']=='PAYMENT_AMOUNT_PRECISION','R01_LOCKED_PRECISION_REFUSAL'
    assert await c.vector(oid)==before


async def test_retained_declaration_confirmation_cannot_bypass_precision(financial_case,two_tenants):
    c=financial_case;oid=await c.seed('UGX');did=uuid.uuid4()
    await c.db.execute(text(f'INSERT INTO "{c.schema}".payment_declarations '
        '(id,order_id,retailer_id,wholesaler_id,declared_amount,method,idempotency_key,status,submitted_by) '
        "VALUES (:d,:o,:r,:w,1.50,'cash',:k,'pending',:u)"),
        {'d':did,'o':oid,'r':c.retailer,'w':c.ws,'k':uuid.uuid4().hex,'u':two_tenants[5]})
    await c.db.commit();before=await c.vector(oid)
    result=await c.client.post(f'/api/v1/declarations/{did}/confirm',headers={'Authorization':'Bearer '+c.token})
    assert (result.status_code,_errcode(result))==(400,'PAYMENT_AMOUNT_PRECISION'),'R01_DECLARATION_PRECISION_REFUSAL'
    assert await c.vector(oid)==before,'R01_DECLARATION_AND_RECEIPT_UNCONSUMED'


@pytest.mark.parametrize('currency,method',[('KES','cash'),('KES','transfer'),('UGX','cash'),('UGX','transfer')])
async def test_valid_partial_final_and_exact_replay(financial_case,currency,method):
    c=financial_case;oid=await c.seed(currency)
    amount='1.25' if currency=='KES' else '25'
    key=uuid.uuid4().hex;first=await c.http_pay(oid,amount,key,method)
    assert first.status_code==200,first.text
    middle=await c.vector(oid)
    replay=await c.http_pay(oid,amount,key,method);assert replay.status_code==200,replay.text
    assert await c.vector(oid)==middle
    final=await c.http_pay(oid,str(Decimal(100)-Decimal(amount)),method=method)
    assert final.status_code==200,final.text
    after=await c.vector(oid)
    assert len(after['payments'])==2 and sum(p['amount'] for p in after['payments'])==100
    assert len(after['ledger_entries'])==4 and sum(e['amount'] for e in after['ledger_entries'])==0
    assert sorted(e['amount'] for e in after['ledger_entries'])==sorted([Decimal(amount),-Decimal(amount),100-Decimal(amount),Decimal(amount)-100])
    assert after['orders'][0]['status']=='paid'
    assert (after['order_credit_holds'][0]['status'],after['order_credit_holds'][0]['remaining_amount'])==('settled',0)
    assert after['binding'][0]['outstanding_balance']==0


async def test_trailing_zeros_are_numeric_equivalence_not_rounding(financial_case):
    c=financial_case;oid=await c.seed('UGX');key=uuid.uuid4().hex
    first=await c.http_pay(oid,'1.000',key);assert first.status_code==200,first.text
    before=await c.vector(oid);same=await c.http_pay(oid,'1',key)
    assert same.status_code==200 and await c.vector(oid)==before


@pytest.mark.parametrize('same_key',[True,False])
async def test_excess_precision_cannot_merge_into_existing_payment(financial_case,same_key):
    c=financial_case;oid=await c.seed();key=uuid.uuid4().hex
    assert (await c.http_pay(oid,'1.00',key)).status_code==200
    before=await c.vector(oid);r=await c.http_pay(oid,'1.005',key if same_key else None)
    assert r.status_code==409 if same_key else (r.status_code,_errcode(r))==(400,'PAYMENT_AMOUNT_PRECISION')
    if same_key:assert _errcode(r)=='IDEMPOTENCY_KEY_CONFLICT'
    assert await c.vector(oid)==before


@pytest.mark.parametrize('currency',[None,'USD'])
async def test_unverified_currency_new_write_refused(financial_case,currency):
    c=financial_case;oid=await c.seed(None);before=await c.vector(oid)
    if currency is not None:
        # Current head044 CHECK forbids persisted USD. Exercise a retained
        # unsupported source at the real locked seam without disabling it or
        # flushing a counterfeit history row into PostgreSQL.
        from services.canonical_payment_service import CanonicalPaymentService
        await c.db.execute(text(f'SET LOCAL search_path TO "{c.schema}", public'))
        svc=CanonicalPaymentService();order=await svc._get_order_by_id_for_update(c.db,str(oid))
        with c.db.no_autoflush:
            order.currency_snapshot=currency
            with pytest.raises(HTTPException) as exc:
                await svc._confirm_payment_for_locked_order(db=c.db,order=order,amount=Decimal('1'),method='cash',
                    transaction_id=None,idempotency_key=uuid.uuid4().hex,created_by=c.actor)
            assert exc.value.detail['code']=='PAYMENT_CURRENCY_UNVERIFIED'
        await c.db.rollback()
        assert await c.vector(oid)==before
        return
    r=await c.http_pay(oid,'1')
    assert (r.status_code,_errcode(r))==(409,'PAYMENT_CURRENCY_UNVERIFIED'),'R01_LEGACY_NEW_WRITE_REFUSED'
    assert await c.vector(oid)==before


async def test_exact_legacy_replay_is_zero_write_not_currency_acceptance(financial_case):
    c=financial_case;oid=await c.seed();key=uuid.uuid4().hex
    assert (await c.http_pay(oid,'1.50',key)).status_code==200
    await c.db.execute(text(f'UPDATE "{c.schema}".orders SET currency_snapshot=NULL WHERE id=:o'),{'o':oid});await c.db.commit()
    before=await c.vector(oid)
    canonical=await c.service_pay(oid,'1.50',key)
    assert canonical.replayed is True and await c.vector(oid)==before
    r=await c.http_pay(oid,'1.50',key)
    assert r.status_code==200,r.text
    assert await c.vector(oid)==before
    changed=await c.http_pay(oid,'2',key);assert changed.status_code==409
    assert await c.vector(oid)==before


async def test_known_currency_replay_still_rejects_illegal_precision(financial_case):
    c=financial_case;oid=await c.seed();key=uuid.uuid4().hex
    assert (await c.http_pay(oid,'1.50',key)).status_code==200
    await c.db.execute(text(f"UPDATE \"{c.schema}\".orders SET currency_snapshot='UGX' WHERE id=:o"),{'o':oid});await c.db.commit()
    before=await c.vector(oid)
    # The shared canonical replay, not the generic HTTP response cache. The
    # currency change is deliberately corrupt fixture history, not a product
    # operation; HTTP hot-cache behavior is retained separately as a gap.
    with pytest.raises(HTTPException) as exc:await c.service_pay(oid,'1.50',key)
    assert exc.value.status_code==400 and exc.value.detail['code']=='PAYMENT_AMOUNT_PRECISION'
    assert await c.vector(oid)==before


async def test_legacy_replay_does_not_relax_retailer_attribution(financial_case,two_tenants):
    c=financial_case;oid=await c.seed();key=uuid.uuid4().hex
    assert (await c.http_pay(oid,'1',key)).status_code==200
    other=(await c.db.execute(text('SELECT retailer_id FROM public.wholesaler_retailer_bindings WHERE tenant_user_id=:u'),{'u':two_tenants[6]})).scalar_one()
    await c.db.execute(text(f'UPDATE "{c.schema}".orders SET currency_snapshot=NULL WHERE id=:o'),{'o':oid})
    await c.db.execute(text(f'UPDATE "{c.schema}".payments SET retailer_id=:r WHERE order_id=:o'),{'o':oid,'r':other})
    await c.db.commit();before=await c.vector(oid)
    with pytest.raises(HTTPException) as exc:await c.service_pay(oid,'1',key)
    assert exc.value.status_code==409 and exc.value.detail['code']=='IDEMPOTENCY_KEY_CONFLICT'
    assert await c.vector(oid)==before


async def test_existing_key_cannot_cross_order(financial_case):
    c=financial_case;a=await c.seed();b=await c.seed();key=uuid.uuid4().hex
    assert (await c.http_pay(a,'1',key)).status_code==200
    before_a=await c.vector(a);before_b=await c.vector(b)
    r=await c.http_pay(b,'1',key)
    assert (r.status_code,_errcode(r))==(409,'IDEMPOTENCY_KEY_CONFLICT')
    assert await c.vector(a)==before_a and await c.vector(b)==before_b


async def test_post_write_fault_rolls_back_full_financial_vector(financial_case):
    c=financial_case;oid=await c.seed();before=await c.vector(oid)
    original=PaymentService._apply_outstanding_balance_delta
    async def fail_after_write(self,*args,**kwargs):
        await original(self,*args,**kwargs)
        raise RuntimeError('R01_POST_BINDING_WRITE_FAILURE')
    with patch.object(PaymentService,'_apply_outstanding_balance_delta',fail_after_write):
        with pytest.raises(RuntimeError,match='R01_POST_BINDING_WRITE_FAILURE'):
            await c.service_pay(oid,'1.25',receipt=True)
    assert await c.vector(oid)==before,'R01_FULL_CHAIN_ROLLBACK'
