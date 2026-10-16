"""Real PG and configured ASGI/JWT image commands; no auth overrides."""
import asyncio
import io
import os
import json
import hashlib
from pathlib import Path
from uuid import uuid4
from uuid import UUID

import pytest
from PIL import Image
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


def body():
    out = io.BytesIO()
    Image.new('RGB', (64, 48), '#276152').save(out, format='PNG')
    return out.getvalue()


def headers(world, revision=0, *, client=False):
    return {'Authorization': 'Bearer ' + world['client_token' if client else 'token'],
            'Content-Type': 'image/png', 'If-Match': str(revision), 'X-Idempotency-Key': 'media-must-not-buffer'}


def path(world):
    return '/api/v1/catalog-products/' + world['product'] + '/image'


async def economics(world):
    async with world['session']() as db:
        facts = {}
        for table in ('skus', 'retailer_prices', 'orders', 'order_items', 'inventory_stocks',
                      'inventory_reservations', 'payments', 'order_credit_holds',
                      'inventory_movements', 'ledger_entries'):
            facts[table] = (await db.execute(text(f'SELECT to_jsonb(t) FROM {table} t '
                'ORDER BY to_jsonb(t)::text'))).scalars().all()
        facts['binding'] = (await db.execute(text('SELECT to_jsonb(b) FROM '
            'public.wholesaler_retailer_bindings b WHERE wholesaler_id=:w ORDER BY retailer_id'),
            {'w': UUID(world['wid'])})).scalars().all()
        return facts


async def confirmed_cash_order(http, world):
    from tests.s1_pricing_quote.test_http import preview, submit, headers as order_headers
    created = await submit(http, world, await preview(http, world))
    assert created.status_code == 201, 'IMAGE_REAL_ORDER_CREATION'
    oid = created.json()['data']['id']
    confirmed = await http.post(f'/api/v1/orders/{oid}/confirm', headers=order_headers(world))
    assert confirmed.status_code == 200, 'IMAGE_REAL_ORDER_CONFIRM'
    return oid


async def seed_nonempty_history(http, world):
    from tests.s1_pricing_quote.test_http import headers as order_headers
    price = await http.put('/api/v1/pricing/prices', headers=order_headers(world), json={
        'retailer_id': world['rid'], 'sku_id': world['sku'], 'price': '90.00', 'expected_revision': 0})
    assert price.status_code == 200
    oid = await confirmed_cash_order(http, world)
    paid = await http.post(f'/api/v1/orders/{oid}/pay', json={'method': 'cash', 'amount': '180.00'},
                           headers=order_headers(world, key=str(uuid4())))
    assert paid.status_code == 200, 'IMAGE_REAL_CASH_PAYMENT'
    fulfilled = await http.post(f'/api/v1/orders/{oid}/fulfill', headers=order_headers(world))
    assert fulfilled.status_code == 200, 'IMAGE_REAL_STOCK_MOVEMENT'
    await confirmed_cash_order(http, world)
    facts = await economics(world)
    assert all(facts.values()), 'IMAGE_NONEMPTY_ECONOMIC_RAW_VECTORS'


@pytest.mark.parametrize('world', ['UG', 'KE'], indirect=True)
async def test_upload_replace_delete_refresh_reupload(r1_client, world):
    await seed_nonempty_history(r1_client, world)
    before = await economics(world)
    first = await r1_client.put(path(world), content=body(), headers=headers(world))
    assert first.status_code == 200, 'IMAGE_REAL_UPLOAD'
    state = first.json()['data']
    assert state['image_revision'] == 1 and state['image']['revision'] == 1
    first_version = state['image']['version']
    for client in (False, True):
        prefix = '/api/v1/' + ('client/products' if client else 'catalog-products')
        response = await r1_client.get(f"{prefix}/{world['product']}/image/{first_version}/thumb", headers=headers(world, client=client))
        assert response.status_code == 200 and response.headers['content-type'] == 'image/webp', 'IMAGE_AUTHORIZED_GET'
        assert response.headers['cache-control'] == 'private, no-store'
    replaced = await r1_client.put(path(world), content=body(), headers=headers(world, 1))
    assert replaced.status_code == 200 and replaced.json()['data']['image_revision'] == 2
    old = await r1_client.get(path(world) + '/' + first_version + '/thumb', headers=headers(world))
    assert old.status_code == 404, 'IMAGE_OLD_VERSION_REJECTED'
    removed = await r1_client.delete(path(world), headers=headers(world, 2))
    assert removed.status_code == 200 and removed.json()['data'] == {'image_revision': 3, 'image': None}
    replay = await r1_client.delete(path(world), headers=headers(world, 3))
    assert replay.status_code == 200 and replay.json()['data']['image_revision'] == 3, 'IMAGE_EMPTY_DELETE_NOOP'
    refreshed = await r1_client.get(path(world).removesuffix('/image'), headers=headers(world))
    assert refreshed.status_code == 200 and refreshed.json()['data']['image_revision'] == 3
    assert refreshed.json()['data']['image'] is None, 'IMAGE_TOMBSTONE_IS_READABLE'
    again = await r1_client.put(path(world), content=body(), headers=headers(world, 3))
    assert again.status_code == 200 and again.json()['data']['image_revision'] == 4
    assert await economics(world) == before, 'IMAGE_ZERO_EXTRA_ECONOMIC_EFFECT'


