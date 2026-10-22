"""Native M1 identity/lifecycle tests on the declared minimum-privilege task DB."""
import json
import os
from pathlib import Path
import secrets
from uuid import UUID,uuid4

from fastapi import HTTPException
import pytest
from sqlalchemy import text,event

from core.security import hash_password,verify_password
from core.config import get_settings
from services.onboarding_service import hash_token
from services.email_delivery import get_dev_staff_email_deliveries
from services.staff_management_service import StaffManagementService,current_staff_access
from services.staff_credential_service import StaffCredentialService
from tests.staff_approval_support import StaffWorld,staff_world

pytestmark=pytest.mark.integration


def remember(delivery):
    root=os.environ.get('STAFF_M1_PRIVATE_DIR')
    if root:
        path=Path(root)/('mail-'+uuid4().hex+'.json')
        path.write_text(json.dumps({'token':delivery.token,'email':delivery.to_email,
            'link':getattr(delivery,'link',getattr(delivery,'reset_link',None))})+'\n')
        os.chmod(path,0o600)


async def invite(world,*,email=None,key='sales',adopt=False):
    email=email or secrets.token_hex(8)+'@example.com'
    async with world.session() as db:
        service=StaffManagementService(db,world.wid,world.schema)
        row=await service.create_member(world.actor,email=email,full_name='M1 employee',template_key=key,
            create_key=uuid4().hex,adopt_existing=adopt)
    async with world.session() as db:
        result=await StaffCredentialService(db).invite(tenant_id=world.wid,schema=world.schema,actor_id=world.actor,
            user_id=UUID(row['id']),owner_password=world.password,expected_version=row['version'])
        delivery=get_dev_staff_email_deliveries(email)[-1]
        remember(delivery)
        assert delivery.token not in json.dumps(result)
        assert delivery.link not in json.dumps(result)
    return result['member'],delivery


@pytest.mark.asyncio
async def test_staff_mailbox_join_and_exact_native_role(staff_world):
    row,mail=await invite(staff_world)
    assert row['is_active'] is False and row['credential_state']=='pending'
    password=secrets.token_urlsafe(32)
    async with staff_world.session() as db:
        assert await StaffCredentialService(db).consume(mail.token,password)=={'action':'joined'}
    async with staff_world.session() as db:
        access=await current_staff_access(db,staff_world.wid,staff_world.schema,row['id'])
        assert not access['is_owner'] and access['staff_state']=='active'
        assert set(access['permissions'])=={'skus:read','retailers:read','pricing:read','orders:read','orders:create'}
    with pytest.raises(HTTPException) as caught:
        async with staff_world.session() as db: await StaffCredentialService(db).consume(mail.token,password)
    assert caught.value.detail['code']=='STAFF_CREDENTIAL_PROOF_FAILED'


@pytest.mark.asyncio
async def test_staff_disable_revokes_invite_and_old_versions(staff_world):
    row,mail=await invite(staff_world)
    async with staff_world.session() as db:
        disabled=await StaffManagementService(db,staff_world.wid,staff_world.schema).edit_member(staff_world.actor,UUID(row['id']),expected_version=row['version'],is_active=False)
    assert disabled['employment_state']=='disabled' and not disabled['is_active']
    with pytest.raises(HTTPException):
        async with staff_world.session() as db: await StaffCredentialService(db).consume(mail.token,secrets.token_urlsafe(32))
    async with staff_world.session() as db:
        assert (await db.execute(text('SELECT used_at,revoked_at FROM public.staff_credential_setup_tokens WHERE tenant_id=:t AND user_id=:u'),{'t':staff_world.wid,'u':UUID(row['id'])})).one().revoked_at is not None


@pytest.mark.asyncio
async def test_staff_create_key_and_template_version_are_durable(staff_world):
    email=secrets.token_hex(8)+'@example.com'
    args=dict(email=email,full_name='Idempotent member',template_key='warehouse',create_key=uuid4().hex)
    async with staff_world.session() as db:
        row=await StaffManagementService(db,staff_world.wid,staff_world.schema).create_member(staff_world.actor,**args)
    async with staff_world.session() as db:
        service=StaffManagementService(db,staff_world.wid,staff_world.schema)
        assert (await service.create_member(staff_world.actor,**args))['id']==row['id']
        templates=await service.templates(staff_world.actor)
        warehouse=next(t for t in templates if t['key']=='warehouse')
        assert warehouse['affected_count']==1
        await service.edit_template(staff_world.actor,'warehouse',['inventory:read'],warehouse['version'])
    with pytest.raises(HTTPException) as caught:
        async with staff_world.session() as db:
            await StaffManagementService(db,staff_world.wid,staff_world.schema).edit_template(staff_world.actor,'warehouse',['orders:read'],warehouse['version'])
    assert caught.value.detail['code']=='STALE_STAFF_VERSION'


