"""R6 contract: smoke-family executables take caller-explicit task-only input.

Missing / empty / whitespace-only values must be refused with a fixed
category before any connection, Docker or DDL side effect, without echoing
the value. Explicit valid values flow into BACKEND_ENV unchanged. The parent
(BASE) bytes lacked this guard and must fail the same semantic assertion.
"""
import json
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
    Expected values travel via argv (never as file literals); the child
    compares BACKEND_ENV entries to them and prints only the verdict."""
    names = ','.join(ENV_NAMES)
    values = '\x1f'.join(VALID[name] for name in ENV_NAMES)
    probe = ('import runpy, sys\n'
             'ns = runpy.run_path(sys.argv[1], run_name="not_main")\n'
             'keys = [n[len("MPANGO_SMOKE_"):] for n in sys.argv[2].split(",")]\n'
             'vals = sys.argv[3].split("\\x1f")\n'
             'ok = all(ns["BACKEND_ENV"][k] == v for k, v in zip(keys, vals))\n'
             'print("PROBE_OK" if ok else "PROBE_MISMATCH")\n')
    return subprocess.run([sys.executable, '-c', probe, str(script), names, values],
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


STANDIN_WRAPPER = r'''
import json, os, sys, threading, types
from http.server import BaseHTTPRequestHandler, HTTPServer
MODE = sys.argv[2]
OVR = os.environ["MPANGO_SMOKE_TEST_OVERRIDE_SECRET"]
OP = os.environ["MPANGO_SMOKE_OPERATOR_SECRET"]
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        h = self.headers
        if "X-Platform-Test-Override" in h:
            # correct: matching override still rejected (403).
            # wrong_accept: policy defects to ACCEPT the MATCHING override
            # only; non-matching values are still 403.
            code = 200 if (MODE == "wrong_accept" and h.get("X-Platform-Test-Override") == OVR) else 403
        elif h.get("X-Platform-Operator") == OP:
            code = 200
        elif h.get("X-Platform-Operator") is not None:
            code = 403
        elif (h.get("Authorization") or "").startswith("Bearer identity-"):
            code = 200
        elif (h.get("Authorization") or "").startswith("Bearer "):
            code = 403
        else:
            code = 401
        self.send_response(code); self.end_headers(); self.wfile.write(b"{}")
    def log_message(self, *a):
        pass
srv = HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
core = types.ModuleType("core"); cs = types.ModuleType("core.security")
cs.create_identity_token = lambda **kw: "identity-" + kw.get("user_id", "x")
cs.create_contextual_token = lambda **kw: "tenant-" + kw.get("tenant_id", "x")
core.security = cs
sys.modules["core"] = core; sys.modules["core.security"] = cs
ns = {"__name__": "not_main", "__file__": sys.argv[1]}
exec(compile(open(sys.argv[1], encoding="utf-8").read(), sys.argv[1], "exec"), ns)
ns["BACKEND_URL"] = "http://127.0.0.1:%d" % srv.server_address[1]
result = ns["run_identity_smoke"]()
print("SMOKE_SUMMARY:" + json.dumps(result["summary"]))
print("CASES:" + json.dumps({c["test"]: c["passed"] for c in result["cases"]}))
srv.shutdown()
'''


def run_identity_smoke_against_stand_in(script, mode):
    return subprocess.run([sys.executable, '-c', STANDIN_WRAPPER, str(script), mode],
                          capture_output=True, text=True, timeout=120,
                          env=env_with(VALID))


@pytest.mark.parametrize('script', SMOKE, ids=lambda s: s.parent.name)
def test_override_control_discriminates_wrong_acceptance(script):
    """Correct production rejection -> all green; a policy that wrongly
    ACCEPTS the matching override must make the smoke non-green."""
    proc = run_identity_smoke_against_stand_in(script, 'correct')
    assert proc.returncode == 0, proc.stderr[-300:]
    summary = json.loads([l for l in proc.stdout.splitlines()
                          if l.startswith('SMOKE_SUMMARY:')][0][14:])
    cases = json.loads([l for l in proc.stdout.splitlines()
                        if l.startswith('CASES:')][0][6:])
    assert summary['failed'] == 0, (summary, cases)
    assert cases['test_override_reject'] is True
    proc = run_identity_smoke_against_stand_in(script, 'wrong_accept')
    summary = json.loads([l for l in proc.stdout.splitlines()
                          if l.startswith('SMOKE_SUMMARY:')][0][14:])
    cases = json.loads([l for l in proc.stdout.splitlines()
                        if l.startswith('CASES:')][0][6:])
    assert summary['failed'] >= 1, 'wrongly accepting policy must fail the smoke'
    assert cases['test_override_reject'] is False


BARRIER_WRAPPER = r'''
import json, runpy, sys
counts = {}
def hook(event, args):
    if event in ("subprocess.Popen", "os.system", "socket.connect", "socket.getaddrinfo"):
        counts[event] = counts.get(event, 0) + 1
        raise PermissionError("BARRIER:" + event)
sys.addaudithook(hook)
exit_code, err = 0, ""
try:
    runpy.run_path(sys.argv[1], run_name="__main__")
except SystemExit as e:
    exit_code = e.code if isinstance(e.code, int) else 1
    err = str(e)
except BaseException as e:
    exit_code, err = -99, type(e).__name__ + ":" + str(e)
print("BARRIERJSON:" + json.dumps({"counts": counts, "exit": exit_code, "err": err[:200]}))
'''


@pytest.mark.parametrize('script', SMOKE, ids=lambda s: s.parent.name)
@pytest.mark.parametrize('category,value', [
    ('SMOKE_INPUT_MISSING', None),
    ('SMOKE_INPUT_EMPTY', ''),
    ('SMOKE_INPUT_WHITESPACE', '   '),
])
def test_rejection_precedes_any_dangerous_call(script, category, value, tmp_path):
    """Real entry chain under an audit barrier: the fixed-category refusal
    must occur with ZERO subprocess/socket attempt counts (connection,
    Docker, DDL all spawn through these)."""
    overrides = dict(VALID)
    overrides['MPANGO_SMOKE_DATABASE_URL'] = value
    if value is None:
        overrides.pop('MPANGO_SMOKE_DATABASE_URL')
    proc = subprocess.run([sys.executable, '-c', BARRIER_WRAPPER, str(script)],
                          capture_output=True, text=True, timeout=120,
                          env=env_with(overrides), cwd=str(tmp_path))
    report = json.loads([l for l in proc.stdout.splitlines()
                         if l.startswith('BARRIERJSON:')][0][12:])
    assert category in report['err'], report
    assert report['counts'] == {}, report


def test_parent_bytes_fail_same_oracle(tmp_path):
    """Permanent oracle: exit via SMOKE_INPUT_MISSING with zero dangerous
    calls. The BASE bytes must FAIL this oracle (semantic RED), with any
    dangerous attempt blocked by the barrier."""
    base = subprocess.run(['git', '-C', str(REPO), 'show',
                           'a1feb59324ab98769e655bc2a708f5ef042e4ad1:verify/p25ed/run_smoke.py'],
                          check=True, capture_output=True).stdout
    old = tmp_path / 'run_smoke_base.py'
    old.write_bytes(base)
    proc = subprocess.run([sys.executable, '-c', BARRIER_WRAPPER, str(old)],
                          capture_output=True, text=True, timeout=120,
                          env=env_with({}), cwd=str(tmp_path))
    report = json.loads([l for l in proc.stdout.splitlines()
                         if l.startswith('BARRIERJSON:')][0][12:])
    assert 'SMOKE_INPUT_MISSING' not in report['err'], \
        'parent bytes must fail the oracle (semantic RED)'
    for event, count in report['counts'].items():
        assert count >= 1, 'blocked attempt recorded'
