#!/usr/bin/env bash
# run_directive.sh v3 — Hardened Directive Runner
# Implements CTO Hardening Requirements (2026-05-17):
#   1. Report Existence Final Gate
#   2. Leo Execution Evidence Gate
#   3. Checkpoint / Progress Gate
#   4. Failure Report Guarantee
#   5. Heartbeat / Timeout
#   6. Verdict Discipline
#
# Routes: INVENTORY_ONLY/SCHEDULED_WATCH → script-only | VALIDATION_GATE → Leo headless
# Never calls chat-type Vibecoder agent.
set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────────
HEARTBEAT_INTERVAL=60        # seconds between heartbeat markers
TOTAL_TIMEOUT_SECS=4500      # 75 minutes absolute limit
EXECUTOR_TIMEOUT_SECS=4200   # 70 minutes for executor (leave 5 min for report)

DIRECTIVE_REPO="${1:-}"
STATE_DIR="$HOME/.openclaw/mpango-directive-runner"
STATE_FILE="$STATE_DIR/state.json"
LOG_DIR="$STATE_DIR/logs"
FALLBACK_REPORT_DIR="$STATE_DIR/fallback-reports"
REPORTS_DIR=""

mkdir -p "$LOG_DIR" "$FALLBACK_REPORT_DIR"

# ── Checkpoint System ──────────────────────────────────────────────────
# Global state tracking
CHECKPOINTS=""
LAST_CHECKPOINT="none"
CHECKPOINT_TS=""

checkpoint() {
  local name="$1"
  local ts
  ts="$(date -Is)"
  CHECKPOINTS+="  ✅ $name @ $ts
"
  LAST_CHECKPOINT="$name"
  CHECKPOINT_TS="$ts"
  echo "[CHECKPOINT] $name @ $ts"
}

checkpoint_warn() {
  local name="$1"
  local msg="${2:-}"
  local ts
  ts="$(date -Is)"
  CHECKPOINTS+="  ⚠️  $name @ $ts — $msg
"
  LAST_CHECKPOINT="$name (warn)"
  CHECKPOINT_TS="$ts"
  echo "[CHECKPOINT_WARN] $name @ $ts — $msg" >&2
}

checkpoint_fail() {
  local name="$1"
  local msg="${2:-}"
  local ts
  ts="$(date -Is)"
  CHECKPOINTS+="  ❌ $name @ $ts — $msg
"
  LAST_CHECKPOINT="$name (failed)"
  CHECKPOINT_TS="$ts"
  echo "[CHECKPOINT_FAIL] $name @ $ts — $msg" >&2
}

# ── Helpers ────────────────────────────────────────────────────────────
die() { echo "FATAL: $*" >&2; exit 2; }

elapsed_since() {
  echo $(( $(date +%s) - $1 ))
}

route_executor() {
  case "$1" in
    INVENTORY_ONLY)  echo "script-only" ;;
    VALIDATION_GATE) echo "leo-headless" ;;
    SCHEDULED_WATCH) echo "script-only" ;;
    *)               echo "unknown" ;;
  esac
}

# Robust field parser — tries multiple header formats
parse_field() {
  local field="$1" filepath="$2" default="${3:-}"
  local val=""
  # Try standard format: "Field-Name: value"
  val="$(grep -E "^${field}:" "$filepath" 2>/dev/null | head -1 | sed "s/^${field}: *//" | sed 's/[[:space:]]*$//' || true)"
  # Fallback: try lowercase, try with spaces
  if [ -z "$val" ]; then
    val="$(grep -iE "^${field}:" "$filepath" 2>/dev/null | head -1 | sed "s/^[^:]*: *//" | sed 's/[[:space:]]*$//' || true)"
  fi
  [ -z "$val" ] && val="$default"
  echo "$val"
}

# ── Validate input ─────────────────────────────────────────────────────
checkpoint "init"

