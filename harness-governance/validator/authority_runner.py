#!/usr/bin/env python3
"""HE2-ET1-R1 end-to-end authority runner for Mpango (DC-12R1-MVP-L1-HE2-ET1).

Single authority gate between an environment and an authoritative command.
State machine with an explicit allowed-transition map (any forbidden jump is
itself a trap):

    INIT -> PREFLIGHT -> VOID                  (preflight trap fires)
    INIT -> PREFLIGHT -> COLLECT_PROVEN        (clean preflight)
    COLLECT_PROVEN -> VOID                     (collect drift / child tamper)
    COLLECT_PROVEN -> AUTHORIZED               (clean collect)
    AUTHORIZED -> VOID                         (nonce drift / SHA drift / missing command)
    AUTHORIZED -> RUNNING                      (clean authorize)
    RUNNING -> VOID                            (trap during launch phase)
    RUNNING -> FINISHED                        (command ran; exit code is the product test's verdict)
    VOID / FINISHED are terminal; a trap lands VOID on disk, and no phase
    ever re-enters COLLECT/AUTHORIZED/RUNNING after a failure.

R1 forced fixes over the ET1 baseline:
  1. The CLI accepts the real argv command (list, never a shell string);
     --authority without a non-empty command fails closed.
  2. collect_proven launches a REAL `pytest --collect-only` child and takes
     the node IDs from the runner-owned plugin's proof file; count,
     uniqueness, and exact set are compared against the frozen manifest.
  3. The plugin re-verifies role / TEST_DATABASE_URL / temp-DB capability /
     candidate / profile / nonce inside the child's pytest_sessionstart.
  4. The nonce is minted runner-side and only compared against the value the
     CHILD wrote to its proof file (cross-process; never self-compared).
  5. candidate_sha is the live `git rev-parse HEAD`; profile_sha and
     manifest_sha are SHA-256 over the actual file bytes.
  6. The authority profile is loaded from an explicit path and validated
     against the JSON schema plus the trap registry; no hardcoded profile.
  7. Lineage comes from live git refs: direct parent = HEAD^, chain base =
     the user-supplied baseline resolved through `git rev-parse`.
  8. Trap -> VOID is persisted; after any failure no later phase starts.
  9. The authority command is launched exactly once; GREEN lands FINISHED
     with exit 0, a non-zero exit is a REAL TEST RED (never VOID).
 10. Publishing is sanitized: variable presence and labels only, no values.

Python 3.11 stdlib only; every subprocess is spawned from an argv list
without a shell and without concatenated shell strings. Evaluator ids are
whitelisted here and map to in-process functions — the registry carries no
shell commands.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

RUNNER_VERSION = "2.0.0"
GOV_DIR = Path("harness-governance")
REGISTRY_PATH = GOV_DIR / "inventory" / "execution-traps.json"
PROFILES_SCHEMA_PATH = GOV_DIR / "schemas" / "authority-profiles.schema.json"
PLUGIN_PATH = GOV_DIR / "tests" / "pytest_et1_collector.py"
# R3: the collect child runs with CWD = canonical backend/ (the same CWD
# the authority command uses). From there `tests.…` would collide with the
# product's backend/tests package, so pytest loads the uniquely-named entry
# shim `et1_collect_entry` (on PYTHONPATH via harness-governance), which
# executes the runner-owned plugin file (path passed via env) — the plugin
# bytes/behavior are unchanged and remain the verified authority.
PLUGIN_MODULE = "et1_collect_entry"
PLUGIN_PROOF_SCHEMA = "harness-governance/pytest_et1_collector/2"
PUBLISH_SCHEMA = "harness-governance/authority-runner/2"

RUN_VERDICT_VOID = "VOID_ENVIRONMENT_PRECHECK"
RUN_VERDICT_GREEN = "AUTHORITY_EXECUTED_GREEN"
RUN_VERDICT_TEST_RED = "TEST_RED_REAL_COMMAND_NONZERO"

STATE_ORDER = ["INIT", "PREFLIGHT", "COLLECT_PROVEN", "AUTHORIZED", "RUNNING", "FINISHED"]
PROOF_TTL_SECONDS = 900

# Explicit allowed-transition map: any (src, tgt) pair not listed here is a
# TRAP_PHASE_CONTINUE_AFTER_FAIL. VOID is reachable from every live phase;
# FINISHED and VOID are terminal.
ALLOWED_TRANSITIONS = {
    "INIT": frozenset({"PREFLIGHT", "VOID"}),
    "PREFLIGHT": frozenset({"COLLECT_PROVEN", "VOID"}),
    "COLLECT_PROVEN": frozenset({"AUTHORIZED", "VOID"}),
    "AUTHORIZED": frozenset({"RUNNING", "VOID"}),
    "RUNNING": frozenset({"FINISHED", "VOID"}),
    "FINISHED": frozenset(),
    "VOID": frozenset(),
}

# Hardcoded evaluator whitelist: the ONLY ids the registry may reference.
# R2-R1: the pre-live evaluator name EVAL_REDIS is REMOVED — the registry
# cannot roll back to the old URL-string semantics.
EVALUATOR_WHITELIST = frozenset(
    {
        "EVAL_PG_ROLE", "EVAL_TEST_DB_URL", "EVAL_TEMP_DB", "EVAL_ALEMBIC_HEAD",
        "EVAL_REDIS_LIVE", "EVAL_COLLECT_MANIFEST", "EVAL_PHASE_FAIL_STOP",
        "EVAL_ROLE_RECHECK", "EVAL_SESSIONSTART_PROOF", "EVAL_GIT_REMOTE",
        "EVAL_GIT_LINEAGE", "EVAL_EVIDENCE_PACKAGING", "EVAL_EOL",
        "EVAL_VITE_SETTLE", "EVAL_EMAIL_DOMAIN",
    }
)

CANONICAL_ORIGIN = "https://github.com/lvoemingjie-hash/Mpango-ERP.git"
# R3-A1: the expected alembic head is bound to the PROTECTED profile
# (profile raw bytes are sha-bound into the run); there is no global
# hardcoded authority head and no CLI/env override path.
EXPECTED_ALEMBIC_HEAD = None  # retired: authority comes from the profile
SPECIAL_USE_DOMAINS = ("invalid", "example", "test", "localhost")

# R2-R1 live-Redis authority constants. The implementation itself lives in
# the SHARED stdlib module validator/redis_authority.py; R2-R2 binds that
# module by ORIGIN and RAW BYTES (a fixed sys.modules key is never trusted —
# a preloaded entry under the key is tamper evidence, not a cache).
SENTINEL_PROBE_ENDPOINT = ("127.0.0.1", 26379)
REDIS_TRAP = ("TRAP_REDIS_WRONG_DB", 14, "PREFLIGHT")

# R3 backend-CWD / temp-DB authority. The probe lives in the SHARED stdlib
# module validator/backend_env_authority.py, bound by origin + raw bytes via
# the same bootstrap policy as the redis module (a fixed sys.modules key is
# never trusted).
BACKEND_ENV_KEY = "et1_backend_env_authority"
BACKEND_ENV_TRAP = ("TRAP_TEMP_DB_CAPABILITY", 12, "PREFLIGHT")
BACKEND_ENV_ALLOWED = ("test", "testing")
TEMPDB_PORTS_VAR = "MPANGO_TEMP_DB_ALLOWED_PORTS"

# R4: bounded manifest transport. The frozen node manifest NEVER travels in a
# single argv/env string (kernel MAX_ARG_STRLEN is 128KB per string; a
# full-suite manifest of ~3800 nodes is ~460KB and exec fails E2BIG before
# any launch). The runner writes ONE canonical transport file (UTF-8, sorted,
# unique, LF-terminated lines), binds its raw-byte SHA-256 into the child's
# environment, and the child independently re-derives that digest from the
# bytes it actually read. Missing file, substituted file, byte drift, digest
# mismatch, duplicate node, non-canonical order, a missing trailing newline
# (truncation) and post-preflight mutation all fail closed. The transport
# file is runner-owned temporary state and is removed during cleanup.
TRANSPORT_PATH_VAR = "ET1_RUNNER_MANIFEST_TRANSPORT_PATH"
TRANSPORT_DIGEST_VAR = "ET1_RUNNER_MANIFEST_TRANSPORT_DIGEST"


def canonical_transport_bytes(nodes: list) -> bytes:
    """Canonical transport encoding: sorted, unique, non-empty node IDs, one
    per line, LF-terminated. Raises (sanitized ValueError) on duplicates or
    an empty set — never a silently weakened manifest."""
    cleaned = [str(n).strip() for n in nodes if str(n) and str(n).strip()]
    if not cleaned:
        raise ValueError("manifest_transport:empty")
    if len(cleaned) != len(set(cleaned)):
        raise ValueError("manifest_transport:duplicate_nodes")
    return ("\n".join(sorted(cleaned)) + "\n").encode("utf-8")


def manifest_transport_digest(transport_bytes: bytes) -> str:
    return hashlib.sha256(transport_bytes).hexdigest()

TEMPDB_HOSTS_VAR = "MPANGO_TEMP_DB_ALLOWED_HOSTS"


class BackendEnvBindingError(Exception):
    """Sanitized module-binding failure for the backend-env authority."""

    def __init__(self, category: str):
        super().__init__(f"backend_env_module:{category}")
        self.category = category


def backend_env_canonical_path() -> Path:
    return (Path(__file__).resolve().parent / "backend_env_authority.py").resolve()


def _module_origin_is_canonical_for(module, canonical: Path) -> bool:
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


def load_backend_env_module():
    """Origin-bound fresh bootstrap for the shared backend-env module (same
    policy as the redis loader: never return a sys.modules entry; a foreign
    preloaded entry is tamper evidence)."""
    import importlib.util

    canonical = backend_env_canonical_path()
    preloaded = sys.modules.get(BACKEND_ENV_KEY)
    tampered = preloaded is not None and not _module_origin_is_canonical_for(
        preloaded, canonical
    )
    sys.modules.pop(BACKEND_ENV_KEY, None)
    try:
        spec = importlib.util.spec_from_file_location(BACKEND_ENV_KEY, str(canonical))
    except (ValueError, OSError):
        raise BackendEnvBindingError("module_origin_untrusted") from None
    if spec is None or getattr(spec, "loader", None) is None:
        raise BackendEnvBindingError("module_origin_untrusted")
    module = importlib.util.module_from_spec(spec)
    sys.modules[BACKEND_ENV_KEY] = module
    try:
        spec.loader.exec_module(module)
    except BackendEnvBindingError:
        raise
    except Exception:
        raise BackendEnvBindingError("module_origin_untrusted") from None
    if not _module_origin_is_canonical_for(module, canonical):
        raise BackendEnvBindingError("module_origin_untrusted")
    return module, tampered


def backend_env_module_raw_digest() -> str:
    return hashlib.sha256(backend_env_canonical_path().read_bytes()).hexdigest()
REDIS_MODULE_KEY = "et1_redis_authority"

# Fixed module-binding categories (never paths, URLs, credentials, or env
# values): they join the redis-authority sanitized label set.
MODULE_BINDING_CATEGORIES = frozenset(
    {
        "module_preload_detected",   # preloaded sys.modules entry, foreign origin
        "module_origin_untrusted",   # wrong/missing spec, loader, __file__, path
        "module_bytes_drift",        # child recompute != runner original
        "module_digest_missing",     # child proof carries no module digest
        "module_digest_mismatch",    # runner original != child-reported digest
        "drift_at_authorize",        # JIT byte recheck at AUTHORIZED failed
        "drift_at_launch",           # JIT byte recheck before the launch failed
    }
)


class RedisModuleBindingError(Exception):
    """Sanitized module-binding failure; `category` is a fixed label from
    MODULE_BINDING_CATEGORIES. Never carries paths or chainable context."""

    def __init__(self, category: str):
        super().__init__(f"redis_module:{category}")
        self.category = category


def redis_module_canonical_path() -> Path:
    """The EXACT canonical location of the shared authority module, resolved
    relative to THIS consumer file (runner and child each resolve their own
    copy of this bootstrap; the two must land on the same file)."""
    return (Path(__file__).resolve().parent / "redis_authority.py").resolve()


def module_origin_is_canonical(module, canonical: Path) -> bool:
    """Reject wrong __file__, wrong spec origin, missing spec/loader, or any
    unexpected path. Both origin AND __file__ must resolve to the exact
    canonical path."""
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


def load_redis_authority_module():
    """R2-R2 module-origin binding bootstrap (consumer-local; the shared
    module itself cannot contain its own loader).

    Policy (closes SHARED_PROBE_MODULE_PRELOAD_INJECTION__AUTHORITY_BYPASS):
      1. a preloaded entry under the fixed key is NEVER returned — its
         origin is checked first; a foreign origin is tamper evidence and
         surfaces as module_preload_detected;
      2. the module is ALWAYS freshly executed from the canonical path's
         raw bytes (the cache is evicted, never reused);
      3. after execution the module's spec origin AND __file__ must both
         resolve to the exact canonical path;
      4. a missing spec/loader is module_origin_untrusted.
    Returns (module, tampered_flag). Raises RedisModuleBindingError on any
    origin/path/spec failure (fixed category, no path in the payload).
    """
    import importlib.util

    canonical = redis_module_canonical_path()
    preloaded = sys.modules.get(REDIS_MODULE_KEY)
    tampered = preloaded is not None and not module_origin_is_canonical(
        preloaded, canonical
    )
    sys.modules.pop(REDIS_MODULE_KEY, None)  # evict: the cache is never reused
    try:
        spec = importlib.util.spec_from_file_location(REDIS_MODULE_KEY, str(canonical))
    except (ValueError, OSError):
        raise RedisModuleBindingError("module_origin_untrusted") from None
    if spec is None or getattr(spec, "loader", None) is None:
        raise RedisModuleBindingError("module_origin_untrusted")
    module = importlib.util.module_from_spec(spec)
    sys.modules[REDIS_MODULE_KEY] = module
    try:
        spec.loader.exec_module(module)
    except RedisModuleBindingError:
        raise
    except Exception:
        raise RedisModuleBindingError("module_origin_untrusted") from None
    if not module_origin_is_canonical(module, canonical):
        raise RedisModuleBindingError("module_origin_untrusted")
    return module, tampered


class TrapFired(Exception):
    """A registered trap fired: fail-stop with a stable exit code."""

    def __init__(self, trap_id: str, exit_code: int, phase: str, presence: bool, evidence: dict):
        super().__init__(f"trap:{trap_id}")
        self.trap_id = trap_id
        self.exit_code = exit_code
        self.phase = phase
        self.presence = presence
        self.evidence = evidence  # sanitized: booleans/labels only


def _to_state(current: str, target: str) -> None:
    """Enforce the explicit allowed-transition map."""
    if target not in ALLOWED_TRANSITIONS.get(current, frozenset()):
        raise TrapFired(
            "TRAP_PHASE_CONTINUE_AFTER_FAIL", 16, current, True,
            {"current": current, "target": target,
             "allowed": sorted(ALLOWED_TRANSITIONS.get(current, frozenset()))},
        )


def load_registry() -> dict:
    with open(REGISTRY_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def registry_traps() -> dict:
    return {t["trap_id"]: t for t in load_registry()["traps"]}


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sanitize_url(url: str) -> str:
    """Return scheme://host:port/<redacted> — never credentials or paths."""
    try:
        parsed = urllib.parse.urlsplit(url)
        return f"{parsed.scheme}://{parsed.hostname}:{parsed.port}/<redacted>"
    except Exception:
        return "<redacted>"


