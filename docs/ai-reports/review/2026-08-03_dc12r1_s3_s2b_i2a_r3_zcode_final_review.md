# DC-12R1-S3-S2B-I2A-R3-Z Independent Final Source Merge Review

## Verdict

`PASS_FOR_CTO_DC12R1_S3_S2B_I2A_R3_ZCODE_FINAL_MERGE_REVIEW`

I2A-R3 (canonical amount integrity boundary guard) is **safe for controlled
merge**. The guard is implemented at the correct boundary (the very first
statement of `CanonicalPaymentService.confirm_payment`, before any database
read, write, idempotency lookup, lock acquisition, or mutation, regardless of
the `skip_prechecks` flag), rejects all five required invalid-amount classes
(negative, zero, Decimal NaN, +Infinity, -Infinity) with a controlled HTTP 400
`INVALID_PAYMENT_AMOUNT`, does not take transaction ownership, and preserves the
existing direct `pay_order` behavior for valid positive payments. No invalid
amount can reach any financial sink because `confirm_payment` is the single
live production write path and the guard precedes every downstream call. No
confirmed financial-integrity defect was found, so no `STOP_AND_REPORT_CTO`
condition is triggered.

This is an independent, read-only review. No product or test file was modified.
The I2A source branch was not edited, committed to, pushed, rebased, or
force-pushed. `product-dev-recovered` was not merged. I2B was not started. Two
review-only artifacts are added on the report branch.

### Evidence-truthfulness note (INFO, not a defect)

The R3 boundary report (`ai-ledger/product-ai/...r3_canonical_amount_integrity_boundary.md`,
"Changed-Scope Proof" table) records the service delta as "+6" lines, while
`git diff --numstat` reports **7** added lines for
`backend/services/canonical_payment_service.py`. The +1 difference is the
trailing blank separator line that follows the 6-line guard block; the report's
"6 lines" refers to the 6 logical guard lines. This is a cosmetic
documentation imprecision (off-by-one separator), not a correctness or
financial-integrity issue. All other quantitative claims in the R3 report
(full-suite 3134/48/15/0/0 twice; 3127 R2 baseline + 7 R3 tests; H4 baseline
3116 + 11 I2A = 3127; 11 original parity tests + 7 R3 test nodes = 18) are
internally consistent and match the Git and test-file evidence.

---

## Reviewer, Role, and Hard-Rule Compliance

- **Reviewer:** ZCode (independent, read-only).
- **Role:** Independent reviewer; no fixes implemented; I2A source branch not
  modified.
- **Hard rules:**
  1. `git fetch --all --prune` executed first — done (exit 0).
  2. All three expected SHAs verified exactly — done (see below).
  3. Clean isolated worktrees used — done (detached review worktree at target;
     separate report worktree from baseline).
  4. I2A source branch not edited/committed/pushed/rebased/force-pushed —
     confirmed (no write to `codex/dc12r1-...-2026-08-01`).
  5. `product-dev-recovered` not merged — confirmed.
  6. I2B not started — confirmed.
  7. Report branch contains only the review report and findings CSV — confirmed.
  8. No confirmed financial-integrity defect — confirmed (no STOP condition).

---

## SHAs Verified (post `git fetch --all --prune`)

| Item | Expected | Observed | Match |
|------|----------|----------|-------|
| Baseline `origin/product-dev-recovered` | `45899145e07c1c21424f2f32904965b49b689e1f` | `45899145e07c1c21424f2f32904965b49b689e1f` | YES |
| Target `origin/codex/dc12r1-s3-s2b-i2a-canonical-payment-service-2026-08-01` | `f7bd75c1d9095ce796ba4777bb738bfb4419fc54` | `f7bd75c1d9095ce796ba4777bb738bfb4419fc54` | YES |
| R3 predecessor | `72a17a60fa119f0d874eb7b7c41f24c0ea5bdafc` | exists as commit; parent of target | YES |

Method: `git rev-parse`, `git cat-file -t`, and `git rev-list --parents -n 1`.

---

## A. Lineage and Scope

### A1. Baseline is an ancestor of target — PROVEN

```
git merge-base --is-ancestor 45899145 f7bd75c1   =>  YES
```

### A2. R3 predecessor is an ancestor of target — PROVEN

