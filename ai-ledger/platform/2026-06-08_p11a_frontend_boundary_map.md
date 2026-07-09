# P11-A Frontend Boundary Map -- Batch Readiness Packet

**Date**: 2026-06-08
**Branch**: `codex/platform-p11a-frontend-boundary-map-2026-06-08`
**Base**: `origin/platform-dev` at `2bbe8e9efd0f8a72898b5ef6bf1768bdf192fe08`
**Status**: Ready for review

---

## Objective

Map the frontend boundary for the first Platform Admin Cockpit UI. This is docs/ledger only -- no UI code built.

## Deliverables

| File | Action |
|------|--------|
| `docs/ai/PLATFORM_PRODUCT_P11_FRONTEND_BOUNDARY.md` | New -- boundary document |
| `docs/ai/README.md` | Modified -- added P11 entry to Platform Product Track read order |
| `ai-ledger/platform/2026-06-08_p11a_frontend_boundary_map.md` | New -- this ledger |

**Total**: 2 new files, 1 modified file, 0 deletions.

## Document Contents

The boundary document defines:

1. **Allowed frontend files/areas** -- new `pages/platform/`, `components/platform/`, `services/platformApi.ts`, `stores/platformStore.ts`, `types/platform.ts`
2. **Forbidden areas** -- auth/RBAC/session rewrites, payment flows, tenant business data, client app, migrations, backend code
3. **Route shape** -- `/platform/*` route group under `PlatformRoute` guard (super_admin only)
4. **P10 API client usage** -- service layer using existing Axios singleton, typed to P10-A contracts
5. **State rules** -- loading -> Skeleton, error -> retry card, empty -> EmptyState, unknown -> gray badge distinct from healthy
6. **Test plan** -- ~33 tests across route guard, type conformance, service layer, component render, state display, integration, forbidden
7. **Risks and open questions** -- platform auth transport gate (blocking for P11-B), sidebar visibility, real-time updates
8. **Implementation phasing** -- P11-B foundation, P11-C directory, P11-D detail

## Key Decisions Documented

| Decision | Resolution |
|----------|-----------|
| Where platform pages live | `pages/platform/` -- isolated from tenant business pages |
| Route guard | New `PlatformRoute` component checking `user.roles.includes('super_admin')` |
| API client | Reuse existing `api.ts` Axios singleton; no separate client |
| State management | New `platformStore.ts` (Zustand) -- isolated from product stores |
| Unknown vs healthy | Gray badge + "N/A" for unknown; green badge for healthy; explicit test cases |
| Write buttons | None in P11 -- all pages read-only |
| Auth transport | BLOCKING for P11-B -- frontend cannot assume Bearer tokens work with P10 guard |

## Open Questions for P11-B

1. **BLOCKING: Platform auth transport** -- P10 production guard requires `X-Platform-Operator` header. Frontend cannot assume Bearer tokens will pass it. P11-B must resolve with an explicit approved decision: (A) frontend sends X-Platform-Operator, or (B) backend guard is extended via separate approved backend/security slice. Not silently assumed.
2. Should "Platform" sidebar item be hidden or grayed out for non-super-admin?

## P11-A-R1: Evidence and Polish Fixes

### README Startup Index Fixed

Added `docs/ai/PLATFORM_PRODUCT_P11_FRONTEND_BOUNDARY.md` as item 11 in the Platform Product Track Entry section of `docs/ai/README.md`, after P10 docs.

### Mojibake / Non-ASCII Fixed

Replaced all non-ASCII characters in both docs and ledger with ASCII equivalents:
- Em-dashes (U+2014) -> `--`
- Box-drawing chars (U+251C, U+2500, U+2502, U+2514) -> `|`, `-`, `|`, `|`
- Not-equal (U+2260) -> `!=`
- Right arrow (U+2192) -> `->`
- Cross/check marks (U+274C, U+2705) -> `X`, `OK`

Both files verified: 0 non-ASCII bytes remaining.

### Auth Transport Contradiction Resolved

Original P11-A doc stated "frontend sends standard Bearer tokens" but P10 production guard requires `X-Platform-Operator` header. This was a contradiction.

**Fixed by:**
- Removed the claim that frontend can assume Bearer tokens work with P10.
- Added a BLOCKING gate for P11-B: auth transport must be explicitly resolved before API wiring.
- Added as first item in boundary checklist.
- Elevated to HIGH risk in risks table.
- Made it the #1 open question for P11-B.
- Clarified that if backend guard needs changing, that requires a separately approved backend/security slice.

## Tests

No runtime tests in P11-A (docs-only).

Expected P11-B+ test plan: ~33 tests.

## GitNexus Risk

**LOW** -- docs-only changes. No runtime code, no frontend code, no backend code. Modified README and two new markdown files.

## Forbidden Path Audit

| Path Pattern | Found |
|-------------|-------|
| `backend/` code | X None |
| `frontend/src/` code | X None |
| `frontend/` package/build config | X None |
| `.github/` | X None |
| `.claude/` | X None |
| `product-dev-recovered/` | X None |
| `migration/` | X None |
| `payment/` | X None |
| `session/` | X None |
| `auth/` (broad rewrite) | X None |
| Docs + ledger + README only | OK Confirmed |

## Push Status

Branch `codex/platform-p11a-frontend-boundary-map-2026-06-08` pushed. Not merged to `platform-dev`.
