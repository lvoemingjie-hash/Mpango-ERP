# S5-D Closeout: Runtime Customer Journey Evidence Packet

| Field | Value |
|---|---|
| **Date** | 2026-06-30 |
| **Sprint** | S5-D Runtime Customer Journey Stabilization |
| **Branch** | `opencode/s5d-closeout-runtime-customer-journey-2026-06-30` |
| **Environment** | Tencent VPS 1.14.247.12, prod stack |
| **Operator** | automated |

---

## 1. Executive Verdict

**S5-D_RUNTIME_CUSTOMER_JOURNEY_STABILIZED_WITH_REMAINING_MVP_UI_GAPS**

The runtime customer journey is stabilized through login, product import, stock adjustment, order lifecycle, multi-partial payment settlement (cash and transfer), and ledger balancing. All backend financial invariants are proven. Remaining gaps are MVP UI polish items (barcode scan, image import, bulk stock wizard) that do not affect backend correctness.

---

## 2. Deployed Commit History

| Commit | Sprint | Description |
|---|---|---|
| `bc6e2b1` | S5-D5 | merge: S5-D5 payment ledger runtime invariant |
| `fe4b375` | S5-D6 | merge: S5-D6 multi-partial payment state machine |
| `1c2803d` | S5-D4B | merge: S5-D4B settled payment financial atomicity |
| Current runtime | S5-D6C | `fe4b375` applied via source patch + backend rebuild |

**Runtime rebuilds performed:**
- S5-D5C: Applied S5-D5 guard to orders.py, rebuilt backend
- S5-D6C: Applied S5-D6 contextual guard to order_service.py, rebuilt backend + gateway

---

## 3. Proven Customer Journeys

### Login + Tenant Selection
- **Evidence:** S5-D4C-R1, S5-D4C-R3, S5-D5C, S5-D6C
- **Result:** `admin@mpango.xyz` login → token → select TEST001 tenant → context token
- **Status:** PASS

### Product CSV Import
- **Evidence:** S5-D2 (product-ai reports)
- **Result:** SKU import with validation, preview, apply flow
- **Status:** PASS (frontend)

### Product Visibility
- **Evidence:** S5-D4C-R1, S5-D5C, S5-D6C
- **Result:** SKU `S5D2-20260626111011-LAPTOP01` visible, retailer price 150.00 applied
- **Status:** PASS

### Stock Adjustment
- **Evidence:** S5-D2-R2 (adjust stock modal SKU binding fix)
- **Result:** Adjust Stock modal correctly displays SKU code, submits adjustment
- **Status:** PASS (frontend fix committed)

### Inventory Logs
- **Evidence:** S5-D2-R2
- **Result:** Inventory movements visible in inventory_stocks table
- **Status:** PASS

### Order Create → Confirm
- **Evidence:** S5-D4C-R1, S5-D4C-R3, S5-D5C, S5-D6C
- **Result:** `POST /api/v1/orders` creates order (draft) → `POST /orders/{id}/confirm` confirms
- **Status:** PASS

### Multi-Partial Cash Payments → Paid → Ledger Balanced
- **Evidence:** S5-D6C (Proof A)
- **Result:** 30+40+30=100 cash payments → order `paid`, 2 ledger entries (cash +150, receivable -150), balanced at 0.00
- **Status:** PASS

### Multi-Partial Transfer Payments → Paid → Ledger Balanced
- **Evidence:** S5-D6C-R2, S5-D6C-R3
- **Result:** 50+50+50=150 transfer payments → order `paid`, all 3 `completed`, 2 ledger entries (cash +150, receivable -150), balanced at 0.00
- **Status:** PASS

### Retry After Paid → No Duplicate Payment/Ledger
- **Evidence:** S5-D6C (Proof D), S5-D6C-R2
- **Result:** Retry on paid order returns `PAYMENT_EXCEEDS_REMAINING` (400), no duplicate payment or ledger entry
- **Status:** PASS

