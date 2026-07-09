# P17-B/C Platform Registry Read-Only Adapter + Cockpit -- Ledger

**Date:** 2026-06-22
**Branch:** `codex/platform-p17bc-registry-adapter-cockpit-2026-06-22`
**Base:** `40f5efb` (origin/platform-dev -- P17-A platform registry lifecycle
contract merge; confirmed as an ancestor of this branch).
**Implementation commit:** `79f306c` (P17-B/C read-only adapter + cockpit; 13
files, 2719 insertions). Push target:
`origin/codex/platform-p17bc-registry-adapter-cockpit-2026-06-22`.
**Report path:** `ai-ledger/platform/2026-06-22_p17bc_registry_adapter_cockpit.md`
(this ledger is the persisted report; the final machine-readable report is
delivered in the work session).
**Author:** Codex (Claude worker)
**Statement:** **Read-only only.** No mutation endpoints, no lifecycle/flag/
provisioning/backup mutations, no migrations, no auth/RBAC/session/tenancy
rewrite, no tenant business tables, no product-dev-recovered change.

---

## Summary

P17-B and P17-C implement the platform registry as a **read-only capability**
behind the existing identity-only super_admin boundary, exactly as the P17-A
contract's P17-B entry gate (section 9) permits.

- **P17-B (backend):** a read-only registry adapter that composes the six
  P17-A data contracts (`PlatformTenantRegistry`, `TenantLifecycleState`,
  `TenantOperationalFlags`, `TenantProvisioningStatus`, `TenantBackupStatus`,
  `TenantRegistryAuditEvent`) and assembles them from **existing** read-only
  sources only (P10 tenant identity + the `PlatformTenant` provisioning
  journal). Every field whose source is unavailable reads its documented
  fallback (`null` / `unknown` / `false`) with a visible reason -- never a
  fabricated `healthy` / `active` / `success` / `exists`.
- **P17-C (frontend):** a read-only Platform Admin Cockpit registry page
  (`/platform/registry`) that renders the registry with `unknown` as gray
  (never green), `null` as `N/A` (never `0`), reasons always visible, and
  **no mutation controls** (no pause/resume/suspend/re-provision/retry/backup).

`unknown` is never `healthy`/`active`; `null` is never `0`/`false`. A stale
`success` backup reads `stale`, never `success` (C4). `failure_reason_redacted`
is an allowlisted reason code only (C2/C6). No tenant business records
(orders/payments/invoices/customers) are queried or exposed.

---

## Conservative role granularity (deferred)

Per the P17-A permission matrix (section 6), `support_operator` and
`engineering_operator` have strictly narrower field visibility than
`super_admin`. Those platform operator roles are **not yet distinguished by the
current auth context** -- the existing token carries `is_super_admin` /
`is_identity_only` only, with no `support_operator` / `engineering_operator`
entitlement (the same constraint documented by P10/P13/P15).

This phase therefore implements **conservative super_admin-only access** by
reusing the existing P10 guard (`require_platform_operator`) unchanged: only an
**identity-only (global) super_admin** (or the operator secret / test override)
may read the registry; a tenant-contextual super_admin and every non-super_admin
role are denied (401/403). The finer per-role field redaction
(support-safe subset, engineering full diagnostics) is **deferred** until
platform auth introduces those roles; the contract and the allowlisted
`failure_reason_redacted` design already isolate the sensitive fields so the
deferred narrowing is additive and does not weaken today's boundary.

---

## Modified / new files (platform-only)

Backend (read-only adapter):
- `backend/api/v1/platform/p17/__init__.py` -- module docstring.
- `backend/api/v1/platform/p17/schemas.py` -- the six registry contracts,
  enums, `source_status` consistency validators, `extra="forbid"`, allowlisted
  `failure_reason_redacted`, freshness helper (`enforce_backup_freshness`),
  redaction helper (`redact_failure_reason`).
- `backend/api/v1/platform/p17/services.py` -- read-only registry adapter
  (P10 identity + `PlatformTenant` provisioning journal); graceful
  null/unknown + reason on unavailable sources.
- `backend/api/v1/platform/p17/routes.py` -- GET-only `/registry` (list) and
  `/registry/{tenant_id}`; identity-only super_admin guard with access-denied
  and best-effort view audit (`registry_view` / `registry_view_denied`).
- `backend/api/app.py` -- registers the P17 router (additive; +5 lines, 0
  deletions, mirrors the P15 block).
- `backend/tests/test_platform_p17_registry.py` -- 40 contract/route/redaction
  tests.

Frontend (read-only cockpit):
- `frontend/src/types/platformRegistry.ts` -- TS mirrors + display helpers.
- `frontend/src/services/platformApi.ts` -- `listTenantRegistry` /
  `getTenantRegistry` (additive; +17 lines, 0 deletions).
- `frontend/src/pages/platform/PlatformRegistryPage.tsx` -- read-only registry
  page (unknown gray, null N/A, no mutation controls).
