# REPORT.md — DC-12R1-MVP-L1-J1-H2-C-I2-E2-V2
## Lubuntu Independent Fresh-Runtime Backend and Browser Final (V4_RELEASE_CROSS_HOST_INDEPENDENT_BACKEND_AND_BROWSER)

**VERDICT: `NOT_PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_C_I2_E2_V2_LUBUNTU_INDEPENDENT_BACKEND_AND_BROWSER_FINAL`.**

**Backend component: achieved — `INDEPENDENT_BACKEND_FULL_SUITE_ZERO_RED` (single
authority launch, `3784 = 3721 passed + 48 skipped + 15 xfailed`,
`failed=0 / errors=0 / xpassed=0 / gap=0`).**

**Browser component: `NOT_RUN` — `BLOCKED_BY_HARNESS_RUNTIME_DEFECT` (§6).**
The frozen `j1h2c-retailer-recovery` harness cannot execute ANY node in ANY
environment without modifying harness bytes, which this directive prohibits.
Per fail-closed discipline the browser phase is recorded NOT_RUN, the full
round claim ceiling is NOT met, and **H2-C does NOT enter controlled
merge-drill eligibility from this round.** Next gate: a CTO-authorized
harness-fix round for the single-line type-import defect (§6.3).

- Date: 2026-08-30 (+08:00); executor: Lubuntu OpenCode (independent)
- VERIFICATION_TIER: `V4_RELEASE_CROSS_HOST_INDEPENDENT_BACKEND_AND_BROWSER`
- CLAIM_CEILING (directive): `INDEPENDENT_BACKEND_FULL_SUITE_AND_H2C_17_NODE_BROWSER_FINAL_ONLY`
- No merge, no deploy, no PRICING/SKU start. **STOP.**

## 1. Proof Gate (candidate identity — PASS)

| Item | Expected | Observed |
|---|---|---|
| Candidate | `86f41b93a3aa0e3c55724b75fc2e2aa4c6dee35b` | `origin/zcode/dc12r1-mvp-l1-j1-h2-c-i2-current-baseline-reintegration-2026-08-30` == candidate |
| Parents | `24a28d76…` + second parent | `24a28d76d6d9483d8101f8e0f537c148dc262859` + `e2274af7816b80d0efb83a8294b2c6503e246b19` |
| Tree/scope | 49 delta paths vs baseline | `git diff --name-only 24a28d76..86f41b93` = exactly **49** |
| KILO_FINAL | `1b84cfe0662a3fca11ee6b9aefbf3e9ec0b2a199` | parent == candidate; increment exactly `review.md`, `findings.csv` |
| E2_PUBLICATION | `df40a202aa859f0f7faf95323dd47ca58ca13582` | reachable, frozen on `origin/reports/…e1-immutable-candidate-publication-2026-08-30` |
| PROTECTED_BASELINE | `24a28d76d6d9483d8101f8e0f537c148dc262859` | still == `origin/product-dev-recovered` at close (re-verified §8) |
| Detached worktree | clean, no drift | `/home/ivy/Desktop/dc12r1-e2-v2-lubuntu-fresh-runtime` @ candidate; zero tracked-file modifications throughout |

## 2. Independent precheck stack (task-exclusive, then destroyed)

Stack `dc12r1e2v2-*` (docker network + containers, random credentials,
task-exclusive ports): PG16 `postgres:16-alpine` @127.0.0.1:18545, Redis7
`redis:7-alpine` @127.0.0.1:16381, sentinel 127.0.0.1:26379 **unreachable**
(nothing listening; connection-refused probe), task-private maildir.

| Proof | Result |
|---|---|
| Runner role `dc12r1e2v2run` (live `pg_roles`) | `rolsuper=f`, `rolcreatedb=t`, `rolcreaterole=t`, `rolreplication=f`, `rolinherit=f` (E1 precedent: CREATEROLE required by migration `011_s6_p_reporting_role`) |
| Canonical `backend/` CWD + `MPANGO_ENV=test` + DB name `test_dc12r1e2v2_backend` + port allowlist `MPANGO_TEMP_DB_ALLOWED_PORTS=18545` | enforced by the shared backend-env authority inside the runner (machine contract) |
| Alembic | `upgrade head` rc=0 as the run role; single head exactly `037_payment_declarations_schema` (profile `AUTHORITY_H2C_BACKEND` bound) |
| Redis | `PING=PONG` (7.4.11); DB15 `DBSIZE=0` before/after |
| Sentinel 26379 | unreachable before, during, after |
| `MPANGO_ALLOW_TEMP_DB_CREATE=1` | set; runner temp-DB capability probe passed; no leftover temp DBs |
| Env evidence | variable names and presence/labels only; no values published |
| Runner preflight (`--preflight-only`, `--baseline-sha e2274af7…`) | **PASS, `state=PREFLIGHT`, rc=0** (`evidence/runner-phase2/authority-preflight.json`) |
| Runner + child recheck (`--collect-only`) | **PASS, count=9/9** frozen ET1 manifest nodes; child `pytest_sessionstart` re-verified role/URL/candidate/profile/nonce cross-process (`evidence/runner-phase2/et1-*-proof.json`) |

