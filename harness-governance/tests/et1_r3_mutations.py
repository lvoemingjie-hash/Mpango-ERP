"""HE2-ET1-R3 mutation probes: backend CWD / temp-DB authority weakenings.

Each mutation patches the candidate (shared backend-env module, runner, or
child plugin) and a hermetic PROBE must report the gate WEAKENED. Restores
are byte-exact (gate machinery).

Probe contract: probe(mod, ctx) -> bool, True == gate HELD, False ==
weakness ESCAPED. Any unexpected exception counts as ESCAPED.
"""

import importlib.util
import os
import sys
import tempfile
import time
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parents[1]
RUNNER_RELPATH = "harness-governance/validator/authority_runner.py"
PLUGIN_RELPATH = "harness-governance/tests/pytest_et1_collector.py"
SHARED_RELPATH = "harness-governance/validator/backend_env_authority.py"

SHARED_PATH = REPO_ROOT / SHARED_RELPATH

LEGAL_URL = "postgresql://ci_gate@127.0.0.1:15455/test_ci_gate"


def _load_runner():
    sys.modules.pop("et1_r3_probe_runner", None)
    sys.modules.pop("et1_backend_env_authority", None)
    spec = importlib.util.spec_from_file_location(
        "et1_r3_probe_runner", str(REPO_ROOT / RUNNER_RELPATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_plugin():
    sys.modules.pop("et1_r3_probe_plugin", None)
    sys.modules.pop("et1_backend_env_authority", None)
    spec = importlib.util.spec_from_file_location(
        "et1_r3_probe_plugin", str(REPO_ROOT / PLUGIN_RELPATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_shared():
    sys.modules.pop("et1_r3_probe_shared", None)
    spec = importlib.util.spec_from_file_location(
        "et1_r3_probe_shared", str(REPO_ROOT / SHARED_RELPATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- Probes (True == gate held) ----------------------------------------------


def probe_cwd_check_deleted(mod_shared, ctx):
    with tempfile.TemporaryDirectory() as tmp:
        non_backend = Path(tmp) / "backendX"
        non_backend.mkdir()
        try:
            facts = mod_shared.backend_env_facts(
                LEGAL_URL, "testing", "15432,5432,15455", "", non_backend)
            return False  # non-backend CWD accepted
        except mod_shared.BackendEnvAuthorityError as err:
            return err.category == "cwd_not_canonical"


def probe_env_check_deleted(mod_shared, ctx):
    try:
        facts = mod_shared.backend_env_facts(
            LEGAL_URL, "production", "15432,5432,15455", "",
            REPO_ROOT / "backend")
        return False  # invalid MPANGO_ENV accepted
    except mod_shared.BackendEnvAuthorityError as err:
        return err.category == "mpango_env_invalid"


def probe_db_name_check_deleted(mod_shared, ctx):
    try:
        facts = mod_shared.backend_env_facts(
            "postgresql://ci_gate@127.0.0.1:15455/mpango_erp_test",
            "testing", "15432,5432,15455", "", REPO_ROOT / "backend")
        return False  # unsafe DB name accepted
    except mod_shared.BackendEnvAuthorityError as err:
        return err.category == "db_name_unsafe"


def probe_port_membership_deleted(mod_shared, ctx):
    try:
        facts = mod_shared.backend_env_facts(
            LEGAL_URL, "testing", "5432,9999", "", REPO_ROOT / "backend")
        return False  # port outside allowlist accepted
    except mod_shared.BackendEnvAuthorityError as err:
        return err.category == "db_port_not_allowed"


def probe_host_check_deleted(mod_shared, ctx):
    try:
        facts = mod_shared.backend_env_facts(
            "postgresql://ci_gate@10.0.0.8:15455/test_ci_gate",
            "testing", "15432,5432,15455", "", REPO_ROOT / "backend")
        return False  # non-loopback, non-allowlisted host accepted
    except mod_shared.BackendEnvAuthorityError as err:
        return err.category == "host_not_allowed"


def probe_child_benv_recheck_deleted(mod_plugin, ctx):
    """The child sessionstart gate must surface benv:* problems for an
    illegal temp-DB configuration; deleting the recheck hides them."""
    gate = mod_plugin.sessionstart_gate({
        "TEST_DATABASE_URL": LEGAL_URL,
        "MPANGO_ENV": "production",  # invalid env must be flagged
        "MPANGO_TEMP_DB_ALLOWED_PORTS": "15432,5432,15455",
        "MPANGO_TEMP_DB_ALLOWED_HOSTS": "",
    })
    problems = gate.get("problems", [])
    return any(p.startswith("benv:") for p in problems)


def probe_runner_child_tempdb_compare_deleted(mod, ctx):
    """A forged child tempdb digest must be rejected by the runner."""
    child = {
        "schema": mod.PLUGIN_PROOF_SCHEMA, "sessionstart_ok": True,
        "nonce": "A" * 32, "redis_module_sha": "M" * 64,
        "tempdb_binding_sha": "F" * 64,  # forged by child
        "sha_match": {"candidate": True, "profile": True, "manifest": True},
        "collected_node_ids": ["N1"],
    }
    try:
        mod.verify_child_proof(child, "A" * 32, ["N1"], redis_module_sha="M" * 64,
                               tempdb_binding_sha="T" * 64)
        return False  # forged digest accepted
    except mod.TrapFired as fired:
        return fired.evidence.get("backend_env") == "tempdb_digest_mismatch"


def probe_launch_env_drift_deleted(mod, ctx):
    """Env drift between authorize and launch must VOID; deleting the JIT
    recheck lets the command launch anyway."""
    with tempfile.TemporaryDirectory() as tmp:
        backend = Path(tmp) / "backend"
        backend.mkdir()
        saved = {k: os.environ.get(k) for k in (
            "TEST_DATABASE_URL", "MPANGO_ENV",
            "MPANGO_TEMP_DB_ALLOWED_PORTS", "MPANGO_TEMP_DB_ALLOWED_HOSTS")}
        os.environ["TEST_DATABASE_URL"] = LEGAL_URL
        os.environ["MPANGO_ENV"] = "testing"
        os.environ["MPANGO_TEMP_DB_ALLOWED_PORTS"] = "15432,5432,15455"
        os.environ["MPANGO_TEMP_DB_ALLOWED_HOSTS"] = ""
        try:
            r = mod.AuthorityRunner(REPO_ROOT, {}, ["x"])
            r._to("PREFLIGHT")
            r.bind_backend_env_module()
            r._require_bound_backend_env_module()
            r._enforce_backend_env_authority()
            r._to("COLLECT_PROVEN")
            r._to("AUTHORIZED")
            # seed a fully valid proof so run() reaches the JIT drift gate
            r.profile_sha_file = str(REPO_ROOT / "harness-governance/inventory/authority-profiles.json")
            r.manifest_sha_file = str(REPO_ROOT / "harness-governance/inventory/et1-node-manifest.txt")
            r.profile_sha = mod.sha256_file(r.profile_sha_file)
            r.manifest_sha = mod.sha256_file(r.manifest_sha_file)
            r.candidate_sha = mod.live_head(REPO_ROOT)
            r.original_nonce = "N" * 32
            import time as _time
            r.proof = {"nonce": "N" * 32, "candidate_sha": r.candidate_sha,
                       "profile_sha": r.profile_sha,
                       "node_manifest_sha": r.manifest_sha,
                       "issued_at": _time.time(), "expires_at": _time.time() + 900,
                       "state_trace": list(r.trace)}
            # R4: bind a real canonical transport file so the transport JIT
            # gate sees pristine bytes (the probe targets backend-env drift).
            _fd, _transport_name = tempfile.mkstemp(prefix="et1r3-transport-")
            with os.fdopen(_fd, "wb") as _fh:
                _fh.write(mod.canonical_transport_bytes(["x"]))
            r.transport_path = Path(_transport_name)
            r.transport_digest = mod.manifest_transport_digest(
                mod.canonical_transport_bytes(["x"]))
            saved_connect = mod._pg_connect
            mod._pg_connect = lambda url: type(
                "C", (), {"execute": lambda s, *a: type(
                    "R", (), {"fetchone": lambda s2: (False, True)})(),
                    "close": lambda s: None})()
            try:
                os.environ["TEST_DATABASE_URL"] = (
                    "postgresql://ci_gate@127.0.0.1:15455/test_drifted")
                sentinel_before = r.sentinel_calls
                try:
                    r.run("stub", "1", [sys.executable, "-c", "pass"])
                    launched = r.sentinel_calls > sentinel_before
                except mod.TrapFired as fired:
                    launched = False
                    if fired.evidence.get("backend_env") != "drift_at_launch":
                        return False  # wrong trap: gate semantics changed
                return not launched  # held == drift blocked the launch
            finally:
                mod._pg_connect = saved_connect
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


PROBES = {
    "cwd_check_deleted": probe_cwd_check_deleted,
    "env_check_deleted": probe_env_check_deleted,
    "db_name_check_deleted": probe_db_name_check_deleted,
    "port_membership_deleted": probe_port_membership_deleted,
    "host_check_deleted": probe_host_check_deleted,
    "child_benv_recheck_deleted": probe_child_benv_recheck_deleted,
    "runner_child_tempdb_compare_deleted": probe_runner_child_tempdb_compare_deleted,
    "launch_env_drift_deleted": probe_launch_env_drift_deleted,
}


# (name, target relpath, (anchor, replacement) canonical-LF patch, probe)
R3_MUTATIONS = [
    (
        "T221-backend-cwd-check-deleted", SHARED_RELPATH,
        (
            '    if (\n        not cwd.exists()\n        or cwd.name != "backend"',
            '    if False and (\n        not cwd.exists()\n        or cwd.name != "backend"',
        ),
        "cwd_check_deleted",
    ),
    (
        "T222-mpango-env-check-deleted", SHARED_RELPATH,
        (
            "    if env not in MPANGO_ENV_ALLOWED:",
            "    if False and env not in MPANGO_ENV_ALLOWED:",
        ),
        "env_check_deleted",
    ),
    (
        "T223-db-name-check-deleted", SHARED_RELPATH,
        (
            "    if not db_name or not DB_NAME_PATTERN.fullmatch(db_name):",
            "    if False:",
        ),
        "db_name_check_deleted",
    ),
    (
        "T224-port-membership-deleted", SHARED_RELPATH,
        (
            "    if port not in ports:",
            "    if False and port not in ports:",
        ),
        "port_membership_deleted",
    ),
    (
        "T225-host-check-deleted", SHARED_RELPATH,
        (
            "    if host not in LOOPBACK_HOSTS and host not in hosts:",
            "    if False and host not in LOOPBACK_HOSTS and host not in hosts:",
        ),
        "host_check_deleted",
    ),
    (
        "T226-child-benv-recheck-deleted", PLUGIN_RELPATH,
        (
            "    benv_problems, tempdb_binding_sha = _backend_env_recheck_problems(env)\n"
            "    problems.extend(benv_problems)",
            "    benv_problems, tempdb_binding_sha = [], \"\"",
        ),
        "child_benv_recheck_deleted",
    ),
    (
        "T227-runner-child-tempdb-compare-deleted", RUNNER_RELPATH,
        (
            "    if not secrets.compare_digest(child_tempdb, tempdb_binding_sha):\n"
            '        raise TrapFired("TRAP_COLLECT_NODE_SET_DRIFT", 15, "COLLECT_PROVEN", True,\n'
            '                        {"backend_env": "tempdb_digest_mismatch"})',
            "    if False and secrets.compare_digest(child_tempdb, tempdb_binding_sha):\n"
            '        raise TrapFired("TRAP_COLLECT_NODE_SET_DRIFT", 15, "COLLECT_PROVEN", True,\n'
            '                        {"backend_env": "tempdb_digest_mismatch"})',
        ),
        "runner_child_tempdb_compare_deleted",
    ),
    (
        "T228-launch-env-drift-deleted", RUNNER_RELPATH,
        (
            "        if self.tempdb_binding_sha is not None:\n"
            "            if self._current_tempdb_binding() != self.tempdb_binding_sha:\n"
            '                raise TrapFired("TRAP_SESSIONSTART_DRIFT", 18, "RUNNING", True,\n'
            '                                {"backend_env": "drift_at_launch"})',
            "        if False and self.tempdb_binding_sha is not None:\n"
            "            if self._current_tempdb_binding() != self.tempdb_binding_sha:\n"
            '                raise TrapFired("TRAP_SESSIONSTART_DRIFT", 18, "RUNNING", True,\n'
            '                                {"backend_env": "drift_at_launch"})',
        ),
        "launch_env_drift_deleted",
    ),
]


def run_probe(probe_name):
    """Load the (possibly patched) candidate and evaluate one probe.

    Returns True when the gate HELD and False when the weakness ESCAPED;
    any unexpected exception counts as ESCAPED (fail loud)."""
    try:
        if probe_name in ("child_benv_recheck_deleted",):
            mod = _load_plugin()
        elif probe_name in ("runner_child_tempdb_compare_deleted",
                            "launch_env_drift_deleted"):
            mod = _load_runner()
        else:
            mod = _load_shared()
        return bool(PROBES[probe_name](mod, None))
    except Exception:
        return False
