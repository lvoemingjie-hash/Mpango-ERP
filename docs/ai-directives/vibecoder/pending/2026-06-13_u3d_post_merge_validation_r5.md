Directive-ID: u3d-post-merge-validation-r5-2026-06-13
Mode: VALIDATION_GATE
Priority: HIGH
Created: 2026-06-13
Status: pending
Target branch: product-dev-recovered
Target-Commit: fb35d473fa782e93632458b9b7ebbea0254fdaa6
Validation-Scope: U3-D post-merge validation R5 after Leo rc initialization fix
Allow-Code-Changes: false
Allow-Product-Push: false
Report branch: reports/lubuntu-validation
Report path: docs/ai-reports/lubuntu/2026-06-13_u3d_post_merge_validation_r5.md

# U3-D Post-Merge Validation R5

Objective:
Validate the exact post-merge product branch commit after U3-D Product Import UX
Entry was promoted into `product-dev-recovered`. R5 verifies the Leo success-path rc initialization
fix on the Lubuntu self-hosted runner.

Required branch/commit checks:
1. `git fetch origin --prune`
2. `git checkout origin/product-dev-recovered --detach`
3. `git rev-parse HEAD`
4. Confirm HEAD equals `fb35d473fa782e93632458b9b7ebbea0254fdaa6`.
5. `git status --short` must be clean before and after validation.

Required validation commands:
1. Frontend U3-D focused tests and production build:
   `cd ../frontend && pnpm install --frozen-lockfile --ignore-scripts && pnpm exec vitest run src/tests/SKUImportModal.test.tsx src/tests/SKUListPage.test.tsx && pnpm run build`
2. Backend U3 import regression from `backend`:
   `poetry run pytest tests/test_u3b1_contract_foundation.py tests/test_u3b2_preview_validate.py tests/test_u3c_import_apply.py -q --tb=short`
3. Phase 5 payment regression from `backend`:
   `poetry run pytest tests/test_phase5_order_payment.py -q --tb=short`
4. U3-D merge scope contract from `backend`:
   `bash -lc 'git -C .. diff --name-only HEAD^1 HEAD | tee /tmp/u3d_scope_files.txt; test "$(wc -l < /tmp/u3d_scope_files.txt)" -eq 11; if grep -E "^(backend/|\\.github/|scripts/|docs/ai/)|alembic" /tmp/u3d_scope_files.txt; then exit 1; fi; echo "u3d_scope_contract=pass 11 files 0 skipped 0 failed"'`

Expected evidence:
- COMMANDS_EXECUTED: 9/9
- PREFLIGHT: 5/5
- VALIDATION: 4/4
- App Import Smoke: `u3d_frontend_tests=passed`, `frontend_build=passed`.
- Receivables Suite: `u3_import_regression=passed`, with no failed tests.
- Phase 5 payment regression: `53 passed, 1 xfailed, 0 failed`.
- Schema contract: `u3d_scope_contract=pass 11 files 0 skipped 0 failed`.
- Schema Skip Reasons: NONE.
- Product Code Modified: no.
- Product Branch Pushed: no.
- Commit Hash: `fb35d473fa782e93632458b9b7ebbea0254fdaa6`.

Hard rules:
- Leo must execute all 5 preflight commands and all 4 validation commands.
- Do not modify product code.
- Do not modify tests.
- Do not commit from the validation target.
- Do not push product branches.
- Do not write report files from Leo; run_directive.sh writes the report.
- If any validation command fails or is skipped, classify as `FAIL_VALIDATION`, not PASS.

Acceptance criteria:
- GitHub Actions conclusion must be `success`.
- Report must exist on `reports/lubuntu-validation`.
- Report Commit Hash must equal `fb35d473fa782e93632458b9b7ebbea0254fdaa6`.
- Mode must be `VALIDATION_GATE`.
- Leo Invoked must be `true`.
- COMMANDS_EXECUTED must be `9/9`.
- VALIDATION must be `4/4`.
- Product Code Modified must be `no`.
- Product Branch Pushed must be `no`.
- Transport health must be healthy.