async def test_real_auth_refuses_before_stream_with_hostile_key(r1_client, world):
    for auth in (None, headers(world, client=True)['Authorization']):
        consumed = []
        async def chunks():
            consumed.append(True)
            yield b'x' * 1024
        supplied = {'Content-Type': 'image/png', 'If-Match': '0', 'X-Idempotency-Key': 'attacker-supplied'}
        if auth: supplied['Authorization'] = auth
        response = await r1_client.put(path(world), content=chunks(), headers=supplied)
        assert response.status_code in (401, 403), 'IMAGE_REAL_AUTH_REFUSAL'
        assert consumed == [], 'IMAGE_AUTH_BEFORE_BODY_CONSUMPTION'
    async with world['session']() as db:
        assert (await db.execute(text('SELECT count(*) FROM catalog_product_images'))).scalar_one() == 0


async def test_native_chunked_oversize_is_rejected_without_pointer(r1_client, world):
    consumed = []
    async def chunks():
        for _ in range(7):
            consumed.append(1)
            yield b'x' * 1024**2
    response = await r1_client.put(path(world), content=chunks(), headers=headers(world))
    assert response.status_code == 413, 'IMAGE_NATIVE_BYTE_LIMIT'
    assert len(consumed) <= 6
    async with world['session']() as db:
        assert (await db.execute(text('SELECT count(*) FROM catalog_product_images'))).scalar_one() == 0


async def test_two_writers_one_winner_and_stale_revision_rejected(r1_client, world):
    results = await asyncio.gather(*[
        r1_client.put(path(world), content=body(), headers=headers(world)) for _ in range(2)])
    assert sum(result.status_code == 200 for result in results) == 1, 'IMAGE_CONCURRENT_ONE_WINNER'
    assert all(result.status_code in (200, 409, 429) for result in results)
    loser = await r1_client.put(path(world), content=body(), headers=headers(world))
    assert loser.status_code == 409, 'IMAGE_STALE_REVISION_MUST_REJECT'
    async with world['session']() as db:
        assert (await db.execute(text('SELECT image_revision FROM catalog_product_images'))).scalar_one() == 1


async def test_other_tenant_and_revoked_binding_cannot_read(r1_client, world, other_world):
    response = await r1_client.put(path(world), content=body(), headers=headers(world))
    assert response.status_code == 200
    version = response.json()['data']['image']['version']
    url = f"/api/v1/client/products/{world['product']}/image/{version}/thumb"
    denied = await r1_client.get(url, headers=headers(other_world, client=True))
    assert denied.status_code == 404, 'IMAGE_CROSS_TENANT_MUST_REJECT'
    async with world['session']() as db:
        await db.execute(text('UPDATE public.wholesaler_retailer_bindings SET is_deleted=true WHERE wholesaler_id=:wid AND retailer_id=:rid'), {'wid': UUID(world['wid']), 'rid': UUID(world['rid'])})
        await db.commit()
    revoked = await r1_client.get(url, headers=headers(world, client=True))
    assert revoked.status_code == 403, 'IMAGE_REVOKED_BINDING_MUST_REJECT'


async def test_inactive_product_has_no_retailer_image_escape(r1_client, world):
    response = await r1_client.put(path(world), content=body(), headers=headers(world))
    assert response.status_code == 200
    version = response.json()['data']['image']['version']
    async with world['session']() as db:
        await db.execute(text('UPDATE catalog_products SET is_active=false WHERE id=:pid'), {'pid': UUID(world['product'])})
        await db.commit()
    client_url = f"/api/v1/client/products/{world['product']}/image/{version}/thumb"
    denied = await r1_client.get(client_url, headers=headers(world, client=True))
    assert denied.status_code == 404, 'IMAGE_INACTIVE_PRODUCT_MUST_REJECT'
    merchant = await r1_client.get(path(world) + '/' + version + '/thumb', headers=headers(world))
    assert merchant.status_code == 200, 'IMAGE_MERCHANT_MAINTENANCE_CONTROL'


