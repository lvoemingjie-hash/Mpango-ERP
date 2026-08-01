# DC-12R1-S3-S2B-I2A-R1-Z Adversarial Source Review

## Verdict

`PASS_FOR_CTO_DC12R1_S3_S2B_I2A_SOURCE_REVIEW`

The extraction is behavior-preserving for the direct `pay_order` path, the
canonical service owns a complete, self-contained set of financial invariants
(no route-only financial check), the service never controls transaction
lifecycle, all financial mutations share one caller-supplied session, every
failure path rolls back atomically with no consumed idempotency state, and the
`force_completed` semantics cannot produce a pending payment. No stop condition
(route-only invariant, TOCTOU window, partial-write path, cross-tenant authority
gap, replay duplication, or inaccurate evidence) is triggered.

This is an independent, read-only source/contract review. No product or test
file was modified. Two review-only artifacts are added on a `reports/` branch.

## Scope Verification

- Target branch reviewed: `codex/dc12r1-s3-s2b-i2a-canonical-payment-service-2026-08-01`
- Verified target SHA: `d39f2eaa0ac55d7da4fc9b9d6ab3530199ffb8d5` (matches expected)
- Verified base SHA: `9528cb6de5f668ed09feb7a1eaa9aafaa537987d` (matches expected)
- Review branch/worktree created from base: `reports/dc12r1-s3-s2b-i2a-r1-zcode-review-2026-08-01` at `9528cb6d`

### Two-commit lineage confirmed

```
d39f2eaa feat(dc12r1-s3-s2b-i2a): extract canonical payment service        (parent: 1183611b)
1183611b docs(dc12r1-s3-s2b-i2a): checkpoint I1 complete and I2A active    (parent: 9528cb6d)
9528cb6d Merge DC-12R1-S3-S2B-I1 financial schema foundation               (BASE)
```

- Commit 1 (`1183611b`, docs-only): `docs/ai/CTO_CURRENT_OPS.md`, `docs/ai/PROJECT.md`
- Commit 2 (`d39f2eaa`, extraction): service, route refactor, new test, one legacy test fix, ledger entry

### Exact seven-file delta confirmed (`9528cb6d..d39f2eaa`)

- `A ai-ledger/product-ai/2026-08-01_dc12r1_s3_s2b_i2a_canonical_payment_service.md`
- `M backend/api/v1/orders.py`
- `A backend/services/canonical_payment_service.py`
- `M backend/tests/test_dc12r1_s1_r5_migration_preflight_exact_catalog.py`
- `A backend/tests/test_dc12r1_s3_s2b_i2a_canonical_payment_service.py`
- `M docs/ai/CTO_CURRENT_OPS.md`
- `M docs/ai/PROJECT.md`

No frontend, migration, permission, config, lockfile, deployment, or protected-ref
file is changed. `py_compile` passes for all four changed Python files.

## Service Inspection And Call Graph

`CanonicalPaymentService.confirm_payment` (canonical_payment_service.py:126-315)
is the single public entry point. The only production caller is
`pay_order` (orders.py:742), which calls it with `skip_prechecks=True`,
passing the already-locked order plus precomputed `target_state` and
`is_credit_collection`. No other production caller exists
(`grep -rln canonical_payment_service` -> only `api/v1/orders.py`).

### Call sequence inside the service (skip_prechecks=False path)

1. `repo.get_by_idempotency_key` (pre-lock replay/conflict)
2. `_get_order_by_id_for_update` -> `SELECT ... FOR UPDATE` on `order.id`, `is_deleted=False`
3. `repo.get_by_idempotency_key` (post-lock replay/conflict)
4. Status / remaining-balance / credit-exposure / overpayment / credit-rules / duplicate-transfer prechecks
5. `repo.create` (payment row)
6. `PaymentService._apply_outstanding_balance_delta` (receivable delta, when applicable)
7. `LedgerService.post_payment_received` (credit-collection ledger post, when applicable) **or**
   `OrderService(db).transition(...)` (state transition + transition-owned ledger entries)
8. `repo.update_cash_transfer_to_completed` (settle pending cash/transfer when order is PAID and `not force_completed`)
9. `repo.get_by_id` (re-fetch latest payment row for the result)

