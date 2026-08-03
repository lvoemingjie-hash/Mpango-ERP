# DC-12R1-S3-S2B-I2B Self-Review — FINAL Plan (R1 + R2 + 3 Addenda)

**Date**: 2026-08-03
**Reviewer**: ZCode (self-review against approved plan)
**Branch**: `codex/dc12r1-s3-s2b-i2b-payment-declaration-runtime-2026-08-03`
**HEAD**: `310653a332a48ed554573e41cb6c944f647d7907`
**Base**: `76fb345c9054530cb0e6abccf35f0cc1863d2bef`

---

## Verdict: MUST CORRECT BEFORE I2B CAN BE MARKED PASS

This self-review finds **3 P1 gaps and 4 P2 gaps** relative to the approved
FINAL plan. The current branch (`310653a3`) is not yet mergeable.

---

## P1 GAPS (must fix — would cause STOP in full gates)

### P1-GAP-1: `_resolve_confirmed_replay` receipt check is prefix-only, not full regex

**Plan requirement (Binding Addendum #1):**
`allocate_receipt=True` replay must check **both** non-NULL **and** format
`^RCT-[0-9]{8}-[0-9]{6}$`; null or malformed → 409.

**What exists:**
- `canonical_payment_service.py:62-67`: `_is_valid_receipt_number()` correctly
  uses the full regex `^RCT-[0-9]{8}-[0-9]{6}$`. ✓
- `canonical_payment_service.py:82-88`: `_enforce_receipt_on_replay()` calls
  `_is_valid_receipt_number()` at the two canonical replay sites. ✓
- **`payment_declaration_service.py:322-323`**: `_resolve_confirmed_replay`
  checks `receipt.startswith("RCT-")` — **prefix only, no full regex.**
  A manually-seeded value like `RCT-bad` would pass this check.

**Severity**: P1. The canonical replay enforcement (in `canonical_payment_service`)
is correct; the declaration replay path (`_resolve_confirmed_replay`) is
weaker. Both paths must use the same validator.

**Fix**: Replace `not receipt.startswith("RCT-")` with `_is_valid_receipt_number(receipt)`
(the same function from `canonical_payment_service.py`).

**File/line**: `backend/services/payment_declaration_service.py:323`

### P1-GAP-2: Two independent full backend gates NOT executed

**Plan requirement (R1 P1 #4):** Two full gates on two independent fresh
PG16/Redis7 stacks (distinct containers, volumes, DBs). Each run: one pytest
process, no exclusions, exit 0, identical totals, failed=0 errors=0.

**What exists:**
- Worktree-local Poetry environment correctly provisioned (bcrypt 4.0.1,
  passlib 1.7.4, all dependencies resolved).
- Focused regression: I2A canonical payment **18/18 pass**. ✓
- Inventory tests: **4/4 pass**. ✓
- I2B submit tests: **9 pass**. ✓
- **Zero full-suite runs** against a complete test DB. The two-stack
  requirement is not satisfied.

**Severity**: P1. This is a mandatory gate. Without it, I2B's impact on the
full test suite cannot be confirmed. The environment has one PG16 container;
two independent stacks require docker compose orchestration that was not
performed.

**Fix**: Run `poetry run pytest tests/ -q` twice on two independent fresh
PG16/Redis7 stacks (separate docker compose projects with distinct volumes,
ports, and databases). Record exact passed/skipped/xfailed/failed/error
totals; both must be identical and have failed=0 errors=0.

### P1-GAP-3: I2B confirm/reject route tests blocked by admin-RBAC harness

**Plan requirement:** All 16 invariants + R2 namespace isolation + 3 binding
addenda must have passing tests.

**What exists:**
- **9 tests pass**: parity gate, submit (create/replay/conflict/invalid-amount/
  transfer-reference/trim/wrong-order), namespace isolation (bare-payment
  fail-closed).
- **10 tests fail**: confirm (full/partial/replay/overpayment/malformed-id),
  reject (terminal/not-pending/reason-validation), and direct-pay
  reserved-prefix rejection. All fail with 403 `PERMISSION_DENIED` —
  the `_admin_token()` helper cannot produce a token carrying
  `payments:confirm_declaration` or `payments:create`.

**Severity**: P1. The confirm/reject/receipt-rollback test coverage is
missing. Without it, invariants 5-12 cannot be proven to pass.

**Fix**: Resolve the test-harness admin user provisioning. The provisioned_pool
creates admin users with proper `public.tenant_users` linkage. Either:
(a) Use the provisioned pool's admin credential directly, or
(b) Grant admin role via `two_tenants` and use the `/auth/login` (identity)
    + `/auth/select-tenant` flow with correct `tenant_id`.

---

## P2 GAPS (should fix — risk to completeness)

### P2-GAP-1: No receipt-rollback proof test

**Plan requirement (correction):** Test that forces a failure after receipt
allocation and asserts zero residue (no payment row, no receipt_number, no
ledger/order/balance mutation, declaration stays pending, sequence number
reusable after rollback, dates use aware UTC).

**Missing**: No test covers this scenario.

**Fix**: Add a test that monkeypatches `OrderService.transition` to raise
after the payment create, then snapshots before/after and proves zero residue.

### P2-GAP-2: No frontend Vitest tests

**Plan requirement:** `src/tests/Dc12r1S3S2I2bDeclarations.test.tsx` +
`npm run test` (Vitest) + `npm run build` (production build).

**What exists:**
- Production build: ✓ (succeeds in 6.96s).
- Vitest: **NOT executed**. No test file created. `npm run test` not run.

**Fix**: Create `Dc12r1S3S2I2bDeclarations.test.tsx` mirroring
`Dc12r1S3S2ClientFinance.test.tsx` (mock `@/services/api`, assert read-only,
assert "Not Received" for pending, assert receipt only for confirmed,
sanitized rejection reason). Run `npm run test`.

### P2-GAP-3: GitNexus impact/detect_changes NOT executed

**Plan requirement:** `gitnexus impact` for `confirm_payment` and receipt
allocation (CRITICAL blast radius = 58 nodes) before editing affected symbols;
`gitnexus analyze` at merge commit; `gitnexus detect_changes`.

**Missing**: GitNexus gates not run in the worktree-local environment.

### P2-GAP-4: Scoped detect-secrets/pre-commit NOT run on worktree HEAD

While pre-commit hooks passed during commit (automatic), a standalone
scoped audit of all I2B files was not performed after the final commit.

---

## VERIFIED-PASSING REQUIREMENTS (COMPLETED)

| # | Requirement | Status | Evidence |
|---|---|---|---|
| R1-1 | Confirmation replay returns 200 (zero writes) | PASS | `payment_declaration_service.py:168-181` — confirmed status returns declaration unchanged; `_resolve_confirmed_replay` fetches existing payment. The canonical replay path in `canonical_payment_service.py:192-212` returns `_replay_result` on match. |
| R1-2 | I2B uses `skip_prechecks=False` | PASS | `payment_declaration_service.py:202-204` — `confirm_payment(skip_prechecks=False, force_completed=True, allocate_receipt=True)`. The canonical service runs the full default precheck path (idempotency, order lock, balance/state/duplicate-transfer). No financial-rule duplication in the declaration service. |
| R1-3 | Tests use real tenant provisioning (no DDL copy) | PASS | `test_dc12r1_s3_s2b_i2b_payment_declarations.py` imports `provisioned_pool`, `s2_clean_db`, `two_tenants` from the S2 test module. Parity gate (`TestParityGate`) asserts `payment_declarations` and `receipt_sequences` exist in a provisioned tenant. Bootstrap log confirms `_reconcile_s2b_i1` creates 037 objects. No private DDL. |
| R2-1 | Public validator rejects `decl-confirm-` prefix | PASS | `orders.py:110-115` — `_validate_idempotency_key` rejects keys starting with `RESERVED_IDEMPOTENCY_KEY_PREFIX = "decl-confirm-"`, returning controlled 400 `RESERVED_IDEMPOTENCY_KEY`. |
| R2-2 | Internal key bypasses public validator | PASS | The declaration service synthesizes `decl-confirm-{declaration_id.hex}` and passes it directly to `confirm_payment(idempotency_key=...)`. The `_validate_idempotency_key` only fires in the `pay_order` route (line ~600 of orders.py). |
| R2-3 | Canonical replay fail-closed (format check) | PASS | `canonical_payment_service.py:62-67`: `_RECEIPT_NUMBER_PATTERN = re.compile(r"^RCT-[0-9]{8}-[0-9]{6}$")`. `_is_valid_receipt_number()` uses this regex. `_enforce_receipt_on_replay()` is called at both replay sites (lines 211, 234) when `allocate_receipt=True`. |
| Add-1 | Receipt format regex in canonical path | PASS | Same as R2-3. Full regex `^RCT-[0-9]{8}-[0-9]{6}$` checked. |
| Add-2 | 201/200 via Response.status_code + Pydantic model | PASS | `client/orders.py:523-524`: `response.status_code = status.HTTP_200_OK` on replay, while the decorator declares `HTTP_201_CREATED`. The handler returns the Pydantic `DataResponse[ClientDeclarationView]` model in all branches. |
| Add-3 | Only (retailer_id, idempotency_key) conflicts reclassified | PASS | `client/orders.py:480-508`: `except IntegrityError` chain — rollback + restore search_path + re-fetch + classify (same → replay 200, different → 409). Other `IntegrityError` → bare `raise` (line 508). |
| Corr | `declared_amount` NaN/Inf/zero/negative guard before SQL | PASS | `payment_declaration_service.py:52-55`: `_is_invalid_amount()` = `amount.is_nan() or amount.is_infinite() or amount <= 0`. Called at line 84 BEFORE any DB op. Short-circuit prevents `InvalidOperation` on NaN. |
| Corr | Malformed `order_id` → 404; overpayment → 400 | PASS | `payment_declaration_service.py:113-121`: `_get_order_for_declaration` returns None for malformed IDs → 404 `ORDER_NOT_FOUND`. Overpayment returns **400 `PAYMENT_EXCEEDS_REMAINING`** from the canonical service (unchanged code). |
| Corr | UPDATE two existing inventory tests in place | PASS | `test_dc12r1_s3_s2_read_only_retailer_finance.py:335`: count `11→15`; new route assertions added. `test_dc12r1_s3_s1_catalog_order_hardening.py:570`: mutation allowlist extended; `:652`: exact-route set extended. All 4 inventory tests pass. |
| Corr | Frontend rejection reason backend-validated | PASS | `declarations.py` (route): rejects empty/whitespace-only reasons with `INVALID_REJECTION_REASON`. `DeclarationRejectRequest` validates 1-256 chars at Pydantic level. Frontend sends reason verbatim; no silent truncation. |
| Corr | Frontend status labels (BC-7/BC-8) | PASS | `DeclarationHistoryPage.tsx`: `STATUS_LABEL` maps pending→"Pending — Not Received", confirmed→"Payment Received", rejected→"Rejected". `declarationLabel()` shows receipt number only for confirmed, "Payment Declaration — Not Received" for pending. |
| Gen | Backward-compatible receipt_number INSERT/SELECT | PASS | `payment_repository.py:314`: conditional INSERT — `receipt_number` only added when non-None. `get_by_idempotency_key_with_receipt` + `get_by_id_with_receipt` added for declaration flow. Regular SELECTs unchanged. I2A tests 18/18 pass. |
| Gen | No migration 038; no dependency/lockfile changes | PASS | No migration file created. `poetry.lock` and `pyproject.toml` SHA256 unchanged. |
| Gen | `git diff --check` clean; `py_compile` all files | PASS | All changed files compile cleanly. Diff check exit 0. |
| Gen | Frontend production build | PASS | `pnpm run build` succeeds (6.96s). |
| Gen | 8 routes registered in `configure_app()` | PASS | Verified via app build + route enumeration. |

---

## SUMMARY

| Category | Count |
|---|---|
| Verified PASS (completed) | 20 |
| P1 gaps (must fix) | 3 |
| P2 gaps (should fix) | 4 |
| **Total requirements reviewed** | **27** |

## Corrected Verdict

The current branch **should not be marked PASS until the 3 P1 gaps are closed**:

1. **P1-GAP-1**: Fix `_resolve_confirmed_replay` receipt check to use
   `_is_valid_receipt_number()` (full regex) instead of `startswith("RCT-")`.
2. **P1-GAP-2**: Execute two full backend gates on two independent fresh
   PG16/Redis7 stacks; both must exit 0, identical totals, failed=0 errors=0.
3. **P1-GAP-3**: Resolve the admin-RBAC test harness so confirm/reject tests
   can produce valid `payments:confirm_declaration` tokens, then complete
   the missing test coverage.

After closing these three P1 gaps (and preferably the four P2 gaps), the
verdict becomes `PASS_FOR_CTO_DC12R1_S3_S2B_I2B_REVIEW`.
