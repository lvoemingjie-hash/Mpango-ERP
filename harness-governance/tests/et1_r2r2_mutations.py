"""HE2-ET1-R2-R2 mutation probes: module-origin and byte-binding weakenings.

Eight mutations attack the R2-R2 binding chain; each PROBE must report the
gate WEAKENED under the patched candidate and HOLD again after the
byte-exact restore. Probes are hermetic (threaded fake RESP server /
in-process fakes); any probe that touches the shared module's real bytes
restores them itself in `finally` and asserts the restoration.

Probe contract: probe(mod, ctx) -> bool, True == gate HELD (pristine),
False == weakness ESCAPED (patched candidate misbehaves).
"""

import hashlib
import importlib.util
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parents[1]
sys.path.insert(0, str(TESTS_DIR))
from test_authority_runner_r2 import FakeRedis, default_handlers, free_port  # noqa: E402

RUNNER_RELPATH = "harness-governance/validator/authority_runner.py"
PLUGIN_RELPATH = "harness-governance/tests/pytest_et1_collector.py"
SHARED_RELPATH = "harness-governance/validator/redis_authority.py"

SHARED_PATH = REPO_ROOT / SHARED_RELPATH


def _load_runner():
    sys.modules.pop("et1_r2r2_probe_runner", None)
    sys.modules.pop("et1_redis_authority", None)
    spec = importlib.util.spec_from_file_location(
        "et1_r2r2_probe_runner", str(REPO_ROOT / RUNNER_RELPATH)
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_plugin():
    sys.modules.pop("et1_r2r2_probe_plugin", None)
    sys.modules.pop("et1_redis_authority", None)
    spec = importlib.util.spec_from_file_location(
        "et1_r2r2_probe_plugin", str(REPO_ROOT / PLUGIN_RELPATH)
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakePreloaded:
    """What a preload injection would plant: permissive and foreign."""

    __file__ = "C:/attacker/redis_authority.py"

    @staticmethod
    def redis_live_check(_url):
        return {"redis": "ok"}

    @staticmethod
    def eval_redis(_url, _ep):
        return {"redis": "ok"}


def _seed_authorized(mod, module_sha):
    """Runner at COLLECT_PROVEN with valid bindings; authorize() runs in the
    probe with the DB seam stubbed (mirrors et1_r2_mutations seeding)."""
    import json
    import time

    profile_path = REPO_ROOT / "harness-governance" / "inventory" / "authority-profiles.json"
    manifest_path = REPO_ROOT / "harness-governance" / "inventory" / "et1-node-manifest.txt"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    sel = next(p for p in profile["profiles"] if p["profile_id"] == "AUTHORITY_H2C_BACKEND")
    r = mod.AuthorityRunner(REPO_ROOT, sel, ["tests/m.py::test_a"])
    r._to("PREFLIGHT")
    r._to("COLLECT_PROVEN")
    r.profile_sha_file = profile_path
    r.manifest_sha_file = manifest_path
    r.profile_sha = mod.sha256_file(profile_path)
    r.manifest_sha = mod.sha256_file(manifest_path)
    r.candidate_sha = mod.live_head(REPO_ROOT)
    r.redis_module_sha = module_sha
    r.proof = {
        "nonce": "P" * 32, "candidate_sha": r.candidate_sha,
        "profile_sha": r.profile_sha, "node_manifest_sha": r.manifest_sha,
        "issued_at": time.time(), "expires_at": time.time() + 900,
        "state_trace": list(r.trace),
    }
    r.original_nonce = "P" * 32

    class FakeConn:
        def execute(self, *a, **k):
            return type("R", (), {"fetchone": lambda s: (False, True)})()

        def close(self):
            pass

    return r, FakeConn


def _with_drifted_shared_bytes(action):
    """Mutate the shared module's real bytes, run `action`, then restore and
    prove byte-exact restoration."""
    snapshot = SHARED_PATH.read_bytes()
    try:
        SHARED_PATH.write_bytes(snapshot + b"\n# r2r2 probe drift\n")
        return action()
    finally:
        SHARED_PATH.write_bytes(snapshot)
        if SHARED_PATH.read_bytes() != snapshot:
            raise AssertionError("shared module bytes NOT restored")


# --- Probes (True == gate held) ----------------------------------------------


def probe_sysmodules_key_trust_restored(mod, ctx):
    """A preloaded fake under the fixed key must be DETECTED (and never
    returned); with key-trust restored, the fake answers and an unreachable
    Redis is accepted."""
    sys.modules["et1_redis_authority"] = _FakePreloaded
    try:
        try:
            mod.redis_live_check(f"redis://127.0.0.1:{free_port()}/15")
            return False  # the fake answered: bypass restored
        except mod.TrapFired as fired:
            return fired.evidence.get("redis") in (
                "module_preload_detected", "connect_failed",
            )
    finally:
        sys.modules.pop("et1_redis_authority", None)


def probe_canonical_path_validation_deleted(mod, ctx):
    """Planting a foreign preloaded module must set the tamper flag (the
    canonical-origin validation); deleting the validation hides it."""
    sys.modules["et1_redis_authority"] = _FakePreloaded
    try:
        try:
            _module, tampered = mod.load_redis_authority_module()
            return tampered is True
        except mod.RedisModuleBindingError:
            return True  # binding failure is also a strict detection
    finally:
        sys.modules.pop("et1_redis_authority", None)


def probe_runner_raw_digest_deleted(mod, ctx):
    expected = hashlib.sha256(SHARED_PATH.read_bytes()).hexdigest()
    try:
        return mod.redis_module_raw_digest() == expected
    except Exception:
        return False


def probe_child_recompute_deleted(mod_plugin, ctx):
    problems, _digest = mod_plugin._redis_module_binding(
        {"ET1_RUNNER_REDIS_MODULE_SHA": "F" * 64}
    )
    return "redis_module:bytes_drift" in problems


def probe_child_digest_self_compare(mod_plugin, ctx):
    problems, _digest = mod_plugin._redis_module_binding(
        {"ET1_RUNNER_REDIS_MODULE_SHA": "F" * 64}
    )
    return "redis_module:bytes_drift" in problems


def probe_runner_child_compare_deleted(mod, ctx):
    original = hashlib.sha256(SHARED_PATH.read_bytes()).hexdigest()
    child = {
        "schema": mod.PLUGIN_PROOF_SCHEMA, "sessionstart_ok": True,
        "nonce": "A" * 32, "redis_module_sha": "F" * 64,  # forged by child
        "sha_match": {"candidate": True, "profile": True, "manifest": True},
        "collected_node_ids": ["N1"],
    }
    try:
        mod.verify_child_proof(child, "A" * 32, ["N1"], redis_module_sha=original)
        return False  # forged child digest accepted
    except mod.TrapFired as fired:
        return fired.evidence.get("redis_module") == "module_digest_mismatch"


def _launch_after_drift(mod):
    """Seed a runner through authorize() with pristine shared-module bytes,
    then drift the bytes and attempt the launch. HELD = the JIT recheck
    blocks the launch with drift_at_launch and sentinel stays 0."""

    def probe():
        module_sha = hashlib.sha256(SHARED_PATH.read_bytes()).hexdigest()
        r, fake_conn_cls = _seed_authorized(mod, module_sha)
        saved = mod._pg_connect
        mod._pg_connect = lambda url: fake_conn_cls()
        try:
            r.authorize("stub", "1")  # bytes still pristine here
            snapshot = SHARED_PATH.read_bytes()
            try:
                SHARED_PATH.write_bytes(snapshot + b"\n# r2r2 probe drift\n")
                sentinel_before = r.sentinel_calls
                try:
                    r.run("stub", "1", [sys.executable, "-c", "pass"])
                    launched = r.sentinel_calls > sentinel_before
                except mod.TrapFired as fired:
                    launched = False
                    if fired.evidence.get("redis_module") != "drift_at_launch":
                        return False  # wrong trap: gate semantics changed
                return not launched  # held == drift blocked the launch
            finally:
                SHARED_PATH.write_bytes(snapshot)
                if SHARED_PATH.read_bytes() != snapshot:
                    raise AssertionError("shared module bytes NOT restored")
        finally:
            mod._pg_connect = saved

    return probe()


def probe_launch_jit_deleted(mod, ctx):
    return _launch_after_drift(mod)


def probe_launch_allowed_after_drift(mod, ctx):
    return _launch_after_drift(mod)


PROBES = {
    "sysmodules_key_trust_restored": probe_sysmodules_key_trust_restored,
    "canonical_path_validation_deleted": probe_canonical_path_validation_deleted,
    "runner_raw_digest_deleted": probe_runner_raw_digest_deleted,
    "child_recompute_deleted": probe_child_recompute_deleted,
    "child_digest_self_compare": probe_child_digest_self_compare,
    "runner_child_compare_deleted": probe_runner_child_compare_deleted,
    "launch_jit_deleted": probe_launch_jit_deleted,
    "launch_allowed_after_drift": probe_launch_allowed_after_drift,
}


# (name, target relpath, (anchor, replacement) canonical-LF patch, probe)
R2R2_MUTATIONS = [
    (
        "S221-sysmodules-key-trust-restored", RUNNER_RELPATH,
        (
            "    preloaded = sys.modules.get(REDIS_MODULE_KEY)\n"
            "    tampered = preloaded is not None and not module_origin_is_canonical(\n"
            "        preloaded, canonical\n"
            "    )\n"
            "    sys.modules.pop(REDIS_MODULE_KEY, None)  # evict: the cache is never reused",
            "    preloaded = sys.modules.get(REDIS_MODULE_KEY)\n"
            "    if preloaded is not None:\n"
            "        return preloaded, False\n"
            "    tampered = preloaded is not None and not module_origin_is_canonical(\n"
            "        preloaded, canonical\n"
            "    )\n"
            "    sys.modules.pop(REDIS_MODULE_KEY, None)  # evict: the cache is never reused",
        ),
        "sysmodules_key_trust_restored",
    ),
    (
        "S222-canonical-path-validation-deleted", RUNNER_RELPATH,
        (
            "    tampered = preloaded is not None and not module_origin_is_canonical(\n"
            "        preloaded, canonical\n"
            "    )",
            "    tampered = False and preloaded is not None and not module_origin_is_canonical(\n"
            "        preloaded, canonical\n"
            "    )",
        ),
        "canonical_path_validation_deleted",
    ),
    (
        "S223-runner-raw-digest-deleted", RUNNER_RELPATH,
        (
            "def redis_module_raw_digest() -> str:\n"
            '    """SHA-256 over the shared module\'s RAW FILE BYTES at the canonical\n'
            '    path (contract: the runner binds bytes, not module objects)."""\n'
            "    return hashlib.sha256(redis_module_canonical_path().read_bytes()).hexdigest()",
            "def redis_module_raw_digest() -> str:\n"
            '    """SHA-256 over the shared module\'s RAW FILE BYTES at the canonical\n'
            '    path (contract: the runner binds bytes, not module objects)."""\n'
            '    return ""',
        ),
        "runner_raw_digest_deleted",
    ),
    (
        "S224-child-recompute-deleted", PLUGIN_RELPATH,
        (
            '    runner_original = env.get("ET1_RUNNER_REDIS_MODULE_SHA", "") or ""\n'
            '    if not runner_original:\n'
            '        problems.append("redis_module:digest_missing")\n'
            '    elif recomputed != runner_original:\n'
            '        problems.append("redis_module:bytes_drift")',
            "    return problems, recomputed",
        ),
        "child_recompute_deleted",
    ),
    (
        "S225-child-digest-self-compare", PLUGIN_RELPATH,
        (
            "    elif recomputed != runner_original:",
            "    elif recomputed != recomputed:",
        ),
        "child_digest_self_compare",
    ),
    (
        "S226-runner-child-compare-deleted", RUNNER_RELPATH,
        (
            "    if not secrets.compare_digest(child_module_sha, redis_module_sha):\n"
            '        raise TrapFired("TRAP_COLLECT_NODE_SET_DRIFT", 15, "COLLECT_PROVEN", True,\n'
            '                        {"redis_module": "module_digest_mismatch"})',
            "    if False and secrets.compare_digest(child_module_sha, redis_module_sha):\n"
            '        raise TrapFired("TRAP_COLLECT_NODE_SET_DRIFT", 15, "COLLECT_PROVEN", True,\n'
            '                        {"redis_module": "module_digest_mismatch"})',
        ),
        "runner_child_compare_deleted",
    ),
    (
        "S227-launch-jit-deleted", RUNNER_RELPATH,
        (
            "            if current_module != self.redis_module_sha:\n"
            '                raise TrapFired("TRAP_SESSIONSTART_DRIFT", 18, "RUNNING", True,\n'
            '                                {"redis_module": "drift_at_launch"})',
            "            if False and current_module != self.redis_module_sha:\n"
            '                raise TrapFired("TRAP_SESSIONSTART_DRIFT", 18, "RUNNING", True,\n'
            '                                {"redis_module": "drift_at_launch"})',
        ),
        "launch_jit_deleted",
    ),
    (
        "S228-launch-allowed-after-drift", RUNNER_RELPATH,
        (
            "            if current_module != self.redis_module_sha:\n"
            '                raise TrapFired("TRAP_SESSIONSTART_DRIFT", 18, "RUNNING", True,\n'
            '                                {"redis_module": "drift_at_launch"})',
            "            if current_module != current_module:\n"
            '                raise TrapFired("TRAP_SESSIONSTART_DRIFT", 18, "RUNNING", True,\n'
            '                                {"redis_module": "drift_at_launch"})',
        ),
        "launch_allowed_after_drift",
    ),
]


def run_probe(probe_name):
    """Load the (possibly patched) candidate and evaluate one probe.

    Returns True when the gate HELD and False when the weakness ESCAPED;
    any unexpected exception counts as ESCAPED (fail loud)."""
    try:
        if probe_name in ("child_recompute_deleted", "child_digest_self_compare"):
            mod = _load_plugin()
        else:
            mod = _load_runner()
        return bool(PROBES[probe_name](mod, None))
    except Exception:
        return False
