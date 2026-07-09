# P25-EG Tenant List Legacy UUID Robustness

| Field | Value |
|---|---|
| **Task ID** | P25-EG (Tenant List Legacy UUID Robustness) |
| **Date** | 2026-07-09 |
| **Mode** | **CODE** -- platform read DTO validator relaxation for legacy UUIDs |
| **Branch** | `codex/product-merge-prep-g2-resolved-merge-rehearsal-2026-07-08` |
| **Worktree** | `_mergeresolve_g2_2026-07-08` |
| **Base (HEAD at start)** | `040e6e0a` (G3-R2 tenant-context deny fail-closed) |
| **Predecessor** | G3-R2 fixed the tenant-context 500; P25-EG fixes the tenant-list legacy-UUID 500 |
| **Result** | **FIXED** -- legacy/non-v4-v7 UUIDs no longer cause HTTP 500 on tenant list/health |

---

## 1. Base Proof Gate

| Check | Result |
|---|---|
| `git fetch origin` | Executed 2026-07-09 |
| `origin/platform-dev` | `12c5ee55` -- **UNCHANGED** |
| `origin/product-dev-recovered` | `19f6afde` -- **UNCHANGED** |
| G3-R2 commit (parent) | `040e6e0a` -- confirmed as branch tip |
| Working tree at edit start | Clean (only G3-R2 committed) |

---

## 2. Problem Statement

GET `/api/v1/platform/p10/tenants` returns **HTTP 500** when a legacy/non-v4-v7
UUID exists in `public.wholesalers.id`.

**Evidence:**
- Route: `GET /api/v1/platform/p10/tenants`
- Traceback path: `routes.py:48` -> `services.py:214` -> `TenantSummary(tenant_id=str(w.id))`
- Offending DB row: `public.wholesalers.id = 11111111-1111-1111-1111-111111111111`
- Row name: `S5D4B R1 Test Wholesaler`
- `platform_tenants` table is empty; `list_tenants` reads `wholesalers`
- `TenantSummary` validator rejects non-v4/v7 UUID -> Pydantic `ValidationError` -> 500

---

## 3. Root Cause

```
list_tenants route (routes.py:48)
  -> services.list_tenant_summaries (services.py:170-229)
    -> TenantSummary(tenant_id=str(w.id)) for each wholesaler row
      -> TenantSummary._validate_tenant_id = field_validator(validate_uuid_v4_v7)
        -> UUID_V4_V7_PATTERN rejects version digit "1" (11111111-...)
          -> ValueError("UUID must be version 4 or 7")
            -> Pydantic ValidationError
              -> HTTP 500
```

The strict `validate_uuid_v4_v7` validator (schemas.py:54-62) requires the UUID
version digit to be 4-7. The legacy UUID `11111111-1111-1111-1111-111111111111`
is version 1 -> fails pattern -> ValueError -> ValidationError -> 500.

The same latent bug exists in `TenantHealth` (same validator, same data source).

---

## 4. Fix

**File**: `backend/api/v1/platform/p10/schemas.py`

### 4.1 New lenient validator -- `validate_uuid_any_version`

Accepts any valid UUID-format string (any version: v1/v4/v7/etc). Non-None
values that are not valid UUID format are still rejected so slugs/garbage do
not leak through. Callers translate those into clean 404s via
`_coerce_tenant_id`.

### 4.2 Applied to read DTOs only

| Model | Field | Before | After |
|---|---|---|---|
| `TenantSummary` | `tenant_id` | `validate_uuid_v4_v7` | `validate_uuid_any_version` |
| `TenantHealth` | `tenant_id` | `validate_uuid_v4_v7` | `validate_uuid_any_version` |
| `PlatformAuditEvent` | `event_id` | `validate_uuid_v4_v7` | **UNCHANGED** (strict) |
| `PlatformAuditEvent` | `tenant_id` | `validate_uuid_v4_v7` | **UNCHANGED** (strict) |

The strict `validate_uuid_v4_v7` remains in force for `PlatformAuditEvent`
where identifiers are platform-generated and v4/v7 enforcement is correct.
Product business UUID validation is not touched.

---

## 5. Preserved Behaviors

| Behavior | Preserved? |
|---|---|
| list_tenants returns HTTP 200 with legacy UUID rows | YES (now fixed) |
| Valid v4/v7 UUIDs still accepted | YES |
| Invalid slug -> clean 404 (via `_coerce_tenant_id` -> None) | YES |
| PlatformAuditEvent event_id still enforces v4/v7 | YES (strict validator unchanged) |
| G3-R2 tenant-context deny fail-closed | YES (untouched, regression verified) |
| Product U6 onboarding/auth chain | YES (no product files modified) |

