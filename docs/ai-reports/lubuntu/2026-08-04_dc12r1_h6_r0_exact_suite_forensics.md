# DC-12R1-H6-R0: Exact-Suite Baseline/Candidate Forensics

**Date**: 2026-08-04  
**Executor**: Lubuntu Codex (Python 3.12.3, Poetry 2.4.1, PG 16.14, Redis 7.4.9)  
**Verdict**: STOP_AND_REPORT_CTO --- candidate has 7 deterministic BRANCH_PRODUCT_DEFECT failures

---

## 1. Exact SHAs

| Ref | SHA | Verified |
|-----|-----|----------|
| Baseline `origin/product-dev-recovered` | `76fb345c9054530cb0e6abccf35f0cc1863d2bef` | YES |
| Candidate `origin/codex/dc12r1-s3-s2b-i2b-r4-h5-causal-regression-2026-08-04` | `049c28d3969dd565c81fe8398f5430287b482733` | YES |
| Ancestry (baseline is ancestor of candidate) | --- | YES |

## 2. Environment Contract

| Item | Value |
|------|-------|
| Python | 3.12.3 (system) |
| PostgreSQL | 16.14 (Alpine, port 57501) |
| Redis | 7.4.9 (port 57901) |
| Test user | `mpango_test` (rolcreatedb=t, rolsuper=f) |
| Alembic head | `037_payment_declarations_schema` |
| Env vars | `MPANGO_ENV=test`, `MPANGO_ALLOW_TEMP_DB_CREATE=1`, `MPANGO_TEMP_DB_ALLOWED_PORTS=57501`, `REPORTING_USER_PASSWORD=test`, `SECRET_KEY=<32+char non-weak>` |
| DB names per stack | `test_h6_bl_a`, `test_h6_cd_a`, `test_h6_bl_b`, `test_h6_cd_b` |
| Redis flush | `FLUSHALL` before each run |
| Pytest command | `python3 -m pytest tests/ -q --tb=short` from `backend/` |

## 3. Four Full-Run Totals

| Stack | Passed | Failed | Error | Skipped | XFailed | Duration |
|-------|--------|--------|-------|---------|---------|----------|
| Baseline A | 3133 | 1 | 0 | 48 | 15 | 1243.66s |
| Baseline B | 3134 | 0 | 0 | 48 | 15 | 1155.36s |
| Candidate A | 3173 | 7 | 0 | 48 | 15 | 1279.94s |
| Candidate B | 3173 | 7 | 1 | 48 | 15 | 1289.58s |

## 4. Node-Set Comparison

### Baseline
- **Baseline A**: 1 nondeterministic failure (`test_status_or_1_equals_1_weakening_rejected`)
- **Baseline B**: clean green (0 failed, 0 error)

### Candidate (identical failure set across A and B)
1. `test_dc12r1_s3_s1_catalog_order_hardening.py::TestProvisioningRolePermissions::test_provisioned_tenant_role_permissions`
2. `test_s5a_fresh_tenant_real_user_journey_gate.py::test_s5a_fresh_tenant_real_user_journey_gate`
3. `test_u6d_verify_email_endpoint.py::test_verify_email_provisions_tenant_schema_without_admin_rbac_side_effects`
4. `test_u6f_onboarding_auth_chain_closeout.py::test_end_to_end_signup_verify_status_happy_path_is_neutral_and_provisions_without_admin`
5. `test_u6f_onboarding_auth_chain_closeout.py::test_closeout_provisions_tenant_but_defers_admin_rbac_until_setup_credential`
6. `test_u6h2_tenant_provisioning_wholesaler_schema.py::test_bootstrap_seeds_current_retailer_rbac_without_admin_grant_all`
7. `test_u6h3_tenant_provisioning_reconcile_cleanup.py::test_reconcile_seeds_current_retailer_rbac_without_admin_grant_all`

Plus Candidate B only: 1 nondeterministic error (`test_platform_p17dc_backup_migration.py::test_latest_completed_excludes_in_progress`)

**Decision Matrix**: Baseline green (B), candidate red with identical 7 nodes across A/B -> classify as **BRANCH_PRODUCT_DEFECT**.

## 5. Root Cause: `bootstrap_tenant_schema.py` Admin Role Injection

The candidate introduces a 9-line modification to `backend/scripts/bootstrap_tenant_schema.py` in `_reconcile_rbac_s1()`:

```python
# S2B-I1: ensure admin role exists BEFORE granting permissions.
await db.execute(text(
    f"INSERT INTO {roles_t} (name, description) "
    "VALUES (:name, :description) ON CONFLICT (name) DO NOTHING"
), {
    "name": ADMIN_ROLE,
    "description": "Tenant administrator with full access",
})
```

This creates an `admin` role during bare tenant bootstrap. The architectural contract (validated by 7 failing tests) is that admin role creation is **deferred** to `OwnerCredentialSetupService.create_first_admin_rbac()` during the owner credential setup lifecycle.

