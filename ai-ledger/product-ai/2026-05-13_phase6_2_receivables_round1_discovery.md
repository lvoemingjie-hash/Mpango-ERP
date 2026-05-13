# Phase 6.2 Round 1 - Receivables MVP Discovery

Date: 2026-05-13
Executor: Claude Code under CTO supervision
CTO Review: corrected for data-source accuracy
Verdict: DISCOVERY_COMPLETE_WITH_CTO_CORRECTIONS

## Worktree Setup

- Worktree path: C:\Users\Jeff0\MPANGO ERP\phase6-2-receivables-mvp-2026-05-13
- Branch: codex/phase6-2-receivables-mvp-2026-05-13
- Base branch: origin/product-dev-recovered
- Base commit: beb89b62bcc32f98c4398f32f900bf809c5c7e70
- Push status: not pushed

## Scope

Round 1 was discovery-only. No product code or tests were changed by the
implementation agent. The only intended artifact is this planning ledger.

Phase 6.2 product goal:

- make credit-sale receivables visible to business users
- expose retailer-level receivable summaries
- expose order-level receivable lists
- prepare for a later collection-recording flow

This is an MVP slice, not a complete accounting subsystem.

## Relevant Files Reviewed

Documentation:

- docs/ai/PROJECT.md
- docs/ai/README.md
- ai-ledger/product-ai/2026-05-13_phase6_credit_payment_promotion.md
- ai-ledger/product-ai/2026-05-13_phase6_credit_ledger_semantics_fix.md

Code:

- backend/api/v1/finance.py
- backend/api/v1/orders.py
- backend/api/v1/payments.py
- backend/services/ledger_service.py
- backend/services/order_service.py
- backend/services/payment_service.py
- backend/repositories/payment_repository.py
- backend/models/ledger.py
- backend/models/order.py
- backend/schemas/payment.py
- backend/tests/test_s5_ledger.py
- backend/tests/test_phase5_order_payment.py

GitNexus:

- Not available in this new worktree. `gitnexus status` reported that the
  repository was not indexed.
- For Round 2 code edits, GitNexus impact analysis must be run from an indexed
  worktree or the worktree must be indexed first.

## Current Architecture

Phase 6.1 credit semantics are already promoted:

- `PaymentService.create_payment()` records structured payments.
- Credit payments increase retailer outstanding exposure.
- Cash and transfer payments decrease retailer outstanding exposure.
- `OrderService.transition(..., payment_method="credit")` skips cash settlement
  ledger entries when moving an order to PAID.
- Credit-paid orders therefore remain visible as receivable exposure in ledger
  semantics.

Important CTO correction:

- There is no `outstanding_balances` table in the current code path.
- The live outstanding field is `public.wholesaler_retailer_bindings.outstanding_balance`,
  updated by `PaymentService._apply_outstanding_balance_delta()`.
- Round 2 must not implement queries against a nonexistent `outstanding_balances`
  table.

Existing finance endpoint:

- `GET /finance/receivables` already exists.
- It is order-level and broad: CONFIRMED, PARTIALLY_PAID, and PAID orders.
- It computes balance due from cash ledger entries.
- It does not clearly distinguish credit-sale receivables from unpaid cash or
  transfer orders.

Existing finance summary:

- `GET /finance/summary` uses ledger aggregates.
- It computes outstanding receivables from RECEIVABLE ledger entries.

## Minimal Safe Data Strategy

Round 2 should avoid migrations.

Safe data sources for read-only visibility:

- `orders`: status, total amount, retailer_id, created_at
- `payments`: method, amount, status, order_id, retailer_id
- `ledger_entries`: authoritative receivable/cash/revenue accounting view
- `public.wholesaler_retailer_bindings.outstanding_balance`: retailer-level
  outstanding exposure maintained by the payment service

Preferred Round 2 approach:

- add read-only service/query logic
- do not mutate ledger, payments, orders, or bindings
- do not add migrations
- do not change order lifecycle
- keep collection recording for Round 3

## Round 2 Proposed API

Read-only endpoints:

1. `GET /finance/receivables/summary`

Purpose:

- retailer-level summary
- total outstanding amount
- credit-sale receivable amount
- unpaid cash/transfer exposure if derivable
- retailer count and order count

2. `GET /finance/receivables/orders`

Purpose:

- order-level receivable list
- filter by retailer_id
- filter by payment method
- filter by order status
- include age_days
- include clear classification such as `credit_receivable` or `unpaid_order`

Round 2 should not replace the existing `GET /finance/receivables` immediately.
It should add clearer endpoints first, leaving the existing endpoint stable.

## Proposed Service Seam

Create:

- backend/services/receivables_service.py

Responsibilities:

- build retailer-level receivable summaries
- build order-level receivable lists
- classify receivable type
- calculate age_days
- keep query behavior read-only

Likely API file to modify:

- backend/api/v1/finance.py

Schema strategy:

- Prefer adding local response assembly in the first MVP if the project pattern
  in finance.py remains `DataResponse[dict]`.
- If typed schemas are added, first verify the existing schema layout. Do not
  assume `backend/schemas/finance.py` exists.

## Round 3 Collection Design Boundary

Collection recording is not Round 2.

For Round 3, CTO currently favors:

- ledger-first collection recording
- post CASH debit and RECEIVABLE credit when money is actually collected
- reduce `wholesaler_retailer_bindings.outstanding_balance`
- do not change order status, because credit payment already closes the order
  lifecycle

Partial collections likely require either:

- a new `collections` table, or
- a carefully designed extension to payments

Do not use `payments.status='completed'` alone as collection evidence. In the
current code, transfer payments are completed immediately and cash/credit can be
pending; status is not sufficient as an accounts-receivable collection ledger.

## Round 2 Risk Assessment

Risk level: LOW-MEDIUM.

Low-risk aspects:

- read-only endpoints
- no migration
- no payment behavior changes
- no order state changes

Medium-risk aspects:

- terminology risk: credit receivable vs unpaid order balance
- SQL risk: tenant schema plus public binding table must be handled carefully
- evidence risk: summaries must reconcile with ledger and payment semantics

Round 2 must explicitly define:

- credit receivable: credit-sale exposure after order lifecycle is closed
- unpaid order: confirmed or partially paid cash/transfer order still awaiting
  settlement

## Required Round 2 Impact Analysis

Before editing code in Round 2, run GitNexus impact analysis on:

- `list_receivables`
- `get_financial_summary`
- `PaymentService._apply_outstanding_balance_delta`
- `PaymentRepository.list_paginated`
- any new or edited service method once introduced

If GitNexus is unavailable in the worktree, index the worktree first or run the
impact analysis from an indexed equivalent worktree before editing.

## Round 2 Recommended Implementation Slice

Files likely to create:

- backend/services/receivables_service.py
- backend/tests/test_receivables_service.py
- backend/tests/test_finance_receivables_api.py

Files likely to modify:

- backend/api/v1/finance.py

Potential schema file:

- backend/schemas/finance.py only if verified appropriate during implementation

Tests to add:

- retailer summary aggregates by retailer
- credit receivable classification
- unpaid order classification
- order list filters by retailer
- order list filters by payment method or classification
- age_days calculation
- existing `tests/test_phase5_order_payment.py` still passes

DB-capable validation target for Vibecoder:

- finance receivables API tests if DB-backed
- `tests/test_s5_ledger.py`
- `tests/test_phase5_order_payment.py`

## CTO Decision

Round 1 discovery is accepted with corrections.

Proceed to Round 2 only after CTO approval. Round 2 should be read-only
receivables visibility and should not include collection recording.