[ -z "$DIRECTIVE_REPO" ] && { die "directive repo path missing"; }
[ -d "$DIRECTIVE_REPO" ] || { die "directive repo path invalid: $DIRECTIVE_REPO"; }

checkpoint "input_validated"

PENDING_DIR="$DIRECTIVE_REPO/docs/ai-directives/vibecoder/pending"
if [ ! -d "$PENDING_DIR" ]; then
  echo "No pending directive directory: $PENDING_DIR"
  exit 0
fi

touch "$STATE_FILE"

# ── Find latest unprocessed directive ───────────────────────────────────
checkpoint "scanning_pending"

latest_directive=""
latest_directive="$(find "$PENDING_DIR" -type f -name '*.md' -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2-)"
if [ -z "${latest_directive:-}" ]; then
  echo "No directive file found"
  exit 0
fi

checkpoint "directive_found"

directive_sha="$(sha256sum "$latest_directive" | awk '{print $1}')"
if grep -q "$directive_sha" "$STATE_FILE" 2>/dev/null; then
  echo "Directive already processed: $latest_directive"
  exit 0
fi

# ── Parse directive fields ─────────────────────────────────────────────
checkpoint "parsing_directive"

TASK_ID="$(parse_field 'Directive-ID' "$latest_directive" "$(parse_field 'Task ID' "$latest_directive" 'unknown')" | tr -d '[:space:]')"
[ -z "$TASK_ID" ] && TASK_ID="unknown"
MODE="$(parse_field 'Mode' "$latest_directive" '')"
PRIORITY="$(parse_field 'Priority' "$latest_directive" 'NORMAL')"
CREATED="$(parse_field 'Created' "$latest_directive" '')"
REPORT_BRANCH="$(parse_field 'Report branch' "$latest_directive" 'reports/lubuntu-validation')"
# Robust Report Path: try standard header, try "Report path", try body "Report path:" line
REPORT_PATH="$(parse_field 'Report path' "$latest_directive" "")"
if [ -z "$REPORT_PATH" ]; then
  # Try parsing from body (non-header lines)
  REPORT_PATH="$(grep -E '^Report path:' "$latest_directive" 2>/dev/null | head -1 | sed 's/^Report path: *//' | sed 's/[[:space:]]*$//' || true)"
fi
if [ -z "$REPORT_PATH" ]; then
  REPORT_PATH="docs/ai-reports/lubuntu/${TASK_ID}.md"
fi

# Validate mode
if ! echo "$MODE" | grep -Eq '^(INVENTORY_ONLY|VALIDATION_GATE|SCHEDULED_WATCH)$'; then
  die "invalid or missing Mode: '$MODE'"
fi

# Validate report path is not empty or just whitespace
if [ -z "$(echo "$REPORT_PATH" | tr -d '[:space:]')" ]; then
  die "Report path resolved to empty string. Directive must specify 'Report path:' header."
fi

# ── Setup ──────────────────────────────────────────────────────────────
checkpoint "setup"

run_id="$(date +%Y%m%d_%H%M%S)"
log_file="$LOG_DIR/${run_id}_directive.log"
# Handle absolute vs relative report paths
if echo "$REPORT_PATH" | grep -q '^/'; then
  report_file="$REPORT_PATH"
else
  report_file="$DIRECTIVE_REPO/$REPORT_PATH"
fi
REPORTS_DIR="$(dirname "$report_file")"
EXECUTOR_TYPE="$(route_executor "$MODE")"

# Verify report path won't resolve to a directory
if [ -d "$report_file" ]; then
  die "Report path resolves to directory, not file: $report_file"
fi

{
  echo "=== Directive Runner v3 (Hardened) ==="
  echo "Task ID: $TASK_ID"
  echo "Mode: $MODE"
  echo "Priority: $PRIORITY"
  echo "Report Branch: $REPORT_BRANCH"
  echo "Report Path: $REPORT_PATH"
  echo "Resolved Report File: $report_file"
  echo "Executor: $EXECUTOR_TYPE"
  echo "Timestamp: $(date -Is)"
  echo "Directive: $latest_directive"
  echo ""
} | tee "$log_file"

