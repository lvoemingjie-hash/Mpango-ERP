"""HE2-ET1-R1 end-to-end authority mutation probes.

Each E2E mutation patches the CANDIDATE runner or plugin source with a
specific weakening (restore self-compare, actual=expected, command=None,
hardcoded candidate/profile/lineage, arbitrary state jump, deleted child
plugin gate, ...) and a PROBE must then report the gate as WEAKENED
(behavior that the pristine candidate rejects becomes accepted). A probe
that still holds under the patch proves the mutation is not a real
weakening, which is itself reported as a gate failure.

Probes are pure in-process functions over the patched module: they never
need PG, Redis, or a pytest child. External seams (the DB driver connect,
subprocess launches) are stubbed at the module boundary only — the gate
logic under test runs unmodified.

Probe contract: probe(mod, ctx) -> bool, True == gate HELD (pristine),
False == weakness ESCAPED (patched candidate accepted what it must reject).
"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import hashlib
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parents[1]
GOV_DIR = REPO_ROOT / "harness-governance"
RUNNER_RELPATH = "harness-governance/validator/authority_runner.py"
PLUGIN_RELPATH = "harness-governance/tests/pytest_et1_collector.py"
SCHEMA_PATH = GOV_DIR / "schemas" / "authority-profiles.schema.json"

RUNNER_PROOF_SCHEMA = "harness-governance/pytest_et1_collector/2"


class FakeConn:
    """Stand-in for the PG connection seam (never the system under test)."""

    def execute(self, *_a, **_k):
        class _Cur:
            def fetchone(self_inner):
                return (False, True)

        return _Cur()

    def close(self):
        pass


class E2ECtx:
    """Sandbox: a real git repo plus gov-style files for live-SHA probes."""

    def __init__(self, tmp_root, with_plugin=True):
        self.root = Path(tmp_root)
        self.gov = self.root / "harness-governance"
        (self.gov / "tests").mkdir(parents=True, exist_ok=True)
        for args in (
            ["git", "init", "-q", str(self.root)],
            ["git", "-C", str(self.root), "config", "user.email", "gate@example.invalid"],
            ["git", "-C", str(self.root), "config", "user.name", "gate"],
        ):
            subprocess.run(args, check=True, capture_output=True)
        (self.root / "seed.txt").write_bytes(b"seed\n")
        subprocess.run(["git", "-C", str(self.root), "add", "seed.txt"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-qm", "seed"], check=True, capture_output=True)
        self.profile = self.gov / "authority-profiles.json"
        self.profile.write_bytes(b'{"schema_version": "1", "profiles": []}')
        self.manifest = self.gov / "et1-node-manifest.txt"
        self.manifest.write_bytes(b"tests/m.py::test_a\ntests/m.py::test_b\n")
        if with_plugin:
            (self.gov / "tests" / "pytest_et1_collector.py").write_bytes(
                (GOV_DIR / "tests" / "pytest_et1_collector.py").read_bytes()
            )


def _load_runner(patched_path):
    key = "et1_e2e_probe_runner"
    sys.modules.pop(key, None)
    spec = importlib.util.spec_from_file_location(key, str(patched_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_plugin(patched_path):
    key = "et1_e2e_probe_plugin"
    sys.modules.pop(key, None)
    spec = importlib.util.spec_from_file_location(key, str(patched_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _honest_child(nonce, collected):
    return {
        "schema": RUNNER_PROOF_SCHEMA,
        "sessionstart_ok": True,
        "nonce": nonce,
        "sha_match": {"candidate": True, "profile": True, "manifest": True},
        "redis_module_sha": "M" * 64,
        "collected_node_ids": list(collected),
    }


E2E_MODULE_SHA = "M" * 64


def _seed_collected(mod, ctx, manifest_sha=None, candidate_sha=None, expires_delta=None):
    """Runner carried to COLLECT_PROVEN with proof bindings matching the
    sandbox; probes then walk authorize() / run() through the real
    transitions. Callers stub mod._pg_connect for the authorize step."""
    r = mod.AuthorityRunner(ctx.root, {"profile_id": "PROBE"}, ["tests/m.py::test_a"])
    r._to("PREFLIGHT")
    r._to("COLLECT_PROVEN")
    r.profile_sha_file = ctx.profile
    r.manifest_sha_file = ctx.manifest
    r.profile_sha = mod.sha256_file(ctx.profile)
    r.manifest_sha = manifest_sha if manifest_sha is not None else mod.sha256_file(ctx.manifest)
    r.candidate_sha = candidate_sha if candidate_sha is not None else mod.live_head(ctx.root)
    issued = time.time()
    expires = issued + expires_delta if expires_delta is not None else issued + 900
    r.proof = {
        "nonce": "P" * 32,
        "candidate_sha": r.candidate_sha,
        "profile_sha": r.profile_sha,
        "node_manifest_sha": r.manifest_sha,
        "issued_at": issued,
        "expires_at": expires,
        "state_trace": list(r.trace),
    }
    r.original_nonce = "P" * 32
    return r


def _authorize_seeded(mod, r):
    """authorize() over the seeded runner with the DB seam stubbed."""
    original_connect = mod._pg_connect
    mod._pg_connect = lambda url: FakeConn()
    try:
        r.authorize("stub", "1")
    finally:
        mod._pg_connect = original_connect
    return r


# --- Probes (True == gate held) ----------------------------------------------


def probe_nonce_self_compare(mod, ctx):
    try:
        mod.verify_child_proof(_honest_child("A" * 32, ["N1"]), "B" * 32, ["N1"],
                               redis_module_sha=E2E_MODULE_SHA)
        return False  # tampered nonce accepted
    except mod.TrapFired as fired:
        return fired.evidence.get("reason") == "nonce_mismatch"


def probe_actual_equals_expected(mod, ctx):
    try:
        mod.verify_child_proof(_honest_child("A" * 32, ["N1", "N2"]), "A" * 32, ["N1", "N3"],
                               redis_module_sha=E2E_MODULE_SHA)
        return False  # drifted node set accepted
    except mod.TrapFired:
        return True


def probe_missing_command_allowed(mod, ctx):
    r = mod.AuthorityRunner(ctx.root, {}, [])
    try:
        r.require_command([])
        return False  # empty command accepted
    except mod.TrapFired:
        return True


def probe_foreign_proof_accepted(mod, ctx):
    forged = dict(_honest_child("A" * 32, ["N1"]), schema="someone-else/1")
    try:
        mod.verify_child_proof(forged, "A" * 32, ["N1"], redis_module_sha=E2E_MODULE_SHA)
        return False  # non-plugin proof accepted
    except mod.TrapFired as fired:
        return fired.evidence.get("reason") == "foreign_proof_origin"


def probe_state_jump_allowed(mod, ctx):
    try:
        mod._to_state("INIT", "RUNNING")
        return False  # forbidden transition accepted
    except mod.TrapFired:
        return True


def probe_sessionstart_gate_disabled(mod_plugin, ctx):
    result = mod_plugin.sessionstart_gate({})  # empty env: everything missing
    return result.get("ok") is False


def probe_duplicate_node_ids_accepted(mod, ctx):
    try:
        mod.verify_child_proof(_honest_child("A" * 32, ["N1", "N1"]), "A" * 32, ["N1"],
                               redis_module_sha=E2E_MODULE_SHA)
        return False
    except mod.TrapFired as fired:
        return fired.evidence.get("reason") == "duplicate_node_ids"


def probe_hardcoded_cli_profile_accepted(mod, ctx):
    bad = ctx.root / "cli-profiles.json"
    bad.write_bytes(json.dumps({"mode": "cli"}).encode("utf-8"))
    try:
        mod.load_explicit_profile(bad, SCHEMA_PATH, "AUTHORITY_H2C_BACKEND")
        return False  # hardcoded cli profile accepted
    except mod.TrapFired as fired:
        return fired.evidence.get("reason") == "hardcoded_or_malformed_profile"


def probe_publish_leaks_env_values(mod, ctx):
    sentinel = "TOPSECRETVALUE-PROBE"
    original = os.environ.get("TEST_DATABASE_URL")
    os.environ["TEST_DATABASE_URL"] = f"postgresql://u:{sentinel}@h/x"
    try:
        out = ctx.root / "publish"
        r = mod.AuthorityRunner(ctx.root, {}, [])
        r.publish(out)
        blob = (out / "authority-preflight.json").read_bytes()
        return sentinel.encode("utf-8") not in blob
    finally:
        if original is None:
            os.environ.pop("TEST_DATABASE_URL", None)
        else:
            os.environ["TEST_DATABASE_URL"] = original


def probe_sentinel_launches_twice(mod, ctx):
    r = _authorize_seeded(mod, _seed_collected(mod, ctx))
    real_run = mod.subprocess.run
    count = {"n": 0}

    def counting_run(cmd, **kwargs):
        if set(kwargs) != {"shell"}:
            return real_run(cmd, **kwargs)  # git/other calls: passthrough
        count["n"] += 1
        return real_run(cmd, **kwargs)

    mod.subprocess.run = counting_run
    original_connect = mod._pg_connect
    mod._pg_connect = lambda url: FakeConn()
    try:
        rc = r.run("stub", "1", [sys.executable, "-c", "pass"])
    finally:
        mod.subprocess.run = real_run
        mod._pg_connect = original_connect
    return count["n"] == 1 and r.sentinel_calls == 1 and rc == 0


def probe_nonzero_exit_classified_void(mod, ctx):
    r = _authorize_seeded(mod, _seed_collected(mod, ctx))
    original_connect = mod._pg_connect
    mod._pg_connect = lambda url: FakeConn()
    try:
        rc = r.run("stub", "1", [sys.executable, "-c", "import sys; sys.exit(3)"])
    finally:
        mod._pg_connect = original_connect
    return rc == 3 and r.state == "FINISHED"


def probe_manifest_bytes_binding_dropped(mod, ctx):
    r = _seed_collected(mod, ctx, manifest_sha="0" * 64)
    try:
        r.authorize("stub", "1")
        return False  # manifest no longer bound to file bytes
    except mod.TrapFired as fired:
        return fired.evidence.get("reason") == "manifest_drift"


def probe_proof_expiry_dropped(mod, ctx):
    r = _seed_collected(mod, ctx, expires_delta=-1.0)
    try:
        r.authorize("stub", "1")
        return False  # expired proof accepted
    except mod.TrapFired as fired:
        return fired.evidence.get("reason") == "proof_expired"


def probe_candidate_not_live(mod, ctx):
    r = _seed_collected(mod, ctx, candidate_sha="f" * 40)
    try:
        r.authorize("stub", "1")
        return False  # hardcoded candidate accepted
    except mod.TrapFired as fired:
        return fired.evidence.get("reason") == "candidate_drift"


def probe_child_plugin_deletion_accepted(mod, ctx):
    import shutil

    empty_dir = tempfile.mkdtemp(prefix="et1e2e-noplug-")
    try:
        empty_ctx = E2ECtx(empty_dir, with_plugin=False)
        try:
            mod.ensure_plugin_available(empty_ctx.gov)
            return False  # deleted plugin accepted
        except mod.TrapFired:
            return True
        except OSError:
            return False  # fails open with an unregistered crash instead of a trap
    finally:
        shutil.rmtree(empty_dir, ignore_errors=True)


# --- Mutation table -----------------------------------------------------------
# (name, target relpath, (anchor, replacement) canonical-LF patch, probe name)

E2E_MUTATIONS = [
    (
        "X01-restore-nonce-self-compare", RUNNER_RELPATH,
        (
            "    if not secrets.compare_digest(child_nonce, original_nonce):",
            "    if not secrets.compare_digest(child_nonce, child_nonce):",
        ),
        "nonce_self_compare",
    ),
    (
        "X02-collect-actual-equals-expected", RUNNER_RELPATH,
        (
            "    if sorted(actual_nodes) != sorted(expected_nodes):",
            "    if False and sorted(actual_nodes) != sorted(expected_nodes):",
        ),
        "actual_equals_expected",
    ),
    (
        "X03-authority-missing-command-allowed", RUNNER_RELPATH,
        (
            "        if not command or not isinstance(command, list) or not any(str(c).strip() for c in command):",
            "        if False and (not command or not isinstance(command, list) or not any(str(c).strip() for c in command)):",
        ),
        "missing_command_allowed",
    ),
    (
        "X04-foreign-child-proof-accepted", RUNNER_RELPATH,
        (
            '    if child.get("schema") != PLUGIN_PROOF_SCHEMA:',
            '    if False and child.get("schema") != PLUGIN_PROOF_SCHEMA:',
        ),
        "foreign_proof_accepted",
    ),
    (
        "X05-state-machine-jump-allowed", RUNNER_RELPATH,
        (
            "    if target not in ALLOWED_TRANSITIONS.get(current, frozenset()):",
            "    if False and target not in ALLOWED_TRANSITIONS.get(current, frozenset()):",
        ),
        "state_jump_allowed",
    ),
    (
        "X06-sessionstart-gate-disabled", PLUGIN_RELPATH,
        (
            '    return {\n        "ok": not problems,',
            '    return {\n        "ok": True,',
        ),
        "sessionstart_gate_disabled",
    ),
    (
        "X07-duplicate-node-ids-accepted", RUNNER_RELPATH,
        (
            "    if len(collected) != len(set(collected)):",
            "    if False and len(collected) != len(set(collected)):",
        ),
        "duplicate_node_ids_accepted",
    ),
    (
        "X08-hardcoded-cli-profile-accepted", RUNNER_RELPATH,
        (
            '    if doc.get("mode") == "cli" or not isinstance(doc.get("profiles"), list):',
            '    if False and (doc.get("mode") == "cli" or not isinstance(doc.get("profiles"), list)):',
        ),
        "hardcoded_cli_profile_accepted",
    ),
    (
        "X09-publish-leaks-env-values", RUNNER_RELPATH,
        (
            '                "TEST_DATABASE_URL_set": bool(os.environ.get("TEST_DATABASE_URL", "").strip()),',
            '                "TEST_DATABASE_URL_set": os.environ.get("TEST_DATABASE_URL", ""),',
        ),
        "publish_leaks_env_values",
    ),
    (
        "X10-sentinel-launches-more-than-once", RUNNER_RELPATH,
        (
            "        result = subprocess.run(command, shell=False)",
            "        result = subprocess.run(command, shell=False)\n"
            "        subprocess.run(command, shell=False)",
        ),
        "sentinel_launches_twice",
    ),
    (
        "X11-nonzero-exit-misclassified-void", RUNNER_RELPATH,
        (
            "        self.command_exit_code = result.returncode\n        self._to(\"FINISHED\")\n        return result.returncode",
            "        self.command_exit_code = result.returncode\n"
            "        self._to(\"VOID\" if result.returncode else \"FINISHED\")\n"
            "        return result.returncode",
        ),
        "nonzero_exit_classified_void",
    ),
    (
        "X12-manifest-bytes-binding-dropped", RUNNER_RELPATH,
        (
            "        if self.manifest_sha_file is not None:\n"
            "            if sha256_file(self.manifest_sha_file) != self.manifest_sha:",
            "        if self.manifest_sha_file is not None:\n"
            "            if False and sha256_file(self.manifest_sha_file) != self.manifest_sha:",
        ),
        "manifest_bytes_binding_dropped",
    ),
    (
        "X13-proof-expiry-check-dropped", RUNNER_RELPATH,
        (
            '        if time.time() > self.proof["expires_at"]:\n'
            '            raise TrapFired("TRAP_SESSIONSTART_DRIFT", 18, "AUTHORIZED", True, {"reason": "proof_expired"})',
            '        if False and time.time() > self.proof["expires_at"]:\n'
            '            raise TrapFired("TRAP_SESSIONSTART_DRIFT", 18, "AUTHORIZED", True, {"reason": "proof_expired"})',
        ),
        "proof_expiry_dropped",
    ),
    (
        "X14-candidate-sha-not-live-git", RUNNER_RELPATH,
        (
            "        if not current or current != self.candidate_sha:",
            "        if False and (not current or current != self.candidate_sha):",
        ),
        "candidate_not_live",
    ),
    (
        "X15-child-plugin-deletion-accepted", RUNNER_RELPATH,
        (
            "    if not plugin_file.is_file():",
            "    if False and not plugin_file.is_file():",
        ),
        "child_plugin_deletion_accepted",
    ),
]

PROBES = {
    "nonce_self_compare": probe_nonce_self_compare,
    "actual_equals_expected": probe_actual_equals_expected,
    "missing_command_allowed": probe_missing_command_allowed,
    "foreign_proof_accepted": probe_foreign_proof_accepted,
    "state_jump_allowed": probe_state_jump_allowed,
    "sessionstart_gate_disabled": probe_sessionstart_gate_disabled,
    "duplicate_node_ids_accepted": probe_duplicate_node_ids_accepted,
    "hardcoded_cli_profile_accepted": probe_hardcoded_cli_profile_accepted,
    "publish_leaks_env_values": probe_publish_leaks_env_values,
    "sentinel_launches_twice": probe_sentinel_launches_twice,
    "nonzero_exit_classified_void": probe_nonzero_exit_classified_void,
    "manifest_bytes_binding_dropped": probe_manifest_bytes_binding_dropped,
    "proof_expiry_dropped": probe_proof_expiry_dropped,
    "candidate_not_live": probe_candidate_not_live,
    "child_plugin_deletion_accepted": probe_child_plugin_deletion_accepted,
}


def run_probe(probe_name, runner_path=None, plugin_path=None):
    """Load the (possibly patched) candidate and evaluate one probe.

    Returns True when the gate HELD (probe satisfied) and False when the
    weakness ESCAPED. Any unexpected exception counts as ESCAPED (fail loud).
    """
    runner_path = Path(runner_path) if runner_path else REPO_ROOT / RUNNER_RELPATH
    plugin_path = Path(plugin_path) if plugin_path else REPO_ROOT / PLUGIN_RELPATH
    try:
        with tempfile.TemporaryDirectory(prefix="et1e2e-probe-") as tmp:
            ctx = E2ECtx(tmp)
            if probe_name == "sessionstart_gate_disabled":
                mod = _load_plugin(plugin_path)
            else:
                mod = _load_runner(runner_path)
            return bool(PROBES[probe_name](mod, ctx))
    except Exception:
        return False
