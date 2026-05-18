Agent: Leo
Mode: INVENTORY_ONLY
Directive-ID: negative-test-D2-report-gate
Priority: low
Created: 2026-05-18
Status: pending
Target-Branch: product-dev-recovered
Validation-Scope: negative-test-report-gate
Allow-Code-Changes: false
Allow-Product-Push: false
Report branch: reports/lubuntu-validation
Report path: /root/impossible_D2_report.md

# Negative Test D2 — Report Path Gate Failure (with v3.1b fix)

Objective:
Verify that the workflow correctly FAILS when the report cannot be written
to the declared path and the final gate on reports/lubuntu-validation cannot
find the report.

This re-runs after fixing run_directive.sh v3.1b (local keyword fix).

Expected:
1. run_directive.sh primary write to /root/ fails (permission denied)
2. Fallback failure report generated
3. Script exits FAIL_RUNNER_INFRA
4. Push step copies fallback (different filename)
5. Final gate checks /root/impossible_D2_report.md → not found
6. Workflow FAILS

Expected verdict: FAIL_RUNNER_INFRA