**Failure mechanisms**:
- Tests #6, #7: `assert not await _role_exists(schema, ADMIN_ROLE)` --- admin role exists after bootstrap
- Test #1: `admin drift` --- admin role has full `ADMIN_PERMISSION_CODES` instead of 3-permission bare set
- Test #2: `UniqueViolationError: roles_name_key` --- bootstrap-created admin role conflicts with test's INSERT
- Tests #3, #4, #5: assert "no admin RBAC side effects" after provisioning

## 6. I2B Teardown Investigation

**No I2B teardown errors reproduced** in any of the four full-suite runs or in targeted runs:
- I2B alone: 42 passed
- I2B after u6h2: 42 passed (u6h2 fails independently)
- I2B after I2A: 60 passed
- I2B in full suite: all 42 pass

The "seven reported I2B teardown errors" from Zcode's environment are not reproducible in this clean environment. Classification: **ENVIRONMENT_GATED** (specific to Zcode's construction).

## 7. H5 Source Truth

### `test_red_ddl_without_dispose_raises_stale_plan` --- FAIL-CLOSED VIOLATION
- Lines 170-173: when `stale_error is None`, the test **passes without assertion**
- This violates fail-closed RED semantics: a RED test must FAIL when the bug doesn't manifest
- The test claims "CAUSAL RED" but actually passes in both RED and GREEN states

### Global engine usage
- Test 1 (RED): uses **private** `create_async_engine()` --- NOT the global boundary
- Tests 2-4 (GREEN/PID/pg_stat_activity): correctly use `from database.session import async_engine, AsyncSessionLocal`

### `_h5_flush_stmt_cache` dependency
- Removing `_h5_flush_stmt_cache` does NOT affect H5 tests
- It DOES cause `InvalidCachedStatementError` when I2A runs before I2B (confirmed in prior session)

## 8. Redis Isolation Truth

| Pattern | Location | Risk |
|---------|----------|------|
| `rate_limit:tenant:{ws_id}:*` SCAN+DELETE | I2B test fixture | **SAFE** --- ws_id unique per provisioned tenant |
| `rate_limit:ip:{test_ip}:*` SCAN+DELETE | S2 test | **SAFE** --- random IP per run |
| `rate_limit:ip:127.0.0.1:{w}` DELETE | I2B autouse fixture | **LOW** --- shared loopback, could reset another test's counter in same 60s window |
| `invalidate_cache(pattern)` | `core/cache.py:307` | **DEAD CODE** --- never called, but unscoped if ever invoked |
| FLUSHDB / FLUSHALL | nowhere | N/A |

**Conclusion**: `rate_limit:tenant:{ws_id}:*` cannot delete keys not owned by the current test. The only cross-test hazard is the loopback IP deletion.

**Recommendation**: Replace `rate_limit:ip:127.0.0.1:{w}` with exact-key deletion or unique `X-Forwarded-For` injection.

## 9. Frontend Accessibility

**Issue**: `DeclarePaymentPage.tsx` (both `0362e7d` and `049c28d`) has `<label>` without `htmlFor` and `<input>` without `id`:

```tsx
<label className="...">Amount (KES)</label>
<input type="number" ... />
```

**Test workaround**: Uses `document.querySelector('input[type="number"]')` instead of `getByLabelText`.

**Correct repair**: Add `htmlFor="amount"` to label, `id="amount"` to input. `querySelector` is not a permanent accessibility workaround.

## 10. Accounting-Gap Proof

| Metric | Value |
|--------|-------|
| Total red nodes observed | 9 (7 deterministic + 2 nondeterministic) |
| Nodes classified | 9 |
| invalid_nodes | 0 |
| accounting_gap | 0 |

**Classification**:
- 7 'x' BRANCH_PRODUCT_DEFECT (bootstrap admin role injection)
- 2 'x' TEST_INFRASTRUCTURE (nondeterministic: alembic upgrade assertion + backup migration teardown)

## 11. Recommended Minimal Follow-up

1. **Revert `bootstrap_tenant_schema.py` admin role injection** --- the 9-line addition breaks 7 tests
2. **Fix H5 RED test** --- add `assert stale_error is not None` when the bug is expected to manifest, or convert to parametrized skip-if-not-reproducible
3. **Add `htmlFor`/`id` to `DeclarePaymentPage.tsx`** --- accessibility + test correctness
4. **Replace loopback IP Redis deletion** with `X-Forwarded-For` spoofing in I2B fixture
5. **Investigate `test_status_or_1_equals_1_weakening_rejected` flakiness** --- nondeterministic on baseline

## 12. Zcode 88/48 Classification

Zcode's reported 88 failed + 48 errors are **not reproducible** in this clean environment. The candidate produces only 7 deterministic failures (all from one root cause) + 0-1 nondeterministic errors. Zcode's result is classified as **ENVIRONMENT_GATED** --- invalid environment construction.

## 13. Cleanup Proof

All four test databases were created and dropped:
- `test_h6_bl_a` --- created, tested, dropped OK
- `test_h6_cd_a` --- created, tested, dropped OK
- `test_h6_bl_b` --- created, tested, dropped OK
- `test_h6_cd_b` --- created, tested, dropped OK

Redis flushed before each run. No residual state.
