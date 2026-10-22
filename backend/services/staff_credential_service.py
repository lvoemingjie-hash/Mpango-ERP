"""Employee mailbox proof is separate from employer authorization."""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import text

from core.config import get_settings
from core.security import hash_password, verify_password
from services.email_delivery import record_staff_setup_email
from services.onboarding_service import generate_verification_token, hash_token, validate_password_policy
from services.staff_identity_guard import lock_credential_domain
from services.staff_management_service import StaffManagementService, staff_error


def proof_failed():
    return staff_error('STAFF_CREDENTIAL_PROOF_FAILED',400)


class StaffCredentialService:
    def __init__(self,db,*,settings=None):
        self.db=db
        self.settings=settings or get_settings()

    async def invite(self,*,tenant_id,schema,actor_id,user_id,owner_password,expected_version):
        staff=StaffManagementService(self.db,tenant_id,schema)
        hint=await self.db.scalar(text(f'SELECT email FROM {staff.q}.users WHERE id=:u'),{'u':user_id})
        if hint: await lock_credential_domain(self.db,[hint],tenant_ids=[staff.tenant_id])
        owner=await staff.require_owner(actor_id,exclusive=True)
        if user_id==owner.owner_user_id: raise staff_error('OWNER_PROTECTED')
        own_hash=await self.db.scalar(text(f'SELECT password_hash FROM {staff.q}.users WHERE id=:u'),{'u':UUID(str(actor_id))})
        if not verify_password(owner_password,own_hash): raise staff_error('OWNER_REAUTHENTICATION_REQUIRED',403)
        member=await staff.member(user_id)
        if member['email']!=hint: raise staff_error('STAFF_IDENTITY_CHANGED')
        if member['version']!=expected_version: raise staff_error('STALE_STAFF_VERSION')
        if member['employment_state']=='disabled': raise staff_error('STAFF_DISABLED')
        events=(await self.db.execute(text(
            "SELECT details FROM public.staff_stock_audit_events WHERE tenant_id=:t AND subject_id=:u "
            "AND event_type IN ('staff_created','staff_invited') ORDER BY created_at DESC,id DESC LIMIT 1"),
            {'t':staff.tenant_id,'u':user_id})).scalar_one_or_none()
        established=member['credential_state']=='ready' or bool(events and events.get('target_had_credential'))
        if member['credential_state']=='ready' and member['employment_state']=='active':
            await staff.invalidate_approval_policy(user_id=user_id)
        version=member['version']+1
        await self.db.execute(text('UPDATE public.staff_credential_setup_tokens SET revoked_at=now() WHERE tenant_id=:t AND user_id=:u AND used_at IS NULL AND revoked_at IS NULL'),{'t':staff.tenant_id,'u':user_id})
        await self.db.execute(text(f"UPDATE {staff.q}.staff_memberships SET credential_state='pending',employment_state='invited',version=:v,updated_at=now() WHERE user_id=:u"),{'v':version,'u':user_id})
        await self.db.execute(text(f'UPDATE {staff.q}.users SET is_active=FALSE,updated_at=now() WHERE id=:u'),{'u':user_id})
        raw=generate_verification_token()
        expiry=datetime.now(timezone.utc)+timedelta(hours=24)
        await self.db.execute(text(
            'INSERT INTO public.staff_credential_setup_tokens (tenant_id,user_id,email,membership_version,token_hash,expires_at) '
            'VALUES (:t,:u,:e,:v,:h,:x)'),{'t':staff.tenant_id,'u':user_id,'e':hint,'v':version,'h':hash_token(raw,self.settings),'x':expiry})
        await staff._advance()
        await staff.audit(UUID(str(actor_id)),'staff_invited',user_id,{'version':version,'target_had_credential':established})
        origin=(self.settings.PUBLIC_FRONTEND_URL or 'http://localhost:5173').rstrip('/')
        record_staff_setup_email(settings=self.settings,to_email=hint,token=raw,link=origin+'/staff/setup-credential#token='+raw)
        return {'action':'invitation_sent','member':await staff.member(user_id)}

    async def consume(self,raw,password):
        validate_password_policy(password)
        if not isinstance(raw,str) or not raw.strip(): raise proof_failed()
        digest=hash_token(raw.strip(),self.settings)
        hint=(await self.db.execute(text('SELECT email FROM public.staff_credential_setup_tokens WHERE token_hash=:h AND purpose=\'staff_credential_setup\''),{'h':digest})).scalar_one_or_none()
        if hint is None: raise proof_failed()
        await lock_credential_domain(self.db,[hint])
        token=(await self.db.execute(text('SELECT * FROM public.staff_credential_setup_tokens WHERE token_hash=:h FOR UPDATE'),{'h':digest})).mappings().one_or_none()
        if (not token or token['purpose']!='staff_credential_setup' or token['email']!=hint or token['used_at'] or token['revoked_at']
                or token['expires_at']<=datetime.now(timezone.utc)):
            raise proof_failed()
        staff=StaffManagementService(self.db,token['tenant_id'],'t_'+token['tenant_id'].hex)
        authority=await staff.lock_authority(exclusive=True)
        if authority.state!='verified' or authority.owner_user_id==token['user_id']: raise proof_failed()
        member=await staff.member(token['user_id'])
        if member['email']!=hint or member['version']!=token['membership_version'] or member['employment_state']!='invited' or member['credential_state']!='pending':
            raise proof_failed()
        await self._assert_not_customer(staff,token['user_id'])
        rows=[]
        tenants=(await self.db.execute(text('SELECT id FROM public.wholesalers WHERE is_deleted IS FALSE ORDER BY id'))).scalars().all()
        for tid in tenants:
            schema='t_'+tid.hex
            try:
                async with self.db.begin_nested():
                    copies=(await self.db.execute(text(f'SELECT id,password_hash,is_active,is_deleted FROM "{schema}".users WHERE lower(email)=:e ORDER BY id FOR UPDATE'),{'e':hint})).mappings().all()
            except Exception:
                raise proof_failed() from None
            rows.extend((schema,r) for r in copies if not (schema==staff.schema and r['id']==token['user_id']))
        active=[r['password_hash'] for _,r in rows if r['is_active'] and not r['is_deleted']]
        event=await self.db.scalar(text("SELECT details FROM public.staff_stock_audit_events WHERE tenant_id=:t AND subject_id=:u AND event_type='staff_invited' AND (details->>'version')::bigint=:v"),
            {'t':staff.tenant_id,'u':token['user_id'],'v':member['version']})
        if not event: raise proof_failed()
        # An inactive target is not a second current credential authority.
        # When no active copy exists, its established credential remains the
        # proof fallback; otherwise the complete active-copy set is authority.
        if event['target_had_credential'] and not active:
            active.append(await self.db.scalar(text(f'SELECT password_hash FROM {staff.q}.users WHERE id=:u FOR UPDATE'),{'u':token['user_id']}))
        if active:
            try: valid=all(verify_password(password,hashed) for hashed in active)
            except (ValueError,TypeError): valid=False
            if not valid: raise proof_failed()
            verified_hash=active[0]
        else:
            if rows: raise proof_failed()
            verified_hash=hash_password(password)
        await self.db.execute(text(f'UPDATE {staff.q}.users SET password_hash=:p,is_active=TRUE,updated_at=now() WHERE id=:u AND is_deleted IS FALSE'),{'p':verified_hash,'u':token['user_id']})
        await staff.invalidate_approval_policy(user_id=token['user_id'])
        await self.db.execute(text(f"UPDATE {staff.q}.staff_memberships SET credential_state='ready',employment_state='active',version=version+1,updated_at=now() WHERE user_id=:u"),{'u':token['user_id']})
        await self.db.execute(text('UPDATE public.staff_credential_setup_tokens SET used_at=now() WHERE id=:i'),{'i':token['id']})
        await staff._advance()
        await staff.audit(token['user_id'],'staff_joined',token['user_id'],{'version':member['version']+1})
        return {'action':'joined'}

    async def _assert_not_customer(self,staff,user_id):
        mapped=await self.db.scalar(text('SELECT EXISTS (SELECT 1 FROM public.wholesaler_retailer_bindings WHERE wholesaler_id=:t AND tenant_user_id=:u)'),{'t':staff.tenant_id,'u':user_id})
        client=await self.db.scalar(text(f'SELECT EXISTS (SELECT 1 FROM {staff.q}.user_roles ur JOIN {staff.q}.role_permissions rp ON rp.role_id=ur.role_id JOIN {staff.q}.permissions p ON p.id=rp.permission_id WHERE ur.user_id=:u AND p.code LIKE \'client:%\')'),{'u':user_id})
        if mapped or client: raise proof_failed()
