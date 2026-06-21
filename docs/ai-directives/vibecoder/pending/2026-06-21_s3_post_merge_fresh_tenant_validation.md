Directive-ID: s3-post-merge-fresh-tenant-validation-2026-06-21
Mode: VALIDATION_GATE
Priority: HIGH
Created: 2026-06-21
Status: pending
Target branch: product-dev-recovered
Target-Commit: afb1abfa425e04aae1dd681f83656a06887152f6
Validation-Scope: S3 post-merge fresh/prepared tenant runtime smoke validation
Allow-Code-Changes: false
Allow-Product-Push: false
Report branch: reports/lubuntu-validation
Report path: docs/ai-reports/lubuntu/2026-06-21_s3_post_merge_fresh_tenant_validation.md

# S3 Post-Merge Fresh Tenant Runtime Validation

Objective:
Independently validate the exact post-merge product branch commit after S3-A
and S3-B runtime smoke gates were promoted into `product-dev-recovered`.

Important CTO classification:
S3-A is mock-DB auth/runtime smoke. S3-B is prepared live tenant proof, not a
fully self-bootstrapping fresh tenant test. Therefore the runner must not
upgrade this evidence to "fresh tenant fully proven" unless the commands below
actually prove it. If live DB or prepared tenant fixtures are missing, classify
as `BLOCKED_ENVIRONMENT` or `FAIL_VALIDATION`, not PASS.

Required branch/commit checks:
1. `git fetch origin --prune`
2. `git checkout origin/product-dev-recovered --detach`
3. `git rev-parse HEAD`
4. Confirm HEAD equals `afb1abfa425e04aae1dd681f83656a06887152f6`.
5. `git status --short` must be clean before and after validation.

Required validation commands:
1. S3 runtime smoke gates from `backend`, with S3-B live DB hard-fail enabled:
   `REPORTING_USER_PASSWORD="${REPORTING_USER_PASSWORD:-mpango_runner_reporting_password}" S3B_REQUIRE_LIVE_DB=1 poetry run pytest tests/test_s3a_fresh_tenant_runtime_smoke.py tests/test_s3b_fresh_tenant_live_runtime_proof.py -q -rxX --tb=short`
2. S2 route authorization policy harness from `backend`:
   `REPORTING_USER_PASSWORD="${REPORTING_USER_PASSWORD:-mpango_runner_reporting_password}" poetry run pytest tests/test_route_authorization_policy.py -q -rxX --tb=short`
3. Platform API and JWT boundary regression from `backend`:
   `REPORTING_USER_PASSWORD="${REPORTING_USER_PASSWORD:-mpango_runner_reporting_password}" poetry run pytest tests/test_platform_stats_api.py tests/test_platform_audit_api.py tests/security/test_jwt_boundaries.py -q --tb=short`
4. S3 merge scope contract from `backend`:
   `bash -lc 'printf "%s\n" "ai-ledger/product-ai/2026-06-21_s3a_fresh_tenant_runtime_smoke.md" "ai-ledger/product-ai/2026-06-21_s3b_fresh_tenant_live_runtime_proof.md" "backend/tests/test_s3a_fresh_tenant_runtime_smoke.py" "backend/tests/test_s3b_fresh_tenant_live_runtime_proof.py" | sort > /tmp/s3_expected_files.txt; git -C .. diff --name-only HEAD^1 HEAD | sort > /tmp/s3_actual_files.txt; diff -u /tmp/s3_expected_files.txt /tmp/s3_actual_files.txt; echo "s3_scope_contract=pass 4 files 0 skipped 0 failed"'`

Expected evidence:
- COMMANDS_EXECUTED: 9/9
- PREFLIGHT: 5/5
- VALIDATION: 4/4
- App Import Smoke: S3 runtime smoke gates passed, with no failed tests.
- Receivables Suite: route authorization policy harness passed, with no failed tests.
- Phase 5 Payment Regression: platform API and JWT boundary regression passed, with no failed tests.
- Schema Contract: `s3_scope_contract=pass 4 files 0 skipped 0 failed`.
- Schema Skip Reasons: NONE.
- Product Code Modified: no.
- Product Branch Pushed: no.
- Commit Hash: `afb1abfa425e04aae1dd681f83656a06887152f6`.

Hard rules:
- Leo/runner must execute all 5 preflight commands and all 4 validation commands.
- Do not modify product code.
- Do not modify tests.
- Do not commit from the validation target.
- Do not push product branches.
- Do not deploy.
- Do not write report files from Leo; run_directive.sh writes the report.
- If any validation command fails or is skipped, classify as `FAIL_VALIDATION`, not PASS.
- If dependencies, Docker, Poetry, live DB, or prepared tenant credentials block execution, classify as `BLOCKED_ENVIRONMENT`, not PASS.
- If S3-B passes only by skipping live DB, classify as `FAIL_VALIDATION`.

Acceptance criteria:
- GitHub Actions conclusion must be `success`.
- Report must exist on `reports/lubuntu-validation`.
- Report Commit Hash must equal `afb1abfa425e04aae1dd681f83656a06887152f6`.
- Mode must be `VALIDATION_GATE`.
- Leo Invoked must be `true`.
- COMMANDS_EXECUTED must be `9/9`.
- VALIDATION must be `4/4`.
- Product Code Modified must be `no`.
- Product Branch Pushed must be `no`.
- Transport health must be healthy.
