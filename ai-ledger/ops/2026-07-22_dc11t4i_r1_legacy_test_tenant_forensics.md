# DC-11T4I-R1: Legacy TEST001 Orphaned Financial Data Forensics

**Date:** 2026-07-22
**Classification:** CONFIRMED_LEGACY_TEST_FIXTURE_CONTAMINATION
**Verdict:** PASS_FORENSICS_CONFIRMED_LEGACY_TEST_FIXTURE
**Wholesaler:** `550e8400-e29b-41d4-a716-446655440000`
**VPS State:** 303dc179e94527668f4f1d2145fab74be0f48751, 5/5 containers healthy

---

## Evidence Summary

### E1: Wholesaler Core Attributes

| Field | Value |
|-------|-------|
| code | `TEST001` |
| name | Mpango Test Tenant |
| status | active |
| is_deleted | false |
| created_at | 2026-06-11 04:43:59.029014+00 |

**Analysis:** Code `TEST001` and name `Mpango Test Tenant` explicitly identify this as a test fixture. Created 2026-06-11, predating all runtime task evidence (earliest order 2026-06-29).

### E2: tenant_registrations

| Metric | Value |
|--------|-------|
| total rows | **0** |
| active | 0 |
| pending | 0 |
| deactivated | 0 |
| is_deleted=true | 0 |
| distinct schemas | 0 |

**Analysis:** Zero tenant registration records. No real onboarding flow was ever initiated for this wholesaler. The derived schema `t_550e8400e29b41d4a716446655440000` exists but has no corresponding registration — it was created directly (likely via database provisioning in early testing).

### E3: Derived Schema Existence

| Schema | Status |
|--------|--------|
| `t_550e8400e29b41d4a716446655440000` | **EXISTS** |
| Total tenant schemas | 11 (including `t_dev`) |

**Analysis:** The derived schema exists and is populated with test data. It was created without a corresponding `tenant_registrations` row — a hallmark of manual test fixture setup.

### E4: t_dev References

| Table | Rows | Refs to Target |
|-------|------|----------------|
| t_dev.users | 1 | N/A |
| t_dev.orders | 0 | N/A |
| t_dev.payments | 0 | N/A |
| t_dev.ledger_entries | N/A | table does not exist |
| t_dev.receivable_bindings | N/A | table does not exist |
| t_dev.receivable_collections | N/A | table does not exist |

**Analysis:** `t_dev` is a minimal development schema with 1 user and no financial data. It does not reference the target wholesaler.

### E5: Binding/Financial Table Status (Derived Schema)

| Table | Status |
|-------|--------|
| receivable_bindings | **DOES NOT EXIST** |
| accounting_ledger | **DOES NOT EXIST** |
| receivable_collections | **DOES NOT EXIST** |
| ledger_entries | EXISTS (22 rows) |

**Analysis:** Migration `035_receivable_collection_integrity` has NOT been applied. The newer receivable tables (`receivable_bindings`, `accounting_ledger`, `receivable_collections`) do not exist. The older `ledger_entries` table contains 22 entries. This is why migration 035 failed in DC-11T4I: the preflight's authoritative registry is `public.tenant_registrations` joined with `public.wholesalers` (function `_registered_tenants`), and the fail-closed path `_validate_nonzero_bindings_are_reconstructable` found that TEST001 carried a nonzero `wholesaler_retailer_bindings.outstanding_balance` but had zero qualifying live `tenant_registrations` rows. `platform_tenants` is not consulted by migration 035; its being empty is contextual evidence only.

### E6: Aggregate Counts (Derived Schema)

| Object | Count |
|--------|-------|
| Users | 1 (active) |
| SKUs | 21 |
| Orders | 17 |
| Payments | 23 |
| Ledger entries | 22 |
| Order items | 17 |

### E7-8: Financial Exposure Analysis

**Orders by Status:**

| Status | Count | Total Amount |
|--------|-------|--------------|
| draft | 2 | 300.00 |
| partially_paid | 4 | 900.00 |
| paid | 11 | 2,250.00 |
| **Total** | **17** | **3,450.00** |

**Payments by Method:**

| Method | Count | Completed | Total Amount |
|--------|-------|-----------|--------------|
| cash | 15 | 13 | 1,875.00 |
| transfer | 8 | 3 | 450.00 |
| **Total** | **23** | **16** | **2,325.00** |

**Ledger Balance:**

| Account Type | Entries | Total Amount |
|--------------|---------|--------------|
| receivable | 11 | -2,250.00 |
| cash | 11 | 2,250.00 |
| **Balance** | **22** | **0.00** |

