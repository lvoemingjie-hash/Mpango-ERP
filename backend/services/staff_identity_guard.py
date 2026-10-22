"""Small transaction-level credential mutex; no global identity catalogue."""
from __future__ import annotations

import hashlib
from collections.abc import Iterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def normalize_staff_email(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError('STAFF_EMAIL_INVALID')
    result = value.strip().lower()
    if not result or len(result) > 255 or '@' not in result or any(c.isspace() for c in result):
        raise ValueError('STAFF_EMAIL_INVALID')
    return result


def credential_mutex_key(email: str) -> int:
    digest = hashlib.sha256(b'mpango/staff-credential/v1\0' + normalize_staff_email(email).encode('utf-8')).digest()
    return int.from_bytes(digest[:8], byteorder='big', signed=True)


async def lock_credential_emails(db: AsyncSession, emails: Iterable[str]) -> None:
    """Acquire the complete set before authority/user/token locks; held to commit."""
    keys = sorted({normalize_staff_email(value) for value in emails})
    await db.execute(text("SELECT set_config('lock_timeout','5s',true)"))
    for email in keys:
        await db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': credential_mutex_key(email)})


async def lock_credential_domain(db: AsyncSession, emails: Iterable[str], *, tenant_ids=()) -> None:
    """Identity keys first, then existing authority rows in UUID order.

    Old schemas without M1 tables retain their old writer contract. A caller
    may reuse its acquired set, never expand identity keys after authority.
    """
    keys=frozenset(normalize_staff_email(e) for e in emails)
    transaction=db.sync_session.get_transaction()
    held=db.info.get('_staff_credential_domain')
    required=set(tenant_ids)
    if held and held[0] is transaction:
        if not keys <= held[1] or not required <= held[2]:
            raise RuntimeError('STAFF_CREDENTIAL_LOCK_ORDER')
        return
    await lock_credential_emails(db, keys)
    tenants=(await db.execute(text('SELECT id FROM public.wholesalers WHERE is_deleted IS FALSE ORDER BY id'))).scalars().all()
    async def affected():
        result=set(required)
        result.update((await db.execute(text(
            'SELECT wholesaler_id FROM public.tenant_registrations '
            'WHERE lower(owner_email)=ANY(:emails) AND wholesaler_id IS NOT NULL AND is_deleted IS FALSE'),
            {'emails':list(keys)})).scalars())
        for tenant_id in tenants:
            schema='t_'+tenant_id.hex
            if (await db.execute(text('SELECT to_regclass(:name)'), {'name':schema+'.users'})).scalar() is None:
                # An unresolved legacy schema is conservatively involved;
                # the specific writer still owns its complete-scan policy.
                result.add(tenant_id)
                continue
            if await db.scalar(text(f'SELECT EXISTS (SELECT 1 FROM "{schema}".users WHERE lower(email)=ANY(:emails))'), {'emails':list(keys)}):
                result.add(tenant_id)
        return result
    selected=await affected()
    for tenant_id in sorted(selected):
        schema='t_'+tenant_id.hex
        if (await db.execute(text('SELECT to_regclass(:name)'), {'name':schema+'.staff_authority'})).scalar() is not None:
            await db.execute(text(f'SELECT singleton FROM "{schema}".staff_authority WHERE singleton=1 FOR UPDATE'))
    if await affected() != selected:
        raise RuntimeError('STAFF_CREDENTIAL_MAPPING_CHANGED')
    db.info['_staff_credential_domain']=(db.sync_session.get_transaction(),keys,frozenset(selected))


async def assert_not_managed_customer(db: AsyncSession, schema: str, user_id) -> None:
    """Retailer mapping must never take over any managed employee."""
    from db.sql_safety import validate_identifier
    validate_identifier(schema)
    if (await db.execute(text('SELECT to_regclass(:name)'), {'name':schema+'.staff_memberships'})).scalar() is not None:
        if (await db.execute(text(f'SELECT EXISTS (SELECT 1 FROM "{schema}".staff_memberships WHERE user_id=:u)'), {'u':user_id})).scalar_one():
            raise RuntimeError('RETAILER_STAFF_IDENTITY_CONFLICT')


async def assert_managed_credential_write_allowed(db: AsyncSession, schema: str, user_id) -> None:
    from db.sql_safety import validate_identifier
    validate_identifier(schema)
    if (await db.execute(text('SELECT to_regclass(:name)'), {'name':schema+'.staff_memberships'})).scalar() is not None:
        state=(await db.execute(text(f'SELECT employment_state FROM "{schema}".staff_memberships WHERE user_id=:u'), {'u':user_id})).scalar()
        if state is not None and state!='active':
            raise RuntimeError('STAFF_CREDENTIAL_MEMBERSHIP_INACTIVE')
