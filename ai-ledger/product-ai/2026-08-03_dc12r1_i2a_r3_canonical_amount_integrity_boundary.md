# DC-12R1-S3-S2B-I2A-R3: Canonical Amount Integrity Boundary

**Date**: 2026-08-03
**Base SHA**: `72a17a60fa119f0d874eb7b7c41f24c0ea5bdafc`
**Branch**: `codex/dc12r1-s3-s2b-i2a-canonical-payment-service-2026-08-01`
**Predecessor**: DC-12R1-S3-S2B-I2A-R2 (reconciliation with H4 baseline)

---

## Objective

Add an amount integrity guard at the very start of
`CanonicalPaymentService.confirm_payment()` that rejects non-positive, NaN,
and +/- Infinity amounts before any database read or write, regardless of the
`skip_prechecks` flag.

---

## Changes Made

### 1. `backend/services/canonical_payment_service.py`

Added 6 lines at the top of `confirm_payment()`, before the `skip_prechecks`
branch:

```python
if amount.is_nan() or amount.is_infinite() or amount <= 0:
    raise _payment_error(
        status.HTTP_400_BAD_REQUEST,
        "INVALID_PAYMENT_AMOUNT",
        "Payment amount must be a positive finite number",
    )
```

The guard:
- Rejects `Decimal('NaN')` via `.is_nan()`
- Rejects `Decimal('Infinity')` and `Decimal('-Infinity')` via `.is_infinite()`
- Rejects zero and negative amounts via `<= 0`
- Applies before any DB read or write
- Applies whether `skip_prechecks` is true or false
- Returns HTTP 400 with code `INVALID_PAYMENT_AMOUNT`
- Does not modify payment status, accounting, or order state semantics

No migration, config, dependency, frontend, or protected-branch changes.

### 2. `backend/tests/test_dc12r1_s3_s2b_i2a_canonical_payment_service.py`

Added 7 new tests (5 test functions, one parametrized over 3 values):

| Test | Description |
|------|-------------|
| `test_r3_negative_cash_amount_rejected_with_zero_mutation` | Negative amount rejected with 400; snapshot proves zero payment/order/balance/ledger mutation |
| `test_r3_zero_amount_rejected` | Zero amount rejected with 400 |
| `test_r3_nan_and_infinity_rejected_without_500[nan]` | NaN rejected with 400 (not 500) |
| `test_r3_nan_and_infinity_rejected_without_500[pos_inf]` | +Infinity rejected with 400 |
| `test_r3_nan_and_infinity_rejected_without_500[neg_inf]` | -Infinity rejected with 400 |
| `test_r3_skip_prechecks_cannot_bypass_amount_guard` | `skip_prechecks=True` with negative amount still rejected |
| `test_r3_failed_attempt_leaves_transaction_retryable` | After rejection, valid payment succeeds on same order |

### 3. Report corrections to R2 evidence ledger

- Removed stale "To be filled" heading
- Added explicit file count: "6 implementation/status files plus this R2 report, total 7"

---

## RED/GREEN Proof

### RED (guard removed, 7 tests fail)

All 7 new tests fail without the guard:
- Negative/zero/NaN/Infinity amounts proceed past the guard and either
  succeed (wrong) or raise non-400 errors
- skip_prechecks bypass works (wrong)
- Failed attempt may corrupt session state

### GREEN (guard applied, all 18 I2A tests pass)

```
18 passed in 10.33s
```

11 original I2A parity tests + 7 new R3 tests, all green.

---

## Focused Gate Results

| Gate | Result |
|------|--------|
| I2A suite (18 tests) | 18 passed |
| Payment/order/receivable/ledger bundle (9 files) | 101 passed |
| H4 regression | 7 passed |
| R4-R1 | 29 passed |
| S1-R5 | 41 passed |
| Alembic sole head | `037_payment_declarations_schema` |

---

## Full Suite Results (two independent fresh PG16 + Redis7 stacks)

| Metric | Run A | Run B |
|---|---:|---:|
| Passed | 3134 | 3134 |
| Skipped | 48 | 48 |
| XFailed | 15 | 15 |
| Failed | 0 | 0 |
| Errors | 0 | 0 |
| Duration | 18:37 | 23:45 |

Totals identical. 3134 = R2 baseline (3127) + 7 new R3 tests.

---

## Changed-Scope Proof

Diff relative to R2 baseline `72a17a6`:

| File | Lines |
|------|-------|
| `backend/services/canonical_payment_service.py` | +6 |
| `backend/tests/test_dc12r1_s3_s2b_i2a_canonical_payment_service.py` | +161 |
| `ai-ledger/product-ai/2026-08-02_dc12r1_i2a_r2_reconciliation_with_h4_baseline.md` | +1/-1 (report correction) |
| `ai-ledger/product-ai/2026-08-03_dc12r1_i2a_r3_canonical_amount_integrity_boundary.md` | new (this report) |

No migration, config, dependency, frontend, permission, or protected-branch
changes.

GitNexus is not available in this validation environment. Changed-scope proof
is provided via `git diff` evidence above.

---

## Verdict

**PASS_FOR_CTO_DC12R1_S3_S2B_I2A_R3_FINAL_MERGE_REVIEW**

The amount integrity guard is implemented at the correct boundary (before any
DB read or write, regardless of skip_prechecks), all RED/GREEN tests pass,
all focused gates are green, and two independent exact full-suite runs produced
identical results with zero failures and zero errors.
