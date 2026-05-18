#!/usr/bin/env bash
# run_directive.sh v3.4 — Hardened Directive Runner (Path Isolation Fix)
#
# R6 Architecture Changes:
#   B. Directive repo (directives/) vs validation target (validation-target/) separated
#   C. Report generation: script generates deterministic report, Leo outputs raw evidence only
#   D. Reports staged to $GITHUB_WORKSPACE/generated-reports/
#   E. Final Gate: hard failure if report missing or incomplete
#
# Preserves from v3.3:
#   - Report Existence Final Gate
#   - Leo Execution Evidence Gate
#   - Checkpoint / Progress Gate
#   - Failure Report Guarantee
#   - Heartbeat / Timeout
#   - Verdict Discipline
#
# Routes: INVENTORY_ONLY/SCHEDULED_WATCH → script-only | VALIDATION_GATE → Leo headless
# Never calls chat-type Vibecoder agent.
set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────────
HEARTBEAT_INTERVAL=60        # seconds between heartbeat markers
TOTAL_TIMEOUT_SECS=4500      # 75 minutes absolute limit
EXECUTOR_TIMEOUT_SECS=4200   # 70 minutes for executor (leave 5 min for report)

DIRECTIVE_REPO="${1:-}"
VALIDATION_TARGET="${2:-}"
STATE_DIR="$HOME/.openclaw/mpango-directive-runner"
STATE_FILE="$STATE_DIR/state.json"
LOG_DIR="$STATE_DIR/logs"
FALLBACK_REPORT_DIR="$STATE_DIR/fallback-reports"
GENERATED_REPORTS_DIR="${GITHUB_WORKSPACE:-/tmp}/generated-reports"
METADATA_FILE="$GENERATED_REPORTS_DIR/_metadata.txt"

mkdir -p "$LOG_DIR" "$FALLBACK_REPORT_DIR" "$GENERATED_REPORTS_DIR"

# ── Checkpoint System ──────────────────────────────────────────────────
CHECKPOINTS=""
LAST_CHECKPOINT="none"
CHECKPOINT_TS=""

checkpoint() {
  local name="$1"
  local ts
  ts="$(date -Is)"
  CHECKPOINTS+="  ✅ $name @ $ts\n"
  LAST_CHECKPOINT="$name"
  CHECKPOINT_TS="$ts"
  echo "[CHECKPOINT] $name @ $ts"
}

checkpoint_warn() {
  local name="$1"
  local msg="${2:-}"
  local ts
  ts="$(date -Is)"
  CHECKPOINTS+="  ⚠️  $name @ $ts — $msg\n"
  LAST_CHECKPOINT="$name (warn)"
  CHECKPOINT_TS="$ts"
  echo "[CHECKPOINT_WARN] $name @ $ts — $msg" >&2
}

checkpoint_fail() {
  local name="$1"
  local msg="${2:-}"
  local ts
  ts="$(date -Is)"
  CHECKPOINTS+="  ❌ $name @ $ts — $msg\n"
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
  val="$(grep -E "^${field}:" "$filepath" 2>/dev/null | head -1 | sed "s/^${field}: *//" | sed 's/[[:space:]]*$//' || true)"
  if [ -z "$val" ]; then
    val="$(grep -iE "^${field}:" "$filepath" 2>/dev/null | head -1 | sed "s/^[^:]*: *//" | sed 's/[[:space:]]*$//' || true)"
  fi
  [ -z "$val" ] && val="$default"
  echo "$val"
}

