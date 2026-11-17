"""Owner-requested mailbox recovery over actual routes/JWT and task PostgreSQL."""
import asyncio
import json
import secrets
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, text

from services.staff_management_service import StaffManagementService
from services.staff_credential_service import StaffCredentialService
from services.email_delivery import get_dev_staff_email_deliveries, get_dev_staff_recovery_deliveries
from tests.test_session_credential_revocation import (
    live_session_world, _identity, _context, _me, _join_copy,
)

pytestmark=pytest.mark.integration
PUBLIC='/api/v1/auth/staff/recover-credential'


async def employee(w):
    email=secrets.token_hex(12)+'@example.com';password=secrets.token_urlsafe(24)
    async with w.session() as db:
        member=await StaffManagementService(db,w.wid,w.schema).create_member(w.actor,email=email,
            full_name='Recovery employee',template_key='sales',create_key=uuid4().hex)
    async with w.session() as db:
        await StaffCredentialService(db).invite(tenant_id=w.wid,schema=w.schema,actor_id=w.actor,
            user_id=UUID(member['id']),owner_password=w.password,expected_version=member['version'])
    raw=get_dev_staff_email_deliveries(email)[-1].token
    async with w.session() as db:
        await StaffCredentialService(db).consume(raw,password)
    async with w.session() as db:
        row=await StaffManagementService(db,w.wid,w.schema).member(UUID(member['id']))
    return SimpleNamespace(actor=UUID(member['id']),email=email,password=password,wid=w.wid,session=w.session),row


async def snapshot(w,uid):
    async with w.session() as db:
        user=tuple((await db.execute(text('SELECT password_hash,credential_epoch,is_active,is_deleted FROM users WHERE id=:u'),{'u':uid})).one())
        member=await db.scalar(text('SELECT to_jsonb(m) FROM staff_memberships m WHERE user_id=:u'),{'u':uid})
        grants=(await db.execute(text('SELECT role_id::text FROM user_roles WHERE user_id=:u ORDER BY 1'),{'u':uid})).scalars().all()
        bindings=(await db.execute(text('SELECT to_jsonb(b) FROM public.wholesaler_retailer_bindings b WHERE wholesaler_id=:t ORDER BY id'),{'t':w.wid})).scalars().all()
    return {'user':user,'member':member,'grants':grants,'bindings':bindings}


async def issue(c,w,row,owner=None,**changes):
    if owner is None: owner=await _context(c,await _identity(c,w),w.wid)
    body={'expected_version':row['version'],'owner_password':w.password};body.update(changes)
    return await c.post('/api/v1/staff/'+row['id']+'/credential-recovery',json=body,
        headers={'Authorization':'Bearer '+owner['access_token']})


async def consume(c,raw,password=None,**kwargs):
    return await c.post(PUBLIC,json={'recovery_token':raw,'new_password':password or secrets.token_urlsafe(24)},**kwargs)


