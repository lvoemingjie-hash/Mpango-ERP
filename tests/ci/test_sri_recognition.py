"""CTO F-01 contract: precise SHA-512 SRI integrity-field recognition.

Recognition is limited to full-line structured integrity fields with a
canonical SHA-512 SRI token. Same-file other-field canaries must stay RED;
malformed tokens, wrong length, wrong field, quoted/extra content must stay
findings; no generalization to plain high-entropy strings; baseline and the
original gate contracts must not regress.

Fixture tokens are random (distinct per line, entropy like real lockfile
SRI); detect-secrets deduplicates identical values within one file, so a
single reused token would not yield two findings.
"""
import base64
import json
from pathlib import Path
import secrets
import subprocess

import pytest

REPO = Path(__file__).resolve().parents[2]
DS = REPO / 'tools/ci/secrets_gate.sh'

AWS_DOC_EXAMPLE = 'wJalr' + 'XUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY'


def random_sri():
    return 'sha512-' + base64.b64encode(secrets.token_bytes(64)).decode('ascii')


def git(root, *args):
    subprocess.run(['git', *args], cwd=root, check=True, capture_output=True)


def run(root):
    return subprocess.run(['bash', str(DS), str(root)], cwd=root,
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


def add(root, name, lines):
    target = root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('\n'.join(lines) + '\n')
    git(root, 'add', '.')


def test_flow_form_recognized_green_baseline_unchanged(clean):
    add(clean, 'pnpm-lock.yaml', ['packages:', '  /a/1.0.0:',
        f'    resolution: {{integrity: {random_sri()}}}',
        '  /b/2.0.0:',
        f'    resolution: {{integrity: {random_sri()}}}'])
    before = (clean / '.secrets.baseline').read_bytes()
    proc = run(clean)
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert report['new_findings'] == 0
    assert report['recognized_sri'] == 2
    assert {r['recognition'] for r in report['recognized']} == {'sha512_sri_integrity_field'}
    assert {r['path'] for r in report['recognized']} == {'pnpm-lock.yaml'}
    assert {r['line'] for r in report['recognized']} == {3, 5}
    assert (clean / '.secrets.baseline').read_bytes() == before


def test_block_form_recognized_green(clean):
    add(clean, 'pnpm-lock.yaml', ['packages:', '  /a/1.0.0:', '    resolution:',
        f'      integrity: {random_sri()}'])
    proc = run(clean)
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert report['new_findings'] == 0 and report['recognized_sri'] == 1


def test_recognition_scoped_by_structure_not_path(clean):
    # recognition keys on the structured field, not the lockfile name; the
    # finding itself still comes from the detector (which scans .yaml here)
    add(clean, 'docs/pins.yaml', [f'resolution: {{integrity: {random_sri()}}}'])
    proc = run(clean)
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert report['new_findings'] == 0 and report['recognized_sri'] == 1
    assert report['recognized'][0]['path'] == 'docs/pins.yaml'


def test_canary_same_lockfile_other_field_red(clean):
    # canary sits in another field of the same, still-valid lockfile document
    add(clean, 'pnpm-lock.yaml', ['packages:', '  /a/1.0.0:',
        f'    resolution: {{integrity: {random_sri()}}}',
        '  /evil/1.0.0:',
        f'    password: "{AWS_DOC_EXAMPLE}"'])
    before = (clean / '.secrets.baseline').read_bytes()
    proc = run(clean)
    assert proc.returncode == 1, 'canary in non-integrity field must stay refused'
    report = json.loads(proc.stdout)
    assert report['recognized_sri'] == 1
    assert report['new_findings'] >= 1
    assert any(f['path'] == 'pnpm-lock.yaml' and f['line'] == 5 for f in report['findings'])
    assert AWS_DOC_EXAMPLE not in proc.stdout + proc.stderr
    assert (clean / '.secrets.baseline').read_bytes() == before


def test_canary_other_file_red(clean):
    add(clean, 'pnpm-lock.yaml', ['packages:', '  /a/1.0.0:',
        f'    resolution: {{integrity: {random_sri()}}}'])
    add(clean, 'second.py', [f'aws_secret_access_key = "{AWS_DOC_EXAMPLE}"'])
    proc = run(clean)
    assert proc.returncode == 1
    report = json.loads(proc.stdout)
    assert report['recognized_sri'] == 1
    assert any(f['path'] == 'second.py' for f in report['findings'])


def test_plain_high_entropy_string_not_recognized(clean):
    payload = base64.b64encode(secrets.token_bytes(64)).decode('ascii')
    add(clean, 'config.py', [f'token = "{payload}"'])
    proc = run(clean)
    assert proc.returncode == 1
    report = json.loads(proc.stdout)
    assert report['recognized_sri'] == 0 and report['new_findings'] >= 1


def test_same_value_mixed_use_sri_first_red(clean):
    # detector dedups the identical value to its first (structured) line;
    # recognition must not exempt the other-field use of the same value
    token = random_sri()
    add(clean, 'pnpm-lock.yaml', ['packages:', '  /a/1.0.0:',
        f'    resolution: {{integrity: {token}}}',
        f'    other_payload: {token}'])
    proc = run(clean)
    assert proc.returncode == 1, 'mixed-use value must stay refused'
    report = json.loads(proc.stdout)
    assert report['recognized_sri'] == 0, 'SRI-first dedup must not exempt other-field use'
    assert any(f['path'] == 'pnpm-lock.yaml' for f in report['findings'])
    assert token not in proc.stdout + proc.stderr


def test_same_value_mixed_use_other_field_first_red(clean):
    token = random_sri()
    add(clean, 'pnpm-lock.yaml', ['packages:',
        f'  other_payload: {token}',
        '  /a/1.0.0:',
        f'    resolution: {{integrity: {token}}}'])
    proc = run(clean)
    assert proc.returncode == 1
    report = json.loads(proc.stdout)
    assert report['recognized_sri'] == 0
    assert any(f['path'] == 'pnpm-lock.yaml' for f in report['findings'])


def test_same_value_all_structured_positions_green(clean):
    # pure duplicate SRI positions of one value remain adjudicated (dedup
    # collapses them to one finding; every occurrence is structured)
    token = random_sri()
    add(clean, 'pnpm-lock.yaml', ['packages:', '  /a/1.0.0:',
        f'    resolution: {{integrity: {token}}}',
        '  /b/2.0.0:',
        f'    resolution: {{integrity: {token}}}'])
    proc = run(clean)
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert report['new_findings'] == 0 and report['recognized_sri'] == 1


def escaped_token():
    while True:
        token = random_sri()
        if '5' in token:
            # YAML double-quoted \\u0035 escape decodes back to the same '5'
            return token, token.replace('5', r'\u0035', 1)


def test_escaped_same_value_sri_first_red(clean):
    import yaml
    token, escaped = escaped_token()
    add(clean, 'pnpm-lock.yaml', ['packages:', '  /a/1.0.0:',
        f'    resolution: {{integrity: {token}}}',
        '  /evil/1.0.0:',
        f'    other_payload: "{escaped}"'])
    # proof of decoded identity: the detector dedups on this equality
    doc = yaml.safe_load((clean / 'pnpm-lock.yaml').read_text())
    packages = doc['packages']
    assert packages['/a/1.0.0']['resolution']['integrity'] \
        == packages['/evil/1.0.0']['other_payload']
    assert token not in (clean / 'pnpm-lock.yaml').read_text().splitlines()[-1]
    proc = run(clean)
    assert proc.returncode == 1, 'escaped same-value mixed use must stay refused'
    report = json.loads(proc.stdout)
    assert report['recognized_sri'] == 0
    assert any(f['path'] == 'pnpm-lock.yaml' for f in report['findings']), \
        'detector must still surface the value'
    assert token not in proc.stdout + proc.stderr


def test_escaped_same_value_other_field_first_red(clean):
    token, escaped = escaped_token()
    add(clean, 'pnpm-lock.yaml', ['packages:',
        f'  early_payload: "{escaped}"',
        '  /a/1.0.0:',
        f'    resolution: {{integrity: {token}}}'])
    proc = run(clean)
    assert proc.returncode == 1
    report = json.loads(proc.stdout)
    assert report['recognized_sri'] == 0
    assert any(f['path'] == 'pnpm-lock.yaml' for f in report['findings'])


MALFORMED_CASES = ('extra_flow_field', 'missing_padding', 'quoted_value',
                   'trailing_comment', 'wrong_algorithm', 'wrong_key',
                   'wrong_payload_length')


def malformed_line(case):
    if case == 'wrong_algorithm':
        token = 'sha256-' + base64.b64encode(secrets.token_bytes(32)).decode('ascii')
    elif case == 'wrong_payload_length':
        token = 'sha512-' + base64.b64encode(secrets.token_bytes(32)).decode('ascii')
    elif case == 'missing_padding':
        token = random_sri().rstrip('=')
        return f'    resolution: {{integrity: {token}}}'
    else:
        token = random_sri()
    if case == 'extra_flow_field':
        return f'    resolution: {{integrity: {random_sri()}, tarball: https://registry.example.invalid/pkg.tgz}}'
    if case == 'wrong_key':
        return f'    resolution: {{integrities: {random_sri()}}}'
    if case == 'quoted_value':
        return f'    resolution: {{integrity: "{random_sri()}"}}'
    if case == 'trailing_comment':
        return f'    resolution: {{integrity: {random_sri()}}} # pinned'
    if case in ('wrong_algorithm', 'wrong_payload_length'):
        return f'    resolution: {{integrity: {token}}}'
    raise ValueError(case)


@pytest.mark.parametrize('case', MALFORMED_CASES)
def test_malformed_sri_stays_refused(clean, case):
    add(clean, 'pnpm-lock.yaml', ['packages:', '  /a/1.0.0:', malformed_line(case)])
    proc = run(clean)
    assert proc.returncode == 1, f'{case} must not be recognized as adjudicated SRI'
    report = json.loads(proc.stdout)
    assert report['recognized_sri'] == 0, case
    assert any(f['path'] == 'pnpm-lock.yaml' for f in report['findings']), case
