"""M1 pure contract tests; runtime authority/HTTP evidence is separate."""
from uuid import UUID

from fastapi import HTTPException
import pytest

from core.permission_registry import (
    ADMIN_PERMISSION_CODES,
    STAFF_DEFAULT_PERMISSION_CODES,
    STAFF_DELEGABLE_PERMISSION_CODES,
    validate_staff_permission_codes,
)
from services.staff_identity_guard import credential_mutex_key, normalize_staff_email
from services.staff_management_service import checked_staff_schema


def test_staff_defaults_are_exact_and_nonadministrative():
    assert STAFF_DEFAULT_PERMISSION_CODES == {
        'warehouse': {'skus:read', 'inventory:read', 'orders:read', 'orders:ship'},
        'sales': {'skus:read', 'retailers:read', 'pricing:read', 'orders:read', 'orders:create'},
        'finance': {'orders:read', 'payments:read', 'finance:read'},
    }
    assert STAFF_DELEGABLE_PERMISSION_CODES <= ADMIN_PERMISSION_CODES
    for codes in STAFF_DEFAULT_PERMISSION_CODES.values():
        assert codes <= STAFF_DELEGABLE_PERMISSION_CODES


@pytest.mark.parametrize('code', [
    'users:create', 'roles:assign', 'orders:update', 'inventory:update', 'inventory:write',
    'system:admin', 'metrics:admin', 'client:orders:create', 'platform:admin', 'orders:*',
    'inventory:adjustments:approve',
])
def test_staff_protected_and_m2_capabilities_cannot_be_delegated(code):
    with pytest.raises(ValueError, match='INVALID_STAFF_TEMPLATE'):
        validate_staff_permission_codes([code])


@pytest.mark.parametrize('codes', [['orders:read','orders:read'], ['orders:read',True], 'orders:read', None])
def test_staff_capabilities_do_not_coerce_or_union_unknown_input(codes):
    with pytest.raises(ValueError, match='INVALID_STAFF_TEMPLATE'):
        validate_staff_permission_codes(codes)


def test_staff_all_authorized_capabilities_can_be_explicitly_selected():
    assert validate_staff_permission_codes(sorted(STAFF_DELEGABLE_PERMISSION_CODES)) == STAFF_DELEGABLE_PERMISSION_CODES


def test_staff_schema_is_bound_to_exact_tenant_uuid():
    tenant_id = UUID('ef11ef81-11c1-4f4f-9178-9041187f1581')
    schema = 't_' + tenant_id.hex
    assert checked_staff_schema(tenant_id, schema) == '"'+schema+'"'
    for wrong in ('public', schema.upper(), 't_test', schema+';', 't_'+'0'*32):
        with pytest.raises(HTTPException) as caught:
            checked_staff_schema(tenant_id, wrong)
        assert caught.value.status_code == 403
        assert caught.value.detail['code'] == 'STAFF_TENANT_MISMATCH'


def test_email_mutex_is_normalized_stable_and_domain_separated():
    assert normalize_staff_email(' Staff@Example.com ') == 'staff@example.com'
    assert credential_mutex_key(' Staff@Example.com ') == credential_mutex_key('staff@example.com')
    assert credential_mutex_key('staff@example.com') != credential_mutex_key('other@example.com')
    assert -(2**63) <= credential_mutex_key('staff@example.com') < 2**63


@pytest.mark.parametrize('value', ['', 'a b@example.com', None, 1])
def test_email_mutex_rejects_invalid_input_before_sql(value):
    with pytest.raises(ValueError, match='STAFF_EMAIL_INVALID'):
        normalize_staff_email(value)


# Native staging application and real login/select-tenant, not dependency overrides.
import asyncio
import secrets
from decimal import Decimal
from uuid import uuid4
from sqlalchemy import event, text
from tests.staff_approval_support import StaffWorld, staff_world as stock_world
from tests.test_inventory_manual_adjustment_http import inventory_http, login, error_code, adjust
from tests.test_staff_credential_compatibility import invite
from services.staff_management_service import StaffManagementService, current_staff_access
from services.staff_credential_service import StaffCredentialService
from services.inventory_service import InventoryService
from core.security import hash_password


