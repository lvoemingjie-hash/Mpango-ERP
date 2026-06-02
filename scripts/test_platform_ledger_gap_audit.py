#!/usr/bin/env python3
"""Tests for platform_ledger_gap_audit.py using unittest and stdlib only."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import platform_ledger_gap_audit as audit

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LEDGER_DIR = "ai-ledger/platform"


def _make_ledger_dir(tmpdir):
    ld = os.path.join(tmpdir, LEDGER_DIR)
    os.makedirs(ld, exist_ok=True)
    return ld


def _write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def _write_file(path, content=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


VALID_MISSION = {
    "phase": "P5-A",
    "agent": "opencode",
    "mission": "ai-ledger/platform/2026-05-31_p5a_test_mission.md",
    "expected_files": ["scripts/platform_ledger_gap_audit.py"],
    "result": "ai-ledger/platform/2026-05-31_p5a_test_result.json",
    "events": "ai-ledger/platform/2026-05-31_p5a_test_events.jsonl",
    "timeout_seconds": 600,
}


def _setup_clean_ledger(tmpdir):
    """Create a complete, valid ledger set."""
    ld = _make_ledger_dir(tmpdir)
    mj = os.path.join(ld, "2026-05-31_p5a_test_mission.json")
    _write_json(mj, VALID_MISSION)
    md = os.path.join(ld, "2026-05-31_p5a_test_mission.md")
    _write_file(md, "# Mission")
    rj = os.path.join(ld, "2026-05-31_p5a_test_result.json")
    _write_json(rj, {"status": "pass"})
    ev = os.path.join(ld, "2026-05-31_p5a_test_events.jsonl")
    _write_file(ev, '{"event":"start"}\n')
    return mj


def _run_cli(repo, extra_args=None):
    cmd = [
        sys.executable,
        os.path.join(SCRIPT_DIR, "platform_ledger_gap_audit.py"),
        "--repo", repo,
    ]
    if extra_args:
        cmd.extend(extra_args)
    return subprocess.run(cmd, capture_output=True, text=True)


class TestCleanLedgerPasses(unittest.TestCase):
    def test_clean_ledger_no_gaps(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _setup_clean_ledger(tmpdir)
            gaps = audit.audit_ledger(tmpdir)
            self.assertEqual(gaps, [], f"expected no gaps, got: {gaps}")

    def test_clean_ledger_cli_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _setup_clean_ledger(tmpdir)
            result = _run_cli(tmpdir)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("No ledger gaps found", result.stdout)


class TestMissingResultFails(unittest.TestCase):
    def test_missing_result_detected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ld = _make_ledger_dir(tmpdir)
            mj = os.path.join(ld, "2026-05-31_p5a_test_mission.json")
            _write_json(mj, VALID_MISSION)
            md = os.path.join(ld, "2026-05-31_p5a_test_mission.md")
            _write_file(md, "# Mission")
            ev = os.path.join(ld, "2026-05-31_p5a_test_events.jsonl")
            _write_file(ev, '{}\n')
            gaps = audit.audit_ledger(tmpdir)
            types = [g["type"] for g in gaps]
            self.assertIn("missing_result", types, f"expected missing_result, got: {types}")

    def test_missing_result_cli_nonzero(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ld = _make_ledger_dir(tmpdir)
            mj = os.path.join(ld, "2026-05-31_p5a_test_mission.json")
            _write_json(mj, VALID_MISSION)
            md = os.path.join(ld, "2026-05-31_p5a_test_mission.md")
            _write_file(md, "# Mission")
            result = _run_cli(tmpdir)
            self.assertNotEqual(result.returncode, 0)


class TestMissingEventsFails(unittest.TestCase):
    def test_missing_events_detected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ld = _make_ledger_dir(tmpdir)
            mj = os.path.join(ld, "2026-05-31_p5a_test_mission.json")
            _write_json(mj, VALID_MISSION)
            md = os.path.join(ld, "2026-05-31_p5a_test_mission.md")
            _write_file(md, "# Mission")
            rj = os.path.join(ld, "2026-05-31_p5a_test_result.json")
            _write_json(rj, {"status": "pass"})
            gaps = audit.audit_ledger(tmpdir)
            types = [g["type"] for g in gaps]
            self.assertIn("missing_events", types, f"expected missing_events, got: {types}")


class TestMissingMissionMarkdownFails(unittest.TestCase):
    def test_missing_mission_markdown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ld = _make_ledger_dir(tmpdir)
            mj = os.path.join(ld, "2026-05-31_p5a_test_mission.json")
            _write_json(mj, VALID_MISSION)
            rj = os.path.join(ld, "2026-05-31_p5a_test_result.json")
            _write_json(rj, {"status": "pass"})
            ev = os.path.join(ld, "2026-05-31_p5a_test_events.jsonl")
            _write_file(ev, '{}\n')
            gaps = audit.audit_ledger(tmpdir)
            types = [g["type"] for g in gaps]
            self.assertIn("missing_mission_markdown", types, f"expected missing_mission_markdown, got: {types}")


class TestOrphanResultFails(unittest.TestCase):
    def test_orphan_result_detected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ld = _make_ledger_dir(tmpdir)
            rj = os.path.join(ld, "2026-05-31_p5a_orphan_result.json")
            _write_json(rj, {"status": "pass"})
            gaps = audit.audit_ledger(tmpdir)
            types = [g["type"] for g in gaps]
            self.assertIn("orphan_result", types, f"expected orphan_result, got: {types}")


class TestOrphanEventsFails(unittest.TestCase):
    def test_orphan_events_detected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ld = _make_ledger_dir(tmpdir)
            ev = os.path.join(ld, "2026-05-31_p5a_orphan_events.jsonl")
            _write_file(ev, '{}\n')
            gaps = audit.audit_ledger(tmpdir)
            types = [g["type"] for g in gaps]
            self.assertIn("orphan_events", types, f"expected orphan_events, got: {types}")


class TestMalformedMissionJsonFails(unittest.TestCase):
    def test_malformed_json_detected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ld = _make_ledger_dir(tmpdir)
            mj = os.path.join(ld, "2026-05-31_p5a_bad_mission.json")
            with open(mj, "w") as f:
                f.write("{broken json!!!")
            gaps = audit.audit_ledger(tmpdir)
            types = [g["type"] for g in gaps]
            self.assertIn("malformed_mission_json", types, f"expected malformed_mission_json, got: {types}")

    def test_malformed_json_cli_nonzero(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ld = _make_ledger_dir(tmpdir)
            mj = os.path.join(ld, "2026-05-31_p5a_bad_mission.json")
            with open(mj, "w") as f:
                f.write("not json at all")
            result = _run_cli(tmpdir)
            self.assertNotEqual(result.returncode, 0)


class TestUnsafePathReferenceFails(unittest.TestCase):
    def test_traversal_in_result(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ld = _make_ledger_dir(tmpdir)
            mission = dict(VALID_MISSION)
            mission["result"] = "../etc/passwd"
            mj = os.path.join(ld, "2026-05-31_p5a_test_mission.json")
            _write_json(mj, mission)
            gaps = audit.audit_ledger(tmpdir)
            types = [g["type"] for g in gaps]
            self.assertIn("unsafe_path", types, f"expected unsafe_path, got: {types}")

    def test_absolute_path_in_events(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ld = _make_ledger_dir(tmpdir)
            mission = dict(VALID_MISSION)
            mission["events"] = "/tmp/evil.jsonl"
            mj = os.path.join(ld, "2026-05-31_p5a_test_mission.json")
            _write_json(mj, mission)
            gaps = audit.audit_ledger(tmpdir)
            types = [g["type"] for g in gaps]
            self.assertIn("unsafe_path", types, f"expected unsafe_path, got: {types}")

    def test_forbidden_path_in_mission(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ld = _make_ledger_dir(tmpdir)
            mission = dict(VALID_MISSION)
            mission["mission"] = "backend/evil.md"
            mj = os.path.join(ld, "2026-05-31_p5a_test_mission.json")
            _write_json(mj, mission)
            gaps = audit.audit_ledger(tmpdir)
            types = [g["type"] for g in gaps]
            self.assertIn("forbidden_path", types, f"expected forbidden_path, got: {types}")


class TestEmptyLedgerDirectoryPasses(unittest.TestCase):
    def test_empty_ledger_no_gaps(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_ledger_dir(tmpdir)
            gaps = audit.audit_ledger(tmpdir)
            self.assertEqual(gaps, [], f"expected no gaps for empty ledger, got: {gaps}")

    def test_empty_ledger_cli_zero(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _make_ledger_dir(tmpdir)
            result = _run_cli(tmpdir)
            self.assertEqual(result.returncode, 0)

    def test_missing_ledger_dir_no_gaps(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            gaps = audit.audit_ledger(tmpdir)
            self.assertEqual(gaps, [])


class TestCliJsonOutput(unittest.TestCase):
    def test_json_output_stable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _setup_clean_ledger(tmpdir)
            result = _run_cli(tmpdir, ["--json"])
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertIn("gaps", data)
            self.assertIn("count", data)
            self.assertEqual(data["count"], 0)
            self.assertEqual(data["gaps"], [])

    def test_json_output_with_gaps(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ld = _make_ledger_dir(tmpdir)
            rj = os.path.join(ld, "2026-05-31_p5a_orphan_result.json")
            _write_json(rj, {"status": "pass"})
            result = _run_cli(tmpdir, ["--json"])
            self.assertNotEqual(result.returncode, 0)
            data = json.loads(result.stdout)
            self.assertEqual(data["count"], len(data["gaps"]))
            self.assertTrue(data["count"] > 0)


class TestOrphanMissionMarkdown(unittest.TestCase):
    def test_orphan_mission_md_detected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ld = _make_ledger_dir(tmpdir)
            md = os.path.join(ld, "2026-05-31_p5a_lonely_mission.md")
            _write_file(md, "# Lonely mission")
            gaps = audit.audit_ledger(tmpdir)
            types = [g["type"] for g in gaps]
            self.assertIn("orphan_mission_markdown", types, f"expected orphan_mission_markdown, got: {types}")


class TestMultipleGapsReported(unittest.TestCase):
    def test_all_gap_types_at_once(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ld = _make_ledger_dir(tmpdir)
            # Malformed mission JSON
            with open(os.path.join(ld, "2026-05-31_p5a_bad_mission.json"), "w") as f:
                f.write("not json")
            # Mission with missing result + events + mission md
            mission = dict(VALID_MISSION)
            _write_json(os.path.join(ld, "2026-05-31_p5a_incomplete_mission.json"), mission)
            # Orphan result
            _write_json(os.path.join(ld, "2026-05-31_p5a_orphan_result.json"), {"status": "ok"})
            # Orphan events
            _write_file(os.path.join(ld, "2026-05-31_p5a_orphan_events.jsonl"), '{}\n')
            # Orphan mission md
            _write_file(os.path.join(ld, "2026-05-31_p5a_lonely_mission.md"), "# Lonely")
            gaps = audit.audit_ledger(tmpdir)
            types = set(g["type"] for g in gaps)
            self.assertIn("malformed_mission_json", types)
            self.assertIn("missing_mission_markdown", types)
            self.assertIn("missing_result", types)
            self.assertIn("missing_events", types)
            self.assertIn("orphan_result", types)
            self.assertIn("orphan_events", types)
            self.assertIn("orphan_mission_markdown", types)


if __name__ == "__main__":
    unittest.main()
