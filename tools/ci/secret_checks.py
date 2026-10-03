"""Pinned offline detector and tracked-file checks; never write baseline."""
import base64
import binascii
import fnmatch
import hashlib
import importlib.metadata
import json
import logging
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

class Refusal(Exception):
    def __init__(self, code, category):
        self.code, self.category = code, category

class DetectorFault(logging.Handler):
    def emit(self, record):
        if record.levelno >= logging.WARNING:
            raise Refusal(3, 'DETECTOR_EXECUTION_FAILED')

# CTO F-01 adjudication (2026-10-03): structured SHA-512 SRI integrity fields
# are non-credential content digests. Recognition is limited to the exact
# structured field forms below: the FULL line must be exactly one integrity
# field expression and the token must be a canonical SHA-512 SRI (base64
# decodes to 64 bytes and re-encodes byte-identically). It is never applied
# to whole files/directories, never generalized to high-entropy strings, and
# never applied to non-Base64 findings. Any doubt leaves the finding refused.
SRI_FIELD_PATTERNS = (
    re.compile(r'^\s*resolution:\s*\{integrity:\s*(sha512-[A-Za-z0-9+/]+=*)\},?\s*$'),
    re.compile(r'^\s*integrity:\s*(sha512-[A-Za-z0-9+/]+=*)\s*,?\s*$'),
)

def _is_legal_sha512_sri(token):
    try:
        decoded = base64.b64decode(token[len('sha512-'):], validate=True)
    except (binascii.Error, ValueError):
        return False
    if len(decoded) != 64:
        return False
    return 'sha512-' + base64.b64encode(decoded).decode('ascii') == token

def _all_decoded_uses_are_integrity(path, token, cache):
    # The detector parses YAML scalars and deduplicates on the DECODED value,
    # so a same-value use written with YAML escapes is invisible to raw-text
    # search. Uses are therefore enumerated on the parsed document: every
    # decoded scalar (or key) equal to or containing the token must be the
    # exact value of a sole-key 'integrity' mapping. Parse failure, ambiguity
    # or any non-integrity use keeps the finding refused.
    if path in cache:
        return cache[path]
    try:
        import yaml
        with open(path, encoding='utf-8') as stream:
            documents = list(yaml.safe_load_all(stream))
    except Exception:
        cache[path] = False
        return False
    state = [False, True]  # approved position found; no non-integrity use

    def collect(node):
        if isinstance(node, dict):
            if len(node) == 1 and 'integrity' in node and node['integrity'] == token:
                state[0] = True
                return
            for key, value in node.items():
                if isinstance(key, str) and (key == token or token in key):
                    state[1] = False
                collect(value)
        elif isinstance(node, list):
            for item in node:
                collect(item)
        elif isinstance(node, str):
            if node == token or token in node:
                state[1] = False

    for document in documents:
        collect(document)
    cache[path] = state[0] and state[1]
    return cache[path]

def sri_recognition(path, line_number, cache):
    try:
        lines = Path(path).read_text(encoding='utf-8').splitlines()
        line = lines[line_number - 1]
    except (OSError, UnicodeError, IndexError):
        raise Refusal(3, 'SRI_RECOGNITION_READ_FAILED') from None
    token = None
    for pattern in SRI_FIELD_PATTERNS:
        match = pattern.match(line)
        if match and _is_legal_sha512_sri(match.group(1)):
            token = match.group(1)
            break
    if token is None:
        return None
    # Two layers, both fail-closed: (1) the reported (deduped first) line is
    # itself the canonical structured field; (2) every decoded use of the
    # value in this file is an approved integrity position.
    if not _all_decoded_uses_are_integrity(path, token, cache):
        return None
    return 'sha512_sri_integrity_field'

