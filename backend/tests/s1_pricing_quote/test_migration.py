"""Real 039 -> 040, rollback and bootstrap parity on task-only databases."""
import asyncio
import importlib.util
import os
from pathlib import Path
import subprocess
import types
import uuid

import pytest
from sqlalchemy import event, text

from tests.async_test_utils import temporary_database_url
from tests.order_state_r2.test_migration_c3 import (
    _engine, _grant_product_minimum, _run_in_fresh_loop,
)

BASE = os.environ['S1_FROZEN_BASE']
BACKEND = Path(__file__).resolve().parents[2]


def upgrade(url, revision):
    def job():
        from alembic import command
        from alembic.config import Config
        before = os.environ.get('DATABASE_URL')
        try:
            os.environ['DATABASE_URL'] = str(url)
            cfg = Config(str(BACKEND / 'alembic.ini'))
            cfg.set_main_option('script_location', str(BACKEND / 'alembic'))
            command.upgrade(cfg, revision)
        finally:
            if before is None:
                os.environ.pop('DATABASE_URL', None)
            else:
                os.environ['DATABASE_URL'] = before
    _run_in_fresh_loop(job)


def predecessor_bootstrap():
    raw = subprocess.check_output(['git', 'show', BASE + ':backend/scripts/bootstrap_tenant_schema.py'], cwd=BACKEND)
    module = types.ModuleType('s1_original_039_bootstrap')
    module.__file__ = str(BACKEND / 'scripts/bootstrap_tenant_schema.py')
    exec(compile(raw, module.__file__, 'exec'), module.__dict__)
    return module.bootstrap


def register(engine):
    wid, rid, reg = (uuid.uuid4() for _ in range(3))
    schema = 't_' + wid.hex
    with engine.begin() as db:
        db.execute(text("INSERT INTO public.wholesalers(id,code,name,status) VALUES(:id,:code,'S1 migration','active')"),
                   {'id': wid, 'code': 'S1M' + wid.hex[:16]})
        db.execute(text("INSERT INTO public.retailers(id,phone,name) VALUES(:id,:phone,'S1 migration')"),
                   {'id': rid, 'phone': '+256' + str(rid.int)[:12]})
        db.execute(text("INSERT INTO public.tenant_registrations "
                   "(id,company_name,country,owner_email,status,wholesaler_id,tenant_schema,expires_at,provisioning_completed_at,password_hash_cleared_at) "
                   "VALUES(:id,'S1 migration','KE',:email,'active',:wid,:schema,now()+interval '1 day',now(),now())"),
                   {'id': reg, 'email': reg.hex + '@example.invalid', 'wid': wid, 'schema': schema})
        db.execute(text("INSERT INTO public.wholesaler_retailer_bindings "
                   "(wholesaler_id,retailer_id,status,outstanding_balance) VALUES(:wid,:rid,'active',0)"),
                   {'wid': wid, 'rid': rid})
    return schema, wid, rid


def catalog(engine, schema):
    with engine.begin() as db:
        db.execute(text('SET LOCAL ROLE mpango_app'))
        cols = db.execute(text("SELECT table_name,column_name,data_type,udt_name,is_nullable,column_default, "
                              "numeric_precision,numeric_scale,character_maximum_length "
                              "FROM information_schema.columns WHERE table_schema=:s "
                              "AND table_name IN ('skus','orders','order_items') ORDER BY table_name,ordinal_position"), {'s': schema}).all()
        cons = db.execute(text("SELECT c.relname,k.conname,pg_get_constraintdef(k.oid) "
                              "FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid "
                              "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=:s "
                              "AND c.relname IN ('skus','orders','order_items') ORDER BY c.relname,k.conname"), {'s': schema}).all()
        indexes = db.execute(text("SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname=:s "
                                 "AND indexname IN ('ux_orders_creation_intent','ux_orders_replacement') ORDER BY indexname"), {'s': schema}).all()
    normalize = lambda rows: [[str(v).replace(schema, 'SCHEMA') for v in row] for row in rows]
    return normalize(cols), normalize(cons), normalize(indexes)


def facts(engine, schema):
    with engine.begin() as db:
        db.execute(text('SET LOCAL ROLE mpango_app'))
        result = {}
        for table in ('skus', 'orders', 'order_items', 'retailer_prices', 'inventory_stocks',
                      'order_credit_holds', 'inventory_movements', 'inventory_reservations', 'ledger_entries'):
            rows = db.execute(text(f'SELECT to_jsonb(t) FROM "{schema}".{table} t ORDER BY id')).scalars().all()
            for row in rows:
                for key in ('base_price','pricing_revision','display_label','country_snapshot','currency_snapshot',
                            'registration_snapshot_id','creation_operation','creation_key_digest','creation_fingerprint',
                            'quote_seen','quote_resolved','replaces_order_id','package_quantity_snapshot','display_label_snapshot'):
                    row.pop(key, None)
            result[table] = rows
        result['guard'] = db.execute(text("SELECT md5(prosrc),pg_get_userbyid(proowner) FROM pg_proc "
                                         "WHERE oid='public.prevent_ledger_modification()'::regprocedure")).one()
        result['memberships'] = db.execute(text("SELECT roleid,member,admin_option,inherit_option,set_option "
                                               "FROM pg_auth_members ORDER BY roleid,member")).all()
    return result


