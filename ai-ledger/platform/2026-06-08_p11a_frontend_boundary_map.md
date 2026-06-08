# P11-A Frontend Boundary Map — Batch Readiness Packet

**Date**: 2026-06-08
**Branch**: `codex/platform-p11a-frontend-boundary-map-2026-06-08`
**Base**: `origin/platform-dev` at `2bbe8e9efd0f8a72898b5ef6bf1768bdf192fe08`
**Status**: Ready for review

---

## Objective

Map the frontend boundary for the first Platform Admin Cockpit UI. This is docs/ledger only — no UI code built.

## Deliverables

| File | Action |
|------|--------|
| `docs/ai/PLATFORM_PRODUCT_P11_FRONTEND_BOUNDARY.md` | New — boundary document |
| `ai-ledger/platform/2026-06-08_p11a_frontend_boundary_map.md` | New — this ledger |

**Total**: 2 new files, 0 modified files, 0 deletions.

## Document Contents

The boundary document defines:

1. **Allowed frontend files/areas** — new `pages/platform/`, `components/platform/`, `services/platformApi.ts`, `stores/platformStore.ts`, `types/platform.ts`
2. **Forbidden areas** — auth/RBAC/session rewrites, payment flows, tenant business data, client app, migrations, backend code
3. **Route shape** — `/platform/*` route group under `PlatformRoute` guard (super_admin only)
4. **P10 API client usage** — service layer using existing Axios singleton, typed to P10-A contracts
5. **State rules** — loading → Skeleton, error → retry card, empty → EmptyState, unknown → gray badge distinct from healthy
6. **Test plan** — ~33 tests across route guard, type conformance, service layer, component render, state display, integration, forbidden
7. **Risks and open questions** — platform auth context resolution, sidebar visibility, real-time updates
8. **Implementation phasing** — P11-B foundation, P11-C directory, P11-D detail

## Key Decisions Documented

| Decision | Resolution |
|----------|-----------|
| Where platform pages live | `pages/platform/` — isolated from tenant business pages |
| Route guard | New `PlatformRoute` component checking `user.roles.includes('super_admin')` |
| API client | Reuse existing `api.ts` Axios singleton; no separate client |
| State management | New `platformStore.ts` (Zustand) — isolated from product stores |
| Unknown vs healthy | Gray badge + "N/A" for unknown; green badge for healthy; explicit test cases |
| Write buttons | None in P11 — all pages read-only |

## Open Questions for P11-B

1. Should frontend send `X-Platform-Operator` header automatically for super_admin users, or should backend accept Bearer tokens for platform operators?
2. Should "Platform" sidebar item be hidden or grayed out for non-super-admin?

## Tests

No runtime tests in P11-A (docs-only).

Expected P11-B+ test plan: ~33 tests.

## GitNexus Risk

**LOW** — docs-only changes. No runtime code, no frontend code, no backend code. Two new markdown files only.

## Forbidden Path Audit

| Path Pattern | Found |
|-------------|-------|
| `backend/` code | ❌ None |
| `frontend/src/` code | ❌ None |
| `frontend/` package/build config | ❌ None |
| `.github/` | ❌ None |
| `.claude/` | ❌ None |
| `product-dev-recovered/` | ❌ None |
| `migration/` | ❌ None |
| `payment/` | ❌ None |
| `session/` | ❌ None |
| `auth/` (broad rewrite) | ❌ None |
| Docs + ledger only | ✅ Confirmed |

## Push Status

Branch `codex/platform-p11a-frontend-boundary-map-2026-06-08` will be pushed after verification. Not merged to `platform-dev`.
