#!/usr/bin/env python3
"""Tests for platform_toolchain_gate.py using unittest and tempfile only."""

import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import platform_toolchain_gate as gate

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def _create_fake_tool(tmpdir, name, version="1.0.0", version_exit=0):
    if sys.platform.startswith("win"):
        ext = ".bat"
        content = (
            f"@echo off\r\necho {name} version {version}\r\nexit /b {version_exit}\r\n"
        )
    else:
        ext = ""
        content = f"#!/bin/sh\necho {name} version {version}\nexit {version_exit}\n"
    path = os.path.join(tmpdir, name + ext)
    with open(path, "w") as f:
        f.write(content)
    if not sys.platform.startswith("win"):
        os.chmod(path, 0o755)
    return path


def _create_fake_version_failure_tool(tmpdir, name):
    if sys.platform.startswith("win"):
        ext = ".bat"
        content = "@echo off\r\necho FAILED\r\nexit /b 1\r\n"
    else:
        ext = ""
        content = "#!/bin/sh\necho FAILED\nexit 1\n"
    path = os.path.join(tmpdir, name + ext)
    with open(path, "w") as f:
        f.write(content)
    if not sys.platform.startswith("win"):
        os.chmod(path, 0o755)
    return path


class TestResolveTool(unittest.TestCase):
    def test_resolve_via_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _create_fake_tool(tmpdir, "testcoder")
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = tmpdir + os.pathsep + old_path
            try:
                resolved = gate.resolve_tool("testcoder")
                self.assertIsNotNone(resolved)
                self.assertTrue(os.path.isfile(resolved))
            finally:
                os.environ["PATH"] = old_path

    def test_resolve_missing(self):
        resolved = gate.resolve_tool("this_tool_does_not_exist_xyzzy")
        self.assertIsNone(resolved)

    def test_resolve_windows_cmd_fallback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tool_path = os.path.join(tmpdir, "fallbackagent.cmd")
            with open(tool_path, "w") as f:
                f.write("@echo off\r\necho fallbackagent 1.0\r\n")

            resolved = gate.resolve_tool(
                "fallbackagent",
                fallback_dirs=[tmpdir],
                is_windows=True,
            )
            self.assertEqual(os.path.normcase(tool_path), os.path.normcase(resolved))


