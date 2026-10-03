"""R6 contract: smoke-family executables take caller-explicit task-only input.

Missing / empty / whitespace-only values must be refused with a fixed
category before any connection, Docker or DDL side effect, without echoing
the value. Explicit valid values flow into BACKEND_ENV unchanged. The parent
(BASE) bytes lacked this guard and must fail the same semantic assertion.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SMOKE = [REPO / 'verify/p25ed/run_smoke.py', REPO / 'verify/p25ee/run_smoke.py',
         REPO / 'verify/p25ef/run_smoke.py']
ENV_NAMES = ['MPANGO_SMOKE_DATABASE_URL', 'MPANGO_SMOKE_SECRET_KEY',
             'MPANGO_SMOKE_OPERATOR_SECRET', 'MPANGO_SMOKE_TEST_OVERRIDE_SECRET',
             'MPANGO_SMOKE_REPORTING_DATABASE_URL']


def load_module(script, env):
    """Run the module-level code only (run_name != '__main__'): validation
    and BACKEND_ENV construction happen at import, before main() effects.
    Asserts the caller-provided values flow into BACKEND_ENV unchanged
    (equality checked inside the child; only the verdict is printed)."""
    probe = ('import runpy, os, sys\n'
             'ns = runpy.run_path(sys.argv[1], run_name="not_main")\n'
             'm = {"DATABASE_URL":"DATABASE_URL","SECRET_KEY":"SECRET_KEY",'
             '"PLATFORM_OPERATOR_SECRET":"OPERATOR_SECRET",'
             '"PLATFORM_TEST_OVERRIDE_SECRET":"TEST_OVERRIDE_SECRET",'
             '"REPORTING_DATABASE_URL":"REPORTING_DATABASE_URL"}\n'
             'ok = all(ns["BACKEND_ENV"][k] == os.environ["MPANGO_SMOKE_" + m[k]] for k in m)\n'
             'print("PROBE_OK" if ok else "PROBE_MISMATCH")\n')
    return subprocess.run([sys.executable, '-c', probe, str(script)],
                          capture_output=True, text=True, timeout=60, env=env)


VALID = {name: 'task-only-' + name.lower().replace('_', '-') + '-input'
         for name in ENV_NAMES}


def env_with(overrides):
    env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
           'HOME': os.environ.get('HOME', '/tmp')}
    for name, value in overrides.items():
        env[name] = value
    return env


@pytest.fixture(autouse=True)
def preserve_script_evidence_artifacts():
    """The scripts can write artifacts next to themselves; snapshot and
    restore every tracked file under verify/ so runs leave the tree clean."""
    import subprocess
    tracked = subprocess.run(['git', '-C', str(REPO), 'ls-files', 'verify'],
                             check=True, capture_output=True, text=True).stdout.split()
    before = {name: (REPO / name).read_bytes() for name in tracked}
    yield
    for name, data in before.items():
        path = REPO / name
        if not path.exists() or path.read_bytes() != data:
            path.write_bytes(data)


@pytest.mark.parametrize('script', SMOKE, ids=lambda s: s.parent.name)
@pytest.mark.parametrize('category,value', [
    ('SMOKE_INPUT_MISSING', None),
    ('SMOKE_INPUT_EMPTY', ''),
    ('SMOKE_INPUT_WHITESPACE', '   '),
])
def test_missing_empty_whitespace_refused_before_side_effects(script, category, value, tmp_path):
    overrides = dict(VALID)
    overrides['MPANGO_SMOKE_DATABASE_URL'] = value
    if value is None:
        overrides.pop('MPANGO_SMOKE_DATABASE_URL')
    cwd = tmp_path / 'cwd'
    cwd.mkdir()
    proc = subprocess.run([sys.executable, str(script)], cwd=str(cwd),
                          capture_output=True, text=True, timeout=60,
                          env=env_with(overrides))
    assert proc.returncode != 0
    assert category in proc.stderr, proc.stderr[-200:]
    for name in ENV_NAMES:
        assert 'task-only-' not in proc.stderr + proc.stdout, 'value echo'


@pytest.mark.parametrize('script', SMOKE, ids=lambda s: s.parent.name)
def test_explicit_values_flow_into_backend_env(script):
    proc = load_module(script, env_with(VALID))
    assert proc.returncode == 0, (proc.stderr[-300:], proc.stdout[-200:])
    assert 'PROBE_OK' in proc.stdout


def test_parent_bytes_lack_the_guard(tmp_path):
    base = subprocess.run(['git', '-C', str(REPO), 'show',
                           'a1feb59324ab98769e655bc2a708f5ef042e4ad1:verify/p25ed/run_smoke.py'],
                          check=True, capture_output=True).stdout
    old = tmp_path / 'run_smoke_base.py'
    old.write_bytes(base)
    proc = subprocess.run([sys.executable, str(old)], cwd=str(tmp_path),
                          capture_output=True, text=True, timeout=90,
                          env=env_with({}))  # no MPANGO_SMOKE_* inputs at all
    assert 'SMOKE_INPUT_MISSING' not in proc.stderr + proc.stdout, \
        'parent bytes must fail the new guard contract (semantic RED)'
    assert proc.returncode != 0  # it fails for its own reasons (no env/no backend), not ours


def test_powershell_entry_converted():
    ps1 = REPO / 'verify/p25ed/start_backend.ps1'
    text = ps1.read_text(encoding='utf-8')
    assert 'Require-SmokeInput' in text
    for name in ('MPANGO_SMOKE_DATABASE_URL', 'MPANGO_SMOKE_SECRET_KEY',
                 'MPANGO_SMOKE_OPERATOR_SECRET', 'MPANGO_SMOKE_TEST_OVERRIDE_SECRET'):
        assert name in text
    assert 'SMOKE_INPUT_MISSING' in text and 'SMOKE_INPUT_WHITESPACE' in text
    if shutil.which('pwsh') is None:
        pytest.skip('pwsh not installed: static contract asserted, runtime chain NOT_TESTED (recorded)')
    proc = subprocess.run(['pwsh', '-NoProfile', '-File', str(ps1)],
                          capture_output=True, text=True, timeout=60,
                          env=env_with({}))
    assert proc.returncode != 0 and 'SMOKE_INPUT_MISSING' in proc.stderr + proc.stdout