- `frontend/src/router/AppRouter.tsx` -- `/platform/registry` under
  `PlatformRoute` (additive; +3 lines, 0 deletions).
- `frontend/src/types/__tests__/platformRegistry.test.ts` -- helper/shape tests.
- `frontend/src/services/__tests__/platformRegistryApi.test.ts` -- API client
  shape tests.
- `frontend/src/pages/platform/__tests__/PlatformRegistryPage.test.tsx` -- page
  component tests.

Ledger:
- `ai-ledger/platform/2026-06-22_p17bc_registry_adapter_cockpit.md` -- this file.

**Forbidden paths untouched:** no `backend/alembic/`, no `migrations/`, no
`product-dev-recovered/`, no auth/RBAC/session/tenancy, no payment/billing, no
tenant business tables, no `.github/`/`.claude/`.

---

## Test evidence (actual, run on the isolated branch)

Backend:
- `tests/test_platform_p17_registry.py` -- **40 passed** (schema/contract,
  response shape, source_status semantics, permissions, GET-only, redaction,
  freshness, provisioning sourcing, graceful degradation, counterexamples).
- Platform regression (shared guards/services) -- **418 passed** across
  `test_platform_p10_contracts`, `test_platform_p11c0_legacy_guard`,
  `test_platform_p12_support_console`, `test_platform_p13_operations_cockpit`,
  `test_platform_p15_incident_triage`, `test_platform_p17_registry`,
  `test_platform_audit`, `test_platform_audit_api`.
- Whole-app build: `configure_app(app, settings)` registers both P17 GET routes
  (`/api/v1/platform/p17/registry`, `/api/v1/platform/p17/registry/{tenant_id}`).

Frontend (P17):
- `src/types/__tests__/platformRegistry.test.ts` -- 14 passed.
- `src/services/__tests__/platformRegistryApi.test.ts` -- 4 passed.
- `src/pages/platform/__tests__/PlatformRegistryPage.test.tsx` -- 10 passed.
- **P17 total: 28 passed**, RC 0. The page tests pass but emit React `act(...)` warnings on stderr (async state updates in `PlatformRegistryPage`); these are non-blocking and deferred to a future polish pass.
- Platform frontend regression (broader, not re-run this slice) -- **117 passed** across 15 platform type / service / page test files; router guards -- 10 passed.

---

## Validation gates

| Gate | Result |
|---|---|
| `git fetch origin --prune` | OK; origin/platform-dev HEAD unchanged at `40f5efb`. |
| P17-A (`40f5efb`) ancestor of origin/platform-dev | Confirmed. |
| `git merge-base --is-ancestor origin/platform-dev HEAD` | YES (branch is ahead of base). |
| `git diff --check origin/platform-dev..HEAD` | Clean (no whitespace/conflict markers). |
| Backend P17 tests | 40 passed. |
| P10/P11/P12/P13/P15 platform regression | 418 passed (no regressions). |
| Frontend P17 tests | 28 passed (14 type + 4 api + 10 page); RC 0; React act() warnings on stderr, non-blocking. |
| Forbidden-path audit | PASS -- all change-set paths are platform-only; no mutation decorators; no business-table queries; no secret/DSN literals (warnings were docstrings / standard `X-Platform-Operator` header / data field names). |
| Non-ASCII scan (changed/new files) | PASS -- 0 non-ASCII in the 4 new P17 source files and the app.py P17-added lines (3 pre-existing em-dashes in app.py comments are unrelated and out of scope). |
| detect-secrets (changed files) | PASS -- 0 findings. Repo pre-commit `Detect secrets` hook also Passed on commit `79f306c`. |
| `npx gitnexus analyze` | RC 0; index up to date (refreshes again via the commit hook). |
| GitNexus `detect_changes` (compare vs origin/platform-dev) | CRITICAL: 14 files, 89 symbols, 19 affected flows. Accepted by CTO review (additive read-only platform surface; see Risk). |

---

## Counterexamples addressed (P17-A section 11)

- **C1** tenant-contextual admin denied -> `TestPermissions::test_tenant_contextual_super_admin_denied` (401/403 on both endpoints).
- **C2 / C6** raw failure detail / provisioning secret -> allowlisted `failure_reason_redacted` validator + `redact_failure_reason`; `TestRedaction::test_failure_reason_redacted_never_contains_raw_secret`.
- **C3** unknown reported as healthy -> `state_source_status` consistency validator + `TestSourceStatusSemantics::test_unknown_status_tenant_not_active`.
- **C4** stale success -> `enforce_backup_freshness` + schema backstop; `TestFreshness`.
- **C5 / C13** transition without actor/reason/audit -> N/A: P17 performs no transitions (read-only); audit emits `registry_view` / `registry_view_denied` only.
- **C7 / C11** mutation endpoint/control -> GET-only router; `TestGetOnly` (POST/PUT/PATCH/DELETE -> 405; router methods == {GET}); page has zero buttons.
- **C8** migration/backend in P17-A -> N/A: this is P17-B/C (implementation phase), not P17-A.
- **C9 / C14** credential/DSN/business leak -> `TestRedaction::test_registry_no_sensitive_keys`, `test_no_tenant_business_tokens_in_response`.
- **C10** 0 instead of null -> null provisioning/backup with reason; `TestSourceStatusSemantics::test_provisioning_and_backup_null_with_reason`.
- **C12** engineering mutating -> N/A: P17 is read-only; no write capability for any role.

