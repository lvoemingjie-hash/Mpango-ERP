# PW1-R2 Phase 1 — Pre-edit regression checklist (saved BEFORE any edit)

Baseline: d2e7e44cf23e91cabfab545c494abd342fec3062 (worktree C:\Users\Jeff0\pw1_r2_worktree)

## Direct callers census (grep, complements GitNexus; JSX composition not modeled by graph)

| Symbol | Production callers | Test callers | Notes |
|---|---|---|---|
| useAuthStore | ClientLayout, Header, Sidebar, DashboardPage, LoginPage, WorkspaceSelectorPage, ClientLoginPage, InventoryPage, CreateOrderPage, OrderListPage, 6 platform pages, RetailerPricingPage, DataIntakePage, SKUListPage, TenantListPage, api.ts, guards.tsx | many (src/tests, src/router/__tests__, src/pages/platform/__tests__) | 187 refs; read-only consumers use selectors (accessToken/user/tenantCode/retailerPortalCode) |
| updateTokens | **api.ts:135,161 (token-refresh interceptor)**, LoginPage:96 (to be replaced), WorkspaceSelectorPage:41 (to be removed), authStore itself | SKUListPage.test.tsx | refresh flow MUST keep working |
| PublicRoute | AppRouter.tsx (public layout) | guards.test.tsx | redirect target '/' under change |
| ProtectedRoute | AppRouter.tsx; comment in LoginPage.tsx:53 | — | admission rule under change |
| WholesalerRoute | AppRouter.tsx | Dc12r1S2RetailerPortal, PrintableWorkspace tests | retailer bounce rule must survive |
| RetailerRoute | AppRouter.tsx | 3 test files | unchanged semantics |
| WorkspaceSelectorPage | AppRouter.tsx | — | atomic completion under change |

GitNexus impact evidence: pw1_r2_evidence/impact_*.json (upstream). TS/JSX caveat:
graph models file-level CodeRelation edges for frontend; React JSX usage counted via
grep census above. Auth surface risk: **CRITICAL** (guards + session store).

## Regression checklist (must stay green after the change)

1. Owner single-tenant login: /auth/login 200 -> auto select-tenant 200 -> me -> '/' dashboard (Condition B unchanged).
2. super_admin login: identity me + login() -> '/' (Condition A unchanged).
3. Multi-tenant owner/retailer: /auth/login 200 -> '/select-workspace' RENDERS tenants (D1 closure) -> select -> select-tenant 200 -> me 200 -> '/' or '/client' by role.
4. Retailer portal login (/retail/login?w=CODE): client login 200 -> '/client', retailerPortalCode preserved (unchanged).
5. Logout: clears tokens/user/tenantCode, preserves retailerPortalCode, -> '/login' (unchanged).
6. Refresh flow (api.ts): 401 -> POST /auth/refresh -> updateTokens -> retry; failure -> logout + redirect (unchanged; updateTokens remains the established-session refresher).
7. Protected routes: anonymous -> '/login' (or retailer portal when retailerPortalCode set).
8. WholesalerRoute: retailer_operator with contextual session -> '/client'; stale retailer session -> portal login.
9. RetailerRoute: non-retailer -> '/login' or portal.
10. /select-workspace without navigation state -> '/login' (unchanged).
11. Pending identity session (token-only): must NOT enter '/', MainLayout, or fire dashboard APIs; PublicRoute must not bounce it to '/'.
12. Owner login 401 -> fixed neutral 'Invalid credentials'; no axios/message/request_id/body/code leakage; URL unchanged; zero token persistence.
13. Single form submit -> exactly ONE POST /auth/login.

## Scope guards (STOP if touched)
Allowed: stores/authStore.ts, router/guards.tsx, pages/auth/LoginPage.tsx,
pages/auth/WorkspaceSelectorPage.tsx, src/tests/* (new tests),
ai-ledger/product-ai/2026-08-14_dc12r1_mvp_l1_pw1_r2_auth_session_closure.md.
