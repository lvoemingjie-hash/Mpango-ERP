# DC-12R1-MVP-L1-PW1-R4-C0-R2 — Mobile Horizontal Overflow Root-Cause Diagnostic (Scope Corrected)

**Task:** PW1R4C0-R2 Phase 6 Responsive Overflow Diagnosis — R4-C0-R2 Scope Correction
**Date:** 2026-08-17
**Product baseline:** `origin/product-dev-recovered` @ `9067e38f83edb38fcdb53fb5d5eea7e75e85cf5f`
**Report branch:** `reports/dc12r1-mvp-l1-pw1-r4-c0-r1-mobile-overflow-diagnostic-2026-08-17`
**Scope:** Evidence/scope correction only — no product code changes. No `overflow-x: hidden` in fix or evidence. No assertion weakening, no clipping or hiding of required controls.

---

## 1. Failing Tests (Reproduced Authoritatively)

| # | Spec | Line | Description | Mobile Overflow |
|---|------|------|-------------|-----------------|
| 1 | `phase6-responsive.spec.ts` | 17 | Wholesaler dashboard | **374px** |
| 2 | `phase6-responsive.spec.ts` | 25 | Wholesaler orders page | **346px** |

**Viewport:** 390 x 844 (iPhone 14 Pro), Playwright `[mobile]` project.
**Passing:** 5/7 tests (retailer catalog, retailer orders, login forms, network, print).
**Retailer pages use `ClientLayout` (mobile-native bottom nav) — zero overflow.**

---

## 2. Root Cause Analysis

### 2.1 Layout Architecture

`MainLayout.tsx` (21 lines) renders:
```
<div class="flex min-h-screen bg-gray-50">           ← root flex, overflow: visible
  <aside class="fixed inset-y-0 left-0 z-30 w-64">   ← sidebar, 256px, always visible
  <div class="flex flex-1 flex-col ml-64">            ← content, margin-left 256px
    <header class="sticky ... shrink-0 ... px-6">     ← header, flex-shrink: 0
    <main class="flex-1 overflow-auto p-6">           ← scrollable content
```

### 2.2 Three Independent Root Causes (Proven by Isolation)

| # | Factor | Component | Tailwind Class | CSS Property | Dashboard Contribution | Orders Contribution |
|---|--------|-----------|---------------|--------------|----------------------|--------------------|
| **RC1** | Unconditional content margin | `MainLayout.tsx:13` | `ml-64` | `margin-left: 16rem (256px)` | **256px (68.4%)** | **256px (74.0%)** |
| **RC2** | Content wrapper auto min-width | `MainLayout.tsx:13` | (implicit flex) | `min-width: auto` | **24px (6.4%)** | **24px (6.9%)** |
| **RC3** | Header children auto min-width | `Header.tsx:32` | `shrink-0` + flex children | `min-width: auto` on nav/badge/user blocks | **94px (25.1%)** | **66px (19.1%)** |

**Note:** The `<aside>` is `position: fixed` and does NOT participate in layout flow. CF1 (hiding sidebar only) produced 0px reduction. The sidebar is purely visual overlay — the `ml-64` margin is the layout driver.

### 2.3 Why `shrink-0` on Header Matters

`Header.tsx:32` has `shrink-0` (flex-shrink: 0) which prevents the header from shrinking below its min-content width. Combined with `justify-between`, the header's flex children (breadcrumb nav `gap-1`, tenant badge `gap-1.5 px-2.5`, user block `gap-2`) each have auto min-widths that sum to 476px (dashboard) / 480px (orders). Even after removing ml-256, the header's min-content exceeds the 390px viewport.

### 2.4 Why `min-width: auto` Matters

In CSS Flexbox, `min-width: auto` is the default. It means a flex item cannot shrink below its content's intrinsic minimum. This applies to both the content wrapper div (`ml-64 flex-1`) and the header's flex children. Setting `min-width: 0` on these elements allows them to shrink freely, enabling the flex layout to fit within 390px.

