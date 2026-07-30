# DC-12R1-S3-S2B-D-R3 Kilo Adversarial Financial Design Review

## Verdict

`STOP_AND_REPORT_CTO_WITH_EXACT_DESIGN_DEFECTS`

## Scope Verification

- Target branch reviewed: `origin/zcode/dc12r1-s3-s2b-d-payment-declaration-contract-2026-07-30`
- Verified tip: `03f18a44ec8153112d3511672014fe725052654b`
- Verified required ancestor: `0f9d259b4a6c20584721c53b59ba94c510d1970d`
- H3 ancestry claim verified: `280a06c3` is an ancestor of `03f18a44`
- Review branch/worktree created: `reports/dc12r1-s3-s2b-d-r3-kilo-review-2026-07-31`

Exact changed-file scope versus required baseline `0f9d259b..03f18a44`:

- `A ai-ledger/product-ai/2026-07-30_dc12r1_s3_s2b_capability_test_matrix.csv`
- `A ai-ledger/product-ai/2026-07-30_dc12r1_s3_s2b_payment_declaration_contract.md`
- `A decision-register/2026-07-30_retailer_payment_declaration_confirmation.md`
- `M docs/ai/CTO_CURRENT_OPS.md`
- `M docs/ai/PROJECT.md`

No product code, migration, schema, test, config, lockfile, or deployment file is changed on the reviewed branch.

## Findings

### 1. High: Migration 037 tenant-enumeration contract is source-inaccurate and would target the wrong tenant set

Evidence:

- The R2 contract says migration 037 must enumerate live tenants with status filters "matching migrations 035/036", but it documents `('pending_email_verification', 'email_verified', 'provisioning', 'provisioned', 'active')` and omits `failed` at `ai-ledger/product-ai/2026-07-30_dc12r1_s3_s2b_payment_declaration_contract.md:19-20`, `:83-89`, and `:202-204`.
- Actual migration 035 uses `LIVE_REGISTRATION_STATUSES = ('pending_email_verification', 'email_verified', 'provisioning', 'active', 'failed')` at `backend/alembic/versions/035_receivable_collection_integrity.py:28-35`.
- Actual migration 036 uses the same status set at `backend/alembic/versions/036_retailer_mvp_identity.py:43-50`.

Why this blocks implementation:

- An implementation that follows the contract literally will not enumerate the same tenant set as the source-of-truth migrations it claims to mirror.
- That is an unsafe migration/catalog assumption and directly triggers the stated stop condition.

Required correction:

- Replace every R2 live-tenant status list with the exact 035/036 source set, or explicitly justify a different set and mark it as a new design decision rather than “migration truth”.

### 2. High: Declaration idempotency is not composable with the canonical payment idempotency model

Evidence:

- The contract intentionally changes declaration idempotency to `UNIQUE(retailer_id, idempotency_key)` and states “Different retailers may independently use the same key” at `ai-ledger/product-ai/2026-07-30_dc12r1_s3_s2b_payment_declaration_contract.md:295-303` and CSV row `FIND-24`.
- The current canonical payment path persists payment idempotency tenant-locally, not retailer-locally:
  - migration 006: unique index on `payments.idempotency_key` within each tenant schema at `backend/alembic/versions/006_phase_b6_payments_idempotency_key.py:8-12` and `:44-51`
  - repository lookup is by raw `idempotency_key` only at `backend/repositories/payment_repository.py:13-31`
  - existing regression proves same key isolation only across tenant schemas, not across retailers in one tenant, at `backend/tests/test_dc11d_payment_replay_concurrency_integrity.py:658-719`
- The design never specifies how declaration confirmation derives a canonical payment idempotency key that remains unique within the tenant when two retailers choose the same declaration key.

Why this blocks implementation:

- If confirmation reuses the declaration key as the payment idempotency key, two different retailers under the same wholesaler can collide on the canonical payment uniqueness boundary.
- That can produce false replay, false 409 conflicts, or mis-associated payment reuse across retailers.
- This is an unresolved financial invariant in the exact path the design says is HIGH blast radius.

Required correction:

- Define a separate canonical-payment idempotency derivation for confirmation, scoped at least by declaration identity or `(retailer_id, declaration_id)` and prove it cannot collide with another retailer in the same tenant.

### 3. High: The receipt contract is incompatible with current canonical pending/completed payment semantics

Evidence:

- The business contract says only a confirmed payment may be labelled received and rendered as a receipt at `ai-ledger/product-ai/2026-07-30_dc12r1_s3_s2b_payment_declaration_contract.md:57-58`.
- The same contract assumes a confirmed declaration resolves to `confirmation_payment_id -> payments.receipt_number` and tests that as TM-16 at `:136-153` and `:399-406`.
- But the current canonical payment route does not make all confirmed cash/transfer writes immediately completed:
  - `pay_order` inserts status `pending` unless the special completion conditions are met at `backend/api/v1/orders.py:754-761`
  - cash/transfer rows are only bulk-updated to `completed` after the order actually reaches `PAID` at `backend/api/v1/orders.py:804-810`

Why this blocks implementation:

- The design never states whether partial declaration confirmations are forbidden, allowed without receipts, or allowed with delayed receipt allocation.
- As written, “declaration confirmed” and “receipt visible through payments.receipt_number” are treated as if they always happen together, but the current canonical path can produce a valid confirmed accounting write whose payment row remains `pending`.
- That leaves receipt allocation timing and receipt visibility unresolved in the exact financial path the design is trying to lock.

Required correction:

