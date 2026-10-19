"""Native 041 registration, actual 042 migration and future-tenant parity.

Run against an explicitly prepared disposable 041 DB. No private task capsule
or administrator is imported. The predecessor bootstrap is exact Git data,
not a mocked active registration or a replacement provisioning decision.
"""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import types
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from tests.order_state_r2.test_migration_c3 import _upgrade_to_head
from tests.s1_pricing_quote.conftest import world as native_world
from tests.s3_negotiation.test_contract import original

# Public Git object identity, not a credential; keep its byte grouping explicit.
BASE = bytes.fromhex('6d003db6 202f3e00 ab465687 919fa7b0 e73bb5ee').hex()
BACKEND = Path(__file__).resolve().parents[2]


async def retained_rows(world):
    result = {}
    async with world['session']() as db:
        for table, key in (
            ('orders', 'id'), ('order_items', 'id'), ('catalog_products', 'id'), ('skus', 'id'),
            ('inventory_stocks', 'id'), ('inventory_movements', 'id'), ('inventory_reservations', 'id'),
            ('order_credit_holds', 'id'), ('payments', 'id'), ('ledger_entries', 'id'),
            ('retailer_prices', 'id'), ('catalog_product_images', 'product_id'),
        ):
            result[table] = (await db.execute(text(f'SELECT to_jsonb(t) FROM {table} t ORDER BY {key}'))).scalars().all()
        result['balance'] = (await db.execute(text(
            'SELECT outstanding_balance FROM public.wholesaler_retailer_bindings WHERE wholesaler_id=:wid AND retailer_id=:rid'),
            {'wid': UUID(world['wid']), 'rid': UUID(world['rid'])})).scalar_one()
    return result


async def catalog_rows(world):
    schema = world['schema']
    async with world['session']() as db:
        columns = (await db.execute(text(
            'SELECT a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull,pg_get_expr(d.adbin,d.adrelid) '
            'FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace '
            'LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum '
            "WHERE n.nspname=:s AND c.relname='order_negotiation_proposals' AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum"), {'s': schema})).all()
        constraints = (await db.execute(text(
            'SELECT k.conname,pg_get_constraintdef(k.oid) FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid '
            "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=:s AND c.relname='order_negotiation_proposals' ORDER BY k.conname"), {'s': schema})).all()
        indexes = (await db.execute(text("SELECT indexname,indexdef FROM pg_indexes WHERE schemaname=:s AND tablename='order_negotiation_proposals' ORDER BY indexname"), {'s': schema})).all()
        triggers = (await db.execute(text(
            'SELECT t.tgname,t.tgenabled::text,t.tgtype,p.proname,p.prosecdef,p.prosrc '
            'FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace '
            "JOIN pg_proc p ON p.oid=t.tgfoid WHERE n.nspname=:s AND c.relname='order_negotiation_proposals' AND NOT t.tgisinternal ORDER BY t.tgname"), {'s': schema})).all()
        identity = (await db.execute(text(
            'SELECT rolsuper,rolcreatedb,rolcreaterole,rolbypassrls FROM pg_roles WHERE rolname=current_user'))).one()
        assert tuple(identity) == (False, False, False, False), 'S3_MIGRATION_PARITY_MINIMUM_RUNTIME_ROLE'
    return [[[ ''.join(str(value).replace('"', '').replace(schema+'.', '').split()) for value in row]
             for row in group] for group in (columns, constraints, indexes, triggers)]


