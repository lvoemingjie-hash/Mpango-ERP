# D1-R1-SUPERVISOR-CORRECTION — authoritative corrections after Codex-L R1 review

Review verdict: `ACCEPT_R1_TO_R5_AS_AUTHOR_EVIDENCE_WITH_R6_UNPROVEN`
(NEXT_ACTION=DOCUMENTATION_CORRECTION_THEN_CTO_DESIGN_REVIEW;
REVIEW_KIND=SOURCE_AND_RETAINED_EVIDENCE_ONLY; REVIEWER_RUNTIME_INVOCATIONS=0).

This document is append-only and SUPERSEDES, where they conflict, the
affected current claims in `IMPLEMENTATION-DESIGN.md` (already corrected in
place this round), `ZCODE-D1-REPORT.md` (R1 addendum §F2/F3 result framing),
and `BEHAVIOR-MATRIX.csv`. Git facts verified by the reviewer:
HEAD `f42e939dff160e727fde7175186aeaadb94a17db`, parent
`6f7e2efe24bb59b5f218a5f4c4f197aa1c5411ba`, tree
`281714f454eda22c4232f17d5596e6580ac5ad5f`, BASE
`1ee75d9faaa00cdcadfe9f46d1e0ac960efc632e`; cumulative BASE delta 26 added
files, product sources unchanged. Claim ceiling:
`AUTHOR_ORDER_STATE_D1_DOCUMENTATION_CLOSEOUT_READY_FOR_CODEXL`.

## 1. Observed run result vs accepted findings (kept separate)

- OBSERVED (author execution, not independent runtime verification): full
  D1 directory run `evidence/2026-09-15T1240Z-r1-full-directory-run1.txt` —
  **33 tests, 27 passed, 6 failed, pytest rc=1**.
- ACCEPTED AS PRODUCT-FINDING EVIDENCE: **R1, R2, R3, R4, R5** (five).
  R3's separately labelled committed diagnostic reads persisted PAID from
  an independent session; its current-behavior assertion is intentionally
  labelled, not a contract claim. R5 wraps the real SMS function and
  injects a RuntimeError at the inventory-deduction entry; rollback
  observations pass BEFORE the SMS assertion fails — this proves
  pre-commit dispatch in the TEST CONFIGURATION (ASGITransport + stub
  transport), not real external SMS delivery.
- NOT ACCEPTED AS PRODUCT-DEFECT PROOF: the sixth failure, formerly
  labelled "R6" — reclassified **TEST_ORACLE_AND_TRANSACTION_FIDELITY_GAP**.
  Product "R6" is UNPROVEN.

## 2. Corrections to specific claims (superseding)

### 2.1 R6 (F1/P1)

The failed race test (a) releases the SKU lock when the verdict session
closes and then re-locks in a SECOND session to assign package_quantity
WITHOUT re-running the history guard in that transaction — not the real
single lock/check/write guard transaction; (b) asserts mutual exclusion in
every ordering, which rejects an ADMISSIBLE sequential history (modify the
unused SKU first, then create an order from the new values); (c) asserts
no comparison of final package_quantity or captured-vs-current snapshots;
(d) can record a post-verdict error while still treating the verdict as
proof of successful mutation; (e) a fixed create path holding the SKU lock
would deadlock the test's own orchestration (guard blocked on create's
lock while create waits for guard_checked). The failure and all original
logs are preserved unchanged; the test failure is a test gap, not a
product RED.

**Source-confirmed risk that REMAINS:** the HTTP create paths read the SKU
catalog row (joined stocks/prices) without FOR UPDATE before the
order_items INSERT, so the first reference is not serialized against the
shared guard lock. Future proof requirements (implementation round, NOT a
D1 design-review prerequisite, no new test round now): ONE
lock/check/write transaction; comparison of only ADMISSIBLE sequential
outcomes against actual committed facts (including package_quantity and
snapshot equality); the correctly locking implementation must be able to
complete.

### 2.2 BEHAVIOR-MATRIX first-reference atomicity wording

Wherever the matrix or report text could be read as claiming first-reference
atomicity (e.g. "first SKU reference freezes package identity" as an
achieved invariant): the freeze is enforced only by the guard's history
check at modification time; the CREATE path reads the SKU unlocked and is
NOT serialized against that guard (source-confirmed). Any such sentence
is a contract statement about the intended semantics, not evidence of an
enforced guarantee.

### 2.3 R5 fault-stage wording

R5's injected RuntimeError fires at the inventory-DEDUCTION ENTRY — after
the FULFILLED transition and flush, BEFORE any real stock deduction or
reservation consumption. The earlier replacement's comment implying
reservations were already consumed is INCORRECT for that test. What is
proven: success-notification suppression failure in the post-transition
stage, and full rollback at that stage. What is NOT covered: an unknown
exception landing mid-way through PARTIAL per-item inventory writes (the
test replaces the whole deduction step). That coverage is future
implementation-round work; no partial-write rollback claim is made.

