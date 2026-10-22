"""M2 native authority, real PG transactions and native JWT/HTTP controls."""
import asyncio
from decimal import Decimal, localcontext
import json
from uuid import UUID, uuid4

from fastapi import HTTPException
import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError

from services.inventory_adjustment_service import InventoryAdjustmentService, adjustment_quantity
from services.inventory_service import InventoryService
from services.staff_management_service import StaffManagementService
from tests.staff_approval_support import staff_world as stock_world
from tests.test_staff_permissions import joined
from tests.test_inventory_manual_adjustment_http import inventory_http, login, error_code


def command(world, db, actor=None):
    db.info['_staff_stock_actor']=str(actor or world.actor)
    return InventoryAdjustmentService(db,world.wid,world.schema)


async def configured(world):
    uid,email,password=await joined(world)
    async with world.session() as db:
        staff=StaffManagementService(db,world.wid,world.schema)
        templates=await staff.templates(world.actor)
        template=next(t for t in templates if t['key']=='warehouse')
        await staff.edit_template(world.actor,'warehouse',template['permission_codes']+['inventory:adjustments:approve'],template['version'])
        service=command(world,db)
        policy=await service.policy(world.actor)
        await service.set_policy(world.actor,approver_ids=[world.actor,uid],owner_direct_enabled=True,
                                 expected_policy_version=policy['policy_version'])
    return uid,email,password


async def submit(world, actor, *, direct=False, delta='1', key=None):
    async with world.session() as db:
        service=command(world,db,actor)
        snap=await service.snapshot(actor,world.sku)
        body={'sellable_unit_id':world.sku,'quantity_delta':delta,'reason_kind':'correction','reason':'M2 observed correction',
              'expected_policy_version':snap['policy_version'],'expected_stock_revision':snap['stock_revision']}
        result=await service.submit(actor,key=key or uuid4().hex,direct=direct,**body)
    return result,body


async def decide(world, actor, row, action='approve', key=None):
    async with world.session() as db:
        return await command(world,db,actor).decide(actor,UUID(row['id']),action=action,key=key or uuid4().hex,
                                                   expected_version=row['version'])


async def facts(world):
    values=await world.snapshot()
    async with world.session() as db:
        values['requests']=list((await db.execute(text('SELECT row_to_json(r)::text FROM inventory_adjustment_requests r ORDER BY id'))).scalars())
        values['audit']=list((await db.execute(text('SELECT row_to_json(a)::text FROM public.staff_stock_audit_events a WHERE tenant_id=:t ORDER BY id'),{'t':world.wid})).scalars())
    return values


@pytest.mark.parametrize('first', ['adjustment', 'order_kernel'])
async def test_stock_lock_composition_with_order_kernel(stock_world, first):
    """Real joined locks, both arrival orders; no simulated database outcomes."""
    world = stock_world
    before = await facts(world)
    held, waiter_started, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    pids, outcomes = {}, {}

    async def participant(kind):
        leader = kind == first
        if not leader:
            await asyncio.wait_for(held.wait(), 10)
        try:
            async with world.session() as db:
                pids[kind] = await db.scalar(text('SELECT pg_backend_pid()'))
                await db.execute(text("SET LOCAL lock_timeout='8s'"))
                await db.execute(text("SET LOCAL statement_timeout='10s'"))
                if not leader:
                    waiter_started.set()
                if kind == 'adjustment':
                    original = db.execute
                    paused = False

                    async def observed(statement, *args, **kwargs):
                        nonlocal paused
                        answer = await original(statement, *args, **kwargs)
                        sql = str(statement).upper()
                        if (leader and not paused and ('FOR UPDATE' in sql or 'FOR SHARE' in sql)
                                and any(name in sql for name in ('INVENTORY_STOCKS', 'SKUS', 'CATALOG_PRODUCTS'))):
                            paused = True
                            held.set()
                            await asyncio.wait_for(release.wait(), 10)
                        return answer

                    db.execute = observed
                    await command(world, db).snapshot(world.actor, world.sku)
                else:
                    await InventoryService()._locked_stock_by_sku_id(
                        db, sku_id=world.sku, sku_code='INV-BOX', require_active=True)
                    if leader:
                        held.set()
                        await asyncio.wait_for(release.wait(), 10)
            outcomes[kind] = 'COMPLETED'
        except DBAPIError as error:
            outcomes[kind] = {'sqlstate': getattr(error.orig, 'sqlstate', None)
                             or getattr(error.orig, 'pgcode', None)}

    async def observer():
        await asyncio.wait_for(waiter_started.wait(), 10)
        waiting = 'order_kernel' if first == 'adjustment' else 'adjustment'
        deadline = asyncio.get_running_loop().time() + 5
        async with world.session() as db:
            while asyncio.get_running_loop().time() < deadline:
                blockers = await db.scalar(text('SELECT pg_blocking_pids(:pid)'), {'pid': pids[waiting]})
                if pids[first] in blockers:
                    release.set()
                    return
        raise AssertionError('M2_LOCK_ORCHESTRATION_NO_OBSERVED_WAITER')

    tasks = [asyncio.create_task(participant(kind)) for kind in ('adjustment', 'order_kernel')]
    tasks.append(asyncio.create_task(observer()))
    try:
        try:
            await asyncio.wait_for(asyncio.gather(*tasks), 20)
        except TimeoutError as error:
            raise AssertionError('M2_LOCK_ORCHESTRATION_TIMEOUT_NOT_PRODUCT_RED') from error
    finally:
        release.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    assert len(pids) == 2 and len(set(pids.values())) == 2, 'M2_LOCK_SESSIONS_NOT_INDEPENDENT'
    print('M2_LOCK_COMPOSITION_FACTS=' + json.dumps({'first': first, 'pids': pids, 'outcomes': outcomes}))
    assert await facts(world) == before, 'M2_LOCK_COMPOSITION_ECONOMIC_DRIFT'
    assert outcomes == {'adjustment': 'COMPLETED', 'order_kernel': 'COMPLETED'}, (
        'M2_ORDER_STOCK_LOCK_COMPOSITION: ' + json.dumps(outcomes))


