"""R6 contract: precise native baseline audit increments through the real gate.

Controls (CTO R6 §2.A / directive §5.2): an audited (path,type,hash) entry
suppresses exactly that observation; the same file+position with a NEW value
must be refused again; the same VALUE in another file must not inherit the
exemption; a new value at the audited position must not inherit it; the
baseline bytes stay identical across scans.
"""
import hashlib
import json
from pathlib import Path
import secrets
import subprocess

import pytest

REPO = Path(__file__).resolve().parents[2]
DS = REPO / 'tools/ci/secrets_gate.sh'


def git(root, *args):
    subprocess.run(['git', *args], cwd=root, check=True, capture_output=True)


def run(root):
    return subprocess.run(['bash', str(DS), str(root)], cwd=root,
                          capture_output=True, text=True, timeout=180)


@pytest.fixture
def fixture(tmp_path):
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


def add_audit_entry(root, path, line, ftype, value):
    doc = json.loads((root / '.secrets.baseline').read_text())
    entry = {'type': ftype, 'filename': path.replace('/', '\\'),
             'hashed_secret': hashlib.sha1(value.encode()).hexdigest(),
             'is_verified': False, 'line_number': line}
    doc['results'].setdefault(path.replace('/', '\\'), []).append(entry)
    (root / '.secrets.baseline').write_text(json.dumps(doc, indent=2) + '\n')
    git(root, 'add', '.')


CANARY = 'c91-synthetic-lowentropy-token'  # Secret Keyword only, no entropy type


def observed_types(root, path):
    proc = run(root)
    assert proc.returncode == 1
    report = json.loads(proc.stdout)
    return sorted(f['type'] for f in report['findings'] if f['path'] == path)


def test_audited_observation_suppressed_new_canary_refused(fixture):
    (fixture / 'ci_env.py').write_text(f'password = "{CANARY}"\n')
    git(fixture, 'add', '.')
    types = observed_types(fixture, 'ci_env.py')
    assert types == ['Secret Keyword'], types
    add_audit_entry(fixture, 'ci_env.py', 1, 'Secret Keyword', CANARY)
    before = (fixture / '.secrets.baseline').read_bytes()
    proc = run(fixture)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)['new_findings'] == 0
    assert (fixture / '.secrets.baseline').read_bytes() == before
    # same file, same position, NEW canary: must be refused again
    fresh = 'c91-fresh-synthetic-lowentropy-token'
    (fixture / 'ci_env.py').write_text(f'password = "{fresh}"\n')
    git(fixture, 'add', '.')
    proc = run(fixture)
    assert proc.returncode == 1, 'new value at audited position must not inherit'
    assert any(f['path'] == 'ci_env.py' for f in json.loads(proc.stdout)['findings'])


def test_same_value_in_other_file_not_exempt(fixture):
    (fixture / 'one.py').write_text(f'password = "{CANARY}"\n')
    git(fixture, 'add', '.')
    add_audit_entry(fixture, 'one.py', 1, 'Secret Keyword', CANARY)
    proc = run(fixture)
    assert proc.returncode == 0
    (fixture / 'two.py').write_text(f'password = "{CANARY}"\n')
    git(fixture, 'add', '.')
    proc = run(fixture)
    assert proc.returncode == 1, 'same value in another file must not inherit'
    assert any(f['path'] == 'two.py' for f in json.loads(proc.stdout)['findings'])


def test_wrong_hash_does_not_suppress(fixture):
    (fixture / 'ci_env.py').write_text(f'password = "{CANARY}"\n')
    git(fixture, 'add', '.')
    add_audit_entry(fixture, 'ci_env.py', 1, 'Secret Keyword',
                    'not-the-value-lowentropy')
    proc = run(fixture)
    assert proc.returncode == 1, 'audit entry must match the exact detector hash'


def test_candidate_baseline_native_audit_markers():
    """The 48 delivered increments carry the native non-credential audit
    verdict (is_secret=false), and every pre-existing entry is preserved
    byte-for-byte against the BASE baseline blob."""
    import subprocess
    base_bytes = subprocess.run(
        ['git', '-C', str(REPO), 'show',
         'a1feb59324ab98769e655bc2a708f5ef042e4ad1:.secrets.baseline'],
        check=True, capture_output=True).stdout
    base_doc = json.loads(base_bytes)
    cur_doc = json.loads((REPO / '.secrets.baseline').read_text())
    marked = [e for v in cur_doc['results'].values() for e in v
              if e.get('is_secret') is False]
    assert len(marked) == 48, len(marked)
    identities = {(e['filename'], e['type'], e['hashed_secret'], e['line_number'])
                  for e in marked}
    assert len(identities) == 48
    for key, entries in base_doc['results'].items():
        current = cur_doc['results'].get(key, [])
        for entry in entries:
            assert entry in current, ('OLD ENTRY CHANGED', key, entry)
    assert cur_doc['plugins_used'] == base_doc['plugins_used']
    assert cur_doc['filters_used'] == base_doc['filters_used']
