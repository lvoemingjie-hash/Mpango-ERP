Directive-ID: night-sprint-n-post-merge-ghost-qa-validation-2026-05-22
Mode: VALIDATION_GATE
Priority: HIGH
Created: 2026-05-22
Status: pending
Target branch: product-dev-recovered
Target-Commit: 9d02e38a52f6111c5ff62f220522fca4a9da7c49
Validation-Scope: Post-merge product-dev-recovered validation for Night Sprint N Finance receivables page recovery
Allow-Code-Changes: false
Allow-Product-Push: false
Report branch: reports/lubuntu-validation
Report path: docs/ai-reports/lubuntu/2026-05-22_night_sprint_n_post_merge_ghost_qa_validation.md

# Night Sprint N Post-Merge Ghost QA Validation

Objective:
Validate `origin/product-dev-recovered` after promoting Night Sprint N into the product line.

Validation contract:
Use `docs/ai-directives/vibecoder/contracts/ghost_qa_validation_contract.md`. This run must validate the merged product branch, not only the feature branch. Treat missing human-centered evidence as a validation failure.

Required branch/commit checks:
1. `git fetch origin --prune`
2. `git checkout origin/product-dev-recovered --detach`
3. `git rev-parse HEAD`
4. Confirm HEAD equals `9d02e38a52f6111c5ff62f220522fca4a9da7c49`.
5. `git status --short` must be clean before and after validation.

Required validation commands:
1. Frontend dependency reuse, lint, production build, and Ghost QA structural contract:
   `cd ../frontend && pnpm install --offline --frozen-lockfile --ignore-workspace --ignore-scripts && pnpm --ignore-workspace run lint && pnpm --ignore-workspace run build && python3 -c "from pathlib import Path; s=Path('src/pages/finance/FinancePage.tsx').read_text(); required=['page > pagination.pages && pagination.pages > 0','buildFinanceSearchParams(tab, pagination.pages','recorded: collectionRecorded','orderId: collectedOrderId','Refreshing...']; missing=[x for x in required if x not in s]; assert not missing, missing; print('ghost_qa_page_recovery_contract=pass')"`
2. Receivables targeted suite from `backend`:
   `REPORTING_USER_PASSWORD=${REPORTING_USER_PASSWORD:-MpangoTest_2026} poetry run pytest tests/test_receivables_service.py tests/test_finance_receivables_api.py -q --tb=short`
3. Phase 5 payment regression from `backend`:
   `REPORTING_USER_PASSWORD=${REPORTING_USER_PASSWORD:-MpangoTest_2026} poetry run pytest tests/test_phase5_order_payment.py -q --tb=short`
4. Prepare `t_dev` and run schema contract from `backend`:
   `MPANGO_DB_USER=${MPANGO_DB_USER:-mpango} MPANGO_DB_PASSWORD=${MPANGO_DB_PASSWORD:-mpango} MPANGO_DB_HOST=${MPANGO_DB_HOST:-127.0.0.1} MPANGO_DB_PORT=${MPANGO_DB_PORT:-5432} MPANGO_DB_NAME=${MPANGO_DB_NAME:-mpango_erp} REPORTING_USER_PASSWORD=${REPORTING_USER_PASSWORD:-MpangoTest_2026} bash -lc 'export DATABASE_URL="postgresql://${MPANGO_DB_USER}:${MPANGO_DB_PASSWORD}@${MPANGO_DB_HOST}:${MPANGO_DB_PORT}/${MPANGO_DB_NAME}"; poetry run python scripts/bootstrap_tenant_schema.py t_dev --database-url "$DATABASE_URL" && poetry run pytest tests/test_payments_schema_contract.py -q --tb=short -rs'`

Expected evidence:
- COMMANDS_EXECUTED: 9/9
- PREFLIGHT: 5/5
- VALIDATION: 4/4
- App Import Smoke: frontend offline install, lint, build, and `ghost_qa_page_recovery_contract=pass`.
- Receivables Suite: 38 passed, 0 failed.
- Phase 5 payment regression: 53 passed, 1 xfailed, 0 failed.
- Schema contract: 40 passed, 0 skipped, 0 failed.
- Schema Skip Reasons: NONE.
- Product Code Modified: no
- Product Branch Pushed: no
- Commit Hash: 9d02e38a52f6111c5ff62f220522fca4a9da7c49

Ghost QA scenario obligations:
- Confirm the merged product branch handles a bookmarked/shared Finance URL whose requested page is beyond the available API pagination page count.
- Confirm page recovery redirects to the last valid page instead of showing a misleading empty state.
- Confirm collection notice state is preserved during page recovery (`collection=recorded` and `collectedOrder` context).
- Confirm Refresh communicates loading state as `Refreshing...`.
- Confirm no product code, test, migration, backend, API, auth, RBAC, tenancy, or platform files were modified by Leo.

Hard rules:
- Leo must execute all 5 preflight commands and all 4 validation commands.
- Command 1 must run install, lint, build, and the Ghost QA structural contract. Do not mark it passed if any part fails.
- Command 4 must run both tenant bootstrap/reconcile and schema contract pytest.
- Do not modify product code.
- Do not modify tests.
- Do not commit from the validation target.
- Do not push product branches.
- Do not write report files from Leo; run_directive.sh writes the report.
- Do not classify as PASS if any validation suite says BLOCKED, failed, error, skipped, or unknown.
- Do not classify as PASS if schema contract has any skipped tests.
- Do not classify as PASS if the Ghost QA structural contract is missing or fails.
- If frontend dependencies cannot be reused offline, classify as BLOCKED_ENVIRONMENT, not PASS.
- If gateway_timeout or fallbackUsed=true occurs, classify as FAIL_RUNNER_INFRA_WITH_VALIDATION_COMPLETED, not PASS.

Acceptance criteria:
- GitHub Actions conclusion = success.
- Runner name = mpango-lubuntu-01.
- Report exists on reports/lubuntu-validation.
- Mode = VALIDATION_GATE.
- Leo Invoked = true.
- COMMANDS_EXECUTED = 9/9.
- VALIDATION = 4/4.
- Frontend install/lint/build all passed.
- Ghost QA structural contract passed.
- Receivables Suite = 38 passed, 0 failed.
- Phase 5 Payment Regression = 53 passed, 1 xfailed, 0 failed.
- Schema Contract = 40 passed, 0 skipped, 0 failed.
- Product code modified = no.
- Product branch pushed = no.
- Transport health is healthy.