## 3. Small compatibility gate (on the precheck stack — ALL GREEN, then stack destroyed)

Focused-49 bundle = `test_dc12r1_j1_h2b_forgot_password_runtime_closure` +
`test_dc12r1_s1_r1_corrections` + `test_dc12r1_s1_r2_strict_mapping` +
`test_dc12r1_s1_retailer_identity` + `test_dc12r1_j1_h2c_retailer_recovery_discovery`
(collect = exactly 49). Focused-59 bundle = the four H2-C frontend test files
(vitest).

| Gate | Result | Evidence |
|---|---|---|
| Backend 49 natural order | **49/49 GREEN** rc=0 | `evidence/phase3/backend-focused49-natural.{log,xml}` |
| Backend 49 reverse order (reversed node-id list) | **49/49 GREEN** rc=0 | `evidence/phase3/backend-focused49-reverse.{log,xml}` |
| Frontend 59 natural order | **59/59 GREEN** rc=0 | `evidence/phase3/frontend-focused59-natural.{log,xml}` |
| Frontend 59 reverse file order | **59/59 GREEN** rc=0 | `evidence/phase3/frontend-focused59-reverse.{log,xml}` |
| Production build (`pnpm run build`) | **GREEN** rc=0 (12.12s) | `evidence/phase3/frontend-build.log` |

Stack `dc12r1e2v2-*` then destroyed (containers+network+volumes removed,
credentials shredded). The authoritative stack below was created全新 and the
contaminated database was never reused.

## 4. Authoritative backend full suite (fresh stack `dc12r1e2v2a-*` — ZERO RED)

Fresh PG16/Redis7, fresh DB, `upgrade head` rc=0 → `037_payment_declarations_schema`,
DB15 `DBSIZE=0`, sentinel unreachable, role proofs re-taken.

### 4.1 Canonical collect-only node list — frozen BEFORE launch

Full-suite collect (`-o addopts="" --collect-only -q tests`): **3784 nodes,
0 duplicates**, rc=0. Frozen to `evidence/backend-node-manifest-3784.txt`
(SHA-256 `c02607c87a1763020bdb0755d919e4b290dba5f494c4356417b10442e6127f35`).

Launcher-side node-set gate immediately before launch (fresh collect vs frozen
manifest): **count 3784 == 3784; normalized set equality `missing=0 / extra=0`**
(`evidence/phase4/node-set-diff.txt`). Disclosure: exactly **8 line-pairs**
(4 parametrized tests × 2 runs) differ byte-wise because their IDs embed
per-run random values (random UUIDs / temp-xlsx zip bytes):
`test_u4d_intake_parser_preview.py::test_parser_rejects_csv_and_xlsx_{cell_length,column_limit,header_length}[…]`
and
`test_u6i3_owner_credential_setup_consume.py::test_invalid_or_missing_raw_token_fails_neutrally[u6i3-<label>-<random>]`.
Normalization maps only these to their stable prefixes; all other 3780−8 IDs
are byte-identical. Count match is exact and un-normalized.

### 4.2 VOID launch attempt #1 (infrastructure — NOT a product red, NOT the authority launch)

First runner invocation passed preflight but the COLLECT child failed to
**spawn**: `OSError: [Errno 7] Argument list too long` — the runner's
`ET1_RUNNER_REQUIRED_NODES` env string for a 3784-node manifest is 456,343
bytes, exceeding the Linux kernel per-string `MAX_ARG_STRLEN` (131,072 B);
the frozen harness carries the expected node list only via environment. The
authority command was **never launched** (`sentinel_calls=0`; failure in
`collect_proven` before AUTHORIZED/RUNNING). Classification: launcher/
infrastructure `VOID` — zero product-test executions. Evidence:
`evidence/phase4/VOID-attempt1-e2big-collect-spawn-stdout.log`.

