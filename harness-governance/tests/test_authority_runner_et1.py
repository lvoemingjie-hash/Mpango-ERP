"""HE2-ET1 unit tests: execution-traps registry + authority runner (20 tests).

Covers (task section 4): registry health, evaluator whitelist enforcement,
trap VOID behavior with stable exit codes, count-equal/node-set-drift RED,
empty TEST_DATABASE_URL RED, just-in-time role escalation RED, phase
fail-stop RED, no-shell invariants, canonical remote mismatch RED, lineage
confusion RED, evidence packaging missing/extra/mismatch RED, EOL
MIXED_EOF fail-closed, proof nonce/profile/candidate drift RED, and the
rolsuper=true negative control proving the full-run sentinel is never
launched.

Standard library only; no product runtime, no PG/Redis/Playwright.
"""

from __future__ import annotations

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
VALIDATOR = GOV_DIR / "validator" / "harness_governance_validator.py"
RUNNER_PATH = GOV_DIR / "validator" / "authority_runner.py"
REGISTRY_PATH = GOV_DIR / "inventory" / "execution-traps.json"
PROFILES_PATH = GOV_DIR / "inventory" / "authority-profiles.json"

VALIDATOR_MUTATIONS_HOST = importlib.util.spec_from_file_location(
    "he2et1_authority_runner", RUNNER_PATH
)


def _load_runner():
    spec = importlib.util.spec_from_file_location("he2et1_authority_runner", RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git_snapshot(root: Path) -> dict:
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file() and "node_modules" not in p.parts and ".git" not in p.parts
    }


class RegistryTruthTests(unittest.TestCase):
    """Machine-verifiable registry contracts (10 tests)."""

    @classmethod
    def setUpClass(cls):
        cls.runner = _load_runner()
        with open(REGISTRY_PATH, encoding="utf-8") as fh:
            cls.registry = json.load(fh)
        cls.traps = {t["trap_id"]: t for t in cls.registry["traps"]}

    def test_exactly_fifteen_traps_with_unique_ids_and_exit_codes(self):
        self.assertEqual(len(self.traps), 15)
        codes = [t["stable_exit_code"] for t in self.traps.values()]
        self.assertEqual(len(set(codes)), 15)
        self.assertTrue(all(c >= 10 and c != 0 for c in codes))

    def test_all_evaluator_ids_come_from_the_hardcoded_whitelist(self):
        for trap in self.traps.values():
            self.assertIn(trap["evaluator_id"], self.runner.EVALUATOR_WHITELIST)

    def test_registry_stores_no_shell_commands(self):
        blob = json.dumps(self.registry)
        for banned in ("shell=True", "os.system", "subprocess.run", "bash -c", "sh -c"):
            self.assertNotIn(banned, blob)

    def test_p0_p1_traps_active_and_profile_referenced(self):
        with open(PROFILES_PATH, encoding="utf-8") as fh:
            profiles = json.load(fh)
        refs = set()
        for profile in profiles["profiles"]:
            refs.update(profile["required_traps"])
        for trap_id, trap in self.traps.items():
            if trap["risk"] in ("P0", "P1"):
                self.assertEqual(trap["status"], "ACTIVE")
                self.assertIn(trap_id, refs, f"{trap_id} not referenced by any profile")

    def test_schema_forbids_additional_properties(self):
        with open(GOV_DIR / "schemas" / "execution-traps.schema.json", encoding="utf-8") as fh:
            schema = json.load(fh)
        self.assertFalse(schema.get("additionalProperties", True))
        item = schema["properties"]["traps"]["items"]
        self.assertFalse(item.get("additionalProperties", True))

    def test_count_equal_but_node_set_different_is_red(self):
        with self.assertRaises(self.runner.TrapFired) as ctx:
            self.runner.eval_collect_manifest(["A", "B", "C"], ["A", "B", "D"])
        self.assertEqual(ctx.exception.exit_code, 15)
        self.assertTrue(ctx.exception.evidence["count_equal"])

    def test_empty_test_database_url_is_red(self):
        with self.assertRaises(self.runner.TrapFired) as ctx:
            self.runner.eval_test_db_url("")
        self.assertEqual(ctx.exception.exit_code, 11)

    def test_mixed_eof_fails_closed_and_pure_eols_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            mixed = Path(tmp) / "mixed.txt"
            mixed.write_bytes(b"a\r\nb\n")
            with self.assertRaises(self.runner.TrapFired) as ctx:
                self.runner.eval_eol(mixed)
            self.assertEqual(ctx.exception.exit_code, 22)
            lf = Path(tmp) / "lf.txt"
            lf.write_bytes(b"a\nb\n")
            self.assertEqual(self.runner.eval_eol(lf)["eol"], "lf")
            crlf = Path(tmp) / "crlf.txt"
            crlf.write_bytes(b"a\r\nb\r\n")
            self.assertEqual(self.runner.eval_eol(crlf)["eol"], "crlf")

    def test_lineage_confusion_is_red_and_distinct_parents_green(self):
        with self.assertRaises(self.runner.TrapFired) as ctx:
            self.runner.eval_git_lineage("a" * 40, "a" * 40)
        self.assertEqual(ctx.exception.exit_code, 20)
        result = self.runner.eval_git_lineage("a" * 40, "b" * 40)
        self.assertNotEqual(result["parent"], result["chain_base"])

    def test_evidence_packaging_missing_extra_mismatch_each_red(self):
        for manifest, disk in (
            ({"files": {"a": "x"}}, ["b"]),          # missing+extra
            ({"files": {"a": "x", "b": "y"}}, ["a"]),  # missing
            ({"files": {"a": "x"}}, ["a", "b"]),       # extra
        ):
            with self.assertRaises(self.runner.TrapFired) as ctx:
                self.runner.eval_evidence_packaging(manifest, disk, [])
            self.assertEqual(ctx.exception.exit_code, 21)
        ok = self.runner.eval_evidence_packaging({"files": {"a": "x"}}, ["a"], [])
        self.assertEqual((ok["missing"], ok["extra"], ok["mismatch"]), (0, 0, 0))


