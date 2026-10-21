"""Explicit approved historical Owner mapping; dry-run unless --apply is supplied.

This command does not select users or discover a plausible Owner. Credentials
are read from DATABASE_URL only, never command-line arguments or output.
"""
import argparse
import asyncio
import json
import os
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from services.staff_identity_guard import lock_credential_emails
from services.staff_management_service import StaffManagementService, checked_staff_schema


async def bind(args):
    q = checked_staff_schema(args.tenant_id, args.schema)
    url = os.environ['DATABASE_URL']
    if url.startswith('postgresql://'):
        url = url.replace('postgresql://', 'postgresql+asyncpg://', 1)
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with async_sessionmaker(engine)() as db:
            async with db.begin():
                hint = (await db.execute(text(f'SELECT email FROM {q}.users WHERE id=:u'),
                                         {'u': args.user_id})).scalar_one_or_none()
                if hint is None:
                    raise RuntimeError('OWNER_MAPPING_REQUIRED')
                await lock_credential_emails(db, [hint])
                service = StaffManagementService(db, args.tenant_id, args.schema)
                result = await service.bind_owner(registration_id=args.registration_id, user_id=args.user_id,
                    source='approved_mapping', evidence_digest=args.approval_sha256, dry_run=not args.apply)
                # The hint is not authority; reject an email change before the mutex.
                actual = (await db.execute(text(f'SELECT email FROM {q}.users WHERE id=:u'),
                                           {'u': args.user_id})).scalar_one()
                if actual != hint:
                    raise RuntimeError('OWNER_BINDING_IDENTITY_CHANGED')
                if not args.apply:
                    await db.rollback()
                return result
    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tenant-id', type=UUID, required=True)
    parser.add_argument('--registration-id', type=UUID, required=True)
    parser.add_argument('--schema', required=True)
    parser.add_argument('--user-id', type=UUID, required=True)
    parser.add_argument('--approval-sha256', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        result = asyncio.run(bind(args))
    except Exception:
        print(json.dumps({'result': 'OWNER_BINDING_REFUSED'}))
        raise SystemExit(4) from None
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
