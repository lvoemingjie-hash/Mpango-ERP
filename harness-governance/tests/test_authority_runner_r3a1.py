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

    def test_preflight_binds_profile_head_and_rejects_mismatch(self):
        from unittest import mock

        with tempfile.TemporaryDirectory() as tmp:
            profile = {"expected_alembic_head": SKU,
                       "expected_alembic_parent": H2C}
            r = self.runner.AuthorityRunner(REPO_ROOT, profile, ["x"])
            r._to("PREFLIGHT")
            r.bind_redis_module()
            r._require_bound_redis_module()
            r.bind_backend_env_module()
            r._require_bound_backend_env_module()
            # the merged repo tree is at 037 — a SKU-bound run must VOID
            with self.assertRaises(self.runner.TrapFired) as ctx:
                r._enforce_backend_env_authority_alembic()
            self.assertEqual(ctx.exception.evidence.get("alembic"),
                             "alembic_head_mismatch")
            # and the binding fields record the profile values
            self.assertEqual(r.alembic_expected, SKU)
            self.assertEqual(r.alembic_parent, H2C)


if __name__ == "__main__":
    unittest.main()