Resolution WITHOUT harness modification: the runner ran with its
profile-frozen ET1 manifest (the exact E1-established mode: E1 recorded
`--collect-only PASS count=9/9`), while the full 3784-node freeze +
fail-closed set gate is enforced launcher-side (§4.1) immediately before the
launch. No shard, no retry, no grep-greening: the product suite itself runs
exactly once, whole.

### 4.3 The single authority launch

`AUTHORITY_H2C_BACKEND`, `--baseline-sha e2274af7…`, authority command
`venv-python -m pytest --junitxml=…/backend-full-junit.xml tests` from the
canonical `backend/` CWD. One invocation. Zero reruns.

| Item | Expected | Observed |
|---|---|---|
| State trace | INIT→…→FINISHED | `INIT->PREFLIGHT, PREFLIGHT->COLLECT_PROVEN, COLLECT_PROVEN->AUTHORIZED, AUTHORIZED->RUNNING, RUNNING->FINISHED` |
| Sentinel / collect spawns | 1 / 1 | `RUN_VERDICT=AUTHORITY_EXECUTED_GREEN sentinel_calls=1 collect_child_spawns=1` |
| Full axis | `3784 = 3721 passed + 48 skipped + 15 xfailed` | **exact** (`3721 passed, 48 skipped, 15 xfailed` in 1895.93s) |
| JUnit | `failed=0 / errors=0` | `tests=3784 failures=0 errors=0 skipped=63` (48 skipped + 15 xfailed) |
| xpassed / gap | 0 / 0 | **0 / 0** |

Evidence: `evidence/phase4/backend-full-stdout.log`, `evidence/phase4/backend-full-junit.xml`,
`evidence/runner-phase4/{authority-preflight.json,authority-trace.json,et1-collect-proof.json,et1-sessionstart-proof.json}`.

## 5. Backend stack destroyed

After the GREEN full suite: containers `dc12r1e2v2a-pg16`, `dc12r1e2v2a-redis7`
removed, network removed, dangling volumes from today removed, credentials
shredded (`dc12r1e2v2a` stack never reused by the browser phase).

## 6. Authoritative browser journey — **NOT_RUN (BLOCKED_BY_HARNESS_RUNTIME_DEFECT)**

### 6.1 Fresh browser-exclusive runtime (built, proven, then destroyed)

Fresh stack `dc12r1e2v2b-*`: PG16 @18545 (role proofs identical to §2),
`upgrade head` rc=0 → `037_payment_declarations_schema`, Redis7 @16381 DB15
`DBSIZE=0`; task-private maildir; launcher-side SMTP sink (:18025) and an
in-process maildir bridge that reads the product's designated non-production
email channel (`services.email_delivery` public getters — the same functions
the product's own pytest suite consumes) and dumps each new delivery into the
maildir as `<email>/*.json` `{"link": …}` — the exact harness maildir format
(product behavior untouched; bridge is launcher infrastructure, reads only).
Real backend on 127.0.0.1:8000 (`MPANGO_ENV=test`, Vite proxy verified),
Vite dev server pinned 127.0.0.1:5173 (`/retail/login` HTTP 200).

Launcher pre-gate: W1 `W1E2V2BROWSER` / W2 `W2E2V2BROWSER` wholesalers
provisioned through the product's public/registry lifecycle with tenant
schemas + admin users; **two fresh, unconsumed W1 invitations created through
the product's official `InvitationService`** (the exact service the
wholesaler API endpoint invokes; the test-env mock auth strategy carries no
`invitations:create` permission, so the API path is unavailable to the
launcher in `MPANGO_ENV=test` — disclosure, no product change). All 13
`J1H2C_*` inputs generated task-privately; harness `pnpm install
--frozen-lockfile` + Chromium installed; bridge end-to-end smoke test
delivered a correct maildir file; smoke mailboxes removed before the run.

### 6.2 The defect (first execution of this frozen harness)

`pnpm exec playwright test --list` (env-free, non-authoritative):

```
SyntaxError: The requested module './neutrality-core.js' does not provide an
export named 'CanonicalFingerprint'
Error: No tests found / Total: 0 tests in 0 files   (rc=1)
```

