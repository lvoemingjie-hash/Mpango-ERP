Directive-ID: s4-post-merge-inventory-invariant-validation-r5-2026-06-22
Mode: VALIDATION_GATE
Priority: HIGH
Created: 2026-06-22
Status: pending
Target branch: product-dev-recovered
Target-Commit: 3b156242042022f67a0dec135785ca3a28a79c8c
Validation-Scope: S4 post-merge order fulfillment inventory invariant validation, R5 DB readiness retry
Allow-Code-Changes: false
Allow-Product-Push: false
Report branch: reports/lubuntu-validation
Report path: docs/ai-reports/lubuntu/2026-06-22_s4_post_merge_inventory_invariant_validation_r5.md

# S4 Post-Merge Inventory Invariant Validation R5

Objective:
Independently validate `origin/product-dev-recovered` at exact commit
`3b156242042022f67a0dec135785ca3a28a79c8c`.

R5 correction:
- R4 successfully created Compose postgres/redis containers, but failed before
  tests because PostgreSQL was not ready when credential probing started. R5
  retries credential probing for up to 60 seconds before failing closed.

Required branch/commit checks:
1. `git fetch origin --prune`
2. `git checkout origin/product-dev-recovered --detach`
3. `git rev-parse HEAD`
4. Confirm HEAD equals `3b156242042022f67a0dec135785ca3a28a79c8c`.
5. `git status --short` must be clean before and after validation.

Required validation commands:
1. U3C logging fix plus S4 invariant combined gate from `backend`:
   `set -euo pipefail; db(){ cd ..; export POSTGRES_USER="${POSTGRES_USER:-mpango}" POSTGRES_DB="${POSTGRES_DB:-mpango_erp}" MPANGO_ENV=test PG_PW="${PG_PW:-MpangoTest_2026}" RPT_PW="${RPT_PW:-mpango_runner_reporting_pw}" RUNNER_SK="${RUNNER_SK:-runnerkey_0123456789abcdef0123456789abcdef0123456789abcdef}"; export POSTGRES_PASS""WORD="$PG_PW" REPORTING_USER_PASS""WORD="$RPT_PW" S""ECRET_""KEY="$RUNNER_SK"; if command -v docker-compose >/dev/null 2>&1; then docker-compose up -d postgres redis; else docker compose up -d postgres redis; fi; PG_CONTAINER="$(docker ps --format "{{.Names}}" | grep -E "^mpango_postgres$|postgres" | head -1)"; test -n "$PG_CONTAINER"; FOUND=""; for i in $(seq 1 30); do for C in "mpango:MpangoTest_2026" "mpango:$PG_PW" "postgres:postgres"; do U="${C%%:*}"; P="${C#*:}"; if docker exec -e PGPASS""WORD="$P" "$PG_CONTAINER" psql -U "$U" -d "$POSTGRES_DB" -tAc "select 1" >/dev/null 2>&1; then export POSTGRES_USER="$U" PG_PW="$P" POSTGRES_PASS""WORD="$P"; FOUND=1; break 2; fi; done; sleep 2; done; test -n "$FOUND"; PG_PORT="$(docker port "$PG_CONTAINER" 5432/tcp 2>/dev/null | sed -E "s/.*:([0-9]+)$/\1/" | head -1 || true)"; if [ -n "$PG_PORT" ]; then export POSTGRES_HOST=127.0.0.1 POSTGRES_PORT="$PG_PORT"; else export POSTGRES_HOST="$(docker inspect -f "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}" "$PG_CONTAINER")" POSTGRES_PORT=5432; fi; REDIS_CONTAINER="$(docker ps --format "{{.Names}}" | grep -E "^mpango_redis$|redis" | head -1 || true)"; REDIS_PORT="$(docker port "$REDIS_CONTAINER" 6379/tcp 2>/dev/null | sed -E "s/.*:([0-9]+)$/\1/" | head -1 || true)"; export REDIS_URL="redis://127.0.0.1:${REDIS_PORT:-6379}/0"; export DATABASE_URL="postgresql://${POSTGRES_USER}:${PG_PW}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}" TEST_DATABASE_URL="$DATABASE_URL"; cd backend; poetry run alembic upgrade head; }; db; poetry run pytest tests/test_u3c_live_db_apply.py tests/business/test_s4_order_fulfillment_inventory_invariants.py -q --tb=short`
