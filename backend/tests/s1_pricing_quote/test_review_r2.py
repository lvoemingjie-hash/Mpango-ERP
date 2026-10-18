"""CTO R2 counterexamples: real JWT/HTTP and task-only PostgreSQL."""
import asyncio
import ast
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import os
from pathlib import Path
import threading
import uuid

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from tests.s1_pricing_quote.test_http import headers, preview, facts
from tests.s1_pricing_quote.test_migration import (
    upgrade, register, predecessor_bootstrap, catalog,
)
from tests.async_test_utils import temporary_database_url
from tests.order_state_r2.test_migration_c3 import (
    _engine, _grant_product_minimum, _run_in_fresh_loop,
)

BACKEND = Path(__file__).resolve().parents[2]


async def old_override(world, retired=False):
    async with world['session']() as db:
        await db.execute(text('UPDATE skus SET base_price=100 WHERE id=:id'),
                         {'id': uuid.UUID(world['sku'])})
        row = (await db.execute(text('INSERT INTO retailer_prices '
            '(sku_id,retailer_id,price,is_deleted,created_by) '
            'VALUES (:sid,:rid,90.01,:retired,:actor) RETURNING id,created_by,created_at'),
            {'sid': uuid.UUID(world['sku']), 'rid': uuid.UUID(world['rid']),
             'retired': retired, 'actor': uuid.UUID(world['actor'])})).one()
        await db.commit()
        return tuple(row)


@pytest.mark.asyncio
@pytest.mark.parametrize('world', ['UG'], indirect=True)
async def test_old_override_retirement_restore_and_zero_effects(r1_client, world):
    original = await old_override(world)
    before = await facts(world)
    body = {'retailer_id': world['rid'], 'sku_id': world['sku'], 'price': '90.01',
            'expected_revision': 0, 'retire': True}
    result = await r1_client.put('/api/v1/pricing/prices', json=body, headers=headers(world))
    assert result.status_code == 200, 'R2_AC01_OLD_AMOUNT_RETIRE'
    assert Decimal(result.json()['data']['price']) == Decimal('90.01')
    assert (await preview(r1_client, world))['total'] == '200'
    bad = await r1_client.put('/api/v1/pricing/prices', json={**body, 'retire': False,
        'expected_revision': 1}, headers=headers(world))
    assert bad.status_code == 422 and bad.json()['code'] == 'MONEY_PRECISION'
    good = await r1_client.put('/api/v1/pricing/prices', json={**body, 'retire': False,
        'expected_revision': 1, 'price': '95'}, headers=headers(world))
    assert good.status_code == 200
    async with world['session']() as db:
        row = (await db.execute(text('SELECT id,created_by,created_at,price,is_deleted '
                                    'FROM retailer_prices'))).one()
        assert tuple(row[:3]) == original and row.price == 95 and not row.is_deleted
        assert (await db.execute(text('SELECT pricing_revision FROM skus'))).scalar_one() == 2
    assert await facts(world) == before, 'R2_AC01_ZERO_ECONOMICS'


@pytest.mark.asyncio
async def test_retire_cannot_create_or_change_amount(r1_client, world):
    body = {'retailer_id': world['rid'], 'sku_id': world['sku'], 'price': '80',
            'expected_revision': 0, 'retire': True}
    missing = await r1_client.put('/api/v1/pricing/prices', json=body, headers=headers(world))
    assert missing.status_code == 404, 'R2_AC01_NO_MISSING_RETIRE_ROW'
    await old_override(world)
    different = await r1_client.put('/api/v1/pricing/prices', json=body, headers=headers(world))
    assert different.status_code == 409, 'R2_AC01_NO_RETIRE_AMOUNT_WRITE'
    async with world['session']() as db:
        assert (await db.execute(text('SELECT price,is_deleted FROM retailer_prices'))).one() == (Decimal('90.01'), False)
        assert (await db.execute(text('SELECT pricing_revision FROM skus'))).scalar_one() == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('world', ['UG'], indirect=True)
