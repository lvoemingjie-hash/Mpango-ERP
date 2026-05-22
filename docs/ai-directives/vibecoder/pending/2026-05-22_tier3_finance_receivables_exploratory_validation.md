Directive-ID: ghost-qa-tier3-finance-receivables-exploratory-2026-05-22
Mode: VALIDATION_GATE
Priority: HIGH
Created: 2026-05-22
Status: pending
Target branch: product-dev-recovered
Target-Commit: a40591f3a3fbde63fb5edb3e4542010b644f8019
Validation-Scope: Tier3 exploratory Ghost QA for Finance receivables MVP closeout
Allow-Code-Changes: false
Allow-Product-Push: false
Report branch: reports/lubuntu-validation
Report path: docs/ai-reports/lubuntu/2026-05-22_tier3_finance_receivables_exploratory_validation.md

# Tier3 Finance Receivables Exploratory Validation

Objective:
Run the stable regression gate plus an additional exploratory Ghost QA browser script that uses variant mocked data and edge-case flows. This is intentionally broader than the fixed Tier2 journey and is meant to catch AI-friendly blind spots before the MVP closeout.

Required branch/commit checks:
1. `git fetch origin --prune`
2. `git checkout origin/product-dev-recovered --detach`
3. `git rev-parse HEAD`
4. Confirm HEAD equals `a40591f3a3fbde63fb5edb3e4542010b644f8019`.
5. `git status --short` must be clean before and after validation.

Required validation commands:
1. Build frontend, run Tier2, then run Tier3 exploratory browser QA from the directives repo:
   `cd ../frontend && pnpm install --offline --frozen-lockfile --ignore-workspace --ignore-scripts && pnpm --ignore-workspace run lint && pnpm --ignore-workspace run build && NODE_PATH="$HOME/.openclaw/mpango-validation-tools/playwright-runtime/node_modules${NODE_PATH:+:$NODE_PATH}" node ../../directives/scripts/ghost_qa/tier2_finance_receivables_journey.cjs && NODE_PATH="$HOME/.openclaw/mpango-validation-tools/playwright-runtime/node_modules${NODE_PATH:+:$NODE_PATH}" node ../../directives/scripts/ghost_qa/tier3_finance_receivables_exploratory.cjs`
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
- App Import Smoke includes:
  - `ghost_qa_tier2_journey=pass(finance_receivables_browser)`
  - `ghost_qa_tier3_exploratory=pass(finance_receivables_edge_cases)`
  - `tier3_empty_state=pass`
  - `tier3_error_recovery=pass`
  - `tier3_invalid_url_recovery=pass`
  - `tier3_unpaid_filter=pass`
- Receivables Suite: 38 passed, 0 failed.
- Phase 5 payment regression: 53 passed, 1 xfailed, 0 failed.
- Schema contract: 40 passed, 0 skipped, 0 failed.
- Schema Skip Reasons: NONE.
- Product Code Modified: no.
- Product Branch Pushed: no.
- Commit Hash: `a40591f3a3fbde63fb5edb3e4542010b644f8019`.

Hard rules:
- Leo must execute all 5 preflight commands and all 4 validation commands.
- If `git rev-parse HEAD` is not exactly `a40591f3a3fbde63fb5edb3e4542010b644f8019`, stop and report `FAIL_VALIDATION`.
- Final Gate must compare this directive's `Target-Commit` against the report `Commit Hash`.
- Do not modify product code.
- Do not modify tests.
- Do not commit from the validation target.
- Do not push product branches.
- Do not write report files from Leo; run_directive.sh writes the report.

Acceptance criteria:
- GitHub Actions conclusion must be `success`.
- Report must exist on `reports/lubuntu-validation`.
- Report Commit Hash must equal `a40591f3a3fbde63fb5edb3e4542010b644f8019`.
- App Import Smoke must include Tier2 pass and all Tier3 exploratory pass markers.
