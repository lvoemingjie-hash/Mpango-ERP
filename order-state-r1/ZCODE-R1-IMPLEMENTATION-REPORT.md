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

---

# F1 ADDENDUM (append-only erratum) — MPANGO_ORDER_STATE_AUTHORITY_R1_IMPLEMENTATION_F1

Parent: b1135646 (REQUIRED_PARENT). This round is LINEAR on the same
branch; no amend/rebase/squash, not pushed, independent review NOT started.
Machine-generated exact changed paths vs FROZEN_PRODUCT_BASE 1ee75d9f are
in `scratch/.../evidence/2026-09-15T2015Z-f1-exact-paths-vs-base.txt`
(git diff --name-status, 28 entries). Historical sections above are
retained verbatim; where this addendum conflicts, the addendum governs.

## CREDIT_HOLD_PERSISTENCE_DECISION_REQUIRED (STOP clause outcome)

There is NO per-order credit-hold authority persistence field. The only
credit surface is the aggregate
`public.wholesaler_retailer_bindings.outstanding_balance`. Per the STOP
clause this round added NO migration and does NOT infer per-order
ownership from the aggregate. Consequences, each captured as a NAMED,
reproduced KNOWN RED (kept RED — never masked):

1. `test_cancel_after_confirm_releases_credit_hold_KNOWN_RED` — confirm
   adds the order total to the binding (+60.00); cancelling that confirmed
   order leaves the hold in place (after_cancel == held). The aggregate
   cannot be decremented without guessing which order's hold it was.
2. `test_confirm_then_credit_payment_does_not_double_count_KNOWN_RED` —
   confirm (hold +80.00) followed by a full CREDIT payment adds +80.00
   again (movement 160.00 for one 80.00 exposure): hold and credit
   exposure are unlinked.
3. `test_receivables_summary_counts_exposure_once_KNOWN_RED` — the
   receivables summary reads the binding aggregate, so it reports the
   doubled exposure (200.00 for a single 100.00 credit order).

CTO decision required: introduce per-order credit-hold persistence
(schema + release/convert semantics) or redefine confirmation credit
occupancy. Until then these three faces stay RED as evidence.

## Fixes delivered this round (all mutation-proven)

- Explicit dispatch-or-reject: generic `apply_transition` refuses the five
  command-owned targets; new explicit `fulfill_order`/`return_order`
  commands and `apply_payment_transition` (sole PAID/PARTIALLY_PAID
  writer, reachable only via CanonicalPaymentService through the adapter);
  `OrderService.transition` dispatches accordingly. Seed call site
  rewired; paid seeding goes through the canonical service only.
- Pre-lock discipline: fulfill/return lock EVERY distinct stock row in one
  global sorted-sku_id order BEFORE any inventory write (`_prelock_stocks`
  + `test_prelock.py` spy oracle; mutation M9 removes it and goes RED).
- Client cancel maps InvalidStateTransitionError/OrderInvariantViolation
  to 409 CANCEL_NOT_ALLOWED; repeated and paid cancels return the stable
  409 (face-5 test; mutation M10 removes the mapping and goes RED);
  cross-tenant neutral 404 preserved.
- Face 6: two orders × two SKUs × reverse item order with fulfill‖return
  under an arrival barrier — both succeed, per-SKU on-hand 97/98 exactly
  as the net ledger implies, zero orphan reservations.

## Mutation runner rebuilt (strict contract)

pristine GREEN gate over every oracle+control BEFORE any mutation;
anchor count must equal exactly 1; mutated source must ast.parse AND
compile; a mutation counts ONLY as named-node + expected-marker + rc==1
semantic RED; rc=4/collection/setup errors and timeouts are VOID
(teardown errors trailing a real assertion RED do not void it);
byte+mode restore with per-path `git status --porcelain` clean proof.
M1 valid syntax; M5 anchored in the REAL HTTP confirm path
(`OrderCommandService.confirm_order`). Mutations M1–M7 (prior faces,
re-anchored to the current code) plus NEW M8 generic-bypass, M9
no-prelock, M10 client-409-mapping-removed: **10/10 PROVEN**
(`evidence/2026-09-15T1945Z-f1-mutations-run4.txt`).