async def test_retired_audit_projection_and_five_effective_paths(r1_client, world):
    await old_override(world, retired=True)
    merchant = await r1_client.get('/api/v1/pricing/prices', params={'retailer_id': world['rid']},
                                   headers=headers(world))
    row = merchant.json()['data']['items'][0]
    assert row['price'] == '100' and row['unorderable_reason'] is None, 'R2_AC02_AUDIT_NOT_EFFECTIVE'
    assert row['override_price'] == '90.01'
    assert row['audit_price_issues']['override_price'] == 'MONEY_PRECISION'
    for path in ('/api/v1/client/products', '/api/v1/client/products/' + world['product']):
        result = await r1_client.get(path, headers=headers(world, client=True))
        assert result.status_code == 200
        data = result.json()['data']
        unit = (data['items'][0] if 'items' in data else data)['units'][0]
        assert unit['can_order'] and Decimal(unit['price']) == 100
    for client in (False, True):
        assert Decimal((await preview(r1_client, world, client=client))['total']) == 200
    async with world['session']() as db:
        await db.execute(text('UPDATE retailer_prices SET is_deleted=false'))
        await db.commit()
    rejected = await r1_client.post('/api/v1/orders/quote', headers=headers(world),
        json={'retailer_id': world['rid'], 'items': [{'sellable_unit_id': world['sku'], 'quantity': 1}]})
    assert rejected.status_code == 422, 'R2_AC02_ACTIVE_INCOMPATIBLE_STILL_REFUSED'


def test_quote_budget_refuses_before_successful_issue():
    from fastapi import HTTPException
    from services.pricing_quote_service import sign_quote
    with pytest.raises(HTTPException) as caught:
        sign_quote({'name': '\u4e2d' * 255 * 100})
    assert caught.value.status_code == 422 and caught.value.detail['code'] == 'QUOTE_BUDGET_EXCEEDED', 'R2_AC03_ISSUE_BUDGET'


@pytest.mark.asyncio
async def test_normal_token_accepted_by_both_submission_schemas(r1_client, world):
    from schemas.order import WholesalerOrderCreateRequest
    from schemas.client import ClientCreateOrderRequest
    from services.pricing_quote_service import read_quote
    quote = await preview(r1_client, world)
    body = {'items': [{'sellable_unit_id': world['sku'], 'sku_code': 'BOX', 'quantity': 2}],
            'quote_token': quote['quote_token']}
    WholesalerOrderCreateRequest.model_validate({**body, 'retailer_id': world['rid']})
    ClientCreateOrderRequest.model_validate(body)
    assert read_quote(quote['quote_token'])['total'] == '180.00'


@pytest.mark.asyncio
async def test_max_lines_nonascii_http_preview_has_no_unusable_success(r1_client, world):
    items = []
    async with world['session']() as db:
        await db.execute(text('UPDATE catalog_products SET name=:n'), {'n': '\u4e2d' * 255})
        for n in range(100):
            sid = (await db.execute(text('INSERT INTO skus '
                '(sku_code,name,unit,package_quantity,catalog_product_id,base_price) '
                'VALUES (:code,:name,\'Box\',12,:pid,90) RETURNING id'),
                {'code': 'LONG' + str(n), 'name': '\u4e2d' * 255, 'pid': uuid.UUID(world['product'])})).scalar_one()
            items.append({'sellable_unit_id': str(sid), 'quantity': 1})
        await db.commit()
    result = await r1_client.post('/api/v1/orders/quote', headers=headers(world),
        json={'retailer_id': world['rid'], 'items': items})
    assert result.status_code == 422 and result.json()['code'] == 'QUOTE_BUDGET_EXCEEDED', 'R2_AC03_LONG_HTTP_PREVIEW'
    assert (await facts(world))['orders'] == 0