# Parse evidence fields directly from raw JSON output.
# The openclaw agent --json output contains the text in result.payloads[0].text
# with \\n as literal escape sequences (not real newlines in the JSON source).
# We use grep -oP to extract each field value, stopping at \\ or \" boundaries.
parse_evidence_from_json() {
  local field="$1" json="$2"
  # v3.4: Use jq to extract clean text from JSON, parse evidence from unescaped content
  local clean_text
  clean_text="$(echo "$json" | sed -n '/^{/,/^}/p' | jq -r '\
    .result.payloads[0].text //\
    .payloads[0].text //\
    .result.finalAssistantVisibleText //\
    .finalAssistantVisibleText //\
    empty\
  ' 2>/dev/null)"
  if [ -n "$clean_text" ]; then
    echo "$clean_text" | grep -oP "${field}:[[:space:]]*\\K[^\\n]+" | head -1 | sed 's/[[:space:]]*$//' || echo "unknown"
  else
    echo "$json" | grep -oP "${field}:[[:space:]]*\\K[^\\]+" | head -1 | sed 's/[[:space:]]*$//' || echo "unknown"
  fi
}

# Parse evidence field from clean text (with real newlines)
parse_evidence() {
  local field="$1" text="$2"
  echo "$text" | grep -iE "${field}:" | head -1 | sed "s/[^:]*:[[:space:]]*//" | sed 's/[[:space:]]*$//' || echo "unknown"
}

# ── Validate input ─────────────────────────────────────────────────────
checkpoint "init"

[ -z "$DIRECTIVE_REPO" ] && { die "directive repo path missing"; }
[ -d "$DIRECTIVE_REPO" ] || { die "directive repo path invalid: $DIRECTIVE_REPO"; }

# R6: Validate validation target
if [ -z "$VALIDATION_TARGET" ]; then
  checkpoint_warn "validation_target" "VALIDATION_TARGET not provided — Leo will work in directives repo (NOT RECOMMENDED for R6)"
else
  if [ ! -d "$VALIDATION_TARGET" ]; then
    checkpoint_warn "validation_target" "VALIDATION_TARGET directory does not exist: $VALIDATION_TARGET"
  else
    checkpoint "validation_target_verified" "path=$VALIDATION_TARGET"
  fi
fi

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
REPORT_PATH="$(parse_field 'Report path' "$latest_directive" "")"
if [ -z "$REPORT_PATH" ]; then
  REPORT_PATH="$(grep -E '^Report path:' "$latest_directive" 2>/dev/null | head -1 | sed 's/^Report path: *//' | sed 's/[[:space:]]*$//' || true)"
fi
if [ -z "$REPORT_PATH" ]; then
  REPORT_PATH="docs/ai-reports/lubuntu/${TASK_ID}.md"
fi

# R6: Parse target branch
TARGET_BRANCH="$(parse_field 'Target branch' "$latest_directive" 'product-dev-recovered')"

if ! echo "$MODE" | grep -Eq '^(INVENTORY_ONLY|VALIDATION_GATE|SCHEDULED_WATCH)$'; then
  die "invalid or missing Mode: '$MODE'"
fi

if [ -z "$(echo "$REPORT_PATH" | tr -d '[:space:]')" ]; then
  die "Report path resolved to empty string."
fi

# ── Setup ──────────────────────────────────────────────────────────────
checkpoint "setup"

run_id="$(date +%Y%m%d_%H%M%S)"
log_file="$LOG_DIR/${run_id}_directive.log"
REPORTS_DIR="$(dirname "$REPORT_PATH")"
EXECUTOR_TYPE="$(route_executor "$MODE")"

# R6: Report staging path — NOT in directives repo
REPORT_BASENAME="$(basename "$REPORT_PATH")"
report_staging_file="$GENERATED_REPORTS_DIR/$REPORT_BASENAME"

# Verify report path won't resolve to a directory
if echo "$REPORT_PATH" | grep -q '/$'; then
  die "Report path ends with / — must be a file, not directory: $REPORT_PATH"
fi

