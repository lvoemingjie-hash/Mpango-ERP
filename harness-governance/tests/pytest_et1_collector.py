"""HE2-ET1-R1 runner-owned pytest plugin: child-process proof collector.

Loaded ONLY by the authority runner as `pytest -p tests.pytest_et1_collector
--collect-only <target>` with cwd=harness-governance (the runner spawns the
child from an argv list, never a shell string).

Division of labor (forced fix 3):
  pytest_sessionstart       re-verify, INSIDE the real child process:
                            role (live PG), TEST_DATABASE_URL presence,
                            temp-DB capability flag, runner nonce,
                            candidate / profile / manifest SHA bindings.
                            No item inspection (collection has not run).
  pytest_collection_finish  session.items is populated; recompute the live
                            candidate / profile / manifest SHAs, compare
                            against the runner-provided values, and write
                            the collect proof with the REAL node IDs.

Every artifact carries presence/labels only — never environment values.
The proof schema marker is checked runner-side, so a proof not written by
THIS plugin can never authorize a launch.
"""

import hashlib
import hmac
import json
import os
import socket
import subprocess
import sys
import urllib.parse
from pathlib import Path

import pytest

PLUGIN_PROOF_SCHEMA = "harness-governance/pytest_et1_collector/2"
SESSIONSTART_SCHEMA = "harness-governance/pytest_et1_collector_sessionstart/2"

# R2-R1/R2-R2: the child independently loads the SHARED stdlib Redis
# authority module from the exact canonical resolved path — never from a
# sys.modules cache — and binds its RAW-BYTE SHA-256 against the runner's
# ORIGINAL digest passed via the environment. No protocol code is duplicated
# here. Only the sentinel endpoint constant stays local so tests can point
# the probe at a controlled listener.
SENTINEL_PROBE_ENDPOINT = ("127.0.0.1", 26379)

# Fixed child-label translation: the shared module's connect failure
# category is published as the child's historical "unreachable" label.
_CHILD_LABELS = {"connect_failed": "unreachable"}

REDIS_MODULE_KEY = "et1_redis_authority"


def _redis_module_canonical_path() -> Path:
    """The child's own resolution of the shared module location; it must
    land on the exact same file the runner binds."""
    return (Path(__file__).resolve().parents[1] / "validator" / "redis_authority.py").resolve()


def _module_origin_is_canonical(module, canonical: Path) -> bool:
    if module is None:
        return False
    spec = getattr(module, "__spec__", None)
    origin = getattr(spec, "origin", None) if spec is not None else None
    file_attr = getattr(module, "__file__", None)
    for candidate in (origin, file_attr):
        if not candidate or not isinstance(candidate, str):
            return False
        try:
            if Path(candidate).resolve() != canonical:
                return False
        except (OSError, ValueError):
            return False
    return True


def _load_redis_authority():
    """Child-side module-origin binding bootstrap. A preloaded entry under
    the fixed key is NEVER returned or trusted: a foreign origin is tamper
    evidence (redis_module:preload_detected); the module is always freshly
    executed from the canonical raw bytes and its origin/PATH re-verified.
    Returns (module, tampered). Raises _RedisModuleBindingError on origin
    or spec failures (fixed categories, no paths)."""
    import importlib.util

    class _RedisModuleBindingError(Exception):
        def __init__(self, category):
            super().__init__(f"redis_module:{category}")
            self.category = category

    canonical = _redis_module_canonical_path()
    preloaded = sys.modules.get(REDIS_MODULE_KEY)
    tampered = preloaded is not None and not _module_origin_is_canonical(
        preloaded, canonical
    )
    sys.modules.pop(REDIS_MODULE_KEY, None)  # the cache is never reused
    try:
        spec = importlib.util.spec_from_file_location(REDIS_MODULE_KEY, str(canonical))
    except (ValueError, OSError):
        raise _RedisModuleBindingError("origin_untrusted") from None
    if spec is None or getattr(spec, "loader", None) is None:
        raise _RedisModuleBindingError("origin_untrusted")
    module = importlib.util.module_from_spec(spec)
    sys.modules[REDIS_MODULE_KEY] = module
    try:
        spec.loader.exec_module(module)
    except _RedisModuleBindingError:
        raise
    except Exception:
        raise _RedisModuleBindingError("origin_untrusted") from None
    if not _module_origin_is_canonical(module, canonical):
        raise _RedisModuleBindingError("origin_untrusted")
    return module, tampered