def readiness(world):
    from scripts.runtime_readiness_gate import evaluate_contract
    return evaluate_contract(os.environ['TEST_DATABASE_URL'], world['schema'], BACKEND)


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['constraint', 'index'])
async def test_wrong_table_catalog_objects_rejected(r1_client, world, kind):
    from scripts.bootstrap_tenant_schema import _reconcile_s1_pricing
    assert await asyncio.to_thread(readiness, world) == []
    async with world['session']() as db:
        if kind == 'constraint':
            await db.execute(text('ALTER TABLE skus DROP CONSTRAINT ck_skus_base_price_positive'))
            await db.execute(text('CREATE TABLE wrong_price (base_price numeric(12,2), '
                'CONSTRAINT ck_skus_base_price_positive CHECK (base_price IS NULL OR base_price > 0))'))
        else:
            await db.execute(text('DROP INDEX ux_orders_replacement'))
            await db.execute(text('CREATE TABLE wrong_order (replaces_order_id uuid)'))
            await db.execute(text('CREATE UNIQUE INDEX ux_orders_replacement ON wrong_order '
                                  '(replaces_order_id) WHERE replaces_order_id IS NOT NULL'))
        await db.commit()
        with pytest.raises(RuntimeError, match='S1_SCHEMA_'):
            await _reconcile_s1_pricing(db, world['schema'])
    reasons = await asyncio.to_thread(readiness, world)
    assert any('S1_SCHEMA_' in r for r in reasons), 'R2_C05_WRONG_OWNER_READINESS'


@pytest.mark.asyncio
async def test_multiple_heads_both_checkers_refuse_without_pk_change(world):
    from scripts.bootstrap_tenant_schema import _require_alembic_revision
    # Only the task migration authority can write its version table.
    engine = _engine(os.environ['TEST_MIGRATION_DATABASE_URL'])
    try:
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO public.alembic_version VALUES ('039_order_credit_holds')"))
        async with world['session']() as db:
            with pytest.raises(RuntimeError, match='bootstrap-first'):
                await _require_alembic_revision(db, '040_s1_pricing_quote_contract')
        reasons = await asyncio.to_thread(readiness, world)
        assert reasons and '039_order_credit_holds' in reasons[0], 'R2_C06_EXACT_VERSION_SET'
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM public.alembic_version WHERE version_num='039_order_credit_holds'"))
        engine.dispose()


def test_revision_contract_finite_consistency():
    source = (BACKEND / 'scripts/bootstrap_tenant_schema.py').read_text()
    from scripts.runtime_readiness_gate import REQUIRED_REVISION
    module = ast.parse((BACKEND / 'alembic/versions/041_catalog_product_main_image.py').read_text())
    revisions = [n.value.value for n in module.body if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == 'revision' for t in n.targets)]
    parsed = ast.parse(source)
    assert revisions == [REQUIRED_REVISION] and any(isinstance(n, ast.Constant)
        and n.value == REQUIRED_REVISION for n in ast.walk(parsed))