Root cause: `j1h2c-retailer-recovery/src/neutrality.ts:12` imports the
**interface** `CanonicalFingerprint` as a value binding
(`import { CanonicalFingerprint, … } from './neutrality-core.js'`). Playwright
transpiles per file and cannot know the binding is type-only, so the runtime
ESM import fails. `pnpm run typecheck` (`tsc --noEmit`) is **GREEN** (rc=0) —
the defect is invisible to the static gates that passed in earlier rounds and
manifests only when the modules load for execution. Every one of the 15
browser nodes routes through `src/neutrality.ts` (HC07–HC10 neutrality is the
core of the protocol), so zero nodes can execute.

Evidence: `evidence/phase5/harness-typecheck.log` (rc=0),
`evidence/phase5/harness-list-defect.log` (rc=1 SyntaxError).

### 6.3 Decision

The directive prohibits modifying the harness. No launcher-side remediation
exists (the defect is inside frozen harness bytes; config cannot repair a
cross-file type-import). Therefore **no authoritative browser launch was
attempted** — there is no retry-to-green, no tally of any non-authoritative
result, and the browser phase is recorded **`NOT_RUN`**. The minimum fix is a
one-line `import type` change in a CTO-authorized harness-fix round; until
then the 17-node reconciliation (HC01–HC17, 15 BROWSER + 2 STATIC), the
dynamic-token/password/Authorization/public-`w` scans, and HC11/HC17 runtime
evidence remain **unproduced**.

## 7. Publication (this report branch)

Branch `reports/dc12r1-mvp-l1-j1-h2-c-i2-e2-v2-lubuntu-independent-backend-browser-final-2026-08-30`,
created directly from the candidate `86f41b93…`; adds `REPORT.md`,
`findings.csv`, `evidence/**`, `manifest_sha256.csv`; **modifies zero
existing files**. `manifest_sha256.csv` covers every blob of THIS commit's
tree excluding exactly one path — itself (self-exclusion manifest);
verification: `missing=0 / extra=0 / mismatch=0` (§8). Secret scan over the
pack: the only `postgresql://`-shaped strings are public placeholder fixtures
inside committed product test node IDs; zero task credentials published
(task credential files were shredded at cleanup, before publication).

## 8. Cleanup closure and frozen-refs re-verification

At close: task containers (`dc12r1e2v2`, `dc12r1e2v2a`, `dc12r1e2v2b`),
networks and dangling volumes removed; task ports 18545/16381/18025/8000/5173
**all free**; sentinel 26379 unreachable; credentials (PG/Redis superuser and
run-role passwords, SMTP secret, all `J1H2C_*` values) **shredded**; task
maildir destroyed; runtime worktree deregistered. Frozen refs re-verified at
close via `git ls-remote`: `origin/zcode/…reintegration-2026-08-30` ==
`86f41b93…`, `origin/kilo/…e2-v1-final-cumulative` == `1b84cfe…`,
`origin/product-dev-recovered` == `24a28d76…`, `origin/reports/…e1…` ==
`df40a202…` — all unchanged. local == remote for this report branch.

## 9. Findings register

See `findings.csv`. Headline: **F-001** harness runtime defect (browser
blocker; HARNESS_DEFECT, explicitly NOT a product red); **F-002** runner
full-manifest env-size limitation (infrastructure; VOID attempt #1);
**F-003** four non-deterministic parametrized node IDs (observation;
normalized, disclosed); **F-004** test-env mock auth lacks
`invitations:create` (disclosure; launcher used the product's
`InvitationService` directly).

## 10. Adjudication

The backend component of the claim ceiling is MET with independent,
single-launch, zero-red authority evidence bound to the candidate. The
browser component is **NOT_RUN** due to a frozen-harness runtime defect that
this directive's prohibitions forbid fixing. The full claim
`…_BACKEND_AND_BROWSER_FINAL` is therefore **NOT PASS**. The candidate gains
NO merge approval, NO deployment readiness, and H2-C does NOT enter the
controlled merge drill on the strength of this round; the backend zero-red
evidence stands as candidate-scoped input for the next authorization.

**VERDICT: `NOT_PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_C_I2_E2_V2_LUBUNTU_INDEPENDENT_BACKEND_AND_BROWSER_FINAL — BROWSER_NOT_RUN_BLOCKED_BY_HARNESS_RUNTIME_DEFECT; BACKEND_FULL_SUITE_ZERO_RED_ACHIEVED`. STOP.**