## Governance

`DEBT-ORDER-STATE-R1-TEST-PATHS` REMOVED (the workaround registration is
gone; no waiver anywhere). Real semantic inventory node
`ORDER-STATE-R1-001` added: route_api layer, owner codex-l, status NOT_RUN
(honest — author-executed, independent rerun pending), real source anchors
covering the product surface and all ten suite paths + the new test files
and the mutation runner, mutation mapping MUT-ORDER-STATE-R1-M1-M10.
Structural gate: **PASS** (16 nodes, 3 pre-existing debts, none opened or
waived by this task).

## Verification chain (order enforced per directive #8)

focused → mutations → governance all reached their required state BEFORE
the full run; the backend full suite then ran EXACTLY ONCE with the task
stack and `PW1R3_TEST_REDIS_URL=redis://127.0.0.1:17773/15` set — result
recorded in `evidence/2026-09-15T2010Z-f1-backend-full-final.txt` (see the
final summary appended below after completion).

## Focused result (author-executed)

`tests/order_state_r1/`: 32 tests — 29 passed + the 3 named credit KNOWN
REDS, rc=1 as expected (`evidence/2026-09-15T2000Z-f1-focused-final.txt`).

## F1 final results (post-stabilization, author-executed)

- Strict mutations re-verified AFTER the stabilization commit:
  `evidence/2026-09-15T2115Z-f1-mutations-run5-final.txt` — pristine gate
  GREEN, **10/10 PROVEN** (M1–M10).
- Focused R1 suite: 32 tests — 29 passed + 3 named credit KNOWN REDs,
  rc=1 (`evidence/2026-09-15T2000Z-f1-focused-final.txt`).
- Affected legacy suites after migration to the explicit contract:
  s5_order_state_machine + s5_ledger + business.financial_loop 33/33
  GREEN; sku_m1_migration (with task temp-db env) 6/6 GREEN.
- The ONE permitted backend full run happened BEFORE the stabilization
  fixes (25 failed / 3827 passed / rc=1,
  `evidence/2026-09-15T2010Z-f1-backend-full-final.txt`, retained
  verbatim). Of those 25: 3 were the named credit KNOWN REDs; 22 were
  legacy direct-transition calls + the seed flush defect — every one
  repaired and re-verified FOCUSED above (per the single-full-run rule no
  second full run was started). Residual known-RED surface in the full
  suite is therefore the 3 credit faces only, by CTO STOP clause.
- Structural gate: PASS with the real ORDER-STATE-R1-001 node and no
  waiver/debt workaround.

---

# F2 ADDENDUM (append-only) — MPANGO_ORDER_STATE_AUTHORITY_R1_IMPLEMENTATION_F2

Parent: 5dfdb3a6 (REQUIRED_PARENT honored); linear commits on the same
branch; no amend/rebase, not pushed, independent review NOT started.
Exact changed paths vs BASE 1ee75d9f (machine-generated, 29 entries):
`scratch/.../evidence/2026-09-16T0245Z-f2-exact-paths-vs-base.txt`.

## Directive-by-directive

1. PARTIALLY_PAID joined COMMAND_OWNED_TARGETS — the generic transition
   refuses all six concrete targets; verified by the face-4 loop and the
   NEW dedicated CONFIRMED→PARTIALLY_PAID refusal oracle (matrix-legal
   edge still refused generically).
2. `OrderService.transition` now REFUSES PAID/PARTIALLY_PAID outright
   (structured InvalidStateTransitionError naming the required canonical
   path); AST guard `test_adapter_refuses_payment_states` proves no
   payment-command call survives in the adapter.
3. `CanonicalPaymentService` calls
   `OrderCommandService.apply_payment_transition` DIRECTLY (result
   unwrapped); production caller AST guard
   `test_payment_command_single_caller_guard` — any other caller goes RED.
