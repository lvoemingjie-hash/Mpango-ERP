Directive-ID: s4-post-merge-inventory-invariant-validation-2026-06-22
Mode: VALIDATION_GATE
Priority: HIGH
Created: 2026-06-22
Status: pending
Target branch: product-dev-recovered
Target-Commit: 3b1562457d488b2234e00535942b3b41172d1ef2
Validation-Scope: S4 post-merge order fulfillment inventory invariant validation
Allow-Code-Changes: false
Allow-Product-Push: false
Report branch: reports/lubuntu-validation
Report path: docs/ai-reports/lubuntu/2026-06-22_s4_post_merge_inventory_invariant_validation.md

# S4 Post-Merge Inventory Invariant Validation

Objective:
Independently validate the exact post-merge product branch commit after U3C
logging key fix and S4 order fulfillment inventory invariant were promoted into
`product-dev-recovered`.

CTO context:
- U3C fix is a one-line logging reserved-key correction:
  `extra["created"]` -> `extra["created_count"]`.
- S4 must prove paid order fulfillment deducts stock atomically, writes
  movement journal entries, rejects negative stock, rolls back failed
  fulfillment, prevents duplicate deduction, and preserves tenant isolation.
- This is validation only. Do not edit product code, tests, directives, reports,
  or product branches from the validation target.

Required branch/commit checks:
1. `git fetch origin --prune`
2. `git checkout origin/product-dev-recovered --detach`
3. `git rev-parse HEAD`
4. Confirm HEAD equals `3b1562457d488b2234e00535942b3b41172d1ef2`.
5. `git status --short` must be clean before and after validation.

Required validation commands:
1. U3C logging fix plus S4 invariant combined gate from `backend`:
   `POSTGRES_HOST="${POSTGRES_HOST:-127.0.0.1}" REPORTING_USER_PASSWORD="${REPORTING_USER_PASSWORD:-mpango_runner_reporting_password}" poetry run pytest tests/test_u3c_live_db_apply.py tests/business/test_s4_order_fulfillment_inventory_invariants.py -q --tb=short`
2. Full inventory selection gate from `backend`:
   `POSTGRES_HOST="${POSTGRES_HOST:-127.0.0.1}" REPORTING_USER_PASSWORD="${REPORTING_USER_PASSWORD:-mpango_runner_reporting_password}" poetry run pytest tests -q -k "inventory and not frontend" --tb=short`
3. Order state machine and payment regression from `backend`:
   `POSTGRES_HOST="${POSTGRES_HOST:-127.0.0.1}" REPORTING_USER_PASSWORD="${REPORTING_USER_PASSWORD:-mpango_runner_reporting_password}" poetry run pytest tests/test_s5_order_state_machine.py tests/test_phase5_order_payment.py -q --tb=short`
4. S3-C live fresh tenant proof from `backend`, with live DB hard-fail enabled:
   `POSTGRES_HOST="${POSTGRES_HOST:-127.0.0.1}" REPORTING_USER_PASSWORD="${REPORTING_USER_PASSWORD:-mpango_runner_reporting_password}" S3C_REQUIRE_LIVE_DB=1 bash -lc 'if [ -z "${S3C_LIVE_DB_URL:-}" ] && [ -n "${DATABASE_URL:-}" ]; then export S3C_LIVE_DB_URL="${DATABASE_URL/postgresql:\/\//postgresql+asyncpg:\/\/}"; fi; poetry run pytest tests/test_s3c_self_contained_fresh_tenant_live_proof.py -q -rxX --tb=short'`

Expected evidence:
- COMMANDS_EXECUTED: 9/9
- PREFLIGHT: 5/5
- VALIDATION: 4/4
- App Import Smoke: U3C+S4 combined gate passed, with no failed tests.
- Receivables Suite: inventory selection gate passed, with no failed tests.
- Phase 5 Payment Regression: S5/Phase5 regression passed, with no failed tests.
- Schema Contract: S3-C live fresh tenant proof passed, with no failed tests and no live-DB skips.
- Schema Skip Reasons: NONE, except known xfailed test(s) must be explicitly reported as expected xfail, not skipped.
- Product Code Modified: no.
- Product Branch Pushed: no.
- Commit Hash: `3b1562457d488b2234e00535942b3b41172d1ef2`.

Hard rules:
- Leo/runner must execute all 5 preflight commands and all 4 validation commands.
- Do not modify product code.
- Do not modify tests.
- Do not commit from the validation target.
- Do not push product branches.
- Do not deploy.
- Do not write report files from Leo; run_directive.sh writes the report.
- If any validation command fails or is skipped, classify as `FAIL_VALIDATION`, not PASS.
- If dependencies, Docker, Poetry, live DB, or prepared DB credentials block execution, classify as `BLOCKED_ENVIRONMENT`, not PASS.
- If S3-C passes only by skipping live DB, classify as `FAIL_VALIDATION`.

Acceptance criteria:
- GitHub Actions conclusion must be `success`.
- Report must exist on `reports/lubuntu-validation`.
- Report Commit Hash must equal `3b1562457d488b2234e00535942b3b41172d1ef2`.
- Mode must be `VALIDATION_GATE`.
- Leo Invoked must be `true`.
- COMMANDS_EXECUTED must be `9/9`.
- VALIDATION must be `4/4`.
- Product Code Modified must be `no`.
- Product Branch Pushed must be `no`.
- Transport health must be healthy.
