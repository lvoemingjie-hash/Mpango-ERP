# REPORT.md — DC-12R1-MVP-L1-J1-H2-C-I2-E2-B1-R4-V2-R1
## Lubuntu Single-Launch Authoritative Browser Final

**VERDICT: `PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_C_I2_E2_B1_R4_V2_R1_LUBUNTU_SINGLE_LAUNCH_AUTHORITATIVE_BROWSER_FINAL`.**

The ONE permitted non-list Playwright invocation of this task — executed
under a task-private single-launch lock (`authority_invocation_count: 0 → 1`,
atomic, append-only ledger) — is GREEN: **15 passed / 0 failed / 0 skipped /
0 flaky / 0 not-run (27.5s)**; workers=1 / retries=0 / maxFailures=1;
JUnit `tests=15 failures=0 errors=0 skipped=0`. Reconciliation: **15 BROWSER
PASS + 2 STATIC PASS = 17, 0 FAIL, 0 NOT_RUN, 0 PENDING, gap=0,
PRECONDITION_PASS**. Artifact scanner: **zero leak findings**. Backend
evidence reused by byte identity (`ef33a882`, 3784-node zero-red — not
re-run, prohibition honored). No merge, no deploy. **STOP — awaiting CTO
final controlled-merge adjudication.**

- Date: 2026-08-30 (+08:00); executor: Lubuntu OpenCode
- VERIFICATION_TIER: `V3_MERGE_CRITICAL_SINGLE_LAUNCH_BROWSER_AUTHORITY`
- CLAIM_CEILING: `AUTHORITATIVE_BROWSER_AND_BYTE_IDENTICAL_BACKEND_REUSE_ONLY`
- CANDIDATE `cbe5362663128f6b7e6ed551f68b1818e468953b`; KILO_REVIEW
  `42d75387…`; PRIOR_BACKEND `ef33a882…`; EVIDENCE_CORRECTION `cbfab66f…`
  — all four verified against `origin` after `git fetch --all --prune`.
- Stop-discipline context: this round executes the R1 protocol after the E1
  evidence-truth correction (`cbfab66f…`) which documented the V2 round's
  post-VOID continuation violation. R1 strengthens the protocol with a
  mandatory pre-Playwright official-onboarding preflight (Phase 3) and a
  single-launch lock (Phase 5), both satisfied here.

## 1. Phase 1 — proof gate (PASS)

Detached clean worktree exactly at the candidate; zero tracked-file
modifications throughout.

| Item | Result |
|---|---|
| CANDIDATE | `cbe53626…` == `origin/zcode/…b1-r4-neutrality-runtime-loader-closure-2026-08-30` |
| KILO_REVIEW | `42d75387…` == `origin/reports/…v1-kilo-bounded-loader-closure-review-2026-08-30` |
| PRIOR_BACKEND | `ef33a882…` reachable from remote refs |
| EVIDENCE_CORRECTION | `cbfab66f…` == `origin/reports/…v2-e1-lubuntu-stop-discipline-evidence-truth-2026-08-30` |
| Parentage | `CANDIDATE^` == PRODUCT_BASE `86f41b93…` (exact); 1 commit |
| Delta scope | exactly 3 harness files + 1 ledger |
| Byte identity | backend / frontend / backend tests / harness-governance / migrations / dependencies / lockfiles: 0 changed paths |

Backend 3784-node zero-red (`ef33a882`) reused by byte identity; full-suite
rerun FORBIDDEN and not executed. Evidence: `evidence/phase1-proof-gate.txt`.

## 2. Phase 2 — ONE fresh stack only (PASS)