---

## 6. Tests

**File**: `backend/tests/test_platform_p10_contracts.py` -- appended
`TestP25EGTenantListLegacyUUID` class (13 tests).

| Test | Covers |
|---|---|
| `test_lenient_accepts_legacy_v1` | `validate_uuid_any_version("11111111-...")` -> accepted |
| `test_lenient_accepts_valid_v4` | v4 UUID accepted |
| `test_lenient_accepts_none` | None passthrough |
| `test_lenient_rejects_garbage` | "not-a-uuid" -> ValueError |
| `test_lenient_rejects_slug` | "smoke-tenant-1" -> ValueError |
| `test_tenant_summary_accepts_legacy_uuid` | TenantSummary constructs with legacy v1 UUID |
| `test_tenant_summary_accepts_valid_v4` | TenantSummary constructs with v4 UUID |
| `test_tenant_summary_accepts_none_tenant_id` | TenantSummary with None tenant_id |
| `test_tenant_health_accepts_legacy_uuid` | TenantHealth constructs with legacy v1 UUID |
| `test_audit_event_id_still_strict_v4_v7` | PlatformAuditEvent rejects legacy UUID event_id (strict unchanged) |
| `test_list_tenant_summaries_legacy_uuid_no_500` | list_tenant_summaries returns without raising on legacy UUID row |
| `test_coerce_tenant_id_slug_returns_none` | Slug -> None -> 404 path preserved |
| `test_coerce_tenant_id_legacy_uuid_parsed` | Legacy UUID parseable by uuid.UUID (for DB lookup) |

### Test results

| Suite | Result |
|---|---|
| `TestP25EGTenantListLegacyUUID` (targeted, 13 tests) | **13/13 PASS** |
| `test_platform_p10_contracts.py` (full file, includes G3-R2 regression) | **173 passed** |

---

## 7. Validation Gates

| Gate | Result |
|---|---|
| `git diff --check` | PASS (no whitespace/conflict errors) |
| Added-line ASCII scan | ADDED LINES ALL ASCII CLEAN (119 pre-existing non-ASCII bytes from `--` section headers unchanged) |
| `detect-secrets scan --baseline .secrets.baseline` | EXIT 0 (clean, no new secrets) |
| `.secrets.baseline` | **UNCHANGED** (restored after scan) |
| Targeted P25-EG tests | 13/13 PASS |
| Full P10 contracts (incl. G3-R2 regression) | 173 passed, 0 failed |
| `npx gitnexus analyze` | Repository indexed successfully (12,157 nodes, 36,702 edges, 780 clusters, 300 flows) |
| Worktree clean | Only 2 intended source files modified |

---

## 8. Scope Diff

```
M  backend/api/v1/platform/p10/schemas.py              (+27 -2)
M  backend/tests/test_platform_p10_contracts.py        (+163)
A  ai-ledger/platform/2026-07-09_p25eg_tenant_list_legacy_uuid_robustness.md  (new)
```

2 source files modified (platform read DTO validator + targeted tests), 1 ledger
added. **0 migrations, 0 lockfile, 0 frontend runtime, 0 product business logic,
0 protected branch push, 0 changes to tenant-context deny path.**

---

## 9. Stop Condition Check

| Stop Condition | Triggered? |
|---|---|
| Out-of-scope file modified | NO |
| tenant.py / G3-R2 path modified | NO (explicitly forbidden, untouched) |
| Product business UUID validation relaxed | NO (only platform read DTO) |
| Migration drift | NO |
| Lockfile/package touched | NO |
| Protected branch push | NO |

**No stop conditions triggered.**

---

## 10. Risk Assessment

| Risk | Level | Mitigation |
|---|---|---|
| Legacy UUID now surfaces in API response | LOW | This is a read-only platform DTO for operators; the UUID was already in the DB, just not reachable |
| Strict v4/v7 enforcement weakened | NONE | Only TenantSummary/TenantHealth relaxed; PlatformAuditEvent remains strict |
| Slug/garbage leaks through | NONE | `validate_uuid_any_version` still rejects non-UUID-format strings; `_coerce_tenant_id` translates slugs to 404 |
| G3-R2 regression | NONE | Full P10 suite 173 passed including all 9 G3-R2 tests |
| Product auth regression | NONE | No product files touched |

---

## 11. Protected Branches

| Ref | SHA | Status |
|---|---|---|
| `origin/platform-dev` | `12c5ee55` | **UNCHANGED** |
| `origin/product-dev-recovered` | `19f6afde` | **UNCHANGED** |

Feature branch pushed only. No protected branch touched.

---

## 12. Blockers

**None.** The fix is complete, tested, and validated. Ready for G4 promotion
inclusion.