---

## Sources reused (contract section 7)

- Tenant identity / schema / status / created_at / support_mode_active: P10
  `list_tenant_summaries` / `get_tenant_summary` (public platform metadata).
- Coarse provisioning lifecycle + schema-created signal: `PlatformTenant`
  provisioning journal (`public.platform_tenants`).
- Runtime telemetry, fine provisioning diagnostics, backup system: **not yet
  instrumented** -> read `null` / `unknown` / `false` + reason (never fabricated).

Forbidden sources untouched: tenant business tables (orders, payments, invoices,
customers), raw request/response bodies, credentials, DSNs, host/port,
connection strings, migration history, raw audit-log payloads.

---

## Risk

GitNexus `detect_changes` (compare vs `origin/platform-dev`) reports the change
as **CRITICAL** by symbol/flow count: **14 files, 89 symbols, 19 affected
execution flows.** The CTO review re-ran this on the branch tip and accepted
it because the blast radius is wide-but-shallow and explainable:

- **Platform-runtime additive.** Every changed symbol is under the platform
  operations surface -- `backend/api/v1/platform/p17/` (backend) and
  `frontend/src/{pages,services,types,router}/.../platform/...` (frontend).
  The 89 symbols come from six new contract models plus a new read-only
  router plus a new page; none of it is product business logic.
- **Read-only by construction.** The only new routes are GET. There are no
  mutation endpoints, no lifecycle / flag / provisioning / backup writes, and
  the cockpit page has zero mutation controls. The 19 affected flows are read
  paths (registry view / view-denied).
- **No product business.** No orders / payments / invoices / customers tables
  are queried or exposed (forbidden-path audit PASS).
- **No migrations.** `backend/alembic/` and `migrations/` are untouched;
  there is no schema change, so the database blast radius is zero.
- **Mitigated by tests.** Backend P17 = 40 passed; frontend P17 = 28 passed;
  P10/P11/P12/P13/P15 platform regression green (no regressions).

Net: the change is **additive read-only platform surface (no product data,
no migrations)**, and every read path it adds is covered by tests.

---

## GitNexus

`npx gitnexus analyze .` indexed the branch (7,040 nodes / 21,372 edges /
469 clusters / 300 flows); indexed commit `79f306c`, status up-to-date.

`npx gitnexus impact <symbol> -r platform-p17bc-registry-adapter-cockpit-2026-06-22`
(per-symbol upstream blast radius on the changed route handlers -- this is the
per-symbol view and is distinct from the branch-level `detect_changes` below):

- `list_tenant_registries` (new P17 service/route): **impactedCount 0,
  processes 0, modules 0** -- the new read-only registry surface has no upstream
  dependants, so changing it breaks nothing at the symbol level.
- `get_tenant_registry` (new P17 route): **impactedCount 0** -- same.
- `require_platform_operator` (the reused P10 identity-only guard -- **not
  modified**, only consumed): risk HIGH *if modified*, 4 direct dependants.
  All four are platform-only:
  `p15/require_platform_operator_with_triage_audit`,
  `p17/require_platform_operator_with_registry_audit` (this phase -- new
  consumer only),
  `p12/require_platform_operator_with_audit`,
  `p13/require_platform_operator_with_ops_audit`.
  This HIGH is the hypothetical "if the guard changed" blast radius; this phase
  does **not** change the guard, so the existing p10/p12/p13/p15 consumers are
  unaffected (confirmed by the 418-passing platform regression). Per the stop
  conditions, a HIGH that is explainable as platform-only and reviewed is not a
  blocker.

`detect_changes` (compare vs `origin/platform-dev`) was run in the CTO review
session (it is an MCP-only operation): **CRITICAL** -- **14 files, 89 symbols,
19 affected execution flows.** The 14-file count is corroborated structurally
by `git diff --name-status origin/platform-dev..HEAD` (the file inventory in
the `Modified / new files` section: 13 source files plus this ledger).

This CRITICAL is the expected, explainable shape for an additive read-only
adapter, not a regression. It is wide because the registry composes six new
contract models and registers a new read-only router plus a page (89
symbols), but shallow because every affected flow is a read path and the
change is platform runtime-only -- no product business, no
auth/RBAC/session change, no migrations, no mutation endpoints. See the
`Risk` section above for the full rationale. The single HIGH in the
per-symbol impact run is on the reused `require_platform_operator` guard,
which this phase consumes but does **not** modify (confirmed green by the
platform regression), so it is non-blocking.
