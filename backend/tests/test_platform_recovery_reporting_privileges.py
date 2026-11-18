"""One private task-managed PG: exact ACL correction and BI positives.

This suite never selects credential values. LIMIT 0 checks statement admission;
the optional synthetic app rows are rolled back. No production credentials,
Operator login, mail, or recovery operation is performed.
"""
import asyncio
import json
import os
from pathlib import Path
from secrets import token_urlsafe
import sys
from urllib.parse import unquote, urlsplit
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio

from scripts.provision_runtime_db_roles import (
    Provisioner, PLATFORM_RECOVERY_REPORTING_SQL,
    platform_recovery_reporting_refusals,
)
from scripts.bootstrap_tenant_schema import bootstrap
from scripts.runtime_readiness_gate import evaluate_contract
from tests.task_owned_pg_resources import _native, task_postgres

pytestmark = pytest.mark.integration
TARGET = 'public.platform_operator_recovery_credentials'


def save(world, name, facts):
    with (world['facts_dir'] / name).open('x') as f:
        os.chmod(f.name, 0o600)
        json.dump(facts, f, indent=2, default=str)
        f.write('\n')


async def facts(world):
    c = await asyncpg.connect(world['migrate_url'])
    try:
        return dict(await c.fetchrow(PLATFORM_RECOVERY_REPORTING_SQL))
    finally:
        await c.close()


async def gate(world):
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv('REPORTING_DATABASE_URL', world['reporting_url'])
        return await asyncio.to_thread(evaluate_contract, world['app_url'], 't_test')


@pytest_asyncio.fixture(scope='module')
async def world():
    shared = urlsplit(os.environ['DATABASE_URL'])
    with task_postgres('reporting_acl', cluster_only=True) as cluster:
        # The existing helper validates empty cluster, full ID/labels/image,
        # volume and loopback mapping before yielding this endpoint.
        app = urlsplit(cluster['runtime_endpoint'])
        admin = urlsplit(cluster['admin_sync'])
        assert app.hostname == admin.hostname == '127.0.0.1'
        assert app.port == admin.port and app.port != (shared.port or 5432)
        assert cluster['container'] != os.environ.get('CI_PG_CONTAINER_ID')
        assert app.username == 'mpango_app' and app.password
        assert admin.username == 'postgres' and admin.path == '/postgres'
        database = app.path.removeprefix('/')
        assert database == 'test_c91_reporting_acl'
        migrate_password = token_urlsafe(32)
        reporting_password = token_urlsafe(32)
        migrate_url = app._replace(netloc=f'mpango_migrate:{migrate_password}@127.0.0.1:{app.port}').geturl()
        reporting_url = app._replace(netloc=f'reporting_user:{reporting_password}@127.0.0.1:{app.port}').geturl()
        provisioner = Provisioner(admin.geturl(), migrate_url, app.geturl(),
                                  'mpango_migrate', 'mpango_app', database)
        root = Path(cluster['private_root'])
        data = dict(admin_url=admin.geturl(), migrate_url=migrate_url, app_url=app.geturl(),
                    reporting_url=reporting_url, facts_dir=root, provisioner=provisioner)

        await provisioner.create_roles_and_database(
            app_password=unquote(app.password), migrate_password=migrate_password,
        )
        migration_env = {k: os.environ[k] for k in (
            'HOME', 'PATH', 'LANG', 'VIRTUAL_ENV', 'PYTHONNOUSERSITE', 'SECRET_KEY',
        ) if k in os.environ}
        migration_env.update(
            DATABASE_URL=migrate_url, MPANGO_ENV='test', REPORTING_USER_PASSWORD=reporting_password,
            PYTHONPATH=str(Path(__file__).resolve().parents[1]), PYTHONDONTWRITEBYTECODE='1',
        )
        await asyncio.to_thread(
            _native, root, 'reporting-migration',
            [sys.executable, '-B', '-m', 'alembic', 'upgrade', '046_staff_credential_recovery'],
            env=migration_env, timeout=120,
        )
        # Check the real fresh legacy ACL before the first application of the
        # correction. No credential values are selected, even here.
        initial = await facts(data)
        assert initial['table_read'] is True and initial['column_read'] is True
        await zero_row_read(data, True)
        save(data, 'fresh-legacy-acl.json', {'facts': initial, 'limit_zero_read_admitted': True})
        await provisioner.apply_minimum_grants()
        await bootstrap('t_test', data['app_url'])
        assert platform_recovery_reporting_refusals(await facts(data)) == []
        assert await gate(data) == []
        yield data


