"""Bounded private media reconciliation; dry-run unless explicitly requested.

Hold the same cross-worker write lease as uploads through the full DB read and
file decision. Unknown files are never adopted or removed. Credentials come
only from IMAGE_RECONCILE_DATABASE_URL, never command arguments or output.
"""
import argparse
import asyncio
import json
import os
import stat
from datetime import datetime, timedelta, timezone
from uuid import UUID

import asyncpg

from services.product_image_storage import DATABASE_IDENTITY_SQL, MediaStore, _directory, canonical_uuid


async def reconcile(root, tenant, execute=False):
    tenant = canonical_uuid(tenant)
    url = os.environ.get('IMAGE_RECONCILE_DATABASE_URL')
    if not url:
        raise RuntimeError('IMAGE_RECONCILE_DATABASE_REQUIRED')
    store = MediaStore(root)
    lock = None
    connection = None
    result = {'tenant': tenant, 'execute': execute, 'eligible': [], 'deleted': [], 'unknown': []}
    try:
        lock = store.acquire_write()
        connection = await asyncpg.connect(url, timeout=5)
        async with connection.transaction(readonly=True):
            # Validate the independently prepared root/DB pair BEFORE walking
            # versions or applying even a perfectly valid wrong DB's pointers.
            store.verify_database(dict(await connection.fetchrow(DATABASE_IDENTITY_SQL)))
            schema = 't_' + UUID(tenant).hex
            await connection.execute(f'SET LOCAL search_path TO "{schema}", public')
            current = {str(row['product_id']): str(row['current_version'])
                for row in await connection.fetch('SELECT product_id,current_version FROM catalog_product_images')}
            tfd = _directory(store.fd, tenant)
            try:
                products = os.listdir(tfd)
                if len(products) > 12000:
                    raise RuntimeError('IMAGE_INVENTORY_LIMIT')
                for product in products:
                    canonical_uuid(product)
                    pfd = _directory(tfd, product)
                    try:
                        versions = os.listdir(pfd)
                        if len(versions) > 12000:
                            raise RuntimeError('IMAGE_INVENTORY_LIMIT')
                        for version in versions:
                            if version == current.get(product):
                                continue
                            if version.startswith('.'):
                                result['unknown'].append([product, version])
                                continue
                            canonical_uuid(version)
                            vfd = _directory(pfd, version)
                            try:
                                if set(os.listdir(vfd)) != {'thumb.webp', 'detail.webp', 'manifest.json'}:
                                    result['unknown'].append([product, version])
                                    continue
                                record_fd = os.open('manifest.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=vfd)
                                try:
                                    st = os.fstat(record_fd)
                                    if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) != 0o600 or not 0 < st.st_size <= 4096:
                                        raise RuntimeError('IMAGE_MANIFEST_IDENTITY')
                                    record = json.loads(os.read(record_fd, 4097))
                                finally:
                                    os.close(record_fd)
                                if (record['tenant'], record['product'], record['version']) != (tenant, product, version):
                                    raise RuntimeError('IMAGE_MANIFEST_ATTRIBUTION')
                                created = datetime.fromisoformat(record['created_utc'])
                                if created.tzinfo is None or created > datetime.now(timezone.utc) - timedelta(hours=24):
                                    continue
                                for variant in ('thumb', 'detail'):
                                    store.read(tenant, product, version, variant, record['variants'][variant])
                                # The write lease excludes both new uncommitted
                                # pointers and concurrent replacement/backup.
                                live = await connection.fetchval('SELECT current_version FROM catalog_product_images WHERE product_id=$1', UUID(product))
                                if str(live) == version:
                                    raise RuntimeError('IMAGE_CURRENT_VERSION_CHANGED')
                                result['eligible'].append([product, version])
                                if execute:
                                    for name in ('thumb.webp', 'detail.webp', 'manifest.json'):
                                        os.unlink(name, dir_fd=vfd)
                                    os.fsync(vfd)
                                    os.rmdir(version, dir_fd=pfd)
                                    os.fsync(pfd)
                                    result['deleted'].append([product, version])
                            finally:
                                os.close(vfd)
                    finally:
                        os.close(pfd)
            finally:
                os.close(tfd)
        return result
    finally:
        if connection is not None:
            await connection.close()
        if lock is not None:
            os.close(lock)
        store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--tenant', required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    try:
        result = asyncio.run(reconcile(args.root, args.tenant, args.execute))
        print(json.dumps(result, sort_keys=True))
    except Exception:
        raise SystemExit('IMAGE_RECONCILE_REFUSED') from None


if __name__ == '__main__':
    main()
