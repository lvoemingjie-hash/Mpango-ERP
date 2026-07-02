# U4-H-A -- Mobile Scan/PWA Feasibility + Thin Slice Contract

**Date**: 2026-07-03
**Branch**: `opencode/u4h-mobile-scan-pwa-thin-slice-2026-07-03`
**Lineage**: `origin/product-dev-recovered`
**Verdict**: `PASS_FOR_CTO_U4H_REVIEW`

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

### MobileScanPreview.test.tsx (8 tests, all PASS)

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

### Test infrastructure (vitest.config.ts + setup.ts)

The branch lacked vitest config. Added jsdom environment + jest-dom matchers +
ResizeObserver polyfill (test-only, not product code).

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

## 4. Boundaries Honored

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

## 5. Test Results

```
vitest run src/tests/MobileScanPreview.test.tsx
Test Files  1 passed (1)
     Tests  8 passed (8)

tsc --noEmit: 0 errors
vite build: built in 5.00s
```

---

## 6. Quality Gates

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

## 7. Files Changed

| File | Change |
|------|--------|
| `frontend/src/pages/skus/MobileScanPreview.tsx` | NEW: scan component |
| `frontend/src/tests/MobileScanPreview.test.tsx` | NEW: 8 tests |
| `frontend/vitest.config.ts` | NEW: vitest config (jsdom) |
| `frontend/src/tests/setup.ts` | NEW: test setup |

---

## 8. Verdict

```
PASS_FOR_CTO_U4H_REVIEW
```
