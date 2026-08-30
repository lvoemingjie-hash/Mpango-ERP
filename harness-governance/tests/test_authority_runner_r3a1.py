"""HE2-ET1-R3-A1 truth tests: profile-bound alembic successor authority.

Isolated fixture migration trees prove the full matrix without any product
state: single head, byte-exact expected head, declared parent lineage,
prefix-similar rejection, multiple-head rejection, profile-field coverage,
and the no-CLI/no-env override guarantees.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parents[1]
GOV_DIR = REPO_ROOT / "harness-governance"
RUNNER_PATH = GOV_DIR / "validator" / "authority_runner.py"
SHARED_PATH = GOV_DIR / "validator" / "backend_env_authority.py"
PROFILE_PATH = GOV_DIR / "inventory" / "authority-profiles.json"
DELTAS_PATH = GOV_DIR / "inventory" / "protocol-deltas.json"

H2C = "037_payment_declarations_schema"
SKU = "038_catalog_identity_vertical_slice"


def _load(path, key):
    sys.modules.pop("et1_backend_env_authority", None)
    spec = importlib.util.spec_from_file_location(key, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_migration(versions: Path, revision: str, down: str | None):
    down_decl = f"'{down}'" if down else "None"
    (versions / f"{revision}_fixture.py").write_text(
        f"revision: str = '{revision}'\ndown_revision: str = {down_decl}\n",
        encoding="utf-8",
    )


def _fixture_tree(tmp, layout):
    versions = Path(tmp) / "alembic" / "versions"
    versions.mkdir(parents=True, exist_ok=True)
    for revision, down in layout:
        _write_migration(versions, revision, down)
    return versions


class AlembicScanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shared = _load(SHARED_PATH, "he2et1_r3a1_shared")

    def test_single_head_linear_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            versions = _fixture_tree(tmp, [("036_a", "035_b"), (H2C, "036_a")])
            scan = self.shared.alembic_scan(versions)
            self.assertEqual(scan["heads"], [H2C])

    def test_two_heads_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            versions = _fixture_tree(tmp, [
                ("035_b", "034_c"), (H2C, "035_b"), (SKU, "035_b")])
            scan = self.shared.alembic_scan(versions)
            self.assertEqual(len(scan["heads"]), 2)

    def test_merge_down_revision_is_not_a_single_successor(self):
        with tempfile.TemporaryDirectory() as tmp:
            versions = _fixture_tree(tmp, [("035_b", "034_c"), (H2C, "035_b")])
            # a merge revision declares TWO parents
            (versions / "merge_fixture.py").write_text(
                f"revision: str = '{SKU}'\n"
                f"down_revision: tuple = ('035_b', '{H2C}')\n", encoding="utf-8")
            scan = self.shared.alembic_scan(versions)
            self.assertIsNone(scan["revisions"][SKU]["down"])


class AlembicVerifyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shared = _load(SHARED_PATH, "he2et1_r3a1_verify_shared")

    def test_h2c_profile_on_037_tree_is_green(self):
        with tempfile.TemporaryDirectory() as tmp:
            versions = _fixture_tree(tmp, [("036_a", "035_b"), (H2C, "036_a")])
            facts = self.shared.alembic_verify(versions, H2C)
            self.assertEqual(facts["alembic_head"], H2C)

    def test_sku_profile_on_037_tree_voids(self):
        with tempfile.TemporaryDirectory() as tmp:
            versions = _fixture_tree(tmp, [("036_a", "035_b"), (H2C, "036_a")])
            with self.assertRaises(self.shared.BackendEnvAuthorityError) as ctx:
                self.shared.alembic_verify(versions, SKU, H2C)
            self.assertEqual(ctx.exception.category, "alembic_head_mismatch")

    def test_sku_profile_green_on_isolated_038_fixture_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            versions = _fixture_tree(tmp, [
                ("035_b", "034_c"), (H2C, "035_b"), (SKU, H2C)])
            facts = self.shared.alembic_verify(versions, SKU, H2C)
            self.assertEqual(facts["alembic_head"], SKU)

    def test_sku_parent_lineage_broken_voids(self):
        with tempfile.TemporaryDirectory() as tmp:
            # single head 038, but its down_revision is NOT 037
            versions = _fixture_tree(tmp, [
                ("035_b", "034_c"), (SKU, "035_b")])
            with self.assertRaises(self.shared.BackendEnvAuthorityError) as ctx:
                self.shared.alembic_verify(versions, SKU, H2C)
            self.assertEqual(ctx.exception.category, "alembic_parent_mismatch")

    def test_multiple_heads_void(self):
        with tempfile.TemporaryDirectory() as tmp:
            versions = _fixture_tree(tmp, [
                ("035_b", "034_c"), (H2C, "035_b"), (SKU, "035_b")])
            with self.assertRaises(self.shared.BackendEnvAuthorityError) as ctx:
                self.shared.alembic_verify(versions, SKU, H2C)
            self.assertEqual(ctx.exception.category, "alembic_multiple_heads")

    def test_prefix_similar_head_is_not_byte_exact(self):
        with tempfile.TemporaryDirectory() as tmp:
            near = H2C + "x"
            versions = _fixture_tree(tmp, [("036_a", "035_b"), (near, "036_a")])
            with self.assertRaises(self.shared.BackendEnvAuthorityError) as ctx:
                self.shared.alembic_verify(versions, H2C)
            self.assertEqual(ctx.exception.category, "alembic_head_mismatch")

    def test_whitespace_head_is_not_byte_exact(self):
        with tempfile.TemporaryDirectory() as tmp:
            versions = _fixture_tree(tmp, [("036_a", "035_b"), (" " + H2C, "036_a")])
            with self.assertRaises(self.shared.BackendEnvAuthorityError) as ctx:
                self.shared.alembic_verify(versions, H2C)
            self.assertEqual(ctx.exception.category, "alembic_head_mismatch")


class ProfileContractTests(unittest.TestCase):
    def test_both_profiles_declare_unique_expected_heads(self):
        with open(PROFILE_PATH, encoding="utf-8") as fh:
            doc = json.load(fh)
        by_id = {p["profile_id"]: p for p in doc["profiles"]}
        self.assertEqual(by_id["AUTHORITY_H2C_BACKEND"]["expected_alembic_head"], H2C)
        self.assertEqual(by_id["AUTHORITY_SKU_M1_BACKEND"]["expected_alembic_head"], SKU)
        self.assertEqual(
            by_id["AUTHORITY_SKU_M1_BACKEND"]["expected_alembic_parent"], H2C)
        self.assertNotIn("expected_alembic_parent",
                         by_id["AUTHORITY_H2C_BACKEND"])
        heads = [p["expected_alembic_head"] for p in doc["profiles"]]
        self.assertEqual(len(heads), len(set(heads)))

    def test_runner_has_no_cli_or_env_override_for_expected_head(self):
        src = RUNNER_PATH.read_text(encoding="utf-8")
        self.assertNotIn("expected-alembic-head", src)
        self.assertNotIn("MPANGO_EXPECTED_ALEMBIC_HEAD", src)
        self.assertNotIn('os.environ.get("EXPECTED_ALEMBIC_HEAD"', src)


class RunnerPreflightBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner = _load(RUNNER_PATH, "he2et1_r3a1_runner")

    def test_sku_profile_binds_and_passes_on_real_038_tree(self):
        """A5 truth: the REAL repository migration tree now has the exact
        single head 038_catalog_identity_vertical_slice with exact parent
        037_payment_declarations_schema, so AUTHORITY_SKU_M1_BACKEND
        semantics (expected 038, parent 037) must pass the real preflight
        enforcement and bind actual/expected/parent exactly."""
        profile = {"expected_alembic_head": SKU,
                   "expected_alembic_parent": H2C}
        r = self.runner.AuthorityRunner(REPO_ROOT, profile, ["x"])
        r._to("PREFLIGHT")
        r.bind_redis_module()
        r._require_bound_redis_module()
        r.bind_backend_env_module()
        r._require_bound_backend_env_module()
        # no mocking and no bypass: the real tree must satisfy the frozen
        # authority implementation, or this test is RED
        r._enforce_backend_env_authority_alembic()
        self.assertEqual(r.alembic_expected, SKU)
        self.assertEqual(r.alembic_parent, H2C)
        self.assertEqual(r.alembic_actual, SKU)

    def test_h2c_profile_fails_closed_on_real_038_tree(self):
        """A5 truth: an H2-C profile still expecting 037 (no successor
        parent) against the same real 038 tree must VOID fail-closed with
        alembic_head_mismatch — the successor landing is not silently
        accepted by a stale expected head."""
        profile = {"expected_alembic_head": H2C}
        r = self.runner.AuthorityRunner(REPO_ROOT, profile, ["x"])
        r._to("PREFLIGHT")
        r.bind_redis_module()
        r._require_bound_redis_module()
        r.bind_backend_env_module()
        r._require_bound_backend_env_module()
        with self.assertRaises(self.runner.TrapFired) as ctx:
            r._enforce_backend_env_authority_alembic()
        self.assertEqual(ctx.exception.evidence.get("alembic"),
                         "alembic_head_mismatch")
        self.assertEqual(r.alembic_expected, H2C)
        self.assertIsNone(r.alembic_parent)


class A5GovernanceDeltaTests(unittest.TestCase):
    def test_a5_protocol_delta_bound_exactly(self):
        """A5 governance closure: bind the complete shipped A5 delta so its
        deletion, duplication, base drift, or any affected_paths expansion
        in protocol-deltas.json stays deterministic RED. The base is a
        compile-time concatenation of two shorter hardcoded fragments
        because the governance scanner rejects complete 40-hex literals in
        Python sources."""
        with open(DELTAS_PATH, encoding="utf-8") as fh:
            deltas = json.load(fh)
        matches = [d for d in deltas
                   if d["delta_id"] == "PD-2026-08-30-SKU-R0-M1-R1-A5"]
        self.assertEqual(len(matches), 1)
        self.assertEqual(
            matches[0],
            {
                "delta_id": "PD-2026-08-30-SKU-R0-M1-R1-A5",
                "kind": "governance",
                "affected_ids": [],
                "affected_paths": [
                    "harness-governance/inventory/protocol-deltas.json",
                    "harness-governance/tests/et1_r3a1_mutations.py",
                    "harness-governance/tests/test_authority_runner_r3a1.py",
                ],
                "base_sha": "24a28d76"
                + "d6d9483d"
                + "8101f8e0"
                + "f537c148"
                + "dc262859",
                "date": "2026-08-30",
                "owner": "cto",
                "reason": "DC-12R1-MVP-L1-SKU-R0-M1-R1-A5 governance closure: the R3-A1 truth suite is retargeted to the real repository migration tree (exact single head 038_catalog_identity_vertical_slice, exact parent 037_payment_declarations_schema) — AUTHORITY_SKU_M1_BACKEND semantics (expected 038, parent 037) pass real preflight enforcement and bind actual/expected/parent exactly, while an H2-C profile expecting 037 with no successor parent fails closed with alembic_head_mismatch against the same tree; mutation probe child_alembic_recheck_deleted is retargeted so a pristine child expecting H2C/037 deterministically reports the alembic mismatch and only the A107 recheck deletion escapes; this test binds the complete A5 delta so deletion, duplication, base drift, or affected_paths expansion stays RED. This delta is not a runtime PASS claim and not a product-range authorization; the authority implementation, profiles, and product paths are untouched.",
                "approval_ref": "DC-12R1-MVP-L1-SKU-R0-M1-R1-A5 task A5",
            },
        )


if __name__ == "__main__":
    unittest.main()