@pytest.mark.asyncio
@pytest.mark.parametrize('same_password',[True,False])
async def test_join_verifies_all_active_copy_passwords_not_bcrypt_bytes(staff_world,same_password):
    email=secrets.token_hex(8)+'@example.com'
    password=secrets.token_urlsafe(32)
    others=[]
    hashes=[]
    try:
        for n in range(2):
            world=StaffWorld()
            others.append(world)
            await world.initialize()
            hashed=hash_password(password if same_password or n==0 else secrets.token_urlsafe(32))
            hashes.append(hashed)
            async with world.session() as db:
                await db.execute(text('INSERT INTO users (email,password_hash,is_active) VALUES (:e,:h,TRUE)'),{'e':email,'h':hashed})
        assert hashes[0]!=hashes[1]
        member,mail=await invite(staff_world,email=email)
        if same_password:
            async with staff_world.session() as db: await StaffCredentialService(db).consume(mail.token,password)
        else:
            refused=False
            try:
                async with staff_world.session() as db: await StaffCredentialService(db).consume(mail.token,password)
            except HTTPException as error:
                refused=error.detail['code']=='STAFF_CREDENTIAL_PROOF_FAILED'
            assert refused,'M1_DIVERGENT_PASSWORD_JOINED'
        for world,hashed in zip(others,hashes):
            async with world.session() as db:
                assert await db.scalar(text('SELECT password_hash FROM users WHERE email=:e'),{'e':email})==hashed
        async with staff_world.session() as db:
            assert (await db.execute(text('SELECT is_active FROM users WHERE id=:u'),{'u':UUID(member['id'])})).scalar_one() is same_password
    finally:
        for world in others:
            if hasattr(world,'engine'): await world.engine.dispose()


@pytest.mark.asyncio
async def test_audit_failure_rolls_back_employee_and_roles(staff_world):
    email=secrets.token_hex(8)+'@example.com'
    def fault(_conn,_cursor,statement,_params,_context,_many):
        if 'INSERT INTO public.staff_stock_audit_events' in statement: raise RuntimeError('M1_AUDIT_FAULT')
    event.listen(staff_world.engine.sync_engine,'before_cursor_execute',fault)
    try:
        with pytest.raises(RuntimeError,match='M1_AUDIT_FAULT'):
            async with staff_world.session() as db:
                await StaffManagementService(db,staff_world.wid,staff_world.schema).create_member(staff_world.actor,
                    email=email,full_name='Rollback',template_key='sales',create_key=uuid4().hex)
    finally:
        event.remove(staff_world.engine.sync_engine,'before_cursor_execute',fault)
    async with staff_world.session() as db:
        assert await db.scalar(text('SELECT count(*) FROM users WHERE email=:e'),{'e':email})==0


