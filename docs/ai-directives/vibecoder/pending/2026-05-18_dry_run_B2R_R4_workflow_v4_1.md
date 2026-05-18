Agent: Leo
Mode: VALIDATION_GATE
Directive-ID: dry-run-B2R-R4-workflow-v4.1
Priority: normal
Created: 2026-05-18
Status: pending
Target-Branch: product-dev-recovered
Validation-Scope: runner-hardening-final-acceptance-B2R-R4
Allow-Code-Changes: false
Allow-Product-Push: false
Report branch: reports/lubuntu-validation
Report path: docs/ai-reports/lubuntu/2026-05-18_dry_run_B2R_R4_workflow_v4_1.md

# Dry Run B2R-R4 — Runner Hardening Final Acceptance

Objective:
Verify the complete call chain produces a GitHub-green conclusion:
GitHub Actions → mpango-lubuntu-01 → run_directive.sh v3.3 → Leo headless → report on reports/lubuntu-validation → final gate PASS.

This is the FINAL acceptance run for runner-hardening. The chain MUST produce:
- GitHub Actions conclusion = success
- runner_name = mpango-lubuntu-01
- final gate passed
- report on reports/lubuntu-validation at declared path

Required commands (Leo must execute ALL 5):
1. git fetch origin --prune
2. git checkout origin/product-dev-recovered --detach
3. git rev-parse HEAD
4. git status --short
5. git log -1 --oneline

Expected verdict:
- PASS_FOR_CTO_REVIEW (if all gates pass + report on reports branch)
- FAIL_RUNNER_INFRA_WITH_VALIDATION_COMPLETED (if embedded fallback used)
- FAIL_RUNNER_INFRA (if total failure)

Validation rules:
- Script: run_directive.sh v3.3 — Leo no-push enforcement + fallbackUsed detection
- Leo MUST NOT push to any remote branch. Only write report locally.
- The workflow push step (v4.1) handles pushing to reports/lubuntu-validation.
- Report MUST exist on reports/lubuntu-validation at the EXACT declared path above.
- fallbackUsed MUST be false (Gateway transport, not embedded fallback).
- No product code modifications. No product branch pushes.
- Leo MUST execute all 5 git commands (evidence gate requires all 5).

Context:
- B2R-R3 (run 26010384384): Leo 5/5 commands, PASS verdict, but GitHub conclusion=failure
  (workflow push step and Leo push conflicted)
- v3.3 fix: Leo prompt now explicitly forbids git push to any branch
- v4.1 workflow: push step includes git pull --rebase to handle any remaining conflicts
- Runner local hash: 9850f42bff55b0ffe67c2014e4554d43 (v3.3)
- Repo copy hash: 9850f42bff55b0ffe67c2014e4554d43 (v3.3, identical)