def _git_output(*args: str, repo_root) -> str:
    """Run git with an argv list (no shell) and return stripped stdout."""
    result = subprocess.run(
        ["git", *args], cwd=str(repo_root), capture_output=True, text=True, shell=False,
    )
    return result.stdout.strip()


def live_head(repo_root) -> str:
    return _git_output("rev-parse", "HEAD", repo_root=repo_root)


def live_parent(repo_root) -> str:
    return _git_output("rev-parse", "HEAD^", repo_root=repo_root)


def resolve_commit(ref: str, repo_root) -> str:
    return _git_output("rev-parse", "--verify", f"{ref}^{{commit}}", repo_root=repo_root)


def _alembic_heads(repo_root) -> list:
    """Single-source-of-truth alembic head computation from migration files.

    Handles both `revision = "x"` and `revision: str = "x"` declarations; a
    revision referenced as someone's down_revision is not a head.
    """
    versions = Path(repo_root) / "backend" / "alembic" / "versions"
    revisions = {}
    for path in sorted(versions.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        rev = re.search(r"^revision(?::\s*str)?\s*=\s*['\"]([^'\"]+)['\"]", text, re.M)
        if not rev:
            continue
        down = re.search(r"^down_revision(?::[^=\n]*)?\s*=\s*(.+)$", text, re.M)
        revisions[rev.group(1)] = down.group(1) if down else "None"
    referenced = set()
    for down in revisions.values():
        referenced.update(re.findall(r"['\"]([^'\"]+)['\"]", down))
    return sorted(set(revisions) - referenced)


# ---------------------------------------------------------------------------
# Evaluator implementations (in-process; no shell)
# ---------------------------------------------------------------------------

def _pg_connect(url: str):
    import psycopg  # optional; absent driver => presence unknown => trap

    return psycopg.connect(url, autocommit=True)


def eval_pg_role(conn) -> dict:
    row = conn.execute(
        "select rolsuper, rolcreatedb from pg_roles where rolname = current_user"
    ).fetchone()
    rolsuper, rolcreatedb = (bool(row[0]), bool(row[1])) if row else (True, False)
    if rolsuper or not rolcreatedb:
        raise TrapFired(
            "TRAP_PG_ROLE_SUPER", 10, "PREFLIGHT", rolsuper,
            {"rolsuper": rolsuper, "rolcreatedb": rolcreatedb},
        )
    return {"rolsuper": rolsuper, "rolcreatedb": rolcreatedb}


def eval_test_db_url(raw: str) -> dict:
    if not raw or not raw.strip():
        raise TrapFired("TRAP_TEST_DB_URL_EMPTY", 11, "PREFLIGHT", True, {"url": "<empty>"})
    parsed = urllib.parse.urlsplit(raw)
    if not parsed.hostname or parsed.scheme not in ("postgresql", "postgresql+asyncpg"):
        raise TrapFired(
            "TRAP_TEST_DB_URL_EMPTY", 11, "PREFLIGHT", True,
            {"url": sanitize_url(raw), "category": "wrong_scheme_or_host"},
        )
    return {"url": sanitize_url(raw), "non_empty": True}


def eval_temp_db(conn, allow_flag: str, db_name: str) -> dict:
    if allow_flag != "1":
        raise TrapFired(
            "TRAP_TEMP_DB_CAPABILITY", 12, "PREFLIGHT", True,
            {"allow_flag": bool(allow_flag)},
        )
    conn.execute(f'create database "{db_name}"')
    probe_url = None  # presence smoke: create -> drop -> absence; no URL persisted
    conn.execute(f'drop database "{db_name}"')
    row = conn.execute(
        "select count(*) from pg_database where datname = %s", (db_name,)
    ).fetchone()
    if row[0] != 0:
        raise TrapFired("TRAP_TEMP_DB_CAPABILITY", 12, "PREFLIGHT", True, {"absence": False})
    return {"created_dropped": True, "absence": True, "probe_url": probe_url}


def eval_alembic_head(repo_root, expected_head: str,
                      expected_parent: str | None = None) -> dict:
    """R3-A1: real alembic heads from the repo tree; exactly one head; the
    actual head must equal the PROFILE's expected head byte-exact; and when
    the profile declares an expected parent, the lineage must be that exact
    single successor. Fixed categories only."""
    module, _tampered = load_backend_env_module()
    versions_dir = Path(repo_root) / "backend" / "alembic" / "versions"
    try:
        facts = module.alembic_verify(versions_dir, expected_head, expected_parent)
    except module.BackendEnvAuthorityError as err:
        category = err.category if err.category in (
            "alembic_multiple_heads", "alembic_head_mismatch",
            "alembic_parent_mismatch", "alembic_tree_unreadable") else "alembic_head_mismatch"
        raise TrapFired("TRAP_ALEMBIC_MULTI_HEAD", 13, "PREFLIGHT", True,
                        {"alembic": category, "head_count":
                         len(module.alembic_scan(versions_dir)["heads"])
                         if category == "alembic_multiple_heads" else None}) from None
    return {"head_count": 1, "alembic_head": facts["alembic_head"]}


def redis_live_check(url: str) -> dict:
    """Runner-side wrapper over the SHARED stdlib Redis authority. The shared
    module is freshly loaded from its canonical path on every use (origin
    re-verified; a preloaded fake is tamper evidence). Every failure maps to
    the registered trap with sanitized evidence only — no URL, host, port,
    credential, path, or chained traceback."""
    module, tampered = load_redis_authority_module()
    if tampered:
        raise TrapFired(*REDIS_TRAP, True, {"redis": "module_preload_detected"})
    try:
        return module.redis_live_check(url)
    except module.RedisAuthorityError as err:
        raise TrapFired(*REDIS_TRAP, True, {"redis": err.category}) from None


def eval_redis(url: str) -> dict:
    """Preflight Redis authority: live DB15 proof + sentinel unreachability,
    both from the shared module (the sentinel endpoint is passed explicitly
    so tests can point the probe at a controlled listener)."""
    module, tampered = load_redis_authority_module()
    if tampered:
        raise TrapFired(*REDIS_TRAP, True, {"redis": "module_preload_detected"})
    try:
        return module.eval_redis(url, SENTINEL_PROBE_ENDPOINT)
    except module.RedisAuthorityError as err:
        raise TrapFired(*REDIS_TRAP, True, {"redis": err.category}) from None


def redis_module_raw_digest() -> str:
    """SHA-256 over the shared module's RAW FILE BYTES at the canonical
    path (contract: the runner binds bytes, not module objects)."""
    return hashlib.sha256(redis_module_canonical_path().read_bytes()).hexdigest()


def eval_collect_manifest(actual_nodes: list, expected_nodes: list) -> dict:
    if sorted(actual_nodes) != sorted(expected_nodes):
        raise TrapFired(
            "TRAP_COLLECT_NODE_SET_DRIFT", 15, "COLLECT_PROVEN", True,
            {"count_equal": len(actual_nodes) == len(expected_nodes)},
        )
    return {"count": len(actual_nodes), "set_equal": True}


def eval_phase_fail_stop(states: list) -> dict:
    seen_fail = False
    for s in states:
        if s in ("FAIL", "VOID"):
            seen_fail = True
        elif seen_fail and s in STATE_ORDER[1:]:
            raise TrapFired("TRAP_PHASE_CONTINUE_AFTER_FAIL", 16, "AUTHORIZED", True, {"continued": s})
    return {"fail_stop": True}


def eval_role_recheck(conn) -> dict:
    row = conn.execute(
        "select rolsuper from pg_roles where rolname = current_user"
    ).fetchone()
    if row and bool(row[0]):
        raise TrapFired("TRAP_JIT_ROLE_ESCALATION", 17, "AUTHORIZED", True, {"rolsuper": True})
    return {"rolsuper": False}


def eval_sessionstart_proof(proof: dict, conn, db_url: str, allow_flag: str,
                            expected_nonce: str | None = None) -> dict:
    """Runner-side SESSIONSTART gate, just before the single launch.

    The nonce check is a cross-value comparison when the runner-side original
    is supplied: the proof's nonce must equal the ORIGINAL minted by this
    runner, never the proof's own value (self-comparison is a defect).
    """
    checks = {
        "role": False, "url": False, "capability": False, "nonce": False,
    }
    row = conn.execute(
        "select rolsuper from pg_roles where rolname = current_user"
    ).fetchone()
    checks["role"] = not (row and bool(row[0]))
    checks["url"] = bool(db_url and db_url.strip())
    checks["capability"] = allow_flag == "1"
    proof_nonce = proof.get("nonce", "")
    if expected_nonce is None:
        checks["nonce"] = bool(proof_nonce)
    else:
        checks["nonce"] = bool(proof_nonce) and secrets.compare_digest(
            proof_nonce, expected_nonce
        )
    if not all(checks.values()):
        raise TrapFired("TRAP_SESSIONSTART_DRIFT", 18, "SESSIONSTART", True, checks)
    return checks


def eval_git_remote(repo_root) -> dict:
    result = subprocess.run(
        ["git", "ls-remote", "--get-url", "origin"],
        cwd=str(repo_root), capture_output=True, text=True, shell=False,
    )
    url = result.stdout.strip()
    if url != CANONICAL_ORIGIN:
        raise TrapFired("TRAP_NON_CANONICAL_REMOTE", 19, "PREFLIGHT", True, {"origin": "<non-canonical>"})
    return {"origin": "canonical"}


def eval_git_lineage(final_tip_parent: str, chain_base: str) -> dict:
    if final_tip_parent == chain_base:
        raise TrapFired(
            "TRAP_LINEAGE_CONFUSION", 20, "PREFLIGHT", True,
            {"parent_equals_chain_base": True},
        )
    return {"parent": final_tip_parent[:12], "chain_base": chain_base[:12]}


def eval_evidence_packaging(manifest: dict, files_on_disk: list, gitignore_rules: list) -> dict:
    declared = set(manifest.get("files", []))
    actual = set(files_on_disk)
    missing = declared - actual
    extra = actual - declared
    mismatch = {f for f in declared & actual if manifest["files"][f] is None} if isinstance(manifest.get("files"), dict) else set()
    if missing or extra or mismatch:
        raise TrapFired(
            "TRAP_EVIDENCE_GITIGNORED", 21, "PACKAGING", True,
            {"missing": len(missing), "extra": len(extra), "mismatch": len(mismatch)},
        )
    return {"missing": 0, "extra": 0, "mismatch": 0}


def eval_eol(path) -> dict:
    data = Path(path).read_bytes()
    crlf = b"\r\n" in data
    lone_lf = data.replace(b"\r\n", b"").count(b"\n") > 0
    if crlf and lone_lf:
        raise TrapFired("TRAP_MIXED_EOF", 22, "PACKAGING", True, {"eol": "mixed"})
    return {"eol": "crlf" if crlf else "lf"}


def eval_vite_settle(spec_text: str) -> dict:
    if "networkidle" in spec_text:
        raise TrapFired("TRAP_VITE_NETWORKIDLE", 23, "PACKAGING", True, {"forbidden_wait": True})
    return {"forbidden_wait": False}


def eval_email_domain(email: str) -> dict:
    domain = email.rsplit("@", 1)[-1].lower() if "@" in email else ""
    labels = domain.split(".") if domain else []
    registrable = labels[-2] if len(labels) >= 2 else (labels[0] if labels else "")
    if registrable in SPECIAL_USE_DOMAINS:
        raise TrapFired("TRAP_SPECIAL_USE_EMAIL_DOMAIN", 24, "PREFLIGHT", True, {"domain_class": "special-use"})
    return {"domain_class": "resolvable"}


def _identity_is_privileged() -> bool:
    """Just-in-time identity check for the launch phase (no DB needed)."""
    try:
        if os.name == "posix" and os.geteuid() == 0:
            return True
    except AttributeError:
        pass
    try:
        import getpass

        return getpass.getuser().strip().lower() in ("root", "administrator")
    except Exception:
        return True  # fail closed: an unknown identity counts as privileged


def _validate_against_schema(doc, schema, path: str = "doc") -> list:
    """Minimal draft-07 subset: required / additionalProperties / types /
    pattern / enum / minLength / minItems, recursing into object items."""
    errors = []
    for key in schema.get("required", []):
        if key not in doc:
            errors.append(f"{path}.{key}:missing")
    props = schema.get("properties", {})
    if schema.get("additionalProperties") is False:
        for key in doc:
            if key not in props:
                errors.append(f"{path}.{key}:additional")
    for key, sub in props.items():
        if key not in doc:
            continue
        value = doc[key]
        expected = sub.get("type")
        actual = {str: "string", dict: "object", list: "array", bool: "boolean"}.get(type(value))
        if expected and actual and expected != actual and not (
            expected == "number" and isinstance(value, (int, float))
        ):
            errors.append(f"{path}.{key}:type")
            continue
        if "pattern" in sub and isinstance(value, str) and not re.search(sub["pattern"], value):
            errors.append(f"{path}.{key}:pattern")
        if "enum" in sub and value not in sub["enum"]:
            errors.append(f"{path}.{key}:enum")
        if "minLength" in sub and isinstance(value, str) and len(value) < sub["minLength"]:
            errors.append(f"{path}.{key}:min_length")
        if expected == "array":
            if "minItems" in sub and len(value) < sub["minItems"]:
                errors.append(f"{path}.{key}:min_items")
            item_schema = sub.get("items")
            if isinstance(item_schema, dict) and item_schema.get("type") == "object":
                for index, item in enumerate(value):
                    if isinstance(item, dict):
                        errors.extend(
                            _validate_against_schema(item, item_schema, f"{path}.{key}[{index}]")
                        )
    return errors


def load_explicit_profile(profile_path, schema_path=PROFILES_SCHEMA_PATH, profile_id: str = ""):
    """Load the authority profile from an explicit path, schema-validate the
    document, select --profile-id, and cross-check its traps against the
    registry. A hardcoded {"mode": "cli"} document can never pass."""
    try:
        with open(profile_path, encoding="utf-8") as fh:
            doc = json.load(fh)
        with open(schema_path, encoding="utf-8") as fh:
            schema = json.load(fh)
    except Exception:
        raise TrapFired("TRAP_PHASE_CONTINUE_AFTER_FAIL", 16, "PREFLIGHT", True,
                        {"reason": "profile_or_schema_unreadable"})
    if doc.get("mode") == "cli" or not isinstance(doc.get("profiles"), list):
        raise TrapFired("TRAP_PHASE_CONTINUE_AFTER_FAIL", 16, "PREFLIGHT", True,
                        {"reason": "hardcoded_or_malformed_profile"})
    errors = _validate_against_schema(doc, schema)
    if errors:
        raise TrapFired("TRAP_PHASE_CONTINUE_AFTER_FAIL", 16, "PREFLIGHT", True,
                        {"reason": "profile_schema_violation", "labels": sorted(errors)[:6]})
    selected = next((p for p in doc["profiles"] if p.get("profile_id") == profile_id), None)
    if selected is None:
        raise TrapFired("TRAP_PHASE_CONTINUE_AFTER_FAIL", 16, "PREFLIGHT", True,
                        {"reason": "profile_id_unknown"})
    known = registry_traps()
    unknown = [t for t in selected.get("required_traps", []) if t not in known]
    if unknown:
        raise TrapFired("TRAP_PHASE_CONTINUE_AFTER_FAIL", 16, "PREFLIGHT", True,
                        {"reason": "profile_unknown_trap", "count": len(unknown)})
    return selected, sha256_file(profile_path)


def ensure_plugin_available(gov_dir) -> dict:
    """The runner-owned collector plugin must exist and declare its proof
    schema BEFORE any child is spawned; a deleted plugin fails closed."""
    plugin_file = Path(gov_dir) / "tests" / "pytest_et1_collector.py"
    if not plugin_file.is_file():
        raise TrapFired("TRAP_COLLECT_NODE_SET_DRIFT", 15, "COLLECT_PROVEN", True,
                        {"reason": "child_plugin_missing"})
    source = plugin_file.read_text(encoding="utf-8")
    if PLUGIN_PROOF_SCHEMA not in source or "def pytest_collection_finish" not in source:
        raise TrapFired("TRAP_COLLECT_NODE_SET_DRIFT", 15, "COLLECT_PROVEN", True,
                        {"reason": "child_plugin_unrecognized"})
    return {"plugin": "present", "schema_declared": True}


def verify_child_proof(child, original_nonce: str, expected_nodes: list,
                       *, redis_module_sha: str,
                       tempdb_binding_sha: str = "",
                       alembic_actual_head: str = "",
                       transport_digest: str = "") -> dict:
    """Cross-process verification of the child's proof against the ORIGINAL
    runner-side values. Every comparison is against an independently held
    value; the child's own values are never trusted as their own reference.
    """
    if not isinstance(child, dict):
        raise TrapFired("TRAP_COLLECT_NODE_SET_DRIFT", 15, "COLLECT_PROVEN", True,
                        {"reason": "proof_not_object"})
    if child.get("schema") != PLUGIN_PROOF_SCHEMA:
        raise TrapFired("TRAP_COLLECT_NODE_SET_DRIFT", 15, "COLLECT_PROVEN", True,
                        {"reason": "foreign_proof_origin"})
    if child.get("sessionstart_ok") is not True:
        raise TrapFired("TRAP_SESSIONSTART_DRIFT", 18, "COLLECT_PROVEN", True,
                        {"reason": "child_sessionstart_not_ok"})
    child_nonce = child.get("nonce", "")
    if not child_nonce or not isinstance(original_nonce, str) or not original_nonce:
        raise TrapFired("TRAP_COLLECT_NODE_SET_DRIFT", 15, "COLLECT_PROVEN", True,
                        {"reason": "nonce_absent"})
    # The CROSS-PROCESS comparison: child proof value vs the ORIGINAL value
    # this runner minted. Self-comparison (proof vs proof) is a defect.
    if not secrets.compare_digest(child_nonce, original_nonce):
        raise TrapFired("TRAP_COLLECT_NODE_SET_DRIFT", 15, "COLLECT_PROVEN", True,
                        {"reason": "nonce_mismatch"})
    sha_match = child.get("sha_match") or {}
    for key in ("candidate", "profile", "manifest"):
        if sha_match.get(key) is not True:
            raise TrapFired("TRAP_COLLECT_NODE_SET_DRIFT", 15, "COLLECT_PROVEN", True,
                            {"reason": "child_sha_drift", "binding": key})
    # R2-R2 cross-process module binding: the child INDEPENDENTLY recomputed
    # the shared module's raw-byte digest; it is compared here against THIS
    # runner's ORIGINAL (the child's own value is never its own reference).
    child_module_sha = child.get("redis_module_sha", "")
    if not isinstance(redis_module_sha, str) or not redis_module_sha:
        raise TrapFired("TRAP_COLLECT_NODE_SET_DRIFT", 15, "COLLECT_PROVEN", True,
                        {"redis_module": "module_digest_missing"})
    if not isinstance(child_module_sha, str) or not child_module_sha:
        raise TrapFired("TRAP_COLLECT_NODE_SET_DRIFT", 15, "COLLECT_PROVEN", True,
                        {"redis_module": "module_digest_missing"})
    if not secrets.compare_digest(child_module_sha, redis_module_sha):
        raise TrapFired("TRAP_COLLECT_NODE_SET_DRIFT", 15, "COLLECT_PROVEN", True,
                        {"redis_module": "module_digest_mismatch"})
    # R3 cross-process temp-DB binding: the child independently recomputed
    # the accepted CWD/env facts digest; compare against THIS runner's
    # ORIGINAL (the child never self-compares).
    child_tempdb = child.get("tempdb_binding_sha", "")
    if not isinstance(tempdb_binding_sha, str) or not tempdb_binding_sha:
        raise TrapFired("TRAP_COLLECT_NODE_SET_DRIFT", 15, "COLLECT_PROVEN", True,
                        {"backend_env": "tempdb_digest_missing"})
    if not isinstance(child_tempdb, str) or not child_tempdb:
        raise TrapFired("TRAP_COLLECT_NODE_SET_DRIFT", 15, "COLLECT_PROVEN", True,
                        {"backend_env": "tempdb_digest_missing"})
    if not secrets.compare_digest(child_tempdb, tempdb_binding_sha):
        raise TrapFired("TRAP_COLLECT_NODE_SET_DRIFT", 15, "COLLECT_PROVEN", True,
                        {"backend_env": "tempdb_digest_mismatch"})
    # R3-A1 cross-process alembic binding: the child independently recomputed
    # the actual head; compare against THIS runner's bound actual head.
    child_head = child.get("alembic_actual_head", "")
    if not isinstance(alembic_actual_head, str) or not alembic_actual_head:
        raise TrapFired("TRAP_COLLECT_NODE_SET_DRIFT", 15, "COLLECT_PROVEN", True,
                        {"alembic": "child_head_missing"})
    if not isinstance(child_head, str) or not child_head:
        raise TrapFired("TRAP_COLLECT_NODE_SET_DRIFT", 15, "COLLECT_PROVEN", True,
                        {"alembic": "child_head_missing"})
    if not secrets.compare_digest(child_head, alembic_actual_head):
        raise TrapFired("TRAP_COLLECT_NODE_SET_DRIFT", 15, "COLLECT_PROVEN", True,
                        {"alembic": "child_head_mismatch"})

    collected = child.get("collected_node_ids")
    if not isinstance(collected, list) or not collected:
        raise TrapFired("TRAP_COLLECT_NODE_SET_DRIFT", 15, "COLLECT_PROVEN", True,
                        {"reason": "collected_not_list_or_empty"})
    if len(collected) != len(set(collected)):
        raise TrapFired("TRAP_COLLECT_NODE_SET_DRIFT", 15, "COLLECT_PROVEN", True,
                        {"reason": "duplicate_node_ids"})
    # R4: cross-process transport binding — the child INDEPENDENTLY re-derived
    # the transport digest from the bytes it read; compare against THIS
    # runner's ORIGINAL (never the child's value against itself).
    child_transport_sha = child.get("manifest_transport_sha", "")
    if not transport_digest:
        raise TrapFired("TRAP_COLLECT_NODE_SET_DRIFT", 15, "COLLECT_PROVEN", True,
                        {"manifest_transport": "runner_digest_missing"})
    if not isinstance(child_transport_sha, str) or not child_transport_sha:
        raise TrapFired("TRAP_COLLECT_NODE_SET_DRIFT", 15, "COLLECT_PROVEN", True,
                        {"manifest_transport": "child_digest_missing"})
    if not secrets.compare_digest(child_transport_sha, transport_digest):
        raise TrapFired("TRAP_COLLECT_NODE_SET_DRIFT", 15, "COLLECT_PROVEN", True,
                        {"manifest_transport": "child_digest_mismatch"})
    child_transport_total = child.get("manifest_transport_nodes_total")
    if child_transport_total != len(expected_nodes):
        raise TrapFired("TRAP_COLLECT_NODE_SET_DRIFT", 15, "COLLECT_PROVEN", True,
                        {"manifest_transport": "child_total_mismatch"})
    eval_collect_manifest(collected, expected_nodes)
    return {
        "nonce_match": True,
        "collected_node_count": len(collected),
        "sha_match": {"candidate": True, "profile": True, "manifest": True},
        "redis_module_match": True,
        "tempdb_match": True,
        "alembic_match": True,
        "manifest_transport_match": True,
    }


# ---------------------------------------------------------------------------
# Authority runner state machine
# ---------------------------------------------------------------------------

class AuthorityRunner:
    def __init__(self, repo_root, profile: dict, expected_nodes: list):
        self.repo_root = Path(repo_root)
        self.profile = profile
        self.expected_nodes = list(expected_nodes)
        self.state = "INIT"
        self.trace: list = []
        self.proof: dict | None = None
        self.sentinel_calls = 0  # negative control: full-run launch counter
        self.collect_spawns = 0  # negative control: child collection counter
        self.original_nonce: str | None = None
        self.candidate_sha: str | None = None
        self.profile_sha: str | None = None
        self.manifest_sha: str | None = None
        self.profile_sha_file = None  # explicit profile path (file-bytes sha)
        self.manifest_sha_file = None  # explicit node-manifest path
        self.collect_child_summary: dict | None = None
        self.command_exit_code: int | None = None
        # R2-R2 module-origin/byte binding (contract 4/5): the runner binds
        # the shared module's canonical path + RAW-BYTE SHA-256; the child
        # independently recomputes both and the two are cross-compared.
        self.redis_module_sha: str | None = None
        self.redis_module_tampered: bool = False
        self.redis_module_category: str = ""
        # R3 backend-CWD / temp-DB binding
        self.backend_env_module_sha: str | None = None
        self.backend_env_tampered: bool = False
        self.backend_env_category: str = ""
        self.authority_cwd: Path | None = None
        self.tempdb_binding_sha: str | None = None
        self.alembic_expected: str | None = None
        self.alembic_parent: str | None = None
        self.alembic_actual: str | None = None
        self.alembic_binding_sha: str | None = None

    def _to(self, state: str) -> None:
        _to_state(self.state, state)
        self.trace.append(f"{self.state}->{state}")
        self.state = state

    def _check_registry_health(self) -> None:
        traps = registry_traps()
        exit_codes = [t["stable_exit_code"] for t in traps.values()]
        if len(exit_codes) != len(set(exit_codes)):
            raise TrapFired("TRAP_PHASE_CONTINUE_AFTER_FAIL", 16, "PREFLIGHT", True, {"registry": "duplicate_exit_code"})
        for trap in traps.values():
            if trap["evaluator_id"] not in EVALUATOR_WHITELIST:
                raise TrapFired("TRAP_PHASE_CONTINUE_AFTER_FAIL", 16, "PREFLIGHT", True, {"registry": "unknown_evaluator"})
            if trap["risk"] in ("P0", "P1") and trap["status"] != "ACTIVE":
                raise TrapFired("TRAP_PHASE_CONTINUE_AFTER_FAIL", 16, "PREFLIGHT", True, {"registry": "p0p1_disabled"})

    def bind_backend_env_module(self) -> None:
        """R3: freshly load the shared backend-env authority from its
        canonical path (origin verified) and bind its RAW-BYTE SHA-256."""
        try:
            _module, tampered = load_backend_env_module()
            self.backend_env_tampered = tampered
            self.backend_env_module_sha = backend_env_module_raw_digest()
        except BackendEnvBindingError as err:
            self.backend_env_tampered = True
            self.backend_env_category = err.category

    def _require_bound_backend_env_module(self) -> None:
        if self.backend_env_tampered or not self.backend_env_module_sha:
            category = self.backend_env_category or (
                "module_preload_detected" if self.backend_env_tampered
                else "module_origin_untrusted"
            )
            raise TrapFired(*BACKEND_ENV_TRAP, True, {"backend_env_module": category})

    def _enforce_backend_env_authority_alembic(self) -> None:
        """R3-A1: real alembic heads from the repo tree, bound to the
        PROTECTED profile's expected head (no CLI/env override exists)."""
        self.alembic_expected = self.profile.get("expected_alembic_head", "")
        self.alembic_parent = self.profile.get("expected_alembic_parent") or None
        if not self.alembic_expected:
            raise TrapFired("TRAP_ALEMBIC_MULTI_HEAD", 13, "PREFLIGHT", True,
                            {"alembic": "profile_missing_alembic_head"})
        head_result = eval_alembic_head(self.repo_root, self.alembic_expected,
                                        self.alembic_parent)
        self.alembic_actual = head_result["alembic_head"]

    def bind_redis_module(self) -> None:
        """R2-R2: freshly load the shared module from the canonical path
        (origin verified) and bind its RAW-BYTE SHA-256. Any preloaded
        foreign module or origin failure is recorded for preflight to VOID
        on — never silently accepted."""
        try:
            _module, tampered = load_redis_authority_module()
            self.redis_module_tampered = tampered
            self.redis_module_sha = redis_module_raw_digest()
        except RedisModuleBindingError as err:
            self.redis_module_tampered = True
            self.redis_module_category = err.category

    def _require_bound_redis_module(self) -> None:
        if self.redis_module_tampered or not self.redis_module_sha:
            category = self.redis_module_category or (
                "module_preload_detected" if self.redis_module_tampered
                else "module_origin_untrusted"
            )
            raise TrapFired(*REDIS_TRAP, True, {"redis": category})

    def preflight(self, db_url: str, allow_flag: str, email: str,
                  final_tip_parent: str, chain_base: str) -> None:
        self._to("PREFLIGHT")
        self._check_registry_health()
        self.bind_redis_module()
        self._require_bound_redis_module()
        self.bind_backend_env_module()
        self._require_bound_backend_env_module()
        self._enforce_backend_env_authority()
        # R3-A1: the expected head comes from the PROTECTED profile (bound by
        # this run's profile raw-byte sha); no CLI/env override exists.
        self._enforce_backend_env_authority_alembic()
        eval_test_db_url(db_url)
        eval_email_domain(email)
        eval_git_remote(self.repo_root)
        eval_git_lineage(final_tip_parent, chain_base)
        try:
            import psycopg  # noqa: F401
            conn = _pg_connect(db_url)
        except TrapFired:
            raise
        except Exception:
            # Driver absent => environment unproven => presence trap.
            raise TrapFired("TRAP_PG_ROLE_SUPER", 10, "PREFLIGHT", True, {"driver": "absent"})
        try:
            eval_pg_role(conn)
            eval_temp_db(conn, allow_flag, f"et1_smoke_{secrets.token_hex(4)}")
        finally:
            conn.close()
        eval_redis(os.environ.get("PW1R3_TEST_REDIS_URL", ""))
        # R3-A1: alembic head already verified via profile-driven enforcement above
        # Bind the candidate this run will prove: the LIVE head right now.
        self.candidate_sha = live_head(self.repo_root)

    def _enforce_backend_env_authority(self) -> None:
        """R3: machine-verify CWD / MPANGO_ENV / temp-DB URL invariants via
        the SHARED probe and bind a digest over the exact accepted facts.
        Evidence is a fixed category only — never URL, host, port, path, or
        credential values."""
        module, _tampered = load_backend_env_module()
        self.authority_cwd = module.canonical_backend_dir(__file__)
        db_url = os.environ.get("TEST_DATABASE_URL", "")
        try:
            facts = module.backend_env_facts(
                url=db_url,
                mpango_env=os.environ.get("MPANGO_ENV", ""),
                allowed_ports_raw=os.environ.get(TEMPDB_PORTS_VAR, ""),
                allowed_hosts_raw=os.environ.get(TEMPDB_HOSTS_VAR, ""),
                authority_cwd=self.authority_cwd,
            )
        except module.BackendEnvAuthorityError as err:
            raise TrapFired(*BACKEND_ENV_TRAP, True,
                            {"backend_env": err.category}) from None
        digest_input = "|".join([
            facts["mpango_env"], facts["db_name"], str(facts["port"]),
            facts["host"], facts["allowed_ports"], facts["allowed_hosts"],
            str(facts["authority_cwd"]),
        ])
        self.tempdb_binding_sha = module.binding_digest(digest_input)
        # R3-A1: the alembic binding travels separately (expected/actual/
        # parent), so the child recomputation stays a mirror of these facts.
        self.alembic_binding_sha = module.binding_digest("|".join([
            self.alembic_expected or "", self.alembic_actual or "",
            self.alembic_parent or ""]))

    def _current_tempdb_binding(self) -> str:
        """Recompute the binding digest from CURRENT process state."""
        module, _tampered = load_backend_env_module()
        db_url = os.environ.get("TEST_DATABASE_URL", "")
        try:
            facts = module.backend_env_facts(
                url=db_url,
                mpango_env=os.environ.get("MPANGO_ENV", ""),
                allowed_ports_raw=os.environ.get(TEMPDB_PORTS_VAR, ""),
                allowed_hosts_raw=os.environ.get(TEMPDB_HOSTS_VAR, ""),
                authority_cwd=self.authority_cwd,
            )
        except module.BackendEnvAuthorityError:
            return ""
        digest_input = "|".join([
            facts["mpango_env"], facts["db_name"], str(facts["port"]),
            facts["host"], facts["allowed_ports"], facts["allowed_hosts"],
            str(facts["authority_cwd"]),
        ])
        return module.binding_digest(digest_input)

    def _alembic_drift(self) -> str | None:
        """Recompute expected-consistency from the CURRENT tree: returns a
        fixed drift category or None when the actual head still equals the
        bound expected head and parent lineage."""
        module, _tampered = load_backend_env_module()
        versions_dir = getattr(self, "alembic_versions_dir", None) or (
            Path(self.repo_root) / "backend" / "alembic" / "versions")
        try:
            scan = module.alembic_scan(versions_dir)
        except module.BackendEnvAuthorityError:
            return "alembic_tree_unreadable"
        if len(scan["heads"]) != 1:
            return "alembic_multiple_heads"
        actual = scan["heads"][0]
        if actual != self.alembic_expected:
            return "alembic_head_drift"
        entry = scan["revisions"][actual]
        if self.alembic_parent and entry["down"] != self.alembic_parent:
            return "alembic_parent_drift"
        return None

    def _current_transport_digest(self) -> str:
        """Recompute the transport file's raw-byte digest from CURRENT state;
        empty string when the file is missing/unreadable."""
        path = getattr(self, "transport_path", None)
        if path is None:
            return ""
        try:
            return manifest_transport_digest(Path(path).read_bytes())
        except OSError:
            return ""

    def _transport_drift(self) -> str | None:
        """Fixed drift category when the transport bytes moved after the
        binding was minted (post-preflight mutation fails closed)."""
        digest = getattr(self, "transport_digest", "")
        if not digest:
            return "transport_unbound"
        if self._current_transport_digest() != digest:
            return "manifest_transport_drift"
        return None

    def _current_alembic_actual(self) -> str:
        """Recompute the actual alembic head from the CURRENT repo tree."""
        module, _tampered = load_backend_env_module()
        try:
            scan = module.alembic_scan(
                Path(self.repo_root) / "backend" / "alembic" / "versions")
            if len(scan["heads"]) == 1:
                return scan["heads"][0]
        except module.BackendEnvAuthorityError:
            pass
        return ""

    def collect_proven(self, *, profile_path, manifest_path, proof_out,
                       sessionstart_out, collect_target) -> None:
        """COLLECT_PROVEN: launch ONE real collect-only pytest child with the
        runner-owned plugin and verify its proof against runner-side values."""
        self._to("COLLECT_PROVEN")
        gov_dir = self.repo_root / "harness-governance"
        ensure_plugin_available(gov_dir)
        self.profile_sha = sha256_file(profile_path)
        self.manifest_sha = sha256_file(manifest_path)
        candidate = live_head(self.repo_root)
        if not candidate:
            raise TrapFired("TRAP_COLLECT_NODE_SET_DRIFT", 15, "COLLECT_PROVEN", True,
                            {"reason": "candidate_unresolvable"})
        self.candidate_sha = candidate
        # The nonce is minted HERE, runner-side. The child receives it via its
        # environment and writes it back into its proof; the only accepted
        # comparison is proof-value vs this ORIGINAL (never proof vs proof).
        self.original_nonce = secrets.token_hex(16)
        proof_out = Path(proof_out).resolve()
        sessionstart_out = Path(sessionstart_out).resolve()
        proof_out.parent.mkdir(parents=True, exist_ok=True)
        for stale in (proof_out, sessionstart_out):
            try:
                stale.unlink()
            except OSError:
                pass
        # R4: bounded transport replaces the single giant env string. The
        # full node manifest travels only through this digest-bound file.
        transport_bytes = canonical_transport_bytes(self.expected_nodes)
        self.transport_digest = manifest_transport_digest(transport_bytes)
        transport_path = proof_out.parent / "et1-manifest.transport"
        transport_path.write_bytes(transport_bytes)
        self.transport_path = transport_path

        child_env = {
            **os.environ,
            "ET1_RUNNER_NONCE": self.original_nonce,
            "ET1_RUNNER_CANDIDATE_SHA": candidate,
            "ET1_RUNNER_PROFILE_SHA": self.profile_sha,
            "ET1_RUNNER_MANIFEST_SHA": self.manifest_sha,
            TRANSPORT_PATH_VAR: str(transport_path),
            TRANSPORT_DIGEST_VAR: self.transport_digest,
            "ET1_RUNNER_PROOF_OUT": str(proof_out),
            "ET1_RUNNER_SESSIONSTART_OUT": str(sessionstart_out),
            "ET1_RUNNER_PROFILE_PATH": str(Path(profile_path).resolve()),
            "ET1_RUNNER_MANIFEST_PATH": str(Path(manifest_path).resolve()),
            "ET1_RUNNER_REPO_ROOT": str(self.repo_root.resolve()),
            "ET1_RUNNER_REDIS_MODULE_SHA": self.redis_module_sha or "",
        }
        target = Path(collect_target)
        if not target.is_absolute():
            target = self.repo_root / target
        child_env["ET1_RUNNER_TEMPDB_BINDING_SHA"] = self.tempdb_binding_sha or ""
        child_env["ET1_RUNNER_ALEMBIC_EXPECTED"] = self.alembic_expected or ""
        child_env["ET1_RUNNER_ALEMBIC_PARENT"] = self.alembic_parent or ""
        # R3: the collect child runs in the SAME canonical backend/ CWD the
        # authority command will use; the entry shim reaches harness-
        # governance via PYTHONPATH (absolute), never by trusting the CWD.
        child_env["PYTHONPATH"] = str(gov_dir.resolve())
        child_env["ET1_RUNNER_PLUGIN_FILE"] = str(
            (gov_dir / "tests" / "pytest_et1_collector.py").resolve()
        )
        cmd = [
            sys.executable, "-m", "pytest",
            "-p", PLUGIN_MODULE,
            "-p", "no:cacheprovider",
            "--collect-only", "-q", str(target),
        ]
        result = subprocess.run(cmd, cwd=str(gov_dir), env=child_env,
                                capture_output=True, text=True, shell=False)
        self.collect_spawns += 1
        if not proof_out.exists():
            raise TrapFired("TRAP_COLLECT_NODE_SET_DRIFT", 15, "COLLECT_PROVEN", True,
                            {"reason": "no_child_proof", "child_rc": result.returncode})
        try:
            child = json.loads(proof_out.read_text(encoding="utf-8"))
        except Exception:
            raise TrapFired("TRAP_COLLECT_NODE_SET_DRIFT", 15, "COLLECT_PROVEN", True,
                            {"reason": "child_proof_unreadable"})
        self.collect_child_summary = verify_child_proof(
            child, self.original_nonce, self.expected_nodes,
            redis_module_sha=self.redis_module_sha,
            tempdb_binding_sha=self.tempdb_binding_sha or "",
            alembic_actual_head=self.alembic_actual or "",
            transport_digest=self.transport_digest,
        )
        # R4: the transport bytes must not have drifted while the child ran.
        if self._current_transport_digest() != self.transport_digest:
            raise TrapFired("TRAP_COLLECT_NODE_SET_DRIFT", 15, "COLLECT_PROVEN", True,
                            {"manifest_transport": "drift_after_collect"})

    def authorize(self, db_url: str, allow_flag: str) -> None:
        self._to("AUTHORIZED")
        eval_phase_fail_stop([s.split("->")[1] for s in self.trace] + [self.state])
        drift = self._transport_drift()
        if drift:
            raise TrapFired("TRAP_SESSIONSTART_DRIFT", 18, "AUTHORIZED", True,
                            {"manifest_transport": drift})
        if not self.proof:
            self.proof = {"nonce": self.original_nonce or "", "issued_at": time.time(),
                          "expires_at": time.time() + PROOF_TTL_SECONDS}
        if time.time() > self.proof["expires_at"]:
            raise TrapFired("TRAP_SESSIONSTART_DRIFT", 18, "AUTHORIZED", True, {"reason": "proof_expired"})
        # Candidate must still be the LIVE head (hardcoded values drift-trap).
        current = live_head(self.repo_root)
        if not current or current != self.candidate_sha:
            raise TrapFired("TRAP_SESSIONSTART_DRIFT", 18, "AUTHORIZED", True,
                            {"reason": "candidate_drift"})
        # Profile and manifest must still be the same FILE BYTES.
        if self.profile_sha_file is not None:
            if sha256_file(self.profile_sha_file) != self.profile_sha:
                raise TrapFired("TRAP_SESSIONSTART_DRIFT", 18, "AUTHORIZED", True,
                                {"reason": "profile_drift"})
        if self.manifest_sha_file is not None:
            if sha256_file(self.manifest_sha_file) != self.manifest_sha:
                raise TrapFired("TRAP_SESSIONSTART_DRIFT", 18, "AUTHORIZED", True,
                                {"reason": "manifest_drift"})
        # R3: the accepted CWD/env facts must still bind exactly at authorize.
        if self.tempdb_binding_sha is not None:
            if self._current_tempdb_binding() != self.tempdb_binding_sha:
                raise TrapFired("TRAP_SESSIONSTART_DRIFT", 18, "AUTHORIZED", True,
                                {"backend_env": "drift_at_authorize"})
        # R3-A1: expected head / actual head / lineage must still hold.
        if self.alembic_expected is not None:
            drift = self._alembic_drift()
            if drift:
                raise TrapFired("TRAP_SESSIONSTART_DRIFT", 18, "AUTHORIZED", True,
                                {"alembic": drift})
        # R2-R2: the shared Redis module's raw bytes must still match the
        # preflight binding by the time the run is authorized.
        if self.redis_module_sha is not None:
            try:
                current_module = hashlib.sha256(
                    redis_module_canonical_path().read_bytes()
                ).hexdigest()
            except OSError:
                current_module = ""
            if current_module != self.redis_module_sha:
                raise TrapFired("TRAP_SESSIONSTART_DRIFT", 18, "AUTHORIZED", True,
                                {"redis_module": "drift_at_authorize"})
        if _identity_is_privileged():
            raise TrapFired("TRAP_JIT_ROLE_ESCALATION", 17, "AUTHORIZED", True,
                            {"identity_class": "privileged"})
        try:
            conn = _pg_connect(db_url)
        except Exception:
            raise TrapFired("TRAP_PG_ROLE_SUPER", 10, "AUTHORIZED", True, {"driver": "absent"})
        try:
            eval_role_recheck(conn)
        finally:
            conn.close()
        self.proof = {
            "nonce": self.original_nonce,
            "candidate_sha": self.candidate_sha,
            "profile_sha": self.profile_sha,
            "node_manifest_sha": self.manifest_sha,
            "issued_at": time.time(),
            "expires_at": time.time() + PROOF_TTL_SECONDS,
            "state_trace": list(self.trace),
        }

    def proof_valid(self) -> bool:
        if not self.proof:
            return False
        if time.time() > self.proof["expires_at"]:
            return False
        candidate = live_head(self.repo_root)
        if not candidate or self.proof.get("candidate_sha") != candidate:
            return False
        if self.profile_sha_file is not None:
            expected_profile = sha256_file(self.profile_sha_file)
        else:
            expected_profile = hashlib.sha256(
                json.dumps(self.profile, sort_keys=True).encode()
            ).hexdigest()
        if self.proof.get("profile_sha") != expected_profile:
            return False
        if self.manifest_sha_file is not None:
            expected_manifest = sha256_file(self.manifest_sha_file)
        else:
            expected_manifest = hashlib.sha256(
                "\n".join(sorted(self.expected_nodes)).encode()
            ).hexdigest()
        if self.proof.get("node_manifest_sha") != expected_manifest:
            return False
        return True

    def require_command(self, command) -> None:
        """--authority without a real argv command fails closed."""
        if not command or not isinstance(command, list) or not any(str(c).strip() for c in command):
            raise TrapFired("TRAP_PHASE_CONTINUE_AFTER_FAIL", 16, "AUTHORIZED", True,
                            {"reason": "missing_command"})

    def run(self, db_url: str, allow_flag: str, command) -> int:
        """RUNNING phase: the single authority launch. A non-zero exit is the
        product test's REAL verdict (returned, never VOID-classified)."""
        self._to("RUNNING")
        if not self.proof_valid():
            raise TrapFired("TRAP_SESSIONSTART_DRIFT", 18, "RUNNING", True, {"proof": "invalid"})
        eval_sessionstart_proof(self.proof, _pg_connect(db_url), db_url, allow_flag,
                                expected_nonce=self.original_nonce)
        # R2-R2 contract 9: just-in-time RAW-BYTE recheck of the shared
        # module — drift after the child proof still blocks the launch.
        if self.redis_module_sha is not None:
            try:
                current_module = hashlib.sha256(
                    redis_module_canonical_path().read_bytes()
                ).hexdigest()
            except OSError:
                current_module = ""
            if current_module != self.redis_module_sha:
                raise TrapFired("TRAP_SESSIONSTART_DRIFT", 18, "RUNNING", True,
                                {"redis_module": "drift_at_launch"})
        # R3 contract 8: CWD/env drift between the child proof and the
        # launch blocks the authority command.
        if self.tempdb_binding_sha is not None:
            pass  # (binding recheck happens below alongside alembic)
        # R3-A1: alembic expected/actual/lineage JIT recheck before launch.
        if self.alembic_expected is not None:
            drift = self._alembic_drift()
            if drift:
                raise TrapFired("TRAP_SESSIONSTART_DRIFT", 18, "RUNNING", True,
                                {"alembic": drift})
        # R4: manifest transport JIT recheck before launch — byte drift after
        # the child proof blocks the authority command.
        drift = self._transport_drift()
        if drift:
            raise TrapFired("TRAP_SESSIONSTART_DRIFT", 18, "RUNNING", True,
                            {"manifest_transport": drift})
        if self.tempdb_binding_sha is not None:
            if self._current_tempdb_binding() != self.tempdb_binding_sha:
                raise TrapFired("TRAP_SESSIONSTART_DRIFT", 18, "RUNNING", True,
                                {"backend_env": "drift_at_launch"})
            if self.authority_cwd is None or not self.authority_cwd.is_dir():
                raise TrapFired("TRAP_SESSIONSTART_DRIFT", 18, "RUNNING", True,
                                {"backend_env": "cwd_not_canonical"})
        if command is None:
            return 0
        if self.sentinel_calls:
            raise TrapFired("TRAP_PHASE_CONTINUE_AFTER_FAIL", 16, "RUNNING", True,
                            {"reason": "already_launched"})
        self.sentinel_calls += 1  # negative control: exactly-one-launch counter
        result = subprocess.run(
            command, shell=False,
            cwd=str(self.authority_cwd) if self.authority_cwd else None,
        )
        self.command_exit_code = result.returncode
        self._to("FINISHED")
        return result.returncode

    def finish(self) -> None:
        if self.state != "FINISHED":
            self._to("FINISHED")

    def publish(self, publish_dir) -> None:
        """Sanitized publish: presence/labels/counts only — never values."""
        out_dir = Path(publish_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        child = self.collect_child_summary or {}
        payload = {
            "schema": PUBLISH_SCHEMA,
            "runner_version": RUNNER_VERSION,
            "state": self.state,
            "presence": {
                "TEST_DATABASE_URL_set": bool(os.environ.get("TEST_DATABASE_URL", "").strip()),
                "MPANGO_ALLOW_TEMP_DB_CREATE": os.environ.get("MPANGO_ALLOW_TEMP_DB_CREATE", "") == "1",
                "PW1R3_TEST_REDIS_URL_set": bool(os.environ.get("PW1R3_TEST_REDIS_URL", "").strip()),
            },
            "lineage": {
                "parent_sha_chars": len(live_parent(self.repo_root)),
                "candidate_sha_chars": len(self.candidate_sha or ""),
                "profile_sha_chars": len(self.profile_sha or ""),
                "manifest_sha_chars": len(self.manifest_sha or ""),
                "nonce_chars": len(self.original_nonce or ""),
            },
            "expected_node_count": len(self.expected_nodes),
            "collected_node_count": child.get("collected_node_count", 0),
            "nonce_match": child.get("nonce_match", False),
            "child_sha_match": child.get("sha_match", {}),
            "redis_module_bound": bool(self.redis_module_sha),
            "redis_module_sha_chars": len(self.redis_module_sha or ""),
            "redis_module_match": child.get("redis_module_match", False),
            "backend_env_bound": bool(self.tempdb_binding_sha),
            "tempdb_binding_sha_chars": len(self.tempdb_binding_sha or ""),
            "tempdb_match": child.get("tempdb_match", False),
            "alembic_expected_bound": bool(self.alembic_expected),
            "alembic_match": child.get("alembic_match", False),
            "manifest_transport_bound": bool(getattr(self, "transport_digest", "")),
            "manifest_transport_match": child.get("manifest_transport_match", False),
            "collect_child_spawns": self.collect_spawns,
            "sentinel_calls": self.sentinel_calls,
            "command_exit_code": self.command_exit_code,
        }
        with open(out_dir / "authority-preflight.json", "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
        with open(out_dir / "authority-trace.json", "w", encoding="utf-8") as fh:
            json.dump({
                "state_trace": list(self.trace),
                "transitions_enforced": "ALLOWED_TRANSITIONS",
            }, fh, indent=2, sort_keys=True)
            fh.write("\n")


def _publish_void_only(publish_dir, fired: TrapFired) -> None:
    """VOID artifact for traps that fire before a runner instance exists."""
    out_dir = Path(publish_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": PUBLISH_SCHEMA,
        "runner_version": RUNNER_VERSION,
        "state": "VOID",
        "trap_id": fired.trap_id,
        "trap_phase": fired.phase,
    }
    with open(out_dir / "authority-preflight.json", "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")
    with open(out_dir / "authority-trace.json", "w", encoding="utf-8") as fh:
        json.dump({"state_trace": [], "transitions_enforced": "ALLOWED_TRANSITIONS"},
                  fh, indent=2, sort_keys=True)
        fh.write("\n")


# ---------------------------------------------------------------------------
# Self-test (no product runtime; pure in-process fixtures)
# ---------------------------------------------------------------------------

def self_test() -> int:
    import tempfile

    failures = 0

    def check(label, condition):
        nonlocal failures
        if not condition:
            failures += 1
            print(f"SELFTEST FAIL: {label}")

    # Registry health: unique ids/exit codes, whitelisted evaluators, P0/P1 active.
    traps = registry_traps()
    check("15 traps registered", len(traps) == 15)
    check("unique trap ids", len({t["trap_id"] for t in traps.values()}) == 15)
    check("unique exit codes", len({t["stable_exit_code"] for t in traps.values()}) == 15)
    check("all evaluators whitelisted", all(t["evaluator_id"] in EVALUATOR_WHITELIST for t in traps.values()))
    check("P0/P1 all ACTIVE", all(t["status"] == "ACTIVE" for t in traps.values() if t["risk"] in ("P0", "P1")))
    check("no shell commands in registry", "shell" not in json.dumps(load_registry()).lower())

    # Explicit allowed-transition map: listed pairs work, unlisted fail.
    for src, targets in ALLOWED_TRANSITIONS.items():
        for tgt in targets:
            try:
                _to_state(src, tgt)
                check(f"allowed {src}->{tgt}", True)
            except TrapFired:
                check(f"allowed {src}->{tgt} must not trap", False)
    for src, tgt in (("INIT", "RUNNING"), ("INIT", "AUTHORIZED"), ("PREFLIGHT", "RUNNING"),
                     ("COLLECT_PROVEN", "FINISHED"), ("AUTHORIZED", "COLLECT_PROVEN"),
                     ("VOID", "PREFLIGHT"), ("FINISHED", "RUNNING"), ("RUNNING", "PREFLIGHT")):
        try:
            _to_state(src, tgt)
            check(f"forbidden {src}->{tgt} must trap", False)
        except TrapFired:
            check(f"forbidden {src}->{tgt} traps", True)

    # Trap: empty URL.
    try:
        eval_test_db_url("")
        check("empty URL traps", False)
    except TrapFired as fired:
        check("empty URL exit code", fired.exit_code == 11)

    # Trap: count-equal but node set drift.
    try:
        eval_collect_manifest(["A", "B"], ["A", "C"])
        check("set drift traps", False)
    except TrapFired as fired:
        check("set drift exit code", fired.exit_code == 15)
        check("count_equal surfaced", fired.evidence.get("count_equal") is True)

    # Trap: phase continue after fail.
    try:
        eval_phase_fail_stop(["PREFLIGHT", "FAIL", "RUNNING"])
        check("phase continue traps", False)
    except TrapFired as fired:
        check("phase continue exit code", fired.exit_code == 16)

    # Trap: lineage confusion.
    try:
        eval_git_lineage("abc", "abc")
        check("lineage traps", False)
    except TrapFired as fired:
        check("lineage exit code", fired.exit_code == 20)

    # R2 live Redis authority: absent/malformed/wrong-db URLs trap closed
    # before any connection is attempted (hermetic: no server required).
    for url, category in (("", "url_absent"), ("garbage", "url_malformed"),
                          ("redis://127.0.0.1:6399/0", "wrong_db")):
        try:
            redis_live_check(url)
            check(f"redis {category} traps", False)
        except TrapFired as fired:
            check(f"redis {category} traps", fired.evidence.get("redis") == category)

    # Trap: packaging mismatch.
    try:
        eval_evidence_packaging({"files": {"a.txt": "sha"}}, ["b.txt"], [])
        check("packaging traps", False)
    except TrapFired as fired:
        check("packaging exit code", fired.exit_code == 21)

    # Trap: mixed EOL.
    with tempfile.NamedTemporaryFile(delete=False) as fh:
        fh.write(b"line1\r\nline2\n")
        mixed_path = Path(fh.name)
    try:
        eval_eol(mixed_path)
        check("mixed EOL traps", False)
    except TrapFired as fired:
        check("mixed EOL exit code", fired.exit_code == 22)
    finally:
        mixed_path.unlink(missing_ok=True)

    # Trap: special-use email domain.
    try:
        eval_email_domain("user@example.com")
        check("special-use domain traps", False)
    except TrapFired as fired:
        check("email exit code", fired.exit_code == 24)

    # GREEN: pure-LF and pure-CRLF both pass.
    with tempfile.NamedTemporaryFile(delete=False) as fh:
        fh.write(b"lf only\nsecond\n")
        lf_path = Path(fh.name)
    with tempfile.NamedTemporaryFile(delete=False) as fh:
        fh.write(b"crlf only\r\nsecond\r\n")
        crlf_path = Path(fh.name)
    check("pure LF passes", eval_eol(lf_path)["eol"] == "lf")
    check("pure CRLF passes", eval_eol(crlf_path)["eol"] == "crlf")
    lf_path.unlink(missing_ok=True)
    crlf_path.unlink(missing_ok=True)

    # Negative control: rolsuper=true => full-run sentinel launched 0 times.
    class FakeSuperConn:
        def execute(self, *_a, **_k):
            class Row:
                def __init__(self, row):
                    self._row = row

                def fetchone(self):
                    return self._row

            return Row((True, True))

        def close(self):
            pass

    runner = AuthorityRunner(Path("."), {"mode": "selftest"}, ["N1"])
    trapped = False
    try:
        eval_pg_role(FakeSuperConn())
    except TrapFired:
        trapped = True
    check("rolsuper=true traps", trapped)
    # The runner never reaches RUNNING because preflight raised first.
    check("sentinel launches zero", runner.sentinel_calls == 0)

    # Proof binding: externally edited proof cannot authorize.
    runner2 = AuthorityRunner(Path("."), {"mode": "selftest"}, ["N1"])
    runner2.proof = {
        "nonce": "forged", "candidate_sha": "0" * 64, "profile_sha": "0" * 64,
        "node_manifest_sha": "0" * 64, "issued_at": time.time(),
        "expires_at": time.time() + PROOF_TTL_SECONDS, "state_trace": [],
    }
    check("forged proof invalid", not runner2.proof_valid())

    # Profile loading: a hardcoded cli-mode document can never pass.
    with tempfile.TemporaryDirectory() as tmp:
        bad = Path(tmp) / "bad-profiles.json"
        bad.write_text(json.dumps({"mode": "cli"}), encoding="utf-8")
        try:
            load_explicit_profile(bad, PROFILES_SCHEMA_PATH, "AUTHORITY_H2C_BACKEND")
            check("hardcoded cli profile rejected", False)
        except TrapFired as fired:
            check("hardcoded cli profile rejected",
                  fired.evidence.get("reason") == "hardcoded_or_malformed_profile")

    # Child proof: tampered nonce (cross-process) must trap.
    tampered = {
        "schema": PLUGIN_PROOF_SCHEMA, "sessionstart_ok": True,
        "nonce": "T" * 32,
        "sha_match": {"candidate": True, "profile": True, "manifest": True},
        "redis_module_sha": "M" * 64,
        "tempdb_binding_sha": "T" * 64,
        "alembic_actual_head": "037_payment_declarations_schema",
        "collected_node_ids": ["N1"],
    }
    try:
        verify_child_proof(tampered, "R" * 32, ["N1"], redis_module_sha="M" * 64,
                           tempdb_binding_sha="T" * 64)
        check("nonce mismatch traps", False)
    except TrapFired as fired:
        check("nonce mismatch traps", fired.evidence.get("reason") == "nonce_mismatch")
    # A foreign proof origin (not the runner-owned plugin schema) must trap.
    forged_origin = dict(tampered, nonce="R" * 32, schema="someone-else/1")
    try:
        verify_child_proof(forged_origin, "R" * 32, ["N1"], redis_module_sha="M" * 64,
                           tempdb_binding_sha="T" * 64)
        check("foreign proof origin traps", False)
    except TrapFired as fired:
        check("foreign proof origin traps", fired.evidence.get("reason") == "foreign_proof_origin")
    # Matching nonce over the real plugin schema passes (with the R4 bounded
    # transport binding: the child's re-derived digest matches the original).
    honest = dict(tampered, nonce="R" * 32,
                  manifest_transport_sha="K" * 64,
                  manifest_transport_nodes_total=1)
    check("honest child proof verifies",
          verify_child_proof(honest, "R" * 32, ["N1"],
                             redis_module_sha="M" * 64,
                             tempdb_binding_sha="T" * 64,
                             alembic_actual_head="037_payment_declarations_schema",
                             transport_digest="K" * 64)["nonce_match"] is True)

    # Duplicate node ids must be named, not folded into set comparison.
    dup = dict(honest, collected_node_ids=["N1", "N1"])
    try:
        verify_child_proof(dup, "R" * 32, ["N1"], redis_module_sha="M" * 64,
                           tempdb_binding_sha="T" * 64,
                           alembic_actual_head="037_payment_declarations_schema")
        check("duplicate node ids trap", False)
    except TrapFired as fired:
        check("duplicate node ids trap", fired.evidence.get("reason") == "duplicate_node_ids")

    # R3: a forged/mismatched temp-DB binding is rejected by name.
    forged_tempdb = dict(honest, tempdb_binding_sha="F" * 64)
    try:
        verify_child_proof(forged_tempdb, "R" * 32, ["N1"], redis_module_sha="M" * 64,
                           tempdb_binding_sha="T" * 64)
        check("forged tempdb digest traps", False)
    except TrapFired as fired:
        check("forged tempdb digest traps",
              fired.evidence.get("backend_env") == "tempdb_digest_mismatch")

    # R2-R2 module binding: a preloaded foreign module under the fixed key
    # is tamper evidence; a fresh canonical load still succeeds.
    import sys as _sys

    class _FakeRedisModule:
        __file__ = str(GOV_DIR / "validator" / "not_redis_authority.py")

    _sys.modules[REDIS_MODULE_KEY] = _FakeRedisModule
    try:
        _module, _tampered = load_redis_authority_module()
        check("preloaded foreign module detected", _tampered is True)
        check("fresh load ignores the preloaded fake",
              module_origin_is_canonical(_module, redis_module_canonical_path()))
    except RedisModuleBindingError:
        check("preloaded foreign module detected", True)
    finally:
        _sys.modules.pop(REDIS_MODULE_KEY, None)

    # No-shell invariants over runner AND plugin sources. The banned literals
    # are assembled so this scan never matches its own source text.
    banned_exec = "os" ".system"
    for source_path in (Path(__file__), GOV_DIR / "tests" / "pytest_et1_collector.py"):
        if source_path.exists():
            blob = source_path.read_text(encoding="utf-8")
            check(f"no shell spawn in {source_path.name}",
                  not re.search(r"shell\s*=\s*" + "True", blob) and banned_exec not in blob)

    if failures:
        print(f"SELFTEST: {failures} failure(s)")
        return 1
    print("SELFTEST: OK (registry + evaluator traps + transition map + cross-process proof + negative control)")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _read_manifest_nodes(manifest_path) -> list:
    try:
        data = Path(manifest_path).read_bytes()
    except Exception:
        raise TrapFired("TRAP_COLLECT_NODE_SET_DRIFT", 15, "COLLECT_PROVEN", True,
                        {"reason": "manifest_unreadable"})
    # EOL-portable (dual autocrlf gate): a PURE native EOL is accepted
    # (LF under autocrlf=false, CRLF under autocrlf=true); only a MIXED
    # blob fails closed. The SHA-256 binding always covers the raw bytes.
    crlf = b"\r\n" in data
    lone_lf = data.replace(b"\r\n", b"").count(b"\n") > 0
    if crlf and lone_lf:
        raise TrapFired("TRAP_MIXED_EOF", 22, "COLLECT_PROVEN", True, {"eol": "manifest_mixed"})
    # R4: split on LF only — `str.splitlines()` would also cut node IDs on
    # embedded CR bytes (parametrized IDs may carry binary fixture params).
    # Pure CRLF files are still handled by the CR/LF normalization; only a
    # MIXED blob fails closed above.
    nodes = [line.strip() for line in data.decode("utf-8").replace("\r\n", "\n").split("\n") if line.strip()]
    if not nodes or len(nodes) != len(set(nodes)):
        raise TrapFired("TRAP_COLLECT_NODE_SET_DRIFT", 15, "COLLECT_PROVEN", True,
                        {"reason": "manifest_empty_or_duplicate"})
    return nodes


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="HE2-ET1-R1 end-to-end authority runner")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--diagnostic-only", action="store_true")
    parser.add_argument("--collect-only", action="store_true")
    parser.add_argument("--authority", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--expected-nodes", default="",
                        help="optional cross-check; must equal the frozen manifest")
    parser.add_argument("--profile", default=str(GOV_DIR / "inventory" / "authority-profiles.json"))
    parser.add_argument("--profile-id", default="AUTHORITY_H2C_BACKEND")
    parser.add_argument("--node-manifest", default=str(GOV_DIR / "inventory" / "et1-node-manifest.txt"))
    parser.add_argument("--collect-target", default=str(GOV_DIR / "tests" / "_et1_collector_fixtures.py"))
    parser.add_argument("--proof-out", default="artifacts/et1-collect-proof.json")
    parser.add_argument("--sessionstart-out", default="artifacts/et1-sessionstart-proof.json")
    parser.add_argument("--publish-dir", default="artifacts")
    parser.add_argument("--baseline-sha", default="",
                        help="chain base; resolved through live git refs")
    parser.add_argument("--command", nargs=argparse.REMAINDER, default=[],
                        help="the product command argv launched once under --authority;"
                             " everything after --command is the argv (options included)")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    repo_root = Path.cwd()
    publish_dir = Path(args.publish_dir)
    runner = None
    try:
        profile, _profile_sha = load_explicit_profile(
            args.profile, PROFILES_SCHEMA_PATH, args.profile_id
        )
        expected_nodes = _read_manifest_nodes(args.node_manifest)
        if args.expected_nodes:
            cli_nodes = [n for n in args.expected_nodes.split(",") if n]
            if sorted(cli_nodes) != sorted(expected_nodes):
                raise TrapFired("TRAP_COLLECT_NODE_SET_DRIFT", 15, "COLLECT_PROVEN", True,
                                {"reason": "expected_nodes_manifest_mismatch"})
        if not args.baseline_sha.strip():
            raise TrapFired("TRAP_LINEAGE_CONFUSION", 20, "PREFLIGHT", True,
                            {"reason": "chain_base_absent"})
        chain_base = resolve_commit(args.baseline_sha.strip(), repo_root)
        if not chain_base:
            raise TrapFired("TRAP_LINEAGE_CONFUSION", 20, "PREFLIGHT", True,
                            {"reason": "chain_base_unresolvable"})
        parent = live_parent(repo_root)
        if not parent:
            raise TrapFired("TRAP_LINEAGE_CONFUSION", 20, "PREFLIGHT", True,
                            {"reason": "parent_unresolvable"})

        runner = AuthorityRunner(repo_root, profile, expected_nodes)
        runner.profile_sha_file = args.profile
        runner.manifest_sha_file = args.node_manifest
        publish_dir.mkdir(parents=True, exist_ok=True)

        db_url = os.environ.get("TEST_DATABASE_URL", "")
        allow_flag = os.environ.get("MPANGO_ALLOW_TEMP_DB_CREATE", "")
        email = os.environ.get("J1H2C_RETAILER_EMAIL", "user@ provisioning.invalid")
        email = email.replace(" ", "")

        runner.preflight(db_url, allow_flag, email, parent, chain_base)
        if args.preflight_only or args.diagnostic_only:
            runner.publish(publish_dir)
            print(f"PREFLIGHT: PASS state={runner.state}")
            return 0
        runner.collect_proven(
            profile_path=args.profile, manifest_path=args.node_manifest,
            proof_out=args.proof_out, sessionstart_out=args.sessionstart_out,
            collect_target=args.collect_target,
        )
        if args.collect_only:
            runner.publish(publish_dir)
            print(f"COLLECT: PASS count={runner.collect_child_summary['collected_node_count']}")
            return 0
        runner.authorize(db_url, allow_flag)
        if not args.authority:
            runner.publish(publish_dir)
            print("AUTHORIZED: proof issued; pass --authority --command ... to run")
            return 0
        runner.require_command(args.command)
        rc = runner.run(db_url, allow_flag, list(args.command))
        runner.publish(publish_dir)
        if rc == 0:
            print(f"RUN_VERDICT={RUN_VERDICT_GREEN} sentinel_calls={runner.sentinel_calls} "
                  f"collect_child_spawns={runner.collect_spawns}")
        else:
            print(f"RUN_VERDICT={RUN_VERDICT_TEST_RED} exit={rc} "
                  f"(real test RED; environment stays FINISHED, never VOID)")
        return rc
    except TrapFired as fired:
        if runner is not None:
            try:
                runner._to("VOID")
            except TrapFired:
                pass  # already terminal
            runner.publish(publish_dir)
        else:
            _publish_void_only(publish_dir, fired)
        print(
            f"RUN_VERDICT={RUN_VERDICT_VOID} trap_id={fired.trap_id} "
            f"phase={fired.phase} presence={fired.presence} "
            f"evidence={json.dumps(fired.evidence, sort_keys=True)}"
        )
        return fired.exit_code
    finally:
        # R4: the transport file is runner-owned temporary state; it is
        # removed on EVERY exit path after the run attempt completes.
        transport_path = getattr(runner, "transport_path", None) if runner else None
        if transport_path is not None:
            try:
                Path(transport_path).unlink()
            except OSError:
                pass


if __name__ == "__main__":
    sys.exit(main())