- Explicitly define whether declaration confirmation is restricted to flows that produce a `completed` canonical payment, or define delayed receipt allocation/visibility semantics for partial cash/transfer confirmations.

### 4. High: Transfer declarations define a `transfer_reference` column but never define how it maps into the canonical unique transfer identity

Evidence:

- The declaration schema includes `transfer_reference VARCHAR(128)` at `ai-ledger/product-ai/2026-07-30_dc12r1_s3_s2b_payment_declaration_contract.md:341-342`.
- The contract otherwise contains no rule mapping `transfer_reference` into canonical `payments.transaction_id` semantics; outside schema mentions, the document has no behavioral mapping for it.
- The current canonical path enforces duplicate-transfer protection on `payments.transaction_id`:
  - duplicate lookup before insert at `backend/api/v1/orders.py:732-739`
  - tenant bootstrap maintains a unique partial index on `payments(transaction_id)` at `backend/scripts/bootstrap_tenant_schema.py:1453-1458` and `:771-778`

Why this blocks implementation:

- Without an explicit mapping rule, confirmation can either lose the external transfer reference completely or bypass the duplicate-transfer invariant that the current canonical path relies on.
- This is a direct ambiguity in transaction ownership and duplicate-accounting prevention.

Required correction:

- State exactly whether `transfer_reference` becomes `payments.transaction_id`, whether it is normalized/truncated, and whether duplicate-transfer rejection uses the existing canonical `transaction_id` uniqueness contract.

### 5. Medium: The branch’s status docs assert the wrong active product baseline and accepted merge SHA

Evidence:

- `docs/ai/CTO_CURRENT_OPS.md` says the active product baseline is `origin/product-dev-recovered@0aec0f0b` and repeats that SHA at `docs/ai/CTO_CURRENT_OPS.md:6`, `:16`, and `:57`.
- `docs/ai/PROJECT.md` says the accepted product merge is `0aec0f0ba9b63aafd43f9194e63348b0f57c7e19` and the product baseline is `origin/product-dev-recovered@0aec0f0b` at `docs/ai/PROJECT.md:6`, `:77`, and `:161`.
- The actual live remote ref is still `origin/product-dev-recovered = 0f9d259b4a6c20584721c53b59ba94c510d1970d`.

Why this matters:

- This branch is supposed to be a source-backed design gate. Misreporting the live product baseline makes the design packet internally inconsistent before implementation even starts.

Required correction:

- Align both status docs to the actual fetched remote baseline or remove the baseline advancement claims from this branch.

### 6. Medium: The report/decision-register/CSV package does not reconcile by `finding_id`, so the claimed gap=0 is false

Evidence:

- The capability matrix is keyed by `FIND-01` through `FIND-42` at `ai-ledger/product-ai/2026-07-30_dc12r1_s3_s2b_capability_test_matrix.csv:1-43`.
- The decision register uses only `DR-01` through `DR-12` and contains no `FIND-*` references at `decision-register/2026-07-30_retailer_payment_declaration_confirmation.md:18-31`.
- The contract self-review still marks “Report/CSV accounting gap = 0” as PASS at `ai-ledger/product-ai/2026-07-30_dc12r1_s3_s2b_payment_declaration_contract.md:511-513`.

Why this matters:

- The deliverable cannot be mechanically reconciled by finding ID as requested.
- That weakens auditability of later implementation and review gates.

Required correction:

- Add a one-to-many mapping from every `FIND-*` row to decision record entries, or embed `finding_id` references directly in the decision register.

## Validated Items

- The branch tip and required ancestor checks passed.
- The H3 frontend permission-fix ancestry claim is true:
  - frontend now checks `payments:create` at `frontend/src/pages/orders/OrderListPage.tsx:70-76`
  - backend pay route still requires `payments:create` at `backend/api/v1/orders.py:558-561`
  - route-policy regression still enforces that contract at `backend/tests/test_route_authorization_policy.py:904-915`
- The branch is docs-only; no product implementation, migration, config, lockfile, or deployment changes are present.
- The contract correctly recognizes that `LedgerService.get_balance` is tenant-wide and unsuitable for retailer statements in its current form:
  - service signature at `backend/services/ledger_service.py:183-215`
- The contract correctly recognizes that `payments.receipt_number` does not yet exist in source and would require schema work.

## GitNexus Impact Evidence

- `PaymentService`: MEDIUM impact, 5 upstream dependents, affecting `backend/api/v1/payments.py` and `backend/api/v1/orders.py`.
- `configure_app`: LOW impact in the current graph.
- `LedgerService`: HIGH impact, with direct callers in `order_service.py` and `orders.py`.
- `ADMIN_PERMISSIONS`: LOW impact.
- `RETAILER_OPERATOR_PERMISSIONS`: LOW impact.
- `pay_order`: GitNexus resolved this symbol ambiguously to `backend/crud/order.py:pay_order` with LOW impact instead of the active route implementation in `backend/api/v1/orders.py`; treat that one result as graph-ambiguity evidence, not authoritative blast-radius truth.

## Stop Conditions Triggered

- Unsafe migration/catalog assumption: yes, by the incorrect 035/036 live-tenant status contract.
- Duplicate accounting / replay ambiguity: yes, by unresolved composition between declaration idempotency and canonical payment idempotency.
- Receipt/settlement ambiguity: yes, by unresolved receipt timing for partial confirmed declarations and missing transfer-reference mapping into canonical transaction identity.

## Recommendation

Do not approve this design packet for implementation. Correct the exact defects above first, then rerun an independent design review against the corrected docs-only branch.