START_TIME="$(date +%s)"

# ── Leo Execution Evidence Tracking ─────────────────────────────────────
LEO_EXECUTED="false"
TRANSPORT_HEALTH="healthy"   # healthy | degraded | failed
LEO_INVOCATION_CMD=""
LEO_COMMANDS_RUN=0
LEO_COMMAND_RESULTS=""

# ── Heartbeat (background) ─────────────────────────────────────────────
heartbeat_pid=""
start_heartbeat() {
  (
    while true; do
      local elapsed phase
      elapsed="$(elapsed_since "$START_TIME")"
      phase="${LAST_CHECKPOINT:-executing}"
      echo "[HEARTBEAT] ts=$(date -Is) elapsed=${elapsed}s phase=$phase last_checkpoint=$LAST_CHECKPOINT directive=$TASK_ID"
      sleep "$HEARTBEAT_INTERVAL"
    done
  ) &
  heartbeat_pid=$!
}

stop_heartbeat() {
  if [ -n "$heartbeat_pid" ]; then
    kill "$heartbeat_pid" 2>/dev/null || true
    wait "$heartbeat_pid" 2>/dev/null || true
    heartbeat_pid=""
  fi
  return 0
}

trap 'stop_heartbeat; echo "[TRAP] Caught signal, generating failure report..."; write_failure_report "INTERRUPTED" "Runner caught signal during execution" "$(elapsed_since "$START_TIME")"; exit 1' INT TERM

# ── Script-only executor ───────────────────────────────────────────────
run_script_only() {
  checkpoint "env_snapshot_start"

  local output=""
  output+="=== Environment Snapshot ($(date -Is)) ===\n"
  output+="hostname: $(hostname)\n"
  output+="os: $(uname -a)\n"
  output+="git: $(git --version 2>/dev/null || echo 'NOT FOUND')\n"
  output+="python: $(python3 --version 2>/dev/null || echo 'NOT FOUND')\n"
  output+="poetry: $(poetry --version 2>/dev/null || echo 'NOT FOUND')\n"
  output+="node: $(node --version 2>/dev/null || echo 'NOT FOUND')\n"
  output+="docker: $(docker --version 2>/dev/null || echo 'NOT FOUND')\n"
  output+="disk_free: $(df -h --output=avail / | tail -1 | xargs)\n"
  output+="memory_free: $(free -h | awk '/Mem:/{print $7}')\n"
  output+="runner_user: $(whoami)\n\n"

  checkpoint "env_snapshot_done"

  output+="=== Git State ===\n"
  if git -C "$DIRECTIVE_REPO" rev-parse --git-dir &>/dev/null; then
    output+="branch: $(git -C "$DIRECTIVE_REPO" rev-parse --abbrev-ref HEAD 2>/dev/null)\n"
    output+="HEAD: $(git -C "$DIRECTIVE_REPO" rev-parse --short HEAD 2>/dev/null)\n"
    output+="clean: $(git -C "$DIRECTIVE_REPO" diff --quiet && echo 'yes' || echo 'no')\n"
    output+="status:\n$(git -C "$DIRECTIVE_REPO" status --short 2>/dev/null)\n"
    output+="recent:\n$(git -C "$DIRECTIVE_REPO" log --oneline -5 2>/dev/null)\n"
  else
    output+="not a git repository\n"
  fi
  output+="\n=== Pending Directives ===\n"
  output+="$(ls -la "$PENDING_DIR/" 2>/dev/null || echo 'N/A')\n"

  checkpoint "script_only_complete"

  echo -e "$output"
}