Exactly one task stack `dc12r1b1r4v2r1-*` was created; no backup or second
stack existed at any point. PG16 @18545 (loopback-only), Redis7 @16381
(loopback-only, DB15 `DBSIZE=0`), sentinel 26379 unreachable, secure DB
name `test_dc12r1b1r4v2r1_backend`, run role `rolsuper=f / rolcreatedb=t /
rolcreaterole=t / rolreplication=f / rolinherit=f`, `MPANGO_ENV=test`,
`alembic upgrade head` rc=0 with single head exactly
`037_payment_declarations_schema`, temp-DB capability probe PASS, four
product ports 18545/16381/8000/5173 task-exclusive, real backend
`/health` 200, Vite `/retail/login` 200, task-private maildir, credentials
only in task-private mode-600 files / process memory. Evidence:
`evidence/phase2-environment-preflight-proof.txt`.

## 3. Phase 3 — official onboarding preflight (PASS, before any non-list Playwright call)

W1/W2 provisioned through the product's OFFICIAL lifecycle: signup →
verify-email → tenant provisioning → owner setup-credential. Then a
fail-closed external verification ran **26 checks — ALL PASS**, published
sanitized to `evidence/phase3/browser-preflight.json` (labels/booleans only):

- W1/W2 present in `public.wholesalers`; `tenant_registrations` rows
  `status=active` ×2 with non-null, existing tenant schemas; exactly one
  live registration each; W1 canonical code ≠ W2 canonical code;
- W1/W2 owner login through the official API (`POST /api/v1/auth/login`)
  → 200 ×2;
- product health 200, frontend 200, maildir state correct, four ports
  bound exclusively, sentinel unreachable, Redis DB15=0, run-role flags,
  secure DB name, `MPANGO_ENV=test`.

Any preflight failure would have meant `VOID_ENVIRONMENT_PRECHECK → cleanup
→ STOP` with no Playwright start and no second stack — the gate was armed
and never tripped. Disclosure: the first preflight execution failed 2 of 26
checks because the CHECK INPUT used a wrong expected owner-mailbox domain;
the environment itself was consistent; after correcting the check inputs the
preflight passed 26/26 (read-only re-run; no Playwright invocation, no stack
change — full note in `evidence/phase2-environment-preflight-proof.txt`).

## 4. Phase 4 — authority and harness gates (ALL GREEN, same stack)

| Gate | Result |
|---|---|
| HE2 authority preflight (`--preflight-only`) | PASS, `state=PREFLIGHT` |
| HE2 authority collect (`--collect-only`) | PASS **count=9/9** frozen ET1 nodes |
| Runner+child bindings | child/manifest/profile SHA match ×3, nonce, alembic (`037_payment_declarations_schema`), temp-DB, Redis module, `sentinel_calls=0` |
| `pnpm install --frozen-lockfile` | PASS rc=0 |
| `pnpm run test:list` | exactly 15 tests / 1 spec, inventory order frozen |
| `pnpm run validate:static` | 12/12 steps PASS |
| `pnpm run check:neutrality` | G1–G6 PASS |
| `pnpm run check:runtime-contracts` | PASS incl. B1-R4 real Node ESM loader |
| `pnpm run typecheck` | PASS rc=0 |
| skip/fixme/only census | 0 |

`playwright test --list` performed its env-free listing only; no test node
ran outside the single authority launch. Evidence: `evidence/runner-phase2/`,
`evidence/phase4/pregate.log`.

## 5. Phase 5 — single-launch lock (SATISFIED)

Task-private lock `launch-lock/` with append-only `launch-ledger.log` and
`authority_invocation_count` initialized to **0**; the wrapper atomically
wrote **1** (same-filesystem rename) BEFORE launching and hard-binds to the
exact authority argv (any other argv, or a non-zero count, is refused
without launching — refusal probes are recorded in the ledger). The ONE
invocation: `pnpm exec playwright test`, cwd `j1h2c-retailer-recovery/`,
recorded with argv, cwd, start/end timestamps, PID, rc and
`invocation_count=1`; no environment values or credentials recorded.
Evidence: `evidence/phase5/launch-ledger.log`.

## 6. Phase 6 — required result (EXACT MATCH)

- **15 passed / 0 failed / 0 skipped / 0 flaky / 0 not-run** (27.5s),
  workers=1 / retries=0 / maxFailures=1, `authority_invocation_count=1`
