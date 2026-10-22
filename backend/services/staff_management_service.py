"""M1 authority primitives. Unmapped history is not an inferred Owner."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
import json
import secrets
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from core.permission_registry import STAFF_DEFAULT_PERMISSION_CODES, STAFF_DELEGABLE_PERMISSION_CODES, validate_staff_permission_codes
from services.staff_identity_guard import lock_credential_domain, normalize_staff_email


def staff_error(code: str, status: int = 409) -> HTTPException:
    return HTTPException(status_code=status, detail={'code': code, 'message': code})


def checked_staff_schema(tenant_id: UUID | str, schema: str) -> str:
    try:
        expected = 't_' + UUID(str(tenant_id)).hex
    except (TypeError, ValueError, AttributeError):
        raise staff_error('STAFF_TENANT_MISMATCH', 403) from None
    if not isinstance(schema, str) or schema != expected:
        raise staff_error('STAFF_TENANT_MISMATCH', 403)
    return '"' + schema + '"'


@dataclass(frozen=True)
class LockedStaffAuthority:
    tenant_id: UUID
    registration_id: UUID
    owner_user_id: UUID | None
    state: str
    authz_revision: int


class StaffManagementService:
    def __init__(self, db: AsyncSession, tenant_id: UUID | str, schema: str):
        self.db = db
        self.q = checked_staff_schema(tenant_id, schema)
        self.tenant_id = UUID(str(tenant_id))
        self.schema = schema

    async def lock_authority(self, *, exclusive: bool | None = False) -> LockedStaffAuthority:
        row = (await self.db.execute(text(
            f'SELECT * FROM {self.q}.staff_authority WHERE singleton=1 '
            + ('FOR UPDATE' if exclusive else 'FOR SHARE' if exclusive is False else '')))).mappings().one_or_none()
        if row is None:
            raise staff_error('OWNER_MAPPING_REQUIRED')
        registration = (await self.db.execute(text(
            'SELECT tr.id FROM public.tenant_registrations tr '
            'JOIN public.wholesalers w ON w.id=tr.wholesaler_id '
            'WHERE tr.tenant_schema=:s AND tr.wholesaler_id=:t AND tr.is_deleted IS FALSE '
            "AND tr.status IN ('provisioning','active') AND w.is_deleted IS FALSE AND w.status='active'"),
            {'s': self.schema, 't': self.tenant_id})).scalar_one_or_none()
        # Signup bootstrap runs on a separate connection before its registration
        # assignment commits. Only unmapped rows may still have NULL hints;
        # verified ownership always binds the complete committed identity.
        valid_ids = (row['tenant_id'] == self.tenant_id and row['registration_id'] == registration)
        if row['state']=='unmapped':
            valid_ids = row['tenant_id'] in (None,self.tenant_id) and row['registration_id'] in (None,registration)
        if registration is None or not valid_ids:
            raise staff_error('OWNER_MAPPING_REQUIRED')
        return LockedStaffAuthority(self.tenant_id, registration, row['owner_user_id'],
                                    row['state'], row['authz_revision'])

    async def assert_non_customer_active_user(self, user_id: UUID, *, lock_user: bool = True) -> None:
        user = (await self.db.execute(text(
            f'SELECT is_active,is_deleted FROM {self.q}.users WHERE id=:id' + (' FOR UPDATE' if lock_user else '')),
            {'id': user_id})).one_or_none()
        if user is None or not user.is_active or user.is_deleted:
            raise staff_error('OWNER_MAPPING_REQUIRED')
        if (await self.db.execute(text(
            'SELECT EXISTS (SELECT 1 FROM public.wholesaler_retailer_bindings '
            'WHERE wholesaler_id=:t AND tenant_user_id=:u)'),
            {'t': self.tenant_id, 'u': user_id})).scalar_one():
            raise staff_error('CUSTOMER_CANNOT_BE_STAFF', 403)
        if (await self.db.execute(text(
            f'SELECT EXISTS (SELECT 1 FROM {self.q}.user_roles ur JOIN {self.q}.roles r ON r.id=ur.role_id '
            f'JOIN {self.q}.role_permissions rp ON rp.role_id=r.id '
            f'JOIN {self.q}.permissions p ON p.id=rp.permission_id '
            "WHERE ur.user_id=:u AND r.is_deleted IS FALSE AND p.is_deleted IS FALSE AND p.code LIKE 'client:%')"),
            {'u': user_id})).scalar_one():
            raise staff_error('CUSTOMER_CANNOT_BE_STAFF', 403)

    async def require_owner(self, actor_id: UUID | str, *, exclusive: bool | None = False) -> LockedStaffAuthority:
        authority = await self.lock_authority(exclusive=exclusive)
        if authority.state != 'verified':
            raise staff_error('OWNER_MAPPING_REQUIRED')
        try:
            actor = UUID(str(actor_id))
        except (ValueError, TypeError, AttributeError):
            raise staff_error('OWNER_REQUIRED', 403) from None
        if actor != authority.owner_user_id:
            raise staff_error('OWNER_REQUIRED', 403)
        # Do not upgrade the user lock on ordinary operations: management owns
        # the authority exclusively, so a current shared read suffices here.
        await self.assert_non_customer_active_user(actor, lock_user=False)
        return authority

    async def bind_owner(self, *, registration_id: UUID, user_id: UUID,
                         source: str, evidence_digest: str, dry_run: bool = True) -> dict:
        if source not in {'owner_setup', 'approved_mapping'} or not re.fullmatch('[0-9a-f]{64}', evidence_digest):
            raise staff_error('OWNER_BINDING_EVIDENCE_REQUIRED')
        authority = await self.lock_authority(exclusive=True)
        if authority.registration_id != registration_id:
            raise staff_error('OWNER_MAPPING_REQUIRED')
        await self.assert_non_customer_active_user(user_id)
        if authority.state == 'verified':
            if authority.owner_user_id != user_id:
                raise staff_error('OWNER_PROTECTED')
            return {'action': 'unchanged', 'dry_run': dry_run}
        if (await self.db.execute(text(
            f'SELECT EXISTS (SELECT 1 FROM {self.q}.staff_memberships WHERE user_id=:u)'),
            {'u': user_id})).scalar_one():
            raise staff_error('OWNER_MAPPING_REQUIRED')
        if not dry_run:
            await self.ensure_templates()
            await self.db.execute(text(
                f'UPDATE {self.q}.staff_authority SET tenant_id=:t,registration_id=:r,owner_user_id=:u,state=\'verified\',source=:source, '
                'evidence_digest=:digest,authz_revision=authz_revision+1,updated_at=now() WHERE singleton=1'),
                {'u': user_id, 't': self.tenant_id, 'r': registration_id, 'source': source, 'digest': evidence_digest})
            await self.audit(user_id, 'owner_bound', user_id, {'source': source, 'evidence_digest': evidence_digest})
        return {'action': 'would_bind' if dry_run else 'bound', 'dry_run': dry_run}

    async def ensure_templates(self):
        """Called only inside the exclusive Owner binding transaction."""
        for code in sorted(STAFF_DELEGABLE_PERMISSION_CODES):
            await self.db.execute(text(f'INSERT INTO {self.q}.permissions (code,description) VALUES (:c,:d) ON CONFLICT (code) DO NOTHING'),{'c':code,'d':code})
        for key,codes in STAFF_DEFAULT_PERMISSION_CODES.items():
            role=await self.db.scalar(text(f'SELECT role_id FROM {self.q}.staff_role_templates WHERE template_key=:k'),{'k':key})
            if role is not None: continue
            role=await self.db.scalar(text(f'INSERT INTO {self.q}.roles (name,description) VALUES (:n,:d) RETURNING id'),
                {'n':'staff_'+key+'_'+uuid4().hex,'d':'Managed staff '+key})
            await self.db.execute(text(f'INSERT INTO {self.q}.staff_role_templates (template_key,role_id) VALUES (:k,:r)'),{'k':key,'r':role})
            await self._set_role_codes(role,codes)

    async def _set_role_codes(self,role_id,codes):
        rows=(await self.db.execute(text(f'SELECT id,code FROM {self.q}.permissions WHERE code=ANY(:codes) AND is_deleted IS FALSE'),
            {'codes':list(codes)})).all()
        if {r.code for r in rows}!=set(codes): raise staff_error('STAFF_PERMISSION_REGISTRY_INCOMPLETE')
        await self.db.execute(text(f'DELETE FROM {self.q}.role_permissions WHERE role_id=:r'),{'r':role_id})
        for row in rows:
            await self.db.execute(text(f'INSERT INTO {self.q}.role_permissions (role_id,permission_id) VALUES (:r,:p)'),{'r':role_id,'p':row.id})

    async def _advance(self):
        await self.db.execute(text(f'UPDATE {self.q}.staff_authority SET authz_revision=authz_revision+1,updated_at=now() WHERE singleton=1'))

    async def member(self,user_id):
        row=(await self.db.execute(text(
            f'SELECT u.id,u.email,u.full_name,u.is_active,m.template_key,m.credential_state,m.employment_state,m.version '
            f'FROM {self.q}.staff_memberships m JOIN {self.q}.users u ON u.id=m.user_id WHERE m.user_id=:u AND u.is_deleted IS FALSE'),
            {'u':user_id})).mappings().one_or_none()
        if row is None: raise staff_error('STAFF_NOT_FOUND',404)
        return {**dict(row),'id':str(row['id'])}

    async def members(self,actor):
        owner=await self.require_owner(actor)
        rows=(await self.db.execute(text(f'SELECT user_id FROM {self.q}.staff_memberships ORDER BY created_at,user_id'))).scalars().all()
        return {'items':[await self.member(uid) for uid in rows], 'owner_id':str(owner.owner_user_id),
                'authz_revision':owner.authz_revision}

    async def templates(self,actor):
        await self.require_owner(actor)
        rows=(await self.db.execute(text(f'SELECT template_key,role_id,version FROM {self.q}.staff_role_templates ORDER BY template_key'))).mappings().all()
        result=[]
        for row in rows:
            codes=(await self.db.execute(text(f'SELECT p.code FROM {self.q}.permissions p JOIN {self.q}.role_permissions rp '
                f'ON rp.permission_id=p.id JOIN {self.q}.roles r ON r.id=rp.role_id '
                'WHERE rp.role_id=:r AND p.is_deleted IS FALSE AND r.is_deleted IS FALSE ORDER BY p.code'),{'r':row['role_id']})).scalars().all()
            count=await self.db.scalar(text(f'SELECT count(*) FROM {self.q}.staff_memberships WHERE template_key=:k'),{'k':row['template_key']})
            result.append({'key':row['template_key'],'permission_codes':codes,'version':row['version'],'affected_count':count})
        return result

    async def edit_template(self,actor,key,codes,expected_version):
        await self.require_owner(actor,exclusive=True)
        try: codes=validate_staff_permission_codes(codes)
        except ValueError: raise staff_error('INVALID_STAFF_TEMPLATE',422) from None
        row=(await self.db.execute(text(f'SELECT role_id,version FROM {self.q}.staff_role_templates WHERE template_key=:k'),{'k':key})).one_or_none()
        if row is None: raise staff_error('INVALID_STAFF_TEMPLATE',422)
        if row.version!=expected_version: raise staff_error('STALE_STAFF_VERSION')
        await self._set_role_codes(row.role_id,codes)
        await self.db.execute(text(f'UPDATE {self.q}.staff_role_templates SET version=version+1 WHERE template_key=:k'),{'k':key})
        await self._advance()
        await self.audit(UUID(str(actor)),'staff_template_updated',row.role_id,{'template_key':key,'version':expected_version+1,'permission_codes':sorted(codes)})
        return await self.templates(actor)

    async def create_member(self,actor,*,email,full_name,template_key,create_key,adopt_existing=False):
        from core.security import hash_password
        email=normalize_staff_email(email)
        await lock_credential_domain(self.db,[email],tenant_ids=[self.tenant_id])
        owner=await self.require_owner(actor,exclusive=True)
        if not create_key or len(create_key)>128: raise staff_error('STAFF_CREATE_KEY_REQUIRED',422)
        key_digest=hashlib.sha256(create_key.encode()).hexdigest()
        payload=hashlib.sha256(json.dumps([email,full_name,template_key,adopt_existing],ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        replay=(await self.db.execute(text(
            "SELECT subject_id,details FROM public.staff_stock_audit_events WHERE tenant_id=:t AND actor_id=:a "
            "AND event_type='staff_created' AND details->>'create_key_digest'=:d"),
            {'t':self.tenant_id,'a':UUID(str(actor)),'d':key_digest})).one_or_none()
        if replay:
            if replay.details['payload_digest']!=payload: raise staff_error('IDEMPOTENCY_KEY_CONFLICT')
            return await self.member(replay.subject_id)
        role=await self.db.scalar(text(f'SELECT role_id FROM {self.q}.staff_role_templates WHERE template_key=:k'),{'k':template_key})
        if role is None: raise staff_error('INVALID_STAFF_TEMPLATE',422)
        existing=(await self.db.execute(text(f'SELECT id,is_active,is_deleted FROM {self.q}.users WHERE lower(email)=:e FOR UPDATE'),{'e':email})).one_or_none()
        if existing:
            if existing.id==owner.owner_user_id: raise staff_error('OWNER_PROTECTED')
            if not adopt_existing or not existing.is_active or existing.is_deleted: raise staff_error('STAFF_EMAIL_UNAVAILABLE')
            await self.assert_non_customer_active_user(existing.id)
            uid=existing.id
            if await self.db.scalar(text(f'SELECT user_id FROM {self.q}.staff_memberships WHERE user_id=:u'),{'u':uid}):
                raise staff_error('STAFF_EMAIL_UNAVAILABLE')
            await self.db.execute(text(f'UPDATE {self.q}.users SET is_active=FALSE,full_name=:n,updated_at=now() WHERE id=:u'),{'n':full_name,'u':uid})
        else:
            uid=await self.db.scalar(text(f'INSERT INTO {self.q}.users (email,password_hash,full_name,is_active) VALUES (:e,:p,:n,FALSE) RETURNING id'),
                {'e':email,'p':hash_password(secrets.token_urlsafe(32)),'n':full_name})
        await self.db.execute(text(f'INSERT INTO {self.q}.staff_memberships (user_id,template_key) VALUES (:u,:k)'),{'u':uid,'k':template_key})
        await self.db.execute(text(f'DELETE FROM {self.q}.user_roles WHERE user_id=:u'),{'u':uid})
        await self.db.execute(text(f'INSERT INTO {self.q}.user_roles (user_id,role_id) VALUES (:u,:r)'),{'u':uid,'r':role})
        await self._advance()
        await self.audit(UUID(str(actor)),'staff_created',uid,{'create_key_digest':key_digest,'payload_digest':payload,'target_had_credential':bool(existing)})
        return await self.member(uid)

    async def edit_member(self,actor,user_id,*,expected_version,full_name=None,is_active=None,template_key=None):
        email=await self.db.scalar(text(f'SELECT email FROM {self.q}.users WHERE id=:u'),{'u':user_id})
        if email: await lock_credential_domain(self.db,[email],tenant_ids=[self.tenant_id])
        owner=await self.require_owner(actor,exclusive=True)
        if user_id==owner.owner_user_id: raise staff_error('OWNER_PROTECTED')
        row=await self.member(user_id)
        if row['version']!=expected_version: raise staff_error('STALE_STAFF_VERSION')
        if full_name is not None:
            await self.db.execute(text(f'UPDATE {self.q}.users SET full_name=:n,updated_at=now() WHERE id=:u'),{'n':full_name,'u':user_id})
        if template_key is not None:
            role=await self.db.scalar(text(f'SELECT role_id FROM {self.q}.staff_role_templates WHERE template_key=:k'),{'k':template_key})
            if role is None: raise staff_error('INVALID_STAFF_TEMPLATE',422)
            await self.db.execute(text(f'DELETE FROM {self.q}.user_roles WHERE user_id=:u'),{'u':user_id})
            await self.db.execute(text(f'INSERT INTO {self.q}.user_roles (user_id,role_id) VALUES (:u,:r)'),{'u':user_id,'r':role})
            await self.db.execute(text(f'UPDATE {self.q}.staff_memberships SET template_key=:k WHERE user_id=:u'),{'k':template_key,'u':user_id})
        if is_active is not None:
            state='invited' if is_active else 'disabled'
            await self.db.execute(text(f'UPDATE {self.q}.staff_memberships SET employment_state=:s WHERE user_id=:u'),{'s':state,'u':user_id})
            await self.db.execute(text(f'UPDATE {self.q}.users SET is_active=FALSE,updated_at=now() WHERE id=:u'),{'u':user_id})
        await self.db.execute(text(f'UPDATE {self.q}.staff_memberships SET version=version+1,updated_at=now() WHERE user_id=:u'),{'u':user_id})
        await self.db.execute(text('UPDATE public.staff_credential_setup_tokens SET revoked_at=now() WHERE tenant_id=:t AND user_id=:u AND used_at IS NULL AND revoked_at IS NULL'),{'t':self.tenant_id,'u':user_id})
        await self._advance()
        await self.audit(UUID(str(actor)),'staff_updated',user_id,{'version':expected_version+1,'employment_state':is_active,'template_key':template_key})
        return await self.member(user_id)

    async def audit(self, actor_id: UUID, event_type: str, subject_id: UUID, details: dict) -> None:
        import json
        await self.db.execute(text(
            'INSERT INTO public.staff_stock_audit_events (tenant_id,actor_id,event_type,subject_id,details) '
            'VALUES (:t,:a,:event,:s,CAST(:details AS jsonb))'),
            {'t': self.tenant_id, 'a': actor_id, 'event': event_type, 's': subject_id,
             'details': json.dumps(details, sort_keys=True)})


def setup_binding_digest(registration_id: UUID, user_id: UUID) -> str:
    return hashlib.sha256(('mpango/owner-setup/v1\0'+str(registration_id)+'\0'+str(user_id)).encode()).hexdigest()


async def current_staff_access(db,tenant_id,schema,user_id,*,lock=True):
    """Current native RBAC under the authority shared lock until commit."""
    q=checked_staff_schema(tenant_id,schema)
    uid=UUID(str(user_id))
    authority=(await db.execute(text(f'SELECT * FROM {q}.staff_authority WHERE singleton=1'+(' FOR SHARE' if lock else '')))).mappings().one_or_none()
    if authority is None: raise staff_error('OWNER_MAPPING_REQUIRED')
    user=(await db.execute(text(f'SELECT email,full_name,is_active,is_deleted FROM {q}.users WHERE id=:u'),{'u':uid})).one_or_none()
    if user is None or not user.is_active or user.is_deleted: raise staff_error('USER_INACTIVE',401)
    member=(await db.execute(text(f'SELECT * FROM {q}.staff_memberships WHERE user_id=:u'),{'u':uid})).mappings().one_or_none()
    roles=(await db.execute(text(f'SELECT r.id,r.name FROM {q}.roles r JOIN {q}.user_roles ur ON ur.role_id=r.id '
        'WHERE ur.user_id=:u AND r.is_deleted IS FALSE'),{'u':uid})).all()
    codes=set((await db.execute(text(f'SELECT p.code FROM {q}.permissions p JOIN {q}.role_permissions rp ON rp.permission_id=p.id '
        f'JOIN {q}.roles r ON r.id=rp.role_id JOIN {q}.user_roles ur ON ur.role_id=r.id '
        'WHERE ur.user_id=:u AND r.is_deleted IS FALSE AND p.is_deleted IS FALSE'),{'u':uid})).scalars())
    if member:
        role_id=await db.scalar(text(f'SELECT role_id FROM {q}.staff_role_templates WHERE template_key=:k'),{'k':member['template_key']})
        if (member['credential_state']!='ready' or member['employment_state']!='active'
                or [r.id for r in roles]!=[role_id] or not codes <= STAFF_DELEGABLE_PERMISSION_CODES):
            raise staff_error('STAFF_PERMISSION_DENIED',403)
    is_owner=False
    if authority['state']=='verified' and authority['owner_user_id']==uid:
        try:
            await StaffManagementService(db,tenant_id,schema).require_owner(uid,exclusive=False if lock else None)
            is_owner=True
        except HTTPException:
            pass
    return {'id':str(uid),'email':user.email,'full_name':user.full_name,'roles':[r.name for r in roles],
            'permissions':sorted(codes),'is_owner':is_owner,'staff_state':member['employment_state'] if member else None,
            'authz_revision':authority['authz_revision']}