@pytest.mark.parametrize('state', ['active', 'provisioning', 'invalid', 'bootstrap_only'])
def test_registry_lifecycle_039_to_040_diagnostic(state):
    with temporary_database_url(os.environ['TEST_DATABASE_URL'], 'r2lifecycle') as url:
        engine = _engine(url)
        try:
            upgrade(url, '039_order_credit_holds')
            _grant_product_minimum(engine)
            schema, _, _ = register(engine)
            _run_in_fresh_loop(asyncio.run, predecessor_bootstrap()(schema, url.app_url))
            with engine.begin() as db:
                if state == 'provisioning':
                    db.execute(text("UPDATE public.tenant_registrations SET status='provisioning', "
                        "provisioning_completed_at=NULL,password_hash_cleared_at=NULL"))
                    db.execute(text("UPDATE public.wholesalers SET status='provisioning'"))
                elif state == 'invalid':
                    db.execute(text("UPDATE public.tenant_registrations SET tenant_schema='t_wrong'"))
                elif state == 'bootstrap_only':
                    db.execute(text('DELETE FROM public.tenant_registrations'))
            before = catalog(engine, schema)
            if state == 'invalid':
                with pytest.raises(RuntimeError, match='S1_TENANT_REGISTRY_MISMATCH'):
                    upgrade(url, '040_s1_pricing_quote_contract')
                assert catalog(engine, schema) == before, 'R2_C04_INVALID_ZERO_DDL'
            else:
                upgrade(url, '040_s1_pricing_quote_contract')
                if state == 'bootstrap_only':
                    # This legacy empty schema is not a registered pricing tenant.
                    assert catalog(engine, schema) == before
                    with engine.begin() as db:
                        db.execute(text('SET LOCAL ROLE mpango_app'))
                        pid = db.execute(text(f'INSERT INTO "{schema}".catalog_products(name) '
                            "VALUES ('Legacy') RETURNING id")).scalar_one()
                        db.execute(text(f'INSERT INTO "{schema}".skus(sku_code,name,unit,package_quantity,catalog_product_id) '
                                        "VALUES ('LEGACY','Legacy','Box',1,:pid)"), {'pid': pid})
                    from scripts.bootstrap_tenant_schema import bootstrap
                    with pytest.raises(RuntimeError, match='S1_POPULATED_SCHEMA_REQUIRES_MIGRATION'):
                        _run_in_fresh_loop(asyncio.run, bootstrap(schema, url.app_url))
                    assert catalog(engine, schema) == before, 'R2_C04_UNSUPPORTED_ZERO_PARTIAL_DDL'
                    with engine.connect() as db:
                        assert db.execute(text("SELECT count(*) FROM pg_stat_activity WHERE "
                            "datname=current_database() AND usename='mpango_app'")).scalar_one() == 0, \
                            'R2_C04_REJECTED_BOOTSTRAP_RELEASES_CONNECTIONS'
                    print('R2_C04_UNSUPPORTED_LEGACY_BLOCKED_WITHOUT_INFERENCE')
                else:
                    from scripts.bootstrap_tenant_schema import bootstrap
                    _run_in_fresh_loop(asyncio.run, bootstrap(schema, url.app_url))
                    assert catalog(engine, schema) != before
                    if state == 'provisioning':
                        async def complete():
                            from db.tenant_filter import mark_session_as_system
                            from services.tenant_provisioning_service import TenantProvisioningService
                            e = create_async_engine(url.app_url.replace('postgresql://', 'postgresql+asyncpg://'), poolclass=NullPool)
                            try:
                                async with async_sessionmaker(e, expire_on_commit=False)() as db:
                                    mark_session_as_system(db, reason='R2 lifecycle diagnostic')
                                    reg = (await db.execute(text('SELECT id FROM public.tenant_registrations'))).scalar_one()
                                    service = TenantProvisioningService(db, database_url=url.app_url)
                                    outcome = await service.provision_wholesaler_and_schema(reg)
                                    assert outcome.action == 'reconciled', 'R2_C04_REAL_PROVISIONER_CONTINUATION'
                                    await db.commit()
                            finally:
                                await e.dispose()
                        _run_in_fresh_loop(asyncio.run, complete())
                        with engine.connect() as db:
                            assert db.execute(text('SELECT status,provisioning_completed_at IS NOT NULL '
                                'FROM public.tenant_registrations')).one() == ('active', True)
                    print('R2_C04_SUPPORTED_UPGRADE_AND_BOOTSTRAP', state)
        finally:
            engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['local', 'sku_shared', 'catalog_shared'])
