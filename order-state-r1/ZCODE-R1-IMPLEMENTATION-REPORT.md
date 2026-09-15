# ZCODE-R1-IMPLEMENTATION-REPORT — MPANGO_ORDER_STATE_AUTHORITY_R1_IMPLEMENTATION

AUTHORIZATION: CTO-AUTH-MPANGO-ORDER-STATE-AUTHORITY-R1-IMPLEMENTATION-2026-09-15
EXECUTOR: Codex-L; IMPLEMENTATION SUBEXECUTOR: ZCode under Codex-L supervision
VERIFICATION TIER: V3_MERGE_CRITICAL
CLAIM CEILING (final line): AUTHOR_ORDER_STATE_R1_IMPLEMENTATION_CANDIDATE_READY_FOR_INDEPENDENT_REVIEW_ONLY
All results below are AUTHOR-EXECUTED until an independent reviewer reruns them.

## 1. Baseline, branch, tree

| Field | Value |
|---|---|
| FROZEN_PRODUCT_BASE | 1ee75d9faaa00cdcadfe9f46d1e0ac960efc632e (tree 5712eb85e6bf76d8662a6bb7890e609d09bd7ec0) |
| Branch | codex/order-state-authority-r1-impl-2026-09-15 (fresh worktree from the exact BASE) |
| Evidence anchor | 474eaf35 (D1 documentation closeout) — EVIDENCE ONLY, not a parent; no pytest logs, evidence files or D1 test artifacts were copied into this tree (fresh `backend/tests/order_state_r1/` written anew; `backend/tests/order_state_d1/` does not exist here) |
| Implementation HEAD | recorded at handback (see §9) |
| Protected branches | `product-dev-recovered` untouched; D1 branch/reports untouched |

Business contract v0.67 (SHA256 EE5F3FD0…) original was NOT present on this
host — not reconstructed; the frozen decisions in CTO §1 governed. The CTO
instruction file itself was verified: SHA256
3b96e8b5121badd817c0e142b8c3bdc4f73097bcd19bb394e4eb4b7643f9bb35.

## 2. Exact changed paths (implementation candidate)

Product (7):
- `backend/services/order_command_service.py` (NEW — the single status writer)
- `backend/services/order_service.py` (compatibility adapter; no direct write)
- `backend/crud/order.py` (status writers + CRUD matrix removed; non-writing
  helpers kept; domain exception re-exported for compatibility)
- `backend/core/domain/order_state.py` (DRAFT→CANCELLED edge; frozen decision)
- `backend/api/v1/orders.py` (confirm/cancel rewired to commands; fulfill/
  return intent plumbing; request params direct-call compatible)
- `backend/api/v1/client/orders.py` (cancel rewired; dual-key 404 kept)
- `backend/api/middleware/auth.py` (post-commit notification dispatcher)

Tests (10): `backend/tests/order_state_r1/` (`__init__`, `conftest`,
`support`, `run_mutations`, `test_baseline`, `test_concurrency`,
`test_freshness`, `test_rollback_vectors`, `test_notifications`,
`test_static_guards`, `test_access_controls` — 23 tests).

Governance (2): `harness-governance/inventory/coverage-debt.json` (new debt
entry registering the ten suite paths — no waiver),
`harness-governance/inventory/inventory.json` (CATALOG-ID-001 crud anchor
re-based to the surviving `create_order` after the writers were removed).

Docs (1): `order-state-r1/LOCK-ORDER.md` (actual lock order + limited
cycle analysis per CTO §3).

Existing-suite follow-up (2): `backend/tests/test_s5_order_state_machine.py`
(DRAFT set 2→3, frozen decision), `backend/tests/test_s5_ledger.py` +
`backend/tests/business/test_financial_loop.py` (confirmation-posting
expectations rewritten to the frozen no-ledger decision — NOT weakened:
the new assertions demand ZERO entries and would fail under the old
behavior, which is exactly what mutation M5 checks).

## 3. CHANGED_OR_ADDED_TESTS_COVERING_NEW_PATHS / CODE_PATH_TO_TEST_MATRIX

| Command-service path | Covering tests |
|---|---|
| `_load_locked` (FOR UPDATE + populate_existing) | test_freshness (both), mutation M2 |
| `_validate_transition` / invariants | test_baseline, s5 suite, mutation M6 |
| `_validate_item_identities` | test_baseline::test_identity_and_snapshots… |
| `_reserve_inventory` (deterministic stock locks) | baseline, concurrency matrix, rollback vectors; mutations — |
| `_release_reservations` (decision inside the lock) | concurrency confirm-vs-cancel; mutation M3 |
| `_reserve_credit` (binding credit reservation) | baseline (balance delta), rollback zero-sends; mutation M4 fault seam |
| `_assign_status` (THE single write) | AST single-writer guard; every behavioral test; mutation M1 |
| `_post_transition_ledger` (CONFIRMED none; PAID/RETURNED preserved) | s5_ledger suite; financial loop; AST no-confirmation-ledger; mutation M5 |
| notification intents → request.state → post-commit dispatch | test_notifications (pre-commit zero, rollback zero, post-commit real recipient); mutation M4 |
| paid/partially_paid fail-closed 409 | baseline, pay-vs-cancel race; mutation M6 |
| whole-request rollback incl. SECOND per-item write | test_rollback_vectors; mutation M7 |

