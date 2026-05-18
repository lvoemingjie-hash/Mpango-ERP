Agent: Leo
Mode: VALIDATION_GATE
Directive-ID: dry-run-B2R2-transport-health
Priority: normal
Created: 2026-05-18
Status: pending
Target-Branch: product-dev-recovered
Validation-Scope: transport-health-verification-R2
Allow-Code-Changes: false
Allow-Product-Push: false
Report branch: reports/lubuntu-validation
Report path: docs/ai-reports/lubuntu/2026-05-18_dry_run_B2R_R2_transport_health.md

# Dry Run B2R-R2 — Gateway Transport Health Verification (Retry 2)

Objective:
Re-verify the full call chain: GitHub Actions → self-hosted runner (mpango-lubuntu-01) → run_directive.sh v3.1b → Leo headless via Gateway (NOT embedded fallback).

This is a NEW directive (B2R-R2). Do NOT overwrite the old B2R report at docs/ai-reports/lubuntu/2026-05-18_dry_run_B2R_transport_health.md. This report goes to a SEPARATE path.

Required commands (Leo must execute ALL 5):
1. git fetch origin --prune
2. git checkout origin/product-dev-recovered --detach
3. git rev-parse HEAD
4. git status --short
5. git log -1 --oneline

Expected verdict:
- PASS_FOR_CTO_REVIEW (if Gateway transport healthy + all 5 commands succeeded + report on reports/lubuntu-validation)
- FAIL_RUNNER_INFRA_WITH_VALIDATION_COMPLETED (if embedded fallback detected but commands ran)
- FAIL_RUNNER_INFRA (if total failure)

Validation rules:
- Embedded fallback MUST NOT be accepted as healthy
- Report MUST exist on reports/lubuntu-validation branch at the EXACT path declared above
- No product code modifications
- No product branch pushes
- Leo MUST execute all 5 git commands (evidence gate requires 5 commands)

Context:
- Previous B2R (run 26008458885) failed: leo_evidence_gate — Leo was NOT invoked
- Root cause: subshell variable capture bug in run_directive.sh v3 — all variable mutations lost
- Fix: run_directive.sh v3.1b — file-based capture preserves shell variables
- Runner mpango-lubuntu-01 freshly re-registered 2026-05-18 10:15 CST
- Script hash: d50c611314d9b09c2bb60e27bad37e24 (runner local)
- Repo copy hash: b02935a28c5c6aee7d6c1764a5ce7393 (automation/cto-directives/scripts/runner/)
- Workflow: v4 (report path gate + reports branch push)
