"""Bounded Settings/seeder contracts; no database or service is started."""
import asyncio
import builtins
import importlib.util
import secrets
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest
from pydantic import ValidationError

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / 'backend'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def valid_import_environment(monkeypatch):
    monkeypatch.setenv('MPANGO_ENV', 'test')
    monkeypatch.setenv('SECRET_KEY', secrets.token_hex(32))


@pytest.fixture
def settings_type(monkeypatch):
    monkeypatch.syspath_prepend(str(BACKEND))
    for key in ('DATABASE_URL', 'MPANGO_ENV', 'SECRET_KEY', 'REDIS_URL',
                'PUBLIC_FRONTEND_URL', 'EMAIL_PROVIDER', 'EMAIL_DELIVERY_MODE'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('MPANGO_ENV', 'test')
    monkeypatch.setenv('SECRET_KEY', secrets.token_hex(32))
    return load(BACKEND / 'core/config.py', 'r6_config').Settings


def required_config():
    return dict(SECRET_KEY=secrets.token_hex(32), REDIS_URL='redis://fixture.invalid:6379/1',
                PUBLIC_FRONTEND_URL='https://fixture.invalid', EMAIL_PROVIDER='smtp',
                EMAIL_DELIVERY_MODE='smtp', SMTP_HOST='smtp.invalid', SMTP_USER='fixture',
                SMTP_PASSWORD=secrets.token_hex(24), EMAIL_FROM='fixture@example.invalid')


@pytest.mark.parametrize('mode', ['staging', 'production'])
@pytest.mark.parametrize('explicit', [False, True])
def test_non_test_database_default_refused(settings_type, mode, explicit, monkeypatch, capsys):
    calls = []
    import socket
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **k: calls.append('connect'))
    kwargs = required_config()
    default = settings_type.model_fields['DATABASE_URL'].default
    if explicit:
        kwargs['DATABASE_URL'] = default
    with pytest.raises(ValidationError) as caught:
        settings_type(_env_file=None, MPANGO_ENV=mode, **kwargs)
    diagnostic = str(caught.value) + capsys.readouterr().err
    assert 'DATABASE' in diagnostic, 'R6_DATABASE_DEFAULT_NOT_REFUSED'
    assert default not in diagnostic and kwargs['SECRET_KEY'] not in diagnostic
    assert calls == []


@pytest.mark.parametrize('mode', ['test', 'staging', 'production'])
def test_explicit_database_and_test_compatibility(settings_type, mode):
    kwargs = required_config()
    if mode != 'test':
        kwargs['DATABASE_URL'] = 'postgresql://fixture.invalid:5432/task'
    result = settings_type(_env_file=None, MPANGO_ENV=mode, **kwargs)
    assert result.MPANGO_ENV == mode
    if mode == 'test':
        assert result.DATABASE_URL == settings_type.model_fields['DATABASE_URL'].default


def test_staging_does_not_inherit_smtp_production_policy(settings_type):
    result = settings_type(_env_file=None, MPANGO_ENV='staging', SECRET_KEY=secrets.token_hex(32),
                           DATABASE_URL='postgresql://fixture.invalid/task')
    assert result.EMAIL_PROVIDER == result.EMAIL_DELIVERY_MODE == 'dev_sink'


