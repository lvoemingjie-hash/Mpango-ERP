#!/usr/bin/env python3
# Tests for platform_worktree_review_packet.py (P16-G).

import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import platform_worktree_review_packet as packet


def _env():
    env = dict(os.environ)
    env["GIT_AUTHOR_NAME"] = "t"
    env["GIT_AUTHOR_EMAIL"] = "t@t"
    env["GIT_COMMITTER_NAME"] = "t"
    env["GIT_COMMITTER_EMAIL"] = "t@t"
    return env


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _make_repo(tmpdir, name="repo"):
    repo = os.path.join(tmpdir, name)
    os.makedirs(repo)
    with open(os.path.join(repo, "base.txt"), "w", encoding="utf-8") as fh:
        fh.write("base\n")
    subprocess.run(["git", "init", "-q", repo], check=True)
    subprocess.run(["git", "-C", repo, "add", "."], check=True)
    subprocess.run(["git", "-C", repo, "commit", "-q", "-m", "base"], check=True, env=_env())
    return repo


def _commit(repo, msg):
    subprocess.run(["git", "-C", repo, "add", "."], check=True)
    subprocess.run(["git", "-C", repo, "commit", "-q", "-m", msg], check=True, env=_env())


class TestReviewPacket(unittest.TestCase):
    def test_packet_captures_commits_files_and_low_risk(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(tmp)
            os.makedirs(os.path.join(repo, "ai-ledger", "platform"))
            os.makedirs(os.path.join(repo, "scripts"))
            with open(os.path.join(repo, "scripts", "x.txt"), "w", encoding="utf-8") as fh:
                fh.write("x\n")
            _commit(repo, "add scripts file")
            target, issue = packet.build_review_packet(
                repo, "HEAD~1", None, "ai-ledger/platform/p16g.json",
                gitnexus_summary="index ok",
                test_results={"failed": 0, "count": 5})
            self.assertIsNone(issue)
            data = _load(target)
        self.assertIsInstance(data["branch"], str)
        self.assertEqual(data["commit_count"], 1)
        self.assertIn("add scripts file", data["commits"])
        self.assertIn("scripts/x.txt", data["modified_files"])
        self.assertTrue(data["forbidden_audit"]["passed"])
        self.assertEqual(data["risk"]["level"], "low")
        self.assertEqual(data["gitnexus_summary"], "index ok")
        self.assertEqual(data["test_results"]["count"], 5)

    def test_packet_high_risk_on_forbidden_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(tmp)
            os.makedirs(os.path.join(repo, "ai-ledger", "platform"))
            os.makedirs(os.path.join(repo, "backend"))
            with open(os.path.join(repo, "backend", "evil.py"), "w", encoding="utf-8") as fh:
                fh.write("x\n")
            _commit(repo, "add backend file")
            target, issue = packet.build_review_packet(repo, "HEAD~1", None, "ai-ledger/platform/p16g2.json")
            self.assertIsNone(issue)
            data = _load(target)
        self.assertFalse(data["forbidden_audit"]["passed"])
        self.assertEqual(data["risk"]["level"], "high")
        self.assertIn("backend/evil.py", data["forbidden_audit"]["forbidden"])

    def test_packet_path_escape_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(tmp)
            target, issue = packet.build_review_packet(repo, "HEAD", None, "scripts/out.json")
        self.assertIsNotNone(issue)
        self.assertIsNone(target)

    def test_packet_loads_batch_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _make_repo(tmp)
            os.makedirs(os.path.join(repo, "ai-ledger", "platform"))
            bp = os.path.join(repo, "ai-ledger", "platform", "batch.json")
            with open(bp, "w", encoding="utf-8") as fh:
                json.dump({"aggregate_verdict": "passed", "passed": 2, "retried": 0,
                           "failed": 0, "skipped": 0, "total_missions": 2,
                           "mode": "execute", "report": "ai-ledger/platform/batch.json"}, fh)
            target, issue = packet.build_review_packet(
                repo, "HEAD", "ai-ledger/platform/batch.json", "ai-ledger/platform/p16g3.json")
            data = _load(target)
        self.assertIsNotNone(data["batch_summary"])
        self.assertEqual(data["batch_summary"]["aggregate_verdict"], "passed")

    def test_render_markdown_has_sections(self):
        pkt = {"branch": "codex/x", "base_ref": "origin/platform-dev", "commit_count": 2,
               "commits": ["feat a", "feat b"], "modified_files": ["scripts/x.py"],
               "forbidden_audit": {"passed": True},
               "batch_summary": {"aggregate_verdict": "passed", "passed": 1, "retried": 0, "failed": 0, "skipped": 0},
               "gitnexus_summary": "ok", "test_results": {"failed": 0},
               "risk": {"level": "low", "reasons": ["all gates passed"]}}
        md = packet.render_packet_markdown(pkt)
        self.assertIn("Platform CTO Review Packet", md)
        self.assertIn("Forbidden path audit: PASS", md)
        self.assertIn("Batch summary", md)
        self.assertIn("GitNexus summary", md)


if __name__ == "__main__":
    unittest.main()
