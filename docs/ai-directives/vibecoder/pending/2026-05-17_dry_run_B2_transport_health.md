Agent: Leo
Mode: VALIDATION_GATE
Directive-ID: dry-run-B2-transport-health
Priority: low
Created: 2026-05-17
Status: pending
Target-Branch: product-dev-recovered
Validation-Scope: inventory-fetch-status-only
Allow-Code-Changes: false
Allow-Product-Push: false
Report branch: reports/lubuntu-validation
Report path: docs/ai-reports/lubuntu/2026-05-17_dry_run_B2_transport_health.md

# Dry Run B2 — Gateway Transport Health Verification

Objective:
Verify the full call chain: GitHub Actions → run_directive.sh → Leo headless via Gateway (NOT embedded fallback).
This run validates that the Gateway path is stable after the B1 failure (SIGTERM at 15:00:08).

Required commands (Leo must execute):
- git fetch origin --prune
- git checkout origin/product-dev-recovered --detach
- git rev-parse HEAD
- git status --short
- git log -1 --oneline

Expected verdict:
- PASS_FOR_CTO_REVIEW (if Gateway transport healthy + commands succeeded)
- FAIL_RUNNER_INFRA_WITH_VALIDATION_COMPLETED (if embedded fallback again)
- FAIL_RUNNER_INFRA (if total failure)

Context from B1 investigation:
- Gateway received SIGTERM at 15:00:08 from external source (not agent-initiated)
- No OOM, no agent tool calls, no config change triggered it
- systemd `Restart=always` policy restarted gateway in 15s
- Possible cause: manual restart or external signal during high load
- Event loop delay warning (3353ms max) at 14:57:31
- Telegram fetch timeout at 14:58:57

This is a dry-run. No code changes. No product push.
