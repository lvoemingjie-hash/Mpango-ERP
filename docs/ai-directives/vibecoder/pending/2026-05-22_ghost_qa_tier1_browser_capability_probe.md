Directive-ID: ghost-qa-tier1-browser-capability-probe-2026-05-22
Mode: VALIDATION_GATE
Priority: HIGH
Created: 2026-05-22
Status: pending
Target branch: product-dev-recovered
Target-Commit: 9d02e38a52f6111c5ff62f220522fca4a9da7c49
Validation-Scope: Ghost QA Tier 1 browser capability probe for Finance receivables validation
Allow-Code-Changes: false
Allow-Product-Push: false
Report branch: reports/lubuntu-validation
Report path: docs/ai-reports/lubuntu/2026-05-22_ghost_qa_tier1_browser_capability_probe.md

# Ghost QA Tier 1 Browser Capability Probe

Objective:
Upgrade Leo from static/structural Ghost QA toward browser-capable human journey validation. This run probes whether the Lubuntu validation machine can support browser-level QA without modifying product code.

Validation contract:
Use `docs/ai-directives/vibecoder/contracts/ghost_qa_validation_contract.md`, especially the "Ghost QA Maturity Tiers" section. This run is Tier 1, not Tier 2. It must not pretend to be a full browser journey if browser automation is missing.

Required branch/commit checks:
1. `git fetch origin --prune`
2. `git checkout origin/product-dev-recovered --detach`
3. `git rev-parse HEAD`
4. Confirm HEAD equals `9d02e38a52f6111c5ff62f220522fca4a9da7c49`.
5. `git status --short` must be clean before and after validation.

Required validation commands:
1. Frontend dependency reuse, lint, production build, Ghost QA structural contract, and browser capability probe:
   `cd ../frontend && pnpm install --offline --frozen-lockfile --ignore-workspace --ignore-scripts && pnpm --ignore-workspace run lint && pnpm --ignore-workspace run build && node -e "const fs=require('fs'); const cp=require('child_process'); const s=fs.readFileSync('src/pages/finance/FinancePage.tsx','utf8'); const required=['page > pagination.pages && pagination.pages > 0','buildFinanceSearchParams(tab, pagination.pages','recorded: collectionRecorded','orderId: collectedOrderId','Refreshing...']; const missing=required.filter(x=>!s.includes(x)); if(missing.length){console.error('ghost_qa_structural_missing='+missing.join(',')); process.exit(1);} function hasModule(name){try{require.resolve(name); return true;}catch(e){return false;}} const hasPwTest=hasModule('@playwright/test'); const hasPw=hasModule('playwright'); const browserPath=cp.execSync('bash -lc \"command -v chromium || command -v chromium-browser || command -v google-chrome || true\"',{encoding:'utf8'}).trim(); console.log('ghost_qa_structural_contract=pass'); console.log('ghost_qa_browser_modules=@playwright/test:'+hasPwTest+',playwright:'+hasPw); console.log('ghost_qa_system_browser='+(browserPath || 'missing')); if(!hasPwTest && !hasPw && !browserPath){console.error('ghost_qa_browser_capability=blocked'); process.exit(2);} console.log('ghost_qa_browser_capability=pass');"`
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
- App Import Smoke: frontend offline install, lint, build, `ghost_qa_structural_contract=pass`, and `ghost_qa_browser_capability=pass`.
- Receivables Suite: 38 passed, 0 failed.
- Phase 5 payment regression: 53 passed, 1 xfailed, 0 failed.
- Schema contract: 40 passed, 0 skipped, 0 failed.
- Schema Skip Reasons: NONE.
- Product Code Modified: no
- Product Branch Pushed: no
- Commit Hash: 9d02e38a52f6111c5ff62f220522fca4a9da7c49

Ghost QA Tier 1 obligations:
- Confirm the structural Finance page recovery contract still exists.
- Confirm whether browser automation is available via `@playwright/test`, `playwright`, or a system Chromium/Chrome executable.
- If browser capability is missing, use `BLOCKED_ENVIRONMENT`, not PASS and not product failure.
- If browser capability is present, report enough evidence for CTO to decide whether to create Tier 2 browser journey directives.

Hard rules:
- Leo must execute all 5 preflight commands and all 4 validation commands.
- Command 1 must run install, lint, build, structural contract check, and browser capability probe.
- Do not modify product code.
- Do not modify tests.
- Do not commit from the validation target.
- Do not push product branches.
- Do not write report files from Leo; run_directive.sh writes the report.
- Do not classify as PASS if any validation suite says BLOCKED, failed, error, skipped, or unknown.
- Do not classify as PASS if schema contract has any skipped tests.
- Do not classify as PASS if browser capability is missing; use BLOCKED_ENVIRONMENT.
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
- Browser capability probe passed.
- Receivables Suite = 38 passed, 0 failed.
- Phase 5 Payment Regression = 53 passed, 1 xfailed, 0 failed.
- Schema Contract = 40 passed, 0 skipped, 0 failed.
- Product code modified = no.
- Product branch pushed = no.
- Transport health is healthy.
