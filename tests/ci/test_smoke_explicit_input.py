"""Real smoke entrypoints under one pre-load process/socket audit barrier.

The trusted pytest parent may create one interpreter. All tested script bytes,
including historical/mutant bytes and import probes, execute only in task tmp.
This is a bounded side-effect contract, not an adversarial OS sandbox.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SMOKE = [REPO / f'verify/{name}/run_smoke.py' for name in ('p25ed', 'p25ee', 'p25ef')]
ENV_NAMES = ['MPANGO_SMOKE_DATABASE_URL', 'MPANGO_SMOKE_SECRET_KEY',
             'MPANGO_SMOKE_OPERATOR_SECRET', 'MPANGO_SMOKE_TEST_OVERRIDE_SECRET',
             'MPANGO_SMOKE_REPORTING_DATABASE_URL']
VALID = {name: 'task-only-' + name.lower().replace('_', '-') + '-input' for name in ENV_NAMES}

BARRIER_WRAPPER = r'''
import io, json, os, runpy, socket, sys, types, urllib.request
from urllib.error import HTTPError
counts = {}
blocked = {"subprocess.Popen", "os.system", "os.posix_spawn", "os.fork",
           "socket.connect", "socket.getaddrinfo", "socket.bind"}
def deny(event):
    counts[event] = counts.get(event, 0) + 1
    raise PermissionError("BARRIER:" + event)
def hook(event, args):
    if event in blocked:
        deny(event)
sys.addaudithook(hook)
socket.socket.listen = lambda *a, **k: deny("socket.listen")
exit_code, err, result = 0, "", {}
try:
    mode = sys.argv[2]
    if mode in ("correct", "wrong_accept"):
        core = types.ModuleType("core")
        security = types.ModuleType("core.security")
        security.create_identity_token = lambda **kw: "fixture-identity"
        security.create_contextual_token = lambda **kw: "fixture-tenant"
        core.security = security
        sys.modules["core"] = core
        sys.modules["core.security"] = security
        def urlopen(request, **kwargs):
            headers = {k.lower(): v for k, v in request.header_items()}
            override = headers.get("x-platform-test-override")
            operator = headers.get("x-platform-operator")
            if override is not None:
                code = 200 if mode == "wrong_accept" and override == os.environ["MPANGO_SMOKE_TEST_OVERRIDE_SECRET"] else 403
            elif operator is not None:
                code = 200 if operator == os.environ["MPANGO_SMOKE_OPERATOR_SECRET"] else 403
            elif headers.get("authorization") == "Bearer fixture-identity":
                code = 200
            elif headers.get("authorization"):
                code = 403
            else:
                code = 401
            if code >= 400:
                raise HTTPError(request.full_url, code, "fixture", {}, io.BytesIO(b"{}"))
            return types.SimpleNamespace(status=code, read=lambda: b"{}")
        urllib.request.urlopen = urlopen
    ns = runpy.run_path(sys.argv[1], run_name="__main__" if mode == "main" else "not_main")
    if mode == "import":
        keys = ["DATABASE_URL", "SECRET_KEY", "PLATFORM_OPERATOR_SECRET",
                "PLATFORM_TEST_OVERRIDE_SECRET", "REPORTING_DATABASE_URL"]
        result["probe_ok"] = all(ns["BACKEND_ENV"][key] == os.environ[name]
                                 for key, name in zip(keys, json.loads(sys.argv[3])))
    elif mode in ("correct", "wrong_accept"):
        smoke = ns["run_identity_smoke"]()
        result = {"summary": smoke["summary"],
                  "cases": {case["test"]: case["passed"] for case in smoke["cases"]}}
except SystemExit as exc:
    exit_code = exc.code if isinstance(exc.code, int) else 1
    err = str(exc)
except BaseException as exc:
    exit_code = -99
    err = "BARRIER_REFUSED" if isinstance(exc, PermissionError) else type(exc).__name__
print("BARRIERJSON:" + json.dumps({"counts": counts, "exit": exit_code,
                                  "err": err, "result": result}))
'''


def env_with(overrides):
    return {'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
            'HOME': os.environ.get('HOME', '/tmp'), 'PYTHONDONTWRITEBYTECODE': '1', **overrides}


def run_protected(script, tmp_path, overrides, mode='main', source=None):
    target = tmp_path / script.parent.name / 'run_smoke.py'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(script.read_bytes() if source is None else source)
    proc = subprocess.run([sys.executable, '-B', '-c', BARRIER_WRAPPER, str(target), mode,
                           json.dumps(ENV_NAMES)], cwd=tmp_path, env=env_with(overrides),
                          capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, 'protected interpreter failed before contract result'
    reports = [line[12:] for line in proc.stdout.splitlines() if line.startswith('BARRIERJSON:')]
    assert len(reports) == 1
    return json.loads(reports[0])


def refusal_oracle(report, category):
    return report['exit'] != 0 and category in report['err'] and report['counts'] == {}


@pytest.mark.parametrize('script', SMOKE, ids=lambda s: s.parent.name)
@pytest.mark.parametrize('category,value', [('SMOKE_INPUT_MISSING', None),
                                           ('SMOKE_INPUT_EMPTY', ''),
                                           ('SMOKE_INPUT_WHITESPACE', '   ')])
def test_missing_empty_whitespace_refused_before_side_effects(script, category, value, tmp_path):
    overrides = dict(VALID)
    if value is None:
        overrides.pop('MPANGO_SMOKE_DATABASE_URL')
    else:
        overrides['MPANGO_SMOKE_DATABASE_URL'] = value
    report = run_protected(script, tmp_path, overrides)
    assert refusal_oracle(report, category), report
    assert not any(v in json.dumps(report) for v in VALID.values()), 'value echo'


@pytest.mark.parametrize('script', SMOKE, ids=lambda s: s.parent.name)
def test_explicit_values_flow_into_backend_env(script, tmp_path):
    report = run_protected(script, tmp_path, VALID, 'import')
    assert report['exit'] == 0 and report['counts'] == {} and report['result']['probe_ok']


def parent_oracle_rejection(tmp_path):
    base = subprocess.run(['git', '-C', str(REPO), 'show',
                           'a1feb59324ab98769e655bc2a708f5ef042e4ad1:verify/p25ed/run_smoke.py'],
                          check=True, capture_output=True).stdout
    report = run_protected(SMOKE[0], tmp_path, {}, source=base)
    assert not refusal_oracle(report, 'SMOKE_INPUT_MISSING'), 'EXPECTED_ORACLE_REJECTION'
    assert report['err'] == 'BARRIER_REFUSED'
    assert report['counts'].get('subprocess.Popen') == 1, report


def test_parent_bytes_lack_the_guard(tmp_path):
    parent_oracle_rejection(tmp_path)


def test_parent_bytes_fail_same_oracle(tmp_path):
    parent_oracle_rejection(tmp_path)


@pytest.mark.parametrize('script', SMOKE, ids=lambda s: s.parent.name)
def test_guard_mutant_fails_same_oracle(script, tmp_path):
    source = script.read_text()
    anchor = '    value = os.environ.get(env_name)\n'
    assert source.count(anchor) == 1
    mutant = source.replace(anchor, '    return "fixture-bypass"\n' + anchor)
    compile(mutant, str(script), 'exec')
    report = run_protected(script, tmp_path, {}, source=mutant.encode())
    assert not refusal_oracle(report, 'SMOKE_INPUT_MISSING'), 'EXPECTED_ORACLE_REJECTION'
    assert report['err'] == 'BARRIER_REFUSED' and report['counts'].get('subprocess.Popen') == 1


@pytest.mark.parametrize('event,source', [
    ('subprocess.Popen', 'import subprocess; subprocess.Popen(["/bin/true"])'),
    ('os.system', 'import os; os.system("true")'),
    ('socket.getaddrinfo', 'import socket; socket.getaddrinfo("fixture.invalid", 1)'),
    ('socket.connect', 'import socket\nwith socket.socket() as sock: sock.connect(("127.0.0.1", 1))'),
    ('socket.bind', 'import socket\nwith socket.socket() as sock: sock.bind(("127.0.0.1", 0))'),
    ('socket.listen', 'import socket\nwith socket.socket() as sock: sock.listen()'),
])
def test_barrier_blocks_process_and_socket_boundary(event, source, tmp_path):
    report = run_protected(SMOKE[0], tmp_path, {}, source=source.encode())
    assert report['err'] == 'BARRIER_REFUSED' and report['counts'] == {event: 1}


@pytest.mark.parametrize('script', SMOKE, ids=lambda s: s.parent.name)
def test_override_control_discriminates_wrong_acceptance(script, tmp_path):
    correct = run_protected(script, tmp_path, VALID, 'correct')
    assert correct['exit'] == 0 and correct['counts'] == {}, correct
    assert correct['result']['summary']['failed'] == 0
    assert correct['result']['cases']['test_override_reject'] is True
    wrong = run_protected(script, tmp_path, VALID, 'wrong_accept')
    assert wrong['exit'] == 0 and wrong['counts'] == {}, wrong
    assert wrong['result']['summary']['failed'] == 1
    assert wrong['result']['cases']['test_override_reject'] is False


@pytest.mark.parametrize('script', SMOKE, ids=lambda s: s.parent.name)
@pytest.mark.parametrize('category,value', [('SMOKE_INPUT_MISSING', None),
                                           ('SMOKE_INPUT_EMPTY', ''),
                                           ('SMOKE_INPUT_WHITESPACE', '   ')])
def test_rejection_precedes_any_dangerous_call(script, category, value, tmp_path):
    test_missing_empty_whitespace_refused_before_side_effects(script, category, value, tmp_path)


def test_powershell_entry_converted():
    text = (REPO / 'verify/p25ed/start_backend.ps1').read_text()
    assert 'Require-SmokeInput' in text
    for name in ENV_NAMES[:-1]:
        assert name in text
    assert 'SMOKE_INPUT_MISSING' in text and 'SMOKE_INPUT_WHITESPACE' in text
    if shutil.which('pwsh') is None:
        pytest.skip('pwsh not installed: runtime chain NOT_TESTED')
    pytest.skip('Windows runtime chain NOT_TESTED in this Linux bounded battery')
