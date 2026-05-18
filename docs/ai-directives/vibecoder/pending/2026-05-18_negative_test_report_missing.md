Agent: Leo
Mode: INVENTORY_ONLY
Directive-ID: negative-test-report-missing
Priority: low
Created: 2026-05-18
Status: pending
Target-Branch: product-dev-recovered
Validation-Scope: negative-test
Allow-Code-Changes: false
Allow-Product-Push: false
Report branch: reports/lubuntu-validation
Report path: /root/impossible_negative_test_report.md

# Negative Test D — Report Path Gate Failure

Objective:
Verify that the workflow correctly FAILS when the report cannot be written to the declared path and the final gate on reports/lubuntu-validation cannot find the report.

This is a NEGATIVE TEST. The workflow MUST fail.

Mechanism:
- Report path is /root/impossible_negative_test_report.md (unwritable by ivy user)
- run_directive.sh primary write fails → generates fallback report
- run_directive.sh exits with FAIL_RUNNER_INFRA
- Push step copies fallback reports (with different filename) to reports branch
- Report Path Final Gate checks for /root/impossible_negative_test_report.md on reports branch
- File does not exist → gate FAILS → workflow FAILS

Expected behavior:
1. run_directive.sh primary write fails (permission denied on /root/)
2. Fallback failure report generated at ~/.openclaw/mpango-directive-runner/fallback-reports/
3. run_directive.sh exits non-zero (FAIL_RUNNER_INFRA)
4. Push step copies fallback reports to reports branch
5. Report Path Final Gate checks for /root/impossible_negative_test_report.md on reports branch
6. File NOT found → gate fails
7. Workflow fails

Expected verdict: FAIL_RUNNER_INFRA