async def joined(world, *, job='warehouse'):
    member,mail=await invite(world,key=job)
    password=secrets.token_urlsafe(32)
    async with world.session() as db:
        await StaffCredentialService(db).consume(mail.token,password)
    return UUID(member['id']),mail.to_email,password


@pytest.mark.asyncio
async def test_native_reissue_http_and_current_revocation(stock_world,inventory_http):
    client,owner,_=inventory_http
    async with stock_world.session() as db:
        await db.execute(text('UPDATE public.retailers SET email=:e WHERE id=:r'),
                         {'e':secrets.token_hex(8)+'@example.com','r':stock_world.retailer})
    path='/api/v1/retailers/'+str(stock_world.retailer)+'/reissue-setup'
    response=await asyncio.wait_for(client.post(path,headers=owner),8)
    assert response.status_code==200,'M1_REISSUE_HTTP_SELF_WAIT'
    async with stock_world.session() as db:
        await db.execute(text("DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE code='retailers:reissue_credential')"))
    response=await client.post(path,headers=owner)
    assert response.status_code==403,'M1_REISSUE_REVOKED_PERMISSION'


@pytest.mark.asyncio
async def test_credential_domain_does_not_lock_unrelated_authority(stock_world):
    from services.staff_identity_guard import lock_credential_domain
    other=StaffWorld()
    try:
        await other.initialize()
        async with stock_world.session() as db:
            await lock_credential_domain(db,[stock_world.email],tenant_ids=[stock_world.wid])
            async def unrelated():
                async with other.session() as second:
                    await lock_credential_domain(second,[other.email],tenant_ids=[other.wid])
                    await second.execute(text('SELECT singleton FROM staff_authority FOR UPDATE NOWAIT'))
            await asyncio.wait_for(unrelated(),3)
    finally:
        if hasattr(other,'engine'): await other.engine.dispose()


@pytest.mark.asyncio
async def test_reissue_final_authority_follows_concurrent_revocation(stock_world,inventory_http):
    client,owner,_=inventory_http
    async with stock_world.session() as db:
        await db.execute(text('UPDATE public.retailers SET email=:e WHERE id=:r'),
                         {'e':secrets.token_hex(8)+'@example.com','r':stock_world.retailer})
        count=await db.scalar(text('SELECT count(*) FROM public.retailer_credential_setup_tokens WHERE retailer_id=:r'),{'r':stock_world.retailer})
    attempted=asyncio.Event()
    def at_lock(_c,_cu,statement,_params,_context,_many):
        if statement.startswith('SELECT singleton FROM "'+stock_world.schema+'".staff_authority') and 'FOR UPDATE' in statement:
            attempted.set()
    from database.session import async_engine
    event.listen(async_engine.sync_engine,'before_cursor_execute',at_lock)
    request=None
    try:
        async with stock_world.session() as db:
            await db.execute(text('SELECT singleton FROM staff_authority WHERE singleton=1 FOR UPDATE'))
            request=asyncio.create_task(client.post('/api/v1/retailers/'+str(stock_world.retailer)+'/reissue-setup',headers=owner))
            await asyncio.wait_for(attempted.wait(),3)
            assert not request.done(),'M1_REISSUE_BYPASSED_AUTHORITY_LOCK'
            await db.execute(text("DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE code='retailers:reissue_credential')"))
        response=await asyncio.wait_for(request,5)
        assert response.status_code==403,'M1_REISSUE_STALE_PREVIEW_AUTHORIZED'
        async with stock_world.session() as db:
            assert await db.scalar(text('SELECT count(*) FROM public.retailer_credential_setup_tokens WHERE retailer_id=:r'),{'r':stock_world.retailer})==count,'M1_REISSUE_REVOKED_WRITE'
    finally:
        event.remove(async_engine.sync_engine,'before_cursor_execute',at_lock)
        if request is not None and not request.done():
            request.cancel()
            await asyncio.gather(request,return_exceptions=True)


