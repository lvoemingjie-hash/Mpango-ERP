# Sprint U2: Empty State & First-Use UX Hardening

**Branch:** `codebuddy/u2-empty-state-first-use-ux-2026-06-11`
**Date:** 2026-06-11
**Status:** COMPLETE

## Mission

Make the first-use product experience usable for a real business user with an empty tenant.
Empty data must not feel like system failure. Error states must guide the user to the next action.

## Scope: 8 Pages Modified

| Page | File | Changes |
|------|------|---------|
| Home (Dashboard) | `pages/DashboardPage.tsx` | First-use welcome EmptyState when no data; improved "No orders" guidance in status breakdown and recent orders table; error state with retry guidance |
| Sales/Orders | `pages/orders/OrderListPage.tsx` | Improved empty-state description with first-use guidance ("Add products and customers first"); error state with Retry button |
| Products/SKUs | `pages/skus/SKUListPage.tsx` | Improved empty-state text ("Your product catalog is empty"); added disabled "Import Products" placeholder button (coming soon); error state with Retry button |
| Stock (Inventory) | `pages/inventory/InventoryPage.tsx` | Replaced disabled "Add First Product" with "Go to Products" link; improved empty-state description; error state with Retry button |
| Money/Finance | `pages/finance/FinancePage.tsx` | Improved empty-state text for first-use scenario; improved error message |
| Payments | `pages/finance/PaymentListPage.tsx` | Improved empty-state description; error state with Retry button |
| Customers/Retailers | `pages/retailers/RetailerListPage.tsx` | Improved empty-state description with call to action; error state with Retry button |
| Customer Pricing | `pages/pricing/RetailerPricingPage.tsx` | Improved both empty states (no customer selected / no prices configured); error state with Retry button |

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
3. Include an inline Retry button (except Dashboard which has no reload function exposed in the template)
4. Guide the user to contact support if the problem persists

### First-Use CTAs

- **Products page:** Prominent "Add Product" primary button + "Import Products" disabled placeholder (coming soon badge)
- **Stock page:** Links directly to Products page via `Link` component
- **Orders page:** "Create Order" button preserved
- **Pricing page:** "Set First Price" CTA preserved

## Validation

- TypeScript: `tsc --noEmit` passes with 0 errors (exit code 0)
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
