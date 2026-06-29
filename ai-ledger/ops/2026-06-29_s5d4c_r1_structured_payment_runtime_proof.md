# S5-D4C-R1: Structured Payment Runtime Proof

**Date:** 2026-06-29
**Sprint:** S5-D4C-R1 (Corrected rerun of S5-D4C with structured payment proof)
**Verdict:** PASS_RUNTIME_STRUCTURED_PAYMENT_SETTLEMENT_PROOF_NEEDS_PASSWORD_ROTATION
**Deployed Commit:** `1c2803d9e68d25137ee90055f37678f9d67be46d` (merge: S5-D4B settled payment financial atomicity)
**OPS Branch:** `opencode/s5d4c-redeploy-settled-payment-smoke-2026-06-29` (same branch as S5-D4C)

---

## Correction Summary

S5-D4C used the state-only pay path (`{"method":"cash"}` without `amount`), which creates no payment row. This rerun uses the structured payment path with `amount` field, which exercises S5-D4B settlement logic and creates Payment records.

---

## Task 1: Security Cleanup — POSTGRES_PASSWORD Exposure

### What happened
During S5-D4C backup step, the command:
```bash
grep -E '^(POSTGRES_DB|POSTGRES_USER|POSTGRES_PASSWORD)=' .env.prod
```
printed `POSTGRES_PASSWORD=[REDACTED]` to session stdout.

### Exposure assessment

| Channel | Exposed? | Detail |
|---------|----------|--------|
| Committed files | NO | Report references exposure but does not contain password |
| Local temp files | NO | Deleted (`vps_pw.txt`, all scripts cleaned up) |
| Telegram/chat | NO | Password appeared in this CLI session output only |
| Persistent shell logs | UNLIKELY | No persistent shell log configured on this machine |
| Git history | NO | No commits contain the password |

### Recommendation
**Rotate the POSTGRES_PASSWORD** since exposure cannot be fully ruled out. The password appeared in session output which may be cached by the CLI tool. Rotation is a precautionary measure.

### Remediated
- All local temp files containing the password were deleted
- No password appears in the committed report files

---

## Task 2: Deploy (carried over from S5-D4C)

| Item | Value |
|------|-------|
| Deployed commit | `1c2803d9e68d25137ee90055f37678f9d67be46d` |
| Backend image | `sha256:130fbe08aa1b5b4870f21620b310f3a047a2607c957ad3f6a7e88939f4225b0c` |
| Frontend image | `sha256:6f26c6b5b4d37311d4116914a342be55f122dab7992bb91de4ddc5903d27fb6d` |
| Gateway image | `sha256:8b1e78743a03dbb2c95171cc58639fef29abc8816598e27fb910ed2e621e589a` |
| Postgres image | `sha256:df7bca0066e6f60cc3dd32faa70caddec20e2c22b58932f79498e5704b23854a` |
| Redis image | `sha256:6ab0b6e7381779332f97b8ca76193e45b0756f38d4c0dcda72dbb3c32061ab99` |
| Health | 5/5 containers healthy |
| Backup | `/tmp/s5d4c_pre_deploy_20260629_134209.sql.gz` (12K, sha256: `22ca4e21...`) |

---

## Task 3: Test Environment

| Item | Value |
|------|-------|
| Tenant | TEST001 (`550e8400-e29b-41d4-a716-446655440000`) |
| Schema | `t_550e8400e29b41d4a716446655440000` |
| Admin | `admin@mpango.xyz` (23 permissions) |
| Retailer | S5D4C Test Duka (`22eb3fb6-3029-4fff-ad50-648259c0dcf4`) |
| SKU | S5D2-20260626111011-LAPTOP01 (on_hand=100, price=KES 150) |
| Binding | Retailer ↔ wholesaler (active) |

---

## Task 4: TEST A — Full Structured Cash Payment

### Flow
| Step | Endpoint | Status | Detail |
|------|----------|--------|--------|
| Create order | POST /api/v1/orders | 201 | SKU-LAPTOP01 x 2, total=KES 300.00, status=draft |
| Confirm | POST /api/v1/orders/{id}/confirm | 200 | status=confirmed |
| **Structured pay** | POST /api/v1/orders/{id}/pay | 200 | `{"amount": 300.00, "method": "cash"}` |

### Pay Response
```json
{
  "order_id": "bfb12d24-d229-47f2-9ff0-b966eee1eef0",
  "status": "paid",
  "payment_id": "0de49cfe-da89-48e3-b30c-d69a17c99cfc",
  "payment_amount": "300.00",
  "payment_method": "cash"
}
```

### Assertions

