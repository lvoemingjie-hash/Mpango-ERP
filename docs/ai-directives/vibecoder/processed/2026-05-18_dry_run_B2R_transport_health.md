Agent: Leo
Mode: VALIDATION_GATE
Directive-ID: dry-run-B2R-transport-health
Priority: normal
Created: 2026-05-18
Status: pending
Target-Branch: product-dev-recovered
Validation-Scope: transport-health-verification
Allow-Code-Changes: false
Allow-Product-Push: false
Report branch: reports/lubuntu-validation
Report path: docs/ai-reports/lubuntu/2026-05-18_dry_run_B2R_transport_health.md

# Dry Run B2R — Gateway Transport Health Verification

Objective:
Verify the full call chain: GitHub Actions → self-hosted runner (mpango-lubuntu-01) → run_directive.sh → Leo headless via Gateway (NOT embedded fallback).

This is a NEW directive (not reusing old B2). Runner has been freshly installed at /home/ivy/gh-runner-mpango-erp/ with correct labels.

Required commands (Leo must execute):
- git fetch origin --prune
- git checkout origin/product-dev-recovered --detach
- git rev-parse HEAD
- git status --short
- git log -1 --oneline

Expected verdict:
- PASS_FOR_CTO_REVIEW (if Gateway transport healthy + all commands succeeded + report on reports/lubuntu-validation)
- FAIL_RUNNER_INFRA_WITH_VALIDATION_COMPLETED (if embedded fallback detected but commands ran)
- FAIL_RUNNER_INFRA (if total failure)

Validation rules:
- Embedded fallback MUST NOT be accepted as healthy
- Report MUST exist on reports/lubuntu-validation branch (not just local fs)
- No product code modifications
- No product branch pushes

Context:
- Runner mpango-lubuntu-01 freshly registered 2026-05-18
- Labels: self-hosted, linux, mpango-lubuntu
- Previous B2 directive (2026-05-17) failed due to SIGTERM during Gateway execution
- This B2R verifies the full chain works end-to-end with the new runner