def _redis_module_binding(env) -> tuple:
    """Independent child-side binding: load the shared module fresh from
    the canonical path, recompute the RAW-BYTE SHA-256, and compare it
    against the runner's ORIGINAL digest from the environment (never a
    self-comparison). Returns (problems, recomputed_digest)."""
    import hashlib

    problems: list = []
    try:
        _module, tampered = _load_redis_authority()
    except _RedisModuleBindingError as err:
        problems.append(f"redis_module:{err.category}")
        if err.category == "origin_untrusted":
            problems.append("redis_module:preload_detected")
        return problems, ""
    if tampered:
        problems.append("redis_module:preload_detected")
    canonical = _redis_module_canonical_path()
    try:
        recomputed = hashlib.sha256(canonical.read_bytes()).hexdigest()
    except OSError:
        problems.append("redis_module:origin_untrusted")
        return problems, ""
    runner_original = env.get("ET1_RUNNER_REDIS_MODULE_SHA", "") or ""
    if not runner_original:
        problems.append("redis_module:digest_missing")
    elif recomputed != runner_original:
        problems.append("redis_module:bytes_drift")
    return problems, recomputed


BACKEND_ENV_KEY = "et1_backend_env_authority"


def _backend_env_canonical_path() -> Path:
    return (Path(__file__).resolve().parents[1] / "validator" / "backend_env_authority.py").resolve()


def _module_origin_is_canonical_be(module, canonical: Path) -> bool:
    if module is None:
        return False
    spec = getattr(module, "__spec__", None)
    origin = getattr(spec, "origin", None) if spec is not None else None
    file_attr = getattr(module, "__file__", None)
    for candidate in (origin, file_attr):
        if not candidate or not isinstance(candidate, str):
            return False
        try:
            if Path(candidate).resolve() != canonical:
                return False
        except (OSError, ValueError):
            return False
    return True


class _BackendEnvBindingError(Exception):
    def __init__(self, category):
        super().__init__(f"backend_env_module:{category}")
        self.category = category


def _load_backend_env_module():
    import importlib.util

    canonical = _backend_env_canonical_path()
    preloaded = sys.modules.get(BACKEND_ENV_KEY)
    tampered = preloaded is not None and not _module_origin_is_canonical_be(
        preloaded, canonical)
    sys.modules.pop(BACKEND_ENV_KEY, None)
    try:
        spec = importlib.util.spec_from_file_location(BACKEND_ENV_KEY, str(canonical))
    except (ValueError, OSError):
        raise _BackendEnvBindingError("origin_untrusted") from None
    if spec is None or getattr(spec, "loader", None) is None:
        raise _BackendEnvBindingError("origin_untrusted")
    module = importlib.util.module_from_spec(spec)
    sys.modules[BACKEND_ENV_KEY] = module
    try:
        spec.loader.exec_module(module)
    except _BackendEnvBindingError:
        raise
    except Exception:
        raise _BackendEnvBindingError("origin_untrusted") from None
    if not _module_origin_is_canonical_be(module, canonical):
        raise _BackendEnvBindingError("origin_untrusted")
    return module, tampered