@pytest.mark.parametrize('value,category', [(None, 'MISSING'), ('', 'EMPTY'), (' \t ', 'WHITESPACE')])
@pytest.mark.parametrize('allow_production', [False, True])
def test_seeder_refuses_before_import_or_write(value, category, allow_production, monkeypatch, capsys):
    module = load(BACKEND / 'scripts/seed_test_tenant.py', 'r6_seed')
    if value is None:
        monkeypatch.delenv('MPANGO_TEST_ADMIN_PASSWORD', raising=False)
    else:
        monkeypatch.setenv('MPANGO_TEST_ADMIN_PASSWORD', value)
    imports = []
    original = builtins.__import__
    def guarded(name, *a, **k):
        if name.startswith(('database', 'models', 'core', 'sqlalchemy')):
            imports.append(name)
            raise AssertionError('R6_SEED_IMPORT_BEFORE_INPUT_GUARD')
        return original(name, *a, **k)
    monkeypatch.setattr(builtins, '__import__', guarded)
    with pytest.raises(SystemExit) as caught:
        asyncio.run(module.seed(also_seed_t_dev=False, allow_production=allow_production))
    assert str(caught.value) == 'TEST_ADMIN_PASSWORD_' + category
    assert imports == [], 'R6_SEED_INPUT_GUARD_MISSING'
    assert capsys.readouterr() == ('', '')


def test_seeder_explicit_value_reaches_actual_hash_and_rbac(monkeypatch, capsys):
    monkeypatch.syspath_prepend(str(BACKEND))
    from core.permission_registry import ADMIN_PERMISSIONS, RETAILER_OPERATOR_PERMISSIONS
    from core.security import verify_password
    module = load(BACKEND / 'scripts/seed_test_tenant.py', 'r6_seed_positive')
    value = secrets.token_urlsafe(24)
    monkeypatch.setenv('MPANGO_TEST_ADMIN_PASSWORD', value)
    monkeypatch.setenv('MPANGO_ENV', 'test')
    rows, permission_ids = [], {}
    class Result:
        def __init__(self, value=None): self.value = value
        def scalar(self): return self.value
    class Session:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def commit(self): rows.append(('COMMIT', {}))
        async def execute(self, sql, params=None):
            sql, params = str(sql), params or {}
            rows.append((sql, params))
            if 'INSERT INTO permissions' in sql:
                permission_ids[params['code']] = str(len(permission_ids) + 1)
            if 'SELECT id FROM permissions' in sql:
                return Result(permission_ids.get(params['code']))
            if 'SELECT id FROM users' in sql: return Result('fixture-user')
            if 'SELECT id FROM roles' in sql: return Result('fixture-role')
            return Result()
    session_module = types.ModuleType('database.session')
    session_module.AsyncSessionLocal = Session
    monkeypatch.setitem(sys.modules, 'database.session', session_module)
    import core.config
    monkeypatch.setattr(core.config, 'get_settings', lambda: types.SimpleNamespace(DATABASE_URL='postgresql://localhost/task'))
    async def no_ddl(*args, **kwargs): pass
    monkeypatch.setattr(module, '_ensure_tenant_tables', no_ddl)
    monkeypatch.setattr(module, '_ensure_public_wholesaler', no_ddl)
    asyncio.run(module.seed(also_seed_t_dev=False, allow_production=False))
    user_insert = next(params for sql, params in rows if 'INSERT INTO users' in sql)
    assert verify_password(value, user_insert['password_hash']), 'R6_SEED_HASH_PATH_NOT_USED'
    assert set(permission_ids) == {code for code, _ in ADMIN_PERMISSIONS + RETAILER_OPERATOR_PERMISSIONS}
    assigned = {params['permission_id'] for sql, params in rows if 'INSERT INTO role_permissions' in sql}
    assert assigned == {permission_ids[code] for code, _ in ADMIN_PERMISSIONS}
    assert value not in str(capsys.readouterr()), 'R6_SEED_PASSWORD_ECHO'
    assert rows[-1][0] == 'COMMIT'


def test_seeder_single_tenant_option_preserved():
    import ast
    module = ast.parse((BACKEND / 'scripts/seed_test_tenant.py').read_text())
    seed = next(node for node in module.body if isinstance(node, ast.AsyncFunctionDef) and node.name == 'seed')
    assert any(isinstance(node, ast.If) and isinstance(node.test, ast.Name)
               and node.test.id == 'also_seed_t_dev' for node in ast.walk(seed))


