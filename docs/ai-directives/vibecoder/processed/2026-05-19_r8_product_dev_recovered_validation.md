Directive-ID: r8-product-dev-recovered-validation-2026-05-19
Mode: VALIDATION_GATE
Priority: HIGH
Created: 2026-05-19
Status: pending
Target-Branch: product-dev-recovered
Target-Commit: c0f80d7cf69d197877453375974c067223cf366e
Validation-Scope: product-dev-recovered Sprint C closeout validation after parser-only gate
Allow-Code-Changes: false
Allow-Product-Push: false
Report branch: reports/lubuntu-validation
Report path: docs/ai-reports/lubuntu/2026-05-19_r8_product_dev_recovered_validation.md

# R8 Product Dev Recovered Validation

Objective:
Run the real DB-capable product validation on Lubuntu through Leo headless after the R8A parser-only gate proved the directive runner can parse 5 preflight commands and 4 validation commands.

Required branch/commit checks:
1. `git fetch origin --prune`
2. `git checkout origin/product-dev-recovered --detach`
3. `git rev-parse HEAD`
4. Confirm HEAD equals `c0f80d7cf69d197877453375974c067223cf366e`.
5. `git status --short` must be clean before and after validation.

Required validation commands:
1. Backend import smoke from `backend`:
   `poetry run python -c "from api.app import app; print(len(app.routes))"`
2. Receivables targeted suite from `backend`:
   `REPORTING_USER_PASSWORD=MpangoTest_2026 poetry run pytest tests/test_receivables_service.py tests/test_finance_receivables_api.py -q --tb=short`
3. Phase 5 payment regression from `backend`:
   `REPORTING_USER_PASSWORD=MpangoTest_2026 poetry run pytest tests/test_phase5_order_payment.py -q --tb=short`
4. Schema contract suite from `backend`:
   `REPORTING_USER_PASSWORD=MpangoTest_2026 poetry run pytest tests/test_payments_schema_contract.py -q --tb=short -rs`

Expected evidence:
- COMMANDS_EXECUTED: 9/9
- PREFLIGHT: 5/5
- VALIDATION: 4/4
- App import smoke passes and reports route count.
- Receivables suite: 38 passed, 0 failed.
- Phase 5 payment regression: 53 passed, 1 xfailed, 0 failed.
- Schema contract: 40 passed, 0 skipped, 0 failed.
- Schema Skip Reasons: NONE when skipped = 0.
- PRODUCT_CODE_MODIFIED: no.
- PRODUCT_BRANCH_PUSHED: no.
- COMMIT_HASH: c0f80d7cf69d197877453375974c067223cf366e.

Hard rules:
- Leo must execute all 5 preflight commands and all 4 validation commands.
- Do not modify product code.
- Do not modify tests.
- Do not commit from the validation target.
- Do not push product branches.
- Do not write report files from Leo; run_directive.sh writes the report.
- Do not classify as PASS if any validation result is missing or unknown.
- If Docker/PostgreSQL/Redis is unavailable, classify as BLOCKED_ENVIRONMENT.
- If any critical DB suite is skipped for environment reasons, classify as PARTIAL_PASS_WITH_DB_EVIDENCE_GAP.
- If gateway_timeout or fallbackUsed=true occurs, classify as FAIL_RUNNER_INFRA_WITH_VALIDATION_COMPLETED, not PASS.

Acceptance criteria:
- GitHub Actions conclusion = success.
- Runner name = mpango-lubuntu-01.
- Report exists on reports/lubuntu-validation.
- Mode = VALIDATION_GATE.
- Leo Invoked = true.
- COMMANDS_EXECUTED = 9/9.
- VALIDATION = 4/4.
- All validation result fields are present and not unknown.
- Product code modified = no.
- Product branch pushed = no.
- Transport health is healthy.
