Agent: Leo
Mode: VALIDATION_GATE
Directive-ID: product-dev-recovered-sprint-c-validation-2026-05-18
Priority: HIGH
Created: 2026-05-18
Status: pending
Target-Branch: product-dev-recovered
Target-Commit: c0f80d7cf69d197877453375974c067223cf366e
Validation-Scope: product-dev-recovered post Sprint C promotion validation
Allow-Code-Changes: false
Allow-Product-Push: false
Report branch: reports/lubuntu-validation
Report path: docs/ai-reports/lubuntu/2026-05-18_product_dev_recovered_sprint_c_validation.md

# Product Dev Recovered Sprint C Validation

Objective:
Validate that `origin/product-dev-recovered` now points to the promoted Sprint C product line and remains safe after the Windows CTO push.

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
- Receivables suite: 38 passed, 0 failed.
- Phase 5 payment regression: 53 passed, 1 xfailed, 0 failed.
- Schema contract: no failures; skipped tests must include explicit skip reasons if any.
- App import smoke: passes and reports route count.

Hard rules:
- Do not modify product code.
- Do not modify tests.
- Do not commit.
- Do not push product branches.
- Do not edit `product-dev-recovered`.
- If Docker/PostgreSQL/Redis is unavailable, classify as `BLOCKED_ENVIRONMENT`, not PASS.
- If any critical DB suite is skipped for environment reasons, classify as `PARTIAL_PASS_WITH_DB_EVIDENCE_GAP`, not PASS.
- If any required command fails, classify as `FAIL_VALIDATION`.

Final verdict options:
- `PASS_FOR_CTO_REVIEW`: all required checks pass, no product code changed, no product push.
- `PARTIAL_PASS_WITH_DB_EVIDENCE_GAP`: non-DB checks pass but DB-capable evidence is incomplete due to skips.
- `BLOCKED_ENVIRONMENT`: validation cannot run because required services or dependencies are unavailable.
- `FAIL_VALIDATION`: any required validation command fails for code/test reasons.

Report requirements:
- Include GitHub Actions run URL.
- Include actual runner name and host name separately if available.
- Include HEAD commit.
- Include full command list with exact pass/fail counts.
- Include skipped test reasons when skipped count is nonzero.
- Include before/after `git status --short`.
- Include final verdict.
