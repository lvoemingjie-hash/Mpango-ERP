"""Source independence plus actual new-tenant catalog and authority checks."""
import ast
import asyncio
import os
from pathlib import Path

import pytest
from sqlalchemy import text


def media_catalog(engine, schema):
    """Full, normalized media contract, not a column-count comparison."""
    with engine.begin() as db:
        queries = {
            'columns': "SELECT a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull,"
                "pg_get_expr(d.adbin,d.adrelid),a.attacl::text FROM pg_attribute a "
                "LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum "
                "WHERE a.attrelid=:oid AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum",
            'constraints': "SELECT conname,contype,pg_get_constraintdef(oid,true) FROM pg_constraint "
                "WHERE conrelid=:oid ORDER BY conname",
            'indexes': "SELECT ic.relname,pg_get_indexdef(i.indexrelid),i.indisvalid,i.indisready,"
                "pg_get_userbyid(ic.relowner),ic.relacl::text FROM pg_index i JOIN pg_class ic "
                "ON ic.oid=i.indexrelid WHERE i.indrelid=:oid ORDER BY ic.relname",
        }
        table = db.execute(text("SELECT c.oid,c.relkind,pg_get_userbyid(c.relowner),c.relacl::text "
            "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=:s "
            "AND c.relname='catalog_product_images'"), {'s': schema}).one()
        result = {'table': tuple(table[1:])}
        for name, query in queries.items():
            result[name] = [tuple(str(v).replace(schema, 'SCHEMA') if v is not None else None for v in row)
                            for row in db.execute(text(query), {'oid': table.oid})]
        result['schema_acl'] = db.execute(text("SELECT pg_get_userbyid(nspowner),nspacl::text "
            "FROM pg_namespace WHERE nspname=:s"), {'s': schema}).one()
        return result


def raw_history(engine, schema, wid):
    result = {}
    with engine.begin() as db:
        db.execute(text('SET LOCAL ROLE mpango_app'))
        for table in ('catalog_products', 'skus', 'retailer_prices', 'orders', 'order_items',
                      'payments', 'inventory_stocks', 'inventory_reservations', 'inventory_movements',
                      'order_credit_holds', 'ledger_entries'):
            result[table] = db.execute(text(f'SELECT to_jsonb(t) FROM "{schema}".{table} t '
                'ORDER BY to_jsonb(t)::text')).scalars().all()
        result['binding'] = db.execute(text('SELECT to_jsonb(b) FROM public.wholesaler_retailer_bindings b '
            'WHERE wholesaler_id=:wid ORDER BY retailer_id'), {'wid': wid}).scalars().all()
        result['old_objects'] = db.execute(text("SELECT c.oid,c.relname,c.relkind,pg_get_userbyid(c.relowner),"
            "c.relacl::text FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname=:s AND c.relname NOT LIKE 'catalog_product_images%' ORDER BY c.oid"), {'s': schema}).all()
    return result


def authority(engine):
    with engine.connect() as db:
        return (db.execute(text('SELECT current_user,session_user')).one(),
            db.execute(text("SELECT rolname,rolsuper,rolcreatedb,rolcreaterole,rolinherit,rolbypassrls "
                            "FROM pg_roles ORDER BY rolname")).all(),
            db.execute(text('SELECT roleid,member,grantor,admin_option,inherit_option,set_option '
                            'FROM pg_auth_members ORDER BY roleid,member,grantor')).all())


def test_two_populated_040_tenants_upgrade_without_migrator_usage_and_full_parity():
    from tests.async_test_utils import temporary_database_url
    from tests.order_state_r2.test_migration_c3 import _engine, _grant_product_minimum, _run_in_fresh_loop
    from tests.s1_pricing_quote.test_migration import upgrade, register, predecessor_bootstrap, seed
    assert os.environ['S1_FROZEN_BASE'] == 'fd37acbbd3af8c9d0ed64ecb4ad0849d4ab8c366'  # pragma: allowlist secret
    with temporary_database_url(os.environ['TEST_DATABASE_URL'], 'image041') as url:
        engine = _engine(url)
        try:
            upgrade(url, '040_s1_pricing_quote_contract')
            _grant_product_minimum(engine)
            tenants = [register(engine) for _ in range(2)]
            for schema, wid, rid in tenants:
                _run_in_fresh_loop(asyncio.run, predecessor_bootstrap()(schema, url.app_url))
                seed(engine, schema, wid, rid)
                with engine.connect() as db:
                    assert db.execute(text('SELECT has_schema_privilege(current_user,:s,\'USAGE\')'),
                                      {'s': schema}).scalar_one() is False, 'IMAGE_SET_ONLY_NO_USAGE'
            before = {s: raw_history(engine, s, w) for s, w, _ in tenants}
            for value in before.values():
                assert all(value[t] for t in ('orders', 'order_items', 'order_credit_holds',
                                             'inventory_stocks', 'retailer_prices')), 'IMAGE_NONEMPTY_UPGRADE_PRESTATE'
            roles = authority(engine)
            upgrade(url, '041_catalog_product_main_image')
            assert authority(engine) == roles, 'IMAGE_UPGRADE_AUTHORITY_UNCHANGED'
            assert {s: raw_history(engine, s, w) for s, w, _ in tenants} == before, 'IMAGE_RAW_HISTORY_UNCHANGED'
            fresh, _, _ = register(engine)
            from scripts.bootstrap_tenant_schema import bootstrap
            _run_in_fresh_loop(asyncio.run, bootstrap(fresh, url.app_url))
            expected = media_catalog(engine, fresh)
            for schema, _, _ in tenants:
                assert media_catalog(engine, schema) == expected, 'IMAGE_FULL_CATALOG_PARITY'
            with engine.connect() as db:
                assert db.execute(text('SELECT version_num FROM public.alembic_version')).scalar_one() == '041_catalog_product_main_image'
        finally:
            engine.dispose()


