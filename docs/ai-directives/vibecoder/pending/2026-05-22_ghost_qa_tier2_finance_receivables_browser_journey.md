Directive-ID: ghost-qa-tier2-finance-receivables-browser-journey-2026-05-22
Mode: VALIDATION_GATE
Priority: HIGH
Created: 2026-05-22
Status: pending
Target branch: product-dev-recovered
Target-Commit: 9d02e38a52f6111c5ff62f220522fca4a9da7c49
Validation-Scope: Tier 2 Ghost QA real browser journey for Finance / Accounts Receivable
Allow-Code-Changes: false
Allow-Product-Push: false
Report branch: reports/lubuntu-validation
Report path: docs/ai-reports/lubuntu/2026-05-22_ghost_qa_tier2_finance_receivables_browser_journey.md

# Ghost QA Tier 2 — Finance Receivables Browser Journey

Objective:
Move beyond structural and launch probes. Leo must validate a real built frontend page in a headless browser and exercise human-centered Finance / Accounts Receivable journeys.

Validation contract:
Use `docs/ai-directives/vibecoder/contracts/ghost_qa_validation_contract.md`.

Required branch/commit checks:
1. `git fetch origin --prune`
2. `git checkout origin/product-dev-recovered --detach`
3. `git rev-parse HEAD`
4. Confirm HEAD equals `9d02e38a52f6111c5ff62f220522fca4a9da7c49`.
5. `git status --short` must be clean before and after validation.

Required validation commands:
1. Build frontend and run the Tier 2 browser journey harness from the directives repo:
   `cd ../frontend && pnpm install --offline --frozen-lockfile --ignore-workspace --ignore-scripts && pnpm --ignore-workspace run lint && pnpm --ignore-workspace run build && NODE_PATH="$HOME/.openclaw/mpango-validation-tools/playwright-runtime/node_modules${NODE_PATH:+:$NODE_PATH}" node ../../directives/scripts/ghost_qa/tier2_finance_receivables_journey.cjs`
2. Receivables targeted suite from `backend`:
   `REPORTING_USER_PASSWORD=${REPORTING_USER_PASSWORD:-MpangoTest_2026} poetry run pytest tests/test_receivables_service.py tests/test_finance_receivables_api.py -q --tb=short`
3. Phase 5 payment regression from `backend`:
   `REPORTING_USER_PASSWORD=${REPORTING_USER_PASSWORD:-MpangoTest_2026} poetry run pytest tests/test_phase5_order_payment.py -q --tb=short`
4. Prepare `t_dev` and run schema contract from `backend`:
   `MPANGO_DB_USER=${MPANGO_DB_USER:-mpango} MPANGO_DB_PASSWORD=${MPANGO_DB_PASSWORD:-mpango} MPANGO_DB_HOST=${MPANGO_DB_HOST:-127.0.0.1} MPANGO_DB_PORT=${MPANGO_DB_PORT:-5432} MPANGO_DB_NAME=${MPANGO_DB_NAME:-mpango_erp} REPORTING_USER_PASSWORD=${REPORTING_USER_PASSWORD:-MpangoTest_2026} bash -lc 'export DATABASE_URL="postgresql://${MPANGO_DB_USER}:${MPANGO_DB_PASSWORD}@${MPANGO_DB_HOST}:${MPANGO_DB_PORT}/${MPANGO_DB_NAME}"; poetry run python scripts/bootstrap_tenant_schema.py t_dev --database-url "$DATABASE_URL" && poetry run pytest tests/test_payments_schema_contract.py -q --tb=short -rs'`

Required Tier 2 journey assertions:
- Open `/finance?page=999&collection=recorded&collectedOrder=order-tier2-credit-0001` in the built app.
- Seed auth state only through browser localStorage; do not modify product code.
- Mock finance APIs only through browser/network interception.
- Confirm stale high page recovers to `page=2`.
- Confirm the `Payment recorded` context survives recovery.
- Confirm a receivable row is visible after recovery.
- Confirm refresh produces visible `Refreshing...` feedback.
- Confirm the `Credit` tab updates URL state to `tab=credit_receivable`.
- Confirm row-level `Collect` navigation preserves return context via `/orders?collect=...&returnTo=finance&financeTab=credit_receivable`.

Expected evidence:
- COMMANDS_EXECUTED: 9/9
- PREFLIGHT: 5/5
- VALIDATION: 4/4
- App Import Smoke: `ghost_qa_tier2_journey=pass(finance_receivables_browser)` plus sub-evidence:
  - `stale_page_recovered=pass`
  - `collection_notice_preserved=pass`
  - `refresh_feedback=pass`
  - `tab_filter_url_state=pass`
  - `collect_navigation_context=pass`
- Receivables Suite: 38 passed, 0 failed.
- Phase 5 payment regression: 53 passed, 1 xfailed, 0 failed.
- Schema contract: 40 passed, 0 skipped, 0 failed.
- Schema Skip Reasons: NONE.
- Product Code Modified: no
- Product Branch Pushed: no
- Commit Hash: 9d02e38a52f6111c5ff62f220522fca4a9da7c49

Hard rules:
- Leo must execute all 5 preflight commands and all 4 validation commands.
- Command 1 must run lint, build, and the Tier 2 browser journey harness.
- The Tier 2 journey must use the built frontend served by Vite preview.
- Do not classify source-only checks as Tier 2.
- Do not modify product code.
- Do not modify tests.
- Do not commit from the validation target.
- Do not push product branches.
- Do not write report files from Leo; run_directive.sh writes the report.
- Do not classify as PASS if App Import Smoke lacks `ghost_qa_tier2_journey=pass`.
- Do not classify as PASS if any validation suite says BLOCKED, failed, error, skipped, or unknown.
- Do not classify as PASS if schema contract has any skipped tests.
- If gateway_timeout or fallbackUsed=true occurs, classify as FAIL_RUNNER_INFRA_WITH_VALIDATION_COMPLETED, not PASS.

Acceptance criteria:
- GitHub Actions conclusion must be `success`.
- Report must exist on `reports/lubuntu-validation`.
- App Import Smoke must include `ghost_qa_tier2_journey=pass(finance_receivables_browser)`.
- COMMANDS_EXECUTED must be 9/9.
- Product code must not be modified.
- Product branch must not be pushed.