The `skip_prechecks=True` path skips steps 1-4 and uses the caller-supplied
locked order and computed state, then performs steps 5-9 unchanged.

## Transaction Lifecycle (Review Points 3, 6)

- `grep` for `commit|rollback|close|flush|AsyncSession(|create_async_engine|sessionmaker|begin()`
  in `canonical_payment_service.py` returns **no transaction-control verb**. The
  service only performs `db.execute(...)` reads/lock and one `db.refresh(order)`
  (line 286). Verified.
- `PaymentRepository` (`repositories/payment_repository.py`) defines
  `get_by_idempotency_key`, `get_by_transaction_id`, `get_by_id`,
  `count_order_payments`, `get_order_paid_total`, `get_order_credit_exposure`,
  `update_cash_transfer_to_completed`, `create` — none call
  `commit/rollback/close`. Verified.
- The request owns exactly one tenant session, created in
  `api/context/tenant.py:create_tenant_session` and finalized in
  `finalize_tenant_context` (commit on success, rollback on failure, close
  always). The route additionally calls `db.rollback()` defensively in every
  `except` branch.
- The service constructs `PaymentService()` (stateless), `OrderService(db)`
  (stores the same `db`), and `LedgerService(db)` (stores the same `db`). All
  downstream mutation helpers (`_apply_outstanding_balance_delta`,
  `OrderService.transition` -> `_post_ledger_entries`, `post_payment_received`)
  operate on the passed-in `db`. `OrderService.transition` calls `self.db.flush()`
  (not commit) and re-locks the order with `with_for_update()` (no-op reentrant
  row lock on the same session).

Conclusion: payment row, outstanding-balance delta, order transition,
transition-ledger entries, credit-collection ledger entry, and settlement update
all execute within the single caller-supplied transaction. The service cannot
commit, cannot roll back, and cannot open or substitute a session. This is
enforced structurally and proven by `test_service_does_not_commit_or_rollback_calls`
(test asserts `commit()`/`rollback()` raise `AssertionError`).

## Financial Invariant Tracing (Review Point 4)

The service's `skip_prechecks=False` branch (lines 146-252) is a complete,
self-contained copy of the route's prechecks. Every invariant below is enforced
**inside the service**, not only in the route:

| Invariant | Route (orders.py) | Service (skip_prechecks=False) |
|---|---|---|
| Idempotency replay (pre-lock) | 607-624 | 147-159 |
| Order lock `FOR UPDATE` + `is_deleted=False` | 626-634 (via `_get_order_by_id_for_update`) | 161-167 (own `_get_order_by_id_for_update`) |
| Idempotency replay (post-lock) | 638-655 | 169-181 |
| PAID order accepts only cash/transfer collection | 662-668 | 188-194 |
| Credit-collection exposure > 0 | 669-677 | 195-201 |
| Overpayment vs remaining exposure | 678-683 | 202-207 |
| Overpayment vs remaining balance | 687-693 | 211-217 |
| State must be CONFIRMED/PARTIALLY_PAID | 695-700 | 218-223 |
| Single credit payment per order | 702-711 | 225-231 |
| Credit rejects split tender | 712-717 | 232-237 |
| Credit amount must equal order total | 718-723 | 238-243 |
| Duplicate transfer `transaction_id` | 732-739 | 247-252 |

Retailer/wholesaler ownership is established by the **tenant-scoped session**
(`get_tenant_db_session` -> `SET LOCAL search_path`), exactly as the route's own
`_get_order_by_id_for_update` does; neither adds an explicit `wholesaler_id`
filter. The service derives `retailer_id`/`wholesaler_id` for the payment row
and delta from the locked `order` object (lines 263, 277-278, 291-292) — no
request-supplied authority is accepted (report claim verified).

## Route-Only Invariant Assessment (Review Point 5) — No P1

This is the central adversarial question. The service exposes two call modes:

- `skip_prechecks=True` (used by `pay_order`): trusts caller-supplied locked
  order and computed state. This is safe **only** because the caller (`pay_order`)
  has already performed the identical prechecks under the same lock within the
  same transaction. The lock is held for the duration; no TOCTOU window exists
  between the route's prechecks and the service's mutation because they share the
  session and the `FOR UPDATE` row lock.