4. ONE shared `_prelock_stocks` strategy (deduplicated, global sorted
   sku_id, optional require_active) serves confirm/cancel/fulfill/return;
   reserve/release consume the prelocked rows; the guard forbids any
   `_locked_stock_by_sku_id` call outside `_prelock_stocks`.
5. New races: confirm‖fulfill and cancel‖fulfill — two orders, two SKUs,
   reverse item order, arrival barriers, exact per-SKU aggregates
   (96/3 + 95/2 and 96/0 + 95/0 respectively), terminal states exact,
   zero orphan reservations.
6. Runner strictness: ONLY rc==1 + exactly the named FAILED node + named
   marker present + zero setup/teardown/collection errors attached to the
   oracle node itself (unrelated fixture-cleanup noise does not void);
   pristine GREEN gate over every oracle+control first; anchor==1;
   mutated source ast.parse+compile; byte+mode restore with worktree-clean
   proof. **13/13 PROVEN** (`evidence/2026-09-16T0230Z-f2-mutations-run6-final.txt`)
   including the three NEW mutations M11 (PARTIALLY_PAID bypass via
   frozenset shrink), M12 (non-canonical payment caller injected into the
   pay route), M13 (inverse global order inside `_prelock_stocks`).
7. Credit RED oracles corrected: face-1 unchanged precise 60/60; face-2
   gained a cash/transfer CONTROL (binding unmoved by a transfer
   settlement) before the 160/80 double-count assertion; face-3 rewritten
   with two ISOLATED retailers — the confirm-only control face asserts the
   current aggregation semantics (binding-hold 50 + unpaid 50 = 100) and
   the credit face asserts 200/100 (the same exposure counted twice);
   `or True` removed (explicit retailer match).
8. Credit product code: UNCHANGED — awaiting the CTO choice; no
   migration, no aggregate-ownership inference; the three named REDs
   remain the evidence (CREDIT_HOLD_PERSISTENCE_DECISION_REQUIRED).
9. Verification chain held: focused (38 passed + 3 named credit REDs,
   rc=1 — `evidence/2026-09-16T0240Z-f2-focused-final.txt`) → mutations
   13/13 → structural gate PASS → the FINAL single backend full run with
   the task stack and PW1R3_TEST_REDIS_URL (result appended below once
   complete; retained verbatim).

## F2 final stabilization (post full-run) — verified focused

The single permitted full run surfaced 33 contract-ripple failures (legacy
suites still writing PAID/PARTIALLY_PAID directly or stubbing the removed
adapter seam). All 33 migrated to the explicit contract and re-verified in
FOCUS: 232 passed across order_state_r1 + s5_order_state_machine +
s5_ledger + business + s5d4b + i2a canonical + dc11d replay + phase5 +
orders/payments — with ONLY the 3 named credit KNOWN REDs RED
(CREDIT_HOLD_PERSISTENCE_DECISION_REQUIRED). Per the one-full-run rule, no
second full run was started; the stabilization commit is 799d261b and the
final HEAD/tree are recorded in the handback.

Final HEAD: 799d261bf3636e073a8b3cfd4439a956b67d6f22
Final tree: 89d07b7c31c885a3a7ce64988b84b7d1ef1b3e18

# F3 ADDENDUM (append-only) — MPANGO_ORDER_STATE_AUTHORITY_R1_IMPLEMENTATION_F3

Parent: 998a549f (REQUIRED_PARENT honored); linear commits on the same
branch; no amend/rebase, not pushed, independent review NOT started.
Claim ceiling: F3_CANDIDATE_READY_FOR_CODEXL_REVIEW_ONLY.

## Codex-L source disposition (accepted for bounded completion)

- cancel derives its stock set from the order's ACTIVE reservations
  (`_prelock_reservation_stocks`), locked by reservation.sku_id in the
  same global sorted-sku_id order, before `_release_reservations`;
- a legacy DRAFT order (no active reservations) cancels as a PURE status
  transition — zero reservation/stock side effects;
- a legacy order WITH reservations still releases exactly what was
  reserved, via reservation.sku_id (order.items identities are never
  consulted for the cancel stock set);