async def test_create_and_sibling_update_real_lock_order(r1_client, world, mode):
    shared = mode != 'local'
    high = uuid.UUID('ffffffff-ffff-ffff-ffff-fffffffffff0')
    low = uuid.UUID(world['sku'])
    async with world['session']() as db:
        await db.execute(text('INSERT INTO skus '
            '(id,sku_code,name,unit,package_quantity,catalog_product_id,base_price) '
            "VALUES (:id,'SECOND','S1 boxes','Box',12,:pid,90)"),
            {'id': high, 'pid': uuid.UUID(world['product'])})
        await db.execute(text('INSERT INTO inventory_stocks(sku_id,quantity_on_hand) VALUES (:id,100)'), {'id': high})
        await db.commit()
    items = [{'sellable_unit_id': str(high), 'quantity': 1},
             {'sellable_unit_id': str(low), 'quantity': 1}]
    response = await r1_client.post('/api/v1/orders/quote', headers=headers(world),
        json={'retailer_id': world['rid'], 'items': items})
    assert response.status_code == 200
    token = response.json()['data']['quote_token']
    first, second, start = threading.Event(), threading.Event(), threading.Barrier(2)
    sql_trace, results = [], []

    def worker(role):
        async def job():
            pid = None
            from services.order_creation_service import submit_draft
            from services.sku_service import SKUService
            engine = create_async_engine(os.environ['TEST_DATABASE_URL'].replace(
                'postgresql://', 'postgresql+asyncpg://'), poolclass=NullPool)
            factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

            @event.listens_for(engine.sync_engine, 'before_cursor_execute')
            def attempt(conn, cursor, statement, parameters, context, many):
                if statement.startswith('UPDATE skus'):
                    sql_trace.append((role, 'flush_attempt', tuple(map(str, parameters))))
                if role == 'update' and shared and 'FOR UPDATE' in statement and 'FROM skus' in statement \
                        and str(low) in tuple(map(str, parameters)):
                    second.set()
                    sql_trace.append((role, 'attempt', tuple(map(str, parameters))))

            @event.listens_for(engine.sync_engine, 'after_cursor_execute')
            def observe(conn, cursor, statement, parameters, context, many):
                if 'FOR UPDATE' in statement and 'FROM skus' in statement:
                    sql_trace.append((role, 'lock', tuple(map(str, parameters))))
                    if role == 'create' and str(low) in tuple(map(str, parameters)):
                        first.set()
                        assert second.wait(10), 'R2_AC04_UPDATE_LOCK_BARRIER'
                    elif role == 'update' and str(high) in tuple(map(str, parameters)):
                        second.set()
                        assert first.wait(10), 'R2_AC04_CREATE_LOCK_BARRIER'
                elif statement.startswith('UPDATE skus'):
                    sql_trace.append((role, 'flush', tuple(map(str, parameters))))

            try:
                async with factory() as db:
                    db.info.update(tenant_schema=world['schema'], tenant_id=world['wid'])
                    @event.listens_for(db.sync_session, 'after_begin')
                    def path(session, transaction, conn):
                        conn.execute(text(f'SET LOCAL search_path TO "{world["schema"]}", public'))
                    pid = (await db.execute(text('SELECT pg_backend_pid()'))).scalar_one()
                    await asyncio.to_thread(start.wait, 10)
                    if role == 'create':
                        await submit_draft(db, wholesaler_id=world['wid'], retailer_id=world['rid'],
                            actor_id=world['actor'], operation='merchant-create', items=items,
                            notes='R2 race', quote_token=token, idempotency_key='r2-' + uuid.uuid4().hex)
                    else:
                        if shared:
                            assert await asyncio.to_thread(first.wait, 10), 'R2_AC04_CREATE_FIRST_LOCK'
                        if mode == 'catalog_shared':
                            from services.catalog_product_service import CatalogProductService
                            from schemas.catalog import CatalogProductUpdate
                            await CatalogProductService().update_product(db, product_id=world['product'],
                                request=CatalogProductUpdate(name='Shared updated'), actor_id=world['actor'])
                        else:
                            await SKUService().update_sku(db, sku_code='SECOND',
                                name='Shared updated' if shared else None, description=None, unit=None,
                                package_quantity=None, category=None, is_active=None,
                                updated_by=world['actor'], display_label=None if shared else 'Pack')
                    await db.commit()
                    results.append((role, pid, 'committed'))
            except Exception as exc:
                sqlstate = getattr(getattr(exc, 'orig', None), 'sqlstate', None)
                results.append((role, pid, sqlstate or type(exc).__name__))
            finally:
                await engine.dispose()
        asyncio.run(job())

    before = await facts(world)
    with ThreadPoolExecutor(max_workers=2) as pool:
        await asyncio.gather(asyncio.to_thread(pool.submit(worker, 'create').result, 30),
                             asyncio.to_thread(pool.submit(worker, 'update').result, 30))
    print('R2_AC04_TRACE', sql_trace, 'OUTCOMES', results)
    after = await facts(world)
    print('R2_AC04_POSTSTATE', before, after)
    async with world['session']() as db:
        rows = (await db.execute(text('SELECT id,name,display_label,updated_by FROM skus ORDER BY id'))).all()
        snapshots = (await db.execute(text('SELECT sellable_unit_id,product_name,unit_snapshot, '
            'package_quantity_snapshot,unit_price,quantity,subtotal FROM order_items ORDER BY sellable_unit_id'))).all()
    print('R2_AC04_SKU_POSTSTATE', [tuple(map(str, r)) for r in rows])
    print('R2_AC04_COMMITTED_SNAPSHOTS', [tuple(map(str, r)) for r in snapshots])
    assert len(results) == 2 and all(r[2] == 'committed' for r in results), 'R2_AC04_NO_DEADLOCK_OR_TIMEOUT'
    assert after['orders'] == 1 and after['items'] == 2
    for name in ('payments', 'ledger', 'reservations', 'holds', 'stock'):
        assert after[name] == before[name], 'R2_AC04_ZERO_ECONOMIC_EFFECTS'
    assert all(r.unit_snapshot == 'Box' and r.package_quantity_snapshot == 12
               and r.unit_price == 90 and r.quantity == 1 and r.subtotal == 90 for r in snapshots)
    if shared:
        assert all(r.name == 'Shared updated' for r in rows)
        locks = [entry[2][0] for entry in sql_trace if entry[:2] == ('update', 'lock')]
        assert locks == [str(low), str(high)], 'R2_AC04_SHARED_GLOBAL_LOCK_ORDER'
    else:
        assert rows[0].updated_by is None, 'R2_AC04_LOCAL_UPDATE_NO_SIBLING_AUDIT_WRITE'
        assert rows[1].display_label == 'Pack'


