# P12-C0 Support Console Frontend Wiring Contract Ledger

**Date:** 2026-06-11
**Branch:** `codex/platform-p12c0-support-console-frontend-contract-2026-06-11`
**Base:** `origin/platform-dev` at `3fca6d2` (P12-B + R1 + R3 merge)
**C0 commit:** (pending)
**Status:** Frontend wiring/contract slice -- types, API client, route shell, reason-required form shell

---

## Branch

- **Branch name:** `codex/platform-p12c0-support-console-frontend-contract-2026-06-11`
- **Base ref:** `origin/platform-dev` at `3fca6d2`

## Modified Files (9 total)

| # | File | Action |
|---|------|--------|
| 1 | `frontend/src/types/support.ts` | **New** -- P12 support console types mirroring backend schemas |
| 2 | `frontend/src/services/supportApi.ts` | **New** -- P12 API client (4 methods) |
| 3 | `frontend/src/pages/platform/SupportConsolePage.tsx` | **New** -- Route shell with reason-required form |
| 4 | `frontend/src/router/AppRouter.tsx` | **Modified** -- Add `/platform/support` route |
| 5 | `frontend/src/components/layout/Sidebar.tsx` | **Modified** -- Add Support Console nav item |
| 6 | `frontend/src/types/__tests__/support.test.ts` | **New** -- 19 type/helper tests |
| 7 | `frontend/src/services/__tests__/supportApi.test.ts` | **New** -- 6 API client tests |
| 8 | `frontend/src/pages/platform/__tests__/SupportConsolePage.test.tsx` | **New** -- 9 component tests |
| 9 | `ai-ledger/platform/2026-06-11_p12c0_support_console_frontend_contract.md` | **New** -- This ledger |

## What P12-C0 Provides

| Component | Detail |
|-----------|--------|
| **Types** | `SupportCategory`, `SupportSessionStatus`, `BundleType`, `DiagnosticSourceStatus`, `SupportSession`, `SupportDiagnosticItem`, `SupportBundle`, `SupportErrorDetail`, `CreateSessionRequest`, `CreateBundleRequest` |
| **API client** | `supportService.createSession()`, `.getDiagnostics()`, `.createBundle()`, `.closeSession()` |
| **Route shell** | `/platform/support` under `PlatformRoute` guard (identity-only super_admin) |
| **Reason form** | Textarea with client-side min 10 char validation, category select, tenant ID input, Start/Close session buttons |
| **Validation helpers** | `isReasonValid()`, `getReasonValidationError()`, `REASON_MIN_LENGTH` |
| **Error handling** | Backend 400 `MISSING_REASON` / `REASON_TOO_SHORT` display safe messages (belt-and-suspenders with client-side validation) |

## What P12-C0 Does NOT Provide

- No full diagnostics dashboard (future P12-C slice)
- No support bundle download UI (future P12-C slice)
- No tenant assignment/role management
- No impersonation controls
- No backend changes
- No new package dependencies

## Contract Rule: Frontend Reason Required

`CreateSessionRequest.reason` is `Optional[str]` in the backend Pydantic schema **only** to allow route-layer 400 + `support_access_denied` audit (P12-B-R3). The frontend **MUST** require reason (minimum 10 characters) before making the API call. This is enforced by:

1. `isReasonValid()` helper returns false for null/empty/short reason
2. `getReasonValidationError()` returns error message for invalid reason
3. "Start Session" button is **disabled** when reason is invalid
4. `CreateSessionRequest` interface in `types/support.ts` declares `reason: string` (not Optional)
5. Explicit contract note comment in `types/support.ts` explaining the backend Optional is an implementation detail

## Tests

### Frontend: 86 passed, 0 failed (34 P12-C0 new)

| File | Tests | Coverage |
|------|-------|----------|
| `types/__tests__/support.test.ts` | 19 | isReasonValid (7), getReasonValidationError (4), REASON_MIN_LENGTH (1), SupportSession conformance (1), SupportDiagnosticItem (2), SupportBundle (1), SupportErrorDetail (2) |
| `services/__tests__/supportApi.test.ts` | 6 | createSession endpoint (2), getDiagnostics (1), createBundle (2), closeSession (1) |
| `pages/platform/__tests__/SupportConsolePage.test.tsx` | 9 | Renders inputs (1), empty reason disabled (1), short reason disabled (1), valid reason enabled (1), validation error display (1), MISSING_REASON error (1), REASON_TOO_SHORT error (1), no impersonation (1), limitation notice (1) |

### Existing frontend regression: 52 passed (P10/P11 tests unchanged)

### Backend: 62 P12 passed, 137 P10 passed (no backend changes)

### Harness gates: 62 agent, 6 runner, 23 directive -- all passed

## GitNexus

| Field | Value |
|-------|-------|
| Nodes | 6,257 |
| Edges | 18,504 |
| Clusters | 413 |
| Flows | 272 |

## Validation

| Check | Result |
|-------|--------|
| Frontend tests | **86 passed**, 0 failed |
| Backend P12 tests | **62 passed**, 0 failed (no backend changes) |
| Backend P10 tests | **137 passed**, 0 failed |
| Agent mission gate | **62 passed** |
| Runner gate | **6 passed** |
| Directive gate | **23 passed** |
| `git diff --check` | PASS |
| Forbidden path audit | PASS (0 hits) |
| No new package dependencies | CONFIRMED |
| No backend files changed | CONFIRMED |
| No auth/RBAC/session/tenancy/payment changes | CONFIRMED |
| GitNexus analyze | PASS -- 6,257 nodes, 18,504 edges |

## Forbidden Path Audit

| Path Pattern | Files Found | Status |
|---|---|---|
| `frontend/src/pages/auth/` | 0 | PASS |
| `frontend/src/stores/authStore` | 0 | PASS |
| `migrations/` | 0 | PASS |
| `product-dev-recovered/` | 0 | PASS |
| `.github/` | 0 | PASS |
| `.claude/` | 0 | PASS |

**Only frontend/src/ and ai-ledger/ files modified. No backend changes.**

## Risk

| Factor | Rating | Notes |
|--------|--------|-------|
| Scope | MEDIUM | Frontend wiring only: types, API client, route shell, form shell |
| Backend impact | NONE | No backend files modified |
| Auth changes | NONE | Reuses existing PlatformRoute guard |
| Package deps | NONE | No new dependencies added |
| Test coverage | HIGH | 34 new P12-C0 tests + 52 existing frontend regression |

**Overall risk: MEDIUM.** Frontend-only surface for platform support console. All impacts confined to P12 frontend files.

## Note: platform-dev Not Merged or Pushed

`platform-dev` was **not merged** and **not pushed** as part of P12-C0. Only the isolated branch was pushed.

## Blockers

None. All gates passed.