class TestOwnerStaffRecovery:
    async def test_success_shared_identity_no_authority_change_and_old_sessions_revoked(self,live_session_world):
        from tests.staff_approval_support import StaffWorld
        w,c,_=live_session_world;target,row=await employee(w);other=StaffWorld()
        try:
            await other.initialize();uid=await _join_copy(other,target)
            identity=await _identity(c,target)
            pairs=[identity,await _context(c,identity,w.wid),await _context(c,identity,other.wid)]
            before=await snapshot(w,target.actor);before_b=await snapshot(other,uid)
            # The foreign UUID really exists and has a valid local membership.
            async with other.session() as db:
                foreign=await StaffManagementService(db,other.wid,other.schema).member(uid)
            assert (await issue(c,w,foreign)).status_code==404
            r=await issue(c,w,row);assert r.status_code==202 and r.json()['data']['delivery']=='accepted_not_confirmed'
            mail=get_dev_staff_recovery_deliveries(target.email)[-1]
            assert mail.token not in r.text and mail.link not in r.text
            assert (await snapshot(w,target.actor))==before and (await snapshot(other,uid))==before_b
            assert (await _me(c,pairs[2]['access_token'])).status_code==200
            async with w.session() as db:
                token=(await db.execute(text('SELECT * FROM public.staff_credential_recovery_tokens WHERE user_id=:u'),{'u':target.actor})).mappings().one()
                assert token['token_hash']!=mail.token and len(token['token_hash'])==64
                assert (token['expires_at']-token['created_at']).total_seconds()==900
                assert token['target_credential_epoch']==before['user'][1]
            password=secrets.token_urlsafe(24);headers={'X-Idempotency-Key':uuid4().hex}
            r=await consume(c,mail.token,password,headers=headers)
            assert r.status_code==200 and r.json()['data']=={'action':'password_recovered','login_required':True}
            assert 'access_token' not in r.text and 'refresh_token' not in r.text
            for world,user,old in [(w,target.actor,before),(other,uid,before_b)]:
                after=await snapshot(world,user)
                assert after['user'][1]==old['user'][1]+1 and after['user'][2:]==old['user'][2:]
                assert {k:v for k,v in after.items() if k!='user'}=={k:v for k,v in old.items() if k!='user'}
            for pair in pairs:
                assert (await _me(c,pair['access_token'])).status_code==401
                assert (await c.post('/api/v1/auth/refresh',json={'refresh_token':pair['refresh_token']})).status_code==401
            assert (await c.post('/api/v1/auth/login',json={'email':target.email,'password':target.password})).status_code==401
            current=await _identity(c,target,password)
            assert (await _me(c,(await _context(c,current,other.wid))['access_token'])).status_code==200
            repeated=await consume(c,mail.token,password,headers=headers)
            assert repeated.status_code==401 and repeated.headers.get('X-Idempotency-Replayed') is None
        finally: await other.engine.dispose()

    @pytest.mark.parametrize('case',['nonowner','admin_alias','identity_only','wrong_password','stale','owner_self','foreign','pending','disabled'])
    async def test_request_authority_and_eligibility(self,live_session_world,case):
        w,c,_=live_session_world;target,row=await employee(w);before=await snapshot(w,target.actor);n=len(get_dev_staff_recovery_deliveries(target.email));changes={};owner=None
        expected={'nonowner':403,'admin_alias':403,'identity_only':403,'wrong_password':403,'stale':409,'owner_self':409,'foreign':404,'pending':409,'disabled':409}[case]
        if case=='nonowner':owner=await _context(c,await _identity(c,target),w.wid)
        if case=='identity_only':owner=await _identity(c,w)
        if case=='admin_alias':
            async with w.session() as db:
                result=await db.execute(text("INSERT INTO user_roles(user_id,role_id) SELECT :u,id FROM roles WHERE name='admin' AND is_deleted IS FALSE ON CONFLICT DO NOTHING"),{'u':target.actor})
                assert result.rowcount==1
            before=await snapshot(w,target.actor)
            owner=await _context(c,await _identity(c,target),w.wid)
        if case=='wrong_password':changes['owner_password']='incorrect-owner-password'
        if case=='stale':changes['expected_version']=row['version']+1
        if case=='owner_self':row={**row,'id':str(w.actor)}
        if case=='foreign':row={**row,'id':str(uuid4())}
        if case in {'pending','disabled'}:
            async with w.session() as db:
                manager=StaffManagementService(db,w.wid,w.schema)
                if case=='disabled':row=await manager.edit_member(w.actor,target.actor,expected_version=row['version'],is_active=False)
                else:
                    invited=await StaffCredentialService(db).invite(tenant_id=w.wid,schema=w.schema,actor_id=w.actor,
                        user_id=target.actor,owner_password=w.password,expected_version=row['version']);row=invited['member']
            before=await snapshot(w,target.actor)
        r=await issue(c,w,row,owner,**changes);assert r.status_code==expected,(case,r.status_code,r.text)
        assert len(get_dev_staff_recovery_deliveries(target.email))==n
        assert await snapshot(w,target.actor)==before

    @pytest.mark.parametrize('case',['unknown','setup_purpose','expired','revoked'])
    async def test_nonactionable_mailbox_proofs(self,live_session_world,case):
        w,c,_=live_session_world;target,row=await employee(w);assert (await issue(c,w,row)).status_code==202
        raw=get_dev_staff_recovery_deliveries(target.email)[-1].token
        if case=='unknown':raw=secrets.token_urlsafe(32)
        pending=None
        if case=='setup_purpose':
            email=secrets.token_hex(12)+'@example.com'
            async with w.session() as db:
                pending=await StaffManagementService(db,w.wid,w.schema).create_member(w.actor,email=email,
                    full_name='Pending proof contrast',template_key='sales',create_key=uuid4().hex)
            async with w.session() as db:
                await StaffCredentialService(db).invite(tenant_id=w.wid,schema=w.schema,actor_id=w.actor,
                    user_id=UUID(pending['id']),owner_password=w.password,expected_version=pending['version'])
            raw=get_dev_staff_email_deliveries(email)[-1].token
        if case in {'expired','revoked'}:
            async with w.session() as db:
                sql="created_at=now()-interval '1 hour',expires_at=now()-interval '1 minute'" if case=='expired' else 'revoked_at=now()'
                await db.execute(text('UPDATE public.staff_credential_recovery_tokens SET '+sql+' WHERE user_id=:u'),{'u':target.actor})
        before=await snapshot(w,target.actor);r=await consume(c,raw)
        assert r.status_code==401 and r.json()['code']=='INVALID_OR_EXPIRED_STAFF_RECOVERY_TOKEN'
        assert await snapshot(w,target.actor)==before
        if pending is not None:
            # Same proof is genuinely actionable at its original purpose.
            async with w.session() as db:
                assert await StaffCredentialService(db).consume(raw,secrets.token_urlsafe(24))=={'action':'joined'}

    async def test_cooldown_and_only_latest_link(self,live_session_world):
        w,c,_=live_session_world;target,row=await employee(w);owner=await _context(c,await _identity(c,w),w.wid)
        assert (await issue(c,w,row,owner)).status_code==202
        first=get_dev_staff_recovery_deliveries(target.email)[-1].token
        assert (await issue(c,w,row,owner)).status_code==429
        assert len(get_dev_staff_recovery_deliveries(target.email))==1
        async with w.session() as db:
            await db.execute(text("UPDATE public.staff_credential_recovery_tokens SET created_at=now()-interval '61 seconds' WHERE user_id=:u"),{'u':target.actor})
        assert (await issue(c,w,row,owner)).status_code==202
        second=get_dev_staff_recovery_deliveries(target.email)[-1].token;assert second!=first
        assert (await consume(c,first)).status_code==401
        assert (await consume(c,second)).status_code==200

    @pytest.mark.parametrize('change',['disable_restore','role','password'])
    async def test_changed_member_or_credential_does_not_resurrect_link(self,live_session_world,change):
        from tests.test_session_credential_revocation import _reset_credential
        w,c,_=live_session_world;target,row=await employee(w);assert (await issue(c,w,row)).status_code==202
        raw=get_dev_staff_recovery_deliveries(target.email)[-1].token
        if change=='password':await _reset_credential(target,secrets.token_urlsafe(24))
        else:
            async with w.session() as db:
                manager=StaffManagementService(db,w.wid,w.schema)
                if change=='role':await manager.edit_member(w.actor,target.actor,expected_version=row['version'],template_key='finance')
                else:
                    disabled=await manager.edit_member(w.actor,target.actor,expected_version=row['version'],is_active=False)
                    await manager.edit_member(w.actor,target.actor,expected_version=disabled['version'],is_active=True)
        before=await snapshot(w,target.actor);assert (await consume(c,raw)).status_code==401
        assert await snapshot(w,target.actor)==before

    async def test_concurrent_consumption_is_exactly_once(self,live_session_world):
        w,c,_=live_session_world;target,row=await employee(w);assert (await issue(c,w,row)).status_code==202
        raw=get_dev_staff_recovery_deliveries(target.email)[-1].token;p1,p2=secrets.token_urlsafe(24),secrets.token_urlsafe(24)
        responses=await asyncio.gather(consume(c,raw,p1),consume(c,raw,p2))
        assert sorted(r.status_code for r in responses)==[200,401]
        winning=p1 if responses[0].status_code==200 else p2;losing=p2 if winning==p1 else p1
        assert (await _me(c,(await _identity(c,target,winning))['access_token'])).status_code==200
        assert (await c.post('/api/v1/auth/login',json={'email':target.email,'password':losing})).status_code==401
        async with w.session() as db:
            assert await db.scalar(text("SELECT count(*) FROM public.staff_stock_audit_events WHERE tenant_id=:t AND subject_id=:u AND event_type='staff_recovery_completed'"),{'t':w.wid,'u':target.actor})==1

    @pytest.mark.parametrize('fault',['second_copy','audit','mail'])
    async def test_transaction_failures_preserve_all_copies_and_token(self,live_session_world,monkeypatch,fault):
        from tests.staff_approval_support import StaffWorld
        import services.email_delivery as delivery
        w,c,_=live_session_world;target,row=await employee(w);other=StaffWorld();installed=False
        try:
            await other.initialize();uid=await _join_copy(other,target)
            before=await snapshot(w,target.actor);b=await snapshot(other,uid)
            if fault=='mail':
                def reject(**kwargs):raise RuntimeError('synthetic-mail-failure')
                with monkeypatch.context() as patch:
                    patch.setattr(delivery,'record_staff_recovery_email',reject)
                    assert (await issue(c,w,row)).status_code==503
                async with w.session() as db:
                    assert await db.scalar(text('SELECT count(*) FROM public.staff_credential_recovery_tokens WHERE user_id=:u'),{'u':target.actor})==0
                assert await snapshot(w,target.actor)==before and await snapshot(other,uid)==b
                return
            assert (await issue(c,w,row)).status_code==202;raw=get_dev_staff_recovery_deliveries(target.email)[-1].token
            if fault=='second_copy':
                async with other.session() as db:
                    await db.execute(text(f'CREATE FUNCTION "{other.schema}".reject_recovery() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION \'RECOVERY_TEST_WRITE_FAILED\'; END; $$'))
                    await db.execute(text(f'CREATE TRIGGER reject_recovery BEFORE UPDATE OF password_hash ON "{other.schema}".users FOR EACH ROW EXECUTE FUNCTION "{other.schema}".reject_recovery()'))
                installed=True
            if fault=='audit':
                from database.session import async_engine
                observed=[]
                def refuse(connection,cursor,statement,parameters,context,many):
                    values=parameters.values() if isinstance(parameters,dict) else parameters
                    if statement.startswith('INSERT INTO public.staff_stock_audit_events') and 'staff_recovery_completed' in values:
                        observed.append('ACTUAL_AUDIT_INSERT_DRIVER_BOUNDARY')
                        raise RuntimeError('synthetic-audit-driver-failure')
                event.listen(async_engine.sync_engine,'before_cursor_execute',refuse)
                try:
                    assert (await consume(c,raw)).status_code==503
                    assert observed==['ACTUAL_AUDIT_INSERT_DRIVER_BOUNDARY']
                finally:event.remove(async_engine.sync_engine,'before_cursor_execute',refuse)
            else:assert (await consume(c,raw)).status_code==503
            assert await snapshot(w,target.actor)==before and await snapshot(other,uid)==b
            async with w.session() as db:
                assert await db.scalar(text('SELECT used_at IS NULL FROM public.staff_credential_recovery_tokens WHERE user_id=:u'),{'u':target.actor}) is True
        finally:
            if installed:
                async with other.session() as db:
                    await db.execute(text(f'DROP TRIGGER reject_recovery ON "{other.schema}".users'))
                    await db.execute(text(f'DROP FUNCTION "{other.schema}".reject_recovery()'))
            await other.engine.dispose()

    async def test_sensitive_validation_and_query_never_echo_body(self,live_session_world,caplog):
        w,c,_=live_session_world;sentinel=secrets.token_urlsafe(28)
        r=await c.post(PUBLIC,json={'recovery_token':sentinel,'new_password':sentinel,'unexpected':{sentinel:sentinel}})
        assert r.status_code==422 and sentinel not in r.text and sentinel not in caplog.text
        r=await c.post(PUBLIC+'?token='+sentinel,json={'recovery_token':sentinel,'new_password':sentinel})
        assert r.status_code==422 and sentinel not in r.text

    async def test_recovery_table_constraints_and_runtime_grants(self,live_session_world):
        from scripts.bootstrap_tenant_schema import _assert_staff_recovery_contract
        w,_,_=live_session_world
        async with w.engine.connect() as db:
            await _assert_staff_recovery_contract(db)
            assert await db.scalar(text("SELECT version_num FROM public.alembic_version"))=='046_staff_credential_recovery'
            assert await db.scalar(text("SELECT has_table_privilege(current_user,'public.staff_credential_recovery_tokens','DELETE')")) is False

    async def test_inactive_copy_and_retailer_binding_are_not_reactivated(self,live_session_world):
        from tests.staff_approval_support import StaffWorld
        w,c,_=live_session_world;target,row=await employee(w);other=StaffWorld()
        try:
            await other.initialize();uid=await _join_copy(other,target)
            async with other.session() as db:
                manager=StaffManagementService(db,other.wid,other.schema);m=await manager.member(uid)
                await manager.edit_member(other.actor,uid,expected_version=m['version'],is_active=False)
                # Independently declared task-only inactive mapping; recovery
                # must neither activate it nor write the excluded user copy.
                await db.execute(text("UPDATE public.wholesaler_retailer_bindings SET tenant_user_id=:u,status='inactive' WHERE wholesaler_id=:t AND retailer_id=:r"),{'u':uid,'t':other.wid,'r':other.retailer})
            before=await snapshot(other,uid)
            assert (await issue(c,w,row)).status_code==202
            assert (await consume(c,get_dev_staff_recovery_deliveries(target.email)[-1].token)).status_code==200
            assert await snapshot(other,uid)==before
        finally:await other.engine.dispose()

    async def test_customer_mapping_cannot_use_employee_recovery(self,live_session_world):
        w,c,_=live_session_world;target,row=await employee(w)
        async with w.session() as db:
            await db.execute(text("UPDATE public.wholesaler_retailer_bindings SET tenant_user_id=:u,status='inactive' WHERE wholesaler_id=:t AND retailer_id=:r"),{'u':target.actor,'t':w.wid,'r':w.retailer})
        before=await snapshot(w,target.actor)
        r=await issue(c,w,row)
        assert r.status_code==400 and r.json()['code']=='STAFF_CREDENTIAL_PROOF_FAILED'
        assert not get_dev_staff_recovery_deliveries(target.email)
        assert await snapshot(w,target.actor)==before

    async def test_expiry_is_rechecked_after_actual_user_row_wait(self,live_session_world,caplog):
        from database.session import async_engine
        w,c,_=live_session_world;target,row=await employee(w)
        assert (await issue(c,w,row)).status_code==202
        raw=get_dev_staff_recovery_deliveries(target.email)[-1].token
        before=await snapshot(w,target.actor);reached=asyncio.Event();task=None;waiter=None
        def observe(connection,cursor,statement,parameters,context,many):
            values=parameters.values() if isinstance(parameters,dict) else parameters
            if (statement.startswith('SELECT email,password_hash,credential_epoch')
                    and f'FROM "{w.schema}".users ' in statement and 'FOR UPDATE' in statement
                    and target.actor in values):
                reached.set()
        event.listen(async_engine.sync_engine,'before_cursor_execute',observe)
        try:
            async with w.session() as blocker:
                await blocker.execute(text('SELECT id FROM users WHERE id=:u FOR UPDATE'),{'u':target.actor})
                # Start the short fixture TTL only AFTER the snapshot and
                # blocker are ready. Domain discovery is real work, not part
                # of the intended user-row wait. Five seconds also keeps the
                # actual row wait below the unchanged production lock_timeout.
                async with w.session() as setup:
                    expiry=await setup.scalar(text("UPDATE public.staff_credential_recovery_tokens SET expires_at=clock_timestamp()+interval '5 seconds' WHERE user_id=:u RETURNING expires_at"),{'u':target.actor})
                task=asyncio.create_task(consume(c,raw))
                # Actual production SQL proves the early token check passed;
                # keep that exact user row locked until the DB clock expires.
                waiter=asyncio.create_task(reached.wait())
                done,_=await asyncio.wait({task,waiter},timeout=10,return_when=asyncio.FIRST_COMPLETED)
                assert waiter in done and waiter.result(), {
                    'precondition':'TARGET_USER_LOCK_NOT_REACHED',
                    'response_status':task.result().status_code if task.done() else None,
                    'fixed_reasons':[getattr(record,'event_class',None) for record in caplog.records
                                     if record.name=='api.v1.auth'],
                }
                for _ in range(120):
                    expired=await blocker.scalar(text('SELECT clock_timestamp()>=:x'),{'x':expiry})
                    if expired:break
                    await asyncio.sleep(.05)
                assert expired is True
            r=await asyncio.wait_for(task,15)
            assert r.status_code==401 and r.json()['code']=='INVALID_OR_EXPIRED_STAFF_RECOVERY_TOKEN'
            assert any(getattr(record,'event_class',None)=='EXPIRED_AFTER_ROW_LOCKS' for record in caplog.records)
            assert await snapshot(w,target.actor)==before
        finally:
            event.remove(async_engine.sync_engine,'before_cursor_execute',observe)
            if waiter is not None and not waiter.done():
                waiter.cancel();await asyncio.gather(waiter,return_exceptions=True)
            if task is not None and not task.done():
                task.cancel();await asyncio.gather(task,return_exceptions=True)
