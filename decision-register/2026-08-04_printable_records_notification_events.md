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
`receipt_number IS NOT NULL` matching `^RCT-[0-9]{8}-[0-9]{6}$` AND the binding
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

## D4 — Statement accounting boundary (R1 — receivable-ledger-sourced)

**Decision (R1 truth correction):**
- The relationship balance trajectory is sourced from **immutable
  `ledger_entries`** (`account_type='receivable'`), scoped through `orders` by
  `(wholesaler_id, retailer_id)`. **Charges** (order confirmed) are receivable
  rows `amount > 0` (`post_order_confirmation`); **collections** (payment
  received) are receivable rows `amount < 0` (`post_payment_received`).
  **`payments` are the display/receipt source, not the balance trajectory.**
- `opening_balance` = `SUM(signed receivable amount) WHERE transaction_date <
  from` (scoped) — i.e. the balance **immediately before** `from`. `from` is
  inclusive, `to` is inclusive; range is `[from, to]`.
- `closing_balance = opening_balance + SUM(signed receivable movement in
  [from, to])`. Equivalently `closing_balance = SUM(signed amount) WHERE
  transaction_date <= to` (scoped). Both formulations must agree.
- `net_movement = charge_total − collection_total` (in-range signed sum);
  `closing_balance == opening_balance + net_movement`.
- `settled_total` = sum of **completed payments** in range — a distinct
  display/receipt identity, **never** substituted for `net_movement`.
- **Pending declarations are never included** in `opening_balance`,
  `closing_balance`, `net_movement`, `charge_total`, `collection_total`, or
  `settled_total`. They appear only in a clearly-labelled **separate
  non-accounting section** (`?include_pending=1`).
- **`binding.outstanding_balance` is the current reconciliation anchor only,
  not a historical balance.** It tracks credit exposure (credit sales +,
  credit collections −; cash/transfer ignored) and diverges from the ledger
  receivable for cash relationships. **Fail-closed:** for credit-only
  relationships, `ledger_current` must equal `binding.outstanding_balance`;
  any mismatch → 409 `STATEMENT_RECONCILIATION_FAILED`, **no balances printed.
  The statement never prints an unbalanced statement.** (§8.3.4.)

**Rationale:** the audit established that `binding.outstanding_balance` and
`SUM(ledger_entries)` measure different things and no reconciliation exists;
sourcing the trajectory from the immutable ledger and fail-closing on
credit-only mismatch prevents printing a wrong balance. Pending declarations
excluded from totals prevents mistaking them for settled funds.

**Risk closed:** wrong balance — closed. Tests `T-STMT-OPEN-01`,
`T-STMT-CLOSE-01`, `T-STMT-ARITH-01`, `T-STMT-ARITH-02`,
`T-STMT-CHARGE-COLLECT-01`, `T-STMT-POSTRANGE-01`, `T-STMT-MISMATCH-01`,
`T-STMT-PENDING-EXCL-01`.

---

## D5 — Permission reuse vs separate print permission

**Decision:** **Reuse existing read permissions** for print, each route with
**exactly one** permission (no "or" wording — R1 correction):
- Order print: `client:orders:read` (retailer), `orders:read` (supplier).
- Declaration print: `client:payments:read` (retailer), `payments:read`
  (supplier).
- Receipt: `client:payments:read` (retailer), `payments:read` (supplier).
- **Statement print (R1): `client:finance:read` (retailer), `finance:read`
  (supplier).** The statement is a finance view, so it uses the finance read
  permission on both sides — not `payments:read`.

A **separate `*:print` permission is deferred to post-MVP.** No new permission
is created in I2C-D or I2C implementation.

**Rationale:** print is read-only and carries no authority the read permission
doesn't already grant. Adding a permission would require a migration/RBAC
change (out of scope) and would risk temporarily breaking print for existing
users. Ownership is already enforced by the dual-key predicate, not by a
distinct permission. **Ambiguous "or" permission wording is removed (R1):** a
single permission per route removes the risk of a route being granted under an
unintended weaker permission.

**Risk closed:** none — read permission cannot create a false receipt (the
eligibility predicate is independent of permission).

---

## D6 — Event timing, replay semantics, and the outbox prerequisite (R1 — deterministic dedup)

**Decision:**
- Events represent **committed state only**; the emitter hooks the
  **post-commit** phase of `submit_declaration` / `confirm_declaration` /
  `reject_declaration`. Rollback emits **nothing**.
- **Dedup is deterministic (R1 correction).** The dedup key is built **only
  from persisted columns**, never from emit-time `now()`:
  `dedup_key = (tenant_id, event_type, aggregate_type, aggregate_id,
  transition_ts, transition_version)`. The `transition_ts` source per event
  type is: `submitted` → `payment_declarations.submitted_at`; `confirmed` and
  `receipt_issued` → `payment_declarations.confirmed_at`; `rejected` →
  `payment_declarations.rejected_at`. `transition_version = 1` (each transition
  is terminal and write-once). A replay that performs **zero new writes**
  cannot change the persisted transition timestamp, so it **can never generate
  a fresh logical transition timestamp or a fresh dedup key** — replayed
  transitions are always deduplicated.