async def test_database_flush_failure_keeps_previous_reference(r1_client, world, monkeypatch):
    await seed_nonempty_history(r1_client, world)
    first = await r1_client.put(path(world), content=body(), headers=headers(world))
    assert first.status_code == 200
    expected = first.json()['data']
    from sqlalchemy.ext.asyncio import AsyncSession
    async def fail(_self, *args, **kwargs):
        raise OSError('synthetic database failure')
    with monkeypatch.context() as scoped:
        scoped.setattr(AsyncSession, 'flush', fail)
        failed = await r1_client.put(path(world), content=body(), headers=headers(world, 1))
    assert failed.status_code == 503, 'IMAGE_FAILED_COMMIT_NOT_SUCCESS'
    refreshed = await r1_client.get(path(world).removesuffix('/image'), headers=headers(world))
    assert refreshed.status_code == 200
    assert refreshed.json()['data']['image_revision'] == expected['image_revision']
    assert refreshed.json()['data']['image']['version'] == expected['image']['version']


@pytest.mark.parametrize('outcome', ['success', 'failure', 'cancel'])
async def test_paused_real_storage_does_not_block_quote_and_cash_or_lose_lease(r1_client, world, monkeypatch, outcome):
    import threading
    from services.product_image_storage import MediaStore
    from tests.s1_pricing_quote.test_http import preview, headers as order_headers
    from core.config import get_settings
    oid = await confirmed_cash_order(r1_client, world)
    entered, finished = asyncio.Event(), asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    original = MediaStore.publish
    def paused(store, *args):
        loop.call_soon_threadsafe(entered.set)
        assert release.wait(8), 'IMAGE_BARRIER_NOT_RELEASED'
        try:
            result = original(store, *args)
            if outcome == 'failure': raise OSError('synthetic post-publication failure')
            return result
        finally:
            loop.call_soon_threadsafe(finished.set)
    monkeypatch.setattr(MediaStore, 'publish', paused)
    task = asyncio.create_task(r1_client.put(path(world), content=body(), headers=headers(world)))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        quote = await asyncio.wait_for(preview(r1_client, world), 2)
        assert quote['total'] == '180.00', 'IMAGE_PAUSE_REAL_QUOTE_PROGRESS'
        paid = await asyncio.wait_for(r1_client.post(f'/api/v1/orders/{oid}/pay',
            json={'method': 'cash', 'amount': '180.00'},
            headers=order_headers(world, key=str(uuid4()))), 2)
        assert paid.status_code == 200, 'IMAGE_PAUSE_REAL_CASH_PROGRESS'
        cash_facts = await economics(world)
        if outcome == 'cancel':
            task.cancel()
            with pytest.raises(asyncio.CancelledError): await task
            other = MediaStore(get_settings().PRODUCT_IMAGE_ROOT)
            try:
                from fastapi import HTTPException
                with pytest.raises(HTTPException, match='IMAGE_BUSY'): other.acquire_write()
            finally:
                other.close()
    finally:
        release.set()
        await asyncio.wait_for(finished.wait(), 5)
    if outcome != 'cancel':
        result = await asyncio.wait_for(task, 5)
        assert result.status_code == (200 if outcome == 'success' else 503)
    # A sentinel writer obtains the real flock only after the last worker has
    # finished and request finalization has released transaction ownership.
    from fastapi import HTTPException
    for _ in range(100):
        store = MediaStore(get_settings().PRODUCT_IMAGE_ROOT)
        try:
            fd = store.acquire_write()
            os.close(fd)
            break
        except HTTPException as exc:
            assert exc.detail['code'] == 'IMAGE_BUSY'
            await asyncio.sleep(0.01)
        finally:
            store.close()
    else:
        pytest.fail('IMAGE_LATE_WORKER_LEASE_NOT_RELEASED')
    async with world['session']() as db:
        revisions = (await db.execute(text('SELECT image_revision FROM catalog_product_images'))).scalars().all()
        assert revisions == ([1] if outcome == 'success' else []), 'IMAGE_NO_LATE_POINTER_WRITE'
    assert await economics(world) == cash_facts, 'IMAGE_NO_EXTRA_ECONOMIC_EFFECT_AFTER_CASH'