@pytest.mark.parametrize('value',['0','0.001','NaN','Infinity','-Infinity','10000000000','1e-1000000'])
def test_quantity_contract(value):
    with pytest.raises(HTTPException) as error: adjustment_quantity(value,'correction')
    assert error.value.detail['code']=='INVALID_ADJUSTMENT_QUANTITY'


def test_decimal_context_and_signed_intents():
    with localcontext() as context:
        context.prec=2
        assert adjustment_quantity('9999999999.9900','gain')==Decimal('9999999999.99')
    for delta,kind in [('1','loss'),('-1','gain'),('1','unknown')]:
        with pytest.raises(HTTPException): adjustment_quantity(delta,kind)


async def test_request_has_no_economics_and_no_other_approver_rejects(stock_world):
    world=stock_world
    before=await facts(world)
    with pytest.raises(HTTPException) as error: await submit(world,world.actor)
    assert error.value.detail['code']=='NO_ELIGIBLE_APPROVER'
    assert await facts(world)==before
    uid,_,_=await configured(world)
    before=await world.snapshot()
    row,_=await submit(world,uid)
    assert row['status']=='pending' and await world.snapshot()==before


async def test_employee_and_owner_self_approval_are_forbidden(stock_world):
    world=stock_world
    uid,_,_=await configured(world)
    for actor in (uid,world.actor):
        row,_=await submit(world,actor)
        before=await facts(world)
        refused=False
        try: await decide(world,actor,row)
        except HTTPException as error: refused=error.status_code==403 and error.detail['code']=='SELF_APPROVAL_FORBIDDEN'
        assert refused,'M2_SELF_APPROVAL_ACCEPTED'
        assert await facts(world)==before


async def test_named_approver_is_additional_to_job_permission(stock_world):
    world=stock_world
    uid,_,_=await configured(world)
    other,_,_=await joined(world)
    row,_=await submit(world,uid)
    before=await facts(world)
    with pytest.raises(HTTPException) as error: await decide(world,other,row)
    assert error.value.detail['code']=='ADJUSTMENT_APPROVER_REQUIRED'
    assert await facts(world)==before


async def test_two_independent_sessions_approve_exactly_once(stock_world):
    world=stock_world
    uid,_,_=await configured(world)
    row,_=await submit(world,uid)
    ready=asyncio.Event()
    arrived=0
    async def attempt():
        nonlocal arrived
        arrived+=1
        if arrived==2:ready.set()
        await asyncio.wait_for(ready.wait(),10)
        try:return await decide(world,world.actor,row)
        except HTTPException as error:return error.detail['code']
    tasks=[asyncio.create_task(attempt()) for _ in range(2)]
    try: results=await asyncio.wait_for(asyncio.gather(*tasks),20)
    finally:
        for task in tasks:
            if not task.done():task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
    assert sum(isinstance(r,dict) and r['status']=='approved_applied' for r in results)==1
    assert results.count('ADJUSTMENT_ALREADY_DECIDED')==1
    assert await world.stock()==(Decimal('101'),Decimal('0'))
    async with world.session() as db:
        assert await db.scalar(text('SELECT count(*) FROM inventory_movements WHERE manual_adjustment_id=:r'),{'r':UUID(row['id'])})==1
        assert await db.scalar(text("SELECT count(*) FROM public.staff_stock_audit_events WHERE tenant_id=:t AND event_type='adjustment_approved_applied'"),{'t':world.wid})==1


