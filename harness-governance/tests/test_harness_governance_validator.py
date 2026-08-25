"""Unit tests for the HE2-R1 harness governance validator.

Runs entirely on temporary copies of the real governance tree: the shipped
schemas, seed inventory, debt register, registry, and the R1 governance
delta are the fixture, so the tests exercise exactly what CI enforces.
Phase 9 of DC-12R1-MVP-L1-HE2-R1: the original 31 HE2 tests are kept or
strengthened (tests that encoded the now-closed bypasses assert the RED
direction instead), and new coverage is added for the R1 rules.
Standard library only.
"""

import argparse
import datetime
import hashlib
import json
import os
import re
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


class WorkspaceTestCase(unittest.TestCase):
    """Copies the real governance tree into a temp workspace per test.

    R1 makes missing source anchors RED, so the fixture also copies every
    anchored product file (at its real path, with its real line count)
    from the repository into the workspace and the baseline tree.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="he2r1-unit-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.gov = os.path.join(self.tmp, "harness-governance")

    @staticmethod
    def copy_anchor_files(dst_root):
        anchors = set()
        for relpath in ("inventory/inventory.json", "inventory/critical-interactions.json"):
            with open(os.path.join(GOV_DIR, relpath), encoding="utf-8") as fh:
                doc = json.load(fh)
            items = doc.get("nodes") or doc.get("interactions") or []
            for item in items:
                for anchor in item.get("source_anchors", []):
                    path = anchor.split(":", 1)[0].strip()
                    if path:
                        anchors.add(path)
        for relpath in sorted(anchors):
            src = os.path.join(REPO_ROOT, relpath)
            if not os.path.isfile(src):
                continue
            dst = os.path.join(dst_root, relpath)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(src, dst)

    def workspace(self):
        shutil.copytree(GOV_DIR, self.gov)
        self.copy_anchor_files(self.tmp)
        return self.tmp

    def pristine_baseline(self):
        baseline = tempfile.mkdtemp(prefix="he2r1-baseline-")
        self.addCleanup(shutil.rmtree, baseline, ignore_errors=True)
        shutil.copytree(GOV_DIR, os.path.join(baseline, "harness-governance"))
        self.copy_anchor_files(baseline)
        return baseline

    def load(self, relpath):
        with open(os.path.join(self.gov, relpath), encoding="utf-8") as fh:
            return json.load(fh)

    def save(self, relpath, doc):
        path = os.path.join(self.gov, relpath)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2, ensure_ascii=False)
            fh.write("\n")

    def nodes(self):
        doc = self.load("inventory/inventory.json")
        return doc, doc["nodes"]

    def validate(self, baseline_dir=None, base_sha=None, mode="structural"):
        args = argparse.Namespace(
            baseline_ref=None, baseline_dir=baseline_dir, base_sha=base_sha, mode=mode
        )
        return v.validate_workspace(self.tmp, TODAY, args)

    def codes(self, report):
        return {violation["code"] for violation in report["violations"]}

    def touch_governed_path(self, relpath="backend/api/_probe.py"):
        full = os.path.join(self.tmp, relpath)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write("# governance sync probe\n")
        return relpath.replace(os.sep, "/")


class MiniSchemaCheckerTests(unittest.TestCase):
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
        v.check_against_schema(
            {"id": "A", "statuz": "PASS"}, schema, "#", schema, lambda *a: seen.append(a)
        )
        self.assertEqual([(c, p) for c, p, _ in seen], [("SCHEMA-ADDITIONAL", "#/statuz")])

    def test_ref_and_items(self):
        seen = []
        schema = {
            "type": "object",
            "properties": {"nodes": {"items": {"$ref": "#/definitions/node"}}},
            "definitions": {"node": {"type": "object", "required": ["id"]}},
        }
        v.check_against_schema(
            {"nodes": [{"id": "A"}, {}]}, schema, "#", schema, lambda *a: seen.append(a)
        )
        self.assertEqual(seen[-1][1], "#/nodes/1")

    def test_unique_items(self):
        seen = []
        schema = {"type": "array", "uniqueItems": True}
        v.check_against_schema(["a", "a"], schema, "#", schema, lambda *a: seen.append(a))
        self.assertEqual([c for c, _, _ in seen], ["SCHEMA-UNIQUE"])
        seen = []
        v.check_against_schema(["a", "b"], schema, "#", schema, lambda *a: seen.append(a))
        self.assertEqual(seen, [])

    def test_unresolvable_ref_is_red(self):
        seen = []
        schema = {"$ref": "#/definitions/nonexistent"}
        v.check_against_schema({}, schema, "#", schema, lambda *a: seen.append(a))
        self.assertEqual([c for c, _, _ in seen], ["SCHEMA-BAD-REF"])

    def test_unknown_keyword_is_red(self):
        seen = []
        schema = {"type": "object", "properties": {"n": {"type": "integer", "minimum": 1}}}
        v.check_schema_document(schema, "x.schema.json", lambda *a: seen.append(a))
        self.assertEqual([c for c, _, _ in seen], ["SCHEMA-UNKNOWN-KEYWORD"])
        self.assertIn("minimum", seen[0][2])


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

    def test_parse_anchor(self):
        self.assertEqual(v.parse_anchor("a/b.py"), ("a/b.py", None))
        self.assertEqual(v.parse_anchor("a/b.py:12"), ("a/b.py", (12, 12)))
        self.assertEqual(v.parse_anchor("a/b.py:38-97"), ("a/b.py", (38, 97)))
        self.assertEqual(v.parse_anchor("a/b.py:x")[1], "invalid")
        self.assertEqual(v.parse_anchor("a/b.py:9-4")[1], (9, 4))  # range order checked later

    def test_semantic_view_strips_notes_only(self):
        record = {"id": "A", "status": "PASS", "notes": "x"}
        self.assertEqual(v.semantic_view(record), {"id": "A", "status": "PASS"})


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


class DeltaAuthorizerTests(unittest.TestCase):
    BASE = "a" * 40
    OTHER = "b" * 40

    def delta(self, delta_id, kind="reorder", ids=None, base_sha=None, paths=None):
        return {
            "delta_id": delta_id,
            "kind": kind,
            "affected_ids": ids if ids is not None else ["A"],
            "affected_paths": paths or [],
            "base_sha": base_sha or self.BASE,
            "owner": "cto",
            "reason": "test",
            "approval_ref": "test",
        }

    def test_new_matching_delta_authorizes(self):
        authorizer = v.DeltaAuthorizer([self.delta("PD-1")], [], self.BASE)
        self.assertIsNone(authorizer.authorize("reorder", ids={"A"}))

    def test_historical_delta_replay(self):
        delta = self.delta("PD-1")
        authorizer = v.DeltaAuthorizer([delta], [delta], self.BASE)
        self.assertEqual(authorizer.authorize("reorder", ids={"A"}), "DELTA-REPLAY")

    def test_base_mismatch(self):
        authorizer = v.DeltaAuthorizer([self.delta("PD-1", base_sha=self.OTHER)], [], self.BASE)
        self.assertEqual(authorizer.authorize("reorder", ids={"A"}), "DELTA-BASE-MISMATCH")

    def test_unknown_base_fails_closed(self):
        authorizer = v.DeltaAuthorizer([self.delta("PD-1")], [], None)
        self.assertEqual(authorizer.authorize("reorder", ids={"A"}), "DELTA-BASE-MISMATCH")

    def test_kind_precision(self):
        authorizer = v.DeltaAuthorizer([self.delta("PD-1", kind="reorder")], [], self.BASE)
        self.assertEqual(authorizer.authorize("removal", ids={"A"}), "")

    def test_covered_paths_only_eligible(self):
        delta = self.delta("PD-1", kind="governance", paths=["harness-governance/validator/"])
        authorizer = v.DeltaAuthorizer([delta], [], self.BASE)
        self.assertIn("harness-governance/validator/", authorizer.covered_paths())
        replay = v.DeltaAuthorizer([delta], [delta], self.BASE)
        self.assertEqual(replay.covered_paths(), set())


class GreenWorkspaceTests(WorkspaceTestCase):
    def test_pristine_tree_structural_green_without_baseline(self):
        self.workspace()
        report = self.validate()
        self.assertTrue(report["green"], report["violations"])
        self.assertEqual(report["coverage"]["total_nodes"], 13)
        self.assertEqual(report["gates"]["structural_gate"], "PASS")

    def test_pristine_tree_is_green_against_pristine_baseline(self):
        baseline = self.pristine_baseline()
        self.workspace()
        report = self.validate(baseline_dir=baseline)
        self.assertTrue(report["green"], report["violations"])

    def test_seed_inventory_makes_no_coverage_claims(self):
        self.workspace()
        _, nodes = self.nodes()
        self.assertTrue(all(node["status"] != "PASS" for node in nodes))
        self.assertTrue(all(node["evidence_sha"] == "" for node in nodes))

    def test_release_gate_blocked_on_seed_debt(self):
        self.workspace()
        report = self.validate(mode="release")
        self.assertEqual(report["gates"]["structural_gate"], "PASS")
        self.assertEqual(report["gates"]["release_gate"], "BLOCKED")
        self.assertIn("DEBT-AUTH-CRITICAL-TUPLES", report["gates"]["release_blockers"])
        self.assertIn("DEBT-COMMERCE-CRITICAL-TUPLES", report["gates"]["release_blockers"])


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
        codes = self.codes(self.validate())
        self.assertIn("INV-PASS-EVIDENCE", codes)
        # outside a git repository the PASS claim is unverifiable: fail closed
        self.assertIn("EVIDENCE-UNVERIFIABLE", codes)

    def test_debt_with_blank_owner_is_red(self):
        self.workspace()
        doc = self.load("inventory/coverage-debt.json")
        doc["debts"][0]["owner"] = "   "
        self.save("inventory/coverage-debt.json", doc)
        self.assertIn("DEBT-INCOMPLETE", self.codes(self.validate()))

    def _waiver(self, **overrides):
        entry = {
            "waiver_id": "WVR-TEST-001",
            "scope": "inventory-sync",
            "reason": "unit test",
            "owner": "cto",
            "risk": "P2",
            "approval_ref": "unit-test",
            "opened_on": "2026-08-20",
            "expires_on": "2026-08-26",
            "paths": ["backend/api/_probe.py"],
        }
        entry.update(overrides)
        return [entry]

    def test_expired_waiver_is_red_even_without_sync_change(self):
        self.workspace()
        self.save("inventory/waivers.json", self._waiver(expires_on="2026-08-24"))
        self.assertIn("WVR-EXPIRED", self.codes(self.validate()))

    def test_waiver_without_paths_is_red(self):
        self.workspace()
        entry = self._waiver()[0]
        del entry["paths"]
        self.save("inventory/waivers.json", [entry])
        self.assertIn("SCHEMA-REQUIRED", self.codes(self.validate()))

    def test_waiver_with_wildcard_or_root_path_is_red(self):
        self.workspace()
        self.save("inventory/waivers.json", self._waiver(paths=["backend/*.py"]))
        self.assertIn("WVR-PATH-INVALID", self.codes(self.validate()))
        self.save("inventory/waivers.json", self._waiver(paths=["."]))
        self.assertIn("WVR-PATH-INVALID", self.codes(self.validate()))

    def test_waiver_cannot_cover_protected_path(self):
        self.workspace()
        self.save(
            "inventory/waivers.json",
            self._waiver(paths=["harness-governance/validator/probe.py"]),
        )
        self.assertIn("WVR-PATH-PROTECTED", self.codes(self.validate()))

    def test_anchor_line_out_of_range_is_red(self):
        self.workspace()
        doc, _ = self.nodes()
        doc["nodes"][0]["source_anchors"] = ["frontend/src/services/api.ts:999999"]
        self.save("inventory/inventory.json", doc)
        self.assertIn("ANCHOR-LINE-INVALID", self.codes(self.validate()))


class SyncRuleTests(WorkspaceTestCase):
    def _waiver(self, paths, expires_on="2026-08-26", waiver_id="WVR-SYNC-001"):
        return [
            {
                "waiver_id": waiver_id,
                "scope": "inventory-sync",
                "reason": "unit test waiver",
                "owner": "cto",
                "risk": "P2",
                "approval_ref": "unit-test",
                "opened_on": "2026-08-20",
                "expires_on": expires_on,
                "paths": paths,
            }
        ]

    def test_governed_change_without_mapping_is_red(self):
        baseline = self.pristine_baseline()
        self.workspace()
        self.touch_governed_path()
        self.assertIn("SYNC-SEMANTIC-MISSING", self.codes(self.validate(baseline_dir=baseline)))

    def test_notes_only_change_does_not_satisfy_sync(self):
        baseline = self.pristine_baseline()
        self.workspace()
        self.touch_governed_path()
        doc, nodes = self.nodes()
        doc["notes"] = doc.get("notes", "") + " [touched the inventory file]"
        nodes[0]["notes"] = "note-only change"
        self.save("inventory/inventory.json", doc)
        self.assertIn("SYNC-SEMANTIC-MISSING", self.codes(self.validate(baseline_dir=baseline)))

    def test_semantic_record_change_satisfies_sync(self):
        baseline = self.pristine_baseline()
        self.workspace()
        # modify (not overwrite) the real anchored file so its line anchors stay valid
        with open(os.path.join(self.tmp, "backend/api/app.py"), "a", encoding="utf-8") as fh:
            fh.write("# governance sync probe: appended product change\n")
        doc, _ = self.nodes()
        node = next(n for n in doc["nodes"] if n["id"] == "AUTH-INT-001")
        node["ui_oracle"] = "updated assertion matching the product change"
        self.save("inventory/inventory.json", doc)
        report = self.validate(baseline_dir=baseline)
        self.assertTrue(report["green"], report["violations"])

    def test_uncovered_second_path_is_reported(self):
        baseline = self.pristine_baseline()
        self.workspace()
        with open(os.path.join(self.tmp, "backend/api/app.py"), "a", encoding="utf-8") as fh:
            fh.write("# governance sync probe: appended product change\n")
        frontend_probe = self.touch_governed_path("frontend/src/_probe.tsx")
        doc, _ = self.nodes()
        node = next(n for n in doc["nodes"] if n["id"] == "AUTH-INT-001")
        node["ui_oracle"] = "updated assertion covering backend/api/app.py only"
        self.save("inventory/inventory.json", doc)
        report = self.validate(baseline_dir=baseline)
        sync = [x for x in report["violations"] if x["code"] == "SYNC-SEMANTIC-MISSING"]
        self.assertEqual(len(sync), 1)
        self.assertIn(frontend_probe, sync[0]["message"])

    def test_active_scoped_waiver_covers_exact_change(self):
        baseline = self.pristine_baseline()
        self.workspace()
        self.touch_governed_path()
        self.save("inventory/waivers.json", self._waiver(["backend/api/_probe.py"]))
        report = self.validate(baseline_dir=baseline)
        self.assertTrue(report["green"], report["violations"])

    def test_multi_waiver_union_covers_all_changed_paths(self):
        baseline = self.pristine_baseline()
        self.workspace()
        backend_probe = self.touch_governed_path("backend/api/_probe.py")
        frontend_probe = self.touch_governed_path("frontend/src/_probe.tsx")
        self.save(
            "inventory/waivers.json",
            self._waiver([backend_probe])
            + self._waiver([frontend_probe], waiver_id="WVR-SYNC-002"),
        )
        report = self.validate(baseline_dir=baseline)
        self.assertTrue(report["green"], report["violations"])

    def test_partial_waiver_leaves_rest_red(self):
        baseline = self.pristine_baseline()
        self.workspace()
        self.touch_governed_path("backend/api/_probe.py")
        frontend_probe = self.touch_governed_path("frontend/src/_probe.tsx")
        self.save("inventory/waivers.json", self._waiver(["backend/api/_probe.py"]))
        report = self.validate(baseline_dir=baseline)
        sync = [x for x in report["violations"] if x["code"] == "SYNC-SEMANTIC-MISSING"]
        self.assertEqual(len(sync), 1)
        self.assertIn(frontend_probe, sync[0]["message"])

    def test_expired_waiver_does_not_cover_sync_change(self):
        baseline = self.pristine_baseline()
        self.workspace()
        self.touch_governed_path()
        self.save(
            "inventory/waivers.json", self._waiver(["backend/api/_probe.py"], "2026-08-24")
        )
        codes = self.codes(self.validate(baseline_dir=baseline))
        self.assertIn("WVR-EXPIRED", codes)
        self.assertIn("SYNC-SEMANTIC-MISSING", codes)

    def test_protected_path_change_without_governance_delta_is_red(self):
        baseline = self.pristine_baseline()
        self.workspace()
        self.touch_governed_path("harness-governance/validator/_probe.py")
        self.assertIn("SYNC-PROTECTED-PATH", self.codes(self.validate(baseline_dir=baseline)))

    def test_protected_path_change_with_base_bound_governance_delta_is_green(self):
        baseline = self.pristine_baseline()
        self.workspace()
        self.touch_governed_path("harness-governance/validator/_probe.py")
        base_sha = "a" * 40
        self.save(
            "inventory/protocol-deltas.json",
            [
                {
                    "delta_id": "PD-UNIT-GOV",
                    "kind": "governance",
                    "affected_ids": [],
                    "affected_paths": ["harness-governance/validator/"],
                    "base_sha": base_sha,
                    "owner": "cto",
                    "reason": "unit test governance change",
                    "approval_ref": "unit-test",
                }
            ],
        )
        report = self.validate(baseline_dir=baseline, base_sha=base_sha)
        self.assertTrue(report["green"], report["violations"])


class StatusTransitionTests(WorkspaceTestCase):
    def _set_baseline_node_status(self, baseline, node_id, status):
        path = os.path.join(baseline, "harness-governance/inventory/inventory.json")
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        for node in doc["nodes"]:
            if node["id"] == node_id:
                node["status"] = status
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2)

    def test_unauthorized_pass_to_not_run_is_red(self):
        baseline = self.pristine_baseline()
        self._set_baseline_node_status(baseline, "AUTH-INT-001", "PASS")
        self.workspace()
        # head keeps NOT_RUN (pristine seed): PASS -> NOT_RUN without a delta
        self.assertIn("STATUS-UNAUTHORIZED", self.codes(self.validate(baseline_dir=baseline)))

    def test_execution_transition_not_run_to_blocked_needs_no_delta(self):
        baseline = self.pristine_baseline()
        self.workspace()
        doc, _ = self.nodes()
        node = next(n for n in doc["nodes"] if n["id"] == "AUTH-INT-001")
        node["status"] = "BLOCKED"
        node["blocked_owner"] = "cto"
        node["blocked_closure_condition"] = "unit test condition"
        self.save("inventory/inventory.json", doc)
        debt = self.load("inventory/coverage-debt.json")
        debt["debts"][0]["node_ids"].append("AUTH-INT-001")
        self.save("inventory/coverage-debt.json", debt)
        codes = self.codes(self.validate(baseline_dir=baseline))
        self.assertNotIn("STATUS-UNAUTHORIZED", codes)

    def test_reclassify_delta_authorizes_transition(self):
        baseline = self.pristine_baseline()
        self._set_baseline_node_status(baseline, "AUTH-INT-001", "PASS")
        self.workspace()
        base_sha = "c" * 40
        self.save(
            "inventory/protocol-deltas.json",
            [
                {
                    "delta_id": "PD-UNIT-RECLASSIFY",
                    "kind": "reclassify",
                    "affected_ids": ["AUTH-INT-001"],
                    "affected_paths": [],
                    "base_sha": base_sha,
                    "owner": "cto",
                    "reason": "unit test reclassification",
                    "approval_ref": "unit-test",
                }
            ],
        )
        codes = self.codes(self.validate(baseline_dir=baseline, base_sha=base_sha))
        self.assertNotIn("STATUS-UNAUTHORIZED", codes)


class EvidenceVerificationTests(WorkspaceTestCase):
    """PASS evidence checks with a scripted git runner; real git is exercised
    by the deterministic RED mutation gate."""

    class FakeGit:
        def __init__(self, exists=True, reachable=True, paths=()):
            self.exists = exists
            self.reachable = reachable
            self.paths = paths

        def __call__(self, root, *args):
            class R:
                def __init__(self, code=0, out=""):
                    self.returncode = code
                    self.stdout = out
                    self.stderr = ""

            if args[0] == "rev-parse":
                return R(0, ".git")
            if args[0] == "cat-file" and args[1] == "-t":
                return R(0, "commit") if self.exists else R(128)
            if args[0] == "branch":
                return R(0, "main") if self.reachable else R(0)
            if args[0] == "tag":
                return R(0, "")
            if args[0] == "cat-file" and args[1] == "-e":
                ok = args[2].split(":", 1)[1] in self.paths
                return R(0) if ok else R(128)
            return R(0)

    def pass_node(self):
        return {
            "id": "X",
            "evidence_sha": "d" * 40,
            "evidence_paths": ["evidence/x.json"],
            "status": "PASS",
        }

    def _verify(self, node, fake):
        ctx = v.GovernanceContext()
        original = v._git
        v._git = fake
        try:
            v._verify_one_pass_node(ctx, self.tmp, "#", node)
        finally:
            v._git = original
        return [x.code for x in ctx.violations]

    def test_valid_commit_evidence_passes(self):
        codes = self._verify(self.pass_node(), self.FakeGit(paths={"evidence/x.json"}))
        self.assertEqual(codes, [])

    def test_all_zero_sha_is_red(self):
        node = self.pass_node()
        node["evidence_sha"] = "0" * 40
        self.assertEqual(self._verify(node, self.FakeGit())[0], "EVIDENCE-SHA-INVALID")

    def test_nonexistent_commit_is_red(self):
        fake = self.FakeGit(exists=False, paths={"evidence/x.json"})
        self.assertEqual(self._verify(self.pass_node(), fake)[0], "EVIDENCE-COMMIT-MISSING")

    def test_unreachable_commit_is_red(self):
        fake = self.FakeGit(reachable=False, paths={"evidence/x.json"})
        self.assertEqual(self._verify(self.pass_node(), fake)[0], "EVIDENCE-COMMIT-UNREACHABLE")

    def test_missing_evidence_path_is_red(self):
        self.assertEqual(
            self._verify(self.pass_node(), self.FakeGit(paths=set()))[0],
            "EVIDENCE-PATH-MISSING",
        )

    def test_missing_evidence_paths_field_is_red(self):
        node = self.pass_node()
        del node["evidence_paths"]
        self.assertEqual(self._verify(node, self.FakeGit())[0], "EVIDENCE-PATH-MISSING")


class RawBlobIntegrityTests(WorkspaceTestCase):
    """R2: 64-hex evidence must hash raw blob bytes, not text-decoded strings.
    These tests use real temporary git repos with binary blobs."""

    def _make_git_repo_with_blob(self, blob_bytes):
        """Create a workspace with a committed binary blob; return (head, base, sha, relpath)."""
        head, base = self.workspace(), self.pristine_baseline()
        evidence_dir = os.path.join(head, "evidence")
        os.makedirs(evidence_dir, exist_ok=True)
        blob_path = os.path.join(evidence_dir, "BLOB-001.bin")
        with open(blob_path, "wb") as fh:
            fh.write(blob_bytes)
        for root in (head,):
            subprocess.run(["git", "-C", root, "init", "-b", "main"], check=True, capture_output=True)
            subprocess.run(["git", "-C", root, "config", "user.email", "test@test"], check=True, capture_output=True)
            subprocess.run(["git", "-C", root, "config", "user.name", "test"], check=True, capture_output=True)
            subprocess.run(["git", "-C", root, "add", "-A"], check=True, capture_output=True)
            subprocess.run(["git", "-C", root, "commit", "-m", "blob"], check=True, capture_output=True)
        sha = subprocess.run(
            ["git", "-C", head, "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True
        ).stdout.strip()
        return head, base, sha, "evidence/BLOB-001.bin"

    def test_binary_blob_raw_digest_green(self):
        """Binary blob with invalid UTF-8 and null bytes: raw SHA-256 must match."""
        binary = b"\x00\xff\xfe\x80\x01binary\x00\x00\xff" + "中文".encode("utf-8") + b"\x00"
        head, base, sha, relpath = self._make_git_repo_with_blob(binary)
        raw_digest = hashlib.sha256(binary).hexdigest()
        doc, nodes = self.nodes()
        node = next(n for n in nodes if n["id"] == "AUTH-INT-001")
        node["status"] = "PASS"
        node["evidence_sha"] = raw_digest
        node["evidence_commit"] = sha
        node["evidence_paths"] = [relpath]
        self.save("inventory/inventory.json", doc)
        report = self.validate(baseline_dir=base)
        evidence_violations = [v for v in report["violations"] if "EVIDENCE" in v["code"]]
        self.assertEqual(evidence_violations, [], evidence_violations)

    def test_binary_blob_text_digest_red(self):
        """Same binary blob, but digest computed via text decode/re-encode: must mismatch."""
        binary = b"\x00\xff\xfe\x80\x01binary\x00\x00\xff"
        head, base, sha, relpath = self._make_git_repo_with_blob(binary)
        # Simulate the old buggy path: decode as utf-8 with replace, then re-encode
        text_digest = hashlib.sha256(binary.decode("utf-8", errors="replace").encode("utf-8", "surrogatepass")).hexdigest()
        doc, nodes = self.nodes()
        node = next(n for n in nodes if n["id"] == "AUTH-INT-001")
        node["status"] = "PASS"
        node["evidence_sha"] = text_digest
        node["evidence_commit"] = sha
        node["evidence_paths"] = [relpath]
        self.save("inventory/inventory.json", doc)
        report = self.validate(baseline_dir=base)
        self.assertIn("EVIDENCE-BLOB-MISMATCH", self.codes(report))

    def test_git_raw_returns_bytes(self):
        """_git_raw must return bytes, not str."""
        result = v._git_raw(self.tmp, "rev-parse", "HEAD")
        self.assertIsInstance(result.stdout, bytes)


class ScannerStrictnessTests(unittest.TestCase):
    """R2/R3: the anchored detect-secrets exclusion must be safe — only
    exact key+hex lines in allowed governance files are excluded; any
    deviation (extra content, wrong key, non-allowed path) stays RED."""

    # R3 strict anchored regex: ^...$, key whitelist, 40 or 40+24 hex, optional trailing comma
    STRICT_RE = re.compile(
        r'^\s*"(base_sha|evidence_sha|evidence_commit)"\s*:\s*"[0-9a-f]{40}([0-9a-f]{24})?"\s*,?\s*$'
    )

    def test_exact_key_hex_matches(self):
        hex40 = "aabbccdd" * 5
        hex64 = hex40 + "1122334455667788" + "aabbccdd"  # 40 + 24 = 64
        for key in ("base_sha", "evidence_sha", "evidence_commit"):
            self.assertIsNotNone(self.STRICT_RE.search(f'  "{key}": "{hex40}"'), key)
            self.assertIsNotNone(self.STRICT_RE.search(f'  "{key}": "{hex64}"'), key)
        # With optional trailing comma
        self.assertIsNotNone(self.STRICT_RE.search(f'  "base_sha": "{hex40}",'))

    def test_sensitive_field_before_sha_not_excluded(self):
        hex40 = "aabbccdd" * 5
        self.assertIsNone(self.STRICT_RE.search(f'  "password": "x", "base_sha": "{hex40}"'))

    def test_sensitive_field_after_sha_not_excluded(self):
        hex40 = "aabbccdd" * 5
        self.assertIsNone(self.STRICT_RE.search(f'  "base_sha": "{hex40}", "password": "secret"'))  # pragma: allowlist secret
        self.assertIsNone(self.STRICT_RE.search(f'  "base_sha": "{hex40}", "token": "abc"'))

    def test_arbitrary_key_not_excluded(self):
        hex40 = "aabbccdd" * 5
        self.assertIsNone(self.STRICT_RE.search(f'  "commit_hash": "{hex40}"'))
        self.assertIsNone(self.STRICT_RE.search(f'  "checksum": "{hex40}"'))

    def test_comment_after_sha_not_excluded(self):
        hex40 = "aabbccdd" * 5
        self.assertIsNone(self.STRICT_RE.search(f'  "base_sha": "{hex40}"  # token=abc123'))

    def test_wrong_length_hex_not_excluded(self):
        self.assertIsNone(self.STRICT_RE.search('  "base_sha": "aabbccdd"'))  # 8 hex
        self.assertIsNone(self.STRICT_RE.search('  "base_sha": "' + 'a' * 39 + '"'))
        self.assertIsNone(self.STRICT_RE.search('  "base_sha": "' + 'a' * 65 + '"'))


class DeltaChainTests(WorkspaceTestCase):
    """R3: governance delta chain must authorize each hop and the cumulative
    review from HE2_PARENT through R1, R2, and R3."""

    def test_cumulative_delta_covers_he2_parent_to_head(self):
        """94b0c300..HEAD structural PASS: cumulative delta covers all."""
        baseline = self.pristine_baseline()
        self.workspace()
        report = self.validate(baseline_dir=baseline, base_sha="94b0c30034d04d1bad87f926a4b09e3dbbe3c6db")
        self.assertTrue(report["green"], report["violations"])

    def test_r2_hop_delta_covers_r1_tip_to_head(self):
        """5a380586..HEAD PASS: R2-hop delta covers R2's protected changes."""
        baseline = self.pristine_baseline()
        self.workspace()
        report = self.validate(baseline_dir=baseline, base_sha="5a380586caab4f662d7e1dfbc7899cf5bd3bc300")
        self.assertTrue(report["green"], report["violations"])


