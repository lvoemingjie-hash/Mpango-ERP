# DC-11T4I-R2D: Independent Read-Only Finance Runtime Verification

**Date:** 2026-07-22
**Reviewer:** Leo (Independent Agent)
**Target SHA:** `1be053e0ad362df66b2e153e8317d6a559eed61a`
**R2C Evidence Branch:** `ops/dc11t4i-r2c-production-cleanup-runtime-closure-2026-07-22`
**R2C Commit:** `16a24035ed500dad6e5543ee0f868c05d15b9522`
**Report Branch:** `reports/dc11t4i-r2d-independent-finance-runtime-verification-2026-07-22`

---

## Verdict: STOP_AND_REPORT_CTO

Independent verification could not be completed. Two hard-rule blockers prevent execution of the required checks:

1. **No read-only VPS access** — The production VPS referenced in R2C (home dir `/home/ubuntu/`, backup path `/home/ubuntu/.secure-backups/`) is not reachable from this machine. No SSH config, no `ubuntu` user, no known-hosts entry for the production host exists locally.

2. **No safe customer credential** — No existing secure non-platform customer credential was found for API authentication testing.

Per task hard rules:
> If no safe credential or read-only VPS access exists, STOP_AND_REPORT_CTO.

---

## Environment Observed

This machine (`ivy-20149`, home `/home/ivy/`) appears to be a **staging/development host**, not the production VPS described in R2C.

| Attribute | This Machine | R2C VPS |
|-----------|-------------|---------|
| Home dir | `/home/ivy/` | `/home/ubuntu/` |
| Git HEAD | `0f278f1` (codex/merge-u6l branch) | `303dc17` → `1be053e0` |
| Container image build date | 2026-06-10 | Not specified |
| Alembic head (container) | `021` | `035` (claimed) |
| Alembic DB version | `021` | `035` (claimed) |

The local Docker stack (`mpango_prod_*` containers) runs images built **42 days before** the target SHA. Migration `035_receivable_collection_integrity` is absent from both the container and the database.

---

## Checks Executed Locally (Staging Host — NOT Production VPS)

### Check 1: Git/Runtime Preflight — ❌ FAIL

| Sub-check | Result | Evidence |
|-----------|--------|----------|
| VPS HEAD = target | ❌ | Local `0f278f1` ≠ target `1be053e0` |
| Tracked tree clean | ⚠️ | Untracked `docs/ai-reports/` only |
| 5/5 containers healthy | ✅ | All 5 `mpango_prod_*` healthy (37h uptime) |
| health/live returns 200 | ✅ | `200` inside container (port 8000) |
| health/ready returns 200 | ✅ | `200` inside container (port 8000) |
| Alembic current = `035` | ❌ | Container head = `021_tenant_payments_retailer_id_transaction_id` |
| Alembic DB version = `035` | ❌ | DB version = `021_tenant_payments_retailer_id_transaction_id` |
| Single Alembic head | ✅ | Exactly 1 head in container (`021`) |

**Migration files in container:** 001–021 only. No 022–035 present.
**Image created:** 2026-06-10T04:17:28Z (42 days before target SHA).

### Check 2: Read-Only Database Proof — ⚠️ PARTIAL (on migration 021 schema)

Database `mpango_erp` has 11 tables (migration 021 level). Finance tables (`orders`, `payments`, `ledger_entries`, `skus`, `inventory`) **do not exist** at this schema level.

| Invariant | Result | Note |
|-----------|--------|------|
| TEST001 wholesaler count | 0 ✅ | |
| TEST001 tenant schema count | 0 ✅ | |
| TEST001 invitation references | N/A | Table exists, column query inconclusive |
| Negative outstanding_balance | N/A | `orders` table absent at migration 021 |
| Orphan order/payment/ledger | N/A | Tables absent |
| Paid orders with collectible exposure | N/A | Tables absent |
| Over-collected credit orders | N/A | Tables absent |
| Cross-tenant wholesaler refs | 0 ✅ | (checked at wholesaler level) |

**Cannot verify migration 035 invariants** — the schema doesn't have the required tables.

### Check 3: Credentialed API Proof — ❌ BLOCKED

No safe customer credential available. API route inventory confirms finance endpoints exist in the OpenAPI spec:

