# S5-D2-R2 -- Adjust Stock Modal SKU Binding Fix

**Date**: 2026-06-26
**Branch**: `opencode/s5d2-r2-adjust-stock-modal-sku-binding-2026-06-26`
**Lineage**: `origin/product-dev-recovered` (`0d88b1a`)
**Verdict**: `PASS_FOR_CTO_REVIEW`

---

## Problem

S5-D2-BROWSER found that the Adjust Stock modal opened with a disabled SKU Code
field that was **empty** instead of showing the selected SKU code.

### Root Cause

`InventoryAdjustModal.tsx` misused `useState` as a side-effect:

```tsx
// BUG: useState initializer runs ONCE on initial mount only.
useState(() => {
  if (isOpen) {
    reset({ sku_code: initialSkuCode, quantity: 0, reason: '' });
    setError(null);
  }
});
```

`useState(initializer)` invokes the initializer function exactly once during the
**first render** to compute initial state. It is never called again on subsequent
renders. Since `InventoryPage` mounts the modal once and toggles `isOpen`/`initialSkuCode`,
the `reset()` call never fires when the modal reopens with a new SKU -- the form
retains whatever default values it had at initial mount (when `initialSkuCode` was `''`
and `isOpen` was `false`).

Additionally, the initializer returns `undefined` (no state value), so the
`useState` itself is dead -- it creates a state slot that is never read or written.

### Secondary Issue

The `<label>` elements were not associated with their `<input>` elements (missing
`htmlFor`/`id`). This is an accessibility defect and prevented `getByLabelText`
from resolving form controls in tests.

---

## Solution

### 1. Replace `useState` side-effect with `useEffect`

```tsx
import { useState, useEffect } from 'react';

// ...

useEffect(() => {
  if (isOpen) {
    reset({ sku_code: initialSkuCode, quantity: 0, reason: '' });
    setError(null);
  }
}, [isOpen, initialSkuCode, reset, setError]);
```

`useEffect` fires after every render where its dependencies changed. Now when the
modal opens (`isOpen: false -> true`) or the parent selects a different SKU
(`initialSkuCode` changes), the form resets correctly:
- `sku_code` = `initialSkuCode`
- `quantity` = `0`
- `reason` = `""`
- `error` cleared

### 2. Associate labels with inputs (`htmlFor`/`id`)

Added `htmlFor`/`id` pairs to all three fields:
- SKU Code: `adjust-sku-code`
- Quantity: `adjust-quantity`
- Reason: `adjust-reason`

This fixes accessibility (screen readers can associate labels) and enables
`getByLabelText` queries in tests.

### What was NOT changed

- The `disabled={!!initialSkuCode}` logic is correct and unchanged -- when a SKU
  is provided (modal opened from a specific row), the field is locked.
- The submit handler (`handleFormSubmit`) is unchanged -- it already passes the
  full `AdjustFormData` (including `sku_code`) to `onSubmit`.
- No backend changes. No deployment. No `product-dev-recovered` push.

---

## Files Changed

| File | Change |
|------|--------|
| `frontend/src/pages/inventory/InventoryAdjustModal.tsx` | +12/-7: `useState` -> `useEffect`, added `htmlFor`/`id` on 3 label/input pairs |
| `frontend/src/tests/InventoryAdjustModal.test.tsx` | +152 (new): 3 tests covering SKU display, submit payload, reset-on-reopen |

---

## Test Results

### New test file: `InventoryAdjustModal.test.tsx` (3 tests, all PASS)

| # | Test | What It Proves |
|---|------|----------------|
| 1 | `displays the initialSkuCode in the disabled SKU field when open` | SKU field shows `S5D2B-CHARGER01` and is disabled when modal opens |
| 2 | `submits sku_code=initialSkuCode with quantity and reason` | `onSubmit` receives `{ sku_code: 'S5D2B-CHARGER01', quantity: -5, reason: 'Damaged in transit' }` |
| 3 | `resets the SKU field when re-opened with a different initialSkuCode` | Re-rendering with new SKU updates the field from `SKU-A` to `SKU-B` |

### Full frontend suite (27 tests, 0 failures)

```
Total: 27 | Pass: 27 | Fail: 0 | Skip: 0

  tests/InventoryAdjustModal.test.tsx => passed
  tests/S5BRealUserSmoke.test.tsx     => passed
  tests/SKUImportE2E.test.tsx         => passed
  tests/SKUImportModal.test.tsx       => passed
  tests/SKUListPage.test.tsx          => passed
```

No regressions. All pre-existing tests continue to pass alongside the 3 new tests.

### Build (PASS)

```
vite v5.4.21 building for production...
transforming...
1228 modules transformed.
built in 4.85s

dist/index.html                   0.51 kB | gzip:   0.33 kB
dist/assets/index-Cp7fv4FB.css   34.93 kB | gzip:   6.24 kB
dist/assets/index-DDw-X1CL.js   542.11 kB | gzip: 157.22 kB
```

TypeScript type check (`tsc --noEmit`): PASS (0 errors).

---

## Quality Gates

| Check | Status |
|-------|--------|
| Frontend only (no backend changes) | PASS |
| No deploy | PASS |
| No `product-dev-recovered` push | PASS |
| `git diff --check` | PASS (no whitespace/conflict markers) |
| Mojibake scan (em-dash, arrows, smart quotes) | PASS (0 matches on both files) |
| Secret scan (password/secret/token patterns) | PASS (0 matches) |
| Linter diagnostics | PASS (0 errors on both files) |

---

## Risk Assessment

- **Blast radius**: LOW. `InventoryAdjustModal` is rendered only by
  `InventoryPage.tsx`. The change is a 1:1 behavioral fix (form now resets
  correctly on open) plus an accessibility improvement (label association).

- **Behavioral change**: The form now resets `quantity` and `reason` every time
  the modal opens. This is the correct UX -- stale values from a previous
  adjustment should not persist into a new one.

- **Rollback**: Revert the single commit. No data or state implications.