def tracked():
    try:
        result = subprocess.run(['git', 'ls-files', '-z'], capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        raise Refusal(5, 'TRACKED_ENUMERATION_FAILED') from None
    if not result.stdout.endswith(b'\0'):
        raise Refusal(5, 'TRACKED_SET_EMPTY_OR_INVALID')
    paths = [os.fsdecode(p) for p in result.stdout.split(b'\0')[:-1]]
    for name in paths:
        try:
            if Path(name).is_absolute() or '..' in Path(name).parts:
                raise ValueError()
            if not stat.S_ISREG(Path(name).lstat().st_mode):
                raise ValueError()
            with open(name, 'rb') as stream:
                stream.read(1)
        except (OSError, ValueError):
            raise Refusal(5, 'TRACKED_INPUT_UNREADABLE_OR_NONREGULAR') from None
    return paths

def detector(paths):
    try:
        if importlib.metadata.version('detect-secrets') != '1.5.0':
            raise Refusal(3, 'DETECTOR_VERSION_MISMATCH')
        from detect_secrets.core.secrets_collection import SecretsCollection
        from detect_secrets.settings import transient_settings
        from detect_secrets.core.log import log
    except (ImportError, importlib.metadata.PackageNotFoundError):
        raise Refusal(3, 'DETECTOR_UNAVAILABLE') from None
    baseline = Path('.secrets.baseline')
    try:
        raw = baseline.read_bytes()
        doc = json.loads(raw)
        if doc['version'] != '1.5.0' or not isinstance(doc['results'], dict) or not doc['plugins_used']:
            raise ValueError()
        known = SecretsCollection.load_from_baseline(doc)
        config = dict(doc)
        # Offline detection is stricter: no suppression via live secret checks.
        config['filters_used'] = [f for f in doc.get('filters_used', [])
            if f['path'] != 'detect_secrets.filters.common.is_ignored_due_to_verification_policies']
        if any(not f['path'].startswith('detect_secrets.filters.') for f in config['filters_used']):
            raise ValueError()
    except (OSError, ValueError, KeyError, TypeError):
        raise Refusal(4, 'BASELINE_INVALID') from None
    fault = DetectorFault()
    old_handlers, old_level = log.handlers[:], log.level
    log.handlers = [fault]
    log.setLevel(logging.WARNING)
    try:
        with transient_settings(config):
            observed = SecretsCollection()
            for name in paths:
                if name != '.secrets.baseline':
                    observed.scan_file(name)
            new = observed - known
            recognized, findings = [], []
            semantic_cache = {}
            for name, secret in new:
                entry = {'path': name, 'line': secret.line_number, 'type': secret.type}
                label = sri_recognition(name, secret.line_number, semantic_cache) \
                    if secret.type == 'Base64 High Entropy String' else None
                (recognized if label else findings).append(
                    dict(entry, recognition=label) if label else entry)
            known_count = sum(1 for _ in observed) - len(findings) - len(recognized)
    except Exception:
        raise Refusal(3, 'DETECTOR_EXECUTION_FAILED') from None
    finally:
        log.handlers, log.level = old_handlers, old_level
    if baseline.read_bytes() != raw:
        raise Refusal(6, 'BASELINE_CHANGED')
    return {'mode': 'detector', 'tracked_files': len(paths),
        'baseline_sha256': hashlib.sha256(raw).hexdigest(), 'baseline_unchanged': True,
        'tool_version': '1.5.0', 'network_verification': False,
        'known_findings': known_count, 'new_findings': len(findings), 'findings': findings,
        'recognized_sri': len(recognized), 'recognized': recognized}

def hardcoded(paths):
    password = re.compile(r'''(password|passwd|pwd|secret|token|api_key|apikey)\s*=\s*["'][^"']{8,}["']''')
    aws = re.compile(r'(AKIA[0-9A-Z]{16}|' + 'AWS_ACCESS_' + 'KEY_ID|' + 'AWS_SECRET_' + 'ACCESS_KEY)')
    findings = []
    for name in paths:
        parts, base = Path(name).parts, Path(name).name
        if (fnmatch.fnmatch(base, '*.pem') or fnmatch.fnmatch(base, '*.key') or base == 'id_rsa'):
            if 'test' not in name and 'example' not in name:
                findings.append({'path': name, 'line': 0, 'type': 'PRIVATE_KEY_FILENAME'})
        if any(p in ('node_modules', 'venv', '.venv') for p in parts):
            continue
        check_password = any(fnmatch.fnmatch(base, g) for g in ('*.py', '*.js', '*.ts', '*.java'))
        check_password = check_password and 'tests' not in parts and 'dist' not in parts
        check_aws = any(fnmatch.fnmatch(base, g) for g in ('*.py', '*.js', '*.ts', '*.env*'))
        if not (check_password or check_aws):
            continue
        try:
            lines = Path(name).read_text(encoding='utf-8').splitlines()
        except (OSError, UnicodeError):
            raise Refusal(3, 'HARDCODED_INPUT_READ_FAILED') from None
        for line, content in enumerate(lines, 1):
            if check_password and password.search(content):
                findings.append({'path': name, 'line': line, 'type': 'HARDCODED_PASSWORD'})
            if check_aws and aws.search(content):
                findings.append({'path': name, 'line': line, 'type': 'AWS_PATTERN'})
    return {'mode': 'hardcoded', 'tracked_files': len(paths),
            'new_findings': len(findings), 'findings': findings}

def main():
    try:
        if len(sys.argv) not in (2, 3) or sys.argv[1] not in ('detector', 'hardcoded'):
            raise Refusal(2, 'USAGE')
        os.chdir(sys.argv[2] if len(sys.argv) == 3 else '.')
        paths = tracked()
        report = detector(paths) if sys.argv[1] == 'detector' else hardcoded(paths)
        print(json.dumps(report, ensure_ascii=True, sort_keys=True))
        return 1 if report['new_findings'] else 0
    except Refusal as exc:
        print(json.dumps({'error': exc.category}), file=sys.stderr)
        return exc.code
    except Exception:
        print('{"error":"CHECK_EXECUTION_FAILED"}', file=sys.stderr)
        return 3

if __name__ == '__main__':
    raise SystemExit(main())
