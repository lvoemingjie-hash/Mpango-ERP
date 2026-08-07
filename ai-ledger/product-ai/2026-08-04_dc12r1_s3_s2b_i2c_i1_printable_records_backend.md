# DC-12R1-S3-S2B-I2C-I1 — Printable Order Declaration Receipt Backend

**Status:** PASS_FOR_CTO_DC12R1_S3_S2B_I2C_I1_R7_REVIEW
**R7 correction:** Exact constraint-evidence closure (no production code changes).
(1) The forced-failure test now asserts the constraint name via the production
chain-safe PostgreSQL diagnostic helper `_extract_constraint_name(exc_info.value)`
(reused from `api.v1.client.orders`), traversing `exc.orig.diag.constraint_name` /
`__cause__` / `__context__` with cycle protection — no human-readable exception
text is substring-matched. (2) `try/finally` now genuinely encompasses **every**
mutating seed step: `oid=None`, `pay1_id`, `pay2_id`, `did=None` are initialized
before `try`; the order is created **inside** `try`; cleanup always runs in
`finally` with all IDs. (3) Fresh-session per-ID zero-residue checks retained for
order + pay1_id + pay2_id. Cumulative R1-R7 blockers table in §6.

**Task type:** Backend implementation (read-only print Contracts A-C only).
**Base:** `origin/zcode/dc12r1-s3-s2b-i2c-d-print-notification-contract-2026-08-04` @ `94d9243b`
**Branch:** `zcode/dc12r1-s3-s2b-i2c-i1-printable-records-backend-2026-08-04`
**Date:** 2026-08-04
**Executor:** local Zcode (real PG16/Redis7 execution)

---

## 0. Summary

Implemented six read-only backend routes for printable records (Contracts A-C
of the I2C-D contract):

| # | Route | Permission | Contract |
|---|---|---|---|
| 1 | `GET /api/v1/client/orders/{order_id}/print` | `client:orders:read` | A (retailer) |
| 2 | `GET /api/v1/orders/{order_id}/print` | `orders:read` | A (supplier) |
| 3 | `GET /api/v1/client/declarations/{declaration_id}/print` | `client:payments:read` | B (retailer) |
| 4 | `GET /api/v1/declarations/{declaration_id}/print` | `payments:read` | B (supplier) |
| 5 | `GET /api/v1/client/declarations/{declaration_id}/receipt` | `client:payments:read` | C (retailer) |
| 6 | `GET /api/v1/declarations/{declaration_id}/receipt` | `payments:read` | C (supplier) |

**Not implemented (out of scope):** Contract D statement, frontend print
pages, event emission, outbox, provider delivery, migration 038, deployment.

## 1. Base Proof Gate

```
origin/zcode/dc12r1-s3-s2b-i2c-d-print-notification-contract-2026-08-04
  => 94d9243b6967cf687a8eeb51e72ec4166e03a9aa   # exact match ✓
```

Isolated worktree `_i2c_i1_2026-08-04` created on the new I2C-I1 branch.
Working tree clean.

## 2. Implementation

### 2.1 New files
- `backend/schemas/print.py` — `OrderPrintView`, `DeclarationPrintView`,
  `ReceiptPrintView`, `PrintOrderItemView`. All money is server-authoritative;
  timestamps carry authoritative UTC + fixed `Africa/Nairobi` (EAT) display.
- `backend/services/print_service.py` — read-only assembly: name resolution,
  `build_order_print`, `build_declaration_print`, `check_receipt_eligibility`
  (fail-closed predicate), `build_receipt_print`. No writes anywhere.
- `backend/tests/test_dc12r1_s3_s2b_i2c_i1_printable_records.py` — 36 tests.

### 2.2 Modified files (routes added; no existing handler logic changed)
- `backend/api/v1/client/orders.py` — `+1` route (`print_order`).
- `backend/api/v1/client/declarations.py` — `+2` routes (`print_client_declaration`, `get_client_receipt`).
- `backend/api/v1/orders.py` — `+1` route (`print_order` supplier side).
- `backend/api/v1/declarations.py` — `+2` routes (`print_declaration`, `get_receipt` supplier side).
- `backend/tests/test_dc12r1_s3_s1_catalog_order_hardening.py` — inventory +3 routes.
- `backend/tests/test_dc12r1_s3_s2_read_only_retailer_finance.py` — inventory 15→18.

