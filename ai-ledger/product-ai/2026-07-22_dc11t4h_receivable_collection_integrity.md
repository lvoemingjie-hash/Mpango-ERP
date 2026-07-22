# DC-11T4H Receivable Collection Integrity

Verdict: PASS_FOR_CTO_DC11T4H_R1_MERGE_REVIEW

## Scope

- Branch: opencode/dc11t4h-receivable-collection-integrity-2026-07-22
- Base: origin/product-dev-recovered @ 303dc179e94527668f4f1d2145fab74be0f48751
- Candidate: the tip committed from this report and the listed changes
- Deployment: not deployed
- Protected branches/tags: not pushed; no release tags moved or created

## Changed Files

- backend/alembic/versions/035_receivable_collection_integrity.py
- backend/api/v1/orders.py
- backend/models/binding.py
- backend/repositories/payment_repository.py
- backend/scripts/bootstrap_tenant_schema.py
- backend/services/payment_service.py
- backend/services/receivables_service.py
- backend/tests/b6_hardening/test_b6_payment_atomicity.py
- backend/tests/b6_hardening/test_b6_payments_api.py
- backend/tests/test_dc11d_payment_replay_concurrency_integrity.py
- backend/tests/test_dc11t4h_receivable_collection_integrity.py
- backend/tests/test_payment_atomicity.py
- backend/tests/test_payments_api.py
- backend/tests/test_phase5_order_payment.py
- backend/tests/test_receivables_service.py
- backend/tests/test_u6f_onboarding_auth_chain_closeout.py
- backend/tests/test_u6i1_owner_credential_setup_schema.py
- frontend/src/components/ui/PaymentRecordModal.tsx
- frontend/src/pages/orders/OrderListPage.tsx
- frontend/src/tests/PaymentRecordModal.test.tsx
- ai-ledger/product-ai/2026-07-22_dc11t4h_receivable_collection_integrity.md

## Contract Evidence

- ReceivablesSummaryResponse and RetailerSummaryItem retain Field(..., ge=0); no Finance schema weakening.
- API serialization is not clamped; write semantics now prevent invalid negative exposure at payment and DB layers.
- Ordinary cash/transfer order settlement no longer decrements public outstanding_balance from zero.
- Credit sale increases outstanding_balance by the credit amount.
- Paid credit-order cash/transfer collection supports partial/final collection, keeps order status paid, posts balanced cash/receivable ledger entries, and uses row-level balance underflow protection.
- Over-collection and extra payment against ordinary fully-paid orders are rejected without payment, balance, order, or ledger side effects.
- Frontend Finance Collect remaining exposure is credit payments minus later cash/transfer collections, not the sum of every payment method.
- Finance summary includes ordinary confirmed/partially-paid balances even when the credit binding cache is zero; retailer/order counts include only rows with actual exposure.
- The Orders table no longer offers Record Payment on every paid cash order. Paid credit collection remains available through the Finance collection path after payment-history verification.
- Payment-history lookup failures are fail-closed in the frontend; the UI no longer assumes that the full order total is collectible.

## Migration Evidence

- Added forward migration 035 only; migrations <=034 unchanged.
- Alembic down_revision is 034_platform_operators; fresh upgrade/current/heads report single head 035_receivable_collection_integrity.
- Existing public binding balances are reconstructed from registered tenant payment history.
- Ordinary cash/transfer-only payment history contributes zero exposure during reconstruction.
- Invalid registry schema ownership and over-collected credit history fail closed before balance mutation.
- Credit history fails closed unless the single credit amount equals the order total and the order is paid; ordinary non-credit history fails closed when collections exceed the order total.
- public.wholesaler_retailer_bindings now has CHECK (outstanding_balance >= 0), and fresh tenant bootstrap ensures the same canonical constraint.
- DB rejects future negative outstanding_balance updates.
- Migration tests create their own authorized disposable databases through temporary_database_url. They do not use DATABASE_URL directly, drop constraints in a shared database, or rewrite unrelated wholesaler balances.

## CTO R1 Review Corrections