@pytest.mark.parametrize('defect', ['missing', 'view', 'late-ddl'])
def test_041_rejects_bad_prestate_or_mid_upgrade_without_partial_tenant_ddl(defect):
    import importlib.util
    from sqlalchemy import event
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from tests.async_test_utils import temporary_database_url
    from tests.order_state_r2.test_migration_c3 import _engine, _grant_product_minimum, _run_in_fresh_loop
    from tests.s1_pricing_quote.test_migration import upgrade, register, predecessor_bootstrap
    with temporary_database_url(os.environ['TEST_DATABASE_URL'], 'imagebad041') as url:
        engine = _engine(url)
        try:
            upgrade(url, '040_s1_pricing_quote_contract')
            _grant_product_minimum(engine)
            schemas = sorted(register(engine)[0] for _ in range(2))
            for schema in schemas:
                _run_in_fresh_loop(asyncio.run, predecessor_bootstrap()(schema, url.app_url))
            if defect != 'late-ddl':
                with engine.begin() as db:
                    db.execute(text('SET LOCAL ROLE mpango_app'))
                    db.execute(text(f'ALTER TABLE "{schemas[1]}".catalog_products RENAME TO preserved_catalog_products'))
                    if defect == 'view':
                        db.execute(text(f'CREATE VIEW "{schemas[1]}".catalog_products AS SELECT * '
                                        f'FROM "{schemas[1]}".preserved_catalog_products'))
            before = authority(engine)
            spec = importlib.util.spec_from_file_location('images041_failure',
                Path(__file__).resolve().parents[2] / 'alembic/versions/041_catalog_product_main_image.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            seen = []
            def fault(_conn, _cursor, statement, _parameters, _context, _executemany):
                if 'CREATE TABLE' in statement and '.catalog_product_images' in statement:
                    seen.append(statement)
                    if len(seen) == 2 and defect == 'late-ddl':
                        raise RuntimeError('IMAGE_SECOND_TENANT_DDL_FAULT')
            event.listen(engine, 'before_cursor_execute', fault)
            try:
                expected = {'missing': 'IMAGE_PREDECESSOR_MISSING', 'view': 'IMAGE_PREDECESSOR_MALFORMED',
                            'late-ddl': 'IMAGE_SECOND_TENANT_DDL_FAULT'}[defect]
                with pytest.raises(RuntimeError, match=expected):
                    with engine.begin() as db:
                        module.op = Operations(MigrationContext.configure(db))
                        module.upgrade()
            finally:
                event.remove(engine, 'before_cursor_execute', fault)
            assert authority(engine) == before, 'IMAGE_FAILED_UPGRADE_IDENTITY_RESTORED'
            with engine.connect() as db:
                assert db.execute(text("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname=ANY(:schemas) AND c.relname='catalog_product_images'"), {'schemas': schemas}).scalar_one() == 0, 'IMAGE_ZERO_PARTIAL_UPGRADE'
                assert db.execute(text('SELECT version_num FROM public.alembic_version')).scalar_one() == '040_s1_pricing_quote_contract'
            assert len(seen) == (2 if defect == 'late-ddl' else 0)
        finally:
            engine.dispose()


def test_migration_and_bootstrap_ddl_are_independent_and_equal():
    root = Path(__file__).resolve().parents[2]
    migration = ast.parse((root / 'alembic/versions/041_catalog_product_main_image.py').read_text())
    ddl = next(ast.literal_eval(n.value) for n in migration.body if isinstance(n, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == 'MEDIA_DDL' for t in n.targets))
    bootstrap = ast.parse((root / 'scripts/bootstrap_tenant_schema.py').read_text())
    function = next(n for n in bootstrap.body if isinstance(n, ast.AsyncFunctionDef) and n.name == '_reconcile_product_images')
    literals = [n for n in ast.walk(function) if isinstance(n, ast.JoinedStr)]
    matching = []
    for node in literals:
        value = ''.join(v.value if isinstance(v, ast.Constant) else '{q}' for v in node.values)
        if value.startswith('CREATE TABLE {q}.catalog_product_images'): matching.append(value)
    assert len(matching) == 1 and ''.join(matching[0].split()) == ''.join(ddl.split())
    assert not any(isinstance(n, ast.ImportFrom) and '041' in (n.module or '') for n in ast.walk(bootstrap))


@pytest.mark.asyncio
async def test_new_tenant_media_catalog_and_runtime_authority(world):
    async with world['session']() as db:
        columns = (await db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema=:s AND table_name='catalog_product_images'"), {'s': world['schema']})).scalars().all()
        assert set(columns) == {'product_id', 'image_revision', 'current_version', 'variants', 'created_by', 'updated_by', 'created_at', 'updated_at'}
        row = (await db.execute(text("SELECT rolsuper,rolcreatedb,rolcreaterole,rolbypassrls FROM pg_roles WHERE rolname=current_user"))).one()
        assert tuple(row) == (False, False, False, False), 'IMAGE_RUNTIME_NO_PRIVILEGE_EXPANSION'
        assert (await db.execute(text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')"))).scalar_one() is False
        assert (await db.execute(text('SELECT version_num FROM public.alembic_version'))).scalar_one() == '041_catalog_product_main_image'
        from scripts.bootstrap_tenant_schema import _reconcile_product_images
        await _reconcile_product_images(db, world['schema'])