- `skip_prechecks=False` (default; intended for the future declaration
  confirmation path): the service performs the **full** precheck sequence itself,
  including the order lock and all overpayment/idempotency/duplicate checks.

A future declaration-confirmation caller using `skip_prechecks=False` (or
defaulting, since `skip_prechecks` defaults to `False`) **cannot bypass any
financial invariant**: every check listed in the table above runs inside the
service before any mutation. There is no financial invariant that lives only in
the route. Therefore no P1/STOP classification applies.

The `locked_order`/`target_state`/`is_credit_collection`/`skip_prechecks`
parameters are a deliberate optimization for the route to avoid recomputing work
it just did; they are guarded by a hard `ValueError` if `skip_prechecks=True` is
requested without all three precomputed inputs (line 142-144).

## Failure Path And Atomicity (Review Point 7)

Four mutation stages can fail after a partial write: after `create`, after
`_apply_outstanding_balance_delta`, after `transition`, after
`update_cash_transfer_to_completed`. The test
`test_service_failures_after_mutation_stages_rollback_all_effects` patches each
stage to raise `RuntimeError` immediately after the real operation succeeds, then
asserts the order/ledger/payment/receivable snapshot is byte-identical to the
pre-call snapshot after rollback. All four stages roll back cleanly.

Idempotency state is never consumed on failure: `repo.create` is the only write
that inserts the idempotency-keyed row. If `create` itself fails (e.g.
`IntegrityError` on a unique constraint), no row exists, so no key is consumed;
the route's `except IntegrityError` block re-reads by idempotency key and replays
or conflicts. If any later stage fails, the transaction rolls back, which also
reverts the payment insert, freeing the idempotency key. There is no path where a
failed payment consumes an idempotency key while leaving no committed payment.

`CanonicalPaymentMutationHttpError` wraps only `HTTPException`s raised by the
post-create mutation helpers, ensuring the route rolls back and re-raises them
rather than committing a half-applied mutation. Domain exceptions
(`InvalidStateTransitionError`, `OrderInvariantViolation`) are **not**
`HTTPException` subclasses (verified: both subclass `Exception` directly), so they
propagate unwrapped to the route's `except (InvalidStateTransitionError, ...)`
handler (orders.py:790), preserving base semantics.

## force_completed Semantics (Review Points 8, 9)

`payment_status` computation (lines 254-258):

```python
payment_status = (
    "completed"
    if force_completed or is_credit_collection
        or (method == "transfer" and target_state == OrderState.PAID)
    else "pending"
)
```

- **`force_completed=False` (the only value `pay_order` passes, orders.py:750):**
  identical to the base route. `is_credit_collection` -> completed; transfer to
  PAID -> completed; cash/transfer partial -> pending; then the
  `update_cash_transfer_to_completed` settlement (guarded by
  `not force_completed`, line 303) runs when the order actually reaches PAID.
  Direct pay_order behavior is preserved (proven by
  `test_service_cash_partial_and_final_matches_route_outcomes`,
  `test_service_transfer_pending_then_completed_matches_route_outcomes`, and the
  credit-collection parity test).
- **`force_completed=True` (future declaration path only):** `payment_status` is
  always `"completed"` regardless of method/target_state. Proven by
  `test_service_force_completed_cannot_create_pending_payment`, which pays a
  partial transfer of 40 against a 100 order with `force_completed=True` and
  asserts `payment_record["status"] == "completed"`, `completed_count == 1`,
  `completed_total == 40`. A pending payment cannot be produced under
  `force_completed=True`. The auto-settlement step is correctly skipped under
  `force_completed=True` (already completed by construction).

## API Compatibility (Review Point 13)

`POST /api/v1/orders/{order_id}/pay` response contract is unchanged:

- HTTP status: 200 OK (`OrderActionResponse`, unchanged decorator).
- Body: `success=True`; `data` keys identical (`order_id`, `status`,
  `payment_id`, `payment_amount`, `payment_method`) via the unchanged
  `_payment_response_data`.
