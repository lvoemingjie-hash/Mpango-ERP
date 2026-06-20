Directive-ID: s2-post-merge-route-auth-validation-2026-06-21
Mode: VALIDATION_GATE
Priority: HIGH
Created: 2026-06-21
Status: pending
Target branch: product-dev-recovered
Target-Commit: c425f7da21544b4b555cbcb087b78e83e116e355
Validation-Scope: S2 post-merge route authorization hardening validation after CTO merge into product-dev-recovered
Allow-Code-Changes: false
Allow-Product-Push: false
Report branch: reports/lubuntu-validation
Report path: docs/ai-reports/lubuntu/2026-06-21_s2_post_merge_route_auth_validation.md

# S2 Post-Merge Route Authorization Validation

Objective:
Independently validate the exact post-merge product branch commit after S2
Route Authorization Hardening was promoted into `product-dev-recovered`.

Required branch/commit checks:
1. `git fetch origin --prune`
2. `git checkout origin/product-dev-recovered --detach`
3. `git rev-parse HEAD`
4. Confirm HEAD equals `c425f7da21544b4b555cbcb087b78e83e116e355`.
5. `git status --short` must be clean before and after validation.

Required validation commands:
1. Route authorization policy harness from `backend`:
   `poetry run pytest tests/test_route_authorization_policy.py -q -rxX --tb=short`
2. Platform API and JWT boundary regression from `backend`:
   `poetry run pytest tests/test_platform_stats_api.py tests/test_platform_audit_api.py tests/security/test_jwt_boundaries.py -q --tb=short`
3. Async exports route regression from `backend`:
   `REPORTING_USER_PASSWORD="${REPORTING_USER_PASSWORD:-mpango_runner_reporting_password}" poetry run pytest tests/test_s6_4_async_exports.py -q --tb=short`
4. S2 merge scope contract from `backend`:
   `bash -lc 'git -C .. diff --name-only HEAD^1 HEAD | tee /tmp/s2_scope_files.txt; if grep -v -E "^(ai-ledger/product-ai/2026-06-21_s2.*\\.md|backend/api/dependencies.py|backend/api/v1/exports.py|backend/api/v1/platform\\.py|backend/api/v1/test/profiling_test\\.py|backend/tests/security/test_jwt_boundaries.py|backend/tests/test_platform_audit_api.py|backend/tests/test_platform_stats_api.py|backend/tests/test_route_authorization_policy.py)$" /tmp/s2_scope_files.txt; then exit 1; fi; echo "s2_scope_contract=pass 0 skipped 0 failed"'`

Expected evidence:
- COMMANDS_EXECUTED: 9/9
- PREFLIGHT: 5/5
- VALIDATION: 4/4
- App Import Smoke: route authorization policy harness passed, with no failed tests.
- Receivables Suite: platform API and JWT boundary regression passed, with no failed tests.
- Phase 5 Payment Regression: async exports regression passed, with no failed tests.
- Schema Contract: `s2_scope_contract=pass 0 skipped 0 failed`.
- Schema Skip Reasons: NONE.
- Product Code Modified: no.
- Product Branch Pushed: no.
- Commit Hash: `c425f7da21544b4b555cbcb087b78e83e116e355`.

Hard rules:
- Leo/runner must execute all 5 preflight commands and all 4 validation commands.
- Do not modify product code.
- Do not modify tests.
- Do not commit from the validation target.
- Do not push product branches.
- Do not deploy.
- Do not write report files from Leo; run_directive.sh writes the report.
- If any validation command fails or is skipped, classify as `FAIL_VALIDATION`, not PASS.
- If dependencies, Docker, Poetry, or database credentials block execution, classify as `BLOCKED_ENVIRONMENT`, not PASS.

Acceptance criteria:
- GitHub Actions conclusion must be `success`.
- Report must exist on `reports/lubuntu-validation`.
- Report Commit Hash must equal `c425f7da21544b4b555cbcb087b78e83e116e355`.
- Mode must be `VALIDATION_GATE`.
- Leo Invoked must be `true`.
- COMMANDS_EXECUTED must be `9/9`.
- VALIDATION must be `4/4`.
- Product Code Modified must be `no`.
- Product Branch Pushed must be `no`.
- Transport health must be healthy.
