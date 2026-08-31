"""HE2-ET1-R4 truth tests: bounded, digest-bound manifest transport.

The frozen node manifest NEVER travels in a single argv/env string (kernel
MAX_ARG_STRLEN = 128KB per string; a full-suite manifest of ~3800 nodes is
~460KB and exec fails E2BIG before any authority launch). These tests bind
the replacement contract end to end:

- canonical transport bytes (sorted, unique, LF-terminated);
- the child gate fails closed on missing/substituted/truncated/duplicated/
  reordered transport files and on digest drift;
- verify_child_proof cross-compares the child's independently re-derived
  transport digest against the runner's ORIGINAL;
- post-binding mutation (drift) fails closed at collect/authorize/launch;
- the runner and plugin sources contain NO single-string manifest env
  transport (regression guard for the retired ET1_RUNNER_REQUIRED_NODES).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
GOV_DIR = TESTS_DIR.parent
REPO_ROOT = GOV_DIR.parent
RUNNER_PATH = GOV_DIR / "validator" / "authority_runner.py"
PLUGIN_PATH = GOV_DIR / "tests" / "pytest_et1_collector.py"


def _load(path: Path, key: str):
    for mod_name in (key, "et1_backend_env_authority"):
        sys.modules.pop(mod_name, None)
    spec = importlib.util.spec_from_file_location(key, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class CanonicalTransportTests(unittest.TestCase):
    def setUp(self):
        self.runner = _load(RUNNER_PATH, "et1_r4_truth_runner")

    def test_canonical_bytes_sorted_unique_lf_terminated(self):
        raw = self.runner.canonical_transport_bytes(["b", "a", "c"])
        self.assertEqual(raw, b"a\nb\nc\n")
        self.assertEqual(self.runner.manifest_transport_digest(raw),
                         hashlib.sha256(raw).hexdigest())

    def test_canonical_bytes_reject_empty_manifest(self):
        with self.assertRaises(ValueError):
            self.runner.canonical_transport_bytes([])

    def test_canonical_bytes_reject_duplicates(self):
        with self.assertRaises(ValueError):
            self.runner.canonical_transport_bytes(["a", "a"])


class PluginTransportGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plugin = _load(PLUGIN_PATH, "et1_r4_truth_plugin")

    def _env(self, tmp, raw=None, digest=None, drop_path=False, drop_digest=False):
        if raw is None:
            raw = b"x\ny\n"
        path = Path(tmp) / "et1-manifest.transport"
        if raw is not None:
            path.write_bytes(raw)
        env = {}
        if not drop_path:
            env["ET1_RUNNER_MANIFEST_TRANSPORT_PATH"] = str(path)
        if not drop_digest:
            env["ET1_RUNNER_MANIFEST_TRANSPORT_DIGEST"] = (
                digest if digest is not None else hashlib.sha256(raw).hexdigest())
        return env

    def test_green_path_returns_sorted_nodes_and_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            problems, (nodes, digest) = self.plugin._manifest_transport_problems(
                self._env(tmp, raw=b"a\nb\n"))
        self.assertEqual(problems, [])
        self.assertEqual(nodes, ["a", "b"])
        self.assertEqual(digest, hashlib.sha256(b"a\nb\n").hexdigest())

    def test_missing_path_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            problems, _ = self.plugin._manifest_transport_problems(
                self._env(tmp, drop_path=True))
        self.assertEqual(problems, ["manifest_transport:path_missing"])

    def test_missing_digest_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            problems, _ = self.plugin._manifest_transport_problems(
                self._env(tmp, drop_digest=True))
        self.assertEqual(problems, ["manifest_transport:digest_missing"])

    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = self._env(tmp, raw=b"a\n")
            Path(env["ET1_RUNNER_MANIFEST_TRANSPORT_PATH"]).unlink()
            problems, (nodes, _) = self.plugin._manifest_transport_problems(env)
        self.assertEqual(problems, ["manifest_transport:unreadable"])
        self.assertEqual(nodes, [])

    def test_substituted_file_digest_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = self._env(tmp, raw=b"a\nb\n", digest=hashlib.sha256(b"z\n").hexdigest())
            problems, _ = self.plugin._manifest_transport_problems(env)
        self.assertEqual(problems, ["manifest_transport:digest_mismatch"])

    def test_truncated_manifest_fails_eof_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = self._env(tmp, raw=b"a\nb")  # no trailing LF (truncated line)
            problems, _ = self.plugin._manifest_transport_problems(env)
        self.assertEqual(problems, ["manifest_transport:non_canonical_eof"])

    def test_duplicate_nodes_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = b"a\na\n"
            env = self._env(tmp, raw=raw, digest=hashlib.sha256(raw).hexdigest())
            problems, _ = self.plugin._manifest_transport_problems(env)
        self.assertEqual(problems, ["manifest_transport:duplicate_nodes"])

    def test_reordered_manifest_fails_closed(self):
        # Digest is bound to canonical (sorted) bytes; a reordered file MUST
        # mismatch the digest before the order check is even reachable.
        with tempfile.TemporaryDirectory() as tmp:
            env = self._env(tmp, raw=b"b\na\n", digest="0" * 64)
            problems, _ = self.plugin._manifest_transport_problems(env)
        self.assertIn("manifest_transport:digest_mismatch", problems)

    def test_reordered_manifest_with_matching_digest_detected(self):
        # Direct-order probe: digest over the exact (unsorted) bytes so the
        # order check itself is what must catch the violation.
        with tempfile.TemporaryDirectory() as tmp:
            raw = b"b\na\n"
            env = self._env(tmp, raw=raw, digest=hashlib.sha256(raw).hexdigest())
            problems, _ = self.plugin._manifest_transport_problems(env)
        self.assertEqual(problems, ["manifest_transport:non_canonical_order"])

    def test_blank_line_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = b"a\n\nb\n"
            env = self._env(tmp, raw=raw, digest=hashlib.sha256(raw).hexdigest())
            problems, _ = self.plugin._manifest_transport_problems(env)
        self.assertEqual(problems, ["manifest_transport:blank_line"])


class VerifyChildProofTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner = _load(RUNNER_PATH, "et1_r4_truth_verify")

    def _child(self, *, transport_sha="t" * 64, total=2):
        return {
            "schema": self.runner.PLUGIN_PROOF_SCHEMA,
            "sessionstart_ok": True,
            "nonce": "n" * 32,
            "sha_match": {"candidate": True, "profile": True, "manifest": True},
            "redis_module_sha": "r" * 64,
            "tempdb_binding_sha": "d" * 64,
            "alembic_actual_head": "038_catalog_identity_vertical_slice",
            "collected_node_ids": ["a", "b"],
            "manifest_transport_sha": transport_sha,
            "manifest_transport_nodes_total": total,
        }

    def _verify(self, child, **kwargs):
        return self.runner.verify_child_proof(
            child, "n" * 32, ["a", "b"],
            redis_module_sha="r" * 64,
            tempdb_binding_sha="d" * 64,
            alembic_actual_head="038_catalog_identity_vertical_slice",
            **kwargs)

    def test_green_transport_binding(self):
        summary = self._verify(self._child(), transport_digest="t" * 64)
        self.assertTrue(summary["manifest_transport_match"])

    def test_runner_digest_missing(self):
        with self.assertRaises(self.runner.TrapFired) as ctx:
            self._verify(self._child())
        self.assertEqual(
            ctx.exception.evidence.get("manifest_transport"), "runner_digest_missing")

    def test_child_digest_missing(self):
        with self.assertRaises(self.runner.TrapFired) as ctx:
            self._verify(self._child(transport_sha=""), transport_digest="t" * 64)
        self.assertEqual(
            ctx.exception.evidence.get("manifest_transport"), "child_digest_missing")

    def test_child_digest_mismatch(self):
        with self.assertRaises(self.runner.TrapFired) as ctx:
            self._verify(self._child(transport_sha="f" * 64), transport_digest="t" * 64)
        self.assertEqual(
            ctx.exception.evidence.get("manifest_transport"), "child_digest_mismatch")

    def test_child_total_mismatch(self):
        with self.assertRaises(self.runner.TrapFired) as ctx:
            self._verify(self._child(total=9), transport_digest="t" * 64)
        self.assertEqual(
            ctx.exception.evidence.get("manifest_transport"), "child_total_mismatch")


class TransportDriftTests(unittest.TestCase):
    def setUp(self):
        self.runner = _load(RUNNER_PATH, "et1_r4_truth_drift")
        self.r = self.runner.AuthorityRunner(REPO_ROOT, {"profile_id": "P"}, ["a"])

    def test_unbound_drifts(self):
        self.assertEqual(self.r._transport_drift(), "transport_unbound")

    def test_clean_and_drifted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "et1-manifest.transport"
            path.write_bytes(b"a\n")
            self.r.transport_path = path
            self.r.transport_digest = hashlib.sha256(b"a\n").hexdigest()
            self.assertIsNone(self.r._transport_drift())
            path.write_bytes(b"a\nb\n")
            self.assertEqual(self.r._transport_drift(), "manifest_transport_drift")
            path.unlink()
            self.assertEqual(self.r._transport_drift(), "manifest_transport_drift")


class SourceContractTests(unittest.TestCase):
    """Regression guard: the retired single-string transport must stay dead."""

    def test_no_full_manifest_env_string_anywhere(self):
        for path in (RUNNER_PATH, PLUGIN_PATH):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn(
                "ET1_RUNNER_REQUIRED_NODES", source,
                f"{path.name} reintroduced the single-string manifest transport")

    def test_publish_reports_transport_binding(self):
        source = RUNNER_PATH.read_text(encoding="utf-8")
        self.assertIn("manifest_transport_bound", source)
        self.assertIn("manifest_transport_match", source)


if __name__ == "__main__":
    unittest.main()
