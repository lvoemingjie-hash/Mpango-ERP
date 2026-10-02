#!/usr/bin/env bash
# Read-only CI secret gate.
# Contract: compare the working tree against .secrets.baseline with the real
# detect-secrets hook/detectors. The baseline is NEVER rewritten by this gate.
# Fail-closed: tool missing/wrong version, corrupt baseline, enumeration
# failure, or baseline mutation all exit non-zero; "clean" is printed only
# after the hook actually ran and found nothing.
set -euo pipefail

readonly PINNED_DETECT_SECRETS_VERSION="1.5.0"
readonly BASELINE_NAME=".secrets.baseline"

readonly EX_FINDINGS=1 EX_USAGE=2 EX_TOOL=3 EX_BASELINE=4 EX_ENUM=5 EX_MUTATED=6

err() { printf '%s\n' "$*" >&2; }

if [ "$#" -gt 1 ]; then
  err "usage: $(basename "$0") [repo_root]"
  exit "$EX_USAGE"
fi

repo_root="${1:-.}"
if ! cd "$repo_root" 2>/dev/null; then
  err "secrets-gate: cannot enter repo root: $repo_root"
  exit "$EX_USAGE"
fi

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  err "secrets-gate: not inside a git work tree: $repo_root"
  exit "$EX_ENUM"
fi

if [ ! -f "$BASELINE_NAME" ]; then
  err "secrets-gate: missing $BASELINE_NAME"
  exit "$EX_BASELINE"
fi

# Baseline must be parseable JSON with an object "results" member.
if ! python3 -c '
import json, sys
try:
    with open(sys.argv[1], "r", encoding="utf-8") as fh:
        doc = json.load(fh)
except Exception:
    sys.exit(1)
sys.exit(0 if isinstance(doc, dict) and isinstance(doc.get("results"), dict) else 1)
' "$BASELINE_NAME" 2>/dev/null; then
  err "secrets-gate: corrupt or unrecognized $BASELINE_NAME"
  exit "$EX_BASELINE"
fi

if ! command -v detect-secrets-hook >/dev/null 2>&1; then
  err "secrets-gate: detect-secrets-hook not found in PATH"
  exit "$EX_TOOL"
fi

tool_version="$(detect-secrets-hook --version 2>/dev/null || true)"
if [ "$tool_version" != "$PINNED_DETECT_SECRETS_VERSION" ]; then
  err "secrets-gate: detect-secrets version '$tool_version' != pinned '$PINNED_DETECT_SECRETS_VERSION'"
  exit "$EX_TOOL"
fi

before_sha="$(sha256sum "$BASELINE_NAME" | awk '{print $1}')"

# Checked path set = git-tracked files (the workflow's full declared scope),
# excluding the baseline itself. -z keeps paths with spaces intact.
files=()
if ! mapfile -d '' -t files < <(git ls-files -z -- . ":(exclude)$BASELINE_NAME"); then
  err "secrets-gate: failed to enumerate git-tracked files"
  exit "$EX_ENUM"
fi
if [ "${#files[@]}" -eq 0 ]; then
  err "secrets-gate: enumerated zero git-tracked files; refusing to report clean"
  exit "$EX_ENUM"
fi

hook_rc=0
hook_output="$(detect-secrets-hook --baseline "$BASELINE_NAME" "${files[@]}" 2>&1)" || hook_rc=$?

after_sha="$(sha256sum "$BASELINE_NAME" | awk '{print $1}')"
if [ "$after_sha" != "$before_sha" ]; then
  err "secrets-gate: $BASELINE_NAME changed during gate run (before $before_sha, after $after_sha); this gate must be read-only"
  exit "$EX_MUTATED"
fi

case "$hook_rc" in
  0)
    echo "✅ secrets gate: no new secrets (${#files[@]} tracked files checked, $BASELINE_NAME unchanged @$before_sha)"
    ;;
  1)
    err "❌ secrets gate: new secrets detected vs $BASELINE_NAME (locations and secret types only):"
    err "$hook_output"
    exit "$EX_FINDINGS"
    ;;
  *)
    err "❌ secrets gate: detect-secrets-hook failed with rc=$hook_rc:"
    err "$hook_output"
    exit "$EX_TOOL"
    ;;
esac