@pytest.mark.parametrize('action',['reject','withdraw'])
async def test_reject_and_withdraw_have_no_economics(stock_world,action):
    uid,_,_=await configured(stock_world)
    row,_=await submit(stock_world,uid)
    before=await stock_world.snapshot()
    result=await decide(stock_world,uid if action=='withdraw' else stock_world.actor,row,action)
    assert result['status']==('withdrawn' if action=='withdraw' else 'rejected')
    assert await stock_world.snapshot()==before


async def test_owner_direct_is_explicit_audited_and_switchable(stock_world):
    world=stock_world
    key=uuid4().hex
    row,body=await submit(world,world.actor,direct=True,key=key)
    assert row['status']=='applied_direct' and row['decision_actor_id']==str(world.actor)
    assert await world.stock()==(Decimal('101'),Decimal('0'))
    async with world.session() as db:
        service=command(world,db)
        policy=await service.policy(world.actor)
        await service.set_policy(world.actor,approver_ids=[world.actor],owner_direct_enabled=False,expected_policy_version=policy['policy_version'])
    before=await facts(world)
    with pytest.raises(HTTPException) as error:await submit(world,world.actor,direct=True)
    assert error.value.detail['code']=='OWNER_DIRECT_DISABLED'
    assert await facts(world)==before
    with pytest.raises(HTTPException) as error:
        async with world.session() as db:await command(world,db).submit(world.actor,key=key,direct=True,**body)
    assert error.value.detail['code']=='OWNER_DIRECT_DISABLED'
    assert await facts(world)==before


async def test_admin_alias_cannot_use_owner_direct(stock_world):
    from core.security import hash_password
    world=stock_world
    async with world.session() as db:
        alias=await db.scalar(text("INSERT INTO users(email,password_hash,is_active) VALUES (:e,:p,true) RETURNING id"),
                              {'e':uuid4().hex+'@example.com','p':hash_password(uuid4().hex)})
        await db.execute(text("INSERT INTO user_roles(user_id,role_id) SELECT :u,id FROM roles WHERE name='admin'"),{'u':alias})
    before=await facts(world)
    refused=False
    try:
        async with world.session() as db:
            snap=await command(world,db).snapshot(world.actor,world.sku)
            await command(world,db,alias).submit(alias,key=uuid4().hex,direct=True,sellable_unit_id=world.sku,
                quantity_delta='1',reason_kind='gain',reason='alias control',
                expected_policy_version=snap['policy_version'],expected_stock_revision=snap['stock_revision'])
    except HTTPException as error:refused=error.detail['code']=='OWNER_REQUIRED'
    assert refused,'M2_ADMIN_ALIAS_DIRECT'
    assert await facts(world)==before


async def test_legacy_service_and_http_are_closed(stock_world,inventory_http):
    client,headers,_=inventory_http
    before=await facts(stock_world)
    refused=False
    try:
        async with stock_world.session() as db:
            await InventoryService().adjust_stock(db,sku_code='INV-BOX',quantity=Decimal('1'),reason='legacy',
                adjusted_by=str(stock_world.actor),tenant_id=str(stock_world.wid),tenant_schema=stock_world.schema)
    except HTTPException as error:refused=error.detail['code']=='MANUAL_ADJUSTMENT_REQUEST_REQUIRED'
    assert refused,'M2_LEGACY_SERVICE_OPEN'
    response=await client.post('/api/v1/inventory/adjust',headers=headers,json={'sku_code':'INV-BOX','quantity':'1','reason':'legacy'})
    assert response.status_code==409 and error_code(response)=='MANUAL_ADJUSTMENT_REQUEST_REQUIRED','M2_LEGACY_HTTP_OPEN'
    assert await facts(stock_world)==before


