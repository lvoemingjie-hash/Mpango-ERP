"""HE2-ET1-R2-R2 truth tests: module-origin and cross-process byte binding.

Counterexamples (contract section 三). Every VOID case asserts state/sentinel
where a runner drives it, sanitized evidence (no paths/secrets), and — where
candidate bytes are touched — byte-exact restoration.

  A  preloaded fake under the fixed sys.modules key  -> VOID, command=0
  B  sitecustomize preload in a REAL child process   -> child fail-closed,
     runner VOID, command=0
  C  module bytes drift preflight->child             -> child flags drift
  D  module bytes drift child->launch                -> JIT VOID, command=0
  E  wrong module __file__/origin                    -> origin untrusted
  F  missing spec/loader                             -> origin untrusted
  G  child self-reports forged digest                -> runner rejects
  H  exact path + exact bytes + fresh PG16/Redis7    -> GREEN, command once
     (H is executed by run_e2e_redis_cases.py RL1 on the live stack; this
     file proves the binding arithmetic that H depends on)
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parents[1]
GOV_DIR = REPO_ROOT / "harness-governance"
RUNNER_PATH = GOV_DIR / "validator" / "authority_runner.py"
PLUGIN_PATH = GOV_DIR / "tests" / "pytest_et1_collector.py"
SHARED_PATH = GOV_DIR / "validator" / "redis_authority.py"
MANIFEST = GOV_DIR / "inventory" / "et1-node-manifest.txt"
PROFILE = GOV_DIR / "inventory" / "authority-profiles.json"
COLLECT = GOV_DIR / "tests" / "_et1_collector_fixtures.py"


def _load(path, key):
    sys.modules.pop("et1_redis_authority", None)
    spec = importlib.util.spec_from_file_location(key, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seed_authorized(mod, module_sha):
    """Runner at AUTHORIZED with proof bindings valid except module state."""
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    sel = next(p for p in profile["profiles"] if p["profile_id"] == "AUTHORITY_H2C_BACKEND")
    r = mod.AuthorityRunner(REPO_ROOT, sel, ["x"])
    r._to("PREFLIGHT")
    r._to("COLLECT_PROVEN")
    r.profile_sha_file = PROFILE
    r.manifest_sha_file = MANIFEST
    r.profile_sha = mod.sha256_file(PROFILE)
    r.manifest_sha = mod.sha256_file(MANIFEST)
    r.candidate_sha = mod.live_head(REPO_ROOT)
    r.redis_module_sha = module_sha
    import time

    r.proof = {
        "nonce": "P" * 32, "candidate_sha": r.candidate_sha,
        "profile_sha": r.profile_sha, "node_manifest_sha": r.manifest_sha,
        "issued_at": time.time(), "expires_at": time.time() + 900,
        "state_trace": list(r.trace),
    }
    r.original_nonce = "P" * 32
    return r


class PreloadInjectionTests(unittest.TestCase):
    """Counterexamples A and E/F: preloaded/foreign/origin-broken modules."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load(RUNNER_PATH, "he2et1_r2r2_runner")

    def tearDown(self):
        sys.modules.pop("et1_redis_authority", None)

    def test_a_preloaded_foreign_module_is_tamper_evidence(self):
        class FakeRedisAuthority:  # what an attacker would preload
            __file__ = str(GOV_DIR / "validator" / "not_redis_authority.py")

        sys.modules["et1_redis_authority"] = FakeRedisAuthority
        # the FIRST fresh load detects the foreign preloaded entry...
        module, tampered = self.mod.load_redis_authority_module()
        self.assertTrue(tampered)
        # ...evicts it, and the module under the key is the REAL one.
        self.assertTrue(self.mod.module_origin_is_canonical(
            module, self.mod.redis_module_canonical_path()))
        self.assertIsNot(sys.modules["et1_redis_authority"], FakeRedisAuthority)
        # a runner binding in this state VOIDs at preflight: command=0
        runner = self.mod.AuthorityRunner(REPO_ROOT, {}, [])
        runner.bind_redis_module()
        runner.redis_module_tampered = True  # tamper recorded at first load
        with self.assertRaises(self.mod.TrapFired) as ctx:
            runner._require_bound_redis_module()
        self.assertEqual(ctx.exception.evidence.get("redis"), "module_preload_detected")
        self.assertEqual(runner.sentinel_calls, 0)

    def test_a_preloaded_fake_cannot_accept_unreachable_redis(self):
        class FakeRedisAuthority:
            __file__ = str(GOV_DIR / "validator" / "elsewhere.py")

            @staticmethod
            def redis_live_check(_url):
                return {"redis": "ok"}

            @staticmethod
            def eval_redis(_url, _ep):
                return {"redis": "ok"}

        sys.modules["et1_redis_authority"] = FakeRedisAuthority
        with self.assertRaises(self.mod.TrapFired) as ctx:
            self.mod.redis_live_check(f"redis://127.0.0.1:{self.mod and 63999}/15")
        self.assertEqual(ctx.exception.evidence.get("redis"), "module_preload_detected")

    def test_e_wrong_module_file_is_origin_untrusted(self):
        module, _ = self.mod.load_redis_authority_module()
        canonical = self.mod.redis_module_canonical_path()
        self.assertFalse(self.mod.module_origin_is_canonical(
            type("M", (), {"__file__": str(GOV_DIR / "tests" / "pytest_et1_collector.py"),
                           "__spec__": None})(),
            canonical,
        ))
        self.assertTrue(self.mod.module_origin_is_canonical(module, canonical))

    def test_f_missing_spec_and_loader_is_origin_untrusted(self):
        module, _ = self.mod.load_redis_authority_module()
        canonical = self.mod.redis_module_canonical_path()
        specless = type("M", (), {"__file__": str(canonical), "__spec__": None})()
        self.assertFalse(self.mod.module_origin_is_canonical(specless, canonical))
        # a module with neither __file__ nor spec
        self.assertFalse(self.mod.module_origin_is_canonical(type("M", (), {}), canonical))