```
git merge-base --is-ancestor 72a17a60 f7bd75c1   =>  YES
git rev-list --parents -n 1 f7bd75c1 =>
  f7bd75c1 72a17a60   (single parent — clean linear R3 increment)
```

The R3 commit `f7bd75c1` ("fix(dc12r1-i2a-r3): canonical amount integrity
boundary guard", author "Independent Runtime Gate (lubuntu)",
2026-08-03T00:34:30+08:00) has exactly one parent `72a17a60` (the R2
reconciliation commit). No merge commit was introduced by R3.

### A3. R3 delta is exactly the four expected files — CONFIRMED

`git diff --name-status 72a17a60..f7bd75c1`:

```
M  ai-ledger/product-ai/2026-08-02_dc12r1_i2a_r2_reconciliation_with_h4_baseline.md
A  ai-ledger/product-ai/2026-08-03_dc12r1_i2a_r3_canonical_amount_integrity_boundary.md
M  backend/services/canonical_payment_service.py
M  backend/tests/test_dc12r1_s3_s2b_i2a_canonical_payment_service.py
```

This matches the mandated R3 file set exactly. The R2 doc modification is the
+1/-1 evidence correction (placeholder "To be filled" replaced by the actual
changed-scope count); the R3 boundary doc is newly added.

R3 numstat:

```
 1   1  ai-ledger/.../2026-08-02_..._r2_reconciliation_with_h4_baseline.md
141   0  ai-ledger/.../2026-08-03_..._r3_canonical_amount_integrity_boundary.md
 7   0  backend/services/canonical_payment_service.py
161   0  backend/tests/test_dc12r1_s3_s2b_i2a_canonical_payment_service.py
```

### A4. No migration/frontend/config/permission/dependency/lockfile/deployment change — CONFIRMED

Category grep across the R3 delta (`72a17a60..f7bd75c1`) and the full candidate
delta (`45899145..f7bd75c1`) for `migration|alembic|frontend|\.vue|\.tsx|
\.jsx|docker|compose|k8s|nginx|\.yaml|\.yml|\.toml|\.ini|\.env|requirements|
pyproject|poetry|package-lock|Pipfile|setup\.py|constraints` returned **no
matches**. The only Alembic reference in the R3 report is the read-only "sole
head" assertion (`037_payment_declarations_schema`), which is a verification,
not a migration file change.

### A5. Full candidate delta vs baseline is expected; no unrelated file — CONFIRMED

`git diff --name-status 45899145..f7bd75c1` (5 commits: I2A R1 + R2 merge +
R2 docs + R3):

```
A  ai-ledger/product-ai/2026-08-01_dc12r1_s3_s2b_i2a_canonical_payment_service.md
A  ai-ledger/product-ai/2026-08-02_dc12r1_i2a_r2_reconciliation_with_h4_baseline.md
A  ai-ledger/product-ai/2026-08-03_dc12r1_i2a_r3_canonical_amount_integrity_boundary.md
M  backend/api/v1/orders.py
A  backend/services/canonical_payment_service.py
A  backend/tests/test_dc12r1_s3_s2b_i2a_canonical_payment_service.py
M  docs/ai/CTO_CURRENT_OPS.md
M  docs/ai/PROJECT.md
```

This is the complete, expected I2A scope: the canonical service + route
refactor + tests (R1), H4 reconciliation docs (R2), and the amount guard (R3).
No unrelated file entered through reconciliation. The H4 files brought in by the
R2 merge are byte-identical to the baseline (per the R2 report and confirmed by
the merge being `--no-ff` clean with no manual conflict resolution).

---

## B. Amount-Integrity Boundary

Guard under review (`backend/services/canonical_payment_service.py:142-147`),
the very first statement of `confirm_payment`:

```python
if amount.is_nan() or amount.is_infinite() or amount <= 0:
    raise _payment_error(
        status.HTTP_400_BAD_REQUEST,
        "INVALID_PAYMENT_AMOUNT",
        "Payment amount must be a positive finite number",
    )
```

### B1. Validation occurs before every DB read/write/lookup/lock/mutation — PASS