class ScannerScopeTests(WorkspaceTestCase):
    """R3/R3-R1: governance hex keys in non-allowed paths must be RED — for
    EVERY file type, not only *.json (os.walk fallback path here; the git
    ls-files path is covered by the git-workspace test below)."""

    HEX40 = "aabbccdd" * 5
    HEX64 = "aabbccdd" * 8

    def _write_probe(self, relpath, line=None):
        line = line if line is not None else f'  "evidence_sha": "{self.HEX40}",'
        full = os.path.join(self.tmp, *relpath.split("/"))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("# probe\n")
            fh.write(line + "\n")
        return relpath

    def test_backend_json_with_hex_key_is_red(self):
        self.workspace()
        probe = os.path.join(self.tmp, "backend", "api", "_probe.json")
        os.makedirs(os.path.dirname(probe), exist_ok=True)
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write('{\n  "base_sha": "' + "aabbccdd" * 5 + '"\n}\n')
        report = self.validate()
        self.assertIn("SCANNER-SCOPE-VIOLATION", self.codes(report))

    def test_backend_python_with_exact_evidence_sha_line_is_red(self):
        self.workspace()
        self._write_probe("backend/probe.py")
        report = self.validate()
        self.assertIn("SCANNER-SCOPE-VIOLATION", self.codes(report))

    def test_frontend_typescript_probe_is_red(self):
        self.workspace()
        self._write_probe("frontend/src/probe.ts")
        report = self.validate()
        self.assertIn("SCANNER-SCOPE-VIOLATION", self.codes(report))

    def test_docs_markdown_probe_is_red(self):
        self.workspace()
        self._write_probe("docs/probe.md")
        report = self.validate()
        self.assertIn("SCANNER-SCOPE-VIOLATION", self.codes(report))

    def test_workflow_yaml_probe_is_red(self):
        self.workspace()
        self._write_probe("workflow/probe.yml")
        report = self.validate()
        self.assertIn("SCANNER-SCOPE-VIOLATION", self.codes(report))

    def test_toml_shaped_line_is_red(self):
        """No extension whitelist: a matching line in a .toml file is RED
        exactly like any other file type."""
        self.workspace()
        self._write_probe("config/probe.toml")
        report = self.validate()
        self.assertIn("SCANNER-SCOPE-VIOLATION", self.codes(report))

    def test_arbitrary_key_stays_green(self):
        self.workspace()
        self._write_probe("backend/probe_any.py", f'  "commit_hash": "{self.HEX40}",')
        scanner_violations = [
            v for v in self.validate()["violations"] if v["code"] == "SCANNER-SCOPE-VIOLATION"
        ]
        self.assertEqual(scanner_violations, [])

    def test_prefix_and_suffix_attached_values_stay_green(self):
        self.workspace()
        self._write_probe("backend/probe_affix.py", f'  "evidence_sha": "secret-{self.HEX40}",')
        self._write_probe("backend/probe_suffix.py", f'  "evidence_sha": "{self.HEX40}-secret",')
        scanner_violations = [
            v for v in self.validate()["violations"] if v["code"] == "SCANNER-SCOPE-VIOLATION"
        ]
        self.assertEqual(scanner_violations, [])

    def test_wrong_length_hex_stays_green(self):
        self.workspace()
        self._write_probe("backend/probe_short.py", '  "evidence_sha": "aabbccdd",')
        self._write_probe("backend/probe_39.py", '  "evidence_sha": "' + "a" * 39 + '",')
        self._write_probe("backend/probe_65.py", '  "evidence_sha": "' + "a" * 65 + '",')
        scanner_violations = [
            v for v in self.validate()["violations"] if v["code"] == "SCANNER-SCOPE-VIOLATION"
        ]
        self.assertEqual(scanner_violations, [])

    def test_64_hex_variant_is_red(self):
        self.workspace()
        self._write_probe("backend/probe_64.py", f'  "evidence_sha": "{self.HEX64}",')
        report = self.validate()
        self.assertIn("SCANNER-SCOPE-VIOLATION", self.codes(report))

    def test_git_tracked_python_probe_is_red_via_ls_files_path(self):
        """The git ls-files candidate path: a tracked probe in a real git
        workspace must be found (no extension filter on the listing)."""
        self.workspace()
        self._write_probe("backend/probe_git.py")

        def git(*args):
            subprocess.run(["git", "-C", self.tmp, *args], check=True, capture_output=True)

        git("init", "-b", "main")
        git("config", "user.email", "scanner-test@example.invalid")
        git("config", "user.name", "scanner scope test")
        git("add", "-A")
        git("commit", "-m", "probe")
        report = self.validate()
        self.assertIn("SCANNER-SCOPE-VIOLATION", self.codes(report))

    def test_allowed_governance_file_with_hex_key_is_green(self):
        """The same hex line in protocol-deltas.json is legitimate — and the
        five allowed governance documents still pass through the ordinary
        schema + delta/evidence verification in the same report."""
        self.workspace()
        report = self.validate()
        scanner_violations = [v for v in report["violations"] if v["code"] == "SCANNER-SCOPE-VIOLATION"]
        self.assertEqual(scanner_violations, [])
        self.assertTrue(report["green"], report["violations"])