@pytest.mark.asyncio
async def test_native_owner_writer_preserves_active_staff_fanout_and_never_reactivates_disabled(staff_world):
    from services.owner_credential_service import OwnerCredentialSetupService
    from services.password_reset_service import PasswordResetService
    from services.email_delivery import get_dev_reset_email_deliveries
    other=StaffWorld()
    try:
        await other.initialize()
        member,mail=await invite(other,email=staff_world.email)
        uid=UUID(member['id'])
        async with other.session() as db:
            await StaffCredentialService(db).consume(mail.token,staff_world.password)
        replacement=secrets.token_urlsafe(32)
        async with staff_world.session() as db:
            owner=OwnerCredentialSetupService(db)
            issued=await owner.issue_setup_token(staff_world.registration)
            consumed=await owner.consume_setup_token(issued.raw_token,replacement)
            await owner.create_first_admin_rbac(consumed)
        async with other.session() as db:
            hashed=await db.scalar(text('SELECT password_hash FROM users WHERE id=:u'),{'u':uid})
            assert verify_password(replacement,hashed),'M1_OWNER_FANOUT_MUST_INCLUDE_ACTIVE_STAFF'
            service=StaffManagementService(db,other.wid,other.schema)
            row=await service.member(uid)
            await service.edit_member(other.actor,uid,expected_version=row['version'],is_active=False)
        async with staff_world.session() as db:
            result=await PasswordResetService(db).request_reset(staff_world.email)
            assert result.issued
            delivery=get_dev_reset_email_deliveries(staff_world.email)[-1]
            remember(delivery)
        final_password=secrets.token_urlsafe(32)
        async with staff_world.session() as db:
            result=await PasswordResetService(db).consume_reset(delivery.token,final_password)
            assert result.updated_tenant_count==1
        async with other.session() as db:
            actual=(await db.execute(text('SELECT password_hash,is_active FROM users WHERE id=:u'),{'u':uid})).one()
            assert actual.password_hash==hashed and actual.is_active is False,'M1_RESET_REACTIVATED_DISABLED_STAFF'
            row=await StaffManagementService(db,other.wid,other.schema).member(uid)
            assert row['employment_state']=='disabled'
    finally:
        if hasattr(other,'engine'): await other.engine.dispose()


@pytest.mark.asyncio
async def test_rehire_joins_with_current_active_copy_after_personal_reset(staff_world):
    from services.password_reset_service import PasswordResetService
    from services.email_delivery import get_dev_reset_email_deliveries
    other=StaffWorld()
    try:
        await other.initialize()
        member,mail=await invite(staff_world,email=other.email)
        uid=UUID(member['id'])
        async with staff_world.session() as db:
            await StaffCredentialService(db).consume(mail.token,other.password)
        async with staff_world.session() as db:
            service=StaffManagementService(db,staff_world.wid,staff_world.schema)
            member=await service.member(uid)
            disabled=await service.edit_member(staff_world.actor,uid,expected_version=member['version'],is_active=False)
            old_hash=await db.scalar(text('SELECT password_hash FROM users WHERE id=:u'),{'u':uid})
        async with other.session() as db:
            assert (await PasswordResetService(db).request_reset(other.email)).issued
            reset=get_dev_reset_email_deliveries(other.email)[-1]
            remember(reset)
        password=secrets.token_urlsafe(32)
        async with other.session() as db:
            assert (await PasswordResetService(db).consume_reset(reset.token,password)).updated_tenant_count==1
        async with staff_world.session() as db:
            assert await db.scalar(text('SELECT password_hash FROM users WHERE id=:u'),{'u':uid})==old_hash
            service=StaffManagementService(db,staff_world.wid,staff_world.schema)
            restored=await service.edit_member(staff_world.actor,uid,expected_version=disabled['version'],is_active=True)
        async with staff_world.session() as db:
            await StaffCredentialService(db).invite(tenant_id=staff_world.wid,schema=staff_world.schema,
                actor_id=staff_world.actor,user_id=uid,owner_password=staff_world.password,expected_version=restored['version'])
            mail=get_dev_staff_email_deliveries(other.email)[-1]
            remember(mail)
        async with staff_world.session() as db:
            await StaffCredentialService(db).consume(mail.token,password)
        async with staff_world.session() as db:
            row=(await db.execute(text('SELECT password_hash,is_active FROM users WHERE id=:u'),{'u':uid})).one()
            assert row.is_active and verify_password(password,row.password_hash),'M1_REHIRE_CURRENT_PASSWORD_REJECTED'
        async with other.session() as db:
            assert verify_password(password,await db.scalar(text('SELECT password_hash FROM users WHERE id=:u'),{'u':other.actor}))
    finally:
        if hasattr(other,'engine'): await other.engine.dispose()