- fulfill/return reject NULL sellable identity with a controlled 409
  ORDER_ITEM_SELLABLE_ID_REQUIRED BEFORE any inventory write (fulfill)
  and BEFORE the return-ledger reversal (return).
Credit accounting, receivables, payments, migrations, pricing, SKU
packaging and notification behavior are UNCHANGED.

## F3 test faces (backend/tests/order_state_r1/test_f3_legacy_faces.py)

Four real-PG faces, all GREEN on the F3 product bytes:

1. `test_legacy_draft_cancel_pure_status_write` — legacy DRAFT (NULL
   sellable_unit_id) cancels 200 -> CANCELLED; no reservations; stock
   untouched 100/0; the ENTIRE legacy order-item snapshot captured
   immediately before cancel is byte-equal afterwards
   (OSR1-F3-DRAFT-SNAPSHOT).
2. `test_legacy_with_reservations_cancel_releases_by_reservation_sku_id`
   — confirm reserves with the REAL sku_id, then the item degrades to
   legacy; cancel releases the reservation and restores 100/0; the
   entire legacy order-item snapshot before cancel equals the snapshot
   after (OSR1-F3-RESV-SNAPSHOT).
3. `test_fulfill_null_identity_controlled_409` — paid order degraded to
   NULL identity: fulfill returns the CONTROLLED 409
   ORDER_ITEM_SELLABLE_ID_REQUIRED, never ValueError/500
   (OSR1-F3-FULFILL-NULL-409).
4. `test_return_null_identity_controlled_409` — fulfilled order degraded
   to NULL identity: return returns the CONTROLLED 409, never
   ValueError/500 (OSR1-F3-RETURN-NULL-409).

## Mutation classifier completed (run_mutations.py)

F3 contract: ONLY rc==1 + exactly the named FAILED node + named marker +
ZERO collection/setup/teardown ERRORs anywhere in the single-node
invocation counts as SEMANTIC_RED. ANY ERROR form voids the run —
`ERROR collecting`, `ERROR at setup/teardown of` section headers, and
short-summary lines beginning `ERROR ` — even when the same run also
shows a valid assertion failure (the F2 rule voided only oracle-node
errors). `test_classifier.py`: 10/10 GREEN (pure, no DB), including the
failure-plus-unrelated-teardown-error vector and a realistic pytest
FAILURES+ERRORS+short-summary vector. The runner's Mutation record is a
NamedTuple (dataclass string-annotation resolution breaks unregistered
importlib loads).

Broad markers replaced with unique oracle labels on the affected
assertions (assertion strength preserved or strengthened): M2
OSR1-M2-ORACLE, M3 OSR1-M3-ORACLE, M6 OSR1-M6-ORACLE, M8 OSR1-M8-ORACLE,
M9 OSR1-M9-ORACLE, M11 OSR1-M11-ORACLE, M13 OSR1-M13-ORACLE. `DID NOT
RAISE`, `reserved|orphan`, `prelock` and the generic 409 alternations no
longer gate any mutation.

Anchors re-based on the F3 product shape (anchor count == 1 verified for
all 16): M3 now targets the cancel reservation-derived block; M9 targets
the F3 fulfill prelock site; M13 now reverses the reservation-derived
cancel lock order (the old `_prelock_stocks` cancel site no longer
exists — mutating it could no longer reach the M13 oracle).

## F3 named mutations (added, no renumber reuse)

- M14_CANCEL_STOCKS_FROM_ORDER_ITEMS — restores cancel stock derivation
  from order.items; oracle
  `test_f3_legacy_faces.py::test_legacy_with_reservations_cancel_releases_by_reservation_sku_id`
  must go RED on OSR1-F3-LEGACY-RESV-CANCEL-OK.
- M15_FULFILL_NULL_IDENTITY_GUARD_BYPASSED — oracle
  `test_fulfill_null_identity_controlled_409` must go RED on
  OSR1-F3-FULFILL-NULL-409.
- M16_RETURN_NULL_IDENTITY_GUARD_BYPASSED — oracle
  `test_return_null_identity_controlled_409` must go RED on
  OSR1-F3-RETURN-NULL-409.