def _backend_env_recheck_problems(env) -> tuple:
    import hashlib

    try:
        module, tampered = _load_backend_env_module()
    except _BackendEnvBindingError as err:
        return ([f"benv:{err.category}", "benv:preload_detected"], "")
    problems: list = []
    if tampered:
        problems.append("benv:preload_detected")
    try:
        facts = module.backend_env_facts(
            url=env.get("TEST_DATABASE_URL", ""),
            mpango_env=env.get("MPANGO_ENV", ""),
            allowed_ports_raw=env.get("MPANGO_TEMP_DB_ALLOWED_PORTS", ""),
            allowed_hosts_raw=env.get("MPANGO_TEMP_DB_ALLOWED_HOSTS", ""),
            authority_cwd=(Path(__file__).resolve().parents[2] / "backend").resolve(),
        )
    except module.BackendEnvAuthorityError as err:
        problems.append(f"benv:{err.category}")
        return problems, ""
    digest_input = "|".join([
        facts["mpango_env"], facts["db_name"], str(facts["port"]),
        facts["host"], facts["allowed_ports"], facts["allowed_hosts"],
        facts["authority_cwd"],
    ])
    recomputed = module.binding_digest(digest_input)
    runner_original = env.get("ET1_RUNNER_TEMPDB_BINDING_SHA", "") or ""
    if not runner_original:
        problems.append("benv:digest_missing")
    elif recomputed != runner_original:
        problems.append("benv:digest_mismatch")
    return problems, recomputed


def _alembic_recheck_problems(env) -> tuple:
    try:
        module, _tampered = _load_backend_env_module()
    except _BackendEnvBindingError as err:
        return [f"alembic:{err.category}"], ""
    expected = env.get("ET1_RUNNER_ALEMBIC_EXPECTED", "") or ""
    parent = env.get("ET1_RUNNER_ALEMBIC_PARENT", "") or None
    if not expected:
        return ["alembic:digest_missing"], ""
    try:
        facts = module.alembic_verify(
            module.canonical_backend_dir(__file__) / "alembic" / "versions",
            expected, parent)
    except module.BackendEnvAuthorityError as err:
        return [f"alembic:{err.category}"], ""
    return [], facts["alembic_head"]


def _manifest_transport_problems(env) -> tuple:
    """R4 CHILD-side bounded manifest transport verification.

    The frozen node manifest never travels in a single argv/env string. The
    runner writes ONE canonical transport file (UTF-8, sorted, unique,
    LF-terminated lines) and binds its raw-byte SHA-256. The child loads the
    canonical bytes itself and re-derives the digest: missing file,
    substituted file, byte drift, digest mismatch, duplicate node,
    non-canonical order, blank lines, or a missing trailing newline
    (truncation) each fail closed with a fixed `manifest_transport:` label.
    Returns (problems, (nodes, digest)); nodes is empty on any problem.
    """
    path = (env.get("ET1_RUNNER_MANIFEST_TRANSPORT_PATH", "") or "").strip()
    expected_digest = (env.get("ET1_RUNNER_MANIFEST_TRANSPORT_DIGEST", "") or "").strip()
    if not path:
        return ["manifest_transport:path_missing"], ([], "")
    if len(expected_digest) != 64:
        return ["manifest_transport:digest_missing"], ([], "")
    try:
        raw = Path(path).read_bytes()
    except OSError:
        return ["manifest_transport:unreadable"], ([], "")
    digest = hashlib.sha256(raw).hexdigest()
    if not hmac.compare_digest(digest, expected_digest):
        return ["manifest_transport:digest_mismatch"], ([], "")
    if not raw.endswith(b"\n"):
        return ["manifest_transport:non_canonical_eof"], ([], "")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return ["manifest_transport:undecodable"], ([], "")
    lines = text.split("\n")[:-1]
    if any(not line.strip() for line in lines):
        return ["manifest_transport:blank_line"], ([], "")
    if len(lines) != len(set(lines)):
        return ["manifest_transport:duplicate_nodes"], ([], "")
    if lines != sorted(lines):
        return ["manifest_transport:non_canonical_order"], ([], "")
    return [], (lines, digest)


