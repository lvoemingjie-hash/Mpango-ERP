Directive-ID: sprint-e-collection-return-validation-2026-05-19
Mode: VALIDATION_GATE
Priority: HIGH
Created: 2026-05-19
Status: pending
Target branch: codex/sprint-e-collection-return-2026-05-19
Target-Commit: 73deb275ffb5cbe0fbc04d8978298f7072540565
Validation-Scope: Feature-branch validation for Sprint E collection return-to-receivables UX
Allow-Code-Changes: false
Allow-Product-Push: false
Report branch: reports/lubuntu-validation
Report path: docs/ai-reports/lubuntu/2026-05-19_sprint_e_collection_return_validation.md

# Sprint E Collection Return Validation

Objective:
Validate `origin/codex/sprint-e-collection-return-2026-05-19` before any promotion decision. This slice only changes the frontend collection navigation loop: order-specific collection launched from Accounts Receivable should return to `/finance` after a successful payment, while direct Sales-page payment behavior remains unchanged.

Required branch/commit checks:
1. `git fetch origin --prune`
2. `git checkout origin/codex/sprint-e-collection-return-2026-05-19 --detach`
3. `git rev-parse HEAD`
4. Confirm HEAD equals `73deb275ffb5cbe0fbc04d8978298f7072540565`.
5. `git status --short` must be clean before and after validation.

Required validation commands:
1. Frontend dependency reuse, lint, and production build:
   `cd ../frontend && pnpm install --offline --frozen-lockfile && pnpm run lint && pnpm run build`
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
- App Import Smoke: frontend lint and build passed.
- Receivables Suite: 38 passed, 0 failed.
- Phase 5 payment regression: 53 passed, 1 xfailed, 0 failed.
- Schema contract: 40 passed, 0 skipped, 0 failed.
- Schema Skip Reasons: NONE.
- PRODUCT_CODE_MODIFIED: no.
- PRODUCT_BRANCH_PUSHED: no.
- COMMIT_HASH: 73deb275ffb5cbe0fbc04d8978298f7072540565.

Hard rules:
- Leo must execute all 5 preflight commands and all 4 validation commands.
- Command 1 must run both frontend lint and frontend build; do not mark it passed if either fails.
- Command 4 must run both tenant bootstrap/reconcile and schema contract pytest.
- Do not modify product code.
- Do not modify tests.
- Do not commit from the validation target.
- Do not push product branches.
- Do not write report files from Leo; run_directive.sh writes the report.
- Do not classify as PASS if schema contract has any skipped tests.
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
- Frontend lint/build passed.
- Receivables Suite = 38 passed, 0 failed.
- Phase 5 Payment Regression = 53 passed, 1 xfailed, 0 failed.
- Schema Contract = 40 passed, 0 skipped, 0 failed.
- Product code modified = no.
- Product branch pushed = no.
- Transport health is healthy.