@pytest_asyncio.fixture
async def legacy_reader(world):
    # Replay exactly the observed legacy table grant in this dedicated
    # database so that readiness (which needs the tenant schema) can see it.
    c = await asyncpg.connect(world['migrate_url'])
    try:
        await c.execute(f'GRANT SELECT ON {TARGET} TO reporting_role')
        yield
    finally:
        # Restore only grants owned by this test if it stopped before apply.
        await c.execute(f'REVOKE SELECT ON {TARGET} FROM reporting_user, reporting_role, PUBLIC')
        await c.close()


async def refused_gates(world, expected):
    result = await world['provisioner'].verify()
    check = result['checks']['platform_recovery_reporting_privileges']
    assert result['ok'] is False and check['ok'] is False
    assert expected in check['reasons']
    reasons = await gate(world)
    assert any(expected in reason for reason in reasons), reasons
    return {'verify': check, 'readiness_reasons': reasons}


async def zero_row_read(world, allowed):
    c = await asyncpg.connect(world['reporting_url'])
    try:
        # Always zero rows: tests privilege enforcement, never fetches a hash.
        sql = f'SELECT credential_hash FROM {TARGET} LIMIT 0'
        if allowed:
            assert await c.fetch(sql) == []
        else:
            with pytest.raises(asyncpg.InsufficientPrivilegeError) as error:
                await c.fetch(sql)
            assert error.value.sqlstate == '42501'
    finally:
        await c.close()


async def bi_and_app_positive(world):
    report = await asyncpg.connect(world['reporting_url'])
    try:
        result = {}
        for view in ['mv_sales_daily', 'rpt_receivables_summary', 'rpt_cash_flow_daily']:
            result[view] = await report.fetchval(f'SELECT count(*) FROM "t_test".{view}')
        result['public_wholesalers'] = await report.fetchval(
            'SELECT count(*) FROM public.wholesalers')
    finally:
        await report.close()
    app = await asyncpg.connect(world['app_url'])
    tx = app.transaction()
    await tx.start()
    try:
        uid = uuid4()
        await app.execute('INSERT INTO public.platform_operators(id,email) VALUES($1,$2)',
                          uid, 'synthetic-' + uid.hex + '@example.com')
        rid = await app.fetchval(f'INSERT INTO {TARGET}(operator_id,credential_hash) '
                                'VALUES($1,$2) RETURNING id', uid, uuid4().hex)
        assert await app.fetchval(f'SELECT status FROM {TARGET} WHERE id=$1', rid) == 'active'
        await app.execute(f"UPDATE {TARGET} SET status='used',used_at=now() WHERE id=$1", rid)
        assert await app.fetchval(f'SELECT status FROM {TARGET} WHERE id=$1', rid) == 'used'
        await app.execute(f'DELETE FROM {TARGET} WHERE id=$1', rid)
        assert await app.fetchval(f'SELECT count(*) FROM {TARGET} WHERE id=$1', rid) == 0
    finally:
        await tx.rollback()
        await app.close()
    return {'view_query_counts': result, 'synthetic_app_select_insert_update_delete': True,
            'app_transaction_rolled_back': True, 'credential_values_selected': False}