@pytest.mark.asyncio
async def test_stock_session_cannot_use_another_owner_or_untrusted_actor(stock_world):
    other=StaffWorld()
    try:
        await other.initialize()
        before=await stock_world.snapshot()
        async with stock_world.session() as db:
            audit_before=await db.scalar(text('SELECT count(*) FROM public.staff_stock_audit_events WHERE tenant_id=:t'),{'t':other.wid})
        for mode in ('other_tenant','missing_actor','wrong_actor'):
            refused=False
            try:
                async with stock_world.session() as db:
                    if mode=='missing_actor': db.info.pop('_staff_stock_actor')
                    if mode=='wrong_actor': db.info['_staff_stock_actor']=str(uuid4())
                    await InventoryService().adjust_stock(db,sku_code='INV-BOX',quantity=Decimal('1'),reason='scope control',
                        adjusted_by=str(other.actor if mode=='other_tenant' else stock_world.actor),
                        tenant_id=str(other.wid if mode=='other_tenant' else stock_world.wid),
                        tenant_schema=other.schema if mode=='other_tenant' else stock_world.schema)
            except HTTPException as exc:
                refused=exc.status_code==403 and exc.detail['code']=='INVENTORY_AUTHORITY_SCOPE_MISMATCH'
            assert refused,'M1_STOCK_SCOPE_ACCEPTED'
            assert await stock_world.snapshot()==before,'M1_STOCK_SCOPE_WROTE'
        async with stock_world.session() as db:
            assert await db.scalar(text('SELECT count(*) FROM public.staff_stock_audit_events WHERE tenant_id=:t'),{'t':other.wid})==audit_before
    finally:
        if hasattr(other,'engine'): await other.engine.dispose()


@pytest.mark.asyncio
async def test_native_staff_http_mailbox_proof_does_not_take_owner_session(stock_world,inventory_http):
    from services.email_delivery import get_dev_staff_email_deliveries
    from tests.test_staff_credential_compatibility import remember
    client,owner,_=inventory_http
    email=secrets.token_hex(8)+'@example.com'
    headers={**owner,'Idempotency-Key':uuid4().hex}
    response=await client.post('/api/v1/staff',headers=headers,json={
        'email':email,'full_name':'Native employee','template_key':'sales'})
    assert response.status_code==201,'M1_HTTP_CREATE'
    member=response.json()['data']
    assert not member['is_active'] and member['credential_state']=='pending'
    replay=await client.post('/api/v1/staff',headers=headers,json={
        'email':email,'full_name':'Native employee','template_key':'sales'})
    assert replay.json()['data']['id']==member['id']
    response=await client.post('/api/v1/staff/'+member['id']+'/credential-setup',headers=owner,
        json={'owner_password':stock_world.password,'expected_version':member['version']})
    assert response.status_code==201,'M1_HTTP_INVITE'
    mail=get_dev_staff_email_deliveries(email)[-1]
    remember(mail)
    assert mail.token not in response.text and mail.link not in response.text,'M1_OWNER_TOKEN_LEAK'
    password=secrets.token_urlsafe(32)
    response=await client.post('/api/v1/auth/staff/setup-credential',
        json={'setup_token':mail.token,'password':password})
    assert response.status_code==200,'M1_HTTP_PROOF'
    me=await client.get('/api/v1/auth/me',headers=owner)
    assert me.status_code==200 and me.json()['data']['is_owner'] is True
    employee=await login(client,stock_world,email=email,password=password)
    me=await client.get('/api/v1/auth/me',headers=employee)
    assert me.status_code==200 and not me.json()['data']['is_owner']
    assert me.json()['data']['staff_state']=='active'
    assert (await client.get('/api/v1/staff',headers=employee)).status_code==403
    assert (await client.get('/api/v1/roles',headers=employee)).status_code==403
    assert (await client.post('/api/v1/users',headers=owner,json={
        'email':'blocked@example.com','password':password,'full_name':'Legacy write'})).status_code==409