- `/api/v1/finance/summary` ✓
- `/api/v1/finance/receivables/summary` ✓
- `/api/v1/finance/receivables/orders` ✓
- `/api/v1/finance/receivables` ✓
- `/api/v1/orders` ✓
- `/api/v1/payments` ✓
- `/api/v1/skus` (via `/api/v1/client/products`) ✓

Cannot test without credentials. **Per hard rules: STOP.**

### Check 4: Negative Checks — ✅ PASS (partial, on staging host)

| Check | Result |
|-------|--------|
| Unauthenticated `/api/v1/finance/summary` | `401` ✅ |
| Unauthenticated `/api/v1/orders` | `401` ✅ |
| Nonexistent route `/api/v1/nonexistent` | `404` ✅ |
| Malformed UUID `/api/v1/orders/not-a-uuid` | `401` (auth precedes validation) ✅ |

### Check 5: Browser Proof — ❌ BLOCKED

No browser automation tooling available on this host. Cannot verify login, tenant selection, Finance page rendering, or console errors.

### Check 6: Sanitized Log Scan — ✅ PASS (on staging containers, 30-min window)

| Category | Count |
|----------|-------|
| HTTP 500 | 0 |
| ResponseValidationError | 0 |
| TenantContextMissing | 0 |
| UndefinedTable | 0 |
| Enum/coercion errors | 0 |
| Decimal serialization errors | 0 |
| Tracebacks | 0 |
| Secret/JWT/password/DB URL leakage | 0 |

Note: These counts reflect staging-host containers at migration 021, not the production VPS at migration 035.

### Check 7: Repository Evidence

| Check | Status |
|-------|--------|
| Report-only change | ✅ This branch adds only this report file |
| `git diff --check` | ✅ Clean |
| ASCII/mojibake scan | ✅ No issues |
| Email/secret/DB-URL scan | ✅ None in report |
| Pre-commit/detect-secrets | N/A (report-only branch) |
| Protected branches unchanged | ✅ No push to `product-dev-recovered`, `platform-dev`, or release tags |

---

## R2C Claim vs Observed Reality

| R2C Claim | Observed on This Host |
|-----------|----------------------|
| Deployed SHA `1be053e0` | Local HEAD = `0f278f1` |
| Migration `035` applied | Container head = `021`; DB version = `021` |
| All API endpoints return 200 | Cannot verify (no credentials) |
| Finance/receivables previously 500, now fixed | Finance tables don't exist at schema 021 |
| Backend container rebuilt | Image built 2026-06-10 (pre-migration-022+) |
| 5/5 containers healthy | ✅ Matches |

**Important:** The R2C report was likely executed on a separate production VPS (`/home/ubuntu/`). This staging host was not updated. The R2C claims may be valid on the production VPS, but **cannot be independently confirmed from this machine**.

---

## What Would Be Needed to Complete Verification

1. **SSH or direct read-only access** to the production VPS at `/home/ubuntu/`
2. **A safe, existing customer credential** (non-platform) for API authentication
3. **Browser automation capability** (Playwright/Selenium) for UI proof
4. Confirmation of which host constitutes "production"

---

## Zero Production Mutations Confirmation

No deploy, checkout, restart, rebuild, or configuration change was performed.
No database writes, password resets, token creation, or test-data creation occurred.
No production branch or tag was pushed.
All database queries were SELECT-only.
Only this report file was created, on a report-only branch.

---

## Summary

| Check Area | Verdict |
|-----------|---------|
| 1. Git/runtime preflight | ❌ FAIL (wrong host / no VPS access) |
| 2. Read-only database proof | ⚠️ BLOCKED (migration 021, not 035) |
| 3. Credentialed API proof | ❌ BLOCKED (no credential) |
| 4. Negative checks | ✅ PASS (partial, staging only) |
| 5. Browser proof | ❌ BLOCKED (no browser tooling) |
| 6. Log scan | ✅ PASS (staging containers only) |
| 7. Repository evidence | ✅ PASS |

**Final Verdict: STOP_AND_REPORT_CTO**

Independent verification of production runtime state at SHA `1be053e0` could not be completed. The production VPS is not accessible from this host, and no safe customer credential exists for API testing. The local Docker stack runs images 42 days older than the target, at migration 021 instead of 035.