## 4. NEGATIVE_AND_FAILURE_PATHS — named mutation results

All seven CTO-required mutations executed (`run_mutations.py`; evidence
`2026-09-15T1620Z-r1-mutations-run3.txt`): each applied an exact byte
replacement, its NAMED oracle went RED, the source was restored
byte-identically (git checkout + sha256 equality), and the paired control
re-ran GREEN.

| Mutation | Oracle (RED) | Control (GREEN) | Result |
|---|---|---|---|
| M1_RESTORE_CRUD_STATUS_WRITER | AST single-writer guard | no-confirmation-ledger guard | PROVEN |
| M2_REMOVE_LOCKED_FRESH_REFRESH | freshness stale-object test | baseline confirm | PROVEN |
| M3_STALE_CANCEL_RELEASE_DECISION | confirm-then-cancel release test | baseline cancel-release | PROVEN |
| M4_RESTORE_PRE_COMMIT_NOTIFICATION | no-send-before-commit test | draft-cancel baseline | PROVEN |
| M5_RESTORE_CONFIRMATION_ACCOUNTING | no-confirmation-ledger guard | baseline confirm | PROVEN |
| M6_OPEN_PAID_CANCELLATION | paid-cancel fail-closed test | draft-cancel baseline | PROVEN |
| M7_BREAK_PARTIAL_ITEM_ROLLBACK | second-item rollback-vector test | baseline cancel-release | PROVEN |

M2 required one bounded diagnosis round (recorded, per CTO §5): the first
oracle version rolled the session between preload and transition, evicting
the stale object and masking the mutation; the oracle was hardened to keep
the stale identity-map object alive (commit
`test(order-state-r1): keep stale CONFIRMED object…`). No mutation was
counted on the strength of a collection/syntax error; run1's M2 attempt
(rc=4-era failure) was discarded and re-proven.

## 5. Focused results (author-executed)

- R1 suite: **23 passed** (`evidence/2026-09-15T1510Z-r1-focused-green.txt`),
  covering: two confirms / two cancels / confirm-vs-cancel / pay-vs-cancel
  (two connections, arrival barriers, orchestrator-owned bounded cleanup,
  facts captured before assertions); two orders × two SKUs with REVERSE
  item order confirming concurrently under a barrier (aggregate reserved
  asserted per SKU); lock-after-preload freshness with fresh-session
  committed reads; fault after the state write AND fault during the second
  per-item inventory write, both rolling back to the exact before-vector
  (state/reservations/stock/movements/ledger/payments); real-HTTP
  permission-denied and cross-tenant (real tenant-B cashier) controls;
  stable and legacy identity/snapshot preservation; notification spy with
  zero pre-commit sends, zero rollback sends, post-commit best-effort to
  the REAL retailer email, and a no-placeholder guard.
- Related existing suites: 102 passed (s5 machine, phase5, orders_api,
  canonical payment, payment atomicity, payments api).
- Business + s5_ledger + R1 + s5/order rerun: 93 passed after the frozen
  decision updates, then the whole order family 165 passed.
- Backend FULL suite FINAL RUN (`evidence/2026-09-15T1730Z-backend-full-
  suite-final.txt`): **3861 passed, 1 failed, 29 skipped, 15 xfailed,
  rc=1 (39:01)**. The single failure is
  `test_pw1r3_rate_limit_context::test_101st_anonymous_is_429…`, which
  requires its OWN sentinel Redis on 127.0.0.1:26379 (ConnectionRefused in
  this environment — reproduced in isolation, signature is the sentinel
  connect, not order logic). Progression across runs is retained verbatim:
  run1 (no env grants) 77f/3698p/47e; run2 (+TEMP_DB/CREATEROLE)
  50f/3776p/36e; final (+CREATEDB+ADMIN+port allowlist) 1f/3861p — the
  convergence isolates the environment families from the product change.

## 6. FULL_SUITE_RESULT and runtime environment

- FINAL RUN: `evidence/2026-09-15T1730Z-backend-full-suite-final.txt`
  (env: task PG16 container osr1-pg16 :17771 — bootstrap/migrator/runtime
  roles separated; runtime granted CREATEDB and ADMIN on the reporting
  roles AFTER the earlier runs showed those are environment grants, not
  product matters; task Redis :17773; MPANGO_ALLOW_TEMP_DB_CREATE=1 +
  MPANGO_TEMP_DB_ALLOWED_PORTS=17771; venv from frozen requirements.txt).
- Prior runs retained: run1/run2 show the environment-family failures
  (temp-DB port allowlist, role privileges) that the final env closes;
  they are preserved verbatim.
- Environment-only leftovers (NOT product failures): the sentinel-port
  family (own redis on 26379) — exactly one test in the final run,
  reproduced standalone with the sentinel ConnectionRefused signature.

## 7. Business decisions applied (frozen, CTO §1)

- Ordinary draft cancel → CANCELLED (matrix edge added; VOIDED untouched
  by any route).
