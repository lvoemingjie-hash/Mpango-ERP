Directive-ID: sprint-m-feature-validation-2026-05-21
Mode: VALIDATION_GATE
Priority: HIGH
Created: 2026-05-21
Status: pending
Target branch: codex/sprint-m-payment-page-recovery-2026-05-21
Target-Commit: c5d8ba0bc86d44a22cabf08f94fa0b5b87e47455
Validation-Scope: Feature-branch validation for Sprint M Payment History Out-of-Range Page Recovery before product merge
Allow-Code-Changes: false
Allow-Product-Push: false
Report branch: reports/lubuntu-validation
Report path: docs/ai-reports/lubuntu/2026-05-21_sprint_m_feature_validation.md

# Sprint M Feature Branch Validation

Objective:
Validate `origin/codex/sprint-m-payment-page-recovery-2026-05-21` before CTO decides whether to merge it into `product-dev-recovered`.

Required branch/commit checks:
1. `git fetch origin --prune`
2. `git checkout origin/codex/sprint-m-payment-page-recovery-2026-05-21 --detach`
3. `git rev-parse HEAD`
4. Confirm HEAD equals `c5d8ba0bc86d44a22cabf08f94fa0b5b87e47455`.
5. `git status --short` must be clean before and after validation.

Required validation commands:
1. Frontend dependency reuse, lint, and production build with workspace isolation and no dependency build scripts:
   `cd ../frontend && pnpm install --offline --frozen-lockfile --ignore-workspace --ignore-scripts && pnpm --ignore-workspace run lint && pnpm --ignore-workspace run build`
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
- App Import Smoke: pnpm install exit 0, eslint exit 0, tsc exit 0, vite build exit 0.
- Receivables Suite: 38 passed, 0 failed.
- Phase 5 payment regression: 53 passed, 1 xfailed, 0 failed.
- Schema contract: 40 passed, 0 skipped, 0 failed.
- Schema Skip Reasons: NONE.
- Product Code Modified: no
- Product Branch Pushed: no
- Commit Hash: c5d8ba0bc86d44a22cabf08f94fa0b5b87e47455

Hard rules:
- Leo must execute all 5 preflight commands and all 4 validation commands.
- Command 1 must run install, lint, and build; do not mark it passed if any of the three exits nonzero.
- Command 4 must run both tenant bootstrap/reconcile and schema contract pytest.
- Do not modify product code.
- Do not modify tests.
- Do not commit from the validation target.
- Do not push product branches.
- Do not write report files from Leo; run_directive.sh writes the report.
- Do not classify as PASS if any validation suite says BLOCKED, failed, error, skipped, or unknown.
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
- Frontend install/lint/build all passed.
- Receivables Suite = 38 passed, 0 failed.
- Phase 5 Payment Regression = 53 passed, 1 xfailed, 0 failed.
- Schema Contract = 40 passed, 0 skipped, 0 failed.
- Product code modified = no.
- Product branch pushed = no.
- Transport health is healthy.
