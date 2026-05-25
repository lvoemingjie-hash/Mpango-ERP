# Sprint R-2 VPS Script Recovery

**Date**: 2026-05-25
**Scope**: Restore and rewrite deployment and cleanup scripts (Draft phase)
**Branch**: ops/sprint-r2-vps-script-recovery-2026-05-25

## 1. Overview
This ledger documents the successful draft recovery of `scripts/safe_cleanup_vps.sh` and `scripts/deploy_vps.sh`.
**Note:** This is a local draft only. No VPS connection, no deployment, and no cleanup operations were executed. No secrets were committed.

## 2. Scripts Restored

### `scripts/safe_cleanup_vps.sh`
- **Default Mode**: `--dry-run` is enabled by default to prevent accidental destructive operations.
- **Targeted Filtering**: Uses Docker Compose label `com.docker.compose.project=mpango` as primary filter, with `^mpango[-_]` name prefix as fallback for containers, networks, and volumes. Images use label match only (no name fallback) to protect shared base images.
- **Safety Constraints**:
  - `docker system prune` is strictly prohibited and not present in the script.
  - No `rm -rf` or file system deletion capabilities.
  - Deleting volumes is disabled by default.
  - Volume deletion requires the explicit `--delete-volumes` flag, a verified backup, and an interactive confirmation typing "I have CTO approval" (when not in dry-run).
- **Discovery-First Flow**: Resources are discovered and displayed with exact targets (ID, name, status, matched_by) before any confirmation prompt appears.
- **Verification**: The script includes explicit stop conditions in its help message.

### `scripts/deploy_vps.sh`
- **Secret Safety**: No IPs, passwords, tokens, or secrets are hardcoded in the script.
- **Environment Verification**: The script checks for the existence of `.env.prod` but explicitly hides its content from any output.
- **Migration Policy**: Executes `alembic upgrade head` normally. Bypassing or stamping migrations is prohibited and not included in the script.
- **Execution Flow**: Includes `--help` and `--dry-run` modes. The script outlines clear stop conditions for missing env files, git failures, docker compose failures, and migration failures.

## 3. Validation Summary
- `git diff --check`: Passed with no whitespace errors.
- `bash -n scripts/safe_cleanup_vps.sh`: Passed syntax check.
- `bash -n scripts/deploy_vps.sh`: Passed syntax check.
- `shellcheck`: (If available on the local machine, results are noted in the command output; otherwise recorded as unavailable).
- **Execution Mode**: Only local static paths and dry-run/help validations were performed. No destructive apply was executed.

## 5. R-2R Corrections (CTO Review)
- **CTO Feedback**: The initial R-2 draft was rejected because `safe_cleanup_vps.sh` contained `rm -rf --project-dir` capabilities, and `deploy_vps.sh` defaulted to apply mode instead of dry-run.
- **`safe_cleanup_vps.sh` Updates**:
  - Removed `--project-dir` parameter and all file system deletion (`rm -rf`) logic.
  - Hardened Docker resource filtering to prioritize `com.docker.compose.project=mpango` label, with a strict `^mpango[-_]` name fallback to prevent greedy regex matches.
- **`deploy_vps.sh` Updates**:
  - Changed default mode to `DRY_RUN=true`.
  - Added explicit `--apply` flag requiring interactive confirmation (`deploy mpango`).
  - Relaxed `.env.prod` check in dry-run mode (only warns), but strictly enforces it in apply mode.
- **Status Confirmation**: Still NO VPS connection, NO cleanup executed, NO deployment executed, and NO secrets committed.

## 6. R-2S Corrections (CTO Review)
- **CTO Feedback**: R-2R was blocked because fallback resources were not displayed before delete confirmation. The user could not review name-fallback matches before approving cleanup.
- **`safe_cleanup_vps.sh` R-2S Updates**:
  - Restructured into three phases: DISCOVERY → CONFIRMATION → EXECUTION.
  - Discovery phase runs first for all resource types, collecting both label and name-fallback matches.
  - Each discovered resource is displayed with exact details: ID, name, status/driver, and matched_by (label or name-fallback).
  - If label query is empty but name fallback hits, the fallback resources are displayed (not hidden).
  - Images: restricted to label match only — no name fallback for image deletion, protecting shared base images.
  - Confirmation prompt only appears after all exact targets are displayed.
- **`deploy_vps.sh` R-2S Updates**:
  - Added prerequisites section to help text: VPS inventory, backup verification, CTO approval.
- **Status Confirmation**: Still NO VPS connection, NO cleanup executed, NO deployment executed, and NO secrets committed.

## 7. R-2S Validation Results
- `git diff --check HEAD~1..HEAD`: See command output below.
- `git show --check --oneline --stat HEAD`: See command output below.
- `bash -n scripts/safe_cleanup_vps.sh`: PASS
- `bash -n scripts/deploy_vps.sh`: PASS
- `bash scripts/safe_cleanup_vps.sh --help`: PASS
- `bash scripts/deploy_vps.sh --help`: PASS
- `bash scripts/deploy_vps.sh --dry-run`: PASS
- `grep` for rm -rf, --project-dir, docker system prune, alembic stamp, hardcoded IP/password/token: None found.
- `shellcheck`: unavailable (not installed, not installing per CTO directive).
- `git status --short`: clean after commit.
- `git log -1 --oneline`: See command output below.
