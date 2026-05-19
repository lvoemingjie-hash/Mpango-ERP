Agent: Vibecoder
Mode: INVENTORY_ONLY
Directive-ID: smoke-runner-restore-20260519
Priority: HIGH
Created: 2026-05-19T11:10:00+08:00
Report branch: reports/lubuntu-validation
Report path: docs/ai-reports/lubuntu/2026-05-19_smoke_runner_restore.md

# Smoke Test — Runner Restoration Verification

Objective:
Minimal smoke test to verify the restored GitHub Actions runner (mpango-lubuntu-01)
can accept jobs, execute the directive workflow, generate a report, and push
to reports/lubuntu-validation.

Required evidence (must appear in generated report):
- PREFLIGHT: at least 3/5 checks passed
- Report file exists at declared report path
- Runner name matches mpango-lubuntu-01
- Workflow completed without error

This is a smoke test only. No code changes. No product validation.