@pytest.mark.asyncio
async def test_existing_041_upgrade_preserves_rows_and_matches_new_tenant(request, monkeypatch, r1_client):
    assert os.environ.get('S3_UPGRADE_DATABASE_PREPARED') == '041', 'S3_EXPLICIT_041_TARGET_REQUIRED'
    assert os.environ.get('TEST_MIGRATION_DATABASE_URL'), 'S3_MIGRATION_IDENTITY_REQUIRED'
    from services import tenant_provisioning_service
    from scripts.bootstrap_tenant_schema import _reconcile_order_negotiations
    raw = subprocess.check_output(['git', 'show', BASE+':backend/scripts/bootstrap_tenant_schema.py'], cwd=BACKEND)
    predecessor = types.ModuleType('s3_exact_predecessor_bootstrap')
    predecessor.__file__ = str(BACKEND/'scripts/bootstrap_tenant_schema.py')
    exec(compile(raw, predecessor.__file__, 'exec'), predecessor.__dict__)
    generator = native_world.__wrapped__(request)
    with monkeypatch.context() as choice:
        choice.setattr(tenant_provisioning_service, '_load_bootstrap', lambda: predecessor.bootstrap)
        world = await anext(generator)
    fresh_generator = None
    try:
        async with world['session']() as db:
            assert (await db.execute(text('SELECT version_num FROM public.alembic_version'))).scalar_one() == '041_catalog_product_main_image'
        await original(r1_client, world)
        version = uuid4()
        async with world['session']() as db:
            await db.execute(text('INSERT INTO catalog_product_images(product_id,image_revision,current_version,variants) VALUES (:pid,1,:version,CAST(:variants AS jsonb))'),
                {'pid': UUID(world['product']), 'version': version, 'variants': json.dumps({'thumbnail': {'path': 'retained/thumbnail.webp'}})})
            await db.commit()
        before = await retained_rows(world)
        _upgrade_to_head(os.environ['TEST_MIGRATION_DATABASE_URL'], '042_order_negotiation_proposals')
        assert await retained_rows(world) == before, 'S3_041_042_HISTORY_MONEY_STOCK_MEDIA_CONSERVATION'
        async with world['session']() as db:
            assert (await db.execute(text('SELECT version_num FROM public.alembic_version'))).scalar_one() == '042_order_negotiation_proposals'
            assert (await db.execute(text('SELECT count(*) FROM order_negotiation_proposals'))).scalar_one() == 0
            await _reconcile_order_negotiations(db, world['schema'])
        fresh_generator = native_world.__wrapped__(request)
        fresh = await anext(fresh_generator)
        assert await catalog_rows(world) == await catalog_rows(fresh), 'S3_MIGRATION_NEW_TENANT_FULL_PROPOSAL_CATALOG_PARITY'
    finally:
        if fresh_generator is not None:
            await fresh_generator.aclose()
        await generator.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize('corruption', ['constraint', 'index', 'trigger', 'trigger_condition'])
async def test_bootstrap_rejects_changed_proposal_contract(world, corruption):
    from scripts.bootstrap_tenant_schema import _reconcile_order_negotiations
    q = '"'+world['schema']+'"'
    async with world['session']() as db:
        async with db.begin_nested():
            if corruption == 'constraint':
                await db.execute(text(f'ALTER TABLE {q}.order_negotiation_proposals DROP CONSTRAINT ck_negotiation_version'))
                await db.execute(text(f'ALTER TABLE {q}.order_negotiation_proposals ADD CONSTRAINT ck_negotiation_version CHECK (version >= 0)'))
            elif corruption == 'index':
                await db.execute(text(f'DROP INDEX {q}.ux_negotiation_pending_source'))
                await db.execute(text(f'CREATE INDEX ux_negotiation_pending_source ON {q}.order_negotiation_proposals (source_order_id)'))
            elif corruption == 'trigger':
                await db.execute(text(f'ALTER TABLE {q}.order_negotiation_proposals DISABLE TRIGGER negotiation_history_immutable'))
            else:
                await db.execute(text(f'DROP TRIGGER negotiation_history_immutable ON {q}.order_negotiation_proposals'))
                await db.execute(text(f'CREATE TRIGGER negotiation_history_immutable BEFORE UPDATE OR DELETE ON {q}.order_negotiation_proposals FOR EACH ROW WHEN (false) EXECUTE FUNCTION {q}.prevent_negotiation_rewrite()'))
            with pytest.raises(RuntimeError, match='NEGOTIATION_CATALOG_'):
                await _reconcile_order_negotiations(db, world['schema'])
        await db.rollback()