---

## 3. Counterfactual Isolation Results

### 3.1 Dashboard (baseline: 374px)

| CF | Intervention | Delta | Step Reduction | Cumulative % |
|----|-------------|-------|---------------|-------------|
| baseline | (none) | 374 | — | — |
| CF1 | `aside { display: none }` | 374 | 0px | 0.0% |
| CF2 | `.ml-64 { margin-left: 0 }` | 118 | 256px | 68.4% |
| CF3 | CF1 + CF2 | 118 | 0px | 68.4% |
| CF4 | CF3 + `header { flex-shrink: 1 }` | 118 | 0px | 68.4% |
| CF5 | CF4 + `.ml-64 { min-width: 0 }` | 94 | 24px | 74.9% |
| CF6 | CF5 + `header { min-width: 0 }` | 94 | 0px | 74.9% |
| **CF7** | **CF6 + header flex children `min-width: 0`** | **0** | **94px** | **100%** |
| CF8 | CF7 + `header { padding: 8px }` | 0 | 0px | 100% |
| CF9 | CF8 + `main { padding: 12px }` | 0 | 0px | 100% |
| CF10 | CF9 + badge ellipsis | 0 | 0px | 100% |
| CF11 | CF10 + content/header `min-width: 0` final (no overflow hidden) | 0 | 0px | 100% |

### 3.2 Orders (baseline: 346px)

| CF | Intervention | Delta | Step Reduction | Cumulative % |
|----|-------------|-------|---------------|-------------|
| baseline | (none) | 346 | — | — |
| CF2 | `.ml-64 { margin-left: 0 }` | 90 | 256px | 74.0% |
| CF5 | + `.ml-64 { min-width: 0 }` | 66 | 24px | 80.9% |
| **CF7** | **+ header flex children `min-width: 0`** | **0** | **66px** | **100%** |

### 3.3 Key Insight

CF8-CF10 (header padding, main padding, badge ellipsis) contributed **0px** reduction. Once flex items can shrink via `min-width: 0`, the flex algorithm distributes available space correctly. The padding/badge fixes are quality-of-life improvements but not necessary for overflow elimination.

---

## 4. Affected Source Files

| File | Line(s) | Issue | RC# |
|------|---------|-------|-----|
| `frontend/src/components/layout/MainLayout.tsx` | 13 | `ml-64` unconditional, content wrapper needs `min-width: 0` | RC1, RC2 |
| `frontend/src/components/layout/Header.tsx` | 32 | `shrink-0` prevents header shrinking, flex children have auto min-width | RC3 |
| `frontend/src/components/layout/Sidebar.tsx` | 57 | `fixed w-64` unconditional — needs `hidden lg:flex` for responsive | RC1 (enabler) |

### Comparison: ClientLayout (Mobile-Safe)

`ClientLayout.tsx` uses:
- No sidebar, no fixed positioning, no margin-left
- `max-w-lg mx-auto` content constraint
- Sticky bottom navigation (mobile-native)
- Zero overflow on 390px viewport

---

## 5. R4-C1 Fix Scope Recommendation

### R4-C1 Mobile Navigation Contract (Pre-Implementation Spec)

| Requirement | Detail |
|-------------|--------|
| **Drawer pattern** | Sidebar hidden on mobile, toggleable via hamburger button in Header |
| **State owner** | `MainLayout.tsx` holds `sidebarOpen` boolean state |
| **Header hamburger** | `Header.tsx` renders hamburger `<button>` on `<lg` breakpoint, passes `onClick` toggle callback |
| **Sidebar as drawer** | On `<lg`: sidebar uses `translate-x` slide-in with backdrop overlay. On `lg+`: sidebar fixed visible as today |
| **Close triggers** | Hamburger toggle, backdrop click, Escape key |
| **Nav-after-close** | After drawer close, focus returns to hamburger button (a11y) |
| **No hidden-without-alternative** | At no breakpoint is sidebar hidden without a hamburger/drawer replacement |

