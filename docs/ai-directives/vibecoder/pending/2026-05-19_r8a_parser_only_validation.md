Directive-ID: r8a-parser-only-validation-2026-05-19
Mode: PARSER_ONLY
Priority: HIGH
Created: 2026-05-19
Status: pending
Target-Branch: product-dev-recovered
Target-Commit: c0f80d7cf69d197877453375974c067223cf366e
Validation-Scope: parser-only proof for product-dev-recovered R8 validation directive
Allow-Code-Changes: false
Allow-Product-Push: false
Report branch: reports/lubuntu-validation
Report path: docs/ai-reports/lubuntu/2026-05-19_r8a_parser_only_validation.md

# R8A Parser-Only Validation

Objective:
Verify that the directive runner can parse the exact preflight and validation command sections needed for the upcoming R8 product validation without invoking Leo and without running product tests.

Required branch/commit checks:
1. `git fetch origin --prune`
2. `git checkout origin/product-dev-recovered --detach`
3. `git rev-parse HEAD`
4. Confirm HEAD equals `c0f80d7cf69d197877453375974c067223cf366e`.
5. `git status --short` must be clean before and after validation.

Required validation commands:
1. Backend import smoke from `backend`: `poetry run python -c "from api.app import app; print(len(app.routes))"`
2. Receivables targeted suite from `backend`: `REPORTING_USER_PASSWORD=MpangoTest_2026 poetry run pytest tests/test_receivables_service.py tests/test_finance_receivables_api.py -q --tb=short`
3. Phase 5 payment regression from `backend`: `REPORTING_USER_PASSWORD=MpangoTest_2026 poetry run pytest tests/test_phase5_order_payment.py -q --tb=short`
4. Schema contract suite from `backend`: `REPORTING_USER_PASSWORD=MpangoTest_2026 poetry run pytest tests/test_payments_schema_contract.py -q --tb=short -rs`

Expected evidence:
- PARSER_PREFLIGHT_COUNT: 5
- PARSER_VALIDATION_COUNT: 4
- PARSER_TOTAL_COUNT: 9
- Leo Invoked: false
- directive_sections_extracted checkpoint reached.
- script_only_complete checkpoint reached.

Hard rules:
- Do not invoke Leo.
- Do not run pytest.
- Do not run product validation commands.
- Do not modify product code.
- Do not modify tests.
- Do not commit from the validation target.
- Do not push product branches.
- If parser counts are not exactly 5/4/9, classify as FAIL_RUNNER_INFRA.

Acceptance criteria:
- GitHub Actions conclusion = success.
- Runner name = mpango-lubuntu-01.
- Report exists on reports/lubuntu-validation.
- Mode = PARSER_ONLY.
- PARSER_PREFLIGHT_COUNT = 5.
- PARSER_VALIDATION_COUNT = 4.
- PARSER_TOTAL_COUNT = 9.
- Leo Invoked = false.
- Final Gate passes parser-only checks.