> **Correction applied in DC-11T4I-R1B (2026-07-22):** The financial interpretation
> originally published here treated the negative receivable aggregate as a valid
> settled balance. That interpretation is **stale and retracted**. See the
> corrected analysis below. TEST001 classification is unchanged:
> `CONFIRMED_LEGACY_TEST_FIXTURE_CONTAMINATION`.

**rpt_receivables_summary (LEGACY / CONTAMINATED — not canonical):**

| Entity Type | Orders | Reported Outstanding |
|-------------|--------|----------------------|
| order | 11 | -2,250.00 |

> This value is produced by the legacy `rpt_receivables_summary` path and is
> **contaminated/stale evidence**. It must NOT be treated as canonical
> post-DC-11T4H receivables semantics.

**Corrected Financial Semantics (canonical post-DC-11T4H):**

- Negative receivable ledger postings are **accounting movements**
  (debit/credit entries on the `receivable` account), **not** a valid negative
  customer outstanding balance. A ledger movement of `-2,250.00` on
  `receivable` is the mechanical offset booked when a payment clears; it is not
  itself a balance.
- Paid orders should contribute **zero remaining receivable exposure** after the
  corresponding collections. A settled order's remaining exposure is
  `max(credit_total - collection_total, 0) = 0`, never negative.
- The authoritative post-DC-11T4H write path (migration 035 function
  `_reconstruct_binding_balances`) computes `wholesaler_retailer_bindings`
  outstanding as `GREATEST(credit_total - collection_total, 0)`, which is always
  non-negative. Accordingly, a binding carrying a stored `outstanding_balance`
  of `-2,325.00` is a **stale/contaminated stored value**, not real negative debt.
  The live probe confirms `count(bindings WHERE outstanding_balance > 0) = 0`
  for TEST001 — i.e., zero real remaining exposure.
- The legacy `rpt_receivables_summary` aggregate of `-2,250.00` is therefore
  contaminated/stale evidence and must not be treated as canonical post-DC-11T4H
  semantics. It reflects a pre-fix calculation path, not the corrected one.
- **DC-11T4H at `1be053e0` fixes the calculation/write path**, but **production
  runtime closure remains pending** — the fix is merged but the live TEST001
  fixture has not yet been cleared and recomputed, so stale values still persist
  in this fixture.

**Exposure Reconciliation (corrected):**
- Total order credit (17 orders): 3,450.00
- Completed collections (cash + transfer): 2,325.00
- Remaining exposure under canonical semantics (sum of per-order
  `max(credit - collection, 0)`): non-negative by construction.
- The legacy report's negative figure is an artifact of summing signed
  `receivable` ledger movements without the `max(..., 0)` guard; it is not a
  customer balance and must not be carried forward.

### E9: Synthetic UUID Family

| Check | Result |
|-------|--------|
| Orders created by user `2b560429` (DC-11T4G test user) | **All 17** |
| Payments created by user `2b560429` | **All 23** |
| Synthetic retailer `51488f90` in orders | 0 |

**Analysis:** Every order and payment in the derived schema was created by user `2b560429-2fbe-4350-b7b5-4d1f80345b36` — the test user used in DC-11T4G runtime testing. This confirms all financial data is synthetic test artifact.

### E10: Public-Table References

| Table | Count |
|-------|-------|
| wholesalers | 1 |
| platform_tenants | **0** |
| tenant_registrations | **0** |
| invitations | 3 |
| wholesaler_retailer_bindings | 2 |
| platform_audit_logs | **0** |

**Analysis:** The only public-table references are:
- The wholesalers row itself (expected)
- 3 invitations (test artifacts from DC-11T4G runtime testing)
- 2 wholesaler-retailer_bindings (test data)

