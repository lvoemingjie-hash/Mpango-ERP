"""M1 authority primitives. Unmapped history is not an inferred Owner."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


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

    async def lock_authority(self, *, exclusive: bool = False) -> LockedStaffAuthority:
        row = (await self.db.execute(text(
            f'SELECT * FROM {self.q}.staff_authority WHERE singleton=1 '
            + ('FOR UPDATE' if exclusive else 'FOR SHARE')))).mappings().one_or_none()
        if row is None:
            raise staff_error('OWNER_MAPPING_REQUIRED')
        registration = (await self.db.execute(text(
            'SELECT tr.id FROM public.tenant_registrations tr '
            'JOIN public.wholesalers w ON w.id=tr.wholesaler_id '
            'WHERE tr.tenant_schema=:s AND tr.wholesaler_id=:t AND tr.is_deleted IS FALSE '
            "AND tr.status IN ('provisioning','active') AND w.is_deleted IS FALSE AND w.status='active'"),
            {'s': self.schema, 't': self.tenant_id})).scalar_one_or_none()
        if (registration is None or row['tenant_id'] != self.tenant_id
                or row['registration_id'] != registration):
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

    async def require_owner(self, actor_id: UUID | str, *, exclusive: bool = False) -> LockedStaffAuthority:
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
            await self.db.execute(text(
                f'UPDATE {self.q}.staff_authority SET owner_user_id=:u,state=\'verified\',source=:source, '
                'evidence_digest=:digest,authz_revision=authz_revision+1,updated_at=now() WHERE singleton=1'),
                {'u': user_id, 'source': source, 'digest': evidence_digest})
            await self.audit(user_id, 'owner_bound', user_id, {'source': source, 'evidence_digest': evidence_digest})
        return {'action': 'would_bind' if dry_run else 'bound', 'dry_run': dry_run}

    async def audit(self, actor_id: UUID, event_type: str, subject_id: UUID, details: dict) -> None:
        import json
        await self.db.execute(text(
            'INSERT INTO public.staff_stock_audit_events (tenant_id,actor_id,event_type,subject_id,details) '
            'VALUES (:t,:a,:event,:s,CAST(:details AS jsonb))'),
            {'t': self.tenant_id, 'a': actor_id, 'event': event_type, 's': subject_id,
             'details': json.dumps(details, sort_keys=True)})


def setup_binding_digest(registration_id: UUID, user_id: UUID) -> str:
    return hashlib.sha256(('mpango/owner-setup/v1\0'+str(registration_id)+'\0'+str(user_id)).encode()).hexdigest()