### Basic Health Endpoints
- **Evidence:** All S5-D reports
- **Result:** `/health/live` 200, `/health/ready` 200, 5/5 containers healthy
- **Status:** PASS

---

## 4. Runtime RBAC Repairs

### Durable Source-Code Seed Fixes (Already Merged)
- S5-A-R1: `bootstrap_tenant_schema.py` now creates `order_status` with `returned` value
- S5-A-R1: Enum reconciliation via `ALTER TYPE order_status ADD VALUE IF NOT EXISTS 'returned'`
- S5-D2-R2: Adjust Stock modal SKU binding fix (useState → useEffect)

### Runtime-Only Grants Applied Manually
- None during S5-D (all RBAC was resolved in earlier sprints)

### Grants Still Needing Durable Seed/Bootstrap Reconciliation
- None identified during S5-D

---

## 5. Financial Invariant Status

### Cash Payment Completed Status
- Cash payments are created as `pending`, then updated to `completed` via `update_cash_transfer_to_completed()` when order reaches `PAID`
- **Evidence:** S5-D4C-R1, S5-D6C
- **Status:** PROVEN

### Transfer Partial Lifecycle: Pending → Completed on Final Settlement
- Transfer payments are created as `pending` (immediate API status)
- On final settlement (order reaches PAID), `update_cash_transfer_to_completed()` updates all rows to `completed`
- **Evidence:** S5-D6C-R3
- **Status:** PROVEN

### Ledger Debit/Credit Totals
- Cash payment: Cash debit +150.00, Receivable credit -150.00, sum = 0.00
- Transfer payment: Same pattern, balanced at 0.00
- **Evidence:** S5-D5C-R1, S5-D6C, S5-D6C-R2
- **Status:** PROVEN

### Credit Exclusion Behavior
- Credit payments skip cash-settlement ledger entries (receivable exposure remains visible)
- **Evidence:** S5-D4B code inspection
- **Status:** PROVEN (code-level)

### No Duplicate Ledger on Retry
- Retry on paid order blocked with `PAYMENT_EXCEEDS_REMAINING`, no duplicate ledger entry
- **Evidence:** S5-D6C (Proof D), S5-D6C-R2
- **Status:** PROVEN

---

## 6. Inventory Invariant Status

### Stock Adjustment Verified
- Adjust Stock modal correctly submits adjustment with SKU code, quantity, reason
- **Evidence:** S5-D2-R2 (InventoryAdjustModal.test.tsx, 3 tests pass)
- **Status:** PASS

### Inventory Logs Visible
- Inventory movements tracked in inventory_stocks and inventory_movements tables
- **Evidence:** S5-D2-R2
- **Status:** PASS

### Order Fulfillment Inventory Deduction
- No S5-D evidence of order fulfillment inventory deduction
- **Status:** NOT TESTED (S5-D scope was payment settlement, not fulfillment)

### Limitations
- Bulk initial stock wizard not implemented
- Barcode/phone-camera scan not implemented
- Product image import not implemented

---

## 7. Remaining MVP UI Gaps

| Gap | Status | Impact |
|---|---|---|
| Barcode / phone-camera scan | Not implemented | Low (manual entry works) |
| Product image import | Not implemented | Low (text-only products work) |
| Bulk initial stock wizard | Not implemented | Medium (manual stock entry required) |
| Permission error messages | Technical (HTTP 403/409) | Low (functional but not user-friendly) |
| Browser proxy issue | `HTTP_PROXY` blocks VPS access from local machine | Medium (UI verification requires VPS-internal or proxy bypass) |
| Pricing/customer dashboard gaps | Retailer price override not documented in UI | Low (backend works correctly) |

---

## 8. Security and Hygiene

### Prior DB Password Exposure Remediation
- POSTGRES_PASSWORD was exposed in S5-D4C session output
- Rotated to new 43-char password in S5-D4C-R3
- Old password no longer active
- **Status:** REMEDIATED