- Confirm = inventory reservation + credit reservation (binding
  outstanding_balance, the existing credit-occupation column) + ZERO
  ledger entries; no `post_confirmation_ledger` switch exists.
- Paid/partially_paid cancel → 409 `REFUND_WORKFLOW_NOT_IMPLEMENTED` with
  an explicit "refund/funds disposition workflow is not implemented"
  message — temporary fail-closed, not described as a permanent business
  prohibition.
- Notifications: typed request-private intents → request.state →
  dispatched only after successful commit by the auth middleware;
  recipients resolved from real retailer contact rows (email/phone);
  missing contact ⇒ logged skip; send failure ⇒ logged post-commit
  delivery failure; zero sends on rollback; NO ORM private attributes, NO
  module globals, NO response fields, NO placeholder recipients (AST
  guard enforces the no-placeholder rule).
- Payments remain exclusively in CanonicalPaymentService (its transition
  calls go through the compatibility adapter; no refund path, cash event,
  second accounting definition or general status endpoint added).
- R6: NOT a repair target — the create-vs-SKU race remains unfixed and
  unclaimed; no create-path SKU lock was added (CTO §3).

## 8. Notification / lock-order / transaction / rollback evidence

- Transaction owner: the tenant middleware (single whole-request
  transaction); commands never commit; verified by the rollback-vector
  tests which read PERSISTED state after failed requests.
- Freshness: every state-decision read is FOR UPDATE +
  populate_existing on the same object used for checks, side effects and
  the single write (freshness tests + M2).
- Lock order: `order-state-r1/LOCK-ORDER.md` — order row first everywhere;
  stock rows sorted (sku_code, sku_id); reservations sorted (sku_code,
  id); confirm-vs-cancel/fulfill inverse table order analyzed as safe
  under the orders-first invariant with the explicit unresolved residual
  (cross-order formal proof not claimed).
- Confirmation accounting proof: `test_static_guards.py::
  test_no_confirmation_ledger_call_anywhere_in_production` (AST, whole
  production tree) + `test_baseline` zero-ledger vector + mutation M5
  (restoring the posting turns the guard RED). All GREEN in the
  candidate.

## 9. Governance and handback bookkeeping

- Structural gate: PASS (`harness-governance/validator … --mode
  structural`) after adding DEBT-ORDER-STATE-R1-TEST-PATHS (registers the
  ten suite paths; release_blocked=false) and re-basing the CATALOG-ID-001
  crud anchor to surviving code. No waiver; no protocol-delta edit; no
  protected governance path touched beyond the two inventory data files.
- handoffctl: existing whitelist change verified as EXACTLY the two ZCode
  lines (init validation + verify schema); containment-regression PASS;
  observed digest PINNED:
  `d4fd6a248680d36890e49c919b3ec74adc3ac2fe36c2e8f4c121e8391ffef51a`
  (handoff event HANDOFFCTL_PINNED). The missing formal authorization
  reference for the original edit remains a CTO disposition item — no
  retrospective approval manufactured.
- Cleanup closure: task containers `69c4362c13854…` (osr1-pg16,
  127.0.0.1:17771) and `b595108d90d8…` (osr1-redis, 17773) — stopped and
  removed after evidence capture, with post-check zero remaining; shared
  mpango_postgres/mpango_redis and all other tasks' containers untouched
  (handoff event CLEANUP_COMPLETE).
- GitNexus: fresh full index after implementation (32,204 nodes); impact
  on `_assign_status` shows exactly the three command methods as callers
  and `apply_transition` upstream = adapter transition → canonical
  payment/declaration/seed/fulfill/return (evidence
  `2026-09-15T1710Z-gitnexus-impact.txt`); `detect_changes` was run at
  handback (output in the handoff command log). Limitation recorded: the
  first index pass predates part of the implementation and was re-run.

## 10. KNOWN REDs / UNCOVERED PATHS

- KNOWN product REDs: NONE in the candidate (23/23 R1 suite GREEN; the
  five D1 product findings are fixed and mutation-proven; R6 was NOT
  attempted — unproven product defect per the D1 disposition, excluded
  from this round by CTO §3).
- UNCOVERED / environment: sentinel-port suites (26379) env-blocked;
  alembic real-upgrade suite needs the temp-DB allowlist envs (now set;
  any residual runs are recorded in the final full-suite log); browser/
  frontend surfaces out of scope; R6 future proof; delivery-stage
  receivable/revenue accounting = separate future task (CTO §1).

## 11. Self-check

`git diff --check` clean; all changed files strict UTF-8 / no BOM / no CR;
detect-secrets scan of every changed file: 0 findings with a VALID
same-shape canary (planted keyword secret detected); evidence manifest:
`scratch/MPANGO_ORDER_STATE_AUTHORITY_R1_IMPLEMENTATION/evidence/`
(focused green, mutations run1-3, full-suite run1-3, gitnexus impact,
self-check file with hashes). D1 branch, evidence anchor and all prior
logs untouched.

AUTHOR_ORDER_STATE_R1_IMPLEMENTATION_CANDIDATE_READY_FOR_INDEPENDENT_REVIEW_ONLY