@pytest.mark.parametrize('value,category', [(None, 'MISSING'), ('', 'EMPTY'), (' \t ', 'WHITESPACE'),
                                           ('runtime', 'VALID')])
def test_seeder_real_cli_refuses_before_database_import(value, category, tmp_path):
    wrapper = '''
import builtins, json, runpy, sys
attempts = []
original = builtins.__import__
def guarded(name, *a, **k):
    if name.startswith(('database', 'models', 'sqlalchemy')):
        attempts.append(name)
        raise PermissionError('DATABASE_IMPORT_BLOCKED')
    return original(name, *a, **k)
builtins.__import__ = guarded
sys.argv = [sys.argv[1]]
error = ''
try:
    runpy.run_path(sys.argv[0], run_name='__main__')
except SystemExit as exc:
    error = str(exc)
except PermissionError:
    error = 'DATABASE_IMPORT_BLOCKED'
print(json.dumps(dict(error=error, attempts=attempts)))
'''
    env = {'PATH': '/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE': '1',
           'MPANGO_ENV': 'test', 'SECRET_KEY': secrets.token_hex(32)}
    if value is not None:
        env['MPANGO_TEST_ADMIN_PASSWORD'] = secrets.token_urlsafe(24) if category == 'VALID' else value
    result = subprocess.run([sys.executable, '-B', '-c', wrapper,
                             str(BACKEND / 'scripts/seed_test_tenant.py')],
                            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0
    report = __import__('json').loads(result.stdout)
    if category == 'VALID':
        assert report == {'error': 'DATABASE_IMPORT_BLOCKED', 'attempts': ['database.session']}
        assert env['MPANGO_TEST_ADMIN_PASSWORD'] not in result.stdout + result.stderr
    else:
        assert report == {'error': 'TEST_ADMIN_PASSWORD_' + category, 'attempts': []}


@pytest.mark.parametrize('script,names', [
    ('b6_verification_curl.sh', ['MPANGO_B6_BASE_URL', 'MPANGO_TEST_ADMIN_PASSWORD', 'MPANGO_B6_TENANT_B_PASSWORD']),
    ('backend/scripts/test_login.sh', ['MPANGO_SMOKE_LOGIN_URL', 'MPANGO_TEST_ADMIN_PASSWORD']),
    ('scripts/test_dashboard.sh', ['MPANGO_DASHBOARD_BASE_URL', 'MPANGO_TEST_ADMIN_PASSWORD']),
    ('ai-ledger/ops/deploy_v0.1.1-rc2.sh', ['MPANGO_SMOKE_REJECTED_PASSWORD']),
    ('ai-ledger/ops/deploy_v0.1.2-rc1.sh', ['MPANGO_SMOKE_REJECTED_PASSWORD']),
])
@pytest.mark.parametrize('value', [None, '', ' \t '])
def test_shell_consumer_rejects_without_process_or_output(script, names, value, tmp_path):
    forbidden = tmp_path / 'unexpected-process'
    # Only bash is launched by the trusted parent. Any child command resolves
    # to a local sentinel, never a real HTTP/Docker/DDL operation.
    for command in ('curl', 'docker', 'docker-compose', 'python3', 'date', 'tee'):
        spy = tmp_path / command
        spy.write_text('#!/bin/bash\nprintf attempted > "' + str(forbidden) + '"\nexit 99\n')
        spy.chmod(0o755)
    env = {'PATH': str(tmp_path), **{name: secrets.token_hex(12) for name in names}}
    if value is None:
        env.pop(names[0])
    else:
        env[names[0]] = value
    result = subprocess.run(['/bin/bash', str(REPO / script)], cwd=tmp_path, env=env,
                            capture_output=True, text=True, timeout=5)
    assert result.returncode == 2 and 'SMOKE_INPUT_REQUIRED' in result.stderr
    assert not forbidden.exists() and not (tmp_path / 'b6_verification_results.txt').exists()
    assert all(v not in result.stdout + result.stderr for v in env.values() if v and v.strip())