# ── Leo headless executor ─────────────────────────────────────────────
run_leo_headless() {
  checkpoint "leo_executor_start"

  if ! command -v openclaw &>/dev/null; then
    checkpoint_fail "leo_executor" "openclaw CLI not found in PATH"
    echo "BLOCKED_ENVIRONMENT: openclaw CLI not found"
    return 1
  fi

  checkpoint "leo_cli_verified"

  local directive_content
  directive_content="$(cat "$latest_directive")"

  LEO_INVOCATION_CMD="openclaw agent --agent main --message 'CTO_DIRECTIVE_TRIGGER' --json"
  LEO_EXECUTED="true"

  checkpoint "leo_invoked"

  local raw_output=""
  local rc=0

  # Wrap in timeout, capture exit code properly
  raw_output="$(timeout "$EXECUTOR_TIMEOUT_SECS" \
    openclaw agent \
      --agent main \
      --message "CTO_DIRECTIVE_TRIGGER

Task ID: $TASK_ID
Mode: $MODE
Report Branch: $REPORT_BRANCH
Report Path: $REPORT_PATH

Directive file: $latest_directive

--- Directive Content ---
$directive_content
--- End Directive ---

Execute the leo-headless-runner skill for this directive.
Do NOT wait for human input. Generate report and exit." \
      --json 2>&1)" || rc=$?

  LEO_COMMANDS_RUN=1  # At minimum, the invocation command itself counts

  # ── Transport Health Detection ──────────────────────────────────────
  # Inspect openclaw agent --json output for transport type.
  # "gateway" = healthy path. "embedded" = degraded (fallback).
  if echo "$raw_output" | grep -qE '"(transport|runner)"[[:space:]]*:[[:space:]]*"embedded"'; then
    TRANSPORT_HEALTH="degraded"
    checkpoint_warn "transport_health" "embedded fallback detected — Gateway path not used"
    echo "[TRANSPORT_DEGRADED] openclaw agent used embedded fallback (not Gateway)"
  elif echo "$raw_output" | grep -qE '"(transport|runner)"[[:space:]]*:[[:space:]]*"gateway"'; then
    TRANSPORT_HEALTH="healthy"
    checkpoint "transport_health"
    echo "[TRANSPORT_HEALTHY] openclaw agent used Gateway path"
  elif echo "$raw_output" | grep -q "EMBEDDED FALLBACK"; then
    TRANSPORT_HEALTH="degraded"
    checkpoint_warn "transport_health" "embedded fallback detected (fallback string)"
    echo "[TRANSPORT_DEGRADED] EMBEDDED FALLBACK detected in output"
  else
    # Cannot determine — if rc=0, assume healthy but note uncertainty
    if [ "$rc" -eq 0 ]; then
      checkpoint_warn "transport_health" "transport type undetermined, assuming healthy (rc=0)"
      echo "[TRANSPORT_UNKNOWN] Could not detect transport type, rc=0"
    else
      TRANSPORT_HEALTH="failed"
      checkpoint_fail "transport_health" "transport undetermined and rc=$rc"
      echo "[TRANSPORT_FAILED] Could not detect transport type, rc=$rc"
    fi
  fi

  if [ "$rc" -eq 0 ]; then
    checkpoint "leo_executor_complete"
    # Try to extract evidence of command execution from output
    if echo "$raw_output" | grep -qiE "(git |pytest |python |alembic |docker )"; then
      LEO_COMMANDS_RUN=2
      LEO_COMMAND_RESULTS="Evidence of command execution found in output (see report)"
    fi
    echo "$raw_output"
  elif [ "$rc" -eq 124 ]; then
    checkpoint_fail "leo_executor" "timeout after ${EXECUTOR_TIMEOUT_SECS}s"
    echo "BLOCKED_EXECUTOR_TIMEOUT: Leo executor exceeded ${EXECUTOR_TIMEOUT_SECS}s"
    echo ""
    echo "Last 50 lines of output:"
    echo "$raw_output" | tail -50
    return 124
  else
    checkpoint_fail "leo_executor" "exit code $rc"
    echo "FAIL_RUNNER_INFRA: Leo executor failed with exit code $rc"
    echo ""
    echo "Last 50 lines of output:"
    echo "$raw_output" | tail -50
    return "$rc"
  fi
}