class ByteBindingTests(unittest.TestCase):
    """Counterexamples C, D, G: raw-byte digest drift and forged digests."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load(RUNNER_PATH, "he2et1_r2r2_byte_runner")

    def setUp(self):
        self._snapshot = SHARED_PATH.read_bytes()

    def tearDown(self):
        SHARED_PATH.write_bytes(self._snapshot)
        self.assertEqual(
            hashlib.sha256(SHARED_PATH.read_bytes()).hexdigest(),
            hashlib.sha256(self._snapshot).hexdigest(),
        )
        sys.modules.pop("et1_redis_authority", None)

    def test_c_drift_before_child_is_flagged_by_child_binding(self):
        plugin = _load(PLUGIN_PATH, "he2et1_r2r2_byte_plugin")
        original = hashlib.sha256(self._snapshot).hexdigest()
        SHARED_PATH.write_bytes(self._snapshot + b"\n# drifted\n")
        problems, recomputed = plugin._redis_module_binding(
            {"ET1_RUNNER_REDIS_MODULE_SHA": original}
        )
        self.assertIn("redis_module:bytes_drift", problems)
        self.assertNotEqual(recomputed, original)

    def test_c_child_binding_green_when_bytes_unchanged(self):
        plugin = _load(PLUGIN_PATH, "he2et1_r2r2_byte_plugin_g")
        original = hashlib.sha256(self._snapshot).hexdigest()
        problems, recomputed = plugin._redis_module_binding(
            {"ET1_RUNNER_REDIS_MODULE_SHA": original}
        )
        self.assertEqual([p for p in problems if p.startswith("redis_module:")], [])
        self.assertEqual(recomputed, original)

    def test_d_drift_before_launch_blocks_the_command(self):
        mod = self.mod
        original = hashlib.sha256(self._snapshot).hexdigest()
        runner = _seed_authorized(mod, original)
        saved_connect = mod._pg_connect
        mod._pg_connect = lambda url: type(
            "C", (), {"execute": lambda s, *a: type(
                "R", (), {"fetchone": lambda s2: (False, True)})(),
                "close": lambda s: None})()
        try:
            runner.authorize("stub", "1")  # passes: bytes still original here
            SHARED_PATH.write_bytes(self._snapshot + b"\n# drifted pre-launch\n")
            with self.assertRaises(mod.TrapFired) as ctx:
                runner.run("stub", "1", ["true"])
            self.assertEqual(ctx.exception.evidence.get("redis_module"), "drift_at_launch")
            self.assertEqual(runner.sentinel_calls, 0)  # command NEVER launched
        finally:
            mod._pg_connect = saved_connect

    def test_g_forged_child_digest_is_rejected(self):
        original = hashlib.sha256(self._snapshot).hexdigest()
        child = {
            "schema": self.mod.PLUGIN_PROOF_SCHEMA, "sessionstart_ok": True,
            "nonce": "A" * 32, "redis_module_sha": "F" * 64,
            "sha_match": {"candidate": True, "profile": True, "manifest": True},
            "collected_node_ids": ["N1"],
        }
        with self.assertRaises(self.mod.TrapFired) as ctx:
            self.mod.verify_child_proof(child, "A" * 32, ["N1"],
                                        redis_module_sha=original)
        self.assertEqual(ctx.exception.evidence.get("redis_module"),
                         "module_digest_mismatch")
        # a MISSING digest is equally unacceptable
        child_missing = dict(child, redis_module_sha="")
        with self.assertRaises(self.mod.TrapFired) as ctx:
            self.mod.verify_child_proof(child_missing, "A" * 32, ["N1"],
                                        redis_module_sha=original)
        self.assertEqual(ctx.exception.evidence.get("redis_module"),
                         "module_digest_missing")


class RunnerPreflightSitecustomizeTests(unittest.TestCase):
    """Counterexample B (accurately scoped per R2-R2-R1): a preloaded fake
    module via PYTHONPATH/sitecustomize is detected by the RUNNER PREFLIGHT
    process (the injected interpreter IS the runner here), which VOIDs at
    preflight with sentinel 0. This is the runner-preflight proof, NOT a
    child-only proof — the dedicated child-only subprocess proof lives in
    test_child_only_sitecustomize_preload below."""

    def test_b_runner_preflight_sitecustomize_preload_voids(self):
        mod = _load(RUNNER_PATH, "he2et1_r2r2_site_runner")
        with tempfile.TemporaryDirectory() as tmp:
            hook = Path(tmp) / "sitecustomize.py"
            hook.write_text(
                "import sys, types\n"
                "_fake = types.ModuleType('et1_redis_authority')\n"
                "_fake.__file__ = 'C:/attacker/child_only/redis_authority.py'\n"
                "def redis_live_check(_url):\n"
                "    return {'redis': 'ok'}\n"
                "_fake.redis_live_check = redis_live_check\n"
                "def eval_redis(_url, _ep):\n"
                "    return {'redis': 'ok'}\n"
                "_fake.eval_redis = eval_redis\n"
                "sys.modules['et1_redis_authority'] = _fake\n",
                encoding="utf-8",
            )
            case_dir = Path(tempfile.mkdtemp(prefix="et1r2r2-b-"))
            env = {
                **{k: v for k, v in __import__("os").environ.items()
                   if k not in ("PW1R3_TEST_REDIS_URL", "TEST_DATABASE_URL")},
                "PYTHONPATH": str(tmp),
                "TEST_DATABASE_URL": "",
                "PW1R3_TEST_REDIS_URL": f"redis://127.0.0.1:{63999}/15",
                "MPANGO_ALLOW_TEMP_DB_CREATE": "1",
            }
            args = [
                sys.executable, str(RUNNER_PATH),
                "--baseline-sha", "246eb190fc07866f098a380e61ebdc5bd9428a04",  # pragma: allowlist secret (public git commit id)
                "--publish-dir", str(case_dir / "publish"),
                "--profile", str(PROFILE), "--node-manifest", str(MANIFEST),
                "--collect-target", str(COLLECT),
                "--proof-out", str(case_dir / "proof.json"),
                "--sessionstart-out", str(case_dir / "ss.json"),
                "--collect-only",
            ]
            proc = subprocess.run(args, capture_output=True, text=True, env=env,
                                  cwd=str(REPO_ROOT))
            published = json.loads(
                (case_dir / "publish" / "authority-preflight.json").read_text(encoding="utf-8")
            )
            # The RUNNER process itself sees the planted fake via PYTHONPATH
            # and VOIDs at preflight; even if it did not, the CHILD would
            # fail closed at its own import of the plugin (both processes
            # run the same origin-binding bootstrap).
            self.assertEqual(proc.returncode, 14)
            self.assertEqual(published.get("state"), "VOID")
            self.assertEqual(published.get("sentinel_calls"), 0)
            self.assertIn("module_preload_detected", proc.stdout + proc.stderr)


class ChildOnlySitecustomizeTests(unittest.TestCase):
    """R2-R2-R1: the TRUE child-only injection proof.

    The PARENT process env stays clean (no sitecustomize, no PYTHONPATH);
    only the pytest child's environment receives the injected PYTHONPATH
    (the monkeypatched spawn mirrors the runner's real child-env assembly).
    The child's sessionstart must fail closed on the preloaded fake, no
    collect proof may be written, and the authority command count stays 0.
    """

    def test_child_only_sitecustomize_preload_fails_child_closed(self):
        mod = _load(RUNNER_PATH, "he2et1_r2r2_childonly_runner")
        import os

        with tempfile.TemporaryDirectory() as hook_dir:
            hook = Path(hook_dir) / "sitecustomize.py"
            hook.write_text(
                "import sys, types\n"
                "_fake = types.ModuleType('et1_redis_authority')\n"
                "_fake.__file__ = 'C:/attacker/child_only/redis_authority.py'\n"
                "def redis_live_check(_url):\n"
                "    return {'redis': 'ok'}\n"
                "_fake.redis_live_check = redis_live_check\n"
                "def eval_redis(_url, _ep):\n"
                "    return {'redis': 'ok'}\n"
                "_fake.eval_redis = eval_redis\n"
                "sys.modules['et1_redis_authority'] = _fake\n",
                encoding="utf-8",
            )
            # the parent env must stay clean
            self.assertNotIn(hook_dir, os.environ.get("PYTHONPATH", ""))
            real_run = mod.subprocess.run
            saved_pythonpath = os.environ.get("PYTHONPATH")

            def child_only_injecting_run(cmd, **kwargs):
                env = kwargs.get("env")
                if env is not None and "pytest" in " ".join(map(str, cmd)):
                    injected = dict(env)
                    injected["PYTHONPATH"] = hook_dir + os.pathsep + env.get("PYTHONPATH", "")
                    kwargs = dict(kwargs, env=injected)
                return real_run(cmd, **kwargs)

            mod.subprocess.run = child_only_injecting_run
            try:
                profile = json.loads(PROFILE.read_text(encoding="utf-8"))
                sel = next(p for p in profile["profiles"]
                           if p["profile_id"] == "AUTHORITY_H2C_BACKEND")
                r = mod.AuthorityRunner(REPO_ROOT, sel, ["x"])
                r._to("PREFLIGHT")
                r.bind_redis_module()
                r._require_bound_redis_module()
                # R3: the real collect flow binds the backend-env authority
                # (legal env required); saved/restored around the run.
                saved_env = {k: os.environ.get(k) for k in (
                    "TEST_DATABASE_URL", "MPANGO_ENV",
                    "MPANGO_TEMP_DB_ALLOWED_PORTS", "MPANGO_TEMP_DB_ALLOWED_HOSTS")}
                os.environ["TEST_DATABASE_URL"] = "postgresql://i1_gate@127.0.0.1:15453/test_i1_gate"
                os.environ["MPANGO_ENV"] = "testing"
                os.environ["MPANGO_TEMP_DB_ALLOWED_PORTS"] = "15432,5432,15453"
                os.environ["MPANGO_TEMP_DB_ALLOWED_HOSTS"] = ""
                r.bind_backend_env_module()
                r._require_bound_backend_env_module()
                r._enforce_backend_env_authority()
                case_dir = Path(tempfile.mkdtemp(prefix="et1r2r2r1-child-"))
                trapped = None
                try:
                    r.collect_proven(
                        profile_path=str(PROFILE), manifest_path=str(MANIFEST),
                        proof_out=str(case_dir / "proof.json"),
                        sessionstart_out=str(case_dir / "ss.json"),
                        collect_target=str(COLLECT),
                    )
                except mod.TrapFired as fired:
                    trapped = fired
                # child failed closed: the runner saw no collect proof
                self.assertIsNotNone(trapped)
                self.assertFalse((case_dir / "proof.json").exists())
                self.assertEqual(r.sentinel_calls, 0)  # no authority command
                self.assertEqual(r.collect_spawns, 1)  # the child really ran
                # the child's own sessionstart proof documents the detection
                ss = json.loads((case_dir / "ss.json").read_text(encoding="utf-8"))
                self.assertFalse(ss.get("ok", True))
                self.assertIn("redis_module:preload_detected", ss.get("problems", []))
                # the parent env never carried the injection
                self.assertNotIn(hook_dir, os.environ.get("PYTHONPATH", ""))
                for key, value in saved_env.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
            finally:
                mod.subprocess.run = real_run
                if saved_pythonpath is None:
                    os.environ.pop("PYTHONPATH", None)
                else:
                    os.environ["PYTHONPATH"] = saved_pythonpath


class CategorySetIntegrityTests(unittest.TestCase):
    """R2-R2-R1: the fixed module-binding category set must be complete —
    exactly the documented labels, and every redis_module label emitted by
    the runner or plugin source must be a member."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load(RUNNER_PATH, "he2et1_r2r2_categories_runner")

    def test_exact_category_set(self):
        expected = {
            "module_preload_detected", "module_origin_untrusted",
            "module_bytes_drift", "module_digest_missing",
            "module_digest_mismatch", "drift_at_authorize", "drift_at_launch",
        }
        self.assertEqual(self.mod.MODULE_BINDING_CATEGORIES, expected)

    def test_every_emitted_label_is_in_the_set(self):
        import re

        # Child-side `redis_module:<label>` labels are their own fixed set
        # (documented translation of the runner categories for the proof).
        child_allowed = {
            "preload_detected", "origin_untrusted", "bytes_drift",
            "digest_missing", "drift",
        }
        emitted = set()
        for source_path in (RUNNER_PATH, PLUGIN_PATH):
            text = source_path.read_text(encoding="utf-8")
            for match in re.findall(r'"(module_[a-z_]+|drift_at_[a-z_]+)"', text):
                emitted.add(match)
            for match in re.findall(r'redis_module:([a-z_]+)', text):
                if match in child_allowed:
                    continue
                emitted.add(match)
        unknown = emitted - self.mod.MODULE_BINDING_CATEGORIES
        self.assertEqual(unknown, set(), f"labels missing from the set: {unknown}")


class ContractWordingTests(unittest.TestCase):
    """Contract 12: the wrong 'same module object' claim is retracted."""

    def test_retracted_claim_no_longer_in_sources(self):
        banned = "literally share one module object"
        for path in (RUNNER_PATH, PLUGIN_PATH):
            self.assertNotIn(banned, path.read_text(encoding="utf-8"))
        runner_src = RUNNER_PATH.read_text(encoding="utf-8")
        self.assertIn("never reused", runner_src)
        self.assertIn("RAW-BYTE", runner_src)


if __name__ == "__main__":
    unittest.main()