The guard is at lines 142-147, before the first DB operation in either branch:
the idempotency lookup `self._repo.get_by_idempotency_key` (line 155, only when
`skip_prechecks=False`) and the order lock `_get_order_by_id_for_update` (line
168). When `skip_prechecks=True`, no new DB read occurs in the precheck branch
(the caller supplied the already-locked order). All mutations
(`self._repo.create` line 267, `_apply_outstanding_balance_delta` 282/296,
`order_service.transition` 302, `ledger.post_payment_received` 288,
`update_cash_transfer_to_completed` 311) occur after line 261 and are therefore
unreachable while the guard can fire.

### B2. Guard rejects all five invalid classes — PASS (empirically verified)

The exact production predicate was executed under Python 3.12 against every
required case:

| Input | Result | Expected |
|-------|--------|----------|
| `Decimal("-1.00")` (negative) | REJECTED(400) | rejected |
| `Decimal("0")` (zero) | REJECTED(400) | rejected |
| `Decimal("NaN")` | REJECTED(400) | rejected |
| `Decimal("Infinity")` (+Inf) | REJECTED(400) | rejected |
| `Decimal("-Infinity")` (-Inf) | REJECTED(400) | rejected |
| `Decimal("100.00")` (valid) | PASS | pass |
| `Decimal("0.01")` (valid tiny) | PASS | pass |

**Short-circuit robustness (verified):** `Decimal("NaN") <= 0` in isolation
raises `decimal.InvalidOperation`. The guard is safe because `or` short-circuits:
`amount.is_nan()` returns `True` for NaN, so `amount <= 0` is never evaluated for
NaN; `amount.is_infinite()` returns `True` for both infinities, so the
comparison is never reached for them either. No exception leaks for any case.
This is precisely why the test `test_r3_nan_and_infinity_rejected_without_500`
asserts a controlled 400 (not a 500 from an uncaught `InvalidOperation`).

### B3. Guard applies with `skip_prechecks=False` and `True` — PASS

The guard is positioned **before** the `if skip_prechecks:` branch (line 149),
so it executes unconditionally for both modes. Proven by
`test_r3_skip_prechecks_cannot_bypass_amount_guard`, which calls
`confirm_payment(skip_prechecks=True, amount=Decimal("-50.00"), ...)` with an
`AsyncMock` db (so any DB touch would itself fail) and asserts HTTP 400
`INVALID_PAYMENT_AMOUNT`. This is the critical case because the production route
`pay_order` always calls `confirm_payment(..., skip_prechecks=True)` (line 754).

### B4. Rejection is controlled HTTP 400 `INVALID_PAYMENT_AMOUNT` — PASS

`_payment_error(status.HTTP_400_BAD_REQUEST, "INVALID_PAYMENT_AMOUNT", ...)`
raises an `HTTPException` with `status_code=400` and
`detail={"code": "INVALID_PAYMENT_AMOUNT", "message": ...}`. Confirmed in every
R3 negative test via `exc_info.value.status_code == 400` and
`exc_info.value.detail["code"] == "INVALID_PAYMENT_AMOUNT"`.

### B5. No invalid amount can reach any financial sink — PASS

Sinks enumerated by the task, with reachability from the guarded entry:

| Sink | Location | Reachable with invalid amount? |
|------|----------|-------------------------------|
| `PaymentRepository.create` | service:267 | No — guard raises first |
| outstanding-balance mutation (`_apply_outstanding_balance_delta`) | service:282,296 | No |
| `OrderService.transition` | service:302 | No |
| ledger posting (`post_payment_received`) | service:288 | No |
| payment completion update (`update_cash_transfer_to_completed`) | service:311 | No |

`confirm_payment` is the single live production write path: GitNexus (re-indexed
at the target commit, 14,329 nodes / 44,363 edges) reports the only production
caller of `confirm_payment` is `pay_order` (`backend/api/v1/orders.py:742`).
The legacy `backend/crud/order.py:pay_order` (`crud_pay_order`) is imported by
the route but **never invoked** (grep confirms zero call sites) — it is residual
dead code, not an alternate payment path. There is no other production caller
that could bypass the guard.

### B6. Valid positive payments preserve existing direct `pay_order` behavior — PASS