@pytest.mark.asyncio
async def test_shared_metadata_with_local_unit_fields_preserved(r1_client, world):
    async with world['session']() as db:
        await db.execute(text('UPDATE inventory_stocks SET quantity_on_hand=0'))
        await db.commit()
    body = {'name': 'Renamed', 'unit': 'Crate', 'display_label': 'Twelve', 'package_quantity': '15'}
    blocked = await r1_client.put('/api/v1/skus/BOX', headers=headers(world), json=body)
    assert blocked.status_code == 409 and blocked.json()['code'] == 'SKU_PACKAGE_QUANTITY_REPRICE_REQUIRED'
    async with world['session']() as db:
        assert (await db.execute(text('SELECT name,unit,package_quantity FROM skus'))).one() == ('S1 boxes', 'Box', Decimal('12'))
        await db.execute(text('UPDATE skus SET base_price=NULL'))
        await db.commit()
    result = await r1_client.put('/api/v1/skus/BOX', headers=headers(world), json=body)
    assert result.status_code == 200, 'R2_AC04_COMBINED_SHARED_LOCAL_UPDATE'
    async with world['session']() as db:
        row = (await db.execute(text('SELECT name,unit,display_label,package_quantity FROM skus'))).one()
        assert row == ('Renamed', 'Crate', 'Twelve', Decimal('15'))