async def test_revision_rejects_change_then_restore_but_not_metadata(stock_world):
    world=stock_world
    uid,_,_=await configured(world)
    row,_=await submit(world,uid)
    async with world.session() as db:
        original=await db.scalar(text('SELECT stock_revision FROM inventory_stocks'))
        await db.execute(text('UPDATE inventory_stocks SET quantity_reserved=1'))
        await db.execute(text('UPDATE inventory_stocks SET quantity_reserved=0'))
        assert await db.scalar(text('SELECT stock_revision FROM inventory_stocks'))==original+2
    before=await facts(world)
    refused=False
    try:await decide(world,world.actor,row)
    except HTTPException as error:refused=error.detail['code']=='STOCK_CHANGED'
    assert refused,'M2_REVERTED_STOCK_APPROVED'
    assert await facts(world)==before
    fresh,_=await submit(world,uid)
    async with world.session() as db:
        revision=await db.scalar(text('SELECT stock_revision FROM inventory_stocks'))
        await db.execute(text('UPDATE inventory_stocks SET updated_at=now()'))
        assert await db.scalar(text('SELECT stock_revision FROM inventory_stocks'))==revision
    assert (await decide(world,world.actor,fresh))['status']=='approved_applied'


async def test_policy_invalidation_is_specific_and_stale_can_be_rejected(stock_world):
    world=stock_world
    uid,_,_=await configured(world)
    row,_=await submit(world,uid)
    async with world.session() as db:
        staff=StaffManagementService(db,world.wid,world.schema)
        member=await staff.member(uid)
        version=(await command(world,db).policy(world.actor))['policy_version']
        await staff.edit_member(world.actor,uid,expected_version=member['version'],full_name='Name only')
        assert (await command(world,db).policy(world.actor))['policy_version']==version
        member=await staff.member(uid)
        await staff.edit_member(world.actor,uid,expected_version=member['version'],is_active=False)
        assert (await command(world,db).policy(world.actor))['policy_version']==version+1
    before=await facts(world)
    with pytest.raises(HTTPException):await decide(world,world.actor,row)
    assert await facts(world)==before
    assert (await decide(world,world.actor,row,'reject'))['status']=='rejected'


async def test_real_success_replay_then_live_revocation_refuses(stock_world,inventory_http):
    world=stock_world
    uid,email,password=await configured(world)
    client,owner_headers,_=inventory_http
    employee_headers=await login(client,world,email=email,password=password)
    # Owner submits; the employee is a different, named approver.
    row,_=await submit(world,world.actor)
    url='/api/v1/inventory/adjustment-requests/'+row['id']+'/approve'
    body={'expected_version':1,'reason':''}
    headers={**employee_headers,'Idempotency-Key':uuid4().hex}
    first=await client.post(url,headers=headers,json=body)
    assert first.status_code==200,first.text
    before=await facts(world)
    replay=await client.post(url,headers=headers,json=body)
    assert replay.status_code==200 and replay.json()['data']['replayed'] is True
    assert await facts(world)==before
    async with world.session() as db:
        staff=StaffManagementService(db,world.wid,world.schema)
        template=next(t for t in await staff.templates(world.actor) if t['key']=='warehouse')
    # Real product permission revocation, not a test-only permission patch.
    revoke=await client.put('/api/v1/staff/role-templates/warehouse',headers=owner_headers,
        json={'permission_codes':[c for c in template['permission_codes'] if c!='inventory:adjustments:approve'],
              'expected_version':template['version']})
    assert revoke.status_code==200
    before=await facts(world)
    refused=await client.post(url,headers=headers,json=body)
    assert refused.status_code==403,'M2_REVOKED_SUCCESS_REPLAYED'
    assert await facts(world)==before


@pytest.mark.parametrize('fault',['stock','movement','audit','terminal','commit'])
async def test_every_failure_rolls_back_full_vector(stock_world,fault):
    world=stock_world
    before=await facts(world)
    reached=[]
    def observer(_c,_cu,sql,_p,_ctx,_many):
        target={'stock':'UPDATE "'+world.schema+'".inventory_stocks','movement':'INSERT INTO "'+world.schema+'".inventory_movements',
                'audit':'INSERT INTO public.staff_stock_audit_events','terminal':'UPDATE "'+world.schema+'".inventory_adjustment_requests'}
        if fault!='commit' and target[fault] in sql:
            reached.append(fault);raise RuntimeError('M2_FAULT_'+fault)
    event.listen(world.engine.sync_engine,'after_cursor_execute',observer)
    caught=False
    try:
        try:
            async with world.session() as db:
                if fault=='commit':
                    async def failed_commit():
                        reached.append('commit');raise RuntimeError('M2_FAULT_commit')
                    db.commit=failed_commit
                service=command(world,db)
                snap=await service.snapshot(world.actor,world.sku)
                await service.submit(world.actor,key=uuid4().hex,direct=True,sellable_unit_id=world.sku,
                    quantity_delta='1',reason_kind='gain',reason='failure control',
                    expected_policy_version=snap['policy_version'],expected_stock_revision=snap['stock_revision'])
        except RuntimeError as error:
            if str(error)!='M2_FAULT_'+fault:raise
            caught=True
    finally:event.remove(world.engine.sync_engine,'after_cursor_execute',observer)
    assert caught,'M2_AUDIT_FAILURE_SWALLOWED' if fault=='audit' else 'M2_FAILURE_NOT_PROPAGATED'
    assert reached==[fault],'M2_AUDIT_FAILURE_SWALLOWED' if fault=='audit' else 'M2_FAILURE_NOT_REACHED'
    assert await facts(world)==before,'M2_PARTIAL_ECONOMIC_COMMIT'