For any `amount > 0` that is finite and non-NaN, the guard predicate is `False`,
so control flow proceeds unchanged into the existing precheck and mutation
logic. The 11 original I2A parity tests (cash partial/final, transfer
pending/completed, credit collection, idempotent replay, overpayment, force
completed, cross-tenant, failure rollback) exercise valid positive amounts and
are unchanged by R3 (their source lines 78-550 are byte-identical to the R2
state). The R3 retryable test
(`test_r3_failed_attempt_leaves_transaction_retryable`) further proves a valid
`Decimal("100.00")` payment succeeds on the same order/session immediately after
a rejected invalid attempt, reaching `order_state == "paid"`.

### B7. Guard does not commit, rollback, or take transaction ownership — PASS

The guard body contains only `raise _payment_error(...)`; there is no
`db.commit`, `db.rollback`, `db.close`, `db.flush`, or session substitution.
The HTTPException propagates to the caller, which owns the session. In the
route, the exception is caught by `except Exception:` (line 797), which performs
`await db.rollback()` (route-owned) and re-raises the original 400. The service
itself never takes transaction ownership, consistent with the I2A-R1 invariant
(`test_service_does_not_commit_or_rollback_calls`).

---

## C. Test Authenticity

File: `backend/tests/test_dc12r1_s3_s2b_i2a_canonical_payment_service.py`.

### C1. All seven R3 test nodes reviewed — PASS

Five R3 test functions; one is parametrized over three values, yielding **7 test
nodes** (matches the R3 doc table):

1. `test_r3_negative_cash_amount_rejected_with_zero_mutation` — negative cash, real DB snapshot.
2. `test_r3_zero_amount_rejected` — zero, 400 code assertion.
3. `test_r3_nan_and_infinity_rejected_without_500[nan]` — NaN.
4. `test_r3_nan_and_infinity_rejected_without_500[pos_inf]` — +Infinity.
5. `test_r3_nan_and_infinity_rejected_without_500[neg_inf]` — -Infinity.
6. `test_r3_skip_prechecks_cannot_bypass_amount_guard` — skip_prechecks=True.
7. `test_r3_failed_attempt_leaves_transaction_retryable` — same-session retry.

### C2. Negative test proves payment/order/balance/ledger state unchanged — PASS

`test_r3_negative_cash_amount_rejected_with_zero_mutation` takes a `_snapshot`
**before** and **after** the rejected call and asserts `after == before`.
`_snapshot` (imported from the DC11D integration helper) reads **real database
state** across all financial dimensions: `order_status`, `payment_count`,
`payment_total`, `completed_count`, `completed_total`, `ledger_count`,
`ledger_sum`, and `outstanding_balance`. The equality assertion therefore
proves zero mutation to payment rows, order status, outstanding balance, and
ledger entries.

### C3. `skip_prechecks` cannot bypass the guard — PASS

`test_r3_skip_prechecks_cannot_bypass_amount_guard` passes `skip_prechecks=True`
with a negative amount and an `AsyncMock` db, then asserts 400
`INVALID_PAYMENT_AMOUNT`. Because the db is a mock, reaching the precheck branch
would not perform a real lookup, but the guard fires before that branch, so the
test isolates the guard from the precheck path.

### C4. NaN and Infinity produce controlled 400, not 500 — PASS

`test_r3_nan_and_infinity_rejected_without_500[nan|pos_inf|neg_inf]` asserts
`exc_info.value.status_code == 400` and
`detail["code"] == "INVALID_PAYMENT_AMOUNT"` for each of NaN, +Infinity,
-Infinity. Combined with the empirical Decimal predicate verification (B2),
this confirms no uncaught `InvalidOperation` escapes as a 500.

### C5. Same caller transaction remains usable after rejection — PASS

`test_r3_failed_attempt_leaves_transaction_retryable` issues a rejected
`Decimal("-1.00")` call on `async_session`, then **on the same session** issues
a valid `Decimal("100.00")` call that succeeds and reaches `order_state ==
"paid"` with `payment_count == 1` and `ledger_count == 2`. This proves the guard
leaves the caller's transaction usable (no poisoned session state).

### C6. Eleven original I2A parity tests unchanged and green — PASS