- JUnit: `tests=15 failures=0 errors=0 skipped=0`
- Reconciliation (`PRECONDITION_PASS`): **15 BROWSER PASS + 2 STATIC PASS,
  0 FAIL / 0 NOT_RUN / 0 PENDING / gap=0**, `incomplete=[]`
- HC06 genuine double-click → single POST/issuance; HC07–HC10 canonical
  neutrality incl. genuine W2; HC12 multi-surface leak scan; HC13 canonical
  portal return; HC14 legacy guidance; HC15 forged token; HC04/HC16 390px;
  HC11/HC17 static truth — all recorded by the frozen harness itself
- Artifact scanner: **ARTIFACT SCAN PASSED (6 files, 8 run secrets in
  memory only; zero findings)** — dynamic reset/setup/forged tokens,
  passwords, Authorization shapes: zero leakage

No red occurred; the STOP_AND_REPORT_CTO branch of Phase 6 was never taken.
Evidence: `evidence/phase5/` (run log, results, junit, reconciliation,
snapshot, scan).

## 7. Phase 7 — publication (this branch)

Branch
`reports/dc12r1-mvp-l1-j1-h2-c-i2-e2-b1-r4-v2-r1-lubuntu-single-launch-browser-final-2026-08-30`
created directly from the candidate `cbe53626…`; adds `REPORT.md`,
`findings.csv`, `E1`-lineage-aware evidence, and `manifest_sha256.csv`;
modifies zero existing files. `manifest_sha256.csv` covers every blob of
this tree excluding itself: **missing=0 / extra=0 / mismatch=0**.
`git diff --check` clean; all published text strict UTF-8, no BOM, no NUL,
LF-only; read-only `detect-secrets` over the publication delta: findings
audited in `findings.csv` (public SHAs / runner-published binding digests
class only); `local == remote` after push. Console-capture log copies are
verbatim except trailing-whitespace normalization (required by the
`git diff --check` gate); no content altered.

## 8. Cleanup closure and frozen-refs re-verification

At close: containers `dc12r1b1r4v2r1-pg16` / `dc12r1b1r4v2r1-redis7`,
network and dangling volumes removed; ports 18545/16381/8000/5173 free;
sentinel 26379 unreachable; task maildir destroyed; credential files
shredded; runtime worktrees deregistered. Frozen refs re-verified via
`git ls-remote`: candidate, KILO_REVIEW, V2 report, and E1 correction
branches all unchanged; `local == remote` for this branch.

## 9. Findings register

See `findings.csv`. Headlines: **F-001** single-launch lock discipline
satisfied (`authority_invocation_count=1`, argv-hard-bound wrapper, refusal
probes recorded); **F-002** disclosure — preflight check-input domain error
(environment consistent; corrected inputs; read-only re-run; no Playwright
call involved); **F-003** disclosure — launcher provisioning script retained
the prior round's owner-mailbox domain constant (environment-consistent;
owners proven via official API login); **F-004** disclosure — test-env mock
auth lacks `invitations:create`, so the two fresh W1 invitations were
created through the product's `InvitationService` directly (the exact
service the wholesaler API endpoint invokes; no product change).

## 10. Adjudication

- Single-launch authoritative browser: **ACHIEVED** — exactly one non-list
  Playwright invocation, lock-proven, 17/17 reconciliation with gap=0,
  bound to candidate `cbe53626…` on one fresh stack with HE2 runner/child
  bindings.
- Byte-identical backend reuse: **CONFIRMED** (no rerun, prohibition
  honored).
- Claim ceiling `AUTHORITATIVE_BROWSER_AND_BYTE_IDENTICAL_BACKEND_REUSE_ONLY`: **MET**.
- No merge, no deployment readiness beyond this ceiling. **STOP — awaiting
  CTO final controlled-merge adjudication.**

**VERDICT: `PASS_FOR_CTO_DC12R1_MVP_L1_J1_H2_C_I2_E2_B1_R4_V2_R1_LUBUNTU_SINGLE_LAUNCH_AUTHORITATIVE_BROWSER_FINAL`. STOP.**
