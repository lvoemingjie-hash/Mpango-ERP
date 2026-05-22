Directive-ID: ghost-qa-tier1b-browser-launch-probe-r3-env-fixed-2026-05-22
Mode: VALIDATION_GATE
Priority: HIGH
Created: 2026-05-22
Status: pending
Target branch: product-dev-recovered
Target-Commit: 9d02e38a52f6111c5ff62f220522fca4a9da7c49
Validation-Scope: R3 verification that Ghost QA browser launch probe PASSES on lubuntu runner with Playwright-cached Chromium
Allow-Code-Changes: false
Allow-Product-Push: false
Report branch: reports/lubuntu-validation
Report path: docs/ai-reports/lubuntu/2026-05-22_ghost_qa_tier1b_browser_launch_probe_r3_env_fixed.md

# Ghost QA Tier 1B Browser Launch Probe R3 — Environment Fixed

Objective:
Re-run the browser launch probe after fixing the Chromium detection path. R2 failed because chromium-browser on lubuntu is a snap stub; R3 command now also checks Playwright's cached Chromium at known locations. This run MUST produce `ghost_qa_browser_launch=pass(...)`.

Root cause of R2 failure:
- `chromium-browser` on lubuntu is a transitional package pointing to snap
- snapd chromium is NOT installed on the runner
- Playwright chromium IS available at `$HOME/.cache/ms-playwright/chromium-1208/chrome-linux64/chrome` but was not on PATH
- The R2 command only searched PATH, never checked Playwright cache dirs

R3 fix:
- Added Playwright cache directory scanning to the fallback browser detection
- Checks `~/.cache/ms-playwright/chromium-*/chrome-linux64/chrome` as first fallback before system PATH

Validation contract:
Use `docs/ai-directives/vibecoder/contracts/ghost_qa_validation_contract.md`. This run specifically verifies that Ghost QA evidence produces a clean pass.

Required branch/commit checks:
1. `git fetch origin --prune`
2. `git checkout origin/product-dev-recovered --detach`
3. `git rev-parse HEAD`
4. Confirm HEAD equals `9d02e38a52f6111c5ff62f220522fca4a9da7c49`.
5. `git status --short` must be clean before and after validation.

Required validation commands:
1. Frontend dependency reuse, lint, production build, structural contract, and headless browser launch probe:
   `cd ../frontend && pnpm install --offline --frozen-lockfile --ignore-workspace --ignore-scripts && pnpm --ignore-workspace run lint && pnpm --ignore-workspace run build && node -e 'const cp=require("child_process"); const fs=require("fs"); const os=require("os"); const path=require("path"); const src=fs.readFileSync("src/pages/finance/FinancePage.tsx","utf8"); const required=["page > pagination.pages && pagination.pages > 0","buildFinanceSearchParams(tab, pagination.pages","recorded: collectionRecorded","orderId: collectedOrderId","Refreshing..."]; const missing=required.filter(x=>!src.includes(x)); if(missing.length){console.error("ghost_qa_structural_missing="+missing.join(",")); process.exit(1);} function tryRequire(name){try{return require(name);}catch(e){return null;}} function findBrowser(){try{const pw=tryRequire("@playwright/test")||tryRequire("playwright"); if(pw&&pw.chromium)return{type:"playwright-module",found:true};}catch(e){} const cacheDir=path.join(os.homedir(),".cache","ms-playwright"); try{const dirs=fs.readdirSync(cacheDir).filter(d=>d.startsWith("chromium-")).sort().reverse(); for(const d of dirs){const chrome=path.join(cacheDir,d,"chrome-linux64","chrome"); if(fs.existsSync(chrome))return{type:"playwright-cache",path:chrome,found:true};}}catch(e){} const sys=cp.execSync("bash -lc \\"command -v chromium-browser || command -v chromium || command -v google-chrome || true\\"",{encoding:"utf8"}).trim(); if(sys)return{type:"system",path:sys,found:true}; return{found:false};} (async()=>{const html="<!doctype html><html><body><main id=\\"app\\">ghost_browser_probe</main><script>document.body.dataset.ghost=\\"ok\\";</script></body></html>"; const browser=findBrowser(); if(!browser.found){console.error("ghost_qa_browser_launch=blocked:no_browser"); process.exit(2);} if(browser.type==="playwright-module"){const pw=tryRequire("@playwright/test")||tryRequire("playwright"); const b=await pw.chromium.launch({headless:true,args:["--no-sandbox"]}); const p=await b.newPage(); await p.setContent(html); const t=await p.textContent("#app"); await b.close(); if(t!=="ghost_browser_probe"){throw new Error("playwright_dom_assertion_failed");} console.log("ghost_qa_browser_launch=pass(playwright)"); return;} const browserPath=browser.path; const out=cp.execFileSync(browserPath,["--headless=new","--disable-gpu","--no-sandbox","--dump-dom","data:text/html,"+encodeURIComponent(html)],{encoding:"utf8",timeout:20000}); if(!out.includes("ghost_browser_probe")){throw new Error("system_browser_dom_assertion_failed");} console.log("ghost_qa_browser_launch=pass("+browser.type+")");})().catch(e=>{console.error("ghost_qa_browser_launch=fail:"+e.message); process.exit(1);});'`
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
- App Import Smoke: frontend offline install, lint, build, structural contract, and browser launch evidence with `ghost_qa_browser_launch=pass(playwright)` or `ghost_qa_browser_launch=pass(playwright-cache)`.
- Receivables Suite: 38 passed, 0 failed.
- Phase 5 payment regression: 53 passed, 1 xfailed, 0 failed.
- Schema contract: 40 passed, 0 skipped, 0 failed.
- Schema Skip Reasons: NONE.
- Product Code Modified: no
- Product Branch Pushed: no
- Commit Hash: 9d02e38a52f6111c5ff62f220522fca4a9da7c49

Hard rules:
- Leo must execute all 5 preflight commands and all 4 validation commands.
- Command 1 must run install, lint, build, structural contract check, and browser launch probe.
- Do not modify product code.
- Do not modify tests.
- Do not commit from the validation target.
- Do not push product branches.
- Do not write report files from Leo; run_directive.sh writes the report.
- Do not classify as PASS if App Import Smoke contains `fail`, `blocked`, or `error`.
- Do not classify as PASS if any validation suite says BLOCKED, failed, error, skipped, or unknown.
- Do not classify as PASS if schema contract has any skipped tests.
- If gateway_timeout or fallbackUsed=true occurs, classify as FAIL_RUNNER_INFRA_WITH_VALIDATION_COMPLETED, not PASS.

Acceptance criteria:
- GitHub Actions conclusion must be `success`.
- Report must exist on `reports/lubuntu-validation`.
- App Import Smoke must show `ghost_qa_browser_launch=pass(playwright)` or `ghost_qa_browser_launch=pass(system)` — no `fail`, `blocked`, or `error`.
- COMMANDS_EXECUTED must be 9/9.
- Product code must not be modified.
- Product branch must not be pushed.