### Minimum Viable Responsive Fix (CSS-only, 4 files)

| File | Change | Tailwind Equivalent |
|------|--------|-------------------|
| `MainLayout.tsx:13` | `ml-64` to `lg:ml-64`, add `min-w-0` on content wrapper, add `sidebarOpen` state + drawer wrapper | Responsive margin + flex shrink |
| `Sidebar.tsx:57` | Add `hidden lg:flex` on `<aside>`, accept `isOpen`/`onClose` props for mobile drawer mode | Hide on mobile, drawer on toggle |
| `Header.tsx:32` | Change `shrink-0` to `lg:shrink-0`, add `min-w-0` to header flex children, add hamburger button on `<lg` | Allow mobile shrink + nav trigger |
| `Header.tsx:56-58` | Badge gets `truncate` or `overflow-hidden text-ellipsis` on `<sm` | Truncate long tenant codes |
| `Header.tsx:32` | `px-6` to `px-4 lg:px-6` | Reduce mobile padding |

### Test Contract (R4-C1 Verification Criteria)

| # | Test | Expected |
|---|------|----------|
| T1 | Hamburger button visible and accessible at 390px viewport | `aria-label`, `role="button"`, in tab order |
| T2 | Drawer default-closed on mobile page load | Sidebar not in DOM accessibility tree or `aria-hidden="true"` |
| T3 | Drawer openable via hamburger click | Sidebar slides in, backdrop visible |
| T4 | Drawer closeable via hamburger, backdrop click, Escape | Sidebar slides out, backdrop removed |
| T5 | Desktop sidebar visible at 1024px+ | Sidebar visible, hamburger hidden |
| T6 | Mobile content has no fixed `ml-64` at 390px | `scrollWidth === clientWidth === 390` |
| T7 | Long tenant code (32 chars) + long user name no page-level overflow | `scrollWidth === clientWidth === 390` |
| T8 | Existing Sidebar nav link behavior unchanged on desktop | All 8 nav links functional, active state correct |
| T9 | Existing Header breadcrumb + tenant badge + user block unchanged on desktop | All visible, same layout at 1024px+ |

### Regression Test Files Required

| File | Purpose |
|------|---------|
| `pw1r4b/tests/phase6-responsive.spec.ts` | Existing mobile overflow regression (lines 17, 25) |
| New: `Pw1R4C1MainLayoutResponsive.test.tsx` | T1-T9 contract tests (hamburger, drawer, responsive sidebar, overflow) |

### Estimated Change Count

- **4 files** (3 modified + 1 new test file)
- **Risk: MEDIUM** — 29 wholesaler/platform routes affected; desktop (lg: 1024px+) behavior unchanged; drawer pattern is standard UX

---

## 6. Evidence Files

| File | Description |
|------|-------------|
| `evidence/dom_measurements.json` | Full DOM width + ancestor chain JSON for both pages, all 11 CFs |
| `evidence/findings.csv` | Machine-readable CF results (page, CF, delta, reduction %) |
| `evidence/dashboard_before.png` | Before fix screenshot (390x844, device pixel ratio) |
| `evidence/dashboard_after.png` | After fix screenshot (CF11: min-width:0 only, no overflow hidden) |
| `evidence/orders_before.png` | Before fix screenshot |
| `evidence/orders_after.png` | After fix screenshot (same fix, no overflow hidden) |
| `evidence/sha256_manifest.txt` | SHA256 of all evidence files via git blob |

---

## 7. Playwright Test Results (Authoritative)

```
2 failed, 5 passed (14.0s)

FAIL [mobile] phase6-responsive.spec.ts:17 — wholesaler dashboard overflow 374px
FAIL [mobile] phase6-responsive.spec.ts:25 — wholesaler orders overflow 346px
PASS [mobile] phase6-responsive.spec.ts:32 — retailer catalog overflow 0px
PASS [mobile] phase6-responsive.spec.ts:40 — retailer orders overflow 0px
PASS [mobile] phase6-responsive.spec.ts:47 — login forms accessible
PASS [mobile] phase6-responsive.spec.ts:60 — no unexpected network failures
PASS [mobile] phase6-responsive.spec.ts:68 — print stub no errors
```