### 2.3 No mutation of existing logic
Payment confirmation, declaration mutation, and ledger logic are untouched.
The receipt eligibility predicate (`check_receipt_eligibility`) is read-only;
it never allocates or repairs a receipt.

## 3. Receipt Eligibility Predicate (fail-closed)

`check_receipt_eligibility` returns `True` iff ALL hold:
1. `declaration.status == 'confirmed'`
2. `confirmation_payment_id` is non-null
3. joined payment exists, `is_deleted IS FALSE` (via `get_by_id_with_receipt`)
4. `payment.status == 'completed'`
5. `receipt_number` matches `^RCT-[0-9]{8}-[0-9]{6}$`
6. relationship binding is active and non-deleted

Any failure → route returns neutral 404 `RECEIPT_NOT_AVAILABLE`. Never
allocates. Replayed GET returns the same receipt identity.

## 4. Read-Only Proof

The zero-write test (`TestZeroWrite.test_all_routes_zero_fingerprint`)
exercises all six routes against a confirmed-declaration-with-receipt
fixture and asserts identical fingerprints before/after across:
`orders`, `order_items`, `payments`, `payment_declarations`,
`ledger_entries`, `receipt_sequences`, and `binding.outstanding_balance`.

## 5. Test Coverage (36 tests — R7)

- Retailer + supplier happy paths for all A-C records.
- Server-authoritative order price/total (unit_price, subtotal, total_amount).
- Pending/rejected declaration non-receipt rendering + non_receipt_notice.
- Confirmed valid receipt (receipt_number, confirmed_amount, EAT timestamp).
- Pending/rejected receipt fail-closed 404 `RECEIPT_NOT_AVAILABLE`.
- Confirmed-but-ineligible declaration print fail-closed 404 (R1).
- Repeated receipt GET returns same identity.
- Cross-retailer order/declaration print denial — real tenant-B records (R1).
- Cross-supplier order print + receipt denial — real tenant-B records (R1).
- Confirmed null-payment fail-closed (R1).
- Confirmed soft-deleted-payment fail-closed (R1).
- Confirmed malformed-receipt-number fail-closed (R1).
- Confirmed wrong-order-payment fail-closed (R1).
- Inactive binding denies supplier receipt 404 + client route 403
  `BINDING_NOT_ACTIVE` (R2: precise code, not vague 403-or-404).
- Same-schema wrong-wholesaler order rejected by DB-level predicate (R2).
- Same-schema wrong-wholesaler order receipt fail-closed (R2).
- Same-schema wrong-retailer payment fail-closed (R2).
- Soft-deleted order receipt fail-closed (R2).
- Deleted binding denies supplier receipt (R2).
- Malformed UUID controlled 404 (never 500).
- Zero SQL writes + zero financial fingerprints.
- No internal-identifier leakage (no `confirmation_payment_id`,
  `tenant_user_id`, cashier user ids in responses).

### Contract B vs Contract C clarification

A confirmed declaration's `/print` (Contract B) returns a
`DeclarationPrintView` with `is_receipt=True` **only** when the full receipt
eligibility predicate passes. It does **not** include `receipt_number` or
`confirmed_amount` — those fields are on `ReceiptPrintView` (Contract C)
only. The `is_receipt=True` flag is a **navigation signal** indicating "this
declaration has a valid receipt available via the `/receipt` route." It is
not a claim that the print view itself contains receipt content. If the
declaration is confirmed but ineligible (missing/invalid payment, bad receipt,
inactive binding), the print route returns 404 — never a partial receipt.

## 6. Gate Results (R7)

### CTO R7 exact-constraint-evidence blockers resolved (cumulative R1-R7)

