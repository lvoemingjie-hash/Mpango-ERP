#!/usr/bin/env python3
"""Platform Worktree Smoke Worker - Mpango ERP (P16-C).

A minimal, safe worker for the real-worktree smoke mission. It proves the
platform_worktree_executor can run a governed worker inside an isolated git
worktree and audit the change it produces.

Contract:

* Write EXACTLY ONE caller-supplied output path (``--output <relpath>``).
* The output path must be relative, traversal-free, free of unsafe parts
  (empty/``.`` segments), not forbidden, and within an allowlisted prefix
  (``scripts/`` or ``ai-ledger/platform/``). Any violation exits non-zero so
  the executor records a ``failed`` verdict -- the worker never silently
  writes somewhere unsafe.
* With ``--commit`` the output is committed in the worktree so the executor's
  committed-change audit (diff base_sha..HEAD) is exercised end to end.
* Worker failure is never swallowed: a non-zero exit surfaces as a failed
  completion report.

Path safety reuses the canonical, regression-tested forbidden/allow rules from
platform_diff_auditor so this worker can never drift from the auditor's
boundary. The absolute / traversal / unsafe-part checks mirror
platform_worktree_executor's helpers.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# Reuse the canonical forbidden/allow rules (no drift from the auditor).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import platform_diff_auditor as diff_auditor  # noqa: E402


# Output may only land in these allowlisted prefixes.
ALLOWED_PREFIXES = diff_auditor.DEFAULT_ALLOWED_PREFIXES

# Deterministic, attributable identity for the optional worker commit.
COMMIT_AUTHOR_NAME = "P16-C Smoke Worker"
COMMIT_AUTHOR_EMAIL = "p16c-smoke@mpango.local"

# Deterministic marker written to the output so audits/tests are reproducible.
OUTPUT_MARKER = {
    "p16c_smoke": True,
    "source": "platform_worktree_smoke_worker",
    "marker": "p16c-real-worktree-smoke",
}


# ---------------------------------------------------------------------------
# Path safety (mirrors platform_worktree_executor)
# ---------------------------------------------------------------------------

def normalize_path(p):
    return p.replace("\\", "/")


def is_absolute(path):
    normalized = normalize_path(path)
    first_part = normalized.split("/", 1)[0]
    return (
        os.path.isabs(path)
        or normalized.startswith("/")
        or ":" in first_part
    )


def is_traversal(path):
    return ".." in normalize_path(path).split("/")


def has_unsafe_path_part(path):
    parts = normalize_path(path).split("/")
    return any(part in ("", ".") for part in parts)


def validate_output_path(path):
    """Return an error string, or None when the path is safe to write."""
    if not isinstance(path, str) or not path.strip():
        return "output must be a non-empty string"
    if is_absolute(path):
        return f"output '{path}' must be relative, not absolute or drive-qualified"
    if is_traversal(path):
        return f"output '{path}' contains directory traversal"
    if has_unsafe_path_part(path):
        return f"output '{path}' contains unsafe path part"
    forbidden, reason = diff_auditor.is_forbidden(path)
    if forbidden:
        return f"output '{path}' is forbidden ({reason})"
    if not diff_auditor.is_allowed(path, ALLOWED_PREFIXES):
        return (
            f"output '{path}' is outside allowlisted prefixes "
            f"{ALLOWED_PREFIXES}"
        )
    return None


# ---------------------------------------------------------------------------
# Git helper (only used when --commit is passed)
# ---------------------------------------------------------------------------

def commit_output(output_rel, repo_dir):
    """Stage and commit the output inside repo_dir. Returns (rc, stderr)."""
    env = dict(os.environ)
    env["GIT_AUTHOR_NAME"] = COMMIT_AUTHOR_NAME
    env["GIT_AUTHOR_EMAIL"] = COMMIT_AUTHOR_EMAIL
    env["GIT_COMMITTER_NAME"] = COMMIT_AUTHOR_NAME
    env["GIT_COMMITTER_EMAIL"] = COMMIT_AUTHOR_EMAIL
    add = subprocess.run(
        ["git", "add", "--", output_rel],
        cwd=str(repo_dir), capture_output=True, text=True,
    )
    if add.returncode != 0:
        return add.returncode, add.stderr.strip()
    commit = subprocess.run(
        ["git", "commit", "-q", "-m", "P16-C smoke worker output"],
        cwd=str(repo_dir), capture_output=True, text=True, env=env,
    )
    return commit.returncode, commit.stderr.strip()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(output, do_commit, repo_dir=None):
    repo_dir = Path(repo_dir or os.getcwd()).resolve()

    issue = validate_output_path(output)
    if issue:
        print(f"smoke worker: rejecting output path: {issue}", file=sys.stderr)
        return 2

    target = repo_dir / normalize_path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(OUTPUT_MARKER, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    if do_commit:
        rc, err = commit_output(normalize_path(output), repo_dir)
        if rc != 0:
            print(f"smoke worker: commit failed (rc={rc}): {err}", file=sys.stderr)
            return 3

    print(f"smoke worker: wrote {output}" + (" (committed)" if do_commit else ""))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Mpango ERP Platform Worktree Smoke Worker (P16-C)"
    )
    parser.add_argument(
        "--output", required=True,
        help="Relative, allowlisted output path to write (exactly one file)",
    )
    parser.add_argument(
        "--commit", action="store_true",
        help="Commit the output in the worktree (exercises committed-change audit)",
    )
    parser.add_argument(
        "--repo", default=None,
        help="Repository root for the optional commit (defaults to cwd)",
    )
    args = parser.parse_args(argv)
    return run(args.output, args.commit, args.repo)


if __name__ == "__main__":
    sys.exit(main())
