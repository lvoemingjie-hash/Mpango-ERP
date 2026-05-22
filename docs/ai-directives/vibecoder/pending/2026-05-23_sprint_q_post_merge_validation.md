Directive-ID: ghost-qa-tier3-sprint-q-post-merge-validation-2026-05-23
Mode: VALIDATION_GATE
Priority: HIGH
Created: 2026-05-23
Status: pending
Target branch: product-dev-recovered
Target-Commit: a9b143624a2ce89b8833140e976fe24f15ec34c9
Validation-Scope: Sprint Q post-merge validation on product-dev-recovered
Allow-Code-Changes: false
Allow-Product-Push: false
Report branch: reports/lubuntu-validation
Report path: docs/ai-reports/lubuntu/2026-05-23_sprint_q_post_merge_validation.md

# Sprint Q Post-Merge Validation

Objective:
Validate the exact post-merge product branch commit after Sprint Q was promoted into `product-dev-recovered`.

Required branch/commit checks:
1. `git fetch origin --prune`
2. `git checkout origin/product-dev-recovered --detach`
3. `git rev-parse HEAD`
4. Confirm HEAD equals `a9b143624a2ce89b8833140e976fe24f15ec34c9`.
5. `git status --short` must be clean before and after validation.

Required validation commands:
1. Build frontend, prove the Sprint Q accessibility contract, then run Tier2 and Tier3 browser QA from the directives repo:
   `cd ../frontend && pnpm install --offline --frozen-lockfile --ignore-workspace --ignore-scripts && pnpm --ignore-workspace run lint && pnpm --ignore-workspace run build && node -e 'const fs=require("fs"); const src=fs.readFileSync("src/pages/finance/FinancePage.tsx","utf8"); const required=["if (days === 0) return \\'New\\'","scope=\"col\"","role=\"progressbar\"","aria-valuenow={pct}"]; const missing=required.filter(x=>!src.includes(x)); if(missing.length){console.error("sprint_q_accessibility_contract=fail:"+missing.join(",")); process.exit(1);} console.log("sprint_q_accessibility_contract=pass(receivable_age_table_progressbar)");' && NODE_PATH="$HOME/.openclaw/mpango-validation-tools/playwright-runtime/node_modules${NODE_PATH:+:$NODE_PATH}" node ../../directives/scripts/ghost_qa/tier2_finance_receivables_journey.cjs && NODE_PATH="$HOME/.openclaw/mpango-validation-tools/playwright-runtime/node_modules${NODE_PATH:+:$NODE_PATH}" node ../../directives/scripts/ghost_qa/tier3_finance_receivables_exploratory.cjs`
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
  - `sprint_q_accessibility_contract=pass(receivable_age_table_progressbar)`
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
- Commit Hash: `a9b143624a2ce89b8833140e976fe24f15ec34c9`.

Hard rules:
- Leo must execute all 5 preflight commands and all 4 validation commands.
- If `git rev-parse HEAD` is not exactly `a9b143624a2ce89b8833140e976fe24f15ec34c9`, stop and report `FAIL_VALIDATION`.
- Final Gate must compare this directive's `Target-Commit` against the report `Commit Hash`.
- Do not modify product code.
- Do not modify tests.
- Do not commit from the validation target.
- Do not push product branches.
- Do not write report files from Leo; run_directive.sh writes the report.

Acceptance criteria:
- GitHub Actions conclusion must be `success`.
- Report must exist on `reports/lubuntu-validation`.
- Report Commit Hash must equal `a9b143624a2ce89b8833140e976fe24f15ec34c9`.
- App Import Smoke must include Sprint Q accessibility contract pass plus Tier2 and Tier3 pass markers.
