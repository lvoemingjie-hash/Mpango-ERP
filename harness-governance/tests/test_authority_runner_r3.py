"""HE2-ET1-R3 truth tests: backend CWD + temp-DB authority matrix.

Hermetic matrix over the SHARED probe (backend_env_authority) and the
runner's binding/drift machinery. The CLI-level negative cases here spawn
the real runner subprocess WITHOUT any PG/Redis: the R3 checks run inside
preflight BEFORE any connection, so each must VOID with exit 12, state
VOID, sentinel 0, and no sensitive value in the output.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
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
SHARED_PATH = GOV_DIR / "validator" / "backend_env_authority.py"

LEGAL = {
    "url": "postgresql://ci_gate@127.0.0.1:15455/test_ci_gate",
    "env": "testing",
    "ports": "15432,5432,15455",
    "hosts": "",
}


def _load(path, key):
    sys.modules.pop(key, None)
    spec = importlib.util.spec_from_file_location(key, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _backend_dir(tmp) -> Path:
    d = Path(tmp) / "backend"
    d.mkdir(parents=True, exist_ok=True)
    return d


class ProbeMatrixTests(unittest.TestCase):
    """The full CWD / temp-DB truth matrix over the SHARED probe."""

    @classmethod
    def setUpClass(cls):
        cls.shared = _load(SHARED_PATH, "he2et1_r3_shared")

    def _category(self, **kw):
        if "cwd" in kw:
            kw["cwd"] = Path(kw["cwd"])
        args = {**LEGAL, **kw}
        with self.assertRaises(self.shared.BackendEnvAuthorityError) as ctx:
            self.shared.check_backend_env(
                args["url"], args["env"], args["ports"], args["hosts"],
                args["cwd"],
            )
        evidence = json.dumps(ctx.exception.__dict__, default=str)
        for banned in ("postgresql://", "127.0.0.1", "test_ci_gate", "mpango_erp_test"):
            self.assertNotIn(banned, evidence)
        return ctx.exception.category

    def test_repo_root_cwd_is_not_canonical(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self._category(cwd=Path(tmp)), "cwd_not_canonical")

    def test_sibling_dir_outside_backend_is_not_canonical(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(
                self._category(cwd=_backend_dir(tmp).with_name("backendX")),
                "cwd_not_canonical",
            )

    def test_symlink_cwd_is_not_canonical(self):
        with tempfile.TemporaryDirectory() as tmp:
            real = _backend_dir(Path(tmp))
            link = Path(tmp) / "backend_link"
            try:
                os.symlink(real, link, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation unavailable on this host")
            self.assertEqual(self._category(cwd=link), "cwd_not_canonical")

    def test_missing_allowed_ports_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(
                self._category(ports="", cwd=_backend_dir(tmp)),
                "db_port_allowlist_missing",
            )

    def test_allowlist_without_actual_port_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(
                self._category(ports="5432,9999", cwd=_backend_dir(tmp)),
                "db_port_not_allowed",
            )

    def test_unsafe_db_name_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(
                self._category(
                    url="postgresql://ci_gate@127.0.0.1:15455/mpango_erp_test",
                    cwd=_backend_dir(tmp),
                ),
                "db_name_unsafe",
            )

    def test_missing_and_invalid_mpango_env_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = _backend_dir(tmp)
            self.assertEqual(
                self._category(env="", cwd=d), "mpango_env_missing")
            self.assertEqual(
                self._category(env="production", cwd=d), "mpango_env_invalid")

    def test_legal_configuration_is_green(self):
        with tempfile.TemporaryDirectory() as tmp:
            facts = self.shared.backend_env_facts(
                LEGAL["url"], LEGAL["env"], LEGAL["ports"], LEGAL["hosts"],
                _backend_dir(tmp),
            )
            self.assertEqual(facts["db_name"], "test_ci_gate")
            self.assertEqual(facts["port"], 15455)
            self.assertEqual(facts["mpango_env"], "testing")

    def test_binding_digest_drifts_on_every_managed_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = _backend_dir(tmp)
            base = self.shared.binding_digest("|".join([
                "testing", "test_ci_gate", "15455", "127.0.0.1",
                "15432,5432,15455", "", str(d),
            ]))
            variants = [
                "|".join(["test", "test_ci_gate", "15455", "127.0.0.1",
                          "15432,5432,15455", "", str(d)]),          # env drift
                "|".join(["testing", "test_other", "15455", "127.0.0.1",
                          "15432,5432,15455", "", str(d)]),          # db name drift
                "|".join(["testing", "test_ci_gate", "5432", "127.0.0.1",
                          "15432,5432,15455", "", str(d)]),          # port drift
                "|".join(["testing", "test_ci_gate", "15455", "127.0.0.1",
                          "15432,5432,15455", "10.0.0.8", str(d)]),  # allowlist drift
                "|".join(["testing", "test_ci_gate", "15455", "127.0.0.1",
                          "15432,5432,15455", "", str(d) + "x"]),    # cwd drift
            ]
            for v in variants:
                self.assertNotEqual(self.shared.binding_digest(v), base)


class RunnerBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner = _load(RUNNER_PATH, "he2et1_r3_runner")

    def test_preflight_binding_and_enforcement_on_legal_env(self):
        r = self.runner.AuthorityRunner(REPO_ROOT, {}, ["x"])
        os.environ["MPANGO_ENV"] = "testing"
        os.environ["TEST_DATABASE_URL"] = LEGAL["url"]
        os.environ["MPANGO_TEMP_DB_ALLOWED_PORTS"] = LEGAL["ports"]
        os.environ["MPANGO_TEMP_DB_ALLOWED_HOSTS"] = ""
        try:
            r.bind_backend_env_module()
            r._require_bound_backend_env_module()
            r._enforce_backend_env_authority()
            self.assertTrue(str(r.authority_cwd).endswith("backend"))
            self.assertEqual(len(r.tempdb_binding_sha), 64)
        finally:
            for k in ("MPANGO_ENV", "MPANGO_TEMP_DB_ALLOWED_PORTS",
                      "MPANGO_TEMP_DB_ALLOWED_HOSTS"):
                os.environ.pop(k, None)

    def test_preloaded_foreign_module_is_tamper_evidence(self):
        sys.modules["et1_backend_env_authority"] = type(
            "Fake", (), {"__file__": "C:/attacker/be.py"})
        try:
            r = self.runner.AuthorityRunner(REPO_ROOT, {}, ["x"])
            r.bind_backend_env_module()
            with self.assertRaises(self.runner.TrapFired) as ctx:
                r._require_bound_backend_env_module()
            self.assertEqual(
                ctx.exception.evidence.get("backend_env_module"),
                "module_preload_detected")
        finally:
            sys.modules.pop("et1_backend_env_authority", None)


class CliNegativeMatrixTests(unittest.TestCase):
    """CLI-level negatives: no PG/Redis needed — R3 preflight runs first."""

    def _run(self, url, mpango_env, ports):
        case = tempfile.mkdtemp(prefix="et1r3cli-")
        env = {**os.environ,
               "TEST_DATABASE_URL": url,
               "MPANGO_ENV": mpango_env,
               "MPANGO_TEMP_DB_ALLOWED_PORTS": ports,
               "MPANGO_TEMP_DB_ALLOWED_HOSTS": ""}
        proc = subprocess.run(
            [sys.executable, str(RUNNER_PATH), "--baseline-sha",
             "246eb190fc07866f098a380e61ebdc5bd9428a04",  # pragma: allowlist secret (public git commit id)
             "--publish-dir", str(Path(case) / "pub"),
             "--authority", "--command", sys.executable, "-c", "pass"],
            capture_output=True, text=True, env=env, cwd=str(REPO_ROOT),
        )
        pub = {}
        pf = Path(case) / "pub" / "authority-preflight.json"
        if pf.exists():
            pub = json.loads(pf.read_text(encoding="utf-8"))
        return proc.returncode, pub, proc.stdout + proc.stderr

    def test_missing_mpango_env_voids_with_zero_launches(self):
        rc, pub, out = self._run(LEGAL["url"], "", LEGAL["ports"])
        self.assertEqual(rc, 12)
        self.assertEqual(pub.get("state"), "VOID")
        self.assertEqual(pub.get("sentinel_calls"), 0)
        self.assertIn("mpango_env_missing", out)

    def test_unsafe_db_name_voids_with_zero_launches(self):
        rc, pub, out = self._run(
            "postgresql://ci_gate@127.0.0.1:15455/mpango_erp_test",
            "testing", LEGAL["ports"])
        self.assertEqual(rc, 12)
        self.assertEqual(pub.get("state"), "VOID")
        self.assertEqual(pub.get("sentinel_calls"), 0)
        self.assertIn("db_name_unsafe", out)

    def test_port_outside_allowlist_voids_with_zero_launches(self):
        rc, pub, out = self._run(
            "postgresql://ci_gate@127.0.0.1:9999/test_ci_gate",
            "testing", LEGAL["ports"])
        self.assertEqual(rc, 12)
        self.assertEqual(pub.get("state"), "VOID")
        self.assertEqual(pub.get("sentinel_calls"), 0)
        self.assertIn("db_port_not_allowed", out)

    def test_missing_allowlist_voids_with_zero_launches(self):
        rc, pub, out = self._run(LEGAL["url"], "testing", "")
        self.assertEqual(rc, 12)
        self.assertEqual(pub.get("state"), "VOID")
        self.assertEqual(pub.get("sentinel_calls"), 0)
        self.assertIn("db_port_allowlist_missing", out)


if __name__ == "__main__":
    unittest.main()