| Assertion | Expected | Actual | Result |
|-----------|----------|--------|--------|
| a. order.status | paid | paid | **PASS** |
| b. payment row exists | yes | payment_id=`0de49cfe-da89-48e3-b30c-d69a17c99cfc` | **PASS** |
| c. payment.method | cash | cash | **PASS** |
| d. payment.status | completed | completed | **PASS** |
| e. ledger balanced | cash+receivable=0 | cash(+300) + receivable(-300) = 0 | **PASS** |
| f. outstanding balance | 0 | 0 (no remaining balance) | **PASS** |

### DB Verification
```
payments: 0de49cfe | bfb12d24 | 300.00 | cash | completed
orders:   bfb12d24 | paid | 300.00
ledger:   cash(+300) + receivable(-300) = balanced
```

---

## Task 5: TEST B — Partial Cash Payment Flow

### Flow
| Step | Endpoint | Status | Detail |
|------|----------|--------|--------|
| Create order | POST /api/v1/orders | 201 | SKU-LAPTOP01 x 3, total=KES 450.00, status=draft |
| Confirm | POST /api/v1/orders/{id}/confirm | 200 | status=confirmed |
| **Partial pay** | POST /api/v1/orders/{id}/pay | 200 | `{"amount": 225.00, "method": "cash"}` (50%) |
| **Final pay** | POST /api/v1/orders/{id}/pay | 200 | `{"amount": 225.00, "method": "cash"}` (remaining 50%) |

### Partial Pay Response
```json
{
  "order_id": "31534edd-b5a0-488e-ba58-f170af5e69fa",
  "status": "partially_paid",
  "payment_id": "97378207-576c-4cec-8f0e-581154d435df",
  "payment_amount": "225.00",
  "payment_method": "cash"
}
```

### Final Pay Response
```json
{
  "order_id": "31534edd-b5a0-488e-ba58-f170af5e69fa",
  "status": "paid",
  "payment_id": "8c75fe33-6114-4b48-898d-68bf93639b16",
  "payment_amount": "225.00",
  "payment_method": "cash"
}
```

### Assertions

| Assertion | Expected | Actual | Result |
|-----------|----------|--------|--------|
| After partial: order.status | partially_paid | partially_paid | **PASS** |
| After partial: payment.status | pending | pending | **PASS** |
| After final: order.status | paid | paid | **PASS** |
| After final: payment.status | completed | completed | **PASS** |
| Payment count | 2 | 2 | **PASS** |
| Ledger balanced | cash+receivable=0 | cash(+450) + receivable(-450) = 0 | **PASS** |

### DB Verification
```
payments: 97378207 | 31534edd | 225.00 | cash | completed  (partial)
payments: 8c75fe33 | 31534edd | 225.00 | cash | completed  (final)
orders:   31534edd | paid | 450.00
ledger:   cash(+450) + receivable(-450) = balanced
```

### Payment Status Transition (S5-D4B behavior)
1. First partial payment: `payment.status = pending`
2. Final payment (settles order): **all cash payments for same order become `completed`**

This confirms the S5-D4B settlement logic: when the order is fully paid, all pending cash payments for that order transition to `completed`.

---

## Task 6: Browser/UI Verification

**Proxy blocks access:** `HTTP_PROXY=http://127.0.0.1:7890`, `NO_PROXY` does not include `1.14.247.12`. Playwright could not install on VPS (PEP 668). VPS-internal HTTP probing confirms frontend serves but does NOT constitute browser rendering verification.

**Marked: UI_BROWSER_NOT_VERIFIED**

---

## Task 7: No-Secrets Confirmation

| Item | Status |
|------|--------|
| Admin password | Generated on VPS, never printed |
| JWT tokens | Never printed (only "got token" logged) |
| DB credentials | POSTGRES_PASSWORD appeared in session output (see Security Cleanup above) |
| Backup content | Never printed |
| Committed files | No secrets in committed files |

---

## Verdict

**PASS_RUNTIME_STRUCTURED_PAYMENT_SETTLEMENT_PROOF_NEEDS_PASSWORD_ROTATION**

### Evidence Summary
- **Full structured cash payment:** Payment row created, status=completed, order=paid
- **Partial cash payment flow:** First payment pending, second payment triggers settlement → both become completed
- **Ledger:** All entries balanced (cash debit + receivable credit = 0)
- **Outstanding balance:** Correctly reflects zero after full payment
- **S5-D4B settlement logic confirmed:** Cash payments transition from pending → completed when order is fully paid

### Files
- S5-D4C report (corrected): `ai-ledger/ops/2026-06-29_s5d4c_runtime_redeploy_settled_payment_smoke.md`
- S5-D4C-R1 report: `ai-ledger/ops/2026-06-29_s5d4c_r1_structured_payment_runtime_proof.md`