# ── Report writer (success) ───────────────────────────────────────────
write_report() {
  local verdict="$1" output="$2" duration="$3" commit="${4:-N/A}" branch="${5:-N/A}"
  local run_url="${GITHUB_SERVER_URL:-unknown}/${GITHUB_REPOSITORY:-unknown}/actions/runs/${GITHUB_RUN_ID:-unknown}"

  mkdir -p "$REPORTS_DIR" 2>/dev/null || true

  local leo_section=""
  if [ "$EXECUTOR_TYPE" = "leo-headless" ]; then
    leo_section="
## Leo Execution Evidence

| Field | Value |
|-------|-------|
| Leo Invoked | $LEO_EXECUTED |
| Invocation Command | \`${LEO_INVOCATION_CMD}\` |
| Commands Executed | $LEO_COMMANDS_RUN |
| Command Results | $LEO_COMMAND_RESULTS |
"
  fi

  local report_content=""
  report_content=$(cat << REPORT_EOF
# Directive Execution Report

## Metadata

| Field | Value |
|-------|-------|
| Directive-ID | $TASK_ID |
| Mode | $MODE |
| Priority | $PRIORITY |
| Created | $CREATED |
| Executed | $(date -Is) |
| Duration | ${duration}s |
| Verdict | **$verdict** |
| Transport Health | $TRANSPORT_HEALTH |
| Executor | $EXECUTOR_TYPE |
| Runner | run_directive.sh v3 (hardened) |
| Commit | $commit |
| Branch | $branch |
| Run URL | $run_url |
| Report Path | $REPORT_PATH |
$leo_section

## Checkpoints

$CHECKPOINTS

## Output

\`\`\`
$output
\`\`\`

---
Generated by Mpango Directive Runner v3 (Hardened) at $(date -Is)
REPORT_EOF
)

  # Try to write to primary path
  if echo "$report_content" > "$report_file" 2>/dev/null; then
    echo "[REPORT] Written to primary: $report_file"
    return 0
  else
    # Fallback: write to local state directory
    local fallback_file="$FALLBACK_REPORT_DIR/${run_id}_${TASK_ID}_fallback.md"
    echo "$report_content" > "$fallback_file"
    echo "[REPORT_FALLBACK] Primary write failed. Written to: $fallback_file"
    echo "[REPORT_FALLBACK] Primary path was: $report_file"
    return 1
  fi
}

# ── Failure report (always generated) ──────────────────────────────────
write_failure_report() {
  local verdict="$1" reason="$2" duration="$3"
  local run_url="${GITHUB_SERVER_URL:-unknown}/${GITHUB_REPOSITORY:-unknown}/actions/runs/${GITHUB_RUN_ID:-unknown}"
  local commit="${4:-N/A}"
  local branch="${5:-N/A}"
  local stderr_summary=""

  # Capture last 20 lines from log if available
  if [ -f "$log_file" ]; then
    stderr_summary="$(tail -20 "$log_file" 2>/dev/null || true)"
  fi

  local leo_section=""
  if [ "$EXECUTOR_TYPE" = "leo-headless" ]; then
    leo_section="
### Leo Execution Evidence
- Leo Invoked: $LEO_EXECUTED
- Commands Executed: $LEO_COMMANDS_RUN
"
  fi

  local report_content=""
  report_content=$(cat << REPORT_EOF
# Directive Execution Report — FAILURE

## Metadata

| Field | Value |
|-------|-------|
| Directive-ID | $TASK_ID |
| Mode | $MODE |
| Verdict | **$verdict** |
| Executor | $EXECUTOR_TYPE |
| Runner | run_directive.sh v3 (hardened) |
| Commit | $commit |
| Branch | $branch |
| Run URL | $run_url |
| Report Path (intended) | $REPORT_PATH |
| Duration | ${duration}s |

## Failure Details

| Field | Value |
|-------|-------|
| Failure Reason | $reason |
| Last Checkpoint | $LAST_CHECKPOINT |
| Last Checkpoint Time | $CHECKPOINT_TS |
$leo_section

## Checkpoints

$CHECKPOINTS

## Last Log Output

\`\`\`
$stderr_summary
\`\`\`

## Next Action

Review the failure reason above. Check:
1. Runner environment (openclaw installed, reachable)
2. Directive file format (valid Mode, Report path headers)
3. GitHub Actions job logs for full trace

---
Generated by Mpango Directive Runner v3 (Hardened) at $(date -Is)
REPORT_EOF
)

  # Try primary path first
  mkdir -p "$REPORTS_DIR" 2>/dev/null || true
  if echo "$report_content" > "$report_file" 2>/dev/null; then
    echo "[FAILURE_REPORT] Written to primary: $report_file"
    return 0
  fi

  # Fallback path
  local fallback_file="$FALLBACK_REPORT_DIR/${run_id}_${TASK_ID}_failure.md"
  mkdir -p "$FALLBACK_REPORT_DIR"
  echo "$report_content" > "$fallback_file"
  echo "[FAILURE_REPORT_FALLBACK] Primary write failed. Written to: $fallback_file"
  echo "[FAILURE_REPORT_FALLBACK] Primary path was: $report_file"
  return 1
}

# ── Report Existence Final Gate ───────────────────────────────────────
verify_report_exists() {
  if [ -f "$report_file" ]; then
    checkpoint "report_exists_gate_pass"
    echo "[GATE] Report exists: $report_file"
    return 0
  else
    checkpoint_fail "report_exists_gate" "report not found at $report_file"
    echo "[GATE_FAIL] Report NOT found at: $report_file"
    # Check fallback
    local fallback_pattern="$FALLBACK_REPORT_DIR/${run_id}_${TASK_ID}_*"
    local fallback_count
    fallback_count="$(find "$FALLBACK_REPORT_DIR" -name "${run_id}_${TASK_ID}_*" -type f 2>/dev/null | wc -l)"
    if [ "$fallback_count" -gt 0 ]; then
      echo "[GATE_WARN] Fallback report(s) exist: $fallback_count file(s)"
      find "$FALLBACK_REPORT_DIR" -name "${run_id}_${TASK_ID}_*" -type f
      return 1
    fi
    echo "[GATE_FAIL] No report (primary or fallback) found!"
    return 1
  fi
}

# ── Leo Execution Evidence Gate ───────────────────────────────────────
verify_leo_evidence() {
  if [ "$EXECUTOR_TYPE" != "leo-headless" ]; then
    checkpoint "leo_evidence_gate_skip"
    echo "[GATE_SKIP] Leo evidence gate skipped (executor=$EXECUTOR_TYPE)"
    return 0
  fi

  if [ "$LEO_EXECUTED" != "true" ]; then
    checkpoint_fail "leo_evidence_gate" "Leo was NOT invoked"
    return 1
  fi

  checkpoint "leo_evidence_gate_pass"
  echo "[GATE] Leo execution evidence: invoked=$LEO_EXECUTED commands=$LEO_COMMANDS_RUN"
  return 0
}

# ── Main execution ─────────────────────────────────────────────────────
VERDICT="PASS_FOR_CTO_REVIEW"
EXECUTOR_OUTPUT=""

echo "[EXEC] executor=$EXECUTOR_TYPE mode=$MODE ts=$(date -Is)" | tee -a "$log_file"

checkpoint "heartbeat_start"
start_heartbeat

# Get git info for report metadata
COMMIT_INFO="$(git -C "$DIRECTIVE_REPO" rev-parse --short HEAD 2>/dev/null || echo 'unknown')"
BRANCH_INFO="$(git -C "$DIRECTIVE_REPO" rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'unknown')"

case "$EXECUTOR_TYPE" in
  script-only)
    checkpoint "executor_script_only_start"
    # [FIX v3.1] file-based capture to preserve shell variables
    local _tmp_out="$STATE_DIR/exec_output_${run_id}.txt"
    run_script_only > "$_tmp_out" 2>&1 || true
    EXECUTOR_OUTPUT="$(cat "$_tmp_out")"
    ;;
  leo-headless)
    checkpoint "executor_leo_headless_start"
    # [FIX v3.1] file-based capture to preserve shell variables
    local _tmp_out="$STATE_DIR/exec_output_${run_id}.txt"
    run_leo_headless > "$_tmp_out" 2>&1
    local rc=$?
    EXECUTOR_OUTPUT="$(cat "$_tmp_out")"
    if [ $rc -ne 0 ]; then
      stop_heartbeat
      local elapsed
      elapsed="$(elapsed_since "$START_TIME")"

      if [ "$rc" -eq 124 ]; then
        VERDICT="BLOCKED_ENVIRONMENT"
      else
        VERDICT="FAIL_RUNNER_INFRA"
      fi

      # Generate failure report (guaranteed)
      write_failure_report "$VERDICT" "Leo executor failed with exit code $rc" "$elapsed" "$COMMIT_INFO" "$BRANCH_INFO"

      # Final gates
      verify_report_exists || echo "[WARN] Report gate failed after executor error"
      verify_leo_evidence || echo "[WARN] Leo evidence gate failed after executor error"

      # Mark processed
      echo "$directive_sha $latest_directive $(date -Is) verdict=$VERDICT executor=$EXECUTOR_TYPE" >> "$STATE_FILE"

      echo "[EXIT] ts=$(date -Is) directive=$TASK_ID verdict=$VERDICT duration=${elapsed}s executor=$EXECUTOR_TYPE" | tee -a "$log_file"
      exit 1
    fi
    ;;
  *)
    VERDICT="FAIL_RUNNER_INFRA"
    write_failure_report "$VERDICT" "Unknown executor type: $EXECUTOR_TYPE" "$(elapsed_since "$START_TIME")" "$COMMIT_INFO" "$BRANCH_INFO"
    exit 1
    ;;
esac

echo -e "$EXECUTOR_OUTPUT" >> "$log_file"

# ── Stop heartbeat, check timeout ─────────────────────────────────────
stop_heartbeat
ELAPSED="$(elapsed_since "$START_TIME")"

checkpoint "heartbeat_stopped"

if [ "$ELAPSED" -gt "$TOTAL_TIMEOUT_SECS" ]; then
  VERDICT="BLOCKED_ENVIRONMENT"
  checkpoint_fail "timeout_check" "exceeded ${TOTAL_TIMEOUT_SECS}s"
  write_failure_report "$VERDICT" "Total timeout exceeded ${TOTAL_TIMEOUT_SECS}s" "$ELAPSED" "$COMMIT_INFO" "$BRANCH_INFO"
  verify_report_exists || true
  echo "$directive_sha $latest_directive $(date -Is) verdict=$VERDICT executor=$EXECUTOR_TYPE" >> "$STATE_FILE"
  echo "[EXIT] ts=$(date -Is) directive=$TASK_ID verdict=$VERDICT duration=${ELAPSED}s executor=$EXECUTOR_TYPE" | tee -a "$log_file"
  exit 1
fi

checkpoint "timeout_check_pass"

# ── Transport Health Gate ────────────────────────────────────────────
# Three-tier verdict based on CTO directive:
#   Gateway healthy + validation OK           → PASS_FOR_CTO_REVIEW
#   Gateway degraded (embedded fallback)       → FAIL_RUNNER_INFRA_WITH_VALIDATION_COMPLETED
#   Gateway failed + validation failed/timeout → FAIL_RUNNER_INFRA
checkpoint "transport_gate"

if [ "$TRANSPORT_HEALTH" = "degraded" ]; then
  VERDICT="FAIL_RUNNER_INFRA_WITH_VALIDATION_COMPLETED"
  checkpoint_warn "transport_gate" "transport degraded — validation may have completed but infra path is unhealthy"
  echo "[TRANSPORT_GATE] DEGRADED: embedded fallback was used. Setting verdict to FAIL_RUNNER_INFRA_WITH_VALIDATION_COMPLETED"
elif [ "$TRANSPORT_HEALTH" = "failed" ]; then
  VERDICT="FAIL_RUNNER_INFRA"
  checkpoint_fail "transport_gate" "transport failed"
  echo "[TRANSPORT_GATE] FAILED: transport health is failed"
else
  checkpoint "transport_gate"
fi

# ── Leo Execution Evidence Gate (VALIDATION_GATE only) ────────────────
if ! verify_leo_evidence; then
  if [ "$VERDICT" = "FAIL_RUNNER_INFRA_WITH_VALIDATION_COMPLETED" ]; then
    # Keep the more specific degraded verdict
    checkpoint_warn "leo_evidence_gate" "evidence gate failed on top of degraded transport"
  else
    VERDICT="FAIL_RUNNER_INFRA"
  fi
  write_failure_report "$VERDICT" "Leo execution evidence gate failed" "$ELAPSED" "$COMMIT_INFO" "$BRANCH_INFO"
fi

# ── Write report ───────────────────────────────────────────────────────
checkpoint "report_write_start"

REPORT_WRITE_RC=0
if [ "$VERDICT" = "PASS_FOR_CTO_REVIEW" ]; then
  write_report "$VERDICT" "$EXECUTOR_OUTPUT" "$ELAPSED" "$COMMIT_INFO" "$BRANCH_INFO" || REPORT_WRITE_RC=$?
  if [ "$REPORT_WRITE_RC" -ne 0 ]; then
    checkpoint_warn "report_written" "primary path failed, fallback used"
    VERDICT="FAIL_RUNNER_INFRA"
  else
    checkpoint "report_written"
  fi
else
  # Already written by failure handler, but write again to be safe
  write_failure_report "$VERDICT" "See checkpoints for failure details" "$ELAPSED" "$COMMIT_INFO" "$BRANCH_INFO" || true
fi

# ── Report Existence Final Gate ───────────────────────────────────────
checkpoint "report_existence_gate"

if ! verify_report_exists; then
  # If we get here with no report at primary path, check fallback
  VERDICT="FAIL_RUNNER_INFRA"
  echo "[CRITICAL] Report not at primary path."
  # Force-write one more failure report as absolute last resort
  write_failure_report "$VERDICT" "Report existence final gate failed — no report at primary path" "$ELAPSED" "$COMMIT_INFO" "$BRANCH_INFO" || true
fi

# ── Mark processed ─────────────────────────────────────────────────────
checkpoint "mark_processed"

echo "$directive_sha $latest_directive $(date -Is) verdict=$VERDICT executor=$EXECUTOR_TYPE checkpoints=$(echo -e "$CHECKPOINTS" | grep -cE '✅|⚠️|❌' || echo 0)" >> "$STATE_FILE"

# ── Exit ───────────────────────────────────────────────────────────────
checkpoint "exit"

echo "[EXIT] ts=$(date -Is) directive=$TASK_ID verdict=$VERDICT duration=${ELAPSED}s executor=$EXECUTOR_TYPE report=$report_file" | tee -a "$log_file"

case "$VERDICT" in
  PASS_FOR_CTO_REVIEW)
    exit 0 ;;
  PARTIAL_PASS_WITH_DB_EVIDENCE_GAP)
    exit 0 ;;
  FAIL_RUNNER_INFRA_WITH_VALIDATION_COMPLETED)
    exit 1 ;;  # degraded path — non-zero exit per CTO directive
  *)
    exit 1 ;;
esac