### 2.4 Notification channel (F2/P1)

The corrected design (IMPLEMENTATION-DESIGN.md §1.2) specifies ONE
request-private channel: intents ride the returned order as a transient
attribute → each endpoint copies them into `request.state`
(`osd1_notification_intents`) → the auth middleware dispatches only after
`finalize_tenant_context` succeeds, then clears the reference; on
rollback/failed commit the request (and its intents) is discarded. No
module/global mutable intent list; nothing intent-bearing is exposed on
public responses. Transitions reached indirectly via
CanonicalPaymentService carry the same returned-order attribute, so no
separate propagation path exists. Delivery is per-request best-effort with
logged failures; NO global exactly-once guarantee is claimed.

### 2.5 Cancellation state policy and the payment sum (F3/P1)

`prior_paid == 0` is NOT the existing cancellation policy and must not
become the gate: PAID/PARTIALLY_PAID rows can carry a zero qualifying
payment sum (legacy/inconsistent rows), so a sum gate alone would OPEN
cancellation for them. The corrected design (IMPLEMENTATION-DESIGN.md
§1.1.2, §1.5) preserves today's HTTP 409 via an EXPLICIT LOCKED-STATE
rejection of CANCELLED/VOIDED from PAID/PARTIALLY_PAID. A paid-amount
check is at most an additional defense-in-depth invariant whose exact
pending/completed semantics await BC evidence; adopting one would create a
second accounting definition and stays OFF until approved. The
confirmation-ledger gate (`post_confirmation_ledger`, default False) is a
PROPOSAL; its effect on existing direct service callers is documented
(none reach CONFIRMED today) in §1.4.

### 2.6 Lock-cycle claim (F4/P2)

IMPLEMENTATION-DESIGN.md §1.6 now states the cycle analysis is LIMITED:
same-order serialization via the orders lock does not prove the complete
cross-order/SKU graph acyclic; the confirm (stocks→reservations) vs
cancel/fulfill (reservations→stocks) inverse table order across different
orders is listed as an unresolved path for the implementing round to argue
or enforce. The multi-SKU create-locking proposal now requires
deduplicated identifiers acquired in ONE fixed global order (sorted
sku_id) BEFORE snapshot/pricing validation, on BOTH create paths.

## 3. Explicit CTO disposition items (carried forward, unresolved)

1. Structural accounting: `SYNC-SEMANTIC-MISSING` — the ten
   `backend/tests/order_state_d1/*` paths (`__init__.py`, `conftest.py`,
   `support.py`, `test_matrix_1_confirm_cancel_baseline.py`,
   `test_matrix_2_double_connection_races.py`,
   `test_matrix_3_locked_orm_freshness.py`,
   `test_matrix_4_whole_request_rollback.py`,
   `test_matrix_5_identity_snapshot_packaging.py`,
   `test_matrix_6_payment_cancel_race.py`,
   `test_matrix_assertion_controls.py`) changed under governed prefix
   `backend/` with no semantic inventory record, waiver, or protocol
   delta. No self-authorized governance change was made; NO structural
   PASS is claimed or authorized by this document.
2. handoffctl executor-whitelist change: digests
   `a14d4a6a…941a6` → `d4fd6a24…ef51a` with before/after lines in
   `evidence/2026-09-15T1255Z-handoffctl-whitelist-diff.txt`; the formal
   authorization reference is MISSING. No re-pin, retrospective
   permission, or waiver is authorized here — CTO to ratify, re-pin, or
   revert.
3. Approved BC-01/02/04 originals: still not provided. Business baseline
   v0.60 is known only by location (Windows
   `AI_REPORT_INBOX/external-architecture-2026-09-06/…`) and SHA256
   `a20e130c04720ceabe60b41c507c1301068e18da2e5fbdf79e831659da148664`;
   the original was not reconstructed from the hash. All
   financial-semantics recommendations (§1.4/§1.5 and adjudication items
   A–E) remain proposals pending that input.
4. R6 product-defect status (future proof per §2.1) and
   partial-inventory-write fault coverage (§2.3): future implementation-
   round work; not prerequisites to this D1 design review.

## 4. Scope of this correction round

Documentation-only: `IMPLEMENTATION-DESIGN.md` edited in place and this
file added. No tests run, no containers, no installs, no governance or
product edits; `f42e939d` and all execution evidence preserved; historical
reports retained verbatim (this file supersedes where conflicts exist).
Checks performed: `git diff --check` on the two paths, strict
UTF-8/no-BOM/no-CR, detect-secrets with a valid same-shape canary —
recorded in `evidence/2026-09-15T1330Z-doc-closeout-self-check.txt` with
preserved pre-edit hashes of both documents.