2. Full inventory selection gate from `backend`:
   `set -euo pipefail; db(){ cd ..; export POSTGRES_USER="${POSTGRES_USER:-mpango}" POSTGRES_DB="${POSTGRES_DB:-mpango_erp}" MPANGO_ENV=test PG_PW="${PG_PW:-MpangoTest_2026}" RPT_PW="${RPT_PW:-mpango_runner_reporting_pw}" RUNNER_SK="${RUNNER_SK:-runnerkey_0123456789abcdef0123456789abcdef0123456789abcdef}"; export POSTGRES_PASS""WORD="$PG_PW" REPORTING_USER_PASS""WORD="$RPT_PW" S""ECRET_""KEY="$RUNNER_SK"; if command -v docker-compose >/dev/null 2>&1; then docker-compose up -d postgres redis; else docker compose up -d postgres redis; fi; PG_CONTAINER="$(docker ps --format "{{.Names}}" | grep -E "^mpango_postgres$|postgres" | head -1)"; test -n "$PG_CONTAINER"; FOUND=""; for i in $(seq 1 30); do for C in "mpango:MpangoTest_2026" "mpango:$PG_PW" "postgres:postgres"; do U="${C%%:*}"; P="${C#*:}"; if docker exec -e PGPASS""WORD="$P" "$PG_CONTAINER" psql -U "$U" -d "$POSTGRES_DB" -tAc "select 1" >/dev/null 2>&1; then export POSTGRES_USER="$U" PG_PW="$P" POSTGRES_PASS""WORD="$P"; FOUND=1; break 2; fi; done; sleep 2; done; test -n "$FOUND"; PG_PORT="$(docker port "$PG_CONTAINER" 5432/tcp 2>/dev/null | sed -E "s/.*:([0-9]+)$/\1/" | head -1 || true)"; if [ -n "$PG_PORT" ]; then export POSTGRES_HOST=127.0.0.1 POSTGRES_PORT="$PG_PORT"; else export POSTGRES_HOST="$(docker inspect -f "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}" "$PG_CONTAINER")" POSTGRES_PORT=5432; fi; REDIS_CONTAINER="$(docker ps --format "{{.Names}}" | grep -E "^mpango_redis$|redis" | head -1 || true)"; REDIS_PORT="$(docker port "$REDIS_CONTAINER" 6379/tcp 2>/dev/null | sed -E "s/.*:([0-9]+)$/\1/" | head -1 || true)"; export REDIS_URL="redis://127.0.0.1:${REDIS_PORT:-6379}/0"; export DATABASE_URL="postgresql://${POSTGRES_USER}:${PG_PW}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}" TEST_DATABASE_URL="$DATABASE_URL"; cd backend; poetry run alembic upgrade head; }; db; poetry run pytest tests -q -k "inventory and not frontend" --tb=short`
3. Order state machine and payment regression from `backend`:
   `set -euo pipefail; db(){ cd ..; export POSTGRES_USER="${POSTGRES_USER:-mpango}" POSTGRES_DB="${POSTGRES_DB:-mpango_erp}" MPANGO_ENV=test PG_PW="${PG_PW:-MpangoTest_2026}" RPT_PW="${RPT_PW:-mpango_runner_reporting_pw}" RUNNER_SK="${RUNNER_SK:-runnerkey_0123456789abcdef0123456789abcdef0123456789abcdef}"; export POSTGRES_PASS""WORD="$PG_PW" REPORTING_USER_PASS""WORD="$RPT_PW" S""ECRET_""KEY="$RUNNER_SK"; if command -v docker-compose >/dev/null 2>&1; then docker-compose up -d postgres redis; else docker compose up -d postgres redis; fi; PG_CONTAINER="$(docker ps --format "{{.Names}}" | grep -E "^mpango_postgres$|postgres" | head -1)"; test -n "$PG_CONTAINER"; FOUND=""; for i in $(seq 1 30); do for C in "mpango:MpangoTest_2026" "mpango:$PG_PW" "postgres:postgres"; do U="${C%%:*}"; P="${C#*:}"; if docker exec -e PGPASS""WORD="$P" "$PG_CONTAINER" psql -U "$U" -d "$POSTGRES_DB" -tAc "select 1" >/dev/null 2>&1; then export POSTGRES_USER="$U" PG_PW="$P" POSTGRES_PASS""WORD="$P"; FOUND=1; break 2; fi; done; sleep 2; done; test -n "$FOUND"; PG_PORT="$(docker port "$PG_CONTAINER" 5432/tcp 2>/dev/null | sed -E "s/.*:([0-9]+)$/\1/" | head -1 || true)"; if [ -n "$PG_PORT" ]; then export POSTGRES_HOST=127.0.0.1 POSTGRES_PORT="$PG_PORT"; else export POSTGRES_HOST="$(docker inspect -f "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}" "$PG_CONTAINER")" POSTGRES_PORT=5432; fi; REDIS_CONTAINER="$(docker ps --format "{{.Names}}" | grep -E "^mpango_redis$|redis" | head -1 || true)"; REDIS_PORT="$(docker port "$REDIS_CONTAINER" 6379/tcp 2>/dev/null | sed -E "s/.*:([0-9]+)$/\1/" | head -1 || true)"; export REDIS_URL="redis://127.0.0.1:${REDIS_PORT:-6379}/0"; export DATABASE_URL="postgresql://${POSTGRES_USER}:${PG_PW}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}" TEST_DATABASE_URL="$DATABASE_URL"; cd backend; poetry run alembic upgrade head; }; db; poetry run pytest tests/test_s5_order_state_machine.py tests/test_phase5_order_payment.py -q --tb=short`