- `message`: happy path returns `"Payment recorded and order updated"` exactly as
  base. The new ternary (`"Payment replayed" if result.replayed else "Payment
  recorded and order updated"`, orders.py:804) cannot return `"Payment replayed"`
  in the skip_prechecks path because the service returns `replayed=False` for all
  non-replay confirmations (line 313); replays are pre-empted by the route's own
  early replay (orders.py:620/651) and the IntegrityError replay (orders.py:772)
  before the success return. The replay message itself (`"Payment replayed"`) was
  already part of the base response shape via `_idempotency_replay_response`.

Error status codes/codes are preserved verbatim: `400 PAYMENT_EXCEEDS_REMAINING`,
`400 CREDIT_*`, `404 ORDER_NOT_FOUND`, `409 ORDER_ALREADY_PAID`,
`409 INVALID_STATE_TRANSITION`, `409 DUPLICATE_TRANSFER_REFERENCE`,
`409 DUPLICATE_CREDIT_PAYMENT`, `409 IDEMPOTENCY_KEY_CONFLICT`.

## Receipt Allocation (Review Point 10)

Receipt allocation is **not implemented** and is **not claimed** to be:

- `repo.create` inserts `order_id, retailer_id, transaction_id, idempotency_key,
  amount, method, status, ...` and does **not** set `receipt_number`
  (verified: no `receipt_number` reference in `create`,
  `canonical_payment_service.py`, `orders.py` pay path).
- Migration `037` creates the `payments.receipt_number` column,
  `payment_declarations`, and `receipt_sequences` tables (schema foundation only);
  no runtime/allocation code consumes them in I2A.
- The ledger entry (`ai-ledger/product-ai/...canonical_payment_service.md`) makes
  zero claims about receipt allocation; it explicitly states I2A adds no
  declaration route or mutation, and PROJECT.md lists receipt/declaration runtime
  as pending (I2B/I2C).

No report claim exceeds actual behavior.

## Legacy Migration Test Change (Review Point 11)

`test_actual_alembic_035_to_036_failure_rolls_back_then_repaired_upgrade_noops`
was updated: `run_alembic_upgrade(config, "head")` -> `run_alembic_upgrade(config, REV_036)`
(three sites), and two `_script_heads(config) == [REV_036]` assertions were removed.

This is a **necessary, correct fix**, not assertion weakening:

- `037_payment_declarations_schema` is now the sole head
  (`revision="037_payment_declarations_schema"`, `down_revision="036_retailer_mvp_identity"`).
  REV_036 is no longer head, so the original `"head"` target and the
  `_script_heads == [REV_036]` assertions would now fail.
- The test is specifically scoped to the 035->036 rollback/no-op scenario (per
  its name). Pinning the upgrade target to `REV_036` keeps the test focused on
  exactly that transition.
- The meaningful invariant — the catalog fingerprint equality
  (`after_noop_payload == before_noop_payload`) and the rollback fingerprint
  equality (`after_failure_payload == before_payload`) — is fully preserved.
  `_current_revision == REV_036` assertions are retained.
- 037 coverage is not reduced: 037 has its own dedicated S2B-I1 suites, which the
  ledger reports as green in the regression bundle.

## Test Runtime Behavior (Review Point 12)

The new suite is runtime-integration, not source inspection or mock-only:

- It imports `_bootstrap_minimal_tenant_schema`, `_seed_confirmed_order`,
  `_set_search_path`, `_snapshot`, `_pay_in_new_session` from the existing
  DC-11D replay/concurrency suite and exercises real PostgreSQL tenant schemas
  via `AsyncSessionLocal`.
- Parity tests (`test_service_cash_partial_and_final_matches_route_outcomes`,
  `test_service_transfer_pending_then_completed_matches_route_outcomes`,
  `test_service_credit_collection_reduces_outstanding_balance_like_route`) run
  the same scenario through both `pay_order` and `CanonicalPaymentService` on
  separate orders in the same session and assert the full `_snapshot`
  (order_status, payment_count, payment_total, completed_count, completed_total,
  ledger_count, ledger_sum, outstanding_balance) is equal between route and
  service.
- Behavioral tests cover: duplicate transaction_id (exact 409 code), idempotent
  replay (one financial result), overpayment rejection (exact 400 code),
  `force_completed` cannot create pending, cross-tenant same-key isolation
  (separate schemas, shared key -> both succeed independently), and four-stage
  failure atomicity (after-create/delta/transition/complete each rollback cleanly).
