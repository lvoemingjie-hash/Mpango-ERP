Agent: Leo
Mode: VALIDATION_GATE
Directive-ID: dry-run-B2R3-transport-health
Priority: normal
Created: 2026-05-18
Status: pending
Target-Branch: product-dev-recovered
Validation-Scope: transport-health-verification-R3
Allow-Code-Changes: false
Allow-Product-Push: false
Report branch: reports/lubuntu-validation
Report path: docs/ai-reports/lubuntu/2026-05-18_dry_run_B2R_R2_transport_health.md

# Dry Run B2R-R3 — Gateway Transport Health Verification (Retry 3)

Objective:
Re-verify the full call chain: GitHub Actions → self-hosted runner (mpango-lubuntu-01) → run_directive.sh v3.2 → Leo headless via Gateway (NOT embedded fallback).

IMPORTANT: This R3 writes to the SAME path as R2 (docs/ai-reports/lubuntu/2026-05-18_dry_run_B2R_R2_transport_health.md), overwriting the R2 report which had incorrect verdict due to transport detection bug.

Required commands (Leo must execute ALL 5):
1. git fetch origin --prune
2. git checkout origin/product-dev-recovered --detach
3. git rev-parse HEAD
4. git status --short
5. git log -1 --oneline

Expected verdict:
- PASS_FOR_CTO_REVIEW (if Gateway transport healthy + all 5 commands succeeded + report on reports/lubuntu-validation)
- FAIL_RUNNER_INFRA_WITH_VALIDATION_COMPLETED (if actual embedded fallback was used)
- FAIL_RUNNER_INFRA (if total failure)

Validation rules:
- The correct transport health check uses "fallbackUsed": true/false from openclaw agent --json output
- "runner": "embedded" is NOT a fallback indicator — it is the CLI binary mode
- Only "fallbackUsed": true means actual embedded fallback occurred
- Report MUST exist on reports/lubuntu-validation branch at the EXACT path declared above
- No product code modifications
- No product branch pushes
- Leo MUST execute all 5 git commands (evidence gate requires commands)

Context:
- R2 (run 26010128852): Leo executed 5/5 commands successfully, but script incorrectly detected "runner:embedded" as degraded
- Fix: run_directive.sh v3.2 — transport detection now checks "fallbackUsed" field instead of "runner" field
- Runner mpango-lubuntu-01 re-registered 2026-05-18 10:15 CST with correct labels
- Script hash: fad29ba1cf7d62f1d012236df2b9b665 (v3.2, runner local)
- Repo copy hash: b02935a28c5c6aee7d6c1764a5ce7393 (automation/cto-directives/scripts/runner/)
- Workflow: v4 (report path gate + reports branch push)