{
  echo "=== Directive Runner v3.4 (Path Isolation Fix) ==="
  echo "Task ID: $TASK_ID"
  echo "Mode: $MODE"
  echo "Priority: $PRIORITY"
  echo "Report Branch: $REPORT_BRANCH"
  echo "Report Path (on branch): $REPORT_PATH"
  echo "Report Staging: $report_staging_file"
  echo "Target Branch: $TARGET_BRANCH"
  echo "Directive Repo: $DIRECTIVE_REPO"
  echo "Validation Target: $VALIDATION_TARGET"
  echo "Executor: $EXECUTOR_TYPE"
  echo "Timestamp: $(date -Is)"
  echo "Directive: $latest_directive"
  echo ""
} | tee "$log_file"

START_TIME="$(date +%s)"

# ── Leo Evidence Fields (populated after Leo runs) ─────────────────────
LEO_EXECUTED="false"
TRANSPORT_HEALTH="healthy"
LEO_INVOCATION_CMD=""
LEO_COMMANDS_RUN=0
LEO_COMMAND_RESULTS=""
LEO_RAW_EVIDENCE=""

# Evidence fields parsed from Leo output
EVIDENCE_VERDICT="unknown"
EVIDENCE_COMMANDS="unknown"
EVIDENCE_CMD1_FETCH="unknown"
EVIDENCE_CMD2_CHECKOUT="unknown"
EVIDENCE_CMD3_REVPARSE="unknown"
EVIDENCE_CMD4_STATUS="unknown"
EVIDENCE_CMD5_LOG="unknown"
EVIDENCE_PRODUCT_MODIFIED="unknown"
EVIDENCE_BRANCH_PUSHED="unknown"
EVIDENCE_COMMIT_HASH="unknown"
EVIDENCE_LATEST_COMMIT="unknown"

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

# ── Script-only executor (unchanged) ───────────────────────────────────
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

