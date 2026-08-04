# Decision Register — Printable Records and Notification Events

**Workstream:** DC-12R1-S3-S2B-I2C-D
**Date:** 2026-08-04
**Base:** `044f7c5cb6ebcb6efbda1d14729c432ea743f1d7`
**Branch:** `zcode/dc12r1-s3-s2b-i2c-d-print-notification-contract-2026-08-04`
**Status:** PASS_FOR_CTO_DC12R1_S3_S2B_I2C_IMPLEMENTATION_PLANNING

This register records the **binding** decisions for the printable-records and
notification-event contracts. Each decision is resolved (no open items that
could produce a false receipt, incorrect balance, cross-tenant leak, or
pre-commit notification). Decisions are referenced by the contract report and
the capability matrix as `D1`–`D9`.

---

## D1 — Browser-print HTML vs generated PDF

**Decision:** The MVP uses **browser-printable, accessible HTML** with a
dedicated `@media print` stylesheet per document. A "Print" button invokes
`window.print()`. **No server-side PDF generation, no PDF library, no headless
browser** is introduced.

**Rationale:**
- No PDF infrastructure exists today (`package.json` has no `jspdf`/`pdfmake`/
  `react-pdf`/`pdf-lib`/`html2pdf`; no `@media print` rules; no print button).
  Adding one is out of I2C-D scope and would add a dependency + render surface
  that must be separately gated.
