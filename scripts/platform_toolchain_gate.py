#!/usr/bin/env python3
"""Platform Toolchain Gate - Mpango ERP.

Validates that required AI agent tools (opencode, goose, etc.) are
available before platform tasks. Resolves via PATH and known Windows
fallback locations.
"""

import argparse
import os
import shutil
import subprocess
import sys


WINDOWS_FALLBACK_DIRS = [
    os.path.expandvars(r"%USERPROFILE%\.local\bin"),
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\opencode"),
    os.path.expandvars(r"%LOCALAPPDATA%\opencode"),
    os.path.expandvars(r"%APPDATA%\npm"),
    os.path.expandvars(r"%APPDATA%\npm\node_modules\opencode-ai\bin"),
    os.path.expandvars(r"%USERPROFILE%\.opencode\bin"),
    os.path.expandvars(r"%LOCALAPPDATA%\goose"),
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\goose"),
]


def candidate_names(name):
    root, ext = os.path.splitext(name)
    if ext:
        return [name]
    return [name, name + ".exe", name + ".cmd", name + ".bat", name + ".ps1"]


def resolve_tool(name, fallback_dirs=None, is_windows=None):
    resolved = shutil.which(name)
    if resolved:
        return resolved
    if is_windows is None:
        is_windows = sys.platform.startswith("win")
    if is_windows:
        for fallback_dir in fallback_dirs or WINDOWS_FALLBACK_DIRS:
            if not fallback_dir:
                continue
            for candidate_name in candidate_names(name):
                candidate = os.path.join(fallback_dir, candidate_name)
                if os.path.isfile(candidate):
                    return candidate
    return None


def get_version(tool_path):
    try:
        result = subprocess.run(
            [tool_path, "--version"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            version_out = (result.stdout or result.stderr).strip()
            return True, version_out if version_out else "(no output)"
        return False, f"version command failed (exit {result.returncode})"
    except subprocess.TimeoutExpired:
        return False, "version command timed out"
    except OSError as e:
        return False, f"could not execute: {e}"


def print_section(title):
    print(flush=True)
    print("=" * 60, flush=True)
    print(f"  {title}", flush=True)
    print("=" * 60, flush=True)


def main():
    parser = argparse.ArgumentParser(
        description="Mpango ERP Platform Toolchain Gate - validate agent tool availability"
    )
    parser.add_argument(
        "--tool", action="append", dest="tools", default=[],
        help="Tool name to check (repeatable, default: opencode)",
    )
    parser.add_argument(
        "--skip-version", action="store_true",
        help="Only check existence, skip --version verification",
    )
    args = parser.parse_args()

    if not args.tools:
        args.tools = ["opencode"]

    print("Platform Toolchain Gate", flush=True)
    print(f"  Tools requested: {', '.join(args.tools)}", flush=True)
    if args.skip_version:
        print("  Mode: existence check only (--skip-version)", flush=True)
    else:
        print("  Mode: existence + --version check", flush=True)
    print(flush=True)

    print_section("TOOLCHAIN CHECKS")
    all_passed = True

    for tool_name in args.tools:
        tool_path = resolve_tool(tool_name)
        if not tool_path:
            print(f"  FAIL  '{tool_name}' not found on PATH", flush=True)
            all_passed = False
            continue

        print(f"  PASS  '{tool_name}' found at {tool_path}", flush=True)

        if args.skip_version:
            continue

        ok, version_info = get_version(tool_path)
        if ok:
            print(f"  PASS  '{tool_name}' version: {version_info}", flush=True)
        else:
            print(f"  FAIL  '{tool_name}' version check: {version_info}", flush=True)
            all_passed = False

    print(flush=True)
    print_section("TOOLCHAIN VERDICT")
    if all_passed:
        print("  Result: ALL TOOLS AVAILABLE", flush=True)
        sys.exit(0)
    else:
        print("  Result: ONE OR MORE TOOLS UNAVAILABLE", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