The 11 original tests (lines 78-550) are byte-identical to their R2 state: the
R3 diff adds only lines after the previous end-of-file (the new R3 block starts
at line 664+, after the prior last test). They remain in force. The R3 report
records the focused I2A gate as "18 passed" (11 original + 7 R3); the
Lubuntu full-suite evidence (3134 passed) is consistent with 11 original parity
tests remaining green (3127 R2 baseline + 7 R3).

### C7. No skip/xfail/deselect/weakened-assertion/mock-only substitution — PASS

- No `pytest.mark.skip`, `xfail`, `--deselect`, or `-k` filter appears in or
  targets the R3 tests.
- The four DB-backed R3 tests (`negative`, `zero`, `nan/inf` ×3, `retryable`)
  use the real `async_session` fixture and real `_seed_confirmed_order` /
  `_snapshot` helpers (DB-backed, not mocks).
- Only `test_r3_skip_prechecks_cannot_bypass_amount_guard` uses `AsyncMock`/`SimpleNamespace`,
  and this is legitimate: it isolates the guard from the precheck branch (the
  test's purpose is to prove the guard fires *before* any DB work, so a mock db
  is the correct way to ensure no DB dependency exists in that path). The
  financial behavior itself is asserted, not mocked away.
- Assertions assert concrete financial facts (`status_code == 400`,
  `detail["code"]`, `after == before`, `order_state == "paid"`,
  `payment_count == 1`, `ledger_count == 2`). No `assert True` or
  weakened/comparative assertion is present.

### C8. Runtime execution of the full I2A file — NOT EXECUTED (environment blocked)

The complete I2A test file requires a PostgreSQL 16 + Redis 7 stack
(`conftest.py` resolves `TEST_DATABASE_URL` / builds a Postgres URL; tests use
`AsyncSessionLocal` and tenant schemas). The review host is Windows with only a
non-project Python 3.12 that has **no `pytest`** installed
(`No module named pytest`), and no project virtualenv or live database is
available. Per the task's explicit instruction ("Do not claim runtime execution
if blocked"), I do **not** claim to have executed the suite.

In lieu of execution, I verified the test logic by static review (C1-C7) and
verified the guard's Decimal semantics empirically under the available Python
3.12 (B2). The reported runtime totals (18 I2A tests; full-suite 3134/48/15/0/0
twice) are taken from the R3 boundary doc and cross-checked for internal
arithmetic consistency (D4-D5) but were not reproduced on this host.

---

## D. Wider Compatibility

### D1. `pay_order` and `CanonicalPaymentService` callers (GitNexus) — PASS

GitNexus (re-indexed at the target commit) `context` and `impact`:

- `confirm_payment` incoming production caller: `pay_order`
  (`backend/api/v1/orders.py:742`) — the **only** production caller. Other
  incoming edges are test functions.
- `confirm_payment` outgoing: `order_service.transition`,
  `ledger_service.post_payment_received`, `_payment_error`,
  `payment_repository` methods, `_get_order_by_id_for_update`,
  `_get_order_for_payment_record`, `_latest_payment_record`, `_replay_result`,
  `_same_payment_request`, `_payment_mapping_or_none`, `_idempotency_conflict`,
  `_duplicate_transfer_reference`. All financial sinks are downstream of the
  guard.
- `pay_order` (route) is an HTTP entry point (0 upstream callers). The CRUD
  `pay_order` (`backend/crud/order.py:392`) has **0 callers** (dead/residual).

### D2. Effective financial blast radius — treated as HIGH — PASS (by design)

GitNexus `impact confirm_payment` reports `risk: LOW` (1 direct caller, 0
processes affected). Per the task instruction, the effective financial blast
radius is treated as **HIGH** regardless, because `confirm_payment` mutates
payments, outstanding receivable balance, order state, and ledger entries.
The HIGH rating is the basis for the exhaustive boundary analysis in Section B;
the guard's correctness is what makes a HIGH-blast-radius change safe.

### D3. H4 reconciliation unchanged; target includes baseline 45899145 — PASS

- A1 proves `45899145` is an ancestor of `f7bd75c1`.
- The R2 reconciliation doc references baseline `45899145` consistently and
  states the `--no-ff` merge of `origin/product-dev-recovered@45899145` was clean
  with H4 files byte-identical to the baseline. The R3 commit did not touch the
  H4 reconciliation logic or any H4 file.

### D4. Two Lubuntu full-suite results internally consistent — PASS

