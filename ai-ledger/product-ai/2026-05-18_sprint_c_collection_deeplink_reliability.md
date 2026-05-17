# Sprint C: Collection Deep-Link Reliability

**Date:** 2026-05-18
**Branch:** `codex/sprint-c-collection-reliability-2026-05-18`
**Base:** `83654b5 feat(finance): polish credit collection workflow`

## Objective

Fix the Sprint B risk where `/orders?collect=<order_id>` only opened the payment modal when the target order was already present in the first 50 loaded rows.

## Root Cause

`OrderListPage.tsx` previously searched only the local `orders` state loaded by `orderService.getAll(1, 50)`. If the target order was outside that first page, the handler returned silently and left the user without a clear result.

## Fix

The collection deep-link handler now:

1. Consumes the `collect` query parameter exactly once to avoid re-trigger loops.
2. Opens the payment modal immediately when the order is already loaded.
3. Falls back to the existing `orderService.getById(id)` API when the order is not in the loaded list.
4. Shows a clear toast if the user lacks permission, the order is not payable, or the lookup fails.

## Files Changed

- `frontend/src/pages/orders/OrderListPage.tsx`
- `ai-ledger/product-ai/2026-05-18_sprint_c_collection_deeplink_reliability.md`

## GitNexus

- CTO impact precheck: `OrderListPage` upstream risk LOW, 0 direct callers, 0 affected processes.
- `gitnexus detect_changes --scope all` after indexing this worktree: LOW risk, 1 changed code file, 0 affected processes.

## Validation

Claude Code implemented the first draft but its permission settings blocked `pnpm` and `git add`. CTO reviewed the diff, found that the initial async fallback could be cancelled by the search-param cleanup rerender, and corrected the handler with a `useRef` one-shot guard before validation.

Commands:

```text
cd frontend
pnpm run lint
```

Result: PASS, exit code 0.

```text
cd frontend
pnpm run build
```

Result: PASS, exit code 0. Vite large chunk warning only.

```text
cd backend
REPORTING_USER_PASSWORD=MpangoTest_2026 poetry run pytest tests/test_phase5_order_payment.py -q --tb=short
```

Result: PASS, `53 passed, 1 xfailed`.

## Risks

- Low risk: the change uses an existing frontend service method and does not change backend behavior.
- No auth, tenant, migration, schema, or package files were touched.
- The deep-link fallback depends on the existing `/orders/{id}` API continuing to return the same `Order` shape used by the list.

## Verdict

PASS_FOR_CTO_REVIEW