async def test_gc_wrong_database_same_tenant_refuses_before_unlink_and_positive_scope(r1_client, world, tmp_path, monkeypatch):
    import asyncpg
    import psycopg2
    from core.config import get_settings
    from services.product_image_storage import MediaStore, DATABASE_IDENTITY_SQL
    from services.product_image_processor import _decode
    from scripts.reconcile_product_image_files import reconcile
    from tests.async_test_utils import temporary_database_url
    from tests.order_state_r2.test_migration_c3 import _engine, _grant_product_minimum, _run_in_fresh_loop
    from tests.s1_pricing_quote.test_migration import upgrade
    from scripts.bootstrap_tenant_schema import bootstrap
    response = await r1_client.put(path(world), content=body(), headers=headers(world))
    assert response.status_code == 200
    current = response.json()['data']['image']['version']
    root = Path(get_settings().PRODUCT_IMAGE_ROOT)
    monkeypatch.setenv('IMAGE_RECONCILE_DATABASE_URL', os.environ['TEST_DATABASE_URL'])
    def snapshot():
        return {str(p.relative_to(root)): (p.stat().st_mode, hashlib.sha256(p.read_bytes()).hexdigest())
                for p in root.rglob('*') if p.is_file()}
    store = MediaStore(str(root)); lock = store.acquire_write()
    try:
        old, _ = store.publish(world['wid'], world['product'], _decode(body(), 'PNG'))
        fresh, _ = store.publish(world['wid'], world['product'], _decode(body(), 'PNG'))
        incomplete, _ = store.publish(world['wid'], world['product'], _decode(body(), 'PNG'))
    finally:
        os.close(lock); store.close()
    parent = root / world['wid'] / world['product']
    record_path = parent / str(old) / 'manifest.json'
    record = json.loads(record_path.read_bytes())
    record['created_utc'] = '2000-01-01T00:00:00+00:00'
    record_path.write_text(json.dumps(record))
    (parent / str(incomplete) / 'detail.webp').unlink()
    unknown = parent / '.owned-incomplete.pending'; unknown.mkdir(mode=0o700)
    marker = root / 'media-binding.json'
    marker_bytes = marker.read_bytes()
    from fastapi import HTTPException
    # Missing/conflicting root binding are permanent negative controls.
    saved = tmp_path / 'owned-binding'
    marker.rename(saved)
    before = snapshot()
    try:
        with pytest.raises(HTTPException, match='IMAGE_DATABASE_BINDING_REQUIRED'):
            await reconcile(str(root), world['wid'], True)
        assert snapshot() == before
    finally:
        saved.rename(marker)
    changed = json.loads(marker_bytes); changed['root_inode'] += 1
    marker.write_text(json.dumps(changed))
    before = snapshot()
    try:
        with pytest.raises(HTTPException, match='IMAGE_DATABASE_BINDING_MISMATCH'):
            await reconcile(str(root), world['wid'], True)
        assert snapshot() == before
    finally:
        marker.write_bytes(marker_bytes)
    # A fully migrated second database with the SAME tenant/product IDs and
    # valid media objects, but a different current pointer. Even copying the
    # approved comment cannot forge the actual database OID/name binding.
    with temporary_database_url(os.environ['TEST_DATABASE_URL'], 'imagewrongdb') as url:
        engine = _engine(url)
        try:
            upgrade(url, '041_catalog_product_main_image')
            _grant_product_minimum(engine)
            with engine.begin() as db:
                from psycopg2 import sql
                db.connection.driver_connection.cursor().execute(
                    sql.SQL('COMMENT ON DATABASE {} IS %s').format(sql.Identifier(db.engine.url.database)),
                    (json.loads(marker_bytes)['database']['pairing'],))
            _run_in_fresh_loop(asyncio.run, bootstrap(world['schema'], url.app_url))
            wrong = await asyncpg.connect(url.app_url.replace('postgresql+asyncpg://', 'postgresql://'))
            try:
                await wrong.execute(f'SET search_path TO "{world["schema"]}", public')
                await wrong.execute('INSERT INTO catalog_products(id,name) VALUES($1,\'Other target\')', UUID(world['product']))
                await wrong.execute('INSERT INTO catalog_product_images(product_id,image_revision,current_version,variants) '
                    'VALUES($1,1,$2,$3::jsonb)', UUID(world['product']), old, json.dumps(record['variants']))
                assert str(await wrong.fetchval('SELECT current_version FROM catalog_product_images')) != current
                identity = dict(await wrong.fetchrow(DATABASE_IDENTITY_SQL))
                assert identity['pairing'] == json.loads(marker_bytes)['database']['pairing']
            finally:
                await wrong.close()
            monkeypatch.setenv('IMAGE_RECONCILE_DATABASE_URL', url.app_url.replace('postgresql+asyncpg://', 'postgresql://'))
            before = snapshot()
            with pytest.raises(HTTPException, match='IMAGE_DATABASE_BINDING_MISMATCH'):
                await reconcile(str(root), world['wid'], True)
            assert snapshot() == before, 'IMAGE_WRONG_DATABASE_ZERO_UNLINK'
        finally:
            engine.dispose()
    monkeypatch.setenv('IMAGE_RECONCILE_DATABASE_URL', os.environ['TEST_DATABASE_URL'])
    result = await reconcile(str(root), world['wid'], True)
    assert result['deleted'] == [[world['product'], str(old)]], 'IMAGE_GC_EXACT_EXPIRED_NONCURRENT_ONLY'
    assert all((parent / str(version)).exists() for version in (current, fresh, incomplete))
    assert unknown.exists() and not (parent / str(old)).exists()
