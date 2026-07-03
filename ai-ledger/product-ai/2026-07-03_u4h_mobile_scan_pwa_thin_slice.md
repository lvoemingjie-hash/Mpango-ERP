# U4-H-A -- Mobile Scan/PWA Feasibility + Thin Slice Contract

**Date**: 2026-07-03
**Branch**: `opencode/u4h-a-r1-mobile-scan-clean-rebase-2026-07-03`
**Lineage**: `origin/product-dev-recovered`
**Verdict**: `PASS_FOR_CTO_U4H_REVIEW`

**Round**: R1 (thin slice) + R2 (detect-loop fix)

---

## 0. Feasibility Decision

| Question | Answer |
|----------|--------|
| Can BarcodeDetector be used without new dependency? | **YES** -- native Web Platform API (Chrome/Edge/Android). No npm package. |
| Is implementation safe (no backend/migration/deploy)? | **YES** -- purely frontend, preview-only, zero API calls. |
| PWA manifest changes needed? | **NO** -- works in any mobile browser with camera. PWA installability deferred. |
| Can scan result connect to intake pipeline safely? | **PARTIAL** -- preview-only this slice. Upload endpoint expects CSV/XLSX files; a barcode produces a code string. Connecting scan to staging requires a new backend endpoint (next slice). |

**Decision**: Implementation is SAFE. Proceed with thin slice.

---

## 1. What Was Built

### MobileScanPreview.tsx (new component)

Standalone mobile scan preview with:
- Native BarcodeDetector (EAN-13/8, Code-128/39, UPC-A/E, QR).
- Manual barcode/SKU text input fallback (always visible).
- Preview-only display (code + timestamp + source label).
- Copy to clipboard button.
- Zero backend calls (onScan callback lets parent decide).
- No image persistence (in-memory only).

### MobileScanPreview.test.tsx (10 tests, all PASS)

**R1 tests (8):**

| # | Test | Proves |
|---|------|--------|
| 1 | BarcodeDetector unavailable -> manual fallback | jsdom fallback works |
| 2 | Does not crash without BarcodeDetector | Safe rendering |
| 3 | Displays captured code after manual submit | Result visible |
| 4 | Calls onScan callback | Correct callback data |
| 5 | Disables capture when input empty | Validation |
| 6 | No backend API called on scan | Preview-only (fetch spy) |
| 7 | Shows disclaimer on result | Preview-only invariant |
| 8 | No public/anonymous entry point | Internal-login-only |

**R2 tests (2):**

| # | Test | Proves |
|---|------|--------|
| 9 | Retries detect() when first call returns empty array | Loop retries transient failures |
| 10 | Stops after barcode detected, calls onScan exactly once | Single-scan invariant; ref stops loop |

---

## 2. Why Preview-Only

The intake upload endpoint expects a CSV/XLSX file. A barcode scan produces a
code string, not a file. Connecting the scan to staging requires a new backend
endpoint (out of scope: "No backend changes unless CTO approves"). The scan
result is therefore preview-only.

**Next slice (U4-H-B)** would add scan-to-staging connection.

---

## 3. Integration Plan

When rebased onto product-dev-recovered (where DataIntakePage exists):

```tsx
import { MobileScanPreview } from './MobileScanPreview';
<MobileScanPreview onScan={(result) => console.log(result.code)} />
```

Drop-in card, no coupling to DataIntakePage internals.

---

## 4. R2 — Detect Loop Fix (scanningRef)

### Problem
The `detectLoop` callback was closing over the React `scanning` state. When `stopCamera()` was called, the stale closure saw `scanning=true` and continued scheduling `requestAnimationFrame` — causing the loop to never stop and the `onScan` callback to potentially fire multiple times.

### Fix
- Added `scanningRef` (`useRef(false)`) that mirrors the `scanning` state.
- `startCamera`: sets `scanningRef.current = true` **before** scheduling the loop.
- `stopCamera`: sets `scanningRef.current = false` **first**, then cancels the RAF.
- `detectLoop`: reads `scanningRef.current` instead of `scanning` state, and `scanning` is removed from the `useCallback` dependency array.

### R2 Commit
```
6937c44 fix(U4-H-A): R2 -- scanningRef replaces stale scanning state in detect loop; +2 camera-loop tests
2 files changed, 116 insertions(+), 2 deletions(-)
```

### R2 Test Results
```
vitest run src/tests/MobileScanPreview.test.tsx
Test Files  1 passed (1)
     Tests  10 passed (10)

tsc --noEmit: 0 errors
vite build: built in ~5s
```

---

## 5. Boundaries Honored

| Constraint | Status |
|-----------|--------|
| No backend changes | PASS |
| No migration / deploy | PASS |
| No product-dev-recovered push | PASS |
| No new dependency | PASS |
| No image persistence | PASS |
| No public/anonymous access | PASS |
| No apply/SKU write API | PASS |

---

## 6. Test Results (R1+R2 Combined)

```
vitest run src/tests/MobileScanPreview.test.tsx
Test Files  1 passed (1)
     Tests  10 passed (10)

tsc --noEmit: 0 errors
vite build: built in ~5s
```

---

## 7. Quality Gates

| Check | Status |
|-------|--------|
| git diff --check | PASS |
| ASCII/mojibake scan | PASS |
| Secret scan | PASS |
| Linter | PASS |
| tsc | PASS |
| vite build | PASS |
| pre-commit | PASS |

---

## 8. Files Changed (R1+R2)

| File | Change |
|------|--------|
| `frontend/src/pages/skus/MobileScanPreview.tsx` | NEW (R1) + FIX (R2): scan component + scanningRef |
| `frontend/src/pages/skus/SKUListPage.tsx` | MODIFIED: add mobile scan link |
| `frontend/src/router/AppRouter.tsx` | MODIFIED: add /skus/scan route |
| `frontend/src/tests/MobileScanPreview.test.tsx` | NEW: 8 tests (R1) + 2 camera-loop tests (R2) |

---

## 9. Verdict

```
PASS_FOR_CTO_U4H_REVIEW
```
