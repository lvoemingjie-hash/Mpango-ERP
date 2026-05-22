Directive-ID: ghost-qa-tier2-sprint-o-finance-refresh-accessibility-r3-hash-gate-2026-05-22
Mode: VALIDATION_GATE
Priority: HIGH
Created: 2026-05-22
Status: pending
Target branch: codex/sprint-o-finance-refresh-accessibility-2026-05-22
Target-Commit: a7f018c126d3eaca02bd8024bb2fd0f5119bbe2c
Validation-Scope: Sprint O exact-hash validation after Final Gate Target-Commit hardening
Allow-Code-Changes: false
Allow-Product-Push: false
Report branch: reports/lubuntu-validation
Report path: docs/ai-reports/lubuntu/2026-05-22_sprint_o_finance_refresh_accessibility_validation_r3_hash_gate.md

# Sprint O — Finance Refresh Accessibility Validation R3 Hash Gate

Objective:
Confirm the hardened Final Gate accepts only reports whose `Commit Hash` exactly matches this directive's `Target-Commit`.

Required branch/commit checks:
1. `git fetch origin --prune`
2. `git checkout origin/codex/sprint-o-finance-refresh-accessibility-2026-05-22 --detach`
3. `git rev-parse HEAD`
4. Confirm HEAD equals `a7f018c126d3eaca02bd8024bb2fd0f5119bbe2c`.
5. `git status --short` must be clean before and after validation.

Required validation commands:
1. Build frontend, prove the labels are distinct, and run the Tier 2 browser journey harness from the directives repo:
   `cd ../frontend && pnpm install --offline --frozen-lockfile --ignore-workspace --ignore-scripts && pnpm --ignore-workspace run lint && pnpm --ignore-workspace run build && node -e 'const fs=require("fs"); const src=fs.readFileSync("src/pages/finance/FinancePage.tsx","utf8"); const required=["Refreshing...","Refreshing balances...","Refresh balances"]; const missing=required.filter(x=>!src.includes(x)); if(missing.length){console.error("sprint_o_label_contract=fail:"+missing.join(",")); process.exit(1);} console.log("sprint_o_label_contract=pass(distinct_refresh_labels)");' && NODE_PATH="$HOME/.openclaw/mpango-validation-tools/playwright-runtime/node_modules${NODE_PATH:+:$NODE_PATH}" node ../../directives/scripts/ghost_qa/tier2_finance_receivables_journey.cjs`
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
  - `sprint_o_label_contract=pass(distinct_refresh_labels)`
  - `ghost_qa_tier2_journey=pass(finance_receivables_browser)`
  - `refresh_feedback=pass`
- Receivables Suite: 38 passed, 0 failed.
- Phase 5 payment regression: 53 passed, 1 xfailed, 0 failed.
- Schema contract: 40 passed, 0 skipped, 0 failed.
- Schema Skip Reasons: NONE.
- Product Code Modified: no.
- Product Branch Pushed: no.
- Commit Hash: `a7f018c126d3eaca02bd8024bb2fd0f5119bbe2c`.

Hard rules:
- Leo must execute all 5 preflight commands and all 4 validation commands.
- If `git rev-parse HEAD` is not exactly `a7f018c126d3eaca02bd8024bb2fd0f5119bbe2c`, stop and report `FAIL_VALIDATION`.
- Final Gate must compare this directive's `Target-Commit` against the report `Commit Hash`.
- Do not modify product code.
- Do not modify tests.
- Do not commit from the validation target.
- Do not push product branches.
- Do not write report files from Leo; run_directive.sh writes the report.

Acceptance criteria:
- GitHub Actions conclusion must be `success`.
- Report must exist on `reports/lubuntu-validation`.
- Report Commit Hash must equal `a7f018c126d3eaca02bd8024bb2fd0f5119bbe2c`.
- App Import Smoke must include both Sprint O label contract pass and Tier 2 journey pass.