# ── Leo headless executor (R6: isolated to VALIDATION_TARGET) ─────────
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

  LEO_INVOCATION_CMD="openclaw agent --agent main --message 'CTO_DIRECTIVE_TRIGGER'"
  LEO_EXECUTED="true"

  checkpoint "leo_invoked"

  local raw_output=""
  local rc=0

  # R6: Leo prompt — work in VALIDATION_TARGET, output raw evidence, NO report files
  local leo_prompt=""
  leo_prompt+="CTO_DIRECTIVE_TRIGGER\n\n"
  leo_prompt+="Task ID: $TASK_ID\n"
  leo_prompt+="Mode: $MODE\n"
  leo_prompt+="Target Branch: $TARGET_BRANCH\n\n"
  leo_prompt+="Directive file: $latest_directive\n\n"
  leo_prompt+="--- Directive Content ---\n"
  leo_prompt+="$directive_content\n"
  leo_prompt+="--- End Directive ---\n\n"
  leo_prompt+="INSTRUCTIONS FOR LEO (R6 PATH ISOLATION):\n\n"
  leo_prompt+="1. Your working directory MUST be: $VALIDATION_TARGET\n"
  leo_prompt+="   - All git commands must be executed in this directory\n"
  leo_prompt+="   - Use absolute paths for all git operations\n\n"
  leo_prompt+="2. FORBIDDEN ACTIONS:\n"
  leo_prompt+="   - Do NOT cd to $DIRECTIVE_REPO\n"
  leo_prompt+="   - Do NOT execute git checkout/reset/pull in $DIRECTIVE_REPO\n"
  leo_prompt+="   - Do NOT write any report file anywhere\n"
  leo_prompt+="   - Do NOT git push to any branch\n"
  leo_prompt+="   - Do NOT modify any tracked files\n\n"
  leo_prompt+="3. Execute these 5 git commands IN ORDER in $VALIDATION_TARGET:\n"
  leo_prompt+="   git -C $VALIDATION_TARGET fetch origin --prune\n"
  leo_prompt+="   git -C $VALIDATION_TARGET checkout origin/$TARGET_BRANCH --detach\n"
  leo_prompt+="   git -C $VALIDATION_TARGET rev-parse HEAD\n"
  leo_prompt+="   git -C $VALIDATION_TARGET status --short\n"
  leo_prompt+="   git -C $VALIDATION_TARGET log -1 --oneline\n\n"
  leo_prompt+="4. After executing all 5 commands, output your evidence in EXACTLY this format:\n"
  leo_prompt+="=== LEO_EVIDENCE ===\n"
  leo_prompt+="VERDICT: PASS_FOR_CTO_REVIEW\n"
  leo_prompt+="COMMANDS_EXECUTED: 5/5\n"
  leo_prompt+="CMD1_FETCH: PASS\n"
  leo_prompt+="CMD2_CHECKOUT: PASS\n"
  leo_prompt+="CMD3_REVPARSE: <hash>\n"
  leo_prompt+="CMD4_STATUS: clean\n"
  leo_prompt+="CMD5_LOG: <commit message>\n"
  leo_prompt+="PRODUCT_CODE_MODIFIED: no\n"
  leo_prompt+="PRODUCT_BRANCH_PUSHED: no\n"
  leo_prompt+="COMMIT_HASH: <full hash>\n"
  leo_prompt+="LATEST_COMMIT: <commit message>\n"
  leo_prompt+="=== LEO_EVIDENCE_END ===\n\n"
  leo_prompt+="5. Do NOT wait for human input. Execute and output evidence immediately.\n"

  # Wrap in timeout, capture exit code properly
  raw_output="$(timeout "$EXECUTOR_TIMEOUT_SECS" \
    openclaw agent \
      --agent main \
      --message "$leo_prompt" \
      --json 2>&1)" || rc=$?

  LEO_COMMANDS_RUN=1

  # ── Transport Health Detection ───────────────────────────────────
  if echo "$raw_output" | grep -qE '"fallbackUsed"[[:space:]]*:[[:space:]]*true'; then
    TRANSPORT_HEALTH="degraded"
    checkpoint_warn "transport_health" "fallbackUsed=true"
    echo "[TRANSPORT_DEGRADED] fallbackUsed=true"
  elif echo "$raw_output" | grep -qE '"fallbackUsed"[[:space:]]*:[[:space:]]*false'; then
    TRANSPORT_HEALTH="healthy"
    checkpoint "transport_health" "fallbackUsed=false"
    echo "[TRANSPORT_HEALTHY] fallbackUsed=false"
  elif echo "$raw_output" | grep -qE '"(transport|runner)"[[:space:]]*:[[:space:]]*"gateway"'; then
    TRANSPORT_HEALTH="healthy"
    checkpoint "transport_health"
    echo "[TRANSPORT_HEALTHY] gateway detected"
  elif [ "$rc" -eq 0 ]; then
    if echo "$raw_output" | grep -qE '"calls"[[:space:]]*:[[:space:]]*[1-9]'; then
      TRANSPORT_HEALTH="healthy"
      checkpoint "transport_health" "rc=0 with tool calls"
    else
      TRANSPORT_HEALTH="healthy"
      checkpoint_warn "transport_health" "undetermined, assuming healthy (rc=0)"
    fi
  else
    TRANSPORT_HEALTH="failed"
    checkpoint_fail "transport_health" "transport undetermined and rc=$rc"
  fi

  if [ "$rc" -eq 0 ]; then
    checkpoint "leo_executor_complete"
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