Zero tenant_registrations (migration 035's authority, joined with `public.wholesalers`), zero platform_audit_logs — no live onboarding or production activity. `platform_tenants` is also empty, which corroborates the absence of a live onboarding lifecycle, but migration 035 does not consult it; its emptiness is contextual evidence only.

### E11: Real Onboarding/Mailbox Lifecycle

| Check | Result |
|-------|--------|
| tenant_registrations rows | **0** |
| onboarding_status_tokens | 17 (global, not specific to this wholesaler) |
| email_verification_tokens | 17 (global, not specific to this wholesaler) |
| owner_credential_setup_tokens | 8 (global, not specific to this wholesaler) |

**Analysis:** No onboarding registration, email verification, or credential setup was ever initiated for this wholesaler. The global token counts (17, 17, 8) belong to other wholesalers in the system. There is no evidence of a real customer onboarding lifecycle for `TEST001`.

### E12: DC-11T4I Backup

| Check | Result |
|-------|--------|
| File exists | Yes |
| Size | 874,700 bytes |
| Readable | Yes (valid PostgreSQL dump header) |
| SHA256 prefix | b4380a8a8cdb5cfaad6d38b8e4992dafd59e3314ff8f8f911ba6edee5467ba02 |

**Analysis:** Backup created during DC-11T4I is intact and readable. It captures the database state at 2026-07-22T06:24:13Z, including all test fixture data.

---

## Classification: CONFIRMED_LEGACY_TEST_FIXTURE_CONTAMINATION

### Evidence Matrix

| Indicator | Value | Classification Signal |
|-----------|-------|----------------------|
| Wholesaler code | `TEST001` | Test fixture |
| Wholesaler name | `Mpango Test Tenant` | Test fixture |
| tenant_registrations | 0 | No real onboarding |
| platform_tenants | 0 | Contextual evidence only (not consulted by migration 035) |
| All orders created_by | `2b560429` (test user) | Synthetic data |
| All payments created_by | `2b560429` (test user) | Synthetic data |
| Invitations | 3 (test runtime) | Test artifacts |
| Wholesaler-retailer bindings | 2 (test data) | Test artifacts |
| platform_audit_logs | 0 | No production activity |
| Email verification | 0 for this wholesaler | No mailbox lifecycle |

### Why This Is Not MIXED_TEST_AND_CUSTOMER_DATA

- Zero real customer indicators (no tenant registrations, no platform_tenants, no audit logs)
- All financial data created by a single test user
- No evidence of any real onboarding, email verification, or credential setup
- The wholesaler is explicitly named "Mpango Test Tenant" with code "TEST001"

### Why This Is Not LEGACY_REAL_TENANT_MISSING_AUTHORITATIVE_REGISTRATION

- This is not a real tenant — it is a test fixture
- The name, code, and data provenance all confirm synthetic origin
- No real customer onboarding lifecycle exists

### Why This Is Not UNKNOWN_DATA_LINEAGE_STOP

- Data lineage is fully traceable: all 17 orders and 23 payments created by test user `2b560429` during DC-11T4G runtime testing
- Wholesaler created 2026-06-11, earliest order 2026-06-29
- All evidence points to synthetic test fixture

---

## Impact on Migration 035

The `CONFIRMED_LEGACY_TEST_FIXTURE_CONTAMINATION` classification explains why migration 035 failed:

1. Migration 035 (`035_receivable_collection_integrity`) performs a preflight check.
2. Its authoritative registry is `public.tenant_registrations` joined with `public.wholesalers` (function `_registered_tenants`, filtered to `is_deleted IS FALSE` and a live `status` set). It does NOT consult `platform_tenants`.
3. The failure path is `_validate_nonzero_bindings_are_reconstructable`: TEST001 carried a nonzero `wholesaler_retailer_bindings.outstanding_balance` but had zero qualifying live `tenant_registrations` rows.
4. The migration therefore fail-closed with `PreflightFailure("nonzero binding balances lack live tenant registration")`.
5. `platform_tenants` being empty is contextual evidence only — it corroborates that no live onboarding occurred, but it is not the authority consulted by migration 035.

**This is the expected behavior.** The migration correctly rejects test fixture data that carries nonzero bindings without a qualifying live `tenant_registrations` row.

---

## Recommendations

1. **Do not apply migration 035 to test fixture data** — the data is synthetic and should not be migrated
2. **Clean up test fixture** (controlled): the exact, evidence-backed cleanup plan
   for TEST001 is specified in
   `ai-ledger/ops/2026-07-22_dc11t4i_r2a_test001_cleanup_design.md`
   (DC-11T4I-R2A). Both TEST001-bound retailers are exclusive to TEST001 (no
   shared retailers); the derived schema and public fixture rows are safe to
   remove in the documented transaction order. Production data is not modified
   in R2A; the plan is proven on a disposable restored copy only.
3. **Proceed with migration 035** on schemas with real customer data only
4. **The backup is intact** and can be used for rollback if needed
5. **Financial wording corrected in R1B**: the negative receivable aggregate is
   an accounting movement, not a settled balance; see E7-8 above.

---

## Backup Reference
- Path: `/home/ubuntu/.secure-backups/dc11t4i_20260722T062413Z.sql`
- Size: 874,700 bytes
- SHA256 prefix: b4380a8a8cdb5cfaad6d38b8e4992dafd59e3314ff8f8f911ba6edee5467ba02
- Status: Readable, intact

---

## VPS State
- SHA: 303dc179e94527668f4f1d2145fab74be0f48751
- 5/5 containers healthy
- No modifications made (strictly read-only investigation)
