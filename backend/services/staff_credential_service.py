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


class StaffRecoveryTokenInvalidError(Exception):
    """Fixed internal reason only; public response never identifies a person."""
    def __init__(self, reason):
        self.reason=reason
        super().__init__('INVALID_OR_EXPIRED_STAFF_RECOVERY_TOKEN')


class StaffCredentialService:
    def __init__(self,db,*,settings=None):
        self.db=db
        self.settings=settings or get_settings()

    async def _recovery_member(self, staff, user_id):
        member=await staff.member(user_id)
        if (member['credential_state']!='ready' or member['employment_state']!='active'
                or not member['is_active']):
            raise staff_error('STAFF_RECOVERY_NOT_ELIGIBLE',409)
        await self._assert_not_customer(staff,user_id)
        row=(await self.db.execute(text(
            f'SELECT email,password_hash,credential_epoch FROM {staff.q}.users '
            'WHERE id=:u AND is_active IS TRUE AND is_deleted IS FALSE FOR UPDATE'),
            {'u':user_id})).one_or_none()
        if row is None or not row.password_hash:
            raise staff_error('STAFF_RECOVERY_NOT_ELIGIBLE',409)
        return member,row

    async def request_recovery(self, *, tenant_id, schema, actor_id, user_id, owner_password, expected_version):
        from services.staff_identity_guard import normalize_staff_email
        from services.email_delivery import record_staff_recovery_email
        staff=StaffManagementService(self.db,tenant_id,schema)
        actor=UUID(str(actor_id));user_id=UUID(str(user_id))
        hints=(await self.db.execute(text(
            f'SELECT id,email FROM {staff.q}.users WHERE id IN (:a,:u) AND is_deleted IS FALSE'),
            {'a':actor,'u':user_id})).all()
        hint={row.id:normalize_staff_email(row.email) for row in hints}
        if user_id not in hint: raise staff_error('STAFF_NOT_FOUND',404)
        if actor not in hint: raise staff_error('OWNER_REQUIRED',403)
        await lock_credential_domain(self.db,hint.values(),tenant_ids=[staff.tenant_id])
        owner=await staff.require_owner(actor,exclusive=True)
        if user_id==owner.owner_user_id: raise staff_error('OWNER_PROTECTED')
        own=(await self.db.execute(text(f'SELECT email,password_hash FROM {staff.q}.users WHERE id=:a'),{'a':actor})).one()
        if normalize_staff_email(own.email)!=hint[actor]: raise staff_error('STAFF_IDENTITY_CHANGED')
        try: reauthenticated=verify_password(owner_password,own.password_hash)
        except (TypeError,ValueError): reauthenticated=False
        if not reauthenticated: raise staff_error('OWNER_REAUTHENTICATION_REQUIRED',403)
        member,row=await self._recovery_member(staff,user_id)
        if row.email!=hint[user_id]: raise staff_error('STAFF_IDENTITY_CHANGED')
        if member['version']!=expected_version: raise staff_error('STALE_STAFF_VERSION')
        now=datetime.now(timezone.utc)
        last=await self.db.scalar(text('SELECT max(created_at) FROM public.staff_credential_recovery_tokens '
            'WHERE tenant_id=:t AND user_id=:u'),{'t':staff.tenant_id,'u':user_id})
        if last is not None and now-last<timedelta(seconds=60):
            raise staff_error('STAFF_RECOVERY_RESEND_TOO_SOON',429)
        await self.db.execute(text('UPDATE public.staff_credential_recovery_tokens SET revoked_at=:n '
            'WHERE tenant_id=:t AND user_id=:u AND used_at IS NULL AND revoked_at IS NULL'),
            {'n':now,'t':staff.tenant_id,'u':user_id})
        raw=generate_verification_token()
        await self.db.execute(text('INSERT INTO public.staff_credential_recovery_tokens '
            '(tenant_id,user_id,initiator_user_id,email,membership_version,target_credential_epoch,token_hash,created_at,expires_at) '
            'VALUES (:t,:u,:a,:e,:v,:g,:h,:n,:x)'),
            {'t':staff.tenant_id,'u':user_id,'a':actor,'e':hint[user_id],'v':member['version'],
             'g':row.credential_epoch,'h':hash_token(raw,self.settings),'n':now,'x':now+timedelta(minutes=15)})
        await staff.audit(actor,'staff_recovery_requested',user_id,{'version':member['version']})
        origin=(self.settings.PUBLIC_FRONTEND_URL or 'http://localhost:5173').rstrip('/')
        record_staff_recovery_email(settings=self.settings,to_email=hint[user_id],token=raw,
            link=origin+'/staff/recover-credential#token='+raw)
        return {'action':'recovery_requested','delivery':'accepted_not_confirmed','expires_in_seconds':900}

    async def consume_recovery(self, raw, password):
        from fastapi import HTTPException
        from services.password_reset_service import (_enumerate_active_tenant_users,
            PasswordResetScanIncompleteError, replace_active_password_copies)
        from services.staff_identity_guard import normalize_staff_email
        validate_password_policy(password)
        if len(password.encode('utf-8'))>72:
            raise ValueError('Password exceeds supported byte length')
        if not isinstance(raw,str) or not raw.strip(): raise StaffRecoveryTokenInvalidError('MISSING')
        digest=hash_token(raw.strip(),self.settings)
        hint=(await self.db.execute(text('SELECT email,tenant_id,initiator_user_id FROM '
            "public.staff_credential_recovery_tokens WHERE token_hash=:h AND purpose='staff_credential_recovery'"),
            {'h':digest})).one_or_none()
        if hint is None: raise StaffRecoveryTokenInvalidError('UNKNOWN')
        staff=StaffManagementService(self.db,hint.tenant_id,'t_'+hint.tenant_id.hex)
        owner_email=await self.db.scalar(text(f'SELECT email FROM {staff.q}.users WHERE id=:a'),{'a':hint.initiator_user_id})
        if not owner_email: raise StaffRecoveryTokenInvalidError('INITIATOR_MISSING')
        owner_hint=normalize_staff_email(owner_email)
        await lock_credential_domain(self.db,[hint.email,owner_hint],tenant_ids=[staff.tenant_id])
        token=(await self.db.execute(text('SELECT * FROM public.staff_credential_recovery_tokens '
            'WHERE token_hash=:h FOR UPDATE'),{'h':digest})).mappings().one_or_none()
        # Fresh clock AFTER all potentially blocking locks, not transaction now().
        if (not token or token['purpose']!='staff_credential_recovery' or token['used_at'] or token['revoked_at']
                or token['expires_at']<=datetime.now(timezone.utc) or token['email']!=hint.email
                or token['tenant_id']!=hint.tenant_id or token['initiator_user_id']!=hint.initiator_user_id):
            raise StaffRecoveryTokenInvalidError('TERMINAL_OR_EXPIRED')
        try:
            owner=await staff.require_owner(token['initiator_user_id'],exclusive=True)
            if owner.owner_user_id==token['user_id']: raise StaffRecoveryTokenInvalidError('OWNER_TARGET')
            actual_owner=await self.db.scalar(text(f'SELECT email FROM {staff.q}.users WHERE id=:a'),{'a':owner.owner_user_id})
            if normalize_staff_email(actual_owner)!=owner_hint: raise StaffRecoveryTokenInvalidError('INITIATOR_CHANGED')
            member,row=await self._recovery_member(staff,token['user_id'])
        except HTTPException:
            raise StaffRecoveryTokenInvalidError('AUTHORITY_OR_MEMBERSHIP_CHANGED') from None
        if (member['version']!=token['membership_version'] or row.email!=hint.email
                or row.credential_epoch!=token['target_credential_epoch']):
            raise StaffRecoveryTokenInvalidError('CREDENTIAL_OR_VERSION_CHANGED')
        scan=await _enumerate_active_tenant_users(self.db)
        if scan.failed_schema_count:
            raise PasswordResetScanIncompleteError(failed_schema_count=scan.failed_schema_count,
                scanned_schema_count=scan.scanned_schema_count)
        copies=[(schema,uid) for email,schema,uid in scan.rows if email==hint.email]
        if (staff.schema,token['user_id']) not in copies or len(copies)!=len(set(copies)):
            raise StaffRecoveryTokenInvalidError('TARGET_SET_CHANGED')
        # All row waits precede the final fresh expiry check. No authority
        # lock is acquired after these user locks; credential-domain order is
        # unchanged, and a non-credential profile update cannot stretch an
        # expiring link past its admission deadline.
        from db.sql_safety import validate_identifier
        for schema,uid in copies:
            try:validate_identifier(schema)
            except Exception:raise RuntimeError('STAFF_RECOVERY_COPY_SHAPE_INVALID') from None
            locked=await self.db.scalar(text(f'SELECT id FROM "{schema}".users WHERE id=:u '
                'AND lower(email)=:e AND is_active IS TRUE AND is_deleted IS FALSE FOR UPDATE'),
                {'u':uid,'e':hint.email})
            if locked!=uid:raise StaffRecoveryTokenInvalidError('TARGET_SET_CHANGED')
        if token['expires_at']<=datetime.now(timezone.utc):
            raise StaffRecoveryTokenInvalidError('EXPIRED_AFTER_ROW_LOCKS')
        replacement=hash_password(password)
        if token['expires_at']<=datetime.now(timezone.utc):
            raise StaffRecoveryTokenInvalidError('EXPIRED_BEFORE_APPLY')
        await replace_active_password_copies(self.db,copies,replacement,preserve_status=True)
        result=await self.db.execute(text('UPDATE public.staff_credential_recovery_tokens SET used_at=:n '
            'WHERE id=:i AND used_at IS NULL AND revoked_at IS NULL'),
            {'i':token['id'],'n':datetime.now(timezone.utc)})
        if result.rowcount!=1: raise StaffRecoveryTokenInvalidError('CONCURRENT_CONSUMPTION')
        await staff.audit(token['user_id'],'staff_recovery_completed',token['user_id'],{'version':member['version']})
        return {'action':'password_recovered','login_required':True}

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