- All four documents render **server-authoritative** data that already exists
  (order prices/totals, declaration states, receipt numbers, statement lines).
  Browser print satisfies the MVP need ("a printable record I can hand to my
  counterparty") without new machinery.
- Each document is a **dedicated route** returning a clean view, so the data
  view's chrome never leaks onto the printed page.

**Implications:**
- The print view is a separate route from the data view.
- The browser's native print dialog produces the PDF; the app does not name or
  store it. The "filename" in the contract is a suggested title only.
- Post-MVP, a generated-PDF path (for email attachment / batch) would be a
  separate, gated prerequisite — explicitly **not** taken now.

**Risk closed:** none — this choice cannot produce a false receipt or balance.

---

## D2 — Document terminology and status labels

**Decision:**
- **Order (A):** client-mapped status (`CREATED, CONFIRMED, DELIVERED,
  CANCELLED, RETURNED`) via `map_order_status_for_client`
  (`schemas/client.py:146`). Internal `partially_paid`/`paid`/`voided` are
  **not shown** on the order document.
- **Declaration (B):** status rendered verbatim from the enum: `Pending`,
  `Confirmed`, `Rejected`. Pending/Rejected carry a prominent **"not a receipt"
  notice**; Confirmed renders the receipt (Contract C).
- **Receipt (C):** single status `Receipt` (it is confirmed by construction).
  Body text: "Payment received and confirmed by {supplier}".
- **Statement (D):** settled lines use receipt-number + method identity. No
  pending/rejected terms in the accounting section.

**Rationale:** reuses the existing client status map and the existing enum;
prevents a pending declaration from being mistaken for a confirmed receipt
(the core integrity rule).

**Risk closed:** false receipt from terminology ambiguity — closed by the
non-receipt notice (D3) and the eligibility predicate (D4).

---

## D3 — Receipt eligibility

**Decision:** A declaration is receipt-eligible **iff all** hold (§7.1):
`status='confirmed'` AND `confirmation_payment_id IS NOT NULL` AND the joined
`payments` row exists, `is_deleted IS FALSE`, `status='completed'`, AND
`receipt_number IS NOT NULL` matching `^RCT-[0-9]{8}-[[0-9]{6}$` AND the binding
is active/non-deleted at request time. **Any failure → 404
`RECEIPT_NOT_AVAILABLE`, render nothing.** No pending/rejected declaration is
ever receipt-eligible.

**Rationale:** this is enforced **at render time** (not by UI hiding), making it
robust against a client bug or a direct URL. The 404 is **neutral** — it does
not distinguish "wrong tenant" from "not confirmed", to avoid leaking
existence.

**Risk closed:** false receipt — closed. Tests `T-RCPT-PENDING-DENIED-01`,
`T-RCPT-REJECTED-DENIED-01`, `T-RCPT-MALFORMED-01`, `T-RCPT-FAILCLOSED-01`.

---

## D4 — Statement accounting boundary

**Decision:**
- `opening_balance` and `closing_balance` are **server-computed** from the
  authoritative current `binding.outstanding_balance` and the in-range settled
  (`payments.status='completed'`) payments. The client never computes them.
- **Pending declarations are never included** in `opening_balance`,
  `closing_balance`, or `settled_total`. They appear only in a clearly-labelled
  **separate non-accounting section** (`?include_pending=1`), never folded into
  accounting totals.
- `closing_balance = opening_balance − (net settled payments in range)`.

**Rationale:** prevents a pending declaration from being mistaken for settled
funds; keeps the accounting identity over authoritative columns only; matches
the existing "not recalculated on this device" convention
(`FinanceBalancePage.tsx:66`).

**Risk closed:** incorrect balance — closed. Tests `T-STMT-OPEN-01`,
`T-STMT-CLOSE-01`, `T-STMT-ARITH-01`, `T-STMT-PENDING-EXCL-01`.

---

## D5 — Permission reuse vs separate print permission

**Decision:** **Reuse existing read permissions** for print:
- Order print: `client:orders:read` (retailer), `orders:read` (supplier).
- Declaration print: `client:payments:read` (retailer), `payments:read`
  (supplier).
- Receipt: `client:payments:read` / `payments:read`.
- Statement print: `client:payments:read` (retailer), `finance:read` or
  `payments:read` (supplier).

A **separate `*:print` permission is deferred to post-MVP.** No new permission
is created in I2C-D or I2C implementation.

**Rationale:** print is read-only and carries no authority the read permission
doesn't already grant. Adding a permission would require a migration/RBAC
change (out of scope) and would risk temporarily breaking print for existing
users. Ownership is already enforced by the dual-key predicate, not by a
distinct permission.

**Risk closed:** none — read permission cannot create a false receipt (the
eligibility predicate is independent of permission).

---

## D6 — Event timing, replay semantics, and the outbox prerequisite

**Decision:**
- Events represent **committed state only**; the emitter hooks the
  **post-commit** phase of `submit_declaration` / `confirm_declaration` /
  `reject_declaration`. Rollback emits **nothing**.
- Replay (idempotent confirm) must **not** duplicate logical notifications; dedup
  on `(event_type, aggregate_id, occurred_at)`.
- `payment_receipt_issued` requires a valid canonical receipt (§7.1); no
  receipt → no receipt event, even if a confirmation event was emitted.
- **A transactional outbox (table + migration + dispatcher) is a separately
  gated future prerequisite.** I2C-D defines the event **shape** only; it does
  **not** add an outbox table, a migration, a queue, a dispatcher, or a
  delivery worker. The post-commit hook itself is also future work.

**Rationale:** defining the contract now lets a future delivery layer be built
against a stable schema, without coupling it to the financial write path. The
"committed only / rollback silent / replay dedup" rules are the three invariants
that prevent false or duplicate notifications.

**Risk closed:** pre-commit notification — closed by the post-commit rule
(`T-EVT-ROLLBACK-01`); duplicate notification — closed by dedup
(`T-EVT-DEDUP-01`).

---

## D7 — Explicit exclusion of provider delivery

**Decision:** I2C-D does **not** implement SMS, WhatsApp, email, push, or any
external-provider delivery. No phone-number lookup, no email address fetch, no
gateway client, no provider credentials, no message templates, no webhook POST,
no delivery receipts. The event payloads carry **no recipient contact info**
(reason text is also excluded from the payload — only a boolean + length).

**Rationale:** delivery is a separate concern with its own vendor, consent,
cost, and privacy surface. Mixing it into this contract would inflate scope and
create a false start. The contracts are delivery-agnostic by design.

**Risk closed:** none — this is a non-expansion.

---

## D8 — No message templates / webhooks / queues in this design

**Decision:** No message templates, no webhook subscriptions, no queue/topic
infrastructure, and no outbox table are defined or implied by I2C-D. Any of
these would be a **separately gated** future prerequisite with its own
migration and contract. The event envelope (§9.2) is the **only** artefact.

**Rationale:** keeps the design minimal and reviewable; avoids implying
infrastructure that isn't approved.

**Risk closed:** none — non-expansion.

---

## D9 — Explicit MVP non-expansion guardrail

**Decision:** I2C **does not**:
- generalize wholesalers/retailers into a Party graph or Commerce Relationship
  Kernel;
- implement upstream-supplier or downstream-consumer layers;
- create cross-supplier comparison or shared accounting;
- add multi-currency;
- add new financial write paths.

The post-MVP Commerce Relationship Kernel remains **strategic memory only**.
Implementation planning stops at printable records + event contracts for the
accepted wholesaler-to-retailer MVP.

**Rationale:** preserves the validated MVP scope; prevents architecture drift
into an unbounded generalization.

**Risk closed:** scope creep — closed.

---

## Reconciliation (accounting gap zero)

| CSV finding_id | Decision ref | Report section | Test IDs |
|---|---|---|---|
| F-ORDER-AUTH | (none — exists) | §5 | T-ORDER-AUTH-01/02 |
| F-ORDER-PRINT-ROUTE | D1, D5 | §5.2 | T-ORDER-PRINT-01/02 |
| F-DECL-NONRECEIPT-NOTICE | D2, D3 | §6.5 | T-DECL-NONRECEIPT-01, T-DECL-REJREASON-01 |
| F-RCPT-ELIGIBILITY | D3 | §7.1 | T-RCPT-ELIG-01, T-RCPT-PENDING-DENIED-01, T-RCPT-REJECTED-DENIED-01, T-RCPT-MALFORMED-01 |
| F-RCPT-REPLAY | D3 | §7.3 | T-RCPT-REPLAY-01 |
| F-RCPT-FAILCLOSED | D3 | §3.7, §7.1 | T-RCPT-FAILCLOSED-01 |
| F-STMT-OPEN-CLOSE | D4 | §8.3 | T-STMT-OPEN-01, T-STMT-CLOSE-01, T-STMT-ARITH-01 |
| F-STMT-PENDING-EXCLUDED | D4 | §8.3 | T-STMT-PENDING-EXCL-01 |
| F-EVT-COMMITTED | D6 | §9.4 | T-EVT-ROLLBACK-01 |
| F-EVT-DEDUP | D6 | §9.4 | T-EVT-DEDUP-01 |
| F-EVT-XTENANT | D6 | §9.5 | T-EVT-XTENANT-01 |
| F-EVT-PROVIDER | D7, D8 | §11 | N/A |
| F-MVP-PARTY | D9 | §11 | N/A |
| F-MIGRATION-038 | D6, scope | §1, §11 | N/A |
| F-PDF-INFRA | D1 | §3.8 | N/A |

Every `finding_id` in the CSV maps to exactly one report section and a
non-empty set of test IDs (or an explicit `NOT_IN_SCOPE`/`FORBIDDEN` with
`N/A`). Every decision `D1`–`D9` is referenced by at least one finding. **No
finding is unaccounted; no test ID is dangling. Accounting gap = 0.**

---

## Unresolved decisions

**None.** No open item could produce a false receipt, incorrect balance,
cross-tenant leak, or pre-commit notification. All such risks are closed by
D3 (receipt eligibility), D4 (statement boundary), the isolation rules (§3 /
report §10), and D6 (committed-state events).

**Verdict:** PASS_FOR_CTO_DC12R1_S3_S2B_I2C_IMPLEMENTATION_PLANNING.
