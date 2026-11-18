"""One fresh task PG: exact ACL correction, fail-closed gates and BI positives.

This suite never selects credential values. LIMIT 0 checks statement admission;
the optional synthetic app rows are rolled back. No production credentials,
Operator login, mail, or recovery operation is performed.
"""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4
import asyncio

import asyncpg
import pytest
import pytest_asyncio

from scripts.provision_runtime_db_roles import (
    Provisioner, PLATFORM_RECOVERY_REPORTING_SQL,
    platform_recovery_reporting_refusals,
)
from scripts.runtime_readiness_gate import evaluate_contract

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
    return await asyncio.to_thread(evaluate_contract, world['app_url'], 't_test')


@pytest_asyncio.fixture(scope='module')
async def world():
    root = Path(os.environ['REPORTING_FIX_TASK_ROOT']).resolve(strict=True)
    path = Path(os.environ['REPORTING_FIX_INPUT_JSON'])
    assert path.parent == root / 'private' and path.name.startswith('B-test-inputs')
    assert not path.is_symlink()
    assert path.stat().st_uid == os.getuid() and path.stat().st_mode & 0o777 == 0o600
    data = json.loads(path.read_text())
    run = Path(os.environ['REPORTING_FIX_RUN_ROOT'])
    assert run.parent == root and run.name in ('run', 'run-r2')
    ready = json.loads((run / 'private/A/resources-ready.json').read_text())
    assert ready['task'] == root.name + '-A'
    assert ready['owner'] == 'codexl-recovery-reporting-r2-20261117'
    pg = next(x for x in ready['containers'] if x['kind'] == 'pg')
    binding = pg['ports']['5432/tcp']
    assert len(binding) == 1 and binding[0]['HostIp'] == '127.0.0.1'
    roles = {'app_url': 'mpango_app', 'migrate_url': 'mpango_migrate',
             'admin_url': 'postgres', 'reporting_url': 'reporting_user'}
    for key, role in roles.items():
        u = urlsplit(data[key])
        if not (u.scheme == 'postgresql' and u.hostname == '127.0.0.1'
                and u.port == int(binding[0]['HostPort']) and u.username == role
                and u.password and not u.query and not u.fragment
                and u.path == ('/postgres' if role == 'postgres' else '/test_ci_mpango')):
            raise RuntimeError('TASK_DATABASE_BINDING_INVALID')
    if data['reporting_url'] != os.environ['REPORTING_DATABASE_URL']:
        raise RuntimeError('REPORTING_RUNTIME_SOURCE_MISMATCH')
    data['facts_dir'] = Path(os.environ['REPORTING_FIX_FACTS_DIR'])
    assert data['facts_dir'].parent == root / 'private'
    assert data['facts_dir'].name.startswith('B-pg-facts-')
    data['facts_dir'].mkdir(mode=0o700)
    data['provisioner'] = Provisioner(data['admin_url'], data['migrate_url'],
                                    data['app_url'], 'mpango_migrate',
                                    'mpango_app', 'test_ci_mpango')
    yield data


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


async def test_legacy_reader_exact_apply_repeat_and_positive_consumers(world):
    before = await facts(world)
    assert before['table_read'] is True and before['column_read'] is True
    await zero_row_read(world, True)
    old = await refused_gates(world, 'PLATFORM_RECOVERY_REPORTING_TABLE_READ')
    save(world, '00-real-legacy-prestate.json', {'facts': before, 'gates': old,
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