class ConfigProtectionTests(WorkspaceTestCase):
    def test_empty_governed_prefixes_is_red(self):
        self.workspace()
        config = self.load("governed-paths.json")
        config["governed_prefixes"] = []
        self.save("governed-paths.json", config)
        codes = self.codes(self.validate())
        self.assertIn("CONFIG-PREFIXES-EMPTY", codes)
        self.assertIn("CONFIG-MINIMUM-PREFIX", codes)

    def test_removing_minimum_product_prefix_is_red(self):
        self.workspace()
        config = self.load("governed-paths.json")
        config["governed_prefixes"] = [
            p for p in config["governed_prefixes"] if p != "backend/"
        ]
        self.save("governed-paths.json", config)
        self.assertIn("CONFIG-MINIMUM-PREFIX", self.codes(self.validate()))

    def test_duplicate_prefix_is_red(self):
        self.workspace()
        config = self.load("governed-paths.json")
        config["governed_prefixes"].append("backend/")
        self.save("governed-paths.json", config)
        self.assertIn("CONFIG-PREFIX-DUP", self.codes(self.validate()))

    def test_config_cannot_un_govern_protected_validator_dir(self):
        baseline = self.pristine_baseline()
        self.workspace()
        config = self.load("governed-paths.json")
        config["governed_prefixes"] = [
            p for p in config["governed_prefixes"] if not p.startswith("harness-governance/")
        ]
        self.save("governed-paths.json", config)
        # protected paths stay governed regardless of the config
        self.touch_governed_path("harness-governance/validator/_probe.py")
        codes = self.codes(self.validate(baseline_dir=baseline))
        self.assertIn("SYNC-PROTECTED-PATH", codes)