# ── Parse Leo Evidence ─────────────────────────────────────────────────
parse_leo_evidence() {
  local raw="$1"
  LEO_RAW_EVIDENCE="$raw"

  # R6b: Parse directly from raw JSON output.
  # The text is in result.payloads[0].text with \\n escapes.
  # grep -oP extracts field values stopping at \\ or \" boundaries.
  EVIDENCE_VERDICT="$(parse_evidence_from_json 'VERDICT' "$raw")"
  EVIDENCE_COMMANDS="$(parse_evidence_from_json 'COMMANDS_EXECUTED' "$raw")"
  EVIDENCE_CMD1_FETCH="$(parse_evidence_from_json 'CMD1_FETCH' "$raw")"
  EVIDENCE_CMD2_CHECKOUT="$(parse_evidence_from_json 'CMD2_CHECKOUT' "$raw")"
  EVIDENCE_CMD3_REVPARSE="$(parse_evidence_from_json 'CMD3_REVPARSE' "$raw")"
  EVIDENCE_CMD4_STATUS="$(parse_evidence_from_json 'CMD4_STATUS' "$raw")"
  EVIDENCE_CMD5_LOG="$(parse_evidence_from_json 'CMD5_LOG' "$raw")"
  EVIDENCE_PRODUCT_MODIFIED="$(parse_evidence_from_json 'PRODUCT_CODE_MODIFIED' "$raw")"
  EVIDENCE_BRANCH_PUSHED="$(parse_evidence_from_json 'PRODUCT_BRANCH_PUSHED' "$raw")"
  EVIDENCE_COMMIT_HASH="$(parse_evidence_from_json 'COMMIT_HASH' "$raw")"
  EVIDENCE_LATEST_COMMIT="$(parse_evidence_from_json 'LATEST_COMMIT' "$raw")"

  checkpoint "evidence_parsed"
  echo "[EVIDENCE] Parsed Leo evidence (from raw JSON):"
  echo "  VERDICT: $EVIDENCE_VERDICT"
  echo "  COMMANDS: $EVIDENCE_COMMANDS"
  echo "  CMD1: $EVIDENCE_CMD1_FETCH"
  echo "  CMD2: $EVIDENCE_CMD2_CHECKOUT"
  echo "  CMD3: $EVIDENCE_CMD3_REVPARSE"
  echo "  CMD4: $EVIDENCE_CMD4_STATUS"
  echo "  CMD5: $EVIDENCE_CMD5_LOG"
  echo "  PRODUCT_MODIFIED: $EVIDENCE_PRODUCT_MODIFIED"
  echo "  BRANCH_PUSHED: $EVIDENCE_BRANCH_PUSHED"
}

# ── Write Metadata File (for workflow push step) ───────────────────────
write_metadata() {
  local verdict="$1"
  cat > "$METADATA_FILE" << META_EOF
REPORT_BASENAME=$REPORT_BASENAME
REPORT_DECLARED_PATH=$REPORT_PATH
REPORT_STAGING_FILE=$report_staging_file
REPORT_BRANCH=$REPORT_BRANCH
VERDICT=$verdict
TASK_ID=$TASK_ID
DIRECTIVE_FILE=$latest_directive
META_EOF
  checkpoint "metadata_written"
  echo "[METADATA] Written to $METADATA_FILE"
}

