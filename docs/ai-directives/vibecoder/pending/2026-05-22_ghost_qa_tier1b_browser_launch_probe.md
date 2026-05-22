Directive-ID: ghost-qa-tier1b-browser-launch-probe-2026-05-22
Mode: VALIDATION_GATE
Priority: HIGH
Created: 2026-05-22
Status: pending
Target branch: product-dev-recovered
Target-Commit: 9d02e38a52f6111c5ff62f220522fca4a9da7c49
Validation-Scope: Ghost QA Tier 1B browser launch probe for future browser-driven human journey validation
Allow-Code-Changes: false
Allow-Product-Push: false
Report branch: reports/lubuntu-validation
Report path: docs/ai-reports/lubuntu/2026-05-22_ghost_qa_tier1b_browser_launch_probe.md

# Ghost QA Tier 1B Browser Launch Probe

Objective:
Prove that Leo can launch a real headless browser, render a local page, and execute a DOM assertion before CTO promotes Tier 2 browser journey directives.

Validation contract:
Use `docs/ai-directives/vibecoder/contracts/ghost_qa_validation_contract.md`, especially Tier 1B. This run is still environment/capability validation. It must not modify product code and must not pretend to be a full product journey.

Required branch/commit checks:
1. `git fetch origin --prune`
2. `git checkout origin/product-dev-recovered --detach`
3. `git rev-parse HEAD`
4. Confirm HEAD equals `9d02e38a52f6111c5ff62f220522fca4a9da7c49`.
5. `git status --short` must be clean before and after validation.

Required validation commands:
1. Frontend dependency reuse, lint, production build, structural contract, and real headless browser launch probe:
   `cd ../frontend && pnpm install --offline --frozen-lockfile --ignore-workspace --ignore-scripts && pnpm --ignore-workspace run lint && pnpm --ignore-workspace run build && node -e 'const cp=require("child_process"); const fs=require("fs"); const src=fs.readFileSync("src/pages/finance/FinancePage.tsx","utf8"); const required=["page > pagination.pages && pagination.pages > 0","buildFinanceSearchParams(tab, pagination.pages","recorded: collectionRecorded","orderId: collectedOrderId","Refreshing..."]; const missing=required.filter(x=>!src.includes(x)); if(missing.length){console.error("ghost_qa_structural_missing="+missing.join(",")); process.exit(1);} function tryRequire(name){try{return require(name);}catch(e){return null;}} (async()=>{const html="<!doctype html><html><body><main id=\\"app\\">ghost_browser_probe</main><script>document.body.dataset.ghost=\\"ok\\";</script></body></html>"; const pw=tryRequire("@playwright/test")||tryRequire("playwright"); if(pw&&pw.chromium){const browser=await pw.chromium.launch({headless:true}); const page=await browser.newPage(); await page.setContent(html); const text=await page.textContent("#app"); await browser.close(); if(text!=="ghost_browser_probe"){throw new Error("playwright_dom_assertion_failed");} console.log("ghost_qa_browser_launch=pass(playwright)"); return;} const browserPath=cp.execSync("bash -lc \\"command -v chromium || command -v chromium-browser || command -v google-chrome || true\\"",{encoding:"utf8"}).trim(); if(!browserPath){console.error("ghost_qa_browser_launch=blocked:no_browser"); process.exit(2);} const out=cp.execFileSync(browserPath,["--headless=new","--disable-gpu","--no-sandbox","--dump-dom","data:text/html,"+encodeURIComponent(html)],{encoding:"utf8",timeout:20000}); if(!out.includes("ghost_browser_probe")){throw new Error("system_browser_dom_assertion_failed");} console.log("ghost_qa_browser_launch=pass(system)");})().catch(e=>{console.error("ghost_qa_browser_launch=fail:"+e.message); process.exit(1);});'`
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
- App Import Smoke: frontend offline install, lint, build, structural contract, and `ghost_qa_browser_launch=pass(...)`.
- Receivables Suite: 38 passed, 0 failed.
- Phase 5 payment regression: 53 passed, 1 xfailed, 0 failed.
- Schema contract: 40 passed, 0 skipped, 0 failed.
- Schema Skip Reasons: NONE.
- Product Code Modified: no
- Product Branch Pushed: no
- Commit Hash: 9d02e38a52f6111c5ff62f220522fca4a9da7c49

Ghost QA Tier 1B obligations:
- Confirm the Finance page structural recovery contract still exists.
- Confirm a real headless browser launches successfully.
- Confirm a DOM assertion executes in that browser.
- If browser launch is unavailable, use `BLOCKED_ENVIRONMENT`, not PASS and not product failure.
- If launch succeeds, CTO may proceed to Tier 2 real product journey validation.

Hard rules:
- Leo must execute all 5 preflight commands and all 4 validation commands.
- Command 1 must run install, lint, build, structural contract check, and browser launch probe.
- Do not modify product code.
- Do not modify tests.
- Do not commit from the validation target.
- Do not push product branches.
- Do not write report files from Leo; run_directive.sh writes the report.
- Do not classify as PASS if any validation suite says BLOCKED, failed, error, skipped, or unknown.
- Do not classify as PASS if schema contract has any skipped tests.
- Do not classify as PASS if browser launch is missing or fails; use BLOCKED_ENVIRONMENT or FAIL_VALIDATION according to root cause.
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
- Browser launch probe passed.
- Receivables Suite = 38 passed, 0 failed.
- Phase 5 Payment Regression = 53 passed, 1 xfailed, 0 failed.
- Schema Contract = 40 passed, 0 skipped, 0 failed.
- Product code modified = no.
- Product branch pushed = no.
- Transport health is healthy.
