# DC-12R1-MVP-L1-J1-H2-C-I2-E2-B1-R6-R5-R2-V2 — Lubuntu Authoritative Browser Final (Single-Stack, Real-Boundary Pass)

- **Executor:** Lubuntu OpenCode2 (Codex-L supervision)
- **Date:** 2026-09-03
- **Candidate:** `ddba2d3eda847f2c15a0f057b5f7ff2f598f38d0` (detached clean worktree)
- **KILO_FINAL:** `3db164dd7146b27ee7b324c0582649680e341ce2` == remote tip of `origin/zcode/dc12r1-mvp-l1-j1-h2-c-i2-e2-b1-r6-r5-r2-kilo-review-2026-09-03` (verified by fetch + rev-parse at run time)
- **BACKEND_EVIDENCE:** `ef33a8827d4beb6c4eb3ba832c3ba46d440d567a` (3784-node backend authority ZERO-RED bound to candidate base `86f41b93a3aa0e3c55724b75fc2e2aa4c6dee35b`)
- **VERIFICATION_TIER:** V4_INDEPENDENT_LINUX_BROWSER_RUNTIME_AUTHORITY
- **CLAIM_CEILING:** `AUTHORITATIVE_BROWSER_PASS_AND_READY_FOR_CTO_MERGE_REHEARSAL_ONLY`
- **Verdict:** `AUTHORITATIVE_BROWSER_PASS` — FINISHED, sealed, single invocation of every gated surface

---

## 1. Proof gate (git truth, all verified live before launch)

| Gate | Result |
|---|---|
| KILO_FINAL == remote tip | YES — fetched `origin/zcode/…-kilo-review-2026-09-03` = `3db164dd` |
| Candidate lineage | YES — `ddba2d3e` is the single-source commit reviewed by KILO_FINAL (parent = `6e96434f` per Kilo review.md) |
| Detached clean worktree from candidate | YES — `/home/ivy/Desktop/dc12r1-b1r6-run`, HEAD `ddba2d3e`, `git status --porcelain` = empty pre-run AND post-run (tracked drift 0) |
| product/backend/frontend/tests/migrations byte-identity vs `86f41b93` | YES — `git rev-parse 86f41b93:backend` == `ddba2d3e:backend` (`b2fc919b…`), `:frontend` == (`4526d782…`), `:Mpango` == (`e69de29b…`); full `git diff --stat` between the two commits over these paths is EMPTY (tests and migrations live under `backend/`) |
| Backend 3784 zero-red | REUSED by byte identity — NOT re-run |
| Actual candidate delta | 5M + 1A (`README.md`, `tools/browser-authority-runner.mjs`, `tools/check-browser-authority-contracts.mjs`, `tools/host-preflight.mjs`, `tools/validate-static.mjs` modified; `ai-ledger/product-ai/…_host_preflight_runtime_truth.md` added) — matches the Kilo-reviewed delta |
| `browser-authority-preflight-helper.mjs` | Authorized (committed) and NOT modified — helper bytes == HEAD blob at every runner checkpoint |

## 2. Invocation discipline (LIMITS honored)

| Mandated counter | Value |
|---|---|
| PREFLIGHT_INVOCATION_COUNT | **1** (runner evidence: `preflight_invocations: 1`) |
| PLAYWRIGHT_INVOCATION_COUNT | **1** (create-exclusive marker `authority-invocation.json`: `playwright_invocation_count: 1`; runner evidence: `child_playwright_invocation_count: 1`) |
| STACK_LIMIT / RERUN / BACKUP_STACK | 1 / 0 / 0 — one task-dedicated stack; no rerun, no swap, no second launch |
| Direct-process entrypoint calls | **1** (single `node tools/browser-authority-entrypoint.mjs --contract … --ledger …`, started directly, cwd = worktree root) |

## 3. Runtime contract (real stack, real processes)

