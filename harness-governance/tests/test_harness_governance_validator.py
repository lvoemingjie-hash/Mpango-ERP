"""Unit tests for the HE2 harness governance validator.

Runs entirely on temporary copies of the real governance tree: the shipped
schemas, seed inventory, debt register, and registry are the fixture, so the
tests exercise exactly what CI enforces. Standard library only.
"""

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parents[1]
GOV_DIR = REPO_ROOT / "harness-governance"
VALIDATOR = GOV_DIR / "validator" / "harness_governance_validator.py"

sys.path.insert(0, str(GOV_DIR / "validator"))
import harness_governance_validator as v  # noqa: E402

TODAY = datetime.date(2026, 8, 25)


def no_baseline():
    return argparse.Namespace(baseline_ref=None, baseline_dir=None)


class WorkspaceTestCase(unittest.TestCase):
    """Copies the real governance tree into a temp workspace per test."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="he2-unit-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.gov = os.path.join(self.tmp, "harness-governance")

    def workspace(self):
        shutil.copytree(GOV_DIR, self.gov)
        return self.tmp

    def load(self, relpath):
        with open(os.path.join(self.gov, relpath), encoding="utf-8") as fh:
            return json.load(fh)

    def save(self, relpath, doc):
        with open(os.path.join(self.gov, relpath), "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2, ensure_ascii=False)
            fh.write("\n")

    def nodes(self):
        doc = self.load("inventory/inventory.json")
        return doc, doc["nodes"]

    def validate(self, baseline_dir=None):
        args = argparse.Namespace(baseline_ref=None, baseline_dir=baseline_dir)
        return v.validate_workspace(self.tmp, TODAY, args)

    def codes(self, report):
        return {violation["code"] for violation in report["violations"]}


class MiniSchemaCheckerTests(unittest.TestCase):
    def schema(self, **kwargs):
        base = {"type": "object", "properties": {}}
        base.update(kwargs)
        return base

    def test_type_mismatch(self):
        seen = []
        schema = {"type": "object", "properties": {"n": {"type": "integer"}}}
        v.check_against_schema({"n": True}, schema, "#", schema, lambda *a: seen.append(a))
        self.assertEqual([c for c, _, _ in seen], ["SCHEMA-TYPE"])

    def test_required_missing(self):
        seen = []
        schema = {"type": "object", "required": ["id"]}
        v.check_against_schema({}, schema, "#", schema, lambda *a: seen.append(a))
        self.assertEqual(seen[0][0], "SCHEMA-REQUIRED")

    def test_enum_rejects_unknown_status(self):
        seen = []
        schema = {"enum": ["PASS", "FAIL"]}
        v.check_against_schema("PASSED", schema, "#/status", schema, lambda *a: seen.append(a))
        self.assertEqual(seen[0][0], "SCHEMA-ENUM")
        self.assertIn("/status", seen[0][1])

    def test_minlength_and_pattern(self):
        seen = []
        schema = {"type": "string", "minLength": 1, "pattern": "^[0-9a-f]*$"}
        v.check_against_schema("", schema, "#", schema, lambda *a: seen.append(a))
        self.assertEqual([c for c, _, _ in seen], ["SCHEMA-MINLENGTH"])
        seen = []
        v.check_against_schema("XYZ", schema, "#", schema, lambda *a: seen.append(a))
        self.assertEqual([c for c, _, _ in seen], ["SCHEMA-PATTERN"])

    def test_additional_properties(self):
        seen = []
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {"id": {"type": "string"}},
        }
        v.check_against_schema({"id": "A", "statuz": "PASS"}, schema, "#", schema, lambda *a: seen.append(a))
        self.assertEqual([(c, p) for c, p, _ in seen], [("SCHEMA-ADDITIONAL", "#/statuz")])

    def test_ref_and_items(self):
        seen = []
        schema = {
            "type": "object",
            "properties": {"nodes": {"items": {"$ref": "#/definitions/node"}}},
            "definitions": {"node": {"type": "object", "required": ["id"]}},
        }
        v.check_against_schema({"nodes": [{"id": "A"}, {}]}, schema, "#", schema, lambda *a: seen.append(a))
        self.assertEqual(seen[-1][1], "#/nodes/1")


class PureFunctionTests(unittest.TestCase):
    def test_lcs(self):
        self.assertEqual(v.lcs(["A", "B", "C"], ["B", "A", "C"]), ["B", "C"])
        self.assertEqual(v.lcs(["A", "B"], ["A", "B"]), ["A", "B"])

    def test_moved_ids(self):
        # The flagged set is the minimal set of IDs off the longest stable order.
        self.assertEqual(v.moved_ids(["A", "B", "C"], ["B", "A", "C"]), {"A"})
        self.assertEqual(v.moved_ids(["A", "B", "C"], ["A", "B", "C"]), set())
        self.assertEqual(v.moved_ids(["A", "B", "C"], ["A", "C", "B"]), {"B"})

    def test_waiver_active_on_expiry_day(self):
        self.assertFalse(v.is_expired("2026-08-25", TODAY))
        self.assertTrue(v.is_expired("2026-08-24", TODAY))
        self.assertTrue(v.is_expired("not-a-date", TODAY))

    def test_evidence_sha_shapes(self):
        self.assertTrue(v.SHA_RE.match("a" * 40))
        self.assertTrue(v.SHA_RE.match("b" * 64))
        for bad in ("", "deadbeef", "A" * 40, "g" * 64, "c" * 41):
            self.assertIsNone(v.SHA_RE.match(bad), bad)

    def test_path_matches(self):
        self.assertTrue(v.path_matches("backend/api/x.py", "backend/"))
        self.assertTrue(v.path_matches("backend", "backend/"))
        self.assertFalse(v.path_matches("backendx/y.py", "backend/"))
        self.assertFalse(v.path_matches("docs/x.md", "backend/"))


class CoverageMathTests(unittest.TestCase):
    def test_blocked_never_counts_as_pass(self):
        nodes = [
            {"id": "A", "risk": "P0", "status": "PASS", "mutation_id": "M1"},
            {"id": "B", "risk": "P1", "status": "BLOCKED", "mutation_id": "M2"},
            {"id": "C", "risk": "P2", "status": "NOT_APPLICABLE", "mutation_id": ""},
            {"id": "D", "risk": "P2", "status": "NOT_RUN", "mutation_id": ""},
        ]
        cov = v.compute_coverage(nodes, [])
        self.assertEqual(cov["by_status"]["PASS"], 1)
        self.assertEqual(cov["by_status"]["BLOCKED"], 1)
        # denominator = total - NOT_APPLICABLE = 3; BLOCKED counts against coverage.
        self.assertAlmostEqual(cov["pass_rate"], 1 / 3, places=3)
        self.assertEqual(cov["p0_p1_mutation_coverage"], {"covered": 2, "total": 2})

    def test_oracle_completeness_requires_all_five(self):
        base = {field: "assertion" for field in v.ORACLE_FIELDS}
        complete = dict(base, id="A", risk="P2", status="NOT_RUN")
        incomplete = dict(base, id="B", risk="P2", status="NOT_RUN", ui_oracle="")
        cov = v.compute_coverage([complete, incomplete], [])
        self.assertAlmostEqual(cov["oracle_completeness"], 0.5)

    def test_debt_summary_partitions_open_and_closed(self):
        debts = [
            {"debt_id": "DEBT-1", "status": "BLOCKED", "risk": "P1", "release_blocked": True},
            {"debt_id": "DEBT-2", "status": "NOT_COVERED", "risk": "P0", "release_blocked": False},
            {"debt_id": "DEBT-3", "status": "CLOSED", "risk": "P2", "release_blocked": False},
        ]
        summary = v.compute_debt_summary(debts)
        self.assertEqual(summary["counts"], {"BLOCKED": 1, "NOT_COVERED": 1, "CLOSED": 1})
        self.assertEqual(summary["open_by_risk"]["P0"], 1)
        self.assertEqual(summary["release_blocking"], 1)
        self.assertEqual(len(summary["open_entries"]), 2)


class GreenWorkspaceTests(WorkspaceTestCase):
    def test_pristine_tree_is_green_without_baseline(self):
        self.workspace()
        report = self.validate()
        self.assertTrue(report["green"], report["violations"])
        self.assertEqual(report["coverage"]["total_nodes"], 13)

    def test_pristine_tree_is_green_against_pristine_baseline(self):
        baseline = tempfile.mkdtemp(prefix="he2-baseline-")
        self.addCleanup(shutil.rmtree, baseline, ignore_errors=True)
        shutil.copytree(GOV_DIR, os.path.join(baseline, "harness-governance"))
        self.workspace()
        report = self.validate(baseline_dir=baseline)
        self.assertTrue(report["green"], report["violations"])

    def test_seed_inventory_makes_no_coverage_claims(self):
        self.workspace()
        _, nodes = self.nodes()
        self.assertTrue(all(node["status"] != "PASS" for node in nodes))
        self.assertTrue(all(node["evidence_sha"] == "" for node in nodes))


class SemanticRuleTests(WorkspaceTestCase):
    def node(self, node_id):
        _, nodes = self.nodes()
        return next(node for node in nodes if node["id"] == node_id)

    def test_blank_oracle_is_red(self):
        self.workspace()
        doc, nodes = self.nodes()
        nodes[0]["ui_oracle"] = "   "
        self.save("inventory/inventory.json", doc)
        self.assertIn("INV-ORACLE-EMPTY", self.codes(self.validate()))

    def test_fake_sentinel_is_red(self):
        self.workspace()
        doc, nodes = self.nodes()
        nodes[0]["network_oracle"] = "n/a"
        self.save("inventory/inventory.json", doc)
        self.assertIn("INV-ORACLE-INVALID", self.codes(self.validate()))

    def test_p0_without_mutation_is_red(self):
        self.workspace()
        doc, _ = self.nodes()
        node = next(n for n in doc["nodes"] if n["id"] == "AUTH-INT-001")
        node["mutation_id"] = ""
        self.save("inventory/inventory.json", doc)
        self.assertIn("INV-MUTATION-MISSING", self.codes(self.validate()))

    def test_blocked_without_owner_is_red(self):
        self.workspace()
        doc, _ = self.nodes()
        node = next(n for n in doc["nodes"] if n["id"] == "MOBILE-DEV-001")
        node["blocked_owner"] = "   "
        self.save("inventory/inventory.json", doc)
        self.assertIn("INV-BLOCKED-OWNER", self.codes(self.validate()))

    def test_pass_without_evidence_sha_is_red(self):
        self.workspace()
        doc, _ = self.nodes()
        node = next(n for n in doc["nodes"] if n["id"] == "AUTH-INT-001")
        node["status"] = "PASS"
        self.save("inventory/inventory.json", doc)
        self.assertIn("INV-PASS-EVIDENCE", self.codes(self.validate()))

    def test_debt_with_blank_owner_is_red(self):
        self.workspace()
        doc = self.load("inventory/coverage-debt.json")
        doc["debts"][0]["owner"] = "   "
        self.save("inventory/coverage-debt.json", doc)
        self.assertIn("DEBT-INCOMPLETE", self.codes(self.validate()))

    def test_expired_waiver_is_red_even_without_sync_change(self):
        self.workspace()
        self.save(
            "inventory/waivers.json",
            [
                {
                    "waiver_id": "WVR-TEST-001",
                    "scope": "inventory-sync",
                    "reason": "unit test",
                    "owner": "cto",
                    "risk": "test",
                    "expires": "2026-08-24",
                }
            ],
        )
        self.assertIn("WVR-EXPIRED", self.codes(self.validate()))


class SyncRuleTests(WorkspaceTestCase):
    def pristine_baseline(self):
        baseline = tempfile.mkdtemp(prefix="he2-baseline-")
        self.addCleanup(shutil.rmtree, baseline, ignore_errors=True)
        shutil.copytree(GOV_DIR, os.path.join(baseline, "harness-governance"))
        return baseline

    def touch_governed_path(self):
        probe = os.path.join(self.tmp, "backend", "api")
        os.makedirs(probe, exist_ok=True)
        with open(os.path.join(probe, "_probe.py"), "w", encoding="utf-8") as fh:
            fh.write("# governance sync probe\n")

    def waiver(self, expires, paths=None):
        entry = {
            "waiver_id": "WVR-SYNC-001",
            "scope": "inventory-sync",
            "reason": "unit test waiver",
            "owner": "cto",
            "risk": "controlled test",
            "expires": expires,
        }
        if paths is not None:
            entry["paths"] = paths
        return [entry]

    def test_governed_change_without_inventory_update_is_red(self):
        baseline = self.pristine_baseline()
        self.workspace()
        self.touch_governed_path()
        self.assertIn("SYNC-INVENTORY-MISSING", self.codes(self.validate(baseline)))

    def test_governed_change_with_inventory_update_is_green(self):
        baseline = self.pristine_baseline()
        self.workspace()
        self.touch_governed_path()
        doc, _ = self.nodes()
        doc["notes"] = doc.get("notes", "") + " [sync probe update]"
        self.save("inventory/inventory.json", doc)
        self.assertTrue(self.validate(baseline)["green"])

    def test_active_waiver_covers_sync_change(self):
        baseline = self.pristine_baseline()
        self.workspace()
        self.touch_governed_path()
        self.save("inventory/waivers.json", self.waiver("2026-08-26"))
        self.assertTrue(self.validate(baseline)["green"])

    def test_scoped_waiver_does_not_cover_other_paths(self):
        baseline = self.pristine_baseline()
        self.workspace()
        self.touch_governed_path()
        self.save("inventory/waivers.json", self.waiver("2026-08-26", paths=["frontend/src/"]))
        self.assertIn("SYNC-INVENTORY-MISSING", self.codes(self.validate(baseline)))

    def test_expired_waiver_does_not_cover_sync_change(self):
        baseline = self.pristine_baseline()
        self.workspace()
        self.touch_governed_path()
        self.save("inventory/waivers.json", self.waiver("2026-08-24"))
        codes = self.codes(self.validate(baseline))
        self.assertIn("WVR-EXPIRED", codes)
        self.assertIn("SYNC-INVENTORY-MISSING", codes)


class CliTests(WorkspaceTestCase):
    def run_cli(self, *extra):
        return subprocess.run(
            [sys.executable, str(VALIDATOR), "--root", self.tmp, "--today", "2026-08-25", *extra],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    def test_cli_green_exit_code_and_outputs(self):
        self.workspace()
        report_path = os.path.join(self.tmp, "report.json")
        summary_path = os.path.join(self.tmp, "summary.md")
        proc = self.run_cli("--report-json", report_path, "--markdown-summary", summary_path)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        with open(report_path, encoding="utf-8") as fh:
            report = json.load(fh)
        self.assertTrue(report["green"])
        with open(summary_path, encoding="utf-8") as fh:
            markdown = fh.read()
        self.assertIn("Coverage summary", markdown)
        self.assertIn("Debt summary", markdown)
        self.assertIn("BLOCKED", markdown)
        self.assertIn("never count as PASS", markdown)

    def test_cli_red_exit_code(self):
        self.workspace()
        doc, nodes = self.nodes()
        nodes[0]["status"] = "PASSED"
        self.save("inventory/inventory.json", doc)
        proc = self.run_cli("--quiet")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("SCHEMA-ENUM", proc.stdout)


if __name__ == "__main__":
    unittest.main()