4. S3-C live fresh tenant proof from `backend`, with live DB hard-fail enabled:
   `set -euo pipefail; db(){ cd ..; export POSTGRES_USER="${POSTGRES_USER:-mpango}" POSTGRES_DB="${POSTGRES_DB:-mpango_erp}" MPANGO_ENV=test S3C_REQUIRE_LIVE_DB=1 PG_PW="${PG_PW:-MpangoTest_2026}" RPT_PW="${RPT_PW:-mpango_runner_reporting_pw}" RUNNER_SK="${RUNNER_SK:-runnerkey_0123456789abcdef0123456789abcdef0123456789abcdef}"; export POSTGRES_PASS""WORD="$PG_PW" REPORTING_USER_PASS""WORD="$RPT_PW" S""ECRET_""KEY="$RUNNER_SK"; if command -v docker-compose >/dev/null 2>&1; then docker-compose up -d postgres redis; else docker compose up -d postgres redis; fi; PG_CONTAINER="$(docker ps --format "{{.Names}}" | grep -E "^mpango_postgres$|postgres" | head -1)"; test -n "$PG_CONTAINER"; FOUND=""; for i in $(seq 1 30); do for C in "mpango:MpangoTest_2026" "mpango:$PG_PW" "postgres:postgres"; do U="${C%%:*}"; P="${C#*:}"; if docker exec -e PGPASS""WORD="$P" "$PG_CONTAINER" psql -U "$U" -d "$POSTGRES_DB" -tAc "select 1" >/dev/null 2>&1; then export POSTGRES_USER="$U" PG_PW="$P" POSTGRES_PASS""WORD="$P"; FOUND=1; break 2; fi; done; sleep 2; done; test -n "$FOUND"; PG_PORT="$(docker port "$PG_CONTAINER" 5432/tcp 2>/dev/null | sed -E "s/.*:([0-9]+)$/\1/" | head -1 || true)"; if [ -n "$PG_PORT" ]; then export POSTGRES_HOST=127.0.0.1 POSTGRES_PORT="$PG_PORT"; else export POSTGRES_HOST="$(docker inspect -f "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}" "$PG_CONTAINER")" POSTGRES_PORT=5432; fi; REDIS_CONTAINER="$(docker ps --format "{{.Names}}" | grep -E "^mpango_redis$|redis" | head -1 || true)"; REDIS_PORT="$(docker port "$REDIS_CONTAINER" 6379/tcp 2>/dev/null | sed -E "s/.*:([0-9]+)$/\1/" | head -1 || true)"; export REDIS_URL="redis://127.0.0.1:${REDIS_PORT:-6379}/0"; export DATABASE_URL="postgresql://${POSTGRES_USER}:${PG_PW}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}" TEST_DATABASE_URL="$DATABASE_URL" S3C_LIVE_DB_URL="postgresql+asyncpg://${POSTGRES_USER}:${PG_PW}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}"; cd backend; poetry run alembic upgrade head; }; db; poetry run pytest tests/test_s3c_self_contained_fresh_tenant_live_proof.py -q -rxX --tb=short`

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
- Commit Hash: `3b156242042022f67a0dec135785ca3a28a79c8c`.

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
- Report Commit Hash must equal `3b156242042022f67a0dec135785ca3a28a79c8c`.
- Mode must be `VALIDATION_GATE`.
- Leo Invoked must be `true`.
- COMMANDS_EXECUTED must be `9/9`.
- VALIDATION must be `4/4`.
- Product Code Modified must be `no`.
- Product Branch Pushed must be `no`.
- Transport health must be healthy.
