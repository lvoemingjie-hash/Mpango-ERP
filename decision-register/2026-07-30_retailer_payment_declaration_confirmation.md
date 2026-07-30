# Decision Record: Retailer Payment Declaration & Cashier Confirmation

**Date:** 2026-07-30
**Status:** APPROVED FOR PLANNING
**Supersedes:** None
**Related:** DC-12R1-S3-S2B-D contract (`ai-ledger/product-ai/2026-07-30_dc12r1_s3_s2b_payment_declaration_contract.md`)

---

## Context

The MPANGO ERP retailer workspace (DC-12R1-S3) currently provides read-only finance access: retailers can view their outstanding balance (`GET /api/v1/client/finance/balance`) and payment history (`GET /api/v1/client/payments`), but cannot initiate or communicate a payment. All payment recording is wholesaler-side via `POST /api/v1/orders/{order_id}/pay` gated by `payments:create`.

The GAP-07 governance freeze deliberately prevents any client route from performing financial mutation. The permission `client:payments:create` exists in the registry (`permission_registry.py:69`) but is consumed by no route — it is a granted-but-unused placeholder.

**Problem:** Retailers who pay via cash or bank transfer have no way to notify their wholesaler that payment was made. The wholesaler must manually check their bank/cash records and record the payment. This creates latency, errors, and friction.

---

## Decision

Introduce a **payment declaration** workflow: a two-phase maker-checker process where the retailer declares a payment (maker) and the wholesaler cashier confirms or rejects it (checker). The declaration has zero accounting effect until confirmation, at which point it triggers the canonical payment write path.

### Key Decisions

| ID | Decision | Rationale |
|---|---|---|
| DR-01 | Tenant-local storage for declarations | Isolation by construction; matches existing tenant-scoped tables |
| DR-02 | State machine: pending → confirmed/rejected (terminal) | Simple, auditable, no withdrawal by retailer |
| DR-03 | Confirmation delegates to canonical `pay_order` path | Single canonical write path; atomicity guaranteed by existing transaction semantics |
| DR-04 | Replace `client:payments:create` with `client:payments:declare` | Current code is unused; new name accurately reflects non-canonical action |
| DR-05 | No file upload in this scope | Separately justified future enhancement |
| DR-06 | Browser-native print only | No server-side PDF infrastructure needed for MVP |
| DR-07 | Event contract only for notifications | SMS/WhatsApp transport deferred to separate scope |
| DR-08 | Migration 037: new table + permission rename | Additive; no changes to existing data |

---

## Alternatives Considered

### A1: Direct retailer payment (activate `client:payments:create`)

**Rejected.** This would let retailers create canonical payments without cashier review, violating the maker-checker principle and creating financial integrity risk. No audit trail of retailer intent vs. cashier confirmation.

### A2: Public schema declaration storage

**Rejected.** Declarations are relationship-scoped. Public storage would require explicit tenant filtering on every query and risks cross-tenant data leakage. Tenant-local storage is the established pattern.

### A3: Allow retailer cancellation of pending declarations

**Rejected.** Allowing withdrawal lets retailers game the pending queue (submit, withdraw, resubmit to delay). Only the cashier should move declarations to terminal state.

### A4: File/photo upload for transfer proof

**Deferred.** Adds storage infrastructure (S3/blob), upload security, and virus scanning. Justified as a separate enhancement with its own contract.

---

## Consequences

### Positive
- Retailers can proactively communicate payment intent.
- Cashier gets a structured queue instead of ad-hoc notifications.
- Full audit trail of declaration → confirmation → canonical payment.
- Zero risk to existing financial integrity (declaration is non-canonical).
- Receipt generation provides proof of payment to retailers.

### Negative
- Additional table and migration (037).
- Additional permissions to manage.
- Cashier must actively confirm each declaration (operational overhead).
- Permission rename requires coordinated migration.

### Neutral
- Print is browser-native (no PDF server needed).
- Notifications are event-contract-only (no transport coupling).

---

## Compliance

This decision is consistent with:
- GAP-07: No client route performs canonical financial mutation.
- BC-1 through BC-10: All business contract rules satisfied.
- Canonical payment path: Reused, not duplicated or bypassed.
- Existing tests: All financial integrity regressions remain valid.