- The initial review found a P1 Finance accuracy gap: the summary queried only positive binding rows, so an ordinary confirmed order with a zero credit binding could disappear from unpaid_order_balance and the visible total.
- The initial review found a P1 test-safety gap: migration tests used DATABASE_URL directly, dropped the canonical CHECK, rewrote unrelated binding balances, and created/dropped schemas without the repository's positive temporary-database authorization gate.
- Both findings were corrected before commit. No protected branch, deployment, or release tag was touched.
- The corrected Finance total is binding-backed credit exposure plus ordinary unpaid order exposure. Fully settled rows are excluded from retailer_count and order_count.
- The destructive migration proof now requires MPANGO_ENV=test, MPANGO_ALLOW_TEMP_DB_CREATE=1, a matching TEST_DATABASE_URL, an explicitly allowed host/port, a test-named source database, and a test-safe role through the shared temporary_database_url guard.

## Validation Results

- PostgreSQL 16.14 / Redis 7 stack 1: alembic upgrade head, current, heads PASS at 035.
- PostgreSQL 16.14 / Redis 7 stack 1: affected backend suite PASS, 68 passed; Phase 5 payment contracts PASS, 53 passed / 1 existing xfailed.
- PostgreSQL 16.14 / Redis 7 stack 2: alembic upgrade head, current, heads PASS at 035.
- PostgreSQL 16.14 / Redis 7 stack 2: final affected backend suite PASS, 123 passed / 1 existing xfailed.
- New DC-11T4H contract file after all fail-closed additions: PASS, 13 passed on PostgreSQL 16.
- Migration/bootstrap regression bundle: PASS, 49 passed with MPANGO_ALLOW_TEMP_DB_CREATE=1 and test_* source database.
- Unit-focused payment/receivables slice: PASS, 26 passed.
- CTO R1 focused backend payment/receivables slice: PASS, 79 passed / 1 existing xfailed.
- CTO R1 Finance/API/real-PG16 regression slice: PASS, 40 passed.
- CTO R1 DC-11T4H real-PG16 contract and migration gate: PASS, 13 passed; the disposable source and per-test databases were removed.
- Frontend focused Collect flow test: PASS, 4 passed.
- Frontend pnpm build: PASS; warnings limited to pre-existing duplicate jsdom package key and chunk-size warning.
- python -m py_compile for changed backend modules/tests: PASS.
- git diff --check: PASS.
- pre-commit scoped to changed files: PASS; detect-secrets hook: PASS.
- Full pre-commit --all-files was attempted but is not a valid DC-11T4H gate in this worktree: it fails on unrelated legacy YAML parse errors and Windows GBK output encoding, and modifies unrelated legacy whitespace/baseline files. Those side effects were restored; the scoped changed-file hooks pass.

## GitNexus

- npx gitnexus status: indexed commit 303dc17, current commit 303dc17, status up-to-date.
- impact PaymentService: HIGH, 22 direct dependents, 2 affected payment-list/get processes; covered by payment API, DC-11D, S5D4B/S5D5/S5D6, Phase 5, and B6 payment tests.
- impact PaymentRepository: MEDIUM, 14 direct dependents; covered by payment and order payment regression suites.
- impact ReceivablesService: LOW, direct finance summary/order list API dependents; covered by DC-10K and receivables service tests.
- impact WholesalerRetailerBinding: LOW, binding repository/model import dependents; covered by migration/bootstrap and DB check tests.
- impact OrderListPage and PaymentRecordModal: LOW; covered by focused frontend Collect flow test and pnpm build.
- Final staged detect_changes reported all 21 changed files at medium risk. Affected graph processes were List_payments -> List_paginated and two frontend idempotency-key graph matches; no additional payment, ledger, or Finance execution flow was surfaced.

## Notes

- No production route/service/model change was made outside the receivable/payment integrity objective.
- No create_all was used.
- No API response contract weakening, batch skip/xfail, deselection, or assertion weakening was introduced. Three destructive migration proofs are explicitly opt-in and passed under the authorized disposable-database guard.
- Existing Phase 5 xfail remains pre-existing and unchanged.