def seed(engine, schema, wid, rid):
    with engine.begin() as db:
        db.execute(text('SET ROLE mpango_app'))
        q = '"' + schema + '"'
        product = db.execute(text(f"INSERT INTO {q}.catalog_products(name) VALUES('Old boxes') RETURNING id")).scalar_one()
        sku = db.execute(text(f"INSERT INTO {q}.skus(sku_code,name,unit,package_quantity,catalog_product_id) "
                              "VALUES('OLD','Old boxes','Box',12,:pid) RETURNING id"), {'pid': product}).scalar_one()
        db.execute(text(f"INSERT INTO {q}.retailer_prices(sku_id,retailer_id,price) VALUES(:sid,:rid,21)"), {'sid': sku, 'rid': rid})
        db.execute(text(f"INSERT INTO {q}.inventory_stocks(sku_id,quantity_on_hand,quantity_reserved) VALUES(:sid,17,2)"), {'sid': sku})
        oid = db.execute(text(f"INSERT INTO {q}.orders(wholesaler_id,retailer_id,status,total_amount) "
                              "VALUES(:wid,:rid,'confirmed',60) RETURNING id"), {'wid': wid, 'rid': rid}).scalar_one()
        db.execute(text(f"INSERT INTO {q}.order_items(order_id,sellable_unit_id,identity_status,unit_snapshot, "
                        "sku_code,product_name,quantity,unit_price,subtotal) VALUES(:oid,:sid,'stable','Box','OLD','Old boxes',2,30,60)"),
                   {'oid': oid, 'sid': sku})
        db.execute(text(f"INSERT INTO {q}.order_credit_holds(order_id,amount,remaining_amount,status) "
                        "VALUES(:oid,60,60,'active')"), {'oid': oid})
        db.execute(text("UPDATE public.wholesaler_retailer_bindings SET outstanding_balance=60 "
                        "WHERE wholesaler_id=:wid AND retailer_id=:rid"), {'wid': wid, 'rid': rid})
        db.execute(text('RESET ROLE'))


def test_nonempty_upgrade_conserves_history_and_matches_fresh_bootstrap():
    assert os.environ.get('MPANGO_ALLOW_TEMP_DB_CREATE') == '1', 'S1_MIGRATION_EXPLICIT_TASK_OPT_IN'
    with temporary_database_url(os.environ['TEST_DATABASE_URL'], 's1migration') as url:
        engine = _engine(url)
        try:
            upgrade(url, '039_order_credit_holds')
            _grant_product_minimum(engine)
            schema, wid, rid = register(engine)
            _run_in_fresh_loop(asyncio.run, predecessor_bootstrap()(schema, url.app_url))
            seed(engine, schema, wid, rid)
            before = facts(engine, schema)
            upgrade(url, '040_s1_pricing_quote_contract')
            assert facts(engine, schema) == before, 'S1_MIGRATION_HISTORY_CONSERVATION'
            with engine.begin() as db:
                db.execute(text('SET LOCAL ROLE mpango_app'))
                assert db.execute(text(f'SELECT base_price,currency_snapshot FROM "{schema}".skus '
                    f'CROSS JOIN "{schema}".orders')).one() == (None, None), 'S1_NO_HISTORICAL_PRICE_OR_CURRENCY_INFERENCE'
            fresh, _, _ = register(engine)
            from scripts.bootstrap_tenant_schema import bootstrap
            _run_in_fresh_loop(asyncio.run, bootstrap(fresh, url.app_url))
            assert catalog(engine, schema) == catalog(engine, fresh), 'S1_FULL_CATALOG_PARITY'
        finally:
            engine.dispose()


def test_mid_upgrade_rolls_back_all_tenants_and_identity():
    assert os.environ.get('MPANGO_ALLOW_TEMP_DB_CREATE') == '1'
    with temporary_database_url(os.environ['TEST_DATABASE_URL'], 's1rollback') as url:
        engine = _engine(url)
        try:
            upgrade(url, '039_order_credit_holds')
            _grant_product_minimum(engine)
            schemas = [register(engine)[0] for _ in range(2)]
            for schema in schemas:
                _run_in_fresh_loop(asyncio.run, predecessor_bootstrap()(schema, url.app_url))
            spec = importlib.util.spec_from_file_location('s1_040_fault', BACKEND / 'alembic/versions/040_s1_pricing_quote_contract.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            before = {s: catalog(engine, s) for s in schemas}
            seen = []
            def fault(_conn, _cursor, statement, _parameters, _context, _executemany):
                if 'ADD COLUMN base_price' in statement:
                    seen.append(statement)
                    if len(seen) == 2:
                        raise RuntimeError('S1_INJECTED_SECOND_TENANT_DDL_FAILURE')
            from alembic.migration import MigrationContext
            from alembic.operations import Operations
            event.listen(engine, 'before_cursor_execute', fault)
            try:
                with pytest.raises(RuntimeError, match='S1_INJECTED_SECOND_TENANT_DDL_FAILURE'):
                    with engine.begin() as db:
                        module.op = Operations(MigrationContext.configure(db))
                        module.upgrade()
            finally:
                event.remove(engine, 'before_cursor_execute', fault)
            assert len(seen) == 2
            assert {s: catalog(engine, s) for s in schemas} == before, 'S1_ZERO_PARTIAL_UPGRADE'
            with engine.connect() as db:
                assert db.execute(text('SELECT current_user=session_user')).scalar_one()
                assert db.execute(text('SELECT version_num FROM public.alembic_version')).scalar_one() == '039_order_credit_holds'
        finally:
            engine.dispose()