@pytest.mark.asyncio
async def test_admin_alias_and_identity_only_token_are_not_owner(stock_world,inventory_http):
    client,owner,_=inventory_http
    uid,email=await stock_world.add_user()
    password=secrets.token_urlsafe(32)
    async with stock_world.session() as db:
        await db.execute(text('UPDATE users SET password_hash=:h WHERE id=:u'),{'h':hash_password(password),'u':uid})
        role=await db.scalar(text("SELECT id FROM roles WHERE name='admin'"))
        await db.execute(text('INSERT INTO user_roles (user_id,role_id) VALUES (:u,:r)'),{'u':uid,'r':role})
    alias=await login(client,stock_world,email=email,password=password)
    before=await stock_world.snapshot()
    assert (await client.get('/api/v1/staff',headers=alias)).status_code==403,'M1_ADMIN_ALIAS_OWNER'
    assert (await adjust(client,alias,'1')).status_code==403,'M1_ADMIN_ALIAS_STOCK'
    spoof=await client.post('/api/v1/inventory/adjust',headers=alias,json={
        'sku_code':'INV-BOX','quantity':'1','reason':'payload cannot authorize',
        'adjusted_by':str(stock_world.actor),'tenant_id':str(stock_world.wid),'tenant_schema':stock_world.schema})
    assert spoof.status_code==403,'M1_PAYLOAD_OWNER_SPOOF'
    assert await stock_world.snapshot()==before
    identity=(await client.post('/api/v1/auth/login',json={'email':stock_world.email,'password':stock_world.password})).json()['data']['access_token']
    response=await client.get('/api/v1/staff',headers={'Authorization':'Bearer '+identity})
    assert response.status_code in (401,403),'M1_IDENTITY_ONLY_OWNER'


@pytest.mark.asyncio
async def test_template_revoke_old_jwt_and_hot_response_cache(stock_world,inventory_http):
    client,owner,_=inventory_http
    uid,email,password=await joined(stock_world)
    employee=await login(client,stock_world,email=email,password=password)
    first=await client.get('/api/v1/inventory/stocks',headers=employee)
    assert first.status_code==200,'M1_WAREHOUSE_POSITIVE'
    templates=(await client.get('/api/v1/staff/role-templates',headers=owner)).json()['data']
    row=next(t for t in templates if t['key']=='warehouse')
    response=await client.put('/api/v1/staff/role-templates/warehouse',headers=owner,json={
        'expected_version':row['version'],'permission_codes':['orders:read']})
    assert response.status_code==200
    assert (await client.get('/api/v1/inventory/stocks',headers=employee)).status_code==403,'M1_STALE_JWT_REVOKE'
    me=await client.get('/api/v1/auth/me',headers=employee)
    assert me.status_code==200 and me.json()['data']['permissions']==['orders:read'],'M1_ME_CACHE'
    assert (await client.put('/api/v1/staff/role-templates/warehouse',headers=owner,json={
        'expected_version':row['version'],'permission_codes':['inventory:read']})).status_code==409
    async with stock_world.session() as db:
        member=await StaffManagementService(db,stock_world.wid,stock_world.schema).member(uid)
    assert (await client.patch('/api/v1/staff/'+str(uid),headers=owner,json={
        'expected_version':member['version'],'is_active':False})).status_code==200
    assert (await client.get('/api/v1/auth/me',headers=employee)).status_code==401,'M1_DISABLED_ME'
    assert (await client.get('/api/v1/inventory/stocks',headers=employee)).status_code in (401,403)


