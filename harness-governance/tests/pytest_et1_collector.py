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

# R2-R1: the child uses the SHARED stdlib Redis authority module (same file,
# same cached sys.modules entry as the runner) — no duplicated protocol
# code. Only this endpoint constant stays local so tests can point the
# sentinel probe at a controlled listener.
SENTINEL_PROBE_ENDPOINT = ("127.0.0.1", 26379)

# Fixed child-label translation: the shared module's connect failure
# category is published as the child's historical "unreachable" label.
_CHILD_LABELS = {"connect_failed": "unreachable"}


def _load_redis_authority():
    """Load the shared Redis authority under the SAME fixed sys.modules key
    the runner uses — both sides literally share one module object."""
    import importlib.util

    key = "et1_redis_authority"
    cached = sys.modules.get(key)
    if cached is not None:
        return cached
    module_path = Path(__file__).resolve().parents[1] / "validator" / "redis_authority.py"
    spec = importlib.util.spec_from_file_location(key, str(module_path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


_redis_auth = _load_redis_authority()


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
        _redis_auth.eval_redis(url, SENTINEL_PROBE_ENDPOINT)
    except _redis_auth.RedisAuthorityError as err:
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
    need(bool(env.get("ET1_RUNNER_REQUIRED_NODES", "").strip()), "required_nodes:missing")
    need(bool(env.get("ET1_RUNNER_PROFILE_PATH", "")), "profile_path:missing")
    need(bool(env.get("ET1_RUNNER_MANIFEST_PATH", "")), "manifest_path:missing")
    need(bool(env.get("ET1_RUNNER_REPO_ROOT", "")), "repo_root:missing")

    db_url = env.get("TEST_DATABASE_URL", "")
    need(bool(db_url.strip()), "test_db_url:missing")
    allow_flag = env.get("MPANGO_ALLOW_TEMP_DB_CREATE", "")
    need(allow_flag == "1", "temp_db_capability:missing")

    # R2: the CHILD re-verifies the live Redis authority (DB15, PING/SELECT/
    # DBSIZE, sentinel unreachability). Redis disappearing after the runner
    # preflight fails the child closed here — no proof, no launch.
    problems.extend(_redis_recheck_problems(env))

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

    return {"ok": not problems, "problems": problems, "role": role}


def _write_sessionstart_proof(path, gate_result, nonce) -> None:
    payload = {
        "schema": SESSIONSTART_SCHEMA,
        "phase": "SESSIONSTART",
        "ok": gate_result["ok"],
        "problems": gate_result["problems"],
        "role": {k: gate_result["role"].get(k) for k in ("verified", "rolsuper", "rolcreatedb")},
        "nonce_chars": len(nonce),
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
    nonce = os.environ.get("ET1_RUNNER_NONCE", "")
    candidate_expected = os.environ.get("ET1_RUNNER_CANDIDATE_SHA", "")
    profile_expected = os.environ.get("ET1_RUNNER_PROFILE_SHA", "")
    manifest_expected = os.environ.get("ET1_RUNNER_MANIFEST_SHA", "")
    required_nodes = [
        n for n in os.environ.get("ET1_RUNNER_REQUIRED_NODES", "").split(",") if n.strip()
    ]
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