class CliTests(WorkspaceTestCase):
    def run_cli(self, *extra):
        return subprocess.run(
            [sys.executable, str(VALIDATOR), "--root", self.tmp, "--today", "2026-08-25", *extra],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    def test_cli_structural_green_exit_code_and_outputs(self):
        self.workspace()
        report_path = os.path.join(self.tmp, "report.json")
        summary_path = os.path.join(self.tmp, "summary.md")
        proc = self.run_cli("--report-json", report_path, "--markdown-summary", summary_path)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        with open(report_path, encoding="utf-8") as fh:
            report = json.load(fh)
        self.assertTrue(report["green"])
        self.assertEqual(report["gates"]["release_gate"], "BLOCKED")
        with open(summary_path, encoding="utf-8") as fh:
            markdown = fh.read()
        self.assertIn("STRUCTURAL_GATE", markdown)
        self.assertIn("RELEASE_GATE", markdown)
        self.assertIn("BLOCKED", markdown)
        self.assertIn("Coverage summary", markdown)
        self.assertIn("Debt summary", markdown)
        self.assertIn("never count as PASS", markdown)

    def test_cli_release_mode_exit_code_three_when_blocked(self):
        self.workspace()
        proc = self.run_cli("--mode", "release", "--quiet")
        self.assertEqual(proc.returncode, 3)
        self.assertIn("RELEASE_BLOCKED", proc.stderr)

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