@pytest.mark.asyncio
async def test_owner_protection_cross_tenant_and_customer_rejection(stock_world,inventory_http):
    client,owner,_=inventory_http
    assert (await client.patch('/api/v1/staff/'+str(stock_world.actor),headers=owner,
        json={'expected_version':1,'is_active':False})).status_code==409,'M1_OWNER_MUTATED'
    uid,email=await stock_world.add_user()
    async with stock_world.session() as db:
        await db.execute(text('UPDATE public.wholesaler_retailer_bindings SET tenant_user_id=:u WHERE wholesaler_id=:t AND retailer_id=:r'),
            {'u':uid,'t':stock_world.wid,'r':stock_world.retailer})
    response=await client.post('/api/v1/staff',headers={**owner,'Idempotency-Key':uuid4().hex},
        json={'email':email,'full_name':'Customer','template_key':'sales','adopt_existing':True})
    assert response.status_code==403 and error_code(response)=='CUSTOMER_CANNOT_BE_STAFF'
    other=StaffWorld()
    try:
        await other.initialize()
        member,_mail=await invite(other)
        assert (await client.get('/api/v1/staff/'+member['id'],headers=owner)).status_code==404,'M1_CROSS_TENANT_MEMBER'
    finally:
        if hasattr(other,'engine'): await other.engine.dispose()


@pytest.mark.asyncio
async def test_inventory_service_requires_current_owner_and_atomic_audit(stock_world):
    before=await stock_world.snapshot()
    with pytest.raises(HTTPException) as caught:
        async with stock_world.session() as db:
            await InventoryService().adjust_stock(db,sku_code='INV-BOX',quantity=Decimal('1'),
                reason='untrusted label',adjusted_by=str(stock_world.actor))
    assert caught.value.status_code==403 and await stock_world.snapshot()==before,'M1_RAW_SERVICE_BYPASS'
    def fault(_c,_cu,sql,_p,_ctx,_m):
        if 'INSERT INTO public.staff_stock_audit_events' in sql: raise RuntimeError('M1_STOCK_AUDIT_FAULT')
    event.listen(stock_world.engine.sync_engine,'before_cursor_execute',fault)
    try:
        with pytest.raises(RuntimeError,match='M1_STOCK_AUDIT_FAULT'): await stock_world.adjust(Decimal('1'))
    finally:
        event.remove(stock_world.engine.sync_engine,'before_cursor_execute',fault)
    assert await stock_world.snapshot()==before,'M1_AUDIT_STOCK_PARTIAL_COMMIT'
    await stock_world.adjust(Decimal('1'))
    async with stock_world.session() as db:
        assert await db.scalar(text("SELECT count(*) FROM public.staff_stock_audit_events WHERE tenant_id=:t AND event_type='owner_inventory_adjusted'"),{'t':stock_world.wid})==1


@pytest.mark.asyncio
async def test_authorized_operation_shared_lock_precedes_revoke_commit(stock_world):
    uid,_email,_password=await joined(stock_world)
    read=asyncio.Event()
    release=asyncio.Event()
    write_started=asyncio.Event()
    written=asyncio.Event()
    def observe(_c,_cu,sql,_p,_ctx,_m):
        if 'staff_authority' in sql and 'FOR UPDATE' in sql: write_started.set()
    async def operation():
        async with stock_world.session() as db:
            access=await current_staff_access(db,stock_world.wid,stock_world.schema,uid)
            assert 'inventory:read' in access['permissions']
            read.set()
            await release.wait()
    async def revoke():
        await read.wait()
        async with stock_world.session() as db:
            service=StaffManagementService(db,stock_world.wid,stock_world.schema)
            await service.edit_template(stock_world.actor,'warehouse',['orders:read'],1)
        written.set()
    event.listen(stock_world.engine.sync_engine,'before_cursor_execute',observe)
    first=asyncio.create_task(operation())
    second=asyncio.create_task(revoke())
    try:
        await asyncio.wait_for(write_started.wait(),15)
        with pytest.raises(TimeoutError): await asyncio.wait_for(written.wait(),0.15)
        release.set()
        await asyncio.wait_for(asyncio.gather(first,second),15)
        async with stock_world.session() as db:
            assert 'inventory:read' not in (await current_staff_access(db,stock_world.wid,stock_world.schema,uid))['permissions']
    finally:
        release.set()
        for task in (first,second):
            if not task.done(): task.cancel()
        await asyncio.gather(first,second,return_exceptions=True)
        event.remove(stock_world.engine.sync_engine,'before_cursor_execute',observe)