# ── Report writer (success — deterministic from evidence) ──────────────
write_report() {
  local verdict="$1" duration="$2"
  local run_url="${GITHUB_SERVER_URL:-unknown}/${GITHUB_REPOSITORY:-unknown}/actions/runs/${GITHUB_RUN_ID:-unknown}"
  local runner_name="$(hostname)"

  mkdir -p "$(dirname "$report_staging_file")" 2>/dev/null || true

  # Build Leo evidence section
  local leo_evidence_section=""
  if [ "$EXECUTOR_TYPE" = "leo-headless" ]; then
    leo_evidence_section="
## Leo Execution Evidence

| Field | Value |
|-------|-------|
| Leo Invoked | $LEO_EXECUTED |
| Invocation Command | \`${LEO_INVOCATION_CMD}\` |
| Transport Health | $TRANSPORT_HEALTH |

### Command Evidence

| Command | Result |
|---------|--------|
| 1. git fetch origin --prune | $EVIDENCE_CMD1_FETCH |
| 2. git checkout origin/$TARGET_BRANCH --detach | $EVIDENCE_CMD2_CHECKOUT |
| 3. git rev-parse HEAD | $EVIDENCE_CMD3_REVPARSE |
| 4. git status --short | $EVIDENCE_CMD4_STATUS |
| 5. git log -1 --oneline | $EVIDENCE_CMD5_LOG |

### Compliance

| Field | Value |
|-------|-------|
| Commands Executed | $EVIDENCE_COMMANDS |
| Product Code Modified | $EVIDENCE_PRODUCT_MODIFIED |
| Product Branch Pushed | $EVIDENCE_BRANCH_PUSHED |
| Commit Hash | $EVIDENCE_COMMIT_HASH |
| Latest Commit | $EVIDENCE_LATEST_COMMIT |
"
  fi

  local report_content=""
  report_content=$(cat << REPORT_EOF
# Directive Execution Report — $TASK_ID

## Metadata

| Field | Value |
|-------|-------|
| Directive-ID | $TASK_ID |
| Mode | $MODE |
| Priority | $PRIORITY |
| Created | $CREATED |
| Executed | $(date -Is) |
| Duration | ${duration}s |
| **Verdict** | **$verdict** |
| Transport Health | $TRANSPORT_HEALTH |
| Executor | $EXECUTOR_TYPE |
| Runner | run_directive.sh v3.4 (path isolation) |
| runner_name | $(hostname) |
| Run URL | $run_url |
| Report Path (on branch) | $REPORT_PATH |
| Report Staging | $report_staging_file |
| Target Branch | $TARGET_BRANCH |
| Directive Repo | $DIRECTIVE_REPO |
| Validation Target | $VALIDATION_TARGET |
$leo_evidence_section

## Checkpoints

$(echo -e "$CHECKPOINTS")

---
Generated by Mpango Directive Runner v3.4 (Path Isolation Fix) at $(date -Is)
REPORT_EOF
)

  # R6: Write to generated-reports (NOT directives repo)
  if echo "$report_content" > "$report_staging_file" 2>/dev/null; then
    echo "[REPORT] Written to staging: $report_staging_file"
    return 0
  else
    local fallback_file="$FALLBACK_REPORT_DIR/${run_id}_${TASK_ID}_fallback.md"
    echo "$report_content" > "$fallback_file"
    echo "[REPORT_FALLBACK] Staging write failed. Written to: $fallback_file"
    return 1
  fi
}

# ── Failure report ─────────────────────────────────────────────────────
write_failure_report() {
  local verdict="$1" reason="$2" duration="$3"
  local run_url="${GITHUB_SERVER_URL:-unknown}/${GITHUB_REPOSITORY:-unknown}/actions/runs/${GITHUB_RUN_ID:-unknown}"
  local stderr_summary=""

  if [ -f "$log_file" ]; then
    stderr_summary="$(tail -20 "$log_file" 2>/dev/null || true)"
  fi

  local leo_section=""
  if [ "$EXECUTOR_TYPE" = "leo-headless" ]; then
    leo_section="
### Leo Execution Evidence
- Leo Invoked: $LEO_EXECUTED
- Commands: $EVIDENCE_COMMANDS
- Product Modified: $EVIDENCE_PRODUCT_MODIFIED
- Branch Pushed: $EVIDENCE_BRANCH_PUSHED
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
| **Verdict** | **$verdict** |
| Executor | $EXECUTOR_TYPE |
| Runner | run_directive.sh v3.4 (path isolation) |
| runner_name | $(hostname) |
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

$(echo -e "$CHECKPOINTS")

## Last Log Output

\`\`\`
$stderr_summary
\`\`\`

## Failure Stage Diagnosis

| Stage | Status |
|-------|--------|
| 1. Runner accepted job | $( [ "$LEO_EXECUTED" = "true" ] || [ "$EXECUTOR_TYPE" = "script-only" ] && echo "PASS" || echo "FAIL" ) |
| 2. Leo invoked | $LEO_EXECUTED |
| 3. Report generation | $( [ -f "$report_staging_file" ] && echo "PASS" || echo "FAIL" ) |
| 4. Report push | N/A (workflow step) |
| 5. Final gate | N/A (workflow step) |

---
Generated by Mpango Directive Runner v3.4 (Path Isolation Fix) at $(date -Is)
REPORT_EOF
)

  mkdir -p "$(dirname "$report_staging_file")" 2>/dev/null || true
  if echo "$report_content" > "$report_staging_file" 2>/dev/null; then
    echo "[FAILURE_REPORT] Written to staging: $report_staging_file"
  else
    local fallback_file="$FALLBACK_REPORT_DIR/${run_id}_${TASK_ID}_failure.md"
    mkdir -p "$FALLBACK_REPORT_DIR"
    echo "$report_content" > "$fallback_file"
    echo "[FAILURE_REPORT_FALLBACK] Written to: $fallback_file"
  fi
}

# ── Report Existence Gate ──────────────────────────────────────────────
verify_report_exists() {
  if [ -f "$report_staging_file" ]; then
    checkpoint "report_exists_gate_pass"
    echo "[GATE] Report exists at staging: $report_staging_file"
    return 0
  else
    checkpoint_fail "report_exists_gate" "report not found at $report_staging_file"
    echo "[GATE_FAIL] Report NOT found at: $report_staging_file"
    local fallback_count
    fallback_count="$(find "$FALLBACK_REPORT_DIR" -name "${run_id}_${TASK_ID}_*" -type f 2>/dev/null | wc -l)"
    if [ "$fallback_count" -gt 0 ]; then
      echo "[GATE_WARN] Fallback report(s) exist: $fallback_count file(s)"
      find "$FALLBACK_REPORT_DIR" -name "${run_id}_${TASK_ID}_*" -type f
    fi
    return 1
  fi
}

# ── Main execution ─────────────────────────────────────────────────────
VERDICT="PASS_FOR_CTO_REVIEW"
EXECUTOR_OUTPUT=""

echo "[EXEC] executor=$EXECUTOR_TYPE mode=$MODE ts=$(date -Is)" | tee -a "$log_file"

checkpoint "heartbeat_start"
start_heartbeat

COMMIT_INFO="$(git -C "$DIRECTIVE_REPO" rev-parse --short HEAD 2>/dev/null || echo 'unknown')"
BRANCH_INFO="$(git -C "$DIRECTIVE_REPO" rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'unknown')"

case "$EXECUTOR_TYPE" in
  script-only)
    checkpoint "executor_script_only_start"
    _tmp_out="$STATE_DIR/exec_output_${run_id}.txt"
    run_script_only > "$_tmp_out" 2>&1 || true
    EXECUTOR_OUTPUT="$(cat "$_tmp_out")"
    ;;
  leo-headless)
    checkpoint "executor_leo_headless_start"
    _tmp_out="$STATE_DIR/exec_output_${run_id}.txt"
    run_leo_headless > "$_tmp_out" 2>&1
    rc=$?
    EXECUTOR_OUTPUT="$(cat "$_tmp_out")"

    # R6: Parse Leo's structured evidence directly from raw JSON output
    parse_leo_evidence "$EXECUTOR_OUTPUT"

    if [ $rc -ne 0 ]; then
      stop_heartbeat
      local elapsed
      elapsed="$(elapsed_since "$START_TIME")"

      if [ "$rc" -eq 124 ]; then
        VERDICT="BLOCKED_ENVIRONMENT"
      else
        VERDICT="FAIL_RUNNER_INFRA"
      fi

      write_failure_report "$VERDICT" "Leo executor failed with exit code $rc" "$elapsed"
      verify_report_exists || echo "[WARN] Report gate failed after executor error"
      write_metadata "$VERDICT"

      echo "$directive_sha $latest_directive $(date -Is) verdict=$VERDICT executor=$EXECUTOR_TYPE" >> "$STATE_FILE"
      echo "[EXIT] ts=$(date -Is) directive=$TASK_ID verdict=$VERDICT duration=${elapsed}s" | tee -a "$log_file"
      exit 1
    fi
    ;;
  *)
    VERDICT="FAIL_RUNNER_INFRA"
    write_failure_report "$VERDICT" "Unknown executor type: $EXECUTOR_TYPE" "$(elapsed_since "$START_TIME")"
    write_metadata "$VERDICT"
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
  write_failure_report "$VERDICT" "Total timeout exceeded ${TOTAL_TIMEOUT_SECS}s" "$ELAPSED"
  verify_report_exists || true
  write_metadata "$VERDICT"
  echo "$directive_sha $latest_directive $(date -Is) verdict=$VERDICT executor=$EXECUTOR_TYPE" >> "$STATE_FILE"
  exit 1
fi

checkpoint "timeout_check_pass"

# ── Transport Health Gate ────────────────────────────────────────────
checkpoint "transport_gate"

if [ "$TRANSPORT_HEALTH" = "degraded" ]; then
  VERDICT="FAIL_RUNNER_INFRA_WITH_VALIDATION_COMPLETED"
  checkpoint_warn "transport_gate" "transport degraded"
elif [ "$TRANSPORT_HEALTH" = "failed" ]; then
  VERDICT="FAIL_RUNNER_INFRA"
  checkpoint_fail "transport_gate" "transport failed"
fi

# ── Leo Evidence Validation (R6) ───────────────────────────────────
if [ "$EXECUTOR_TYPE" = "leo-headless" ]; then
  if [ "$LEO_EXECUTED" != "true" ]; then
    VERDICT="FAIL_RUNNER_INFRA"
    checkpoint_fail "leo_evidence_gate" "Leo was NOT invoked"
  elif [ "$EVIDENCE_COMMANDS" != "5/5" ]; then
    VERDICT="FAIL_RUNNER_INFRA"
    checkpoint_fail "leo_commands_gate" "Leo commands: $EVIDENCE_COMMANDS (expected 5/5)"
  elif echo "$EVIDENCE_PRODUCT_MODIFIED" | grep -qiE "^no$|^false$"; then
    checkpoint "leo_product_modified_gate" "product code not modified"
  else
    VERDICT="FAIL_RUNNER_INFRA"
    checkpoint_fail "leo_product_modified_gate" "product code was modified: $EVIDENCE_PRODUCT_MODIFIED"
  fi
fi

# ── Write report ───────────────────────────────────────────────────────
checkpoint "report_write_start"

if [ "$VERDICT" = "PASS_FOR_CTO_REVIEW" ]; then
  write_report "$VERDICT" "$ELAPSED" || VERDICT="FAIL_RUNNER_INFRA"
else
  write_failure_report "$VERDICT" "See checkpoints for failure details" "$ELAPSED" || true
fi

# ── Report Existence Final Gate ───────────────────────────────────────
checkpoint "report_existence_gate"

if ! verify_report_exists; then
  VERDICT="FAIL_RUNNER_INFRA"
  write_failure_report "$VERDICT" "Report existence final gate failed" "$ELAPSED" || true
fi

# ── Write metadata (for workflow push step) ───────────────────────────
checkpoint "metadata_write"
write_metadata "$VERDICT"

# ── Mark processed ─────────────────────────────────────────────────────
checkpoint "mark_processed"

echo "$directive_sha $latest_directive $(date -Is) verdict=$VERDICT executor=$EXECUTOR_TYPE" >> "$STATE_FILE"

# ── Exit ───────────────────────────────────────────────────────────────
checkpoint "exit"

echo "[EXIT] ts=$(date -Is) directive=$TASK_ID verdict=$VERDICT duration=${ELAPSED}s executor=$EXECUTOR_TYPE report=$report_staging_file" | tee -a "$log_file"

case "$VERDICT" in
  PASS_FOR_CTO_REVIEW) exit 0 ;;
  *) exit 1 ;;
esac
