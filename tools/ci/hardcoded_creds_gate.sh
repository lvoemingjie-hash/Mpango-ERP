#!/usr/bin/env bash
# Hardcoded-credential gate.
# Same checks and the same intended include/exclude scope as the original
# security-scan.yml step; only the shell control flow is repaired:
#   - grep arguments are no longer amputated by a stray `;`
#   - grep exit status is interpreted explicitly: 0 = match (reject),
#     1 = no match (pass), >=2 = grep execution error (reject)
# Matched line content is never printed (locations only); the gate prints
# "clean" only after every check actually ran.
set -uo pipefail

# -e is deliberately unset: each grep rc must be inspected, not abort the script.
fail=0

# run_grep_check <label> <pattern> <include-globs...> -- <exclude-dirs...>
run_grep_check() {
  local label="$1" pattern="$2"
  shift 2
  local includes=() excludes=()
  while [ "$#" -gt 0 ] && [ "$1" != "--" ]; do includes+=("$1"); shift; done
  [ "$#" -gt 0 ] && shift
  while [ "$#" -gt 0 ]; do excludes+=("$1"); shift; done

  local cmd=(grep -rn -E "$pattern")
  local glob dir
  for glob in "${includes[@]}"; do cmd+=("--include=$glob"); done
  for dir in "${excludes[@]}"; do cmd+=("--exclude-dir=$dir"); done
  cmd+=(.)

  local out rc
  out="$("${cmd[@]}" 2>&1)" && rc=0 || rc=$?
  case "$rc" in
    0)
      printf '❌ %s: potential hardcoded credentials at (line content suppressed):\n' "$label" >&2
      printf '%s\n' "$out" | sed -E 's/^([^:]*:[0-9]+):.*$/\1/' >&2
      fail=1
      ;;
    1)
      printf '✔ %s: no matches\n' "$label"
      ;;
    *)
      printf '❌ %s: grep execution error (rc=%s):\n%s\n' "$label" "$rc" "$out" >&2
      fail=1
      ;;
  esac
}

PASSWORD_PATTERN='(password|passwd|pwd|secret|token|api_key|apikey)\s*=\s*["'"'"'][^"'"'"']{8,}["'"'"']'
AWS_PATTERN='(AKIA[0-9A-Z]{16}|AWS_ACCESS_KEY_ID|AWS_SECRET_ACCESS_KEY)'

# Original intended scope: source files, excluding dependency/venv/build and
# test directories (the `;` bug amputated the tests excludes; they are part of
# the step's original declared intent and are restored, not newly added).
run_grep_check "password-pattern check" "$PASSWORD_PATTERN" \
  "*.py" "*.js" "*.ts" "*.java" -- \
  node_modules venv .venv dist tests backend/tests

# Original AWS check scope: same includes plus .env*, excluding only
# dependency/venv dirs (no test-dir exclusion in the original).
run_grep_check "AWS credential check" "$AWS_PATTERN" \
  "*.py" "*.js" "*.ts" "*.env*" -- \
  node_modules venv .venv

# Private key files: original find expression and test/example path filter.
key_matches="$(find . \( -name "*.pem" -o -name "*.key" -o -name "id_rsa" \) -type f 2>/dev/null | grep -v "test" | grep -v "example" || true)"
if [ -n "$key_matches" ]; then
  printf '❌ private-key check: key files detected:\n%s\n' "$key_matches" >&2
  fail=1
else
  printf '✔ private-key check: no key files\n'
fi

if [ "$fail" -ne 0 ]; then
  printf '❌ hardcoded credentials gate: FAILED\n' >&2
  exit 1
fi
printf '✅ hardcoded credentials gate: all checks ran clean\n'
