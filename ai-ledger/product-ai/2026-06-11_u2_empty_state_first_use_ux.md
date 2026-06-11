# Sprint U2: Empty State & First-Use UX Hardening

**Branch:** `codebuddy/u2-empty-state-first-use-ux-2026-06-11`
**Date:** 2026-06-11
**Status:** COMPLETE (U2 + U2-R1)

## Mission

Make the first-use product experience usable for a real business user with an empty tenant.
Empty data must not feel like system failure. Error states must guide the user to the next action.

## Scope: 8 Pages Modified

| Page | File | Changes |
|------|------|---------|
| Home (Dashboard) | `pages/DashboardPage.tsx` | First-use welcome EmptyState when no data; improved "No orders" guidance in status breakdown and recent orders table; error state with Retry button; API failure vs empty data distinction |
| Sales/Orders | `pages/orders/OrderListPage.tsx` | Improved empty-state description with first-use guidance ("Add products and customers first"); error state with Retry button |
| Products/SKUs | `pages/skus/SKUListPage.tsx` | Improved empty-state text ("Your product catalog is empty"); added disabled "Import Products" placeholder button (coming soon); error state with Retry button |
| Stock (Inventory) | `pages/inventory/InventoryPage.tsx` | Replaced disabled "Add First Product" with "Go to Products" link; improved empty-state description; error state with Retry button |
| Money/Finance | `pages/finance/FinancePage.tsx` | Improved empty-state text for first-use scenario; improved error message |
| Payments | `pages/finance/PaymentListPage.tsx` | Improved empty-state description; error state with Retry button |
| Customers/Retailers | `pages/retailers/RetailerListPage.tsx` | Improved empty-state description with call to action; error state with Retry button |
| Customer Pricing | `pages/pricing/RetailerPricingPage.tsx` | Improved both empty states (no customer selected / no prices configured); error state with source-aware Retry button |

## Changes Summary

### Empty States (8 pages)

All 8 pages now display clear, actionable guidance when data is empty:

- **Products:** "Your product catalog is empty. Add your first product to start selling, or import products from a spreadsheet." + Add Product CTA + Import Products placeholder (disabled, coming soon)
- **Orders:** "Create an order to get started. Add products and customers first, then come back here to record sales." + Create Order CTA
- **Stock:** "Your warehouse is empty. Add products first, then stock levels will appear here as you create orders or adjust inventory." + Go to Products link
- **Finance:** "All credit accounts are settled, or you have not made any credit sales yet. Create orders and accept payments to see activity here."
- **Payments:** "Payment records will appear here once you start collecting payments against orders."
- **Customers:** "Customers will appear here once they register using your invitation link. Share your business link to start building your customer base."
- **Pricing (no selection):** "Choose a customer from the dropdown above to view and set their custom product prices."
- **Pricing (no prices):** "This customer has no custom prices yet. Set prices for your products so this customer can place orders." + Set First Price CTA
- **Dashboard:** "Welcome to your dashboard. Your business overview will appear here as you get started. Add products, create orders, and onboard customers to see your metrics come to life."

### Error States (8 pages)

All error states now:
1. Use clear language ("Could not load..." instead of "Failed to load...")
2. Suggest checking connection and retrying
3. Include an inline Retry button on all 8 pages (including Dashboard)
4. Guide the user to contact support if the problem persists

### First-Use CTAs

- **Products page:** Prominent "Add Product" primary button + "Import Products" disabled placeholder (coming soon badge)
- **Stock page:** Links directly to Products page via `Link` component
- **Orders page:** "Create Order" button preserved
- **Pricing page:** "Set First Price" CTA preserved

## U2-R1 Fixes (Round 1 Review Fixes)

### Fix 1: Dashboard API failure vs empty data distinction

**Problem:** DashboardPage used `Promise.allSettled` but never checked `rejected` results. All 4 API calls could fail silently and the page would show the first-use EmptyState instead of an error. The `load()` function was trapped inside a `useEffect` closure and could not be called by a Retry button.

**Fix:**
- Extracted `load()` from the `useEffect` into a `useCallback` so it is callable from the Retry button
- Added explicit `failedCount` tracking: counts how many of the 4 `Promise.allSettled` results are `rejected`
- If all 4 fail: sets `error` with "Could not load any dashboard data" + Retry button
- If some fail: sets `error` with "Some dashboard data failed to load" + Retry button
- If none fail: no error is set, first-use EmptyState or data displays normally

**Evidence: API errors cannot be hidden by empty state**
The rendering logic uses `{error && <error banner>}` followed by `{!error && <content>}`. When `failedCount > 0`, `error` is set to a non-null string. This means:
1. If all 4 APIs return HTTP 500 -> `failedCount === 4` -> `error` is set -> red error banner with Retry is shown -> EmptyState is NOT shown
2. If all 4 APIs return HTTP 200 with empty arrays -> `failedCount === 0` -> `error` stays null -> first-use EmptyState IS shown
3. If 2 APIs fail and 2 return empty -> `failedCount === 2` -> `error` is set -> red error banner with Retry is shown -> EmptyState is NOT shown

A real API failure (rejected promise) always results in `error` being set, which prevents the EmptyState from rendering. The two states are mutually exclusive.

### Fix 2: Pricing Retry reloads customers on initial load failure

**Problem:** The Retry button on RetailerPricingPage only called `loadPrices()`, which fetches prices for a selected retailer. If the initial customers list failed to load (retailer dropdown empty), clicking Retry would do nothing useful because there were no customers to select.

**Fix:**
- Extracted the inline `loadInitial()` function into a named `loadRetailers` useCallback
- Added `errorSource` state (`'retailers' | 'prices' | null`) to track which operation failed
- Retry button now dispatches to the correct loader: if `errorSource === 'retailers'` it calls `loadRetailers()`, otherwise it calls `loadPrices()`
- This ensures that when the customer dropdown fails to populate, clicking Retry actually re-fetches the customer list

## Validation

- `pnpm lint`: passes with 0 warnings/errors (exit code 0)
- `pnpm build`: passes, production bundle built successfully (exit code 0)
- `tsc --noEmit`: passes with 0 errors (exit code 0)
- `git diff --check origin/product-dev-recovered..HEAD`: passes with 0 issues (exit code 0)
- Linter: 0 diagnostics on all modified files
- No backend changes
- No new dependencies

## Files Changed (8 frontend source files)

1. `frontend/src/pages/DashboardPage.tsx`
2. `frontend/src/pages/orders/OrderListPage.tsx`
3. `frontend/src/pages/skus/SKUListPage.tsx`
4. `frontend/src/pages/inventory/InventoryPage.tsx`
5. `frontend/src/pages/finance/FinancePage.tsx`
6. `frontend/src/pages/finance/PaymentListPage.tsx`
7. `frontend/src/pages/retailers/RetailerListPage.tsx`
8. `frontend/src/pages/pricing/RetailerPricingPage.tsx`

## Constraints Met

- [x] No new backend business logic
- [x] No deploy, no VPS, no platform changes
- [x] Empty data does not show "Failed to load" for valid empty responses
- [x] Error states include user-facing next-action text
- [x] Products page has prominent "Add Product" CTA
- [x] Products page has "Import Products" placeholder (disabled, clearly marked coming soon)
- [x] Dashboard shows first-use welcome state for empty tenants
- [x] All 8 target pages addressed
- [x] Dashboard explicitly distinguishes API failure from empty data (U2-R1)
- [x] Dashboard has functional Retry button (U2-R1)
- [x] Pricing Retry reloads customers when initial load failed (U2-R1)