Every mutation requires: pristine oracle GREEN, anchor count exactly one,
mutated source parses+compiles, rc=1, exact node, unique marker, no
pytest ERROR, byte+mode-identical restoration, control GREEN. The
complete 16-mutation run executes ONLY against the linear checkpoint
commit (never against uncommitted product bytes); its result matrix is
appended to this section after execution.

## Lock-order documentation synced to the actual implementation

`services/order_command_service.py` module docstring and
`order-state-r1/LOCK-ORDER.md` now state the real discipline: globally
sorted UUID (sku_id) stock locks, deduplicated, before any inventory
write; cancel derives refs from active reservations; the historical
cancel inverse order (reservations before stocks) is closed; the
nonexistent `test_lock_order_matrix.py` reference and the old
sku-code/per-item claims are removed. The static guard
`test_all_commands_share_prelock_strategy` now enforces the F2/F3
two-helper funnel: `_prelock_stocks` (confirm/fulfill/return) plus
`_prelock_reservation_stocks` (cancel, exactly one call site), with
every `_locked_stock_by_sku_id` call confined to the two helpers.

## Focused verification (author-executed, task-local PG16/Redis)

Environment: throwaway containers osr1-pg16 (127.0.0.1:17771) and
osr1-redis (127.0.0.1:17773); stack pytest 9.1.1 / pytest-asyncio 1.4.0
/ anyio 4.12.1 / hypothesis 6.168.0 / SQLAlchemy 2.0.45 / Python 3.12.3.
Evidence: `scratch/MPANGO_ORDER_STATE_AUTHORITY_R1_IMPLEMENTATION/evidence/F3/`.

1. `test_classifier.py` (pure): 10 passed.
2. `test_static_guards.py` + `test_classifier.py`: 17 passed.
3. `test_f3_legacy_faces.py` (real PG): 4 passed.
4. Full `tests/order_state_r1/` MINUS the three named
   CREDIT_HOLD_PERSISTENCE_DECISION_REQUIRED tests: 52 passed,
   3 deselected, rc=0
   (`2026-09-16T0816Z-f3-r1-suite-focused.txt`).

## Governance

`harness-governance/inventory/inventory.json` node ORDER-STATE-R1-001:
anchors re-pointed at the F3 lines (command sites, guards, cancel
reservation-stocks helper), the two new test files added, mutation
mapping extended to MUT-ORDER-STATE-R1-M1-M16, notes record the F3
legacy-face extension. Structural gate: re-run against the checkpoint
commit with baseline REQUIRED_PARENT; result appended below.

## STOP conditions honored

- Credit product code UNCHANGED; no migration; no aggregate-ownership
  inference; the three credit REDs are NOT waived and were NOT re-run
  (excluded from every authorized run).
- BACKEND_FULL_SUITE=NOT_RUN this round; no full-suite claim derives
  from the pre-799d F2 run.
- INDEPENDENT_REVIEW=NOT_STARTED.
CREDIT_HOLD_PERSISTENCE_DECISION_REQUIRED stands.

## F3 mutation matrix (post-checkpoint) — complete run PROVEN

Runner: `python3 tests/order_state_r1/run_mutations.py` (all 16) executed
against commit f4109f8e (11 pristine-gate node runs, 16 mutated oracle
runs, 16 control runs). Result: **ALL 16 PROVEN (strict semantic RED)**,
rc=0, zero FAILs
(`evidence/F3/2026-09-16T0954Z-f3-mutations-run2-final.txt`).
Every mutation: pristine oracle GREEN, anchor count exactly one, mutated
source ast.parse+compile, rc=1, exact named node, unique OSR1 marker, no
pytest ERROR, byte+mode-identical restore, worktree clean, control GREEN.