| Revision | Blocker | Fix |
|---|---|---|
| R1 | Confirmed declaration not receipt-eligible by default | `build_declaration_print` requires `receipt_eligible` from full predicate |
| R1 | Payment not validated against same order/retailer | `check_receipt_eligibility` asserts `payment.order_id/retailer_id == declaration` |
| R1 | Supplier routes lack ownership + binding check | Explicit `wholesaler_id` + `_supplier_binding_active` on all supplier routes |
| R2 | Supplier order not DB-level dual-key | `get_order_for_wholesaler(order_id, wholesaler_id)` SQL predicate |
| R2 | Order ownership not validated in receipt chain | `check_receipt_eligibility` validates order.wholesaler_id/retailer_id; `build_receipt_print` returns None if order is None |
| R3 | Test pollution (unregistered rows, unrestored binding) | `_cleanup_seeded_rows` fresh session; `_snapshot_binding`/`_restore_binding` |
| R4 | Cleanup not fail-closed (UnboundLocalError, swallowed rollback) | IDs init `None` before `try`; `_restore_binding` asserts `rowcount==1` + fresh-session re-read |
| R5 | `except Exception: pass` (false-green) | `pytest.raises(IntegrityError)` with constraint-name assertion |
| R6 | `finally` lost when `pytest.raises` fails | `try/finally` wraps the mutating seed steps; cleanup always runs |
| R6 | Second payment ID not tracked; only text match | Pre-generate `pay2_id`; track all 3 IDs in cleanup + zero-residue |
| **R7** | Constraint name matched by substring (`"ux_..." in str(exc)`) | **Exact diagnostic**: `_extract_constraint_name(exc_info.value) == "ux_payments_receipt_number"` via the production chain-safe helper (traverses `exc.orig.diag.constraint_name` / `__cause__` / `__context__` with cycle protection). No exception text is parsed. |
| **R7** | Order creation was outside `try` (a seed failure before `try` skipped cleanup) | **All** mutating seed steps (order + 2 payments) now inside `try`; `oid=None, pay1_id, pay2_id, did=None` initialized before `try`; `finally` cleans all IDs |

### Order-independence proof (R7)

- Natural order: **36 passed, 0 failed**
- Reverse order (cleanup/binding/predicate tests run first, then full suite): **44 passed, 0 failed** — zero residue, no cross-test interference
- Per-test `_tenant_table_fingerprint` before/after assertion proves zero residue
- `TestForcedSeedFailureCleanup`: `try/finally` over all seed steps + exact `_extract_constraint_name` diagnostic + fresh-session per-ID zero-residue for all 3 IDs

### Exact commands (R7)

Two independent fresh stacks, each PG16 + Redis7 from clean images:

```
# Stack A: PG 59355 / Redis 59356   Stack B: PG 59357 / Redis 59358
docker run -d --name mpango_i2ci1r7a_pg  -e POSTGRES_PASSWORD=... -p 59355:5432 postgres:16-alpine
docker run -d --name mpango_i2ci1r7a_redis                          -p 59356:6379 redis:7-alpine
# (mirrored for Stack B on 59357/59358)

# per stack: create test-safe DB + user, run migrations
CREATE USER test_user WITH PASSWORD '<disposable-test-password>' CREATEDB SUPERUSER;
CREATE DATABASE test_mpango OWNER test_user;
# TEST_DATABASE_URL / DATABASE_URL built by tests/conftest.py from POSTGRES_* env
alembic -x url=postgresql+asyncpg://test_user@postgres:5432/test_mpango upgrade head

# per stack: full backend suite (sequential, identical pinned deps)
docker exec -w /repo/backend -e MPANGO_ENV=test -e MPANGO_ALLOW_TEMP_DB_CREATE=1 \
  -e POSTGRES_HOST=postgres -e POSTGRES_USER=test_user -e POSTGRES_DB=test_mpango \
  -e "TEST_DATABASE_URL=postgresql://test_user@postgres:5432/test_mpango" \
  ... python -m pytest tests/ -p no:cacheprovider -q -rf --tb=line
```

Pinned deps (exact): fastapi 0.128.0, starlette 0.50.0, anyio 4.12.1, httpx
0.28.1, sqlalchemy 2.0.45, asyncpg 0.31.0, pytest 8.4.2, pytest-asyncio 0.26.0,
bcrypt 4.0.1, openpyxl 3.1.5.

### R7 gate runs (Stack A: PG 59355 / Redis 59356, Stack B: PG 59357 / Redis 59358)