- `payment_receipt_issued` requires a valid canonical receipt (§7.1); no
  receipt → no receipt event, even if a confirmation event was emitted.
- **A transactional outbox (table + migration + dispatcher) is a separately
  gated future prerequisite.** I2C-D defines the event **shape** only; it does
  **not** add an outbox table, a migration, a queue, a dispatcher, or a
  delivery worker. The post-commit hook itself is also future work.
- **I2C implementation remains print-only.** Event **emission** is out of scope
  for I2C implementation and waits for the separately gated transactional-outbox
  workstream. I2C delivers only the four printable records.

**Rationale:** defining the contract now lets a future delivery layer be built
against a stable schema, without coupling it to the financial write path. The
"committed only / rollback silent / deterministic replay dedup" rules are the
three invariants that prevent false or duplicate notifications. Building the
dedup key on persisted (not emit-time) timestamps removes the failure mode
where a replay mints a new timestamp and a duplicate logical notification
sneaks through.

**Risk closed:** pre-commit notification — closed by the post-commit rule
(`T-EVT-ROLLBACK-01`); duplicate notification — closed by deterministic dedup
(`T-EVT-DEDUP-01`); unstable dedup key — closed (R1).

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

## D-tz — Timezone truth (R1 correction)

**Decision (R1):**
- **No tenant-configurable timezone setting exists in the platform today.** The
  audit found no tenant timezone column/field. The prior draft's implication
  that timezone config "is an existing platform concern" is **withdrawn**.
- The MVP uses **authoritative UTC** (stored/`TIMESTAMPTZ`, displayed verbatim)
  plus a **single fixed display zone `Africa/Nairobi`**, labelled **"EAT"**,
  computed server-side. The client never recomputes the offset.
- **Tenant-configurable timezone is post-MVP.** This contract makes no claim
  that such configuration already exists.
- Date-range `from`/`to` day boundaries are interpreted against the fixed
  `Africa/Nairobi` zone, with the UTC boundary also shown for audit.

**Rationale:** avoids an unsupported claim (a non-existent config) that would
mislead the I2C implementer into querying a timezone setting that does not
exist. A fixed display zone is honest and sufficient for the Kenyan MVP.

**Risk closed:** unsupported timezone claim — closed (R1). Test `T-TZ-TRUTH-01`.

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
| F-STMT-LEDGER-SOURCE | D4 | §8.1, §8.3.1, §8.5 | T-STMT-LEDGER-01, T-STMT-LEDGER-IMMUTABLE-01 |
| F-STMT-SIGNED-MOVEMENTS | D4 | §8.2, §8.3.1 | T-STMT-SIGNED-01, T-STMT-CHARGE-COLLECT-01 |
| F-STMT-BALANCE-CACHE | D4 | §8.1, §8.3.4 | T-STMT-BALANCE-01 |
| F-STMT-OPEN-CLOSE | D4 | §8.3.2 | T-STMT-OPEN-01, T-STMT-CLOSE-01, T-STMT-ARITH-01, T-STMT-ARITH-02 |
| F-STMT-POSTRANGE | D4 | §8.3.2 | T-STMT-POSTRANGE-01 |
| F-STMT-RECON-FAILCLOSED | D4 | §8.3.4 | T-STMT-MISMATCH-01 |
| F-STMT-PENDING-EXCLUDED | D4 | §8.3.3 | T-STMT-PENDING-EXCL-01 |
| F-TZ-TRUTH | D-tz | §3.5, §8.7 | T-TZ-TRUTH-01 |
| F-EVT-COMMITTED | D6 | §9.4 | T-EVT-ROLLBACK-01 |
| F-EVT-DEDUP | D6 | §9.2.1, §9.4 | T-EVT-DEDUP-01 |
| F-EVT-XTENANT | D6 | §9.5 | T-EVT-XTENANT-01 |
| F-EVT-PROVIDER | D7, D8 | §11 | N/A |
| F-MVP-PARTY | D9 | §11 | N/A |
| F-MIGRATION-038 | D6, scope | §1, §11 | N/A |
| F-PDF-INFRA | D1 | §3.8 | N/A |

Every `finding_id` in the CSV maps to exactly one report section and a
non-empty set of test IDs (or an explicit `NOT_IN_SCOPE`/`FORBIDDEN` with
`N/A`). Every decision `D1`–`D9`, `D-tz` is referenced by at least one
finding. **No finding is unaccounted; no test ID is dangling. Accounting gap
= 0.**

---

## Unresolved decisions

**None.** No open item could produce a false receipt, incorrect balance,
cross-tenant leak, unstable dedup, unsupported timezone claim, ambiguous
permission, or pre-commit notification. All such risks are closed by D3
(receipt eligibility), D4 (receivable-ledger-sourced statement boundary +
fail-closed reconciliation), D5 (exact single permission per route), D6
(deterministic dedup on persisted columns), D-tz (fixed EAT display, no
tenant-config claim), and the isolation rules (§3 / report §10).

**Verdict:** PASS_FOR_CTO_DC12R1_S3_S2B_I2C_IMPLEMENTATION_PLANNING_R1.