| Mutation | Oracle RED | Marker |
|---|---|---|
| M1_RESTORE_CRUD_STATUS_WRITER | static_guards::test_single_direct_status_writer | second direct order-status writer |
| M2_REMOVE_LOCKED_FRESH_REFRESH | freshness::test_confirm_after_external_cancel_uses_locked_fresh_state | OSR1-M2-ORACLE |
| M3_STALE_CANCEL_RELEASE_DECISION | concurrency::test_race_confirm_then_cancel_releases_reservations | OSR1-M3-ORACLE |
| M4_RESTORE_PRE_COMMIT_NOTIFICATION | notifications::test_rollback_produces_zero_sends | sends observed for a rolled-back request |
| M5_RESTORE_CONFIRMATION_ACCOUNTING | baseline::test_confirm_reserves_stock_and_credit_and_posts_no_ledger | confirmation posted ledger entries |
| M6_OPEN_PAID_CANCELLATION | baseline::test_paid_cancel_fail_closed_with_workflow_code | OSR1-M6-ORACLE |
| M7_BREAK_PARTIAL_ITEM_ROLLBACK | rollback_vectors::test_fulfill_fault_during_second_item_write_rolls_back_all | second per-item inventory write |
| M8_GENERIC_BYPASS | f1_faces::test_generic_transition_refuses_command_owned_targets | OSR1-M8-ORACLE |
| M9_FULFILL_NO_PRELOCK | prelock::test_fulfill_prelocks_all_stocks_before_first_write | OSR1-M9-ORACLE |
| M10_CLIENT_409_MAPPING_REMOVED | f1_faces::test_client_cancel_route_maps_domain_errors_409_direct | unmapped |
| M11_PARTIALLY_PAID_BYPASS | f1_faces::test_generic_refuses_partially_paid_on_confirmed | OSR1-M11-ORACLE |
| M12_NON_CANONICAL_PAYMENT_CALLER | static_guards::test_payment_command_single_caller_guard | non-canonical caller |
| M13_CROSS_COMMAND_LOCK_ORDER | prelock::test_cancel_prelocks_all_stocks_in_global_order | OSR1-M13-ORACLE |
| M14_CANCEL_STOCKS_FROM_ORDER_ITEMS | f3_legacy_faces::test_legacy_with_reservations_cancel_releases_by_reservation_sku_id | OSR1-F3-LEGACY-RESV-CANCEL-OK |
| M15_FULFILL_NULL_IDENTITY_GUARD_BYPASSED | f3_legacy_faces::test_fulfill_null_identity_controlled_409 | OSR1-F3-FULFILL-NULL-409 |
| M16_RETURN_NULL_IDENTITY_GUARD_BYPASSED | f3_legacy_faces::test_return_null_identity_controlled_409 | OSR1-F3-RETURN-NULL-409 |

Provenance note (retained verbatim in evidence): run1
(`2026-09-16T0932Z-f3-mutations-run1.txt`) at checkpoint 265cf6a7 proved
M1–M13 but M14/M15/M16 returned MARKER_MISSING — the mutated command's
ValueError (uuid.UUID on the NULL identity) re-raises through
ASGITransport(raise_app_exceptions=True) into the test, so the labeled
post-response asserts never executed. The repair commit f4109f8e wraps
the three action calls: a transport exception is converted to a labeled
AssertionError carrying the same unique marker (pristine flow unchanged,
4/4 F3 faces GREEN). A scoped pre-commit probe
(`2026-09-16T0953Z-f3-mutations-probe-m14-16.txt`) confirmed 3/3, and the
complete run above was then executed at f4109f8e.

## F3 final state

- Structural governance gate: PASS
  (`2026-09-16T0932Z-f3-structural-gate.txt`, baseline 998a549f,
  structural=PASS release=BLOCKED-in-structural-mode, rc=0).
- Exact changed paths vs REQUIRED_PARENT 998a549f: 13 files
  (`2026-09-16T1011Z-f3-exact-paths-vs-parent.txt`).
- Linear commits this round: 265cf6a7 -> f4109f8e -> (this matrix
  commit); no amend/rebase; not pushed.
- BACKEND_FULL_SUITE=NOT_RUN this round. The three credit
  CREDIT_HOLD_PERSISTENCE_DECISION_REQUIRED REDs remain excluded from
  every authorized run, NOT waived. INDEPENDENT_REVIEW=NOT_STARTED.