class TestGetVersion(unittest.TestCase):
    def test_version_success(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _create_fake_tool(tmpdir, "myversion")
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = tmpdir + os.pathsep + old_path
            try:
                resolved = gate.resolve_tool("myversion")
                ok, info = gate.get_version(resolved)
                self.assertTrue(ok)
                self.assertIn("myversion", info)
                self.assertIn("1.0.0", info)
            finally:
                os.environ["PATH"] = old_path

    def test_version_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _create_fake_version_failure_tool(tmpdir, "badversion")
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = tmpdir + os.pathsep + old_path
            try:
                resolved = gate.resolve_tool("badversion")
                ok, info = gate.get_version(resolved)
                self.assertFalse(ok)
                self.assertIn("failed", info)
            finally:
                os.environ["PATH"] = old_path


class TestCliDefaultTool(unittest.TestCase):
    def test_default_tool_is_opencode(self):
        result = subprocess.run(
            [sys.executable, os.path.join(SCRIPT_DIR, "platform_toolchain_gate.py"),
             "--skip-version"],
            capture_output=True, text=True,
        )
        self.assertIn("Tools requested: opencode", result.stdout)


class TestCliFoundViaPath(unittest.TestCase):
    def test_found_via_path_passes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _create_fake_tool(tmpdir, "testagent")
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = tmpdir + os.pathsep + old_path
            try:
                result = subprocess.run(
                    [sys.executable,
                     os.path.join(SCRIPT_DIR, "platform_toolchain_gate.py"),
                     "--tool", "testagent"],
                    capture_output=True, text=True,
                )
                self.assertEqual(
                    0, result.returncode,
                    f"expected exit 0, got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}",
                )
                self.assertIn("PASS", result.stdout)
                self.assertIn("testagent", result.stdout)
                self.assertIn("ALL TOOLS AVAILABLE", result.stdout)
            finally:
                os.environ["PATH"] = old_path


class TestCliMissingTool(unittest.TestCase):
    def test_missing_tool_fails(self):
        result = subprocess.run(
            [sys.executable, os.path.join(SCRIPT_DIR, "platform_toolchain_gate.py"),
             "--tool", "nonexistent_tool_abc123"],
            capture_output=True, text=True,
        )
        self.assertNotEqual(
            0, result.returncode,
            f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
        )
        self.assertIn("FAIL", result.stdout)
        self.assertIn("nonexistent_tool_abc123", result.stdout)
        self.assertIn("TOOLS UNAVAILABLE", result.stdout)


class TestCliVersionFailure(unittest.TestCase):
    def test_version_failure_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _create_fake_version_failure_tool(tmpdir, "brokentool")
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = tmpdir + os.pathsep + old_path
            try:
                result = subprocess.run(
                    [sys.executable,
                     os.path.join(SCRIPT_DIR, "platform_toolchain_gate.py"),
                     "--tool", "brokentool"],
                    capture_output=True, text=True,
                )
                self.assertNotEqual(
                    0, result.returncode,
                    f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
                )
                self.assertIn("FAIL", result.stdout)
                self.assertIn("brokentool", result.stdout)
                self.assertIn("version check", result.stdout)
            finally:
                os.environ["PATH"] = old_path


class TestCliSkipVersion(unittest.TestCase):
    def test_skip_version_passes_if_executable_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _create_fake_version_failure_tool(tmpdir, "skipme")
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = tmpdir + os.pathsep + old_path
            try:
                result = subprocess.run(
                    [sys.executable,
                     os.path.join(SCRIPT_DIR, "platform_toolchain_gate.py"),
                     "--tool", "skipme", "--skip-version"],
                    capture_output=True, text=True,
                )
                self.assertEqual(
                    0, result.returncode,
                    f"expected exit 0, got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}",
                )
                self.assertIn("PASS", result.stdout)
                self.assertIn("ALL TOOLS AVAILABLE", result.stdout)
            finally:
                os.environ["PATH"] = old_path


class TestCliMultipleTools(unittest.TestCase):
    def test_multiple_tools_all_pass(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _create_fake_tool(tmpdir, "tool_a")
            _create_fake_tool(tmpdir, "tool_b")
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = tmpdir + os.pathsep + old_path
            try:
                result = subprocess.run(
                    [sys.executable,
                     os.path.join(SCRIPT_DIR, "platform_toolchain_gate.py"),
                     "--tool", "tool_a", "--tool", "tool_b"],
                    capture_output=True, text=True,
                )
                self.assertEqual(
                    0, result.returncode,
                    f"expected exit 0, got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}",
                )
                self.assertIn("tool_a", result.stdout)
                self.assertIn("tool_b", result.stdout)
                self.assertIn("ALL TOOLS AVAILABLE", result.stdout)
            finally:
                os.environ["PATH"] = old_path

    def test_multiple_tools_one_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _create_fake_tool(tmpdir, "good_tool")
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = tmpdir + os.pathsep + old_path
            try:
                result = subprocess.run(
                    [sys.executable,
                     os.path.join(SCRIPT_DIR, "platform_toolchain_gate.py"),
                     "--tool", "good_tool", "--tool", "missing_tool_xyz"],
                    capture_output=True, text=True,
                )
                self.assertNotEqual(
                    0, result.returncode,
                    f"expected nonzero exit, got {result.returncode}\nstdout: {result.stdout}",
                )
                self.assertIn("good_tool", result.stdout)
                self.assertIn("missing_tool_xyz", result.stdout)
                self.assertIn("FAIL", result.stdout)
                self.assertIn("TOOLS UNAVAILABLE", result.stdout)
            finally:
                os.environ["PATH"] = old_path


class TestCliStdoutSections(unittest.TestCase):
    def test_sections_appear_in_output(self):
        result = subprocess.run(
            [sys.executable, os.path.join(SCRIPT_DIR, "platform_toolchain_gate.py"),
             "--skip-version"],
            capture_output=True, text=True,
        )
        self.assertIn("TOOLCHAIN CHECKS", result.stdout)
        self.assertIn("TOOLCHAIN VERDICT", result.stdout)


if __name__ == "__main__":
    unittest.main()