| Contract | Executed truth |
|---|---|
| Task-dedicated PG16 + Redis7 | `docker`: `dc12r1_b1r6_pg16` (postgres:16-alpine, **PostgreSQL 16.15**, 127.0.0.1:25432), `dc12r1_b1r6_redis7` (redis:7-alpine, 127.0.0.1:26380); no other stack touched |
| Browser role least privilege | role `j1h2c_browser`: `rolcanlogin=t`, `rolsuper=f`, `rolcreaterole=f`, `rolcreatedb=f`, `rolreplication=f` (queried live; the runner's host gate re-proved it via psql) |
| Alembic single head/current | `alembic heads` → `037_payment_declarations_schema`; `alembic current` → `037_payment_declarations_schema` (full-token equality, exactly one of each; re-proven inside the host gate from `J1H2C_HOST_BACKEND_DIR`) |
| Redis PING / SELECT 15 / DBSIZE=0 | Real socket conversation inside the host gate: `+PONG` / `+OK` / `:0`; DB15 was flushed and remained 0 through the run (backend uses the product-default DB index, so the task-DB proof stays true) |
| Sentinel 26379 unreachable | Connection to 127.0.0.1:26379 refused before run (host-gate `sentinelVerdict(false)` → `check_green`) |
| PID file / live process / ownership token | `backend.pid` = PID of the uvicorn process serving 127.0.0.1:18200; `ps -p PID -ww -o args=` carried the `J1H2C_HOST_SERVICE_TOKEN` (all three agreed at host-gate time) |
| `J1H2C_HOST_PG*` explicit binding | The module mapped the descriptors to `-h 127.0.0.1 -p 25432 -d mpango_authority -U j1h2c_browser`; ambient `PG*` variables stripped (any case) except task `PGPASSWORD` |
| psql via `-f -` + stdin | Host-gate probes issued the SQL on the child's stdin through `psql … -f -` (no `-c`); values traveled only as `-v name=value` argv elements |
| CORS Origin == Allow-Origin exactly | Runner-owned process-isolated probe: `OPTIONS /client/auth/forgot-password` with Origin → **200** + `access-control-allow-origin: <exact Origin>` (verified manually pre-run and by the runner's `cors_probe_passed=true`) |
| Maildir empty, mode 700 | Created `drwx------`, zero entries at preflight; afterwards received exactly the journey's real deliveries (see §6) |

## 4. Provisioning (formal product lifecycles only — no DB forging)

- **W1 and W2** were onboarded through the product's own public onboarding API: `POST /api/v1/auth/signup` → emailed verification link → `POST /api/v1/auth/verify-email` (in-product tenant provisioning + schema bootstrap) → emailed owner setup link → `POST /api/v1/auth/onboarding/setup-credential` → identity login → `POST /api/v1/auth/select-tenant`. Canonical codes are the REAL product-issued registry codes (distinct, uppercase, `[A-Z0-9]+`).
- **Invitations** were created through the formal `POST /api/v1/invitations` endpoint (`InvitationService`, W1 owner JWT, `invitations:create`): two fresh pairs, verified + unverified phones, both `status=active`, `used_at IS NULL` at gate time (host-gate psql probe proved both pairs available).
- **Retailer owner identity** (`J1H2C_RETAILER_EMAIL`) was never registered pre-run: the preflight helper proved `owner_identity_fresh_unregistered` with an **exact 401** from the formal login; the harness `beforeAll` remained the SOLE register → setup-credential → login lifecycle.
- Emails (verification, owner setup, retailer setup, resets) traveled the REAL production transport: backend `MPANGO_ENV=production` + `EMAIL_PROVIDER=smtp` → task SMTP sink → task maildir JSON deliveries. `PUBLIC_FRONTEND_URL` was the HTTPS SPA origin (product-mandated absolute links); the frontend was served as the real built SPA on both task origins (HTTP origin for the journey, HTTPS origin carrying the absolute email links); the local CA was installed into the Chromium NSS trust store (`~/.pki/nssdb`).

## 5. Required pass accounting

| Mandated | Achieved |
|---|---|
| 15_BROWSER_PASS | 15/15 (HC01–HC10, HC12–HC16) — `reconciliation.json` nodes all PASS |
| 2_STATIC_PASS | 2/2 (HC11, HC17 — runtime static class, never counted as browser) |
| FAIL / NOT_RUN / PENDING | 0 / 0 / 0 |
| GAP | 0 (`summary.gap=0`, `incomplete=[]`, outcomes pass=17) |
| PRECONDITION_PASS | `preconditionOutcome: "PRECONDITION_PASS"` |
| SCANNER_FINDINGS | 0 (`ARTIFACT SCAN PASSED` required by the child before `complete=true`) |
| CANDIDATE_TREE_DRIFT | 0 (tracked `git status --porcelain` empty post-run) |
| Playwright stats | `results.json` expected=15 unexpected=0 skipped=0 flaky=0 interrupted=0; junit `tests="15" failures="0" skipped="0" errors="0"`, no `<failure>`/`<error>` |
| Entrypoint outcome | `FINISHED`, rc=0, `reconciliation_complete=true`, `ledger_sealed=true`, `candidate_sha=ddba2d3e…` cross-bound at authorize/launch/post-run |

## 6. Newly executed code paths (this run exercised them for real)

1. **psql stdin / descriptor binding** (`host-preflight.mjs` `buildPsqlInvocation` → `psqlTransport`): every host-gate SQL statement reached psql preprocessing via stdin (`-f -`), the connection target was bound exclusively from `J1H2C_HOST_PG*` (`-h/-p/-d/-U`), ambient `PG*` env was stripped case-insensitively with only the task `PGPASSWORD` preserved, and invitation/role values traveled solely as `-v` variables (`:'name'` placeholders resolved by the preprocessor). Runtime role probe returned `t|f|f|f|f`; both invitation probes returned count 1.
2. **Alembic underscore revision verdict** (`alembicRevisionsVerdict`): `alembic heads` / `alembic current` executed against the task DB returned the real underscored ID `037_payment_declarations_schema` — exactly one head, exactly one current, full whole-token equality (the hex-only/prefix-match refusals were not triggered because the real stack is healthy).
3. **Redis SELECT 15 / DBSIZE** (`redisConversation`): one real socket conversation `PING → +PONG`, `SELECT 15 → +OK`, `DBSIZE → :0` proved the task DB 15 EMPTY inside the gate.
4. **Sentinel unreachable** (`sentinelProbe` + `sentinelVerdict`): 26379 on the Redis host refused the connection → proven UNREACHABLE → `check_green` (a running sentinel would have RED'd `sentinel_reachable`).
5. **Complete RED-category persistence**: the ledger path executed end-to-end — the `host_preflight` record was persisted with its full `red_categories` array (empty under GREEN, labels-only by construction) and the `preflight` record persisted `red_categories` (0 categories); the same sink is the path that persists every fixed category under any RED, with the plane VOIDed before authorize at spawn=0.

## 7. Reconciliation and result classification

- `FULL_SUITE_RESULT=REUSED_BY_BYTE_IDENTITY_NOT_RERUN` (3784 zero-red backend evidence bound to the byte-identical product tree)
- `CHANGED_OR_ADDED_TESTS=NONE_RUNTIME_ONLY` (candidate delta touched harness authority tooling only; no product tests changed or added)
- Run duration ≈ 17 s wall clock (loopback stack, no artificial waits); child wrapper pid 355844 rc=0, Playwright pid 355852 rc=0, both cross-bound in the sealed evidence.

## 8. Publication integrity

- Published from a detached worktree at the candidate; branch = `reports/dc12r1-mvp-l1-j1-h2-c-i2-e2-b1-r6-r5-r2-v2-lubuntu-authoritative-browser-final-2026-09-03`; pushed to `origin` and re-fetched: **local == remote**.
- Disinfection manifest (0 / 0 / 0): (a) sensitive-value scan over every published evidence file — **0 hits** (all 15 materialized values + task secrets, incl. emails, passwords, invitation codes, canonical codes, URLs); (b) URL/host/domain scan — **0 hits**; (c) secret-scanner over the published diff — **0 findings**; tracked-tree drift 0.
- Evidence files (all value-free by construction): `evidence/entrypoint-result.json` (runner-sealed authority evidence), `evidence/ledger.jsonl` (hash-chained, terminal_seal), `evidence/reconciliation.json`, `evidence/reconciliation.csv`, `evidence/results.json`, `evidence/results-junit.xml`, `evidence/authority-invocation.json`, `evidence/maildir-snapshot.json` (identity labels + filenames only).
- Resource cleanup after evidence capture: task containers removed, task processes stopped, no residual listeners on the task ports.

## 9. Scope boundary

This pass proves the authoritative browser journey against the real product on a real dedicated stack. It does NOT merge, deploy, or modify the candidate. **STOP** per directive — the branch is ready for CTO merge rehearsal only.