| Gate | Stack | Result | Exit |
|---|---|---|---|
| I2C-I1 R7 suite | A | 36 passed, 0 failed | 0 |
| I2C-I1 R7 suite | B | 36 passed, 0 failed | 0 |
| **Gate A (R7, full backend)** | A (PG 59355, Redis 59356) | **3162 passed, 100 skipped, 15 xfailed, 2 failed, 0 errors** (916s) | 1 |
| **Gate B (R7, full backend)** | B (PG 59357, Redis 59358) | **3162 passed, 100 skipped, 15 xfailed, 2 failed, 0 errors** (923s) | 1 |

Both gates run sequentially (independent, no resource contention). Pass/skip
totals are identical across both stacks. The I2C-I1 printable-records suite
(36 tests) is **0 failed / 0 errors** on both stacks.

### The 2 full-suite failures are pre-existing infra artifacts, not R7 code

Both failures are the **same static guard** in two files:
`test_u6h2_...wholesaler_schema.py` and `test_u6h3_...reconcile_cleanup.py` —
`test_forbidden_wholesaler_api_crud_repository_and_bootstrap_files_are_untouched`.
The guard shells out to `git diff --name-only <BASE_REF>` against the working
tree. In this isolated git **worktree** the `.git` pointer resolves to a
host-absolute path (`C:/Users/.../.git/worktrees/_i2c_i1_2026-08-04`) that does
not exist inside the containerized test runner, so the subprocess fails. The
guard's actual assertion (the changed-files set is disjoint from
`FORBIDDEN_EDIT_PATHS`) was verified directly on the host where git resolves
correctly:

```
$ git diff --name-only 6a8ddcf348e9b1bdcc902929011e6212cc675cf8 -- \
  | grep -Fx -e backend/models/wholesaler.py -e backend/api/v1/wholesalers.py \
            -e backend/crud/wholesaler.py -e backend/repositories/wholesaler_repository.py \
            -e backend/api/v1/platform/tenants.py -e backend/api/v1/platform/stats.py
# (no output) → intersection EMPTY → guard PASSES
```

The R7 diff touches only the 2 allowed files
(`backend/tests/test_dc12r1_s3_s2b_i2c_i1_printable_records.py` and this
report); zero forbidden paths. These 2 failures are unchanged from the R6 base
and are independent of the printable-records work. They will resolve in an
environment with a non-worktree checkout (e.g. the scheduled Lubuntu independent
verification).

## 7. Adversarial Self-Review (R7)

| Threat | Closure |
|---|---|
| False receipt | Fail-closed eligibility predicate; pending/rejected → 404; confirmed-but-ineligible → 404 |
| False receipt association | payment.order_id/retailer_id match declaration; order.wholesaler_id/retailer_id match binding |
| Price recomputation | Server-authoritative order rows only; no request prices |
| Cross-tenant access | DB-level dual-key SQL predicate (`get_order_for_wholesaler`); same-schema wrong-wholesaler test proves it |
| Soft-delete bypass | Soft-deleted order → `get_order_for_wholesaler` returns None → 404 (tested) |
| Partial receipt | `build_receipt_print` returns None if order is None → 404, never null totals |
| GET mutation | Zero-fingerprint test proves zero writes |
| Timestamp fabrication | Authoritative UTC `datetime.now(timezone.utc)` + fixed EAT display |
| Internal ID leakage | No-leakage tests; response models omit internal IDs |
| Route-permission drift | Exact permission per route; inventory tests updated |
| Constraint mis-attribution (R7) | Exact `_extract_constraint_name` diagnostic — no exception-text substring match; asserts the live asyncpg `diag.constraint_name` |
| Partial cleanup after early seed failure (R7) | Order creation moved inside `try`; all 4 IDs init before `try`; `finally` cleans every ID regardless of where the body fails |

## 8. Verdict

**PASS_FOR_CTO_DC12R1_S3_S2B_I2C_I1_R7_REVIEW**

The R7 correction closes the exact-constraint-evidence blocker: the forced-failure
test no longer substring-matches exception text — it asserts the constraint name
through the production chain-safe PostgreSQL diagnostic helper. `try/finally`
genuinely encompasses every mutating seed step (order creation moved inside
`try`; all 4 IDs initialized before `try`). The 2 full-suite failures are
pre-existing worktree-git infra artifacts, verified disjoint from the R7 diff on
the host; the printable-records suite is 0 failed / 0 errors on both stacks.
Per the R6→R7 handoff, the next step is the scheduled **Lubuntu independent
verification** (non-worktree checkout), then controlled merge.