def _redis_recheck_problems(env) -> list:
    """R2-R1 CHILD-side live Redis recheck via the SHARED authority module.

    Connects the PW1R3_TEST_REDIS_URL's OWN host/port and proves
    PING==PONG / SELECT 15==OK / DBSIZE==0 plus sentinel-26379
    unreachability. Returns fixed `redis:` labels only — never hosts,
    ports, passwords, or any environment value. An empty list = recheck
    passed. Redis disappearing after the runner preflight fails the child
    closed here: no proof, no launch.
    """
    url = (env.get("PW1R3_TEST_REDIS_URL", "") or "").strip()
    if not url:
        return ["redis:url_absent"]
    try:
        module, tampered = _load_redis_authority()
    except _RedisModuleBindingError as err:
        return [f"redis_module:{err.category}"]
    if tampered:
        return ["redis_module:preload_detected"]
    try:
        module.eval_redis(url, SENTINEL_PROBE_ENDPOINT)
    except module.RedisAuthorityError as err:
        return [f"redis:{_CHILD_LABELS.get(err.category, err.category)}"]
    return []


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git_head(repo_root: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True, text=True, shell=False,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def sessionstart_gate(env) -> dict:
    """Re-verify the environment bindings inside the CHILD process.

    Returns a sanitized result dict {ok, problems, role}. On any missing or
    contradictory binding the gate fails closed (ok=False) and the hook
    exits the child before collection — a child that cannot re-prove the
    runner's bindings never produces an acceptable proof.
    """
    problems = []

    def need(condition, label):
        if not condition:
            problems.append(label)

    proof_out = env.get("ET1_RUNNER_PROOF_OUT", "")
    need(bool(proof_out.strip()), "proof_out:missing")
    nonce = env.get("ET1_RUNNER_NONCE", "")
    need(len(nonce) >= 16, "nonce:missing_or_short")
    candidate = env.get("ET1_RUNNER_CANDIDATE_SHA", "")
    profile_sha = env.get("ET1_RUNNER_PROFILE_SHA", "")
    manifest_sha = env.get("ET1_RUNNER_MANIFEST_SHA", "")
    need(len(candidate) in (40, 64), "candidate_sha:missing")  # sha1 / sha256 git
    need(len(profile_sha) == 64, "profile_sha:missing")
    need(len(manifest_sha) == 64, "manifest_sha:missing")
    need(bool(env.get("ET1_RUNNER_PROFILE_PATH", "")), "profile_path:missing")
    need(bool(env.get("ET1_RUNNER_MANIFEST_PATH", "")), "manifest_path:missing")
    need(bool(env.get("ET1_RUNNER_REPO_ROOT", "")), "repo_root:missing")

    # R4: the frozen node manifest travels ONLY through the bounded,
    # digest-bound transport file — never in a single argv/env string.
    transport_problems, _transport_loaded = _manifest_transport_problems(env)
    problems.extend(transport_problems)

    db_url = env.get("TEST_DATABASE_URL", "")
    need(bool(db_url.strip()), "test_db_url:missing")
    allow_flag = env.get("MPANGO_ALLOW_TEMP_DB_CREATE", "")
    need(allow_flag == "1", "temp_db_capability:missing")

    # R2: the CHILD re-verifies the live Redis authority (DB15, PING/SELECT/
    # DBSIZE, sentinel unreachability). Redis disappearing after the runner
    # preflight fails the child closed here — no proof, no launch.
    problems.extend(_redis_recheck_problems(env))

    # R2-R2: independent module-origin + raw-byte binding. The child
    # recomputes the shared module's digest from the canonical path and
    # compares it with the runner's ORIGINAL (never self-compared); any
    # mismatch means the module moved between preflight and the child.
    module_problems, redis_module_sha = _redis_module_binding(env)
    problems.extend(module_problems)

    # R3: independent backend-CWD / temp-DB re-verification in the child.
    benv_problems, tempdb_binding_sha = _backend_env_recheck_problems(env)
    problems.extend(benv_problems)

    # R3-A1: independent alembic successor verification in the child.
    alembic_problems, alembic_actual = _alembic_recheck_problems(env)
    problems.extend(alembic_problems)

    # LIVE role re-verification in the child: not superuser AND createdb.
    role = {"verified": False, "rolsuper": True, "rolcreatedb": False}
    if db_url.strip():
        try:
            import psycopg

            conn = psycopg.connect(db_url, autocommit=True)
            try:
                row = conn.execute(
                    "select rolsuper, rolcreatedb from pg_roles where rolname = current_user"
                ).fetchone()
                role = {
                    "verified": row is not None,
                    "rolsuper": bool(row[0]) if row else True,
                    "rolcreatedb": bool(row[1]) if row else False,
                }
            finally:
                conn.close()
        except Exception:
            role = {"verified": False, "rolsuper": True, "rolcreatedb": False,
                    "reason": "driver_or_connect_failed"}
    need(role.get("verified") and not role.get("rolsuper") and role.get("rolcreatedb"),
         "role:child_recheck_failed")

    return {
        "ok": not problems,
        "problems": problems,
        "role": role,
        "redis_module_sha": redis_module_sha,
        "redis_module_ok": not module_problems,
        "tempdb_binding_sha": tempdb_binding_sha,
        "tempdb_ok": not benv_problems,
        "alembic_actual_head": alembic_actual,
        "alembic_ok": not alembic_problems,
    }


def _write_sessionstart_proof(path, gate_result, nonce) -> None:
    payload = {
        "schema": SESSIONSTART_SCHEMA,
        "phase": "SESSIONSTART",
        "ok": gate_result["ok"],
        "problems": gate_result["problems"],
        "role": {k: gate_result["role"].get(k) for k in ("verified", "rolsuper", "rolcreatedb")},
        "nonce_chars": len(nonce),
        "redis_module_ok": gate_result.get("redis_module_ok", False),
        "redis_module_sha_chars": len(gate_result.get("redis_module_sha", "")),
        "backend_env_ok": gate_result.get("tempdb_ok", False),
        "tempdb_binding_sha_chars": len(gate_result.get("tempdb_binding_sha", "")),
        "alembic_ok": gate_result.get("alembic_ok", False),
        "alembic_head_chars": len(gate_result.get("alembic_actual_head", "")),
    }
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def pytest_sessionstart(session):
    nonce = os.environ.get("ET1_RUNNER_NONCE", "")
    gate_result = sessionstart_gate(os.environ)
    sessionstart_out = os.environ.get("ET1_RUNNER_SESSIONSTART_OUT", "")
    if sessionstart_out:
        try:
            _write_sessionstart_proof(sessionstart_out, gate_result, nonce)
        except OSError:
            pass
    if not gate_result["ok"]:
        print(
            "ET1-SESSIONSTART FAIL: "
            + json.dumps(gate_result["problems"], sort_keys=True),
            file=sys.stderr,
        )
        pytest.exit("child sessionstart gate failed", 2)


def pytest_collection_finish(session):
    """Items are populated: real node IDs + live SHA re-verification."""
    _module_problems, redis_module_sha = _redis_module_binding(os.environ)
    redis_module_ok = not _module_problems
    _benv_problems, tempdb_binding_sha = _backend_env_recheck_problems(os.environ)
    tempdb_ok = not _benv_problems
    _alembic_problems, alembic_actual = _alembic_recheck_problems(os.environ)
    alembic_ok = not _alembic_problems
    nonce = os.environ.get("ET1_RUNNER_NONCE", "")
    candidate_expected = os.environ.get("ET1_RUNNER_CANDIDATE_SHA", "")
    profile_expected = os.environ.get("ET1_RUNNER_PROFILE_SHA", "")
    manifest_expected = os.environ.get("ET1_RUNNER_MANIFEST_SHA", "")
    transport_problems, transport_loaded = _manifest_transport_problems(os.environ)
    required_nodes = list(transport_loaded[0]) if transport_loaded[0] else []
    transport_digest_seen = transport_loaded[1] if transport_loaded[0] else ""
    proof_out = os.environ.get("ET1_RUNNER_PROOF_OUT", "")
    repo_root = os.environ.get("ET1_RUNNER_REPO_ROOT", "")
    profile_path = os.environ.get("ET1_RUNNER_PROFILE_PATH", "")
    manifest_path = os.environ.get("ET1_RUNNER_MANIFEST_PATH", "")

    # Live recomputation INSIDE the child; compared against runner values.
    candidate_live = _git_head(repo_root) if repo_root else ""
    try:
        profile_live = _sha256_bytes(Path(profile_path).read_bytes()) if profile_path else ""
    except OSError:
        profile_live = ""
    try:
        manifest_live = _sha256_bytes(Path(manifest_path).read_bytes()) if manifest_path else ""
    except OSError:
        manifest_live = ""
    sha_match = {
        "candidate": bool(candidate_live) and candidate_live == candidate_expected,
        "profile": bool(profile_live) and profile_live == profile_expected,
        "manifest": bool(manifest_live) and manifest_live == manifest_expected,
    }

    presence = {
        "TEST_DATABASE_URL": bool(os.environ.get("TEST_DATABASE_URL", "").strip()),
        "MPANGO_ALLOW_TEMP_DB_CREATE": os.environ.get("MPANGO_ALLOW_TEMP_DB_CREATE", "") == "1",
        "nonce_provided": len(nonce) >= 16,
        "sessionstart_gate": "passed",  # reaching this hook implies it
    }
    errors = []
    for key, matched in sha_match.items():
        if not matched:
            errors.append(f"sha_drift:{key}")
    if not redis_module_ok:
        errors.append("redis_module:drift")
    if not tempdb_ok:
        errors.append("backend_env:drift")
    if not alembic_ok:
        errors.append("alembic:drift")
    errors.extend(transport_problems)

    collected = []
    try:
        for item in session.items:
            collected.append(item.nodeid)
    except Exception as exc:
        errors.append(f"collect:node_ids:exception:{type(exc).__name__}")
    if not collected:
        errors.append("collect:no_items")

    db_url = os.environ.get("TEST_DATABASE_URL", "")
    try:
        parsed = urllib.parse.urlsplit(db_url)
        db_label = f"{parsed.scheme}://{parsed.hostname}:{parsed.port}/<redacted>" if db_url else "<empty>"
    except Exception:
        db_label = "<redacted>"

    proof = {
        "schema": PLUGIN_PROOF_SCHEMA,
        "phase": "COLLECT",
        "sessionstart_ok": True,
        "presence": presence,
        "errors": errors,
        "labels": {
            "db_url": db_label,
            "nonce_chars": len(nonce),
            "candidate_sha_chars": len(candidate_expected),
            "profile_sha_chars": len(profile_expected),
            "manifest_sha_chars": len(manifest_expected),
            "required_nodes_total": len(required_nodes),
            "collected_unique": len(collected) == len(set(collected)),
        },
        "sha_match": sha_match,
        "redis_module_sha": redis_module_sha,
        "redis_module_ok": redis_module_ok,
        "tempdb_binding_sha": tempdb_binding_sha,
        "tempdb_ok": tempdb_ok,
        "alembic_actual_head": alembic_actual,
        "alembic_ok": alembic_ok,
        "manifest_transport_sha": transport_digest_seen,
        "manifest_transport_nodes_total": len(required_nodes),
        "nonce": nonce,
        "collected_node_ids": sorted(collected),
    }

    if proof_out:
        target = Path(proof_out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if errors:
        print(f"ET1-COLLECT FAIL: errors={json.dumps(errors, sort_keys=True)}", file=sys.stderr)
        pytest.exit("child collect proof recorded drift", 1)

    print(f"ET1-COLLECT OK nodes={len(collected)}", file=sys.stderr)