- One focused mock-based test (`test_route_uses_canonical_payment_service_...`)
  verifies the route invokes the service with `force_completed=False` and the
  default skip-prechecks contract; this is a structural seam test, complementing
  (not replacing) the runtime parity tests.

Note on independent runtime re-verification: the local Poetry virtualenv in this
review environment is non-functional (the venv `python.exe` resolves to the
system Python and `Lib/site-packages` is empty; `asyncpg`/`sqlalchemy` are not
importable outside `poetry run`, and `poetry run` child stdio is detached in this
Git Bash shell, producing empty output). Independent re-execution of the suite
against the available PostgreSQL 16 container was therefore not achievable in
this environment. The verdict above rests on complete static analysis of source,
tests, contracts, and docs, plus confirmed `py_compile` of all changed files.

## Docs And Ledger Consistency (Review Point 14)

`docs/ai/PROJECT.md` and `docs/ai/CTO_CURRENT_OPS.md` updates are factually
consistent with the repository state:

- Migration head updated `036` -> `037_payment_declarations_schema` — matches
  `alembic/versions/037_payment_declarations_schema.py` (verified sole head).
- Accepted product merge updated `0f9d259b` -> `9528cb6d` — matches the verified
  base of this branch.
- I1 marked merged at `9528cb6d`; I2A marked active; I2B/I2C/frontend/runtime
  marked pending — matches the delivery plan and the absence of any declaration
  route/mutation in this slice.
- CTO_CURRENT_OPS "What Is Not Closed" updated from "Retailer payment declaration
  is not implemented" to "Canonical payment transaction service extraction is not
  yet complete" — accurately reflects I2A-in-progress.

The ledger entry (`ai-ledger/product-ai/2026-08-01_..._canonical_payment_service.md`)
claims are accurate and conservative:
- "Service never commits, rolls back, closes, or replaces the caller session" — verified.
- "No request-supplied wholesaler or retailer authority exists in the service" — verified.
- "`force_completed=True` is supported in the service for later declaration use,
  but direct `pay_order` always calls it with `force_completed=False`" — verified.
- "No declaration HTTP route or declaration mutation was added in I2A" — verified.
- Migration test fix rationale ("now that head is 037") — verified.

No claim in the report or docs exceeds actual behavior.

## Findings Summary

No P1/P2 defects. Two informational observations (neither triggers a stop
condition):

1. **INFO — venv hygiene (environment, not target branch):** the local Poetry
   venv is non-functional in this review environment, preventing independent
   runtime re-execution of the suite. This is an environment limitation of the
   review, not a defect in the reviewed branch. The verdict rests on static
   analysis; the branch's own GREEN evidence (3120 passed on two fresh DBs) and
   the runtime-integration design of the new tests support the conclusion.
2. **INFO — skip_prechecks trust boundary:** the `skip_prechecks=True` fast path
   trusts caller-supplied `target_state`/`is_credit_collection`. This is safe
   today (sole caller is `pay_order`, which precomputes under the same lock) and
   is correctly defaulted to `False` for all other/future callers, so the
   default path enforces every invariant internally. Future callers must not call
   `skip_prechecks=True` without performing equivalent prechecks under the same
   held lock; consider documenting this precondition in the service docstring as a
   guardrail (no code change required for this slice).

## Stop Conditions Check

| Stop condition | Triggered? | Evidence |
|---|---|---|
| Route-only invariant | No | Full invariant set duplicated in service `skip_prechecks=False` branch (table above) |
| TOCTOU window | No | Order `FOR UPDATE` lock held across prechecks+mutation in one session |
| Partial-write path | No | All stages share one transaction; four-stage failure atomicity test passes |
| Cross-tenant authority gap | No | Tenant session search_path + retailer/wholesaler derived from locked order |
| Replay duplication | No | Replay returns existing record without re-mutating; idempotency never consumed on failure |
| Inaccurate evidence | No | Report/docs claims verified against source; receipt allocation correctly unclaimed |

## Verdict

`PASS_FOR_CTO_DC12R1_S3_S2B_I2A_SOURCE_REVIEW`