async def test_legacy_reader_exact_apply_repeat_and_positive_consumers(world, legacy_reader):
    before = await facts(world)
    assert before['table_read'] is True and before['column_read'] is True
    await zero_row_read(world, True)
    old = await refused_gates(world, 'PLATFORM_RECOVERY_REPORTING_TABLE_READ')
    save(world, '00-replayed-legacy-acl.json', {'facts': before, 'gates': old,
                                              'limit_zero_read_admitted': True})
    # Additional controlled direct/PUBLIC grants are synthetic cases, not a
    # claim that those were present in the historical default-ACL observation.
    c = await asyncpg.connect(world['migrate_url'])
    try:
        await c.execute(f'GRANT SELECT ON {TARGET} TO reporting_user, reporting_role, PUBLIC')
    finally:
        await c.close()
    positive_before = await bi_and_app_positive(world)
    for index in range(2):
        await world['provisioner'].apply_minimum_grants()
        actual = await facts(world)
        assert platform_recovery_reporting_refusals(actual) == []
        await zero_row_read(world, False)
        verified = await world['provisioner'].verify()
        assert verified['ok'] is True, verified
        assert await gate(world) == []
        positive = await bi_and_app_positive(world)
        assert positive == positive_before
        save(world, f'01-fixed-repeat-{index}.json', {'facts': actual,
             'verify_ok': verified['ok'], 'readiness_ok': True,
             'reporting_hash_limit_zero_sqlstate': '42501', 'positive': positive})


@pytest.mark.parametrize('principal', ['reporting_user', 'reporting_role', 'PUBLIC'])
async def test_residual_column_grants_refuse_without_silent_cleanup(world, principal):
    c = await asyncpg.connect(world['migrate_url'])
    try:
        await c.execute(f'GRANT SELECT(credential_hash) ON {TARGET} TO {principal}')
        before = await facts(world)
        assert before['table_read'] is False and before['column_read'] is True
        with pytest.raises(RuntimeError, match='PLATFORM_RECOVERY_REPORTING_COLUMN_READ'):
            await world['provisioner'].apply_minimum_grants()
        after = await facts(world)
        assert after == before  # Whole authorization transaction rolled back.
        negative = await refused_gates(world, 'PLATFORM_RECOVERY_REPORTING_COLUMN_READ')
        save(world, 'column-' + principal + '.json', {'facts': after, 'gates': negative,
                                                   'unreviewed_column_acl_untouched': True})
    finally:
        await c.execute(f'REVOKE SELECT(credential_hash) ON {TARGET} FROM {principal}')
        await c.close()


@pytest.mark.parametrize('inherit', [True, False])
async def test_unknown_inherited_or_set_only_reader_refuses_without_role_revocation(world, inherit):
    role = 'mp_r2_reader_' + uuid4().hex[:8]
    admin = await asyncpg.connect(world['admin_url'])
    migrate = await asyncpg.connect(world['migrate_url'])
    try:
        await admin.execute(f'CREATE ROLE "{role}" NOLOGIN')
        await migrate.execute(f'GRANT SELECT ON {TARGET} TO "{role}"')
        await admin.execute(f'GRANT "{role}" TO reporting_user WITH INHERIT '
                            + ('TRUE' if inherit else 'FALSE') + ', SET TRUE')
        before = await facts(world)
        assert before['table_read'] is inherit
        assert before['unknown_reader_roles'] == [role]
        with pytest.raises(RuntimeError, match='PLATFORM_RECOVERY_REPORTING_UNAPPROVED_ROLE_PATH'):
            await world['provisioner'].apply_minimum_grants()
        assert await facts(world) == before
        assert await migrate.fetchval('SELECT has_table_privilege($1,$2,\'SELECT\')', role, TARGET)
        negative = await refused_gates(world, 'PLATFORM_RECOVERY_REPORTING_UNAPPROVED_ROLE_PATH')
        save(world, 'unknown-role-' + str(inherit) + '.json', {'facts': before,
             'gates': negative, 'unknown_role_grant_and_membership_untouched': True})
    finally:
        await admin.execute(f'REVOKE "{role}" FROM reporting_user')
        await migrate.execute(f'REVOKE SELECT ON {TARGET} FROM "{role}"')
        await admin.execute(f'DROP ROLE "{role}"')
        await migrate.close()
        await admin.close()