async def test_terminal_payload_movement_and_audit_are_immutable(stock_world):
    world=stock_world
    row,_=await submit(world,world.actor,direct=True)
    before=await facts(world)
    for statement in (
        'UPDATE inventory_adjustment_requests SET payload=payload',
        'DELETE FROM inventory_adjustment_requests',
        'UPDATE inventory_movements SET quantity=quantity WHERE manual_adjustment_id IS NOT NULL',
        'DELETE FROM inventory_movements WHERE manual_adjustment_id IS NOT NULL',
        'UPDATE public.staff_stock_audit_events SET details=details WHERE tenant_id=:t',
    ):
        with pytest.raises(DBAPIError):
            async with world.session() as db:await db.execute(text(statement),{'t':world.wid})
    assert await facts(world)==before


async def test_missing_stock_and_key_conflict_have_no_writes(stock_world):
    world=stock_world
    key=uuid4().hex
    row,body=await submit(world,world.actor,direct=True,key=key)
    before=await facts(world)
    async with world.session() as db:
        replay=await command(world,db).submit(world.actor,key=key,direct=True,**body)
        assert replay['replayed'] and replay['id']==row['id']
    assert await facts(world)==before
    with pytest.raises(HTTPException) as error:
        async with world.session() as db:await command(world,db).submit(world.actor,key=key,direct=True,**{**body,'quantity_delta':'2'})
    assert error.value.detail['code']=='IDEMPOTENCY_KEY_CONFLICT'
    assert await facts(world)==before


async def test_real_order_reserve_release_is_still_a_revision_change(stock_world):
    from services.order_command_service import OrderCommandService
    world=stock_world
    uid,_,_=await configured(world)
    row,_=await submit(world,uid)
    order_id=await world.reserve(1)
    async with world.session() as db:
        await OrderCommandService(db).cancel_order(UUID(str(order_id)),updated_by=str(world.actor))
    assert await world.stock()==(Decimal('100'),Decimal('0'))
    before=await facts(world)
    with pytest.raises(HTTPException) as error:await decide(world,world.actor,row)
    assert error.value.detail['code']=='STOCK_CHANGED'
    assert await facts(world)==before


async def test_cross_tenant_missing_stock_and_sellability_changes_fail_closed(stock_world):
    from tests.staff_approval_support import StaffWorld
    world=stock_world
    uid,_,_=await configured(world)
    row,_=await submit(world,uid)
    async with world.session() as db:await db.execute(text('UPDATE skus SET is_active=false WHERE id=:s'),{'s':world.sku})
    before=await facts(world)
    with pytest.raises(HTTPException) as error:await decide(world,world.actor,row)
    assert error.value.status_code==409 and error.value.detail['code']=='STOCK_CHANGED'
    assert await facts(world)==before
    other=StaffWorld()
    try:
        await other.initialize()
        other_before=await facts(other)
        with pytest.raises(HTTPException) as error:await decide(other,other.actor,row)
        assert error.value.status_code==404
        assert await facts(other)==other_before and await facts(world)==before
    finally:await other.engine.dispose()


async def test_missing_stock_cannot_be_created_by_submission(stock_world):
    world=stock_world
    async with world.session() as db:await db.execute(text('DELETE FROM inventory_stocks WHERE sku_id=:s'),{'s':world.sku})
    before=await facts(world)
    with pytest.raises(HTTPException) as error:
        async with world.session() as db:
            await command(world,db).submit(world.actor,key=uuid4().hex,direct=True,sellable_unit_id=world.sku,
                quantity_delta='1',reason_kind='gain',reason='missing stock',expected_policy_version=1,expected_stock_revision=1)
    assert error.value.detail['code']=='STOCK_NOT_INITIALIZED'
    assert await facts(world)==before
