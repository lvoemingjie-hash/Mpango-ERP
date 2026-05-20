Directive-ID: sprint-i-finance-refresh-confirmation-validation-r2-2026-05-20
Mode: VALIDATION_GATE
Priority: HIGH
Created: 2026-05-20
Status: pending
Target branch: codex/sprint-i-finance-refresh-confirmation-2026-05-20
Target-Commit: 15486a7ca5f98e59ea719aef525b41422c4d1a20
Validation-Scope: Sprint I Finance refresh confirmation R2 after runner evidence formatting failure
Allow-Code-Changes: false
Allow-Product-Push: false
Report branch: reports/lubuntu-validation
Report path: docs/ai-reports/lubuntu/2026-05-20_sprint_i_finance_refresh_confirmation_validation_r2.md

# Sprint I Feature Branch Validation R2

Objective:
Validate `origin/codex/sprint-i-finance-refresh-confirmation-2026-05-20` before any merge into `product-dev-recovered`.

R2 reason:
The first validation run completed Leo execution with 9/9 commands but failed runner infra because a compliance value was parsed as `no ✅` instead of exact `no`. In this run, all compliance values must be emitted as exact ASCII tokens with no emoji, decorations, suffixes, or prose.

Required branch/commit checks:
1. `git fetch origin --prune`
2. `git checkout origin/codex/sprint-i-finance-refresh-confirmation-2026-05-20 --detach`
3. `git rev-parse HEAD`
4. Confirm HEAD equals `15486a7ca5f98e59ea719aef525b41422c4d1a20`.
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
- Product Code Modified: no
- Product Branch Pushed: no
- Commit Hash: 15486a7ca5f98e59ea719aef525b41422c4d1a20

Strict output discipline:
- For Product Code Modified, output exactly `no` or `yes`.
- For Product Branch Pushed, output exactly `no` or `yes`.
- Do not append emoji, checkmarks, punctuation, notes, or markdown decorations to these two values.
- If product code is clean, the value must be exactly `no`.
- If product branch was not pushed, the value must be exactly `no`.

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