R3 report records two independent fresh PG16 + Redis7 runs, both identical:

| Metric | Run A | Run B |
|---|---:|---:|
| Passed | 3134 | 3134 |
| Skipped | 48 | 48 |
| XFailed | 15 | 15 |
| Failed | 0 | 0 |
| Errors | 0 | 0 |

Internally consistent (identical across two runs; zero failures/errors). The 48
skipped and 15 xfailed are unchanged from the H4 baseline per the R2 report,
indicating no test-contract regression.

### D5. Report arithmetic and changed-file claims match Git evidence — PASS (one INFO)

- R3 = R2 baseline (3127) + 7 new R3 tests = 3134. ✓
- R2 = H4 baseline (3116) + 11 I2A tests = 3127. ✓
- 11 original parity + 7 R3 = 18 I2A tests. ✓
- R3 changed-file set matches `git diff --name-status 72a17a60..f7bd75c1`
  exactly (4 files). ✓
- Full candidate delta vs baseline = 8 files, matching the expected I2A scope. ✓
- R2 doc "6 implementation/status files plus this R2 report, total 7" matches
  `git diff --name-only 45899145..72a17a60` (= 7 files, including the R2
  report itself). ✓
- **INFO:** R3 doc "Changed-Scope Proof" table lists the service delta as "+6"
  while `git diff --numstat` reports **7** added lines. The +1 is the trailing
  blank separator line after the 6 logical guard lines. Cosmetic documentation
  imprecision; no correctness or financial-integrity impact.

---

## Quality Gates

| Gate | Method | Result |
|------|--------|--------|
| `git diff --check` (R3 delta) | `git diff --check 72a17a60..f7bd75c1` | clean (exit 0) |
| `git diff --check` (full delta) | `git diff --check 45899145..f7bd75c1` | clean (exit 0) |
| Mojibake scan | grep for U+FFFD / `Ã` / `â€` / `ï¿½` and non-ASCII in all 4 R3 files | clean (0 non-ASCII) |
| Scoped pre-commit | `pre-commit run --files <4 R3 files>` | all Passed (trailing-ws, eof, yaml n/a, large-files, detect-secrets) |
| Scoped detect-secrets | `detect-secrets scan <4 files> --baseline .secrets.baseline` | exit 0 (no new secrets) |
| GitNexus context/impact | re-indexed target; `context`/`impact` for `confirm_payment`, `pay_order` | single production caller; guard upstream of all sinks |
| Decimal predicate | Python 3.12 execution of exact guard predicate for all 5 invalid + 2 valid cases | all correct; short-circuit prevents `InvalidOperation` leak |

---

## Reviewer Self-Check (pre-commit)

Before committing the report, the reviewer confirmed:

- [x] The guard is the first statement of `confirm_payment` and precedes every
      DB read/write/lookup/lock/mutation (read the full function, lines 126-322).
- [x] All five invalid-amount classes are rejected (empirically executed the
      exact predicate).
- [x] The guard applies in both `skip_prechecks` modes (structural + test proof).
- [x] No invalid amount can reach any financial sink (single production caller;
      guard upstream of all sinks).
- [x] The guard takes no transaction ownership (no commit/rollback/close/flush).
- [x] The seven R3 test nodes are authentic, DB-backed (where required), with
      concrete assertions and no skip/xfail/deselect/weakening.
- [x] The 11 original parity tests are unchanged.
- [x] Runtime execution was not claimed where the environment blocked it.
- [x] `git diff --check`, mojibake, pre-commit, and detect-secrets are clean.
- [x] The report branch was created from the canonical baseline `45899145` and
      contains only the two review artifacts.
- [x] The I2A source branch, `product-dev-recovered`, `main`, `platform-dev`,
      and tags are untouched by this review.

---

## Deliverables

1. `docs/ai-reports/review/2026-08-03_dc12r1_s3_s2b_i2a_r3_zcode_final_review.md` (this file).
2. `docs/ai-reports/review/2026-08-03_dc12r1_s3_s2b_i2a_r3_zcode_findings.csv`.

## Final Verdict

`PASS_FOR_CTO_DC12R1_S3_S2B_I2A_R3_ZCODE_FINAL_MERGE_REVIEW`