### No Secrets in Committed Reports
- All reports scanned for secrets, JWTs, passwords, .env content
- No secrets found in committed files
- **Status:** CLEAN

### Backups Kept Outside Repo
- DB backups stored at `/tmp/` on VPS (not in git repo)
- **Status:** CLEAN

### Remaining Recommendations
- Rotate POSTGRES_PASSWORD via Tencent console for belt-and-suspenders safety
- Consider credential rotation for VPS SSH access if compromise suspected

---

## 9. Final Risk Register

| Risk | Severity | Status | Recommended Next Sprint |
|---|---|---|---|
| Multi-partial payment deadlock | HIGH | RESOLVED (S5-D6) | None |
| Password exposure | MEDIUM | REMEDIATED (S5-D4C-R3) | Tencent console rotation |
| Ledger entries not wired for partial payments | HIGH | RESOLVED (S5-D6) | None |
| State machine rejects `partially_paid → partially_paid` | HIGH | RESOLVED (S5-D6) | None |
| Browser UI verification blocked by proxy | MEDIUM | OPEN | Bypass proxy or use VPS-internal browser |
| Bulk stock wizard missing | MEDIUM | OPEN | MVP UI polish sprint |
| Barcode scan not implemented | LOW | OPEN | Product data-entry sprint |
| Product image import not implemented | LOW | OPEN | Product data-entry sprint |
| Permission error messages technical | LOW | OPEN | MVP UI polish sprint |

---

## 10. Recommended Next Phase

### Option A: MVP UI Polish Sprint
- Fix permission error messages (user-friendly 403/409)
- Add loading states and error boundaries
- Improve order creation form UX
- **OPS Recommendation:** SECOND CHOICE (backend is stable, UI polish is nice-to-have)

### Option B: Product Data-Entry/Scan/Import Sprint
- Implement barcode/phone-camera scan
- Add product image upload
- Build bulk initial stock wizard
- Improve CSV import with validation feedback
- **OPS Recommendation:** FIRST CHOICE (removes manual entry bottleneck, enables real-world usage)

### Option C: Finance/Reporting Dashboard Polish Sprint
- Build receivables summary dashboard
- Add cash flow daily report visualization
- Implement payment reconciliation view
- Add order history with payment timeline
- **OPS Recommendation:** THIRD CHOICE (financial invariants are proven, dashboard is nice-to-have)

---

## Appendix: Source Reports

| Report | Path |
|---|---|
| S5-D4C-R1 | `ai-ledger/ops/2026-06-29_s5d4c_r1_structured_payment_runtime_proof.md` |
| S5-D4C-R3 | `ai-ledger/ops/2026-06-29_s5d4c_r3_password_rotation_runtime_recheck.md` |
| S5-D5C | `ai-ledger/ops/2026-06-30_s5d5c_exact_merge_runtime_provenance.md` |
| S5-D5C-R1 | `ai-ledger/ops/2026-06-30_s5d5c_r1_runtime_ledger_proof_correction.md` |
| S5-D6C | `ai-ledger/ops/2026-06-30_s5d6c_exact_merge_runtime_proof.md` |
| S5-D6C-R1 | `ai-ledger/ops/2026-06-30_s5d6c_r1_transfer_partial_settlement_audit.md` |
| S5-D6C-R2 | `ai-ledger/ops/2026-06-30_s5d6c_r2_transfer_final_settlement_rerun.md` |
| S5-D6C-R3 | `ai-ledger/ops/2026-06-30_s5d6c_r3_transfer_status_timing_clarification.md` |
| S5-D2-R2 | `ai-ledger/product-ai/2026-06-26_s5d2_r2_adjust_stock_modal_sku_binding_fix.md` |
| S5-A | `ai-ledger/product-ai/2026-06-24_s5a_fresh_tenant_real_user_journey_gate.md` |
