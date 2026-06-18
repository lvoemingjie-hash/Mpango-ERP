Directive-ID: u3e-post-merge-validation-2026-06-18
Mode: VALIDATION_GATE
Priority: HIGH
Created: 2026-06-18
Status: pending
Target branch: product-dev-recovered
Target-Commit: 53ca2143f5e43b918c258e3f488e6944c5a7a41b
Validation-Scope: U3-E post-merge validation after CTO merge into product-dev-recovered
Allow-Code-Changes: false
Allow-Product-Push: false
Report branch: reports/lubuntu-validation
Report path: docs/ai-reports/lubuntu/2026-06-18_u3e_post_merge_validation.md

# U3-E Post-Merge Validation

Objective:
Validate the exact post-merge product branch commit after U3-E Product Import E2E Hardening was promoted into `product-dev-recovered`.

Required branch/commit checks:
1. `git fetch origin --prune`
2. `git checkout origin/product-dev-recovered --detach`
3. `git rev-parse HEAD`
4. Confirm HEAD equals `53ca2143f5e43b918c258e3f488e6944c5a7a41b`.
5. `git status --short` must be clean before and after validation.

Required validation commands:
1. Frontend U3-D/U3-E focused tests and production build:
   `cd ../frontend && pnpm install --frozen-lockfile --ignore-scripts && pnpm exec vitest run src/tests/SKUListPage.test.tsx src/tests/SKUImportModal.test.tsx src/tests/SKUImportE2E.test.tsx && pnpm run build`
2. Backend U3 import regression from `backend`:
   `poetry run pytest tests/test_u3b1_contract_foundation.py tests/test_u3b2_preview_validate.py tests/test_u3c_import_apply.py tests/test_u3e_e2e_hardening.py -q --tb=short`
3. Phase 5 payment regression from `backend`:
   `REPORTING_USER_PASSWORD="${REPORTING_USER_PASSWORD:-mpango_runner_reporting_password}" poetry run pytest tests/test_phase5_order_payment.py -q --tb=short`
4. U3-E merge scope contract from `backend`:
   `bash -lc 'git -C .. diff --name-only HEAD^1 HEAD | tee /tmp/u3e_scope_files.txt; test "$(wc -l < /tmp/u3e_scope_files.txt)" -eq 3; if grep -v -E "^(ai-ledger/product-ai/2026-06-13_u3e_product_import_e2e_hardening.md|backend/tests/test_u3e_e2e_hardening.py|frontend/src/tests/SKUImportE2E.test.tsx)$" /tmp/u3e_scope_files.txt; then exit 1; fi; echo "u3e_scope_contract=pass 3 files 0 skipped 0 failed"'`

Expected evidence:
- COMMANDS_EXECUTED: 9/9
- PREFLIGHT: 5/5
- VALIDATION: 4/4
- App Import Smoke: frontend U3 tests passed and frontend build passed.
- Receivables Suite: backend U3 import regression passed, with no failed tests.
- Phase 5 payment regression: `53 passed, 1 xfailed, 0 failed`.
- Schema contract: `u3e_scope_contract=pass 3 files 0 skipped 0 failed`.
- Schema Skip Reasons: NONE.
- Product Code Modified: no.
- Product Branch Pushed: no.
- Commit Hash: `53ca2143f5e43b918c258e3f488e6944c5a7a41b`.

Hard rules:
- Leo/runner must execute all 5 preflight commands and all 4 validation commands.
- Do not modify product code.
- Do not modify tests.
- Do not commit from the validation target.
- Do not push product branches.
- Do not write report files from Leo; run_directive.sh writes the report.
- If any validation command fails or is skipped, classify as `FAIL_VALIDATION`, not PASS.

Acceptance criteria:
- GitHub Actions conclusion must be `success`.
- Report must exist on `reports/lubuntu-validation`.
- Report Commit Hash must equal `53ca2143f5e43b918c258e3f488e6944c5a7a41b`.
- Mode must be `VALIDATION_GATE`.
- Leo Invoked must be `true`.
- COMMANDS_EXECUTED must be `9/9`.
- VALIDATION must be `4/4`.
- Product Code Modified must be `no`.
- Product Branch Pushed must be `no`.
- Transport health must be healthy.
