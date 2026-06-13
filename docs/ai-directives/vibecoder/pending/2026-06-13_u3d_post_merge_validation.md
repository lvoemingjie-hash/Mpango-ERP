Directive-ID: u3d-post-merge-validation-2026-06-13
Mode: VALIDATION_GATE
Priority: HIGH
Created: 2026-06-13
Status: pending
Target branch: product-dev-recovered
Target-Commit: fb35d473fa782e93632458b9b7ebbea0254fdaa6
Validation-Scope: U3-D post-merge validation on product-dev-recovered
Allow-Code-Changes: false
Allow-Product-Push: false
Report branch: reports/lubuntu-validation
Report path: docs/ai-reports/lubuntu/2026-06-13_u3d_post_merge_validation.md

# U3-D Post-Merge Validation

Objective:
Validate the exact post-merge product branch commit after U3-D Product Import UX
Entry was promoted into `product-dev-recovered`.

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
   `python - <<'PY'
import subprocess, sys
expected = {
    "ai-ledger/product-ai/2026-06-12_u3d_product_import_ux_entry.md",
    "frontend/package.json",
    "frontend/pnpm-lock.yaml",
    "frontend/src/pages/skus/SKUImportModal.tsx",
    "frontend/src/pages/skus/SKUListPage.tsx",
    "frontend/src/services/skuImportService.ts",
    "frontend/src/tests/setup.ts",
    "frontend/src/tests/SKUImportModal.test.tsx",
    "frontend/src/tests/SKUListPage.test.tsx",
    "frontend/src/types/import.ts",
    "frontend/vitest.config.ts",
}
cmd = ["git", "-C", "..", "diff", "--name-only", "HEAD^1", "HEAD"]
actual = set(subprocess.check_output(cmd, text=True).splitlines())
missing = sorted(expected - actual)
extra = sorted(actual - expected)
forbidden = sorted(p for p in actual if p.startswith(("backend/", ".github/", "scripts/", "docs/ai/")) or "alembic" in p.lower())
if missing or extra or forbidden:
    print("u3d_scope_contract=fail")
    print("missing=", missing)
    print("extra=", extra)
    print("forbidden=", forbidden)
    sys.exit(1)
print("u3d_scope_contract=pass 11 files 0 skipped 0 failed")
PY`

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
- If `git rev-parse HEAD` is not exactly `fb35d473fa782e93632458b9b7ebbea0254fdaa6`, stop and report `FAIL_VALIDATION`.
- Final Gate must compare this directive's `Target-Commit` against the report `Commit Hash`.
- Do not modify product code.
- Do not modify tests.
- Do not commit from the validation target.
- Do not push product branches.
- Do not write report files from Leo; run_directive.sh writes the report.
- If dependency installation is blocked by network/cache issues, classify as `BLOCKED_ENVIRONMENT`, not PASS.
- If any validation command fails or is skipped, classify as `FAIL_VALIDATION`, not PASS.
- If gateway_timeout or fallbackUsed=true occurs, classify as `FAIL_RUNNER_INFRA_WITH_VALIDATION_COMPLETED`, not PASS.

Acceptance criteria:
- GitHub Actions conclusion must be `success`.
- Report must exist on `reports/lubuntu-validation`.
- Report Commit Hash must equal `fb35d473fa782e93632458b9b7ebbea0254fdaa6`.
- Mode must be `VALIDATION_GATE`.
- Leo Invoked must be `true`.
- COMMANDS_EXECUTED must be `9/9`.
- VALIDATION must be `4/4`.
- App Import Smoke must not be unknown and must not contain fail/blocked.
- Receivables Suite must not be unknown and must not contain failures.
- Phase 5 Payment Regression must not be unknown and must not contain failures.
- Schema Contract must include `u3d_scope_contract=pass` and must have `0 skipped, 0 failed`.
- Product Code Modified must be `no`.
- Product Branch Pushed must be `no`.
- Transport health must be healthy.
