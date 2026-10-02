"""Real offline detector, failure and workflow-dispatch contracts, no DB fixture."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import venv

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
DS = REPO / 'tools/ci/secrets_gate.sh'
HC = REPO / 'tools/ci/hardcoded_creds_gate.sh'

def git(root, *args):
    subprocess.run(['git', *args], cwd=root, check=True, capture_output=True)

def run(script, root, env=None):
    return subprocess.run(['bash', str(script), str(root)], cwd=root, env=env,
                          capture_output=True, text=True, timeout=120)

@pytest.fixture
def clean(tmp_path):
    root = tmp_path / 'fixture'
    root.mkdir()
    git(root, 'init', '-q')
    (root / 'app.py').write_text('print("hello")\n')
    git(root, 'add', '.')
    result = subprocess.run(['detect-secrets', 'scan'], cwd=root,
                            capture_output=True, text=True, check=True)
    (root / '.secrets.baseline').write_text(result.stdout)
    git(root, 'add', '.')
    return root

def test_clean_and_stale_baseline_remain_readonly(clean):
    baseline = clean / '.secrets.baseline'
    doc = json.loads(baseline.read_text())
    doc['results']['app.py'] = [{'type': 'Secret Keyword', 'hashed_secret': 'a' * 40,
                                'line_number': 90, 'is_verified': False}]
    baseline.write_text(json.dumps(doc))
    git(clean, 'add', '.')
    before = baseline.read_bytes()
    proc = run(DS, clean)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)['baseline_unchanged']
    assert baseline.read_bytes() == before, 'R5_BASELINE_READONLY'

def test_canary_spaces_real_detector_red_no_value(clean):
    value = 'C91_SYNTHETIC_NOT_A_CREDENTIAL_' + secrets.token_hex(24)
    (clean / 'secret config.py').write_text('password = ' + repr(value))
    git(clean, 'add', '.')
    before = (clean / '.secrets.baseline').read_bytes()
    proc = run(DS, clean)
    assert proc.returncode == 1, 'R5_DISCOVERY_MUST_REJECT'
    report = json.loads(proc.stdout)
    assert report['new_findings'] > 0 and any(f['path'] == 'secret config.py' for f in report['findings'])
    assert value not in proc.stdout + proc.stderr
    assert (clean / '.secrets.baseline').read_bytes() == before

def test_tool_missing_red(clean, tmp_path):
    isolated = tmp_path / 'without-detector'
    venv.EnvBuilder(with_pip=False).create(isolated)
    env = dict(os.environ, PATH=str(isolated / 'bin') + ':/usr/bin:/bin')
    proc = run(DS, clean, env)
    assert proc.returncode == 3 and 'DETECTOR_UNAVAILABLE' in proc.stderr

@pytest.mark.parametrize('body', ['not-json', '{"results":{}}'])
def test_corrupt_baseline_red(clean, body):
    (clean / '.secrets.baseline').write_text(body)
    assert run(DS, clean).returncode == 4

def test_enumeration_failure_rejects_even_partial_output(clean, tmp_path):
    binpath = tmp_path / 'bin'
    binpath.mkdir()
    command = binpath / 'git'
    command.write_text('#!/bin/sh\nprintf "app.py\\000"\nexit 2\n')
    command.chmod(0o755)
    env = dict(os.environ, PATH=str(binpath) + ':' + os.environ['PATH'])
    for script in (DS, HC):
        assert run(script, clean, env).returncode == 5, 'R5_TOOL_FAILURE_MUST_REJECT'

def test_unreadable_tracked_input_not_clean(clean):
    (clean / 'gone.py').write_text('print(1)')
    git(clean, 'add', '.')
    (clean / 'gone.py').unlink()
    assert run(DS, clean).returncode == 5
    assert run(HC, clean).returncode == 5

def test_hardcoded_clean_and_canary(clean):
    assert run(HC, clean).returncode == 0
    value = 'C91_NOT_A_CREDENTIAL_' + secrets.token_hex(16)
    (clean / 'db.py').write_text('password = ' + repr(value))
    git(clean, 'add', '.')
    proc = run(HC, clean)
    assert proc.returncode == 1, 'R5_HARDCODED_MATCH_MUST_REJECT'
    assert any(f['path'] == 'db.py' for f in json.loads(proc.stdout)['findings'])
    assert value not in proc.stdout + proc.stderr

def test_original_excludes_and_aws_test_scope(clean):
    folder = clean / 'backend/tests'
    folder.mkdir(parents=True)
    (folder / 'db.py').write_text('password = "' + secrets.token_hex(16) + '"')
    git(clean, 'add', '.')
    assert run(HC, clean).returncode == 0
    (folder / 'aws.py').write_text('AWS_ACCESS_' + 'KEY_ID = "synthetic"')
    git(clean, 'add', '.')
    assert run(HC, clean).returncode == 1

def test_untracked_private_files_are_outside_declared_scope(clean):
    (clean / 'private.py').write_text('password = "' + secrets.token_hex(16) + '"')
    assert run(DS, clean).returncode == run(HC, clean).returncode == 0

def test_private_key_filename_rejected(clean):
    (clean / 'owned.key').write_text('synthetic-not-a-key')
    git(clean, 'add', '.')
    assert run(HC, clean).returncode == 1

def test_detector_failure_is_fixed_category(clean, tmp_path):
    folder = tmp_path / 'tools/ci'
    shutil.copytree(REPO / 'tools/ci', folder)
    source = folder / 'secret_checks.py'
    source.write_text(source.read_text().replace('observed.scan_file(name)',
                      '(_ for _ in ()).throw(RuntimeError("synthetic-fault"))'))
    proc = run(folder / 'secrets_gate.sh', clean)
    assert proc.returncode == 3 and 'DETECTOR_EXECUTION_FAILED' in proc.stderr
    assert 'synthetic-fault' not in proc.stderr

def test_detector_logged_read_failure_is_not_clean(clean, tmp_path):
    folder = tmp_path / 'fault-tools/ci'
    shutil.copytree(REPO / 'tools/ci', folder)
    source = folder / 'secret_checks.py'
    source.write_text(source.read_text().replace('observed.scan_file(name)',
                      'log.warning("synthetic-unreadable")'))
    proc = run(folder / 'secrets_gate.sh', clean)
    assert proc.returncode == 3 and 'DETECTOR_EXECUTION_FAILED' in proc.stderr
    assert 'synthetic-unreadable' not in proc.stderr

def test_workflow_runs_real_entrypoint_under_strict_bash(clean):
    doc = yaml.safe_load((REPO / '.github/workflows/security-scan.yml').read_text())
    steps = {s['id']: s for s in doc['jobs']['secret-detection']['steps'] if 'id' in s}
    assert 'detect-secrets==1.5.0' in steps['detect-secrets']['run']
    assert '--baseline' not in steps['detect-secrets']['run']
    shutil.copytree(REPO / 'tools/ci', clean / 'tools/ci')
    git(clean, 'add', '.')
    for key in ('detect-secrets', 'hardcoded-credentials'):
        body = steps[key]['run']
        if key == 'detect-secrets':
            # Installation is already satisfied in the test venv; run the exact
            # workflow body (not a separately implemented detector).
            assert 'tools/ci/secrets_gate.sh' in body
        proc = subprocess.run(['bash', '-euo', 'pipefail', '-c', body], cwd=clean,
                              capture_output=True, text=True, timeout=120)
        assert proc.returncode == 0, proc.stderr
    summary = next(s['run'] for s in doc['jobs']['secret-detection']['steps']
                   if s.get('name') == 'Security scan summary')
    assert 'steps.detect-secrets.outcome' in summary and 'job.status' in summary