---

## 8. Impact Analysis (Manual Blast Radius)

### 8.1 Component Dependency Chain

```
AppRouter.tsx
  ├── <MainLayout /> (2 route groups)
  │     ├── <Sidebar />  (RC1: ml-64 unconditional margin-left 256px)
  │     ├── <Header />   (RC3: shrink-0, flex children auto min-width)
  │     └── <Outlet />   (RC2: content wrapper min-width: auto)
  └── <ClientLayout /> (mobile-safe, unaffected)
```

### 8.2 Affected Routes (all under MainLayout, all overflow on mobile)

**Wholesaler ERP routes** (AppRouter.tsx:113):
| # | Route | Page Component |
|---|-------|----------------|
| 1 | `/` | DashboardPage |
| 2 | `/orders` | OrderListPage |
| 3 | `/orders/new` | WholesalerCreateOrderPage |
| 4 | `/inventory` | InventoryPage |
| 5 | `/inventory/logs` | InventoryLogPage |
| 6 | `/skus` | SKUListPage |
| 7 | `/skus/intake` | DataIntakePage |
| 8 | `/skus/scan` | MobileScanPreview |
| 9 | `/retailers` | RetailerListPage |
| 10 | `/pricing` | RetailerPricingPage |
| 11 | `/tenants` | TenantListPage |
| 12 | `/finance` | FinancePage |
| 13 | `/payments` | PaymentListPage |
| 14 | `/declarations` | DeclarationQueuePage |
| 15–19 | Print/receipt/statement routes | OrderPrintPage, DeclarationPrintPage, etc. |

**Platform Admin routes** (AppRouter.tsx:202):
| # | Route | Page Component |
|---|-------|----------------|
| 20–29 | `/platform/*` | PlatformOverviewPage, PlatformTenantDirectoryPage, etc. |

**Total: ~29 routes affected** (all pages wrapped by MainLayout).

### 8.3 Unaffected Routes (ClientLayout — mobile-safe)

All `/client/*` routes use `ClientLayout` (bottom nav, max-w-lg, zero overflow). These are **not affected** by the MainLayout overflow bug.

### 8.4 Test Files Referencing Affected Components

| Test File | Component |
|-----------|-----------|
| `layout/__tests__/SidebarOps.test.tsx` | Sidebar |
| `layout/__tests__/SidebarApprovals.test.tsx` | Sidebar |
| `tests/Header.test.tsx` | Header |
| `platform/__tests__/p25/P25_SidebarNav.test.tsx` | Sidebar |
| `platform/__tests__/PlatformControlledExecutionNav.test.tsx` | Sidebar |
| `platform/__tests__/PlatformIncidentCloseoutsNav.test.tsx` | Sidebar |
| `platform/__tests__/PlatformOperatorTasksNav.test.tsx` | Sidebar |
| `tests/phase6-responsive.spec.ts` | Integration (2 failing) |

### 8.5 Risk Assessment

- **Risk: MEDIUM** — All wholesaler ERP and platform admin pages overflow on mobile, but retailer-facing pages (ClientLayout) are unaffected.
- **Fix scope:** 3 source files (MainLayout.tsx, Sidebar.tsx, Header.tsx), ~5 CSS class changes.
- **Test scope:** Existing phase6-responsive.spec.ts will validate fix; no new tests needed for diagnosis phase.

---

## 9. GitNexus Impact Tool Note

The `gitnexus_impact` tool could not locate repository `_r1base_product` (not indexed). Manual impact analysis above covers the full blast radius via source code grep of `AppRouter.tsx` route tree and all import references to `MainLayout`, `Sidebar`, and `Header`.