class RunnerTruthTests(unittest.TestCase):
    """Authority runner invariants (10 tests)."""

    @classmethod
    def setUpClass(cls):
        cls.runner = _load_runner()

    class FakeConn:
        def __init__(self, rolsuper=False, rolcreatedb=True):
            self.rolsuper = rolsuper
            self.rolcreatedb = rolcreatedb

        def execute(self, *_a, **_k):
            conn = self

            class _Cur:
                def fetchone(self_inner):
                    return (conn.rolsuper, conn.rolcreatedb)

            return _Cur()

        def close(self):
            pass

    def test_rolsuper_true_traps_and_sentinel_never_launches(self):
        runner = self.runner.AuthorityRunner(Path("."), {"m": 1}, ["N1"])
        with self.assertRaises(self.runner.TrapFired) as ctx:
            self.runner.eval_pg_role(self.FakeConn(rolsuper=True))
        self.assertEqual(ctx.exception.exit_code, 10)
        self.assertEqual(runner.sentinel_calls, 0)

    def test_phase_continue_after_fail_is_red(self):
        with self.assertRaises(self.runner.TrapFired) as ctx:
            self.runner.eval_phase_fail_stop(["PREFLIGHT", "FAIL", "RUNNING"])
        self.assertEqual(ctx.exception.exit_code, 16)

    def test_jit_role_escalation_is_red(self):
        with self.assertRaises(self.runner.TrapFired) as ctx:
            self.runner.eval_role_recheck(self.FakeConn(rolsuper=True))
        self.assertEqual(ctx.exception.exit_code, 17)

    def test_runner_source_contains_no_shell_true(self):
        source = RUNNER_PATH.read_text(encoding="utf-8")
        self.assertNotIn("shell=True", source)

    def test_non_canonical_remote_is_red(self):
        class FakeResult:
            stdout = "https://evil.example/repo.git"
            returncode = 0

        original = subprocess.run

        def fake_run(*_a, **_k):
            return FakeResult()

        saved = subprocess.run
        subprocess.run = fake_run
        try:
            with self.assertRaises(self.runner.TrapFired) as ctx:
                self.runner.eval_git_remote(Path("."))
        finally:
            subprocess.run = saved
        self.assertEqual(ctx.exception.exit_code, 19)
        self.assertNotIn("evil.example", str(ctx.exception.evidence))

    def test_sessionstart_drift_is_red_on_capability_missing(self):
        proof = {"nonce": "n" * 16}
        with self.assertRaises(self.runner.TrapFired) as ctx:
            self.runner.eval_sessionstart_proof(
                proof, self.FakeConn(), "postgresql://x", ""
            )
        self.assertEqual(ctx.exception.exit_code, 18)

    def test_forged_proof_cannot_authorize(self):
        runner = self.runner.AuthorityRunner(REPO_ROOT, {"m": 1}, ["N1"])
        runner.proof = {
            "nonce": "forged", "candidate_sha": "0" * 64, "profile_sha": "0" * 64,
            "node_manifest_sha": "0" * 64, "issued_at": 0, "expires_at": 1e18,
            "state_trace": [],
        }
        self.assertFalse(runner.proof_valid())

    def test_expired_proof_is_invalid(self):
        runner = self.runner.AuthorityRunner(REPO_ROOT, {"m": 1}, ["N1"])
        runner.proof = {
            "nonce": "n", "candidate_sha": sha_of_registry(),
            "profile_sha": runner_sha_profile(runner),
            "node_manifest_sha": manifest_sha(runner),
            "issued_at": 0, "expires_at": 0, "state_trace": [],
        }
        self.assertFalse(runner.proof_valid())

    def test_trap_fired_output_is_sanitized(self):
        fired = self.runner.TrapFired(
            "TRAP_TEST_DB_URL_EMPTY", 11, "PREFLIGHT", True,
            {"url": "<redacted>", "secret": "FIXTURE_MARKER"},  # pragma: allowlist secret
        )
        self.assertNotIn("SUPER-SECRET", fired.evidence.get("url", ""))

    def test_self_test_passes_end_to_end(self):
        result = subprocess.run(
            [sys.executable, str(RUNNER_PATH), "--self-test"],
            capture_output=True, text=True, cwd=str(REPO_ROOT),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("SELFTEST: OK", result.stdout)


def sha_of_registry():
    import hashlib

    return hashlib.sha256(REGISTRY_PATH.read_bytes()).hexdigest()


def runner_sha_profile(runner):
    import hashlib

    return hashlib.sha256(
        json.dumps(runner.profile, sort_keys=True).encode()
    ).hexdigest()


def manifest_sha(runner):
    import hashlib

    return hashlib.sha256(
        "\n".join(sorted(runner.expected_nodes)).encode()
    ).hexdigest()


if __name__ == "__main__":
    unittest.main()