@pytest.mark.asyncio
async def test_native_reset_failure_rolls_back_every_copy_and_token(staff_world):
    from services.password_reset_service import PasswordResetService,PasswordResetApplyFailedError
    from services.email_delivery import get_dev_reset_email_deliveries
    other=StaffWorld()
    try:
        await other.initialize()
        member,mail=await invite(other,email=staff_world.email)
        uid=UUID(member['id'])
        async with other.session() as db: await StaffCredentialService(db).consume(mail.token,staff_world.password)
        async with staff_world.session() as db:
            await PasswordResetService(db).request_reset(staff_world.email)
            delivery=get_dev_reset_email_deliveries(staff_world.email)[-1]
            remember(delivery)
        before={}
        for world,user in ((staff_world,staff_world.actor),(other,uid)):
            async with world.session() as db:
                before[world.schema]=await db.scalar(text('SELECT password_hash FROM users WHERE id=:u'),{'u':user})
        updates=[]
        def fault(_c,_cu,statement,_params,_context,_many):
            if statement.startswith('UPDATE "') and '.users SET password_hash' in statement:
                updates.append(statement.split('"')[1])
                if len(updates)==2: raise RuntimeError('M1_RESET_SECOND_COPY_FAULT')
        event.listen(staff_world.engine.sync_engine,'before_cursor_execute',fault)
        try:
            with pytest.raises(PasswordResetApplyFailedError):
                async with staff_world.session() as db:
                    await PasswordResetService(db).consume_reset(delivery.token,secrets.token_urlsafe(32))
        finally:
            event.remove(staff_world.engine.sync_engine,'before_cursor_execute',fault)
        assert len(updates)==2,'M1_RESET_FAULT_NOT_REACHED'
        for world,user in ((staff_world,staff_world.actor),(other,uid)):
            async with world.session() as db:
                assert await db.scalar(text('SELECT password_hash FROM users WHERE id=:u'),{'u':user})==before[world.schema]
        from services.onboarding_service import hash_token
        from core.config import get_settings
        async with staff_world.session() as db:
            assert (await db.execute(text('SELECT used_at FROM public.password_reset_tokens WHERE token_hash=:h'),{'h':hash_token(delivery.token,get_settings())})).scalar_one() is None
    finally:
        if hasattr(other,'engine'): await other.engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('failure',['expired','superseded','scan_incomplete','retailer_overlap'])
async def test_personal_proof_failure_keeps_pending_and_never_consumes(staff_world,failure):
    member,mail=await invite(staff_world)
    uid=UUID(member['id'])
    if failure=='expired':
        async with staff_world.session() as db:
            await db.execute(text("UPDATE public.staff_credential_setup_tokens SET created_at=now()-interval '2 days',expires_at=now()-interval '1 minute' WHERE tenant_id=:t AND user_id=:u"),{'t':staff_world.wid,'u':uid})
    if failure=='superseded':
        async with staff_world.session() as db:
            await StaffCredentialService(db).invite(tenant_id=staff_world.wid,schema=staff_world.schema,actor_id=staff_world.actor,
                user_id=uid,owner_password=staff_world.password,expected_version=member['version'])
            remember(get_dev_staff_email_deliveries(mail.to_email)[-1])
    if failure=='retailer_overlap':
        async with staff_world.session() as db:
            await db.execute(text('UPDATE public.wholesaler_retailer_bindings SET tenant_user_id=:u WHERE wholesaler_id=:t AND retailer_id=:r'),
                {'u':uid,'t':staff_world.wid,'r':staff_world.retailer})
    reached=[]
    def fault(_c,_cu,statement,_params,_ctx,_many):
        if statement.startswith('SELECT id,password_hash,is_active,is_deleted FROM "') and 'FOR UPDATE' in statement:
            reached.append(True)
            raise RuntimeError('M1_SCAN_INCOMPLETE')
    if failure=='scan_incomplete': event.listen(staff_world.engine.sync_engine,'before_cursor_execute',fault)
    try:
        with pytest.raises(HTTPException) as caught:
            async with staff_world.session() as db:
                await StaffCredentialService(db).consume(mail.token,secrets.token_urlsafe(32))
        assert caught.value.detail['code']=='STAFF_CREDENTIAL_PROOF_FAILED'
    finally:
        if failure=='scan_incomplete': event.remove(staff_world.engine.sync_engine,'before_cursor_execute',fault)
    if failure=='scan_incomplete': assert reached
    async with staff_world.session() as db:
        assert await db.scalar(text('SELECT is_active FROM users WHERE id=:u'),{'u':uid}) is False
        assert await db.scalar(text('SELECT used_at FROM public.staff_credential_setup_tokens WHERE token_hash=:h'),
            {'h':hash_token(mail.token,get_settings())}) is None
